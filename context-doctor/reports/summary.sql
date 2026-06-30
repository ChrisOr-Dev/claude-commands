-- summary (back-compat) — global token aggregates over `turns`.
--
-- This is the report's registered "main query": it carries the $days param so
-- `doctor report summary --sql` prints it and param-validation applies. The full
-- summary JSON is post-assembled in Python (reports.py::_assemble_summary) from
-- this row PLUS a per-session helper query — the payload has nested/structured
-- output (top_expensive, period) that one flat result set can't express.
--
-- Semantics match doctor_core.build_summary EXACTLY on the same data:
--   * NO synthetic exclusion (build_summary does not exclude <synthetic> rows).
--   * total_misses = count(is_miss) — is_miss is ctx>5000 AND hit_pct<20, the
--     same ported heuristic build_summary recomputes inline.
--   * period days are the ORIGINAL UTC date strings (timestamp[:10]) — recovered
--     via `ts AT TIME ZONE 'UTC'` so the stored TIMESTAMPTZ renders back to the
--     UTC day build_summary read from the raw ISO string; NULL ts ignored.
--   * `days` window is turn-ts based (ts >= now() - $days days); on the same
--     recent data this selects the same turns as legacy file-mtime filtering.
--
-- TIMESTAMPTZ is never returned natively to Python (pytz is absent in this env):
-- the period min/max days are emitted as VARCHAR via strftime.
SELECT
  count(*)                                         AS total_turns,
  coalesce(sum(input_tokens), 0)                   AS total_input,
  coalesce(sum(output_tokens), 0)                  AS total_output,
  coalesce(sum(cache_read), 0)                     AS total_cache_read,
  coalesce(sum(cache_creation), 0)                 AS total_cache_creation,
  coalesce(sum(CASE WHEN is_miss THEN 1 ELSE 0 END), 0) AS total_misses,
  min(strftime(ts AT TIME ZONE 'UTC', '%Y-%m-%d')) AS min_day,
  max(strftime(ts AT TIME ZONE 'UTC', '%Y-%m-%d')) AS max_day
FROM turns
WHERE ts IS NULL OR ts >= now() - ($days * INTERVAL 1 DAY);
