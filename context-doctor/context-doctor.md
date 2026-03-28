# /context-doctor — Token Usage Analysis

Analyze Claude Code token usage and provide optimization recommendations.
Heavy analysis runs in an external script (zero token cost). You only interpret the JSON result.

## Execute

1. Run the analysis script:
```bash
bash ~/.claude/commands/context-doctor/analyze.sh 7
```

2. If python3 + matplotlib are available, generate a visual chart:
```bash
python3 ~/.claude/commands/context-doctor/analyze-visual.py 2>/dev/null && echo "CHART_OK" || echo "NO_CHART"
```

3. If CHART_OK, show the chart to the user by reading `context_analysis.png` in the current directory.

## Interpret & Recommend

Read the JSON output and apply these rules:

| Condition | Recommendation |
|-----------|---------------|
| avg_final_context_k > 200 | Use /clear or /last-word more often. Aim to clear before 200K. |
| sessions_over_400k > 0 | Flag these sessions. Split large tasks into smaller sessions. |
| cache_hit_rate_pct < 90 | Keep prompt intervals under 5 minutes to avoid cache TTL expiry. |
| cache_misses > 5% of total_turns | Significant cost from cache misses. Avoid long pauses between prompts. |
| extra_tokens_from_misses_k > 1000 | High waste from cache misses. Consider shorter, focused sessions. |
| total_output_k / total_input_k > 0.3 | Request concise responses. Add "be brief" to CLAUDE.md. |

Output the full report, then the recommendations. Keep it concise.
