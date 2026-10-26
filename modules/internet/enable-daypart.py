import fcntl
import os
import pwd
import shutil
import time
from pathlib import Path
import sys
sys.path.insert(0, '/home/njm/piradio/modules')
from internet.common import atomic_json, load_config, read_json
from internet.daypart import current_period, effective_config, music_pool

repo = Path('/home/njm/piradio/modules/internet')
config_path = Path('/etc/piradio-internet/config.json')
config = load_config(config_path)
example = load_config(repo / 'config.example.json')
state = Path(config['state_dir'])
account = pwd.getpwnam('njm')
with (state / 'worker.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    backup = config_path.with_name('config.before-daypart.json')
    if not backup.exists():
        shutil.copyfile(config_path, backup)
    config['day_schedule'] = example['day_schedule']
    for name in ('morning', 'day', 'evening', 'night'):
        folder = Path(config['day_schedule']['periods'][name]['music_folder'])
        folder.mkdir(exist_ok=True)
        os.chown(folder, account.pw_uid, account.pw_gid)
        folder.chmod(0o755)
    atomic_json(config_path, config)
    config_path.chmod(0o644)
    load_config(config_path)
    # Seed independent clocks from the last completed combined bulletin.
    history_path = state / 'play-history.json'
    history = read_json(history_path, {})
    if '_section_plays' not in history:
        last = max([record.get('last_played', 0) if isinstance(record, dict) else record
                    for key, record in history.items() if not key.startswith('_')] or [0])
        history['_section_plays'] = {'news': last, 'weather': last}
        atomic_json(history_path, history)
        os.chown(history_path, account.pw_uid, account.pw_gid)
    catalog_path = state / 'catalog.json'
    catalog = read_json(catalog_path, {})
    catalog.setdefault('last_weather_generation', catalog.get('last_generation_attempt', time.time()))
    atomic_json(catalog_path, catalog)
    os.chown(catalog_path, account.pw_uid, account.pw_gid)
    installed = Path('/usr/local/lib/piradio/internet')
    for name in ('daypart.py', 'common.py', 'player.py', 'worker.py', 'segments.py'):
        shutil.copyfile(repo / name, installed / name)
    launcher = Path('/usr/local/lib/piradio/foreground.py')
    backup_launcher = launcher.with_name('foreground.before-daypart.py')
    if not backup_launcher.exists():
        shutil.copyfile(launcher, backup_launcher)
    shutil.copyfile(repo / 'foreground.py', launcher)
    launcher.chmod(0o644)
    folder, files = music_pool(config)
    print('Day feature enabled:', current_period(config), 'timezone:', config['day_schedule']['timezone'])
    print('Current music pool:', folder, 'songs:', len(files))
    print('Period folders ready; original media and song attributes retained.')
