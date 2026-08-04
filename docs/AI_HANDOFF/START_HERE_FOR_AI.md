# Start Here — For AI Coding Agents

**Read this document first. Then open only the authoritative sources it routes you to for the
current task.** It is the single entry point for every AI session in this repository. It does not
restate what other documents already say correctly — it tells you which document to open for which
question, and gives you the handful of facts you need before you open any of them.

If a task instruction ever conflicts with a rule linked from here, stop and surface the conflict
rather than guessing.

---

## 1. Project mission

**FMITS** (Financial Market Intelligence & Trading System) is a personal, AI-assisted market
decision-support system built as a deterministic pipeline:

```
Data → deterministic calculations → structured features → AI interpretation → decision support
```

It is **not** a signal bot and **not** an automated trading system. `WAIT` and `NO TRADE` are valid
outcomes. Capital preservation and testability outrank impressive output.

Full statement: [`docs/README.md`](../README.md) §"What FMITS is" ·
[`PROJECT_SPECIFICATION_V1.md`](../../PROJECT_SPECIFICATION_V1.md) ·
[`PROJECT_VISION_ADDENDUM_V1.md`](../../PROJECT_VISION_ADDENDUM_V1.md).

---

## 2. Current product status

Read **[`CURRENT_STATE.md`](CURRENT_STATE.md)** for the numbers (commit, test count, exports,
milestone). Do not trust a remembered number — read the file; it is updated every milestone and this
document is not.

The durable facts, unlikely to change milestone to milestone:

- **Product surface:** five CLI commands — `facts`, `mtf`, `regime`, `swing`, `daily` — each a strict
  superset of the one before it in what it composes, never in what it computes.
- **Product Value Level 2** — a usable swing-analysis assistant, one page per instrument carrying
  facts, regime, evidence and conflicts, now runnable across a watchlist in one command. Ladder in
  [`reports/0004`](../../reports/0004_2026-08-01_FMITS_BUSINESS_AND_CAPABILITY_ARCHITECTURE_V1.md) §12.
- **The deterministic structural chain is complete**, end to end, from a candle series to a
  multi-timeframe, regime-classified, conflict-checked workspace with a stated decision-context
  verdict. Nothing in that chain is Planned — everything above it is.
- No AI interpretation layer exists yet. No direction, score, ranking or recommendation exists
  anywhere in the product — this is enforced by tests, not by convention.

---

## 3. High-level architecture

Two things to hold in your head, and nothing more — the detail lives in the linked documents.

**The target layering** (L0 kernel → L11 memory/learning), aspirational and only partially built:
[`reports/0003`](../../reports/0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md) §11 has the full
diagram. Built today: L0 (canonical kernel) through L5 (deterministic context, including
`fmis.market_regime`) and the parts of L7 (`fmis.evidence`, `fmis.decision_support`) that a composition
root reaches. L6, L8 and above are Planned.

**The composition chain that actually exists**, per [ADR-0007](../adr/ADR-0007-application-layer-boundary.md)
("a composition root may import every engine below it; no engine may import a composition root"):

```
engines (L0–L5, L7)  →  fmis.pipeline  →  fmis.workspace  →  fmis.daily
                         (one instrument)  (one page)         (a watchlist)
```

Each arrow is a **strict superset**, never a new computation — `fmis.workspace` calls no engine
directly, and `fmis.daily` calls no engine or builder except `fmis.workspace`'s own composition root.
This is verified by an AST-based test in every milestone that adds a layer; see any recent design
document's "Invariants" table for the pattern.

For the concrete, current directory-by-directory dependency rules (what may import what, right now):
[`REPOSITORY_MAP.md`](../REPOSITORY_MAP.md).

---

## 4. Repository navigation

| I need... | Go to |
|---|---|
| **Architecture** — target layering, module boundaries, roadmap | [`ARCHITECTURE_AND_ROADMAP_V1.md`](../ARCHITECTURE_AND_ROADMAP_V1.md), [`reports/0003`](../../reports/0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md) |
| **Current directory rules** — what may import what | [`REPOSITORY_MAP.md`](../REPOSITORY_MAP.md) |
| **ADRs** — one accepted decision per file, why it was made this way | [`adr/README.md`](../adr/README.md) — 26 to date |
| **Backlog** — what's NOW / NEXT / LATER / DONE | [`FMITS_PRODUCT_BACKLOG.md`](../../FMITS_PRODUCT_BACKLOG.md) |
| **Changelog** — what the product can actually do, and since when | [`FMITS_PRODUCT_CHANGELOG.md`](../../FMITS_PRODUCT_CHANGELOG.md) |
| **Current state** — commit, test count, exports, active milestone | [`CURRENT_STATE.md`](CURRENT_STATE.md) |
| **Design docs** — the reasoning behind a shipped milestone | [`docs/README.md`](../README.md) index — every design doc is paired with its review |
| **Reviews** — independent verification of a shipped milestone (mutation results, adversarial cases, P0–P3 findings) | same index, `reviews/` rows |
| **Testing bar** — this repo's actual standard | no single canonical guide; the bar is demonstrated repeatedly in the reviews above: 100 % line coverage plus **mutation testing with zero survivors**, byte-identical source restoration verified by SHA-256. Read one recent review (e.g. [`DETERMINISTIC_DAILY_WORKFLOW_V1_REVIEW.md`](../reviews/DETERMINISTIC_DAILY_WORKFLOW_V1_REVIEW.md)) for the concrete pattern before writing tests for a new milestone. |
| **Workflow** — how a milestone actually gets built | [`CLAUDE.md`](../../CLAUDE.md) "Working principles" and "Operational reports"; the paper trail is [`reports/README.md`](../../reports/README.md). No dedicated engineering-workflow document exists yet — this section and §6 below are the closest thing to one. |
| **Git safety rules** | [`CLAUDE.md`](../../CLAUDE.md) "Git safety" — read before any commit, push, or history-changing command |

---

## 5. Current active milestone

Read the **"Current milestone"** section at the top of [`CURRENT_STATE.md`](CURRENT_STATE.md) and the
single **NOW** item in [`FMITS_PRODUCT_BACKLOG.md`](../../FMITS_PRODUCT_BACKLOG.md) §5 — there is
exactly one, by rule. Both are kept current at the end of every milestone; this document is not, so
never answer "what's being worked on" from memory of a past session.

---

## 6. Engineering workflow

The cycle, observable across every shipped milestone in [`docs/README.md`](../README.md)'s index:

**design → implement → independently review → commit → (separately authorized) push.**

- One milestone does one thing. [`CLAUDE.md`](../../CLAUDE.md): *"Do one small thing per milestone...
  Do not bundle unrelated changes."*
- A milestone that changes architecture gets a design document in `docs/design/` before code, and an
  ADR in `docs/adr/` if it establishes a new boundary — not every milestone needs one; several recent
  ones explicitly note *"no ADR required"* because they composed existing boundaries.
- Every milestone gets an independent review in `docs/reviews/`, re-deriving claims from the live
  repository rather than trusting the implementation's own account of itself. The reviews consistently
  find real defects that 100 % line coverage alone did not catch — that pattern is the reason mutation
  testing is mandatory, not optional.
- Dated, point-in-time work (audits, cross-cutting analyses) goes in `reports/`, numbered sequentially
  and indexed in [`reports/README.md`](../../reports/README.md) — never in `docs/`, which holds
  *standing* documentation that gets updated in place.
- Commits and pushes follow [`CLAUDE.md`](../../CLAUDE.md) "Git safety" exactly. Never commit, merge,
  rebase, tag or push without the owner's explicit authorization for that specific action.

---

## 7. Model selection and session-cost policy

The full policy — Sonnet as the default model, the four specific cases that justify Opus, the
required per-task model declaration, session-boundary rules for `/clear` and `/compact`, and why
"Opus is safer" is not sufficient justification on its own — is
[`docs/development/AI_ENGINEERING_WORKFLOW_AND_COST_POLICY.md`](../development/AI_ENGINEERING_WORKFLOW_AND_COST_POLICY.md).
Read it before choosing a model or a session boundary; it is not restated here.

In one line: **Sonnet by default, large and autonomous; Opus only for concrete architecture,
systemic reasoning, unknown-root-cause debugging or critical independent review, kept narrow;
`/clear` at milestone or unrelated-task boundaries, `/compact` only within one continuing task.**

---

## 8. Reading policy

Read the **minimum** authoritative documentation for the task, not everything linked from here.

For almost any task, that minimum is: this document, then [`CURRENT_STATE.md`](CURRENT_STATE.md), then
whichever single row of §4's table matches the task. Read a design document or an ADR in full only
when you are about to touch the boundary it governs. Read `ARCHITECTURE_AND_ROADMAP_V1.md` or
`reports/0003` in full only when the task is itself architectural. Never read the entire `reports/`
directory to answer a question one recent report already answers — use
[`reports/README.md`](../../reports/README.md)'s index to find the specific one.

If two documents disagree: an **ADR** wins over `ARCHITECTURE_AND_ROADMAP_V1.md` on the decision it
covers ([`CLAUDE.md`](../../CLAUDE.md)); the **live code** wins over any document about current state —
fix the document, per §6's review-first workflow, rather than trusting the stale one.

---

## 9. Project principles

The non-negotiable rules live in [`CLAUDE.md`](../../CLAUDE.md) — read it in full; it is short.
In one line each, so you know what to expect before you open it: **product first, not documentation** ·
**deterministic first, AI second** · **every milestone must increase product value** · **git history is
never rewritten without explicit authorization**.

The vision and domain principles — why `WAIT`/`NO TRADE` are valid outcomes, why long-term investing
and short-term trading are kept as separate domains, capital preservation over impressive output — live
in [`PROJECT_SPECIFICATION_V1.md`](../../PROJECT_SPECIFICATION_V1.md) and
[`PROJECT_VISION_ADDENDUM_V1.md`](../../PROJECT_VISION_ADDENDUM_V1.md). Read them before proposing
anything that touches what the system is *for*, as opposed to how one module is built.

The engine-level engineering rules (closed-candles-only, no epsilon comparisons, no hidden signals,
dependency direction, immutable results) are owned by the ADRs, not by this document — see §4's ADR
row. Restating them here would duplicate them and let this document drift out of sync with the rule it
is quoting; that duplication is exactly what this rewrite removed.

---

**When in doubt:** prefer the smaller, more reversible, better-tested change, and ask the owner rather
than guess on anything this document doesn't resolve.
