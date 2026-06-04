#!/usr/bin/env bash
set -u

SERVICE_NAME="pirateradio.service"
MEDIA_DIR="/pirateradio"

section() {
    echo
    echo "============================================================"
    echo "$*"
    echo "============================================================"
}

section "System"
uname -a
cat /etc/os-release 2>/dev/null || true

section "Commands"
for cmd in python python3 ffmpeg arecord file systemctl journalctl; do
    printf "%-12s " "$cmd"
    command -v "$cmd" || true
done

section "Runtime files"
ls -lah /root/PirateRadio.py /root/pifm 2>/dev/null || true
file /root/pifm 2>/dev/null || true
ldd /root/pifm 2>/dev/null || true

section "Media directory"
findmnt -T "${MEDIA_DIR}" 2>/dev/null || true
ls -lah "${MEDIA_DIR}" 2>/dev/null | sed -n '1,120p' || true

section "Config"
cat "${MEDIA_DIR}/pirateradio.config" 2>/dev/null || true

section "Announcements"
find "${MEDIA_DIR}/announce" -maxdepth 1 -type f 2>/dev/null | sort | sed -n '1,80p' || true

section "Main audio files"
find "${MEDIA_DIR}" -maxdepth 1 -type f \
    \( -iname '*.mp3' -o -iname '*.wav' -o -iname '*.m4a' -o -iname '*.aac' -o -iname '*.flac' \) \
    2>/dev/null | sort | sed -n '1,120p' || true

section "Service status"
systemctl status "${SERVICE_NAME}" --no-pager 2>/dev/null || true

section "Recent logs"
journalctl -u "${SERVICE_NAME}" -n 120 --no-pager 2>/dev/null || true
