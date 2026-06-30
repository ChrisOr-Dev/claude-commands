-- rolling — moving average of a metric. Dispatched by `mode` in the assembler.
--
-- This is the "main query" registered in catalog.toml so that `doctor report
-- rolling --sql` prints the param block and param-validation applies. The actual
-- execution is assembled in Python (_assemble_rolling in reports.py), which
-- loads rolling_days.sql or rolling_turns.sql depending on the `mode` param.
--
-- Params:
--   metric (ident): numeric column to average. Default: total_tokens.
--   window (int):   window size (days or turns, depending on mode). Default: 20.
--   days   (int):   time range to query. Default: 7.
--   mode   (text):  'days' (per-day buckets, N-day moving avg) or
--                   'turns' (last-N-turns window over individual turns).
--
-- See rolling_days.sql / rolling_turns.sql for the actual queries.
SELECT
  strftime(ts AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%M:%S') AS ts_str,
  {metric}                                              AS metric
FROM turns
WHERE NOT is_synthetic
  AND ts IS NOT NULL
  AND ts >= now() - ($days * INTERVAL 1 DAY)
ORDER BY ts;
