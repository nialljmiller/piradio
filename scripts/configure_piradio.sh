#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="${PIRADIO_CONFIG:-/pirateradio/pirateradio.config}"
SERVICE_NAME="${PIRADIO_SERVICE:-pirateradio.service}"

if [[ -t 1 ]] && command -v tput >/dev/null 2>&1; then
    BOLD="$(tput bold || true)"
    RESET="$(tput sgr0 || true)"
    CYAN="$(tput setaf 6 || true)"
    MAGENTA="$(tput setaf 5 || true)"
    GREEN="$(tput setaf 2 || true)"
    YELLOW="$(tput setaf 3 || true)"
    RED="$(tput setaf 1 || true)"
else
    BOLD=""
    RESET=""
    CYAN=""
    MAGENTA=""
    GREEN=""
    YELLOW=""
    RED=""
fi

run_root() {
    if [[ "${EUID}" -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

pause() {
    printf "\nPress Enter to continue..."
    read -r _
}

banner() {
    clear 2>/dev/null || true

    printf "%s%s\n" "${MAGENTA}" "${BOLD}"
    cat <<'BANNER'
============================================================
                        PIRATE RADIO
============================================================
BANNER

    printf "%s\n" "${CYAN}"
    cat <<'BANNER'
          .------------------------------------------------.
          |                                                |
          |              THE BLACK FLAG BROADCAST           |
          |                                                |
          |                FM CONFIG WIZARD                 |
          |                                                |
          '------------------------------------------------'


            /\
            ||_____-----_____-----_____
            ||   O                  O  \
            ||    O\\    ___    //O    /
            ||       \\ /   \//        \
            ||         |_O O_|         /
            ||          ^ | ^          \
            ||        // UUU \\        /
            ||    O//            \\O   \
            ||   O                  O  /
            ||_____-----_____-----_____\
            ||
            ||.





          +----------------------------------------------+
          |  TRANSMITTER : pifm                          |
          |  SIGNAL      : FM                             |
          |  MODE        : HEADLESS RADIO                 |
          |  CARGO       : MUSIC / ANNOUNCEMENTS          |
          +----------------------------------------------+

                . . . tuning transmitter . . .
                . . . checking the signal . . .
                . . . loading the playlist . . .
BANNER

    printf "%s\n" "${YELLOW}"
    cat <<'BANNER'
          Set the frequency. Choose shuffle mode.
          Choose repeat mode. Start the broadcast.
BANNER

    printf "%s\n" "${RESET}"
}

trim_value() {
    sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

read_config_value() {
    local key="$1"
    local default="$2"

    if [[ ! -f "${CONFIG_FILE}" ]]; then
        printf "%s\n" "${default}"
        return
    fi

    local value
    value="$(
        grep -Ei "^[[:space:]]*${key}[[:space:]]*=" "${CONFIG_FILE}" 2>/dev/null \
            | tail -n 1 \
            | sed 's/^[^=]*=//' \
            | trim_value
    )"

    if [[ -z "${value}" ]]; then
        printf "%s\n" "${default}"
    else
        printf "%s\n" "${value}"
    fi
}

valid_frequency() {
    local value="$1"
    awk -v f="${value}" '
        BEGIN {
            if (f ~ /^[0-9]+([.][0-9]+)?$/ && f >= 87.5 && f <= 108.0) {
                exit 0
            }
            exit 1
        }
    '
}

normalize_bool() {
    local value
    value="$(printf "%s" "$1" | tr '[:upper:]' '[:lower:]')"

    case "${value}" in
        true|yes|y|1|on)
            printf "True\n"
            ;;
        false|no|n|0|off)
            printf "False\n"
            ;;
        *)
            return 1
            ;;
    esac
}

prompt_frequency() {
    local current="$1"
    local value

    while true; do
        printf "%sFM frequency in MHz%s [%s]: " "${BOLD}" "${RESET}" "${current}"
        read -r value
        value="${value:-$current}"

        if valid_frequency "${value}"; then
            printf "%s\n" "${value}"
            return
        fi

        printf "%sFrequency must be between 87.5 and 108.0 MHz.%s\n" "${RED}" "${RESET}" >&2
    done
}

prompt_bool() {
    local label="$1"
    local current="$2"
    local current_norm
    local prompt
    local value
    local normalized

    current_norm="$(normalize_bool "${current}" || printf "False")"

    if [[ "${current_norm}" == "True" ]]; then
        prompt="Y/n"
    else
        prompt="y/N"
    fi

    while true; do
        printf "%s%s%s [%s]: " "${BOLD}" "${label}" "${RESET}" "${prompt}"
        read -r value

        if [[ -z "${value}" ]]; then
            printf "%s\n" "${current_norm}"
            return
        fi

        if normalized="$(normalize_bool "${value}")"; then
            printf "%s\n" "${normalized}"
            return
        fi

        printf "%sPlease answer yes or no.%s\n" "${RED}" "${RESET}" >&2
    done
}

write_config() {
    local frequency="$1"
    local shuffle="$2"
    local repeat_all="$3"
    local stereo="$4"

    local config_dir
    local tmp
    local backup

    config_dir="$(dirname "${CONFIG_FILE}")"
    tmp="$(mktemp)"
    backup="${CONFIG_FILE}.bak.$(date +%Y%m%d-%H%M%S)"

    cat > "${tmp}" <<CONFIG
[pirateradio]
frequency = ${frequency}
shuffle = ${shuffle}
repeat_all = ${repeat_all}
stereo_playback = ${stereo}
CONFIG

    run_root mkdir -p "${config_dir}"

    if [[ -f "${CONFIG_FILE}" ]]; then
        run_root cp -a "${CONFIG_FILE}" "${backup}"
        printf "%sBacked up old config:%s %s\n" "${YELLOW}" "${RESET}" "${backup}"
    fi

    run_root install -m 0644 "${tmp}" "${CONFIG_FILE}"
    rm -f "${tmp}"

    printf "%sWrote config:%s %s\n" "${GREEN}" "${RESET}" "${CONFIG_FILE}"
}

maybe_restart_service() {
    if ! command -v systemctl >/dev/null 2>&1; then
        return
    fi

    printf "\nRestart %s now? [Y/n]: " "${SERVICE_NAME}"
    read -r answer
    answer="${answer:-y}"

    case "$(printf "%s" "${answer}" | tr '[:upper:]' '[:lower:]')" in
        y|yes)
            run_root systemctl restart "${SERVICE_NAME}"
            printf "%sRestarted %s.%s\n" "${GREEN}" "${SERVICE_NAME}" "${RESET}"
            run_root systemctl status "${SERVICE_NAME}" --no-pager || true
            ;;
        *)
            printf "Not restarting. Apply later with:\n"
            printf "  sudo systemctl restart %s\n" "${SERVICE_NAME}"
            ;;
    esac
}

main() {
    banner

    printf "%sConfig file:%s %s\n" "${BOLD}" "${RESET}" "${CONFIG_FILE}"
    printf "%sService:%s     %s\n" "${BOLD}" "${RESET}" "${SERVICE_NAME}"

    local current_frequency
    local current_shuffle
    local current_repeat_all
    local current_stereo

    current_frequency="$(read_config_value frequency 101.1)"
    current_shuffle="$(read_config_value shuffle False)"
    current_repeat_all="$(read_config_value repeat_all True)"
    current_stereo="$(read_config_value stereo_playback True)"

    printf "\nCurrent settings:\n"
    printf "  frequency       = %s\n" "${current_frequency}"
    printf "  shuffle         = %s\n" "${current_shuffle}"
    printf "  repeat_all      = %s\n" "${current_repeat_all}"
    printf "  stereo_playback = %s\n" "${current_stereo}"

    printf "\n%sTip:%s choose a clear frequency with little/no local station activity.\n" "${YELLOW}" "${RESET}"
    pause

    local new_frequency
    local new_shuffle
    local new_repeat_all
    local new_stereo

    printf "\n%sPirate Radio setup%s\n\n" "${CYAN}${BOLD}" "${RESET}"

    new_frequency="$(prompt_frequency "${current_frequency}")"
    new_shuffle="$(prompt_bool "Shuffle songs?" "${current_shuffle}")"
    new_repeat_all="$(prompt_bool "Repeat forever?" "${current_repeat_all}")"
    new_stereo="$(prompt_bool "Stereo playback?" "${current_stereo}")"

    printf "\n%sNew config preview:%s\n" "${BOLD}" "${RESET}"
    printf "  frequency       = %s\n" "${new_frequency}"
    printf "  shuffle         = %s\n" "${new_shuffle}"
    printf "  repeat_all      = %s\n" "${new_repeat_all}"
    printf "  stereo_playback = %s\n" "${new_stereo}"

    printf "\nWrite this config? [Y/n]: "
    read -r confirm
    confirm="${confirm:-y}"

    case "$(printf "%s" "${confirm}" | tr '[:upper:]' '[:lower:]')" in
        y|yes)
            write_config "${new_frequency}" "${new_shuffle}" "${new_repeat_all}" "${new_stereo}"
            maybe_restart_service
            ;;
        *)
            printf "No changes made.\n"
            exit 0
            ;;
    esac

    printf "\n%sDone. Yarrr.%s\n" "${GREEN}${BOLD}" "${RESET}"
}

main "$@"
