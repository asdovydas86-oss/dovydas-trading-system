# 0052 — Price Zone Interaction Semantics Research Gate (R3 / R4)

| Field | Value |
|---|---|
| **Report number** | 0052 |
| **Title** | Price Zone Interaction Semantics Research Gate — R3 / R4 |
| **Date** | 2026-09-20 |
| **Report type** | Research / design record |
| **Model** | Claude Opus 5 (1M context) |
| **Repository branch** | `main` |
| **Baseline commit** | `527a162` |
| **Preregistration commit** | **`296831a`** — sealed and pushed **before** the harness existed |
| **Status** | Final |

---

## 1. The one-paragraph answer

**R3 is resolved, and the thing it resolves to is not what the question assumed.** A second
consecutive close beyond a frozen zone band *does* mark a distinguishable state: it moves the
probability that price is still beyond the band ten bars later from **0.41 to 0.65**, a
**+24-point** separation that holds on 1D and 4H, on primary and holdout, and survives every
admissibility invariant. But a **placebo band — identical width, identical establishment bar,
displaced in price so that no structural level anchored it — separates by the same +24 points.**
The state is real. **Its attribution to the zone is not.** FMITS may therefore compute the
persistence state, and must not call it *zone acceptance*.

**R4 is `NO SUPPORT`.** The return hazard to a real zone is statistically indistinguishable from
the return hazard to a placebo band at every elapsed range on every role — ratio **0.96–1.02** on
the two well-powered roles, with several bins significantly *below* 1. A return to a zone is not
attributable to the prior transition, so **no `RETEST` state may be built, and no window parameter
exists to be chosen.** The raw hazard decays steeply (0.206 → 0.015 over 40 bars) exactly as a
first-passage hazard must; without the placebo this study would have reported a confident
three-bar retest window that is an artifact of arithmetic.

**Nothing in `src/` or `tests/` changed. Zero files.**

---

## 2. Verified starting state

Every row inspected live and independently of the brief, which was treated as untrusted.

| Field | Found |
|---|---|
| `HEAD` · `main` · `origin/main` · remote `refs/heads/main` | all **`527a162`** |
| Ahead / behind | `0 / 0` |
| Tracked tree | clean |
| Untracked | the **16** pre-existing research documents under `docs/design/` and `docs/reviews/` |
| Stash · active Git operation | empty · none |
| Operator dashboard | **PID 46403 on `127.0.0.1:8787`, `LISTEN`** since 7 Sep — read-only inspection, never signalled, `pkill`/`killall` never used |
| `~/.fmits` | present, `scan_memory/` only |
| `~/.fmits/risk_policy.json` | **absent** — not created by this milestone |

**Every §3 binding fact in the brief was verified rather than assumed**, and all held:
`ZONE_WIDTH_POLICY_V1` is `atr14-anchor-0_50` / `ATR_MULTIPLE` / `atr_14` / `k = 0.50` /
`AT_ANCHOR_ESTABLISHMENT` (`models.py:250`), one policy shared by all three roles, bands frozen
and never merged, `ZonePricePosition` geometry-only with **no `role` field anywhere**, and **no
interaction type of any kind** on the package's public surface.

---

## 3. Authority reconciliation — and it changed the study

R3 and R4 are stated in three live places and **they do not say the same thing.**

| Source | Wording |
|---|---|
| **Report 0047 §45** *(binding)* | R3 *"…make «acceptance» a **distinguishable state rather than a restatement of a close breach**?"* · R4 *"Within how many bars must a retest occur **to be attributable to the break**?"* |
| `CURRENT_STATE.md` §0 | *"How many closes make acceptance? Within how many bars is a return a retest?"* |
| `FMITS_PRODUCT_BACKLOG.md` §5 | *"How many closes beyond a band constitute acceptance? … a retest **rather than a coincidence**?"* |

**The original is the careful one and the paraphrases dropped the load-bearing clauses.** R3 asks
for a *distinguishable state*; R4 asks for *attributability*. Run against `CURRENT_STATE.md`'s
phrasing, this gate would have been obliged to return two numbers it had not earned — and it would
have returned them, because both numbers exist and both are misleading. The gate was run against
§45. The planning paraphrases are corrected at close, in the direction of the older and more
precise source.

---

## 4. The preregistration preceded the harness, and Git proves it

| Artifact | Value |
|---|---|
| Document | [`docs/design/ZONE_INTERACTION_RESEARCH_QUESTIONS_V1.md`](../docs/design/ZONE_INTERACTION_RESEARCH_QUESTIONS_V1.md) |
| `sha256` | `d98e15167979e684f2d7bc4d41c58a47244b6853eebb76f95359dc5e51dcc41e` |
| Commit | **`296831a`**, pushed to `origin/main` and verified with `git ls-remote` |
| State of `research/zone_interactions/` at that commit | **did not exist** |

It fixed, before a single number was computed: both exact formulations, the decomposition, the
candidate evidence set with a reason per member, the a-priori rejections, the comparison design,
the metrics, the horizons, the bins, the dataset, the cluster unit, the bootstrap seed
(`20260920`), the minimum-cell rule, the twenty fixtures, the ten admissibility invariants, the
permitted/forbidden information, the multiple-comparison policy, and the six verdicts with
numeric thresholds — **`≥ 10` percentage points for R3, hazard ratio `≥ 1.25` for R4.**

Only a **power audit** preceded the seal: zone counts, `EXIT` counts, `TRAVERSE` counts, and how
many events had ten bars of room. No outcome, no group split, no hazard, no placebo. §6.1 of the
preregistration records that table and says so.

---

## 5. Two design decisions that carried the whole result

### 5.1 Matched knowledge time (R3)

Comparing "one close" against "two closes" naively compares groups classified **one bar apart**,
so the two-close group is evaluated one bar further into the future and wins by construction.
Instead every comparison is nested at a matched classification bar:

| | classified at | evaluated over |
|---|---|---|
| **C1** `SINGLE` vs `DOUBLE` | `t0+1` | `[t0+2, t0+11]` |
| **C2** `DOUBLE_ONLY` vs `TRIPLE` | `t0+2` | `[t0+3, t0+12]` |
| **C3** displacement bins | `t0` | `[t0+1, t0+10]` |

The primary outcome is a **snapshot** at the horizon, not a path statistic, because a path
statistic is mechanically coupled to where price stood at the classification bar. The coupled
metric (M2) is still reported — **and the preregistration declared the coupling in advance rather
than explaining it afterwards.**

### 5.2 The placebo band (R4 — and, post hoc, R3)

Under a driftless walk, the first-passage hazard back to **any** price interval declines with
elapsed time. So a decaying return hazard is arithmetic, not a retest. For every real zone the
harness builds four controls:

```
P(δ) = [low + δ·w , high + δ·w]      δ ∈ {−4, −2, +2, +4}
```

Same width, same establishment bar, same series. **One difference: no confirmed structural level
anchored it.** Contamination is measured, not assumed: **45.3 %** of placebo events came from bands
with no confirmed level inside them (`270,276` of `596,578`), and only that **clean** subset is used
for attribution.

---

## 6. Dataset

Milestone CD's committed capture, digest
`07b500c7f26ac8b2a57784646654b620c2e4e4a20a475808f96b44c53b0f475f`. **No network, no credential.**
Written for a different milestone, so it cannot have been chosen to flatter this one. The
primary/holdout split is **inherited from the capture**, not chosen here.

| Universe | Role | Symbols | Zones | `EXIT` | `TRAVERSE` | events/zone |
|---|---|---|---|---|---|---|
| primary | 1W | 15 | 326 | 804 | 407 | 2.5 |
| primary | 1D | 15 | 1,147 | 10,173 | 4,455 | 8.9 |
| primary | 4H | 15 | 3,047 | 69,774 | 32,383 | 22.9 |
| holdout | 1W | 21 | 305 | 646 | 129 | 2.1 |
| holdout | 1D | 21 | 1,314 | 8,729 | 2,977 | 6.6 |
| holdout | 4H | 21 | 3,742 | 63,022 | 25,065 | 16.8 |
| **total** | | **36** | **9,881** | **153,148** | **65,416** | |

Plus **596,578** placebo events.

**Limitations, stated rather than discovered later:** survivorship (36 symbols listed and liquid at
capture); no newer majors such as `SOLUSDT`; 1D and 1W aggregated deterministically from 4H rather
than natively captured; **no volume column at all**, which removed one candidate evidence form
outright; and every result is conditional on `k = 0.50`, which this gate was forbidden to retune
and did not.

---

## 7. Dependence — why no interval is computed over 153,148

**22.9 events per zone** on primary 4H. One zone contributes many transitions as price oscillates
around it, one bar contributes events against many overlapping bands, and the three roles share one
price history. Treating these as independent samples would manufacture precision from
autocorrelation.

The unit of inference is the **symbol**: 15 primary, 21 holdout. Per-symbol rates, a **paired
Wilcoxon signed-rank** across symbols, and a **cluster bootstrap resampling symbols** (2,000 draws,
seed `20260920`). Every cell reports its event count, its symbol count, and how many symbols
cleared the per-symbol minimum.

**Minimum-cell rule, applied mechanically before any effect was read:** ≥ 200 events per group and
≥ 10 symbols each contributing ≥ 5. It fired on 1W in both universes and those cells are reported
`UNDERPOWERED`, exactly as §6.1 predicted before the run.

---

## 8. R3 — measurements

### 8.1 C1 — does a second consecutive close add information? (M1, H = 10)

| Universe | Role | n `SINGLE` | n `DOUBLE` | rate `SINGLE` | rate `DOUBLE` | difference | 95 % CI | Wilcoxon | symbols |
|---|---|---|---|---|---|---|---|---|---|
| primary | 1W | 195 | 548 | — | — | — | — | — | **UNDERPOWERED** |
| primary | 1D | 2,669 | 7,442 | 0.418 | 0.640 | **+0.222** | [+0.206, +0.236] | 7.3e−04 | 15 |
| primary | 4H | 19,158 | 50,540 | 0.411 | 0.657 | **+0.246** | [+0.237, +0.255] | 7.3e−04 | 15 |
| holdout | 1W | 147 | 433 | — | — | — | — | — | **UNDERPOWERED** |
| holdout | 1D | 2,357 | 6,287 | 0.392 | 0.642 | **+0.250** | [+0.230, +0.269] | 6.4e−05 | 21 |
| holdout | 4H | 17,412 | 45,491 | 0.419 | 0.658 | **+0.239** | [+0.229, +0.249] | 6.4e−05 | 21 |

Four reportable cells, all far above the sealed 10-point bar, all the same sign, primary and
holdout agreeing to within 3 points. Holm-adjusted minimum p = **5.1e−04**.

### 8.2 C2 — a third close adds as much again

| Universe | Role | rate `DOUBLE_ONLY` | rate `TRIPLE` | difference |
|---|---|---|---|---|
| primary | 1D | 0.398 | 0.673 | **+0.275** |
| primary | 4H | 0.434 | 0.697 | **+0.262** |
| holdout | 1D | 0.397 | 0.682 | **+0.286** |
| holdout | 4H | 0.418 | 0.698 | **+0.280** |

**There is no knee.** Each additional close adds roughly the same separation as the one before, so
the count is a **resolution control**, not a threshold with an optimum — the identical structural
conclusion report 0050 reached about `k`, arrived at independently.

### 8.3 C3 — displacement separates too, and C4 says it is not the same information

| Universe | Role | `< 0.25` ATR | `0.25–0.75` | `≥ 0.75` | far − near |
|---|---|---|---|---|---|
| primary | 1D | 0.529 (n=4,446) | 0.598 (n=4,171) | 0.743 (n=1,498) | +0.214 |
| primary | 4H | 0.525 (n=30,257) | 0.603 (n=28,016) | 0.726 (n=11,430) | +0.200 |
| holdout | 1D | 0.533 (n=3,837) | 0.594 (n=3,633) | 0.742 (n=1,183) | +0.209 |
| holdout | 4H | 0.526 (n=26,905) | 0.606 (n=26,036) | 0.730 (n=9,974) | +0.204 |

**C4 — the second close still separates *within* every displacement bin:**

| Universe | Role | `< 0.25` | `0.25–0.75` | `≥ 0.75` |
|---|---|---|---|---|
| primary | 1D | +0.169 | +0.220 | UNDERPOWERED (n=68) |
| primary | 4H | +0.207 | +0.232 | +0.292 |
| holdout | 1D | +0.190 | +0.262 | UNDERPOWERED (n=58) |
| holdout | 4H | +0.196 | +0.231 | +0.269 |

So **count and displacement are complementary, not redundant.** R3-C's hypothesis that displacement
*dominates* the count is **refuted**: knowing how far price closed beyond the band does not make the
second close uninformative, and the count's effect is in fact largest where displacement is largest.

### 8.4 Sensitivity — smooth, no knife-edge

| Universe | Role | H = 5 | H = 10 | H = 20 |
|---|---|---|---|---|
| primary | 1D | +0.306 | +0.222 | +0.157 |
| primary | 4H | +0.317 | +0.246 | +0.175 |
| holdout | 1D | +0.306 | +0.250 | +0.142 |
| holdout | 4H | +0.318 | +0.239 | +0.168 |

Monotone decay with horizon, as a persistence effect must. **M2**, the coupled metric, mirrors M1
exactly (`−0.204` to `−0.227`), which is the consistency check it was kept for.

### 8.5 POST-HOC — the control R3 was not given, and it changes the reading

**This analysis was not preregistered. It is labelled `POST-HOC` here, in the module that computes
it, and in every table it touches.** Reading §8.1 made plain that R3 carried *exactly* the exposure
§5.2 built a placebo for and had no control: a price that closed beyond a band twice is further
from that band, and a random walk started further away is more likely to be further away later.
The placebo bands already existed. Running the identical C1 comparison on the clean ones costs one
pass.

| Universe | Role | **real** diff | **placebo** diff | excess | strict-subset diff | placebo n |
|---|---|---|---|---|---|---|
| primary | 1W | +0.253 *(UP)* | +0.248 | +0.005 | +0.359 | 1,846 |
| primary | 1D | **+0.222** | **+0.224** | **−0.003** | +0.301 | 18,890 |
| primary | 4H | **+0.246** | **+0.243** | **+0.004** | +0.337 | 116,367 |
| holdout | 1W | +0.293 *(UP)* | +0.263 | +0.030 | +0.425 | 1,163 |
| holdout | 1D | **+0.250** | **+0.251** | **−0.002** | +0.357 | 18,508 |
| holdout | 4H | **+0.239** | **+0.237** | **+0.002** | +0.335 | 112,665 |

**The excess is zero to three decimal places and flips sign across cells.** A band with no
structural level behind it separates `SINGLE` from `DOUBLE` exactly as well as a real zone does.

Two supporting facts. **75–78 % of `SINGLE` events are already back inside the band at the
classification bar**, so C1 is substantially "came back" versus "stayed out". The **strict subset**
— both groups still outside the band at `t0+1`, removing that asymmetry entirely — shows an even
*larger* separation (+0.30 to +0.43), so the finding is not the tautology it might have been. The
state is genuinely distinguishable. It is simply **not a fact about the zone**.

### 8.6 Splits the preregistration required

**Direction.** Downward transitions persist more than upward ones (1D holdout: 0.660 vs 0.469).
This is an asymmetry in the **market sample**, not in the rule — reflection symmetry of the
classifier is proven exactly in §10. Over 2023–2026 USDT pairs this most likely reflects sample
composition, and **it is not a licence for direction-dependent semantics.**

**Overlap.** `overlap_inside > 1` occurs on 17.6 % (primary 4H) of events and shifts the outcome
rate only from 0.582 to 0.612. Overlap is representable and is not distorting the result.

**Gaps.** `GAPPED_BEYOND` transitions are **almost non-existent** in continuously-traded crypto —
3, 98 and 161 events per cell. **E3-MECH is unmeasurable on this dataset** and is reported as such
rather than as a null result.

---

## 9. R4 — measurements

### 9.1 Stage 1 — attribution fails

Return hazard = returns ÷ person-bars at risk, real zones versus **clean** placebo bands.

**primary 4H** — 69,774 real events, 116,506 clean placebo:

| elapsed | real | placebo | ratio | difference | 95 % CI |
|---|---|---|---|---|---|
| 1 | 0.2058 | 0.2068 | **0.995** | −0.0010 | [−0.0042, +0.0030] |
| 2–3 | 0.1213 | 0.1220 | **0.995** | −0.0006 | [−0.0027, +0.0015] |
| 4–6 | 0.0705 | 0.0717 | **0.982** | −0.0013 | [−0.0029, +0.0002] |
| 7–10 | 0.0457 | 0.0451 | **1.014** | +0.0006 | [−0.0008, +0.0020] |
| 11–20 | 0.0267 | 0.0260 | **1.024** | +0.0006 | [−0.0002, +0.0015] |
| 21–40 | 0.0149 | 0.0146 | **1.023** | +0.0003 | [−0.0000, +0.0007] |

**holdout 4H** — 63,022 real, 112,852 clean placebo: ratios **0.964 · 0.971 · 0.973 · 1.008 · 0.994
· 0.995.** Three of those CIs exclude zero **in the negative direction** — `[-0.0114, -0.0040]`,
`[-0.0059, -0.0014]` and, marginally, `[-0.0042, -0.000006]` — so real zones are returned to
*slightly less* often than placebo bands. Statistically significant, practically **0.8 percentage
points at most**, and **pointing the wrong way for the retest hypothesis**. This is the
preregistration's §7.5 warning — *significance is necessary, never sufficient* — made concrete: a
Holm-surviving result here would have argued **against** retests, not for them.

**1D:** 0.90–1.05 across every bin in both universes. **1W:** the only ratios above 1.25 anywhere
are the 4–6 bin (primary 1.224, holdout 1.287) on the role whose other bins read 0.817 and 0.770 —
one bin, one role, not reproduced, and the sealed criterion required **≥ 2 roles**.

**The sealed bar was a ratio ≥ 1.25 in at least one bin, same sign on primary and holdout,
Holm-surviving, on ≥ 2 roles. Nothing came close.**

### 9.2 The trap the placebo caught

The raw real-zone hazard is **0.206 → 0.121 → 0.070 → 0.046 → 0.027 → 0.015**. A seven-fold decay,
steepest in the first three bars. Presented alone this is a textbook "retests cluster within 2–3
bars" chart, and it would have produced a confident `R4 = 3 bars`.

**The placebo hazard is 0.207 → 0.122 → 0.072 → 0.045 → 0.026 → 0.015.** The decay is entirely
first-passage geometry. **The single most valuable line in this report is that those two rows are
the same row.**

### 9.3 Every variant agrees

| Variant | Result |
|---|---|
| **R4-E** excursion ≥ 0 / 0.5 / 1.0 ATR before the return | ratios 0.92–1.08, no trend; the one outlier (0.555) sits on a single 1D bin |
| **R4-A** `RETURN_TOUCH` instead of close-inside | ratios 0.94–1.08; primary 4H bin 1 is **1.000** |
| **R4-D** split by `SINGLE` / `DOUBLE` | mechanically confounded — `DOUBLE` *means* not returned at `j=1`, so its `j=1` hazard is 0 by definition. **Reported as a definitional artifact, not a finding** |
| **R4-F** intervening transitions | only **33.5 %** of the 144,303 resolved episodes have *no* other zone transition in between; **30 %** have ten or more. Attribution to one zone is not merely unsupported, it is rarely even isolable |
| **R4-G** clock | bar count and elapsed time are affine within a role here, so only the cross-role comparison is informative; the hazard shape is the same on all three roles, favouring **bars** over duration. Weak evidence, stated as weak |

### 9.4 Stage 2 was not run

By the preregistration's own ordering. Fitting a window to an unattributable return is the exact
mistake §4 exists to prevent.

---

## 10. Admissibility, adversarial fixtures and reproducibility

**68/68 fixture assertions pass** (`fixtures.py`), covering all twenty §11 classes. They assert
invariants and candidate-distinguishing behaviour, **never an interpretation** — a fixture claiming
"this is an acceptance" would invent the answer being researched.

**27/27 real-data checks pass** (`verify.py`): prefix stability of classification and of knowable
outcomes; window-start insensitivity; reflection symmetry on real price paths (event counts equal,
sides exactly mirrored); scale invariance at ×2, ×1024 and ×0.125; determinism **byte-identical
across processes at `PYTHONHASHSEED` 0 and 12345**; `src/` and `tests/` never import the research
package; `fmis` imports with `research/` off the path.

### 10.1 Three defects found and fixed, recorded rather than tidied away

1. **The artifact was not reproducible, and the cause was mine.** `gzip.open` stamps the wall clock
   into the gzip header, so identical payloads hashed differently on every run. A determinism check
   that had been *asserted* rather than *measured* would have shipped this. Fixed with a byte-stable
   writer (`mtime=0`); three runs now agree exactly.
2. **Five fixture expectations were wrong, and the harness was right.** I had written the expected
   return bar as a *bar index* where the field is *elapsed bars*. The fixtures failed, and the
   correct response was to fix the fixtures. Recorded because a silent "adjust the test until it
   passes" is indistinguishable from this in a diff and completely different in kind.
3. **Two verifier checks were too strict and were wrong about *why*.** Prefix stability flagged one
   event whose `beyond_at_1` moved `ABSENT → 1` at the prefix's final bar — that is history
   arriving, not drift, and the check now respects the knowable-at-`t0` / knowable-later split the
   whole study is built on. Window-start flagged 36 events whose `disp_atr` differed **in the 13th
   significant figure**: ATR(14) is a recursive Wilder average with no finite warm-up, so a
   different load window perturbs every later value in its last bits. That is a property of the
   **production indicator**, quantified here for the first time; displacement is now compared as a
   *bin* — which is what the research consumes — plus a 1e−9 relative tolerance, and **no event
   changes bin.**

---

## 11. Verdicts

**Each verdict is read off the sealed §9 table, criterion by criterion, not argued to.**

| R3 criterion (sealed) | Met? |
|---|---|
| Passes **all** of §8 | **Yes** — 27/27 |
| Separates **M1** by ≥ 10 points | **Yes** — +22 to +25 |
| Same sign on primary **and** holdout | **Yes** |
| Reportable and same-signed on **all three** roles | **No** — 1W `UNDERPOWERED` in both universes |
| Holm-surviving | **Yes** — adjusted p = 5.1e−04 |
| Neighbouring values continuous, no knife-edge | **Yes** — smooth in both `N` and `H` |

One role underpowered, the limitation nameable → **RESOLVED WITH LIMITATIONS**, by the table.

**Two criteria were checked and explicitly do *not* apply.** `NO SUPPORT` requires that no candidate
reach 10 points, or that the effect reverse between universes, or that it survive *only* where
mechanically coupled — none holds; the effect is present on the *uncoupled* M1 and the strict
subset is larger still. `REQUIRES A DIFFERENT QUESTION` is defined in §9.1 as the **evidence form**
being wrong, illustrated by displacement dominating the count — and displacement demonstrably does
**not** dominate (§8.3).

**Why the post-hoc placebo does not change the verdict.** The preregistration states that the
post-hoc control "cannot promote R3 beyond what §9 allows, and it cannot be used to *lower* a
preregistered bar." Letting an unsealed analysis move a sealed verdict is exactly the failure the
seal exists to prevent, and it would be no more legitimate in the negative direction than in the
positive. So the verdict stands where the sealed table puts it, **and the attribution failure is
recorded where §9.1 requires a limitation to be recorded: in the recommended semantics, which
forbid the name *acceptance*.** A reader who thinks the placebo finding is the more important fact
is right — and it is stated in §1, in the verdict below, in ADR-0034 D1 and in the registry.


### R3 — **RESOLVED WITH LIMITATIONS**

**What is established.** Consecutive closes beyond a frozen band mark a genuinely distinguishable
state. Two closes versus one moves the ten-bar persistence probability by **+22 to +25 points**;
three versus two adds **+26 to +29** more. It is causal, prefix-stable, deterministic,
reflection-symmetric, scale-invariant and explicit under missing ATR. ATR-normalised displacement
carries **complementary** information and does not dominate the count.

**What is not established, and it is the part the product wanted.** The separation is **not
attributable to the zone.** A placebo band with no structural level behind it separates by the same
amount (post-hoc, §8.5). Whatever is being measured is a property of price persistence relative to
*any* horizontal band of that width.

**Exact definition of what may be computed**

> For a frozen band `[low, high]` and a bar `t` whose close left the band while bar `t−1`'s close
> was inside it, the state `CLOSED_BEYOND_FOR_N_BARS` is the count of consecutive closes strictly
> beyond the same boundary beginning at `t`. **Knowledge time: bar `t + N − 1`.** Requires only
> closed candles and the band. Undefined — never defaulted — where the band does not exist.

- **Parameter:** none is owed. `N` is a **resolution control**, not a threshold; there is no knee.
- **Limitations:** 1W is `UNDERPOWERED` in both universes; gapped transitions unmeasurable;
  conditional on `k = 0.50`; direction asymmetry is a sample property, not a semantic.
- **Production safety:** computing the state is safe. **Naming it acceptance is not.**

### R4 — **NO SUPPORT**

A return to a zone after an outside state occurs at the same rate as a return to a displaced band
that no structural level anchored — **ratio 0.96–1.02** on 4H and 1D across both universes, with
several bins significantly below 1. This holds under both return definitions, all three excursion
preconditions, and the split by prior persistence.

- **What remains unknown:** nothing that more of *this* data would answer. The comparison is
  precise, not noisy — the well-powered cells have 63k–70k real events against 113k–117k controls
  and the CIs are ±0.004 wide.
- **Would another dataset answer it?** Unlikely to reverse it. A capture with volume, order-flow or
  higher-resolution intrabar data would test a *different* hypothesis about retests, not this one.
- **Recommendation:** **defer the concept, do not park the parameter.** There is no parameter.

---

## 12. Recommended semantics, and what is explicitly rejected

### Admissible — low-level, observable, and named for what was measured

`INSIDE` · `OUTSIDE_ABOVE` · `OUTSIDE_BELOW` · `EXIT` · `TRAVERSE` · `RETURN_TO_ZONE_AFTER_OUTSIDE_STATE`
· `CLOSED_BEYOND_FOR_N_BARS` · `OUTSIDE_EPISODE_LENGTH`

### Rejected, each on evidence

| Rejected | Why |
|---|---|
| **`RETEST`** | R4 `NO SUPPORT`. The word asserts attribution the data refuses |
| **`ACCEPTANCE`** | The state exists; the *zone* attribution does not (§8.5). Naming it acceptance credits the level with an effect any band produces |
| **`BREAKOUT`** | Never measured, and a `CLOSE_BREACH` is still not a breakout |
| **`FALSE_BREAKOUT` · `RECLAIM` · `REJECTION`** | Each needs R4 |
| **A retest bar-window** | No window exists to choose |
| **Direction-specific semantics** | The asymmetry is in the sample, not the rule |
| **Per-role constants** | Not tested and not needed; the rule transfers where it is powered |

### Role derivation (ADR-0033 §8) — minimal evidence per label

| Label | Needs | Available after this gate? |
|---|---|---|
| `UNTESTED` | no `EXIT` and no touch since establishment | **Yes** — pure bookkeeping |
| `HELD_FROM_ABOVE` / `HELD_FROM_BELOW` | a touch or `EXIT` that did *not* persist — i.e. a *held* judgement | **No** — "held" is the same attribution R4 refused |
| `BROKEN_UPWARD` / `BROKEN_DOWNWARD` | zone-attributable persistence | **No** — §8.5 |
| `ROLE_FLIPPED` | a break **and** an attributable retest from the other side | **No** — needs both |
| `INDETERMINATE` | the residual | Only meaningful once a sibling exists |

**One of seven labels is derivable, and it is the one that means "nothing has happened".** The
approved vocabulary is not forced into a state machine. **Support/resistance labels remain
unavailable**, and the position shortcut remains forbidden.

---

## 13. Non-regression

| Held | State |
|---|---|
| `src/` · `tests/` | **zero files changed** — `git diff --stat HEAD -- src tests` empty |
| **Full suite** | **`15,416 passed · 0 failed · 0 skipped · 0 warnings`** under `-W error` on cleared bytecode, 754.87 s — **identical to the TA Slice 5B baseline of 15,416**, as a gate that adds no production test must be |
| Policy non-regression | `tests/test_swing_setup_policy_non_regression.py` — **4 passed** under `-W error` on cleared bytecode; the 81-fixture per-fixture digest table asserted and **not edited** |
| Strategy · risk · Scan Memory · dashboard | untouched; no zone fact reaches any of them |
| Operator instance PID 46403 on 8787 | `LISTEN` at start and at close; never stopped, signalled or requested |
| `~/.fmits` | unchanged; `risk_policy.json` still absent |
| 16 untracked research documents | present and unmodified |

> **One honest note on the digest.** Prior reports cite a policy digest `8b22e6c9…` recomputed
> "outside the suite", but **the recipe for that aggregate is not recorded anywhere in the
> repository** — three plausible reconstructions over the frozen baseline produce three different
> values, none of them `8b22e6c9…`. Rather than publish a number I could not derive, policy
> non-regression is evidenced here by **re-running the 81-fixture assertion suite itself**, which is
> strictly stronger than matching a summary hash. Recording the digest's recipe is a small,
> genuinely useful follow-up.

---

## 14. Artifacts

| File | `sha256` (16) | Size |
|---|---|---|
| `0052_zone_interaction_events.json.gz` | `4605b66eaab7bfbe` | 15 M |
| `0052_zone_interaction_tables.json.gz` | `197ebaee875a92b1` | 28 K |
| `0052_posthoc_placebo_r3.json.gz` | `7bb4f722347bf49d` | 4 K |

Reproduce from committed inputs:

```
.venv/bin/python research/zone_interactions/run.py       # events      -> 0052_zone_interaction_events.json.gz
.venv/bin/python research/zone_interactions/analyze.py   # every table -> 0052_zone_interaction_tables.json.gz
.venv/bin/python research/zone_interactions/posthoc.py   # POST-HOC    -> 0052_posthoc_placebo_r3.json.gz
.venv/bin/python research/zone_interactions/fixtures.py  # 68 assertions
.venv/bin/python research/zone_interactions/verify.py    # 27 checks
```

---

## 15. Recommended next milestone

**Not a zone interaction slice.** R3 cannot carry a role and R4 cannot exist, so the Zone
Interactions step stays **BLOCKED** — now on evidence rather than on ignorance, which is a better
place to be blocked.

**Recommended: Price Phases** (`CAPABILITY_REGISTRY.md` §6 step 2). Unblocked, needs no new research
parameter, ships user-visible capability, and this gate produced nothing that changes its footing.

Pending: owner and ChatGPT review of **[ADR-0034](../docs/adr/ADR-0034-zone-interaction-evidence-boundary.md)**
(`Proposed`), which records the negative boundary so it is not re-litigated by intuition later.
