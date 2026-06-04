# Recovered Pi radio system

## OS

The original image appears to be Arch Linux ARM.

Python path on the recovered image:

    /usr/bin/python -> python3
    /usr/bin/python3 -> python3.3

## Boot service

Recovered service:

    [Unit]
    Description=Pirate Radio

    [Service]
    Type=forking
    ExecStart=/root/PirateRadio.py

    [Install]
    WantedBy=multi-user.target

## fstab

Recovered relevant entries:

    /dev/mmcblk0p1  /boot           vfat    defaults        0       0
    /dev/mmcblk0p3  /pirateradio    vfat    defaults        0       0

## Runtime config

Recovered config:

    [pirateradio]
    frequency = 101.1
    shuffle = False
    repeat_all = True
    stereo_playback = True

## Core binary

`pifm` is a 32-bit ARM dynamically linked ELF executable.

Known hash:

    860708a8086cee6463495b70b2486a8ffa773a46c0384b81b4d9eda84ab6d1db  pifm

See `docs/source_snapshot.sha256` for the full recovered-source hash list.
