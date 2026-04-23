import os

base_dir = '/Users/nivas/Documents/Python Softwarez/Boss'
routes_path = os.path.join(base_dir, 'app', 'event_mgmt_routes.py')

with open(routes_path, 'r') as f:
    routes_code = f.read()

new_routes = """
@em.route('/hackathon/<event_id>/rounds')
def em_hackathon_rounds(event_id):
    user = session.get('user')
    event = _can_access_hackathon(user, event_id)
    if not event: return 'Access denied', 403
    return render_template('em_hackathon_rounds.html', user=user, event=event)

@em.route('/api/hackathon/<event_id>/rounds', methods=['POST'])
def api_hackathon_update_rounds(event_id):
    user = session.get('user')
    if not is_admin(user) and not is_club_admin(user):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    events = get_events()
    ev = next((e for e in events if e['id'] == event_id), None)
    if not ev: return jsonify({'success': False}), 404
    
    data = request.json or {}
    ev['evaluation_rounds'] = data.get('rounds', [])
    save_events(events)
    return jsonify({'success': True})

@em.route('/api/hackathon/team/<team_id>/promote', methods=['POST'])
def api_hackathon_promote_team(team_id):
    user = session.get('user')
    if not is_admin(user) and not is_club_admin(user):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json or {}
    target_round = data.get('round_index', 0)
    
    teams = get_hackathon_teams()
    team = next((t for t in teams if t['team_id'] == team_id), None)
    if not team: return jsonify({'success': False, 'message': 'Team not found'}), 404
    
    team['current_round'] = target_round
    DB.save_hackathon_team(team)
    return jsonify({'success': True})
"""

if "@em.route('/hackathon/<event_id>/rounds')" not in routes_code:
    routes_code = routes_code.replace("@em.route('/hackathon/<event_id>/bulk-email')", new_routes + "\n@em.route('/hackathon/<event_id>/bulk-email')")
    with open(routes_path, 'w') as f:
        f.write(routes_code)
    print("Added rounds routes")
else:
    print("Routes exist")
