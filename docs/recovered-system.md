# Recovered Pi radio system

## OS

Original image appears to be Arch Linux ARM.

Python path:

```text
/usr/bin/python -> python3
/usr/bin/python3 -> python3.3

Boot service

[Unit]
Description=Pirate Radio

[Service]
Type=forking
ExecStart=/root/PirateRadio.py

[Install]
WantedBy=multi-user.target

fstab

/dev/mmcblk0p1  /boot           vfat    defaults        0       0
/dev/mmcblk0p3  /pirateradio    vfat    defaults        0       0

Config

[pirateradio]
frequency = 101.1
shuffle = False
repeat_all = True
stereo_playback = True

Core binary

pifm is a 32-bit ARM dynamically-linked ELF executable.

See source_snapshot.sha256 for hashes of recovered files.
