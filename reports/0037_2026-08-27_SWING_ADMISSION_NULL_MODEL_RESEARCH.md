# Swing Admission Edge vs Random-Entry Null — Implementation and Research Record

| Field | Value |
|---|---|
| **Report number** | 0037 |
| **Title** | Swing Admission Edge vs Random-Entry Null (Milestone CA) |
| **Date** | 2026-08-27 |
| **Report type** | Implementation + Research |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | base `21dac05`; this milestone's work is **uncommitted** in the working tree |
| **Status** | Final |

**Milestone:** CA — Swing Admission Edge vs Random-Entry Null.

**Scope guard.** No production trading policy changed. `CONFIRMATION_LOOKBACK_BARS`
is still `10`, `MINIMUM_AGREEING_FAMILIES` is still `2`, `DEFAULT_TIMEFRAMES` is
still 1W/1D/4H, and the stop and target rules are untouched. **No strategy,
admission rule, geometry or exit was promoted.** Nothing here is a forward test,
no order was placed, no exchange was contacted and no credential was read.

---

## 1. The answer, first

> **Does the current FMITS swing admission rule select timestamps and directions
> with better forward outcomes than matched null entries drawn from the same
> market opportunity set?**
>
> **No. `NO_EDGE`, on all five sealed null families.** Not one reaches
> `MECHANISM_EVIDENCE`. And the result is not merely an absence: **the measured
> effects are negative.** At the pre-registered primary horizon the engine's own
> admissions underperform controls matched on symbol, sample, volatility band and
> calendar neighbourhood.

| null family | question | development | validation | holdout |
|---|---|---|---|---|
| `ca_null_matched_timing` | timing | **−0.2028** | **−0.3347** | **−0.5337** |
| `ca_null_opposite_direction` | direction *(declared degenerate)* | −0.0056 | −0.3485 | −0.6167 |
| `ca_null_random_direction_same_bar` | direction | −0.0110 | −0.2036 | −0.3125 |
| `ca_null_matched_timing_random_direction` | combined | +0.0357 | −0.1918 | −0.3088 |
| `ca_null_eligible_but_rejected` | gate | **−0.1947** | **−0.0641** | **−0.1227** |

*Effect = mean paired difference in ATR at horizon 24 (4 calendar days). The bar
for a meaningful effect was sealed at **+0.10 ATR**, derived from the deciding
cost scenario. Fourteen of the fifteen cells are negative.*

### What this does and does not establish

**An earlier draft of this report called the gate ladder "the sharpest finding"
and said the admission gate "reliably selects the wrong tail". The independent
code review (§29) refuted that, I verified the refutation myself, and it is
withdrawn.** What follows is what survives.

**ESTABLISHED — no admission edge is demonstrable.**
No sealed family cleared the pre-declared +0.10 ATR bar on development. **Not one
of the fifteen bootstrap intervals excludes zero on the positive side.** After
five milestones and four rejected search spaces, there is still no measured
evidence that this admission rule selects better than a matched control.

**NOT ESTABLISHED — that admission is actively harmful.**
The point estimates lean negative and the *sign* is stable across seeds, but
**14 of 15 symbol-clustered bootstrap intervals span zero.** Only
`ca_null_matched_timing` on the holdout excludes it (−0.9470, −0.0308).

**AND THE STUDY IS UNDERPOWERED BY CONSTRUCTION — this is CA's most important
limitation, and it was found by review rather than by design.**
On development the bootstrap half-width is ≈ **0.558 ATR** against a sealed bar of
**0.10 ATR**. Detecting a 0.10 ATR effect with an interval that excluded zero
would need roughly **(0.558/0.10)² × 155 ≈ 4,800 matched admissions per sample** —
about **31×** what five years of this universe produces. **`NO_EDGE` here means
"no edge large enough to be visible at 155 admissions", not "no edge."** The
sealed criteria demanded a precision the admission count cannot deliver, and no
realisation of this data could have produced `ADMISSION_EDGE_CANDIDATE`. That is
a defect in the pre-registration's power assumptions, recorded as CA-8.

**WITHDRAWN — the gate-ladder claim.**
The ladder is an **unpaired, unmatched, unclustered** comparison, and it does not
survive CA's own sealed uncertainty machinery:

| admitted − unconfirmed | development | validation | holdout |
|---|---|---|---|
| instant-pooled (as first reported) | −0.1618 | −0.4220 | −0.2411 |
| **symbol-clustered 95 % CI** | **(−0.644, +0.387)** | **(−0.996, +0.166)** | **(−0.658, +0.220)** |
| **equal-symbol weighting** | −0.0533 | −0.4631 | **+0.0266 (reverses)** |
| symbols where admitted *beats* unconfirmed | 6 / 15 | 4 / 15 | 8 / 21 |
| raw % return, mean | +0.02 pp (tie) | −1.34 pp | −0.95 pp |

**Zero is inside all three intervals, and on the holdout equal-symbol weighting
reverses the sign.** §23 justifies symbol clustering for every family effect;
applying that same standard to the ladder dissolves it. The ladder's large *n* is
4H bars sharing 23 of 24 forward bars — it is not 8,793 independent experiments.

**Also withdrawn: "the deduplication is costing."** `confirmed_repeat`'s +0.4538
on development is **90 % one symbol** — TRXUSDT contributes +0.4102 of it. Without
TRXUSDT the rung is +0.0516 and the gap against `admitted` collapses from 0.46 ATR
to 0.054. CA applies a concentration bound to every family effect and applied none
to the ladder; the one place it bites is the one place it was not checked.

**What this settles for BW → BZ, stated at the strength the evidence supports.**
Four milestones rejected timeframe variants, thirteen geometries, one geometry's
neighbourhood and five exit mechanisms, and none could distinguish *"the geometry
is wrong"* from *"there is no signal to shape"*. CA cannot fully separate them
either — but it establishes that **no admission edge is detectable at this
universe's sample size**, which means further tuning of geometry or exits is
searching for something nobody has shown is there.

---

## 2. Starting git state

The brief named `21dac0547fa27c116d7037de0ee6f16b9ced345c` as the released
end-state of Milestone BZ. **It was correct**, and every check agreed:

```
branch            main
HEAD              21dac0547fa27c116d7037de0ee6f16b9ced345c
                  docs(product): record swing persistence research milestone
local main        21dac05   (identical)
origin/main       21dac05   (identical)
git ls-remote     21dac05   refs/heads/main
ahead / behind    0 / 0
stash             empty
unresolved ops    none — no MERGE_HEAD, REBASE_HEAD, CHERRY_PICK_HEAD or BISECT
working tree      clean apart from 16 pre-existing untracked AP/BB-era research
                  documents under docs/design/ and docs/reviews/
```

**Those 16 documents were not staged, modified, deleted, renamed, moved or
absorbed.** They appear in §30's `git status` exactly as they appeared before
this milestone began — 16 untracked, 0 modified, verified at the close of the
milestone.

**Baseline suite before any CA code was written: 12,055 passing under
`-W error`.** Report 0036 §17 records 11,997 at the close of BZ's main pass; the
difference is BZ's own completion pass, which added
`test_swing_lab_persistence_artifact.py` after that figure was written.

---

## 3. Architecture and reuse audit

§1 of the brief requires the existing owners to be mapped before any code is
written. They were, and **CA added no backtester, no fill engine, no ATR, no
structure engine, no trend engine, no regime engine, no cost engine, no candle
reducer and no setup identity scheme.**

| Concern | Owner CA reuses | How |
|---|---|---|
| what a swing admission *is* | `swing_setup.policy.evaluate_setup` | **read, never re-evaluated** — CA reads the assessment BZ already persisted |
| setup identity / first confirmation | `swing_setup.research_identity.OpportunityTracker` | **called**, walked in bar order |
| sample boundaries | `swing_lab.preregistration.SAMPLES` | **imported by identity** — a test asserts `is SAMPLES` |
| cost scenarios | `swing_lab.preregistration.VALIDATION_COST_SCENARIOS` | **imported by identity** |
| ATR | `features.indicators.atr.AverageTrueRange` via `pipeline.regime.FAST_ATR_PERIOD` | **called at every bar** — see §3.2 |
| entry convention | `swing_lab.trades.simulate_trade`'s rule | reproduced: open of `signal_index + 1` |
| horizon semantics | `swing_lab.persistence.observe_path`'s checkpoints | reproduced: horizon *n* reads `bars[signal_index + n]` |
| horizons | `swing_lab.persistence.CHECKPOINT_BARS` | **a subset**, asserted |
| sample floor | `swing_lab.metrics.SAMPLE_FLOOR` | imported |
| concentration bound | `swing_lab.geometry_verdict.MAX_SINGLE_SYMBOL_SHARE` | imported |
| walk-forward length / majors | `swing_lab.validation_study.WALK_FORWARD_MONTHS`, `MAJOR_SYMBOLS` | imported |
| inputs | `swing_lab.persistence_artifact` (Milestone BZ's capture) | **read offline** |
| result surface | `pipeline.cli` `research` area | one new choice |

### 3.1 The three extractions, and why they are not new seams

CA needed three things that already existed but were welded to a `LabTrade`. In
each case the existing owner was **extracted rather than duplicated**, so the
laboratory keeps one definition:

| extracted | from | now shared with |
|---|---|---|
| `walk_forward_boundaries()` | `validation_study.walk_forward` | CA's per-universe curve |
| `concentration_of_magnitudes()` | `robustness.concentration_of` | CA's paired differences |
| `nearest_rank_quantile()` | `persistence_study._quantile` | CA's bootstrap and null |

All three are behaviour-preserving: `walk_forward` now *calls* the boundary
function, `concentration_of` now *delegates* to the magnitude function, and BZ's
`_quantile` is now a one-line call. The pre-existing suites covering them pass
unchanged, and BY's and BZ's pinned digests are byte-identical afterwards (§20).

**Duplicating a ten-line share calculation would have been the easier change and
the wrong one.** Two copies of a concentration formula are two places for a
denominator to stop matching its numerator.

### 3.2 The ATR is production's, called — not reimplemented

`AverageTrueRange` is Wilder-smoothed from a seed taken at the start of the
series it is handed, so its value at a bar depends on the *window* it is computed
over. The replay view held at most `candle_limit` closed candles, so reproducing
production's reading means handing the feature exactly that window.

The obvious objection is cost — a quarter of a million bars, each needing a
250-candle window. **That objection was measured rather than assumed: the whole
of both universes takes 12 seconds.** There is therefore no case whatsoever for a
second ATR implementation, and CA does not have one.

**Proof it is production's number.** Recomputing the ATR from the persisted bars
at each of the **480 captured candidates** reproduces that candidate's own
`execution_atr` **bit for bit — 480 of 480, worst relative error exactly 0.0**.

---

## 4. Was Milestone BZ's capture sufficient? **Yes, and no schema extension was needed**

The brief warns that BZ explicitly records an artifact limitation — execution-
timeframe bars and structural readings are persisted, but the 1D/1W series that
*generated* those readings are not — and instructs that this must not be silently
worked around.

**It was not worked around. It was tested.** The question is not whether the
capture is complete in general; it is whether it can support *this* experiment.
Three checks decided it, all run before any outcome was computed:

### 4.1 The capture reconstructs the production admission decision exactly

`ThesisObservation` carries `setup_state`, `setup_direction`,
`decision_context_state` and `context_regime_structure` at **every analysable
4H bar**. Replaying those through production's own `OpportunityTracker`, in bar
order, and applying `evaluate_setup`'s own precedence reproduces the capture's
admitted candidate list:

| universe | candidates in the capture | reconstructed by CA | match |
|---|---|---|---|
| primary (15 symbols) | 246 | 246 | **exact** |
| holdout (21 symbols) | 234 | 234 | **exact** |

The gate-ladder census also reconciles to the capture's own instant count
exactly — 104,130 measured instants for primary and 99,666 for the holdout,
both to the unit. **This is the claim that entitles CA to call its `ADMITTED`
stage the live product's decision rather than a reconstruction of it**, and it is
asserted by regression rather than by argument.

### 4.2 The eligible-but-rejected population is production's own vocabulary

`SetupState.CANDIDATE` already means, in production's own words, *"a directional
thesis exists but the execution-timeframe confirmation this policy requires has
not occurred."* CA did not invent an "almost setup"; it read one that has been in
`swing_setup/models.py` since Milestone AR. The population is large — 8,793
instants on development, 5,602 on validation, 15,312 on the holdout — and it is
the strongest control CA has.

### 4.3 What the capture cannot support, stated rather than glossed

* **The setup-timeframe (1D) ATR is available only at admitted instants**, because
  1D bars are not persisted. CA does not use it: its outcome is expressed in
  **execution-timeframe** ATR, which is available at every bar.
* **CA cannot ask *why* a pivot was detected.** It reads what the structural
  engines concluded, not the series they concluded it from. CA asks no such
  question. This is recorded as limitation CA-6.

**Conclusion: the BZ capture is sufficient for CA, and CA extended no schema.**
The alternative — a fresh 77-minute network replay — would have introduced a
second dataset and made every CA figure incomparable with BZ's for provider
reasons. That is precisely the failure BZ recorded as defect BZ-D2.

---

## 5. The pre-registration, and when it was sealed

`src/fmis/swing_lab/admission_preregistration.py` fixes every null family,
threshold, horizon, matching rule, seed, sample boundary, stratum and verdict
criterion, and pins their SHA-256:

```
id      ca-swing-admission-null-model-v1
digest  910cad28001ee18d9630f685e454bfd6bf24fb7d78b907e89172371b83f25e8a
```

**It was computed and printed before the first forward outcome was computed.**
The run script verifies it before reading a single bar, and the first line of the
run log is `seal verified 910cad28…`. The seal and the content live in the same
file, so a change to either without the other is a red test.

`tests/test_swing_lab_admission_preregistration.py` holds **72 tests**. Thirty
parametrised mutations — a family dropped, the families reordered, a threshold
moved, a criterion deleted, a sample edge shifted, the matching radius narrowed,
the separation halved, the seeds changed, the deciding cost scenario switched —
are each shown to **change the digest**. The digest is also asserted stable across
`PYTHONHASHSEED` 0 / 1 / 12345.

### What was sealed before results, in brief

**Primary metric.** Direction-normalised, ATR-normalised forward return at
**horizon 24 execution bars**, chosen by a stated rule rather than by inspection —
see §8.

**Five null families**, each carrying a `PREDICTION:` and a `REFUTED BY:`
sentence. `CaNullFamily.__post_init__` refuses to construct one without both: a
family with no stated refutation cannot fail, and a milestone whose families
cannot fail is a search.

**Verdict vocabulary.** `NO_EDGE`, `INCONCLUSIVE`, `MECHANISM_EVIDENCE`,
`ADMISSION_EDGE_CANDIDATE`. **Every member has `is_approved_for_trading = False`
and `earns_forward_test = False`, including `ADMISSION_EDGE_CANDIDATE`** —
asserted over the whole enum. CA measures admission with no geometry attached, so
there is no complete policy to forward-test and no gate in this repository that
could receive one.

---

## 6. Samples — Milestone BY's, imported by identity

A test asserts `CA_PRE_REGISTRATION.samples is SAMPLES`, so CA and BZ cannot
drift apart and a CA figure is comparable with a BZ figure by construction.

| sample | universe | symbols | window | admissions | contamination |
|---|---|---|---|---|---|
| **Development** | primary | 15 | 2023-06-01 → 2025-06-01 | **155** | **CONTAMINATED BY CONSTRUCTION** |
| **Validation** | primary | the same 15 | 2025-06-01 → 2026-08-01 | **91** | **SEMI-CONTAMINATED** — new period, old symbols |
| **Holdout** | holdout | **21 never measured** | 2024-06-01 → 2026-08-01 | **234** | **THE HOLDOUT** |

**Universes are never pooled.** Development and validation share a universe and
are cut by date; the holdout is a separate replay. A regression asserts every
result carries its own sample identity, and `FamilySampleResult` has no field
that could hold a pooled number. This is the structural half of the answer to
BY's own pooling defect.

*CA measures slightly more admissions than BZ (155/91/234 against BZ's
151/88/225 paths) because CA needs no geometry: a candidate BZ's stop/target
policy skipped for lacking a level is still a decision instant here. That is the
milestone's whole point — admission measured independently of trade management.*

---

## 7. Matching methodology

The matching rule **is** the null, and every constraint was set from a property
of the *inputs* — pool sizes, eligibility counts — with no forward outcome
computed. Reading pool sizes before sealing is what makes these numbers
defensible; reading an effect would have made them a search.

| constraint | value | why |
|---|---|---|
| symbol | **exact** | a control from another symbol carries that symbol's drift, liquidity and beta; the engine does not choose symbols |
| sample | **exact** | a control crossing a boundary imports the holdout into development |
| **minimum separation** | **60 bars** | **exactly the evaluation window.** A nearer control would share forward bars with the admission it is compared against, and the paired difference would be partly a number minus itself |
| calendar radius | tiers of **540 / 1080 / 2160** bars (90 / 180 / 360 days), tightest first | a distant control is matched on volatility but not on market-wide risk regime; the tiers populate thin pools without a per-family knob |
| ATR band | **\|ln(atr_c / atr_a)\| ≤ 0.60**, i.e. [0.55×, 1.82×] | the outcome is *already* divided by ATR, so this keeps the control in a comparable volatility **environment** rather than equalising a denominator |
| admitted instants | **excluded from every pool** | a null containing FMITS admissions is partly FMITS against itself |
| minimum pool | **10** | below it the admission is `UNMATCHED` and reported, never matched against a pool too small to be a null |

**The ATR band was set to 0.60 to maximise control COVERAGE, not effect.** At
0.40 the eligible-but-rejected control silently discards a quarter of its
admissions on development; at 0.60 it retains ≥ 97 % on every sample. A control
family that drops a quarter of its admissions is a biased control, not a strict
one.

**`CONFIRMED_REPEAT` instants are deliberately KEPT in the broad pool.** They are
moments the engine did not admit, and removing them would have quietly made the
null easier by discarding its most signal-like members. As §12 shows, they are
the *best*-performing rung on development — so keeping them made the null
materially harder to beat, which is the correct direction for a control.

### Matching outcome

| family | dev matched / unmatched | val | holdout | radius tiers used (dev) |
|---|---|---|---|---|
| `ca_null_matched_timing` | 155 / **0** | 91 / 0 | 234 / 0 | tier 0: 153, tier 1: 1, tier 2: 1 |
| `ca_null_matched_timing_random_direction` | 155 / **0** | 91 / 0 | 234 / 0 | tier 0: 153, tier 1: 1, tier 2: 1 |
| `ca_null_eligible_but_rejected` | 151 / **4** | 90 / 1 | 229 / 5 | tier 0: 134, tier 1: 5, tier 2: 12 |

**Ten unmatched admissions in total, all in the eligible-but-rejected family, all
reported.** Better than 97 % coverage on every sample and every family.

---

## 8. Randomisation, seeds and repetitions

**Every seed is SHA-256 over the draw's own identity** —
`{master}|{family}|{sample}|{symbol}|{bar_index}|{replicate}` — truncated to 64
bits. Python's built-in `hash` is **never** used: it is salted per process, and a
study seeded with it would draw different controls on two runs of the same
machine while claiming to be deterministic. A test runs the derivation under
three `PYTHONHASHSEED` values and asserts one answer.

| parameter | value | justification, fixed before results |
|---|---|---|
| draws per admission | **200** | the control term's own sampling error enters the effect at 1/√200 ≈ 7 % of the per-instant spread; pool medians are 400–550, so 200 samples a large fraction without exhausting it |
| null replicates | **1000** | resolves a percentile to 0.1, finer than the 95.0 bar the verdict reads |
| bootstrap replicates | **2000** | conventional count for a stable 95 % percentile interval |
| master seeds | **(1, 2, 3, 4, 5)**, primary 1 | 2–5 exist only to answer whether a sign is a property of the data or of one draw; they can make a criterion FAIL, never pass |

**Seed stability, development effects:**

| family | s1 | s2 | s3 | s4 | s5 | sign stable |
|---|---|---|---|---|---|---|
| `ca_null_matched_timing` | −0.2028 | −0.2554 | −0.2461 | −0.2114 | −0.2184 | **yes** |
| `ca_null_eligible_but_rejected` | −0.1947 | −0.1697 | −0.1698 | −0.1625 | −0.1516 | **yes** |
| `ca_null_random_direction_same_bar` | −0.0110 | −0.0095 | +0.0051 | +0.0063 | −0.0036 | no |
| `ca_null_matched_timing_random_direction` | +0.0357 | −0.0019 | +0.0060 | −0.0277 | +0.0239 | no |
| `ca_null_opposite_direction` | −0.0056 | ×5 identical | | | | **yes** (deterministic) |

**The two families with a real negative effect keep their sign under every seed.
The two hovering near zero do not** — which is exactly what a seed-stability
criterion is for, and it caught them.

**Control identities are persisted.** The artifact carries a SHA-256 over every
drawn control identity per family and sample. A digest rather than the list is
deliberate: the list is ~288,000 bar indices, and a digest detects any difference
at all in one comparison. A regression asserts regenerating the draws reproduces
the digest.

---

## 9. The primary metric, and why it is this one

**Direction-normalised, ATR-normalised forward return at horizon 24 execution
bars.** Chosen by a rule written down before any outcome existed:

> The primary horizon is the **shortest declared horizon strictly greater than
> Milestone BZ's measured median bars-to-peak on production geometry over the
> development sample**, which report 0036 §8 records as **19 execution bars**.
> Over `FORWARD_HORIZONS = (1, 3, 6, 12, 24, 60)` that rule resolves **uniquely
> to 24**.

**Why it represents a swing admission.** On a 4H execution timeframe, 24 bars is
**4 calendar days** — past the point at which BZ measured a typical favourable
move to have peaked, so it is not day-trading noise; and 40 % of the inherited
60-bar evaluation window, so it is not dominated by the window bound. The
shorter horizons (1–6 bars, 4–24 hours) measure the breakout impulse rather than
the swing; the longest (60 bars) **is** the bound.

**Why no cost, stop, target or exit is applied.** BW, BX, BY and BZ established
that trade management is the losing half of this strategy. A measurement
carrying it cannot separate a bad entry from a bad exit — which is the one thing
CA exists to do. Costs enter once, as the magnitude an effect must clear.

**Why the bar is +0.10 ATR.** The deciding cost scenario
`swing-lab-conservative-10bps` charges 0.002 of notional per round trip. The
primary universe's median ATR/close over its admitted instants is **0.0202**, so
one round trip is **0.002 / 0.0202 = 0.099 ATR**. An admission edge smaller than
the cost of acting on it is not an edge. The bar is the cost, rounded to 0.10.
(It coincides with BZ's own +0.10R mechanism bar, which keeps the two milestones
readable against each other, but it was derived here independently.)

---

## 10. Development result

**155 matched admissions, 15 symbols, 83 long / 72 short.**

| family | effect | 95 % cluster bootstrap | null percentile | concentration |
|---|---|---|---|---|
| `ca_null_matched_timing` | **−0.2028** | (−0.7494, +0.3662) | 32.6 | 0.113 |
| `ca_null_opposite_direction` | −0.0056 | (−1.1646, +1.1701) | 0.0 † | 0.116 |
| `ca_null_random_direction_same_bar` | −0.0110 | (−0.5955, +0.5880) | 51.8 | 0.118 |
| `ca_null_matched_timing_random_direction` | **+0.0357** | (−0.5317, +0.6023) | 51.2 | 0.117 |
| `ca_null_eligible_but_rejected` | **−0.1947** | (−0.7401, +0.3873) | 28.2 | 0.113 |

† degenerate — see §11.

**Every family fails `development_effect` (+0.10 ATR).** The single positive
figure, +0.0357 for the combined family, is a third of the bar, sits at the 51st
percentile of its own null, has a bootstrap interval spanning zero, and **flips
sign under two of the five master seeds**. It is noise, and the sealed criteria
identify it as noise without a judgement call.

**Concentration passes everywhere** — the largest single-symbol share is 11.3 %
against a 40 % bound. This result is not one coin wearing a universe.

### The complete effect-size and uncertainty table, all three samples

| family | sample | n | unmatched | symbols | effect | 95 % cluster bootstrap | null percentile |
|---|---|---|---|---|---|---|---|
| `ca_null_matched_timing` | development | 155 | 0 | 15 | −0.2028 | (−0.7494, +0.3662) | 32.6 |
| | validation | 91 | 0 | 15 | −0.3347 | (−1.0347, +0.3482) | 26.6 |
| | **holdout** | 234 | 0 | 21 | **−0.5337** | **(−0.9470, −0.0308)** | **3.6** |
| `ca_null_opposite_direction` | development | 155 | 0 | 15 | −0.0056 | (−1.1646, +1.1701) | 0.0 † |
| | validation | 91 | 0 | 15 | −0.3485 | (−1.6584, +0.9885) | 0.0 † |
| | holdout | 234 | 0 | 21 | −0.6167 | (−1.4647, +0.3395) | 0.0 † |
| `ca_null_random_direction_same_bar` | development | 155 | 0 | 15 | −0.0110 | (−0.5955, +0.5880) | 51.8 |
| | validation | 91 | 0 | 15 | −0.2036 | (−0.8436, +0.4277) | 35.4 |
| | holdout | 234 | 0 | 21 | −0.3125 | (−0.7404, +0.1832) | 15.4 |
| `ca_null_matched_timing_random_direction` | development | 155 | 0 | 15 | +0.0357 | (−0.5317, +0.6023) | 51.2 |
| | validation | 91 | 0 | 15 | −0.1918 | (−0.8000, +0.4401) | 36.9 |
| | holdout | 234 | 0 | 21 | −0.3088 | (−0.7368, +0.2201) | 19.2 |
| `ca_null_eligible_but_rejected` | development | 151 | 4 | 15 | −0.1947 | (−0.7401, +0.3873) | 28.2 |
| | validation | 90 | 1 | 15 | −0.0641 | (−0.7377, +0.7031) | 41.0 |
| | holdout | 229 | 5 | 21 | −0.1227 | (−0.5796, +0.3545) | 35.5 |

† degenerate null — a point mass at zero, see §11. Not evidence.

**Exactly one of the fifteen intervals excludes zero**, and it is the timing null
on the never-measured holdout, on the **negative** side. **No interval anywhere
excludes zero on the positive side.** That is the honest statistical summary of
this milestone: there is no evidence of a positive admission edge, and one
sample's worth of evidence for a negative one.

**Avoiding significance theatre.** The percentile column is reported because the
seal commissions it, but §22 records that the sealed null is **conservative** —
it has larger variance than the statistic it judges, so those percentiles are
systematically pulled toward the middle. The bootstrap column is the
variance-matched statement and is the one to read.

---

## 11. Direction edge, and a degeneracy declared in advance

`ca_null_opposite_direction` is **algebraically degenerate at the primary metric,
and the pre-registration says so** — this is not a discovery made after the
numbers arrived. A fixed-horizon direction-normalised ATR return is antisymmetric
in direction, so the opposite-direction control at the same bar equals **minus**
the admission's own return exactly. Its paired difference is therefore identically
**2 × the admission's own mean return** and carries no information beyond it.

It follows that the admission's own raw mean forward return is half the table
above: **−0.0028 (dev), −0.1742 (val), −0.3083 (holdout)** — the same figures the
gate ladder reports for the `admitted` rung, as they must be.

Its null is likewise a point mass at zero (every draw is one bar in one
direction), which is why its "0.0 percentile" is meaningless and why the seal
forbids reading it as independent evidence. It was measured anyway because its
MFE/MAE diagnostics are *not* degenerate, and because omitting a control the
brief names would be a silent narrowing of the experiment.

**The non-degenerate direction test is `ca_null_random_direction_same_bar`**:
FMITS's chosen side against a seeded fair coin, at FMITS's own instant. Result:
**−0.0110 / −0.2036 / −0.3125**. On development the engine's direction is
indistinguishable from a coin; on both unseen samples it is worse than one.

**Direction-cohort decomposition** (declared stratum), primary horizon:

| family | dev long (83) | dev short (72) | val long (16) | val short (75) | hold long (40) | hold short (194) |
|---|---|---|---|---|---|---|
| `ca_null_matched_timing` | −0.5206 | +0.1636 | *refused* | −0.2829 | −1.4555 | −0.3437 |
| `ca_null_random_direction_same_bar` | −0.2054 | +0.2131 | *refused* | −0.0646 | −1.5415 | −0.0591 |
| `ca_null_eligible_but_rejected` | −0.5440 | +0.1886 | *refused* | +0.0737 | −0.9703 | +0.0407 |

**The long cohort is severely negative on every sample that can state it** —
−0.52 on development and −1.46 on the holdout. The short cohort is positive on
development and negative on validation, so it is **not** a conditional edge; the
one exception is discussed in §19. The 16-admission validation long cohort is
**refused, not stated** — the sample floor doing its job on a real cut.

---

## 12. Timing edge, and the gate attribution

> **This section carried CA's strongest claim in the first draft, and the
> independent review refuted it. The refutation was verified independently and
> the claim is withdrawn.** The tables stand; the inference drawn from them in
> §12.2 does not. Read §12.3 before using any figure here.

**Every rung of the production ladder, and the forward outcome of what stopped
there** (mean direction-normalised ATR return at horizon 24):

| rung | development | validation | holdout |
|---|---|---|---|
| `context_insufficient` | 0 instants | 0 | 0 |
| `regime_blocked` | 32,034 — **REFUSED** | 20,562 — REFUSED | 50,094 — REFUSED |
| `tally_disagreed` | 20,040 — **REFUSED** | 8,448 — REFUSED | 24,828 — REFUSED |
| `unconfirmed` *(gate rejected)* | **+0.1589** (8,793) | **+0.2478** (5,602) | −0.0672 (15,312) |
| `confirmed_repeat` | **+0.4538** (4,768) | +0.0293 (3,637) | −0.0788 (9,198) |
| **`admitted`** | **−0.0028** (155) | **−0.1742** (91) | **−0.3083** (234) |

**The three rungs below the family tally are REFUSED, not blank.** Production had
formed no direction at those instants, so a direction-normalised return is
undefined for them; computing one as a long's would report the market's own drift
as though it were a selection result. The census is stated instead, and it is
explicitly not comparable with the rungs above.

### 12.2 What the first draft concluded from this — WITHDRAWN

The first draft read the table as *"the admitted rung is the worst directional
rung on all three samples"*, *"the gate reliably selects the wrong tail"* and
*"the deduplication is also costing"*. **All three are withdrawn.**

### 12.3 Why they are withdrawn

The independent review (§29) observed that the ladder is the only statistic in CA
with **no clustering, no interval and no concentration bound**, while §23 argues
at length that every family effect needs all three. Applying CA's own sealed
estimator — resample symbols with replacement — to `admitted − unconfirmed`:

| | development | validation | holdout |
|---|---|---|---|
| instant-pooled gap | −0.1618 | −0.4220 | −0.2411 |
| **symbol-clustered 95 % CI** | **(−0.644, +0.387)** | **(−0.996, +0.166)** | **(−0.658, +0.220)** |
| **equal-symbol weighting** | −0.0533 | −0.4631 | **+0.0266** |
| symbols where admitted *beats* unconfirmed | 6/15 | 4/15 | 8/21 |

**Zero is inside every interval**, roughly 40 % of symbols point the other way,
and **on the holdout equal-symbol weighting reverses the sign** — admitted
(−0.2695) beats both `unconfirmed` (−0.2962) and `confirmed_repeat` (−0.3111).
The large *n* is illusory: consecutive 4H instants share 23 of their 24 forward
bars, so 8,793 instants are nothing like 8,793 experiments.

**And the `confirmed_repeat` claim was one symbol.** TRXUSDT contributes **+0.4102
of the +0.4538** development figure from 738 of 4,768 instants. Excluding it the
rung is **+0.0516** and the gap against `admitted` falls from 0.46 ATR to 0.054.

**Both figures were reproduced independently before the claims were withdrawn.**

### 12.4 What survives from the ladder

1. **The census is exact and useful** — it reconciles to the capture's own instant
   counts to the unit, and it is what makes the eligible-but-rejected control
   possible at all.
2. **The regime gate and the tally cannot be scored**, because they carry no
   production direction. CA says nothing about whether 1W gating or the
   two-family tally add value. Named rather than filled with a long's return.
3. **Nothing in the ladder is evidence of an admission edge in either
   direction.** The matched, paired, clustered null families in §10 are CA's
   evidence; the ladder is a census with an unclustered mean attached.

**Timing edge verdict: no edge demonstrated; the point estimate leans negative
and the study cannot resolve it.** `ca_null_matched_timing` holds direction fixed
and varies only *when*: −0.2028 / −0.3347 / −0.5337, sign-stable across all five
seeds. Its holdout interval is the one interval in the milestone that excludes
zero (−0.9470, −0.0308); its development and validation intervals do not.

---

## 13. Combined admission result

`ca_null_matched_timing_random_direction` — FMITS's instant **and** FMITS's
direction against a matched instant entered on a coin — is the closest thing CA
measures to *"is the engine worth having"*.

**+0.0357 / −0.1918 / −0.3088.** It is the only family with a positive
development figure and it fails on every count that matters: a third of the
sealed bar, the 51st percentile of its own null, a bootstrap interval spanning
zero, and a sign that flips under two of five seeds.

Its horizon profile is the one thing that passes — all six horizons share the
positive sign on development — which is worth stating precisely because it is
the family's *only* passing robustness criterion and it did not save it.

---

## 14. Eligible-but-rejected result — **MEASURABLE, and measured**

The brief asks for this control if the architecture exposes a scientifically
defensible population, and instructs that it be classified `NOT MEASURABLE`
rather than manufactured otherwise. **It is measurable, and no definition was
invented.**

`SetupState.CANDIDATE` is production's own vocabulary: decision context
sufficient, context-role regime trending, family tally agreed, execution
confirmation **not** occurred. Each control is measured in its own production
direction, so the comparison isolates the confirmation gate and nothing else.

| sample | matched | unmatched | effect | bootstrap | percentile |
|---|---|---|---|---|---|
| development | 151 | 4 | **−0.1947** | (−0.7401, +0.3873) | 28.2 |
| validation | 90 | 1 | **−0.0641** | (−0.7377, +0.7031) | 41.0 |
| holdout | 229 | 5 | **−0.1227** | (−0.5796, +0.3545) | 35.5 |

**Negative on all three samples, sign-stable across all five seeds.** The
confirmation gate does not add information; it subtracts it.

### The no-lookahead constraint that shaped this control

A tempting definition is *"opportunities the gate rejected and which never
confirmed"*. **That definition is lookahead** — whether an opportunity later
confirmed is not knowable at the control's own decision bar — so it was refused.
The sealed definition classifies at decision time only, which means some controls
belong to opportunities that confirmed later. That is stated as limitation CA-4
rather than buried: this control is *"moments at which the engine had not yet
admitted"*, not *"opportunities it never took"*, and it is the stronger of the two
only because the other is unavailable without reading the future.

---

## 15. The fixed-horizon profile

Development, effect in ATR:

| family | 1 | 3 | 6 | 12 | **24** | 60 |
|---|---|---|---|---|---|---|
| `ca_null_matched_timing` | +0.0796 | +0.0848 | +0.0938 | −0.0772 | **−0.2028** | −0.2098 |
| `ca_null_opposite_direction` | +0.1545 | +0.1884 | +0.2708 | +0.0832 | **−0.0056** | +0.3744 |
| `ca_null_random_direction_same_bar` | +0.0804 | +0.1051 | +0.1412 | +0.0491 | **−0.0110** | +0.1659 |
| `ca_null_matched_timing_random_direction` | +0.0754 | +0.1010 | +0.1510 | +0.0550 | **+0.0357** | +0.2579 |
| `ca_null_eligible_but_rejected` | +0.0789 | +0.0721 | +0.0633 | −0.1834 | **−0.1947** | +0.6636 |

**The shape is consistent and it is the milestone's second real finding.** Every
family is **positive at 1–6 bars** (4–24 hours), crosses to **negative around
12–24 bars** (2–4 days), and several turn positive again at 60.

> **The admission engine identifies a genuine short-lived impulse and then holds
> through its reversal.** The confirmation gate fires on a structure break — by
> construction, *after* a move has begun — and the 4-to-24-hour continuation is
> real. By four days it has been given back and more.

This is the same phenomenon BZ measured from the other side: 92.1 % of positions
surrender a full R of open profit, median time to +1R of 2 bars, peak at bar 19.
**BZ saw the give-back and asked whether an exit could rescue it. CA shows the
give-back is a property of what is being SELECTED, not of when it is closed** —
which is why none of BZ's five exit mechanisms could recover it.

**The horizon-profile criterion is a bar, not a search.** The verdict is decided
at horizon 24 alone; the other five feed exactly one criterion and can only make
a verdict fail. Three families fail it, including `ca_null_matched_timing`
(3 of 6 agree, against a bar of 4) — its negative primary result is *contradicted
by its own short-horizon shape*, and the seal reports that rather than
suppressing it.

---

## 16. MFE / MAE and the ±1 ATR excursion race

**Mean excursions at horizon 24, in ATR:**

| family / sample | admission MFE | admission MAE | control MFE | control MAE |
|---|---|---|---|---|
| `matched_timing` / development | **+3.360** | **−3.183** | +3.004 | −2.809 |
| `matched_timing` / validation | +2.552 | −3.363 | +2.827 | −2.951 |
| `matched_timing` / holdout | +2.584 | −2.895 | +2.914 | −2.765 |

**On development, admissions move MORE in both directions** — higher favourable
*and* deeper adverse excursion than their controls. The engine is selecting
higher-realised-volatility moments, not better-directed ones. **On the holdout it
is strictly worse both ways**: lower MFE (2.584 vs 2.914) *and* deeper MAE
(−2.895 vs −2.765).

**The ±1 ATR race** — does the instant reach +1 ATR favourable before 1 ATR
adverse? Bars whose range spans both thresholds are **refused as ambiguous** and
excluded from the rate, never ordered by a guess:

| sample | admissions | matched controls | ambiguous |
|---|---|---|---|
| development | **0.571** | 0.499 | 286 |
| validation | 0.478 | 0.518 | 154 |
| holdout | 0.534 | 0.515 | 403 |

**This is the one diagnostic that looks like selection** — +7.2 pp on
development, +1.9 pp on the holdout — and it **reverses on validation** (−4.0 pp),
so it is not a validated edge. It is, however, entirely consistent with §15: the
admission is more likely to see its first ATR go the right way, and its 4-day
return is still worse. **A short-lived impulse followed by a reversal produces
exactly this pair of numbers.**

**Positive-return rate of admissions at horizon 24: 0.471 / 0.451 / 0.479.**
Below a coin on all three samples.

---

## 17. Walk-forward, per universe, never pooled

`ca_null_matched_timing`:

| primary universe | 23H2 | 24H1 | 24H2 | 25H1 | 25H2 | 26H1 |
|---|---|---|---|---|---|---|
| development | +0.316 (39) | −0.748 (38) | −0.266 (37) | −0.134 (41) | — | — |
| validation | — | — | — | — | −0.993 (23) / −0.450 (57) | +1.639 (11) |

| holdout universe | 24H2 | 25H1 | 25H2 | 26H1 |
|---|---|---|---|---|
| | −0.834 (56) | −0.941 (47) | −0.760 (52) | −0.043 (64) / +0.554 (15) |

**Two curves, two universes, never one.** Milestone BY published a wrong
conclusion by pooling three samples into a single curve while the traded universe
doubled mid-curve; a CA regression refuses a pooled curve by name and
`FamilySampleResult` has no field that could hold one.

The holdout curve is negative in **four of five** windows. The final window in
each curve holds 11–15 admissions and is well below the sample floor for any
claim — reported because a curve that omits its thin windows reads as continuous
coverage, not because those cells mean anything.

---

## 18. No-lookahead proofs

Proven the way BW, BX, BY and BZ prove it — **change the future and require the
past not to notice** — with a non-vacuity control for every claim.

| claim | proof | the control that stops it passing vacuously |
|---|---|---|
| a control's identity cannot depend on any bar | `admission_matching` imports **neither `PriceBar` nor `ForwardOutcome`**, asserted by AST; `eligible_pool` and `match_admission` have no `bars` parameter | an instant **before** the admission **does** change the pool |
| a `DecisionInstant` cannot carry the future | asserted to hold no `bars`, `forward`, `outcome`, `mfe`, `mae` or `future` field | — |
| `stage_of` cannot see forward | it reads only enum values a `ThesisObservation` froze at that bar | an altered `setup_state` **does** move the stage |
| a control never overlaps its own admission's window | every instant within ±59 bars is excluded | the instant at **exactly** 60 bars **is** admitted to the pool |
| an admission is never its own control | admitted bars are removed from every pool | a non-admitted bar at the same distance **is** kept |
| fixed-horizon outcomes may change, identities may not | the outcome is computed **after** matching, from a frozen instant | mutating a post-decision bar changes the outcome and not the match |
| the eligible-but-rejected classification is frozen at decision time | `SetupState.CANDIDATE` at that bar, with **no** conditioning on whether the opportunity later confirmed | recorded as CA-4 |

**The structural half of the proof is stronger than the mutational half**, and it
is the argument BX, BY and BZ rest on: a `DecisionInstant` holds a symbol, a bar
index, a stage, a direction, a close and an ATR **and no bar of any resolution**,
so a matching rule handed one *cannot* read forward — not by discipline but by
what exists.

---

## 19. Concentration, decompositions, and the conditional-edge rule

**Concentration passes on every family**: largest single-symbol share 0.113–0.118
against a 40 % bound.

**Declared strata** (fixed before results, and the only cuts CA may draw a
conclusion from):

* **direction** — §11. Long severely negative; short positive on development,
  negative on validation. Not a conditional edge.
* **volatility regime** — `steady` is the worst cut on development for every
  family (e.g. −0.5994 for `matched_timing` against +0.0085 `contracting`), but
  the ordering does not survive: on validation `steady` is the *best*
  (+0.0937). `expanding` holds 7–10 admissions on two samples and is **refused**.
* **major / non-major** — **the holdout contains zero major symbols**, so this
  cut is structurally unmeasurable there. It is reported as such rather than as a
  zero. On development majors are positive (+0.2692) and non-majors negative
  (−0.4551); on validation majors are the worse of the two (−0.5650). No
  consistent story.

### The conditional-edge rule was sealed and is UNMEASURABLE

The seal states that a declared stratum clearing **every mechanism criterion on
all three samples** may be reported as CONDITIONAL `MECHANISM_EVIDENCE`. The
mechanism criteria include `null_percentile` and `bootstrap_excludes_zero` — and
`CA_REQUIRED_DECOMPOSITIONS` commissions those statistics **per family and per
sample only, not per stratum.**

**So the conditional rule cannot be evaluated, and it is reported as
unmeasurable rather than allowed to evaporate.** This matters for one cut in
particular: `ca_null_eligible_but_rejected`'s **short** cohort is positive on all
three samples (+0.1886 / +0.0737 / +0.0407). Under the sealed rule that cohort is
**not** conditional mechanism evidence, because two of the criteria it would have
to clear were never computed for it, and only one of the three figures clears the
+0.10 bar in any case. **It is recorded here so a future milestone can
pre-register it, and it is explicitly not promoted.**

This is CA's equivalent of BZ's unmeasured robustness neighbourhood: a sealed
criterion that could not be run, named rather than quietly dropped.

---

## 20. Production safety

**CA altered no production decision, and the claim is checked rather than made.**

* `swing_setup`, `paper`, `trade_lifecycle`, `positions`, `portfolio`,
  `position_sizing`, `journal`, `market_regime`, `structural_trend`,
  `decision_context`, `evidence` and `risk` are **untouched** — none appears in
  the changed-file list at all (§30).
* **Milestone BY's pinned seal is `a81b6ab8…` — byte-identical.**
  **Milestone BZ's pinned seal is `4d089ff4…` — byte-identical.** Both match what
  report 0036 recorded, after CA's three extractions.
* Architecture guards assert no `swing_lab` module names an execution verb,
  mentions EVEDEX, calls an AI model, or touches the filesystem outside the
  artifact modules.
* `CaVerdict.is_approved_for_trading` and `CaVerdict.earns_forward_test` are
  `False` for **every** member, asserted over the whole enum.
* No order was placed, no exchange API was contacted, no credential was read, no
  portfolio, paper or risk state was modified, and no risk limit was changed.
* **No AI interpretation was added.** CA is deterministic end to end.

---

## 21. Reproducibility

**CA has no live path at all.** `fmits research admission` **requires**
`--from-capture` and refuses to run without it: a study that refetched mutable
market data would not be reproducible even with frozen code, which is exactly the
failure BZ recorded as BZ-D2.

| gate | result |
|---|---|
| offline reproduction with the network made **fatal** | **passes** — `fetch_raw_klines` monkeypatched to raise, study runs to completion |
| two runs of the same capture | **payload-for-payload identical**, including the control-identity digests |
| **two full independent executions** of the whole experiment | **every effect identical to all reported digits** |
| capture digest verified before measuring | `fcd0991b…` ✔ |
| an edited capture | **refused before anything is measured** |
| study artifact digest | verifies; an edited effect or manifest field is caught |
| the same study written to two paths | **byte-identical** (gzip `mtime=0`, `filename=""`) |
| a BZ capture handed to the CA reader | **refused by name** |
| a foreign schema version | **refused, never upgraded silently** |

**The CA artifact carries both digests** — the pre-registration it was measured
*under* and the BZ capture it was measured *over*. Together they answer the
question BZ could not answer of BY: two runs disagree, is it the code, the rules,
or the data? Different capture digest → the data. Different pre-registration
digest → the rules. Both equal and the numbers differ → the code, and nothing
else.

---

## 22. A conservatism in the sealed null, discovered during the run

**This is reported rather than fixed, because fixing it would mean reopening a
pre-registration after seeing results.**

The sealed empirical null pairs **two single control draws** per admission. The
observed effect pairs **one admission against the mean of 200 controls**. The
null therefore has materially larger variance than the statistic it judges, so
`null_percentile` is a harder bar to clear than a variance-matched null would be.

* **The implementation is exactly what was sealed** — the seal says "pairing two
  independent control draws per admission and taking the same mean difference",
  and that is what the code does. No seal was violated.
* **The consequence is one-directional: it can only produce false NEGATIVES.** A
  wider null raises the percentile an effect must reach. It cannot manufacture an
  edge; it can only hide one.
* **It did not decide any verdict.** Every family fails `development_effect`
  first, and that criterion does not read the null at all.
* **The properly variance-matched uncertainty statement is the symbol-clustered
  bootstrap**, which *is* sealed, *is* correctly matched to the statistic, and is
  reported for every family and sample.

A future milestone re-running this experiment should pre-register a
variance-matched null (one draw against the ensemble of the remainder). CA states
the defect and leaves its own seal alone.

### And a second inaccuracy, in the seal's own words

The independent review found that the sealed text overstates what the null does.
`RandomisationSpec.rationale` says the empirical null *"carries the same
clustering and the same sample size as the observed effect"*. **It carries the
same sample size. It does not carry the same clustering** — `_empirical_null`
draws one generator per record and takes a plain mean, with no symbol resampling
anywhere.

**This is an inaccuracy in a sealed document and it cannot be corrected without
breaking the seal, so it is disclosed instead.** The claim sits in two sealed
places — `CA_RANDOMISATION.rationale` and the `null_percentile` criterion's own
requirement text — and both are inside the digest.

**The same claim was also repeated in two UNSEALED docstrings in
`admission_study.py`, and those have been corrected**, because a docstring known
to be wrong is a defect whatever the seal says. The split is deliberate: the
sealed text stands and is disclosed; the code's own prose states the truth and
points at this section.

Its direction is the same as §22's: the null is wider than it should be
(measured at ~1.5× the clustered bootstrap's half-width), so it can only suppress
a positive result, never manufacture one. It decided no verdict — every family
fails `development_effect`, which does not read the null.

**Both of these belong in the same lesson.** A pre-registration is only as good
as the statistics it commits to, and CA's were written before the estimator was
built. A future seal should pin the estimator by *test*, not by prose.

---

## 23. Dependence and pseudoreplication

CA does **not** treat overlapping 4H observations as independent experiments.

* **The 60-bar minimum separation** guarantees a control never shares forward
  bars with the admission it is compared against — the single most important
  constraint, and the reason the separation equals the evaluation window rather
  than some smaller round number.
* **The bootstrap resamples by SYMBOL, not by admission.** Admissions on one
  symbol share its drift and regime; resampling them individually would report
  an interval too narrow by exactly that dependence.
* **Admissions overlapping each other are counted, not assumed away**: 33 of 155
  on development, 14 of 91 on validation, 49 of 234 on the holdout fall within
  60 bars of another admission on the same symbol. This is limitation CA-7, and
  the count is reported rather than implied to be zero.
* **Every comparison is paired**, which removes the symbol, period and drift
  differences that an unpaired aggregate would import.

---

## 24. Limitations

`CA_LIMITATIONS` (CA-1 … CA-7) travels inside the study and prints on every
report, with BZ's, BY's, BX's and BW's inherited beneath it.

- **CA-1 — THE OUTCOME IS NOT A TRADE.** No stop, target, exit or cost is
  applied. A positive admission effect would not have implied a profitable
  strategy, and this negative one does not imply the engine is worse than random
  *as a trading system* — it implies the moments it selects are worse than
  matched moments.
- **CA-2 — THE HORIZON BOUND IS INHERITED.** Every horizon is bounded by BW's
  60-bar (10-day) window so CA stays comparable with BW–BZ. BZ recorded this as
  the most questionable inherited assumption in the series for a strategy
  described as "swing". CA inherits it knowingly and does not resolve it.
- **CA-3 — MATCHING CANNOT REMOVE AN UNOBSERVED CONFOUND.** Controls are matched
  on symbol, sample, volatility band and calendar neighbourhood. Anything
  predicting returns that is correlated with admission but not with those four is
  not removed, and CA cannot name what it did not measure.
- **CA-4 — THE ELIGIBLE-BUT-REJECTED POPULATION IS CLASSIFIED AT DECISION TIME**,
  so some of its instants belong to opportunities that confirmed later. See §14.
- **CA-5 — SAMPLES, SYMBOLS AND WINDOWS ARE MILESTONE BY'S**, so BY-2 … BY-5
  apply unchanged: development is contaminated by construction, the holdout
  window opens later, the holdout symbols are materially less liquid, and the
  universe is survivorship-filtered.
- **CA-6 — THE INPUTS ARE MILESTONE BZ'S CAPTURE**, whose own limitation stands:
  only execution-timeframe bars are persisted. CA needs no more and says so.
- **CA-7 — ADMISSIONS ARE NOT INDEPENDENT OF EACH OTHER.** See §23.

Additionally, and not in the sealed list because they were discovered during the
run or by the independent review:

- **CA-8 — THE STUDY IS UNDERPOWERED FOR ITS OWN BAR, and this is the most
  important thing a reader should carry away.** With 155 / 91 / 234 matched
  admissions and a development bootstrap half-width of ≈ 0.558 ATR against a
  0.10 ATR bar, an interval excluding zero would need ≈ 4,800 admissions per
  sample — about 31× what exists. **No realisation of this data could have
  produced `ADMISSION_EDGE_CANDIDATE`**, so `NO_EDGE` is a statement about
  resolution as much as about the market. Found by independent review, not by
  design; a future seal must include a power calculation.
- **CA-9 — THE GATE LADDER IS UNCLUSTERED, UNMATCHED AND UNBOUNDED.** It has no
  bootstrap, no null and no concentration guard, while every family effect has
  all three. Its headline claims were withdrawn (§12.2–12.3) after review. It
  remains a valid census and an invalid inferential statistic.
- **The null's conservatism, and the seal's clustering misstatement** (§22).
- **The conditional-edge rule is unmeasurable as sealed** (§19).
- **The two lowest rungs of the ladder cannot be scored** (§12.4), so CA says
  nothing about whether the 1W regime gate or the two-family tally add value.

### What the brief asked for and CA did not deliver

* **No dashboard page.** The brief permits a very thin read-only addition to the
  existing research seam. The dashboard's seam takes *study* artifacts of a
  different shape, and CA's value is in tables a terminal renders better than a
  card. Recorded as **not done** rather than half-done.
* **The dashboard's 30–45 s refresh** was left untouched, as instructed, and is
  preserved for a later UX milestone.

---

## 25. Interpretation

Against the brief's six cases this is **CASE 4** — *neither timing nor direction
beats a matched null* — but it is **not** "in its strongest form", and the first
draft's claim that it was has been withdrawn (§12.2).

> **No admission edge is demonstrable. The point estimates lean negative. The
> study cannot resolve whether the true effect is negative or merely absent.**

* **Timing:** −0.2028 / −0.3347 / −0.5337, sign-stable across all five seeds.
  One of three intervals excludes zero.
* **Direction:** −0.0110 / −0.2036 / −0.3125 against a fair coin. No interval
  excludes zero; the development figure is a coin flip.
* **Combined:** +0.0357 / −0.1918 / −0.3088; the one positive is a third of the
  bar, sits at the 51st percentile of its null, and flips sign under two of five
  seeds.
* **Gate:** −0.1947 / −0.0641 / −0.1227, sign-stable across seeds. No interval
  excludes zero. **It is no longer described as corroborated by the gate ladder**
  — that corroboration did not survive symbol clustering (§12.3).

**And the honest reason all four fail is partly statistical, not only
substantive.** §1 and CA-8 record it: with 155 admissions and a bootstrap
half-width of 0.558 ATR against a 0.10 ATR bar, **no realisation of this data
could have produced `ADMISSION_EDGE_CANDIDATE`.** The sealed criteria asked for
precision this universe cannot supply. A reader must not take `NO_EDGE` as
"proved there is no edge"; it is "no edge of a size this study could see".

**A mechanism worth pre-registering, offered as a hypothesis and nothing more.**
Every family is positive at 1–6 bars (4–24 hours) and negative by 12–24 bars
(§15), and admissions win the ±1 ATR race on two of three samples while losing
the four-day return on all three (§16). That pattern is *consistent with* the
engine confirming on a structure break and so entering near the end of a short
impulse. **CA did not establish this.** It is a shape in the data that a
purpose-built experiment should test.

**What follows for the architecture.** Not *"the gate actively harms"* — that is
withdrawn. The defensible statement is narrower and still decisive:

> **Five milestones have now searched timeframes, geometries, geometry
> neighbourhoods, exit mechanisms and admission itself, and none has produced
> measurable evidence of an edge. Continuing to tune components around this
> admission rule is optimising inside a space nobody has shown contains
> anything.**

So: **do not preserve the current admission architecture on the strength of
anything measured here, and do not tune one component.** Either redesign
admission on a stated hypothesis, or first establish — on a larger universe, where
the question is answerable — whether any edge exists to redesign toward.

---

## 26. Recommended next milestone — **do not begin it**

**CB — Statistical power before another hypothesis.**

The first draft recommended *"redesign what confirmation means, because that is
the stage CA localised the loss to"*. **That recommendation rested on the
withdrawn gate-ladder claim and is itself withdrawn.** CA did not localise the
loss to any stage; it established that no edge is measurable at this sample size.

**The binding constraint is power, not hypotheses.** CA-8 is the finding that
should drive sequencing: 155 admissions and a 0.558 ATR bootstrap half-width
against a 0.10 ATR bar means **no experiment of this shape can answer this
question on this universe.** Testing a sixth, seventh and eighth idea at n=155
would produce five more `NO_EDGE` verdicts that mean nothing.

So the next milestone should **make the question answerable** before asking it
again. Three ways, cheapest first:

1. **Widen the universe.** The admission count scales with symbols × period. The
   capture machinery is built and a wider replay is a fetch, not a redesign.
   Reaching ~4,800 admissions per sample is roughly a 30× increase — probably out
   of reach, which is itself worth establishing early rather than late.
2. **Raise the effect the study must detect**, by pre-registering a bar the
   sample *can* resolve, and accepting that a sub-0.5 ATR edge is undetectable
   here. This is honest and it may conclude that this universe cannot support the
   question at all.
3. **Change the unit** to something with more independent observations than one
   per admitted setup — the `unconfirmed` population is 50× larger, though it is
   not what the product trades.

**Only then** is a confirmation-semantics redesign worth pre-registering. When it
happens, the shape in §15 and §16 (positive at 1–6 bars, negative by 12–24, and
winning the ±1 ATR race on two of three samples) is the hypothesis to test — and
testing it would change what the product *is*, since a 4-to-24-hour edge is not
swing trading. **That is the owner's decision, not a research one.**

Four things a future milestone should fix in this machinery: the
**variance-matched null** and the seal's **clustering misstatement** (§22),
**per-stratum bootstrap and null statistics** so the sealed conditional-edge rule
becomes measurable (§19), and either **versioning the gate-ladder aggregation or
dropping it** (§29). And every future seal should carry a **power calculation** —
CA's did not, and that omission cost this milestone its headline.

---

## 27. Falsification pass — an independent recomputation, and four attacks

§25's conclusion was attacked before it was reported, using a **separate code
path**: an independent script that re-derives the ATR from the Wilder formula,
re-derives forward returns, re-derives the admitted set and re-derives the gate
ladder **without importing any `admission*` module for the arithmetic.**

### The independent recomputation agrees exactly

| rung | CA reported | independent recomputation |
|---|---|---|
| development / `unconfirmed` | +0.1589 | **+0.1589** |
| development / `confirmed_repeat` | +0.4538 | **+0.4538** |
| development / `admitted` | −0.0028 | **−0.0028** |
| validation / `unconfirmed` | +0.2478 | **+0.2478** |
| validation / `admitted` | −0.1742 | **−0.1742** |
| holdout / `unconfirmed` | −0.0672 | **−0.0672** |
| holdout / `admitted` | −0.3083 | **−0.3083** |

Every rung, every sample, to four decimals, from independently written
arithmetic. Instant counts also match to the unit.

### Attack 1 — is the negative result a handful of outliers? **No — it is worse without them**

| sample | mean | **median** | **10 %-trimmed mean** | min | max | positive rate |
|---|---|---|---|---|---|---|
| development | −0.0028 | **−0.2024** | **−0.1565** | −11.88 | +15.99 | 0.471 |
| validation | −0.1742 | **−0.1652** | **−0.1614** | −9.48 | +9.86 | 0.451 |
| holdout | −0.3083 | **−0.1129** | **−0.1637** | −16.77 | +10.04 | 0.479 |

**The mean was flattering the admissions, not damning them.** On development the
median (−0.2024) is far worse than the mean (−0.0028), and the trimmed means are
negative and strikingly consistent across all three samples (−0.157, −0.161,
−0.164). The positive rate is below a coin on every sample.

### Attack 2 — is it an ATR-normalisation artifact? **No**

Recomputed as **raw fractional price returns**, with ATR removed from the
arithmetic entirely:

| sample | mean | median | positive rate |
|---|---|---|---|
| development | **−0.102 %** | −0.219 % | 0.471 |
| validation | **−0.528 %** | −0.407 % | 0.451 |
| holdout | **−1.037 %** | −0.285 % | 0.479 |

Negative on every sample, on both mean and median, with no ATR anywhere.

### Attack 3 — does the gate-ladder claim survive robust statistics? **Yes, and it strengthens**

`admitted` minus `unconfirmed`:

| sample | mean difference | **median difference** |
|---|---|---|
| development | −0.1618 | −0.1004 |
| validation | −0.4220 | **−0.6024** |
| holdout | −0.2411 | **−0.3585** |

Negative on both statistics on all three samples, and **larger in magnitude on
medians** for validation and the holdout.

### Attack 4 — is the SHORT branch's sign wrong? **No — the declared degeneracy proves it**

The universes are short-heavy, so a wrong `SHORT` branch would invalidate
everything. The independent recomputation gives admitted long/short means of
−0.1986 / +0.2229 (development) and −1.5485 / −0.0526 (holdout).

CA's `ca_null_opposite_direction` cohorts are **−0.3971 / +0.4457** and
**−3.0970 / −0.1053** — **exactly twice**, to four decimals, in all four cells.
That is the algebraic degeneracy §11 declared *before results*, confirmed
numerically against independently computed figures. A sign error in either branch
would break this identity.

### Attack 5 — is the gate ladder an ATR-denominator artifact? **No, but it is a weighting artifact**

The denominators are near-identical across rungs, so there is no denominator
problem:

| sample | ATR/price, `unconfirmed` | `confirmed_repeat` | `admitted` |
|---|---|---|---|
| development | 0.01938 | 0.02003 | 0.02140 |
| validation | 0.01961 | 0.02054 | 0.01838 |
| holdout | 0.02495 | 0.02607 | 0.02596 |

But recomputed as **raw percentage returns**, the development gap disappears:

| admitted − unconfirmed | development | validation | holdout |
|---|---|---|---|
| ATR-normalised | −0.1618 | −0.4220 | −0.2411 |
| **raw %, mean** | **+0.02 pp** | −1.34 pp | −0.95 pp |

**On development the ATR-normalised gap comes from volatility weighting, not from
raw price behaviour.** This was the first crack in the ladder claim; §12.3's
symbol-clustering result finished it.

### Attack 6 — does the ladder survive CA's own clustered estimator? **No**

Reported in full at §12.3 and §29 finding 1. Zero is inside the symbol-clustered
95 % interval on all three samples, and equal-symbol weighting reverses the
holdout. **This attack succeeded, and the claim it attacked was withdrawn.**

### What the falsification pass concluded

**Attacks 1–4 failed: the sealed family effects are robust.** They survive
medians, 10 %-trimmed means, removal of ATR normalisation, and the antisymmetry
identity confirms the sign convention on both branches.

**Attacks 5 and 6 succeeded against the gate ladder**, which is not one of the
sealed measurements. The withdrawal is recorded in §1, §12.2–12.3 and §29 rather
than quietly absorbed.

**The verdict is unchanged: `NO_EDGE`, zero candidates.** What changed is how
strongly this report is entitled to talk about *why*.

---

## 28. Verification

| gate | result |
|---|---|
| **Full repository under `-W error`** | **12,380 passing**, 0 failures (from **12,055** at the start of CA; **+325**) — re-run after the three review fixes |
| Focused CA suite | **282 tests** across 7 new files |
| **Hostile review** | **33 probes, 0 failures** |
| **Independent code review** | **8 findings, all verified independently: 3 code defects FIXED, 2 headline claims WITHDRAWN, 2 limitations ACCEPTED, 1 seal inaccuracy DISCLOSED** — see §29 |
| **Experiment re-run after every fix** | **every effect, interval, percentile and verdict byte-identical** to the pre-fix run |
| **Independent recomputation** of the headline | **agrees to 4 decimals on every rung and sample** (§27) |
| **Production-equivalence** of the admitted set | **246/246 primary, 234/234 holdout — exact** |
| **Production ATR reproduction** | **480/480 candidates bit-exact**, worst relative error 0.0 |
| **Two full independent executions** | every effect identical to all reported digits |
| Offline reproduction, network **made fatal** | passes |
| CA seal `910cad28…` | verified before and after |
| BY's pinned seal `a81b6ab8…` | **byte-identical** |
| BZ's pinned seal `4d089ff4…` | **byte-identical** |
| Determinism | CA digest and seed derivation stable across `PYTHONHASHSEED` 0 / 1 / 12345 |
| Architecture guards | **334 passing**, roster and artifact-exemption list extended |
| New runtime dependencies | **0** — `pyproject.toml` and `uv.lock` unchanged |
| ADRs required | **0** |
| Guards weakened | **0** |
| Guards widened | **1** — the artifact-module exemption list, 4 → 5, which is that guard's designed extension point (one entry per milestone that persists a research record) |

### Coverage

Statement **and** branch, over CA's scope:

| module | cover | notable misses |
|---|---|---|
| `admission_matching.py` | **100 %** | — |
| `admission_preregistration.py` | **99 %** | one type guard |
| `admission_study.py` | **96 %** | defensive branches and unreachable build errors |
| `admission.py` | **96 %** | argument type guards |
| `admission_artifact.py` | **95 %** | decode type guards |
| `admission_render.py` | **92 %** | formatting guards, two wrap branches |
| **total** | **96 %** | 27 statements, 26 branches uncovered of 1,168 / 328 |

**No coverage exclusion was added anywhere**, and the misses are named rather
than excused. Unlike BX, BY and BZ there is **no uncovered network entry point**,
because CA has no live path at all — every line of the run is reachable offline.

### One guard fired during development and was obeyed rather than widened

`test_no_geometry_module_names_a_position_size_or_leverage` rejected
`admission_render.py` because the prose *"the pre-declared margin"* contains the
substring `margin`. The guard is a deliberately blunt substring probe and
tightening it would weaken it for every other module, so **the sentence was
reworded to "threshold"** — the same resolution BZ recorded for `PersistencePath`
and `reached`.

Two guards were also **strengthened rather than accepted**: the renderer's
"owns no rule" tests were rewritten from text matching to AST inspection (so a
docstring mentioning `Decimal` and a renderer *constructing* one are told apart),
and the "aggregates nothing" guard was left strict — the renderer's text wrapper
was rewritten to use a running length instead of `sum()` so that no exception had
to be carved out for it.

---

## 29. Independent code review, and what it changed

An independent adversarial review was run against CA's new modules, briefed to
**falsify** the conclusion rather than to check style. It returned eight findings.
**Every material finding was verified independently before being accepted** — the
verification is a separate script that recomputes the disputed quantities from the
capture without importing the code under review.

**It was the most valuable single step in this milestone.** It refuted the claim
the first draft called its sharpest, and it found a real code defect of exactly
the class Milestone BZ had already been bitten by.

| # | finding | my verification | disposition |
|---|---|---|---|
| 1 | The gate ladder has no clustering, no interval and no concentration bound; zero is inside the symbol-clustered CI on all three samples, and **equal-symbol weighting reverses the holdout** | **CONFIRMED** — reproduced: CIs (−0.644,+0.387), (−0.996,+0.166), (−0.658,+0.220); equal-weight −0.0533 / −0.4631 / **+0.0266**; 6/15, 4/15, 8/21 symbols go the other way | **Claim WITHDRAWN.** §1 and §12 rewritten; recorded as limitation CA-9 |
| 2 | `confirmed_repeat`'s +0.4538 on development is 90 % TRXUSDT | **CONFIRMED** — TRXUSDT contributes +0.4102 of +0.4538; without it the rung is +0.0516 and the gap collapses from 0.46 to 0.054 ATR | **Claim WITHDRAWN** (§12.3) |
| 3 | `assess_ca` can return `NO_EDGE` when the `sample` criterion is `UNMEASURABLE`, because `_aggregate` computed the headline effect with no `SAMPLE_FLOOR` guard | **CONFIRMED** — reproduced with 3 matched admissions | **FIXED — defect CA-D1.** The effect and every horizon are now absent below the floor; 3 regressions added |
| 4 | Every `False` on development/validation is decided by a point estimate whose own CI covers the pass region; the criteria are structurally unpassable at this *n* | **CONFIRMED** — 14/15 intervals contain both 0 and +0.10; ≈ 4,800 admissions needed | **ACCEPTED as limitation CA-8**, promoted into §1. No code change: the criteria are sealed |
| 5 | The horizon profile contradicts the headline (positive at h=1 in 15/15 cells), and its own failure is counted as evidence for the headline | **CONFIRMED** — h=1 positive in all 15 cells | **ACCEPTED.** §25 rewritten; the h=1–6 positivity is now stated as a hypothesis to pre-register, not as support for the negative |
| 6 | `GateRung.count` is the full rung while `mean_absolute_move` is over the strided subsample | **CONFIRMED** (latent — not consumed by any reported figure) | **FIXED — defect CA-D2.** `measured` is now reported beside `count`; regression added |
| 7 | `match_admission` derives `stages` and never uses it, so a caller could measure a different null under a sealed family's id and the identity digest would still verify | **CONFIRMED** (latent — `study_from_capture` pairs them correctly) | **FIXED — defect CA-D3.** The index is now checked against the family's sealed pool; 2 regressions added |
| 8 | `_empirical_null` is not symbol-clustered, contrary to the sealed text's claim that it "carries the same clustering" | **CONFIRMED** — the null's range is ≈1.5× the clustered bootstrap's | **DISCLOSED, not fixed** (§22). The text is inside the seal and cannot be corrected without breaking it; the error is conservative |

**Categories the review cleared, each verified numerically by the reviewer and
consistent with my own checks:** sign arithmetic on both LONG and SHORT branches
(critical, given short-heavy universes); the outcome cache's (bar, direction) key
and its per-universe ATR sharing; matching completeness and the impossibility of a
control overlapping its admission; pairing bias; and the cluster bootstrap's
construction and seed-collision safety.

### The three defects, and whether they changed any result

**They did not.** CA-D1 bites only below `SAMPLE_FLOOR`, and every measured cell
holds 90–234 matched admissions. CA-D2 adds a reported field. CA-D3 adds a check
that the production path already satisfied. **The experiment was re-run after all
three fixes and every effect, interval, percentile and verdict is byte-identical
to the pre-fix run** — verified by diffing the two reports.

**What the review did change is the report's claims, and those changes are
large.** Two headline findings were withdrawn, one limitation was promoted to the
front of the document, and the interpretation in §25 was rewritten from *"the gate
selects worse than the population it rejects"* to *"no admission edge is
demonstrable, and the study cannot resolve whether one exists"*.

### One thing the reviewer flagged that I could not close

The cross-symbol aggregation of the gate ladder **is not in the repository** — no
code path aggregates `GateRung` across its `sample:symbol` key. The figures in
§12.1 were produced by analysis scripts in the session scratchpad. The reviewer
reproduced them correctly as the count-weighted pooled mean, and so did my own
independent script, so the numbers are right — but **an unversioned, untested
aggregation should not have carried a headline claim**, and that is part of why
the claim did not survive. A future milestone should either version the
aggregation or stop drawing conclusions from the ladder.

---

## 30. Changed files

**New (`src/fmis/swing_lab/`):** `admission.py`, `admission_preregistration.py`,
`admission_matching.py`, `admission_study.py`, `admission_artifact.py`,
`admission_render.py`

**Modified (`src/`):**
- `swing_lab/validation_study.py` — `walk_forward_boundaries` extracted; behaviour preserved
- `swing_lab/robustness.py` — `concentration_of_magnitudes` extracted; `concentration_of` delegates
- `swing_lab/metrics.py` — `nearest_rank_quantile` added
- `swing_lab/persistence_study.py` — `_quantile` delegates to it
- `pipeline/cli.py` — `fmits research admission`, `--save-study`, `--causal-proven`

**New (`tests/`):** `test_swing_lab_admission.py`,
`test_swing_lab_admission_preregistration.py`,
`test_swing_lab_admission_matching.py`, `test_swing_lab_admission_study.py`,
`test_swing_lab_admission_artifact.py`, `test_swing_lab_admission_surface.py`,
`test_swing_lab_admission_hostile.py`

**Modified (`tests/`):** `test_swing_lab_architecture.py` (module roster, artifact
exemption list)

**Documentation:** this report; `reports/README.md`;
`docs/AI_HANDOFF/CURRENT_STATE.md`; `FMITS_PRODUCT_BACKLOG.md`.

`FMITS_PRODUCT_CHANGELOG.md` is **not** updated: CA delivers a research
capability whose headline result is that the admission engine shows no edge.
Recording that as a user-visible capability release would misrepresent it.

---

## 31. Commit boundary

**Nothing was committed and nothing was pushed.**

`HEAD` remains `21dac05`, `origin/main` remains `21dac05`, 0 ahead / 0 behind.
The 16 pre-existing untracked research documents under `docs/design/` and
`docs/reviews/` are untouched.

Two commits are **prepared but not created**:

```
Commit A   feat(research): add swing admission null-model laboratory
           src/ and tests/ only

Commit B   docs(product): record swing admission edge study
           documentation only
```
