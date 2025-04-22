from flask import Flask, render_template, request, jsonify, session, send_from_directory
from flask_cors import CORS
import os
import json
import re
import warnings
import faiss
import pickle
import markdown
from langchain.chains import RetrievalQA
from sentence_transformers import CrossEncoder
from openai import OpenAI
from langchain_core.runnables import Runnable

app = Flask(__name__, static_folder='./build', template_folder='./build')
app.secret_key = 'esrs_generator_secret_key'
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "http://localhost:5173"}})

app.config['SESSION_COOKIE_SAMESITE'] = 'None' 
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.template_folder, 'index.html')

warnings.filterwarnings("ignore")

client = OpenAI(
  base_url="https://integrate.api.nvidia.com/v1",
  api_key="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"
)

def load_vectorstore(db_folder):
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
        temperature=0,
        top_p=0.1,
        max_tokens=112000,
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


nace_vs = load_vectorstore("nace_db")
default_vs = load_vectorstore("default_db")

sector_vectorstores = {}
merged_vectorstores = {}

sector_db_map = {
    "Oil & Gas Company": "oil_gas_db",
    "Mining, Quarrying and Coal": "mining_db",
    "Road Transport": "road_db"
}

for sector, db_name in sector_db_map.items():
    sector_vectorstores[sector] = load_vectorstore(db_name)

    sector_vs = sector_vectorstores[sector]

    default_docs = default_vs.similarity_search("", k=100000)  
    
    sector_docs = sector_vs.similarity_search("", k=100000) 
    
    all_docs = default_docs + sector_docs
    
    merged_vectorstores[sector] = {
        'vectorstore': sector_vs,
        'docs': all_docs
    }

with open("sector_classification.json", "r", encoding="utf-8") as f:
    special_sectors = json.load(f)

nace_chain = load_chain(nace_vs)

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.form['message']
    print("Session:", session)
    
    if 'initialized' not in session:
        company_desc = user_message
        result = process_company_description(company_desc)
        
        session['initialized'] = True
        session['company_desc'] = company_desc
        session['nace_sector'] = result['nace_sector']
        session['esrs_sector'] = result['esrs_sector']
        session['conversation_history'] = [
            f"Company description: {company_desc}",
            f"ESRS standards to follow: {'Agnostic Standards' if result['esrs_sector'] == 'Agnostic' else f'Agnostic Standards + {result['esrs_sector']}'}"
        ]
        
        session.modified = True
        
        return jsonify({
            'answer': f"Thank you for your company description. Based on my analysis, your company falls under NACE sector {result['nace_sector']}. How can I help you with your ESRS reporting requirements?",
            'context': '',
            'is_first_message': True,
            'nace_sector': result['nace_sector'],
            'esrs_sector': result['esrs_sector']
        })
    else:
        response = process_question(user_message)
        session.modified = True
        return response
    
@app.route('/check_session', methods=['GET'])
def check_session():
    if 'initialized' in session:
        return jsonify({
            'initialized': True,
            'nace_sector': session.get('nace_sector', ''),
            'esrs_sector': session.get('esrs_sector', '')
        })
    return jsonify({'initialized': False})

@app.route('/save_content', methods=['POST'])
def save_content():
    content = request.form.get('content', '')
    # Here you would save the content to a database or file
    # For now, we'll just return success
    return jsonify({'status': 'success', 'message': 'Content saved successfully'})

@app.route('/reset', methods=['POST'])
def reset_session():
    session.clear()
    return jsonify({'status': 'success'})

def process_company_description(company_desc):
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
    
    match = re.search(r'([A-U](\d{1,2})(\.\d{1,2}){0,2})', nace_result)
    
    if match:
        nace_sector = match.group(1)
        print(f"Company sector according to NACE: {nace_sector}") 
        esrs_sector = special_sectors.get(nace_sector, "Agnostic")
    else:
        nace_sector = "Agnostic"
        print("Could not determine exact NACE code. Using agnostic standards.") 
        esrs_sector = "Agnostic"
    
    return {
        'nace_sector': nace_sector,
        'esrs_sector': esrs_sector
    }

def process_question(question):
    company_desc = session.get('company_desc', '')
    nace_sector = session.get('nace_sector', 'agnostic')
    esrs_sector = session.get('esrs_sector', 'Agnostic')
    conversation_history = session.get('conversation_history', [])
    
    qa_vs = default_vs
    
    if esrs_sector in sector_db_map:
        merged_data = merged_vectorstores.get(esrs_sector)
        
        if merged_data:
            qa_vs = merged_data['vectorstore']
    
    retrieved_docs = qa_vs.similarity_search(question, k=10)
    
    ranked_docs = sorted(
        retrieved_docs,
        key=lambda doc: reranker.predict([(question, doc.page_content)]),
        reverse=True
    )[:5]
    
    context = "\n".join([doc.page_content for doc in ranked_docs])
    
    contextual_query = f"""
    Instructions:
    - Follow the ESRS standards.
    - Use the context provided for reference.
    - No need to include summary tables
    - Answer must be complete and accurate
    - Give brief and concise answers
    - Prioritize information quality over aesthetics
    - Don't show tables, only plain text
    - Don't say what was provided in context
    - Give answer in markdown format
    - Don't include numeric lists, only bullet points
    Question: {question}
    Context:
    {context}
    Take into account the previous conversation:
    {conversation_history}
    """
    
    answer = get_llm_response(contextual_query)
    answer = markdown.markdown(answer, extensions=['tables', 'md_in_html'])
    
    conversation_history.append(f"Q: {question}")
    conversation_history.append(f"A: {answer}")
    session['conversation_history'] = conversation_history
    
    return jsonify({
        'answer': answer,
        'context': context,
        'is_first_message': False
    })

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)