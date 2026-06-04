"""
check_audio.py
Scans every audio file in /pirateradio and verifies ffmpeg can decode it.
Any file that fails gets moved to /pirateradio/quarantine/ so it won't
hang PirateRadio.py on boot.

Run this on the laptop before putting the SD card back in the RPi:
    python check_audio.py

Or drop it in the RPi's boot sequence before PirateRadio.py.
Results are written to /pirateradio/audio_check.log
"""

import os
import re
import subprocess

# ── Mount points ──────────────────────────────────────────────────────────────

LOCAL_DIR = next(
    (p for p in ["/pirateradio", "/run/media/njm/PIRATERADIO"] if os.path.isdir(p)),
    None
)
if LOCAL_DIR is None:
    raise RuntimeError("Cannot find PIRATERADIO mount.")

AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.wav', '.flac', '.aac'}
QUARANTINE_DIR   = os.path.join(LOCAL_DIR, "quarantine")
LOG_PATH         = os.path.join(LOCAL_DIR, "audio_check.log")

# ── Check a single file ───────────────────────────────────────────────────────

def check_file(path):
    """Returns (ok, error_message). Uses ffmpeg to fully decode the file."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path,
             "-f", "null", "-"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=30  # if ffmpeg hangs on a file, give up after 30s
        )
        if result.returncode != 0:
            return False, result.stderr.decode(errors='replace').strip()
        return True, None
    except subprocess.TimeoutExpired:
        return False, "ffmpeg timed out (>30s)"
    except FileNotFoundError:
        return False, "ffmpeg not found — install it first"

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Collect all audio files, skipping quarantine dir
    audio_files = []
    for root, dirs, files in os.walk(LOCAL_DIR):
        dirs[:] = [d for d in dirs if d != 'quarantine']
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS:
                audio_files.append(os.path.join(root, f))

    if not audio_files:
        print("No audio files found.")
        return

    os.makedirs(QUARANTINE_DIR, exist_ok=True)

    bad  = []
    good = 0

    with open(LOG_PATH, 'w') as log:
        log.write(f"Checking {len(audio_files)} files...\n\n")

        for n, path in enumerate(audio_files, 1):
            name = os.path.relpath(path, LOCAL_DIR)
            print(f"[{n}/{len(audio_files)}] {name}", end='', flush=True)

            ok, err = check_file(path)

            if ok:
                print(" ✓")
                log.write(f"OK  : {name}\n")
                good += 1
            else:
                print(f" ✗  {err}")
                log.write(f"BAD : {name}\n      {err}\n")
                bad.append(path)

        log.write(f"\n{good} OK, {len(bad)} bad\n")
        if bad:
            log.write("\nQuarantined:\n")

    # Move bad files out of the way
    for path in bad:
        dest = os.path.join(QUARANTINE_DIR, os.path.basename(path))
        try:
            os.rename(path, dest)
            print(f"Quarantined: {os.path.basename(path)}")
            with open(LOG_PATH, 'a') as log:
                log.write(f"  {os.path.basename(path)}\n")
        except Exception as e:
            print(f"Could not quarantine {os.path.basename(path)}: {e}")

    print(f"\n{good} OK, {len(bad)} quarantined.")
    print(f"Log written to {LOG_PATH}")

if __name__ == "__main__":
    main()
