#!/bin/bash
# ping-claude setup
# Creates ~/scripts/ping-claude.sh and installs a launchd agent
# that pings Claude Code at 09:00, 14:00, 19:00 daily.

set -e

SCRIPTS_DIR="$HOME/scripts"
PING_SCRIPT="$SCRIPTS_DIR/ping-claude.sh"
PLIST="$HOME/Library/LaunchAgents/com.claudecode.ping.plist"
LABEL="com.claudecode.ping"

# 1. Create scripts directory
mkdir -p "$SCRIPTS_DIR"

# 2. Write the ping script
cat > "$PING_SCRIPT" << 'SCRIPT'
#!/bin/bash
LOG="$HOME/scripts/ping-claude.log"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pinging Claude Code..." >> "$LOG"
RESPONSE=$(claude --print "ping" 2>&1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Response: $RESPONSE" >> "$LOG"
SCRIPT

chmod +x "$PING_SCRIPT"

# 3. Unload existing agent if any
if launchctl list "$LABEL" &>/dev/null; then
    launchctl unload "$PLIST" 2>/dev/null || true
fi

# 4. Write launchd plist (09:00, 14:00, 19:00)
cat > "$PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claudecode.ping</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$PING_SCRIPT</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key><integer>9</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <dict>
            <key>Hour</key><integer>14</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <dict>
            <key>Hour</key><integer>19</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
    </array>
    <key>StandardOutPath</key>
    <string>$SCRIPTS_DIR/ping-claude.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPTS_DIR/ping-claude.log</string>
</dict>
</plist>
PLIST

# 5. Load the agent
launchctl load "$PLIST"

echo "ping-claude scheduler installed and loaded."
echo "  Script : $PING_SCRIPT"
echo "  Log    : $SCRIPTS_DIR/ping-claude.log"
echo "  Times  : 09:00 / 14:00 / 19:00 daily"
