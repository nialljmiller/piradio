# piradio

Headless Raspberry Pi FM radio setup.

This repository preserves a working Raspberry Pi FM radio system recovered from an old Raspberry Pi image.

## What it does

The Pi boots headlessly, starts a systemd service, runs `PirateRadio.py`, decodes audio with `ffmpeg`, and pipes raw audio into `pifm` for FM transmission.

## Original boot chain

    /etc/systemd/system/pirateradio.service
        -> /root/PirateRadio.py
            -> /root/pifm
            -> /pirateradio

## Original runtime paths

    /root/PirateRadio.py
    /root/pifm
    /pirateradio/pirateradio.config
    /pirateradio/song_attributes.csv
    /pirateradio/waiting.mp3
    /pirateradio/announce/

## Important directories in this repo

    src/                 recovered PirateRadio.py
    legacy/root/         recovered pifm binary
    legacy/systemd/      recovered systemd service
    config/              example config
    scripts/             helper tools for checking/scoring/ranking music
    data/                examples and recovered file lists
    docs/                recovery notes and hashes

## Current status

This is a faithful source capture plus a legacy-layout installer. It is not yet a polished modern installer.

Do not run `install_legacy_layout.sh` on your laptop. It is intended for a Raspberry Pi target system.
