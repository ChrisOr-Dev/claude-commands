# Claude Commands

A collection of optimized custom commands for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Install globally and use across all your projects.

一組優化過的 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 自訂指令集合。全域安裝後可在所有專案中使用。

---

## Installation / 安裝

### npx (Node.js)

```bash
# Install all commands / 安裝全部指令
npx claude-commands --all

# Install a specific command / 安裝特定指令
npx claude-commands last-word
```

### bunx (Bun)

```bash
# Install all commands / 安裝全部指令
bunx claude-commands --all

# Install a specific command / 安裝特定指令
bunx claude-commands last-word
```

### Homebrew

```bash
brew tap ChrisOr-Dev/claude-commands
brew install claude-commands
```

> Homebrew tap coming soon. / Homebrew tap 即將推出。

### curl (no dependencies / 無需依賴)

```bash
# Install all commands / 安裝全部指令
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --all --remote

# Install a specific command / 安裝特定指令
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word
```

### Git Clone / 手動安裝

```bash
git clone https://github.com/ChrisOr-Dev/claude-commands.git
cd claude-commands
chmod +x install.sh
./install.sh --all
```

---

## Available Commands / 可用指令

| Command | Description | Description (中文) | Credit |
|---------|-------------|-------------------|--------|
| [`/last-word`](./last-word/) | Session wrap-up & knowledge archival before clearing context | 清空 context 前的收尾歸檔工具 | Inspired by [@chan_yu_chen](https://www.threads.com/@chan_yu_chen/post/DWBIYy3Eek3) |

### Install Individual Commands / 分開安裝指令

<details>
<summary><strong>/last-word</strong> — Session wrap-up & knowledge archival / 收尾歸檔工具</summary>

Run before clearing context to preserve learnings and enable seamless continuation.

清空 context 前執行，保存學習成果並產生接續 prompt。

```bash
# npx
npx claude-commands last-word

# bunx
bunx claude-commands last-word

# curl
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word

# Manual / 手動
cp last-word/last-word.md ~/.claude/commands/last-word.md
```

Usage in Claude Code / 使用方式：
```
/last-word
```

[Read more / 詳細說明 →](./last-word/)

</details>

---

## Uninstall / 移除

```bash
# Clone the repo first if you haven't / 先 clone repo
cd claude-commands
chmod +x uninstall.sh

# Remove all / 移除全部
./uninstall.sh --all

# Remove specific command / 移除特定指令
./uninstall.sh last-word
```

Or remove manually / 或手動移除：

```bash
rm ~/.claude/commands/<command-name>.md
```

---

## How It Works / 運作方式

Claude Code loads custom commands from `~/.claude/commands/`. Each `.md` file becomes a slash command you can invoke in any session.

Claude Code 會從 `~/.claude/commands/` 載入自訂指令。每個 `.md` 檔案會變成可在任何 session 中使用的 slash command。

**Directory structure / 目錄結構：**

```
claude-commands/
├── README.md
├── package.json
├── install.sh
├── uninstall.sh
├── bin/
│   └── cli.sh
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
5. Add an entry to the Available Commands table and Install Individual Commands section in this README
6. Submit a pull request

---

## License

MIT
