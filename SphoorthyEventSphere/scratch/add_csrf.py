import os
import re

def add_csrf(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # regex to find <form method="POST" ...> and insert csrf_token if not present
    # Case insensitive for POST
    def repl(match):
        form_tag = match.group(0)
        if 'csrf_token' in content: # Simple check if already present anywhere in file
            return form_tag
        
        # Insert after the opening <form ...> tag
        return form_tag + '\n    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>'

    # Match <form ... method="POST" ...> (handling different order of attributes)
    # We want to be careful not to double-insert if it's already there in the form specific block
    # but the simple check above should prevent most cases if it's already globally present.
    
    # Improved regex: find <form ...> where method="POST" (case insensitive)
    # and then check if the NEXT few tags have csrf_token
    pattern = re.compile(r'(<form[^>]*method=["\']POST["\'][^>]*>)', re.IGNORECASE)
    
    new_content = ""
    last_end = 0
    for m in pattern.finditer(content):
        new_content += content[last_end:m.end()]
        # Check if the next 200 chars contain csrf_token
        lookahead = content[m.end():m.end()+200]
        if 'csrf_token' not in lookahead:
            new_content += '\n    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>'
        last_end = m.end()
    new_content += content[last_end:]

    if new_content != original_content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        return True
    return False

# Directories to process
dirs_to_process = [
    'templates/hackathon'
]

files_updated = 0
for d in dirs_to_process:
    full_path = os.path.join('/Users/nivas/Documents/Python Softwarez/Boss', d)
    if not os.path.exists(full_path): continue
    for root, _, files in os.walk(full_path):
        for file in files:
            if file.endswith('.html'):
                if add_csrf(os.path.join(root, file)):
                    files_updated += 1
                    print(f"Added CSRF to: {os.path.join(root, file)}")

print(f"Total files updated: {files_updated}")
