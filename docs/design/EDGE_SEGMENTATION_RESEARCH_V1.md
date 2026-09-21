# Edge Segmentation Research V1

**Milestone:** AY
**Status:** Investigation complete — measurement only, no code changes
**Date:** 2026-08-10
**Model:** Claude Sonnet 5
**Repository state:** `main`, working tree unchanged by this milestone under `src/`, `tests/`,
`docs/adr/`, `FMITS_PRODUCT_BACKLOG.md`, `FMITS_PRODUCT_CHANGELOG.md`
**Type:** Research investigation, not a design record — produces no contract, no ADR, no backlog
entry, no strategy change, no filter proposal, no threshold proposal, no ranking of what the
product should do next

---

## 0. What this document is

Milestone AV measured whether the system wins (47.4% target-first / 52.6% stop-first on raw
wick-touch counts; 46.6% win rate among resolved outcomes once `AMBIGUOUS_SAME_BAR` and
`NEITHER_WITHIN_WINDOW` are excluded — report 0011). Milestone AW measured whether the three
evidence families are independent (they are not: 75–79% pairwise agreement when both are
directional). Milestone AX measured which individual evidence observations, inside those families,
earn their place. This document asks the next question, unanswered by any of the three: **where**,
inside the outcomes those milestones already measured, does whatever edge exists concentrate —
and where does it vanish or invert?

This is not a new backtest and not a new metric. Every number below is a segmentation of the
identical 146 evaluated outcomes (133 resolved) Milestones AV/AW/AX already produced, cut along
axes that were already computed by the deterministic pipeline but never persisted onto
`HistoricalObservation`, plus a small number of arithmetic derivations (percentages, quartile
buckets, correlation coefficients) over those already-computed facts. No new indicator, no new
regime dimension, no new threshold, and no strategy line changed to produce any figure in this
document.

**Not a recommendation.** No sentence below says a threshold, a filter, or a policy *should*
change. Sections 8/9 ("where FMITS appears strongest/weakest") report descriptive extremes of the
existing, unmodified policy's own historical outcomes — never a proposal to act on them. Section 10
exists specifically to warn against over-reading them.

---

## 1. Method

### 1.1 Data source

One fresh, read-only extraction, mirroring `fmis.swing_setup.backtest_harness.run_backtest`'s own
instant-by-instant replay loop exactly — same replay transport, same clock, same
`IdentityTracker`, same call to `setup_inputs_and_assessment_for_sheet`, same call to
`evaluate_outcome` at `is_first_confirmation` — so every count reconciles against the production
harness and against AW's and AX's independent draws from the same population (§2.2). The
extraction script lives outside the repository, in a scratch directory, per the precedent AW and AX
set; it is described in full in the Appendix.

Beyond the replay loop itself, the script makes a small number of **additional read-only calls** to
already-public, already-used pure functions, to recover facts the production
`HistoricalObservation`/`SetupOutcome` models compute internally but do not persist:

- `fmis.pipeline.regime.regime_for_sheet`, called a second time on the SETUP (1D) and EXECUTION
  (4H) role sheets — `compose.py` already calls this once per role internally
  (`compose.py:315-317`) and discards the SETUP/EXECUTION results before building
  `SetupInputs`; only the CONTEXT (1W) role's regime survives onto `HistoricalObservation`.
- The `atr_14`/`atr_50` feature values already present on each role's `StructuralFactSheet.features`
  (`regime_features()` already includes both — `fmis/pipeline/regime.py:124-136` — and
  `fmis.market_regime.classify._volatility_dimension` already reads both to classify
  `VolatilityState` as a fast/slow **ratio**; this script reads the same two numbers directly,
  normalized by that role's own close price, to get a magnitude rather than only a change-direction
  verdict).
- The identical `break_age` arithmetic `fmis.swing_setup.policy.py:344-348` already performs
  internally to gate confirmation staleness (`execution_closed_count - 1 - matching_break.index`,
  searching `execution_breaks` backward for the first match on the confirming side — the same
  selection rule as the policy's own private `_latest_matching_break`, reproduced rather than
  imported so this script calls no private name) — computed here from the same two public
  `SetupInputs` fields the policy itself reads, and cross-validated against `trigger.bar_index` on
  every `CONFIRMED` row (§1.2).
- `inputs.context_structural_trend`/`setup_structural_trend`/`execution_structural_trend` — all
  three already exist on `SetupInputs` (`compose.py:268-270`) as the raw per-role
  `StructuralTrendType`; only the first two, reduced into two of the three voting **families**,
  survive onto `HistoricalObservation.directional_factors`. This document reads all three roles
  directly, which is what makes §3.4 (RQ4, literal 1W/1D/4H agreement) a different measurement from
  AW's family-independence study — AW's three "families" are `context_structural_trend` (1W),
  `setup_structural_trend` (1D) and `setup_evidence_alignment` (also 1D, not a third timeframe);
  the EXECUTION (4H) role never casts a directional vote at all (`policy.py:342`,
  `execution_structural_trend` only gates confirmation staleness/opposition, never votes).

No production module was imported differently than `run_backtest` already imports it, and nothing
under `src/` was changed to produce any of these values.

### 1.2 Internal validation performed before trusting the extraction

- **Reconciliation**: total observations, WAIT/CANDIDATE/CONFIRMED counts, evaluated-outcome count,
  and every `OutcomeStatus` count reproduce AW's and AX's independent draws over the identical
  window **exactly** (§2.2) — the single strongest check available that the mirrored replay loop is
  behaving identically to the one inside `run_backtest`.
- **`break_age` cross-check**: for every `CONFIRMED` observation, `trigger.bar_index` (already
  computed by the policy and carried on `SetupAssessment.trigger`) was compared against the break
  this script's own backward search selected. On a smoke run (BTCUSDT alone, 19 confirmed rows) the
  two agreed on every row a persisting identity was re-observed across consecutive bars: `break_age`
  incremented by exactly 1 per bar while `trigger_bar_index` stayed fixed at the same origin bar —
  the relationship the formula requires if it is reading the same break the policy itself is
  reading.
- **Quartile-bucket sums**: every bucketed table's cell counts sum to the same 146 (or 133 resolved)
  total as the unbucketed baseline, for every one of RQ1/RQ5/RQ6/RQ7's four segmentations.

### 1.3 Statistics convention

- **Win rate** = `TARGET_FIRST / (TARGET_FIRST + STOP_FIRST)` — resolved outcomes only,
  `AMBIGUOUS_SAME_BAR` and `NEITHER_WITHIN_WINDOW` excluded from the numerator and denominator,
  identical to AV/AX's own convention.
- **Confidence interval**: 95% Wilson score interval (no continuity correction), computed from
  stdlib `math` only — chosen over the normal (Wald) approximation because several segments here
  have `n < 20` or a proportion near 0 or 1, where Wald intervals are known to misbehave.
- **Effect size**: Pearson correlation coefficient (`statistics.correlation`, stdlib, Python 3.12)
  between a continuous predictor and the binary resolved outcome, reported alongside its `n`, for
  every segmentation with a natural continuous axis (ATR%, RR, stop/target distance, confirmation
  age).
- **Denominator discipline**: every table below states `n_resolved` (the outcome win-rate
  denominator) beside `n_evaluated` (the larger population including ambiguous/unresolved rows) —
  the two are never conflated.
- **Smallness**: any cell with `n_resolved < 10` is flagged inline as too small for a reliable
  estimate and excluded from the strongest/weakest rankings in §8/§9 (which require `n_resolved ≥
  10` to appear at all — themselves still often too small to generalize from, as §10 explains at
  length).

---

## 2. Dataset

### 2.1 Scope

Identical scope to AV/AW/AX, by design — a fourth independent live draw from the same population,
not a different one. Ten symbols (`DEFAULT_BACKTEST_SYMBOLS`): BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT,
XRPUSDT, DOGEUSDT, ADAUSDT, LINKUSDT, AVAXUSDT, DOTUSDT. Real public Binance spot data,
`2025-07-04` to `2026-08-07` (400 days, `DEFAULT_BACKTEST_DAYS`). Per-symbol candle counts,
identical to all three prior runs: 1w × 57, 1d × 401, 4h × 2,401.

### 2.2 Reconciliation against AV/AW/AX

| | This run (2026-08-10) | AX (2026-08-10) | AW (2026-08-08) | Report 0011 (2026-08-08) |
|---|---|---|---|---|
| Total observations | **21,680** | 21,680 | 21,680 | 21,730 |
| WAIT | 21,102 | 21,102 | 21,102 | 21,147 |
| CANDIDATE (rows) | 401 | 401 | 401 | 401 |
| CONFIRMED (rows) | 177 | 177 | 177 | 182 |
| Evaluated outcomes | 146 | 146 | 146 | 151 |
| TARGET_FIRST | 62 | 62 | — | — |
| STOP_FIRST | 71 | 71 | — | — |
| AMBIGUOUS_SAME_BAR | 5 | 5 | — | — |
| NEITHER_WITHIN_WINDOW | 8 | 8 | — | — |

Byte-identical to AX's own numbers, drawn the same day over the same closed window — the expected
result once every candle in the window is fully closed and no longer revisable (AX §2.2's own
explanation for why it, in turn, matched AW exactly two days after AW's own draw diverged slightly
from report 0011's, taken one day earlier while the window's tail was still live). This is this
document's primary sanity check that the mirrored replay loop, not `run_backtest` itself, is
behaving identically to production.

### 2.3 Which symbols actually appear in the outcome-bearing population

Not previously stated by AV/AW/AX in these terms, and directly relevant to every table below:
**only 5 of the 10 backtested symbols ever produced an evaluated outcome in this window.**

| Symbol | Confirmed rows | Evaluated outcomes | Resolved outcomes |
|---|---|---|---|
| DOTUSDT | 84 | 53 | 52 |
| ETHUSDT | 34 | 34 | 26 |
| ADAUSDT | 24 | 24 | 23 |
| BTCUSDT | 19 | 19 | 16 |
| LINKUSDT | 16 | 16 | 16 |
| SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, AVAXUSDT | 0 | 0 | 0 |

DOTUSDT alone supplies **39.1% of every resolved outcome this document segments** (52/133) —
roughly four times an even one-symbol-in-ten share, and nearly twice an even
one-symbol-in-five share among the five symbols that ever produced one. §10 returns to this at
length: it is not a sampling artifact of this extraction, it is a property of the 146-row
population every segmentation below draws from.

### 2.4 Inherited limitations

Every limitation `BACKTEST_LIMITATIONS` (AV-1 through AV-9, `backtest_harness.py:135-167`) and
every limitation AW §2.4/AX §2.3 name applies unchanged: no fees/slippage/spread modelled,
`TARGET_FIRST`/`STOP_FIRST` are wick-touch classifications and never a win rate in the trading
sense, `AMBIGUOUS_SAME_BAR` is a refusal to guess intrabar order, the 60-bar evaluation window is a
stated measurement policy, and every number here restates the printed R:R at confirmation, never a
realized return.

This document adds one further limitation specific to itself: **the numeric ATR%/regime/trend
values read for SETUP and EXECUTION roles are computed identically to how CONTEXT-role values
already reach production, but confirm nothing about how a live user would see them** — no product
surface today prints setup- or execution-role regime, so §3's SETUP/EXECUTION-role tables describe
fully real, already-computed pipeline facts that happen not to be rendered anywhere yet.

---

## 3. Segmentation — RQ1 through RQ9

### RQ1 — Volatility

**Two different measurements, because two different things already exist in the pipeline and
neither alone is what RQ1 asks for.**

**(a) The production categorical regime** (`VolatilityState`: EXPANDING/CONTRACTING/STEADY/
INSUFFICIENT — the fast/slow ATR-ratio *change* the live product already computes and could print,
context role):

| State | n_resolved | Win rate |
|---|---|---|
| CONTRACTING | 101 | 45/101 = 45.5% (95% CI 36.2%–55.2%) |
| STEADY | 16 | 3/16 = 18.75% (95% CI 6.6%–43.0%) |
| INSUFFICIENT | 16 | 13/16 = 81.25% (95% CI 57.0%–93.4%) |

**INSUFFICIENT's 81.25% figure is an artifact, not a finding — see §7.** All 16 rows are DOTUSDT,
five consecutive calendar days (2026-06-22 to 06-25), one continuous volatile stretch; `atr_slow`
(ATR-50, context/1w role) was `None` for DOTUSDT specifically at these instants while `atr_fast`
(ATR-14) read an extreme 29.4% of price — the state that gates the ratio to `INSUFFICIENT` rather
than measuring a real "low/no volatility" regime.

**(b) Numeric ATR% (Wilder ATR-14 as a fraction of that role's own close), quartile-bucketed over
the full 21,680-row population** — quartile edges computed independently per role, from every
observation (not just the 146 evaluated ones — the honest population an ATR reading is drawn from).
A 1w-role edge and a 4h-role edge are not the same number and are not meant to be compared to each
other directly, only within their own role's column:

| Role | Bucket | Edge (ATR14/close) | n_resolved | Win rate |
|---|---|---|---|---|
| CONTEXT (1w) | Low | ≤ 16.9% | 58 | 32/58 = 55.2% (42.5%–67.3%) |
| CONTEXT | Medium | 16.9%–22.5% | 0 | none reached CONFIRMED |
| CONTEXT | High | 22.5%–29.3% | 59 | 17/59 = 28.8% (18.8%–41.4%) |
| CONTEXT | Very High | > 29.3% | 16 | 13/16 = 81.25% (57.0%–93.4%) — **the same 16 DOTUSDT rows as (a)'s INSUFFICIENT bucket** |
| SETUP (1d) | Low | ≤ 4.2% | 58 | 32/58 = 55.2% (42.5%–67.3%) |
| SETUP | Medium | 4.2%–5.5% | 36 | 11/36 = 30.6% (18.0%–46.9%) |
| SETUP | High | 5.5%–6.9% | 39 | 19/39 = 48.7% (33.9%–63.8%) |
| SETUP | Very High | > 6.9% | 0 | **none reached CONFIRMED at all** |
| EXECUTION (4h) | Low | ≤ 1.53% | 65 | 34/65 = 52.3% (40.4%–64.0%) |
| EXECUTION | Medium | 1.53%–1.95% | 28 | 9/28 = 32.1% (17.9%–50.7%) |
| EXECUTION | High | 1.95%–2.45% | 39 | 18/39 = 46.2% (31.6%–61.4%) |
| EXECUTION | Very High | > 2.45% | 1 | 1/1 — uninterpretable |

Point-biserial correlation between raw ATR% and resolved win, over the 133 resolved outcomes:
CONTEXT r=−0.065 (n=133), SETUP r=+0.012 (n=133), EXECUTION r=−0.034 (n=133) — **all three
indistinguishable from zero.** The CONTEXT-role Medium bucket and the SETUP-role Very High bucket
are entirely empty of confirmed setups, and EXECUTION-role Very High has exactly one: **the top (or,
at CONTEXT, a middle) quartile of the pipeline's own already-computed volatility essentially never
produces a confirmed setup in this dataset at some roles at all** — a finding about what reaches
CONFIRMED, not about what happens once it does (§6 returns to this).

### RQ2 — Trend strength

**Cannot be answered as posed, and this document says so rather than inventing a proxy.** No
numeric trend-strength score exists anywhere in `fmis.structural_trend` or `fmis.market_regime`;
this is not an extraction gap, it is stated, deliberate design in the source itself —
`structural_trend/trend.py:25` and `structural_trend/models.py:244` both explicitly list "score,
strength, rank, probability, duration, magnitude" among what the package refuses to carry, and
`__init__.py:36` repeats the same refusal at the package level. No weak/moderate/strong/extreme
bucketing is possible without inventing a scoring function the codebase does not have — which this
document was explicitly told not to do ("no filter proposal").

What *is* measurable is the one categorical field that exists: `StructuralTrendType`
(`SUSTAINED_HIGHER`/`SUSTAINED_LOWER`/`NEUTRAL`/`INDETERMINATE`), per role, at confirmation:

| Role | State | n_resolved | Win rate |
|---|---|---|---|
| CONTEXT (1w) | sustained_higher | 58 | 55.2% (42.5%–67.3%) |
| CONTEXT | sustained_lower | 75 | 40.0% (29.7%–51.3%) |
| SETUP (1d) | sustained_higher | 58 | 55.2% (42.5%–67.3%) |
| SETUP | sustained_lower | 67 | 41.8% (30.7%–53.7%) |
| SETUP | neutral | 8 | 25.0% (7.1%–59.1%, n<10) |
| EXECUTION (4h) | sustained_higher | 51 | 60.8% (47.1%–73.0%) |
| EXECUTION | neutral | 50 | 48.0% (34.8%–61.5%) |
| EXECUTION | sustained_lower | 32 | 21.9% (11.0%–38.8%) |

At CONTEXT and SETUP roles, `sustained_higher` outperforms `sustained_lower`; the CONTEXT-role gap
(55.2% vs 40.0%) has non-overlapping point estimates but overlapping 95% CIs. The EXECUTION-role
spread (60.8% vs 21.9%) is the widest categorical gap measured for any single field in this
document — see §8/§9 and §10's confound warning before reading that as a finding about execution
timing rather than about direction/symbol mix.

### RQ3 — Regime

CONTEXT-role `StructureState` is **`trending` for all 146 evaluated outcomes, with zero
variance** — a direct structural consequence of how a directional candidate reaches `CONFIRMED` at
all (it needs `context_structural_trend` to vote `long`/`short`, and `StructureState.TRENDING`
requires the same swing-based reading that vote is built from), not something this document can
segment. SETUP- and EXECUTION-role structure state, never persisted in production, does vary:

| Role | Structure state | n_resolved | Win rate |
|---|---|---|---|
| SETUP (1d) | trending | 99 | 47/99 = 47.5% (37.9%–57.2%) |
| SETUP | transitioning | 33 | 15/33 = 45.5% (29.8%–62.0%) |
| SETUP | indeterminate | 1 | 0/1 — uninterpretable |
| EXECUTION (4h) | indeterminate | 35 | 20/35 = 57.1% (40.9%–72.0%) |
| EXECUTION | trending | 60 | 34/60 = 56.7% (44.1%–68.4%) |
| EXECUTION | transitioning | 33 | 7/33 = 21.2% (10.7%–37.8%) |
| EXECUTION | ranging | 5 | 1/5 — n<10 |

Participation state (`ParticipationState`), all three roles:

| Role | Participation | n_resolved | Win rate |
|---|---|---|---|
| CONTEXT | subdued | 92 | 50/92 = 54.3% (44.2%–64.1%) |
| CONTEXT | typical | 41 | 12/41 = 29.3% (17.6%–44.5%) |
| SETUP | subdued | 62 | 40/62 = 64.5% (52.1%–75.3%) |
| SETUP | elevated | 23 | 2/23 = **8.7%** (2.4%–26.8%) |
| SETUP | typical | 48 | 20/48 = 41.7% (28.8%–55.7%) |
| EXECUTION | typical | 30 | 15/30 = 50.0% (33.2%–66.8%) |
| EXECUTION | elevated | 50 | 24/50 = 48.0% (34.8%–61.5%) |
| EXECUTION | subdued | 53 | 23/53 = 43.4% (31.0%–56.7%) |

SETUP-role `elevated` participation's 8.7% is the single lowest win rate of any `n_resolved ≥ 10`
cell measured in this document (§9). §10 shows this cell, too, is symbol-concentrated.

### RQ4 — Timeframe agreement

Raw pairwise agreement between the three roles' `StructuralTrendType`, over the **full 21,680-row
population** (every WAIT/CANDIDATE/CONFIRMED instant, not only confirmed ones — the honest
denominator for "how often are 1W/1D/4H aligned" as posed):

| Pair | Agreement |
|---|---|
| CONTEXT (1w) vs SETUP (1d) | 4,680/21,680 = 21.6% (95% CI 21.0%–22.1%) |
| SETUP (1d) vs EXECUTION (4h) | 7,215/21,680 = 33.3% (95% CI 32.7%–33.9%) |
| CONTEXT (1w) vs EXECUTION (4h) | 4,496/21,680 = 20.7% (95% CI 20.2%–21.3%) |

Full three-way agreement is rare across the whole population: all three agree only 1,629/21,680 =
7.5% of the time; exactly 2 of 3 agree 11,504/21,680 = 53.1%; all three disagree pairwise
8,547/21,680 = 39.4%.

**Restricted to the 146 evaluated outcomes, `all_disagree` never occurs at all** — a direct
consequence of confirmation requiring at least 2 of the 3 *families* to agree (§1.1's distinction:
CTX-trend and SETUP-trend are 2 of those 3 families, so both being directional and disagreeing
with each other on the confirmed side is close to impossible by construction):

| Agreement level (146 outcomes) | n_resolved | Win rate |
|---|---|---|
| All 3 roles agree | 83 | 38/83 = 45.8% (35.5%–56.4%) |
| Exactly 2 of 3 agree | 50 | 24/50 = 48.0% (34.8%–61.5%) |

No measurable difference (point estimates 2.2 points apart, heavily overlapping CIs). **Full
timeframe agreement does not measurably improve outcomes in this dataset**, at the same time as
being the same structural fact AW already found for the family-level vote — agreement here is
close to a restatement of "the policy's own confirmation gate," not an independent signal.

### RQ5 — RR buckets

| RR bucket | n_resolved | Win rate |
|---|---|---|
| 0–1 | 51 | 38/51 = 74.5% (61.1%–84.5%) |
| 1–2 | 23 | 9/23 = 39.1% (22.2%–59.2%) |
| 2–3 | 11 | 6/11 = 54.5% (28.0%–78.7%, n<10 borderline) |
| 3–5 | 15 | 6/15 = 40.0% (19.8%–64.3%) |
| 5+ | 33 | 3/33 = **9.1%** (3.1%–23.6%) |

Point-biserial correlation between displayed RR and resolved win: **r = −0.30 (n=133)** — the
strongest single-variable correlation measured anywhere in this document. Mean realized R across
all 133 resolved outcomes (win → `+RR`, loss → `−1`): **+0.240** (stdev 2.99) — a small positive
figure, entirely consistent with AV's own headline 46.6% win rate landing above the ~46.5%
breakeven a mean displayed RR near 1.15 would require, and directly answering RQ5's own question:
**displayed RR correlates negatively with the probability of hitting it, but the two do not net to
zero — 0–1 RR setups both win far more often and contribute the most resolved trades (51 of 133)**.

### RQ6 — Stop distance

Stop distance as a fraction of reference price, quartile-bucketed over the 146 evaluated outcomes:

| Bucket | Edge | n_resolved | Win rate |
|---|---|---|---|
| Very tight | ≤ 0.48% | 34 | 7/34 = 20.6% (10.3%–36.8%) |
| Tight–Medium | 0.48%–1.35% | 35 | 12/35 = 34.3% (20.8%–50.8%) |
| Medium–Wide | 1.35%–2.68% | 36 | 21/36 = 58.3% (42.2%–72.9%) |
| Very wide | > 2.68% | 28 | 22/28 = 78.6% (60.5%–89.8%) |

Correlation between stop distance and resolved win: **r = +0.41 (n=133)** — second-strongest
measured. **RQ6's own question — "do tight stops really lose more often?" — is answered yes, and
strongly, in this dataset.** §10 flags the mechanical alternative explanation before this is read
as a directional-edge finding.

### RQ7 — Target distance

| Bucket | Edge | n_resolved | Win rate |
|---|---|---|---|
| Near | ≤ 0.74% | 34 | 29/34 = 85.3% (69.9%–93.6%) |
| Near–Mid | 0.74%–1.72% | 35 | 12/35 = 34.3% (20.8%–50.8%) |
| Mid–Far | 1.72%–3.87% | 37 | 11/37 = 29.7% (17.5%–45.8%) |
| Far | > 3.87% | 27 | 10/27 = 37.0% (21.5%–55.8%) |

Correlation: **r = −0.32 (n=133)**. Mostly monotonic — Near dramatically outperforms every other
bucket — but **not fully monotonic**: Far (37.0%) is higher than Mid-Far (29.7%), a small
non-monotonicity worth naming rather than smoothing over (§6).

### RQ8 — Confirmation age

**A structural ceiling exists that RQ8 as posed does not anticipate.** `CONFIRMATION_LOOKBACK_BARS
= 10` (`policy.py:78`) means a break older than 10 bars **cannot confirm at all** — the candidate
stays `CANDIDATE` forever, never reaches `CONFIRMED`, and is never outcome-evaluated. The maximum
`confirmation_break_age_bars` observed across all 177 `CONFIRMED` rows is exactly **10** — RQ8's
own "fresh...10 bars" framing already covers the entire reachable range; nothing beyond bar 10 has
ever been measured, or can be, without the policy itself changing (which this document does not
propose).

| Age (bars) | n_resolved | Win rate |
|---|---|---|
| 0 | 12 | 6/12 = 50.0% |
| 1 | 12 | 9/12 = 75.0% |
| 2 | 16 | 11/16 = 68.75% |
| 3 | 14 | 5/14 = 35.7% |
| 4 | 14 | 5/14 = 35.7% |
| 5 | 12 | 6/12 = 50.0% |
| 6 | 11 | 5/11 = 45.5% |
| 7 | 13 | 6/13 = 46.2% |
| 8 | 10 | 4/10 = 40.0% |
| 9 | 9 | 2/9 = 22.2% (n<10) |
| 10 | 10 | 3/10 = 30.0% |

Roughly even distribution across all 11 ages (9–17 per bucket — this is not a sample that piles up
at "fresh"). Correlation between age and resolved win: **r = −0.20 (n=133)** — a mild, not
negligible, tendency toward lower win rates at higher staleness, weaker than RQ5's or RQ6's
correlations and with no single age bucket standing far outside its neighbours' overlapping CIs.

### RQ9 — Evidence count

Only 2 or 3 families can ever agree — `MINIMUM_AGREEING_FAMILIES = 2` out of exactly 3 total named
families (§1.1); **"4 agreeing" (as RQ9's own example range suggested) cannot occur** and is not a
gap in this measurement, it is a fact about how many families exist (§7).

| Agreeing families | n_resolved | Win rate |
|---|---|---|
| 2 | 128 | 61/128 = 47.7% (39.2%–56.3%) |
| 3 | 5 | 1/5 = 20.0% (3.6%–62.4%, n<10) |

`n=5` for the 3-family group is far too small to conclude anything — its 95% CI (3.6%–62.4%)
entirely contains the 2-family group's point estimate. **This dataset cannot answer whether more
agreement helps**, and does not pretend otherwise: 177 CONFIRMED rows split 147/30 between 2 and 3
families (§ full population, not evaluated-only), and the 3-family group's already-small population
shrinks further once `AMBIGUOUS_SAME_BAR`/`NEITHER_WITHIN_WINDOW` are excluded.

---

## 4. Tables

Every table required by §3 above is reproduced in full there; no additional aggregate table is
needed beyond what each RQ subsection already carries. §5's cross-interaction tables follow.

---

## 5. Cross-interactions

### 5.1 Deliberate Simpson's-paradox search (RQ10)

Four two-way splits were checked deliberately for full reversal — the aggregate ordering between
two groups inverting inside **every** subgroup of a second variable, the textbook Simpson's
paradox shape. **None of the four showed a full reversal.** Two showed a partial reversal in some,
not all, checked subgroups; both are reported honestly below rather than as a discovered paradox.

| Check | Aggregate | Subgroups checked | Subgroups reversed |
|---|---|---|---|
| Evidence count (2 vs 3 families) within RR bucket | 2-fam 47.7% (n=128) > 3-fam 20.0% (n=5) | 4 (of 5 RR buckets; one had no 3-fam observation) | 1 of 4 — `1-2` bucket: 2-fam 38.1%(n=21) < 3-fam 50.0%(n=2) |
| Timeframe full-agreement vs not, within symbol | all_3 45.8%(n=83) ≈ not_all 48.0%(n=50) | 3 (of 5 symbols; only 3 had both agreement levels represented) | 2 of 3 — ETHUSDT (95.0% vs 16.7%) and LINKUSDT (60.0% vs 0.0%) both favour all-agree far more than the near-tied aggregate does; DOTUSDT (21.9% vs 75.0%) alone matches the aggregate's own direction |
| LONG vs SHORT within regime structure | LONG 55.2%(n=58) > SHORT 40.0%(n=75) | 1 (CONTEXT structure has zero variance, §3 RQ3) | 0 of 1 — not a real check, only one subgroup exists |
| RR≥2 vs RR<2, within stop-distance quartile | RR<2 63.5%(n=74) > RR≥2 25.4%(n=59) | 3 | 1 of 3 — `High` stop bucket: RR≥2 87.5%(n=8) > RR<2 50.0%(n=28) |

None of these constitutes a genuine Simpson's paradox (full reversal), and every reversed cell
found has `n ≤ 8` on at least one side — too small to distinguish a real local reversal from noise.
The closest candidate (`High` stop bucket, RR≥2 vs RR<2) inverts on an 8-observation cell against a
59-observation aggregate; §10 explains why this document does not treat it as a finding.

### 5.2 Deterministic clusters (RQ11)

Two-dimensional cells, `n_resolved ≥ 5` shown, no clustering algorithm — plain deterministic
grouping on already-computed fields:

| Cluster (SETUP-role ATR quartile × ...) | n_resolved | Win rate |
|---|---|---|
| Low ATR × CONTEXT trending | 58 | 55.2% |
| High ATR × CONTEXT trending | 39 | 48.7% |
| Medium ATR × CONTEXT trending | 36 | 30.6% |
| Low ATR × all-3-agree | 51 | 60.8% |
| High ATR × 2-of-3-agree | 25 | 64.0% |
| Medium ATR × 2-of-3-agree | 18 | 38.9% |
| Medium ATR × all-3-agree | 18 | 22.2% |
| High ATR × all-3-agree | 14 | 21.4% |
| Low ATR × 2-of-3-agree | 7 | 14.3% (n<10) |

| RR bucket × confirmation freshness | n_resolved | Win rate |
|---|---|---|
| 0–1 RR × stale (3–10 bars) | 38 | 73.7% |
| 5+ RR × stale (3–10 bars) | 27 | **0.0%** |
| 1–2 RR × stale | 19 | 31.6% |
| 0–1 RR × fresh (0–2 bars) | 13 | 76.9% |
| 3–5 RR × stale | 11 | 27.3% |
| 2–3 RR × stale | 10 | 50.0% |

The 5+-RR/stale cell (0/27, 95% CI 0.0%–12.5%) is the single most extreme cluster found — every one
of the RR-5+ bucket's rare wins (3 of 33, §3 RQ5) occurred in a fresher confirmation window, and
every one of its stale confirmations lost. This 27-row cell is drawn from DOTUSDT (11), ADAUSDT
(10), BTCUSDT (4), ETHUSDT (1) and LINKUSDT (1) — spread across all 5 outcome-bearing symbols, not
concentrated in one, though DOTUSDT and ADAUSDT together still supply 21 of the 27 (78%).

| Evidence count × direction | n_resolved | Win rate |
|---|---|---|
| 2 families × SHORT | 75 | 40.0% |
| 2 families × LONG | 53 | 58.5% |
| 3 families × LONG | 5 | 20.0% (n<10) |

No `3 families × SHORT` cell exists at all in the resolved population (0 observations) — every
3-family confirmed-and-resolved outcome in this dataset happened to be LONG.

---

## 6. Unexpected findings

1. **The pipeline's own top-quartile volatility reading almost never survives to a confirmed
   setup.** SETUP-role ATR% top quartile: 0 of 146 evaluated outcomes. EXECUTION-role: 1 of 146.
   This is a fact about what reaches `CONFIRMED`, not about win rate once confirmed — worth naming
   because RQ1 as posed assumes all four buckets would be populated roughly evenly, and they are
   not.

2. **`VolatilityState.INSUFFICIENT`'s apparent 81.25% win rate and CONTEXT-role "Very High" ATR
   quartile's apparent 81.25% win rate are literally the same 16 rows**, all DOTUSDT, all within a
   five-calendar-day span. Two ostensibly different segmentations (a categorical regime state
   meaning "the ratio could not be computed" and a numeric quartile meaning "extremely high
   volatility") pointed at the identical, tiny, single-symbol, single-episode population. Neither
   is a second, corroborating measurement of the other — they are the same measurement read twice
   through different fields (§7, §10).

3. **Target distance is not fully monotonic against win rate** (§3 RQ7): Near (85.3%) → Near-Mid
   (34.3%) → Mid-Far (29.7%) → Far (37.0%). The dip-then-rise at the far end is small and inside
   overlapping confidence intervals, but a strictly monotonic relationship — the intuitive
   "nearer is always better" story RQ7 invites — is not what the data shows.

4. **RR≥5 with a stale (3–10 bar) confirmation lost every single time** (0/27, §5.2) — the most
   extreme cell in the entire cross-interaction search, more extreme than any single-variable
   segmentation in §3.

5. **DOTUSDT alone supplies 39% of every resolved outcome measured** (§2.3), and disproportionately
   populates nearly every extreme cell named in §3 and §5 (elevated participation: 11 of 23; RR 5+:
   14 of 33; nearest-target quartile: 17 of 34; tightest-stop quartile: 14 of 34). This was not
   anticipated going in and materially shapes how every other finding in this document should be
   read (§10).

---

## 7. False assumptions discovered

- **RQ1's implicit assumption — that "Low/Medium/High/Very High ATR" would be four roughly
  populated buckets — is false at the SETUP and EXECUTION roles.** The top bucket is empty or
  near-empty because high volatility, at those roles, appears to suppress confirmation rather than
  merely accompany it (§6.1) — a hypothesis this document measures the shape of but does not test
  the cause of (no experiment varying the policy was run, nor could one be under this milestone's
  rules).
- **RQ2's premise — that a weak/moderate/strong/extreme trend-strength axis exists to segment by —
  is false.** It was deliberately never built (§3 RQ2); this is a design fact about the codebase,
  not a data-availability gap this extraction could close.
- **RQ3's premise — that CONTEXT-role regime `structure` would show meaningful variation
  (STEADY/EXPANDING/TRANSITIONING as literally named in the brief) — is false at the CONTEXT
  role specifically.** It is `trending` for 100% of evaluated outcomes, a direct consequence of the
  confirmation gate itself (§3 RQ3), not a market fact this dataset happens to exhibit. Variation
  does exist at SETUP and EXECUTION roles, measured in §3 instead.
- **RQ8's implicit assumption — that "stale" confirmation could mean anything up to 10 bars, with
  headroom to see what happens beyond that — is false.** 10 bars is not a measurement choice this
  document made; it is `CONFIRMATION_LOOKBACK_BARS`, a hard policy ceiling. Nothing older than 10
  bars has ever reached `CONFIRMED`, in this dataset or in any dataset this policy could produce.
- **RQ9's implicit assumption — that agreement counts up to 4 (its own example range) could be
  observed — is false.** Exactly 3 families exist; 4-family agreement is not a smaller sample of a
  real phenomenon, it is a state the current architecture cannot produce at all (§3 RQ9, §1.1).
- **The two RQ1 "confirmations" in §6.2 look like independent corroboration and are not.** A
  categorical regime state and a numeric quartile bucket, read from what appear to be two different
  computations, resolved to the exact same 16 rows. A reader skimming only the summary tables in
  §3 without cross-checking row identity (as this document did, in §7's own preparation) could
  easily double-count this as two separate pieces of evidence for "low/insufficient volatility
  predicts high win rate," when it is one 16-row, one-symbol, one-week observation counted twice.

---

## 8. Where FMITS appears strongest

Every `n_resolved ≥ 10` cell across every table in §3, ranked by win rate, top 10 (descending):

| Rank | Segment | n_resolved | Win rate (95% CI) |
|---|---|---|---|
| 1 | Target distance: Near (≤0.74%) | 34 | 85.3% (69.9%–93.6%) |
| 2 | CONTEXT ATR: Very High (= INSUFFICIENT regime, §6.2, same 16 rows) | 16 | 81.25% (57.0%–93.4%) |
| 3 | CONTEXT regime volatility: INSUFFICIENT (same 16 rows as #2) | 16 | 81.25% (57.0%–93.4%) |
| 4 | Stop distance: Very wide (>2.68%) | 28 | 78.6% (60.5%–89.8%) |
| 5 | Confirmation age: 1 bar | 12 | 75.0% (46.8%–91.1%) |
| 6 | RR bucket: 0–1 | 51 | 74.5% (61.1%–84.5%) |
| 7 | Confirmation age: 2 bars | 16 | 68.75% (44.4%–85.8%) |
| 8 | SETUP participation: subdued | 62 | 64.5% (52.1%–75.3%) |
| 9 | EXECUTION regime volatility: contracting | 18 | 61.1% (38.6%–79.7%) |
| 10 | EXECUTION structural trend: sustained_higher | 51 | 60.8% (47.1%–73.0%) |

Ranks #2 and #3 are the same 16 rows (§6.2) and should be read as one entry, not two. Every entry
above `n_resolved = 62` (rank 8) has `n < 35`; §10 explains why this list is a description of what
happened in 133 historical resolved outcomes, not a claim about where the policy has a durable
edge.

---

## 9. Where FMITS appears weakest

Same universe, ascending order, bottom 10:

| Rank | Segment | n_resolved | Win rate (95% CI) |
|---|---|---|---|
| 1 | SETUP participation: elevated | 23 | 8.7% (2.4%–26.8%) |
| 2 | RR bucket: 5+ | 33 | 9.1% (3.1%–23.6%) |
| 3 | CONTEXT regime volatility: steady | 16 | 18.75% (6.6%–43.0%) |
| 4 | Stop distance: Very tight (≤0.48%) | 34 | 20.6% (10.3%–36.8%) |
| 5 | EXECUTION regime structure: transitioning | 33 | 21.2% (10.7%–37.8%) |
| 6 | EXECUTION structural trend: sustained_lower | 32 | 21.9% (11.0%–38.8%) |
| 7 | CONTEXT ATR: High quartile | 59 | 28.8% (18.8%–41.4%) |
| 8 | CONTEXT participation: typical | 41 | 29.3% (17.6%–44.5%) |
| 9 | Target distance: Mid-Far | 37 | 29.7% (17.5%–45.8%) |
| 10 | Confirmation age: 10 bars | 10 | 30.0% (10.8%–60.3%) |

The single most extreme weak cell measured anywhere in this document is not on this list because
its `n_resolved = 27 ≥ 10` threshold *is* met but it is a cross-interaction, not a single-variable
segment: **RR 5+ with a stale (3–10 bar) confirmation, 0/27 (§5.2)**. Restated here because §8/§9's
single-variable framing would otherwise bury the strongest signal in the entire document under a
weaker, single-axis one (RR 5+ alone, rank #2 above, 9.1%).

---

## 10. Threats to validity

**This is the most important section of this document, and every table above should be read
through it.**

1. **One symbol dominates the population this entire document segments.** DOTUSDT is 39.1% of all
   133 resolved outcomes (§2.3) — not because it was overweighted in extraction, but because it is
   the only symbol of the ten backtested that produced a confirmed setup in most weeks of this
   400-day window. Every table in §3 and every cluster in §5 is, to a first approximation, "what
   DOTUSDT's price path did, plus four smaller symbols' contributions." A reader treating any cell
   here as "FMITS's edge under condition X, across the market" is treating one asset's specific
   400-day history as if it were ten independent draws.

2. **Five of ten backtested symbols contributed zero evaluated outcomes.** SOLUSDT, BNBUSDT,
   XRPUSDT, DOGEUSDT and AVAXUSDT never produced a single confirmed, evaluated setup in this
   window. This document cannot say anything about the policy's behaviour on those five symbols —
   not "no edge," simply **no observations at all** — and every aggregate figure in this document
   silently excludes them.

3. **Within-symbol outcomes are not independent trials.** Even restricted to the 133 resolved
   outcomes (already deduplicated to one evaluation per distinct setup identity, §1.1's
   `IdentityTracker`), consecutive setup identities on the same symbol during one sustained
   directional stretch share the same underlying price path. The 27-observation "RR 5+ stale"
   cluster (§5.2, 0.0% win) draws 26 of its 33 parent-bucket observations from just two symbols
   (DOTUSDT 14, ADAUSDT 12) — closer to two extended episodes than 27 independent bets.

4. **Small-sample rankings (§8/§9) are sensitive to exactly which `n≥10` threshold is chosen.**
   Several entries sit at `n=10`–`16`; moving the threshold to `n≥20` would drop half of each
   ranking. This document picked `n≥10` before looking at the results (a floor low enough to
   include RQ8/RQ9's naturally small per-bucket populations) and states plainly that it is a low
   bar, not a validated one.

5. **RQ6/RQ7's correlations may be substantially mechanical rather than informational.** A wider
   stop is, by construction, harder for price to reach before the target; a nearer target is, by
   construction, easier to touch. Part of `r=+0.41` (stop distance) and `r=−0.32` (target distance)
   plausibly reflects pure touch-probability geometry — the same reason far-OTM options are cheap —
   rather than the policy's directional evidence adding information. This document has no way to
   separate the two effects from the data it has (doing so would require, at minimum, a
   volatility-normalized touch-probability model this repository does not have and this milestone
   was not asked to build).

6. **The window itself was chosen for a documented structural reason (AV's own 400-day minimum for
   weekly EMA-50 warm-up), not blind to any result** — but it is still one 400-day window,
   2025-07-04 to 2026-08-07, and every segmentation in this document inherits whatever was
   idiosyncratic about crypto markets specifically during that period. A different 400-day window
   could plausibly reorder several of §8/§9's rankings.

7. **Multiple comparisons were not corrected for.** §3 through §5 report roughly 25 distinct
   segmentations across dozens of cells; at a 95% confidence level, several "significant-looking"
   point estimates are expected to arise from chance alone even if the underlying policy had zero
   true segment-level variation. No Bonferroni or similar correction is applied anywhere in this
   document — every confidence interval should be read as if it were the only one being examined,
   because it was not.

---

## 11. Red Team

**Attacking this document's own strongest claims.**

- *"RR correlates negatively with win probability (r=−0.30) — real, but is it new information?"*
  Partially circular by construction: a stop and target are both nearest-detected structural
  levels (AR-3), so a high displayed RR at confirmation typically means the target sits unusually
  far from a nearby, tight stop — i.e., RR itself is already a geometric summary of the same
  stop-distance and target-distance facts RQ6/RQ7 measure separately. The three correlations
  (RR r=−0.30, stop r=+0.41, target r=−0.32) are not three independent confirmations of one
  underlying edge; they are three views of two numbers (stop distance, target distance) that RR is
  algebraically derived from.
- *"DOTUSDT's dominance invalidates every finding."* Overstated. DOTUSDT's own win rate (42.3%,
  22/52) is close to the 46.6% aggregate, not an outlier driving the aggregate itself — its
  dominance inflates apparent sample sizes and manufactures the *appearance* of independent
  confirmation across many cells, without necessarily biasing any single aggregate win-rate
  estimate in one particular direction. The correct reading is "confidence intervals here are
  narrower than they should be," not "every point estimate is wrong."
- *"The Simpson's search (§5.1, RQ10) found nothing, so there is no paradox to find."* This
  document checked exactly four deliberately chosen 2-way splits, not an exhaustive search of the
  full cross-product of every field measured. A fifth or fifteenth split not tried here could
  reveal a genuine reversal this document simply did not look for. "Searched deliberately, found
  none" (§5.1's own honest framing) is not the same claim as "none exists."
- *"§6 unexpected finding #1 (top-quartile ATR suppresses confirmation) sounds like a real
  volatility-gate mechanism — is it?"* This document measured the shape (0 or 1 of 146 outcomes in
  the top ATR quartile) but not the mechanism. A structural-level detector that produces fewer
  clean swing levels during extreme volatility, a break-of-structure detector that fires
  differently, or simply five symbols' idiosyncratic price paths happening to spend their most
  volatile stretches outside confirmation windows are all consistent with the same observed shape.
  This document cannot and does not distinguish between them.
- *"The whole exercise assumes `TARGET_FIRST`/`STOP_FIRST` is the right outcome variable to
  segment by."* Inherited unmodified from AV (limitation AV-2): a same-bar wick touch, no fees, no
  slippage, no realized PnL. Every win-rate figure in this document is a segmentation of that same
  already-limited variable — no segmentation, however fine-grained, escapes AV's own original
  measurement boundary.

---

## 12. Questions that still cannot be answered

- **Does the policy have a durable, symbol-general edge in any of the strongest segments named in
  §8?** Not from this dataset — §10.1–10.3 make this the central unresolved question the whole
  document raises without being able to close.
- **What would RQ1/RQ2/RQ8/RQ9 show on a wider volatility/trend-strength/confirmation-age/
  agreement-count range?** Structurally unanswerable without changing the policy itself
  (§7's false-assumption entries) — not a data gap, a boundary this milestone was explicitly
  forbidden from moving.
- **Is the RQ6/RQ7 stop/target-distance correlation informational or purely mechanical (§10.5)?**
  Would require a touch-probability-normalized baseline this repository has no component for, and
  this milestone was not authorized to build one.
- **Would SOLUSDT/BNBUSDT/XRPUSDT/DOGEUSDT/AVAXUSDT show the same segment-level patterns if they
  had produced any confirmed setups?** Entirely unknown — zero observations, not weak ones.
- **Is DOTUSDT's dominance a property of this specific 400-day window, or would a different
  10-symbol universe or window redistribute which symbol dominates?** Would require re-running
  this extraction over a different window or universe, which this milestone's own rules (reuse the
  existing backtest exactly, measure once) do not permit within its scope.
- **Does the 0/27 "RR≥5, stale confirmation" cluster (§5.2, §9) reflect a real interaction, or is
  27 observations, drawn mostly from two symbols, simply too few to say?** This document flags it
  as the single most extreme finding measured and, in the same breath, cannot rule out chance —
  both statements are true at once, and no further measurement inside this milestone's scope can
  separate them.

---

## Appendix — reproduction

Two scripts, neither part of the shipped package, both calling only already-public production
functions plus the identical policy arithmetic named in §1.1, living outside the repository in a
scratch directory:

- **`ay_extract.py`** — mirrors `fmis.swing_setup.backtest_harness.run_backtest`'s own
  instant-by-instant loop (`fetch_historical_dataset` → per symbol, per instant:
  `build_replay_transport` → `multi_timeframe_facts_for_symbol(..., features=regime_features(),
  transport=replay_transport, clock=lambda moment=instant: moment)` →
  `setup_inputs_and_assessment_for_sheet` → `IdentityTracker.observe` → `evaluate_outcome` at
  `is_first_confirmation`), with three additional read-only calls per instant: `regime_for_sheet`
  on the SETUP and EXECUTION role sheets, direct reads of `atr_14`/`atr_50` off each role's
  `StructuralFactSheet.features`, and a backward search over `inputs.execution_breaks` identical to
  `policy.py`'s own `_latest_matching_break`. Serializes all 21,680 observations and all 146
  outcomes to JSON (`dataset.json`, 34MB). Run: `PYTHONPATH=<repo>/src <repo>/.venv/bin/python3
  ay_extract.py > dataset.json` — real Binance data, `DEFAULT_BACKTEST_SYMBOLS`,
  `DEFAULT_BACKTEST_DAYS=400`, end `2026-08-07T00:00:00+00:00`, `run_at=2026-08-10T00:00:00+00:00`.
  Reconciles exactly against AW's and AX's own independent draws (§2.2).
- **`ay_analyze.py`** — pure-Python (stdlib `json`/`math`/`statistics`/`collections` only, no
  third-party dependency) over `dataset.json`. Computes every table in §3–§5: Wilson 95% CIs,
  Pearson point-biserial correlations, quartile bucketing over stated populations, the four
  deliberate Simpson's-paradox checks, the five deterministic 2-D clusters, and the `n≥10`
  strongest/weakest rankings. Both are read-only with respect to the production package; neither
  changed a line under `src/`.
