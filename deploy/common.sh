# Shared by the deploy scripts: paths and deploy/.env. Sourced, not run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TURBO="$ROOT/vendor/turbo-cloud"
NITRO="$ROOT/vendor/nitro-next"
PLUGIN="$ROOT/turbo-plugin"

# deploy/.env is read as data, one KEY=value per line, never run as shell code: a stray word after
# a value (`WB_ASSETS_DIR=/path deploy/turbo.sh`) would otherwise run that command, and running
# turbo.sh from its own settings loops until the system runs out of processes.
# Only WB_* keys are taken; surrounding spaces and one pair of quotes are dropped. A value already in
# the environment wins over the file.
load_env() {
    local file="$1" line key value

    [ -f "$file" ] || return 0

    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%$'\r'}"
        case "$line" in '' | '#'*) continue ;; esac

        key="${line%%=*}"
        value="${line#*=}"
        key="${key//[[:space:]]/}"

        if [ "$key" = "$line" ] || ! [[ "$key" =~ ^WB_[A-Z0-9_]+$ ]]; then
            echo "deploy/.env: skipped a line that is not WB_NAME=value: $line" >&2
            continue
        fi

        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
        case "$value" in
            \"*\") value="${value:1:${#value}-2}" ;;
            \'*\') value="${value:1:${#value}-2}" ;;
        esac

        [ -n "${!key:-}" ] || export "$key=$value"
    done < "$file"
}

load_env "$ROOT/deploy/.env"

need() {
    command -v "$1" >/dev/null 2>&1 || { echo "Needs $1: $2" >&2; exit 1; }
}

# A path setting that is set must name something that exists, or the script stops here: Turbo
# would otherwise start on a wrong path (a new 400 MB asset download into it, for one).
need_path() {
    local name="$1" kind="$2" value="${!1:-}"

    [ -n "$value" ] || return 0

    if { [ "$kind" = file ] && [ ! -f "$value" ]; } || { [ "$kind" = dir ] && [ ! -d "$value" ]; }; then
        echo "$name is not an existing $kind: '$value' (check deploy/.env)" >&2
        exit 1
    fi
}
