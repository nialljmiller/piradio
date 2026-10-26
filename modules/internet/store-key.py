import os
from pathlib import Path
source = Path('/home/njm/.piradio-gemini.key')
key = source.read_text().strip()
if not key or any(c.isspace() for c in key) or not all(c.isalnum() or c in '._-' for c in key):
    raise SystemExit('Invalid key format')
path = '/etc/piradio-internet/credentials.env'
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.fchmod(fd, 0o600)
with os.fdopen(fd, 'w') as output:
    output.write('GEMINI_API_KEY=' + key + '\n')
source.unlink()
print('Credentials stored; no API request made.')
