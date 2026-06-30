-- context-doctor metrics warehouse — canonical schema
-- schema_version: 3
--
-- This file is the SINGLE SOURCE OF TRUTH for the warehouse schema and the
-- published contract for any external consumer (dashboard, ad-hoc SQL, a second
-- user). The packaged `doctor` tool executes THIS FILE to create the store on
-- first run — it does not define tables inline — so the running schema and this
-- artifact cannot drift.
--
-- Versioning (see adr/0005-schema-versioning-rebuild.md): the `schema_version`
-- above MUST equal the value seeded into `meta` below. The DuckDB store is a
-- DERIVED CACHE of the raw JSONL logs; to evolve the schema, bump the version
-- here, edit the DDL, and the tool drops & re-ingests from JSONL (no migrations).
-- Because the JSONL is always the source of truth, ANY version is reachable by
-- re-ingest — schema evolution is low-risk and freely revisitable.
--
-- VERSION HISTORY (review exact line diffs via `git log -p schema.sql`):
--   v1  initial — turns, events, ingested_files, meta, sessions view.
--   v2  capture tool-call names + skill/command invocations as `events` rows
--       (no DDL change — generic events table absorbs them) + session_class table.
--   v3  phases first-class: a `phases` table (per-session activity segments with
--       fold-point markers) ; session_class redefined as a ROLLUP of phases.
--
-- `doctor schema` prints this DDL (or the live DDL of an existing store) so a
-- consumer without the repo can still obtain the contract; `doctor schema --diff vN`
-- (future) renders the delta between two versions for review.

CREATE TABLE turns (
  uuid           TEXT PRIMARY KEY,   -- assistant record uuid (idempotency key)
  parent_uuid    TEXT,
  session_id     TEXT NOT NULL,
  project        TEXT NOT NULL,      -- project_for(path): hash dir, sessions/-layout aware
  git_branch     TEXT,
  cwd            TEXT,
  ts             TIMESTAMPTZ,        -- from .timestamp (ISO-8601, stored UTC); NULL-tolerant
  model          TEXT,               -- .message.model; '<synthetic>' rows flagged, see is_synthetic
  is_synthetic   BOOLEAN,            -- model == '<synthetic>' (excluded from billed aggregates)
  stop_reason    TEXT,
  input_tokens   BIGINT,
  output_tokens  BIGINT,
  cache_read     BIGINT,             -- cache_read_input_tokens
  cache_creation BIGINT,             -- cache_creation_input_tokens
  context_tokens BIGINT,             -- cache_read + input + cache_creation (derived)
  total_tokens   BIGINT,             -- context_tokens + output (derived)
  is_miss        BOOLEAN,            -- ctx>5000 AND hit_pct<20 (ported miss heuristic)
  hit_pct        DOUBLE,             -- cache_read/context_tokens*100 (NULL when ctx==0)
  n_tool_use     INTEGER,            -- count content[].type=='tool_use'
  n_thinking     INTEGER,            -- count content[].type=='thinking'
  n_text         INTEGER,            -- count content[].type=='text'
  web_search     INTEGER,            -- server_tool_use.web_search_requests (0 when absent)
  web_fetch      INTEGER,            -- server_tool_use.web_fetch_requests (0 when absent)
  source_file    TEXT NOT NULL
);

CREATE TABLE events (
  source_file TEXT NOT NULL,
  session_id  TEXT,
  ts          TIMESTAMPTZ, -- NULL for control records (mode/permission-mode) — ordered by file position
  seq         INTEGER,     -- monotonic per-file event ordinal, assigned at ingest (one assistant line may emit several events; orders timeless records by file position)
  type        TEXT NOT NULL,   -- user | system | attachment | mode | permission-mode
  subtype     TEXT,            -- system.subtype | attachment.type | user kind (prompt|tool_result)
  key         TEXT,            -- free slot: e.g. mode value, messageCount label
  num         DOUBLE,          -- free numeric: durationMs | tool_result count | messageCount
  ref         TEXT,            -- free ref: e.g. sourceToolAssistantUUID / promptId
  UNIQUE (source_file, seq)    -- idempotency key (events have no uuid; seq is a per-file ordinal, see ingested_files.last_event_seq)
);
-- v2: `events` now also carries per-tool-call and skill/command rows projected from assistant turns
--     (the ADR-0003 "promote a type without migration" path — no DDL change, new rows only):
--       tool_use   : type='tool_use', subtype=<tool name>, key=input.skill (Skill only), ref=turn uuid
--       command    : type='command',  subtype='local_command'|'queued_command', key=command/skill name
--       posture    : type='mode'|'permission-mode' (key=value) + attachment 'auto_mode'/'plan_mode*'
--     These drive session/phase activity classification (see session_class + adr/0013).

CREATE TABLE meta (
  schema_version INTEGER     -- MUST match the `schema_version` header above; mismatch => drop & re-ingest
);
INSERT INTO meta (schema_version) VALUES (3);

-- v3: phases — activity classification's FIRST-CLASS UNIT (see adr/0013).
-- A session is a timeline of phases, not one fixed type. Each phase is a contiguous
-- segment of one dominant activity; `end_marker` records the FOLD-POINT that ended it
-- (the transition into the next phase). The core metric is this segmentation — where the
-- boundaries fall and how long each phase runs — not a single per-session label.
-- Derived from `events` (mode transitions / ExitPlanMode / plan_mode* / compact_boundary)
-- + `turns`; recomputable any time by re-deriving (the JSONL is authoritative).
CREATE TABLE phases (
  session_id     TEXT NOT NULL,
  phase_no       INTEGER NOT NULL,   -- 0-based ordinal within the session
  started_at     TIMESTAMPTZ,
  ended_at       TIMESTAMPTZ,        -- NULL for the final / still-open phase
  classification TEXT,               -- 'planning' | 'implementation' | 'mixed' | 'other'
  confidence     DOUBLE,             -- 0..1 heuristic certainty (B)
  end_marker     TEXT,               -- fold-point that closed it: 'exit_plan_mode' | 'plan_mode_reentry'
                                      --   | 'compact_boundary' | 'mode_change' | NULL (session end)
  n_turns        INTEGER,            -- assistant turns in the phase
  total_tokens   BIGINT,             -- token rollup for the phase
  PRIMARY KEY (session_id, phase_no)
);

-- v2/v3: per-session activity stamp. For source='derived' this is a ROLLUP of `phases`
-- (dominant classification + aggregate confidence + planning/impl share); for
-- source='labeled' it is an explicit ground-truth label (authoritative — never overwritten
-- by a re-derived rollup). The phases table is the unit of truth; this is the convenience
-- default stamp consumers filter on. See adr/0013-session-activity-classification.md.
CREATE TABLE session_class (
  session_id         TEXT NOT NULL,
  classification     TEXT NOT NULL,   -- dominant: 'planning' | 'implementation' | 'mixed' | 'other'
  confidence         DOUBLE,          -- 0..1 heuristic certainty (B); 1.0 for explicit labels (C)
  planning_share     DOUBLE,          -- fraction of session time/turns in planning phases (rollup)
  source             TEXT NOT NULL,   -- 'derived' (rollup of phases) | 'labeled' (explicit ground truth)
  classifier_version TEXT,            -- provenance: which heuristic/labeler produced this stamp
  effective_at       TIMESTAMPTZ,     -- when the stamp takes effect / was assigned (cutover boundary)
  PRIMARY KEY (session_id, source)    -- at most one derived + one labeled row per session; labeled wins
);

CREATE TABLE ingested_files (
  path          TEXT PRIMARY KEY,
  mtime         DOUBLE,
  size          BIGINT,
  last_offset   BIGINT,      -- byte offset of end of last fully-ingested line (append-aware)
  last_line_no  BIGINT,      -- absolute line count ingested so far (seeds line-number resume across tail reads)
  last_event_seq BIGINT,     -- highest events.seq assigned for this file (seeds the per-file event ordinal across tail reads)
  ingested_at   TIMESTAMPTZ
);

-- Optional convenience view: per-session rollups for consumers/dashboards.
-- Derived only; safe to drop/recreate.
CREATE VIEW sessions AS
SELECT
  t.session_id,
  any_value(t.project)                                   AS project,
  min(t.ts)                                              AS started_at,
  max(t.ts)                                              AS last_ts,
  count(*) FILTER (WHERE NOT t.is_synthetic)             AS turns,
  max(t.context_tokens)                                  AS max_context_tokens,
  sum(t.total_tokens) FILTER (WHERE NOT t.is_synthetic)  AS total_tokens,
  count(*) FILTER (WHERE t.is_miss)                       AS misses,
  ( SELECT count(*) FROM events e
    WHERE e.session_id = t.session_id
      AND e.type = 'system' AND e.subtype = 'compact_boundary' ) AS compactions
FROM turns t
GROUP BY t.session_id;
