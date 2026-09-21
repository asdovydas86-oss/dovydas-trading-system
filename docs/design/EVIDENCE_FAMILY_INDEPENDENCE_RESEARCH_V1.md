# Evidence Family Independence Research V1

**Milestone:** AW
**Status:** Investigation complete — measurement only, no code changes
**Date:** 2026-08-08
**Model:** Claude Sonnet 5
**Repository state:** `main`, working tree unchanged by this milestone (see §0.3)
**Type:** Research investigation, not a design record — produces no contract, no ADR, no backlog entry

---

## Table of contents

- [0. What this document is](#0-what-this-document-is)
- Part 1 — Methodology
- Part 2 — Dataset
- Part 3 — Measurements
- Part 4 — Statistical observations
- Part 5 — Unexpected findings
- Part 6 — What can and cannot be concluded
- Red team — alternative explanations attacked
- Appendix — reproduction

---

## 0. What this document is

### 0.1 The question

Report [0011](../../reports/0011_2026-08-08_SWING_SETUP_BACKTEST_V1_IMPLEMENTATION.md) §23 measured
that two of the Swing Setup Engine's three "independent" evidence families agree 75–79% of the time
when both are directional. That report's own §38 named the resulting question explicitly and declined
to answer it: does the `MINIMUM_AGREEING_FAMILIES = 2` policy
(`fmis.swing_setup.policy.py:69`) provide genuine independent corroboration, or does it sometimes
count the same market information twice? This milestone answers that question **by measurement**, over
a fresh, real historical dataset, with no theory offered in place of a number.

### 0.2 What this document is not

- Not a strategy change. `fmis/swing_setup/policy.py`, `fmis/market_regime/*`,
  `fmis/decision_support/*` and `fmis/structural_trend/*` have a zero-line diff from this milestone.
- Not a recommendation. Part 6 and the whole document end with facts. No sentence in this document
  says "should" about the product. Where a finding implies a natural follow-up question, that question
  is named without being answered.
- Not an ADR, not a backlog change, not a report under `reports/` (this is a `docs/design/` research
  record per the milestone's own instruction).
- Not a claim that this window, these ten symbols, or this measurement technique generalize beyond what
  is stated. Part 6 is deliberately conservative about this.

### 0.3 What changed in the repository

Nothing under `src/`, `tests/`, `docs/adr/`, `FMITS_PRODUCT_BACKLOG.md` or `FMITS_PRODUCT_CHANGELOG.md`.
This file is the only new artifact. The analysis scripts that produced every number in this document
live outside the repository, in a scratch directory, and are described in the Appendix so the work is
reproducible without being shipped as product code.

---

# Part 1 — Methodology

## 1.1 Data source: the unmodified production path, re-run

Every number in this document is derived from a fresh call to
`fmis.swing_setup.backtest_harness.run_backtest` — the exact, unmodified Milestone AV production
function, imported and called read-only. No line of that function, or of anything it calls
(`multi_timeframe_facts_for_symbol`, `setup_inputs_and_assessment_for_sheet`, `evaluate_setup`), was
changed to produce this research. The call used the same ten symbols, the same historical window and
the same timeframe roles as report 0011, so this dataset is a second, independent live draw from the
same population report 0011 measured, not a re-analysis of report 0011's own frozen numbers.

```
run_backtest(
    DEFAULT_BACKTEST_SYMBOLS,                          # the same 10-symbol universe
    start_time=2025-07-04T00:00:00Z,
    end_time=2026-08-07T00:00:00Z,                      # identical window to report 0011
    run_at=2026-08-08T00:00:00Z,
)
```

`HistoricalObservation.directional_factors` — already present on **every** observation, `WAIT`
included, per `docs/design/SWING_SETUP_BACKTEST_V1.md` §7 — is the raw material for every measurement
below: three `FamilyLean` entries per observation, `family` in
`{context_structural_trend, setup_structural_trend, setup_evidence_alignment}`, `lean` in
`{long, short, conflicting, unavailable}` (`fmis/swing_setup/models.py:97-113`).

## 1.2 Why a second run instead of re-analysing report 0011's numbers

Report 0011's own artifact is a rendered terminal report and a set of aggregate counts in a markdown
table — not a serialized dataset. Re-running the harness against live Binance data was the only way to
obtain the full per-observation record (all three leans, per observation, per symbol) needed to answer
RQ2–RQ10, which report 0011 never computed. §2.2 below reconciles the resulting counts against report
0011's aggregate numbers as a sanity check on both runs.

## 1.3 Definitions

**Family** — one of the three named strings above. **Lean** — one of the four values above. **Directional**
— a lean of `long` or `short`; `conflicting` and `unavailable` are both non-directional but for different,
stated reasons (`fmis/swing_setup/models.py:97-113`): `conflicting` means the family's own evidence
disagrees with itself (something was read, and it did not resolve); `unavailable` means nothing could be
read at all. This document keeps all four categories distinct throughout rather than collapsing
`conflicting`/`unavailable` into one "no signal" bucket, because §3.2 and §5 show the two families differ
sharply in *how* they abstain, and collapsing the categories would erase that difference.

**Pairwise agreement (RQ1)** — restricted to observations where *both* families of a pair are directional,
the fraction where they name the same side. This is exactly report 0011 §23's own metric, reproduced here
as a sanity check (§2.2) and then extended.

**Mutual information (RQ7)** — chosen over Pearson correlation because a lean is a categorical, unordered
value (there is no numeric distance between `long` and `conflicting`); correlation requires an arbitrary
numeric encoding that would itself be a hidden design choice. Mutual information `I(A;B) = H(A) - H(A|B)`,
computed in bits over the full four-symbol alphabet, measures how much knowing one family's exact reading
(including whether it is available or conflicted, not only its direction) reduces uncertainty about the
other's — with no assumption about the shape of the dependency. Reported alongside each family's own
entropy `H` and the conditional entropies, so a reader can see how much of each family's own uncertainty
the other family actually resolves.

**Chance-corrected agreement / kappa (RQ7, added beyond the brief's own RQ list)** — a raw agreement
percentage on a 2-outcome variable (long/short) is inflated by nothing more than both families sharing
the same base rate: two independent coins that each land heads 90% of the time will "agree" roughly 82%
of the time by chance alone. Restricted to the both-directional subsample, this document computes the
agreement rate expected under independence from each family's own observed long/short split within that
subsample, and reports Cohen's-kappa-style
`κ = (observed − expected) / (1 − expected)` — `0` means the raw agreement number is fully explained by
shared base rate, `1` means perfect agreement beyond what the base rate alone predicts. This statistic is
not in the milestone brief's RQ list; it was added because RQ7 ("correlation is not enough... estimate
actual information overlap") cannot be answered honestly from a raw percentage alone once the marginal
skew described in §3.2 is visible in the data — see §5.1 for why this mattered here specifically.

**Deciding vote / necessary vs. redundant (RQ3/RQ4/RQ8/RQ9)** — among observations that reached
`CANDIDATE` or `CONFIRMED` (`assessment.direction is not None`), a family that agreed with the resulting
direction is *necessary* if exactly two of the three families agreed (removing either one would drop
agreement below `MINIMUM_AGREEING_FAMILIES = 2` and the result would revert to `WAIT`), and *redundant*
if all three agreed (removing any one still leaves two, and the result is unchanged). This directly
operationalizes RQ3, RQ4, RQ8 and RQ9 as one measurement rather than four separate ones, because they are
the same question asked from four angles.

## 1.4 What "per timeframe" means for RQ1

`DEFAULT_TIMEFRAMES` (`fmis/pipeline/multi_timeframe.py:118-123`) fixes one interval per role for every
symbol in this dataset: `CONTEXT=1w`, `SETUP=1d`, `EXECUTION=4h`. Each evidence family lives on exactly
one role — `context_structural_trend` on 1w, `setup_structural_trend` and `setup_evidence_alignment` both
on 1d — so "per timeframe" and "per family" collapse to the same partition in this dataset; there is no
second timeframe configuration to compare against. This is stated plainly rather than fabricating a
per-timeframe breakdown that does not exist in the data.

## 1.5 Analysis code

Two scripts, described in full in the Appendix, neither committed to the repository: one calls
`run_backtest` and serializes every observation and outcome to JSON; the second is pure-Python arithmetic
(stdlib `collections`/`math` only, no third-party dependency) over that JSON, producing every table in
Part 3. Both are read-only with respect to the production package.

---

# Part 2 — Dataset

## 2.1 Scope

Ten symbols (`DEFAULT_BACKTEST_SYMBOLS`): BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, ADAUSDT,
LINKUSDT, AVAXUSDT, DOTUSDT. Real public Binance spot data, `2025-07-04` to `2026-08-07` (400 days),
identical per-symbol candle counts to report 0011: 1w × 57, 1d × 400, 4h × 2,395–2,400.

## 2.2 Observation counts, and reconciliation against report 0011

| | This run (2026-08-08) | Report 0011 (2026-08-08, earlier fetch) | Difference |
|---|---|---|---|
| Total observations | 21,680 | 21,730 | −50 |
| WAIT | 21,102 | 21,147 | −45 |
| CANDIDATE | 401 | 401 | **0** |
| CONFIRMED | 177 | 182 | −5 |
| Evaluated outcomes | 146 | 151 | −5 |

Pairwise agreement, the one metric both runs computed the same way:

| Pair | This run | Report 0011 |
|---|---|---|
| context trend ↔ setup trend | 55.6% (n=6,160) | 55.5% (n=6,171) |
| context trend ↔ evidence alignment | 79.0% (n=3,128) | 78.9% (n=3,133) |
| setup trend ↔ evidence alignment | 75.1% (n=6,566) | 75.2% (n=6,571) |

The two runs agree to within 0.1–0.2 percentage points on every pairwise rate, and the `CANDIDATE` count
is exactly identical. The small differences in total observations and `CONFIRMED` count are attributed to
real-market data refetch, not a defect in the harness: `run_backtest`'s own determinism guarantee
(`docs/design/SWING_SETUP_BACKTEST_V1.md` §4, proven by `tests/test_swing_setup_backtest.py`) is that
*two calls over an identical cached historical dataset* produce a byte-identical result — it makes no
claim about two separate live fetches, a day apart, against a real exchange whose recent candles can
still be revised. This distinction matters for §3.9 (DOTUSDT), where the difference is largest, and is
stated there rather than left implicit.

## 2.3 Per-symbol state counts

| Symbol | Observations | WAIT | CANDIDATE | CONFIRMED |
|---|---|---|---|---|
| ADAUSDT | 2,168 | 2,120 | 24 | 24 |
| AVAXUSDT | 2,168 | 2,168 | 0 | 0 |
| BNBUSDT | 2,168 | 2,168 | 0 | 0 |
| BTCUSDT | 2,168 | 2,120 | 29 | 19 |
| DOGEUSDT | 2,168 | 2,168 | 0 | 0 |
| DOTUSDT | 2,168 | 1,890 | 194 | 84 |
| ETHUSDT | 2,168 | 2,054 | 80 | 34 |
| LINKUSDT | 2,168 | 2,078 | 74 | 16 |
| SOLUSDT | 2,168 | 2,168 | 0 | 0 |
| XRPUSDT | 2,168 | 2,168 | 0 | 0 |

Five of ten symbols (AVAXUSDT, BNBUSDT, DOGEUSDT, SOLUSDT, XRPUSDT) never produced a single `CANDIDATE`
in this window — identical to report 0011's finding. Every measurement in Part 3 that touches a
directional or confirmed observation is necessarily drawn from the other five symbols only; this is
stated explicitly wherever it changes a table's interpretation (§3.9, §6).

## 2.4 Inherited limitations

Every limitation stated in `BACKTEST_LIMITATIONS` (`fmis/swing_setup/backtest_harness.py:135-167`,
AV-1 through AV-9) applies unchanged to this dataset: no fees/slippage/spread modelled, `TARGET_FIRST`/
`STOP_FIRST` are wick-touch classifications and never a win rate, `AMBIGUOUS_SAME_BAR` is a refusal to
guess intrabar order, entry is the confirming bar's close, setup identity has two named fallbacks,
`NEITHER_WITHIN_WINDOW` conflates two different situations, the 60-bar evaluation window is a stated
policy not a tuned value. This document adds no new claim about profitability or realized outcomes
anywhere.

---

# Part 3 — Measurements

## 3.1 RQ1 — pairwise agreement, overall and per symbol

Overall (restated from §2.2 for completeness):

| Pair | Both directional (n) | Agree | Rate |
|---|---|---|---|
| CTX (context trend) ↔ SETUP (setup trend) | 6,160 | 3,422 | 55.6% |
| CTX ↔ EVID (evidence alignment) | 3,128 | 2,472 | 79.0% |
| SETUP ↔ EVID | 6,566 | 4,934 | 75.1% |

Per symbol — the same three rates, computed independently within each symbol's own 2,168 observations:

| Symbol | CTX↔SETUP (n, rate) | CTX↔EVID (n, rate) | SETUP↔EVID (n, rate) |
|---|---|---|---|
| ADAUSDT | 624, 83.7% | 458, 93.0% | 366, 83.6% |
| AVAXUSDT | 0, — | 0, — | 600, 77.0% |
| BNBUSDT | 570, 48.4% | 324, 81.5% | 498, 79.5% |
| BTCUSDT | 866, 40.2% | 330, 52.7% | 732, 77.0% |
| DOGEUSDT | 426, 42.3% | 162, 37.0% | 696, 82.8% |
| DOTUSDT | 1,202, 72.0% | 648, **100.0%** | 828, 66.7% |
| ETHUSDT | 696, 56.9% | 324, 72.2% | 684, 91.2% |
| LINKUSDT | 522, 35.6% | 204, 61.8% | 768, 58.6% |
| SOLUSDT | 606, 42.6% | 282, 61.7% | 698, 79.4% |
| XRPUSDT | 648, 60.2% | 396, 92.4% | 696, 64.7% |

Range across symbols: CTX↔SETUP spans 35.6%–83.7% (48 points), CTX↔EVID spans 37.0%–100.0% (63 points),
SETUP↔EVID spans 58.6%–91.2% (33 points). Every pair's per-symbol range is wider than the gap between
the three pairs' own overall rates. See §5.5 and §6.

## 3.2 RQ2 — marginal and conditional probabilities

Marginal lean distribution, each family over all 21,680 observations:

| Family | long | short | conflicting | unavailable |
|---|---|---|---|---|
| CTX (context trend, 1w) | 4.8% | 35.6% | 18.7% | 40.9% |
| SETUP (setup trend, 1d) | 27.8% | 43.4% | 28.6% | 0.2% |
| EVID (evidence alignment, 1d) | 9.8% | 32.1% | 58.2% | 0.0% |

Three distinct profiles: CTX is directional only 40.4% of the time and unavailable a plurality of the
time (early-window EMA(50)/structural-history warmup, consistent with report 0011 §24's regime-warmup
finding); SETUP is almost always available (99.8%) and directional a majority of the time (71.2%); EVID
is always available in this window but *conflicting* a majority of the time (58.2%) — over twice CTX's
conflicting rate and over twice SETUP's. EVID is directional only 41.9% of the time, and when it is, it
strongly prefers `short` (32.1%) over `long` (9.8%), a 3.3:1 ratio — the sharpest lean skew of the three
families.

Selected conditional probabilities (full table in the appendix's JSON output; every cell restated here
is `P(row family = row value | column family = column value)`, not restricted to both-directional):

| Given | P(CTX=long) | P(CTX=short) | P(CTX=conflicting) | P(CTX=unavailable) |
|---|---|---|---|---|
| SETUP=long | 6.5% | 38.3% | 16.6% | 38.6% |
| SETUP=short | 4.6% | 32.2% | 19.5% | 43.7% |
| EVID=long | 4.3% | 19.4% | 9.1% | **67.3%** |
| EVID=short | 3.5% | 34.3% | 21.1% | 41.1% |

The `EVID=long → CTX` row is the clearest illustration of §1.3's point about not collapsing categories:
given EVID reads `long`, the single most likely CTX reading is not `long` (4.3%) or even `short` (19.4%)
but **unavailable** (67.3%) — the 79.0% "both-directional agreement" statistic in §3.1 is conditioned on
an event (both families directional at once) that is itself a minority of the data, and this table shows
what the other 85.6% of EVID=long cases actually look like. See §5.1.

## 3.3 RQ3/RQ4/RQ8/RQ9 — deciding votes, necessity, and per-family dominance/redundancy

Among the 578 observations that reached `CANDIDATE` or `CONFIRMED` (i.e., a direction was assigned):

| | Count | Share of 578 |
|---|---|---|
| All three families agreed (redundant vote for all three) | 162 | 28.0% |
| Exactly CTX + SETUP agreed | 398 | 68.9% |
| Exactly CTX + EVID agreed | 18 | 3.1% |
| Exactly SETUP + EVID agreed (CTX absent from the winning pair) | **0** | 0.0% |

Per-family participation (how often the family is among the agreeing set at all) and necessity (of the
observations it participates in, how often its vote was structurally required rather than redundant):

| Family | Participates in | Participation rate | Necessary in | Necessary share of its own participation |
|---|---|---|---|---|
| CTX | 578 / 578 | **100.0%** | 416 | 72.0% |
| SETUP | 560 / 578 | 96.9% | 398 | 71.1% |
| EVID | 180 / 578 | 31.1% | 18 | **10.0%** |

CTX is part of the agreeing coalition in every single directional result in this dataset, with no
exception, and its vote is structurally load-bearing (not just along for the ride) 72.0% of the time it
appears. EVID participates in less than a third of directional results, and even when it does agree with
the outcome, its vote was actually necessary only one time in ten — nine times out of ten it agreed with
a direction that CTX and SETUP had already decided between themselves. See §5.2 for the architectural
reason this is not a coincidence.

## 3.4 RQ5 — combination frequency

Of 64 possible (CTX, SETUP, EVID) lean triples, **36 were observed** in this dataset; 28 never occurred.
The three "all agree" triples that exist in the data:

| CTX | SETUP | EVID | Count | Share |
|---|---|---|---|---|
| short | short | short | 1,152 | 5.31% |
| conflicting | conflicting | conflicting | 698 | 3.22% |
| long | long | long | 84 | 0.39% |
| unavailable | unavailable | unavailable | 0 | 0.00% |

(No all-unavailable triple exists because EVID was never `unavailable` in this window, per §3.2.) The
ten most frequent triples overall, out of 21,680 observations:

| Rank | CTX | SETUP | EVID | Count | Share |
|---|---|---|---|---|---|
| 1 | unavailable | short | conflicting | 2,058 | 9.49% |
| 2 | short | short | conflicting | 1,880 | 8.67% |
| 3 | unavailable | short | short | 1,746 | 8.05% |
| 4 | short | conflicting | conflicting | 1,628 | 7.51% |
| 5 | short | long | conflicting | 1,422 | 6.56% |
| 6 | unavailable | long | conflicting | 1,272 | 5.87% |
| 7 | unavailable | conflicting | conflicting | 1,236 | 5.70% |
| 8 | **short** | **short** | **short** | 1,152 | 5.31% |
| 9 | conflicting | short | conflicting | 1,046 | 4.82% |
| 10 | conflicting | short | short | 782 | 3.61% |

None of the top ten triples contains a `long` CTX reading; the most frequent triple with `CTX=long`
anywhere in it (`long, long, conflicting`) ranks 22nd at 1.33% share.

## 3.5 RQ6 — outcome by agreement class

Every observation classified by the same rule `policy._tally` applies (§1.3's "directional" definition,
extended to the win/oppose/single/none partition):

| Class | Total | WAIT | CANDIDATE | CONFIRMED | Candidate rate | Confirmed rate |
|---|---|---|---|---|---|---|
| Opposing votes present | 3,946 | 3,946 | 0 | 0 | 0.0% | 0.0% |
| Exactly one directional vote | 8,506 | 8,506 | 0 | 0 | 0.0% | 0.0% |
| No directional votes | 1,952 | 1,952 | 0 | 0 | 0.0% | 0.0% |
| ≥2 agree SHORT, 0 oppose | 6,226 | 5,900 | 218 | 108 | 3.5% | 1.7% |
| ≥2 agree LONG, 0 oppose | 1,050 | 798 | 183 | 69 | 17.4% | 6.6% |

The first three rows are a direct restatement of `policy._tally`'s own rule (`fmis/swing_setup/policy.py:
120-133`) and confirm the harness's data is internally consistent with the policy that produced it — not
an independent finding about family behaviour. The last two rows are the substantive measurement: even
when the family-agreement condition is fully satisfied, the great majority of observations still resolve
to `WAIT`, because `evaluate_setup` gates on `context_regime_structure is TRENDING` and
`decision_context_state is not INSUFFICIENT` *before* consulting the family tally at all
(`fmis/swing_setup/policy.py:299-318`). Satisfying "2 of 3 agree, 0 oppose" is necessary but far from
sufficient. See §5.4 for the SHORT/LONG asymmetry in how often that sufficiency is reached.

## 3.6 RQ6 (continued) — outcomes split by which pair decided

Every evaluated outcome (146 total), joined back to the observation that confirmed it, and split by
exactly which pair of families supplied the winning direction:

| Deciding pair | Outcomes | Target-first | Stop-first | Ambiguous | Neither |
|---|---|---|---|---|---|
| CTX + SETUP | 132 | 59 | 61 | 4 | 8 |
| All three | 5 | 1 | 4 | 0 | 0 |
| CTX + EVID | 9 | 2 | 6 | 1 | 0 |
| SETUP + EVID alone | 0 | — | — | — | — |

132 of 146 outcomes (90.4%) were decided by CTX+SETUP. The other two cohorts (n=5, n=9) are far below
`MIN_SAMPLE_FOR_RATE = 5` — or barely at it — and no rate is computed from them here; report 0011 §23's
own `all_agree` cohort numbers (1 target-first, 4 stop-first out of 5) match this run's `All three` row
exactly, which is itself further reconciliation between the two independent live runs.

## 3.7 RQ7 — mutual information, entropy, and chance-corrected agreement

Entropy (`H`, bits) and mutual information (`MI`, bits), computed over the full four-symbol alphabet
across all 21,680 observations:

| Pair | H(A) | H(B) | MI(A;B) | MI as % of min(H(A),H(B)) |
|---|---|---|---|---|
| CTX ↔ SETUP | 1.721 | 1.570 | 0.0079 | 0.50% |
| CTX ↔ EVID | 1.721 | 1.308 | 0.0264 | 2.02% |
| SETUP ↔ EVID | 1.570 | 1.308 | 0.0475 | 3.63% |

Each family carries close to its own maximum possible entropy (2.0 bits for a 4-outcome variable) — none
is close to trivially predictable from its own history. But knowing one family's *exact* state (direction
**and** availability/conflict status) resolves under 4% of any other family's uncertainty, for every pair.
This is a very different picture from §3.1's 55–79% agreement numbers, and §5.1 explains why both are
correct measurements of different things.

Chance-corrected agreement, restricted to the both-directional subsample each pair's §3.1 rate was
computed from:

| Pair | n (both directional) | P(long) each side | Observed agreement | Expected under independence | κ |
|---|---|---|---|---|---|
| CTX ↔ SETUP | 6,160 | 13.3% / 43.8% | 55.6% | 54.5% | **0.022** |
| CTX ↔ EVID | 3,128 | 10.7% / 16.0% | 79.0% | 76.7% | **0.100** |
| SETUP ↔ EVID | 6,566 | 36.6% / 21.2% | 75.1% | 57.7% | **0.412** |

This is the sharpest result in this document. All three pairs show high raw agreement or a headline
number report 0011 flagged as concerning, but chance-correction separates them into three different
stories:

- **CTX ↔ SETUP** (κ = 0.022): the 55.6% raw agreement is almost entirely explained by both families
  independently favouring SHORT most of the time (86.7% and 56.2% of their own directional readings,
  respectively) — once that shared skew is accounted for, there is essentially no residual dependency.
  This matches report 0011's own framing of this pair as "closer to independent."
- **CTX ↔ EVID** (κ = 0.100): the 79.0% raw agreement — the *highest* of the three pairs, and the one
  that might read as most concerning on its own — is **90% explained by shared base rate** (89.3% and
  84.0% SHORT-skew respectively) and only 10% by anything else. This is the opposite of what the raw
  ranking suggests: the headline-highest agreement pair is one of the two weakest on a chance-corrected
  basis.
- **SETUP ↔ EVID** (κ = 0.412): the 75.1% raw agreement carries real, substantial dependency beyond what
  either family's own base rate predicts — over four times the corrected dependency of either other pair.
  This is the one pair where "these two are largely reading the same signal" is a chance-corrected,
  not merely a raw-percentage, finding. §5.2/Red team examines a structural explanation for exactly this
  pair.

## 3.8 RQ10 — per-symbol comparison (summary)

Combining §2.3, §3.1 and §3.3 by symbol:

| Symbol | CANDIDATE/CONFIRMED reached | CTX participation | CTX↔SETUP agreement | CTX↔EVID agreement | SETUP↔EVID agreement |
|---|---|---|---|---|---|
| ADAUSDT | yes (48 directional results) | 100% | 83.7% | 93.0% | 83.6% |
| BTCUSDT | yes (48) | 100% | 40.2% | 52.7% | 77.0% |
| DOTUSDT | yes (278) | 100% | 72.0% | **100.0%** | 66.7% |
| ETHUSDT | yes (114) | 100% | 56.9% | 72.2% | 91.2% |
| LINKUSDT | yes (90) | 100% | 35.6% | 61.8% | 58.6% |
| AVAXUSDT, BNBUSDT, DOGEUSDT, SOLUSDT, XRPUSDT | no | n/a | 35.6–60.2% | 37.0–92.4% | 64.7–82.8% |

CTX participates in 100% of directional results in **every one of the five symbols that reached one** —
the dominance in §3.3's aggregate is not carried by one or two symbols; it holds symbol by symbol,
without exception, in this dataset. Pairwise agreement rates otherwise vary widely by symbol even among
the five active ones (e.g. LINKUSDT's CTX↔SETUP at 35.6% vs. ADAUSDT's 83.7%), and the five symbols that
never produced a directional result still show a full range of pairwise-agreement behaviour among
themselves despite never mattering to a live decision in this window.

---

# Part 4 — Statistical observations

**Three-tier dependency structure, not a uniform "families are correlated."** §3.7's chance-corrected
result is the central quantitative finding of this document: the three pairs are not equally dependent.
CTX↔SETUP is close to statistically independent once base rate is removed (κ=0.02). CTX↔EVID's high raw
number is mostly a base-rate artifact (κ=0.10). SETUP↔EVID carries real, substantial redundancy (κ=0.41).
Report 0011's own framing — "two of the three pairs agree 75–79%... real evidence these families are not
fully independent" — is correct as a raw-agreement statement and, on this more detailed measurement,
turns out to understate how differently the two "75–79%" pairs behave once the shared base rate is
accounted for.

**CTX dominates the deciding coalition, without exception, in this dataset.** §3.3 and §3.8: 100%
participation in all 578 directional results and in every one of the five symbols that reached a
directional result at all. §5.2 traces this to a specific, source-verified architectural fact rather than
treating it as an unexplained empirical regularity.

**EVID is doubly weak: least often directional, and least often necessary when it is.** §3.2: EVID is
directional only 41.9% of the time (vs. CTX 40.4%, SETUP 71.2%) and, of the three, the only one whose
non-directional state is dominated by internal conflict (58.2% `conflicting`) rather than unavailability.
§3.3: even restricted to the cases where EVID does agree with the eventual direction, its vote was
structurally necessary only 10.0% of the time. These are two independent lines of measurement pointing
the same direction.

**Whether a family-agreement condition converts into an actual candidate is strongly asymmetric by side.**
§3.5: SHORT-agreeing observations converted to `CANDIDATE`/`CONFIRMED` 5.2% of the time; LONG-agreeing
observations converted 24.0% of the time — a 4.6× difference. This is a measurement about the regime/
context gate's interaction with the family tally, not about the families' agreement with each other, and
is a distinct axis from every other finding in this document.

**The aggregate pairwise-agreement numbers mask wide per-symbol variation.** §3.1, §3.8: every pair's
per-symbol range (33–63 percentage points) is wider than the spread between the three pairs' own overall
rates (55.6–79.0%, a 23-point spread). A single aggregate "these families agree 75–79%" statement, taken
alone, does not describe any individual symbol's actual behaviour well.

---

# Part 5 — Unexpected findings

## 5.1 Unconditional mutual information is close to zero even where conditional agreement is highest

§3.7's MI table shows under 4% of any family's entropy is explained by any other family, for every pair
— including CTX↔EVID, the pair with the *highest* raw agreement rate (79.0%). This is not a contradiction
with §3.1: mutual information is computed over the full dataset and the full four-symbol alphabet, while
the 79.0% figure is conditioned on the both-directional event, which itself occurs in only 3,128 of
21,680 observations (14.4%) for that specific pair. §3.2's conditional table makes the mechanism visible
directly: given EVID reads `long`, CTX's single most likely reading is `unavailable` (67.3%), not
agreement. The 79.0% number describes a real pattern *within a minority slice* of the data; it does not
describe the dataset as a whole. Both statistics are correct; they answer different questions, and a
reader who sees only the higher, more alarming-sounding number would substantially overestimate how often
these two families are actually redundant across the full range of what the system observes.

## 5.2 CTX's dominance is architectural, not merely empirical — traced to source

§3.3's "CTX participates in 100.0% of directional results, with no exception across 578 observations and
five active symbols" is not a coincidence discovered by measurement alone; tracing the code shows it is
close to a logical necessity of how the policy is built, independent of this particular dataset:

- `evaluate_setup` requires `context_regime_structure is StructureState.TRENDING` before it will ever
  consult the family tally at all (`fmis/swing_setup/policy.py:310-318`).
- `context_regime_structure` is produced by `classify_regime`'s structure dimension
  (`fmis/market_regime/classify.py:147-232`), which requires **both** its own "swing structure" evidence
  reading and its own "moving average" evidence reading to independently say `"trending"` before
  returning `StructureState.TRENDING` (line 230: `TRENDING if swing_reading == "trending" else RANGING`,
  reached only after both readings are confirmed equal at line 216).
- The swing-structure reading is `"trending"` **if and only if**
  `subject.structural_trend in (SUSTAINED_HIGHER, SUSTAINED_LOWER)`
  (`fmis/market_regime/classify.py:84-97`, `_SUSTAINED` defined at line 78) — precisely the condition
  under which `policy._trend_lean` (`fmis/swing_setup/policy.py:81-96`) returns a directional `Lean.LONG`
  or `Lean.SHORT` for the CTX factor, rather than `CONFLICTING` or `UNAVAILABLE`.
- `regime_input_from_sheet` (`fmis/pipeline/regime.py:157-177`) builds the `RegimeInput` that supplies
  `subject.structural_trend` directly from `structure.trend` — and `fmis/swing_setup/compose.py:268`
  builds `context_structural_trend` (the CTX evidence-family factor `SetupInputs` carries) from that exact
  same `context_view.structure.trend` value (`compose.py:271` builds `context_regime_structure` from the
  same `context_view`, via `context_regime = regimes[CONTEXT_ROLE].by_dimension`).

The two values — the regime gate's own `TRENDING` classification, and the CTX evidence-family vote — are
built by two different modules (`market_regime` and `policy`) reading the **identical**
`context_view.structure.trend` value. `TRENDING` cannot be reached unless that value is already
`SUSTAINED_HIGHER` or `SUSTAINED_LOWER` — which is exactly the condition under which the CTX evidence
factor is directional rather than abstaining. This means: whenever a directional `CANDIDATE`/`CONFIRMED`
result is possible at all, CTX is, by construction, already directional before the family tally is even
consulted — a stacked constraint (the gate) largely subsuming a vote-counting rule (the tally) that reads
the same underlying number a second time under a different name. §3.3's empirical 100% is the visible
consequence of this, in this one dataset; the code trace suggests it would hold in essentially any window
where a `CANDIDATE`/`CONFIRMED` occurs at all, not only this one — though that broader claim is not itself
directly measured here (see Part 6).

## 5.3 SETUP+EVID never independently forms the deciding pair

§3.3: of 578 directional results, zero were decided by exactly SETUP and EVID agreeing while CTX did not
also agree. Given §5.2's finding that CTX is architecturally forced to be directional (and, by the tally
rule's "zero opposing" requirement, on the winning side) whenever any directional result exists at all,
this specific zero is a direct and expected consequence of §5.2 rather than a separate, additional finding
about SETUP and EVID's own relationship — it is recorded here because it is the cleanest single number
that shows §5.2's mechanism operating in the confirmed-outcome data, not as new information about SETUP
and EVID specifically.

## 5.4 LONG-agreeing observations convert to a directional result 4.6× more often than SHORT-agreeing ones

§3.5: 24.0% vs. 5.2%. This is measured over a materially smaller LONG sample (1,050 vs. 6,226
observations, itself reflecting §3.2's marginal skew toward SHORT), and no mechanism for the difference is
established or claimed here — see the Red team section for candidate alternative explanations. It is
recorded as a fact about this window because it is large, easy to reproduce from the same data, and not
implied by anything else in this document.

## 5.5 Per-symbol heterogeneity is large enough that the aggregate number is a poor summary for any one symbol

§3.1/§3.8: DOTUSDT shows perfect (100.0%, n=648) CTX↔EVID agreement in this window; DOGEUSDT shows 37.0%
(n=162) for the identical pair. Both are real, non-trivial sample sizes for a 400-day, 4h-execution
dataset. A single aggregate statement about "these two families" describes neither symbol's actual
behaviour.

---

# Part 6 — What can and cannot be concluded

Deliberately conservative, per the milestone brief's own instruction.

## 6.1 Can be concluded — directly measured, in this dataset, this window

- The three evidence-family pairs are **not equally dependent**: chance-corrected agreement (κ) is 0.02
  (CTX↔SETUP), 0.10 (CTX↔EVID), 0.41 (SETUP↔EVID). SETUP↔EVID carries the only substantial
  chance-corrected redundancy of the three pairs.
- Raw agreement percentage alone (report 0011's original §23 metric) does not rank the pairs the same
  way chance-corrected agreement does: CTX↔EVID has the *highest* raw agreement (79.0%) but the *lowest*
  chance-corrected dependency of the two "high-agreement" pairs (κ=0.10, vs. SETUP↔EVID's κ=0.41 at a
  lower raw rate of 75.1%).
- CTX (context-role structural trend) was part of the agreeing coalition in 100% of the 578 directional
  results in this dataset, across every one of the five symbols that reached a directional result, and
  its vote was structurally necessary (not redundant) in 72.0% of those.
- This CTX dominance is traceable, in the current source code, to the same underlying value
  (`context_view.structure.trend`) supplying both the pre-tally regime gate and the CTX evidence-family
  vote — a specific, named architectural fact (§5.2), not only an empirical pattern.
- EVID (setup-role evidence alignment) participated in only 31.1% of directional results and was the
  necessary, non-redundant vote in only 10.0% of those — the weakest family on both measures.
- Even full family agreement is far from sufficient for a directional result: only 162 of 1,236
  observations where all three literally agreed (13.1%) ever reached `CANDIDATE`/`CONFIRMED`, because the
  regime/decision-context gates operate independently of and prior to the family tally.

## 6.2 Cannot be concluded from this milestone

- **Whether the `MINIMUM_AGREEING_FAMILIES = 2` policy should change.** That is a decision, not a
  measurement, and explicitly out of this milestone's scope.
- **Whether outcomes (target-first vs. stop-first) differ by which pair decided the trade.** §3.6: the
  only cohort with a defensible sample size (CTX+SETUP, n=132) represents 90.4% of all outcomes; the other
  two cohorts (n=5, n=9) are at or below the production code's own `MIN_SAMPLE_FOR_RATE = 5` floor. No
  comparison between them is statistically meaningful with this dataset.
- **Whether the LONG/SHORT conversion-rate asymmetry (§5.4) reflects anything about the policy's design**,
  as opposed to this specific 400-day window's market conditions, the smaller LONG sample size, or some
  interaction between the two. Not distinguished here.
- **Whether these findings generalize** beyond this exact 10-symbol, crypto-spot, 400-day,
  1w/1d/4h-role window. A different symbol universe, a longer or differently-dated window, or a different
  asset class could show different marginal skews, different κ values, or a different dominant family —
  none of that is tested here.
- **Whether the architectural mechanism in §5.2 (shared `structure.trend` value) is the *complete*
  explanation for CTX's 100% participation**, as opposed to a substantial contributor alongside other,
  unexamined factors. The code trace establishes a necessary logical condition (TRENDING requires CTX
  directional); it does not by itself rule out every other contributing mechanism.
- **Whether SETUP↔EVID's real chance-corrected dependency (κ=0.41) reflects a shared computational root**
  as opposed to a genuine, coincidental co-movement in this specific window's price action. §5.2's sibling
  finding for CTX is a proven code-level fact; the SETUP↔EVID case (Red team, below) is a plausible,
  architecturally-motivated hypothesis, not a proof of the same rigor.

---

# Red team — alternative explanations attacked

Every major finding above, with the alternative explanation considered and, where possible, weighed
against the data already in hand.

**Finding: SETUP↔EVID shows real chance-corrected dependency (κ=0.41).**
*Alternative explanation offered in this document's own §3.7/§5:* both families are different lenses on
the same 1-day close-price series over similar lookback windows — `setup_structural_trend`'s swing
detection reads candle high/low over a small (2-bar) neighbourhood
(`fmis/market_structure/swings.py::detect_swings`), while `setup_evidence_alignment`'s EMA-based
observations read the close price through EMA(20)/EMA(50)
(`fmis/decision_support/report.py`, `fmis/features/indicators/ema.py`) — no shared function call, but
the same underlying series over overlapping horizons.
*Attack:* this is architecturally plausible and consistent with why CTX↔SETUP (same algorithm, *different*
candle series — 1w vs. 1d) shows much lower dependency (κ=0.02) despite running literally the same code.
But it is not proven the way §5.2's CTX finding is: no source-level tracing was done in this milestone to
show the two computations are *mathematically forced* to agree at any rate, only that they are *plausible
candidates* to agree often given a real, sustained market trend. An equally consistent alternative is that
this specific 400-day window happened to contain unusually clean, sustained trends in the five active
symbols, which would inflate both algorithms' agreement without any structural entanglement — a
"the market, not the code" explanation this document cannot rule out with the tools used here. A future
measurement across multiple, differently-shaped historical windows (a different volatility/trend regime)
would be needed to separate "structurally likely to agree" from "happened to agree in this window."

**Finding: CTX participates in 100% of directional results (§3.3, §5.2).**
*Alternative explanation:* the shared-value architectural mechanism (§5.2) is real and directly traced in
source, but the 100% figure could still, in principle, partly reflect this dataset's own small sample of
active symbols (five) and observations (578) — a single symbol behaving unusually could not by itself
produce a 100% rate across five independent symbols, which is some protection against this, but the total
directional-result count (578) is not large in an absolute sense.
*Attack:* the code-level mechanism in §5.2 is a **necessary condition** (`TRENDING` cannot occur unless
CTX is already directional), not merely a correlational pattern — so unlike most findings in this
document, this one does not depend on this dataset's sample size at all for its *logical* validity, only
its *empirical confirmation*. The 100% is exactly what the mechanism predicts; a different rate would have
been the puzzle needing explanation, not this one. The remaining open question — noted in §6.2 — is
whether some other, unexamined path could let `TRENDING` occur with CTX non-directional (e.g. a bug, or a
transitioning-state edge case in `_structure_dimension`); this document did not attempt to prove the
absence of such a path, only to show the path that is present and sufficient to explain the finding.

**Finding: raw pairwise agreement (75–79%) for two pairs (report 0011's headline finding).**
*Alternative explanation:* shared base rate alone, not genuine dependency — exactly what §3.7's
chance-correction was designed to test.
*Attack:* already directly tested with a purpose-built statistic (κ, §3.7) rather than left as an open
question. For CTX↔EVID, observed agreement (79.0%) is barely above what shared base rate alone predicts
(76.7%), κ=0.10 — the base-rate explanation is substantially confirmed. For SETUP↔EVID, observed
agreement (75.1%) sits well above its own base-rate prediction (57.7%), κ=0.41 — the base-rate explanation
is substantially rejected; a large share of this pair's agreement cannot be produced by base rate alone
and is attributable to some other, real dependency between the two families.

**Finding: LONG-agreeing observations convert to a directional result 4.6× more often than SHORT-agreeing
ones (§5.4).**
*Alternative explanations, none tested here:* (a) sampling noise — the LONG cohort (n=1,050) is roughly a
sixth the size of the SHORT cohort (n=6,226); (b) market-structure asymmetry — if this window's LONG
opportunities disproportionately occurred during genuinely cleaner, more sustained uptrends (which would
also make the regime gate easier to satisfy) while SHORT opportunities occurred during choppier or more
range-bound conditions, the gate-pass-rate difference would reflect market character, not any asymmetry
in the policy itself; (c) an asymmetry in how `_STOP_SIDE`/`_TARGET_SIDE`/the confirmation-lookback
interacts with the two directions that was not examined in this milestone.
*Attack:* none of these three has been distinguished from the others with the data gathered here — this
finding is reported exactly as measured (§5.4) and deliberately left unresolved (§6.2), because resolving
it would require either a much larger sample, a different window, or a code trace this milestone did not
perform.

**Finding: per-symbol heterogeneity is large (§3.1, §5.5).**
*Alternative explanation:* small per-symbol directional-observation counts could make some of the more
extreme per-symbol rates (e.g. DOGEUSDT's 37.0% CTX↔EVID at n=162) unstable estimates rather than a real
symbol-level difference.
*Attack:* partially valid — n=162 is the smallest cell in the CTX↔EVID column and should be read with
more caution than DOTUSDT's n=648 100.0% figure. But the heterogeneity claim does not rest on any single
extreme cell: every one of the ten symbols' three pairwise rates was computed from at least 162
observations (§3.1), and the *range* across ten independently-measured symbols (33–63 points) is far
wider than normal sampling noise at these sample sizes would produce by chance for values this far from
0% or 100%. The direction of the finding (real heterogeneity exists) is well supported; the *exact* rate
for any single small-n cell (particularly DOGEUSDT's and BNBUSDT's CTX↔EVID cells, n=162 and n=324) should
not be over-read.

**Finding: report 0011's dataset and this milestone's dataset differ by 50 observations and 5 confirmed
setups (§2.2), concentrated in DOTUSDT (§3.6/§2.2 note).**
*Alternative explanation:* a defect in the harness's determinism guarantee, contradicting
`docs/design/SWING_SETUP_BACKTEST_V1.md`'s own claim.
*Attack:* the determinism guarantee, read precisely, is scoped to two calls over an *identical cached
historical dataset* (`tests/test_swing_setup_backtest.py`'s determinism tests construct one fixed dataset
and call `run_backtest` twice against it) — it says nothing about two separate live fetches against a real
exchange, a day apart, where Binance's own served data for recent candles can differ between fetches. This
document's two runs are two separate live fetches, not two calls over one cached dataset, so this
difference is outside what the determinism guarantee claims to cover, and is not evidence of a harness
defect. This was not independently verified against Binance's raw API response for the specific disputed
candles in this milestone (that would be its own, separate investigation); it is recorded here as the most
parsimonious explanation consistent with the guarantee's actual, stated scope, not as a proven root cause.

---

# Appendix — reproduction

Two scripts, neither part of the shipped package, both calling only already-public production functions:

1. **Data extraction** — imports `fmis.swing_setup.backtest_harness.run_backtest` and
   `DEFAULT_BACKTEST_SYMBOLS`, calls it with `start_time=2025-07-04T00:00:00Z`,
   `end_time=2026-08-07T00:00:00Z`, `run_at=2026-08-08T00:00:00Z` (all other parameters at their
   production defaults), and serializes every `HistoricalObservation` (all three `directional_factors`,
   symbol, timestamp, state, direction) and every `SetupOutcome` to JSON.
2. **Analysis** — pure Python (stdlib `json`/`math`/`collections` only), reading that JSON and computing
   every table in Part 3: pairwise/triple agreement, marginals/conditionals, the deciding-vote/necessity
   breakdown, the full combination-frequency table, outcome-by-agreement-class and
   outcome-by-deciding-pair, per-pair entropy/mutual information, chance-corrected agreement (κ), and the
   per-symbol breakdown.

Re-running script 1 against live Binance data will not reproduce today's exact observation/outcome counts
byte-for-byte (§2.2's Red team entry explains why); it will reproduce the pairwise-agreement rates,
marginal distributions, and chance-corrected κ values to within a fraction of a percentage point, as
demonstrated by this document's own §2.2 reconciliation against report 0011's independent, earlier run
over the same nominal window.
