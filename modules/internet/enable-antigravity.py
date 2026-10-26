"""Stage Google's supported subscription CLI; random activation follows live verification."""
import json
import shutil
from pathlib import Path
for name in ('cli.py',):
    shutil.copyfile(Path(__file__).parent/name,Path('/usr/local/lib/piradio/internet')/name)
p=Path('/etc/piradio-internet/config.json');data=json.loads(p.read_text())
data.update(gemini_cli_kind='antigravity',gemini_cli_path='/home/njm/.local/bin/agy',gemini_cli_model='gemini-3.8-flash-medium')
tmp=p.with_suffix('.agy.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');tmp.chmod(0o644);tmp.replace(p)
print('Google subscription writer staged using Antigravity; active writer:',data['text_provider'])
