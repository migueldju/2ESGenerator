import os
import json
import re
import warnings
import faiss
import pickle
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain_huggingface import HuggingFaceEmbeddings
from sentence_transformers import CrossEncoder
from langchain_community.llms import Ollama

warnings.filterwarnings("ignore")

# Cargar FAISS desde archivo
def load_vectorstore(db_folder):
    """Carga el vectorstore desde su carpeta correspondiente."""
    db_path = os.path.join("vectorstores", db_folder)

    index = faiss.read_index(os.path.join(db_path, "index.faiss"))

    with open(os.path.join(db_path, "vectorstore.pkl"), "rb") as f:
        vectorstore = pickle.load(f)

    vectorstore.index = index 
    return vectorstore


reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")

llm = Ollama(model="llama3.2:1b", temperature=0.2, num_ctx=2048)

def load_chain(llm, vectorstore):
    retriever = vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": 10})  # Búsqueda híbrida
    return RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True
    )

print("Welcome to ESGenerator")
print("Loading vectorstores...")

nace_vs = load_vectorstore("nace_db")
default_vs = load_vectorstore("default_db")

company_desc = input("Describe your company so I can know which sector it belongs: ")

nace_chain = load_chain(llm, nace_vs)
nace_sector = None

for _ in range(2):
    result = nace_chain({"query": f"According to NACE, which sector CODE does this company belong to: {company_desc}? Only the code."})
    match = re.search(r'([A-U](\d{1,2})(\.\d{1,2}){0,2})', result['result'].strip())
    
    if match:
        nace_sector = match.group(1)
        print(f"Company sector according to NACE: {nace_sector}")
        break

if not nace_sector:
    nace_sector = "agnostic"
    print("Could not determine exact NACE code. Using agnostic standards.")

with open("sector_classification.json", "r", encoding="utf-8") as f:
    special_sectors = json.load(f)

esrs_sector = special_sectors.get(nace_sector, "nothing else")

sector_db_map = {
    "Oil & Gas Standards": "oil_gas_db",
    "Mining, Quarrying and Coal Standards": "mining_db",
    "Road Transport Standards": "road_db"
}

qa_vs = default_vs

if esrs_sector in sector_db_map:
    specific_vs = load_vectorstore(sector_db_map[esrs_sector])
    
    if hasattr(qa_vs, "merge_from") and hasattr(specific_vs, "merge_from"):
        qa_vs.merge_from(specific_vs)
    else:
        print(f"Warning: Could not merge {esrs_sector}. Using default database.")

qa_chain = load_chain(llm, qa_vs)

conversation_history = [
    f"Company description: {company_desc}",
    f"NACE sector code: {nace_sector}",
    f"ESRS standards to follow: Agnostic Standards + {esrs_sector}"
]

print("Ask your questions:")
while True:
    question = input("\nQ: ")
    
    retrieved_docs = qa_vs.similarity_search(question, k=10)

    ranked_docs = sorted(
        retrieved_docs, 
        key=lambda doc: reranker.predict([(question, doc.page_content)]), 
        reverse=True
    )[:5]

    context = "\n".join([doc.page_content for doc in ranked_docs])
    print(context)
    contextual_query = f"""
    Answer based on previous conversation and company information.
    Follow the ESRS standards. 
    Context:
    {context}
    
    Question: {question}
    """

    result = qa_chain({"query": contextual_query})
    answer = result.get('result', '').strip()

    
    print(f"\nA: {answer}\n")
    
    conversation_history.append(f"Q: {question}")
    conversation_history.append(f"A: {answer}")
