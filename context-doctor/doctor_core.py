"""
Context Doctor — shared parser + aggregator (stdlib only).

Single source of truth for both the JSON summary (analyze.sh wrapper) and the
visual chart (analyze-visual.py). Reads Claude Code session JSONL, extracts
per-turn token usage from the canonical ``.message.usage.*`` path, and emits the
same JSON schema as the original analyze.sh — with correct values.

Why this exists: the previous line-based grep/awk extractor double-counted every
token field, because each assistant record repeats its usage numbers under
``.message.usage.iterations[]``. Parsing the JSON object (not the text) reads the
canonical value once and ignores the duplicate automatically.

Usage (CLI): python3 doctor_core.py [days]   (default: 7)   -> JSON to stdout

Credit: Inspired by u/RyanSeanPhillips' context_analysis.py
        https://github.com/RyanSeanPhillips/cldctrl
"""

import os
import sys
import json
import time

CLAUDE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "projects")

# Cache-miss heuristic (ported 1:1 from the original awk block).
CTX_MIN_FOR_MISS = 5000
MISS_HIT_PCT = 20


def project_for(path):
    """Project bucket = parent dir of the session file.

    Robust to a ``.../<hash>/sessions/<uuid>.jsonl`` layout (some Claude Code
    versions): if the immediate parent is ``sessions``, climb one more level so
    bucketing keys on the real project hash, never the literal ``"sessions"``.
    """
    d = os.path.dirname(path)
    base = os.path.basename(d)
    if base == "sessions":
        base = os.path.basename(os.path.dirname(d))
    return base


def find_session_files(days, claude_dir=CLAUDE_DIR):
    """Yield *.jsonl session files modified within the last ``days`` days.

    Mirrors the original ``find ... -mtime -DAYS -not -path '*/subagents/*'``.
    """
    cutoff = time.time() - days * 86400
    for root, _dirs, files in os.walk(claude_dir):
        if os.sep + "subagents" + os.sep in (root + os.sep):
            continue
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            fp = os.path.join(root, name)
            try:
                if os.path.getmtime(fp) >= cutoff:
                    yield fp
            except OSError:
                continue


def _count_blocks(content):
    """Count message.content[] blocks by type. Tolerant of absent/non-list."""
    n_tool_use = n_thinking = n_text = 0
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            bt = block.get("type")
            if bt == "tool_use":
                n_tool_use += 1
            elif bt == "thinking":
                n_thinking += 1
            elif bt == "text":
                n_text += 1
    return n_tool_use, n_thinking, n_text


def _row_for(rec, proj, path):
    """Build a turn row dict from an assistant record carrying ``message.usage``.

    Returns ``None`` if the record is not an assistant turn with a usage dict.
    Carries both the legacy summary keys (untouched) and the richer warehouse
    ``turns`` columns, all read from the single record already in hand.
    """
    if rec.get("type") != "assistant":
        return None
    message = rec.get("message") or {}
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None

    inp = _int(usage.get("input_tokens"))
    out = _int(usage.get("output_tokens"))
    cr = _int(usage.get("cache_read_input_tokens"))
    cw = _int(usage.get("cache_creation_input_tokens"))
    ctx = cr + inp + cw

    model = message.get("model")
    is_synthetic = model == "<synthetic>"

    if ctx == 0:
        hit_pct = None
        is_miss = False
    else:
        hit_pct = (cr / ctx) * 100
        is_miss = ctx > CTX_MIN_FOR_MISS and hit_pct < MISS_HIT_PCT

    n_tool_use, n_thinking, n_text = _count_blocks(message.get("content"))

    server = usage.get("server_tool_use")
    if not isinstance(server, dict):
        server = {}
    web_search = _int(server.get("web_search_requests"))
    web_fetch = _int(server.get("web_fetch_requests"))

    return {
        # --- legacy summary keys (unchanged) ---
        "session": rec.get("sessionId") or "unknown",
        "project": proj,
        "input": inp,
        "output": out,
        "cache_read": cr,
        "cache_creation": cw,
        "context": ctx,
        "total": ctx + out,
        "timestamp": rec.get("timestamp") or "",
        # --- richer warehouse `turns` columns ---
        "uuid": rec.get("uuid"),
        "parent_uuid": rec.get("parentUuid"),
        "git_branch": rec.get("gitBranch"),
        "cwd": rec.get("cwd"),
        "model": model,
        "is_synthetic": is_synthetic,
        "stop_reason": message.get("stop_reason"),
        "hit_pct": hit_pct,
        "is_miss": is_miss,
        "n_tool_use": n_tool_use,
        "n_thinking": n_thinking,
        "n_text": n_text,
        "web_search": web_search,
        "web_fetch": web_fetch,
        "source_file": path,
    }


def iter_session(path, start_offset=0, start_line_no=0):
    """Generator yielding one turn row dict per assistant record with usage.

    Append-aware incremental resume: opens ``path`` in binary mode, seeks to
    ``start_offset``, and tracks the byte position by accumulating each line's
    raw byte length (never relying on text-mode ``tell()``). Only lines ending in
    ``b"\\n"`` are consumed; a partial trailing line (concurrent append) or EOF
    stops iteration, leaving that line for the next run.

    Every fully-consumed line advances the offset and increments the line count
    (assistant or not), so ``end_line_no`` is an absolute line index. Yields rows
    only for ``assistant`` records carrying ``message.usage``.

    On exhaustion, ``return``s ``(end_offset, end_line_no)`` — surfaced to the
    caller as ``StopIteration.value`` (or discarded by ``list()``).
    """
    proj = project_for(path)
    offset = start_offset
    line_no = start_line_no
    try:
        f = open(path, "rb")
    except OSError:
        return (offset, line_no)
    with f:
        f.seek(start_offset)
        while True:
            raw = f.readline()
            if not raw.endswith(b"\n"):
                # partial trailing line or EOF: leave unconsumed.
                break
            offset += len(raw)
            line_no += 1
            line = raw.decode("utf-8", errors="ignore")
            if '"assistant"' not in line:
                continue
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            row = _row_for(rec, proj, path)
            if row is not None:
                yield row
    return (offset, line_no)


def parse_session(path):
    """Parse one JSONL file into a list of per-turn dicts.

    One row per ``assistant`` record carrying ``.message.usage``. Tokens are read
    from the canonical usage path; ``iterations[]`` is ignored by construction.
    Malformed lines are skipped. Returns the legacy summary keys plus the richer
    warehouse ``turns`` columns so all consumers share one extraction.

    Thin shim over ``iter_session`` — ``list()`` consumes the generator and
    discards its ``(end_offset, end_line_no)`` return value.
    """
    return list(iter_session(path))


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def iter_turns(days, claude_dir=CLAUDE_DIR):
    """All turns across every session file in the window."""
    for fp in find_session_files(days, claude_dir):
        for t in parse_session(fp):
            yield t


def build_summary(days, claude_dir=CLAUDE_DIR):
    """Aggregate turns into the analyze.sh JSON schema (logic ported from awk)."""
    total_input = total_output = total_cr = total_cw = 0
    total_turns = total_misses = 0
    min_date = max_date = ""
    sess_max = {}
    sess_proj = {}
    sess_total = {}

    for t in iter_turns(days, claude_dir):
        sid = t["session"]
        ctx = t["context"]
        total_tok = t["total"]

        total_input += t["input"]
        total_output += t["output"]
        total_cr += t["cache_read"]
        total_cw += t["cache_creation"]
        total_turns += 1

        if ctx > CTX_MIN_FOR_MISS:
            hit_pct = (t["cache_read"] / ctx) * 100
            if hit_pct < MISS_HIT_PCT:
                total_misses += 1

        if ctx > sess_max.get(sid, 0):
            sess_max[sid] = ctx
            sess_proj[sid] = t["project"]
        sess_total[sid] = sess_total.get(sid, 0) + total_tok

        ts = t["timestamp"]
        if ts:
            day = ts[:10]
            if min_date == "" or day < min_date:
                min_date = day
            if max_date == "" or day > max_date:
                max_date = day

    sess_count = 0
    sum_ctx = 0.0
    over_200k = over_400k = 0
    max_ctx_all = 0
    # Top-3 by max context, preserving the awk insertion-sort behavior.
    top = []  # list of (max_ctx, sid, proj, total)
    for sid, mctx in sess_max.items():
        sess_count += 1
        ck = mctx / 1000
        sum_ctx += ck
        if ck > 200:
            over_200k += 1
        if ck > 400:
            over_400k += 1
        if mctx > max_ctx_all:
            max_ctx_all = mctx
        top.append((mctx, sid, sess_proj.get(sid, ""), sess_total.get(sid, 0)))

    top.sort(key=lambda r: r[0], reverse=True)
    top = top[:3]

    avg_ctx = (sum_ctx / sess_count) if sess_count > 0 else 0
    hit_rate = ((total_turns - total_misses) / total_turns * 100) if total_turns > 0 else 0
    extra = int(total_misses * avg_ctx * 0.9)

    return {
        "period": "%s ~ %s" % (min_date, max_date),
        "sessions_analyzed": sess_count,
        "total_turns": total_turns,
        "avg_final_context_k": int(avg_ctx),
        "max_context_k": int(max_ctx_all / 1000),
        "sessions_over_200k": over_200k,
        "sessions_over_400k": over_400k,
        "cache_hit_rate_pct": round(hit_rate, 1),
        "cache_misses": total_misses,
        "total_input_k": int(total_input / 1000),
        "total_output_k": int(total_output / 1000),
        "total_cache_read_k": int(total_cr / 1000),
        "total_cache_creation_k": int(total_cw / 1000),
        "extra_tokens_from_misses_k": extra,
        "top_expensive": [
            {
                "session": sid[:8],
                "project": proj,
                "max_context_k": int(mctx / 1000),
                "total_tokens_k": int(tot / 1000),
            }
            for (mctx, sid, proj, tot) in top
        ],
    }


def main(argv):
    days = 7
    if len(argv) > 1:
        try:
            days = int(argv[1])
        except ValueError:
            print('{"error":"days argument must be an integer"}', file=sys.stderr)
            return 1

    if not os.path.isdir(CLAUDE_DIR):
        print('{"error":"Claude Code data directory not found at %s"}' % CLAUDE_DIR,
              file=sys.stderr)
        return 1

    files = list(find_session_files(days))
    if not files:
        print('{"error":"No session files found in the last %d days"}' % days)
        return 0

    print(json.dumps(build_summary(days), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
