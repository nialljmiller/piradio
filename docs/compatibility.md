# Compatibility

## Recommended target

Use:

    Raspberry Pi OS Lite 32-bit

This is the primary supported install target for now.

## Why not any Raspberry Pi Linux OS?

The recovered system depends on:

- systemd
- Python 3
- ffmpeg
- ALSA utilities
- `/pirateradio` as the media/config directory
- the recovered 32-bit ARM `pifm` binary

Other Raspberry Pi Linux distributions may have different package names, different library layouts, different audio defaults, or different support for 32-bit binaries.

## Current support levels

| Support level | Meaning |
|---|---|
| Known working | Recovered from this exact setup. |
| Primary target | Installer is designed for this first. |
| Likely | Expected to work, but still needs real hardware testing. |
| Maybe | Plausible, but may need manual fixes. |
| Unsupported | Not targeted by the installer. |
| Unknown | Do not assume it works. |

## OS compatibility

| OS | Support level |
|---|---:|
| Recovered Arch Linux ARM image | Known working |
| Raspberry Pi OS Lite 32-bit | Primary target |
| Raspberry Pi OS Desktop 32-bit | Likely |
| Raspberry Pi OS 64-bit / Debian Bookworm aarch64 | Tested to start service |
| Ubuntu Server 32-bit ARM | Maybe |
| Ubuntu Server 64-bit ARM | Not recommended |
| Alpine Linux | Unsupported |
| DietPi | Unsupported |
| LibreELEC | Unsupported |
| RetroPie | Unsupported |

## Model compatibility

| Raspberry Pi model | Support level |
|---|---:|
| Raspberry Pi 1 | Likely |
| Raspberry Pi Zero | Likely |
| Raspberry Pi Zero W | Likely |
| Raspberry Pi Zero 2 W | Likely |
| Raspberry Pi 2 | Likely |
| Raspberry Pi 3 | Likely |
| Raspberry Pi 4 | Maybe |
| Raspberry Pi 5 | Unknown / not recommended yet |
| Raspberry Pi Pico / Pico W | Not supported |
