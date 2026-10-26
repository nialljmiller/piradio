#!/usr/bin/python3
"""Enable the staged module only after successfully generating a cached recording."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, '/usr/local/lib/piradio')
from internet.common import atomic_json, load_config

if os.geteuid() != 0:
    raise SystemExit('Run with sudo')
config_path = Path('/etc/piradio-internet/config.json')
config = load_config(config_path)
if not Path('/etc/piradio-internet/credentials.env').is_file():
    raise SystemExit('Credentials are not configured')
state = Path(config['state_dir'])
# Include commissioning calls in the same daily allowance as normal generation.
previous_budget = state / 'test' / 'budget.json'
budget_path = state / 'budget.json'
if previous_budget.exists() and not budget_path.exists():
    atomic_json(budget_path, json.loads(previous_budget.read_text()))
    shutil.chown(budget_path, user='njm', group='njm')
config['text_model'] = 'gemini-3.5-flash-lite'
config['enabled'] = True
atomic_json(config_path, config)
os.chmod(config_path, 0o644)
try:
    subprocess.run(['systemctl', 'start', 'piradio-internet.service'], check=True)
    catalog = json.loads((state / 'catalog.json').read_text())
    if not any(c.get('ready') and c['expires'] > time.time() for c in catalog['clips']):
        raise RuntimeError('No fresh verified recording available')
except Exception:
    config['enabled'] = False
    atomic_json(config_path, config)
    os.chmod(config_path, 0o644)
    raise SystemExit('Generation not ready; module remains disabled and original radio continues')
launcher = Path('/usr/local/lib/piradio/foreground.py')
backup = launcher.with_name('foreground.before-internet.py')
if not backup.exists():
    shutil.copy2(launcher, backup)
shutil.copy2(Path(__file__).with_name('foreground.py'), launcher)
os.chmod(launcher, 0o755)
try:
    subprocess.run(['systemctl', 'restart', 'pirateradio'], check=True)
    time.sleep(5)
    subprocess.run(['systemctl', 'is-active', '--quiet', 'pirateradio'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'piradio-internet.timer'], check=True)
except Exception:
    config['enabled'] = False
    atomic_json(config_path, config)
    os.chmod(config_path, 0o644)
    shutil.copy2(backup, launcher)
    subprocess.run(['systemctl', 'disable', '--now', 'piradio-internet.timer'])
    subprocess.run(['systemctl', 'restart', 'pirateradio'])
    raise SystemExit('Activation failed; original radio restored')
print('Internet bulletins enabled; generator timer and radio are active.')
