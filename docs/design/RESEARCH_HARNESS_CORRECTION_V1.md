# Research Harness Correction V1 — warm-up, window boundaries, counterfactual replay

**Milestone:** BC
**Status:** Implemented
**Date:** 2026-08-11
**Model:** Claude Opus 5
**Type:** Design + implementation record for a research-infrastructure correction.
**Scope guard:** This document changes no trading policy. `CONFIRMATION_LOOKBACK_BARS` is still
`10`. No threshold was tuned, no indicator added, no AI introduced, and no claim of improved
trading performance is made anywhere in this milestone.

---

## Table of contents

- [1. What BB found, and what had to change](#1-what-bb-found-and-what-had-to-change)
- [2. The four boundaries](#2-the-four-boundaries)
- [3. Deriving the warm-up prefix](#3-deriving-the-warm-up-prefix)
- [4. Measured data availability, and the window it permits](#4-measured-data-availability-and-the-window-it-permits)
- [5. The research-only policy override](#5-the-research-only-policy-override)
- [6. Opportunity identity, and the AV defect it replaces](#6-opportunity-identity-and-the-av-defect-it-replaces)
- [7. Why a replay and not a post-filter](#7-why-a-replay-and-not-a-post-filter)
- [8. Temporal segments](#8-temporal-segments)
- [9. No-lookahead, re-argued under the new boundaries](#9-no-lookahead-re-argued-under-the-new-boundaries)
- [10. Module map](#10-module-map)
- [11. Rejected alternatives](#11-rejected-alternatives)
- [12. What the corrected harness measured](#12-what-the-corrected-harness-measured)
- [13. What this milestone does not fix](#13-what-this-milestone-does-not-fix)

---

## 1. What BB found, and what had to change

Milestone BB (`docs/design/CONFIRMATION_FRESHNESS_POLICY_DECISION_V1.md` §2.3, §5.2) found two
research-validity defects in the AV–BA chain. Neither is a bug in the arithmetic; both are defects
in what the numbers were *about*.

**Finding #1 — the window meant the wrong thing.** `run_backtest` fetched exactly
`[start_time, end_time]` and treated the whole of it as the measurement period. The context-role
regime needs the moving-average family, which needs weekly EMA(50), which yields nothing until 50
closed weekly candles exist. On a 400-day fetch that is roughly the first 350 days. BB's derivation
lands on 2026-06-22 as the first instant any `CONFIRMED` result was structurally possible — the same
calendar day as the first `confirmed_at` in BA's own table. A "400-day backtest" was a **43-day**
measurement with a 357-day silent prefix inside it.

**Finding #2 — the counterfactual was emulated by deletion.** BA answered "what would a stricter
confirmation-age bound have produced?" by removing already-observed stale confirmations. Read
against `policy.py`, that is not the counterfactual. When `break_is_stale` is true the assessment
becomes `CANDIDATE`, not `WAIT`: the candidate survives, keeps watching a level, and
`_latest_matching_break` will select a *new* break on the confirming side if one occurs later — at
which point the setup confirms at a different bar, a different reference price, a different stop and
a different target. A filter can only ever return a subset of what was already seen. It is
structurally incapable of producing the deferred confirmation.

Both are infrastructure problems, and this milestone fixes the infrastructure.

---

## 2. The four boundaries

`ResearchWindow` (`fmis.swing_setup.research_models`) carries four instants instead of two:

```
warmup_start        measurement_start   measurement_end   outcome_tail_end
     |───── warm-up ──────|──── measured ─────|───── tail ─────|
     indicators warm here  observations count  outcomes resolve
     nothing is counted    setups form here    no setup forms
```

**Measurement is half-open.** An instant `T` is measured exactly when
`measurement_start <= T < measurement_end`. Half-open rather than closed for two reasons: segments
tile the window without a shared endpoint that would be counted twice, and `measurement_end` names
one unambiguous instant — the first that is *not* measured.

The three phases partition time, and a test asserts that every instant satisfies exactly one of
`is_warmup` / `is_measured` / `is_tail`.

**What each phase may do.**

| Phase | May initialize state | May be counted | May create a setup | May resolve an outcome |
|---|---|---|---|---|
| Warm-up / priming | yes | **no** | no (none is recorded as measured) | no |
| Measured | yes | yes | yes | yes |
| Outcome tail | — | **no** | **no — instants there are never replayed** | yes |

The tail rule is enforced at the strongest available point: the harness's instant list is filtered
to `priming_start <= instant < measurement_end` before any composition call is made, so there is no
code path on which a tail instant could produce an observation at all.

**Identity priming.** An opportunity already running when the window opens would otherwise be
counted as beginning there. `DEFAULT_IDENTITY_PRIMING_BARS = 60` execution-role bars are replayed
immediately before `measurement_start` purely to prime the opportunity tracker. Those observations
are recorded — a reader can see them — and carry `in_measurement=False`, which excludes them from
every denominator. An opportunity whose *first* confirmation falls in the priming window produces no
outcome, because the decision was not made inside the measured window; the count of such
opportunities is reported in run metadata.

---

## 3. Deriving the warm-up prefix

AV's 400-day default was hand-derived from one dependency someone thought of. The correction is not
a better hand-derived number; it is a derivation that asks the production objects themselves
(`fmis.swing_setup.research_warmup.derive_warmup`).

**Components, per role.**

| Component | Number read from | Value at defaults |
|---|---|---|
| Every feature in `regime_features()` | the feature's own result metadata (`warmup_bars` / `warmup_candles`) | EMA(200) → 200 binds; ATR(50) → 51; MACD → 34; RelVol(20) → 21; EMA(50) → 50; RSI/ATR(14) → 15 |
| Structural detection | `fmis.market_structure.required_candles(left, right)` | 5 |
| Regime transition lookback | `RegimePolicy.transition_lookback_bars` | policy default |
| Confirmation staleness (execution role only) | `fmis.swing_setup.policy.CONFIRMATION_LOOKBACK_BARS` | 10 |
| **Requested analysis window** | the `limit` the harness passes to `multi_timeframe_facts_for_symbol` | **250** — binds |

A feature is *asked*, by computing it against a two-candle probe series and reading the warm-up its
own metadata declares. A feature that declares none raises rather than scoring zero: silently
treating an unknown requirement as satisfied is exactly the failure BB found, and it must fail
loudly rather than quietly.

**The requested analysis window is a warm-up component, and this is the part that is easy to miss.**
The composition path asks for `limit` candles at every role and reads whatever it gets. A role
holding fewer than `limit` closed candles is analysed over a **shorter window than production
uses** — fewer swings detected, fewer structural levels, a different assessment — even when every
indicator has a value. That is warm-up truncation, so it is counted as one.

**The requirement is per role, and the cost is per role's unit.** The same 250 bars costs 250 days
at `1d`, 41.7 days at `4h`, and **250 weeks — 1750 days — at `1w`**. The weekly context role
dominates every crypto window, because weekly history is the shortest history there is.

**Fetching is per interval, not per prefix.** Each interval is fetched from
`measurement_start − warmup.for_interval(interval) − priming`. Fetching all three from the global
1750-day prefix would pull tens of thousands of 4H rows no execution decision can read. The priming
term is added to *every* interval, because a priming instant analysed over a slightly short window
could read a different direction, and the tracker it primes is what decides whether an opportunity
at the boundary counts as beginning inside the window.

**The claim is checked, not asserted.** At every measured instant the harness records, per role,
whether any feature was still warming up and whether the role held fewer closed candles than the
harness requested; the minimum closed count seen at each role is reported in run metadata and
printed on the report. A derived prefix that is right in theory and wrong in practice would look
exactly like AV's — every number reconciling over a window that cannot produce a result — and these
counters are what make that falsifiable rather than argued.

At the harness defaults the derived prefix is **1750 days (250 weeks)**, and the breakdown is
printed on every research report.

---

## 4. Measured data availability, and the window it permits

Part 3 of the brief says *measure, do not assume*. `probe_availability` asks the provider for each
series' earliest and latest candle directly, and reports whether the requested window is satisfiable
per `(symbol, interval)` with the shortfall stated as a duration.

Measured on 2026-08-11 for the ten AV symbols, the weekly (binding) role begins:

| Symbol | First weekly candle | 250 weekly candles complete at |
|---|---|---|
| BTCUSDT, ETHUSDT | 2017-08-14 | 2022-06-06 |
| BNBUSDT | 2017-11-06 | 2022-08-29 |
| ADAUSDT | 2018-04-16 | 2023-02-06 |
| XRPUSDT | 2018-04-30 | 2023-02-20 |
| LINKUSDT | 2019-01-14 | 2023-11-06 |
| DOGEUSDT | 2019-07-01 | 2024-04-22 |
| SOLUSDT | 2020-08-10 | 2025-05-26 |
| DOTUSDT | 2020-08-17 | 2025-06-02 |
| **AVAXUSDT** | **2020-09-21** | **2025-07-07** ← binds |

The prefix must also cover the identity-priming replay (§2), which is 60 execution-role bars — ten
days. **The common measurement window is therefore bounded below by 2025-07-17**, and the study uses
`2025-07-17 → 2026-08-01` — 380 days — with a 10-day outcome tail to 2026-08-11.

An unsatisfiable window **raises with the measured shortfall** rather than being quietly shortened.
That refusal is the whole point: silently measuring less than was asked for, and reporting it under
the requested dates, is how a 400-day claim came to mean 43 days.

**This is a trade, and it is stated rather than hidden.** A per-symbol window would give BTCUSDT
four years instead of thirteen months. A common window was chosen because symbol comparisons are
otherwise not comparisons at all (limitation `BC-3`).

---

## 5. The research-only policy override

`evaluate_setup` gains exactly one parameter:

```python
def evaluate_setup(
    inputs: SetupInputs,
    *,
    research_confirmation_max_age: int | None = None,
) -> SetupAssessment:
```

**Containment, by four independent mechanisms** (`tests/test_swing_setup_research_boundary.py`):

1. **Default identity.** Omitted, the production constant applies and the result is byte-identical
   to what the function returned before the parameter existed. Tested at five break ages.
2. **Signature containment.** `setup_assessment_for_sheet`, `setup_for_symbol`,
   `run_setup_for_symbols` and `run_market_scan` — the four functions the live product calls —
   neither accept it nor take `**kwargs` through which it could arrive. Checked against the real
   signatures, not by reading source. The single reachable seam is
   `setup_inputs_and_assessment_for_sheet`, which the historical research harness already used.
3. **Call-site containment.** A scan of `src/fmis/**` asserts that only `policy.py` (defines),
   `compose.py` (forwards) and `swing_setup/research_*.py` (uses) name it at all.
4. **Self-identification.** Every assessment produced under the override carries
   `policy_id = "swing-setup-v1+research(max_confirmation_age=N)"` and a limitation line reading
   `RESEARCH OVERRIDE ACTIVE`. A research artifact filed as a production one is therefore detectable
   after the fact, not merely improbable.

It is deliberately **not** a policy object. A `ResearchPolicy` dataclass alongside `RegimePolicy`
would look like a first-class second policy and would eventually be passed from somewhere it should
not be. An `int | None` named `research_*` reads, at every call site, as what it is.

`ResearchPolicyVariant` names a variant for a *run*; it is never read by `evaluate_setup`, which
takes an `int`. The variant object cannot change behaviour; it can only describe it.

At the CLI, `--max-confirmation-age` requires `--research` and exits non-zero without it.

---

## 6. Opportunity identity, and the AV defect it replaces

**A defect found while building this milestone, not previously reported.**
`fmis.swing_setup.backtest_identity.setup_identity` keys a setup on
`Trigger.level.origin.index` — the pivot's position in the closed-candle sequence. That sequence is
the sliding analysis window, so a *fixed* swing's index falls by one every bar. The identity
therefore changes every bar even when nothing about the market has.

Measured directly on a real 400-day BTCUSDT AV run: **48 of 48 directional observations report
`is_new_setup=True`**. Measured across all ten symbols on the same window: **549 "unique setups"
from 552 directional observations, and 186 "unique confirmed setups" from 186 confirmed
observations** — a 1:1 ratio in both cases. AV's "unique setups" is a count of directional bars, and
`is_first_confirmation` fires on essentially every confirmed bar rather than once per setup — so one
persisting confirmed setup is outcome-evaluated many times, inflating the outcome count with
near-duplicate, highly correlated rows.

BC does not change AV's identity (that would rewrite a published milestone's behaviour). It defines
its own, in `fmis.swing_setup.research_identity`:

> An **opportunity** is a maximal run of consecutive observations for one symbol carrying the same
> `Direction`, uninterrupted by a `WAIT` or a direction flip. Its key is the symbol, the direction,
> and the instant the run began.

The property that makes this the right key for *this* milestone: **it is invariant to the
confirmation-age override.** The override changes only `break_is_stale`, which decides `CONFIRMED`
versus `CANDIDATE`. It cannot change whether a direction exists — that is settled earlier, by the
decision-context gate, the context-role regime gate and the family tally, none of which it touches.
Two variants replayed over the same candles therefore decompose history into the *same*
opportunities, and a test asserts exactly that. Without it, "the variant produced fewer
confirmations" would be uninterpretable; with it, each of the brief's five lineage questions is a
join on a stable key.

This is research lineage. It defines no trading object and makes no claim that one run of
directional bars is one trade (limitation `BC-4`).

---

## 7. Why a replay and not a post-filter

Each variant replays **every** measured instant through the production composition path with the
bound supplied. Nothing is filtered.

`research_compare.post_filter_comparison` then reproduces BA's method — keep the baseline
confirmations whose recorded break age already satisfies the bound, drop the rest — and sets it
beside the replay's own result:

| Field | Meaning |
|---|---|
| `post_filter_kept` | what BA's method produces |
| `replay_confirmations` | what replaying the policy under that bound produces |
| `only_in_post_filter` | kept by the filter, not produced by the replay |
| **`only_in_replay`** | **the population a filter cannot reach** — a confirmation that exists *because* a stricter bound deferred a candidate onto a later, fresher break |
| `agreement_rate` | the two populations' Jaccard agreement |

`confirmation_break_age_bars` is now persisted on every observation. BB noted it never was, which is
why the filter it criticised could not be checked against a real replay in the first place.

The deferral lifecycle is proved offline and deterministically, not only on live data: the synthetic
fixture in `tests/test_swing_setup_research.py` produces a baseline confirmation on a 3-bar-old
break that, under a 1-bar bound, is deferred and re-confirms later — `shifted_later >= 1`,
`removed == 0`, `only_in_replay >= 1`.

---

## 8. Temporal segments

Segments are equal-length half-open slices of the measurement window, cut by a ladder fixed in code
and independent of any result: **yearly** when two or more years fit, **half-yearly** when two halves
fit, **quarterly** otherwise. Boundaries come from the ladder and the window's length — never from
where outcomes happened to fall, which would be subgroup-shopping.

At the study's 380-day window the ladder selects **two half-year segments**. Finer temporal
resolution is reported separately, by week / month / year, in the concentration report.

---

## 9. No-lookahead, re-argued under the new boundaries

The replay mechanism is unchanged: a `Transport` bound to instant `T` pre-filters to
`close_time < T`, and `fetch_klines` independently re-derives `is_closed` from the same clock. Two
independent checks over one boundary. What BC adds is a third boundary system on top, and each
property below is a test:

| Property | Test |
|---|---|
| A changed **warm-up** candle *may* legitimately change later state | `test_a_changed_warmup_candle_may_legitimately_change_later_state` (asserts it does — a harness where it did not would be ignoring its own warm-up) |
| A changed **future measurement** candle cannot alter an earlier decision | `test_a_changed_future_measurement_candle_cannot_alter_an_earlier_decision` |
| A changed **outcome-tail** candle cannot alter the setup that preceded it | `test_a_changed_tail_candle_moves_an_outcome_but_no_observation` |
| Tail candles resolve outcomes but create no measured observation | same test — outcomes differ, observations byte-identical |
| Warm-up observations never enter reported counts | `test_warmup_observations_are_recorded_and_never_counted` |
| `measurement_start` / `measurement_end` respected exactly | `test_the_measurement_window_is_exact_at_both_edges` |

The tail test is constructed rather than incidental: the measurement window is closed two bars after
a real confirmation so that confirmation's entire resolution path lies in the tail, which is the only
arrangement under which the property is actually exercised.

**A performance change with a correctness obligation.** `prepare_replay_index` replaces the
transport's linear scan with a binary search over close times, because a multi-variant study over a
properly warmed dataset would otherwise pay a cost that grows with the *length of history* — the
opposite of what this milestone is for. It changes no result, and a test asserts byte-identical
responses with and without it. An unsorted series is rejected rather than binary-searched.

---

## 10. Module map

| Module | Holds |
|---|---|
| `research_models.py` | `ResearchWindow`, `WarmupRequirement`/`RoleWarmup`/`WarmupComponent`, `ResearchPolicyVariant`, `TemporalSegment`, `SeriesAvailability`/`AvailabilityReport`, `ResearchObservation`, `ResearchBacktestRun`, `ConfirmationRecord`, `VariantComparison`, `PostFilterComparison` |
| `research_warmup.py` | the warm-up derivation and the availability probe |
| `research_identity.py` | `opportunity_key`, `OpportunityTracker` |
| `research_harness.py` | the fetch, the replay loop, `build_segments`, `run_research_study` |
| `research_metrics.py` | per-variant aggregates and `ConcentrationReport` |
| `research_compare.py` | `compare_variant`, `post_filter_comparison` |
| `research_render.py` | the terminal report and availability page |

`ResearchBacktestRun` is deliberately **not** `BacktestRun`. An AV run and a BC run answer different
questions over different windows, and one type would invite reading a corrected number as a
regression against an under-warmed one.

---

## 11. Rejected alternatives

| Alternative | Why rejected |
|---|---|
| Change `CONFIRMATION_LOOKBACK_BARS` to a `RegimePolicy`-style policy object | Reads as a first-class second production policy; would eventually be passed from a production call site. The override is deliberately awkward to reach |
| Extend `run_backtest` in place | AV's results are published. Silently changing what `fmits backtest` means would make report 0011 wrong retroactively. `--research` opts in; the default path is untouched |
| Treat the warm-up prefix as "50 weekly candles, as BB derived" | Covers one dependency. The derivation exists so the next added feature does not repeat AV's mistake |
| Exclude the requested `limit` from the warm-up requirement | Would buy a year of measurement window by analysing early instants over a shorter window than production uses — the exact class of defect being corrected |
| Per-symbol measurement windows (longer for older symbols) | Longer sample, incomparable symbols. Stated as `BC-3` rather than taken |
| Fix `backtest_identity` in place | Rewrites a published milestone's behaviour. BC adds its own identity and reports the AV defect instead |

---

## 12. What the corrected harness measured

Full figures are in [report 0012](../../reports/0012_2026-08-11_RESEARCH_HARNESS_CORRECTION_IMPLEMENTATION.md);
the four that matter to this design record:

| Claim this design makes | Measured |
|---|---|
| The window is fully warm at every measured instant | 0 role-views warming, 0 below the requested 250-candle window, 0 insufficient-data instants; minimum closed candles 250 / 250 / 250 across ~160,000 instants |
| The usable period is much larger than BB's | AV: outcomes span **41 days** of a 400-day window. BC: **380 days**, all usable — a 9.3× increase |
| Concentration materially improves | Largest 5-day cluster **49.0 % → 11.4 %**; distinct confirmation days 23 → 35; outcomes in 10 months across 2 years rather than 2 months in 1 |
| The override reproduces production exactly | Replaying at the production bound of 10: 45 baseline confirmations, 45 variant, **45 unchanged, 0 shifted, 0 lost, 0 new**, identical outcomes |

And the one the milestone exists to close — BB finding #2, at `max_age = 2`:

| Method | Confirmations | Target / stop | Target-first |
|---|---|---|---|
| BA-style post-filter over the baseline | 21 | 12 / 6 | 66.7 % |
| True counterfactual replay | 39 | 19 / 12 | 61.3 % |

**18 of the replay's 39 confirmations do not exist in the post-filtered population at all**, and the
two methods agree on 53.8 % of their union. The post-filter is not a noisier estimate of the same
thing; it is a measurement of a different, smaller population.

---

## 13. What this milestone does not fix

- **Co-movement.** Ten crypto majors over one common window remain highly correlated, and 60-bar
  evaluation windows overlap. A larger, better-warmed sample reduces concentration; it does not make
  observations independent (`BC-8`).
- **The weekly-history ceiling.** 250 weekly candles is nearly five years, and the youngest symbol
  has six. The common window is thirteen months because the data does not exist, not because the
  harness stopped early (`BC-3`).
- **AV's identity defect, in AV.** Reported here and corrected only inside the research layer.
- **Anything about policy.** No confirmation-age bound is recommended, selected, or described as
  better. The variant table is sensitivity evidence.
