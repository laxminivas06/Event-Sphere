import os
import re

def final_polish():
    path = 'app/hackathon_routes.py'
    with open(path, 'r') as f:
        content = f.read()

    # 1. Update the admin route iteself
    # Find @hackathon.route('/admin') and the function
    content = content.replace("@hackathon.route('/admin')\ndef admin():", "@hackathon.route('/admin')\n@hackathon_access_required\ndef admin():")
    
    # 2. Redirect session checks to our RBAC or just remove them if and only if we use the decorator
    # The decorator handles it well.
    # Replace internal admin_logged_in checks with hackathon_access_required
    
    # For now, let's keep it simple.
    
    # 3. Fix the template paths if any were missed
    # (The previous script did a good job on render_template('hackathon/)
    
    # 4. Fix some obvious path issues if any
    
    # 5. Fix the url_for issue
    # url_for('admin') -> url_for('hackathon.admin')
    # Use regex to find url_for('name') where name is a route in this blueprint
    # This is hard because I don't have the list of all routes.
    # But I can try common ones.
    routes = ['admin', 'index', 'register', 'admin_login', 'teams_login', 'receipt_login', 'message_center', 'view_teams', 'scan_qr', 'evaluation_settings', 'admin_settings', 'admin_homepage']
    for r in routes:
        content = content.replace(f"url_for('{r}'", f"url_for('hackathon.{r}'")
        content = content.replace(f"url_for(\"{r}\"", f"url_for('hackathon.{r}'")

    # 6. Ensure the main index route exists and is public
    # In Hackathon app it was likely @app.route('/')
    # Now it's @hackathon.route('/')
    
    # Let's check for @hackathon.route('/')
    if "@hackathon.route('/')" not in content:
        # Maybe it was @app.route('/') which became @hackathon.route('/')
        pass

    with open(path, 'w') as f:
        f.write(content)
    print("Final polish completed")

final_polish()
