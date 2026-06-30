-- cache-health — per-day cache hit rate, miss count, and extra-token cost.
--
-- `days` (int): rolling time window. Default: 7.
--
-- `hit_rate_pct` = cache_read / context_tokens * 100 averaged over non-NULL
-- context_tokens rows (NULL context_tokens means context==0 → excluded).
-- `extra_tokens_k` approximates the penalty from misses: each miss re-sends
-- ~90% of the average context window from that day.
--
-- Synthetic rows excluded (billed-token view).
-- TIMESTAMPTZ never returned natively (pytz absent): day is VARCHAR.
WITH daily AS (
  SELECT
    strftime(ts AT TIME ZONE 'UTC', '%Y-%m-%d') AS day,
    count(*)                                     AS turns,
    count(*) FILTER (WHERE is_miss)              AS miss_count,
    avg(hit_pct) FILTER (WHERE hit_pct IS NOT NULL) AS hit_rate_pct,
    avg(context_tokens)                          AS avg_context
  FROM turns
  WHERE NOT is_synthetic
    AND ts IS NOT NULL
    AND ts >= now() - ($days * INTERVAL 1 DAY)
  GROUP BY day
)
SELECT
  day,
  turns,
  miss_count,
  round(coalesce(hit_rate_pct, 0), 1)                  AS hit_rate_pct,
  round(coalesce(miss_count * avg_context * 0.9, 0) / 1000.0, 1)
                                                        AS extra_tokens_k
FROM daily
ORDER BY day;
