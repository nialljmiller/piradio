import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0, '/usr/local/lib/piradio')
from internet.common import load_config
from internet.player import Relay, write_all
config = load_config('/etc/piradio-internet/config.json')
state = Path(config['state_dir'])
preview = json.loads((state / 'preview/catalog.json').read_text())['clips'][0]
if not preview.get('ready') or preview['expires'] <= time.time():
    raise SystemExit('Fresh preview unavailable')
main_pid = int(subprocess.check_output(['systemctl', 'show', 'pirateradio', '-p', 'MainPID', '--value']))
cgroup = Path('/proc/' + str(main_pid) + '/cgroup').read_text().strip().split('::', 1)[1]
children = []
radio_processes = []
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        stat = (proc/'stat').read_text().rsplit(')', 1)[1].split()
        args = (proc/'cmdline').read_bytes().split(b'\0')
        if int(stat[1]) == main_pid:
            children.append((int(proc.name), args))
        if (proc/'cgroup').read_text().strip().split('::', 1)[1] == cgroup:
            radio_processes.append((int(proc.name), args))
    except (OSError, ValueError, IndexError):
        pass
fm = next((pid for pid, args in radio_processes if args and b'pi_fm_rds' in args[0]), None)
if fm is None:
    raise SystemExit('Transmitter not found')
# Actual source decoder must be playing music, not a pirate announcement.
music = [args for pid, args in children if args and b'ffmpeg' in args[0] and b'-i' in args]
if not music or any(b'/announce/' in args[args.index(b'-i')+1] for args in music):
    raise SystemExit('Pirate announcement is playing; defer the test')
# The original module opens its music pipe before any other pipes: fd 3.
# Validate it remains a read-only anonymous pipe before duplicating it.
parent_fd = Path('/proc/' + str(main_pid) + '/fd/3')
flags = Path('/proc/' + str(main_pid) + '/fdinfo/3').read_text()
if not os.readlink(parent_fd).startswith('pipe:') or int(next(line.split()[1] for line in flags.splitlines() if line.startswith('flags:')), 8) & os.O_ACCMODE != os.O_RDONLY:
    raise SystemExit('Original music pipe could not be verified')
input_fd = os.open(parent_fd, os.O_RDONLY)
old_relays = [pid for pid, args in radio_processes if pid != os.getpid()
              and any(arg.endswith(b'/test-mix-live.py') for arg in args)]
cgroup = Path('/proc/' + str(main_pid) + '/cgroup').read_text().strip().split('::', 1)[1]
# Detached relay remains inside the radio service cgroup, so a station stop
# kills it and its transmitter. The original song decoder is never restarted.
if os.fork():
    os.close(input_fd)
    print('Live mix test starting; original song decoder stays running.', flush=True)
    raise SystemExit(0)
os.setsid()
log_fd = os.open('/var/lib/piradio-internet/live-mix-test.log', os.O_WRONLY|os.O_CREAT|os.O_APPEND, 0o644)
os.dup2(log_fd, 1)
os.dup2(log_fd, 2)
if log_fd > 2:
    os.close(log_fd)
Path('/sys/fs/cgroup' + cgroup + '/cgroup.procs').write_text(str(os.getpid()))
transmitter = None
speech = None
try:
    for old in old_relays:
        os.kill(old, signal.SIGSTOP)
    os.kill(fm, signal.SIGINT)
    for _ in range(100):
        try:
            status = Path('/proc/' + str(fm) + '/stat').read_text().rsplit(')', 1)[1].split()[0]
            if status == 'Z':
                break
        except FileNotFoundError:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError('Old transmitter did not stop cleanly')
    for old in old_relays:
        os.kill(old, signal.SIGKILL)
    transmitter = subprocess.Popen(['/root/pifm', '-', '92.1', '44100', 'stereo'],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    speech = subprocess.Popen(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
        '-i', preview['audio'], '-af', 'afade=t=in:d=0.3,afade=t=out:st=' + str(preview['duration']-0.3) + ':d=0.3',
        '-f', 's16le', '-ac', '2', '-ar', '44100', '-'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    relay = Relay(config)
    print('ON AIR: Reginald Radio on nill FM; music ducked to 8%.', flush=True)
    while True:
        music_data = os.read(input_fd, 16384)
        if not music_data:
            break
        voice = b''
        if speech is not None:
            voice = speech.stdout.read(len(music_data))
            if not voice:
                code = speech.wait()
                speech.stdout.close()
                speech = None
                print('Bulletin finished; restoring music volume. Voice exit: ' + str(code), flush=True)
        if speech is not None or relay.music_gain < 1:
            music_data = relay.mix(music_data, voice, 2, config['music_duck_gain'] if speech else 1.0)
        write_all(transmitter.stdin.fileno(), music_data)
except Exception as exc:
    print('Relay failure: ' + type(exc).__name__, flush=True)
    subprocess.run(['systemctl', '--no-block', 'restart', 'pirateradio'])
finally:
    os.close(input_fd)
    for proc in (speech, transmitter):
        if proc is not None and proc.poll() is None:
            proc.terminate()
