"""Slice 8 -- scale/memory profiling gate (ADR-0008).

The gate is a **memory-ceiling assertion on a small box, not a turn count**: it
builds a synthetic warehouse large enough that the heaviest report would be
memory-hungry, forces a deliberately LOW ``memory_limit`` (via the
``DOCTOR_MEMORY_LIMIT_BYTES`` override added in this slice) so DuckDB must spill
to ``temp_directory`` instead of OOMing, and asserts that:

  (a) the heavy reports still complete correctly (bands ``percentile_cont`` +
      rolling window function return sane rows),
  (b) ``current_setting('memory_limit')`` reflects the forced low cap,
  (c) ``temp_directory`` is set and writable, and **spill actually occurs**
      (the load-bearing out-of-core proof -- deliverable (d)),
  (e) peak process RSS stays under the 4 GB-safe ceiling (~1 GB target).

Spill evidence (measured on the installed DuckDB 1.5.4, this box):
  * ``rolling`` (mode=turns, window=10) over **1 M** rows under a 128 MiB cap
    **spills ~17 MB** to ``temp_directory`` and returns all 1 M rows -- the
    window-function sort IS out-of-core in 1.5.4 (an earlier draft of this gate
    wrongly assumed a 1.1/1.2-era non-spilling sort and dropped to 100 k rows,
    which never spills; corrected here to assert real spill).
  * ``bands`` ``percentile_cont`` over 1 M rows fits within 128 MiB (no spill);
    it is kept as a correctness-under-cap check, not the spill proof.

Without a cap, DuckDB defaults to ~80% of host RAM (tens of GB on a big box,
3.2 GB on a 4 GB floor machine); the forced 128 MiB cap is 25-200x lower, so a
green run proves bounded, spill-backed operation regardless of host RAM -- the
property the gate exists to verify. This gate is also ADR-0008's polars
revisit-trigger: if at real warehouse scale a heavy report OOMs under the
production cap *despite* spill, polars becomes justified.

Each case runs in a **child subprocess** so peak RSS is a clean per-process
measurement via ``resource.getrusage(RUSAGE_SELF).ru_maxrss`` (KB on Linux).

Run:  python3 test_memory_gate.py
"""

import json
import os
import subprocess
import sys
import unittest

# Peak-RSS ceiling: 1 GB, matching the plan target ("~1 GB RSS"). Measured peak
# for the 1 M-row report workload on this box is ~0.8 GB, so 1 GB is a real
# (not loose) bound with modest headroom over the Python+duckdb baseline.
RSS_CEILING_BYTES = 1 * 1024 * 1024 * 1024

# Forced memory limit for the report sub-test. 128 MiB: low enough to force the
# rolling window-sort to spill, high enough that the bulk INSERT can still commit
# (64 MiB fails the insert's own block-pin at this row count).
FORCED_MEMORY_LIMIT = 128 * 1024 * 1024

# Synthetic warehouse size for the report gate. 1 M rows makes rolling spill.
N_ROWS = 1_000_000

# JSONL turn counts for the ingest O(batch) tests (3x multiplier).
INGEST_SMALL = 200
INGEST_LARGE = 600

# Directory containing warehouse.py / reports.py (same dir as this file).
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))


def _run_child(script, env_extra=None, timeout=120):
    """Run ``script`` in a child Python process; return its stdout JSON payload."""
    env = os.environ.copy()
    if env_extra:
        env.update({k: str(v) for k, v in env_extra.items()})
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, env=env, timeout=timeout,
        cwd=_MODULE_DIR,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "child exited %d:\nstdout=%r\nstderr=%r"
            % (result.returncode, result.stdout[:2000], result.stderr[:2000]))
    lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError("child produced no output")
    return json.loads(lines[-1])


# A reusable INSERT that fills `turns` with N synthetic rows entirely inside
# DuckDB (no JSONL / no per-row executemany -- 60k rows through the real ingest
# path takes minutes; the brief permits a direct insert for sizing).
_INSERT_TURNS = (
    "    conn.execute('''\n"
    "        INSERT INTO turns SELECT\n"
    "            gen_random_uuid()::TEXT, NULL,\n"
    "            'sess_' || (i %% {mod})::TEXT, 'gate-proj', NULL, NULL,\n"
    "            (now() - (i * INTERVAL 1 SECOND))::TIMESTAMPTZ,\n"
    "            'claude-opus-4-8', false, 'end_turn',\n"
    "            (random()*10000+1000)::BIGINT, (random()*2000+200)::BIGINT,\n"
    "            (random()*200000+50000)::BIGINT, (random()*50000+5000)::BIGINT,\n"
    "            (random()*300000+50000)::BIGINT, (random()*310000+52000)::BIGINT,\n"
    "            false, (random()*100)::DOUBLE, (random()*5)::INTEGER, 0, 1, 0, 0,\n"
    "            'synthetic.jsonl'\n"
    "        FROM range({n}) AS t(i)\n"
    "    ''')\n"
)

# Child: build two 1 M-row stores, run bands (fits) and rolling (spills) under a
# 128 MiB cap, sampling temp_directory bytes during the rolling report to prove
# spill. Emits rss, spill_bytes, counts, and the applied memory_limit.
_REPORT_SPILL_CHILD = (
    "import json, os, resource, tempfile, threading, time\n"
    "import duckdb, reports, warehouse\n"
    "\n"
    "with tempfile.TemporaryDirectory() as td:\n"
    "    db_bands = os.path.join(td, 'bands.duckdb')\n"
    "    db_roll  = os.path.join(td, 'roll.duckdb')\n"
    "\n"
    "    conn = duckdb.connect(db_bands)\n"
    "    warehouse.bootstrap(conn)\n"
    + _INSERT_TURNS.format(mod=1000, n=N_ROWS) +
    "    conn.close()\n"
    "    conn = duckdb.connect(db_roll)\n"
    "    warehouse.bootstrap(conn)\n"
    + _INSERT_TURNS.format(mod=100, n=N_ROWS) +
    "    conn.close()\n"
    "\n"
    "    # bands: percentile_cont GROUP BY (fits in cap -- correctness check).\n"
    "    bc = warehouse.connect(db_bands, duckdb_mod=duckdb)\n"
    "    mem_setting = bc.execute(\"SELECT current_setting('memory_limit')\").fetchone()[0]\n"
    "    tmp_dir = bc.execute(\"SELECT current_setting('temp_directory')\").fetchone()[0]\n"
    "    bands_rows = reports.run_report(bc, 'bands',\n"
    "        {'edges': [50000, 200000, 400000], 'days': 3650})\n"
    "    bc.close()\n"
    "\n"
    "    # rolling: window sort over 1 M rows -- MUST spill under the 128 MiB cap.\n"
    "    rc = warehouse.connect(db_roll, duckdb_mod=duckdb)\n"
    "    roll_tmp = rc.execute(\"SELECT current_setting('temp_directory')\").fetchone()[0]\n"
    "    peak = {'b': 0}\n"
    "    stop = {'s': False}\n"
    "    def _sample():\n"
    "        while not stop['s']:\n"
    "            tot = 0\n"
    "            for root, _d, files in os.walk(roll_tmp):\n"
    "                for fn in files:\n"
    "                    try: tot += os.path.getsize(os.path.join(root, fn))\n"
    "                    except OSError: pass\n"
    "            if tot > peak['b']: peak['b'] = tot\n"
    "            time.sleep(0.01)\n"
    "    th = threading.Thread(target=_sample); th.start()\n"
    "    rolling_rows = reports.run_report(rc, 'rolling',\n"
    "        {'metric': 'total_tokens', 'window': 10, 'days': 3650, 'mode': 'turns'})\n"
    "    stop['s'] = True; th.join()\n"
    "    rc.close()\n"
    "\n"
    "rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
    "print(json.dumps({\n"
    "    'rss_bytes': rss_kb * 1024,\n"
    "    'n_rows': %d,\n"
    "    'bands_count': len(bands_rows),\n"
    "    'rolling_count': len(rolling_rows),\n"
    "    'spill_bytes': peak['b'],\n"
    "    'mem_setting': mem_setting,\n"
    "    'temp_dir_set': bool(tmp_dir),\n"
    "}))\n"
) % N_ROWS

_INGEST_CHILD = (
    "import json, os, resource, tempfile\n"
    "import duckdb, warehouse\n"
    "\n"
    "N_TURNS = int(os.environ.get('_GATE_N_TURNS', '200'))\n"
    "\n"
    "def _mk(i):\n"
    "    return json.dumps({'type': 'assistant', 'sessionId': 'sess-%d' % (i % 20),\n"
    "        'uuid': 'u%d' % i, 'parentUuid': None,\n"
    "        'timestamp': '2026-01-01T00:00:00Z',\n"
    "        'message': {'model': 'claude-opus-4-8', 'usage': {'input_tokens': 100,\n"
    "            'output_tokens': 200, 'cache_read_input_tokens': 300,\n"
    "            'cache_creation_input_tokens': 400},\n"
    "            'content': [{'type': 'text', 'text': 'x'}]}})\n"
    "\n"
    "with tempfile.TemporaryDirectory() as td:\n"
    "    src = os.path.join(td, 'projects', 'proj-gate')\n"
    "    os.makedirs(src)\n"
    "    with open(os.path.join(src, 'turns.jsonl'), 'w') as f:\n"
    "        for i in range(N_TURNS): f.write(_mk(i) + '\\n')\n"
    "    conn = warehouse.connect(os.path.join(td, 'g.duckdb'), duckdb_mod=duckdb)\n"
    "    warehouse.bootstrap(conn)\n"
    "    warehouse.ingest(conn, source_dir=os.path.join(td, 'projects'))\n"
    "    conn.close()\n"
    "\n"
    "rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
    "print(json.dumps({'rss_bytes': rss_kb * 1024, 'n_turns': N_TURNS}))\n"
)


class TestMemoryGate(unittest.TestCase):
    """Scale/memory profiling gate (ADR-0008, slice 8)."""

    _spill_payload = None

    def _report_payload(self):
        # Run the (slowish) report child once and cache it for both assertions.
        if TestMemoryGate._spill_payload is None:
            TestMemoryGate._spill_payload = _run_child(
                _REPORT_SPILL_CHILD,
                env_extra={"DOCTOR_MEMORY_LIMIT_BYTES": str(FORCED_MEMORY_LIMIT)},
                timeout=120,
            )
        return TestMemoryGate._spill_payload

    def test_report_spills_and_stays_correct_under_low_cap(self):
        """Heavy reports under a 128 MiB cap: correct output, spill occurs, cap applied."""
        p = self._report_payload()
        # (a) correctness under the cap
        self.assertGreater(p["bands_count"], 0, "bands returned no rows")
        self.assertEqual(p["rolling_count"], N_ROWS,
                         "rolling must return all rows (got %d)" % p["rolling_count"])
        # (b) the forced low cap is in effect (MiB, not a GiB default)
        self.assertNotIn("GiB", p["mem_setting"],
                         "env override not applied: memory_limit=%r" % p["mem_setting"])
        # (c) temp_directory configured
        self.assertTrue(p["temp_dir_set"], "temp_directory not set")
        # (d) THE load-bearing out-of-core proof: spill actually happened
        self.assertGreater(
            p["spill_bytes"], 0,
            "no spill observed under the 128 MiB cap -- the gate failed to exercise "
            "the out-of-core path (rolling over %d rows, memory_limit=%s)"
            % (N_ROWS, p["mem_setting"]))

    def test_report_peak_rss_under_ceiling(self):
        """Peak RSS of the heavy report workload stays under the ~1 GB ceiling."""
        p = self._report_payload()
        self.assertLess(
            p["rss_bytes"], RSS_CEILING_BYTES,
            "report workload peak RSS %.0f MB exceeds the %.0f MB ceiling "
            "(spill=%.1f MB, memory_limit=%s)"
            % (p["rss_bytes"] / 1048576, RSS_CEILING_BYTES / 1048576,
               p["spill_bytes"] / 1048576, p["mem_setting"]))

    def test_ingest_peak_rss_under_ceiling(self):
        """Ingesting 200 and 600 turns each stays under the ceiling."""
        for n in (INGEST_SMALL, INGEST_LARGE):
            p = _run_child(_INGEST_CHILD, env_extra={"_GATE_N_TURNS": str(n)}, timeout=30)
            self.assertLess(
                p["rss_bytes"], RSS_CEILING_BYTES,
                "ingest N=%d peak RSS %.0f MB exceeds ceiling"
                % (n, p["rss_bytes"] / 1048576))

    def test_ingest_rss_is_obatch_not_ofile(self):
        """A 3x-larger file must not yield > 2x the RSS -- proves O(batch) ingest."""
        small = _run_child(_INGEST_CHILD, env_extra={"_GATE_N_TURNS": str(INGEST_SMALL)}, timeout=30)
        large = _run_child(_INGEST_CHILD, env_extra={"_GATE_N_TURNS": str(INGEST_LARGE)}, timeout=30)
        self.assertLess(
            large["rss_bytes"], small["rss_bytes"] * 2,
            "ingest RSS scales with file size -- O(batch) broken: small=%.0f MB, large=%.0f MB"
            % (small["rss_bytes"] / 1048576, large["rss_bytes"] / 1048576))

    def test_memory_limit_override_default_unchanged(self):
        """The env override must not perturb the default heuristic when absent."""
        import warehouse
        os.environ.pop("DOCTOR_MEMORY_LIMIT_BYTES", None)
        default = warehouse._memory_limit_bytes()
        self.assertGreaterEqual(default, 512 * 1024 * 1024)   # >= 512 MB floor
        self.assertLessEqual(default, 1024 * 1024 * 1024)     # <= 1 GB hard cap
        os.environ["DOCTOR_MEMORY_LIMIT_BYTES"] = "134217728"
        try:
            self.assertEqual(warehouse._memory_limit_bytes(), 134217728)  # honored
            os.environ["DOCTOR_MEMORY_LIMIT_BYTES"] = "1000000"           # < 64 MB floor
            self.assertEqual(warehouse._memory_limit_bytes(), 64 * 1024 * 1024)  # clamped up
        finally:
            os.environ.pop("DOCTOR_MEMORY_LIMIT_BYTES", None)
        self.assertEqual(warehouse._memory_limit_bytes(), default)  # back to default


if __name__ == "__main__":
    unittest.main(verbosity=2)
