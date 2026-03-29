# /ping-claude — Session Warm-Up Scheduler

Set up scheduled automatic "ping" to Claude Code at 9:00, 14:00, 19:00 daily.
Prevents hitting the 5-hour session rate limit by keeping sessions active from early in the day.

## Execute

Run the setup script:

```bash
bash ~/.claude/commands/ping-claude/setup.sh
```

## Verify

After setup, confirm the scheduler is loaded:

```bash
launchctl list | grep com.claudecode.ping
```

Expected output: a line with `com.claudecode.ping` (PID may show 0 if not currently running, that's normal).

Check the log for recent pings:

```bash
tail -20 ~/scripts/ping-claude.log
```

## Done

Report:
- Whether setup succeeded or failed (with any error)
- The three scheduled times (09:00, 14:00, 19:00)
- Location of the ping script (`~/scripts/ping-claude.sh`) and log (`~/scripts/ping-claude.log`)
- Confirm launchctl shows the agent as loaded

If setup failed, show the error and suggest fix.

## Uninstall

To remove the scheduler:

```bash
launchctl unload ~/Library/LaunchAgents/com.claudecode.ping.plist
rm ~/Library/LaunchAgents/com.claudecode.ping.plist
rm ~/scripts/ping-claude.sh
```
