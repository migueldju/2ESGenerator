import os
import json
import re
import warnings
import faiss
import pickle
from langchain.chains import RetrievalQA
from sentence_transformers import CrossEncoder
from openai import OpenAI
from langchain_core.runnables import Runnable
from langchain_community.vectorstores import FAISS

warnings.filterwarnings("ignore")

client = OpenAI(
  base_url="https://integrate.api.nvidia.com/v1",
  api_key="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"
)

def load_vectorstore(db_folder):
    """Carga el vectorstore desde su carpeta correspondiente."""
    db_path = os.path.join("vectorstores", db_folder)

    index = faiss.read_index(os.path.join(db_path, "index.faiss"))

    with open(os.path.join(db_path, "vectorstore.pkl"), "rb") as f:
        vectorstore = pickle.load(f)

    vectorstore.index = index
    return vectorstore

reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")

def get_llm_response(prompt):
    completion = client.chat.completions.create(
        model="nvidia/llama-3.3-nemotron-super-49b-v1",
        messages=[{"role": "system", "content": "Be brief."
        "Only return the most COMPLETE and accurate answer. "
        "Avoid explanations, introductions, and additional context. "
        "No need to introduce a summary at the end. "},
                  {"role": "user", "content": prompt}],
        temperature=0.05,
        top_p=0.1,
        max_tokens=2048,
        frequency_penalty=0.1,
        presence_penalty=0,
        stream=False
    )
    return completion.choices[0].message.content.strip()

class NvidiaLLM(Runnable):
    def invoke(self, input):
        return get_llm_response(input["query"])

def load_chain(vectorstore):
    retriever = vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": 10})
    return RetrievalQA.from_chain_type(
        llm=NvidiaLLM(),
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True
    )

print("Welcome to ESGenerator")
print("Loading vectorstores...")

nace_vs = load_vectorstore("nace_db")
default_vs = load_vectorstore("default_db")

company_desc = input("Describe your company so I can know which sector it belongs: ")

nace_chain = load_chain(nace_vs)
nace_sector = None

retrieved_docs = nace_vs.similarity_search(company_desc, k=3)

ranked_docs = sorted(
    retrieved_docs,
    key=lambda doc: reranker.predict([(company_desc, doc.page_content)]),
    reverse=True
)[:3]

context = "\n".join([doc.page_content for doc in ranked_docs])

contextual_query = f"""
You are a NACE classification assistant.
Your job is to identify and return the exact NACE code.

Instructions:
- Analyze the company description.
- Use the context provided for reference.
- Respond with ONLY the NACE code (e.g., 'A01.1' or 'B05').
- Don't forget to include the letter

Company description:
{company_desc}

Context:
{context}
"""

nace_result = get_llm_response(contextual_query)

nace_result = re.sub(r'(\b[a-u]\b)', lambda m: m.group(1).upper(), nace_result)
nace_result = re.sub(r'\.\s+', '.', nace_result)

print(nace_result)

match = re.search(r'([A-U](\d{1,2})(\.\d{1,2}){0,2})', nace_result)

if match:
    nace_sector = match.group(1)
    print(f"Company sector according to NACE: {nace_sector}")
else:
    nace_sector = "agnostic"
    print("Could not determine exact NACE code. Using agnostic standards.")

with open("sector_classification.json", "r", encoding="utf-8") as f:
    special_sectors = json.load(f)

esrs_sector = special_sectors.get(nace_sector, "")

sector_db_map = {
    "Oil & Gas Company": "oil_gas_db",
    "Mining, Quarrying and Coal": "mining_db",
    "Road Transport": "road_db"
}

qa_vs = default_vs

if esrs_sector in sector_db_map:
    specific_vs = load_vectorstore(sector_db_map[esrs_sector])
    qa_vs.merge_from(specific_vs)

qa_chain = load_chain(qa_vs)

conversation_history = [
    f"Company description: {company_desc}",
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
    Instructions:
    - Follow the ESRS standards.
    - Use the context provided for reference.
    - No need to include summary tables
    - Answer must be complete and accurate
    - Give brief and concise answers
    - Prioritize information quality over aesthetics
    - Don't show tables, only plain text
    - GIVE SPECIAL ATTENTION TO THE CONTEXT
    Question: {question}
    Context:
    {context}
    Take into account the previous conversation:
    {conversation_history}
    """

    answer = get_llm_response(contextual_query)

    print(f"\nA: {answer}\n")

    conversation_history.append(f"Q: {question}")
    conversation_history.append(f"A: {answer}")