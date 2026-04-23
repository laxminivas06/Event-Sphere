import os
import re

# List of endpoints that belong to the hackathon blueprint
HACKATHON_ENDPOINTS = [
    'index', 'register', 'admin_login', 'admin', 'admin_settings', 'admin_homepage', 
    'check_roll_number', 'evaluation_settings', 'evaluator_login', 'evaluation_dashboard',
    'cleanup_projects', 'debug_projects_list', 'fix_tech_stack', 'evaluate_team',
    'view_project', 'download_project', 'submit_project', 'api_submit_project',
    'evaluation_results', 'teams_login', 'team_access_check', 'team_logout',
    'receipt_login', 'receipt_access_check', 'receipt_logout', 'generate_receipt',
    'view_receipt', 'message_center', 'view_teams', 'delete_team',
    'get_members', 'toggle_payment', 'send_receipt_email', 'resend_registration_email',
    'download_id_card', 'download_receipt', 'scan_qr', 'process_scan',
    'get_scanned_logs', 'export_attendance', 'stats', 'suggestions',
    'submit_suggestion', 'retrieve_qr', 'payment', 'export_teams_csv',
    'leaderboard', 'upload_students', 'attendance_dashboard', 'mark_attendance',
    'admin_logout', 'serve_project_file'
]

def update_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # Pattern to match url_for('endpoint') or url_for("endpoint")
    # We want to avoid endpoints that are already prefixed with 'hackathon.' or start with '.'
    for endpoint in HACKATHON_ENDPOINTS:
        # Match matches 'endpoint' or "endpoint"
        # Using negative lookbehind to avoid already prefixed ones
        pattern = r"url_for\((['\"]){}(['\"])\)".format(re.escape(endpoint))
        replacement = r"url_for(\1hackathon.{}\2)".format(endpoint)
        content = re.sub(pattern, replacement, content)
        
        # Also match with arguments: url_for('endpoint', ...)
        pattern = r"url_for\((['\"]){}(['\"],)".format(re.escape(endpoint))
        replacement = r"url_for(\1hackathon.{}\2)".format(endpoint)
        content = re.sub(pattern, replacement, content)

    if content != original_content:
        with open(filepath, 'w') as f:
            f.write(content)
        return True
    return False

# Directories to process
dirs_to_process = [
    'templates/hackathon',
    'app'
]

files_updated = 0
for d in dirs_to_process:
    full_path = os.path.join('/Users/nivas/Documents/Python Softwarez/Boss', d)
    if not os.path.exists(full_path):
        continue
    for root, _, files in os.walk(full_path):
        for file in files:
            if file.endswith('.html') or file.endswith('.py'):
                if update_file(os.path.join(root, file)):
                    files_updated += 1
                    print(f"Updated: {os.path.join(root, file)}")

print(f"Total files updated: {files_updated}")
