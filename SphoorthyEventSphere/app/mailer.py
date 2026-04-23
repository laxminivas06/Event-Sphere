import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
import os

# System Defaults (Fallback if club config is missing)
DEFAULT_SMTP_SERVER = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587
DEFAULT_SMTP_USER = "your-email@gmail.com"
DEFAULT_SMTP_PASS = "your-app-password"

class Mailer:
    @staticmethod
    def _get_smtp_settings(club_id=None):
        """Fetches SMTP settings for a specific club or returns defaults."""
        if club_id:
            from app.models import DB
            club = DB.get_club_by_id(club_id)
            if club and 'smtp_config' in club:
                config = club['smtp_config']
                if config.get('user') and config.get('password'):
                    return (
                        config.get('server', DEFAULT_SMTP_SERVER),
                        int(config.get('port', DEFAULT_SMTP_PORT)),
                        config.get('user'),
                        config.get('password')
                    )
        
        return (DEFAULT_SMTP_SERVER, DEFAULT_SMTP_PORT, DEFAULT_SMTP_USER, DEFAULT_SMTP_PASS)

    @staticmethod
    def send_email(to_email, subject, body, html_body=None, image_path=None, club_id=None, attachment_path=None):
        try:
            server_addr, port, user, password = Mailer._get_smtp_settings(club_id)
            
            msg = MIMEMultipart()
            msg['From'] = user
            msg['To'] = to_email
            msg['Subject'] = subject

            msg.attach(MIMEText(body, 'plain'))
            if html_body:
                msg.attach(MIMEText(html_body, 'html'))

            if image_path and os.path.exists(image_path):
                with open(image_path, 'rb') as f:
                    img = MIMEImage(f.read())
                    img.add_header('Content-ID', '<qr_code>')
                    msg.attach(img)

            if attachment_path and os.path.exists(attachment_path):
                with open(attachment_path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(attachment_path)}"')
                    msg.attach(part)

            server = smtplib.SMTP(server_addr, port)
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
            server.quit()
            return True
        except Exception as e:
            print(f"Email error for {club_id}: {e}")
            return False

    @staticmethod
    def send_bulk_email(recipient_list, subject, content, club_id=None):
        for email in recipient_list:
            Mailer.send_email(email, subject, content, club_id=club_id)
