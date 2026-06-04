# piradio

Headless Raspberry Pi FM radio setup.

This repo preserves the working Pirate Radio setup from an old Raspberry Pi image.

## Original boot chain

systemd starts:

```text
/etc/systemd/system/pirateradio.service

which runs:

/root/PirateRadio.py

The Python script reads music and config from:

/pirateradio

and pipes decoded audio from ffmpeg into:

/root/pifm

Original runtime paths

/root/PirateRadio.py
/root/pifm
/pirateradio/pirateradio.config
/pirateradio/song_attributes.csv
/pirateradio/waiting.mp3
/pirateradio/announce/

Current status

This is currently a faithful source capture, not yet a polished installer.

