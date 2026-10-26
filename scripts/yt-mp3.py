#!/usr/bin/env python3
"""Interactive YouTube MP3 importer for the station's folder libraries."""
import argparse
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'modules'))
from internet.attributes import sync_folder
from internet.common import load_config


def parse_link(value):
    value = value.strip().strip('\"\'<>').replace('\\&', '&').replace('&amp;', '&')
    if '://' not in value:
        value = 'https://' + value
    parsed = urlsplit(value)
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
        raise ValueError('Enter a YouTube video link.')
    parts = parsed.path.strip('/').split('/')
    if host in ('youtu.be', 'www.youtu.be'):
        video = parts[0]
    elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com',
                  'youtube-nocookie.com', 'www.youtube-nocookie.com'):
        if parts[0] == 'watch':
            video = parse_qs(parsed.query).get('v', [''])[0]
        elif parts[0] in ('shorts', 'live', 'embed') and len(parts) == 2:
            video = parts[1]
        else:
            video = ''
    else:
        raise ValueError('That is not a YouTube link.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
        raise ValueError('No valid video ID found; paste a single-video link.')
    return 'https://www.youtube.com/watch?v=' + video


def score(label):
    while True:
        value = input(f'{label} (0–100) [50]: ').strip()
        if not value:
            return 50
        try:
            result = int(value)
            if 0 <= result <= 100:
                return result
        except ValueError:
            pass
        print('Enter a whole number from 0 to 100, or press Enter for 50.')


def choose_folder(config):
    choices = [('main', '/pirateradio')]
    choices.extend((name, p['music_folder']) for name, p in
                   config.get('day_schedule', {}).get('periods', {}).items())
    print('Choose the music folder:')
    for i, (name, folder) in enumerate(choices, 1):
        print(f'  {i}. {name} — {folder}')
    while True:
        answer = input('Folder (number or name) [main]: ').strip().lower() or 'main'
        for i, (name, folder) in enumerate(choices, 1):
            if answer in (name, str(i)):
                path = Path(folder)
                path.mkdir(parents=True, exist_ok=True)
                if not os.access(path, os.W_OK):
                    raise PermissionError(f'Cannot write {path}; run this script with sudo.')
                return path
        print('Choose one of the listed folders.')


def download(url, temporary):
    import yt_dlp
    options = {
        'format': 'bestaudio/best', 'noplaylist': True,
        'outtmpl': str(Path(temporary) / '%(title).150B [%(id)s].%(ext)s'),
        'restrictfilenames': True, 'ffmpeg_location': '/usr/bin',
        'retries': 5, 'fragment_retries': 5, 'socket_timeout': 30,
        'concurrent_fragment_downloads': 1,
        'postprocessor_args': {'ffmpeg': ['-threads', '1']},
        'js_runtimes': {'deno': {'path': '/home/njm/.local/bin/deno'}},
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3',
                            'preferredquality': '192'}],
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=True)
        if not info or info.get('_type') == 'playlist':
            raise ValueError('Expected one video.')
    files = list(Path(temporary).glob('*.mp3'))
    if len(files) != 1 or files[0].stat().st_size == 0:
        raise RuntimeError('Download did not produce a complete MP3.')
    return files[0]


def import_song(folder, url, energy=None, organics=None, prefix=None):
    # Hidden staging directory is excluded by its empty visible audio pool;
    # use /var/tmp so the recursive station scanner cannot find it.
    with tempfile.TemporaryDirectory(prefix='piradio-download-', dir='/var/tmp') as temporary:
        audio = download(url, temporary)
        target = folder / ((prefix + '_' if prefix else '') + audio.name)
        if target.exists():
            print(f'Already present: {target.name}; keeping the existing file and scores.')
            return target
        energy = score('Energy') if energy is None else energy
        organics = score('Organics') if organics is None else organics
        # Publish scores first, then atomically expose the complete audio file.
        # Stage on the target filesystem to make the final rename atomic.
        import shutil
        fd, staging = tempfile.mkstemp(prefix='.import-', suffix='.tmp', dir=folder)
        os.close(fd)
        try:
            shutil.copyfile(audio, staging)
            os.chmod(staging, 0o644)
            sync_folder(folder, [str(target)], rescore=True,
                        scorer=lambda path: (energy, organics))
            os.replace(staging, target)
        finally:
            if os.path.exists(staging):
                os.unlink(staging)
        print(f'Added {target.name} — energy {energy}, organics {organics}', flush=True)
        return target


def run_batch(args):
    import csv, fcntl, shutil, time, signal
    def stop_batch(signum, frame):
        raise SystemExit(143)
    signal.signal(signal.SIGTERM, stop_batch)
    from internet.common import atomic_json, read_json
    if not all(0 <= value <= 100 for value in (args.energy, args.organics)):
        raise ValueError('Scores must be between 0 and 100')
    folder = Path('/pirateradio' if args.folder == 'main' else args.folder)
    if not folder.is_absolute():
        raise ValueError('Batch destination must be main or an absolute path')
    folder.mkdir(parents=True, exist_ok=True)
    state_path = Path(args.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = read_json(state_path, {'jobs': {}})
        with open(args.batch, newline='') as source:
            jobs = list(csv.DictReader(source))
        for index, job in enumerate(jobs, 1):
            url = parse_link(job['youtube_url'])
            record = state['jobs'].get(url, {})
            if record.get('status') in ('complete','duplicate') and Path(record.get('path','/missing')).is_file():
                continue
            if record.get('status') == 'failed' and not args.retry_failed:
                continue
            video_id = url.rsplit('=',1)[1]
            existing = next((p for p in folder.glob('*.mp3') if '['+video_id+']' in p.name), None)
            if existing:
                state['jobs'][url] = dict(status='duplicate', path=str(existing), title=job['title'], artist=job['artist'])
                atomic_json(state_path,state)
                continue
            duration = float(job.get('duration') or 3600)
            needed = int(duration * 24000 * 3) + 2 * 1024**3
            if min(shutil.disk_usage(folder).free,shutil.disk_usage('/var/tmp').free) < needed:
                state['blocked'] = 'Insufficient disk space for '+job['title']
                atomic_json(state_path,state)
                print(state['blocked'], flush=True)
                return 2
            state.pop('blocked',None)
            state['current'] = dict(job, index=index, total=len(jobs), started=time.time())
            atomic_json(state_path,state)
            print(f"[{index}/{len(jobs)}] {job['artist']} — {job['title']} ({duration/60:.0f} minutes)",flush=True)
            try:
                target = import_song(folder,url,args.energy,args.organics,prefix=job['artist'])
                state['jobs'][url] = dict(status='complete',path=str(target),title=job['title'],artist=job['artist'],finished=time.time())
            except Exception as exc:
                state['jobs'][url] = dict(status='failed',title=job['title'],artist=job['artist'],error=str(exc)[:1000])
                print('Failed; continuing:',str(exc),flush=True)
            state.pop('current',None)
            atomic_json(state_path,state)
        state['finished'] = time.time()
        atomic_json(state_path,state)
        print('Batch finished. Completed:',sum(j.get('status')=='complete' for j in state['jobs'].values()),
              'Failed:',sum(j.get('status')=='failed' for j in state['jobs'].values()),flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='/etc/piradio-internet/config.json')
    parser.add_argument('--batch', help='CSV with artist, title, youtube_url, duration columns')
    parser.add_argument('--folder', default='main', help='Batch destination: main or absolute folder')
    parser.add_argument('--energy', type=int, default=30)
    parser.add_argument('--organics', type=int, default=50)
    parser.add_argument('--state', default='/var/lib/piradio-download/batch-progress.json')
    parser.add_argument('--retry-failed', action='store_true')
    args = parser.parse_args()
    if args.batch:
        return run_batch(args)
    try:
        folder = choose_folder(load_config(args.config))
        print(f'Adding to {folder}. An empty link exits.')
        while True:
            link = input('\nYouTube link (Enter to finish): ').strip()
            if not link:
                break
            try:
                import_song(folder, parse_link(link))
            except Exception as exc:
                print(f'Could not add this song: {exc}\nTry another link.')
    except (KeyboardInterrupt, EOFError):
        print('\nFinished.')
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
