from flask import Flask
from models import db, User, Conversation, Answer, Document
from config import get_config
import os

# Create a minimal app for initializing the database
app = Flask(__name__)
app.config.from_object(get_config())

db.init_app(app)

with app.app_context():
    db.create_all()
    print("Database tables created successfully!")
    
    # Check if tables were created
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    
    print("\nTables in the database:")
    for table_name in inspector.get_table_names():
        print(f"- {table_name}")
        
    print("\nColumns in 'users' table:")
    for column in inspector.get_columns('users'):
        print(f"- {column['name']}: {column['type']}")

if __name__ == "__main__":
    print("Initializing database...")