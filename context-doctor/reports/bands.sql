-- bands — count/sum/mean/median/p90/max per band of any numeric dimension.
--
-- `dimension` (ident, whitelisted): the column to bucket. Default: context_tokens.
-- `edges` (int_list):  bucket boundaries; `50k,200k,400k` shorthand accepted.
--                      Band assignment: band = count of edges <= metric, so:
--                        band 0 = below first edge (< edges[0])
--                        band 1 = [edges[0], edges[1])
--                        ...
--                        band len(edges) = above last edge (>= edges[-1])
--                      This matches PostgreSQL width_bucket semantics; implemented
--                      via list_filter because DuckDB 1.5.x lacks width_bucket.
-- `days` (int):  rolling window (same NULL-tolerant convention as summary.sql).
--
-- Synthetic rows excluded (unlike summary, bands is a billed-token view; the
-- is_synthetic flag was specifically designed to exclude "<synthetic>" model rows
-- from aggregates like these).
--
-- TIMESTAMPTZ never returned natively (pytz absent in this env).
WITH base AS (
  SELECT {dimension} AS metric
  FROM turns
  WHERE NOT is_synthetic
    AND (ts IS NULL OR ts >= now() - ($days * INTERVAL 1 DAY))
)
SELECT
  len(list_filter($edges, x -> x <= metric))             AS band,
  count(*)                                               AS count,
  coalesce(sum(metric), 0)                               AS sum,
  avg(metric)                                            AS mean,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY metric)    AS median,
  percentile_cont(0.9) WITHIN GROUP (ORDER BY metric)    AS p90,
  max(metric)                                            AS max
FROM base
GROUP BY band
ORDER BY band;
