import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
from pathlib import Path
sys.path.insert(0, '/usr/local/lib/piradio')
from internet.common import atomic_json, load_config
from internet.worker import Budget, render
from internet.fish import Fish
config=load_config('/etc/piradio-internet/config.json')
state=Path(config['state_dir'])
reference=state/'reference/pirate.wav'
reference.parent.mkdir(parents=True,exist_ok=True)
source='/pirateradio/announce/arrr-that-last-song-hit-harder-than-a-cannonball-to-a-pirate-ship-ready-yer-ears-for-more-treasure-ye-scallywags-101soundboards.mp3'
subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',source,
                '-t','20','-ac','1','-ar','24000',str(reference)],check=True)
config.update(voice_provider='fish',fish_reference_audio=str(reference),
    fish_reference_text='Arrr, that last song hit harder than a cannonball to a pirate ship! Ready yer ears for more treasure, ye scallywags!')
credentials=Path('/etc/piradio-internet/credentials.env').read_text().splitlines()
key=next(line.split('=',1)[1] for line in credentials if line.startswith('FISH_API_KEY='))
os.environ['FISH_API_KEY']=key
preview=dict(config,state_dir=str(state/'preview'))
# Separate commissioning allowance: one explicitly authorized free-provider audition.
allowance=dict(config,state_dir=str(state/'fish-commissioning'),max_voice_calls_per_day=2)
script='Ahoy, me hearties! This be Reginald Radio aboard nill FM! Batten down the hatches, here comes yer weather!'
entry=dict(id=hashlib.sha256(script.encode()).hexdigest(),script=script,kind='evergreen',
           created=time.time(),expires=time.time()+30*86400,ready=False,sources=[],topics=[])
catalog=dict(clips=[entry],seen=[],feeds={})
try:
    render(preview,catalog,Fish(config,Budget(allowance)),entry)
    atomic_json(state/'fish-settings.json',{key:config[key] for key in ('voice_provider','fish_reference_audio','fish_reference_text')})
    print('Fish pirate audition ready:',round(entry['duration'],1),'seconds. Held, not broadcast.',flush=True)
except urllib.error.HTTPError as exc:
    print('Fish request failed. HTTP:',exc.code,flush=True)
    message=exc.read(3000).decode(errors='replace').replace(key,'[redacted]')
    print(message[:1000],flush=True)
    raise SystemExit(1)
