import json
import urllib.error
import urllib.request
from pathlib import Path
key = next(line.split('=', 1)[1] for line in Path('/etc/piradio-internet/credentials.env').read_text().splitlines() if line.startswith('GEMINI_API_KEY='))
request = urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models', headers={'x-goog-api-key': key})
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read(200000))
    print('Models endpoint works; selected model available:', any(m['name'].endswith('gemini-3.5-flash-lite') for m in data.get('models', [])))
except urllib.error.HTTPError as exc:
    body = exc.read(2000).decode(errors='replace').replace(key, '[redacted]')
    print('Model listing HTTP status:', exc.code)
    print(body[:1000])

import os
import sys
sys.path.insert(0, '/usr/local/lib/piradio')
from internet.worker import Budget
from internet.common import load_config
config = load_config('/etc/piradio-internet/config.json')
Budget(config).reserve('text', 1000)
body = {'contents': [{'parts': [{'text': 'Reply with just the word ahoy.'}]}], 'generationConfig': {'maxOutputTokens': 40}}
request = urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent', data=json.dumps(body).encode(), headers={'x-goog-api-key': key, 'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(request, timeout=75) as response:
        data = json.loads(response.read(100000))
    print('GenerateContent endpoint works:', bool(data.get('candidates')))
except urllib.error.HTTPError as exc:
    body = exc.read(4000).decode(errors='replace').replace(key, '[redacted]')
    print('Generation HTTP status:', exc.code)
    print(body[:2000])
