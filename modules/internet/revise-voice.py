import hashlib
import json
import os
import sys
import time
from pathlib import Path
sys.path.insert(0, '/usr/local/lib/piradio')
from internet.common import atomic_json, load_config
from internet.worker import Gemini, Budget, render
config_path = Path('/etc/piradio-internet/config.json')
config = load_config(config_path)
new = load_config('/home/njm/piradio/modules/internet/config.example.json')
for key in ('host_name', 'station_name', 'voice_style'):
    config[key] = new[key]
atomic_json(config_path, config)
os.chmod(config_path, 0o644)
state = Path(config['state_dir'])
catalog = json.loads((state / 'catalog.json').read_text())
items = catalog['clips'][-1]['sources']
# Remove old identity recordings from eligibility before making any new request.
catalog['clips'] = []
atomic_json(state / 'catalog.json', catalog)
key = Path('/etc/piradio-internet/credentials.env').read_text().strip().split('=', 1)[1]
os.environ['GEMINI_API_KEY'] = key
provider = Gemini(config, Budget(config))
script, used = provider.script(items)
now = time.time()
entry = dict(id=hashlib.sha256(script.encode()).hexdigest(), script=script, kind='news',
             created=now, expires=now+config['news_ttl_seconds'], ready=False,
             sources=[item for item in items if item['id'] in used])
entry['topics'] = list(dict.fromkeys(topic for item in entry['sources'] for topic in item.get('topics', [])))
entry['expires'] = min([entry['expires']] + [item['expires'] for item in entry['sources'] if 'expires' in item])
catalog['clips'] = [entry]
catalog['last_generation_attempt'] = now
atomic_json(state / 'catalog.json', catalog)
render(config, catalog, provider, entry)
for path in (state / 'catalog.json', state / 'budget.json'):
    import shutil
    shutil.chown(path, user='njm', group='njm')
print('Revised recording ready:', round(entry['duration'], 1), 'seconds', flush=True)
print(script, flush=True)
