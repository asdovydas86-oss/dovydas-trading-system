# Swing Product Slice 2 — The Operator Decision Layer

| Field | Value |
|---|---|
| **Report number** | 0043 |
| **Title** | Swing Product Slice 2 — The Operator Decision Layer |
| **Date** | 2026-09-04 |
| **Report type** | Implementation (product) |
| **Model** | Claude Opus 5 (1M context) |
| **Repository branch** | `main` |
| **Audited commit** | `77475a5a734081d4f317b3e2aed59fe93738c3f1` |
| **Status** | Complete |
| **Scope** | Put the trading question above the audit question, and preserve per-role reading times. **No trading-policy change of any kind.** Not risk, not sizing, not stops, not alerts, not a redesign. |

---

## 1. The operator's feedback, and what it actually said

Slice 1 succeeded: every scanned symbol reached the page with its evidence
intact. The operator then used the BTCUSDT page and reported the next problem.

It was **not** that the information was wrong, or missing, or too little. It was
that the page answered an **audit** question before it answered a **trading**
one. To learn four things — what was decided, which way the readable evidence
points, what is holding it, and how old the data is — the operator read a long
technical record and assembled them himself.

Slice 2 puts those four above the audit. **It removes nothing.**

## 2. Root causes, both confirmed in the code

### 2.1 The four facts existed and none of them was a value

Every one was *derivable* and none was *represented*:

* **which way the readable evidence points** — the three `DirectionalFactor`
  leans were on the assessment, and nothing reduced them to a line. A surface
  doing it itself would have been a renderer inferring a side;
* **what is holding it** — the policy's three `WAIT` exits were distinguishable
  only as three different English sentences. A sentence cannot be counted,
  grouped, or compared across two symbols;
* **the two timeframe states** — present inside the evidence table, not on a row;
* **how old the data is** — see below.

### 2.2 Per-role reading times were discarded at a seam with a visible `_`

`MultiTimeframeFactSheet` carries an `as_of` **per view** and says explicitly
that `newest_as_of` is *"not a shared observation instant"*. The swing
composition then kept only that one value, and `run_setup_for_symbols` discarded
the fact sheet entirely:

```python
_, assessment = setup_for_symbol(symbol, ...)   # the sheet, dropped
```

So a page could state one instant for three timeframes that are read separately
and close at different rates. **The live measurement is the argument**: on
2026-09-04 the BTCUSDT page said `assessment as of 2026-09-04T04:00Z`, and the
three roles behind it were

```
1w context    2026-08-24 00:00Z   11d 12h old   ← the role that gates everything
1d setup      2026-09-03 00:00Z    1d 12h old
4h execution  2026-09-04 08:00Z       4h  6m old
```

The single instant was the *newest* of the three. The reading that decides
whether any direction may exist at all was **eleven days old**, and the page
implied eight hours.

## 3. Architecture

```
sheet + inputs ─► SetupReadings ──┐
                                  ├─► summarise_decision ─► DecisionSummary
SetupAssessment ──────────────────┘        (fmis.swing_setup)
                                  │
                                  └─► SetupRunResult.readings
                                        → SwingWorkspace.decisions
                                          → SymbolDecisionRow → renderer
```

**Three new types in `fmis.swing_setup`,** which ADR-0028 makes the one package
permitted to name a side:

* `TimeframeReading` — one role's `role`, `interval`, `as_of`, `closed_count`,
  and `age_at(reference)`. The subtraction lives beside the instant it measures,
  which is the arrangement `fmis.market_pulse` already uses and the reason both
  layers above are guarded against arithmetic;
* `SetupReadings` — the per-role readings plus the three **structured**
  context-regime dimensions. Assembled *after* the assessment from values the
  composition had already computed;
* `decision_summary.py` — `DevelopingEvidence` and `Blocker`, pure projections.

**`SetupRunResult` gains one defaulted field, `readings`,** and
`run_setup_for_symbols` stops discarding the sheet. It flows to the workspace
with **no change to `fmis.today` at all** — `TodayRun.results` already carries
`SetupRunResult` through.

**One fetch, one regime evaluation, one assessment.**
`setup_reading_and_assessment_for_symbol` calls
`setup_inputs_and_assessment_for_sheet`, which `setup_assessment_for_sheet` was
already a thin wrapper over. `setup_for_symbol` keeps its exact signature and
delegates.

**One requirement, one place.** `evaluate_setup` compared
`inputs.context_regime_structure is not StructureState.TRENDING` inline. That
value is now `CONTEXT_ROLE_STRUCTURE_REQUIREMENT`, read by both the gate and the
summary that tells an operator what the gate demands — so the page cannot
explain a rule the policy no longer applies.

## 4. Files changed

| File | Change |
|---|---|
| `src/fmis/swing_setup/models.py` | `TimeframeReading` (with `age_at`), `SetupReadings` |
| `src/fmis/swing_setup/decision_summary.py` | **new** — `DevelopingEvidence`, `Blocker`, `DecisionSummary`, `summarise_decision` |
| `src/fmis/swing_setup/policy.py` | `CONTEXT_ROLE_STRUCTURE_REQUIREMENT` named; the inline comparison reads it |
| `src/fmis/swing_setup/compose.py` | `setup_readings_for`, `setup_reading_and_assessment_for_symbol`; `SetupRunResult.readings`; the scan stops discarding the sheet |
| `src/fmis/swing_workspace/models.py` | `TimeframeLine`; `SymbolDecision.developing` / `.blocker` / `.timeframes` |
| `src/fmis/swing_workspace/sections.py` | `_timeframe_lines`; `symbol_decisions(..., reference_time=)` |
| `src/fmis/swing_workspace/builder.py` | passes the page's own instant |
| `src/fmis/operator_dashboard/models.py` | `TimeframeRow`, `DevelopingEvidenceRow`, `BlockerRow`, `SwingSnapshot`; `SwingView.snapshot` |
| `src/fmis/operator_dashboard/sections.py` | `swing_snapshot`, `_developing_row`, `_blocker_row` |
| `src/fmis/operator_dashboard/render.py` | the overview table, the snapshot, the four-panel symbol page, `_IndependenceNotes` |
| `src/fmis/swing_setup/__init__.py`, `swing_workspace/__init__.py`, `operator_dashboard/__init__.py` | exports |
| `tests/swing_decision_helpers.py` | `GATE_LEANING`, `live(..., readings=)` |
| `tests/test_swing_operator_summary.py` | **new** — 43 tests |
| `tests/test_swing_operator_summary_non_vacuity.py` | **new** — 10 tests |
| `tests/test_swing_symbol_decision*.py` | two panel names updated with the panels they name |

## 5. The overview

`/swing` opens with **This scan** — five tiles (scanned, confirmed, candidates,
waiting, could not be read) and two distributions: symbols per **blocker kind**
and per **developing-evidence state**. Every category is an engine enum's own
member. Distributions are in the **enums' declaration order, not by size**,
because a distribution sorted by frequency reads as a ranking of importance.

The per-symbol table replaces `Direction · Classification · Reason` with:

```
Symbol | Decision | Developing evidence | HTF context | Setup state | What is holding it | Data age
```

`Data age` states all three roles separately and never averages them.

## 6. The symbol page — four panels, in the order the question is asked

1. **decision** — decision, developing evidence, what is holding it, HTF
   context, setup state, evidence quality, data age. Slice 1's full decision
   fields, thesis, confirmation and invalidation are one disclosure inside it;
2. **timeframe context and data times** — the regime lines, and a table of every
   role's instant, age and closed-bar count;
3. **directional families**;
4. **evidence and independence audit** — every item, in full, behind a
   disclosure.

Slice 1 built panels 3 and 4 and put them first. **Nothing was removed to make
room**; a test asserts every evidence item's key, statement and observed value is
still on the page.

## 7. Developing evidence — the semantics, and the line they hold

`WAIT` means the policy formed no directional candidate. That is final. The
three families it tallies can still all lean one way — because the gate *before*
the tally rejected the symbol. Reporting only *"WAIT, direction unavailable"*
discards a computed fact; reporting *"LONG"* contradicts the policy.

So the product reports a third thing, in its own type and vocabulary:

| `DevelopingEvidenceState` | Means |
|---|---|
| `DIRECTION_STATED` | the policy named a direction; it is carried verbatim |
| `LEANING` | no direction stated, and every voting family agrees on one side |
| `DIVIDED` | no direction stated, and the voting families disagree |
| `NONE_READABLE` | no direction stated and no family cast a vote |

It renders as *"long leaning · not confirmed, and no direction was stated"*,
always beside the decision chip. **Five enforcement points**, not one:

* `DecisionSummary` rejects `DIRECTION_STATED` beside a `WAIT` state, and rejects
  a `direction` the assessment does not carry — on the **type**, so a second
  producer cannot assemble the contradiction;
* `DevelopingEvidence` rejects a `LEANING` with an opposing family, and a lean
  without a side;
* a test asserts a leaning summary leaves the assessment's state `WAIT`;
* a test asserts the rendered row shows `state-wait` beside the word `leaning`;
* a test forbids *"long signal"*, *"is a candidate"*, *"entry signal"* and
  friends anywhere on the page.

Every conclusion names the families that produced it (`agreeing`, `opposing`,
`non_voting`), and a test asserts every named family exists on the assessment —
so *"why does it say leaning?"* is answered by reading the row, not the source.

## 8. The blocker — the policy's own path, not a re-decision

`Blocker` names which of `evaluate_setup`'s exits fired, walked in the policy's
own order over the same structured values: decision-context sufficiency, then
the context-role regime gate, then the directional tally.

`requirement` answers *"what must become different?"* by restating a condition
the policy **already** states — *"the context-role regime structure must be
`trending`"*. It never states what the market must do to get there. A test
rejects any currency symbol, decimal price, or the words *will / expect / likely
/ soon / predict* in any blocker text, on every fixture.

**The anti-drift guard** is the important one: a test walks all 27 seed triples
and asserts the named blocker always agrees with the sentence the policy itself
wrote — 24 WAIT exits checked, both kinds covered, zero mismatches. If the
policy changes an exit and this projection does not, that test fails.

**When the facts are absent, the answer is `UNDETERMINED`.** A result carrying no
`SetupReadings` cannot tell the two lower `WAIT` exits apart, because the
context-role regime state *is* that distinction. It says so rather than
recovering the answer from the thesis prose — §18's rule, applied to the one
place it was tempting to break.

## 9. Freshness — the decision, and why it stopped where it did

**The dormant architecture was inspected and deliberately not activated.**
`fmis.snapshotting.FreshnessReading` exists and has **no producer anywhere**. It
is not a freshness *policy*: it is a field of a persisted `MarketSnapshot`
record, it measures **bar ages** at snapshot-freeze time rather than wall-clock
age, and constructing one would mean standing up the snapshot-record pipeline —
exactly the large dormant architecture §15 says not to switch on for a display
concern.

**What was implemented instead** is the smallest truthful layer: per-role
`as_of`, `closed_count`, and an age measured against the page's own instant,
carried from the fact sheet that already had them.

**No `FRESH`/`STALE` verdict is published, and this is a decision rather than an
omission.** This repository has validated no staleness bound for any of the three
roles, and the roles are not comparable — a weekly candle closes once a week and
a four-hour candle six times a day, so one threshold could not serve all three
and three invented thresholds would be three unvalidated policies. A test asserts
no model field matches `fresh|stale|expired|verdict|ok|healthy`, and the page
says so in words: *"No age here is called fresh or stale… the age and the bar
count are stated; the judgement is yours."*

The product does not imply stale data is current. It states the age and declines
to grade it.

## 10. Evidence hierarchy and repetition

The audit moved to panel 4, behind a disclosure, **unchanged in content**. One
genuine repetition was removed: the projection attaches a full explanation to
every non-independent item, and several items legitimately share one. Rendered
inline, the operator read one long paragraph several times.

`_IndependenceNotes` numbers each **distinct** explanation, prints it once
beneath the table, and marks each row with its number — the pattern the page's
existing `_Footnotes` already uses. Auditability is unchanged: every row still
carries its own marker, and the full text is on the row's `title`.

Family keys gained readable labels (`context_structural_trend` → *HTF structural
trend*) with **the engine key printed beside every one**, so presentation
improved and provenance did not move.

## 11. Policy non-regression

Same mechanism as Slice 1, same matrix: 81 fixtures through
`setup_assessment_for_sheet`, canonicalised as complete recursive `repr()`
renderings of the assessment and the evidence report.

```
before Slice 2:  81 records, sha256 096a575a015f1e0ed991a049033993b90350b36be6361458d07fbcc36b4a7a42
after  Slice 2:  81 records, sha256 096a575a015f1e0ed991a049033993b90350b36be6361458d07fbcc36b4a7a42
distribution unchanged: 72 WAIT, 9 CANDIDATE
```

**Byte-identical, and identical to Slice 1's** — the same digest three
milestones running. `tests/test_swing_setup_policy_non_regression.py` carries the
per-fixture digests and passes unchanged.

This covers the two changes that touched policy-adjacent code: naming
`CONTEXT_ROLE_STRUCTURE_REQUIREMENT` (a constant equal to the literal it
replaced, compared with the identical `is` test) and the composition-root
refactor (the same sequence, nothing discarded).

## 12. Tests added — 53

| Module | Tests |
|---|---|
| `test_swing_operator_summary.py` | 43 |
| `test_swing_operator_summary_non_vacuity.py` | 10 |

Covering: developing-evidence semantics and the five points that stop it
promoting a decision; the named blocker and its agreement with the policy's own
prose across the matrix; the `UNDETERMINED` honesty case; per-role instants,
ages, missing reference, missing readings; the absence of any freshness verdict;
the snapshot's categories, enum ordering, and the absence of a market verdict
field; no-ranking field guards; the four-panel order; the summary's labels; the
independence warning reaching the summary; the audit still complete; no invented
invalidation; engine keys still visible; and every dashboard route.

**One test was found vacuous and replaced.** The independence-deduplication test
inspected a fixture whose four explanations are four *distinct* strings, so its
loop never executed. It now tests `_IndependenceNotes` directly — a repeated note
numbered once and referenced twice — plus a rendered assertion that every
distinct explanation is numbered and every marker resolves.

## 13. Non-vacuity

Proved against the pre-Slice-2 shape, which is still constructible because every
carrier Slice 2 widened is optional: a `SetupRunResult` with no `readings`, a
`symbol_decisions` call with no `reference_time`, and a `SwingView` with its
default snapshot.

* **freshness** — the old result shape carries no reading instant at all
  (`decision.timeframes == ()`); the old call signature carries instants with no
  age; the old page has no *Last closed candle* column and says so;
* **developing evidence** — the old record's field is unset and *"no
  developing-evidence summary was produced"* renders in its place; the word
  *leaning* is absent from the old row and present in the new one;
* **named blocker** — the old row had only a 120+ character sentence; the two
  WAIT cases could not be compared on any value;
* **snapshot** — the old view's tiles report `Scanned 0`;
* **hierarchy** — the audit was panel 2 of 4 and is now panel 4, with the
  trading answer in panel 1.

## 14. Full suite

**14,102 → 14,155 passing under `-W error`, in 11:14.** The delta is exactly the
53 tests added — no test elsewhere was removed, disabled or renamed. No
failures, no new warnings, and no skips (`-ra` is in `addopts`, so a skip would
have been reported; none was).

**One regression was found by the full suite and fixed.** `test_structural_trend`
guards the layering rule by scanning every file *below* that engine for the text
`fmis.structural_trend` — not for an import, for the **string**. A docstring
sentence and a hardcoded provenance label in the renderer both contained it. The
guard was right and the code was wrong twice over: a renderer that spells an
engine's module name is a second place that name lives, and the producing engine
was already on the page anyway, supplied by the engine itself on every row of the
directional families table. Both literals were removed; no exemption was widened.

## 15. Live verification (2026-09-04, live Binance data, port 8899)

Operator instance on 8787 untouched throughout. All twelve routes `200`.

**The overview, before opening anything:**

```
Scanned 6 · Confirmed 0 · Candidates 0 · Waiting 6 · Could not be read 0
HTF regime not eligible  5      leaning  5
timeframes disagree      1      divided  1

BTCUSDT  wait  long leaning…  1w neutral          1d sustained_higher  HTF regime not eligible (transitioning)  1w 11d 12h · 1d 1d 12h · 4h 4h 6m
BNBUSDT  wait  divided        1w sustained_lower  1d sustained_higher  timeframes disagree                      1w 11d 12h · 1d 1d 12h · 4h 4h 6m
ETHUSDT  wait  long leaning…  1w sustained_higher 1d sustained_higher  HTF regime not eligible (transitioning)  …
SOLUSDT  wait  long leaning…  1w neutral          1d neutral           HTF regime not eligible (transitioning)  …
XRPUSDT  wait  long leaning…  1w neutral          1d sustained_higher  HTF regime not eligible (ranging)        …
DOGEUSDT wait  long leaning…  1w neutral          1d sustained_higher  HTF regime not eligible (indeterminate)  …
```

**BTCUSDT** (39,358 bytes) — `wait` · *long leaning · not confirmed, and no
direction was stated* · **HTF regime not eligible**, observed `transitioning`,
requirement *must be `trending`* · 1w `neutral` / 1d `sustained_higher` ·
2 supporting, 1 conflicting, **independent corroboration not established** ·
1w **11d 12h**, 1d 1d 12h, 4h 4h 6m.

**BNBUSDT** (37,771 bytes) — `wait` · *divided* · **timeframes disagree** (the
gate **passed**) · 1w `sustained_lower` against 1d `sustained_higher`. A visibly
different blocker, a different developing state, a different HTF reading.

**SOLUSDT** (38,997 bytes) — the third, materially different case: leaning like
BTC and blocked by the same gate, but with a **`neutral` setup timeframe** and an
inverted evidence balance (1 supporting, 2 conflicting).

**Guards, checked on the live HTML:** no quantified edge claim; no *opportunity
score*, *closeness*, *conviction*, *profitable*, *validated edge*; no *almost
ready*, *strong opportunity*, *high potential*, *near entry*; no `>fresh<`,
`>stale<` or *up to date*.

## 16. Research boundary

CA (NO_EDGE), CB (UNDERPOWERED), CC (INFEASIBLE) and CD (dependence exists; the
independent-cluster assumption rejected) are **not** rewritten or reinterpreted.

They forbid claiming a validated edge, a calibrated probability or a confidence
score. They do not forbid explaining a deterministic conclusion. *"Long leaning
evidence"* is a **tally of stated leans**, not a probability that the symbol
rises — enforced by the five points in §7, the no-ranking field guards, and the
rendered assertions in §15.

## 17. Product acceptance

**Before Slice 2 — what did understanding BTCUSDT cost?**
A ~32 KB page opening with the evidence audit. The decision fields were present
but the four operator questions had to be assembled by reading: the lean by
inspecting three factor rows and comparing them, the blocker by reading a 200-
character sentence, the timeframe states by reading the evidence table, and the
data age not at all — one instant was shown for three timeframes, and it was the
newest of the three.

**After Slice 2 — what is understood in ten seconds?**
From `/swing`, without opening anything: 6 scanned, none actionable, 5 held by
the HTF regime gate and 1 by a timeframe conflict, 5 with evidence leaning, and
the weekly data 11 days old across the board. From `/swing/BTCUSDT`, in the first
panel: WAIT · long-leaning, not confirmed · held by the HTF regime gate
(`transitioning`, must be `trending`) · 1w neutral, 1d sustained_higher ·
independent corroboration not established · 1w 11d 11h old.

**What can Dovydas do that he could not before?**

Open the Swing workspace and, without clicking a symbol, see what each one is
waiting for, where directional evidence is developing, what the higher and setup
timeframes say, whether the evidence independence is weak, and how old each
timeframe's data is — then open a symbol and get the same answer in one panel,
dropping into the full evidence audit only when he wants it.

And one thing he could not learn at all: **that the weekly reading behind every
regime gate on the page was eleven days old** while the page's single timestamp
said eight hours.

## 18. Deferred to Slice 3

1. **A freshness policy** — per-role staleness bounds, and any `FRESH`/`STALE`
   verdict. Requires a validated bound per role; none exists. §9 records why the
   `fmis.snapshotting` architecture was not activated for this.
2. **The terminal `fmits workspace` renderer** does not show the operator
   summary or the per-role times. The model carries both; only the dashboard
   renders them.
3. **`fmits scan` and `fmits setup`** do not show per-role times either.
4. Risk, sizing, stops, targets, execution, paper, AI interpretation, alerts,
   scan-to-scan change tracking and EP-21 remain out of scope and untouched.
