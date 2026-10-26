import json
import os
import pwd
import shutil
import subprocess
import time
from pathlib import Path
import sys
sys.path.insert(0, '/usr/local/lib/piradio')
from internet.common import atomic_json, load_config
from internet.player import Relay

repo = Path('/home/njm/piradio/modules/internet')
config_path = Path('/etc/piradio-internet/config.json')
config = load_config(config_path)
preview = Path('/var/lib/piradio-internet/segmented-preview')
main = Path(config['state_dir'])
catalog = json.loads((preview / 'catalog.json').read_text())
ready = [c for c in catalog['clips'] if c.get('ready') and c['expires'] > time.time()]
if not ready or not any({s['kind'] for s in c.get('sections', [])} == {'weather', 'news'} for c in ready):
    raise SystemExit('A complete, fresh weather and news bulletin is required before activation.')
backup = main / 'catalog.before-segments.json'
if (main / 'catalog.json').exists() and not backup.exists():
    shutil.copyfile(main / 'catalog.json', backup)
shutil.copytree(preview / 'audio', main / 'audio', dirs_exist_ok=True)
def relocate(value):
    if isinstance(value, dict):
        return {k: relocate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [relocate(v) for v in value]
    if isinstance(value, str) and value.startswith(str(preview) + '/'):
        return str(main) + value[len(str(preview)):]
    return value
for name in ('catalog.json', 'connectors.json', 'text-unavailable.json'):
    source = preview / name
    if source.exists():
        atomic_json(main / name, relocate(json.loads(source.read_text())))
account = pwd.getpwnam('njm')
for directory, dirs, files in os.walk(main):
    os.chown(directory, account.pw_uid, account.pw_gid)
    for filename in files:
        os.chown(Path(directory) / filename, account.pw_uid, account.pw_gid)
launcher = Path('/usr/local/lib/piradio/foreground.py')
backup_launcher = launcher.with_name('foreground.before-segmented.py')
if not backup_launcher.exists():
    shutil.copyfile(launcher, backup_launcher)
shutil.copyfile(repo / 'foreground.py', launcher)
shutil.copyfile(repo / 'systemd/piradio-internet.timer', '/etc/systemd/system/piradio-internet.timer')
config['enabled'] = True
atomic_json(config_path, config)
config_path.chmod(0o644)
# Validate complete local assembly and queue eligibility before changing playback.
clip = Relay(config).choose()
if not clip:
    config['enabled'] = False
    atomic_json(config_path, config)
    config_path.chmod(0o644)
    raise SystemExit('The cached bulletin is not playable; station not restarted.')
try:
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', 'pirateradio'], check=True)
    subprocess.run(['systemctl', 'restart', 'pirateradio'], check=True)
    subprocess.run(['systemctl', 'is-active', '--quiet', 'pirateradio'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'piradio-internet.timer'], check=True)
    subprocess.run(['systemctl', 'start', 'piradio-internet.service'], check=True)
except Exception:
    config['enabled'] = False
    atomic_json(config_path, config)
    config_path.chmod(0o644)
    shutil.copyfile(backup_launcher, launcher)
    subprocess.run(['systemctl', 'disable', '--now', 'piradio-internet.timer'])
    subprocess.run(['systemctl', 'restart', 'pirateradio'])
    raise
print('Normal operation enabled. First bulletin eligible after 30 seconds, then every 20 minutes.')
print('Complete bulletin %.1f seconds; persistent connector library ready.' % clip['duration'])
