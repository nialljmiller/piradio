"""Install optional Grok text support while retaining the active text provider."""
import json
import os
import shutil
from pathlib import Path
root=Path(__file__).parent
for name in ('grok.py','worker.py','segments.py','common.py'):
    shutil.copyfile(root/name,Path('/usr/local/lib/piradio/internet')/name)
config_path=Path('/etc/piradio-internet/config.json')
config=json.loads(config_path.read_text())
config.setdefault('text_provider','gemini')
config.setdefault('grok_text_model','grok-4.7')
config.setdefault('grok_max_tokens',1536)
backup=config_path.with_name('config.before-grok.json')
if not backup.exists(): shutil.copy2(config_path,backup)
temporary=config_path.with_suffix('.grok.tmp')
temporary.write_text(json.dumps(config,indent=2)+'\n'); temporary.chmod(0o644); temporary.replace(config_path)
print('Grok installed. Active text provider:',config['text_provider'])
