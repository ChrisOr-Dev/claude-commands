"""
Context Doctor — Visual Analysis for Claude Code
Generates a token usage chart from JSONL session files.

Requirements: pip install matplotlib numpy
Usage: python3 analyze-visual.py [days]
Output: context_analysis.png in current directory

Credit: Based on u/RyanSeanPhillips' context_analysis.py
        https://github.com/RyanSeanPhillips/cldctrl
"""

import os
import re
import sys
import platform
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import numpy as np
except ImportError:
    print("Requires: pip install matplotlib numpy", file=sys.stderr)
    sys.exit(1)

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 7
CLAUDE_DIR = Path.home() / '.claude' / 'projects'
LOCAL_TZ = timezone(timedelta(seconds=-datetime.now().astimezone().utcoffset().total_seconds()))
CUTOFF = datetime.now(LOCAL_TZ) - timedelta(days=DAYS)

plt.style.use('dark_background')
BG = '#0d1117'
PANEL_BG = '#161b22'
GRID_COLOR = '#30363d'
plt.rcParams.update({
    'figure.facecolor': BG, 'axes.facecolor': PANEL_BG,
    'axes.edgecolor': GRID_COLOR, 'axes.labelcolor': '#e6edf3',
    'text.color': '#e6edf3', 'xtick.color': '#8b949e', 'ytick.color': '#8b949e',
    'grid.color': GRID_COLOR, 'grid.alpha': 0.3,
})

COLORS = ['#ff6b6b', '#ff9f43', '#feca57', '#48dbfb', '#55efc4',
          '#a29bfe', '#fd79a8', '#6c5ce7', '#00cec9', '#0abde3']


def parse_session(fp):
    turns = []
    with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if '"assistant"' not in line or '"input_tokens"' not in line:
                continue
            cache = re.search(r'"cache_read_input_tokens"\s*:\s*(\d+)', line)
            inp = re.search(r'"input_tokens"\s*:\s*(\d+)', line)
            out = re.search(r'"output_tokens"\s*:\s*(\d+)', line)
            cw = re.search(r'"cache_creation_input_tokens"\s*:\s*(\d+)', line)
            ts = re.search(r'"timestamp"\s*:\s*"([^"]+)"', line)

            cr = int(cache.group(1)) if cache else 0
            it = int(inp.group(1)) if inp else 0
            ot = int(out.group(1)) if out else 0
            cwr = int(cw.group(1)) if cw else 0
            ctx = cr + it + cwr

            timestamp = None
            if ts:
                try:
                    timestamp = datetime.fromisoformat(
                        ts.group(1).replace('Z', '+00:00')).astimezone(LOCAL_TZ)
                except Exception:
                    pass

            if ctx > 5000:
                hit_pct = (cr / ctx * 100) if ctx > 0 else 0
                turns.append({
                    'context': ctx, 'total': cr + it + ot + cwr,
                    'cache_read': cr, 'is_miss': hit_pct < 20,
                    'timestamp': timestamp,
                })
    return turns


# Collect all turns
all_turns = []
sessions = []
for proj_dir in CLAUDE_DIR.iterdir():
    if not proj_dir.is_dir():
        continue
    for jf in proj_dir.glob('*.jsonl'):
        if jf.stat().st_mtime < CUTOFF.timestamp():
            continue
        turns = parse_session(jf)
        if turns:
            contexts = [t['context'] / 1000 for t in turns]
            sessions.append({'name': proj_dir.name, 'contexts': contexts,
                             'max_ctx': max(contexts)})
            all_turns.extend(turns)

if not all_turns:
    print("No data found.", file=sys.stderr)
    sys.exit(1)

sessions.sort(key=lambda s: s['max_ctx'], reverse=True)
all_turns.sort(key=lambda t: t['timestamp'] or datetime.min.replace(tzinfo=LOCAL_TZ))

# Plot: 2 rows x 2 cols
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle(f'Context Doctor — {len(sessions)} sessions, {len(all_turns):,} turns (last {DAYS} days)',
             fontsize=16, fontweight='bold', color='white', y=0.98)

# 1. Context growth curves (top 10 sessions)
ax = axes[0, 0]
for i, s in enumerate(sessions[:10]):
    ax.plot(s['contexts'], linewidth=1.5, alpha=0.8, color=COLORS[i % len(COLORS)])
ax.axhline(y=200, color='#ff9f43', linestyle='--', linewidth=1.5, alpha=0.6, label='200K warning')
ax.axhline(y=400, color='#ff6b6b', linestyle='--', linewidth=1.5, alpha=0.6, label='400K danger')
ax.set_xlabel('Turn #')
ax.set_ylabel('Context (K tokens)')
ax.set_title('Context Growth (Top 10 Sessions)', fontsize=12, color='#48dbfb')
ax.legend(fontsize=8)
ax.grid(alpha=0.2)

# 2. Context size distribution
ax = axes[0, 1]
max_ctxs = [s['max_ctx'] for s in sessions]
ax.hist(max_ctxs, bins=20, color='#48dbfb', alpha=0.7, edgecolor='#30363d')
ax.axvline(x=200, color='#ff9f43', linestyle='--', linewidth=1.5, label='200K')
ax.axvline(x=400, color='#ff6b6b', linestyle='--', linewidth=1.5, label='400K')
ax.set_xlabel('Max Context (K tokens)')
ax.set_ylabel('Session Count')
ax.set_title('Max Context Distribution', fontsize=12, color='#48dbfb')
ax.legend(fontsize=8)
ax.grid(alpha=0.2)

# 3. Cache hits vs misses over time
ax = axes[1, 0]
hits = [t for t in all_turns if not t['is_miss'] and t['timestamp']]
misses = [t for t in all_turns if t['is_miss'] and t['timestamp']]
if hits:
    ax.scatter([t['timestamp'] for t in hits], [t['context'] / 1000 for t in hits],
               alpha=0.05, s=4, color='#55efc4', edgecolors='none', label='Cache hit')
if misses:
    ax.scatter([t['timestamp'] for t in misses], [t['context'] / 1000 for t in misses],
               alpha=0.6, s=20, color='#ff6b6b', edgecolors='none', label='Cache MISS')
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
ax.set_xlabel('Date')
ax.set_ylabel('Context (K tokens)')
ax.set_title('Cache Hits vs Misses', fontsize=12, color='#ff6b6b')
ax.legend(fontsize=9)
ax.grid(alpha=0.2)

# 4. Daily token consumption
ax = axes[1, 1]
daily = {}
for t in all_turns:
    if not t['timestamp']:
        continue
    day = t['timestamp'].date()
    daily.setdefault(day, 0)
    daily[day] += t['total']
days_sorted = sorted(daily.keys())
vals = [daily[d] / 1_000_000 for d in days_sorted]
ax.bar(days_sorted, vals, width=0.8, color='#a29bfe', alpha=0.7)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
ax.set_xlabel('Date')
ax.set_ylabel('Total Tokens (M)')
ax.set_title('Daily Token Consumption', fontsize=12, color='#a29bfe')
ax.grid(alpha=0.2)

plt.tight_layout(rect=[0, 0, 1, 0.95])
out = Path.cwd() / 'context_analysis.png'
plt.savefig(str(out), dpi=150, bbox_inches='tight', facecolor=BG)
print(f"Saved: {out}")
