import json
import os
from pathlib import Path
p=Path('/etc/piradio-internet/config.json')
c=json.loads(p.read_text())
c.update(json.loads(Path('/var/lib/piradio-internet/fish-settings.json').read_text()))
c['enabled']=False
p.write_text(json.dumps(c,indent=2)+'\n')
os.chmod(p,0o644)
print('Fish selected; automatic generation remains held.')
