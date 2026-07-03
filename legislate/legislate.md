# /legislate — Turn One Strong-Model Session Into Durable Harness Rules

Use this on your most capable available model, when a weaker model will run this harness long-term afterward. Don't do routine tasks. Convert your judgment into files a weaker model can execute — whatever lands on disk is the value that survives, not this conversation.

## Ground Rules

1. Work autonomously. Inspect the environment yourself (CLAUDE.md, subagents, model/effort options, MCP, skills, memory). Ask at most 5 clarifying questions up front, then stop asking and finish unattended.
2. Rank deliverables by value; write each to disk the moment it's done. This session can be interrupted anytime — whatever's on disk then is everything the user gets.
3. Back up any existing file before editing it. Put new content in new files; keep the always-loaded file (e.g. CLAUDE.md) a thin router pointing at them.
4. Your reader is a weaker model. Rules must be concrete and executable, with criteria and examples — abstract advice ("keep quality high") equals writing nothing.
5. Every deliverable must run at the weaker model's tier — don't rely on capability only you have.
6. Run at max reasoning effort if available; long turns are fine.

## Deliverables (in this order, write-as-you-go)

- **A. Diagnosis** — top 3 ways this harness wastes tokens, loses focus, or produces errors, each with a concrete fix. Everything below cites this.
- **B. Rewrite the root config file** (e.g. CLAUDE.md) — highest-leverage, loaded every session. Merge duplicates, cut stale content, extract long sections into files it points to.
- **C. Model dispatch protocol** (own file) — commander delegates all legwork (bulk reads, repo scans, web research, batch edits), main loop only receives conclusions; delegation triple (goal+motivation / acceptance criteria / report format); explicit model+effort choice from what's actually available; report contract (conclusions + file:line only, large artifacts saved to a file with the path returned); escalation ladder (cheap model errs once → escalate; mid-tier errs twice on same subtask with full failure trace → escalate; solved pattern → demote to cheap model for batch reuse; cap total retries); verification is never self-verification (fresh-context agent: read-back for files, tests/live-run for code, second opinion for high-risk calls).
- **D. Externalized judgment** (own file) — rubrics a weaker model can execute for calls only a strong model is naturally good at: when to escalate model, when something is actually done, when to stop and ask the user, what signals mean the approach is wrong (pivot, not retry), how to verify the quality floor. One positive and one negative example per rule.
- **E. Delegation prompt templates** — fill-in-the-blank, acceptance criteria + report format baked in, one each for: search, implementation, refactor, research, review.
- **F. Maintenance protocol** — how future weaker models safely update everything above: what they may change unsupervised vs. needs user confirmation, where lessons from mistakes get written back and in what format, when to compact.
- **G. Letter to future sessions** — three things nobody asked but you judge most important for this environment, plus the most likely way this system degrades and how to prevent it.

## Closing (mandatory)

1. Spawn a fresh-context subagent to adversarially review everything: contradicting rules, wrong paths/tool names, language a weaker model would misread. Fix until clean.
2. Read-back verify each file actually landed with complete content.
3. Give the user a one-page summary: what changed, why, how to use it starting now.
4. If context runs low: stop producing new deliverables, finish steps 1-3 first, and write anything unfinished into the Letter to Future Sessions as a handoff.

## Honesty Clause

State the harness's limits explicitly. Decomposition, verification, and multi-sample review compensate for execution quality — not for ambiguous requirements or taste judgments. Write down what to do when those are hit: escalate model, get an external second opinion, or say plainly it can't be done. Look up what you don't know; flag what you can't find. Never fabricate.
