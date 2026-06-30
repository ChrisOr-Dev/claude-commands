-- top-expensive — sessions ranked by peak context window size.
--
-- Per-session: max context tokens (as _k = /1000), total tokens (_k), project.
-- `days`  (int): rolling time window. Default: 7.
-- `limit` (int): how many sessions to return. Default: 10.
--
-- NULL-ts rows included (same convention as summary: ts IS NULL OR ts >= …).
-- Synthetic rows excluded from BOTH the per-session max and total (is_synthetic
-- is "excluded from billed aggregates" per the schema); a fully-synthetic session
-- yields a NULL peak and sorts last.
-- TIMESTAMPTZ never returned natively (pytz absent): first_ts is VARCHAR.
SELECT
  session_id                                                       AS session,
  any_value(project)                                               AS project,
  max(context_tokens) FILTER (WHERE NOT is_synthetic) / 1000.0     AS max_context_k,
  coalesce(sum(total_tokens) FILTER (WHERE NOT is_synthetic), 0) / 1000.0
                                                                   AS total_tokens_k,
  min(strftime(ts AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%M:%S'))        AS first_ts
FROM turns
WHERE ts IS NULL OR ts >= now() - ($days * INTERVAL 1 DAY)
GROUP BY session_id
ORDER BY max_context_k DESC
LIMIT $limit;
