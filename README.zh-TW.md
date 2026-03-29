**繁體中文** | [English](./README.md)

# Claude Commands

一組優化過的 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 自訂指令集合。全域安裝後可在所有專案中使用。

這是一個開源項目，收集網路上實用的 Claude Code 優化技巧，整理為即用的指令，提供一鍵安裝。所有 credit 歸屬原作者。

---

## 安裝

### npx (Node.js)

```bash
# 安裝全部指令
npx claude-commands --all

# 安裝特定指令（可多選）
npx claude-commands last-word
npx claude-commands last-word context-doctor
```

### bunx (Bun)

```bash
# 安裝全部指令
bunx claude-commands --all

# 安裝特定指令（可多選）
bunx claude-commands last-word
bunx claude-commands last-word context-doctor
```

### Homebrew

```bash
brew tap ChrisOr-Dev/claude-commands
brew install claude-commands
```

### curl（無需依賴）

```bash
# 安裝全部指令
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --all --remote

# 安裝特定指令（可多選）
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word context-doctor
```

### Git Clone 手動安裝

```bash
git clone https://github.com/ChrisOr-Dev/claude-commands.git
cd claude-commands
chmod +x install.sh
./install.sh --all
```

---

## 可用指令

| 指令 | 說明 | Credit |
|------|------|--------|
| [`/last-word`](./last-word/) | 清空 context 前的收尾歸檔工具 | 靈感來自 [@chan_yu_chen](https://www.threads.com/@chan_yu_chen/post/DWBIYy3Eek3) |
| [`/context-doctor`](./context-doctor/) | Token 使用分析與優化建議 | 靈感來自 [RyanSeanPhillips](https://github.com/RyanSeanPhillips) |
| [`/ping-claude`](./ping-claude/) | 每日 session 暖機排程，避免 5 小時 rate limit | 靈感來自 [@maigo.tom](https://www.threads.com/@maigo.tom) |

### 分開安裝指令

<details>
<summary><strong>/last-word</strong> — 收尾歸檔工具</summary>

清空 context 前執行，保存學習成果並產生接續 prompt。

```bash
npx claude-commands last-word
# 或
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word
# 或手動
cp last-word/last-word.md ~/.claude/commands/last-word.md
```

在 Claude Code 中使用：`/last-word`

[詳細說明 →](./last-word/)

</details>

<details>
<summary><strong>/context-doctor</strong> — Token 使用分析</summary>

分析 Claude Code 的 token 使用情況並取得優化建議。重分析由獨立腳本執行（零 token 消耗）。

```bash
npx claude-commands context-doctor
# 或
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote context-doctor
# 或手動
mkdir -p ~/.claude/commands/context-doctor
cp context-doctor/context-doctor.md ~/.claude/commands/context-doctor.md
cp context-doctor/analyze.sh context-doctor/analyze-visual.py ~/.claude/commands/context-doctor/
```

在 Claude Code 中使用：`/context-doctor`

[詳細說明 →](./context-doctor/)

</details>

<details>
<summary><strong>/ping-claude</strong> — 每日 session 暖機排程器</summary>

每天自動在 09:00、14:00、19:00 對 Claude Code 發送 ping，提前啟動 session 計時器，避免在尖峰時段觸碰 5 小時 rate limit。

```bash
npx claude-commands ping-claude
# 或
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote ping-claude
# 或手動
mkdir -p ~/.claude/commands/ping-claude
cp ping-claude/ping-claude.md ~/.claude/commands/ping-claude.md
cp ping-claude/setup.sh ~/.claude/commands/ping-claude/
```

在 Claude Code 中使用：`/ping-claude`

[詳細說明 →](./ping-claude/)

</details>

---

## 移除

```bash
cd claude-commands
chmod +x uninstall.sh

# 移除全部
./uninstall.sh --all

# 移除特定指令
./uninstall.sh last-word
```

或手動移除：

```bash
rm ~/.claude/commands/<command-name>.md
```

---

## 運作方式

Claude Code 會從 `~/.claude/commands/` 載入自訂指令。每個 `.md` 檔案會變成可在任何 session 中使用的 slash command。

**目錄結構：**

```
claude-commands/
├── README.md
├── package.json
├── install.sh
├── uninstall.sh
├── bin/
│   └── cli.js
├── last-word/
│   ├── last-word.md         <- 指令檔案
│   └── README.md
└── context-doctor/
    ├── context-doctor.md    <- 指令檔案
    ├── analyze.sh           <- 獨立分析腳本
    ├── analyze-visual.py    <- 可選圖表產生器
    └── README.md
```

每個指令有自己的目錄。安裝腳本會複製 `.md` 到 `~/.claude/commands/`，附屬腳本則複製到子目錄。

---

## 貢獻

想新增指令？

1. 建立新目錄：`your-command/`
2. 新增指令檔案：`your-command/your-command.md`
3. 新增說明文件：`your-command/README.md` + `your-command/README.zh-TW.md`
4. 更新 `install.sh` 和 `uninstall.sh` 中的 `ALL_COMMANDS` 陣列
5. 在兩個 README 的可用指令表格中新增項目
6. 提交 pull request

---

## 授權

MIT
