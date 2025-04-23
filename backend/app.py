from flask import Flask, render_template, request, jsonify, session, send_from_directory, url_for
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_mail_sendgrid import MailSendGrid
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
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
from logging.handlers import RotatingFileHandler
import hashlib
from models import db

# Initialize Flask app
app = Flask(__name__, static_folder='./build', template_folder='./build')
app.config.from_object(get_config())
app.config['MAIL_SENDGRID_API_KEY'] = 'your_sendgrid_api_key_here'  # Replace with your SendGrid API key

# Configure logging
if not os.path.exists('logs'):
    os.mkdir('logs')
file_handler = RotatingFileHandler('logs/esrs_generator.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('ESGenerator startup')

# Set up rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["20000 per day", "5000 per hour"],
    storage_uri="memory://",
)

allowed_origins = os.environ.get('ALLOWED_ORIGINS', 'http://localhost:5173,http://localhost:3000').split(',')
CORS(app, 
     resources={r"/*": {"origins": allowed_origins}}, 
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# Update these session cookie settings
app.config['SESSION_COOKIE_SAMESITE'] = None  # Required for cross-origin requests with credentials
app.config['SESSION_COOKIE_SECURE'] = False   # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

# Initialize extensions
db.init_app(app)
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

# Get API key from environment variable instead of hardcoding
api_key = os.environ.get('NVIDIA_API_KEY')
if not api_key:
    api_key = "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"

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key
)

# Load vectorstore function
def load_vectorstore(db_folder):
    db_path = os.path.join("vectorstores", db_folder)
    
    if not os.path.exists(db_path):
        app.logger.error(f"Vectorstore path not found: {db_path}")
        raise FileNotFoundError(f"Vectorstore path not found: {db_path}")

    try:
        index = faiss.read_index(os.path.join(db_path, "index.faiss"))

        with open(os.path.join(db_path, "vectorstore.pkl"), "rb") as f:
            vectorstore = pickle.load(f)

        vectorstore.index = index
        return vectorstore
    except Exception as e:
        app.logger.error(f"Error loading vectorstore: {str(e)}")
        raise

# Initialize reranker
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")

# LLM response function
def get_llm_response(prompt):
    try:
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
    except Exception as e:
        app.logger.error(f"Error getting LLM response: {str(e)}")
        return "I'm sorry, I encountered an error processing your request. Please try again later."

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
try:
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
except Exception as e:
    app.logger.error(f"Error loading vector stores: {str(e)}")

# Load sector classification
try:
    with open("sector_classification.json", "r", encoding="utf-8") as f:
        special_sectors = json.load(f)
except Exception as e:
    app.logger.error(f"Error loading sector classification: {str(e)}")

# Initialize NACE chain
nace_chain = load_chain(nace_vs)

# Security helper functions
def generate_csrf_token():
    """Generate a CSRF token for form protection"""
    if 'csrf_token' not in session:
        session['csrf_token'] = hashlib.sha256(os.urandom(64)).hexdigest()
    return session['csrf_token']

def validate_csrf_token(token):
    """Validate the CSRF token from a form submission"""
    return token and 'csrf_token' in session and token == session['csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

# Routes
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.template_folder, 'index.html')

@app.route('/chat', methods=['POST'])
@limiter.limit("30 per minute")
def chat():
    user_message = request.form['message']
    app.logger.info(f"Chat message received. Session initialized: {'initialized' in session}")
    
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
    # Add CSRF protection
    if not validate_csrf_token(request.form.get('csrf_token')):
        app.logger.warning(f"CSRF token validation failed: {request.remote_addr}")
        return jsonify({'status': 'error', 'message': 'Invalid CSRF token'}), 403
        
    content = request.form.get('content', '')
    
    # Sanitize input if needed
    
    # Save to database
    document = Document(
        user_id=current_user.id,
        name=f"ESRS Report {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        content=content
    )
    db.session.add(document)
    db.session.commit()
    
    app.logger.info(f"Content saved by user {current_user.id}")
    return jsonify({'status': 'success', 'message': 'Content saved successfully'})

@app.route('/reset', methods=['POST'])
def reset_session():
    session.clear()
    return jsonify({'status': 'success'})

# Authentication routes
@app.route('/register', methods=['POST'])
@limiter.exempt  # Exempt from rate limiting for development
def register():
    try:
        data = request.json
        
        if not data or not data.get('username') or not data.get('email') or not data.get('password'):
            return jsonify({'message': 'Missing required fields'}), 400
        
        # Validate email format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, data['email']):
            return jsonify({'message': 'Invalid email format'}), 400
        
        # Password strength check
        if len(data['password']) < 8:
            return jsonify({'message': 'Password must be at least 8 characters long'}), 400
        
        # Check if user with email already exists
        if User.query.filter_by(email=data['email']).first():
            app.logger.info(f"Registration attempt with existing email: {data['email']}")
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
        try:
            verification_url = url_for('verify_email', token=user.verification_token, _external=True)
            email_service.send_verification_email(user, verification_url)
        except Exception as email_error:
            app.logger.warning(f"Failed to send verification email: {str(email_error)}")
            # Continue registration process even if email fails
        
        app.logger.info(f"New user registered: {user.username}")
        return jsonify({'message': 'User registered successfully. Please check your email to verify your account.'}), 201
    except Exception as e:
        app.logger.error(f"Registration error: {str(e)}")
        return jsonify({'message': 'An error occurred. Please try again.'}), 500

@app.route('/verify-email/<token>', methods=['GET'])
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    
    if not user:
        app.logger.warning(f"Invalid email verification attempt with token: {token}")
        return jsonify({'message': 'Invalid verification token'}), 400
    
    user.is_verified = True
    user.verification_token = None
    db.session.commit()
    
    app.logger.info(f"Email verified for user: {user.username}")
    return jsonify({'message': 'Email verified successfully. You can now log in.'}), 200

@app.route('/login', methods=['POST'])
@limiter.exempt  # Exempt from rate limiting for development
def login():
    try:
        data = request.json
        
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'message': 'Missing email or password'}), 400
        
        user = User.query.filter_by(email=data['email']).first()
        
        # Always take the same time to respond whether user exists or not (to prevent timing attacks)
        if not user or not user.check_password(data['password']):
            app.logger.warning(f"Failed login attempt for email: {data.get('email')}")
            return jsonify({'message': 'Invalid email or password'}), 401
        
        if not user.is_verified:
            return jsonify({'message': 'Please verify your email before logging in'}), 401
        
        # Log in user
        login_user(user)
        
        # Regenerate session to prevent session fixation
        session.regenerate()
        
        app.logger.info(f"User logged in: {user.username}")
        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email
            }
        }), 200
    except Exception as e:
        app.logger.error(f"Login error: {str(e)}")
        return jsonify({'message': 'An error occurred. Please try again.'}), 500

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    username = current_user.username
    logout_user()
    session.clear()
    app.logger.info(f"User logged out: {username}")
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
# @limiter.limit("5 per hour")
def forgot_password():
    data = request.json
    
    if not data or not data.get('email'):
        return jsonify({'message': 'Email address is required'}), 400
    
    user = User.query.filter_by(email=data['email']).first()
    
    # Always return success even if user not found (security)
    if not user:
        app.logger.info(f"Password reset requested for non-existent email: {data.get('email')}")
        return jsonify({'message': 'If your email is registered, you will receive a reset link'}), 200
    
    # Generate reset token
    user.reset_token = str(uuid.uuid4())
    user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
    db.session.commit()
    
    # Send password reset email
    reset_url = url_for('reset_password_page', token=user.reset_token, _external=True)
    email_service.send_password_reset_email(user, reset_url)
    
    app.logger.info(f"Password reset link sent to: {user.email}")
    return jsonify({'message': 'If your email is registered, you will receive a reset link'}), 200

@app.route('/reset-password/<token>', methods=['GET'])
def reset_password_page(token):
    user = User.query.filter_by(reset_token=token).first()
    
    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        app.logger.warning(f"Invalid password reset attempt with token: {token}")
        return jsonify({'message': 'Invalid or expired reset token'}), 400
    
    # Return a page that allows the user to enter a new password
    return render_template('reset_password.html', token=token, csrf_token=generate_csrf_token())

@app.route('/reset-password', methods=['POST'])
# @limiter.limit("5 per hour")
def reset_password():
    data = request.json
    
    if not data or not data.get('token') or not data.get('password'):
        return jsonify({'message': 'Missing required fields'}), 400
    
    # Validate CSRF token
    if not validate_csrf_token(data.get('csrf_token')):
        app.logger.warning("CSRF token validation failed in password reset")
        return jsonify({'message': 'Invalid request'}), 403
    
    user = User.query.filter_by(reset_token=data['token']).first()
    
    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        app.logger.warning(f"Invalid password reset attempt with token: {data.get('token')}")
        return jsonify({'message': 'Invalid or expired reset token'}), 400
    
    # Password strength check
    if len(data['password']) < 8:
        return jsonify({'message': 'Password must be at least 8 characters long'}), 400
    
    user.set_password(data['password'])
    user.reset_token = None
    user.reset_token_expiry = None
    db.session.commit()
    
    app.logger.info(f"Password reset successful for user: {user.username}")
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

@app.route('/user/update-profile', methods=['POST'])
@login_required
def update_user_profile():
    data = request.json
    
    # Validate CSRF token
    if not validate_csrf_token(data.get('csrf_token')):
        app.logger.warning("CSRF token validation failed in profile update")
        return jsonify({'message': 'Invalid request'}), 403
    
    if data.get('username') and data['username'] != current_user.username:
        # Check if username is already taken
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'message': 'Username already taken'}), 400
        current_user.username = data['username']
    
    if data.get('password'):
        # Password strength check
        if len(data['password']) < 8:
            return jsonify({'message': 'Password must be at least 8 characters long'}), 400
        
        # Verify current password
        if not current_user.check_password(data.get('current_password', '')):
            app.logger.warning(f"Failed password change attempt for user: {current_user.username}")
            return jsonify({'message': 'Current password is incorrect'}), 400
            
        current_user.set_password(data['password'])
    
    db.session.commit()
    
    app.logger.info(f"Profile updated for user: {current_user.username}")
    return jsonify({'message': 'Profile updated successfully'}), 200

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

@app.route('/user/conversation/<int:conversation_id>', methods=['GET'])
@login_required
def get_conversation_details(conversation_id):
    conversation = Conversation.query.filter_by(id=conversation_id, user_id=current_user.id).first()
    
    if not conversation:
        return jsonify({'message': 'Conversation not found'}), 404
    
    answers = Answer.query.filter_by(conversation_id=conversation_id).order_by(Answer.created_at).all()
    
    answers_data = []
    for answer in answers:
        answers_data.append({
            'id': answer.id,
            'question': answer.question,
            'answer': answer.answer,
            'created_at': answer.created_at.isoformat()
        })
    
    return jsonify({
        'id': conversation.id,
        'title': conversation.title,
        'nace_sector': conversation.nace_sector,
        'esrs_sector': conversation.esrs_sector,
        'company_description': conversation.company_description,
        'created_at': conversation.created_at.isoformat(),
        'answers': answers_data
    }), 200

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

@app.route('/user/document/<int:document_id>', methods=['GET'])
@login_required
def get_document_content(document_id):
    document = Document.query.filter_by(id=document_id, user_id=current_user.id).first()
    
    if not document:
        return jsonify({'message': 'Document not found'}), 404
    
    return jsonify({
        'id': document.id,
        'name': document.name,
        'content': document.content,
        'created_at': document.created_at.isoformat()
    }), 200

@app.route('/user/document/<int:document_id>', methods=['DELETE'])
@login_required
def delete_document(document_id):
    document = Document.query.filter_by(id=document_id, user_id=current_user.id).first()
    
    if not document:
        return jsonify({'message': 'Document not found'}), 404
    
    db.session.delete(document)
    db.session.commit()
    
    app.logger.info(f"Document deleted by user {current_user.id}: {document_id}")
    return jsonify({'message': 'Document deleted successfully'}), 200

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
