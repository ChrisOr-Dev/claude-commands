# /context-doctor

Token usage analysis for Claude Code — find out where your tokens go and how to save them.

Claude Code token 使用分析 — 找出 token 花在哪裡，以及如何節省。

---

## Why / 為什麼需要

The 1M context window removed the old auto-compaction at ~160K tokens. Sessions now grow unchecked past 500K+. Every prompt resends the full context, so at 500K with 3 tool calls, a single prompt costs 1.5M tokens. Cache misses at large context sizes are ~10x more expensive.

1M context window 移除了舊的 ~160K 自動壓縮。Session 現在可以不受限制地成長超過 500K。每次 prompt 重送完整 context，500K + 3 tool calls = 一個 prompt 花費 1.5M tokens。大 context 下的 cache miss 成本是原來的 ~10 倍。

---

## How It Works / 運作方式

**Token-efficient design:** Heavy analysis runs in standalone scripts (zero token cost). The Claude agent only reads a small JSON summary and gives recommendations.

**省 token 設計：** 重分析由獨立腳本執行（零 token 消耗）。Agent 只讀取小型 JSON 摘要並給建議。

```
analyze.sh (pure bash)  →  JSON summary  →  agent interprets  →  recommendations
     zero tokens              ~500 bytes        minimal tokens
```

### Components

| File | Purpose | Dependencies |
|------|---------|-------------|
| `analyze.sh` | Core analysis — parses JSONL, outputs JSON | bash + awk (built-in) |
| `analyze-visual.py` | Optional chart generation | python3 + matplotlib + numpy |
| `context-doctor.md` | Agent instructions (< 50 lines) | None |

---

## What It Reports / 報告內容

| Metric | Description | Description (中文) |
|--------|-------------|-------------------|
| Context growth | Avg/max context size per session | 每 session 的 context 成長 |
| Sessions > 200K / 400K | Count of oversized sessions | 超大 session 數量 |
| Cache hit rate | % of turns served from cache | Cache 命中率 |
| Cache misses | Count and estimated extra cost | Cache miss 次數和額外成本 |
| Token breakdown | Input / output / cache read / cache creation | Token 分類統計 |
| Top expensive sessions | Ranked by max context size | 最貴的 sessions |

---

## Recommendations / 建議邏輯

| Condition | Recommendation |
|-----------|---------------|
| Avg context > 200K | Use /clear or /last-word more often |
| Sessions > 400K exist | Split large tasks into smaller sessions |
| Cache hit rate < 90% | Keep prompt intervals under 5 minutes |
| High cache miss cost | Avoid long pauses between prompts |
| High output/input ratio | Request concise responses |

---

## Standalone Usage / 獨立使用

You can run the analysis scripts directly without Claude Code:

```bash
# JSON report (last 7 days)
bash ~/.claude/commands/context-doctor/analyze.sh 7

# JSON report (last 30 days)
bash ~/.claude/commands/context-doctor/analyze.sh 30

# Visual chart (requires matplotlib)
python3 ~/.claude/commands/context-doctor/analyze-visual.py 7
```

---

## Install / 安裝

```bash
# Via installer
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote context-doctor

# Or manually
mkdir -p ~/.claude/commands/context-doctor
cp context-doctor.md ~/.claude/commands/context-doctor.md
cp analyze.sh analyze-visual.py ~/.claude/commands/context-doctor/
```

## Usage / 使用

In Claude Code, type:

```
/context-doctor
```

---

## Credits

- [RyanSeanPhillips](https://github.com/RyanSeanPhillips) — 1M context token burn analysis
- [cldctrl](https://github.com/RyanSeanPhillips/cldctrl) — context_analysis.py
