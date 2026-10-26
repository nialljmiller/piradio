import hashlib
import json
import time
from pathlib import Path
from sys import path
path.insert(0, '/usr/local/lib/piradio')
from internet.common import atomic_json
key = next(line.split('=', 1)[1] for line in Path('/etc/piradio-internet/credentials.env').read_text().splitlines() if line.startswith('GEMINI_API_KEY='))
state = Path('/var/lib/piradio-internet/segmented-preview')
atomic_json(state / 'text-unavailable.json', {'key': hashlib.sha256(key.encode()).hexdigest(), 'until': time.time()+86400, 'status': 402})
p = state / 'catalog.json'
c = json.loads(p.read_text()); c['last_generation_attempt'] = 0; p.write_text(json.dumps(c))
import os, pwd
account = pwd.getpwnam('njm')
os.chown(state / 'text-unavailable.json', account.pw_uid, account.pw_gid)
print('Recorded confirmed Gemini 402; next attempt delayed for 24 hours unless the key changes.')
