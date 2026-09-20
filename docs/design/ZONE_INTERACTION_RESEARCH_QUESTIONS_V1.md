# Zone Interaction Semantics Research — Preregistration V1

**Subjects:** research questions **R3** and **R4** ([report 0047](../../reports/0047_2026-09-07_TECHNICAL_ANALYSIS_ARCHITECTURE_GATE.md) §45),
the two parameters [ADR-0033](../adr/ADR-0033-price-zone-semantics-and-the-tolerance-boundary.md)
names as the reason `ZoneInteraction` and `ZoneReading` are not in V1.

| Field | Value |
|---|---|
| **Status** | **PREREGISTRATION — sealed before the measurement harness exists** |
| **Written at commit** | `527a162` (baseline `HEAD` = `main` = `origin/main` = remote, `0/0`, clean tracked tree) |
| **Date** | 2026-09-20 |
| **Milestone** | Price Zone Interaction Semantics Research Gate (report **0052**) |
| **Decides** | nothing. It fixes *what will be measured*, *what would refute each candidate*, and *what each verdict means* |
| **Ships** | no capability. `src/` and `tests/` are expected to be untouched |

> **This document is committed and pushed before the harness that can reveal a result exists.**
> Git history is the evidence. Anything added after results exist is marked `POST-HOC` in place
> and is not part of the preregistration.

---

## 0. Why this preregistration is required, and why it is harder than 0050's

[Report 0050](../../reports/0050_2026-09-18_PRICE_ZONE_SEMANTICS_RESEARCH_GATE.md) could refuse
outcome data entirely: D1 was a question about **representation**, and its honest answer was that
`k` is a resolution control with no optimum. R3 and R4 are not that kind of question. They assert
that a **state of the market** exists — that "price accepted beyond this area" and "price came back
to test it" name something real — and a claim about market behaviour cannot be settled by
describing geometry.

That makes this gate more dangerous, not less, in one specific way. The vocabulary arrives
pre-loaded. *Acceptance*, *breakout* and *retest* are words every chart-reader already believes in,
and a study that starts from "how many closes?" has already conceded that the state exists and is
merely haggling over its threshold. **The preregistered position of this gate is that the existence
of each state is the hypothesis, and the parameter is at most a consequence.**

Three failure modes this document exists to make impossible after the fact:

1. **Tautological evaluation.** Defining acceptance by N future closes and then reporting that
   accepted events persist is a restatement, not a finding (§9).
2. **Random-walk folklore.** Returns to a price area cluster shortly after price leaves it *for any
   band whatsoever*, because first-passage hazard declines with elapsed time under a driftless
   walk. A declining return hazard is therefore **not** evidence that a zone was retested. Without
   a control this gate would "discover" retests in pure noise (§6.2).
3. **Threshold rescue.** Widening a grid until something separates. The grids below are fixed now
   and are small.

---

## 1. Authority reconciliation — the exact wording that binds

R3 and R4 are stated in three live places, and they do **not** say the same thing. The
reconciliation is recorded here because it changes the study.

| Source | Wording | Status |
|---|---|---|
| **[Report 0047](../../reports/0047_2026-09-07_TECHNICAL_ANALYSIS_ARCHITECTURE_GATE.md) §45** | **R3** *"How many consecutive closes make «acceptance» a **distinguishable state rather than a restatement of a close breach**?"* · **R4** *"Within how many bars must a retest occur **to be attributable to the break**?"* | **BINDING — the original, and the most careful** |
| [`CURRENT_STATE.md`](../AI_HANDOFF/CURRENT_STATE.md) §0 | *"How many closes make acceptance? Within how many bars is a return a retest?"* | **Lossy paraphrase.** Superseded by §45 for research purposes |
| [`FMITS_PRODUCT_BACKLOG.md`](../../FMITS_PRODUCT_BACKLOG.md) §5 | *"How many closes beyond a band constitute acceptance? … Within how many bars is a return to a band a retest rather than a coincidence?"* | Paraphrase; the *"rather than a coincidence"* clause **preserves** R4's attribution requirement |

**The reconciliation, and it is the whole design.** Report 0047's own wording already contains the
escape hatch that the shorter paraphrases drop. R3 asks for a **distinguishable state**, not a
count — a count that distinguishes nothing answers R3 with *"no number, because there is no state"*.
R4 asks for **attributability**, not a window — a window around an unattributable return is a
number describing a coincidence. The two paraphrases in `CURRENT_STATE.md` reduce both questions to
their parameters, and a study run against those paraphrases would be obliged to return numbers it
had not earned.

**This gate is run against report 0047 §45's wording.** The planning paraphrases will be corrected
to match at close, in the direction of the older and more precise source — the same disposition
[report 0051](../../reports/0051_2026-09-18_TECHNICAL_ANALYSIS_SLICE_5B.md) applied when the
backlog and the ADR disagreed.

**Nothing in ADR-0033 is modified by this gate.** Its role vocabulary (§8) is approved *vocabulary*;
this document treats its derivability as open, per the ADR's own statement that approval "is not
permission to build the interaction engine".

---

## 2. Verified binding facts this study takes as input

Every row verified live at `527a162` before this document was written. **None of these may be
changed by this gate** (milestone brief §20).

| Fact | Verification |
|---|---|
| `fmis.price_zones` exists and ships geometry only | 1,132 lines; 15 public names |
| `ZONE_WIDTH_POLICY_V1` = `atr14-anchor-0_50`, `ATR_MULTIPLE`, `atr_14`, `k = 0.50`, `AT_ANCHOR_ESTABLISHMENT` | `models.py:250` |
| One policy shared by 1W / 1D / 4H | single module constant; no per-role variant exists |
| Bands are `anchor.price ± width/2`, frozen, never merged, split, resized or deleted | `PriceZone.__post_init__` rejects a member outside the band |
| `ZonePricePosition` is geometry; **no `role` field exists anywhere** | `grep` over `price_zones/` |
| **No interaction type exists** — no `ZoneInteraction`, `ZoneReading`, `ACCEPTANCE`, `RECLAIM`, `RETURN_INSIDE`, breakout or retest | verified over the package's public surface |
| `CrossingKind` = `TOUCH` · `WICK_BREACH` · `CLOSE_BREACH`; `CrossingMechanism` = `WITHIN_RANGE` · `GAPPED_BEYOND` · `ALREADY_BEYOND` | `level_crossing/models.py:99` |
| Exact equality is a `TOUCH`, never a breach; no epsilon anywhere | same docstring; ADR-0013 §4 |
| Zones overlap heavily at `k = 0.50` | 0050: 70 % of adjacent pairs |
| Zone evidence reaches no strategy surface; independence `NOT ESTABLISHED` (R15) | ADR-0033; unchanged by this gate |

---

## 3. R3 — exact formulation

> **R3 (binding, report 0047 §45).** How many consecutive closes make "acceptance" a distinguishable
> state rather than a restatement of a close breach?

**Operational formulation this gate tests:**

> Does any causally-knowable, prefix-stable rule over the bars following a first close beyond a
> frozen zone band partition those events into two or more classes whose **subsequent** behaviour
> differs materially, robustly, and in the same direction on primary and holdout data — and if so,
> what is the least evidence that achieves it?

**R3 is answered `NO SUPPORT` if no such rule exists.** No number is owed.

### 3.1 Decomposition — the independent decisions inside R3

| ID | Question | Why it is separable |
|---|---|---|
| **R3-A** | What is the observable state vocabulary for *leaving* a band at all? | A definition question, answered by construction, not measurement. Fixed in §5 |
| **R3-B** | Does a **second** consecutive close beyond add information over the first? | This is R3's literal question, and it is a nested comparison at matched knowledge time (§3.3) |
| **R3-C** | Does **ATR-normalised displacement** beyond the boundary add information, and does it *dominate* close count? | Report 0047 §45 assumed the count. Displacement is a competing, cheaper, single-bar evidence form. If it dominates, R3's premise is wrong in an interesting way |
| **R3-D** | Is the partition **reflection-symmetric**? | Admissibility, not a finding (§8). Upward and downward must receive identical semantics |
| **R3-E** | Does the answer **transfer** across roles (1W/1D/4H) and across the primary/holdout universes? | A rule that works on 4H alone is a per-segment calibration, not a semantic (R20) |
| **R3-F** | Does **zone overlap** change the answer, and can the model represent a close that is beyond one band and inside another? | Overlap is first-class at `k = 0.50`. Measured, not assumed away |

### 3.2 Candidate evidence forms — the complete set, with a reason each

| ID | Evidence, knowable at | Why it is in the set |
|---|---|---|
| **E1-COUNT** | consecutive closes beyond the same boundary; `N ∈ {1, 2, 3}` | R3's literal subject. `N = 1` is the degenerate reference: it **is** a close breach, so "`N = 1` is not separable from `N = 2`" is precisely the negative answer R3 permits |
| **E2-DISP** | signed distance of the transition close beyond the boundary ÷ `ATR_14` at the transition bar; bins `< 0.25` · `0.25–0.75` · `≥ 0.75` | Single-bar, no waiting, already computed by production. Tests whether *how far* beats *how many* |
| **E3-MECH** | `WITHIN_RANGE` vs `GAPPED_BEYOND` at the transition bar | Already a production fact (`CrossingMechanism`); costs nothing to carry; the milestone brief asks for gap behaviour explicitly |
| **E4-JOINT** | `E1-COUNT` × `E2-DISP` (2 × 3) | The only way to answer R3-C's *"dominates"*. Not a new parameter — a cross-tabulation of two already-preregistered ones |

**Rejected a priori, on evidence rather than preference:**

| Rejected | Why |
|---|---|
| **Volume-confirmed acceptance** | **Not expressible.** The committed capture carries `(timestamp, O, H, L, C)` and **no volume column**; `dataset.py` writes `volume=0.0`. A volume rule cannot be tested on this dataset and inventing one is a new ingestion contract |
| **Absolute / tick distance** | **Not expressible.** `fmis.data.Candle` carries no instrument metadata — the identical finding 0050 recorded for `W-TICK` |
| **Intrabar path** (touch-then-break ordering within one bar) | **Not observable.** `PRICE_ZONE_LIMITATIONS` already records that a bar has no provable internal sequence |
| **Session / time-of-day conditioning** | Crypto trades continuously and no session model exists under `src/` |
| **Per-role constants** (a different `N` for 1W/1D/4H) | Forbidden as a *candidate*. A role difference may be a **finding** (R3-E), but three constants selected per role is three fits |
| **`N ≥ 4`** | Not in the grid. The dataset's 1W arm cannot support it (§7.3), and a count that needs four bars to classify has a knowledge time approaching the evaluation horizon |
| **Continuous displacement thresholds** | Three interpretable bins, not an optimised cut point. Optimising a continuous threshold is the behaviour §14 of the brief forbids |

### 3.3 The comparison design — how leakage is made impossible

This is the load-bearing part of R3 and it is fixed now.

Let `t0` be the **transition bar**: the first bar whose close is outside a band whose previous
closed bar's close was inside it (§5.2).

Naively comparing "1 close" against "2 closes" compares two groups classified at **different**
bars, so the 2-close group is evaluated from one bar further into the future. **Every comparison
below is instead nested at a matched knowledge time:**

| Comparison | Classification completes at | Both groups evaluated over | Groups |
|---|---|---|---|
| **C1** — does close #2 add information? | `t0 + 1` | `[t0+2, t0+1+H]` | `SINGLE` = close(`t0+1`) not beyond on the transition side · `DOUBLE` = close(`t0+1`) beyond on the transition side |
| **C2** — does close #3 add information? | `t0 + 2` | `[t0+3, t0+2+H]` | conditional on `DOUBLE`; `DOUBLE_ONLY` vs `TRIPLE` |
| **C3** — displacement | `t0` | `[t0+1, t0+H]` | three `E2-DISP` bins |
| **C4** — joint | `t0 + 1` | `[t0+2, t0+1+H]` | 2 × 3 cells of `E4-JOINT` |

Both groups in every comparison are classified from information available at the **same** bar and
evaluated over a window that begins **after** that bar. No classification bar is ever inside an
evaluation window.

### 3.4 Outcome metrics, and an honest statement about one of them

| ID | Definition | Role |
|---|---|---|
| **M1** | `P(close at the last bar of the evaluation window is beyond the band on the transition side)` — a **snapshot**, not a path | **R3 primary.** Chosen because a snapshot at `H` is not mechanically implied by where price stood at the classification bar |
| **M2** | `P(any close inside the band during the evaluation window)` | **Secondary, and partly coupled by construction.** A `SINGLE` event is, at its classification bar, already not beyond — so it starts nearer the band. M2 is reported because it is the natural reading of "did the transition hold", and **the coupling is declared here, before results, rather than explained afterwards** |
| **M3** | median signed displacement at the last bar of the window, in units of `ATR_14` **at `t0`**, positive in the transition direction | Secondary; continuous; scale-free |

**Horizon.** `H = 10` bars primary. Sensitivity at `H ∈ {5, 20}`. Fixed now.

---

## 4. R4 — exact formulation

> **R4 (binding, report 0047 §45).** Within how many bars must a retest occur to be attributable to
> the break?

**Operational formulation this gate tests, in two strictly ordered stages:**

> **Stage 1 (attribution).** Is a return to a frozen band after price has left it attributable to
> the prior transition at all — that is, does it occur *more* than it would for an equivalent band
> that no structural level anchored?
>
> **Stage 2 (window), attempted only if Stage 1 succeeds.** Does that excess concentrate in a
> bounded range of elapsed bars, or is it uniform in elapsed time?

**If Stage 1 fails, R4 is answered `NO SUPPORT` and Stage 2 is not run.** A window fitted to an
unattributable return is a number describing a coincidence, and R4's own wording — *"to be
attributable to the break"* — makes Stage 1 the question rather than a preliminary to it.

### 4.1 Decomposition

| ID | Question |
|---|---|
| **R4-A** | What observable defines the return — a close back inside, or any range intersection with the band? |
| **R4-B** | **Attribution.** Does the real-zone return hazard exceed the placebo-band hazard? |
| **R4-C** | If it does, is the excess bounded in elapsed bars (a window) or flat (a lifecycle state)? |
| **R4-D** | Must R3 "acceptance" exist before a return can be attributed? Measured by splitting R4-B by `SINGLE` / `DOUBLE` |
| **R4-E** | Does requiring a minimum excursion away first change attribution? |
| **R4-F** | Does an intervening transition on **another** zone break attribution? |
| **R4-G** | Is elapsed **bar count** or elapsed **market time** the right clock? |
| **R4-H** | Does a traverse (price passing completely through without closing inside) belong to this concept at all? |

### 4.2 The placebo control — the design that makes R4 answerable

**The problem.** Under a driftless random walk the first-passage hazard back to any price interval
declines with elapsed time. Measure return times after a zone transition and a decaying hazard will
appear whether or not zones mean anything. Report 0037 established the null-model convention in this
repository; R4 needs one or it cannot distinguish a market fact from arithmetic.

**The control.** For each real zone `Z = [lo, hi]` with width `w` and anchor establishment index
`e`, construct **placebo bands** of identical width and identical establishment index, displaced in
price:

```
P(δ) = [lo + δ·w , hi + δ·w]      δ ∈ {−4, −2, +2, +4}
```

A placebo band is the same geometry, over the same series, established at the same bar, differing
in exactly one respect: **no confirmed structural level anchored it.** Transitions and returns are
generated on placebo bands by the identical rules (§5), and the identical metrics are computed.

**Placebo contamination is measured, not assumed away.** A displaced band may happen to contain a
confirmed level. Every placebo event records whether any level established by that bar lies inside
it; results are reported over all placebos **and** over the **clean** subset (no contained level),
and the two are reported separately whether or not they agree.

**Why displacement and not a shuffled series.** A surrogate series would also destroy the
volatility clustering that sets the band width, changing two things at once. Displacement changes
one.

### 4.3 Metrics

| ID | Definition |
|---|---|
| **M4** | Discrete return hazard `h(j) = returns at elapsed j ÷ at-risk at j`, `j = 1…J`, right-censored at series end (Kaplan–Meier convention). **R4 primary**, computed for real and placebo bands |
| **M5** | Cumulative return probability `F(j) = 1 − Π(1 − h(i))` |
| **M6** | Hazard **ratio** and **difference**, real ÷ placebo and real − placebo, per elapsed bin |
| **M7** | Fraction of outside episodes with ≥ 1 intervening transition on another zone before the return (R4-F) |

**`J = 40`** for 4H and 1D; **`J = 20`** for 1W. Elapsed bins for M6: `1` · `2–3` · `4–6` · `7–10` ·
`11–20` · `21–40`. Fixed now.

**Return definitions, both measured (R4-A):** `RETURN_CLOSE_INSIDE` (first bar with `lo ≤ close ≤ hi`)
and `RETURN_TOUCH` (first bar with `high ≥ lo and low ≤ hi`). Primary is `RETURN_CLOSE_INSIDE`,
because it is the one that does not depend on an intrabar extreme whose ordering is unknowable.

**Excursion precondition (R4-E):** maximum distance beyond the boundary reached before the return,
in `ATR_14` at `t0`; analysis repeated conditional on `≥ 0`, `≥ 0.5`, `≥ 1.0`.

**Clock (R4-G):** bar count is primary. Elapsed wall-clock time is recorded per event, and because
each role's bars are uniformly spaced in this dataset the two clocks are affine within a role — so
**R4-G is answerable across roles only**, by asking whether the hazard knee lands at the same bar
count or the same elapsed duration on 4H, 1D and 1W. This limitation is declared now.

---

## 5. The observable vocabulary — fixed by construction, before measurement

**Deliberately low-level. No word below is an interpretation, and none may be renamed to one.**

### 5.1 Per-bar state against one band

For a closed bar with close `c` against a frozen band `[lo, hi]`:

```
c > hi                 ->  OUTSIDE_ABOVE
c < lo                 ->  OUTSIDE_BELOW
lo <= c <= hi          ->  INSIDE
```

Inclusive at both edges, **exactly** as `PriceZone` membership is inclusive and with the same
exact-comparison rule `CrossingKind` uses: equality is `INSIDE`, never outside. No epsilon.

### 5.2 Events

| Event | Definition | Knowable at |
|---|---|---|
| **`EXIT`** | state(`t`) ≠ `INSIDE` and state(`t−1`) = `INSIDE`, with `t−1 ≥` the anchor's establishment index | `t` |
| **`TRAVERSE`** | state(`t`) and state(`t−1`) both ≠ `INSIDE` and differ | `t` |
| **`RETURN`** | first `t_r > t0` with state(`t_r`) = `INSIDE` | `t_r` |
| **`OUTSIDE_EPISODE`** | the span `[t0, t_r)`, or `[t0, end]` if censored | continuously |

**`EXIT` is the R3/R4 subject. `TRAVERSE` is recorded and reported separately and is never merged
into `EXIT`** — a bar that jumps from one side of a band to the other never established an outside
state relative to an inside one, and calling it the same event would answer R4-H by assumption.

**No state below is named `BREAKOUT`, `ACCEPTANCE`, `RECLAIM`, `RETEST`, `REJECTION`, `HOLD` or
`FAILURE`.** If R3 supports a persistent state, §26 of the milestone brief governs its name, and the
recommendation may explicitly be that FMITS can classify it and still must not call it a breakout.

### 5.3 Overlap (R3-F) — represented, never resolved

Every event records `overlap_inside_count`: the number of **other** zones of the same symbol and
role, established by `t0`, that contain the transition close. A close beyond one band while inside
another is a **normal, representable state**, not an error. All R3 results are reported split by
`overlap_inside_count = 0` versus `≥ 1`.

**Zones are never merged, and interactions stay zone-local.** Each band is tracked independently and
one bar may generate events against many bands.

---

## 6. Dataset

**[`reports/artifacts/0040_cd_source_capture.json.gz`](../../reports/artifacts/), content digest
`07b500c7f26ac8b2a57784646654b620c2e4e4a20a475808f96b44c53b0f475f`.** Committed, offline, **no
network and no credential**, written by Milestone CD for a different purpose — which is why it
cannot have been selected to flatter this result. The same capture report 0050 used.

| Universe | Symbols | 4H bars/symbol | Span |
|---|---|---|---|
| **primary** | 15 | 7,313 | 2023-04-10 → 2026-08-11 |
| **holdout** | 21 | 5,117 | 2024-04-10 → 2026-08-11 |

**The primary/holdout split is inherited, not chosen here.** It is a property of the committed
capture, fixed by Milestone CD before this question was asked.

Roles are built by `research/zone_semantics/dataset.py` exactly as report 0050 built them: native
4H, deterministic 1D and 1W aggregation, **incomplete buckets dropped** at both ends.

### 6.1 Adequacy assessment — required by the brief before the capture may be reused

Measured before sealing (counts only — §7.4):

| Universe | Role | Zones | `EXIT` events | `TRAVERSE` | with `H=10` room |
|---|---|---|---|---|---|
| primary | 1W | 326 | **804** | 407 | 743 |
| primary | 1D | 1,147 | **10,173** | 4,455 | 10,111 |
| primary | 4H | 3,047 | **69,774** | 32,383 | 69,698 |
| holdout | 1W | 305 | **646** | 129 | 580 |
| holdout | 1D | 1,314 | **8,729** | 2,977 | 8,644 |
| holdout | 4H | 3,742 | **63,022** | 25,065 | 62,903 |

**Verdict: adequate for 1D and 4H; 1W is declared at risk of `UNDERPOWERED` before any result is
seen.** 1W carries ~40–50 events per symbol, and the C2 (`N=3`) and joint 2×3 cells will subdivide
it further. The §7.3 minimum-cell rule will decide, not a judgement made after looking.

**Known limitations, stated now:**

- **Survivorship.** The 36 symbols were listed and liquid at capture. Delisted assets are absent.
  For R3/R4 this biases toward markets that persisted; it does not obviously favour either verdict,
  and it is not repaired here.
- **No newer majors** (`SOLUSDT` and similar). Relevant to a claim about *today's* market
  composition; not relevant to whether a state transition is distinguishable in principle.
- **1D and 1W are aggregated from 4H**, not natively captured. Acceptable because both roles are
  built by the identical deterministic rule production would use, and the alternative is a network
  fetch this gate is not authorised to make.
- **No volume**, which removes one candidate evidence form outright (§3.2).
- **One `k`.** Every result is conditional on `k = 0.50`. The brief forbids retuning it and this
  gate does not.

**Because the capture is adequate on the two roles that carry the events, this gate proceeds. No new
data-source contract is required and none is requested.**

---

## 7. Inference, dependence and power

### 7.1 Events are not independent and will not be reported as though they were

`69,774` events arose from `3,047` zones — **≈ 17 events per zone**. One zone contributes many
transitions as price oscillates around it; one bar contributes events against many overlapping
bands; the three roles share one underlying price history. **No p-value or interval will be computed
over the raw event count.**

### 7.2 The unit of inference is the symbol

- **36 clusters** (15 primary, 21 holdout), the coarsest grouping that removes both within-zone and
  overlapping-zone dependence.
- **Primary inference:** per-symbol rates, then a **paired** comparison across symbols (Wilcoxon
  signed-rank on each symbol's own group difference). A symbol is one paired observation.
- **Uncertainty:** cluster bootstrap resampling **symbols** with replacement, 2,000 resamples, seed
  **`20260920`**, fixed now. Percentile intervals at 95 %.
- Event-level, zone-level and symbol-level counts are all reported so the dependence is visible
  rather than asserted.
- Cross-role results are reported **per role** and never pooled.

### 7.3 Minimum-cell rule — fixed now

A comparison is reportable only if **both** groups satisfy:

- **≥ 200 events**, and
- **≥ 10 symbols** each contributing **≥ 5 events**.

A cell failing either test is reported **`UNDERPOWERED`** and no effect is read from it. This rule
is applied mechanically, before the effect is looked at.

### 7.4 What was computed before sealing, exactly

A **power audit only**: zone counts, `EXIT` counts, `TRAVERSE` counts, and how many events have
`H = 10` bars of room — the table in §6.1. **No outcome, no group split, no hazard, no comparison
and no placebo was computed.** The probe is reproduced in the report.

### 7.5 Multiple comparisons

Preregistered primary comparisons: **R3 family** — C1, C2, C3, C4 × 3 roles = 12. **R4 family** —
hazard-difference over 6 elapsed bins × 3 roles = 18. **Holm correction within each family
separately.** Raw and adjusted values both reported. Sensitivity runs (`H ∈ {5,20}`, excursion
conditions, return definitions, `δ` values) are **robustness checks, not additional primary tests**,
and are reported as such.

**Statistical significance is not the criterion.** A Holm-surviving difference of two percentage
points is not a semantic. §9's thresholds are about magnitude and stability; significance is
necessary, never sufficient.

---

## 8. Admissibility — invariants every candidate must pass

**A candidate failing any of these is disqualified regardless of how well it separates outcomes.**
Tested on the candidate classification rule itself, not on the outcome.

| # | Invariant | Test |
|---|---|---|
| 1 | **Causality** | Every event carries an explicit knowledge-time index; no field reads a bar beyond it |
| 2 | **Prefix stability** | Re-run over every prefix; a classification once emitted never changes. **0** changed classifications required |
| 3 | **Determinism** | Byte-identical artifacts across two processes and `PYTHONHASHSEED ∈ {0, 1, 12345}` |
| 4 | **Reflection symmetry** | On `mirror_about − price`, every classification maps exactly to its mirror. Upward and downward semantics must be identical |
| 5 | **Scale invariance** | On `×2`, `×1024`, `×0.125`, classifications are identical |
| 6 | **Warm-up / missing ATR** | Before ATR warm-up the answer is an explicit *unavailable*, never a default or a substituted width |
| 7 | **No intrabar path** | No rule may depend on the order of events within one bar |
| 8 | **Timeframe transfer** | Same rule, no per-role constant (a role *difference* may be a finding) |
| 9 | **Cross-asset transfer** | Direction of effect consistent primary → holdout |
| 10 | **Window-start insensitivity** | Truncating the leading 10 % of bars does not change classifications of surviving events |

---

## 9. Verdict criteria — fixed before any result

### 9.1 R3

| Verdict | Criteria |
|---|---|
| **RESOLVED** | A candidate passes **all** of §8; separates **M1** by **≥ 10 percentage points**; same sign on primary **and** holdout; reportable (§7.3) and same-signed on **all three** roles; Holm-surviving; neighbouring parameter values behave **continuously** (no knife-edge) |
| **RESOLVED WITH LIMITATIONS** | As above, but one role is `UNDERPOWERED` or contradicts, and the limitation is nameable and stated in the recommended semantics |
| **BOUNDED BUT NOT IDENTIFIED** | Separation exists and is **monotone** in the parameter with no plateau or knee — the 0050 outcome. Report the region; **refuse a point value** |
| **UNDERPOWERED** | §7.3 fails on the cells that would decide it |
| **NO SUPPORT** | No candidate reaches 10 points on M1 on any role, or the effect reverses between primary and holdout, or it survives only where it is mechanically coupled (M2 but not M1) |
| **REQUIRES A DIFFERENT QUESTION** | The measurements show the state is real but the evidence form is wrong — e.g. displacement dominates count so decisively that "how many closes" is the wrong question |

**10 percentage points on M1 is the preregistered bar, and it is deliberately high.** A separation
smaller than that does not justify two deterministic names, two code paths and a role vocabulary in
a product whose stated principle is that internal complexity is not value.

### 9.2 R4

| Verdict | Criteria |
|---|---|
| **RESOLVED** | Stage 1 passes — real hazard exceeds **clean** placebo hazard by a **ratio ≥ 1.25** in at least one elapsed bin, same sign on primary and holdout, Holm-surviving, on ≥ 2 roles — **and** Stage 2 identifies a bounded elapsed range beyond which the excess is indistinguishable from placebo, at the same range on ≥ 2 roles |
| **RESOLVED WITH LIMITATIONS** | Stage 1 passes; Stage 2 gives a range that differs by role or is wide |
| **BOUNDED BUT NOT IDENTIFIED** | Stage 1 passes but the excess is **flat** in elapsed time → attribution exists, **no window exists**, and *retest* is a **lifecycle state, not a bar-window parameter**. R4's literal question would then be answered *"no number; the question presumes a window that is not there"* |
| **UNDERPOWERED** | §7.3 fails |
| **NO SUPPORT** | Real and clean-placebo hazards are indistinguishable → a return is **not attributable** to the transition. Recommend at most the neutral observable `RETURN_TO_ZONE_AFTER_OUTSIDE_STATE`, and **no `RETEST` state at all** |

### 9.3 Role derivation (ADR-0033 §8)

Independently of R3/R4, the report states the **minimal evidence** each of the seven approved labels
would require, and which remain **unavailable** after this gate. **The seven labels will not be
forced into a state machine because the ADR names them.** A role staying unavailable is an
acceptable and expected outcome.

---

## 10. Permitted and forbidden information

**Permitted:** OHLC of the same series strictly after the classification bar · `ATR_14` at or before
the classification bar · zone sets derived from the prefix ending at the classification bar ·
`CrossingKind` / `CrossingMechanism` facts at or before it.

**Forbidden, and asserted in the harness:**

- `ATR` read after the classification bar (the exact hazard 0050 measured at 983,916 illegal events)
- zone boundaries recomputed from later history, or final-history zone membership where prefix-time
  membership differs
- centred windows, hindsight-selected anchors, any lookahead into the classification
- **PnL, win rate, Sharpe, returns, entry or exit prices, LONG/SHORT labels, the swing policy,
  evidence votes, Scan Memory, risk budgets** — none is read and none is computed. **This is not
  strategy research and produces no trading recommendation**
- the holdout universe for **any** choice: thresholds, bins, horizons, grids and verdict criteria
  are fixed in this document and the holdout is scored **once**, at the end

---

## 11. Adversarial fixtures

Built **before** the empirical results are trusted, on synthetic series, asserting **invariants and
candidate-distinguishing behaviour** — deliberately **not** asserting an interpretation, because the
interpretation is what is being researched.

| # | Fixture | What it must establish |
|---|---|---|
| 1 | Wick beyond, close inside | No `EXIT`. Never an interaction by close-state |
| 2 | One close barely beyond, immediate return | `EXIT` then `RETURN` at `j=1`; `SINGLE` |
| 3 | One close far beyond, immediate return | Same classification as #2 under E1; **different** under E2 — the fixture that proves the two evidence forms are not the same rule |
| 4 | Two closes beyond, then return | `DOUBLE`; classification completes at `t0+1` |
| 5 | Alternating closes around the boundary | Each `INSIDE`→outside is a fresh `EXIT`; no state is carried across a return |
| 6 | Gap wholly beyond the band | `EXIT` with `GAPPED_BEYOND`; no intrabar claim |
| 7 | Close beyond one band, inside an overlapping one | Both recorded; `overlap_inside_count = 1`; neither suppressed |
| 8 | One bar interacting with several bands | One event per band; zone-local |
| 9 | Excursion away, then boundary touch only | `RETURN_TOUCH` fires, `RETURN_CLOSE_INSIDE` does not |
| 10 | Excursion away, then full return inside | Both fire, at the same or different bars |
| 11 | Excursion away, then straight through | `RETURN` fires on entry; the traverse does not cancel it |
| 12 | Return after a very long interval | Recorded with its true elapsed `j`; **no window is applied at classification time** |
| 13 | Another zone's transition in between | `M7` flag set; the episode is not broken |
| 14 | Same-bar exit and return | Impossible by construction (one close per bar); the fixture asserts the construction |
| 15 | Mirrored up/down sequence | Exactly mirrored classifications (§8.4) |
| 16 | Decimal-scaled copy (`×1024`, `×0.125`) | Identical classifications (§8.5) |
| 17 | Missing ATR / warm-up | No zone, therefore no event; explicit unavailable |
| 18 | No future bars after classification | Event emitted, outcome **censored**, never dropped silently and never counted as a non-return |
| 19 | Event at the window boundary | Right-censoring handled by the hazard estimator |
| 20 | Repeated returns / repeated exits | Each episode independent; no double counting |

---

## 12. Harness, reproducibility and isolation

- Lives in **`research/zone_interactions/`**, outside `src/`, per `research/README.md`.
- **Production code produces every structural fact** — `detect_swings`, `compare_swing_sequence`,
  `label_swing_sequence`, `structural_levels`, `derive_price_zones`, `zone_width_series`,
  `AverageTrueRange`. The harness owns the event walk, the placebo construction and the metrics, and
  **re-derives no production mathematics**.
- A guard asserts **0** references to `research` from `src/` and `tests/`, and that `fmis` imports
  with `research/` off the path.
- No network, no credential, no wall clock, no randomness outside the seeded bootstrap.
- Artifacts written to `reports/artifacts/0052_*.json.gz` with recorded `sha256`.

---

## 13. The statement this document exists to make

**No parameter is required to win.**

`NO SUPPORT` for acceptance, `NO SUPPORT` for retest, or both, are **successful outcomes** of this
gate. They would prevent an interaction engine, a role vocabulary, a support/resistance label and
every breakout-adjacent concept from being built on a distinction that does not exist — which is
worth more to the product than a threshold that survives only because someone needed one.

The milestone succeeds by producing an honest answer.
