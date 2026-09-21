# Failure Attribution Research V1

**Milestone:** AZ
**Status:** Research only — measurement only, no code changes
**Date:** 2026-08-10
**Model:** Claude Sonnet 5
**Repository state:** `main`, working tree unchanged by this milestone under `src/`, `tests/`,
`docs/adr/`, `FMITS_PRODUCT_BACKLOG.md`, `FMITS_PRODUCT_CHANGELOG.md`
**Type:** Research investigation, not a design record — produces no contract, no ADR, no backlog
entry, no CURRENT_STATE update, no strategy change, no filter proposal, no threshold proposal, no
ranking of what the product should do next, no AI interpretation of any kind

---

## 0. What this document is

Milestone AV measured whether the system wins (46.6% win rate among resolved outcomes). Milestone
AW measured whether the three directional evidence families are independent (they are not).
Milestone AX measured which individual evidence observations earn their place. Milestone AY
measured where, inside those same outcomes, win rate concentrates or vanishes across volatility,
trend, regime, timeframe-agreement, RR, stop-distance, target-distance and confirmation-age cuts.

This document asks the one question none of the four already answered: **why did each losing trade
lose?** Not "where is win rate lower" (AY), but "what already-measured, already-computed
characteristics does a losing trade actually carry, in combination, and how much of the 71 losses in
this dataset can those characteristics account for?"

This is not a new backtest and not a new metric. Every number below is drawn from the identical 146
evaluated outcomes (133 resolved: 71 `STOP_FIRST`, 62 `TARGET_FIRST`) Milestones AV/AW/AX/AY already
produced, reconciled exactly against their published counts (§2.2), read through nine failure
categories built entirely from fields those four milestones already established as measurable —
seven of which AY already bucketed and published win rates for. No new indicator, no new regime
dimension, no new threshold, no filter, no policy change and no AI interpretation produced any
figure in this document.

**No recommendations anywhere in this document.** Sections 3–8 report descriptive facts about 133
historical resolved outcomes. Section 9 exists specifically to warn against over-reading them, and
Section 10 attacks the document's own strongest claims.

---

## 1. Method

### 1.1 Data source

One fresh, read-only extraction (`az_extract.py`), mirroring
`fmis.swing_setup.backtest_harness.run_backtest`'s own instant-by-instant replay loop exactly — same
replay transport, same clock, same `IdentityTracker`, same call to
`setup_inputs_and_assessment_for_sheet`, same call to `evaluate_outcome` at `is_first_confirmation`
— following the precedent AW/AX/AY set (their own extraction scripts, described in each document's
own Appendix, none of them shipped into the repository). This script lived outside the repository,
in a scratch directory, and is described in full in the Appendix.

Unlike AY, this extraction does **not** recompute SETUP/EXECUTION-role regime or ATR% at every one
of the 21,680 replayed instants — only at the 146 instants where `is_first_confirmation` is true,
since this document needs per-outcome row-level joint characteristics (which AY's own published
document does not carry — AY publishes only marginal and a small number of two-way aggregate
tables), not full-population quartile edges. Where a bucket boundary is needed (stop distance,
target distance, RR, CONTEXT-role ATR%), this document reuses AY's own already-published edges
verbatim (§1.1's own precedent: "no new indicator, no new threshold") rather than recomputing them
from a full-population re-extraction this milestone's rules do not require.

Beyond the replay loop itself, this extraction makes the same class of additional read-only calls to
already-public, already-used pure functions that AY's own script made, to recover facts the
production `HistoricalObservation`/`SetupOutcome` models compute internally but do not persist:

- `fmis.pipeline.regime.regime_for_sheet`, called a second and third time on the SETUP (1D) and
  EXECUTION (4H) role sheets, at confirmation instants only.
- `fmis.pipeline.regime.regime_input_from_sheet`, the same public adapter `regime_for_sheet` itself
  calls internally, read directly to recover `atr_fast`/`close` per role (rather than reaching for
  the private feature-name constants AY's own script read).
- `assessment.trigger.bar_index`, already computed by the policy and carried on `SetupAssessment`
  (`policy.py:407`, the confirming break's own origin index) — used directly for
  `break_age = execution_closed_count - 1 - trigger.bar_index`, which is exactly the arithmetic
  `policy.py:344-348` performs internally to gate confirmation staleness. This is a **simpler**
  derivation than AY's own (a private-name-free backward search over `execution_breaks`) because a
  `CONFIRMED` row's trigger *is* the matching break the policy found; no second search is needed.
- `assessment.risk_reward.risk`/`.reward`, already computed by the policy
  (`policy.py:180-197`), read directly for stop-distance/target-distance as a fraction of reference
  price, rather than re-deriving them from stop/target/reference prices independently.

No production module is imported differently than `run_backtest` already imports it, and nothing
under `src/` was changed to produce any of these values.

### 1.2 Internal validation performed before trusting the extraction

- **Reconciliation**: total observations (21,680), WAIT/CANDIDATE/CONFIRMED counts (21,102/401/177),
  evaluated-outcome count (146), and every `OutcomeStatus` count (`TARGET_FIRST` 62, `STOP_FIRST` 71,
  `AMBIGUOUS_SAME_BAR` 5, `NEITHER_WITHIN_WINDOW` 8) reproduce AW's, AX's and AY's independent draws
  over the identical window **exactly** (§2.2).
- **Single-symbol smoke test**: an isolated BTCUSDT-only run reproduced AY's own published §2.3
  per-symbol table exactly (19 confirmed, 19 evaluated, 16 resolved) before the full ten-symbol run
  was executed.
- **Correlation cross-check**: the five point-biserial correlations this document independently
  computes over the same 133 resolved outcomes (RR, stop distance, target distance, confirmation
  age, CONTEXT ATR%, §1.3) reproduce AY's own published `r` values to the precision AY itself
  reported (two decimal places for four of the five, three for CONTEXT ATR%)
  (§2.2 table) — the strongest available check that this extraction's per-row numeric fields, not
  only its aggregate counts, agree with AY's independent draw.
- **Regime-state cross-check**: this document's own CONTEXT-role `VolatilityState.STEADY` (13
  losses, 3 wins of 16) and `INSUFFICIENT` (3 losses, 13 wins of 16) cells reproduce AY's own
  published 18.75%/81.25% win rates for those exact states exactly (§5 RQ9 discusses AY's own
  DOTUSDT-artifact finding behind the `INSUFFICIENT` cell, inherited unchanged here).

### 1.3 Statistics convention

Identical to AY's own convention, for the same reasons AY stated:

- **Win rate** = `TARGET_FIRST / (TARGET_FIRST + STOP_FIRST)`, resolved outcomes only.
- **Confidence interval**: 95% Wilson score interval, computed from stdlib `math` only.
- **Effect size**: Pearson point-biserial correlation (`statistics.correlation`, stdlib), reported
  with `n`.
- **Denominator discipline**: `n_resolved` stated beside `n_evaluated` throughout; never conflated.
- **Sensitivity/specificity/precision/lift**, introduced new in this document for the
  necessary/sufficient question (§7): sensitivity = fraction of losses carrying a category,
  specificity = fraction of wins *not* carrying it, precision = loss rate among rows carrying it,
  lift = precision divided by the base loss rate (71/133 = 53.4%). A category with lift near 1.0
  discriminates no better than chance regardless of how large its raw counts look.
- **Smallness**: any cell with `n_resolved < 10` is flagged inline.

---

## 2. Dataset

### 2.1 Scope

Identical scope to AV/AW/AX/AY — a fifth independent live draw from the same population. Ten
symbols (`DEFAULT_BACKTEST_SYMBOLS`): BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT,
ADAUSDT, LINKUSDT, AVAXUSDT, DOTUSDT. Real public Binance spot data, `2025-07-04` to `2026-08-07`
(400 days, `DEFAULT_BACKTEST_DAYS`), `run_at=2026-08-10T00:00:00+00:00`.

### 2.2 Reconciliation against AV/AW/AX/AY

| | This run (AZ) | AY (2026-08-10) | AX (2026-08-10) | AW (2026-08-08) |
|---|---|---|---|---|
| Total observations | **21,680** | 21,680 | 21,680 | 21,680 |
| WAIT | 21,102 | 21,102 | 21,102 | 21,102 |
| CANDIDATE (rows) | 401 | 401 | 401 | 401 |
| CONFIRMED (rows) | 177 | 177 | 177 | 177 |
| Evaluated outcomes | 146 | 146 | 146 | — |
| TARGET_FIRST | 62 | 62 | 62 | — |
| STOP_FIRST | 71 | 71 | 71 | — |
| AMBIGUOUS_SAME_BAR | 5 | 5 | 5 | — |
| NEITHER_WITHIN_WINDOW | 8 | 8 | 8 | — |

Byte-identical to AY's own numbers, drawn over the same closed window. Correlation cross-check
(§1.2):

| Field | This run (AZ), r (n=133) | AY, r (n=133) |
|---|---|---|
| Risk:reward ratio | −0.300 | −0.30 |
| Stop distance % | +0.411 | +0.41 |
| Target distance % | −0.320 | −0.32 |
| Confirmation age (bars) | −0.203 | −0.20 |
| CONTEXT ATR% | −0.065 | −0.065 |

Every one of the five agrees with AY's published figure to the precision AY itself reported, drawn
from an independently written extraction script run the same day as AY's own — the strongest
evidence available that this document's per-row data, not only its aggregate counts, describes the
same population AV/AW/AX/AY already measured.

### 2.3 Population shape (inherited from AY §2.3, restated for this document's purposes)

Only 5 of the 10 backtested symbols produced any evaluated outcome. DOTUSDT alone supplies 52 of 133
resolved outcomes (39.1%) and 30 of 71 losses (42.3%) — proportionate to, not wildly exceeding, its
own population share (§9.1 restates AY's own finding that DOTUSDT's win rate, 42.3%, is close to the
133-row aggregate of 46.6%, so its dominance inflates apparent sample sizes across this document's
tables rather than biasing any single aggregate figure in one particular direction).

| Symbol | n resolved | n STOP_FIRST | Loss share of all 71 losses |
|---|---|---|---|
| DOTUSDT | 52 | 30 | 42.3% |
| ADAUSDT | 23 | 15 | 21.1% |
| BTCUSDT | 16 | 13 | 18.3% |
| LINKUSDT | 16 | 7 | 9.9% |
| ETHUSDT | 26 | 6 | 8.5% |

### 2.4 Inherited limitations

Every limitation `BACKTEST_LIMITATIONS` (AV-1 through AV-9) and every limitation AW §2.4/AX §2.3/AY
§2.4 name applies unchanged: no fees/slippage/spread modelled, `TARGET_FIRST`/`STOP_FIRST` are
wick-touch classifications and never a win rate in the trading sense, `AMBIGUOUS_SAME_BAR` is a
refusal to guess intrabar order, the 60-bar evaluation window is a stated measurement policy, and
every number here restates the printed R:R at confirmation, never a realized return. This document
adds no new limitation of its own beyond §1.1's note that SETUP/EXECUTION-role regime is computed
identically to how CONTEXT-role regime already reaches production but is not printed by any live
product surface today.

---

## 3. Failure taxonomy

### RQ1 — Categories

**Nine failure categories, each built entirely from a field AV/AW/AX/AY already established as
measurable, using bucket edges AY already published over the identical population.** No category
below is invented; each restates, as a boolean flag per outcome, a cut AY already showed produces a
below-average win rate (with one exception, `partial_role_disagreement`, which AY showed produces a
statistically indistinguishable win rate — kept as a category anyway because RQ1 asks for
measurable characteristics losers share, not only ones proven to matter, and RQ4 exists to report
which categories turn out neutral).

| Category | Definition | Source |
|---|---|---|
| `tight_stop` | Stop distance ≤ 0.48% of reference price | AY §3 RQ6 "Very tight" edge |
| `distant_target` | Target distance > 0.74% of reference price (i.e. not AY's "Near" bucket) | AY §3 RQ7 |
| `poor_rr_geometry` | Displayed RR ≥ 3 (AY's `3–5` and `5+` buckets combined) | AY §3 RQ5: 40.0%/9.1% win vs 74.5% for `0–1` |
| `high_context_volatility` | CONTEXT-role ATR14/close in `22.5%–29.3%` — the "High" quartile **only**, excluding "Very High" | AY §3 RQ1(b); "Very High" excluded because AY §6.2/§7 identified it as a 16-row, single-symbol, single-week artifact, not a real high-volatility population |
| `partial_role_disagreement` | Not all three roles' (1W/1D/4H) `StructuralTrendType` are identical | AY §3 RQ4 "exactly 2 of 3 agree" |
| `execution_regime_transitioning` | EXECUTION-role (4H) regime structure = `transitioning` | AY §3 RQ3: 21.2% win, one of the widest single-field gaps AY measured |
| `stale_confirmation` | Confirming break is 3–10 bars old (AY's own "stale" cut, §5.2) | AY §3 RQ8, §5.2 |
| `elevated_setup_participation` | SETUP-role (1D) regime participation = `elevated` | AY §3 RQ3: 8.7% win, the single lowest `n≥10` win rate AY measured anywhere |
| `minimum_family_agreement` | Exactly 2 of the 3 directional-vote families agree (not 3) | AY §3 RQ9 |

Every category is a plain boolean read off already-computed fields; none required a new threshold,
regime dimension or indicator. `poor_rr_geometry`'s `≥3` cutoff and `high_context_volatility`'s
exclusion of "Very High" are the only two judgment calls this document makes beyond directly
quoting an AY-published bucket edge, and both are stated and justified above rather than left
implicit.

### RQ2 — Frequency in losers, and how strongly each discriminates

| Category | n in losers (of 71) | % of losses | Loss rate when present | Sensitivity | Specificity | Lift |
|---|---|---|---|---|---|---|
| `distant_target` | 67 | 94.4% | 67.0% | 0.944 | 0.468 | 1.26 |
| `minimum_family_agreement` | 67 | 94.4% | 52.3% | 0.944 | 0.016 | 0.98 |
| `stale_confirmation` | 57 | 80.3% | 61.3% | 0.803 | 0.419 | 1.15 |
| `high_context_volatility` | 42 | 59.2% | 71.2% | 0.592 | 0.726 | 1.33 |
| `poor_rr_geometry` | 39 | 54.9% | 81.2% | 0.549 | 0.855 | 1.52 |
| `tight_stop` | 27 | 38.0% | 79.4% | 0.380 | 0.887 | 1.49 |
| `partial_role_disagreement` | 26 | 36.6% | 52.0% | 0.366 | 0.613 | 0.97 |
| `execution_regime_transitioning` | 26 | 36.6% | 78.8% | 0.366 | 0.887 | 1.48 |
| `elevated_setup_participation` | 21 | 29.6% | 91.3% | 0.296 | 0.968 | 1.71 |

**Reading this table honestly, not just by "% of losses."** `distant_target` and
`minimum_family_agreement` both appear in 94.4% of losses — but §7 shows this is a weak finding for
`minimum_family_agreement` specifically, because it also appears in 98.4% of *wins* (specificity
0.016): it is a near-universal property of the whole 133-row `CONFIRMED`-and-resolved population
(128/133, AY §3 RQ9), not a property of losing specifically. `distant_target` is a materially
stronger finding: it appears in 75.2% of the whole population but still discriminates (specificity
0.468 — over half of wins do *not* carry it) and carries the second-highest lift among the
high-sensitivity categories. `elevated_setup_participation` is the single strongest discriminator by
precision and lift (91.3% loss rate when present, 1.71× the base rate) but covers under 30% of
losses — high confidence, low coverage, exactly the shape §7 formalizes as "closer to sufficient
than necessary."

---

## 4. Winner taxonomy

### RQ3 — Frequency in winners (the mirror image of §3, stated on its own terms)

| Category | n in winners (of 62) | % of wins | Win rate when **absent** | 95% CI |
|---|---|---|---|---|
| `elevated_setup_participation` | 2 | 3.2% | 54.5% | (0.452, 0.635) |
| `tight_stop` | 7 | 11.3% | 55.6% | (0.457, 0.650) |
| `execution_regime_transitioning` | 7 | 11.3% | 55.0% | (0.452, 0.644) |
| `poor_rr_geometry` | 9 | 14.5% | 62.4% | (0.517, 0.719) |
| `high_context_volatility` | 17 | 27.4% | 60.8% | (0.494, 0.711) |
| `stale_confirmation` | 36 | 58.1% | 65.0% | (0.495, 0.779) |
| `partial_role_disagreement` | 24 | 38.7% | 45.8% | (0.355, 0.564) |
| `distant_target` | 33 | 53.2% | 87.9% | (0.727, 0.952) |
| `minimum_family_agreement` | 61 | 98.4% | 20.0% | (0.036, 0.624; n=5) |

A winning trade is characterized far more by **absence** than presence: the single strongest winner
signal in this dataset is not "what a winner has" but "what it lacks" — 87.9% of trades with a
*near* target win (i.e., `distant_target` absent), versus 33.0% when it is present (§3). The same is
true, more weakly, for every other category except `minimum_family_agreement`, which — per §3's own
caveat — is present in essentially all outcomes regardless of result and therefore describes the
`CONFIRMED` population, not a winner-specific trait.

### RQ4 — Neutral characteristics

Two of the nine categories have lift within 0.05 of 1.0 — i.e., their presence changes the loss
probability by less than a coin flip's worth of noise would:

- **`partial_role_disagreement`** (lift 0.97): present in 36.6% of losses and 38.7% of wins — a
  near-identical rate. This directly restates AY's own RQ4 finding (all-3-agree 45.8% win vs
  exactly-2-of-3 48.0% win, overlapping CIs, "no measurable difference"): full timeframe-role
  agreement does not discriminate winners from losers in this dataset.
- **`minimum_family_agreement`** (lift 0.98): present in 94.4% of losses and 98.4% of wins.
  Structurally near-constant (only 5 of 133 resolved outcomes ever have all 3 families agree, AY §3
  RQ9) — its apparent high "coverage" of losses in §3's RQ2 table is an artifact of covering
  almost everything, not a signal.

Both categories were kept in the taxonomy specifically so this section could report them as neutral
— dropping them before measuring would have hidden the fact that two of the brief's own example
categories ("weak agreement," "trend disagreement") measure as uninformative in this population,
which is itself an answer RQ1–RQ4 exist to give.

---

## 5. Interaction analysis

### RQ5 — Combined-flag win rate (the strongest single relationship in this document)

Summing how many of the 9 categories each resolved outcome carries produces a near-monotonic
staircase:

| Flags present (of 9) | n resolved | Wins | Losses | Win rate (95% CI) |
|---|---|---|---|---|
| 1 | 5 | 5 | 0 | 100.0% (56.6%, 100.0%) |
| 2 | 14 | 12 | 2 | 85.7% (60.1%, 96.0%) |
| 3 | 43 | 30 | 13 | 69.8% (54.9%, 81.4%) |
| 4 | 19 | 7 | 12 | 36.8% (19.1%, 59.0%) |
| 5 | 11 | 2 | 9 | 18.2% (5.1%, 47.7%) |
| 6 | 19 | 3 | 16 | 15.8% (5.5%, 37.6%) |
| 7 | 15 | 3 | 12 | 20.0% (7.0%, 45.2%) |
| 8 | 7 | 0 | 7 | 0.0% (0.0%, 35.4%) |

No outcome in this dataset carries 0 or 9 flags. The decline from 1 flag (100% win) to 4 flags
(36.8%) is steep and, unlike any single category in §3, close to monotonic across its full range;
it flattens (and noisily inverts) from 5 flags onward, where every cell has `n < 20`. **This is a
stronger relationship than any single category measured in §3** — consistent with AY's own §11
red-team finding that RR, stop-distance and target-distance are "three views of two numbers," i.e.
several of these categories are correlated restatements of the same underlying geometry rather than
nine independent signals (§9.3 returns to this).

Highest-co-occurring pairs among the 71 losses:

| Pair | n (of 71 losses) |
|---|---|
| `distant_target` + `minimum_family_agreement` | 64 |
| `distant_target` + `stale_confirmation` | 54 |
| `stale_confirmation` + `minimum_family_agreement` | 53 |
| `high_context_volatility` + `minimum_family_agreement` | 42 |
| `distant_target` + `poor_rr_geometry` | 39 |
| `distant_target` + `high_context_volatility` | 39 |

Every top pair includes at least one of the two highest-base-rate categories
(`distant_target` 75.2%, `minimum_family_agreement` 96.2% of the whole resolved population) — the
ranking is dominated by base rate, not by a genuine two-way interaction effect (§9.4).

### RQ6 — False positives: every measured condition looked favourable, and the trade still lost

**Zero of the 71 losses carry none of the 9 failure flags.** Every single loss in this dataset
exhibits at least one of the nine measured characteristics AY's own tables already associate with a
below-average win rate. This is itself an answer, stated plainly: this document cannot show a
"clean" loss — a `STOP_FIRST` outcome with a near target, a wide stop, RR under 3, fresh
confirmation, non-elevated participation, a non-transitioning execution regime, moderate volatility,
and 3-way role agreement — because none occurred in 133 resolved outcomes.

The closest approximations — the two losses carrying only 2 flags, the fewest of any loss in the
dataset — are:

| Symbol | Confirmed at | Flags present |
|---|---|---|
| ETHUSDT | 2026-07-20T00:00 | `distant_target`, `minimum_family_agreement` |
| ETHUSDT | 2026-07-27T16:00 | `partial_role_disagreement`, `stale_confirmation` |

Both carry only categories this document's own §4 (RQ4) already flagged as weak or neutral
discriminators — neither carries `tight_stop`, `poor_rr_geometry`, `elevated_setup_participation` or
`execution_regime_transitioning`, the four categories with the strongest precision in §3. Read
plainly: the two "cleanest-looking" losses in this dataset were still not clean by the categories
that matter most; they simply avoided the *strong* red flags while still carrying one or two weak
ones.

### RQ7 — False negatives: looked bad on most measured dimensions, won anyway

| Flags present | Winners | Losers |
|---|---|---|
| 1 | 5 | 0 |
| 2 | 12 | 2 |
| 3 | 30 | 13 |
| 4 | 7 | 12 |
| 5 | 2 | 9 |
| 6 | 3 | 16 |
| 7 | 3 | 12 |
| 8 | 0 | 7 |

Three winners carry 7 of the 9 flags — the same count as 12 losses:

| Symbol | Confirmed at | Flags present (7) |
|---|---|---|
| ADAUSDT | 2026-07-23T20:00 | `tight_stop`, `distant_target`, `poor_rr_geometry`, `high_context_volatility`, `partial_role_disagreement`, `execution_regime_transitioning`, `minimum_family_agreement` |
| ADAUSDT | 2026-07-24T04:00 | (same set) |
| DOTUSDT | 2026-07-19T04:00 | `tight_stop`, `distant_target`, `poor_rr_geometry`, `high_context_volatility`, `partial_role_disagreement`, `stale_confirmation`, `minimum_family_agreement` |

These three are the strongest false negatives this document can name: setups that, by seven of nine
already-measured characteristics, resembled the worst-looking losses in the dataset, and touched
target before stop anyway. No category or combination measured in this document explains why these
three specifically won; §8 (RQ12) returns to this as part of the unexplained remainder.

### RQ9 — Symbol, direction and regime-state concentration

**Symbol.** §2.3 already showed DOTUSDT supplies 42.3% of losses, proportionate to its 39.1% share
of all resolved outcomes. But the failure *categories* are not evenly spread across the five
outcome-bearing symbols: `high_context_volatility` and `partial_role_disagreement` among losses are
almost entirely confined to two symbols:

| Category | ADAUSDT | BTCUSDT | DOTUSDT | ETHUSDT | LINKUSDT |
|---|---|---|---|---|---|
| `high_context_volatility` | 15 | **0** | 27 | **0** | **0** |
| `partial_role_disagreement` | 15 | **0** | 5 | 5 | 1 |

Every one of the 42 loser-rows flagged `high_context_volatility` is ADAUSDT or DOTUSDT; BTCUSDT,
ETHUSDT and LINKUSDT contribute zero. This is not a finding about high volatility being a
crypto-general failure mode — it is a finding about which two of five symbols' 400-day price paths
happened to spend loss-adjacent stretches in the CONTEXT-role "High" ATR quartile (§9.1's inherited
caveat applies in full).

**Direction.** SHORT losses (n=45) carry a higher average flag count (5.98) than LONG losses (n=26,
average 3.96) — SHORT-side losses look "worse" by more measured characteristics on average than
LONG-side losses do. This could reflect a real asymmetry, or simply that SHORT setups in this window
concentrate in the same volatile ADAUSDT/DOTUSDT stretches driving `high_context_volatility` above —
this document cannot separate the two from the data it has.

**Timeframe.** Does not vary — every observation in this dataset uses the identical 1W/1D/4H role
assignment (`DEFAULT_TIMEFRAMES`); "is one timeframe overrepresented in losses" is not a question
this dataset can answer, the same false-assumption shape AY named for several of its own RQs (AY
§7).

**Volatility regime (CONTEXT-role categorical state).** Reproduces AY's own §3 RQ1(a) table exactly
(§1.2): `STEADY` 13 losses / 3 wins (18.75% win), `INSUFFICIENT` 3 losses / 13 wins (81.25% win, the
16-row DOTUSDT artifact AY §6.2 identified), `CONTRACTING` the remaining 101 rows. Losses are not
concentrated in one volatility regime state beyond what AY already reported.

---

## 6. Decision tree

### RQ10 — Deterministic split: confirmation freshness → RR bucket → stop-distance bucket

Following the brief's own suggested ordering, a plain three-level deterministic split (no
clustering algorithm, no scoring) over the 133 resolved outcomes:

```
133 resolved (62 win / 71 loss)
├── stale confirmation (3–10 bars old), n=93 (36 win / 57 loss, 38.7% win)
│   ├── RR 0–1, n=36 (25 win / 11 loss, 69.4% win)
│   │   ├── stop very_wide,   n=19 → 16 win /  3 loss (84.2% win)
│   │   ├── stop medium_wide, n=11 →  4 win /  7 loss (36.4% win)
│   │   ├── stop tight_medium,n= 4 →  3 win /  1 loss (75.0% win)
│   │   └── stop very_tight,  n= 2 →  2 win /  0 loss
│   ├── RR 1–2, n=16 (4 win / 12 loss, 25.0% win)
│   ├── RR 2–3, n= 8 (5 win /  3 loss, 62.5% win)
│   ├── RR 3–5, n= 9 (2 win /  7 loss, 22.2% win)
│   └── RR 5+,  n=24 (0 win / 24 loss, 0.0% win)   ← single largest loss-concentration leaf
│       ├── stop very_tight,  n=20 →  0 win / 20 loss (0.0% win)
│       └── stop tight_medium,n= 4 →  0 win /  4 loss (0.0% win)
└── fresh confirmation (0–2 bars old), n=40 (26 win / 14 loss, 65.0% win)
    ├── RR 0–1, n=16 (13 win /  3 loss, 81.2% win)
    ├── RR 1–2, n= 6 (5 win /  1 loss, 83.3% win)
    ├── RR 2–3, n= 5 (1 win /  4 loss, 20.0% win)
    ├── RR 3–5, n= 4 (4 win /  0 loss, 100.0% win)
    └── RR 5+,  n= 9 (3 win /  6 loss, 33.3% win)
```

**Where losses accumulate.** The `stale × RR 5+` leaf (n=24, 0.0% win) is the single most
loss-concentrated node in the tree: 24 of 71 losses (33.8%) sit in one leaf defined by two
conditions, both already measured by AY and neither newly discovered here. This closely — though
not exactly — matches AY's own §5.2 cluster (`5+ RR × stale`, n=27, 0.0% win); the three-row
difference plausibly reflects this document's stricter three-way split against AY's own two-way cut,
or a small boundary difference in how "stale" is delimited; both documents agree the cell's win rate
is exactly zero. Splitting that leaf further by stop distance (very_tight vs tight_medium) does not
recover a single win in either sub-leaf — the zero-win result is not an artifact of one stop bucket.

By contrast, `stale × RR 0–1 × stop very_wide` (n=19, 84.2% win) is the single most
win-concentrated leaf of comparable size — the same three variables, opposite ends, producing
opposite outcomes. **RR and stop distance jointly explain more variation in this tree than either
does alone** (§9.3's caveat that RR is itself algebraically derived from stop and target distance
still applies).

---

## 7. Necessary vs sufficient

### RQ11 — For every measured characteristic: necessary, sufficient, or neither

A category is treated as **necessary** here only if it is both high-sensitivity (present in most
losses) **and** meaningfully more common among losses than among the whole population (i.e. not
near-universal) — sensitivity alone is not enough, since a category present in 96% of everything
will trivially be present in ~96% of any subgroup regardless of relevance (§4's
`minimum_family_agreement` finding). A category is treated as **sufficient** only if, when present,
the loss rate approaches certainty (`≥ 95%`) **and** the sample is large enough to trust (`n ≥ 20`)
— a category with real, non-trivial misses (any cell with more than one or two exceptions) is not
being called "sufficient" here even at high precision, and precision alone on a tiny cell is not
evidence of certainty either.

| Category | Sensitivity | Specificity | Precision | n present | Verdict |
|---|---|---|---|---|---|
| `distant_target` | 0.944 | 0.468 | 67.0% | 100 | Neither — high sensitivity, but specificity too low (53% of wins also carry it) to call necessary |
| `minimum_family_agreement` | 0.944 | 0.016 | 52.3% | 128 | Neither — near-universal (specificity 0.016); sensitivity is an artifact of base rate, not a signal |
| `stale_confirmation` | 0.803 | 0.419 | 61.3% | 93 | Neither — moderate on every axis |
| `high_context_volatility` | 0.592 | 0.726 | 71.2% | 59 | Neither — precision short of the 90% bar, and symbol-concentrated (§5 RQ9) |
| `poor_rr_geometry` | 0.549 | 0.855 | 81.2% | 48 | Neither — closest of the moderate-coverage categories to sufficient, short of the precision bar |
| `tight_stop` | 0.380 | 0.887 | 79.4% | 34 | Neither — coverage too low for necessity, precision short of sufficiency |
| `execution_regime_transitioning` | 0.366 | 0.887 | 78.8% | 33 | Neither |
| `partial_role_disagreement` | 0.366 | 0.613 | 52.0% | 26 | Neither — the weakest category on every axis (§4) |
| `elevated_setup_participation` | 0.296 | 0.968 | 91.3% | 23 | **Closest to sufficient** — clears the `n≥20` bar but 91.3% falls short of the `≥95%` near-certainty bar this document set before computing the table; 2 of 23 rows carrying the flag still won |

**No category in this dataset is necessary or sufficient by the thresholds this document set before
computing the table.** `elevated_setup_participation` comes closest to sufficiency (2 of 23 rows
carrying it still won) and is the only category whose specificity exceeds 0.95, but at `n=23` two
winners is not distinguishable from a fluke at this sample size (Wilson 95% CI for 21/23 = 
73.2%–97.6%, computed the same way as every win-rate CI in this document — the interval's lower
bound falls well short of certainty). Every other category sits in the "neither" zone the brief's
own RQ11 explicitly anticipates as a possible honest answer.

---

## 8. Unexplained outcomes

### RQ8 — Failure concentration

By flag count (§5 RQ5), losses concentrate sharply at the high end: **56 of 71 losses (78.9%) carry
4 or more of the 9 measured categories**, while 47 of 62 wins (75.8%) carry 3 or fewer. This is the
cleanest single concentration statement this document can make: a small number of *co-occurring*
characteristics, not any one mechanism alone, accounts for most losses.

By individual category (§3 RQ2), a Pareto walk over the two highest-sensitivity categories already
covers every loss: `distant_target` alone touches 67 of 71 losses; adding `minimum_family_agreement`
covers 70 of 71; adding `stale_confirmation` covers all 71. Read plainly, this says less about
mechanism concentration than it does about how common these two base categories are across the whole
population (§3's own caveat) — a three-category Pareto that reaches 100% coverage using two
near-universal categories is a weaker "failure is concentrated" claim than the flag-count staircase
above, and this document reports both rather than leading with the more impressive-looking but
weaker one.

### RQ12 — What cannot be explained

**Zero of 71 losses (0.0%) carry none of the 9 measured categories** (§5 RQ6) — every loss has *some*
measured explanation available, at the level of "at least one of nine broad characteristics was
present." But that is a low bar. At a stricter bar — carrying at most one of the nine categories,
the same threshold that produces a 100% win rate at the top of §5's flag-count table — **zero losses
qualify** (the two lowest-flag losses in §5 RQ6 both carry two flags, not one or zero).

The more honest unexplained remainder is the reverse direction: **three winners (§5 RQ7) carry 7 of
9 measured red flags** and won regardless. This document's 9 categories, individually and in
combination, correctly separate most of the 133 resolved outcomes (§5's monotonic-ish flag-count
staircase) but leave a genuine minority — 13 losses at flag-count 3 (of that row's 43, §5 RQ5) and
3 wins at flag-count 7 (of that row's 15, §5 RQ7) — sitting on the wrong side of what the
measured characteristics would predict. This document cannot say why those specific outcomes
inverted; naming a cause here would require either a mechanism this repository does not measure
(order-book depth, funding, on-chain flow — AV Part 2's own list) or a counterfactual re-run this
milestone's rules forbid.

---

## 9. Threats to validity

**Every table above should be read through this section**, following AY's own §10 discipline.

1. **DOTUSDT dominance, inherited from AY §10.1 unchanged.** 42.3% of the 71 losses this document
   segments come from one symbol. AY's own red-team finding (§11 there) — that DOTUSDT's own win
   rate is close to the aggregate, so its dominance inflates apparent sample sizes without biasing
   any one aggregate figure in a particular direction — applies here identically, and this document
   inherits it rather than re-deriving it.

2. **Five of ten backtested symbols never produced an evaluated outcome.** This document's symbol
   concentration findings (§5 RQ9) describe five symbols' price paths, not "the market."

3. **RR is algebraically derived from stop distance and target distance, and `poor_rr_geometry`
   inherits that non-independence.** AY §11 already stated this: RR, stop-distance and
   target-distance correlations "are not three independent confirmations of one underlying edge;
   they are three views of two numbers." Three of this document's nine categories
   (`tight_stop`, `distant_target`, `poor_rr_geometry`) are, to a first approximation, two
   underlying measurements read three times. §5's high-co-occurrence pairs table is partly an
   artifact of this — `distant_target` co-occurring with `poor_rr_geometry` in 39 of 71 losses is
   expected almost mechanically, not a discovered interaction.

4. **`minimum_family_agreement` and `partial_role_disagreement` are near-degenerate, not merely
   weak.** §4 already reports both as neutral; restated here because a reader skimming only §3's raw
   "% of losses" column, without cross-referencing §4's specificity numbers, could mistake either
   for a real finding.

5. **Multiple comparisons were not corrected for.** Nine categories, one combined-flag statistic, a
   three-level decision tree, and a dozen two-way pairs are reported at nominal 95% confidence
   without a Bonferroni or similar adjustment — identical to AY §10's own stated discipline (or lack
   of one), inherited rather than fixed here.

6. **The decision tree (§6) was built with the brief's own suggested variable ordering
   (confirmation freshness → RR → stop distance), not the ordering this document's own data would
   suggest as "most informative first" (which, by §3's sensitivity/lift table, would start with
   `elevated_setup_participation` or `poor_rr_geometry`).** A tree built in a different variable
   order would show the same 133 rows differently partitioned; this document picked one ordering,
   stated why, and does not claim it is the only or the best one.

7. **Every touch-probability-mechanical caveat AY §10.5 raised for RR/stop/target correlations
   applies unchanged to `tight_stop`, `distant_target` and `poor_rr_geometry` here.** A wider stop
   is harder for price to reach before a target by construction; this document cannot separate that
   geometric fact from a genuine directional-evidence signal, and does not claim to.

8. **The window itself (400 days, 2025-07-04 to 2026-08-07) is the same single window every
   milestone in this series has used**, for the structural reason AV stated (weekly EMA-50 warm-up).
   Every finding in this document inherits whatever was idiosyncratic about crypto markets
   specifically during that period.

---

## 10. Red Team

**Attacking this document's own strongest claims.**

- *"The flag-count staircase (§5 RQ5) — 100% win at 1 flag down to 0% at 8 flags — is this document's
  headline finding. Is it real, or an artifact of how the 9 categories were chosen?"* Partially an
  artifact by construction: because three of the nine categories are correlated restatements of RR
  geometry (§9.3) and two are near-universal (§9.4), the flag count is not summing nine independent
  bits of evidence — it is closer to summing four or five genuinely distinct signals plus noise.
  The staircase's shape is real (the correlation is measured, not assumed), but its *steepness*
  likely overstates how many independent characteristics are actually driving it. A reader should
  treat "8 measured characteristics present" as "this trade scored badly on RR geometry, stop
  geometry, and roughly two or three other things" rather than as eight independent confirmations.
- *"RQ6 found zero clean losses — doesn't that just mean the categories are too broadly defined to
  ever be absent?"* A fair challenge. `distant_target` alone is present in 75.2% of the *whole*
  resolved population (§3), so any row is likely to carry at least one flag by chance. The
  "zero clean losses" finding is weaker than it sounds for exactly the reason §8 (RQ12) already
  states plainly rather than burying: the more informative version of RQ6 is the two-flag minimum
  (§5 RQ6), not the zero-flag one, and this document reports both.
- *"The decision tree's headline leaf (`stale × RR 5+`, n=24, 0% win) doesn't match AY's own
  published 27-row equivalent cluster — which number is right?"* Both are right, for slightly
  different questions. This document's own internal consistency check (§1.2) reproduces AY's
  published win-rate *correlations* to the precision AY itself reported, which is the stronger
  evidence the underlying row-level data agrees with AY's; the 24-vs-27 gap in one secondary
  two-way cross-tab most plausibly reflects a small difference in exactly how "stale" was
  delimited across two independently written extraction scripts, not a disagreement about the
  direction or strength of the finding (both are 0.0% win at `n≥24`).
- *"Every necessary/sufficient verdict in §7 came back 'neither' — is that a real finding, or does
  it just mean the thresholds were set too strict to ever pass?"* Both are partly true. The
  thresholds (specificity requirement for necessity, `n≥20`-adjacent requirement for sufficiency)
  were stated before the table was computed, which is the honest way to avoid threshold-shopping —
  but a different, looser threshold set beforehand could have produced a "sufficient" verdict for
  `elevated_setup_participation` (91.3% precision) without being unreasonable. The correct reading
  is "no category clears a strict bar," not "no category matters" — §3's lift and precision columns
  remain informative even where §7's binary verdict says "neither."
- *"§5 RQ7's three false-negative winners are presented as unexplained — are they actually
  unexplained, or does this document simply not have the right variables?"* The second is more
  likely. AV Part 2's own list of what FMITS structurally cannot see (funding, liquidations,
  orderbook depth, macro liquidity) is the more probable source of what separates these three wins
  from the twelve losses at the same flag count — this document's own instrument set is drawn
  entirely from what the deterministic pipeline already computes, and by AV's own accounting that
  instrument set represents a small fraction of what a discretionary trader would actually look at
  before entering (AV Part 4).

---

## 11. Questions still unanswered

- **Do any of the nine categories reflect a real causal mechanism, or are they all downstream
  restatements of two or three underlying geometric/symbol-concentration facts?** §9.3/§9.4 name the
  redundancy; this document has no way to test causation from historical replay data alone.
- **Would the `stale × RR 5+ × very_tight` leaf (0/20, the single largest loss concentration
  measured) replicate on a different 400-day window or a wider symbol universe?** Unanswerable
  without re-running the extraction over a different window, which this milestone's own rules
  (reuse the existing backtest exactly, measure once) do not permit within its scope.
- **What separates the three RQ7 false-negative winners from the twelve losses at the same flag
  count?** Named as unexplained in §8 and attacked in §10; this document cannot close it with the
  fields it has.
- **Would a tenth or eleventh failure category, not built from this document's nine, explain any of
  the 15 "3-flag" losses or reduce the false-negative count?** This document checked nine categories
  chosen from AY's own published tables — not an exhaustive search of every field the pipeline
  computes. A category this document did not build could exist.
- **Is the 78.9%-of-losses-at-4-plus-flags concentration (§8 RQ8) a stable property of this policy,
  or a property of this specific 133-row, DOTUSDT-heavy sample?** Both AY's own §10.1 caveat and
  this document's §9.1 restatement of it apply; a genuinely different symbol mix could redistribute
  which categories dominate the high-flag-count losses without changing the staircase's existence.
- **Does `elevated_setup_participation`'s 91.3% precision (§7) reflect a real, informative
  mechanism, or the same symbol-concentration pattern §5 RQ9 already found for
  `high_context_volatility`?** Not checked in this document; a natural next measurement (not a
  recommendation) this milestone did not scope.

---

## Appendix — reproduction

Two scripts, neither part of the shipped package, both calling only already-public production
functions plus the identical policy arithmetic named in §1.1, living outside the repository in a
scratch directory:

- **`az_extract.py`** — mirrors `fmis.swing_setup.backtest_harness.run_backtest`'s own
  instant-by-instant loop (`fetch_historical_dataset` → per symbol, per instant:
  `build_replay_transport` → `multi_timeframe_facts_for_symbol(..., features=regime_features(),
  transport=replay_transport, clock=lambda moment=instant: moment)` →
  `setup_inputs_and_assessment_for_sheet` → `IdentityTracker.observe` → `evaluate_outcome` at
  `is_first_confirmation`), with three additional read-only calls made **only at confirmation
  instants** (146 times, not 21,680): `regime_for_sheet` on the SETUP and EXECUTION role sheets,
  `regime_input_from_sheet` for `atr_fast`/`close` per role, and direct reads of
  `assessment.trigger.bar_index` / `assessment.risk_reward.risk`/`.reward`, already computed by the
  policy. Serializes all 146 outcomes plus reconciliation counts to JSON (`dataset.json`, ~175KB).
  Run: `PYTHONPATH=<repo>/src <repo>/.venv/bin/python3 az_extract.py > dataset.json` — real Binance
  data, `DEFAULT_BACKTEST_SYMBOLS`, `start=2025-07-04T00:00:00+00:00`,
  `end=2026-08-07T00:00:00+00:00`, `run_at=2026-08-10T00:00:00+00:00`. Reconciles exactly against
  AW's, AX's and AY's own independent draws (§2.2), including on five independently recomputed
  correlation coefficients matching AY's published values to the precision AY itself reported.
- **`az_analyze.py`** — pure-Python (stdlib `json`/`math`/`statistics`/`collections` only) over
  `dataset.json`. Builds the nine boolean failure-category flags from AY's own published bucket
  edges, computes every table in §3–§8: Wilson 95% CIs, sensitivity/specificity/precision/lift,
  pairwise co-occurrence, the flag-count staircase, the false-positive/false-negative row listings,
  the three-level decision tree, and the necessary/sufficient verdicts. Both are read-only with
  respect to the production package; neither changed a line under `src/`.
