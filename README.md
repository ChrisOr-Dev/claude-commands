# Claude Commands

A collection of optimized custom commands for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Install globally and use across all your projects.

一組優化過的 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 自訂指令集合。全域安裝後可在所有專案中使用。

---

## Quick Install / 快速安裝

**Install all commands / 安裝全部指令：**

```bash
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --all --remote
```

**Install a specific command / 安裝特定指令：**

```bash
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word
```

## Manual Install / 手動安裝

```bash
git clone https://github.com/ChrisOr-Dev/claude-commands.git
cd claude-commands
chmod +x install.sh
./install.sh --all
```

## Uninstall / 移除

```bash
# Clone the repo first if you haven't
cd claude-commands
chmod +x uninstall.sh
./uninstall.sh --all
```

Or remove manually / 或手動移除：

```bash
rm ~/.claude/commands/<command-name>.md
```

---

## Available Commands / 可用指令

| Command | Description | Description (中文) |
|---------|-------------|-------------------|
| [`/last-word`](./last-word/) | Session wrap-up & knowledge archival before clearing context | 清空 context 前的收尾歸檔工具 |

---

## How It Works / 運作方式

Claude Code loads custom commands from `~/.claude/commands/`. Each `.md` file becomes a slash command you can invoke in any session.

Claude Code 會從 `~/.claude/commands/` 載入自訂指令。每個 `.md` 檔案會變成可在任何 session 中使用的 slash command。

**Directory structure / 目錄結構：**

```
claude-commands/
├── README.md
├── install.sh
├── uninstall.sh
└── last-word/
    ├── last-word.md    ← command file (copied to ~/.claude/commands/)
    └── README.md       ← detailed documentation
```

Each command lives in its own directory with its `.md` file and documentation. The installer copies only the `.md` files to your Claude Code commands directory.

每個指令有自己的目錄，包含 `.md` 檔案和說明文件。安裝腳本只會複製 `.md` 檔案到 Claude Code 的指令目錄。

---

## Contributing / 貢獻

Want to add a new command? / 想新增指令？

1. Create a new directory: `your-command/`
2. Add the command file: `your-command/your-command.md`
3. Add documentation: `your-command/README.md`
4. Update `ALL_COMMANDS` array in `install.sh` and `uninstall.sh`
5. Add an entry to the Available Commands table in this README
6. Submit a pull request

---

## License

MIT
