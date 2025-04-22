from flask import Flask, render_template, request, jsonify, session, send_from_directory, url_for, redirect
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
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
from datetime import datetime, timedelta
import uuid
from email_service import EmailService
from config import get_config

# Initialize Flask app
app = Flask(__name__, static_folder='./build', template_folder='./build')
app.config.from_object(get_config())

# Enable CORS
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "http://localhost:5173"}})

# Set session cookie settings
app.config['SESSION_COOKIE_SAMESITE'] = 'None' 
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Initialize email service
email_service = EmailService(app)

# Suppress warnings
warnings.filterwarnings("ignore")

# Import models
from models import User, Conversation, Answer, Document

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


client = OpenAI(
  base_url="https://integrate.api.nvidia.com/v1",
  api_key="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"
)

# Load vectorstore function
def load_vectorstore(db_folder):
    db_path = os.path.join("vectorstores", db_folder)

    index = faiss.read_index(os.path.join(db_path, "index.faiss"))

    with open(os.path.join(db_path, "vectorstore.pkl"), "rb") as f:
        vectorstore = pickle.load(f)

    vectorstore.index = index
    return vectorstore

# Initialize reranker
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")

# LLM response function
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

# Custom NvidiaLLM class
class NvidiaLLM(Runnable):
    def invoke(self, input):
        return get_llm_response(input["query"])

# Load chain function
def load_chain(vectorstore):
    retriever = vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": 10})
    return RetrievalQA.from_chain_type(
        llm=NvidiaLLM(),
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True
    )

# Load vectorstores
nace_vs = load_vectorstore("nace_db")
default_vs = load_vectorstore("default_db")

# Sector vectorstores
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

# Load sector classification
with open("sector_classification.json", "r", encoding="utf-8") as f:
    special_sectors = json.load(f)

# Initialize NACE chain
nace_chain = load_chain(nace_vs)

# Routes
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.template_folder, 'index.html')

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
        
        # If user is authenticated, save the conversation
        if current_user.is_authenticated:
            conversation = Conversation(
                user_id=current_user.id,
                nace_sector=result['nace_sector'],
                title="Conversation " + datetime.now().strftime("%Y-%m-%d %H:%M"),
                esrs_sector=result['esrs_sector'],
                company_description=company_desc
            )
            db.session.add(conversation)
            db.session.commit()
            session['conversation_id'] = conversation.id
        
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
@login_required
def save_content():
    content = request.form.get('content', '')
    
    # Save to database
    document = Document(
        user_id=current_user.id,
        name=f"ESRS Report {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        content=content
    )
    db.session.add(document)
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'Content saved successfully'})

@app.route('/reset', methods=['POST'])
def reset_session():
    session.clear()
    return jsonify({'status': 'success'})

# Authentication routes
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    
    if not data or not data.get('username') or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Missing required fields'}), 400
    
    # Check if user with email already exists
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'message': 'Email already registered'}), 400
    
    # Check if username is taken
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'message': 'Username already taken'}), 400
    
    # Create new user
    user = User(
        username=data['username'],
        email=data['email']
    )
    
    # Set password
    user.set_password(data['password'])
    
    # Generate verification token
    user.verification_token = str(uuid.uuid4())
    
    # Save user to database
    db.session.add(user)
    db.session.commit()
    
    # Send verification email
    verification_url = url_for('verify_email', token=user.verification_token, _external=True)
    email_service.send_verification_email(user, verification_url)
    
    return jsonify({'message': 'User registered successfully. Please check your email to verify your account.'}), 201

@app.route('/verify-email/<token>', methods=['GET'])
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    
    if not user:
        return jsonify({'message': 'Invalid verification token'}), 400
    
    user.is_verified = True
    user.verification_token = None
    db.session.commit()
    
    return jsonify({'message': 'Email verified successfully. You can now log in.'}), 200

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Missing email or password'}), 400
    
    user = User.query.filter_by(email=data['email']).first()
    
    if not user or not user.check_password(data['password']):
        return jsonify({'message': 'Invalid email or password'}), 401
    
    if not user.is_verified:
        return jsonify({'message': 'Please verify your email before logging in'}), 401
    
    # Log in user
    login_user(user)
    
    return jsonify({
        'message': 'Login successful',
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email
        }
    }), 200

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logout successful'}), 200

@app.route('/check-auth', methods=['GET'])
def check_auth():
    if current_user.is_authenticated:
        return jsonify({
            'isAuthenticated': True,
            'username': current_user.username,
            'email': current_user.email,
            'id': current_user.id
        }), 200
    else:
        return jsonify({'isAuthenticated': False}), 200

@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.json
    
    if not data or not data.get('email'):
        return jsonify({'message': 'Email address is required'}), 400
    
    user = User.query.filter_by(email=data['email']).first()
    
    # Always return success even if user not found (security)
    if not user:
        return jsonify({'message': 'If your email is registered, you will receive a reset link'}), 200
    
    # Generate reset token
    user.reset_token = str(uuid.uuid4())
    user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
    db.session.commit()
    
    # Send password reset email
    reset_url = url_for('reset_password_page', token=user.reset_token, _external=True)
    email_service.send_password_reset_email(user, reset_url)
    
    return jsonify({'message': 'If your email is registered, you will receive a reset link'}), 200

@app.route('/reset-password/<token>', methods=['GET'])
def reset_password_page(token):
    user = User.query.filter_by(reset_token=token).first()
    
    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        return jsonify({'message': 'Invalid or expired reset token'}), 400
    
    # Return a page that allows the user to enter a new password
    return render_template('reset_password.html', token=token)

@app.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.json
    
    if not data or not data.get('token') or not data.get('password'):
        return jsonify({'message': 'Missing required fields'}), 400
    
    user = User.query.filter_by(reset_token=data['token']).first()
    
    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        return jsonify({'message': 'Invalid or expired reset token'}), 400
    
    user.set_password(data['password'])
    user.reset_token = None
    user.reset_token_expiry = None
    db.session.commit()
    
    return jsonify({'message': 'Password reset successful. You can now log in.'}), 200

# User profile routes
@app.route('/user/profile', methods=['GET'])
@login_required
def get_user_profile():
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'email': current_user.email,
        'created_at': current_user.created_at.isoformat()
    }), 200

@app.route('/user/conversations', methods=['GET'])
@login_required
def get_user_conversations():
    conversations = Conversation.query.filter_by(user_id=current_user.id).order_by(Conversation.created_at.desc()).all()
    
    result = []
    for conversation in conversations:
        result.append({
            'id': conversation.id,
            'title': conversation.title,
            'nace_sector': conversation.nace_sector,
            'esrs_sector': conversation.esrs_sector,
            'created_at': conversation.created_at.isoformat()
        })
    
    return jsonify(result), 200

@app.route('/user/documents', methods=['GET'])
@login_required
def get_user_documents():
    documents = Document.query.filter_by(user_id=current_user.id).order_by(Document.created_at.desc()).all()
    
    result = []
    for document in documents:
        result.append({
            'id': document.id,
            'name': document.name,
            'created_at': document.created_at.isoformat()
        })
    
    return jsonify(result), 200

# Helper functions
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
    
    # If user is authenticated and conversation exists, save the answer
    if current_user.is_authenticated and 'conversation_id' in session:
        answer_record = Answer(
            conversation_id=session['conversation_id'],
            question=question,
            answer=answer
        )
        db.session.add(answer_record)
        db.session.commit()
    
    return jsonify({
        'answer': answer,
        'context': context,
        'is_first_message': False
    })

if __name__ == '__main__':
    # Create tables if they don't exist
    with app.app_context():
        db.create_all()
    app.run(debug=True, use_reloader=False)