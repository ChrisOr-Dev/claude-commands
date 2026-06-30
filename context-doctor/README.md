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
analyze.sh -> doctor_core.py  ->  JSON summary  ->  agent interprets  ->  recommendations
        zero tokens                 ~500 bytes        minimal tokens
```

### Components

| File | Purpose | Dependencies |
|------|---------|-------------|
| `analyze.sh` | Thin stdlib wrapper — runs the parser, outputs the JSON summary | bash + python3 |
| `doctor_core.py` | Core analysis — parses JSONL, aggregates tokens | python3 (stdlib only) |
| `analyze-visual.py` | Optional chart generation | python3 + matplotlib + numpy |
| `doctor` (CLI) | Optional DuckDB **warehouse** — incremental ingest + a queryable report catalog | uv + duckdb |
| `warehouse.py` / `reports.py` / `reports/` | Warehouse store/ingest + the report catalog engine | (part of the `doctor` package) |
| `context-doctor.md` | Agent instructions (< 50 lines) | None |

> **Note:** the stdlib JSON summary requires only `python3` (no pip packages).
> Parsing moved from line-based bash/awk into `doctor_core.py` so token counts are read from the
> canonical `.message.usage.*` path (the old extractor double-counted via `usage.iterations[]`).
> matplotlib/numpy remain optional (visual chart); `uv`/`duckdb` are optional (warehouse).

---

## Warehouse (optional)

The `doctor` CLI is a DuckDB-backed **metrics warehouse**: instead of re-parsing every JSONL on each run and emitting one fixed number, it **incrementally ingests** new sessions into a local store (`~/.claude/context-doctor/metrics.duckdb`) and serves a **catalog of named, parameterized reports** — distribution stats (median/p90), configurable bands, rolling averages, per-project rollups — all as JSON.

```bash
doctor reports                                              # list the report catalog
doctor report summary --days 7                              # back-compat summary (same schema as analyze.sh)
doctor report bands --dimension context_tokens --edges 50k,200k,400k
doctor report rolling --metric total_tokens --window 20 --mode days
doctor report <name> --sql                                 # print a report's SQL (copy/extend)
doctor ingest                                               # manual refresh (reports auto-ingest first)
```

Available reports: `summary`, `bands`, `rolling`, `top-expensive`, `by-project`, `cache-health`, `daily`. Reports are the read interface — `doctor report <name>` runs one, `doctor reports` lists the catalog, `doctor report <name> --sql` prints its SQL, and `doctor ingest` refreshes the store.

**Graceful degrade.** The warehouse is purely additive. `doctor report summary` emits the *same* JSON schema as `analyze.sh`, and the `/context-doctor` skill prefers `doctor` but falls back to the stdlib `analyze.sh` when `uv`/`duckdb` isn't present — so the summary always works, with or without the warehouse. Requires [`uv`](https://docs.astral.sh/uv) (`uv tool install` puts `doctor` on PATH and pulls `duckdb`).

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

# Warehouse reports (requires uv + duckdb)
doctor report summary --days 7
doctor report bands --dimension context_tokens --edges 50k,200k,400k
```

---

## Install

```bash
# From a local clone — installs the skill + stdlib scripts AND, if uv is present,
# puts the `doctor` warehouse CLI on PATH via `uv tool install` (best-effort; the
# stdlib summary still works without uv/duckdb).
./install.sh context-doctor

# Remote (skill + stdlib scripts only; the warehouse needs the local package dir):
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote context-doctor

# or fully manual
mkdir -p ~/.claude/commands/context-doctor
cp context-doctor.md ~/.claude/commands/context-doctor.md
cp analyze.sh doctor_core.py analyze-visual.py ~/.claude/commands/context-doctor/
uv tool install ./context-doctor    # optional: enables the `doctor` warehouse CLI
```

## Usage

In Claude Code, type: `/context-doctor`

---

## Credits

- [RyanSeanPhillips](https://github.com/RyanSeanPhillips) — 1M context token burn analysis
- [cldctrl](https://github.com/RyanSeanPhillips/cldctrl) — context_analysis.py
