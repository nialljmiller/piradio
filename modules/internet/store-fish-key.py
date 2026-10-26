import os
from pathlib import Path
source=Path('/home/njm/.piradio-fish.key')
key=source.read_text().strip()
if not key or not all(c.isalnum() or c in '._-' for c in key):
    raise SystemExit('Invalid key format')
p=Path('/etc/piradio-internet/credentials.env')
lines=[line for line in p.read_text().splitlines() if not line.startswith('FISH_API_KEY=')]
fd=os.open(p,os.O_WRONLY|os.O_TRUNC,0o600)
os.fchmod(fd,0o600)
with os.fdopen(fd,'w') as out:
    out.write('\n'.join(lines+['FISH_API_KEY='+key])+'\n')
source.unlink()
print('Fish credentials stored securely.')
