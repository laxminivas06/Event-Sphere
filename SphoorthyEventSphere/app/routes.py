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

    # 1. Check Admins / Evaluators / Managers in admins.json
    admins = DB.get_admins()
    for admin in admins:
        admin_email = admin.get('email', '').strip().lower()
        admin_roll = admin.get('roll_number', '').strip().lower()
        
        # Match by email or roll_number
        if (admin_email == roll.lower() or admin_roll == roll.lower()) and admin.get('password') == dob:
            session['user'] = admin
            return jsonify({'success': True, 'user': admin})

    # 2. Check Students
    student = DB.get_student_by_roll(roll)
    if student and student.get('dob') == dob:
        student['role'] = 'student'
        session['user'] = student
        return jsonify({'success': True, 'user': student})

    return jsonify({'success': False, 'message': 'Invalid credentials. Please try again.'})

@api.route('/events/update_details', methods=['POST'])
def update_event_details():
    user = session.get('user')
    if not user: return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.form.to_dict()
    event_id = data.get('event_id') or data.get('id')
    club_id = user.get('role', '').split('_')[0] if user.get('role', '').endswith('_admin') else None
    
    # If super_admin, we might need club_id from somewhere else, but usually club admins call this.
    if user.get('role') == 'super_admin':
        # Find which club this event belongs to
        all_events = DB.get_events()
        event = next((e for e in all_events if e['id'] == event_id), None)
        if event: club_id = event['club_id']
    
    if not club_id: return jsonify({'success': False, 'message': 'Club not found'}), 404
    
    events = DB.get_events(club_id)
    event = next((e for e in events if e['id'] == event_id), None)
    if not event: return jsonify({'success': False, 'message': 'Event not found'}), 404
    
    # Update fields
    for field in ['title', 'venue', 'date', 'time', 'payment_type', 'fee', 'description']:
        if field in data:
            event[field] = data[field]
            
    if 'event_type' in data:
        event['registration_type'] = data['event_type']
    
    # Handle collaborating clubs
    event['collaborating_clubs'] = request.form.getlist('collaborating_clubs')

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
    
    # Save all fields sent from the letter
    for key, value in data.items():
        if key not in ['club_id', 'event_id']:
            event[key] = value
            
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
    
    from app.models import slugify
    event_slug = slugify(event['title'])
    upload_dir = os.path.join('static', 'uploads', 'clubs', club_id, 'events', event_slug, 'reports')
    os.makedirs(upload_dir, exist_ok=True)
    
    filename = f"report_{uuid.uuid4().hex[:8]}.pdf"
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
        reader = csv.DictReader(content)
        
        students = DB.get_students()
        added_count = 0
        updated_count = 0
        
        for row in reader:
            roll = row.get('roll_number') or row.get('Roll Number')
            if not roll: continue
            roll = str(roll).strip().upper()
            
            name = row.get('name') or row.get('Name') or ''
            dept = row.get('department') or row.get('Department') or ''
            year = row.get('year') or row.get('Year') or ''
            email = row.get('email') or row.get('Email') or ''
            phone = row.get('phone') or row.get('Phone') or ''
            
            existing = next((s for s in students if s['roll_number'].upper() == roll), None)
            if existing:
                if name: existing['name'] = name
                if dept: existing['department'] = dept
                if year: existing['year'] = year
                if email: existing['email'] = email
                if phone: existing['phone'] = phone
                updated_count += 1
            else:
                students.append({
                    'roll_number': roll,
                    'name': name,
                    'department': dept,
                    'year': year,
                    'email': email,
                    'phone': phone,
                    'dob': '2000-01-01', # Default
                    'photo': None,
                    'contributions': []
                })
                added_count += 1
                
        DB.save_students(students)
        return jsonify({'success': True, 'message': f'Imported! Added: {added_count}, Updated: {updated_count}'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

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
    
    # Update fields
    if 'about' in data: club['about'] = data['about']
    if 'mission' in data: club['mission'] = data['mission']
    if 'vision' in data: club['vision'] = data['vision']
    if 'mentor_name' in data: club['mentor']['name'] = data['mentor_name']
    if 'mentor_designation' in data: club['mentor']['designation'] = data['mentor_designation']
    
    # Handle gallery image removal
    remove_img = data.get('remove_gallery_image')
    if remove_img and 'gallery' in club:
        club['gallery'] = [img for img in club['gallery'] if img != remove_img]
        # Optionally delete file
        
    # Handle new gallery images
    new_images = request.files.getlist('gallery_images')
    if new_images:
        upload_dir = os.path.join('static', 'uploads', 'clubs', club_id, 'gallery')
        os.makedirs(upload_dir, exist_ok=True)
        if 'gallery' not in club: club['gallery'] = []
        for img in new_images:
            if img.filename:
                fn = f"gallery_{uuid.uuid4().hex[:8]}_{img.filename}"
                img.save(os.path.join(upload_dir, fn))
                club['gallery'].append(fn)
                
    # Handle office bearers
    bearer_names = request.form.getlist('bearer_names')
    bearer_roles = request.form.getlist('bearer_roles')
    bearer_phones = request.form.getlist('bearer_phones')
    bearer_photos = request.files.getlist('bearer_photos')
    
    if bearer_names:
        bearers = []
        upload_dir = os.path.join('static', 'uploads', 'clubs', club_id, 'bearers')
        os.makedirs(upload_dir, exist_ok=True)
        for i in range(len(bearer_names)):
            photo_fn = None
            if i < len(bearer_photos) and bearer_photos[i].filename:
                photo_fn = f"bearer_{uuid.uuid4().hex[:8]}_{bearer_photos[i].filename}"
                bearer_photos[i].save(os.path.join(upload_dir, photo_fn))
            
            bearers.append({
                'name': bearer_names[i],
                'role': bearer_roles[i],
                'phone': bearer_phones[i],
                'photo': photo_fn or (club['office_bearers'][i]['photo'] if i < len(club.get('office_bearers', [])) else None)
            })
        club['office_bearers'] = bearers

    DB.save_club(club)
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
        # This route handles both free and paid (verified) registrations
        data = request.json or {}
        club_id = data.get('club_id')
        event_id = data.get('event_id')
        
        if not club_id:
            return jsonify({'success': False, 'message': 'Registration failed: Club ID is missing.'}), 400
        if not event_id:
            return jsonify({'success': False, 'message': 'Registration failed: Event ID is missing.'}), 400
            
        event = DB.get_event_by_id(club_id, event_id)
        if not event:
            return jsonify({'success': False, 'message': f'Registration failed: Event with ID {event_id} not found in club {club_id}.'}), 400

        # Payment Verification if paid
        is_paid = event.get('payment_type') == 'paid'
        payment_details = data.get('payment_details')
        
        # Team Member check: if they are a member, they don't pay individually
        reg_type = data.get('reg_type', 'individual')
        team_role = data.get('team_role')
        if reg_type == 'team' and team_role == 'member':
            is_paid = False # Leader pays for the team
        
        if is_paid:
            if not payment_details:
                return jsonify({'success': False, 'message': 'Registration failed: Payment details are required for this paid event.'}), 400
                
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
                return jsonify({'success': False, 'message': 'Server Error: Institutional Razorpay credentials are not configured.'}), 500
                
            params_dict = {
                'razorpay_order_id': payment_details.get('razorpay_order_id'),
                'razorpay_payment_id': payment_details.get('razorpay_payment_id'),
                'razorpay_signature': payment_details.get('razorpay_signature')
            }
            
            if not all(params_dict.values()):
                return jsonify({'success': False, 'message': 'Registration failed: Incomplete payment confirmation received from Razorpay.'}), 400

            client = razorpay.Client(auth=(key_id, key_secret))
            try:
                client.utility.verify_payment_signature(params_dict)
            except Exception as sig_err:
                return jsonify({'success': False, 'message': f'Registration failed: Payment signature verification failed. {str(sig_err)}'}), 400

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
            'roll_number': data.get('roll_number'),
            'department': data.get('branch') or data.get('department'),
            'year': data.get('year'),
            'reg_type': reg_type,
            'team_role': team_role,
            'team_name': data.get('team_name'),
            'team_id': data.get('team_id'),
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


