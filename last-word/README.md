# /last-word

Session wrap-up & knowledge archival — run before clearing context to preserve learnings and enable seamless continuation.

清空 context 前的收尾歸檔工具 — 保存學習成果，讓下次 session 無痛接續。

---

## Why / 為什麼需要

Claude Code's context quality degrades around 40% usage. Rather than relying on auto-compact, proactively wrap up while quality is still high.

Claude Code 的 context 品質在使用約 40% 後會開始下降。與其依賴 auto compact，不如在品質還好的時候主動做一次乾淨的收尾。

**Recommended workflow / 建議工作流程：**

```
Work → context reaches ~40% → /last-word → /clear → paste starter prompt → continue
```

---

## What It Does / 功能

| Step | Action | Action (中文) |
|------|--------|--------------|
| 1 | **Review conversation** — identify blockers, wins, CLAUDE.md gaps | 回顧對話 — 找出卡點、好做法、CLAUDE.md 缺漏 |
| 2 | **Classify & archive** — route learnings to the right place | 分類歸檔 — 判斷每個 learning 該存在哪裡 |
| 3 | **Handle remaining work** — save progress + generate starter prompt | 處理未完成工作 — 存進度 + 產生接續用 prompt |
| 4 | **Sync GitHub issues** — verify issue status matches progress | 同步 GitHub issue — 確認狀態與進度一致 |
| 5 | **Clean stale content** — remove outdated memory and CLAUDE.md entries | 清理過期內容 — 刪除過時的 memory 和 CLAUDE.md |
| 6 | **Check uncommitted changes** — warn before clearing | 檢查未 commit 的變更 — 避免遺失工作 |
| 7 | **Final summary** — confirm ready to clear | 最終摘要 — 確認可以 clear |

---

## Archive Classification / 歸檔分類邏輯

The most important design decision: not everything goes to the same place.

最重要的設計：不是所有東西都塞同一個地方。

| Type | Destination | Example |
|------|-------------|---------|
| Universal rule | `~/.claude/CLAUDE.md` | "Always use integration tests, not mocks" |
| Project rule | `{project}/CLAUDE.md` | "This repo uses pnpm, not npm" |
| Temporary state | Memory | "Feature X is 60% done, steps 4-5 remaining" |
| Design decision | Design doc or memory | "Chose approach A over B because of X constraint" |
| Already tracked | **Don't save** | Already in git history or GitHub issues |

| 類型 | 目標 | 範例 |
|------|------|------|
| 通用規則 | `~/.claude/CLAUDE.md` | 「一律用 integration test，不要 mock」 |
| 專案規則 | `{project}/CLAUDE.md` | 「這個 repo 用 pnpm 不用 npm」 |
| 暫時狀態 | Memory | 「Feature X 做到 60%，剩步驟 4 和 5」 |
| 設計決策 | Design doc 或 memory | 「選方案 A 不選 B，因為 X 限制」 |
| 已追蹤 | **不存** | 已在 git 或 GitHub issue 中 |

---

## Starter Prompt / 接續 Prompt

When there's unfinished work, `/last-word` generates a ready-to-paste prompt for your next session:

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

Paste it at the start of your next session to pick up exactly where you left off.

下次開 session 時貼上，就能精準地接續上次的進度。

---

## Benefits / 好處

1. **Seamless continuation** — no time wasted rebuilding context after clear
2. **Progressive learning** — each session's lessons become next session's rules
3. **No bloat** — stale memory and CLAUDE.md entries are cleaned every time

1. **無痛接續** — clear 後不用花時間重建 context
2. **漸進式學習** — 每次 session 的教訓變成下次的規則
3. **不膨脹** — 每次收工都會清理過期和重複的內容

---

## Install / 安裝

```bash
# Via installer
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word

# Or manually
cp last-word.md ~/.claude/commands/last-word.md
```

## Usage / 使用

In Claude Code, type:

```
/last-word
```

---

## Credits

Inspired by [@chan_yu_chen](https://www.threads.com/@chan_yu_chen)'s session wrap-up workflow shared on [Threads](https://www.threads.com/@chan_yu_chen/post/DWBIYy3Eek3).

靈感來自 [@chan_yu_chen](https://www.threads.com/@chan_yu_chen) 在 [Threads](https://www.threads.com/@chan_yu_chen/post/DWBIYy3Eek3) 分享的 session 收尾工作流程。
