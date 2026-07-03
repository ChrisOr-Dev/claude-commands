[繁體中文](./README.zh-TW.md) | **English**

# /legislate

Spend one session on your most capable model turning its judgment into durable harness rules — so every future session on a weaker model runs better because of it.

---

## Why

Model access is often tiered: you may only occasionally reach your most capable model, while day-to-day work runs on a cheaper/faster one. Judgment doesn't transfer between sessions by itself — but files do.

`/legislate` reframes a high-tier session: instead of spending it on a one-off task, spend it *legislating* — writing the rules, dispatch protocols, and rubrics that let the weaker model you'll use tomorrow act as if it had today's judgment.

---

## What It Does

| Step | Action |
|------|--------|
| Ground rules | Work autonomously, ask ≤5 questions up front, write-as-you-go, back up before editing, write for a weaker reader |
| A | **Diagnose** — top 3 ways the current harness leaks tokens, loses focus, or errors out |
| B | **Rewrite the root config** — the highest-leverage file, loaded every session |
| C | **Model dispatch protocol** — delegation rules, report contracts, escalation ladder, verification-not-self-verification |
| D | **Externalized judgment** — rubrics with positive/negative examples for calls only a strong model is naturally good at |
| E | **Delegation prompt templates** — fill-in-the-blank templates for search / implementation / refactor / research / review |
| F | **Maintenance protocol** — how weaker models safely update all of the above |
| G | **Letter to future sessions** — what you weren't asked but judge important, plus how this system is most likely to degrade |
| Closing | Adversarial fresh-context review, read-back verification, one-page summary, checkpoint-and-handoff if context runs low |

---

## Design Choices

**Value-ranked, write-as-you-go.** The session can be interrupted at any point — an interrupted `/last-word` loses nothing new, but an interrupted `/legislate` session should still leave the highest-value artifacts on disk.

**Weak-reader writing.** Every rule this command produces must include concrete criteria and a positive/negative example. "Keep quality high" is not a rule a weaker model can execute; "escalate if the same subtask fails twice with a full failure trace attached" is.

**Verification is never self-verification.** The whole point of externalizing judgment is that the model doing the work shouldn't be the one grading it — even in this legislating session, deliverables get a fresh-context adversarial review before they're considered done.

**Honesty about limits.** No amount of rubric-writing turns a weaker model into a strong one for genuinely ambiguous or taste-driven decisions. `/legislate` requires an explicit answer for what to do when the harness hits that wall: escalate, get a second opinion, or say so.

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote legislate
# or manually
cp legislate/legislate.md ~/.claude/commands/legislate.md
```

## Usage

Switch to your most capable available model, then in Claude Code type: `/legislate`

---

## Credits

Inspired by a technique shared by [@gyozalab](https://www.threads.com/@gyozalab) on Threads: using a rare high-tier model session to "legislate" rather than execute, so its judgment persists as files for every subsequent session.
