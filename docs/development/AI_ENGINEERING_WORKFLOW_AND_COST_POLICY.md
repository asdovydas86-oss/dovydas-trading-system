# AI Engineering Workflow and Cost Policy

**Status:** Approved — standing development policy.
**Scope:** Every AI coding session (Claude Code or equivalent) working in this repository.
**Relationship to other documents:** This is the authoritative source for model selection and
session-cost discipline. [`docs/AI_HANDOFF/START_HERE_FOR_AI.md`](../AI_HANDOFF/START_HERE_FOR_AI.md)
carries a short operational summary and links here — it does not duplicate this policy. Where a
future document restates this policy and the two disagree, this document wins.

---

## 1. AI cost is an engineering resource

Tokens, session time and model tier are not free and not incidental — they are an engineering
resource like compute or engineer-hours, and are managed with the same discipline. A task is not
"done cheaply enough" by default; cost is chosen deliberately, per task, against what the task
actually requires.

This does not mean minimizing spend as a goal in itself. It means spend is **proportionate to the
task** — an architecture decision with long-lived consequences justifies more careful (and more
expensive) reasoning than a mechanical implementation of an already-accepted design.

## 2. Product value per AI cost

The metric that matters is **product value produced per unit of AI cost**, not AI cost alone and
not product value alone. A milestone that costs more but removes an architectural hazard, or a
milestone that costs less because the design was already settled, can both be a good outcome. A
milestone that costs little but adds nothing the owner can use is not a good outcome regardless of
its price.

See [`CLAUDE.md`](../../CLAUDE.md) "Working principles" — **Product first** and **Every milestone
must increase product value** — for the product side of this same discipline. This policy is the
cost side of the same standard, not a separate one.

## 3. Model selection

### 3.1 Sonnet is the default implementation model

Sonnet is the default model for engineering work in this repository. Most milestones are
implementation of an already-accepted design, a test suite for an already-designed module, or a
mechanical, bounded, reversible change — exactly the profile Sonnet is suited to.

### 3.2 Opus is reserved for specific, concrete cases

Opus is used only when the task itself demands it:

- **Concrete architecture** — the scope is genuinely in question and must be resolved by reasoning
  before code is written (a new package boundary, a new ADR, a schema with long-lived consequences).
- **Systemic reasoning** — the task requires holding multiple interacting parts of the system in
  mind at once to reach a correct decision, not just executing a known plan.
- **Unknown-root-cause debugging** — the defect's cause is not yet known and finding it requires
  open-ended reasoning across the system, as opposed to fixing a defect whose cause is already
  identified.
- **Critical independent review** — adversarially re-deriving another session's claims, finding what
  its own tests did not catch, before a milestone is accepted.

Each of these is a property of the *task*, not a preference. If a task does not fall into one of
these four cases, it defaults to Sonnet.

### 3.3 "Opus is safer" is not sufficient justification

Reaching for Opus because it is generally more capable, "just in case," or to avoid the discomfort
of a wrong first attempt is not a valid reason on its own. The relevant question is always whether
*this specific task* has one of the four properties in §3.2 — not whether a stronger model would do
it somewhat better. A wrong first attempt on a bounded, reversible Sonnet task costs little to
correct; that cheap correction is itself part of why Sonnet is the default, not a reason to avoid
Sonnet.

### 3.4 Every Claude task must declare its own routing

Before starting substantive work, every Claude task states:

- **Task type** — e.g. implementation of an accepted design, mechanical documentation sync,
  architecture-first design, independent review, unknown-root-cause debugging.
- **Recommended model** — Sonnet or Opus.
- **Reason** — which of §3.1's default case or §3.2's four cases applies, in one sentence.
- **Whether `/clear` follows** — per §5, stated up front so the session boundary is a decision, not
  an afterthought.

This declaration is short — one line each — and is not itself a design document.

### 3.5 Sonnet tasks should normally be large and autonomous

Because Sonnet is the default and the common case, Sonnet sessions should be scoped to complete a
meaningful, autonomous unit of work — a full milestone's implementation, a full test suite, a full
documentation sync — rather than being split into many small back-and-forth exchanges. Splitting a
Sonnet-appropriate task into many small sessions adds session-boundary overhead (re-reading
`START_HERE_FOR_AI.md`, `CURRENT_STATE.md`, the backlog) without adding value.

### 3.6 Opus tasks should be focused and high-value

Because Opus is reserved and costs more, Opus sessions should be scoped narrowly to the specific
reasoning task that justified Opus in the first place — resolve the architecture question, find the
root cause, complete the independent review — and then hand off to a Sonnet session for any
resulting mechanical implementation. An Opus session that drifts into implementation work it did not
need to do is a cost-policy violation even if the resulting code is correct.

## 4. Repository documentation replaces conversation memory

This repository's standing documentation — `START_HERE_FOR_AI.md`, `CURRENT_STATE.md`, the ADRs,
the design docs and reviews indexed in [`docs/README.md`](../README.md), the backlog and changelog —
is the durable record of the project. A session's own conversation history is not: it does not
persist, is not reviewed, and is not authoritative. Any fact a future session needs belongs in the
repository, not in the expectation that a future session will have access to this one's context.

## 5. Minimal authoritative reading, not "read everything"

A session reads the **minimum** authoritative documentation the task requires, not the whole
repository's documentation tree. `START_HERE_FOR_AI.md` §8 states the concrete minimum for most
tasks (that document, `CURRENT_STATE.md`, and the one matching row of its navigation table) and this
policy does not restate it — the same minimal-reading discipline applies to cost, not only to time:
reading more than the task requires spends tokens without adding value, in the same way that
choosing a stronger model than the task requires does.

## 6. Session boundaries: `/clear` and `/compact`

- **`/clear` at milestone or unrelated-task boundaries.** A new milestone, or a switch to a
  genuinely unrelated investigation, starts from a fresh session. Carrying an unrelated prior task's
  context forward costs tokens and risks stale assumptions leaking into the new task.
- **`/compact` only while continuing the same long task.** When a single milestone's session has
  grown long — a long design discussion, a long review — but the task has not changed, `/compact`
  preserves the working thread. It is not a substitute for `/clear` at a genuine task boundary.

See [`START_HERE_FOR_AI.md`](../AI_HANDOFF/START_HERE_FOR_AI.md) §7 for the session-policy summary
that points here.

## 7. Product principles this policy does not override

This is a cost and workflow policy. It does not change, and is subordinate to, the product
principles in [`CLAUDE.md`](../../CLAUDE.md):

- **Product first.** The objective is a production-quality system the owner uses daily. No amount of
  cost discipline justifies producing documentation, reports or process in place of product value.
- **Every milestone must increase product value.** Cost efficiency on a milestone that adds no
  product value is not a win.

## 8. Cost per completed milestone is an engineering metric

Track cost the same way the repository tracks test count, coverage and mutation-survivor count: as
a fact about a completed milestone, alongside its product value, not as a target to minimize in
isolation. A milestone's report or review may note the model tier(s) used and, where session cost is
known, the approximate cost, so that cost-per-value is visible across milestones over time. This is
observational, not a gate — no milestone is blocked on hitting a cost number.

## 9. Quality is never reduced to save tokens

This policy governs *which model* and *how much reading* a task uses — never the testing bar, the
review standard, or the correctness of the work itself. The repository's testing bar (100 % line
coverage, mutation testing with zero survivors, independent review before acceptance — see
`START_HERE_FOR_AI.md` §4's "Testing bar" row) applies identically regardless of which model tier
produced the work. A cheaper session that ships untested or under-reviewed work has not saved cost —
it has deferred a larger cost onto the review or debugging that follows.

---

**When in doubt:** state the task type, the recommended model and the reason (§3.4), pick the
smaller and more reversible option, and ask the owner rather than guess.
