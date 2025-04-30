import logging
from flask_mail_sendgrid import MailSendGrid
from flask_mail import Message
import os

class EmailService:
    def __init__(self, app=None):
        self.logger = logging.getLogger(__name__)
        self.sender = None
        self.mail = None
        self.email_enabled = False
        self.frontend_url = None
        if app:
            self.init_app(app)

    def init_app(self, app):
        self.sender = app.config.get('MAIL_DEFAULT_SENDER')
        self.mail = MailSendGrid(app)
        self.email_enabled = bool(app.config.get('MAIL_SENDGRID_API_KEY'))
        self.frontend_url = app.config.get('FRONTEND_URL', os.environ.get('FRONTEND_URL', 'http://localhost:5173'))

        self.logger.info(f"Email service configured with sender: {self.sender}")
        self.logger.info(f"Using SendGrid API key: {'Configured' if self.email_enabled else 'Not configured'}")
        self.logger.info(f"Frontend URL for email links: {self.frontend_url}")

        if not self.email_enabled:
            self.logger.warning("Email service not fully configured - emails will be logged but not sent")

    def send_email(self, to, subject, html_body):
        """Send an email with proper security settings"""
        try:
            if not self.email_enabled:
                self.logger.info(f"[EMAIL LOGGING] Would send to {to} | Subject: {subject}")
                self.logger.info(f"[EMAIL CONTENT] {html_body[:200]}...")
                return True

            msg = Message(subject=subject, recipients=[to], html=html_body, sender=self.sender)
            self.mail.send(msg)
            self.logger.info(f"Email sent successfully to {to}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send email to {to}: {e}")
            return False

    def _wrap_template(self, header_title, username, content_html):
        """Wrap core content in a styled email layout"""
        return f"""
        <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; color: #000000; line-height: 1.6; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #004aad; color: white; text-align: center; padding: 10px; }}
                    .content {{ padding: 20px; }}
                    .button {{ background-color: #004aad; color: white !important; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; }}
                    .button-text {{ color: white !important; text-decoration: none; }}
                    .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header"><h1>{header_title}</h1></div>
                    <div class="content">
                        <p>Hello {username},</p>
                        {content_html}
                        <p>Best regards,<br>The ESGenerator Team</p>
                    </div>
                    <div class="footer">
                        <p>This is an automated message, please do not reply.</p>
                    </div>
                </div>
            </body>
        </html>
        """

    def send_verification_email(self, user, verification_url):
        if not verification_url.startswith(self.frontend_url) and '/verify-email/' in verification_url:
            token = verification_url.split('/verify-email/')[1]
            verification_url = f"{self.frontend_url}/verify-email/{token}"
            
        content = f"""
            <p>Thank you for registering with ESGenerator. Please verify your email by clicking below:</p>
            <p style="text-align: center;">
                <a href="{verification_url}" class="button"><span class="button-text">Verify Email Address</span></a>
            </p>
            <p>If the button doesn't work, copy this link into your browser:</p>
            <p>{verification_url}</p>
            <p>This link will expire in 24 hours.</p>
        """
        html = self._wrap_template("Welcome to ESGenerator", user.username, content)
        return self.send_email(user.email, "Verify Your Email Address - ESGenerator", html)

    def send_password_reset_email(self, user, reset_url):
        if not reset_url.startswith(self.frontend_url) and '/reset-password/' in reset_url:
            token = reset_url.split('/reset-password/')[1]
            reset_url = f"{self.frontend_url}/reset-password/{token}"
            
        content = f"""
            <p>We received a request to reset your password. Click below to proceed:</p>
            <p style="text-align: center;">
                <a href="{reset_url}" class="button"><span class="button-text">Reset Password</span></a>
            </p>
            <p>If the button doesn't work, copy this link into your browser:</p>
            <p>{reset_url}</p>
            <p>This link will expire in 1 hour.</p>
            <p>If you did not request a reset, please ignore this message.</p>
        """
        html = self._wrap_template("ESGenerator Password Reset", user.username, content)
        return self.send_email(user.email, "Reset Your Password - ESGenerator", html)

    def send_notification_email(self, user, subject, message):
        html = self._wrap_template("ESGenerator Notification", user.username, message)
        return self.send_email(user.email, subject, html)