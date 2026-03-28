[繁體中文](./README.zh-TW.md) | **English**

# Claude Commands

A collection of optimized custom commands for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Install globally and use across all your projects.

This is an open source project that collects useful Claude Code optimization techniques found across the internet, packages them into ready-to-use commands, and provides one-click installation. All credits go to the original authors.

---

## Installation

### npx (Node.js)

```bash
# Install all commands
npx claude-commands --all

# Install specific command(s)
npx claude-commands last-word
npx claude-commands last-word context-doctor
```

### bunx (Bun)

```bash
# Install all commands
bunx claude-commands --all

# Install specific command(s)
bunx claude-commands last-word
bunx claude-commands last-word context-doctor
```

### Homebrew

```bash
brew tap ChrisOr-Dev/claude-commands
brew install claude-commands
```

### curl (no dependencies)

```bash
# Install all commands
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --all --remote

# Install specific command(s)
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word context-doctor
```

### Git Clone

```bash
git clone https://github.com/ChrisOr-Dev/claude-commands.git
cd claude-commands
chmod +x install.sh
./install.sh --all
```

---

## Available Commands

| Command | Description | Credit |
|---------|-------------|--------|
| [`/last-word`](./last-word/) | Session wrap-up & knowledge archival before clearing context | Inspired by [@chan_yu_chen](https://www.threads.com/@chan_yu_chen/post/DWBIYy3Eek3) |
| [`/context-doctor`](./context-doctor/) | Token usage analysis with optimization recommendations | Inspired by [RyanSeanPhillips](https://github.com/RyanSeanPhillips) |

### Install Individual Commands

<details>
<summary><strong>/last-word</strong> — Session wrap-up & knowledge archival</summary>

Run before clearing context to preserve learnings and enable seamless continuation.

```bash
npx claude-commands last-word
# or
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word
# or manually
cp last-word/last-word.md ~/.claude/commands/last-word.md
```

Usage in Claude Code: `/last-word`

[Read more →](./last-word/)

</details>

<details>
<summary><strong>/context-doctor</strong> — Token usage analysis</summary>

Analyze your Claude Code token usage and get optimization recommendations. Heavy analysis runs in standalone scripts (zero token cost).

```bash
npx claude-commands context-doctor
# or
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote context-doctor
# or manually
mkdir -p ~/.claude/commands/context-doctor
cp context-doctor/context-doctor.md ~/.claude/commands/context-doctor.md
cp context-doctor/analyze.sh context-doctor/analyze-visual.py ~/.claude/commands/context-doctor/
```

Usage in Claude Code: `/context-doctor`

[Read more →](./context-doctor/)

</details>

---

## Uninstall

```bash
cd claude-commands
chmod +x uninstall.sh

# Remove all
./uninstall.sh --all

# Remove specific command
./uninstall.sh last-word
```

Or remove manually:

```bash
rm ~/.claude/commands/<command-name>.md
```

---

## How It Works

Claude Code loads custom commands from `~/.claude/commands/`. Each `.md` file becomes a slash command you can invoke in any session.

**Directory structure:**

```
claude-commands/
├── README.md
├── package.json
├── install.sh
├── uninstall.sh
├── bin/
│   └── cli.js
├── last-word/
│   ├── last-word.md         <- command file
│   └── README.md
└── context-doctor/
    ├── context-doctor.md    <- command file
    ├── analyze.sh           <- standalone analysis script
    ├── analyze-visual.py    <- optional chart generator
    └── README.md
```

Each command lives in its own directory. The installer copies `.md` files to `~/.claude/commands/` and any extra scripts to a subdirectory.

---

## Contributing

Want to add a new command?

1. Create a new directory: `your-command/`
2. Add the command file: `your-command/your-command.md`
3. Add documentation: `your-command/README.md` + `your-command/README.zh-TW.md`
4. Update `ALL_COMMANDS` array in `install.sh` and `uninstall.sh`
5. Add an entry to the Available Commands table in both README files
6. Submit a pull request

---

## License

MIT
