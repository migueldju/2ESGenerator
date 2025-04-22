import os
import nltk
import warnings
import faiss
import pickle
from langchain.text_splitter import SentenceTransformersTokenTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_huggingface import HuggingFaceEmbeddings

warnings.filterwarnings("ignore")


def split_into_sentences(text):
    return nltk.sent_tokenize(text)


def load_documents(folder_path):
    documents = []
    text_splitter = SentenceTransformersTokenTextSplitter(chunk_size=300, chunk_overlap=60)

    for doc in os.listdir(folder_path):
        file_path = os.path.join(folder_path, doc)

        if doc.lower().endswith('.pdf'):
            loader = PyPDFLoader(file_path)
            pdf_docs = loader.load()
            for doc in pdf_docs:
                doc.page_content = "\n".join(split_into_sentences(doc.page_content)) 
                split_docs = text_splitter.split_documents([doc])
                documents.extend(split_docs)

        elif doc.lower().endswith('.txt'):
            loader = TextLoader(file_path, encoding="utf-8")
            loaded_docs = loader.load()

            for doc in loaded_docs:
                doc.page_content = "\n".join(split_into_sentences(doc.page_content)) 
                split_docs = text_splitter.split_documents([doc]) 
                documents.extend(split_docs)

    return documents

# Creamos el vectorstore en FAISS y guardarlo en una carpeta específica
def create_vectorstore(documents, folder_path):
    os.makedirs(folder_path, exist_ok=True)  # Crear carpeta si no existe

    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vectorstore = FAISS.from_documents(documents, embedding=embeddings)

    # Guardar el índice FAISS y la metadata con Pickle en la carpeta
    faiss.write_index(vectorstore.index, os.path.join(folder_path, "index.faiss"))
    with open(os.path.join(folder_path, "vectorstore.pkl"), "wb") as f:
        pickle.dump(vectorstore, f)

    return vectorstore

def save_vs(docs_path, db_folder):
    docs = load_documents(docs_path)
    return create_vectorstore(docs, db_folder)

# Directorios de documentos y nombres de bases de datos (crear carpetas con estos nombres)
paths = {
    "NACE": "vectorstores/nace_db",
    "Agnostic Standards": "vectorstores/default_db",
    "Oil & Gas Company": "vectorstores/oil_gas_db",
    "Mining, Quarrying and Coal": "vectorstores/mining_db",
    "Road Transport": "vectorstores/road_db"
}

# Crear los vectorstores en sus respectivas carpetas
for folder, db_name in paths.items():
    save_vs(folder, db_name)
