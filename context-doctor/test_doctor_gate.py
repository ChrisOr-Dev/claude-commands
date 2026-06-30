"""Tests for the ``doctor`` CLI duckdb degrade gate (slice 0).

Run: python3 context-doctor/test_doctor_gate.py
 or: python3 -m unittest context-doctor/test_doctor_gate.py

Covers the contract that warehouse subcommands (ingest/report/reports/schema)
must, when the ``duckdb`` module cannot be imported, print a one-line install
hint to stderr and exit non-zero — never silently — and succeed past the gate
when duckdb is present.
"""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import doctor


class TestRequireDuckDB(unittest.TestCase):
    def test_present_returns_module(self):
        # duckdb is installed in this env; require_duckdb returns the module.
        os.environ.pop("DOCTOR_FORCE_NO_DUCKDB", None)
        mod = doctor.require_duckdb()
        self.assertTrue(hasattr(mod, "connect"))

    def test_forced_absent_raises(self):
        os.environ["DOCTOR_FORCE_NO_DUCKDB"] = "1"
        try:
            with self.assertRaises(doctor.DuckDBUnavailable):
                doctor.require_duckdb()
        finally:
            os.environ.pop("DOCTOR_FORCE_NO_DUCKDB", None)


class TestGateExitsNonZero(unittest.TestCase):
    """When duckdb is forced absent, every warehouse subcommand must:
    exit non-zero AND emit the install hint to stderr."""

    def _run(self, argv):
        err = io.StringIO()
        os.environ["DOCTOR_FORCE_NO_DUCKDB"] = "1"
        try:
            with redirect_stderr(err):
                code = doctor.main(argv)
        except SystemExit as exc:
            code = exc.code
        finally:
            os.environ.pop("DOCTOR_FORCE_NO_DUCKDB", None)
        return code, err.getvalue()

    def test_ingest_degrades(self):
        code, err = self._run(["ingest"])
        self.assertNotEqual(code, 0)
        self.assertIn("duckdb", err)

    def test_report_degrades(self):
        code, err = self._run(["report", "summary"])
        self.assertNotEqual(code, 0)
        self.assertIn("duckdb", err)

    def test_reports_degrades(self):
        code, err = self._run(["reports"])
        self.assertNotEqual(code, 0)
        self.assertIn("duckdb", err)

    def test_schema_degrades(self):
        code, err = self._run(["schema"])
        self.assertNotEqual(code, 0)
        self.assertIn("duckdb", err)


class TestGatePassesWhenPresent(unittest.TestCase):
    """With duckdb present the gate is cleared and the real subcommand runs.

    Slice 5 wired ``report`` and ``reports`` for real, so we use isolated
    ``--source``/``--db`` overrides (temp dirs) to exercise gate-pass without
    touching the live per-user store.  The test verifies that, when duckdb is
    available, the command exits without the install hint and produces output."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = self._tmp.name
        self.source = os.path.join(root, "projects")
        os.makedirs(self.source)
        self.db = os.path.join(root, "test.duckdb")

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        os.environ.pop("DOCTOR_FORCE_NO_DUCKDB", None)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = doctor.main(argv)
        except SystemExit as exc:
            code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_report_passes_gate_and_runs(self):
        """doctor report summary (with overrides) exits 0 and returns JSON."""
        code, out, err = self._run([
            "report", "summary",
            "--source", self.source, "--db", self.db,
        ])
        self.assertEqual(code, 0, "expected exit 0; stderr=%r" % err)
        # No install hint (gate was cleared).
        self.assertNotIn("install", err.lower())
        # Output is valid JSON with the summary keys.
        payload = json.loads(out)
        self.assertIn("total_turns", payload)

    def test_reports_passes_gate_and_lists_catalog(self):
        """doctor reports exits 0 and includes 'summary' in the listing."""
        code, out, err = self._run([
            "reports",
            "--source", self.source, "--db", self.db,
        ])
        self.assertEqual(code, 0, err)
        self.assertNotIn("install", err.lower())
        listing = json.loads(out)
        self.assertIn("summary", [r["name"] for r in listing])


class TestParserSkeleton(unittest.TestCase):
    def test_subcommands_recognized(self):
        parser = doctor.build_parser()
        for cmd in ("ingest", "report", "reports", "schema"):
            args = parser.parse_args([cmd] if cmd != "report" else [cmd, "summary"])
            self.assertEqual(args.command, cmd)

    def test_global_overrides_present(self):
        parser = doctor.build_parser()
        args = parser.parse_args(["ingest", "--source", "/x", "--db", "/y.duckdb"])
        self.assertEqual(args.source, "/x")
        self.assertEqual(args.db, "/y.duckdb")

    def test_no_command_returns_usage_code(self):
        self.assertEqual(doctor.main([]), 2)


if __name__ == "__main__":
    unittest.main()
