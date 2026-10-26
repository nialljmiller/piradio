"""Enable day-aware folders for the talking clips between songs."""
import json
import os
import pwd
import shutil
from pathlib import Path
config_path=Path('/etc/piradio-internet/config.json')
config=json.loads(config_path.read_text())
backup=config_path.with_name('config.before-transitions.json')
if not backup.exists(): shutil.copy2(config_path,backup)
user=pwd.getpwnam('njm')
root=Path('/pirateradio/announce')
for name,period in config['day_schedule']['periods'].items():
    folder=root/name; folder.mkdir(exist_ok=True)
    os.chown(folder,user.pw_uid,user.pw_gid)
    period['transition_folder']=str(folder)
temporary=config_path.with_suffix('.transitions.tmp')
temporary.write_text(json.dumps(config,indent=2)+'\n'); temporary.chmod(0o644); temporary.replace(config_path)
shutil.copyfile(Path(__file__).parent/'daypart.py','/usr/local/lib/piradio/internet/daypart.py')
print('Time-dependent transitions installed.')
