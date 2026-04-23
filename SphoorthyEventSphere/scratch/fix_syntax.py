import os
import re

def fix_syntax(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # Replace url_for('hackathon.endpoint',) with url_for('hackathon.endpoint', 
    content = re.sub(r"url_for\((['\"])hackathon\.([a-zA-Z0-9_]+)\1,\)", r"url_for(\1hackathon.\2\1,", content)

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
                if fix_syntax(os.path.join(root, file)):
                    files_updated += 1
                    print(f"Fixed: {os.path.join(root, file)}")

print(f"Total files fixed: {files_updated}")
