import logging
import os
import pwd
from pathlib import Path
import sys
sys.path.insert(0, '/usr/local/lib/piradio')
from internet.common import load_config, read_json
from internet.worker import Budget, voice_provider, refresh
from internet.segments import prepare_connectors

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
for line in Path('/etc/piradio-internet/credentials.env').read_text().splitlines():
    if line.startswith(('GEMINI_API_KEY=', 'FISH_API_KEY=')):
        key, value = line.split('=', 1)
        os.environ[key] = value
config = load_config('/etc/piradio-internet/segmented-preview.json')
account = pwd.getpwnam('njm')
os.initgroups('njm', account.pw_gid)
os.setgid(account.pw_gid)
os.setuid(account.pw_uid)
try:
    prepare_connectors(config, voice_provider(config, Budget(config)))
    print('LIBRARY READY: twelve reusable connectors', flush=True)
    refresh(config)
    catalog = read_json(Path(config['state_dir']) / 'catalog.json', {'clips': []})
    for clip in catalog['clips']:
        if clip.get('ready'):
            print('CACHED BULLETIN: %.1f seconds; sections: %s' % (clip['duration'],
                  ', '.join(s['kind'] for s in clip.get('sections', []))), flush=True)
            print(clip['script'], flush=True)
except Exception as exc:
    if hasattr(exc, 'code'):
        print('Provider HTTP status: ' + str(exc.code), flush=True)
        import json
        try:
            raw = exc.read(8192).decode(errors='replace')
            try:
                error = json.loads(raw).get('error', {})
                if not isinstance(error, dict):
                    error = {'message': str(error)}
            except ValueError:
                error = {'message': raw}
            message = str(error.get('message', ''))[:500]
            for key in ('GEMINI_API_KEY', 'FISH_API_KEY'):
                message = message.replace(os.environ.get(key, 'secret-placeholder'), '[redacted]')
            print(str(error.get('status', '')) + ': ' + message, flush=True)
        except Exception:
            pass
    print('Preparation stopped: ' + type(exc).__name__, flush=True)
    raise SystemExit(1)
