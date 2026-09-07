#!/usr/bin/env bash
# Quick launcher for the Doc Agent local interfaces.
#
# The MCP server speaks JSON-RPC over stdio, so every message this script prints
# goes to stderr and the UI's own output is redirected to a log file. stdout is
# left clean for the protocol.

set -euo pipefail

cd -- "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

VENV="${DOC_AGENT_VENV:-.venv}"
UI_HOST="${DOC_AGENT_UI_HOST:-127.0.0.1}"
UI_PORT="${DOC_AGENT_UI_PORT:-8080}"
UI_LOG="${DOC_AGENT_UI_LOG:-.working/ui.log}"

log() { printf '[run] %s\n' "$*" >&2; }
die() { printf '[run] error: %s\n' "$*" >&2; exit 1; }

usage() {
    cat >&2 <<'EOF'
Usage: ./run.sh [ui|mcp|both] [--host HOST] [--port PORT]

Modes
  ui      Local NiceGUI interface (default).
  mcp     Read-oriented MCP server on stdio.
  both    UI in the background, MCP in the foreground on clean stdio.

Options
  --host HOST   UI bind address (default 127.0.0.1).
  --port PORT   UI port (default 8080).
  -h, --help    Show this message.

Environment
  DOC_AGENT_HOME                Knowledge store location.
  DOC_AGENT_MAX_CONTEXT_TOKENS  Retrieval budget in estimated tokens.
  DOC_AGENT_VENV                Virtualenv path (default .venv).
  DOC_AGENT_UI_HOST/_UI_PORT    Defaults for the flags above.
  DOC_AGENT_UI_LOG              UI log file in `both` mode (default .working/ui.log).

The virtualenv is created and the project installed on first run.
EOF
}

MODE=""
while [ $# -gt 0 ]; do
    case "$1" in
        ui|mcp|both)
            [ -z "$MODE" ] || die "mode already set to '$MODE'"
            MODE="$1"
            shift
            ;;
        --host)
            [ $# -ge 2 ] || die "--host needs a value"
            UI_HOST="$2"
            shift 2
            ;;
        --port)
            [ $# -ge 2 ] || die "--port needs a value"
            UI_PORT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf '[run] error: unknown argument: %s\n\n' "$1" >&2
            usage
            exit 1
            ;;
    esac
done
MODE="${MODE:-ui}"

case "$UI_PORT" in
    ''|*[!0-9]*) die "--port must be a number, got '$UI_PORT'" ;;
esac

# Resolve the console script, tolerating POSIX and Windows venv layouts.
find_bin() {
    for candidate in "$VENV/bin/doc-agent" "$VENV/Scripts/doc-agent.exe" "$VENV/Scripts/doc-agent"; do
        if [ -x "$candidate" ]; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    return 1
}

BIN="$(find_bin || true)"
if [ -z "$BIN" ]; then
    log "installing into $VENV (first run)"
    if command -v uv >/dev/null 2>&1; then
        uv venv "$VENV" >&2
        uv pip install --quiet --python "$VENV/bin/python" -e ".[dev]" >&2
    else
        command -v python3 >/dev/null 2>&1 || die "python3 not found"
        python3 -m venv "$VENV" >&2
        "$VENV/bin/python" -m pip install --quiet --upgrade pip >&2
        "$VENV/bin/python" -m pip install --quiet -e ".[dev]" >&2
    fi
    BIN="$(find_bin || true)"
    [ -n "$BIN" ] || die "install finished but doc-agent was not found in $VENV"
fi

start_ui_background() {
    mkdir -p -- "$(dirname -- "$UI_LOG")"
    "$BIN" ui --host "$UI_HOST" --port "$UI_PORT" >"$UI_LOG" 2>&1 </dev/null &
    UI_PID=$!
    trap 'kill "$UI_PID" 2>/dev/null || true' EXIT INT TERM

    # Give uvicorn a moment to bind so a port clash surfaces here, not silently in the log.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        kill -0 "$UI_PID" 2>/dev/null || break
        if command -v curl >/dev/null 2>&1 &&
            curl -fsS -o /dev/null --max-time 1 "http://$UI_HOST:$UI_PORT" 2>/dev/null; then
            break
        fi
        sleep 0.5
    done

    if ! kill -0 "$UI_PID" 2>/dev/null; then
        log "the UI exited during startup; last lines of $UI_LOG:"
        tail -n 20 -- "$UI_LOG" >&2 || true
        exit 1
    fi
}

case "$MODE" in
    ui)
        log "UI on http://$UI_HOST:$UI_PORT  (Ctrl-C to stop)"
        exec "$BIN" ui --host "$UI_HOST" --port "$UI_PORT"
        ;;
    mcp)
        if [ -t 0 ]; then
            log "MCP speaks JSON-RPC over stdio and is normally spawned by its client,"
            log "so a bare terminal will just look idle. Register it instead:"
            log "  {\"command\": \"$PWD/$BIN\", \"args\": [\"mcp\"]}"
        fi
        exec "$BIN" mcp
        ;;
    both)
        start_ui_background
        log "UI  http://$UI_HOST:$UI_PORT  (logs: $UI_LOG)"
        log "MCP stdio on this terminal; Ctrl-C stops both"
        "$BIN" mcp
        ;;
esac
