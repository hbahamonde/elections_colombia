#!/bin/zsh

set -euo pipefail

project_dir="${0:A:h}"
server_host="127.0.0.1"
server_port="8000"
server_url="http://${server_host}:${server_port}"
skip_browser=false

if [[ "${1:-}" == "--no-browser" ]]; then
    skip_browser=true
fi

pause_before_closing() {
    if [[ "$skip_browser" == false && -t 0 ]]; then
        echo
        echo "The local experiment server has stopped."
        echo "Press any key to close this window."
        read -k 1
    fi
}

trap pause_before_closing EXIT

cd "$project_dir"

echo "Conjoint experiment — local testing"
echo "Project: $project_dir"
echo

if command -v lsof >/dev/null 2>&1 && \
        lsof -nP -iTCP:"$server_port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $server_port is already being used."
    echo "If the experiment is already running, open: $server_url"
    if [[ "$skip_browser" == false ]]; then
        open "$server_url"
    fi
    exit 0
fi

if [[ ! -x ".venv/bin/python" ]]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo "Python 3 is not installed or is not available in Terminal."
        echo "Install Python 3, then run this launcher again."
        exit 1
    fi

    echo "Creating the private Python environment…"
    python3 -m venv .venv
fi

# Putting the project's environment first is important because oTree's
# development reloader launches a second oTree process.
export PATH="$project_dir/.venv/bin:$PATH"

requirements_hash="$(shasum -a 256 requirements.txt | awk '{print $1}')"
requirements_stamp=".venv/.conjoint-requirements-sha256"
installed_hash=""

if [[ -f "$requirements_stamp" ]]; then
    installed_hash="$(<"$requirements_stamp")"
fi

if [[ "$requirements_hash" != "$installed_hash" ]] || \
        ! python -c "import otree, psycopg2" >/dev/null 2>&1; then
    echo "Installing the project requirements…"
    python -m pip install -r requirements.txt
    print -r -- "$requirements_hash" > "$requirements_stamp"
fi

if [[ "$skip_browser" == false ]]; then
    (
        for attempt in {1..30}; do
            if curl --silent --fail --output /dev/null "$server_url"; then
                open "$server_url"
                exit 0
            fi
            sleep 1
        done
    ) &
fi

echo
echo "Starting oTree at $server_url"
echo "Keep this window open while testing."
echo "Press Control+C here when you want to stop the server."
echo

otree devserver "${server_host}:${server_port}"
