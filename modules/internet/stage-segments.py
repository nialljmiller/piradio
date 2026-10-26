import json
import os
import pwd
import shutil
import subprocess
from pathlib import Path

repo = Path('/home/njm/piradio/modules/internet')
installed = Path('/usr/local/lib/piradio/internet')
for name in ('fish.py', 'common.py', 'worker.py', 'player.py', 'segments.py'):
    shutil.copyfile(repo / name, installed / name)
config_path = Path('/etc/piradio-internet/config.json')
config = json.loads(config_path.read_text())
example = json.loads((repo / 'config.example.json').read_text())
for name in ('text_failure_fallback', 'first_bulletin_delay_seconds', 'segmented_bulletins', 'max_bulletin_seconds', 'repeat_after_seconds',
             'max_repeats_per_news_recording', 'generation_interval_seconds',
             'news_generation_interval_seconds', 'weather_ttl_seconds',
             'max_text_calls_per_day', 'max_text_tokens_per_day',
             'max_voice_calls_per_day', 'max_voice_seconds_per_day', 'connectors'):
    config[name] = example[name]
config['enabled'] = False
references = [{'audio': config['fish_reference_audio'], 'text': config['fish_reference_text']}]
for filename, transcript, destination in (
    ('why-did-the-pirate-play-the-guitar-because-he-loved-strummin-up-trouble-now-listen-close-for-the-next-troublemaker-101soundboards.mp3',
     'Why did the pirate play the guitar? Because he loved strummin up trouble! Now listen close for the next troublemaker!', 'guitar.wav'),
    ('get-ready-to-raise-yer-tankards-and-stomp-yer-feet-me-hearties-for-the-next-tune-be-fiercer-than-blackbeard-himself-101soundboards.mp3',
     'Get ready to raise yer tankards and stomp yer feet, me hearties, for the next tune be fiercer than Blackbeard himself!', 'tankards.wav')):
    output = Path('/var/lib/piradio-internet/reference') / destination
    subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                    '-i', str(Path('/pirateradio/announce') / filename), '-t', '20',
                    '-ac', '1', '-ar', '24000', '-c:a', 'pcm_s16le', str(output)], check=True)
    references.append({'audio': str(output), 'text': transcript})
config['fish_references'] = references
backup = config_path.with_name('config.before-segments.json')
if not backup.exists():
    shutil.copyfile(config_path, backup)
config_path.write_text(json.dumps(config, indent=2) + '\n')
preview = dict(config, enabled=True, state_dir='/var/lib/piradio-internet/segmented-preview',
               budget_state_dir=config['state_dir'])
preview_path = Path('/etc/piradio-internet/segmented-preview.json')
preview_path.write_text(json.dumps(preview, indent=2) + '\n')
account = pwd.getpwnam('njm')
Path(preview['state_dir']).mkdir(exist_ok=True)
os.chown(preview['state_dir'], account.pw_uid, account.pw_gid)
print('Segment module staged; three reference clips; automatic broadcasts remain disabled.')
