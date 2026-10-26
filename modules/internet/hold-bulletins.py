import json
import os
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, '/usr/local/lib/piradio')
from internet.common import atomic_json
subprocess.run(['systemctl', 'disable', '--now', 'piradio-internet.timer'], check=True)
config_path = Path('/etc/piradio-internet/config.json')
config = json.loads(config_path.read_text())
config['enabled'] = False
atomic_json(config_path, config)
os.chmod(config_path, 0o644)
state = Path(config['state_dir'])
catalog_path = state / 'catalog.json'
catalog = json.loads(catalog_path.read_text())
if catalog.get('clips'):
    atomic_json(state / 'held-catalog.json', catalog)
catalog['clips'] = []
atomic_json(catalog_path, catalog)
import shutil
shutil.chown(catalog_path, user='njm', group='njm')
print('Automatic generation and bulletin playback held. Music continues.')
