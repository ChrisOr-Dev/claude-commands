"""Tests for the ``doctor`` CLI duckdb degrade gate (slice 0).

Run: python3 context-doctor/test_doctor_gate.py
 or: python3 -m unittest context-doctor/test_doctor_gate.py

Covers the contract that warehouse subcommands (ingest/report/reports/schema)
must, when the ``duckdb`` module cannot be imported, print a one-line install
hint to stderr and exit non-zero — never silently — and succeed past the gate
when duckdb is present.
"""

import io
import os
import unittest
from contextlib import redirect_stderr

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
    """With duckdb present the gate is cleared; the stub then reports
    'not yet implemented' and exits non-zero WITHOUT the install hint."""

    def _run(self, argv):
        err = io.StringIO()
        os.environ.pop("DOCTOR_FORCE_NO_DUCKDB", None)
        try:
            with redirect_stderr(err):
                code = doctor.main(argv)
        except SystemExit as exc:
            code = exc.code
        return code, err.getvalue()

    def test_ingest_passes_gate_then_stub(self):
        code, err = self._run(["ingest"])
        self.assertNotEqual(code, 0)               # stub still exits non-zero
        self.assertIn("not yet implemented", err)  # got past the gate
        self.assertNotIn("install", err.lower())   # no install hint emitted


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
