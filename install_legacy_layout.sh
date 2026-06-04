#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo ./install_legacy_layout.sh"
    exit 1
fi

install -m 0755 src/PirateRadio.py /root/PirateRadio.py
install -m 0755 legacy/root/pifm /root/pifm
install -m 0644 legacy/systemd/pirateradio.service /etc/systemd/system/pirateradio.service

mkdir -p /pirateradio

if [[ ! -f /pirateradio/pirateradio.config ]]; then
    install -m 0644 config/pirateradio.config.example /pirateradio/pirateradio.config
fi

systemctl daemon-reload
systemctl enable pirateradio.service

echo "Installed legacy piradio layout."
echo "Put music in /pirateradio and start with:"
echo "  sudo systemctl start pirateradio.service"
