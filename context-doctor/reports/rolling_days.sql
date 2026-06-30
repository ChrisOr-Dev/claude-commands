-- rolling (mode=days) helper — N-day moving average of a metric.
--
-- Bucketed by UTC day first (sum per day), then a window-function moving average
-- over the last `window` days (inclusive). This is the Grafana-style time-series
-- view: each row is one calendar day and its N-day rolling average.
--
-- `metric`  (ident, whitelisted): the numeric column to average. Default: total_tokens.
-- `window`  (int): number of preceding days (inclusive) in the moving window.
-- `days`    (int): how many past days of data to return rows for.
--
-- Synthetic rows excluded — this is a billed-token view.
-- TIMESTAMPTZ never returned natively (pytz absent): day is VARCHAR.
WITH daily AS (
  SELECT
    strftime(ts AT TIME ZONE 'UTC', '%Y-%m-%d') AS day,
    sum({metric})                                AS day_total
  FROM turns
  WHERE NOT is_synthetic
    AND ts IS NOT NULL
    AND ts >= now() - ($days * INTERVAL 1 DAY)
  GROUP BY day
)
SELECT
  day,
  day_total,
  avg(day_total) OVER (
    ORDER BY day
    ROWS BETWEEN ($window - 1) PRECEDING AND CURRENT ROW
  ) AS rolling_avg
FROM daily
ORDER BY day;
