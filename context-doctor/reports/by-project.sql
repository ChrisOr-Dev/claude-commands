-- by-project — per-project rollups: turns, sessions, max context, total tokens,
-- miss count.
--
-- `days` (int): rolling time window. Default: 7.
--
-- Synthetic rows excluded (billed view); NULL-ts rows included (same convention as
-- summary.sql: ts IS NULL OR ts >= …).
SELECT
  project,
  count(*) FILTER (WHERE NOT is_synthetic)         AS turns,
  count(DISTINCT session_id)                       AS sessions,
  coalesce(max(context_tokens) FILTER (WHERE NOT is_synthetic), 0) AS max_context,
  coalesce(sum(total_tokens) FILTER (WHERE NOT is_synthetic), 0) AS total_tokens,
  count(*) FILTER (WHERE is_miss)                  AS miss_count
FROM turns
WHERE ts IS NULL OR ts >= now() - ($days * INTERVAL 1 DAY)
GROUP BY project
ORDER BY total_tokens DESC;
