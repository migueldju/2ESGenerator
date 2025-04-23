import os
from flask import Flask
from flask_mail import Mail, Message

app = Flask(__name__)
app.config['SECRET_KEY'] = 'top-secret!'
app.config['MAIL_SERVER'] = 'smtp.sendgrid.net'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'apikey'
app.config['MAIL_PASSWORD'] = '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'
app.config['MAIL_DEFAULT_SENDER'] = 'esgeneratornoreply@gmail.com'

mail = Mail(app)

with app.app_context():
    msg = Message('Twilio SendGrid Test Email', recipients=['recipient@example.com'])
    msg.body = 'This is a test email!'
    msg.html = '<p>This is a test email!</p>'
    
    try:
        mail.send(msg)
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
