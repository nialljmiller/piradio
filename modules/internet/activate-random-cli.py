"""Use both subscription writers; temporarily cool down Google's empty/busy response."""
import fcntl
import hashlib
import json
import os
import pwd
import shutil
import sys
import time
from pathlib import Path
sys.path.insert(0,'/home/njm/piradio/modules')
from internet.common import atomic_json,read_json
state=Path('/var/lib/piradio-internet')
with (state/'worker.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    for name in ('cli.py','worker.py'):
        shutil.copyfile(Path(__file__).parent/name,Path('/usr/local/lib/piradio/internet')/name)
    path=Path('/etc/piradio-internet/config.json');data=read_json(path,{})
    data.update(text_provider='random-cli',gemini_cli_model='gemini-3.8-flash-low',google_cli_authenticated=True)
    atomic_json(path,data);path.chmod(0o644)
    auth=Path('/home/njm/.gemini/antigravity-cli/antigravity-oauth-token')
    fingerprint=hashlib.sha256(str(auth.stat().st_mtime_ns).encode()).hexdigest()
    cooldown=state/'text-unavailable-gemini-cli.json'
    atomic_json(cooldown,{'key':fingerprint,'until':time.time()+900,'status':'google-capacity-unavailable'})
    user=pwd.getpwnam('njm');os.chown(cooldown,user.pw_uid,user.pw_gid)
    print('Random CLI mode enabled. Google temporarily cooling down; daily caps unchanged.')
