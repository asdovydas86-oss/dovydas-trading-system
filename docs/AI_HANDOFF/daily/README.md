# Session handoffs

One file per meaningful project session: **`YYYY-MM-DD.md`**. If a day holds two genuinely separate
sessions, append a suffix — `2026-09-16-b.md`.

**Purpose:** preserve *decisions and continuation state* so the next session does not depend on chat
memory. **Not** a transcript. **Not** a duplicate of a report — link to reports instead.

**Authority:** a handoff is a **continuity pointer**. It is not authoritative over the live
repository, the ADRs, or [`../CURRENT_STATE.md`](../CURRENT_STATE.md). If a handoff and the code
disagree, the code is right.

**When to write one:** at the end of any session that changed the repository, made a decision, reached
a research conclusion, or left work unfinished. A session that only answered a question needs none.

## Template

```markdown
# Session — YYYY-MM-DD

| Field | Value |
|---|---|
| **Session type** | implementation / audit / design / research / documentation |
| **Model** | |
| **Branch · HEAD at start** | |
| **HEAD at end** | |
| **origin/main at end** | |

## Attempted
## Completed
## NOT completed
## Product change
(or: none — this session changed no user-visible capability)
## Architecture decisions
## Research conclusions
## Owner / product observations
## New requirements
## Findings
## Review state
## Tests and verification
(state exactly what was and was not run)
## Commits / push state
## Dashboard / operator state
## Deferred
## Risks and blind spots
## EXACT NEXT STEP
## MUST NOT FORGET
```

## Index

| Date | Session | Handoff |
|---|---|---|
| 2026-09-16 | Project Memory & Documentation Gate | [2026-09-16.md](2026-09-16.md) |
| 2026-09-17 | TA Slice 5A — Recover Technical Context & Feature Series | [2026-09-17.md](2026-09-17.md) |
