import fcntl
import io
import json
import os
import pwd
import shutil
import wave
from pathlib import Path
import sys
sys.path.insert(0, '/home/njm/piradio/modules')
from internet.common import atomic_json, load_config, read_json
from internet.fish import amplify_pcm

repo = Path('/home/njm/piradio/modules/internet')
config_path = Path('/etc/piradio-internet/config.json')
config = load_config(config_path)
example = load_config(repo / 'config.example.json')
state = Path(config['state_dir'])
account = pwd.getpwnam('njm')
with (state / 'worker.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    marker_path = state / 'speech-gain.json'
    marker = read_json(marker_path, {'gain': 1.0, 'files': {}})
    target = example['fish_speech_gain']
    for path in (state / 'audio').glob('*.wav'):
        if path.name.startswith('assembled-'):
            continue
        applied = marker['files'].get(path.name, marker['gain'])
        if applied == target:
            continue
        with wave.open(str(path)) as wav:
            channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
            if width != 2 or channels not in (1, 2):
                raise ValueError('Unsupported cached speech')
            pcm = wav.readframes(wav.getnframes())
        pcm = amplify_pcm(pcm, rate, channels, target / applied)
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(channels); wav.setsampwidth(width); wav.setframerate(rate)
            wav.writeframes(pcm)
        temporary = path.with_suffix('.gain-tmp')
        temporary.write_bytes(output.getvalue())
        os.chown(temporary, account.pw_uid, account.pw_gid)
        os.replace(temporary, path)
        marker['files'][path.name] = target
        atomic_json(marker_path, marker)
    marker['gain'] = target
    atomic_json(marker_path, marker)
    os.chown(marker_path, account.pw_uid, account.pw_gid)
    for name in ('fish_speech_gain', 'news_topic_priorities', 'priority_override_score',
                 'priority_override_max_age_seconds', 'priority_override_patterns'):
        config[name] = example[name]
    atomic_json(config_path, config)
    config_path.chmod(0o644)
    load_config(config_path)
    for name in ('fish.py', 'worker.py', 'common.py'):
        shutil.copyfile(repo / name, Path('/usr/local/lib/piradio/internet') / name)
    catalog = read_json(state / 'catalog.json', {})
    catalog['last_news_generation'] = 0
    catalog['last_generation_attempt'] = 0
    atomic_json(state / 'catalog.json', catalog)
    os.chown(state / 'catalog.json', account.pw_uid, account.pw_gid)
print('Speech raised 1.94 dB with peak limiting; topical priority and urgency overrides applied. Music was not restarted.')
