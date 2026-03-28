# /last-word — Session Wrap-Up & Knowledge Archival

You are performing a structured session wrap-up before the user clears context. Follow each step carefully and report results as you go.

## Step 1: Review the Conversation

Scan the entire conversation and identify:
- **Blockers**: Where did you get stuck? What caused it?
- **Wins**: What approaches worked well and should be repeated?
- **CLAUDE.md gaps**: Any rules or patterns that should have been in CLAUDE.md but weren't?

Output a brief summary of findings.

## Step 2: Classify & Archive Learnings

For each learning identified in Step 1, decide where it belongs using these criteria:

| Type | Destination | Criteria |
|------|-------------|----------|
| Universal rule | `~/.claude/CLAUDE.md` | Applies across all projects (e.g., "always use integration tests") |
| Project rule | `{project_root}/CLAUDE.md` or `{project_root}/.claude/CLAUDE.md` | Only relevant to current repo (e.g., "this repo uses pnpm not npm") |
| Temporary state | Memory (project-scoped) | In-progress work, current status (e.g., "feature X is 60% done") |
| Design decision | Design doc (if exists) or memory | Architecture choices with rationale (e.g., "chose approach A over B because...") |
| Already tracked | **Do not save** | Already in git history, GitHub issues, or existing docs |

**Rules:**
- Before writing any new entry, check if a similar one already exists — update instead of duplicating
- For CLAUDE.md entries, append to the appropriate section or create a new section if needed
- For memory entries, use the project's memory system if available

Apply the classification and make the changes. Report what was saved and where.

## Step 3: Handle Remaining Work

If there is unfinished work from this session:

1. **Save to memory**: Record what was done, what remains, relevant branches, and issue numbers
2. **Generate a starter prompt**: Create a ready-to-paste prompt for the next session that includes:
   - What was accomplished
   - What still needs to be done (with specific steps)
   - Relevant file paths, branches, and issue numbers
   - Any context the next session needs to know

Output the starter prompt in a code block so the user can copy it.

If all work is complete, skip this step and say so.

## Step 4: Sync GitHub Issues

Check if there are GitHub issues related to this session's work:
- Run `gh issue list` to see open issues
- Verify issue status matches actual progress
- Suggest closing issues that were resolved, or updating ones that progressed

If no GitHub issues are relevant, skip this step.

## Step 5: Clean Stale Content

Scan for outdated or redundant content:

1. **Memory**: Read existing memory files. Remove entries that are:
   - Completed tasks that are done
   - Outdated information superseded by newer entries
   - Duplicates of what's already in CLAUDE.md or docs
2. **CLAUDE.md**: Check for:
   - Rules that no longer apply
   - Duplicate or conflicting entries
   - Entries that should be moved to project-level CLAUDE.md (or vice versa)

Report what was cleaned up.

## Step 6: Check Uncommitted Changes

Run `git status` and `git diff --stat` to check for uncommitted work.

- If there are uncommitted changes: **warn the user** and list the files. Ask if they want to commit before clearing.
- If clean: report "No uncommitted changes."

## Step 7: Final Summary & Confirmation

Output a summary:

```
=== Session Wrap-Up Complete ===

Archived:
- [list what was saved and where]

Cleaned:
- [list what was removed or merged]

Starter Prompt:
- [saved / not needed]

Uncommitted Changes:
- [none / list files]

Ready to /clear: [Yes / No — reason]
```

Wait for user confirmation before they proceed with `/clear`.
