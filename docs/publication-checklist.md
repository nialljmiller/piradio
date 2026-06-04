# Publication checklist

Before heavily publicising this repository:

## Must do

- Confirm actual RF output on a receiver.
- Add one photo or screenshot of the working setup.
- Confirm license/attribution status for the original Make Magazine Pirate Radio script.
- Confirm source/license status for the recovered `pifm` binary.
- Decide whether to keep the `pifm` binary in the repo, move it to a release asset, or replace it with build instructions.
- Keep the full music library out of Git.
- Keep private/local song metadata out of Git unless intentionally publishing it.

## Should do

- Add a short demo GIF or terminal screenshot of the installer.
- Add a short demo GIF or terminal screenshot of the config wizard.
- Add tested hardware details.
- Add tested OS details.
- Add GitHub topics.

Suggested GitHub topics:

- raspberry-pi
- fm-radio
- systemd
- linux
- maker
- installer
- retrocomputing
- headless

## Compatibility claims

Do not claim broad compatibility until tested.

Current honest claim:

- recovered original setup: known working historically
- Raspberry Pi OS / Debian Bookworm aarch64: service tested running after installing armhf runtime
- RF output: needs receiver confirmation
