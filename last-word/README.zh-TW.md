**繁體中文** | [English](./README.md)

# /last-word

清空 context 前的收尾歸檔工具 — 保存學習成果，讓下次 session 無痛接續。

---

## 為什麼需要

Claude Code 的 context 品質在使用約 40% 後會開始下降。與其依賴 auto compact，不如在品質還好的時候主動做一次乾淨的收尾。

**建議工作流程：**

```
工作 -> context 到 ~40% -> /last-word -> /clear -> 貼上 starter prompt -> 繼續
```

---

## 功能

| 步驟 | 動作 |
|------|------|
| 1 | **回顧對話** — 找出卡點、好做法、CLAUDE.md 缺漏 |
| 2 | **分類歸檔** — 判斷每個 learning 該存在哪裡 |
| 3 | **處理未完成工作** — 存進度 + 產生接續用 prompt |
| 4 | **同步 GitHub issue** — 確認狀態與進度一致 |
| 5 | **清理過期內容** — 刪除過時的 memory 和 CLAUDE.md |
| 6 | **檢查未 commit 的變更** — 避免遺失工作 |
| 7 | **最終摘要** — 確認可以 clear |

---

## 歸檔分類邏輯

最重要的設計：不是所有東西都塞同一個地方。

| 類型 | 目標 | 範例 |
|------|------|------|
| 通用規則 | `~/.claude/CLAUDE.md` | 「一律用 integration test，不要 mock」 |
| 專案規則 | `{project}/CLAUDE.md` | 「這個 repo 用 pnpm 不用 npm」 |
| 暫時狀態 | Memory | 「Feature X 做到 60%，剩步驟 4 和 5」 |
| 設計決策 | Design doc 或 memory | 「選方案 A 不選 B，因為 X 限制」 |
| 已追蹤 | **不存** | 已在 git 或 GitHub issue 中 |

---

## 接續 Prompt

有未完成的工作時，`/last-word` 會產生一段可直接貼上的 prompt：

```
Continue the work on [feature]. Here's where I left off:

Done:
- Implemented X
- Fixed Y

Remaining:
- Step 4: ...
- Step 5: ...

Branch: feature/xyz
Related issues: #12, #15
Key files: src/foo.ts, src/bar.ts
```

下次開 session 時貼上，就能精準地接續上次的進度。

---

## 好處

1. **無痛接續** — clear 後不用花時間重建 context
2. **漸進式學習** — 每次 session 的教訓變成下次的規則
3. **不膨脹** — 每次收工都會清理過期和重複的內容

---

## 安裝

```bash
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word
# 或手動
cp last-word.md ~/.claude/commands/last-word.md
```

## 使用

在 Claude Code 中輸入：`/last-word`

---

## Credits

靈感來自 [@chan_yu_chen](https://www.threads.com/@chan_yu_chen) 在 [Threads](https://www.threads.com/@chan_yu_chen/post/DWBIYy3Eek3) 分享的 session 收尾工作流程。
