import json
import os
import sys
from pathlib import Path
sys.path.insert(0, '/usr/local/lib/piradio')
from internet.common import load_config
from internet.worker import collect, Gemini, Budget
config = load_config('/etc/piradio-internet/config.json')
config['state_dir'] = '/var/lib/piradio-internet/test'
config['text_model'] = 'gemini-3.5-flash-lite'
Path(config['state_dir']).mkdir(parents=True, exist_ok=True)
secret = Path('/etc/piradio-internet/credentials.env').read_text().strip().split('=', 1)[1]
os.environ['GEMINI_API_KEY'] = secret
reports = collect(config, {})[:2]
print('Fresh reports:', len(reports), flush=True)
if not reports:
    raise SystemExit('No fresh reports available')
provider = Gemini(config, Budget(config))
try:
    script, ids = provider.script(reports)
    print('Script:', script, flush=True)
    data, duration = provider.voice(script)
    Path(config['state_dir'], 'sample.wav').write_bytes(data)
    print('Audio verified:', round(duration, 1), 'seconds', flush=True)
except Exception as exc:
    print('Test failed:', type(exc).__name__, flush=True)
    if hasattr(exc, 'code'):
        print('HTTP status:', exc.code, flush=True)
        try:
            error = json.loads(exc.read(65536)).get('error', {})
            message = str(error.get('message', '')).replace(secret, '[redacted]')
            print('Provider error:', message[:1500], flush=True)
        except Exception:
            pass
    raise SystemExit(1)
