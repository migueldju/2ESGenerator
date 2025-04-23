import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate
from flask_mail_sendgrid import MailSendGrid
from flask_mail import Message

import ssl

class EmailService:
    def __init__(self, app=None):
        if app:
            self.logger = logging.getLogger(__name__)
            self.init_app(app)
        self.mail = MailSendGrid(app)
            
            
    def init_app(self, app):
        self.host = app.config.get('MAIL_SERVER')
        self.port = app.config.get('MAIL_PORT')
        self.username = app.config.get('MAIL_USERNAME')
        self.password = app.config.get('MAIL_PASSWORD')
        self.use_tls = app.config.get('MAIL_USE_TLS', False)
        self.use_ssl = app.config.get('MAIL_USE_SSL', False)
        self.sender = app.config.get('MAIL_DEFAULT_SENDER')
        
        self.sendgrid_api_key = app.config.get('MAIL_SENDGRID_API_KEY')
        
        if self.host == 'smtp.sendgrid.net' and self.sendgrid_api_key:
            self.username = 'apikey'
            self.password = self.sendgrid_api_key

        self.logger.info(f"Email service configured with server: {self.host}:{self.port}")
        self.logger.info(f"Email TLS: {self.use_tls}, SSL: {self.use_ssl}")
        self.logger.info(f"Using SendGrid: {self.host == 'smtp.sendgrid.net'}")
        
        self.email_enabled = bool(self.host and self.port and (
            (self.username and self.password) or 
            (self.host != 'smtp.sendgrid.net')
        ))
        
        if not self.email_enabled:
            self.logger.warning("Email service not fully configured - emails will be logged but not sent")
            
    def send_email(self, to, subject, template):
        """Send an email with proper security settings"""
        try:
            # Create email message
            msg = Message("Hello",
            sender="from@example.com",
            mail_options={'from_name': 'John'},
            recipients=[to])
            msg.html = template
            msg.subject = subject
            self.mail.send(msg)
            self.logger.info(f"Email sent successfully to {to}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send email: {str(e)}")
            return False
            
    def send_verification_email(self, user, verification_url):
        """Send an email verification link to a new user"""
        subject = "Verify Your Email Address - ESGenerator"
        template = f"""
        <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #4CAF50; color: white; padding: 10px; text-align: center; }}
                    .content {{ padding: 20px; }}
                    .button {{ background-color: #4CAF50; color: white; padding: 10px 20px; 
                              text-decoration: none; border-radius: 5px; display: inline-block; }}
                    .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Welcome to ESGenerator</h1>
                    </div>
                    <div class="content">
                        <p>Hello {user.username},</p>
                        <p>Thank you for registering with ESGenerator. To complete your registration, please verify your email address by clicking the button below:</p>
                        <p style="text-align: center;">
                            <a href="{verification_url}" class="button">Verify Email Address</a>
                        </p>
                        <p>If the button doesn't work, please copy and paste the following link into your browser:</p>
                        <p>{verification_url}</p>
                        <p>This link will expire in 24 hours.</p>
                        <p>Best regards,<br>The ESGenerator Team</p>
                    </div>
                    <div class="footer">
                        <p>If you did not create an account, please ignore this email.</p>
                        <p>This is an automated message, please do not reply.</p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        return self.send_email(user.email, subject, template)
        
    def send_password_reset_email(self, user, reset_url):
        """Send a password reset link to a user"""
        subject = "Reset Your Password - ESGenerator"
        template = f"""
        <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #2196F3; color: white; padding: 10px; text-align: center; }}
                    .content {{ padding: 20px; }}
                    .button {{ background-color: #2196F3; color: white; padding: 10px 20px; 
                              text-decoration: none; border-radius: 5px; display: inline-block; }}
                    .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>ESGenerator Password Reset</h1>
                    </div>
                    <div class="content">
                        <p>Hello {user.username},</p>
                        <p>We received a request to reset your password. If you made this request, please click the button below to reset your password:</p>
                        <p style="text-align: center;">
                            <a href="{reset_url}" class="button">Reset Password</a>
                        </p>
                        <p>If the button doesn't work, please copy and paste the following link into your browser:</p>
                        <p>{reset_url}</p>
                        <p>This link will expire in 1 hour.</p>
                        <p>If you did not request a password reset, please ignore this email or contact support if you have concerns.</p>
                        <p>Best regards,<br>The ESGenerator Team</p>
                    </div>
                    <div class="footer">
                        <p>This is an automated message, please do not reply.</p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        return self.send_email(user.email, subject, template)
        
    def send_notification_email(self, user, subject, message):
        """Send a general notification email to a user"""
        template = f"""
        <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #2a66b3; color: white; padding: 10px; text-align: center; }}
                    .content {{ padding: 20px; }}
                    .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>ESGenerator Notification</h1>
                    </div>
                    <div class="content">
                        <p>Hello {user.username},</p>
                        {message}
                        <p>Best regards,<br>The ESGenerator Team</p>
                    </div>
                    <div class="footer">
                        <p>This is an automated message, please do not reply.</p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        return self.send_email(user.email, subject, template)