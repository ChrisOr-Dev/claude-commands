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


if __name__ == "__main__":
    unittest.main()
