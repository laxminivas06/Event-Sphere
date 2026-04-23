import os
import json

base_dir = '/Users/nivas/Documents/Python Softwarez/Boss'
routes_path = os.path.join(base_dir, 'app', 'event_mgmt_routes.py')

# 1. Update routes
with open(routes_path, 'r') as f:
    routes_code = f.read()

# Add hackathon hub routes
new_routes = """
# ═══════════════════════════════════════════════════════════════════════════════
# HACKATHON DASHBOARD ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@em.route('/hackathon/<event_id>/hub')
def em_hackathon_hub(event_id):
    user = session.get('user')
    event = _can_access_hackathon(user, event_id)
    if not event: return 'Access denied', 403
    return render_template('em_hackathon_hub.html', user=user, event=event)

@em.route('/hackathon/<event_id>/registrations')
def em_hackathon_registrations(event_id):
    user = session.get('user')
    event = _can_access_hackathon(user, event_id)
    if not event: return 'Access denied', 403
    teams = get_hackathon_teams(event_id)
    return render_template('em_hackathon_registrations.html', user=user, event=event, teams=teams)

@em.route('/hackathon/<event_id>/analytics')
def em_hackathon_analytics(event_id):
    user = session.get('user')
    event = _can_access_hackathon(user, event_id)
    if not event: return 'Access denied', 403
    return render_template('em_hackathon_analytics.html', user=user, event=event)

@em.route('/hackathon/<event_id>/evaluators')
def em_hackathon_evaluators(event_id):
    user = session.get('user')
    event = _can_access_hackathon(user, event_id)
    if not event: return 'Access denied', 403
    # evaluators logic is in em_admin but we can show it here too
    evaluators = get_evaluators()
    assigned = [e for e in evaluators if event_id in e.get('assigned_events', [])]
    return render_template('em_hackathon_evaluators.html', user=user, event=event, evaluators=assigned)

@em.route('/hackathon/<event_id>/bulk-email')
def em_hackathon_bulkemail(event_id):
    user = session.get('user')
    event = _can_access_hackathon(user, event_id)
    if not event: return 'Access denied', 403
    return render_template('em_hackathon_bulkemail.html', user=user, event=event)

@em.route('/hackathon/<event_id>/scanner')
def em_hackathon_scanner(event_id):
    user = session.get('user')
    event = _can_access_hackathon(user, event_id)
    if not event: return 'Access denied', 403
    return render_template('em_hackathon_scanner.html', user=user, event=event)

@em.route('/api/hackathon/team/<team_id>/verify_cash', methods=['POST'])
def api_hackathon_verify_cash(team_id):
    user = session.get('user')
    if not is_admin(user) and not is_club_admin(user):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    teams = get_hackathon_teams()
    t = next((tk for tk in teams if tk['team_id'] == team_id), None)
    if not t: return jsonify({'success': False, 'message': 'Team not found'}), 404
    
    t['payment_status'] = 'paid'
    t['payment_method'] = 'Cash (Verified)'
    t['verified_by'] = user.get('email') or user.get('name', '')
    t['verified_at'] = datetime.datetime.now().isoformat()
    DB.save_hackathon_team(t)
    return jsonify({'success': True, 'message': 'Payment verified'})

@em.route('/api/hackathon/scan', methods=['POST'])
def api_hackathon_scan():
    user = session.get('user')
    if not is_admin(user) and not is_club_admin(user): return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    qr_data = (request.json or {}).get('qr_data', '').strip()
    parts = qr_data.split('|')
    if len(parts) < 3 or parts[0] != 'HT':
        return jsonify({'success': False, 'message': '❌ Invalid QR format'}), 400

    event_id = parts[1]
    team_id = parts[2]
    teams = get_hackathon_teams(event_id)
    team = next((t for t in teams if t['team_id'] == team_id), None)
    if not team:
        return jsonify({'success': False, 'message': '❌ Team not found'}), 404

    if team.get('payment_status') in ('failed', 'pending', None) and next((e for e in get_events() if e['id']==event_id),{}).get('event_type') == 'paid':
        return jsonify({'success': False, 'message': '❌ Payment incomplete'}), 400

    if team.get('checked_in'):
        return jsonify({'success': False, 'already_in': True, 'message': '⚠️ Already checked in'}), 409

    team['checked_in'] = True
    team['checked_in_at'] = datetime.datetime.now().isoformat()
    DB.save_hackathon_team(team)

    return jsonify({'success': True, 'message': f'✅ Entry granted to team {team["team_name"]}', 'team': team})

@em.route('/api/hackathon/bulk-email/<event_id>', methods=['POST'])
def api_hackathon_bulk_email(event_id):
    user = session.get('user')
    event = _can_access_hackathon(user, event_id)
    if not event: return jsonify({'success': False}), 403
    data = request.json or {}
    subject = data.get('subject', '').strip()
    message = data.get('message', '').strip()
    teams = get_hackathon_teams(event_id)
    sent = 0
    failed = 0
    for t in teams:
        leader_email = next((m.get('email') for m in t.get('members',[]) if m.get('is_leader')), None)
        if not leader_email: continue
        try:
            ev_title = event.get('title', '')
            html_body = f"<div style='font-family:Arial,sans-serif;max-width:600px;margin:auto;background:#0f172a;color:#f1f5f9;padding:2rem;'><h1>📣 {subject}</h1><p>Hi Team {t['team_name']},</p><p>{message}</p><p>Event: {ev_title}</p></div>"
            Mailer.send_email(leader_email, subject, message, html_body)
            sent += 1
        except:
            failed += 1
    return jsonify({'success': True, 'sent': sent, 'failed': failed, 'total': len(teams)})

"""

if "@em.route('/hackathon/<event_id>/hub')" not in routes_code:
    # Insert before the end or after a specific hackathon block
    routes_code = routes_code.replace("# ═══════════════════════════════════════════════════════════════════════════════\n# HACKATHON PAGE ROUTES", new_routes + "\n# ═══════════════════════════════════════════════════════════════════════════════\n# HACKATHON PAGE ROUTES")
    with open(routes_path, 'w') as f:
        f.write(routes_code)
    print("Routes updated successfully")
else:
    print("Routes already exist")

# Also need to modify em_admin.html to link to the new hub
em_admin_path = os.path.join(base_dir, 'templates', 'em_admin.html')
with open(em_admin_path, 'r') as f:
    em_admin_code = f.read()

em_admin_code = em_admin_code.replace('href="/em/hackathon/{{ ev.id }}/teams"', 'href="/em/hackathon/{{ ev.id }}/hub"')
em_admin_code = em_admin_code.replace('<i class="fas fa-list"></i> View Teams', '<i class="fas fa-rocket"></i> Manage Hackathon')

with open(em_admin_path, 'w') as f:
    f.write(em_admin_code)
print("em_admin updated")

# Also need to update api_hackathon_register_team to support payment_status and qr_data
if "team['payment_status'] =" not in routes_code:
    new_reg = """
    team = {
        'team_id': _team_id(),
        'event_id': event_id,
        'team_name': team_name,
        'leader_id': identifier,
        'members': [{
            'roll_number': user.get('roll_number', ''),
            'name': user.get('name', ''),
            'email': user.get('email', ''),
            'dept': user.get('department', ''),
            'year': user.get('year', ''),
            'is_leader': True
        }] + members_data,
        'project_title': '',
        'github_url': '',
        'demo_url': '',
        'description': '',
        'submission_file': None,
        'submitted': False,
        'submitted_at': None,
        'created_at': datetime.datetime.now().isoformat(),
        'payment_status': 'free' if event.get('event_type') == 'free' else 'pending_cash',
        'payment_method': 'free' if event.get('event_type') == 'free' else 'Pending',
        'qr_data': f'HT|{event_id}|' + _team_id(),
        'checked_in': False,
        'checked_in_at': None
    }
    # Update QR data properly
    team['qr_data'] = f'HT|{event_id}|{team["team_id"]}'
"""
    # Just a simple hack: I will do this in the script later.

