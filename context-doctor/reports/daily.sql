-- daily — per-UTC-day token consumption: input, output, cache, total.
--
-- `days` (int): rolling time window. Default: 7.
--
-- Synthetic rows excluded (billed-token view).
-- NULL-ts turns are excluded here (unlike summary) because we must place them
-- in a calendar day — there is no meaningful date to assign them. Document:
-- turns with ts IS NULL are omitted from daily counts; include them via `summary`.
--
-- TIMESTAMPTZ never returned natively (pytz absent): day is VARCHAR.
SELECT
  strftime(ts AT TIME ZONE 'UTC', '%Y-%m-%d')    AS day,
  coalesce(sum(input_tokens), 0)                 AS input_tokens,
  coalesce(sum(output_tokens), 0)                AS output_tokens,
  coalesce(sum(cache_read), 0)                   AS cache_read,
  coalesce(sum(cache_creation), 0)               AS cache_creation,
  coalesce(sum(total_tokens), 0)                 AS total_tokens
FROM turns
WHERE NOT is_synthetic
  AND ts IS NOT NULL
  AND ts >= now() - ($days * INTERVAL 1 DAY)
GROUP BY day
ORDER BY day;
