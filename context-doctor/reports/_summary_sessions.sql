-- summary helper (NOT a standalone catalog report) — per-session rollups that
-- feed the assembled `summary` payload's top_expensive / over-band / avg-context
-- numbers. Shares the SAME $days window as summary.sql so the two agree.
--
-- Mirrors doctor_core.build_summary's per-session reduction sourced from `turns`:
--   max_ctx    = max(context_tokens)   (sess_max[sid])
--   sess_total = sum(total_tokens)     (sess_total[sid])
--   project    = arg_max(project, context_tokens)  (project at the max-ctx turn;
--                build_summary assigns project at the first strictly-greater max
--                — identical when project is session-constant, which it is)
--   first_day  = min UTC day string, used only as a deterministic tie-break proxy
--                for build_summary's first-seen ordering in the top-3 stable sort.
--
-- TIMESTAMPTZ never returned natively (pytz absent): first_day is VARCHAR.
SELECT
  session_id,
  max(context_tokens)                       AS max_ctx,
  coalesce(sum(total_tokens), 0)            AS sess_total,
  arg_max(project, context_tokens)          AS project,
  min(strftime(ts AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%M:%S')) AS first_day
FROM turns
WHERE ts IS NULL OR ts >= now() - ($days * INTERVAL 1 DAY)
GROUP BY session_id;
