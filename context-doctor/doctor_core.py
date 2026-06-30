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
import re
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

    ``days=None`` disables the mtime window entirely and yields ALL non-subagent
    session files — the warehouse **ingest** path (keep-all store): the ``days``
    window is a *report* filter, not an ingest filter, so backfill must not skip
    older JSONL. The default (an integer ``days``) is unchanged.
    """
    cutoff = None if days is None else time.time() - days * 86400
    for root, _dirs, files in os.walk(claude_dir):
        if os.sep + "subagents" + os.sep in (root + os.sep):
            continue
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            fp = os.path.join(root, name)
            if cutoff is None:
                yield fp
                continue
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


def _iter_lines(path, start_offset=0, start_line_no=0):
    """Shared byte-offset line walker for the incremental parsers.

    Opens ``path`` in binary mode, seeks to ``start_offset``, and yields
    ``(line_no, decoded_line)`` for every newline-terminated line, tracking the
    byte position by accumulating each line's raw byte length (never relying on
    text-mode ``tell()``). Only lines ending in ``b"\\n"`` are consumed; a partial
    trailing line (concurrent append) or EOF stops iteration, leaving that line
    for the next run. ``line_no`` is the absolute 1-based line index of the line
    just yielded.

    On exhaustion, ``return``s ``(end_offset, end_line_no)`` — surfaced to the
    caller as ``StopIteration.value``. Both ``iter_session`` and ``parse_events``
    build on this so their offset mechanics can never drift.
    """
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
            yield (line_no, raw.decode("utf-8", errors="ignore"))
    return (offset, line_no)


def iter_session(path, start_offset=0, start_line_no=0):
    """Generator yielding one turn row dict per assistant record with usage.

    Append-aware incremental resume via :func:`_iter_lines`: only ``assistant``
    records carrying ``message.usage`` produce a row, but every fully-consumed
    line advances the offset and line count so ``end_line_no`` is an absolute
    line index.

    On exhaustion, ``return``s ``(end_offset, end_line_no)`` — surfaced to the
    caller as ``StopIteration.value`` (or discarded by ``list()``).
    """
    proj = project_for(path)
    walker = _iter_lines(path, start_offset, start_line_no)
    while True:
        try:
            _line_no, line = next(walker)
        except StopIteration as stop:
            return stop.value
        if '"assistant"' not in line:
            continue
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        row = _row_for(rec, proj, path)
        if row is not None:
            yield row


_COMMAND_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>", re.DOTALL)


def _command_name_from_content(content):
    """Extract a slash-command name from a ``local_command`` ``content`` blob.

    Real ``system/local_command`` records carry NO ``command`` field; the command
    name (when present) is embedded in ``content`` as ``<command-name>/foo<…>``.
    Many such records are stdout-only continuations with no command tag — those
    yield ``None``. Returns the stripped command name or ``None``.
    """
    if not isinstance(content, str):
        return None
    m = _COMMAND_NAME_RE.search(content)
    if not m:
        return None
    name = m.group(1).strip()
    return name or None


def _count_tool_results(content):
    """Count ``tool_result`` blocks in a ``user`` ``message.content`` list."""
    if not isinstance(content, list):
        return 0
    return sum(
        1 for b in content
        if isinstance(b, dict) and b.get("type") == "tool_result"
    )


def _events_for(rec, line_no):
    """Project one curated record into zero or more generic ``events`` dicts.

    Mirrors the per-type table in the warehouse plan. Returns a list of event
    dicts (a single ``assistant`` line may yield several — one per ``tool_use``
    block). Unknown / skipped record types return an empty list and never raise.
    No ``seq`` is assigned here (the ingest layer owns that); each event carries
    the absolute source ``line_no`` instead.
    """
    rtype = rec.get("type")
    session_id = rec.get("sessionId")
    ts = rec.get("timestamp")

    def ev(etype, subtype=None, key=None, num=None, ref=None):
        return {
            "session_id": session_id,
            "ts": ts,
            "line_no": line_no,
            "type": etype,
            "subtype": subtype,
            "key": key,
            "num": num,
            "ref": ref,
        }

    if rtype == "assistant":
        out = []
        message = rec.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = block.get("name")
                key = None
                if name == "Skill":
                    inp = block.get("input")
                    if isinstance(inp, dict):
                        key = inp.get("skill")
                out.append(ev("tool_use", subtype=name, key=key,
                              ref=rec.get("uuid")))
        return out

    if rtype == "user":
        message = rec.get("message") or {}
        content = message.get("content")
        has_tur = "toolUseResult" in rec
        n_results = _count_tool_results(content)
        if has_tur or n_results:
            if isinstance(content, list):
                num = n_results
            else:
                # toolUseResult present but content isn't a list -> fallback 1.
                num = n_results if n_results else 1
            return [ev("user", subtype="tool_result", num=num,
                       ref=rec.get("promptId"))]
        return [ev("user", subtype="prompt")]

    if rtype == "system":
        subtype = rec.get("subtype")
        if subtype == "turn_duration":
            mc = rec.get("messageCount")
            return [ev("system", subtype="turn_duration",
                       num=rec.get("durationMs"),
                       key=(str(mc) if mc is not None else None))]
        if subtype == "compact_boundary":
            return [ev("system", subtype="compact_boundary")]
        if subtype == "local_command":
            return [ev("command", subtype="local_command",
                       key=_command_name_from_content(rec.get("content")))]
        # stop_hook_summary / away_summary / api_error / … -> skip (curated set).
        return []

    if rtype == "attachment":
        att = rec.get("attachment")
        if not isinstance(att, dict):
            return []
        att_type = att.get("type")
        if att_type == "queued_command":
            key = att.get("prompt") or att.get("commandMode")
            return [ev("command", subtype="queued_command", key=key)]
        return [ev("attachment", subtype=att_type)]

    if rtype == "mode":
        return [ev("mode", key=rec.get("mode"))]

    if rtype == "permission-mode":
        return [ev("permission-mode", key=rec.get("permissionMode"))]

    # ai-title / custom-title / last-prompt / file-history-snapshot /
    # queue-operation / … -> skip, never crash.
    return []


def parse_events(path, start_offset=0, start_line_no=0):
    """Generator projecting curated records into generic ``events`` rows.

    Sibling of :func:`iter_session` sharing the exact same byte-offset mechanics
    (via :func:`_iter_lines`). Yields one event dict per projected event — a
    single ``assistant`` line may yield several (one per ``tool_use`` block). Each
    event dict has keys ``session_id, ts, line_no, type, subtype, key, num, ref``.
    Does NOT assign ``seq`` (the ingest layer does, since one line can hold many
    events). Unknown / skipped record types produce no rows and never crash.

    On exhaustion, ``return``s ``(end_offset, end_line_no)`` — surfaced to the
    caller as ``StopIteration.value``.
    """
    walker = _iter_lines(path, start_offset, start_line_no)
    while True:
        try:
            line_no, line = next(walker)
        except StopIteration as stop:
            return stop.value
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(rec, dict):
            continue
        for event in _events_for(rec, line_no):
            yield event


def iter_turns_and_events(path, start_offset=0, start_line_no=0):
    """Combined single-pass generator yielding tagged turn AND event items.

    Walks :func:`_iter_lines` ONCE and ``json.loads`` each line ONCE, then yields
    tagged tuples reusing the SAME extraction helpers as the standalone parsers
    (no logic duplication):

    * ``("turn", row_dict)`` — for each assistant record with usage (via
      :func:`_row_for`); identical to what :func:`iter_session` yields.
    * ``("event", event_dict)`` — for each projected event (via
      :func:`_events_for`); a single assistant line may yield several.

    This is the ingest backbone (warehouse slice 4): turns and events are
    populated in one pass so each file is read/parsed once. :func:`iter_session`
    and :func:`parse_events` stay as-is (their tests + standalone uses remain
    valid); this is a sibling built on the same helpers.

    On exhaustion, ``return``s ``(end_offset, end_line_no)`` — surfaced to the
    caller as ``StopIteration.value``.
    """
    proj = project_for(path)
    walker = _iter_lines(path, start_offset, start_line_no)
    while True:
        try:
            line_no, line = next(walker)
        except StopIteration as stop:
            return stop.value
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(rec, dict):
            continue
        row = _row_for(rec, proj, path)
        if row is not None:
            yield ("turn", row)
        for event in _events_for(rec, line_no):
            yield ("event", event)


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
