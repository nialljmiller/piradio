import subprocess
import time
from pathlib import Path
clip = '/var/lib/piradio-internet/test/sample.wav'
if not Path(clip).is_file():
    raise SystemExit('Verified test clip missing')
# Wait for music; never stop a spoken announcement for this test.
for attempt in range(120):
    result = subprocess.check_output(['journalctl', '-u', 'pirateradio', '-n', '30', '--no-pager'], text=True)
    transitions = [line for line in result.splitlines() if 'Playing song ' in line or 'Playing announcement ' in line]
    if transitions and 'Playing song ' in transitions[-1]:
        break
    time.sleep(5)
else:
    raise SystemExit('Announcement still playing; test deferred')
subprocess.run(['systemctl', 'stop', 'pirateradio'], check=True)
try:
    print('Broadcasting the 36-second bulletin at 92.1 MHz now.', flush=True)
    encoder = subprocess.Popen(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-i', clip,
        '-f', 's16le', '-acodec', 'pcm_s16le', '-ac', '2', '-ar', '44100', '-'], stdout=subprocess.PIPE)
    transmitter = subprocess.Popen(['/root/pifm', '-', '92.1', '44100', 'stereo'], stdin=encoder.stdout,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    encoder.stdout.close()
    try:
        code = transmitter.wait(timeout=75)
        encoder.wait(timeout=5)
        print('Bulletin finished. Transmitter exit:', code, flush=True)
    finally:
        for process in (encoder, transmitter):
            if process.poll() is None:
                process.kill()
                process.wait()
finally:
    subprocess.run(['systemctl', 'start', 'pirateradio'], check=True)
    print('Normal Pirate Radio restarted.', flush=True)
