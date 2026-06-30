#!/bin/bash
# Claude Commands Uninstaller
# https://github.com/ChrisOr-Dev/claude-commands

set -e

TARGET_DIR="$HOME/.claude/commands"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ALL_COMMANDS=("last-word" "context-doctor" "ping-claude")

usage() {
    echo "Usage: uninstall.sh [OPTIONS] [COMMAND_NAME...]"
    echo ""
    echo "Options:"
    echo "  --all       Uninstall all commands from this collection"
    echo "  -h, --help  Show this help message"
    echo ""
    echo "Commands:"
    for cmd in "${ALL_COMMANDS[@]}"; do
        echo "  - $cmd"
    done
}

uninstall_command() {
    local cmd_name="$1"
    local target_file="$TARGET_DIR/$cmd_name.md"

    if [ ! -f "$target_file" ]; then
        echo -e "${YELLOW}[SKIP]${NC} $cmd_name — not installed"
        return 0
    fi

    rm "$target_file"
    # Remove extras directory if exists
    if [ -d "$TARGET_DIR/$cmd_name" ]; then
        rm -rf "$TARGET_DIR/$cmd_name"
    fi
    echo -e "${GREEN}[ OK ]${NC} $cmd_name — removed"

    # context-doctor: symmetric with install — also remove the packaged `doctor`
    # warehouse CLI if it was put on PATH via `uv tool install`. Best-effort: skip
    # quietly if uv is absent or the tool was never installed (stdlib-only setup).
    if [ "$cmd_name" = "context-doctor" ]; then
        uninstall_doctor_tool
    fi
    return 0
}

# Best-effort removal of the packaged `doctor` CLI. Never fatal: a stdlib-only
# install (no uv) has nothing to remove here.
uninstall_doctor_tool() {
    if ! command -v uv >/dev/null 2>&1; then
        echo -e "${YELLOW}[SKIP]${NC}   doctor CLI — 'uv' not found on PATH (nothing to uninstall)."
        return 0
    fi
    if uv tool uninstall context-doctor >/dev/null 2>&1; then
        echo -e "${GREEN}[ OK ]${NC}   doctor CLI → removed via uv tool uninstall"
    else
        echo -e "${YELLOW}[SKIP]${NC}   doctor CLI — not installed via uv (nothing to uninstall)."
    fi
    return 0
}

# Parse arguments
COMMANDS=()
UNINSTALL_ALL="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --all)
            UNINSTALL_ALL="true"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            exit 1
            ;;
        *)
            COMMANDS+=("$1")
            shift
            ;;
    esac
done

if [ "$UNINSTALL_ALL" = "true" ]; then
    COMMANDS=("${ALL_COMMANDS[@]}")
elif [ ${#COMMANDS[@]} -eq 0 ]; then
    echo -e "${RED}Error: No command specified.${NC}"
    echo ""
    usage
    exit 1
fi

echo "Removing Claude commands from $TARGET_DIR ..."
echo ""

for cmd in "${COMMANDS[@]}"; do
    uninstall_command "$cmd"
done

echo ""
echo "Done."
