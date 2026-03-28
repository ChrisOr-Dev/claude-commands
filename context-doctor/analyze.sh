#!/bin/bash
# Context Doctor — Token Usage Analyzer for Claude Code
# Analyzes JSONL session files and outputs a JSON summary.
# No dependencies beyond bash/grep/awk. Zero token cost.
#
# Usage: bash analyze.sh [days]    (default: 7 days)
# Output: JSON summary to stdout
#
# Credit: Inspired by u/RyanSeanPhillips' context_analysis.py
#         https://github.com/RyanSeanPhillips/cldctrl

set -e

DAYS="${1:-7}"
CLAUDE_DIR="$HOME/.claude/projects"

if [ ! -d "$CLAUDE_DIR" ]; then
    echo '{"error":"Claude Code data directory not found at '"$CLAUDE_DIR"'"}' >&2
    exit 1
fi

JSONL_FILES=$(find "$CLAUDE_DIR" -name "*.jsonl" -mtime -"$DAYS" -not -path "*/subagents/*" 2>/dev/null)

if [ -z "$JSONL_FILES" ]; then
    echo '{"error":"No session files found in the last '"$DAYS"' days"}'
    exit 0
fi

# Extract token data from assistant messages, one line per turn:
# session_id input_tokens output_tokens cache_read cache_creation timestamp project
extract_turns() {
    while IFS= read -r file; do
        local proj
        proj=$(basename "$(dirname "$file")")
        grep -n '"type"' "$file" 2>/dev/null | grep '"assistant"' | while IFS=: read -r lineno _; do
            local line
            line=$(sed -n "${lineno}p" "$file")
            # Only process lines with input_tokens
            if echo "$line" | grep -q '"input_tokens"'; then
                local inp out cr cw sid ts
                inp=$(echo "$line" | grep -o '"input_tokens"[[:space:]]*:[[:space:]]*[0-9]*' | grep -o '[0-9]*$' || echo 0)
                out=$(echo "$line" | grep -o '"output_tokens"[[:space:]]*:[[:space:]]*[0-9]*' | grep -o '[0-9]*$' || echo 0)
                cr=$(echo "$line" | grep -o '"cache_read_input_tokens"[[:space:]]*:[[:space:]]*[0-9]*' | grep -o '[0-9]*$' || echo 0)
                cw=$(echo "$line" | grep -o '"cache_creation_input_tokens"[[:space:]]*:[[:space:]]*[0-9]*' | grep -o '[0-9]*$' || echo 0)
                sid=$(echo "$line" | grep -o '"sessionId"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"' || echo "unknown")
                ts=$(echo "$line" | grep -o '"timestamp"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"' || echo "")
                [ -z "$inp" ] && inp=0
                [ -z "$out" ] && out=0
                [ -z "$cr" ] && cr=0
                [ -z "$cw" ] && cw=0
                echo "$sid $inp $out $cr $cw $ts $proj"
            fi
        done
    done <<< "$JSONL_FILES"
}

# Run extraction and pipe to awk for aggregation
extract_turns | awk '
BEGIN {
    total_input = 0; total_output = 0; total_cr = 0; total_cw = 0
    total_turns = 0; total_misses = 0
    over_200k = 0; over_400k = 0; max_ctx_all = 0
    min_date = ""; max_date = ""
}
{
    sid = $1; inp = $2+0; out = $3+0; cr = $4+0; cw = $5+0; ts = $6; proj = $7
    ctx = cr + inp + cw
    total_tok = cr + inp + out + cw

    total_input += inp; total_output += out; total_cr += cr; total_cw += cw
    total_turns++

    # Cache miss: hit% < 20 and context > 5000
    if (ctx > 5000) {
        hit_pct = (cr / ctx) * 100
        if (hit_pct < 20) total_misses++
    }

    # Track max context per session
    if (ctx > sess_max[sid]) {
        sess_max[sid] = ctx
        sess_proj[sid] = proj
    }
    sess_total[sid] += total_tok

    # Date range
    if (ts != "") {
        day = substr(ts, 1, 10)
        if (min_date == "" || day < min_date) min_date = day
        if (max_date == "" || day > max_date) max_date = day
    }
}
END {
    sess_count = 0; sum_ctx = 0
    # Arrays for top 3
    for (i = 1; i <= 3; i++) { top_ctx[i] = 0; top_sid[i] = ""; top_proj[i] = ""; top_total[i] = 0 }

    for (sid in sess_max) {
        sess_count++
        ck = sess_max[sid] / 1000
        sum_ctx += ck
        if (ck > 200) over_200k++
        if (ck > 400) over_400k++
        if (sess_max[sid] > max_ctx_all) max_ctx_all = sess_max[sid]

        for (i = 1; i <= 3; i++) {
            if (sess_max[sid] > top_ctx[i]) {
                for (j = 3; j > i; j--) {
                    top_ctx[j] = top_ctx[j-1]; top_sid[j] = top_sid[j-1]
                    top_proj[j] = top_proj[j-1]; top_total[j] = top_total[j-1]
                }
                top_ctx[i] = sess_max[sid]; top_sid[i] = substr(sid, 1, 8)
                top_proj[i] = sess_proj[sid]; top_total[i] = sess_total[sid]
                break
            }
        }
    }

    avg_ctx = (sess_count > 0) ? sum_ctx / sess_count : 0
    hit_rate = (total_turns > 0) ? ((total_turns - total_misses) / total_turns * 100) : 0
    extra = int(total_misses * avg_ctx * 0.9)

    printf "{\n"
    printf "  \"period\": \"%s ~ %s\",\n", min_date, max_date
    printf "  \"sessions_analyzed\": %d,\n", sess_count
    printf "  \"total_turns\": %d,\n", total_turns
    printf "  \"avg_final_context_k\": %d,\n", avg_ctx
    printf "  \"max_context_k\": %d,\n", max_ctx_all / 1000
    printf "  \"sessions_over_200k\": %d,\n", over_200k
    printf "  \"sessions_over_400k\": %d,\n", over_400k
    printf "  \"cache_hit_rate_pct\": %.1f,\n", hit_rate
    printf "  \"cache_misses\": %d,\n", total_misses
    printf "  \"total_input_k\": %d,\n", total_input / 1000
    printf "  \"total_output_k\": %d,\n", total_output / 1000
    printf "  \"total_cache_read_k\": %d,\n", total_cr / 1000
    printf "  \"total_cache_creation_k\": %d,\n", total_cw / 1000
    printf "  \"extra_tokens_from_misses_k\": %d,\n", extra
    printf "  \"top_expensive\": [\n"
    first = 1
    for (i = 1; i <= 3; i++) {
        if (top_ctx[i] > 0) {
            if (!first) printf ",\n"
            printf "    {\"session\":\"%s\",\"project\":\"%s\",\"max_context_k\":%d,\"total_tokens_k\":%d}", \
                top_sid[i], top_proj[i], top_ctx[i]/1000, top_total[i]/1000
            first = 0
        }
    }
    printf "\n  ]\n"
    printf "}\n"
}
'
