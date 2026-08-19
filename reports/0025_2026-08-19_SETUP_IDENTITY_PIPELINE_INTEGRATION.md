# Report 0025 — Setup Identity Pipeline Integration (BG-D1b) — Implementation Record

| Field | Value |
|---|---|
| **Report number** | 0025 |
| **Title** | Setup Identity Pipeline Integration (BG-D1b) — Implementation Record |
| **Date** | 2026-08-19 |
| **Report type** | Implementation |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `1909134` — the production code and tests of this slice, committed on top of BG-D1's product-docs commit, which sits on `ec352b7`. This record and the product documents are committed directly on top of it |
| **Status** | Final |

---

## 1. What shipped, in one sentence

The stable setup identity built in `BG-D1` is now reachable from live market
data: one new application-layer package turns the swing-setup engine's
`SetupAssessment` into a `SetupObservation`, groups a run of them into
`SetupOccurrence`s, and tells a caller whether the latest reading is a **new
idea** or the **same idea seen again**.

**No new record kind. No repository. No CLI change. Nothing persisted.**

---

## 2. Where it went, and why not where the brief said

The brief asked for the adapter in `fmis.pipeline`, beside `prices`. **It cannot
live there**, and the guard that says so is one of the repository's strongest:

> `test_no_market_half_package_imports_the_trading_domain` — *"Or the analysis
> becomes a function of the position — the oldest bias in trading."*

`fmis.pipeline` is a market-half package in that guard's own list, and this
adapter necessarily names `fmis.proposal`, `fmis.accounts`, `fmis.snapshotting`,
`fmis.money` and `fmis.versioning`. Placing it under `fmis.pipeline` was tried
and **failed that guard**.

`pipeline/prices.py` is not a counter-example — it is the pattern. It holds no
domain import either; it delegates to `fmis.marks`, an application package. Every
domain edge `pipeline/cli.py` has is the same shape: it names `fmis.paper`,
`fmis.valuation`, `fmis.trade_capture`, `fmis.statistics`, `fmis.today` — an
application package — and never a domain root.

So the adapter is `fmis.setup_observation`, the application tier, which is
exactly where the cited precedent puts the domain-touching half. This satisfies
the brief's intent — *at the composition root, not in the domain and not in
`swing_setup`* — without weakening the guard.

**It is also not re-exported from `fmis.pipeline`.** That was tried too: importing
it there pulls `fmis.accounts` and behind it a chain ending in a package that
imports `fmis.pipeline`, raising `ImportError: cannot import name
'EvidenceReport' from partially initialized module`. Four import-order regression
tests pin this.

---

## 3. What was built

### `fmis/setup_observation/observe.py`

| Export | Purpose |
|---|---|
| `observation_from_assessment(...)` | one live `SetupAssessment` → one `SetupObservation` |
| `observe_setup_series(...)` | a chronological run → `SetupIdentityRun` |
| `SetupIdentityRun` | observations, occurrences, and `is_new_occurrence` / `repeated_observation_count` |
| `setup_version_set(...)` | the version axes in force, policy recorded but never in identity |
| `STOP_TRIGGER_SEMANTICS` | `BD` R-13 as a value: stop on **touch**, invalidation on **close** |
| `SETUP_OBSERVATION_BOOK` | `Book.SWING`, a parameter everywhere below |

**The anchor comes from the stop, and only when the stop has a `MEASURED`
origin.** `BD` R-13 records that the stop price and the structural invalidation
are the same number, so the level a setup is risked against is the level the idea
is anchored on. A stop with no `LevelOrigin` — ADR-0019 D2's unlabelled swing —
yields `Absent` rather than a fabricated anchor.

**Identity never sees the window.** `LevelOrigin.index` is passed through only as
`LevelOriginRef.swing_index`, which `anchor_identity` excludes. Identity is the
pivot candle's absolute timestamp, its label and its confirmation window.

### Three design decisions worth stating

1. **The direction map is derived, not written out.** `_DIRECTIONS = {member:
   TradeDirection(member.value) for member in Direction}`. ADR-0028 §5 keeps
   directional vocabulary out of every package that has not earned it, and this
   one has not: it translates a side, it never decides one. **No exemption was
   added to `test_directional_vocabulary_boundary`** — the guard passes over the
   new package unchanged. The map is also total by construction, so a third
   member in either vocabulary raises at import time instead of mapping to
   nothing.
2. **Freshness is honestly absent.** §9.3 names three bar ages; the built engine
   computes none of them, and the only age in the repository is a private
   research helper that subtracts two numbers. Deriving one here would be
   arithmetic; inventing one would be worse. Each age is `Absent` with the
   reason. An AST test asserts the module contains no arithmetic operator at all.
3. **`float` → `Decimal` crosses exactly once**, through
   `exact_from_market_price`, the single sanctioned conversion in the domain.

---

## 4. One guard allowlist extended, and it is stated plainly

`tests/test_level_crossing.py::test_nothing_below_imports_level_crossing` keeps a
curated list of packages permitted to name `fmis.level_crossing`. The new package
reads `PriceLevel`, `LevelSide` and `LevelOrigin` **by reference**, so it was
added — a seventh entry, with the justification written into the test's docstring
in the same style as the sixth.

This is the guard's own documented widening mechanism, used as designed: it was
widened for Milestone AR on exactly this footing (*"reuses `PriceLevel`/`LevelSide`
by reference… computing nothing new"*). The rule it protects is unchanged —
nothing *below* `fmis.level_crossing` reaches into it, and no consumer re-derives
a level. **This is the only guard file touched by this milestone**, and it is
recorded here rather than left for a reader to find in a diff.

---

## 5. Verification

| Gate | Result |
|---|---|
| Focused adapter suite | **53 passed** (`tests/test_setup_observation.py`) |
| BG-D1 domain suite | **66 passed** (`tests/test_setup_identity.py`) |
| Proposal / persistence / statistics regressions | **1180 passed** |
| Swing-setup + pipeline regressions | **799 passed** |
| Full repository under `-W error` | **8499 passed**, 0 failed |
| Statement + branch coverage, new package | **100 %**, 0 missed |
| Mutation probes, adapter | **22 / 23 detected** |
| Mutation probes, BG-D1 domain (re-run) | **33 / 34 detected** |
| Architecture / boundary / cycle guards | all pass; 4 import-order tests added |

### 5.1 The two mutation survivors, both proven equivalent

- **Adapter — *"a non-directional reading is given an anchor"***: removing the
  `direction.is_directional` guard changes nothing, because `SetupAssessment`
  refuses a WAIT result that carries a stop, so `stop_reading` is always `None`
  when the direction is `NO_TRADE`. A test asserts that refusal directly. The
  guard stays so a future third direction member cannot silently acquire an
  anchor.
- **Domain — *"a naive pivot timestamp is accepted"***: carried over from report
  0024 §6.1, unchanged. `encode_timestamp` already raises on a naive datetime.

### 5.2 Requirement 6, test by test

| Required property | Test |
|---|---|
| same setup across bars → one occurrence | `test_one_setup_across_many_bars_is_one_occurrence` |
| sliding windows create no new identity | `test_a_sliding_window_does_not_create_new_identities` |
| new structural anchor → new occurrence | `test_a_new_structural_anchor_starts_a_new_occurrence` |
| deterministic rerun → identical identity | `test_a_deterministic_rerun_produces_identical_identities` |
| no-lookahead preserved | `test_no_lookahead_a_prefix_yields_a_prefix_of_the_same_identities`, `test_an_observation_never_depends_on_a_later_one` |
| policy version does not rewrite identity | `test_a_policy_version_change_does_not_rewrite_identity` |
| captured artifacts never cite a derived key | `test_a_captured_artifact_never_references_a_derived_occurrence_key` |
| admission dedup uses stable anchor semantics | `test_admission_deduplicates_an_adapter_built_anchor_across_a_window_slide` |

The no-lookahead test is the strong form: for **every** prefix length of a
20-bar series, the occurrence identities from the prefix are a prefix of the
identities from the full run.

### 5.3 Live demonstration

Deterministic, network-free, through the real adapter:

```
live assessments of one unchanged idea      : 552
distinct window indices in that series      : 552
AV identity (window-relative)  -> setups    : 552
BG-D1 identity (stable anchor) -> occurrences: 1

the one occurrence
  observed on       552 bars
  first_confirmed   2026-08-01T03:00:00+00:00
  is_new_occurrence False  <- a surface prints 'seen before'

confirmed BARS      549   <- what AV outcome-evaluated
confirmed DECISIONS 1     <- what BG-D1 evaluates

swing_index at bar 0 / bar 551: 551 / 0  (provenance, not identity)
identity equal across that slide: True
```

The 549 again reproduces report 0012 §7's figure exactly.

---

## 6. Preserved, and checked

| Invariant | Result |
|---|---|
| `fmis.swing_setup` strategy logic | **unchanged** — not one line of `policy.py` or `compose.py` touched |
| `fmits setup` output | **unchanged** — no CLI file touched |
| Existing proposal behaviour | unchanged; `admit` still uses report 0024's `anchors_match` |
| Record kinds | **15 → 15** |
| New runtime dependencies | 0 |
| Import cycles | 0, with four order-permutation tests |
| Scoring / confidence / AI / indicators / regime / execution / venue code | none added |

---

## 7. Findings recorded rather than quietly fixed

1. **The brief's placement was not achievable as written.** §2. Recorded rather
   than resolved by adding an exemption to the market-half guard.
2. **The pipeline package cannot re-export this adapter.** §2. A real circular
   import, not a style preference.
3. **Freshness remains unbuilt.** §3.2. §9.3's three bar ages are `Absent` with a
   reason on every observation. Building them means giving the engine a bar-age
   fact, which is engine work this milestone had no mandate for.
4. **`SetupType` is still never populated.** Every observation carries
   `Absent`. §9.2 makes classification owner-asserted, and no surface asks the
   owner for it yet.
5. **Nothing calls the adapter in production yet.** It is complete, proven and
   reachable, but `fmits setup`, `fmits scan` and `fmits today` do not use it —
   deliberately, because requirement 4 was to leave existing output unchanged.
   Wiring a surface to it is the next slice and is where the user-visible
   capability arrives.
6. **`research_identity` still holds a second grouping rule**, unchanged from
   report 0024 §7.4.

---

## 8. Product documents

**The changelog is deliberately unchanged.** `FMITS_PRODUCT_CHANGELOG.md` records
user-visible capability only, and this milestone adds none: no command changed,
no output changed. `CURRENT_STATE.md` and `FMITS_PRODUCT_BACKLOG.md` are updated.

---

## 9. Commits

```
ec352b7  feat(setup): add stable setup identity projections   (BG-D1)
1909134  feat(setup): integrate stable setup identity into pipeline
           docs(product): record setup identity pipeline integration   (this record)
```
