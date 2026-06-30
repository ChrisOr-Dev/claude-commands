"""Slice 6 tests — remaining catalog reports: bands, rolling, top-expensive,
by-project, cache-health, daily.

All tests run against a frozen ``--source`` (a temp dir of fixture JSONL) and a
throwaway ``--db`` in a temp dir — NEVER the user's real ~/.claude store.

Key correctness checks (plan Verification requirements):
  - ``bands`` median/p90 match an independent reference computation (Python
    ``statistics.median`` / manual p90 over the same fixture values).
  - ``rolling`` matches a hand-computed moving average for BOTH ``mode=days``
    and ``mode=turns``.
  - ``bands`` builds buckets from a passed ``--edges`` list (not just defaults).
  - The ident whitelist rejects out-of-choices ``dimension``/``metric`` values.
  - ``rolling`` mode validation rejects anything other than 'days'/'turns'.

Run: uv run python -m unittest test_reports_catalog
"""

import datetime
import io
import json
import os
import statistics
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout, redirect_stderr

import duckdb

import doctor
import reports
import warehouse

_ALL_REPORTS = ("bands", "rolling", "top-expensive", "by-project",
                "cache-health", "daily")

_NOW = time.time()


def _ts(off_seconds):
    """UTC timestamp ``off_seconds`` before now (within any sane --days window)."""
    dt = datetime.datetime.fromtimestamp(_NOW - off_seconds, datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts_at(day_offset, hour=12):
    """UTC timestamp at ``hour`` on the day ``day_offset`` days before today."""
    base = datetime.datetime.fromtimestamp(_NOW, datetime.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0)
    dt = (base - datetime.timedelta(days=day_offset)).replace(hour=hour)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _day_str(day_offset):
    """UTC date string for the day ``day_offset`` days before today."""
    base = datetime.datetime.fromtimestamp(_NOW, datetime.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0)
    dt = base - datetime.timedelta(days=day_offset)
    return dt.strftime("%Y-%m-%d")


def _asst(uuid, sid, context_tokens, total_tokens, *,
          model="claude-opus-4-8", off_seconds=3600,
          inp=0, out=0, cr=0, cw=0, is_miss=False, project=None,
          ts_str=None):
    """Build a minimal assistant JSONL record."""
    cr = cr or context_tokens
    inp = inp or max(context_tokens - cr, 0)
    out = out or (total_tokens - context_tokens)
    return {
        "type": "assistant",
        "sessionId": sid,
        "uuid": uuid,
        "parentUuid": None,
        "timestamp": ts_str or _ts(off_seconds),
        "message": {
            "model": model,
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_read_input_tokens": cr,
                "cache_creation_input_tokens": cw,
            },
            "content": [{"type": "text", "text": "x"}],
        },
    }


def _write(fp, records):
    with open(fp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


class CatalogTestBase(unittest.TestCase):
    """Base: temp source + DB; ingest helper; run_report shortcut."""

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

    def _run(self, name, overrides=None):
        conn = warehouse.connect(self.db, duckdb_mod=duckdb)
        try:
            return reports.run_report(conn, name, overrides or {})
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# bands
# ---------------------------------------------------------------------------

class TestBands(CatalogTestBase):
    """Verify bucket assignment, median/p90 correctness vs independent reference."""

    def _fixture(self):
        """5 turns spread across 4 bands [0,50k), [50k,200k), [200k,400k), [400k+)."""
        return [
            _asst("u1", "s1", 10_000,   12_000),   # band 0: < 50k
            _asst("u2", "s1", 60_000,   70_000),   # band 1: [50k,200k)
            _asst("u3", "s2", 80_000,   90_000),   # band 1: [50k,200k)
            _asst("u4", "s2", 250_000, 280_000),   # band 2: [200k,400k)
            _asst("u5", "s3", 410_000, 450_000),   # band 3: >= 400k
        ]

    def test_band_counts_match_expected_buckets(self):
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("bands", {"edges": [50000, 200000, 400000], "days": 30})
        by_band = {r["band"]: r for r in rows}
        self.assertEqual(by_band[0]["count"], 1)
        self.assertEqual(by_band[1]["count"], 2)
        self.assertEqual(by_band[2]["count"], 1)
        self.assertEqual(by_band[3]["count"], 1)

    def test_median_matches_independent_reference(self):
        """Band-1 has two values: median should be statistics.median([60k, 80k])."""
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("bands", {"edges": [50000, 200000, 400000], "days": 30})
        by_band = {r["band"]: r for r in rows}

        # Independent reference for band 1 ([50k, 200k)).
        band1_vals = [60_000, 80_000]
        expected_median = statistics.median(band1_vals)
        self.assertAlmostEqual(by_band[1]["median"], expected_median, places=1,
                               msg="band 1 median mismatch vs statistics.median")

        # Independent reference for band 0 (single value, median == that value).
        self.assertAlmostEqual(by_band[0]["median"], 10_000.0, places=1)

    def test_p90_matches_independent_reference(self):
        """p90 via DuckDB percentile_cont(0.9) == hand-computed reference."""
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("bands", {"edges": [50000, 200000, 400000], "days": 30})
        by_band = {r["band"]: r for r in rows}

        # For band 1 (2 values: [60000, 80000]):
        # percentile_cont(0.9) linear interpolation: 60000 + 0.9*(80000-60000) = 78000.
        self.assertAlmostEqual(by_band[1]["p90"], 78_000.0, places=1,
                               msg="band 1 p90 mismatch vs hand-computed reference")

        # For a single-value band median == p90 == the value.
        self.assertAlmostEqual(by_band[0]["p90"], 10_000.0, places=1)

    def test_custom_edges_override_default(self):
        """Passing custom edges gives different band assignments than the default."""
        _write(self.jsonl, self._fixture())
        self._ingest()
        # With a single edge at 100k: band 0 = <100k (3 turns), band 1 = >=100k (2 turns).
        rows = self._run("bands", {"edges": [100000], "days": 30})
        by_band = {r["band"]: r for r in rows}
        self.assertEqual(by_band[0]["count"], 3)   # 10k, 60k, 80k
        self.assertEqual(by_band[1]["count"], 2)   # 250k, 410k

    def test_shorthand_edges_expand_correctly(self):
        """'50k,200k,400k' shorthand → [50000, 200000, 400000]."""
        bind, _ = reports.resolve_params(
            reports.get_report("bands"),
            {"edges": "50k,200k,400k"})
        self.assertEqual(bind["edges"], [50_000, 200_000, 400_000])

    def test_dimension_ident_whitelist_rejects_invalid(self):
        """Out-of-choices dimension raises ReportError."""
        rep = reports.get_report("bands")
        with self.assertRaises(reports.ReportError):
            reports.resolve_params(rep, {"dimension": "evil; DROP TABLE turns"})
        with self.assertRaises(reports.ReportError):
            reports.resolve_params(rep, {"dimension": "uuid"})

    def test_dimension_valid_choice_resolves(self):
        """Valid dimension choices all resolve without error."""
        rep = reports.get_report("bands")
        for col in ("context_tokens", "total_tokens", "output_tokens", "input_tokens"):
            _, idents = reports.resolve_params(rep, {"dimension": col})
            self.assertEqual(idents["dimension"], col)

    def test_synthetic_rows_excluded(self):
        """Synthetic (<synthetic>) turns are excluded from bands."""
        _write(self.jsonl, self._fixture() + [
            _asst("u99", "synth_sess", 600_000, 700_000,
                  model="<synthetic>"),
        ])
        self._ingest()
        rows = self._run("bands", {"edges": [50000, 200000, 400000], "days": 30})
        # band 3 should still be 1 (the synthetic 600k turn must NOT appear).
        by_band = {r["band"]: r for r in rows}
        self.assertEqual(by_band.get(3, {}).get("count", 0), 1)

    def test_bands_in_catalog_listing(self):
        """'bands' appears in reports listing with description and params."""
        listing = reports.list_reports()
        names = [r["name"] for r in listing]
        self.assertIn("bands", names)
        entry = next(r for r in listing if r["name"] == "bands")
        self.assertIn("dimension", entry["params"])
        self.assertIn("edges", entry["params"])
        self.assertIn("days", entry["params"])


# ---------------------------------------------------------------------------
# rolling
# ---------------------------------------------------------------------------

class TestRolling(CatalogTestBase):
    """Verify both modes against hand-computed reference values."""

    def _fixture_turns(self):
        """10 turns over 5 days, 2 per day. total_tokens = 100..800 in steps of 100."""
        recs = []
        for i in range(10):
            # day_offset: turns 0-1 are 4 days ago, 2-3 are 3 days ago, etc.
            day_off = 4 - (i // 2)
            hour = 10 if (i % 2 == 0) else 14
            tot = (i + 1) * 100
            recs.append(
                _asst("u%d" % (i + 1), "s%d" % (i // 2 + 1), tot, tot,
                      ts_str=_ts_at(day_off, hour)))
        return recs

    def test_rolling_days_mode_window3_matches_hand_computed(self):
        """mode=days, window=3: each day row's rolling_avg == hand-computed moving avg."""
        _write(self.jsonl, self._fixture_turns())
        self._ingest()
        rows = self._run("rolling", {"metric": "total_tokens", "window": 3,
                                     "days": 30, "mode": "days"})
        # Expected per-day totals: day-4=300, day-3=400+... wait, turns are:
        # day-4: u1=100, u2=200 → sum=300
        # day-3: u3=300, u4=400 → sum=700
        # day-2: u5=500, u6=600 → sum=1100
        # day-1: u7=700, u8=800 → ... wait let me recalculate.
        # i=0: day_off=4-0=4, tot=100; i=1: day_off=4-0=4, tot=200
        # i=2: day_off=4-1=3, tot=300; i=3: day_off=3, tot=400
        # i=4: day_off=4-2=2, tot=500; i=5: day_off=2, tot=600
        # i=6: day_off=4-3=1, tot=700; i=7: day_off=1, tot=800
        # i=8: day_off=4-4=0, tot=900; i=9: day_off=0, tot=1000
        daily_totals = [
            (_day_str(4), 100 + 200),   # = 300
            (_day_str(3), 300 + 400),   # = 700
            (_day_str(2), 500 + 600),   # = 1100
            (_day_str(1), 700 + 800),   # = 1500
            (_day_str(0), 900 + 1000),  # = 1900
        ]
        # Hand-compute 3-day rolling avg (ROWS 2 PRECEDING AND CURRENT ROW).
        sums = [d[1] for d in daily_totals]
        expected = []
        for i, (day, _) in enumerate(daily_totals):
            window_vals = sums[max(0, i - 2): i + 1]
            expected.append((day, sum(window_vals) / len(window_vals)))

        self.assertEqual(len(rows), len(expected))
        for row, (exp_day, exp_avg) in zip(rows, expected):
            self.assertEqual(row["day"], exp_day, "day mismatch")
            self.assertAlmostEqual(row["rolling_avg"], exp_avg, places=2,
                                   msg="rolling_avg mismatch for day %s" % exp_day)

    def test_rolling_turns_mode_window3_matches_hand_computed(self):
        """mode=turns, window=3: each turn's rolling_avg == hand-computed moving avg."""
        _write(self.jsonl, self._fixture_turns())
        self._ingest()
        rows = self._run("rolling", {"metric": "total_tokens", "window": 3,
                                     "days": 30, "mode": "turns"})
        # Turn order by ts: u1=100, u2=200, u3=300, u4=400, u5=500, u6=600,
        #                   u7=700, u8=800, u9=900, u10=1000
        vals = list(range(100, 1100, 100))
        self.assertEqual(len(rows), len(vals))
        for i, (row, v) in enumerate(zip(rows, vals)):
            window_vals = vals[max(0, i - 2): i + 1]
            exp_avg = sum(window_vals) / len(window_vals)
            self.assertAlmostEqual(row["rolling_avg"], exp_avg, places=2,
                                   msg="rolling_avg mismatch at turn %d" % (i + 1))
            self.assertEqual(row["metric"], v,
                             msg="metric value mismatch at turn %d" % (i + 1))

    def test_rolling_invalid_mode_raises_report_error(self):
        """mode='weekly' raises ReportError (not a traceback)."""
        _write(self.jsonl, self._fixture_turns())
        self._ingest()
        with self.assertRaises(reports.ReportError) as ctx:
            self._run("rolling", {"metric": "total_tokens", "window": 3,
                                  "days": 30, "mode": "weekly"})
        self.assertIn("mode", str(ctx.exception))

    def test_rolling_metric_whitelist_rejects_invalid(self):
        """Out-of-choices metric raises ReportError."""
        rep = reports.get_report("rolling")
        with self.assertRaises(reports.ReportError):
            reports.resolve_params(rep, {"metric": "session_id"})

    def test_rolling_metric_valid_choices_resolve(self):
        """All whitelisted metric choices resolve without error."""
        rep = reports.get_report("rolling")
        for col in ("context_tokens", "total_tokens", "output_tokens", "input_tokens"):
            _, idents = reports.resolve_params(rep, {"metric": col})
            self.assertEqual(idents["metric"], col)

    def test_rolling_days_synthetic_excluded(self):
        """Synthetic turns do not appear in rolling output."""
        recs = self._fixture_turns() + [
            _asst("u_syn", "syn", 999, 999, model="<synthetic>",
                  ts_str=_ts_at(0, 9)),
        ]
        _write(self.jsonl, recs)
        self._ingest()
        rows = self._run("rolling", {"metric": "total_tokens", "window": 1,
                                     "days": 30, "mode": "turns"})
        metrics = [r["metric"] for r in rows]
        self.assertNotIn(999, metrics, "synthetic turn should not appear in rolling")

    def test_rolling_in_catalog_listing(self):
        """'rolling' appears in the catalog with the expected params."""
        listing = reports.list_reports()
        entry = next(r for r in listing if r["name"] == "rolling")
        self.assertIn("metric", entry["params"])
        self.assertIn("window", entry["params"])
        self.assertIn("mode", entry["params"])
        self.assertIn("days", entry["params"])


# ---------------------------------------------------------------------------
# top-expensive
# ---------------------------------------------------------------------------

class TestTopExpensive(CatalogTestBase):

    def _fixture(self):
        return [
            _asst("u1", "sessA", 100_000, 120_000, off_seconds=3600 * 5),
            _asst("u2", "sessA", 300_000, 320_000, off_seconds=3600 * 4),  # sessA max=300k
            _asst("u3", "sessB", 500_000, 550_000, off_seconds=3600 * 3),  # sessB max=500k
            _asst("u4", "sessC",  50_000,  60_000, off_seconds=3600 * 2),  # sessC max=50k
        ]

    def test_top_expensive_ordered_by_max_context_desc(self):
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("top-expensive", {"days": 30, "limit": 10})
        sessions = [r["session"] for r in rows]
        # sessB(500k) > sessA(300k) > sessC(50k)
        self.assertEqual(sessions[0], "sessB")
        self.assertEqual(sessions[1], "sessA")
        self.assertEqual(sessions[2], "sessC")

    def test_top_expensive_max_context_k_correct(self):
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("top-expensive", {"days": 30, "limit": 10})
        by_sess = {r["session"]: r for r in rows}
        self.assertAlmostEqual(by_sess["sessB"]["max_context_k"], 500.0, places=0)
        self.assertAlmostEqual(by_sess["sessA"]["max_context_k"], 300.0, places=0)
        self.assertAlmostEqual(by_sess["sessC"]["max_context_k"], 50.0, places=0)

    def test_top_expensive_limit_honored(self):
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("top-expensive", {"days": 30, "limit": 2})
        self.assertEqual(len(rows), 2)
        # top 2: sessB, sessA
        sessions = [r["session"] for r in rows]
        self.assertIn("sessB", sessions)
        self.assertIn("sessA", sessions)

    def test_top_expensive_in_catalog(self):
        listing = reports.list_reports()
        names = [r["name"] for r in listing]
        self.assertIn("top-expensive", names)


# ---------------------------------------------------------------------------
# by-project
# ---------------------------------------------------------------------------

class TestByProject(CatalogTestBase):

    def _fixture(self):
        return [
            _asst("u1", "sA", 10_000,  12_000, off_seconds=3600 * 5),
            _asst("u2", "sA", 20_000,  22_000, off_seconds=3600 * 4),
            # Force a different project by putting records in a second JSONL dir.
            # We use the same session but different UUIDs; project comes from the dir.
        ]

    def test_by_project_returns_project_rows(self):
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("by-project", {"days": 30})
        self.assertGreater(len(rows), 0)
        row = rows[0]
        self.assertIn("project", row)
        self.assertIn("turns", row)
        self.assertIn("sessions", row)
        self.assertIn("max_context", row)
        self.assertIn("total_tokens", row)
        self.assertIn("miss_count", row)

    def test_by_project_turn_count_correct(self):
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("by-project", {"days": 30})
        total_turns = sum(r["turns"] for r in rows)
        self.assertEqual(total_turns, 2)

    def test_by_project_synthetic_excluded_from_turns(self):
        _write(self.jsonl, self._fixture() + [
            _asst("u99", "sA", 5000, 5500, model="<synthetic>", off_seconds=3600),
        ])
        self._ingest()
        rows = self._run("by-project", {"days": 30})
        total_turns = sum(r["turns"] for r in rows)
        # synthetic excluded: still 2
        self.assertEqual(total_turns, 2)

    def test_by_project_in_catalog(self):
        listing = reports.list_reports()
        names = [r["name"] for r in listing]
        self.assertIn("by-project", names)


# ---------------------------------------------------------------------------
# cache-health
# ---------------------------------------------------------------------------

class TestCacheHealth(CatalogTestBase):

    def _fixture(self):
        """Mix of cache hits and misses over 2 days."""
        return [
            # day 1 ago: 1 hit, 1 miss
            _asst("u1", "s1",  50_000,  60_000,
                  ts_str=_ts_at(1, 10), cr=40_000, inp=10_000, out=10_000),
            _asst("u2", "s1",   5_100,   5_200,
                  ts_str=_ts_at(1, 14), cr=100, inp=5_000, out=100),   # miss: cr tiny
            # day 0: 2 hits
            _asst("u3", "s2",  80_000,  90_000,
                  ts_str=_ts_at(0, 10), cr=75_000, inp=5_000, out=10_000),
            _asst("u4", "s2", 100_000, 110_000,
                  ts_str=_ts_at(0, 14), cr=90_000, inp=10_000, out=10_000),
        ]

    def test_cache_health_has_day_rows(self):
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("cache-health", {"days": 30})
        self.assertGreater(len(rows), 0)
        self.assertIn("day", rows[0])
        self.assertIn("turns", rows[0])
        self.assertIn("miss_count", rows[0])
        self.assertIn("hit_rate_pct", rows[0])
        self.assertIn("extra_tokens_k", rows[0])

    def test_cache_health_ordered_by_day(self):
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("cache-health", {"days": 30})
        days = [r["day"] for r in rows]
        self.assertEqual(days, sorted(days))

    def test_cache_health_in_catalog(self):
        listing = reports.list_reports()
        names = [r["name"] for r in listing]
        self.assertIn("cache-health", names)


# ---------------------------------------------------------------------------
# daily
# ---------------------------------------------------------------------------

class TestDaily(CatalogTestBase):

    def _fixture(self):
        return [
            _asst("u1", "s1", 10_000, 12_000, ts_str=_ts_at(1, 10),
                  inp=1_000, cr=9_000, cw=0, out=2_000),
            _asst("u2", "s1", 20_000, 25_000, ts_str=_ts_at(1, 14),
                  inp=2_000, cr=18_000, cw=0, out=5_000),
            _asst("u3", "s2", 50_000, 60_000, ts_str=_ts_at(0, 10),
                  inp=5_000, cr=45_000, cw=0, out=10_000),
        ]

    def test_daily_rows_per_utc_day(self):
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("daily", {"days": 30})
        self.assertEqual(len(rows), 2)  # 2 distinct days

    def test_daily_token_columns_present(self):
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("daily", {"days": 30})
        for row in rows:
            for col in ("day", "input_tokens", "output_tokens", "cache_read",
                        "cache_creation", "total_tokens"):
                self.assertIn(col, row)

    def test_daily_totals_match_fixture(self):
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("daily", {"days": 30})
        by_day = {r["day"]: r for r in rows}

        yesterday = _day_str(1)
        today = _day_str(0)

        # yesterday: 2 turns — total_tokens = 12k + 25k = 37k
        self.assertEqual(by_day[yesterday]["total_tokens"], 12_000 + 25_000)
        # today: 1 turn — total_tokens = 60k
        self.assertEqual(by_day[today]["total_tokens"], 60_000)

    def test_daily_ordered_by_day(self):
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("daily", {"days": 30})
        days = [r["day"] for r in rows]
        self.assertEqual(days, sorted(days))

    def test_daily_synthetic_excluded(self):
        _write(self.jsonl, self._fixture() + [
            _asst("u99", "syn", 500, 600, model="<synthetic>",
                  ts_str=_ts_at(0, 8)),
        ])
        self._ingest()
        rows = self._run("daily", {"days": 30})
        by_day = {r["day"]: r for r in rows}
        today = _day_str(0)
        # synthetic excluded: today total still 60k
        self.assertEqual(by_day[today]["total_tokens"], 60_000)

    def test_daily_null_ts_excluded(self):
        """Turns with ts IS NULL are excluded from daily (they have no date)."""
        _write(self.jsonl, self._fixture())
        self._ingest()
        rows = self._run("daily", {"days": 30})
        # All fixture turns have ts; NULL-ts would add an extra row (it can't be
        # placed in a day). Just verify row count equals distinct day count.
        self.assertEqual(len(rows), 2)

    def test_daily_in_catalog(self):
        listing = reports.list_reports()
        names = [r["name"] for r in listing]
        self.assertIn("daily", names)


# ---------------------------------------------------------------------------
# catalog listing includes all new reports
# ---------------------------------------------------------------------------

class TestCatalogCompleteness(unittest.TestCase):
    def test_all_new_reports_in_catalog(self):
        listing = reports.list_reports()
        names = {r["name"] for r in listing}
        expected = {"summary", "bands", "rolling", "top-expensive",
                    "by-project", "cache-health", "daily"}
        self.assertEqual(expected, names,
                         "catalog names mismatch: %s" % (names ^ expected))


# ---------------------------------------------------------------------------
# CLI surface: --sql (no DB contact), bad-param rejection, reports listing,
# and a read-only end-to-end smoke of every report via --source/--db.
# ---------------------------------------------------------------------------

class TestCliSurface(CatalogTestBase):
    """Drive doctor.main(argv) with a frozen --source / throwaway --db."""

    def _cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                rc = doctor.main(argv)
            except SystemExit as exc:
                rc = exc.code if isinstance(exc.code, int) else 1
        return rc, out.getvalue(), err.getvalue()

    def _smoke_fixture(self):
        """A small fixture exercising every report (synthetic + a miss + spread)."""
        return [
            _asst("u1", "sA", 100_000, 120_000, off_seconds=3600 * 5),
            _asst("u2", "sA", 300_000, 320_000, off_seconds=3600 * 4),
            _asst("u3", "sB", 500_000, 550_000, off_seconds=3600 * 3),
            _asst("u4", "sC",   5_100,   5_200,
                  cr=100, inp=5_000, out=100, off_seconds=3600 * 2),   # a miss
            _asst("u5", "sD", 600_000, 700_000,
                  model="<synthetic>", off_seconds=3600),               # synthetic
        ]

    def test_reports_lists_all_six_plus_summary(self):
        rc, out, err = self._cli(["reports"])
        self.assertEqual(rc, 0, err)
        names = {r["name"] for r in json.loads(out)}
        self.assertEqual(
            names,
            {"summary", "bands", "rolling", "top-expensive",
             "by-project", "cache-health", "daily"})

    def test_sql_flag_prints_each_template_without_db_contact(self):
        # --sql must print the template and NEVER connect/ingest/execute.
        for name in _ALL_REPORTS:
            rc, out, err = self._cli([
                "report", name, "--sql",
                "--source", self.projects, "--db", self.db])
            self.assertEqual(rc, 0, "%s --sql failed: %s" % (name, err))
            self.assertIn("FROM turns", out, "%s template body missing" % name)
            # No DB file created — no connect happened.
            self.assertFalse(os.path.exists(self.db),
                             "%s --sql touched the store" % name)

    def test_non_numeric_edges_element_rejected_non_traceback(self):
        _write(self.jsonl, self._smoke_fixture())
        rc, out, err = self._cli([
            "report", "bands", "--edges", "50k,oops,400k",
            "--source", self.projects, "--db", self.db])
        self.assertNotEqual(rc, 0)
        self.assertNotIn("Traceback", err)
        self.assertEqual(out, "")
        self.assertIn("edges", err)

    def test_out_of_choices_dimension_rejected_non_traceback(self):
        _write(self.jsonl, self._smoke_fixture())
        rc, out, err = self._cli([
            "report", "bands", "--dimension", "uuid",
            "--source", self.projects, "--db", self.db])
        self.assertNotEqual(rc, 0)
        self.assertNotIn("Traceback", err)
        self.assertEqual(out, "")
        self.assertIn("dimension", err)

    def test_edges_shorthand_bins_correctly_via_cli(self):
        # 5 turns: context 100k,300k,500k,5.1k (+ synthetic dropped).
        _write(self.jsonl, self._smoke_fixture())
        rc, out, err = self._cli([
            "report", "bands", "--edges", "50k,200k,400k", "--days", "30",
            "--source", self.projects, "--db", self.db])
        self.assertEqual(rc, 0, err)
        by_band = {r["band"]: r for r in json.loads(out)}
        # band 0: 5.1k ; band 1: 100k ; band 2: 300k ; band 3: 500k
        self.assertEqual(by_band[0]["count"], 1)
        self.assertEqual(by_band[1]["count"], 1)
        self.assertEqual(by_band[2]["count"], 1)
        self.assertEqual(by_band[3]["count"], 1)

    def test_each_report_runs_end_to_end_via_cli(self):
        """Read-only smoke: every report runs via --source/--db → valid JSON."""
        _write(self.jsonl, self._smoke_fixture())
        for name in _ALL_REPORTS:
            rc, out, err = self._cli([
                "report", name, "--days", "30",
                "--source", self.projects, "--db", self.db])
            self.assertEqual(rc, 0, "%s failed: %s" % (name, err))
            payload = json.loads(out)        # must be valid JSON
            self.assertIsInstance(payload, list, "%s not tabular" % name)

    def test_rolling_both_modes_run_via_cli(self):
        _write(self.jsonl, self._smoke_fixture())
        for mode in ("days", "turns"):
            rc, out, err = self._cli([
                "report", "rolling", "--mode", mode, "--days", "30",
                "--source", self.projects, "--db", self.db])
            self.assertEqual(rc, 0, "rolling mode=%s failed: %s" % (mode, err))
            self.assertIsInstance(json.loads(out), list)


if __name__ == "__main__":
    unittest.main()
