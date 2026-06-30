"""Slice 5 tests — report catalog engine + the back-compat `summary` report.

Everything runs against a frozen ``--source`` (a temp dir of fixture JSONL) and a
throwaway ``--db`` in a temp dir — NEVER the user's real ~/.claude store. Covers:

  1. back-compat exactness: ``doctor report summary --days N`` JSON ==
     ``doctor_core.build_summary(days=N, claude_dir=<same source>)`` field-for-field
     (incl. identical <synthetic> treatment, top_expensive, over-200k/400k);
  2. param validation (bad int, unknown param, out-of-choices ident, non-numeric
     int_list element);
  3. ``--sql`` prints the template and does NOT execute / ingest;
  4. ``doctor reports`` lists ``summary`` with its description;
  5. injection safety: a ``1; DROP TABLE turns`` value bound via ``$name`` is data,
     not SQL — the table survives.

Run: python3 context-doctor/test_reports.py
"""

import datetime
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout, redirect_stderr

import duckdb

import doctor
import doctor_core
import reports
import warehouse


_NOW = time.time()


def _ts(off_seconds):
    """A recent UTC 'Z' timestamp, off_seconds before now (so any sane --days
    window includes it; legacy file-mtime and ts filters then agree)."""
    dt = datetime.datetime.fromtimestamp(_NOW - off_seconds, datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _asst(uuid, sid, cache_read, *, inp=100, out=200, cw=400,
          model="claude-opus-4-8", off=3600):
    return {
        "type": "assistant", "sessionId": sid, "uuid": uuid, "timestamp": _ts(off),
        "message": {
            "model": model,
            "usage": {"input_tokens": inp, "output_tokens": out,
                      "cache_read_input_tokens": cache_read,
                      "cache_creation_input_tokens": cw},
            "content": [{"type": "text", "text": "x"}],
        },
    }


def _fixture_records():
    """A fixture exercising synthetic rows, top_expensive (>3 sessions) and the
    over-200k / over-400k bands."""
    return [
        _asst("u1", "sessAAAAAAAA", 300000),                   # sessA max 300k
        _asst("u2", "sessAAAAAAAA", 250000),
        _asst("u3", "sessBBBBBBBB", 100000),                   # sessB 100k
        _asst("u4", "sessCCCCCCCC", 5000, model="<synthetic>"),  # synthetic kept
        _asst("u5", "sessDDDDDDDD", 450000),                   # sessD over 400k
        _asst("u6", "sessEEEEEEEE", 60000),                    # 4th+ session
        # a cache miss: ctx>5000, hit_pct<20 (cache_read tiny vs input)
        _asst("u7", "sessFFFFFFFF", 100, inp=50000),
    ]


def _write(fp, records):
    with open(fp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


class ReportsTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.projects = os.path.join(self.root, "projects")
        self.source = os.path.join(self.projects, "-proj")
        os.makedirs(self.source)
        self.db = os.path.join(self.root, "store", "metrics.duckdb")
        self.jsonl = os.path.join(self.source, "s.jsonl")

    def tearDown(self):
        self._tmp.cleanup()

    def _ingest(self):
        conn = warehouse.connect(self.db, duckdb_mod=duckdb)
        try:
            warehouse.bootstrap(conn)
            warehouse.ingest(conn, source_dir=self.projects)
        finally:
            conn.close()

    def _run_report(self, name, overrides):
        conn = warehouse.connect(self.db, duckdb_mod=duckdb)
        try:
            return reports.run_report(conn, name, overrides)
        finally:
            conn.close()

    def _cli(self, argv):
        """Invoke doctor.main(argv); return (rc, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                rc = doctor.main(argv)
            except SystemExit as exc:
                rc = exc.code if isinstance(exc.code, int) else 1
        return rc, out.getvalue(), err.getvalue()


class TestSummaryBackCompat(ReportsTestBase):
    def test_summary_matches_build_summary_field_for_field(self):
        _write(self.jsonl, _fixture_records())
        expected = doctor_core.build_summary(days=3650, claude_dir=self.projects)

        self._ingest()
        got = self._run_report("summary", {"days": 3650})

        # Whole-dict equality — every field, including nested top_expensive.
        self.assertEqual(got, expected)
        # Sanity: the synthetic row IS counted (matches build_summary).
        self.assertEqual(got["total_turns"], 7)
        # sessD over 400k, sessA+sessD over 200k.
        self.assertEqual(got["sessions_over_400k"], 1)
        self.assertEqual(got["sessions_over_200k"], 2)
        # the miss heuristic fired on u7.
        self.assertEqual(got["cache_misses"], 1)

    def test_summary_via_cli_matches_build_summary(self):
        _write(self.jsonl, _fixture_records())
        expected = doctor_core.build_summary(days=3650, claude_dir=self.projects)

        rc, out, err = self._cli([
            "report", "summary", "--days", "3650",
            "--source", self.projects, "--db", self.db])
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out), expected)


class TestParamValidation(ReportsTestBase):
    def test_bad_days_rejected_no_traceback(self):
        _write(self.jsonl, _fixture_records())
        rc, out, err = self._cli([
            "report", "summary", "--days", "notanint",
            "--source", self.projects, "--db", self.db])
        self.assertNotEqual(rc, 0)
        self.assertIn("days", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(out, "")

    def test_unknown_param_rejected(self):
        _write(self.jsonl, _fixture_records())
        rc, out, err = self._cli([
            "report", "summary", "--bogus", "1",
            "--source", self.projects, "--db", self.db])
        self.assertNotEqual(rc, 0)
        self.assertIn("bogus", err)
        self.assertNotIn("Traceback", err)

    def test_ident_out_of_choices_rejected(self):
        catalog = {
            "demo": reports.Report(
                "demo",
                {"description": "d", "sql": "demo.sql",
                 "params": {"col": {"type": "ident",
                                    "default": "context_tokens",
                                    "choices": ["context_tokens", "total_tokens"]}}},
                self._demo_catalog_dir()),
        }
        rep = catalog["demo"]
        with self.assertRaises(reports.ReportError):
            reports.resolve_params(rep, {"col": "evil; DROP TABLE turns"})
        # a valid choice resolves
        _bind, idents = reports.resolve_params(rep, {"col": "total_tokens"})
        self.assertEqual(idents["col"], "total_tokens")

    def test_int_list_non_numeric_element_rejected(self):
        catalog_dir = self._demo_catalog_dir()
        with open(os.path.join(self.root, "edges.sql"), "w",
                  encoding="utf-8") as f:
            f.write("SELECT width_bucket(context_tokens, $edges) FROM turns;\n")
        rep = reports.Report(
            "demo",
            {"description": "d", "sql": "edges.sql",
             "params": {"edges": {"type": "int_list",
                                  "default": [50000, 200000]}}},
            catalog_dir)
        with self.assertRaises(reports.ReportError):
            reports.resolve_params(rep, {"edges": "50k,oops,400k"})
        # shorthand expands correctly
        bind, _idents = reports.resolve_params(rep, {"edges": "50k,200k,400k"})
        self.assertEqual(bind["edges"], [50000, 200000, 400000])

    def _demo_catalog_dir(self):
        """A temp dir holding a trivial demo.sql so Report() can read it."""
        path = os.path.join(self.root, "demo.sql")
        with open(path, "w", encoding="utf-8") as f:
            f.write("SELECT {col} FROM turns WHERE 1=1;\n")
        return __import__("pathlib").Path(self.root)


class TestUndeclaredTokenRejected(unittest.TestCase):
    def test_template_token_without_ident_param_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            from pathlib import Path
            sqlp = os.path.join(d, "x.sql")
            with open(sqlp, "w", encoding="utf-8") as f:
                f.write("SELECT {dimension} FROM turns;\n")
            # {dimension} is not declared as an ident param -> reject.
            with self.assertRaises(reports.ReportError):
                reports.Report("x", {"description": "d", "sql": "x.sql",
                                     "params": {}}, Path(d))


class TestSqlFlag(ReportsTestBase):
    def test_sql_prints_template_without_executing_or_ingesting(self):
        # No fixture written, no store created beforehand. --sql must print the
        # template and never connect/ingest/execute.
        rc, out, err = self._cli([
            "report", "summary", "--sql",
            "--source", self.projects, "--db", self.db])
        self.assertEqual(rc, 0, err)
        self.assertIn("FROM turns", out)
        self.assertIn("$days", out)
        # No DB file was created (no connect happened).
        self.assertFalse(os.path.exists(self.db))


class TestReportsList(ReportsTestBase):
    def test_reports_lists_summary_with_description(self):
        rc, out, err = self._cli(["reports"])
        self.assertEqual(rc, 0, err)
        listing = json.loads(out)
        names = [r["name"] for r in listing]
        self.assertIn("summary", names)
        summary = [r for r in listing if r["name"] == "summary"][0]
        self.assertTrue(summary["description"])
        self.assertIn("days", summary["params"])


class TestInjectionSafety(ReportsTestBase):
    def test_drop_table_value_is_data_not_sql(self):
        _write(self.jsonl, _fixture_records())
        self._ingest()
        before = self._run_report("summary", {"days": 3650})["total_turns"]
        self.assertGreater(before, 0)

        # A malicious `days` value: it is rejected as a non-int (the param is
        # typed int) — never interpolated as SQL. Either way the table survives.
        rc, out, err = self._cli([
            "report", "summary", "--days", "1; DROP TABLE turns",
            "--source", self.projects, "--db", self.db])
        self.assertNotEqual(rc, 0)
        self.assertNotIn("Traceback", err)

        # turns still intact and queryable.
        conn = duckdb.connect(self.db)
        try:
            n = conn.execute("SELECT count(*) FROM turns").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(n, before)

    def test_injection_via_bound_text_param_is_inert(self):
        # Directly bind a hostile string to a $-placeholder text param and prove
        # DuckDB treats it as a literal, not executable SQL.
        conn = duckdb.connect(":memory:")
        try:
            conn.execute("CREATE TABLE turns (uuid TEXT)")
            conn.execute("INSERT INTO turns VALUES ('keep')")
            evil = "x'; DROP TABLE turns; --"
            rows = conn.execute(
                "SELECT count(*) FROM turns WHERE uuid = $v", {"v": evil}
            ).fetchone()
            self.assertEqual(rows[0], 0)          # no match — treated as data
            # table survived the bind.
            self.assertEqual(
                conn.execute("SELECT count(*) FROM turns").fetchone()[0], 1)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
