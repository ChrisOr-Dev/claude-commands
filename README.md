# Claude Commands

A collection of optimized custom commands for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Install globally and use across all your projects.

一組優化過的 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 自訂指令集合。全域安裝後可在所有專案中使用。

---

## Installation / 安裝

### npx (Node.js)

```bash
# Install all commands / 安裝全部指令
npx claude-commands --all

# Install specific command(s) / 安裝特定指令（可多選）
npx claude-commands last-word
npx claude-commands last-word context-doctor
```

### bunx (Bun)

```bash
# Install all commands / 安裝全部指令
bunx claude-commands --all

# Install specific command(s) / 安裝特定指令（可多選）
bunx claude-commands last-word
bunx claude-commands last-word context-doctor
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

# Install specific command(s) / 安裝特定指令（可多選）
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word context-doctor
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
| [`/context-doctor`](./context-doctor/) | Token usage analysis with optimization recommendations | Token 使用分析與優化建議 | Inspired by [u/RyanSeanPhillips](https://www.reddit.com/r/ClaudeAI/comments/1s5qove/) |

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

<details>
<summary><strong>/context-doctor</strong> — Token usage analysis / Token 使用分析</summary>

Analyze your Claude Code token usage and get optimization recommendations. Heavy analysis runs in standalone scripts (zero token cost).

分析 Claude Code 的 token 使用情況並取得優化建議。重分析由獨立腳本執行（零 token 消耗）。

```bash
# npx
npx claude-commands context-doctor

# bunx
bunx claude-commands context-doctor

# curl
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote context-doctor

# Manual / 手動
mkdir -p ~/.claude/commands/context-doctor
cp context-doctor/context-doctor.md ~/.claude/commands/context-doctor.md
cp context-doctor/analyze.sh context-doctor/analyze-visual.py ~/.claude/commands/context-doctor/
```

Usage in Claude Code / 使用方式：
```
/context-doctor
```

[Read more / 詳細說明 →](./context-doctor/)

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
│   └── cli.js
├── last-word/
│   ├── last-word.md         ← command file
│   └── README.md
└── context-doctor/
    ├── context-doctor.md    ← command file
    ├── analyze.sh           ← standalone analysis script
    ├── analyze-visual.py    ← optional chart generator
    └── README.md
```

Each command lives in its own directory. The installer copies `.md` files to `~/.claude/commands/` and any extra scripts to a subdirectory.

每個指令有自己的目錄。安裝腳本會複製 `.md` 到 `~/.claude/commands/`，附屬腳本則複製到子目錄。

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
