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

ALL_COMMANDS=("last-word")

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
    echo -e "${GREEN}[ OK ]${NC} $cmd_name — removed"
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
