#!/usr/bin/python3
"""Run the original station with optional cached bulletin playback."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('pirateradio', '/root/PirateRadio.py')
radio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(radio)
radio.daemonize = lambda: None
# Planned live upgrades can restart between songs without the boot jingle.
skip_startup = Path('/var/lib/piradio-internet/skip-startup-once')
if skip_startup.exists():
    skip_startup.unlink()
    radio.play_waiting = lambda: None
    radio.stop_waiting_after_minimum_time = lambda: None
config = '/etc/piradio-internet/config.json'
if Path(config).is_file():
    try:
        from internet.daypart import attach_music
        attach_music(vars(radio), config)
        from internet.player import attach
        attach(vars(radio), config)
    except Exception as exc:
        print('Internet module unavailable; original playback continues:', type(exc).__name__, flush=True)
raise SystemExit(radio.main())
