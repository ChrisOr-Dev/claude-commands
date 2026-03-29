[繁體中文](./README.zh-TW.md) | **English**

# /ping-claude — Session Warm-Up Scheduler

Automatically ping Claude Code at 09:00, 14:00, and 19:00 every day to start a fresh session timer — so you never run into the 5-hour rate limit in the middle of your work.

## How It Works

Claude Code's session timer starts when you first send a message. If you don't start early enough, you'll hit the 5-hour limit right when you need it most. This command sets up a macOS launchd scheduler that sends a silent `ping` at fixed times, so the session clock starts reliably each period.

## Usage

Run once to set up:

```
/ping-claude
```

Claude will:
1. Create `~/scripts/ping-claude.sh` — the ping script
2. Install a launchd agent at `~/Library/LaunchAgents/com.claudecode.ping.plist`
3. Load it and verify it's active

After that, no further action is needed.

## What Gets Created

| Path | Purpose |
|------|---------|
| `~/scripts/ping-claude.sh` | Runs `claude --print "ping"` and logs the response |
| `~/scripts/ping-claude.log` | Log of all ping attempts and responses |
| `~/Library/LaunchAgents/com.claudecode.ping.plist` | macOS scheduler (09:00 / 14:00 / 19:00) |

## Customize Schedule

Edit the plist to change trigger times:

```bash
launchctl unload ~/Library/LaunchAgents/com.claudecode.ping.plist
nano ~/Library/LaunchAgents/com.claudecode.ping.plist
launchctl load ~/Library/LaunchAgents/com.claudecode.ping.plist
```

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.claudecode.ping.plist
rm ~/Library/LaunchAgents/com.claudecode.ping.plist
rm ~/scripts/ping-claude.sh
```

## Credit

Inspired by [@maigo.tom](https://www.threads.com/@maigo.tom)
