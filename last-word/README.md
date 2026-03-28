[繁體中文](./README.zh-TW.md) | **English**

# /last-word

Session wrap-up & knowledge archival — run before clearing context to preserve learnings and enable seamless continuation.

---

## Why

Claude Code's context quality degrades around 40% usage. Rather than relying on auto-compact, proactively wrap up while quality is still high.

**Recommended workflow:**

```
Work -> context reaches ~40% -> /last-word -> /clear -> paste starter prompt -> continue
```

---

## What It Does

| Step | Action |
|------|--------|
| 1 | **Review conversation** — identify blockers, wins, CLAUDE.md gaps |
| 2 | **Classify & archive** — route learnings to the right place |
| 3 | **Handle remaining work** — save progress + generate starter prompt |
| 4 | **Sync GitHub issues** — verify issue status matches progress |
| 5 | **Clean stale content** — remove outdated memory and CLAUDE.md entries |
| 6 | **Check uncommitted changes** — warn before clearing |
| 7 | **Final summary** — confirm ready to clear |

---

## Archive Classification

The most important design decision: not everything goes to the same place.

| Type | Destination | Example |
|------|-------------|---------|
| Universal rule | `~/.claude/CLAUDE.md` | "Always use integration tests, not mocks" |
| Project rule | `{project}/CLAUDE.md` | "This repo uses pnpm, not npm" |
| Temporary state | Memory | "Feature X is 60% done, steps 4-5 remaining" |
| Design decision | Design doc or memory | "Chose approach A over B because of X constraint" |
| Already tracked | **Don't save** | Already in git history or GitHub issues |

---

## Starter Prompt

When there's unfinished work, `/last-word` generates a ready-to-paste prompt for your next session:

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

---

## Benefits

1. **Seamless continuation** — no time wasted rebuilding context after clear
2. **Progressive learning** — each session's lessons become next session's rules
3. **No bloat** — stale memory and CLAUDE.md entries are cleaned every time

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote last-word
# or manually
cp last-word.md ~/.claude/commands/last-word.md
```

## Usage

In Claude Code, type: `/last-word`

---

## Credits

Inspired by [@chan_yu_chen](https://www.threads.com/@chan_yu_chen)'s session wrap-up workflow shared on [Threads](https://www.threads.com/@chan_yu_chen/post/DWBIYy3Eek3).
