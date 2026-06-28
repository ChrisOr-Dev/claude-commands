#!/bin/bash
# Context Doctor — Token Usage Analyzer for Claude Code
# Thin wrapper around doctor_core.py (the single source of truth for parsing).
# Outputs a JSON summary of session token usage to stdout.
#
# Usage: bash analyze.sh [days]    (default: 7 days)
# Requires: python3 (stdlib only — no pip packages needed for the summary).
#
# Credit: Inspired by u/RyanSeanPhillips' context_analysis.py
#         https://github.com/RyanSeanPhillips/cldctrl

set -e

# Preflight: this is a thin wrapper — all parsing/aggregation lives in
# doctor_core.py, so python3 (stdlib only, no pip packages) is required.
if ! command -v python3 >/dev/null 2>&1; then
    # printf is a bash builtin, so this message prints even with a bare PATH.
    printf '%s\n' \
        "context-doctor: python3 not found on PATH." \
        "" \
        "analyze.sh is a thin wrapper around doctor_core.py — the JSON summary is produced" \
        "by Python (standard library only, no pip packages needed). Install python3, then" \
        "re-run this command:" \
        "" \
        "  - Debian/Ubuntu/WSL:  sudo apt update && sudo apt install -y python3" \
        "  - macOS (Homebrew):   brew install python3" \
        "  - Any OS via mise:    mise use -g python@latest    (https://mise.jdx.dev)" \
        "" \
        "The optional chart (analyze-visual.py) additionally needs: pip install matplotlib numpy" >&2
    echo '{"error":"python3 is required for the context-doctor summary but was not found on PATH"}'
    exit 1
fi

exec python3 "$(dirname "$0")/doctor_core.py" "${1:-7}"
