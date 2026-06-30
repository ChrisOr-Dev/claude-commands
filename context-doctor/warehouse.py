"""Context Doctor — DuckDB store + incremental ingest (warehouse layer).

Module split (ADR-0010): ``doctor.py`` is the CLI, this module owns the store
and ingest. It executes the **packaged** ``schema.sql`` (the canonical contract —
see ADR-0005) to create the store, enforces the ``schema_version`` header, and
incrementally appends the ``turns`` table from session JSONL.

Slice 3 scope: ``turns`` ingest only. The schema creates every table (events,
phases, session_class, …) but those stay empty until later slices. Events
ingest and ``last_event_seq`` population land in slice 4.

Memory model (ADR-0008): ingest is O(batch) — ``iter_session`` is a generator,
chunked through ``itertools.batched`` into ``executemany``; DuckDB is bounded by
a conservative ``memory_limit`` and spills to a ``tmp/`` dir beside the DB.
"""

import json
import os
import re
from datetime import datetime, timezone
from itertools import batched
from pathlib import Path

import doctor_core

# Default per-user store + source (ADR-0011). Both overridable via the CLI.
DEFAULT_DB = Path.home() / ".claude" / "context-doctor" / "metrics.duckdb"
DEFAULT_SOURCE = Path.home() / ".claude" / "projects"

# Packaged canonical schema (ships in the wheel/sdist; resolved relative to this
# module so the running schema and the published contract cannot drift).
SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Batch size for the streamed appender (peak Python memory = one batch).
BATCH_SIZE = 2000

# Memory caps (bytes).
_GB = 1024 ** 3
_MEM_HARD_CAP = 1 * _GB        # never exceed 1GB
_MEM_FLOOR = 512 * 1024 * 1024  # never go below 512MB
_MEM_FRACTION = 0.25            # ~25% of detected RAM

_SCHEMA_VERSION_RE = re.compile(r"^--\s*schema_version:\s*(\d+)\s*$", re.MULTILINE)

# Ordered (column, row-dict-key) mapping for the `turns` table. The row dict uses
# LEGACY keys (session/timestamp/input/output/context/total) — mapped here once.
_TURNS_COLS = [
    ("uuid", "uuid"),
    ("parent_uuid", "parent_uuid"),
    ("session_id", "session"),
    ("project", "project"),
    ("git_branch", "git_branch"),
    ("cwd", "cwd"),
    ("ts", "timestamp"),
    ("model", "model"),
    ("is_synthetic", "is_synthetic"),
    ("stop_reason", "stop_reason"),
    ("input_tokens", "input"),
    ("output_tokens", "output"),
    ("cache_read", "cache_read"),
    ("cache_creation", "cache_creation"),
    ("context_tokens", "context"),
    ("total_tokens", "total"),
    ("is_miss", "is_miss"),
    ("hit_pct", "hit_pct"),
    ("n_tool_use", "n_tool_use"),
    ("n_thinking", "n_thinking"),
    ("n_text", "n_text"),
    ("web_search", "web_search"),
    ("web_fetch", "web_fetch"),
    ("source_file", "source_file"),
]
_TURNS_COL_NAMES = [c for c, _ in _TURNS_COLS]
_TURNS_INSERT = (
    "INSERT INTO turns (%s) VALUES (%s) ON CONFLICT (uuid) DO NOTHING"
    % (", ".join(_TURNS_COL_NAMES), ", ".join(["?"] * len(_TURNS_COL_NAMES)))
)

# `events` columns in INSERT order. `source_file` and `seq` are assigned at
# ingest (not by the parser); the rest come from the event dict.
_EVENTS_INSERT = (
    "INSERT INTO events "
    "(source_file, session_id, ts, seq, type, subtype, key, num, ref) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT (source_file, seq) DO NOTHING"
)


def schema_text():
    """Return the packaged schema.sql text."""
    return SCHEMA_PATH.read_text(encoding="utf-8")


def expected_schema_version(text=None):
    """Parse ``-- schema_version: N`` from the packaged schema.sql (single source
    of the expected version). Raises if the header is missing/malformed."""
    if text is None:
        text = schema_text()
    m = _SCHEMA_VERSION_RE.search(text)
    if not m:
        raise ValueError("schema.sql is missing a '-- schema_version: N' header")
    return int(m.group(1))


def _detect_ram_bytes():
    """Best-effort total RAM in bytes (Linux sysconf); None if undetectable."""
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return None


def _memory_limit_bytes():
    """Conservative cap: min(1GB, ~25% of detected RAM), 512MB floor.

    Falls back to 1GB if RAM is undetectable.

    **Override (ops / testing):** set the ``DOCTOR_MEMORY_LIMIT_BYTES``
    environment variable to a positive integer to override the auto-derived
    cap entirely.  The value is floored at 64 MB (``_MEM_FLOOR_OVERRIDE``) so
    an operator never accidentally sets an unworkably low cap in production; it
    is never clamped upward, so a low test value like ``67108864`` (64 MB) is
    honoured as-is.  When the env var is absent or zero the default heuristic
    applies unchanged — existing tests and production behaviour are unaffected.
    """
    raw_env = os.environ.get("DOCTOR_MEMORY_LIMIT_BYTES", "")
    if raw_env:
        try:
            env_val = int(raw_env)
        except ValueError:
            env_val = 0
        if env_val > 0:
            _MEM_FLOOR_OVERRIDE = 64 * 1024 * 1024  # 64 MB — safety floor for override
            return max(_MEM_FLOOR_OVERRIDE, env_val)

    ram = _detect_ram_bytes()
    if ram is None:
        candidate = _GB
    else:
        candidate = min(_MEM_HARD_CAP, int(ram * _MEM_FRACTION))
    return max(_MEM_FLOOR, candidate)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _ts_or_none(value):
    """ISO timestamp string, with "" -> None so DuckDB stores NULL."""
    return value if value else None


def _event_key(value):
    """Coerce an event ``key`` to the TEXT column. ``None``/``str`` pass through;
    anything else (e.g. a ``queued_command`` ``prompt`` that is a content-block
    list) is JSON-encoded so a non-string never reaches the TEXT column."""
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _event_num(value):
    """Coerce an event ``num`` to the DOUBLE column. ``None`` stays; ``int``/
    ``float`` -> ``float``; anything else (incl. ``bool`` guarded out) -> ``None``."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _event_row_tuple(source_file, seq, event):
    """Map a parser event dict + ingest-assigned ``(source_file, seq)`` to the
    ordered `events` value tuple, applying column-type coercions."""
    return (
        source_file,
        event.get("session_id"),
        _ts_or_none(event.get("ts")),
        seq,
        event.get("type"),
        event.get("subtype"),
        _event_key(event.get("key")),
        _event_num(event.get("num")),
        event.get("ref"),
    )


def connect(db_path=None, duckdb_mod=None):
    """Open the DuckDB store at ``db_path`` (default per-user), creating the
    parent dir on first run, and apply the bounded-memory PRAGMAs.

    ``memory_limit`` = min(1GB, ~25% RAM), 512MB floor; ``temp_directory`` = a
    ``tmp/`` dir beside the DB so sort/percentile spills to disk. Pass
    ``duckdb_mod`` to inject the module (the CLI passes the gate-checked one);
    otherwise it is imported here."""
    if duckdb_mod is None:
        import duckdb as duckdb_mod
    db_path = Path(db_path) if db_path is not None else DEFAULT_DB
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = db_path.parent / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    conn = duckdb_mod.connect(str(db_path))
    conn.execute("PRAGMA memory_limit='%dB'" % _memory_limit_bytes())
    conn.execute("SET temp_directory = ?", [str(tmp_dir)])
    return conn


def _has_meta(conn):
    row = conn.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_name = 'meta'"
    ).fetchone()
    return bool(row and row[0])


def _drop_all(conn):
    """Drop every object the schema creates (derived cache — ADR-0005)."""
    # Drop the convenience view first (depends on tables), then tables.
    conn.execute("DROP VIEW IF EXISTS sessions")
    for tbl in ("turns", "events", "phases", "session_class",
                "ingested_files", "meta"):
        conn.execute("DROP TABLE IF EXISTS %s" % tbl)


def bootstrap(conn):
    """Ensure the store carries the expected schema version.

    Fresh store (no ``meta``): execute schema.sql. Existing store with a matching
    ``meta.schema_version``: no-op. Mismatch: DROP everything and re-create from
    the packaged schema (the caller then re-ingests — the schema is a derived
    cache). Returns ``True`` if the store was (re)built fresh (caller should treat
    any prior ingest state as gone), ``False`` if it was already current."""
    text = schema_text()
    expected = expected_schema_version(text)

    if not _has_meta(conn):
        conn.execute(text)
        return True

    row = conn.execute("SELECT schema_version FROM meta").fetchone()
    current = row[0] if row else None
    if current == expected:
        return False

    # Mismatch — never run on a stale schema. Drop & rebuild.
    _drop_all(conn)
    conn.execute(text)
    return True


def _stored_file_state(conn, path):
    """Return ``(mtime, size, last_offset, last_line_no, last_event_seq)`` for
    ``path`` from ``ingested_files``, or ``None`` if unseen."""
    return conn.execute(
        "SELECT mtime, size, last_offset, last_line_no, last_event_seq "
        "FROM ingested_files WHERE path = ?",
        [path],
    ).fetchone()


def _turns_row_tuple(row):
    """Map a parser row dict (legacy keys) to the ordered `turns` value tuple,
    or ``None`` if the row lacks a uuid (PRIMARY KEY can't be NULL — skip it)."""
    if not row.get("uuid"):
        return None
    out = []
    for col, key in _TURNS_COLS:
        if col == "ts":
            out.append(_ts_or_none(row.get(key)))
        else:
            out.append(row.get(key))
    return tuple(out)


def _ingest_file(conn, path, start_offset, start_line_no, start_event_seq):
    """Stream ``turns`` AND ``events`` from one file in a single pass.

    Drives the combined ``iter_turns_and_events`` generator (the file is read +
    parsed ONCE), routing ``"turn"`` items into the turns batch and ``"event"``
    items into the events batch — both chunked through ``itertools.batched``
    (peak memory = one batch). Each event is assigned a monotonic per-file
    ``seq`` from a counter seeded at ``start_event_seq`` (0 for a fresh/rewritten
    file; the stored ``last_event_seq`` on resume), so one assistant line's
    multiple ``tool_use`` blocks get distinct seqs and a tail read continues the
    ordinal without collision or gap.

    Returns ``(turns_inserted, skipped_no_uuid, events_inserted, end_offset,
    end_line_no, end_event_seq)``. ``end_*`` offset/line come from the
    generator's StopIteration value; ``end_event_seq`` is the seq counter after
    the file (i.e. the next free seq), which ``ingest`` stores as
    ``last_event_seq``."""
    gen = doctor_core.iter_turns_and_events(
        path, start_offset=start_offset, start_line_no=start_line_no)
    turns_inserted = 0
    skipped = 0
    events_inserted = 0
    end_state = [start_offset, start_line_no]
    # Mutable counter so the inner generator can advance it as events stream by.
    seq_state = [start_event_seq]

    def _drive():
        # Drive the combined generator manually so its return value (end
        # offset/line) is captured from StopIteration rather than lost.
        while True:
            try:
                yield next(gen)
            except StopIteration as stop:
                if stop.value is not None:
                    end_state[0], end_state[1] = stop.value
                return

    # Single walk: split the tagged stream into two batched sinks. We can't run
    # two independent ``batched`` over one generator, so buffer per-tag up to
    # BATCH_SIZE and flush each sink as it fills.
    turn_buf = []
    event_buf = []

    def _flush_turns():
        nonlocal turns_inserted
        if turn_buf:
            conn.executemany(_TURNS_INSERT, turn_buf)
            turns_inserted += len(turn_buf)
            turn_buf.clear()

    def _flush_events():
        nonlocal events_inserted
        if event_buf:
            conn.executemany(_EVENTS_INSERT, event_buf)
            events_inserted += len(event_buf)
            event_buf.clear()

    for tag, item in _drive():
        if tag == "turn":
            t = _turns_row_tuple(item)
            if t is None:
                skipped += 1
            else:
                turn_buf.append(t)
                if len(turn_buf) >= BATCH_SIZE:
                    _flush_turns()
        else:  # "event"
            seq = seq_state[0]
            seq_state[0] = seq + 1
            event_buf.append(_event_row_tuple(path, seq, item))
            if len(event_buf) >= BATCH_SIZE:
                _flush_events()

    _flush_turns()
    _flush_events()

    return (turns_inserted, skipped, events_inserted,
            end_state[0], end_state[1], seq_state[0])


def _upsert_ingested_file(conn, path, mtime, size, last_offset, last_line_no,
                          last_event_seq):
    conn.execute(
        "INSERT INTO ingested_files "
        "(path, mtime, size, last_offset, last_line_no, last_event_seq, "
        " ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (path) DO UPDATE SET "
        "  mtime = excluded.mtime, size = excluded.size, "
        "  last_offset = excluded.last_offset, "
        "  last_line_no = excluded.last_line_no, "
        "  last_event_seq = excluded.last_event_seq, "
        "  ingested_at = excluded.ingested_at",
        [path, mtime, size, last_offset, last_line_no, last_event_seq,
         _now_iso()],
    )


def ingest(conn, source_dir=None):
    """Incrementally ingest ``turns`` from every session JSONL under
    ``source_dir`` (default ``~/.claude/projects``).

    Discovery uses ``find_session_files(days=None)`` — the mtime window is
    DISABLED for ingest (keep-all store); only the subagents filter applies.
    Files are processed one at a time. Per file, ``ingested_files`` decides:

    * unchanged (same mtime AND size) -> skip;
    * grew (size > stored) -> resume from ``last_offset`` / ``last_line_no``;
    * shrank / rewritten / new (size < stored, or no row) -> DELETE the file's
      existing ``turns`` rows, then ingest from offset 0.

    ``events`` are populated in the SAME single pass as ``turns`` (slice 4):
    each event gets a monotonic per-file ``seq`` (seeded from the stored
    ``last_event_seq`` on resume, 0 on a fresh/rewritten file), inserted with an
    ``ON CONFLICT (source_file, seq) DO NOTHING`` idempotency backstop; the seq
    counter's end value is stored as ``last_event_seq`` (the next free seq).
    Returns a summary dict (incl. ``events_inserted``)."""
    source = Path(source_dir) if source_dir is not None else DEFAULT_SOURCE

    files_scanned = 0
    files_ingested = 0
    files_skipped = 0
    turns_inserted = 0
    events_inserted = 0
    rows_skipped_no_uuid = 0

    for fp in doctor_core.find_session_files(None, claude_dir=str(source)):
        files_scanned += 1
        try:
            st = os.stat(fp)
        except OSError:
            continue
        mtime = st.st_mtime
        size = st.st_size

        stored = _stored_file_state(conn, fp)
        if stored is not None:
            (s_mtime, s_size, s_offset, s_line_no, s_event_seq) = stored
            if mtime == s_mtime and size == s_size:
                files_skipped += 1
                continue
            if size > s_size:
                # grew -> resume from the stored tail position; seed the seq
                # counter from last_event_seq so tail events continue the
                # ordinal without collision or gap.
                start_offset, start_line_no = int(s_offset), int(s_line_no)
                start_event_seq = int(s_event_seq) if s_event_seq is not None else 0
            else:
                # shrank / rewritten -> purge this file's turns AND events,
                # re-ingest from offset 0 with the seq counter reset to 0.
                conn.execute("DELETE FROM turns WHERE source_file = ?", [fp])
                conn.execute("DELETE FROM events WHERE source_file = ?", [fp])
                start_offset, start_line_no = 0, 0
                start_event_seq = 0
        else:
            start_offset, start_line_no = 0, 0
            start_event_seq = 0

        (inserted, skipped, ev_inserted,
         end_offset, end_line_no, end_event_seq) = _ingest_file(
            conn, fp, start_offset, start_line_no, start_event_seq)
        turns_inserted += inserted
        events_inserted += ev_inserted
        rows_skipped_no_uuid += skipped
        files_ingested += 1

        _upsert_ingested_file(
            conn, fp, mtime, size, end_offset, end_line_no, end_event_seq)

    return {
        "files_scanned": files_scanned,
        "files_ingested": files_ingested,
        "files_skipped": files_skipped,
        "turns_inserted": turns_inserted,
        "events_inserted": events_inserted,
        "rows_skipped_no_uuid": rows_skipped_no_uuid,
    }
