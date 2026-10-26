"""Incremental folder attributes; bounded FFmpeg/NumPy analysis for small Pis."""
import csv
import fcntl
import logging
import os
import subprocess
import tempfile
from pathlib import Path

LOG = logging.getLogger('piradio.attributes')


def guess(path):
    import numpy as np
    # Analyse a bounded mono sample rather than loading a complete track into RAM.
    def decode(offset):
        result = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '1', '-ss', str(offset),
            '-i', str(path), '-t', '45', '-ac', '1', '-ar', '8000', '-f', 'f32le', '-'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=True)
        return np.frombuffer(result.stdout, dtype='<f4')
    y = decode(30)
    if len(y) < 40000:
        y = decode(0)
    if len(y) < 2048 or not np.isfinite(y).all():
        raise ValueError('No usable audio sample')
    frames = y[:len(y)//1024*1024].reshape(-1, 1024)
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(1024)))
    weights = spectrum.sum(axis=1) + 1e-12
    centroid = float(np.mean((spectrum * np.fft.rfftfreq(1024, 1/8000)).sum(axis=1) / weights))
    rms = float(np.sqrt(np.mean(y*y)))
    envelope = np.sqrt(np.mean(frames*frames, axis=1))
    pulse = float(np.mean(np.abs(np.diff(envelope))) / (np.mean(envelope)+1e-9))
    flatness = float(np.mean(np.exp(np.mean(np.log(spectrum+1e-12), axis=1)) /
                             (np.mean(spectrum, axis=1)+1e-12)))
    # Fixed scales keep append-only estimates independent of the batch size.
    energy = round(40*min(rms/.20, 1) + 40*min(pulse/.35, 1) + 20*min(centroid/2500, 1))
    organics = round(100*(1-min(flatness/.5, 1)))
    return max(0, min(100, energy)), max(0, min(100, organics))


def sync_folder(folder, files, rescore=False, scorer=None):
    """Keep existing values; append successfully analysed missing songs atomically."""
    scorer = scorer or guess
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'song_attributes.csv'
    with (folder / '.song_attributes.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = []
        if target.exists():
            with target.open(newline='') as source:
                rows = list(csv.reader(source))
        existing = {row[0]: i for i, row in enumerate(rows) if len(row) >= 3}
        changed = not target.exists()
        for song in dict.fromkeys(map(str, files)):
            if song in existing and not rescore:
                continue
            try:
                energy, organics = scorer(song)
            except Exception as exc:
                LOG.warning('Cannot estimate %s: %s; will retry next scan', song, exc)
                continue
            row = [song, str(energy), str(organics)]
            if song in existing:
                rows[existing[song]] = row
            else:
                existing[song] = len(rows)
                rows.append(row)
            changed = True
            LOG.info('Estimated %s: energy=%s organics=%s', song, energy, organics)
        if changed:
            fd, temporary = tempfile.mkstemp(prefix='.attributes-', dir=folder)
            try:
                with os.fdopen(fd, 'w', newline='') as output:
                    csv.writer(output).writerows(rows)
                    output.flush()
                    os.fsync(output.fileno())
                os.chmod(temporary, target.stat().st_mode & 0o777 if target.exists() else 0o644)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return target


def pools(config, root='/pirateradio'):
    from .daypart import scan
    periods = config.get('day_schedule', {}).get('periods', {})
    reserved = [p['music_folder'] for p in periods.values()]
    yield 'main', root, scan(root, reserved + [str(Path(root)/'announce')])
    for name, period in periods.items():
        yield name, period['music_folder'], scan(period['music_folder'])


def sync_all(config, root='/pirateradio'):
    for name, folder, files in pools(config, root):
        sync_folder(folder, files)
        LOG.info('Attributes ready: %s (%s songs)', name, len(files))


def main():
    import argparse
    from .common import load_config
    parser = argparse.ArgumentParser(description='Estimate song attributes independently for each music folder')
    parser.add_argument('--config', default='/etc/piradio-internet/config.json')
    parser.add_argument('--folder', default='all', help='all, main, morning, day, evening, night, or an absolute folder path')
    parser.add_argument('--rescore-all', action='store_true', help='Explicitly overwrite existing values')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    config = load_config(args.config)
    selected = list(pools(config))
    if args.folder != 'all':
        selected = [p for p in selected if p[0] == args.folder or p[1] == args.folder]
        if not selected:
            if not Path(args.folder).is_absolute():
                parser.error('Unknown folder name')
            from .daypart import scan
            selected = [(args.folder, args.folder, scan(args.folder))]
    for name, folder, files in selected:
        target = sync_folder(folder, files, args.rescore_all)
        print(f'{name}: {target} ({len(files)} songs)')


if __name__ == '__main__':
    main()
