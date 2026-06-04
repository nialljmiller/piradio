"""
auto_score.py
Scores unscored songs in song_attributes.csv using librosa.
CSV paths are /pirateradio/... — this script translates them to the local
mount point for actual file access.

Usage:
    python auto_score.py             # score only 50,50 songs
    python auto_score.py --rescore-all
"""

import csv
import os
import re
import sys
import warnings
import numpy as np

warnings.filterwarnings("ignore")

# ── Mount points ──────────────────────────────────────────────────────────────

LOCAL_DIR = next(
    (p for p in ["/pirateradio", "/run/media/njm/PIRATERADIO"] if os.path.isdir(p)),
    None
)
if LOCAL_DIR is None:
    raise RuntimeError("Cannot find PIRATERADIO mount.")

RPI_DIR       = "/pirateradio"
CSV_PATH      = os.path.join(LOCAL_DIR, "song_attributes.csv")

ANALYSIS_OFFSET   = 30.0
ANALYSIS_DURATION = 45.0

def rpi_to_local(path):
    """Translate /pirateradio/... path to the local mount path."""
    return path.replace(RPI_DIR, LOCAL_DIR, 1)

# ── Feature extraction ────────────────────────────────────────────────────────

def extract_features(local_path):
    import librosa
    try:
        y, sr = librosa.load(local_path, offset=ANALYSIS_OFFSET,
                             duration=ANALYSIS_DURATION, mono=True)
        if len(y) < sr * 5:
            raise ValueError("too short at offset")
    except Exception:
        y, sr = librosa.load(local_path, duration=ANALYSIS_DURATION, mono=True)

    tempo, _   = librosa.beat.beat_track(y=y, sr=sr)
    tempo      = float(np.atleast_1d(tempo)[0])
    rms        = float(np.mean(librosa.feature.rms(y=y)))
    centroid   = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    y_harm, _  = librosa.effects.hpss(y)
    harm_ratio = float(np.mean(np.abs(y_harm)) / (np.mean(np.abs(y)) + 1e-9))
    contrast   = float(np.mean(librosa.feature.spectral_contrast(y=y, sr=sr)))

    return dict(tempo=tempo, rms=rms, centroid=centroid,
                harm_ratio=harm_ratio, contrast=contrast)

def normalise(values):
    arr = np.array(values, dtype=float)
    lo, hi = arr.min(), arr.max()
    if hi == lo:
        return [50.0] * len(values)
    return ((arr - lo) / (hi - lo) * 100).tolist()

# ── CSV helpers ───────────────────────────────────────────────────────────────

def load_csv():
    if not os.path.exists(CSV_PATH):
        print(f"CSV not found at {CSV_PATH} — run filerename.py first.")
        sys.exit(1)
    rows = []
    with open(CSV_PATH, newline='') as f:
        for row in csv.reader(f):
            if len(row) == 3:
                rows.append(row)
    return rows

def save_csv(rows):
    with open(CSV_PATH, 'w', newline='') as f:
        csv.writer(f).writerows(rows)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    rescore_all = '--rescore-all' in sys.argv
    rows = load_csv()

    to_score = [
        i for i, (_, e, o) in enumerate(rows)
        if rescore_all or (e.strip() == '50' and o.strip() == '50')
    ]

    if not to_score:
        print("All songs already scored. Use --rescore-all to overwrite.")
        sys.exit(0)

    print(f"Analysing {len(to_score)} song(s)...")

    features = {}
    for n, i in enumerate(to_score, 1):
        rpi_path   = rows[i][0]
        local_path = rpi_to_local(rpi_path)
        print(f"  [{n}/{len(to_score)}] {os.path.basename(rpi_path)}", end='', flush=True)
        if not os.path.exists(local_path):
            print(" — FILE NOT FOUND, skipping")
            continue
        try:
            features[i] = extract_features(local_path)
            print(" ✓")
        except Exception as e:
            print(f" — ERROR: {e}")

    if not features:
        print("No features extracted.")
        sys.exit(1)

    indices = list(features.keys())
    def col(k): return [features[i][k] for i in indices]

    t = normalise(col('tempo'));    r = normalise(col('rms'))
    c = normalise(col('centroid')); h = normalise(col('harm_ratio'))
    s = normalise(col('contrast'))

    for j, i in enumerate(indices):
        energy   = int(np.clip(round(0.40*t[j] + 0.40*r[j] + 0.20*c[j]), 0, 100))
        organics = int(np.clip(round(0.60*h[j] + 0.40*s[j]),              0, 100))
        rows[i][1] = str(energy)
        rows[i][2] = str(organics)

    save_csv(rows)
    print(f"\nDone. {len(features)} songs scored.")

if __name__ == "__main__":
    main()
