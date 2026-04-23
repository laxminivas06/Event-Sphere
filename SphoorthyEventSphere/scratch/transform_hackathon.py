import os
import re

def transform():
    source = 'Hackathon/qr_attendance/app.py'
    target = 'app/hackathon_routes.py'
    
    if not os.path.exists(source):
        print(f"Source {source} not found")
        return

    with open(source, 'r') as f:
        content = f.read()

    # 1. Define our new clean imports block
    new_imports = [
        "from flask import Blueprint, render_template, request, redirect, url_for, jsonify, send_file, session, flash, Response, current_app",
        "from functools import wraps",
        "import os",
        "import json",
        "import qrcode",
        "import io",
        "import shutil",
        "from fpdf import FPDF",
        "from io import BytesIO",
        "from datetime import datetime, time, timedelta",
        "import base64",
        "import csv",
        "import re",
        "import threading",
        "import uuid",
        "import pytz",
        "import random",
        "import string",
        "from pathlib import Path",
        "from werkzeug.utils import secure_filename",
        "from werkzeug.security import generate_password_hash, check_password_hash",
        "from flask_wtf import FlaskForm",
        "from wtforms import StringField, SubmitField, SelectField, HiddenField, RadioField",
        "from wtforms.validators import DataRequired, Email, Optional, Length, Regexp",
        "from reportlab.lib.pagesizes import letter",
        "from reportlab.pdfgen import canvas",
        "from reportlab.lib.utils import ImageReader",
        "from reportlab.lib import colors",
        "from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, HRFlowable",
        "from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle",
        "from reportlab.lib.units import inch",
        "from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT",
        "from app.mailer import Mailer",
        "try:",
        "    import pandas as pd",
        "except ImportError:",
        "    pd = None",
        "import smtplib",
        "from email.mime.multipart import MIMEMultipart",
        "from email.mime.text import MIMEText",
        "from email.mime.application import MIMEApplication",
        "from num2words import num2words",
        "import math",
        "import tempfile"
    ]
    
    # 2. Extract logic from original content
    lines = content.split('\n')
    cleaned_lines = []
    
    # Patterns to remove completely
    skip_patterns = [
        r"^from flask import",
        r"^import flask",
        r"^import os",
        r"^import json",
        r"^import qrcode",
        r"^import io",
        r"^from fpdf import",
        r"^from io import",
        r"^from datetime import",
        r"^import base64",
        r"^import csv",
        r"^import re",
        r"^from flask_wtf",
        r"^from wtforms",
        r"^import threading",
        r"^from werkzeug\.utils import",
        r"^from werkzeug\.security import",
        r"^from reportlab",
        r"^import random",
        r"^import string",
        r"^from pathlib import",
        r"^from email\.mime",
        r"^import textwrap",
        r"^from num2words import",
        r"^import math",
        r"^import uuid",
        r"^import pytz",
        r"^app = Flask",
        r"^csrf = CSRFProtect",
        r"^mail = Mail",
        r"^app\.secret_key =",
        r"^from flask_mail import",
        r"^import sys",
        r"^import time",
        r"^from werkzeug\.security",
        r"^from fpdf from io" # Just in case
    ]

    for line in lines:
        stripped = line.strip()
        should_skip = False
        for p in skip_patterns:
            if re.match(p, stripped):
                should_skip = True
                break
        if should_skip:
            continue
            
        # Replace app references
        # Don't replace app.config at load time
        if stripped.startswith('app.config['):
            continue
            
        line = line.replace('app.route', 'hackathon.route')
        line = line.replace('app.errorhandler', 'hackathon.app_errorhandler')
        line = line.replace('app.config', 'current_app.config')
        line = line.replace('app.logger', 'current_app.logger')
        line = line.replace('app.root_path', 'current_app.root_path')
        line = line.replace('app.app_context()', 'current_app.app_context()')
        
        # Indentation for shutil at line 1218 (or similar)
        if 'shutil.copy2(' in line:
            # Normalize indentation to match neighbors
            line = line.strip()
            line = '            ' + line
            
        # Update templates path
        line = line.replace("render_template('", "render_template('hackathon/")
        line = line.replace('render_template("', 'render_template("hackathon/')
        
        # Data paths
        line = line.replace("'data/", "'data/hackathon/")
        line = line.replace('"data/', '"data/hackathon/')
        line = line.replace("'static/qr_images'", "'static/hackathon/qr_images'")
        line = line.replace('"static/qr_images"', '"static/hackathon/qr_images"')
        line = line.replace("'static/receipts'", "'static/hackathon/receipts'")
        line = line.replace('"static/receipts"', '"static/hackathon/receipts/')
        
        # Fix missing shutil
        if 'shutil.' in line and 'import shutil' not in "\n".join(new_imports):
            # Already added in new_imports
            pass

        cleaned_lines.append(line)

    final_content = "\n".join(new_imports) + "\n\n"
    final_content += "hackathon = Blueprint('hackathon', __name__, template_folder='../templates/hackathon', static_folder='../static/hackathon')\n\n"
    
    # RBAC decorator & Helpers
    final_content += """
def hackathon_access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get('user')
        if not user:
            return redirect(url_for('login_page'))
        if user.get('role') == 'super_admin':
            return f(*args, **kwargs)
        if user.get('hackathon_admin'):
            return f(*args, **kwargs)
        flash('Unauthorized access to Hackathon module', 'danger')
        return redirect(url_for('home'))
    return decorated_function

class MockMail:
    def send(self, msg):
        try:
            from app.mailer import Mailer
            # Adapt Message object to Mailer.send_email
            to_email = msg.recipients[0] if hasattr(msg, 'recipients') and msg.recipients else None
            if not to_email: return
            Mailer.send_email(
                to_email=to_email,
                subject=msg.subject,
                body=msg.body if hasattr(msg, 'body') else '',
                html_body=msg.html if hasattr(msg, 'html') else None
            )
        except Exception as e:
            print(f"MockMail error: {e}")

mail = MockMail()

# Blueprint initialization
@hackathon.before_app_first_request
def init_hackathon():
    os.makedirs('data/hackathon', exist_ok=True)
    os.makedirs('static/hackathon/qr_images', exist_ok=True)
    os.makedirs('static/hackathon/receipts', exist_ok=True)
    if 'initialize_files' in globals():
        globals()['initialize_files']()

"""
    final_content += "\n".join(cleaned_lines)
    
    # Remove if name == main
    final_content = re.sub(r"if __name__ == ['\"]__main__['\"]:\s+app\.run\(.*?\)", "", final_content, flags=re.DOTALL)
    
    # Final fix for any leftover @app.route
    final_content = final_content.replace('@app.route', '@hackathon.route')
    
    # url_for fixes
    routes = ['admin', 'index', 'register', 'admin_login', 'teams_login', 'receipt_login', 'message_center', 'view_teams', 'scan_qr', 'evaluation_settings', 'admin_settings', 'admin_homepage']
    for r in routes:
        final_content = re.sub(f"(?<!hackathon\\.)url_for\\(['\"]{r}['\"]", f"url_for('hackathon.{r}'", final_content)

    with open(target, 'w') as f:
        f.write(final_content)
    print(f"Successfully re-transformed to {target}")

if __name__ == "__main__":
    transform()
