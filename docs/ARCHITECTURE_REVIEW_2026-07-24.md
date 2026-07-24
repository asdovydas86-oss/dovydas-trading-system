# Architecture Review — 2026-07-24

**Status:** Review record (no production code was modified)
**Baseline:** `5e7e3d55c53d31ec515c0296daebd0745ae83386` — `feat(data): enforce canonical UTC timestamps`
**Test baseline:** 218 passing, working tree clean, `main` in sync with `origin/main`
**Purpose:** verify that the architecture is still correct **before** more implementation lands, so that
module boundaries are validated while changing them is still cheap.
**Relationship to other documents:** this record does not modify
[ARCHITECTURE_AND_ROADMAP_V1.md](ARCHITECTURE_AND_ROADMAP_V1.md), which remains authoritative for
boundaries and decisions D1–D11. Where the code and that document disagree, this record states the
disagreement and — per the repository rule that *the code is the truth about current state* — describes
what actually exists, then names the decision required to reconcile the two.

---

# 1. Method

Every claim below was verified by reading the working tree at the baseline commit: all 22 Python modules
under `src/`, all 10 test modules, and every document under `docs/`. The internal import graph was
extracted mechanically from the source rather than from documentation. Nothing in this review is inferred
from memory of an earlier session.

---

# 2. Verified current state

## 2.1 Internal dependency graph (extracted from source)

```
fmis.data._timeutils            (no internal imports — leaf)
        ↑
fmis.data.models                (imports _timeutils)
fmis.data.observation           (imports _timeutils)
        ↑
fmis.data.alignment             (imports fmis.data.observation)
        ↑
fmis.data.__init__              (re-exports models, observation, alignment)
        ↑
fmis.features.types             (imports fmis.data)
        ↑                  ↖
fmis.features.registry     fmis.features.indicators.{ema,atr,rsi,macd}
        ↑                  ↗
fmis.features.feature_engine.engine   (imports fmis.data, registry, types)

fmis.features.indicators.sources    (no internal imports — leaf)
fmis.features.indicators.ema_math   (no internal imports — leaf)
```

**Result: acyclic, one-directional, no upward imports.** No module imports a later pipeline stage. No
provider, AI, strategy, risk, or execution import exists anywhere. The two shared kernels remain
dependency-free. No sibling indicator imports another sibling. `fmis.features` does not — and cannot
usefully — reach `ObservationSeries` or the alignment service.

## 2.2 Data flow, end to end

```
(no ingestion layer yet — CandleSeries constructed by tests/callers)
        │
        ▼
Candle / CandleSeries ──── validate on construction (UTC, ordering, OHLC invariants)
        │
        ├──► FeatureEngine.compute(series, names, sources=)
        │        series.closed() → topological order → Feature.compute(FeatureContext) → FeatureResult
        │        └──► FeatureSet(symbol, timeframe, as_of=last closed candle)
        │
        └──► (GAP: no CandleSeries → ObservationSeries reduction)

ObservationSeries ──► align_intersection(series...) ──► AlignmentResult(series…, AlignmentReport)
        │
        └──► (nothing consumes this yet — the RVE is the intended consumer)
```

The two halves of the system — the candle/feature pipeline and the observation/alignment pipeline — are
**not yet connected**. Section 4 (R1) treats this as the principal gap.

## 2.3 Test coverage by module (218 total)

| Module | Tests |
|---|---|
| `tests/test_data_models.py` | 50 |
| `tests/test_observation.py` | 39 |
| `tests/test_ema.py` | 27 |
| `tests/test_macd.py` | 24 |
| `tests/test_rsi.py` | 22 |
| `tests/test_alignment.py` | 22 |
| `tests/test_atr.py` | 15 |
| `tests/test_features_architecture.py` | 12 |
| `tests/test_ema_math.py` | 5 |
| `tests/test_smoke.py` | 2 |

---

# 3. Layer-by-layer assessment

Legend: **sound** (no action) · **sound, note recorded** · **decided, work scheduled** · **gap**
(the R2/R3 "decision required" entries in the original review are now decided — see §4 and §5.)

| Layer | Status | Assessment |
|---|---|---|
| **Data flow** | gap, scheduled (I-E) | Correct within each half; the two halves do not meet (R1). |
| **Module boundaries** | decided, scheduled (I-E) | Clean everywhere; alignment placement is decided — move to `fmis.alignment` (R2, [ADR-0002](adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md)). |
| **Package structure** | sound | `src/` layout, one responsibility per package, empty Tier-2 packages carry documented intent at near-zero cost. |
| **Deterministic vs AI responsibilities** | sound | The separation is not merely documented — it is *enforced*: `FeatureCategory` is technical-only and a test asserts the exact member set and the absence of `MACRO`/`NEWS`/`ONCHAIN`/`DERIVATIVES`/`SENTIMENT`/`AI`. No AI code exists to leak. |
| **Adapter layer** | gap (by design) | Does not exist. Currently a strength — no provider type has reached the domain — and a known limitation: nothing populates a `CandleSeries`. Two obligations now belong to it explicitly (R13, ADR-0001). |
| **Canonical data models** | sound, note recorded | `Candle`, `CandleSeries`, `ObservationSeries` are frozen, validated, tuple-normalized, UTC-enforced. Notes: R3 (no knowledge date), R4 (`_timeutils` privacy), R11 (float vs Decimal). |
| **Indicators** | sound | EMA/ATR/RSI/MACD: closed-candles-only, explicit warm-up, explicit insufficient-data state, provenance in metadata, shared `ema_series` prevents divergent EMA implementations, no third-party TA library. |
| **Feature layer** | sound, note recorded | Registry-based discovery keeps the engine open/closed; topological ordering handles feature-on-feature dependencies; results immutable. Note: R5 (last-value-only results) and R8 (implicit as-of contract). |
| **Relative value engine** | not started | Correctly absent. Its prerequisites are R1 and the decisions in §5. Design in [RVE_DESIGN_V1.md](RVE_DESIGN_V1.md). |
| **Strategy engine** | not started | No premature coupling exists. The seam is correct: strategy consumes features/RVE/regime, and nothing below it may name a signal. |
| **Portfolio engine** | not started | Will depend on RVE (correlation) and Risk. Blocked on nothing today; must resolve R11 before it handles money. |
| **Risk engine** | not started | Same as portfolio: R11 applies. |
| **AI interpretation layer** | not started | The boundary is well defended in advance: `FeatureResult` is documented as deterministic-only, and AI output is explicitly barred from being stored as one. |
| **Execution layer** | not started | Correctly deferred and disabled by principle. |
| **Paper trading** | not started | Correctly ordered after strategy + backtesting. |
| **Backtesting** | not started | The one unbuilt layer whose requirements already constrain an existing contract — see R5 and R8. This is the most important forward-looking finding in this review. |
| **Future live execution** | not started | No coupling, no premature abstraction. Nothing to review. |

---

# 4. Findings

Numbered `R1…R14`, ordered by how expensive they become if left until later.

## R1 — The candle pipeline and the observation pipeline are not connected *(gap — blocks Milestone J)*

`ObservationSeries` and `align_intersection` exist and are well tested, but **nothing can produce an
`ObservationSeries` from a `CandleSeries`**. The Milestone I scope in the architecture document (§10 and
§14) lists "a helper deriving one from a `CandleSeries` + source" as a deliverable; it was not
implemented.

**Why it matters:** every RVE v1 metric — ratio, log ratio, indexed performance, relative return,
correlation — operates on two aligned series, and in practice at least one of them is a *price* series.
Without the reduction there is no path from market data into the alignment machinery, so Milestone J
cannot begin. This is not a design flaw; it is an unfinished milestone.

**Where it belongs:** beside the model in `fmis.data`. It is a pure domain transform (pick a source field,
carry the timestamps) requiring no policy, no I/O, and no configuration. Open Question §13.4 leaned the
same way; this review closes it in that direction.

**Cost of delay:** low now, high later — the longer the two halves stay unconnected, the more likely a
future RVE implementation grows its own ad-hoc conversion inline, duplicating the transform.

## R2 — The alignment service lives inside the canonical model package *(decided — move to `fmis.alignment`)*

Decision D4 and the Milestone I code scope both state that alignment is a **policy/service, not a model**,
and place it in a separate module (`src/fmis/alignment/`). The implementation put it at
`src/fmis/data/alignment.py` and re-exported `align_intersection`, `AlignmentResult`, `AlignmentReport`,
and `SeriesAlignmentStats` from `fmis.data`.

**This is a genuine deviation from an accepted decision, not a documentation lag.** Two positions are
defensible:

- *Alignment belongs outside `fmis.data`* (the recorded decision). `fmis.data` is the domain kernel; its
  job is to define what data **is**. Alignment defines how data is **made comparable**, and it is
  explicitly a *policy* — strict intersection is one of several possible policies, with forward-fill,
  as-of joins, resampling, and vintage handling already named as future siblings. Once those arrive, a
  `fmis.data` that contains them is no longer a kernel; it is a grab-bag, and the "canonical models import
  nothing but each other" invariant becomes hard to state.
- *Alignment belongs inside `fmis.data`* (what was built). It operates only on canonical models, produces
  only canonical models, imports nothing else, and splitting a two-file concern across two packages is
  ceremony. The current file is 153 lines and genuinely cohesive with `observation.py`.

**Recommendation: move it to `src/fmis/alignment/`, now.** Not because the current placement is harmful
today, but because the cost is asymmetric. Today the move is two file moves plus an import line, with the
public import path `fmis.data.align_intersection` being the only thing that changes. After the RVE, the
forward-fill policy, and the resampling policy are built on top of it, the same move touches every
consumer. The recorded decision (D4) already anticipated exactly this.

**If the alternative is preferred instead**, that is entirely reasonable — but D4 must then be amended
with an ADR stating *why* alignment over canonical models is considered part of the canonical layer, and
what the rule is for the next policy module. What must **not** happen is the code and the accepted
decision continuing to disagree silently.

**Resolution (2026-07-24): accepted — move to `fmis.alignment`.** Recorded in
[ADR-0002](adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md); the code move is scheduled as
**Milestone I-E** (implementation under a separate prompt). No code was moved in this documentation
milestone.

## R3 — Nothing in the model expresses *when a value became knowable* *(decided — macro/vintage data gated)*

Architecture doc §7.3 states that look-ahead bias is "structurally prevented: a value may only enter a
computation at a timestamp at which it was **knowable**", and §10/§14 require a no-look-ahead test as
Milestone I acceptance. **Neither is currently true, and the test does not exist — because it cannot yet
be written.**

`ObservationSeries` carries exactly one time dimension: the observation timestamp. Macro data has two —
the period it describes (*observation date*) and the moment it was published (*release/knowledge date*),
with revisions producing several values for one observation date. With only one dimension, strict
intersection cannot express "this M2 print for March was not knowable until mid-April", so a backtest
aligning price to macro on observation date consumes information from the future. Nothing in the current
code prevents it; only the absence of macro data does.

**This is the finding most likely to force an expensive refactor**, because the fix changes the shape of a
canonical model that the alignment service, the RVE, and every future backtest will already depend on.
Three options, in increasing cost-if-delayed:

1. **Add an optional parallel `knowledge_timestamps` tuple to `ObservationSeries` now** (same length,
   `None` meaning "observation-dated, revision-unaware"). Cheap today; additive; makes the look-ahead test
   writable immediately; forces alignment to state whether it matches on observation or knowledge time.
2. **Introduce a separate `VintagedSeries` model when macro arrives**, leaving `ObservationSeries`
   untouched. Keeps today's model minimal but means alignment, the RVE, and their tests must eventually
   handle two series types, or the RVE must be generalized after it is written.
3. **Accept the gap**, and record honestly that the look-ahead guarantee is *aspirational* until macro
   ingestion exists.

**Recommendation: option 3 for now, with the guarantee downgraded in the documentation, and the
availability-time model (option 1's substance) executed as its own milestone before any macro or vintage
work — never alongside it.** The important immediate action is to stop describing a structural guarantee
that the code does not provide.

**Resolution (2026-07-24): accepted — the guarantee is corrected and macro/vintage data is gated.**
Recorded in [ADR-0003](adr/ADR-0003-availability-time-boundary.md). The documentation now distinguishes
four things explicitly: (i) market candle observations currently represent completed market events;
(ii) canonical timestamps are exact instants; (iii) the current `ObservationSeries` model does **not**
represent release/publication/revision/knowledge time; (iv) no-look-ahead protection for
macro/released/revised/vintage data is therefore **planned, not implemented**. Macroeconomic,
fundamental-release, revised, and vintage datasets **must not be integrated until an explicit
availability-time model is designed and accepted**, and that model is recorded as a required precursor
milestone. The exact model shape (parallel `knowledge_timestamps` vs a separate `VintagedSeries`) is left
to that milestone's design, driven by a real data source.

**Separately and cheaply:** the crypto-vs-equity mixed-calendar test (7-day vs 5-day series, verifying
dropped observations are counted rather than absorbed) *is* writable today against the existing code and
was also listed in the Milestone I acceptance criteria. It is missing and is scheduled with Milestone I-E.

## R4 — `_timeutils` is private but is a system-wide contract *(architectural risk)*

`validate_utc_timestamp` defines the canonical time rule for the entire system (ADR-0001), yet lives in a
leading-underscore module inside `fmis.data`. Every future layer that handles a timestamp — provider
adapters normalizing exchange time, the RVE stamping an `as_of`, risk recording an entry time, execution,
persistence — needs the same rule.

A private module has exactly two futures: it gets imported across package boundaries anyway (making the
underscore a lie), or the rule gets re-implemented slightly differently somewhere else (the precise
failure that `sources.py` and `ema_math.py` were extracted to prevent). The precedent for the fix is
already in the repository: shared, dependency-free kernels are legitimate and may be imported by anything
(architecture doc §5.1).

**Recommendation: promote it to a public shared kernel at the point of second use** — either
`fmis.data.timeutils` (public, staying with the models it validates) or a top-level `fmis.time`. No action
required today, because there is exactly one consumer package; the trigger is the first import from
outside `fmis.data`.

## R5 — A feature returns only its latest value, which makes backtesting quadratic *(architectural risk)*

Every implemented indicator computes the full series internally and returns **only the last element**
(`ema_series(prices, period)[-1]`; the final ATR/RSI after the smoothing loop). `FeatureResult.value` is a
scalar describing the most recent closed bar, and `FeatureSet.as_of` is a single timestamp.

For the current use — "what are the indicators right now" — this is exactly right and pleasantly simple.
For backtesting it is not: replaying `N` bars requires calling `compute()` once per bar with a truncated
series, and each call recomputes the whole history. That is **O(N²)** work per feature, and the cost is
structural rather than an optimization detail.

The important part is not the performance number; it is that the fix touches the `Feature` protocol — the
most-depended-on contract in the codebase. Two ways out, both of which should be *chosen deliberately*
rather than discovered under pressure during the backtesting milestone:

- **Additive (preferred):** extend the protocol with an optional `compute_series(context)` returning the
  full aligned series, defaulting to the current behaviour. Existing features keep working; the engine
  gains a "backtest mode"; nothing breaks. The `Feature` protocol is a `Protocol`, so this is genuinely
  additive.
- **Structural:** make features incremental/streaming (carrying state across bars). Much faster, and much
  harder to keep pure, reproducible, and testable — it trades away the property the project values most.

**Recommendation: no action now; record the additive path as the intended one so the backtesting milestone
does not reopen the protocol from scratch.** Notably, the `FeatureValue` union already permits a
`Sequence`, so a series-valued result needs no contract change either.

## R6 — `AlignmentReport` omits `missing_count` and `staleness`, and one of them should stay omitted *(documentation)*

The architecture document (§7.3, §10, §14) requires the report to carry retained observations,
`alignment_loss`, `missing_count`, and staleness. The implementation provides `input_series_count`,
`aligned_observation_count`, `common_start`, `common_end`, and per-series
`original_count`/`aligned_count`/`dropped_count`.

Reviewing the omissions rather than simply filing them as debt:

- **`missing_count` is not yet well-defined.** "Missing" presupposes an expected grid — a calendar or
  frequency against which absence is measured. Strict intersection has no such grid; it only knows which
  instants each series actually contains. `dropped_count` already answers the meaningful question ("how
  many of this series' observations did alignment discard"). A true `missing_count` becomes definable only
  when an explicit expected-frequency or calendar concept exists, which is deliberately out of scope.
- **`staleness` should not live in the alignment report at all.** Staleness is *age relative to some
  reference instant*. Computing it requires either the wall clock — which would break the reproducibility
  principle outright (same inputs must always give the same outputs) — or an injected `as_of`, which
  alignment does not and should not take. It belongs to the layer that legitimately owns an evaluation
  instant: the RVE result. The design in [RVE_DESIGN_V1.md](RVE_DESIGN_V1.md) places it there.

**Recommendation: no code change. The specification is what should move** — `missing_count` deferred until
a calendar concept exists, `staleness` reassigned to the RVE. Recorded here so the omission reads as a
decision rather than an oversight.

## R7 — Vocabulary drift: `alignment_loss` vs `dropped_count` *(documentation)*

The document says `alignment_loss`; the code says `dropped_count` (per series). They mean the same thing.
Harmless in isolation, but the RVE output schema in §7.6 also uses `alignment_loss`, so the two will meet.
**Recommendation: keep the code's `dropped_count` as the per-series field name and use `alignment_loss`
only for a future aggregate figure, or align the names when the RVE result object is built.** Decide once,
at RVE implementation time; noted so it is not decided twice.

## R8 — The engine has no `as_of`; the caller's truncation duty is unwritten *(documentation)*

`FeatureEngine.compute()` uses every closed candle it is given, and stamps `as_of` from the last one.
There is no way to say "evaluate as of time T against a longer series". This is a reasonable design — it
keeps the engine pure and the truncation responsibility in one place — but the responsibility is
**implicit**, and backtesting correctness depends entirely on it.

**Recommendation: state the contract explicitly in the documentation (done):** *the caller is responsible
for supplying only data knowable at the evaluation instant; the engine performs no truncation and has no
notion of "now".* Alternatively add an explicit optional `as_of` parameter that truncates internally —
more foolproof, slightly less pure. Not urgent; must be settled before the backtesting milestone.

## R9 — `alignment.py`'s module docstring describes a policy the UTC contract made unreachable *(documentation, in code)*

The docstring's timezone/timezone-equality section still explains that `2026-01-01T10:00+00:00` and
`2026-01-01T11:00+01:00` are the same instant and therefore intersect, and carries a caveat about DST-aware
`zoneinfo` zones and `fold`. Since `5e7e3d5`, **neither situation is constructible** — a fixed `+01:00`
offset and any DST-aware zone are both rejected by `ObservationSeries`. The corresponding *tests* were
correctly migrated in that commit; the docstring was not.

It is not wrong, only obsolete, and it invites a future reader to believe the module defends against
hazards that the model now prevents. **Recommendation: rewrite the docstring to reference ADR-0001 and
state the simpler truth — all timestamps are canonical UTC, so instant equality is exact.** Left unchanged
here because this review is documentation-only and the file is production code; it is a one-commit
follow-up.

## R10 — The "`fmis.data` imports nothing internal" invariant needs restating *(documentation)*

`REPOSITORY_MAP.md` records that `fmis.data` "imports nothing internal — this is verified and must stay
true". With `_timeutils`, `observation`, and `alignment` added, the package's modules now import **each
other**, which is correct and harmless. The invariant that actually matters is: **`fmis.data` imports
nothing from outside `fmis.data`.** Restated in this review's documentation updates.

## R11 — The `float` decision was scoped to market data; money has no decision yet *(note for a future layer)*

`models.py` documents deliberately: OHLCV uses `float`, and `Decimal` is "deferred and will be
reconsidered later for money, accounting, order sizing, and execution". That reasoning is sound and the
deferral is explicit — but it lives only in a module docstring, while the layers it constrains (Risk,
Portfolio, Execution) are governed by the architecture document, which never mentions it.

**Recommendation: no action now; the Risk/Portfolio milestone must open with an explicit money-type
decision (an ADR), not inherit `float` by default.** Surfaced here so the deferral is not silently
forgotten at exactly the moment it matters.

## R12 — `fmis.features` transitively imports the alignment service *(minor)*

`fmis/features/types.py` does `from fmis.data import CandleSeries`, which executes `fmis/data/__init__.py`
and therefore imports `observation` and `alignment` — code the Feature Engine is architecturally forbidden
to use. There is no cycle and no correctness issue; it is import-time coupling only. It resolves itself if
R2 moves alignment out of `fmis.data`. Otherwise, importing `from fmis.data.models import CandleSeries`
would express the narrower dependency. **Very low priority; listed for completeness.**

## R13 — `is_closed` is caller-supplied, so the closed-candle guarantee is only as strong as ingestion *(note for the adapter layer)*

The closed-candle rule is enforced rigorously *within* the system — at the engine and again inside every
feature, idempotently. But `Candle.is_closed` is simply a constructor argument, validated for nothing.
Today the only constructors are tests and fixtures, so the risk is zero. The moment a provider adapter
exists, correctly determining "is this bar final?" — from bar timestamp, interval, and the provider's
own semantics — becomes that adapter's single most consequential responsibility, and getting it wrong
would silently reintroduce repainting everywhere downstream.

**Recommendation: record it as an explicit obligation in the adapter-layer specification (done).**

## R14 — Duplicated responsibilities: none found

Checked deliberately, since it was in scope. EMA math is shared via `ema_series`; the OHLC source
vocabulary is shared via `sources.py`; per-model validation is per-model invariants rather than
duplication; and the double `closed()` call (engine and feature) is a deliberate, documented, idempotent
redundancy. `Candle` and `ObservationSeries` validate timestamps through **one** shared function. No
divergent re-implementations exist.

---

# 5. Divergences from ARCHITECTURE_AND_ROADMAP_V1

| # | Document says | Code does | Resolution |
|---|---|---|---|
| 1 | Alignment in a separate module, e.g. `src/fmis/alignment/` (D4, §10) | `src/fmis/data/alignment.py`, re-exported from `fmis.data` | **Decided (R2)** — move to `fmis.alignment` ([ADR-0002](adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md)); code move is Milestone I-E |
| 2 | Milestone I delivers a `CandleSeries → ObservationSeries` helper (§10, §14) | Not implemented | **Build it (R1)** in Milestone I-E — prerequisite for Milestone J |
| 3 | `AlignmentReport` carries `missing_count` and staleness (§7.3, §10, §14) | Neither present | **Amend the spec (R6)** — `missing_count` undefined without a calendar; staleness belongs to the RVE |
| 4 | Look-ahead bias is "structurally prevented" (§7.3); a no-look-ahead test is Milestone I acceptance (§14) | No knowledge-date dimension exists; the test is unwritable | **Decided (R3)** — claim corrected; macro/vintage data gated until an availability-time model is accepted ([ADR-0003](adr/ADR-0003-availability-time-boundary.md)) |
| 5 | Mixed-calendar (crypto vs equity) test is Milestone I acceptance (§10, §14) | Missing | **Add the test** in Milestone I-E — writable today, cheap |
| 6 | Field named `alignment_loss` (§7.3, §7.6) | `dropped_count` | **Reconcile at RVE implementation (R7)** |
| 7 | 147 tests (§2.6 and three other documents) | 218 tests | **Corrected** in this review's documentation updates |
| 8 | `fmis.data` "imports nothing internal" | Intra-package imports exist and are correct | **Restated (R10)** as "imports nothing from outside `fmis.data`" |

Divergences 7 and 8 are documentation lag and are fixed by this review. Divergences 3, 4, and 6 are
specification corrections argued above (4 now an accepted decision). Divergences 1 and 2 are resolved by
decision and scheduled work (Milestone I-E); 5 is scheduled with the same milestone.

---

# 6. What is confirmed healthy

Stated explicitly, because a review that lists only problems misrepresents the system:

- **No circular dependencies. No upward imports. No hidden coupling** beyond the trivial import-time note
  in R12. The graph was extracted from source, not assumed.
- **No missing abstraction layer in what exists.** Every seam the roadmap needs — model vs service, math
  vs orchestration, indicator vs interpretation, deterministic vs AI — is already present as a real
  boundary, not just a naming convention.
- **The immutability discipline is uniform**: frozen slotted dataclasses everywhere, tuple normalization
  at construction, `MappingProxyType` for metadata and for MACD's structured value, defensive copying of
  caller-supplied inputs. Tests assert it rather than trusting it.
- **Warm-up and insufficient-data handling is exemplary** — derived, documented, tested on both sides of
  the boundary, and never a guessed number.
- **Scope boundaries are test-enforced, not merely written down.** `FeatureCategory` is asserted to be
  technical-only, with named forbidden members.
- **Zero runtime dependencies**, reproducible environment, and a test suite that runs in 0.07 s — which is
  itself an architectural asset: it makes the review-first workflow costless.

---

# 7. Readiness verdict

The architecture is **sound and does not require restructuring.** No boundary needs to be redrawn, no
layer is missing from the design, and nothing built so far will need to be rewritten.

Before Milestone J (RVE v1a) begins, both blocking items are now **decided** and folded into a single
implementation milestone, **I-E — Observation Reduction & Alignment Boundary** (under a separate prompt):

1. **R1** — implement the `CandleSeries → ObservationSeries` reduction, with explicit price-field
   selection and tests. Without it the RVE has no input.
2. **R2** — move the alignment service to `fmis.alignment`
   ([ADR-0002](adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md)).

Folded into the same milestone because they are cheap now and awkward later: the missing mixed-calendar
alignment test (§5, divergence 5), and the `alignment.py` docstring correction (R9).

R5 needs no action now but should not be rediscovered under deadline before backtesting. **R3 is decided**
([ADR-0003](adr/ADR-0003-availability-time-boundary.md)): macro/fundamental/revised/vintage data is gated
until an availability-time model is designed and accepted — a required precursor milestone, not near-term.
R11's money-type choice needs its own ADR before Risk/Portfolio/Execution are built.
