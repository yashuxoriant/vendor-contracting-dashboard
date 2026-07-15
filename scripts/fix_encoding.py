import re

# Fix bomSlice.js
path = r'c:\Users\singh_y\workspace\it-contracting-dashboard\frontend\src\store\slices\bomSlice.js'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# These are the mojibake sequences for en-dash/em-dash when UTF-8 was read as latin-1
replacements = [
    ('\u00e2\u0080\u0093', ' - '),   # â€" corrupted en-dash
    ('\u00e2\u0080\u0094', ' - '),   # â€" corrupted em-dash
    ('\u2013', ' - '),               # actual en-dash
    ('\u2014', ' - '),               # actual em-dash
]
for bad, good in replacements:
    content = content.replace(bad, good)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify BOM names
for line in content.split('\n'):
    if "name:'" in line or 'name:"' in line:
        print('BOM name:', line.strip())

print('Done')
