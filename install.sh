#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SERVICE_NAME="pirateradio.service"
MEDIA_DIR="/pirateradio"

START_SERVICE=1
CREATE_DEMO_AUDIO=1
FREQUENCY="${PIRADIO_FREQUENCY:-101.1}"

log() {
    echo "[piradio install] $*"
}

warn() {
    echo "[piradio install WARNING] $*" >&2
}

die() {
    echo "[piradio install ERROR] $*" >&2
    exit 1
}

usage() {
    cat <<USAGE
Usage:
  sudo ./install.sh [options]

Options:
  --no-start          Install and enable service, but do not start it now.
  --no-demo-audio     Do not create demo audio if /pirateradio has no audio.
  --frequency FREQ    Frequency to write into config if config is missing.
                      Default: ${FREQUENCY}

Environment:
  PIRADIO_FREQUENCY=101.1 sudo -E ./install.sh

This installer must be run on the target Raspberry Pi, not on your laptop.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-start)
            START_SERVICE=0
            shift
            ;;
        --no-demo-audio)
            CREATE_DEMO_AUDIO=0
            shift
            ;;
        --frequency)
            [[ $# -ge 2 ]] || die "--frequency requires a value"
            FREQUENCY="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1"
            ;;
    esac
done

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        die "Run as root: sudo ./install.sh"
    fi
}

check_repo_files() {
    [[ -f "${REPO_DIR}/src/PirateRadio.py" ]] || die "Missing src/PirateRadio.py"
    [[ -f "${REPO_DIR}/legacy/root/pifm" ]] || die "Missing legacy/root/pifm"
}

install_packages() {
    log "Installing runtime packages"

    if command -v apt-get >/dev/null 2>&1; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get install -y python3 ffmpeg alsa-utils file binutils

        # Native runtime libraries.
        apt-get install -y libc6 libstdc++6 libgcc-s1 2>/dev/null || \
        apt-get install -y libc6 libstdc++6 libgcc1 2>/dev/null || true

        # The recovered pifm binary is 32-bit ARM hard-float.
        # On 64-bit Raspberry Pi OS, install the armhf loader/libs too.
        if [[ "$(uname -m)" == "aarch64" ]]; then
            log "Installing armhf runtime for recovered 32-bit pifm binary"
            dpkg --add-architecture armhf
            apt-get update
            apt-get install -y libc6:armhf libstdc++6:armhf libgcc-s1:armhf
        fi

    elif command -v pacman >/dev/null 2>&1; then
        pacman -Sy --needed --noconfirm python ffmpeg alsa-utils file binutils gcc-libs

    else
        warn "No apt-get or pacman found. Skipping package installation."
        warn "You need python3, ffmpeg, alsa-utils, file, binutils, libc, libstdc++, and libgcc."
    fi
}

warn_about_architecture() {
    local arch
    arch="$(uname -m)"

    log "Detected architecture: ${arch}"

    case "${arch}" in
        armv6l|armv7l|armv8l)
            ;;
        aarch64)
            warn "64-bit OS detected. The recovered pifm binary is 32-bit ARM."
            warn "If pifm fails with missing loader/libs, use 32-bit Raspberry Pi OS Lite."
            ;;
        *)
            warn "This does not look like a Raspberry Pi ARM userspace."
            warn "Install may complete, but pifm probably will not run here."
            ;;
    esac
}

prepare_media_mount_or_dir() {
    log "Preparing ${MEDIA_DIR}"

    mkdir -p "${MEDIA_DIR}"

    if mountpoint -q "${MEDIA_DIR}"; then
        log "${MEDIA_DIR} is already a mountpoint"
        return
    fi

    if command -v blkid >/dev/null 2>&1; then
        local dev
        dev="$(blkid -L PIRATERADIO 2>/dev/null || true)"

        if [[ -n "${dev}" ]]; then
            log "Found partition labelled PIRATERADIO: ${dev}"

            if ! grep -Eq '[[:space:]]/pirateradio[[:space:]]' /etc/fstab; then
                local backup="/etc/fstab.piradio.bak.$(date +%Y%m%d-%H%M%S)"
                cp /etc/fstab "${backup}"
                log "Backed up /etc/fstab to ${backup}"

                cat >> /etc/fstab <<FSTAB

# piradio media partition
LABEL=PIRATERADIO  /pirateradio  vfat  defaults,nofail,umask=022  0  0
FSTAB
            fi

            mount "${MEDIA_DIR}" || warn "Could not mount ${MEDIA_DIR}; continuing with directory if usable"
        else
            log "No partition labelled PIRATERADIO found; using ${MEDIA_DIR} as a normal directory"
        fi
    fi
}

install_runtime_files() {
    log "Installing runtime files"

    install -m 0755 "${REPO_DIR}/src/PirateRadio.py" /root/PirateRadio.py
    install -m 0755 "${REPO_DIR}/legacy/root/pifm" /root/pifm

    # Modern Raspberry Pi OS usually has python3 but not necessarily /usr/bin/python.
    sed -i '1s|^#!.*python.*$|#!/usr/bin/env python3|' /root/PirateRadio.py
}

write_config_if_missing() {
    mkdir -p "${MEDIA_DIR}/announce"

    if [[ ! -f "${MEDIA_DIR}/pirateradio.config" ]]; then
        log "Writing default config to ${MEDIA_DIR}/pirateradio.config"

        cat > "${MEDIA_DIR}/pirateradio.config" <<CONFIG
[pirateradio]
frequency = ${FREQUENCY}
shuffle = False
repeat_all = True
stereo_playback = True
CONFIG
    else
        log "Keeping existing ${MEDIA_DIR}/pirateradio.config"
    fi
}

count_main_audio_files() {
    find "${MEDIA_DIR}" -maxdepth 1 -type f \
        \( -iname '*.mp3' -o -iname '*.wav' -o -iname '*.m4a' -o -iname '*.aac' -o -iname '*.flac' \) \
        ! -iname 'waiting.mp3' \
        | wc -l
}

count_announcement_files() {
    find "${MEDIA_DIR}/announce" -maxdepth 1 -type f \
        \( -iname '*.mp3' -o -iname '*.wav' -o -iname '*.m4a' -o -iname '*.aac' -o -iname '*.flac' \) \
        | wc -l
}

make_demo_mp3() {
    local output="$1"
    local freq="$2"
    local duration="$3"

    ffmpeg -hide_banner -loglevel error -y \
        -f lavfi -i "sine=frequency=${freq}:duration=${duration}" \
        -ac 2 -ar 44100 -q:a 7 "${output}"
}

create_demo_audio_if_needed() {
    if [[ "${CREATE_DEMO_AUDIO}" -ne 1 ]]; then
        log "Skipping demo audio creation"
        return
    fi

    command -v ffmpeg >/dev/null 2>&1 || die "ffmpeg is required to create demo audio"

    mkdir -p "${MEDIA_DIR}/announce"

    if [[ ! -f "${MEDIA_DIR}/waiting.mp3" ]]; then
        log "Creating demo waiting audio"
        make_demo_mp3 "${MEDIA_DIR}/waiting.mp3" 330 70
    fi

    if [[ "$(count_main_audio_files)" -eq 0 ]]; then
        log "Creating demo song audio"
        make_demo_mp3 "${MEDIA_DIR}/demo_song.mp3" 440 30
    fi

    if [[ "$(count_announcement_files)" -eq 0 ]]; then
        log "Creating demo announcement audio"
        make_demo_mp3 "${MEDIA_DIR}/announce/demo_announcement.mp3" 880 4
    fi
}

install_systemd_service() {
    log "Installing systemd service"

    cat > "/etc/systemd/system/${SERVICE_NAME}" <<SERVICE
[Unit]
Description=Pirate Radio FM transmitter
After=local-fs.target sound.target
RequiresMountsFor=/pirateradio

[Service]
Type=forking
ExecStart=/root/PirateRadio.py
WorkingDirectory=/root
Restart=always
RestartSec=5
GuessMainPID=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}"
}

validate_install() {
    log "Validating install"

    command -v python3 >/dev/null 2>&1 || die "python3 not found"
    command -v ffmpeg >/dev/null 2>&1 || die "ffmpeg not found"

    [[ -x /root/PirateRadio.py ]] || die "/root/PirateRadio.py missing or not executable"
    [[ -x /root/pifm ]] || die "/root/pifm missing or not executable"
    [[ -d "${MEDIA_DIR}" ]] || die "${MEDIA_DIR} missing"
    [[ -f "${MEDIA_DIR}/pirateradio.config" ]] || die "${MEDIA_DIR}/pirateradio.config missing"
    [[ -f "${MEDIA_DIR}/waiting.mp3" ]] || die "${MEDIA_DIR}/waiting.mp3 missing"

    if [[ "$(count_main_audio_files)" -eq 0 ]]; then
        die "No main audio files found in ${MEDIA_DIR}"
    fi

    if [[ "$(count_announcement_files)" -eq 0 ]]; then
        die "No announcement audio files found in ${MEDIA_DIR}/announce"
    fi

    python3 -m py_compile /root/PirateRadio.py

    if command -v ldd >/dev/null 2>&1; then
        if ldd /root/pifm 2>&1 | grep -q 'not found'; then
            ldd /root/pifm || true
            die "pifm has missing shared libraries"
        fi
    fi
}

start_service_if_requested() {
    if [[ "${START_SERVICE}" -ne 1 ]]; then
        log "Not starting service because --no-start was used"
        return
    fi

    log "Starting ${SERVICE_NAME}"

    systemctl restart "${SERVICE_NAME}" || {
        warn "Service failed to start"
        systemctl status "${SERVICE_NAME}" --no-pager || true
        journalctl -u "${SERVICE_NAME}" -n 120 --no-pager || true
        exit 1
    }

    sleep 3

    if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
        warn "Service is not active after start"
        systemctl status "${SERVICE_NAME}" --no-pager || true
        journalctl -u "${SERVICE_NAME}" -n 120 --no-pager || true
        exit 1
    fi

    log "${SERVICE_NAME} is active"
}

print_summary() {
    cat <<SUMMARY

[piradio install] Done.

Installed:
  /root/PirateRadio.py
  /root/pifm
  /etc/systemd/system/${SERVICE_NAME}
  ${MEDIA_DIR}/pirateradio.config

Useful commands:
  sudo systemctl status ${SERVICE_NAME}
  sudo journalctl -u ${SERVICE_NAME} -f
  sudo systemctl restart ${SERVICE_NAME}
  sudo systemctl stop ${SERVICE_NAME}

Media directory:
  ${MEDIA_DIR}

Put songs directly in:
  ${MEDIA_DIR}

Put announcements in:
  ${MEDIA_DIR}/announce

Config:
  ${MEDIA_DIR}/pirateradio.config

SUMMARY
}

main() {
    require_root
    check_repo_files
    warn_about_architecture
    install_packages
    prepare_media_mount_or_dir
    install_runtime_files
    write_config_if_missing
    create_demo_audio_if_needed
    install_systemd_service
    validate_install
    start_service_if_requested
    print_summary
}

main "$@"
