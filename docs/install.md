# Install

The intended install method is:

1. Boot a live Raspberry Pi.
2. SSH into it.
3. Clone this repo.
4. Run `sudo ./install.sh`.

Do not install onto a mounted SD card unless doing recovery work.

## Fresh Pi install

On the Pi:

    sudo apt update
    sudo apt install -y git
    git clone https://github.com/nialljmiller/piradio.git
    cd piradio
    sudo ./install.sh

The installer will:

- install runtime packages
- install `/root/PirateRadio.py`
- install `/root/pifm`
- create `/pirateradio`
- use a partition labelled `PIRATERADIO` if one exists
- create demo audio if no audio is present
- install and start `pirateradio.service`

## Set frequency at install time

    PIRADIO_FREQUENCY=101.1 sudo -E ./install.sh

Or edit later:

    sudo nano /pirateradio/pirateradio.config
    sudo systemctl restart pirateradio.service

## Real music library

Songs go directly in:

    /pirateradio

Announcements go in:

    /pirateradio/announce

The installer creates demo audio only so the service can start on a fresh machine.

## Debugging

Run:

    sudo ./scripts/piradio_doctor.sh

Useful service commands:

    sudo systemctl status pirateradio.service
    sudo journalctl -u pirateradio.service -f
    sudo systemctl restart pirateradio.service
    sudo systemctl stop pirateradio.service

## Notes

The recovered `pifm` binary is a 32-bit ARM executable. A 32-bit Raspberry Pi OS Lite image is the safest target. A 64-bit OS may require extra compatibility libraries or may fail.
