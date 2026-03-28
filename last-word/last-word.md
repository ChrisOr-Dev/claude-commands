# /last-word — Session Wrap-Up

Structured session wrap-up before clearing context. Follow each step, report results as you go.

## Step 1: Review

Scan the conversation. Identify: blockers, wins, CLAUDE.md gaps. Brief summary.

## Step 2: Classify & Archive

For each learning, decide where it goes:
- **Universal rule** → `~/.claude/CLAUDE.md`
- **Project rule** → `{project_root}/CLAUDE.md`
- **Temp state** → Memory (project-scoped)
- **Design decision** → Design doc or memory
- **Already tracked** → Do not save

Before writing, check for duplicates — update existing entries instead.

## Step 3: Remaining Work

If unfinished work exists:
1. Save progress to memory (what's done, what remains, branches, issues)
2. Generate a starter prompt for next session in a code block

If all complete, say so and skip.

## Step 4: Sync Issues

If `gh` CLI is available, run `gh issue list`. Verify status matches progress. Suggest closing resolved issues.

## Step 5: Clean Stale Content

Scan memory and CLAUDE.md. Remove: completed tasks, outdated entries, duplicates. Report changes.

## Step 6: Uncommitted Changes

Run `git status` and `git diff --stat`. Warn if uncommitted changes exist.

## Step 7: Summary

```
=== Session Wrap-Up Complete ===
Archived: [what was saved and where]
Cleaned: [what was removed]
Starter Prompt: [saved / not needed]
Uncommitted: [none / list files]
Ready to /clear: [Yes / No — reason]
```

Wait for user confirmation before /clear.
