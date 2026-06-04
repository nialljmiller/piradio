"""
filerename.py
Renames bad filenames and rebuilds song_attributes.csv.

Paths in the CSV are always written as /pirateradio/... (the RPi mount path),
regardless of where this script is run from.
"""

import os
import re
import csv

# ── Mount points ──────────────────────────────────────────────────────────────

LOCAL_DIR = next(
    (p for p in ["/pirateradio", "/run/media/njm/PIRATERADIO"] if os.path.isdir(p)),
    None
)
if LOCAL_DIR is None:
    raise RuntimeError("Cannot find PIRATERADIO mount. Is the SD card plugged in?")

RPI_DIR       = "/pirateradio"
CSV_FILE_PATH = os.path.join(LOCAL_DIR, "song_attributes.csv")

# ── Config ────────────────────────────────────────────────────────────────────

AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.wav', '.flac', '.aac'}
SAFE_CHARS  = re.compile(r'[^a-zA-Z0-9_]')  # ASCII only — strips non-English chars too
BITRATE_TAG = re.compile(r'\b\d+[Kk]bit_\w+\b')

# ── Filename logic ────────────────────────────────────────────────────────────

def needs_rename(base):
    return bool(SAFE_CHARS.search(base))

def clean_filename(base):
    base = BITRATE_TAG.sub('', base)
    base = re.sub(SAFE_CHARS, '_', base)
    base = re.sub(r'_+', '_', base)
    return base.strip('_')

# ── Rename pass ───────────────────────────────────────────────────────────────

def rename_files():
    for filename in sorted(os.listdir(LOCAL_DIR)):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in AUDIO_EXTENSIONS:
            continue
        base = os.path.splitext(filename)[0]
        if not needs_rename(base):
            continue
        new_name = clean_filename(base) + ext
        old_path = os.path.join(LOCAL_DIR, filename)
        new_path = os.path.join(LOCAL_DIR, new_name)
        if old_path == new_path:
            continue
        if os.path.exists(new_path):
            print(f"SKIP (collision): '{filename}' -> '{new_name}'")
            continue
        try:
            os.rename(old_path, new_path)
            print(f"Renamed: '{filename}' -> '{new_name}'")
        except Exception as e:
            print(f"Failed:  '{filename}': {e}")

# ── CSV rebuild ───────────────────────────────────────────────────────────────

def build_csv():
    # Load existing scores keyed on the RPI path.
    # Also index by the cleaned version of each path so renamed files
    # (e.g. Japanese chars stripped) recover their old scores.
    existing = {}
    if os.path.exists(CSV_FILE_PATH):
        with open(CSV_FILE_PATH, newline='') as f:
            for row in csv.reader(f):
                if len(row) == 3:
                    rpi_path = re.sub(r'^.*/PIRATERADIO/', RPI_DIR + '/', row[0])
                    existing[rpi_path] = (row[1], row[2])
                    # Also register under the cleaned path
                    base, ext = os.path.splitext(os.path.basename(rpi_path))
                    cleaned_name = clean_filename(base) + ext
                    cleaned_rpi  = os.path.join(os.path.dirname(rpi_path), cleaned_name)
                    if cleaned_rpi != rpi_path:
                        existing.setdefault(cleaned_rpi, (row[1], row[2]))

    music_files = []
    for root, dirs, files in os.walk(LOCAL_DIR):
        dirs.sort()
        dirs[:] = [d for d in dirs if d not in ('announce', 'quarantine')]
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS:
                local_path = os.path.join(root, f)
                rpi_path   = local_path.replace(LOCAL_DIR, RPI_DIR, 1)
                music_files.append(rpi_path)

    with open(CSV_FILE_PATH, 'w', newline='') as f:
        writer = csv.writer(f)
        for rpi_path in music_files:
            energy, organics = existing.get(rpi_path, ('50', '50'))
            writer.writerow([rpi_path, energy, organics])

    print(f"CSV rebuilt: {len(music_files)} songs -> {CSV_FILE_PATH}")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Local mount : {LOCAL_DIR}")
    print(f"RPi paths   : {RPI_DIR}")
    print()
    print("=== Renaming files ===")
    rename_files()
    print("\n=== Rebuilding CSV ===")
    build_csv()
