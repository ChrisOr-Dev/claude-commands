"""Slice 3 tests — DuckDB store + incremental `turns` ingest.

All tests run against a frozen ``--source`` and a throwaway ``--db`` in temp
dirs, so nothing live appends mid-test and the idempotency check is
deterministic (ADR-0004 / ADR-0010). Covers backfill, idempotency, incremental
tail resume, shrink/rewrite re-ingest, schema-version-mismatch rebuild, and the
bounded-memory PRAGMAs.

Run: python3 context-doctor/test_warehouse.py
"""

import json
import os
import tempfile
import unittest

import duckdb

import warehouse


def _assistant(uuid, sid="s1", ts="2026-06-28T00:00:00Z", **usage_extra):
    usage = {"input_tokens": 100, "output_tokens": 200,
             "cache_read_input_tokens": 300, "cache_creation_input_tokens": 400}
    usage.update(usage_extra)
    return {
        "type": "assistant", "sessionId": sid, "timestamp": ts, "uuid": uuid,
        "message": {"model": "claude-opus-4-8", "usage": usage,
                    "content": [{"type": "text", "text": "hi"}]},
    }


def _write_lines(fp, records):
    with open(fp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _append_lines(fp, records):
    with open(fp, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


class WarehouseTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.source = os.path.join(self.root, "projects", "proj-hash")
        os.makedirs(self.source)
        self.db = os.path.join(self.root, "store", "metrics.duckdb")
        self.f1 = os.path.join(self.source, "a.jsonl")
        self.f2 = os.path.join(self.source, "b.jsonl")

    def tearDown(self):
        self._tmp.cleanup()

    def _ingest(self):
        conn = warehouse.connect(self.db, duckdb_mod=duckdb)
        try:
            warehouse.bootstrap(conn)
            return warehouse.ingest(conn, source_dir=os.path.join(
                self.root, "projects"))
        finally:
            conn.close()

    def _turns_count(self):
        conn = duckdb.connect(self.db)
        try:
            return conn.execute("SELECT count(*) FROM turns").fetchone()[0]
        finally:
            conn.close()


class TestBackfill(WarehouseTestBase):
    def test_first_ingest_inserts_all_assistant_turns(self):
        _write_lines(self.f1, [_assistant("u1"), _assistant("u2")])
        _write_lines(self.f2, [_assistant("u3")])
        summary = self._ingest()
        self.assertEqual(summary["turns_inserted"], 3)
        self.assertEqual(summary["files_scanned"], 2)
        self.assertEqual(summary["files_ingested"], 2)
        self.assertEqual(self._turns_count(), 3)

        # ingested_files has a sane row per file.
        conn = duckdb.connect(self.db)
        try:
            rows = conn.execute(
                "SELECT path, size, last_offset, last_line_no "
                "FROM ingested_files ORDER BY path").fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 2)
        for path, size, last_offset, last_line_no in rows:
            self.assertEqual(last_offset, os.path.getsize(path))
            self.assertEqual(last_offset, size)
            self.assertGreater(last_line_no, 0)


class TestIdempotency(WarehouseTestBase):
    def test_second_ingest_unchanged_inserts_zero(self):
        _write_lines(self.f1, [_assistant("u1"), _assistant("u2")])
        _write_lines(self.f2, [_assistant("u3")])
        self._ingest()
        before = self._turns_count()
        summary2 = self._ingest()
        self.assertEqual(summary2["turns_inserted"], 0)
        self.assertEqual(summary2["files_skipped"], 2)
        self.assertEqual(self._turns_count(), before)


class TestIncrementalTail(WarehouseTestBase):
    def test_appended_line_adds_exactly_one(self):
        _write_lines(self.f1, [_assistant("u1"), _assistant("u2")])
        self._ingest()
        self.assertEqual(self._turns_count(), 2)
        _append_lines(self.f1, [_assistant("u3")])
        summary = self._ingest()
        self.assertEqual(summary["turns_inserted"], 1)
        self.assertEqual(self._turns_count(), 3)


class TestShrinkRewrite(WarehouseTestBase):
    def test_shrunk_file_reingests_without_duplicates(self):
        _write_lines(self.f1, [_assistant("u1"), _assistant("u2"),
                               _assistant("u3")])
        self._ingest()
        self.assertEqual(self._turns_count(), 3)
        # Rewrite smaller with a fresh set of uuids.
        _write_lines(self.f1, [_assistant("v1")])
        summary = self._ingest()
        self.assertEqual(summary["turns_inserted"], 1)
        # old u1..u3 deleted, only v1 remains.
        self.assertEqual(self._turns_count(), 1)
        conn = duckdb.connect(self.db)
        try:
            uuids = [r[0] for r in conn.execute(
                "SELECT uuid FROM turns").fetchall()]
        finally:
            conn.close()
        self.assertEqual(uuids, ["v1"])


class TestSchemaVersionMismatch(WarehouseTestBase):
    def test_mismatch_drops_and_reingests(self):
        _write_lines(self.f1, [_assistant("u1"), _assistant("u2")])
        self._ingest()
        self.assertEqual(self._turns_count(), 2)

        # Corrupt the stored schema version.
        conn = duckdb.connect(self.db)
        try:
            conn.execute("UPDATE meta SET schema_version = -999")
        finally:
            conn.close()

        # Reconnect + bootstrap: mismatch -> drop & rebuild (turns wiped), then
        # ingest backfills from the JSONL again to the correct count.
        summary = self._ingest()
        self.assertEqual(self._turns_count(), 2)
        self.assertEqual(summary["turns_inserted"], 2)
        # version restored.
        conn = duckdb.connect(self.db)
        try:
            ver = conn.execute("SELECT schema_version FROM meta").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(ver, warehouse.expected_schema_version())


class TestNullUuidSkipped(WarehouseTestBase):
    def test_assistant_without_uuid_is_skipped_and_counted(self):
        good = _assistant("u1")
        bad = _assistant("u2")
        del bad["uuid"]  # no uuid -> skip (PRIMARY KEY can't be NULL)
        _write_lines(self.f1, [good, bad])
        summary = self._ingest()
        self.assertEqual(summary["turns_inserted"], 1)
        self.assertEqual(summary["rows_skipped_no_uuid"], 1)
        self.assertEqual(self._turns_count(), 1)


class TestMemoryPragmas(WarehouseTestBase):
    def test_memory_limit_and_temp_directory_set(self):
        conn = warehouse.connect(self.db, duckdb_mod=duckdb)
        try:
            mem = conn.execute(
                "SELECT current_setting('memory_limit')").fetchone()[0]
            tmp = conn.execute(
                "SELECT current_setting('temp_directory')").fetchone()[0]
        finally:
            conn.close()
        # memory_limit reflects a bounded cap (<= ~1GB, not the 80% default).
        self.assertTrue(mem)
        self.assertTrue(any(u in mem for u in ("MiB", "GiB")))
        # temp_directory is a tmp/ dir beside the DB.
        self.assertTrue(tmp.endswith("tmp"))
        self.assertTrue(os.path.isdir(tmp))

    def test_memory_limit_within_expected_bounds(self):
        b = warehouse._memory_limit_bytes()
        self.assertGreaterEqual(b, 512 * 1024 * 1024)
        self.assertLessEqual(b, 1024 ** 3)


# --- Slice 4: events ingest (combined single pass) -------------------------

def _assistant_two_tools(uuid, sid="s1", ts="2026-06-28T00:00:00Z"):
    """Assistant turn whose content carries TWO tool_use blocks (must get two
    distinct event seqs) plus usage (so it also produces a turn row)."""
    return {
        "type": "assistant", "sessionId": sid, "timestamp": ts, "uuid": uuid,
        "message": {
            "model": "claude-opus-4-8",
            "usage": {"input_tokens": 100, "output_tokens": 200,
                      "cache_read_input_tokens": 300,
                      "cache_creation_input_tokens": 400},
            "content": [
                {"type": "text", "text": "doing two things"},
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                {"type": "tool_use", "name": "Read", "input": {"file": "x"}},
            ],
        },
    }


def _local_command(sid="s1", ts="2026-06-28T00:00:01Z"):
    return {"type": "system", "subtype": "local_command", "sessionId": sid,
            "timestamp": ts,
            "content": "<command-name>/doctor</command-name> stdout"}


def _queued_command(prompt, sid="s1", ts="2026-06-28T00:00:02Z"):
    return {"type": "attachment", "sessionId": sid, "timestamp": ts,
            "attachment": {"type": "queued_command", "prompt": prompt}}


def _mode(value="plan", sid="s1", ts="2026-06-28T00:00:03Z"):
    return {"type": "mode", "mode": value, "sessionId": sid, "timestamp": ts}


def _permission_mode(value="acceptEdits", sid="s1", ts="2026-06-28T00:00:04Z"):
    return {"type": "permission-mode", "permissionMode": value,
            "sessionId": sid, "timestamp": ts}


def _turn_duration(ms=1234, mc=5, sid="s1", ts="2026-06-28T00:00:05Z"):
    return {"type": "system", "subtype": "turn_duration", "durationMs": ms,
            "messageCount": mc, "sessionId": sid, "timestamp": ts}


class EventsTestBase(WarehouseTestBase):
    def _events(self, where=""):
        conn = duckdb.connect(self.db)
        try:
            sql = ("SELECT source_file, seq, type, subtype, key, num, ref "
                   "FROM events")
            if where:
                sql += " WHERE " + where
            sql += " ORDER BY source_file, seq"
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def _events_count(self):
        conn = duckdb.connect(self.db)
        try:
            return conn.execute("SELECT count(*) FROM events").fetchone()[0]
        finally:
            conn.close()


class TestEventsPopulatedAndSeq(EventsTestBase):
    def test_events_match_projection_with_monotonic_unique_seq(self):
        _write_lines(self.f1, [
            _assistant_two_tools("u1"),     # 2 tool_use events
            _local_command(),               # command/local_command
            _queued_command("/plan now"),   # command/queued_command (str key)
            _mode("plan"),                  # mode
            _permission_mode("acceptEdits"),  # permission-mode
            _turn_duration(1234, 5),        # system/turn_duration
        ])
        summary = self._ingest()
        rows = self._events(
            "source_file = '%s'" % self.f1.replace("'", "''"))

        subtypes = [(t, st) for (_sf, _sq, t, st, _k, _n, _r) in rows]
        self.assertEqual(subtypes, [
            ("tool_use", "Bash"),
            ("tool_use", "Read"),
            ("command", "local_command"),
            ("command", "queued_command"),
            ("mode", None),
            ("permission-mode", None),
            ("system", "turn_duration"),
        ])

        seqs = [sq for (_sf, sq, *_rest) in rows]
        self.assertEqual(seqs, list(range(len(rows))))         # 0..N-1
        self.assertEqual(seqs, sorted(seqs))                    # monotonic
        self.assertEqual(len(seqs), len(set(seqs)))             # unique
        # The two tool_use blocks on ONE line got DISTINCT seqs.
        self.assertEqual(seqs[0], 0)
        self.assertEqual(seqs[1], 1)
        self.assertNotEqual(seqs[0], seqs[1])

        # turn_duration carried durationMs (num) and messageCount (key).
        td = [r for r in rows if r[3] == "turn_duration"][0]
        self.assertEqual(td[5], 1234.0)
        self.assertEqual(td[4], "5")

        self.assertEqual(summary["events_inserted"], len(rows))


class TestCombinedPass(EventsTestBase):
    def test_one_ingest_populates_both_turns_and_events(self):
        _write_lines(self.f1, [
            _assistant_two_tools("u1"),
            _local_command(),
        ])
        summary = self._ingest()
        self.assertEqual(summary["turns_inserted"], 1)
        self.assertEqual(self._turns_count(), 1)
        self.assertEqual(summary["events_inserted"], 3)  # 2 tool_use + 1 command
        self.assertEqual(self._events_count(), 3)


class TestEventsIdempotency(EventsTestBase):
    def test_reingest_unchanged_adds_zero_events_and_turns(self):
        _write_lines(self.f1, [
            _assistant_two_tools("u1"),
            _local_command(),
            _mode("plan"),
        ])
        self._ingest()
        turns_before = self._turns_count()
        events_before = self._events_count()
        summary2 = self._ingest()
        self.assertEqual(summary2["turns_inserted"], 0)
        self.assertEqual(summary2["events_inserted"], 0)
        self.assertEqual(self._turns_count(), turns_before)
        self.assertEqual(self._events_count(), events_before)


class TestEventsIncrementalTail(EventsTestBase):
    def test_appended_events_continue_seq_without_collision(self):
        _write_lines(self.f1, [
            _assistant_two_tools("u1"),   # seq 0,1
            _local_command(),             # seq 2
        ])
        self._ingest()
        self.assertEqual(self._events_count(), 3)
        conn = duckdb.connect(self.db)
        try:
            stored_seq = conn.execute(
                "SELECT last_event_seq FROM ingested_files WHERE path = ?",
                [self.f1]).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(stored_seq, 3)  # next free seq

        _append_lines(self.f1, [
            _mode("acceptEdits"),         # seq 3
            _turn_duration(99, 1),        # seq 4
        ])
        summary = self._ingest()
        self.assertEqual(summary["events_inserted"], 2)
        rows = self._events()
        seqs = [sq for (_sf, sq, *_rest) in rows]
        self.assertEqual(seqs, [0, 1, 2, 3, 4])  # continues, no collision/gap
        self.assertEqual(len(seqs), len(set(seqs)))

        conn = duckdb.connect(self.db)
        try:
            stored_seq2 = conn.execute(
                "SELECT last_event_seq FROM ingested_files WHERE path = ?",
                [self.f1]).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(stored_seq2, 5)  # advanced


class TestEventsKeyCoercion(EventsTestBase):
    def test_queued_command_list_prompt_stored_as_text(self):
        # A queued_command whose `prompt` is a content-block LIST (not a str).
        list_prompt = [{"type": "text", "text": "/plan"},
                       {"type": "text", "text": "now"}]
        _write_lines(self.f1, [_queued_command(list_prompt)])
        summary = self._ingest()  # must not crash
        self.assertEqual(summary["events_inserted"], 1)
        rows = self._events()
        self.assertEqual(len(rows), 1)
        key = rows[0][4]
        self.assertIsInstance(key, str)              # TEXT, not a crash
        self.assertEqual(json.loads(key), list_prompt)  # round-trips


class TestEventsShrinkRewrite(EventsTestBase):
    def test_rewrite_smaller_purges_and_reseqs_from_zero(self):
        _write_lines(self.f1, [
            _assistant_two_tools("u1"),   # seq 0,1
            _local_command(),             # seq 2
            _mode("plan"),                # seq 3
        ])
        self._ingest()
        self.assertEqual(self._events_count(), 4)

        # Rewrite smaller with fresh content.
        _write_lines(self.f1, [_local_command()])  # one event
        summary = self._ingest()
        self.assertEqual(summary["events_inserted"], 1)
        rows = self._events()
        self.assertEqual(len(rows), 1)
        seqs = [sq for (_sf, sq, *_rest) in rows]
        self.assertEqual(seqs, [0])                  # reset from 0
        self.assertEqual(len(seqs), len(set(seqs)))  # no duplicate seq
        self.assertEqual(rows[0][2], "command")
        self.assertEqual(rows[0][3], "local_command")


if __name__ == "__main__":
    unittest.main()
