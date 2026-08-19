# Report 0024 — Stable Setup Identity (Milestone BG-D1) — Implementation Record

| Field | Value |
|---|---|
| **Report number** | 0024 |
| **Title** | Stable Setup Identity (Milestone BG-D1) — Implementation Record |
| **Date** | 2026-08-19 |
| **Report type** | Implementation |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `ec352b7` — the production code and tests of this milestone, committed on top of `2da08b9`. This record and the product documents are committed directly on top of it |
| **Status** | Final |

---

## 1. What shipped, in one sentence

A setup now keeps the same name from one bar to the next, so one idea that
persists for a week is **one** setup rather than forty — closing the measured
defect in which 552 directional observations of a single unchanged idea were
counted as 549 distinct setups.

**No new package. No new record kind. No new domain vocabulary.** Three modules
inside `fmis.proposal`, one latent defect fixed in `lifecycle.admit`, and one
line of the research harness corrected.

---

## 2. How this milestone was scoped, and why it changed

The task as issued was **Milestone BQ — Swing Setup Engine Foundation**: create
`src/fmis/setup/` holding twelve new immutable types (`SwingSetup`,
`SetupSnapshot`, `SetupEvidence`, `SetupConfirmation`, `SetupWarning`,
`SetupContradiction`, `SetupInvalidation`, `SetupQuality`, `SetupStatus`,
`SetupRepository`, `SetupViews`, `SetupErrors`), an append-only repository and a
`fmits setup` CRUD command.

That brief carried its own gate: *"Confirm no existing package already owns this
responsibility. Only then begin implementation."* **The gate failed**, and the
work was re-scoped by the owner to BG-D1 before any code was written. The
findings that failed it:

| BQ type | Already owned by |
|---|---|
| `SwingSetup`, `SetupRepository` | `fmis.proposal.OpportunityProposal` + `OpportunityRepository` — already immutable, append-only, supersession-only, no delete, no overwrite |
| `SetupStatus` | `fmis.swing_setup.SetupState` and `fmis.proposal.lifecycle.ProposalState` |
| `SetupQuality` | `fmis.swing_setup.SetupAssessment` |
| `SetupEvidence`, `SetupConfirmation`, `SetupContradiction` | `EvidenceCitation` + `supporting_evidence` / `opposing_evidence` |
| `SetupInvalidation` | `invalidation: LevelReading \| Absent` |
| `fmits setup` | already exists (`src/fmis/pipeline/cli.py:623`) and prints an assessment page |

`TRADING_DOMAIN_DATA_MODEL_V1` also rules on the question directly. §174: *"`SetupType`,
`SetupOccurrence` and `SetupObservation` are three different types and no field is
[shared]."* §163: *"**There is no separate Opportunity object.**"* §617–618 places all
three Setup types in **`fmis.proposal`**, not a new package. §9.3 and §9.4 give
`SetupObservation` and `SetupOccurrence` durability `REBUILDABLE_PROJECTION`, which
`fmis.persistence.kinds` **refuses to store at all** — so the requested append-only
repository would have persisted a type the model classes as non-storable.

Building BQ literally would have created a fourth meaning of "setup" that §174
forbids and duplicated business logic across three packages.

---

## 3. The defect, measured

`AV`'s setup identity was keyed on `Trigger.level.origin.index`. That index is
**window-relative**: the analysis window slides forward one candle per instant, so
a fixed swing's index falls by one every bar. The identity therefore changed every
bar even when nothing about the market had.

| Measurement | Value | Source |
|---|---|---|
| Directional observations, corrected research window | 552 | report 0012 §7 |
| "Unique setups" reported | 549 | report 0012 §7 |
| Ratio | ~1:1 | — |
| 400-day BTCUSDT run, observations reporting `is_new_setup` | 48 of 48 | `research_identity.py` docstring |

The consequence is not cosmetic. `is_first_confirmation` fired on essentially every
confirmed bar rather than once per setup, so one idea was outcome-evaluated many
times and every rate computed over those outcomes carried an inflated denominator.

### 3.1 The latent defect nobody had hit yet

`fmis.snapshotting.Anchor` — the `MEASURED` identity the data model specifies — has
existed since `BH`. **Nothing in `src/` ever constructed one.** `lifecycle.admit`'s
`_anchor_matches` compared anchors with `left == right`, full structural equality,
which includes `LevelOriginRef.swing_index` — the window-relative field.

Had an anchor ever been built from live data, creation rule 4 would have failed to
deduplicate and **created a new proposal every bar** — 549 from 552 again, this time
with frozen artifacts pointing at them, which is precisely what `admit`'s own
docstring says keying on the `MEASURED` anchor prevents. This is fixed here.

---

## 4. What was built

### 4.1 `fmis/proposal/setup_identity.py` — the rule, stated once

The whole fix is one line of policy: **an identity may only be built from facts
that do not move when the window moves.**

- `stable_origin_id(pivot_timestamp, label, confirmation_bars)` — a content digest
  over the pivot candle's **absolute timestamp**, its swing label, and the
  confirmation window. The index is **not** an input.
- `level_origin_ref(...)` — builds a `LevelOriginRef` whose `origin_id` is stable
  and whose `swing_index` is carried as **provenance only**.
- `anchor_of(...)` — the one legal way to assemble an `Anchor`.
- `anchor_identity(anchor)` — the grouping key. Includes market, book, direction,
  `origin_id`, confirmation window. **Excludes `swing_index`.**
- `anchors_match(left, right)` — used by both creation rule 4 and the read-time
  grouping, so deduplication and counting can never disagree.
- `SETUP_VOCABULARY_ID = "setup"` — §9.2's vocabulary named once.

**`SetupType` is not a new class.** §9.2 makes it a `VersionedTerm` in the `setup`
vocabulary — the shape `TradePlan.setup_type` already carries and
`fmis.statistics.breakdown` already groups on. `VersionedTerm`'s own docstring
already lists *"a setup type"* among its seven vocabularies.

**Why the confirmation window is in the identity but the policy version is not.**
Nothing here reads a `policy_id`, `calculation_version` or `VersionSet`, so two
variants replayed over the same candles decompose history into the same setups.
The confirmation window *is* included because ADR-0024 makes it provenance rather
than policy: a level derived under a different window is a different level, and
`LevelOrigin` has recorded that distinction in its own equality since it was built.

### 4.2 `fmis/proposal/observation.py` — `SetupObservation` (§9.3)

Composes `SetupReading` rather than redeclaring its eighteen fields — §9.3's purpose
line is *"given a home in the domain model **without being copied**"*. Adds only what
the market half has no reason to know: market, book, `VersionSet`, and an optional
`SetupType` that defaults to `Absent`.

**It is a projection, and the type says so by what it lacks**: no record id, no
`RecordAudit`, no `to_payload`, no `from_payload`. A test asserts the store refuses it.

### 4.3 `fmis/proposal/occurrence.py` — `SetupOccurrence` (§9.4)

`group_occurrences(observations, *, occurrence_gap_bars)` — a pure function of the
series and one named parameter. Exposes `began_at`, `last_seen_at`,
`observation_count`, `ever_confirmed`, `first_confirmed_at`.

**`occurrence_gap_bars` is required and has no default.** The data model declines to
choose a value; so does this module. A default would be a trading policy chosen by a
library author, and `BD` §6.7 already found the existing hardcoded parameters *"are
load-bearing and have never been varied or validated."*

### 4.4 Two fixes to existing code

| File | Change |
|---|---|
| `fmis/proposal/lifecycle.py` | `_anchor_matches` now calls `anchors_match` instead of `==`. Closes §3.1 |
| `fmis/swing_setup/backtest_identity.py` | `setup_identity` keys on `level.origin.timestamp` instead of `level.origin.index`. Closes the defect where it actually fires |

---

## 5. Architecture

**Zero new market→domain or domain→market edges.** `fmis.proposal` still imports
nothing from the market half — `test_trade_domain_architecture.py`'s
`test_no_domain_package_imports_an_engine` passes unchanged. `stable_origin_id` takes
the swing label as **text**, not as a `StructuralSwingLabel`, which is what keeps the
domain describable without the engine.

That guard's own docstring anticipated this milestone: *"The data model permits exactly
one read-only edge — `fmis.proposal` reading `fmis.swing_setup` — and this milestone
does not use it… Asserting zero edges now means the day one is added is a deliberate
change to this test rather than an unnoticed import."* **The edge was not taken.**

| Invariant | Result |
|---|---|
| New packages | 0 |
| New record kinds | 0 (15 → 15) |
| Domain types changed | 0 |
| ADRs widened | 0 |
| Architecture guards weakened | 0 |
| New runtime dependencies | 0 |
| Export collisions | 0 |
| Import cycles | 0 |

---

## 6. Verification

| Gate | Result |
|---|---|
| Focused BG-D1 suite | **66 passed** (`tests/test_setup_identity.py`) |
| Backtest identity regressions | **16 passed**, 2 new |
| Proposal / lifecycle regressions | **262 passed** |
| Full repository under `-W error` | **8440 passed**, 0 failed |
| Statement coverage, 3 new modules | **100 %** |
| Branch coverage, 3 new modules | **100 %** |
| Mutation probes | **33 / 34 detected** |
| Determinism | identical digest across 3 separate processes |

### 6.1 The one mutation survivor, and why it is equivalent

*"a naive pivot timestamp is accepted"* — removing `require_utc` from
`stable_origin_id` leaves the suite green because `encode_timestamp`, one line
later, already raises `RecordValidationError: timestamp must be timezone-aware, got
a naive datetime`. Verified directly. The guard is defence in depth with a better
message, not a reachable behaviour change.

### 6.2 Live demonstration

Deterministic, network-free, run against the built product:

```
directional observations of one unchanged idea : 552
AV identity (window-relative index)  -> setups : 552
BG-D1 identity (stable anchor)  -> occurrences : 1

the one occurrence: observed on 552 bars
  ever_confirmed    True
  first_confirmed   2026-08-01T03:00:00+00:00

confirmed BARS      549   <- what AV outcome-evaluated
confirmed DECISIONS 1     <- what BG-D1 evaluates
```

The 549 reproduces report 0012 §7's figure exactly.

---

## 7. Findings recorded rather than quietly fixed

1. **`admit` could never have deduplicated.** §3.1. The most consequential finding
   here: a shipped correctness mechanism that was inert because its one input was
   never constructed. Fixed.
2. **`fmis.snapshotting.Anchor`, `SetupReading`, `FreshnessReading` and
   `StopTriggerSemantics` have no producer.** They were built in `BH` and are
   constructed nowhere in `src/`. BG-D1 makes them constructible and used by the
   domain, but the composition-root adapter that builds a `SetupObservation` from a
   live `SetupAssessment` is **not** built here — see §8.
3. **BP's statistics do not overcount setups.** The task premise was that they did.
   `fmis.statistics.collect` folds over **trades** (`list_paper_trades`,
   `trade_capture.views`), one `TradeStat` per trade; it never counts observations
   or setups, and `setup_type` appears only as a breakdown dimension on a plan. No
   change to `fmis.statistics` was required or made. The overcounting was in the
   backtest harness, and that is where it was fixed.
4. **`research_identity.OpportunityTracker` is now a second grouping rule.** It keys
   on `(symbol, direction, run start instant)` with no gap tolerance and no anchor,
   and its docstring says it *"defines no trading object, is never read by the live
   product."* It is correct for cross-variant research lineage and was left alone,
   but two grouping rules now exist in the repository. Consolidating them onto
   `anchor_identity` is follow-up work, not a defect today.
5. **`LevelOriginRef.swing_index` is now decorative for identity purposes.** It is
   still carried and still validated, and `OpportunityProposal` still cross-checks it
   against its own invalidation level's origin. A future reader may reasonably ask
   whether the field earns its place.

---

## 8. What this milestone deliberately did not do

- **No composition-root adapter.** Nothing yet converts a live `SetupAssessment` into
  a `SetupObservation`. The domain layer is complete and proven; the market→domain
  binding belongs in `fmis.pipeline` alongside `pipeline/prices.py` and is the natural
  next slice.
- **No CLI.** No `fmits` command surfaces occurrences yet. There is therefore **no new
  user-visible capability**, and the changelog is correctly left unchanged.
- **No `occurrence_gap_bars` value chosen.** §4.3.
- **No consolidation of `research_identity`.** §7.4.

---

## 9. Commits

```
ec352b7  feat(setup): add stable setup identity projections
           docs(product): record setup identity milestone   (this record)
```

The production code and tests landed as `ec352b7` on top of `2da08b9`; this record
and the product documents are committed directly on top of it.
