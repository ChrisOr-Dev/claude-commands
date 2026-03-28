#!/bin/bash
# Claude Commands Installer
# https://github.com/ChrisOr-Dev/claude-commands

set -e

REPO_URL="https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main"
TARGET_DIR="$HOME/.claude/commands"
SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# All available commands (add new commands here)
ALL_COMMANDS=("last-word" "context-doctor")

# Commands that have extra files (scripts) in a subdirectory
# Format: "command-name:file1,file2,..."
COMMAND_EXTRAS=(
    "context-doctor:analyze.sh,analyze-visual.py"
)

usage() {
    echo "Usage: install.sh [OPTIONS] [COMMAND_NAME...]"
    echo ""
    echo "Options:"
    echo "  --all       Install all available commands"
    echo "  --force     Overwrite existing commands without prompting"
    echo "  --remote    Download from GitHub instead of local files"
    echo "  -h, --help  Show this help message"
    echo ""
    echo "Available commands:"
    for cmd in "${ALL_COMMANDS[@]}"; do
        echo "  - $cmd"
    done
    echo ""
    echo "Examples:"
    echo "  ./install.sh last-word          # Install specific command"
    echo "  ./install.sh --all              # Install all commands"
    echo "  ./install.sh --all --force      # Install all, overwrite existing"
}

get_extras() {
    local cmd_name="$1"
    for entry in "${COMMAND_EXTRAS[@]}"; do
        local name="${entry%%:*}"
        local files="${entry#*:}"
        if [ "$name" = "$cmd_name" ]; then
            echo "$files"
            return
        fi
    done
}

install_command() {
    local cmd_name="$1"
    local force="$2"
    local remote="$3"
    local source_file=""

    if [ "$remote" = "true" ]; then
        source_file=$(mktemp)
        if ! curl -fsSL "$REPO_URL/$cmd_name/$cmd_name.md" -o "$source_file" 2>/dev/null; then
            echo -e "${RED}[FAIL]${NC} $cmd_name — could not download from GitHub"
            rm -f "$source_file"
            return 1
        fi
    else
        source_file="$SCRIPT_DIR/$cmd_name/$cmd_name.md"
        if [ ! -f "$source_file" ]; then
            echo -e "${RED}[FAIL]${NC} $cmd_name — source file not found: $source_file"
            return 1
        fi
    fi

    local target_file="$TARGET_DIR/$cmd_name.md"

    if [ -f "$target_file" ] && [ "$force" != "true" ]; then
        echo -e "${YELLOW}[SKIP]${NC} $cmd_name — already exists (use --force to overwrite)"
        [ "$remote" = "true" ] && rm -f "$source_file"
        return 0
    fi

    cp "$source_file" "$target_file"
    echo -e "${GREEN}[ OK ]${NC} $cmd_name.md → $target_file"
    [ "$remote" = "true" ] && rm -f "$source_file"

    # Install extra files (scripts) into subdirectory
    local extras
    extras=$(get_extras "$cmd_name")
    if [ -n "$extras" ]; then
        local extras_dir="$TARGET_DIR/$cmd_name"
        mkdir -p "$extras_dir"

        IFS=',' read -ra FILES <<< "$extras"
        for file in "${FILES[@]}"; do
            if [ "$remote" = "true" ]; then
                local tmp_extra
                tmp_extra=$(mktemp)
                if curl -fsSL "$REPO_URL/$cmd_name/$file" -o "$tmp_extra" 2>/dev/null; then
                    cp "$tmp_extra" "$extras_dir/$file"
                    chmod +x "$extras_dir/$file" 2>/dev/null || true
                    echo -e "${GREEN}[ OK ]${NC}   $file → $extras_dir/$file"
                else
                    echo -e "${YELLOW}[WARN]${NC}   $file — could not download (optional)"
                fi
                rm -f "$tmp_extra"
            else
                local src="$SCRIPT_DIR/$cmd_name/$file"
                if [ -f "$src" ]; then
                    cp "$src" "$extras_dir/$file"
                    chmod +x "$extras_dir/$file" 2>/dev/null || true
                    echo -e "${GREEN}[ OK ]${NC}   $file → $extras_dir/$file"
                fi
            fi
        done
    fi

    return 0
}

# Parse arguments
FORCE="false"
REMOTE="false"
INSTALL_ALL="false"
COMMANDS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --all)
            INSTALL_ALL="true"
            shift
            ;;
        --force)
            FORCE="true"
            shift
            ;;
        --remote)
            REMOTE="true"
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

if [ "$INSTALL_ALL" = "true" ]; then
    COMMANDS=("${ALL_COMMANDS[@]}")
elif [ ${#COMMANDS[@]} -eq 0 ]; then
    echo -e "${RED}Error: No command specified.${NC}"
    echo ""
    usage
    exit 1
fi

# If running via curl pipe, force remote mode
if [ -z "$SCRIPT_DIR" ] || [ ! -f "$SCRIPT_DIR/install.sh" ]; then
    REMOTE="true"
fi

mkdir -p "$TARGET_DIR"

echo "Installing Claude commands to $TARGET_DIR ..."
echo ""

SUCCESS=0
FAIL=0
for cmd in "${COMMANDS[@]}"; do
    if install_command "$cmd" "$FORCE" "$REMOTE"; then
        SUCCESS=$((SUCCESS + 1))
    else
        FAIL=$((FAIL + 1))
    fi
done

echo ""
echo "Done. $SUCCESS installed, $FAIL failed."

if [ $SUCCESS -gt 0 ]; then
    echo ""
    echo "Usage: type /<command-name> in Claude Code to run."
fi
