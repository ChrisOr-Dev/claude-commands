#!/bin/bash
# CLI wrapper for npx/bunx usage
# Delegates to install.sh with all arguments

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec "$SCRIPT_DIR/install.sh" "$@"
