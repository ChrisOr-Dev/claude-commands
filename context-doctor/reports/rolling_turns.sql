-- rolling (mode=turns) helper — last-N-turns window average of a metric.
--
-- Each row is one assistant turn ordered by timestamp; rolling_avg is the
-- average of the current turn and the preceding (window-1) turns.
--
-- `metric`  (ident, whitelisted): the numeric column to average. Default: total_tokens.
-- `window`  (int): number of turns in the rolling window (inclusive).
-- `days`    (int): how many past days of data to include.
--
-- Synthetic rows excluded — this is a billed-token view.
-- TIMESTAMPTZ never returned natively (pytz absent): ts_str is VARCHAR.
SELECT
  strftime(ts AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%M:%S') AS ts_str,
  session_id,
  {metric}                                              AS metric,
  avg({metric}) OVER (
    ORDER BY ts
    ROWS BETWEEN ($window - 1) PRECEDING AND CURRENT ROW
  )                                                     AS rolling_avg
FROM turns
WHERE NOT is_synthetic
  AND ts IS NOT NULL
  AND ts >= now() - ($days * INTERVAL 1 DAY)
ORDER BY ts;
