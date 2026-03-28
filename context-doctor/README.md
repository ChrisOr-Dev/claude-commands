[繁體中文](./README.zh-TW.md) | **English**

# /context-doctor

Token usage analysis for Claude Code — find out where your tokens go and how to save them.

---

## Why

The 1M context window removed the old auto-compaction at ~160K tokens. Sessions now grow unchecked past 500K+. Every prompt resends the full context, so at 500K with 3 tool calls, a single prompt costs 1.5M tokens. Cache misses at large context sizes are ~10x more expensive.

---

## How It Works

**Token-efficient design:** Heavy analysis runs in standalone scripts (zero token cost). The Claude agent only reads a small JSON summary and gives recommendations.

```
analyze.sh (pure bash)  ->  JSON summary  ->  agent interprets  ->  recommendations
     zero tokens              ~500 bytes        minimal tokens
```

### Components

| File | Purpose | Dependencies |
|------|---------|-------------|
| `analyze.sh` | Core analysis — parses JSONL, outputs JSON | bash + awk (built-in) |
| `analyze-visual.py` | Optional chart generation | python3 + matplotlib + numpy |
| `context-doctor.md` | Agent instructions (< 50 lines) | None |

---

## What It Reports

| Metric | Description |
|--------|-------------|
| Context growth | Avg/max context size per session |
| Sessions > 200K / 400K | Count of oversized sessions |
| Cache hit rate | % of turns served from cache |
| Cache misses | Count and estimated extra cost |
| Token breakdown | Input / output / cache read / cache creation |
| Top expensive sessions | Ranked by max context size |

---

## Recommendations

| Condition | Recommendation |
|-----------|---------------|
| Avg context > 200K | Use /clear or /last-word more often |
| Sessions > 400K exist | Split large tasks into smaller sessions |
| Cache hit rate < 90% | Keep prompt intervals under 5 minutes |
| High cache miss cost | Avoid long pauses between prompts |
| High output/input ratio | Request concise responses |

---

## Standalone Usage

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

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote context-doctor
# or manually
mkdir -p ~/.claude/commands/context-doctor
cp context-doctor.md ~/.claude/commands/context-doctor.md
cp analyze.sh analyze-visual.py ~/.claude/commands/context-doctor/
```

## Usage

In Claude Code, type: `/context-doctor`

---

## Credits

- [RyanSeanPhillips](https://github.com/RyanSeanPhillips) — 1M context token burn analysis
- [cldctrl](https://github.com/RyanSeanPhillips/cldctrl) — context_analysis.py
