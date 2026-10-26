import json
import os
import shutil
import sys
from pathlib import Path
sys.path.insert(0, '/usr/local/lib/piradio')
from internet.common import atomic_json, load_config
from internet.worker import Gemini, Budget, render
path = Path('/etc/piradio-internet/config.json')
config = load_config(path)
new = load_config('/home/njm/piradio/modules/internet/config.example.json')
config['voice_style'] = new['voice_style']
atomic_json(path, config)
os.chmod(path, 0o644)
state = Path(config['state_dir'])
preview = dict(config, state_dir=str(state / 'preview'))
catalog = json.loads((state / 'preview/catalog.json').read_text())
entry = catalog['clips'][0]
entry['ready'] = False
atomic_json(state / 'preview/catalog.json', catalog)
secret = Path('/etc/piradio-internet/credentials.env').read_text().strip().split('=', 1)[1]
os.environ['GEMINI_API_KEY'] = secret
render(preview, catalog, Gemini(config, Budget(config)), entry)
shutil.chown(state / 'budget.json', user='njm', group='njm')
print('Stronger English pirate preview ready:', round(entry['duration'], 1), 'seconds. Held for your cue.', flush=True)
