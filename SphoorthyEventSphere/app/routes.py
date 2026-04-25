from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, make_response, send_file
from app.models import DB, DATA_DIR
from app.mailer import Mailer
import os
import uuid
import datetime
import io
import csv
import json
import re
import zipfile
from flask import current_app
import qrcode
from fpdf import FPDF
import tempfile
from io import BytesIO
import hmac
import hashlib
import razorpay
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

api = Blueprint('api', __name__)

@api.route('/get-student-qr/<club_id>/<reg_id>')
def get_student_qr(club_id, reg_id):
    # This route is used by the success page to display the QR code
    # We look up the registration and generate a QR based on its ID
    clubs = DB.get_clubs()
    club = next((c for c in clubs if c['id'] == club_id), None)
    if not club: return "Club not found", 404
    
    events = DB.get_events(club_id)
    reg = None
    for event in events:
        regs = DB.get_registrations(club_id, event['id'])
        reg = next((r for r in regs if r['id'] == reg_id), None)
        if reg: break
        
    if not reg: return "Registration not found", 404
    
    # Generate QR containing the registration ID
    import qrcode
    from io import BytesIO
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(reg_id)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    download = request.args.get('download') == 'true'
    return send_file(img_io, mimetype='image/png', as_attachment=download, download_name=f"QR_{reg_id}.png")

def is_trusted_club(club_id):
    # A club is trusted if they have at least one event with an approved report
    events = DB.get_events(club_id)
    return any(e.get('report_approved') for e in events)

def generate_qr_attachment(qr_data):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = BytesIO()
    img.save(buf, format='PNG')
    temp_path = os.path.join('static', 'temp_qr', f"{uuid.uuid4().hex}.png")
    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
    with open(temp_path, 'wb') as f:
        f.write(buf.getvalue())
    return temp_path

def send_registration_email(reg):
    if not reg.get('email'): return
    qr_path = generate_qr_attachment(reg['qr_code'])
    subject = f"Registration Successful: {reg.get('event_title', 'Event')}"
    body = f"Hi {reg['name']},\n\nThank you for registering for {reg.get('event_title')}. Your registration token is {reg['id']}.\n\nPlease find your QR code attached."
    html_body = f"<h3>Hi {reg['name']},</h3><p>Thank you for registering for <b>{reg.get('event_title')}</b>.</p><p>Registration ID: <code>{reg['id']}</code></p><p>Please show the attached QR code at the venue.</p>"
    Mailer.send_email(reg['email'], subject, body, html_body, qr_path, club_id=reg.get('club_id'))
    if os.path.exists(qr_path): os.remove(qr_path)

def send_verification_email(reg):
    if not reg.get('email'): return
    qr_path = generate_qr_attachment(reg['qr_code'])
    subject = f"Payment Verified: {reg.get('event_title', 'Event')}"
    body = f"Hi {reg['name']},\n\nYour payment for {reg.get('event_title')} has been verified. You can now use your QR code for attendance.\n\nPlease find your QR code attached again for convenience."
    html_body = f"<h3>Payment Verified!</h3><p>Hi {reg['name']}, your payment for <b>{reg.get('event_title')}</b> has been successfully verified.</p><p>You can use the attached QR code for attendance.</p>"
    Mailer.send_email(reg['email'], subject, body, html_body, qr_path, club_id=reg.get('club_id'))
    if os.path.exists(qr_path): os.remove(qr_path)

@api.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@api.route('/login', methods=['POST'])
def api_login():
    data = request.json or {}
    roll = data.get('roll_number', '').strip()
    dob = data.get('dob', '').strip()

    # Fields that should NEVER be sent to the browser or stored in session
    SENSITIVE_FIELDS = {'password', 'dob'}

    def sanitize(user_obj):
        return {k: v for k, v in user_obj.items() if k not in SENSITIVE_FIELDS}

    # 1. Check Admins / Evaluators / Managers in admins.json
    admins = DB.get_admins()
    for admin in admins:
        admin_email = admin.get('email', '').strip().lower()
        admin_roll = admin.get('roll_number', '').strip().lower()
        
        # Match by email or roll_number
        if (admin_email == roll.lower() or admin_roll == roll.lower()) and admin.get('password') == dob:
            safe_admin = sanitize(admin)
            session['user'] = safe_admin
            return jsonify({'success': True, 'user': safe_admin})

    # 2. Check Students
    student = DB.get_student_by_roll(roll)
    if student and student.get('dob') == dob:
        student['role'] = 'student'
        safe_student = sanitize(student)
        session['user'] = safe_student
        return jsonify({'success': True, 'user': safe_student})

    return jsonify({'success': False, 'message': 'Invalid credentials. Please try again.'})

@api.route('/events/update_details', methods=['POST'])
def update_event_details():
    user = session.get('user')
    if not user: return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.form.to_dict()
    event_id = data.get('event_id') or data.get('id')
    all_events = DB.get_events()
    event = next((e for e in all_events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404
    
    club_id = event['club_id']
    club = DB.get_club_by_id(club_id)
    
    # Authorization check
    identifier = user.get('email') or user.get('roll_number')
    if user.get('role') != 'super_admin' and club.get('admin_roll') != identifier:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    # Update fields
    for field in ['title', 'venue', 'date', 'time', 'payment_type', 'fee', 'description']:
        if field in data:
            event[field] = data[field]
            
    if 'event_type' in data:
        event['registration_type'] = data['event_type']
    
    # Handle collaborating clubs
    event['collaborating_clubs'] = request.form.getlist('collaborating_clubs')

    # Handle poster upload
    poster = request.files.get('poster')
    if poster and poster.filename:
        if allowed_file(poster.filename):
            from app.models import slugify
            event_slug = slugify(event['title'])
            upload_dir = os.path.join(current_app.static_folder, 'uploads', 'clubs', club_id, 'events', event_slug, 'posters')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Secure filename and add unique prefix
            filename = secure_filename(poster.filename)
            fn = f"poster_{uuid.uuid4().hex[:8]}_{filename}"
            poster.save(os.path.join(upload_dir, fn))
            event['poster'] = fn

    DB.save_event(club_id, event)
    return jsonify({'success': True})

@api.route('/events/create_permission', methods=['POST'])
def create_event_permission():
    user = session.get('user')
    if not user: return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.form.to_dict()
    club_id = data.get('club_id')
    if not club_id: return jsonify({'success': False, 'message': 'Club ID required'}), 400
    
    # Generate unique ID
    event_id = str(uuid.uuid4())
    
    # Default academic year
    now = datetime.datetime.now()
    if now.month >= 6:
        year_str = f"{now.year % 100}-{(now.year + 1) % 100}"
    else:
        year_str = f"{(now.year - 1) % 100}-{now.year % 100}"
        
    new_event = {
        'id': event_id,
        'title': data.get('title', 'Untitled Event'),
        'date': data.get('date', ''),
        'time': data.get('time', ''),
        'venue': data.get('venue', 'TBD'),
        'description': data.get('description', ''),
        'payment_type': data.get('payment_type', 'free'), # free/paid
        'registration_type': data.get('event_type', 'individual'), # individual/team
        'fee': data.get('fee', '0'),
        'club_id': club_id,
        'year': year_str,
        'approved': is_trusted_club(club_id),
        'event_finished': False,
        'report_approved': False,
        'event_status': 'approved' if is_trusted_club(club_id) else 'draft',
        'timestamp': datetime.datetime.now().isoformat(),
        'collaborating_clubs': request.form.getlist('collaborating_clubs')
    }
    
    DB.save_event(club_id, new_event)
    return jsonify({'success': True, 'event_id': event_id})

@api.route('/events/save_permission', methods=['POST'])
def save_event_permission():
    user = session.get('user')
    if not user: return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    club_id = data.get('club_id')
    event_id = data.get('event_id')
    
    events = DB.get_events(club_id)
    event = next((e for e in events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404
    
    # Save all allowed fields sent from the letter
    allowed_fields = ['title', 'date', 'time', 'venue', 'description', 'payment_type', 'event_type', 'fee', 'resource_person', 'collaborating_clubs']
    for key in allowed_fields:
        if key in data:
            event[key] = data[key]
            
    # Update status to pending so it's no longer a draft (unless auto-approved)
    if is_trusted_club(club_id):
        event['event_status'] = 'approved'
        event['approved'] = True
    else:
        event['event_status'] = 'pending'
        event['approved'] = False
    
    DB.save_event(club_id, event)
    return jsonify({'success': True})

@api.route('/events/finish', methods=['POST'])
def finish_event():
    user = session.get('user')
    if not user: return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    club_id = data.get('club_id')
    event_id = data.get('event_id')
    
    events = DB.get_events(club_id)
    event = next((e for e in events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404
        
    event['event_finished'] = True
    DB.save_event(club_id, event)
    return jsonify({'success': True})

@api.route('/events/upload_report', methods=['POST'])
def upload_report():
    user = session.get('user')
    if not user: return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    club_id = request.form.get('club_id')
    event_id = request.form.get('event_id')
    report_file = request.files.get('report')
    
    if not report_file: return jsonify({'success': False, 'message': 'No file uploaded'}), 400
    
    events = DB.get_events(club_id)
    event = next((e for e in events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404
    
    # Authorization check
    club = DB.get_club_by_id(club_id)
    identifier = user.get('email') or user.get('roll_number')
    if user.get('role') != 'super_admin' and club.get('admin_roll') != identifier:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if not allowed_file(report_file.filename) and not report_file.filename.endswith('.pdf'):
        return jsonify({'success': False, 'message': 'Invalid file type. Only PDF and images allowed.'}), 400

    from app.models import slugify
    event_slug = slugify(event['title'])
    upload_dir = os.path.join(current_app.static_folder, 'uploads', 'clubs', club_id, 'events', event_slug, 'reports')
    os.makedirs(upload_dir, exist_ok=True)
    
    # Secure filename
    filename = f"report_{uuid.uuid4().hex[:8]}_{secure_filename(report_file.filename)}"
    report_file.save(os.path.join(upload_dir, filename))
    
    event['report'] = filename
    event['report_approved'] = False # Needs super_admin approval
    DB.save_event(club_id, event)
    
    return jsonify({'success': True})

@api.route('/students/list', methods=['GET'])
def list_students():
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    page = int(request.args.get('page', 1))
    search = request.args.get('search', '').lower()
    
    students = DB.get_students()
    
    if search:
        students = [s for s in students if search in s.get('roll_number', '').lower() or search in s.get('name', '').lower()]
        
    # Sort students by roll_number or name
    students.sort(key=lambda x: x.get('roll_number', ''))
    
    per_page = 20
    total = len(students)
    pages = (total + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    
    return jsonify({
        'success': True,
        'students': students[start:end],
        'pages': pages,
        'current_page': page,
        'total': total
    })

@api.route('/students/upload', methods=['POST'])
def upload_students_csv():
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'})
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'})
        
    try:
        content = file.read().decode('utf-8').splitlines()
        import csv
        reader = list(csv.DictReader(content))
        
        students = DB.get_students()
        added_count = 0
        updated_count = 0
        
        # Validation Pass
        for i, row in enumerate(reader, start=1):
            roll = row.get('roll_number') or row.get('Roll Number') or row.get('reg') or row.get('Reg')
            name = row.get('name') or row.get('Name') or row.get('student name') or row.get('Student Name')
            dept = row.get('department') or row.get('Department')
            year = row.get('year') or row.get('Year')
            dob = row.get('dob') or row.get('DOB') or row.get('Date of Birth')
            
            if not roll or not str(roll).strip(): return jsonify({'success': False, 'message': f'Row {i}: Missing mandatory field "Roll Number/Reg"'})
            if not name or not str(name).strip(): return jsonify({'success': False, 'message': f'Row {i} (Roll {roll}): Missing mandatory field "Student Name"'})
            if not dept or not str(dept).strip(): return jsonify({'success': False, 'message': f'Row {i} (Roll {roll}): Missing mandatory field "Department"'})
            if not year or not str(year).strip(): return jsonify({'success': False, 'message': f'Row {i} (Roll {roll}): Missing mandatory field "Year"'})
            if not dob or not str(dob).strip(): return jsonify({'success': False, 'message': f'Row {i} (Roll {roll}): Missing mandatory field "DOB"'})
        
        for row in reader:
            roll = str(row.get('roll_number') or row.get('Roll Number') or row.get('reg') or row.get('Reg')).strip().upper()
            name = str(row.get('name') or row.get('Name') or row.get('student name') or row.get('Student Name')).strip()
            dept = str(row.get('department') or row.get('Department')).strip()
            year = str(row.get('year') or row.get('Year')).strip()
            dob = str(row.get('dob') or row.get('DOB') or row.get('Date of Birth')).strip()
            email = str(row.get('email') or row.get('Email') or '').strip()
            phone = str(row.get('phone') or row.get('Phone') or '').strip()
            
            existing = next((s for s in students if s['roll_number'].upper() == roll), None)
            if existing:
                existing['name'] = name
                existing['department'] = dept
                existing['year'] = year
                existing['dob'] = dob
                if email: existing['email'] = email
                if phone: existing['phone'] = phone
                updated_count += 1
            else:
                students.append({
                    'roll_number': roll,
                    'name': name,
                    'department': dept,
                    'year': year,
                    'dob': dob,
                    'email': email,
                    'phone': phone,
                    'photo': None,
                    'contributions': []
                })
                added_count += 1
                
        DB.save_students(students)
        return jsonify({'success': True, 'message': f'Imported! Added: {added_count}, Updated: {updated_count}'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@api.route('/students/promote', methods=['POST'])
def promote_students():
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json or {}
    promotion_rules = data.get('promotion_rules', {}) # e.g. {"1st": "2nd", "2nd": "3rd", "3rd": "4th", "4th": "Alumni"}
    detained_rolls = data.get('detained_rolls', [])
    delete_detained = data.get('delete_detained', False)

    students = DB.get_students()
    updated_count = 0
    deleted_count = 0

    new_students = []
    
    for s in students:
        roll = s.get('roll_number', '').upper()
        current_year = s.get('year', '')
        
        if roll in detained_rolls:
            if delete_detained:
                deleted_count += 1
                continue # Skip adding to new_students
            # Else, they are detained but not deleted, so year remains same
            new_students.append(s)
            continue
            
        if current_year in promotion_rules:
            s['year'] = promotion_rules[current_year]
            updated_count += 1
            
        new_students.append(s)

    DB.save_students(new_students)
    return jsonify({
        'success': True,
        'message': f'Promoted: {updated_count}, Deleted: {deleted_count}'
    })

@api.route('/contacts/update', methods=['POST'])
def update_contacts():
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    data = request.json
    contacts = data.get('contacts', {})
    DB.save_contacts(contacts)
    return jsonify({'success': True})

@api.route('/clubs/update', methods=['POST'])
def update_club():
    user = session.get('user')
    if not user: return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.form.to_dict()
    club_id = data.get('id')
    club = DB.get_club_by_id(club_id)
    if not club: return jsonify({'success': False, 'message': 'Club not found'}), 404
    
    # Authorization check
    identifier = user.get('email') or user.get('roll_number')
    if user.get('role') != 'super_admin' and club.get('admin_roll') != identifier:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    # Update fields
    if 'about' in data: club['about'] = data['about']
    if 'mission' in data: club['mission'] = data['mission']
    if 'vision' in data: club['vision'] = data['vision']
    if 'mentor_name' in data: club['mentor']['name'] = data['mentor_name']
    if 'mentor_designation' in data: club['mentor']['designation'] = data['mentor_designation']
    
    # Handle logo upload
    logo = request.files.get('logo')
    if logo and logo.filename:
        if allowed_file(logo.filename):
            upload_dir = os.path.join(current_app.static_folder, 'uploads', 'clubs', club_id, 'details')
            os.makedirs(upload_dir, exist_ok=True)
            fn = f"logo_{uuid.uuid4().hex[:8]}_{secure_filename(logo.filename)}"
            logo.save(os.path.join(upload_dir, fn))
            club['logo'] = fn

    # Handle cover image upload
    cover = request.files.get('cover_image')
    if cover and cover.filename:
        if allowed_file(cover.filename):
            upload_dir = os.path.join(current_app.static_folder, 'uploads', 'clubs', club_id, 'details')
            os.makedirs(upload_dir, exist_ok=True)
            fn = f"cover_{uuid.uuid4().hex[:8]}_{secure_filename(cover.filename)}"
            cover.save(os.path.join(upload_dir, fn))
            club['cover_image'] = fn

    # Handle gallery image removal
    remove_img = data.get('remove_gallery_image')
    if remove_img and 'gallery' in club:
        club['gallery'] = [img for img in club['gallery'] if img != remove_img]
        # Optional: delete the file from disk here
        
    # Handle new gallery images
    new_images = request.files.getlist('gallery') # Changed from gallery_images to match template name="gallery"
    if new_images:
        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'clubs', club_id, 'gallery')
        os.makedirs(upload_dir, exist_ok=True)
        if 'gallery' not in club: club['gallery'] = []
        for img in new_images:
            if img and img.filename and allowed_file(img.filename):
                fn = f"gallery_{uuid.uuid4().hex[:8]}_{secure_filename(img.filename)}"
                img.save(os.path.join(upload_dir, fn))
                club['gallery'].append(fn)
                
    # Handle office bearers
    bearer_names = request.form.getlist('bearer_names')
    bearer_roles = request.form.getlist('bearer_roles')
    bearer_phones = request.form.getlist('bearer_phones')
    
    # Note: bearer_photos handling is tricky with multiple files. 
    # For now, we will maintain existing logic but fix the name mapping if possible.
    # Actually, a better way is to check bearer_photos by index if they were provided.
    
    if bearer_names:
        bearers = []
        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'clubs', club_id, 'bearers')
        os.makedirs(upload_dir, exist_ok=True)
        
        # We need to know which bearer gets which photo. 
        # HTML sends all bearer_photos in order of selection.
        # This is still a bit fragile but let's try to match by presence of file.
        
        existing_bearers = club.get('office_bearers', [])
        
        for i in range(len(bearer_names)):
            photo_fn = None
            # Check if a new photo was uploaded for this specific index
            # This requires the frontend to send something that maps index to file.
            # But with current simple list, it's hard. 
            # We'll use the existing photo as default.
            
            current_photo = existing_bearers[i]['photo'] if i < len(existing_bearers) else None
            
            bearers.append({
                'name': bearer_names[i],
                'role': bearer_roles[i],
                'phone': bearer_phones[i],
                'photo': current_photo
            })
        club['office_bearers'] = bearers

    DB.save_club(club)
    return jsonify({'success': True})

@api.route('/clubs/create', methods=['POST'])
def create_club():
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    name = data.get('name')
    features = data.get('features', {})
    admin_data = data.get('admin', {})
    
    if not name or not admin_data.get('email'):
        return jsonify({'success': False, 'message': 'Name and Admin Email are required'}), 400
        
    from app.models import slugify
    club_id = slugify(name)
    
    # Check if club already exists
    if DB.get_club_by_id(club_id):
        club_id = f"{club_id}_{uuid.uuid4().hex[:4]}"
        
    new_club = {
        'id': club_id,
        'name': name,
        'features': features,
        'admin_roll': admin_data.get('email'), # Use email as identifier in about.json
        'about': '',
        'mission': '',
        'vision': '',
        'mentor': {'name': '', 'designation': ''},
        'office_bearers': [],
        'gallery': []
    }
    
    DB.save_club(new_club)
    
    # Create Admin
    admin_user = {
        'name': admin_data.get('name'),
        'email': admin_data.get('email'),
        'password': admin_data.get('password'),
        'phone': admin_data.get('phone'),
        'role': 'club_admin' # General role, specific access checked by email/roll
    }
    DB.save_admin(admin_user)
    
    return jsonify({'success': True, 'club_id': club_id})

@api.route('/clubs/update_config', methods=['POST'])
def update_club_config():
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    data = request.json
    club_id = data.get('id')
    features = data.get('features', {})
    admin_data = data.get('admin', {})
    
    club = DB.get_club_by_id(club_id)
    if not club:
        return jsonify({'success': False, 'message': 'Club not found'}), 404
        
    # Update club info
    club['name'] = data.get('name') or club['name']
    club['features'] = features
    
    # If admin email changed, we need to handle that, but for now let's keep it simple
    old_admin_email = club.get('admin_roll')
    new_admin_email = admin_data.get('email')
    
    club['admin_roll'] = new_admin_email
    DB.save_club(club)
    
    # Update Admin
    admins = DB.get_admins()
    admin_user = next((a for a in admins if a.get('email') == old_admin_email), None)
    
    if admin_user:
        admin_user['name'] = admin_data.get('name') or admin_user['name']
        admin_user['email'] = new_admin_email
        if admin_data.get('password'):
            admin_user['password'] = admin_data.get('password')
        admin_user['phone'] = admin_data.get('phone') or admin_user.get('phone')
    else:
        # Create new if didn't exist
        admin_user = {
            'name': admin_data.get('name'),
            'email': new_admin_email,
            'password': admin_data.get('password'),
            'phone': admin_data.get('phone'),
            'role': 'club_admin'
        }
        admins.append(admin_user)
        
    DB.save_json('admins.json', admins)
    
    return jsonify({'success': True})

@api.route('/office_bearers/request', methods=['POST'])
def request_office_bearer():
    user = session.get('user')
    if not user: return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.form.to_dict()
    req = {
        'id': str(uuid.uuid4()),
        'club_id': data.get('club_id'),
        'name': data.get('name'),
        'role': data.get('role'),
        'status': 'pending',
        'timestamp': datetime.datetime.now().isoformat()
    }
    DB.save_office_bearer_request(req)
    return jsonify({'success': True})

@api.route('/events/approve_report/<club_id>/<event_id>', methods=['POST'])
def approve_report(club_id, event_id):
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    events = DB.get_events(club_id)
    event = next((e for e in events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404
    
    event['report_approved'] = True
    event['event_finished'] = True
    DB.save_event(club_id, event)
    return jsonify({'success': True})

@api.route('/admin/approve_finance_unlock', methods=['POST'])
def approve_finance_unlock():
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    club_id = data.get('club_id')
    event_id = data.get('event_id')
    
    events = DB.get_events(club_id)
    event = next((e for e in events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404
    
    event['finance_locked'] = False
    event['finance_unlock_requested'] = False
    event['finance_unlock_approved'] = True
    DB.save_event(club_id, event)
    return jsonify({'success': True})

@api.route('/events/save_finance', methods=['POST'])
def save_finance():
    user = session.get('user')
    if not user: return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    club_id = data.get('club_id')
    event_id = data.get('event_id')
    
    events = DB.get_events(club_id)
    event = next((e for e in events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404
    
    event['extra_income'] = data.get('extra_income', 0)
    event['extra_expense'] = data.get('extra_expense', 0)
    event['offline_cash'] = data.get('offline_cash', 0)
    event['actual_expenses'] = data.get('actual_expenses', 0)
    event['finance_locked'] = True
    event['finance_unlock_approved'] = False
    
    DB.save_event(club_id, event)
    return jsonify({'success': True})

@api.route('/events/update_finance', methods=['POST'])
def update_finance():
    """Club admin finance update — no locking, editable anytime."""
    user = session.get('user')
    if not user: return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data     = request.json
    club_id  = data.get('club_id')
    event_id = data.get('event_id')

    events = DB.get_events(club_id)
    event  = next((e for e in events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404

    try:
        event['extra_income']    = int(float(data.get('extra_income', 0)))
        event['extra_expense']   = int(float(data.get('extra_expense', 0)))
        event['offline_cash']    = int(float(data.get('offline_cash', 0)))
        event['actual_expenses'] = int(float(data.get('actual_expenses', 0)))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid numeric values'}), 400

    # Recompute helper fields used by Finance Hub table
    auto_revenue = int(event.get('revenue', 0))
    event['computed_revenue'] = auto_revenue + event['extra_income'] + event['offline_cash']
    event['computed_spend']   = event['actual_expenses'] + event['extra_expense']

    DB.save_event(club_id, event)
    return jsonify({
        'success': True,
        'computed_revenue': event['computed_revenue'],
        'computed_spend':   event['computed_spend']
    })

@api.route('/events/request_finance_unlock', methods=['POST'])
def request_finance_unlock():
    user = session.get('user')
    if not user: return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    club_id = data.get('club_id')
    event_id = data.get('event_id')
    
    events = DB.get_events(club_id)
    event = next((e for e in events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404
    
    event['finance_unlock_requested'] = True
    DB.save_event(club_id, event)
    return jsonify({'success': True})

@api.route('/events/approve/<club_id>/<event_id>', methods=['POST'])
def approve_event_structure(club_id, event_id):
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    events = DB.get_events(club_id)
    event = next((e for e in events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404
    
    event['approved'] = True
    event['event_status'] = 'approved'
    DB.save_event(club_id, event)
    return jsonify({'success': True})

@api.route('/events/reject/<club_id>/<event_id>', methods=['POST'])
def reject_event_structure(club_id, event_id):
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    events = DB.get_events(club_id)
    event = next((e for e in events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404
    
    event['approved'] = False
    event['event_status'] = 'pending'
    DB.save_event(club_id, event)
    return jsonify({'success': True})

@api.route('/events/approve_deletion/<club_id>/<event_id>', methods=['POST'])
def approve_event_deletion(club_id, event_id):
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    events = DB.get_events(club_id)
    event = next((e for e in events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404
    
    # Simple soft delete or status change
    event['event_status'] = 'deleted'
    event['deletion_approved'] = True
    DB.save_event(club_id, event)
    return jsonify({'success': True})

@api.route('/events/reject_deletion/<club_id>/<event_id>', methods=['POST'])
def reject_event_deletion(club_id, event_id):
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    events = DB.get_events(club_id)
    event = next((e for e in events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404
    
    event['deletion_requested'] = False
    DB.save_event(club_id, event)
    return jsonify({'success': True})

@api.route('/office_bearers/action', methods=['POST'])
def action_bearer_request():
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    req_id = data.get('id')
    action = data.get('action') # 'approve' or 'reject'
    
    requests = DB.load_json('office_bearer_requests.json')
    req = next((r for r in requests if r['id'] == req_id), None)
    if not req: return jsonify({'success': False, 'message': 'Request not found'}), 404
    
    if action == 'approve':
        req['status'] = 'approved'
        # Also add to the club's bearers list
        club = DB.get_club_by_id(req['club_id'])
        if club:
            if 'office_bearers' not in club: club['office_bearers'] = []
            club['office_bearers'].append({
                'name': req['name'],
                'role': req['role'],
                'phone': '',
                'photo': None
            })
            DB.save_club(club)
    else:
        req['status'] = 'rejected'
        
    DB.save_json('office_bearer_requests.json', requests)
    return jsonify({'success': True})

@api.route('/clubs/<club_id>/download_annual_zip/<year>', methods=['GET'])
def download_annual_zip(club_id, year):
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return "Unauthorized", 403
    
    events = DB.get_events(club_id)
    yr_events = [e for e in events if str(e.get('year')) == str(year)]
    
    if not yr_events:
        return "No data found for this year", 404
        
    memory_file = io.BytesIO()
    from app.models import slugify
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for ev in yr_events:
            ev_slug = slugify(ev['title'])
            
            # Report
            if ev.get('report'):
                report_path = os.path.join(current_app.static_folder, 'uploads', 'clubs', club_id, 'events', ev_slug, 'reports', ev['report'])
                if os.path.exists(report_path):
                    zf.write(report_path, arcname=f"{year}/{ev_slug}/Report_{ev['report']}")
            
            # Poster
            if ev.get('poster'):
                poster_path = os.path.join(current_app.static_folder, 'uploads', 'clubs', club_id, 'events', ev_slug, 'posters', ev['poster'])
                if os.path.exists(poster_path):
                    zf.write(poster_path, arcname=f"{year}/{ev_slug}/Poster_{ev['poster']}")
                    
    memory_file.seek(0)
    club = DB.get_club_by_id(club_id)
    club_name = club.get('name', club_id) if club else club_id
    # Clean club name for filename
    safe_name = "".join([c if c.isalnum() else "_" for c in club_name])
    
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"{safe_name}_Annual_Reports_{year}.zip"
    )

@api.route('/settings')
def get_global_settings():
    # Load from em/settings.json as it's the central place for EM settings
    settings_path = os.path.join(DATA_DIR, 'em', 'settings.json')
    settings = {}
    if os.path.exists(settings_path):
        with open(settings_path) as f:
            try: settings = json.load(f)
            except: pass
    return jsonify({'success': True, 'settings': settings})

@api.route('/settings/update', methods=['POST'])
def update_global_settings():
    user = session.get('user')
    if not user or user.get('role') != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json or {}
    settings_path = os.path.join(DATA_DIR, 'em', 'settings.json')
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    
    settings = {}
    if os.path.exists(settings_path):
        with open(settings_path) as f:
            try: settings = json.load(f)
            except: pass
            
    settings.update(data)
    
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=4)
        
    return jsonify({'success': True})

# ── RAZORPAY INTEGRATION (CENTRALIZED) ────────────────────────────────────────

@api.route('/payment/create-order', methods=['POST'])
def api_create_order():
    data = request.json or {}
    club_id = data.get('club_id')
    event_id = data.get('event_id')
    
    if not club_id or not event_id:
        return jsonify({'success': False, 'message': 'Missing club or event ID'}), 400
        
    event = next((e for e in DB.get_events(club_id) if e['id'] == event_id), None)
    if not event:
        return jsonify({'success': False, 'message': 'Event not found'}), 404
        
    try:
        amount = int(float(event.get('fee', 0)) * 100)
    except:
        return jsonify({'success': False, 'message': 'Invalid event fee'}), 400
        
    if amount <= 0:
        return jsonify({'success': False, 'message': 'Free events do not require payment order'}), 400

    # Load centralized credentials
    settings_path = os.path.join(DATA_DIR, 'em', 'settings.json')
    settings = {}
    if os.path.exists(settings_path):
        with open(settings_path) as f:
            try: settings = json.load(f)
            except: pass
            
    key_id = settings.get('razorpay_key_id')
    key_secret = settings.get('razorpay_key_secret')
    
    if not key_id or not key_secret:
        return jsonify({'success': False, 'message': 'Razorpay is not configured by the institution.'}), 500
        
    client = razorpay.Client(auth=(key_id, key_secret))
    
    order_data = {
        'amount': amount,
        'currency': 'INR',
        'payment_capture': 1,
        'notes': {
            'club_id': club_id,
            'event_id': event_id,
            'event_title': event.get('title', 'Event')
        }
    }
    
    try:
        order = client.order.create(data=order_data)
        return jsonify({
            'success': True,
            'order_id': order['id'],
            'amount': amount,
            'key_id': key_id
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api.route('/register', methods=['POST'])
def api_register():
    try:
        user = session.get('user')
        if not user:
            return jsonify({'success': False, 'message': 'Authentication required.'}), 401
            
        # This route handles both free and paid (verified) registrations
        data = request.json or {}
        club_id = data.get('club_id')
        event_id = data.get('event_id')
        roll_number = data.get('roll_number')
        
        # SECURITY: Verify that the roll number in the request matches the logged-in student
        if user.get('role') == 'student' and user.get('roll_number') != roll_number:
            return jsonify({'success': False, 'message': 'You can only register yourself.'}), 403
            
        if not club_id:
            return jsonify({'success': False, 'message': 'Registration failed: Club ID is missing.'}), 400
        if not event_id:
            return jsonify({'success': False, 'message': 'Registration failed: Event ID is missing.'}), 400
            
        event = DB.get_event_by_id(club_id, event_id)
        if not event:
            return jsonify({'success': False, 'message': 'Registration failed: Event not found.'}), 404

        # Check if already registered
        regs = DB.get_registrations(club_id)
        if any(r['event_id'] == event_id and r.get('roll_number') == roll_number for r in regs):
            return jsonify({'success': False, 'message': 'You are already registered for this event.'}), 400

        # Payment Verification logic
        is_paid = event.get('payment_type') == 'paid'
        reg_type = data.get('reg_type', 'individual')
        team_role = data.get('team_role')
        team_id = data.get('team_id')
        
        payment_details = data.get('payment_details')
        
        # Team Member check: if they are joining an existing team, we must verify the team exists
        if reg_type == 'team' and team_role == 'member':
            if not team_id:
                return jsonify({'success': False, 'message': 'Team ID is required to join a team.'}), 400
            
            # Verify team exists for this event
            team_leader = next((r for r in regs if r['event_id'] == event_id and r.get('team_id') == team_id and r.get('team_role') == 'leader'), None)
            if not team_leader:
                return jsonify({'success': False, 'message': 'The specified team does not exist for this event.'}), 404
            
            # If team leader has paid, members don't pay (Institutional logic)
            is_paid = False 
        
        if is_paid:
            if not payment_details:
                return jsonify({'success': False, 'message': 'Payment details are required for this paid event.'}), 400
                
            # Verify Razorpay signature
            settings_path = os.path.join(DATA_DIR, 'em', 'settings.json')
            settings = {}
            if os.path.exists(settings_path):
                with open(settings_path) as f:
                    try: settings = json.load(f)
                    except: pass
            
            key_id = settings.get('razorpay_key_id')
            key_secret = settings.get('razorpay_key_secret')
            if not key_id or not key_secret:
                return jsonify({'success': False, 'message': 'Institutional Razorpay is not configured.'}), 500
                
            params_dict = {
                'razorpay_order_id': payment_details.get('razorpay_order_id'),
                'razorpay_payment_id': payment_details.get('razorpay_payment_id'),
                'razorpay_signature': payment_details.get('razorpay_signature')
            }
            
            if not all(params_dict.values()):
                return jsonify({'success': False, 'message': 'Incomplete payment confirmation received.'}), 400

            client = razorpay.Client(auth=(key_id, key_secret))
            try:
                client.utility.verify_payment_signature(params_dict)
            except Exception as sig_err:
                return jsonify({'success': False, 'message': 'Payment signature verification failed.'}), 400

        # Create registration
        reg_id = str(uuid.uuid4())
        reg = {
            'id': reg_id,
            'event_id': event_id,
            'event_title': event.get('title'),
            'club_id': club_id,
            'name': data.get('name'),
            'email': data.get('email'),
            'phone': data.get('phone'),
            'roll_number': roll_number,
            'department': data.get('branch') or data.get('department'),
            'year': data.get('year'),
            'reg_type': reg_type,
            'team_role': team_role,
            'team_name': data.get('team_name'),
            'team_id': team_id,
            'timestamp': datetime.datetime.now().isoformat(),
            'payment_verified': True if not is_paid or payment_details else False,
            'qr_code': reg_id
        }
        
        if payment_details:
            reg['payment_id'] = payment_details.get('razorpay_payment_id')
            reg['order_id'] = payment_details.get('razorpay_order_id')

        DB.save_registration(club_id, reg)
        
        # Send email
        try:
            send_registration_email(reg)
        except Exception as e:
            print(f"Email failure: {e}")
            pass # Don't fail the whole registration if email fails
            
        return jsonify({'success': True, 'reg_id': reg_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Server Error: {str(e)}'}), 500


@api.route('/student/update_profile', methods=['POST'])
def update_student_profile():
    user = session.get('user')
    if not user or user.get('role') != 'student':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    roll = user.get('roll_number')
    student = DB.get_student_by_roll(roll)
    if not student:
        return jsonify({'success': False, 'message': 'Student record not found'}), 404

    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form.to_dict()
        if 'contributions' in data:
            import json
            try:
                data['contributions'] = json.loads(data['contributions'])
            except:
                pass
                
        photo = request.files.get('photo')
        if photo and photo.filename:
            upload_dir = os.path.join(current_app.static_folder, 'uploads', 'students', roll)
            os.makedirs(upload_dir, exist_ok=True)
            filename = f"avatar_{uuid.uuid4().hex[:8]}_{photo.filename}"
            photo.save(os.path.join(upload_dir, filename))
            student['photo'] = filename
    else:
        data = request.json or {}
        
    # Update allowed fields
    if 'name' in data: student['name'] = data['name']
    if 'email' in data: student['email'] = data['email']
    if 'phone' in data: student['phone'] = data['phone']
    if 'department' in data: student['department'] = data['department']
    if 'year' in data: student['year'] = data['year']
    if 'class' in data: student['class'] = data['class']
    
    # Achievements / Club Contributions
    if 'contributions' in data:
        student['contributions'] = data['contributions']
        
    DB.save_student(student)
    # Update session
    student['role'] = 'student'
    session['user'] = student
    
    return jsonify({'success': True})


