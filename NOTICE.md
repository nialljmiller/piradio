# Notice and attribution

This repository contains a recovered and modernized Raspberry Pi FM radio setup.

The original Pirate Radio Python script was authored by Wynter Woods for Make Magazine. This project preserves and modifies that recovered script so it can be installed and run more easily on modern Raspberry Pi systems.

This repository also includes a recovered `pifm` executable from the original working Raspberry Pi image. The exact source and license status of this recovered binary still needs to be confirmed before treating this repository as a fully reusable open-source release.

## What this repository adds

The main contributions of this repository are:

- recovery of a working headless Raspberry Pi radio setup from an old image
- reproducible repository layout
- one-command installer
- systemd service installation
- Raspberry Pi OS 64-bit compatibility handling for the recovered 32-bit ARM `pifm` binary
- diagnostic tooling
- configuration tooling
- documentation and compatibility notes

## License status

License status is not fully resolved yet.

Do not assume all recovered upstream components are freely reusable until the original license status of the Make Magazine Pirate Radio script and the bundled `pifm` executable has been confirmed.

Until then, treat this project as a preservation, recovery, and personal-use modernization project.
