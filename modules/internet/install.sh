#!/bin/bash
# Stage the optional module without enabling generation or changing FM playback.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
    echo 'Run this installer with sudo.' >&2
    exit 1
fi
module_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
getent passwd njm >/dev/null
command -v ffmpeg >/dev/null
python3 -c "import numpy" 2>/dev/null || apt-get install -y python3-numpy
install -d -m 0755 /usr/local/lib/piradio/internet /etc/piradio-internet
for source_file in __init__.py common.py worker.py player.py fish.py segments.py daypart.py attributes.py grok.py cli.py daily_connectors.py cadence.py news_bank.py; do
    install -m 0644 "$module_dir/$source_file" "/usr/local/lib/piradio/internet/$source_file"
done
if [[ ! -e /etc/piradio-internet/config.json ]]; then
    install -m 0644 "$module_dir/config.example.json" /etc/piradio-internet/config.json
fi
if python3 -c 'import json, sys; sys.exit(json.load(open("/etc/piradio-internet/config.json")).get("voice_provider") != "fish")'; then
    apt-get install -y python3-msgpack
fi
install -d -o njm -g njm -m 0755 /var/lib/piradio-internet
install -m 0644 "$module_dir/systemd/piradio-internet.service" /etc/systemd/system/
install -m 0644 "$module_dir/systemd/piradio-internet.timer" /etc/systemd/system/
PYTHONPATH=/usr/local/lib/piradio python3 -m internet.worker status
systemctl daemon-reload
echo 'Module staged. Timer and FM playback were not changed.'
