"""Enable Grok subscription CLI, retaining factual fallback and FM playback."""
import json
import shutil
from pathlib import Path
root=Path(__file__).parent
for name in ('cli.py','worker.py','segments.py','common.py'):
    shutil.copyfile(root/name,Path('/usr/local/lib/piradio/internet')/name)
config=Path('/etc/piradio-internet/config.json')
backup=config.with_name('config.before-cli.json')
if not backup.exists(): shutil.copy2(config,backup)
data=json.loads(config.read_text());data.update(text_provider='grok-cli',grok_cli_path='/home/njm/.grok/bin/grok',cli_timeout_seconds=120)
temporary=config.with_suffix('.cli.tmp');temporary.write_text(json.dumps(data,indent=2)+'\n');temporary.chmod(0o644);temporary.replace(config)
dropin=Path('/etc/systemd/system/piradio-internet.service.d');dropin.mkdir(exist_ok=True)
(dropin/'subscription-cli.conf').write_text('[Service]\nProtectHome=read-only\nReadWritePaths=/home/njm/.grok\nMemoryMax=256M\nEnvironment=HOME=/home/njm\n')
print('Subscription CLI selected. No FM restart required.')
