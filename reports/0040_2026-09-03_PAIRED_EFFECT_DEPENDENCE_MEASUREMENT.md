# Milestone CD — Paired-Effect Dependence Measurement

| Field | Value |
|---|---|
| **Report number** | 0040 |
| **Title** | Paired-Effect Dependence Measurement |
| **Date** | 2026-09-03 |
| **Report type** | Research (measurement) |
| **Model** | Claude Opus 5 (1M context) |
| **Repository branch** | `main` |
| **Audited commit** | `f47cd05ece1ee4812bef6d3ffea05aaaa17391ae` |
| **Status** | Complete. Delivered as **one commit** on top of `f47cd05`, on the owner's explicit instruction to commit and push at closure. |
| **Pre-registration seal** | `28f8ebed0aa66dd77d16b08b8a8eecda86c922e5ded9db6da24881674c37c25d` |
| **Source capture digest** | `07b500c7f26ac8b2a57784646654b620c2e4e4a20a475808f96b44c53b0f475f` |
| **Study artifact digest** | `2a7ba54ed16d2f3d723883c72bbe25919d2d1ada78278430579a005f54fd9c9a` (pre-review run `754dccd6…` preserved as `0040_cd_paired_dependence_prereview.json.gz`) |
| **Scientific verdict** | `INCONCLUSIVE` |
| **Design implication** | `INCONCLUSIVE` on the sealed headline; `UNREACHABLE` on 5 of 15 panels |
| **Independent review** | **Performed — 3 reviewers, 30 findings, 2 critical.** One of the two invalidated this report's central *explanation* and one invalidated its effective-cluster *arithmetic*. Both are corrected below; §30 records every finding and its disposition. **This report was substantially rewritten after review.** |

---

## Reading key

Every claim in this report is tagged.

- **FACT** — a property of the repository or the data that needs no inference.
- **MEASUREMENT** — a number this milestone computed, with the method that produced it.
- **INFERENCE** — a conclusion drawn from measurements, which could be wrong if an assumption is.
- **LIMITATION** — something this milestone could not do or could not know.
- **HYPOTHESIS** — a proposal for future work. Not a finding.

---

## Required separation — where each part lives

This report is written in the milestone brief's own order. The closure brief asks
for nineteen things to be **clearly separated**; they are, and this is where each
one is.

| # | required part | section |
|---|---|---|
| 1 | Question CD was intended to answer | §4, §5 |
| 2 | Provenance and exact CA reproduction | §8, §23 |
| 3 | Pre-registration and seal history | §4, §4.1 |
| 4 | Sealed estimator and sealed results | §11, §13.1, §13.2, §24 |
| 5 | Reviewer A findings (statistics) | §24.1, §12, §14, §17.1, §18, §30.2 |
| 6 | Reviewer B findings (bias / causality) | §13.2, §13.3, §15, §22, §28, §30.2 |
| 7 | Reviewer C findings (engineering) | §8, §16, §17.2, §23.1, §25, §26, §30.2 |
| 8 | Corrected / post-review diagnostics | §24.1, §17.1, §18, and `CD_POST_REVIEW_LIMITATIONS` |
| 9 | **What survives review** | **§29.1** |
| 10 | **What no longer survives review** | **§29.2** |
| 11 | Implications for CB | §15, §24 |
| 12 | Implications for CC | §28 |
| 13 | Implications for CA | §8, §32, and §29.3 A–F |
| 14 | Limitations | §35, sealed CD-1…CD-7, post-review CD-8…CD-20 |
| 15 | Required next research step | §34 |
| 16 | Engineering verification | §31, §32, §33 |
| 17 | Mutation evidence | §27 |
| 18 | Offline reproducibility | §23.2 |
| 19 | Final verdict | §29, §29.3 |

**Four categories are kept apart throughout, and the distinction is load-bearing:**

| category | meaning | how it is handled |
|---|---|---|
| **SEALED** | fixed in `CD_PREREGISTRATION_DIGEST` before any result | never edited; quoted as sealed |
| **IMPLEMENTATION BUG** | code failed to execute the seal faithfully | **fixed**, with a non-vacuity regression |
| **METHODOLOGICAL LIMITATION** | the seal itself is imprecise or wrong | **disclosed**, behaviour pinned, never rewritten |
| **POST-REVIEW DIAGNOSTIC** | computed after the fact, outside the seal | reported *beside* the sealed figure, never in place of it |

---

## 1. The answer, first

**MEASUREMENT.** Across the economic assets Milestone CA actually measured, the
paired admission-versus-control forward-effect observations are **positively
dependent between assets observed in the same period**, at

    r_b = +0.1984      95 % block bootstrap [-0.0491, +0.4181]

on the sealed primary family and sample, and **essentially independent within one
asset**, at

    rho_w = -0.0355    95 % asset bootstrap [-0.0774, -0.0064]

**MEASUREMENT.** The point estimate is positive in **all fifteen (family, sample)
panels**, from +0.0951 to +0.5492, median +0.1968, and in **all sixteen cells** of
the sealed sensitivity grid, from +0.1217 to +0.5142.

**FACT — the sealed verdict is `INCONCLUSIVE`, and that is the honest answer.** On
the primary family and sample the interval runs from −0.0491 to +0.4181. It spans
from *at or below zero* — no dependence penalty at all — to *far above* the
saturation threshold — unreachable at any universe size. A panel of fifteen
assets cannot separate those two worlds, and the pre-registered rule says so
rather than reading the point estimate as if the interval were not there. Five of
the fifteen panels — every family on **validation** — put the *lower* bound above
the threshold and are `UNREACHABLE` across their whole interval.

### 1.1 Two things this report got wrong, and independent review caught

**This section exists because the first version of this report led with both of
them.** Neither changes the verdict; both change what the verdict *means*.

**(a) The mechanism was wrong.** The first version attributed `r_b > 0` to CA's
controls sitting "90–360 days" from their admission, so that the pairing was not
contemporaneous. Three refutations, each reproduced (§13.3):

- `eligible_pool` filters `distance < separation or distance > radius`. **The
  radius is a ceiling, not a floor.** Controls sit **10 to 90 days** away for
  1,387 of the 1,430 matched rows.
- **Two of the five families draw a `SAME_BAR` control** — 960 of 2,390 rows — so
  no calendar distance applies to them at all.
- The real mechanism is worse: `control_forward` is the mean over **200** draws,
  so `sd(control) / sd(admission) = 0.168` and
  **`corr(D, admission_forward) = +0.9868`**. For `ca_null_opposite_direction`,
  `control ≡ −admission` to 6e-14 and `D ≡ 2 × admission`; since the ICC is
  scale-invariant, **that family's `r_b` *is* the raw-outcome `r_b` exactly**.

**CD did not measure the dependence of a market-neutralised paired effect. It
measured, very nearly, the dependence of the raw admission outcome.** The pairing
removes almost nothing — not because the control is far away, but because
averaging 200 controls annihilates the control leg's variance.

**(b) The effective-cluster arithmetic was overstated by about 3×.** `r_b` is the
correlation between two **individual** contemporaneous observations;
`K / (1 + (K−1) r)` expects the mean pairwise correlation of **cluster-level**
series. Those coincide only if every admission of one asset is contemporaneous
with every admission of another, and admissions are scattered over the window.
Writing `q` for the fraction of cross-asset observation pairs that actually share
a block, the design-relevant quantity is `q · r_b`. On a CA-shaped panel with a
**known** `r_b` of 0.20 (§24.1):

| quantity | value |
|---|---|
| measured true design effect | **1.4266** |
| the sealed formula `1 + (K−1) r_b` | **3.7446** |
| overlap-corrected `1 + (K−1) q r_b` | **1.3895** |

On the headline panel `q = 0.1880`, so the design-relevant correlation is
**+0.0373**, not +0.1984. Corrected, Milestone CC's 38 eligible assets supply
**8.0 – 23.1** effective independent clusters rather than 1.8 – 8.4, and its
106-asset ceiling supplies **9.1 – 37.5** rather than 1.8 – 9.7.

**The qualitative conclusion survives every correction.** All fifteen corrected
values remain above `1/K* = 0.002141`; the shortfall against 467 is **12–51×**
rather than 50–250×; and the verdict is unchanged. What changed is that the
report may no longer claim saturation has *already* been reached — only that it
binds well before 467.

**FACT.** The sealed formula is inside the digest and is **left exactly as
sealed**. The correction is computed beside it, carried in the artifact, printed
by the renderer, and recorded as post-review limitation **CD-8** — Milestone CC's
own pattern for a finding that arrives after a seal.

### 1.2 What is left standing, and it is still the important thing

**MEASUREMENT.** Milestone CC assumed CA's paired within-symbol difference
removes the market factor and measured a residual of **+0.0023** by proxy. The
measured value on the actual paired effects is **+0.1984** — roughly **eighty
times** larger — and it is positive in every panel and every grid cell. Even
after the 3× arithmetic correction, the design-relevant `q · r_b` of **+0.0373**
is **17× the threshold at which the requirement stops being finite**.

**INFERENCE.** The information does not accumulate across assets the way
Milestone CB's `MORE_CLUSTERS_SAME_DENSITY` path assumes. That conclusion is
robust to every correction independent review forced, and it is the one the owner
should act on.

### What this does and does not establish

- It does **not** say the strategy is good or bad. Milestone CA's `NO_EDGE`
  stands untouched.
- It does **not** approve trading, paper trading, shadow trading or a threshold
  change. `DependenceVerdict` and `RequirementOutcome` report
  `is_approved_for_trading` `False` for every member, asserted over both enums.
- It does **not** overturn Milestone CC. CC's `INFEASIBLE` on `cluster_count`
  stands as the historical record; §28 records a refinement beside it.
- It **does** close Milestone CB's limitation **CB-2** — the unmeasured
  intracluster correlation — with a measured value (§15).
- It **does** replace CC's failed residual proxy with an estimator that recovers
  a known dependence, and shows CC's estimator returning the same number at every
  true correlation on the very same panels (§12, §20).

---

## 2. Verified starting state

**FACT.** Checked before anything was written, not assumed.

| Check | Value |
|---|---|
| `HEAD` | `f47cd05ece1ee4812bef6d3ffea05aaaa17391ae` |
| local `main` | `f47cd05ece1ee4812bef6d3ffea05aaaa17391ae` |
| `origin/main` | `f47cd05ece1ee4812bef6d3ffea05aaaa17391ae` |
| `git ls-remote origin refs/heads/main` | `f47cd05ece1ee4812bef6d3ffea05aaaa17391ae` |
| ahead / behind | `0 / 0` |
| branch | `main` |
| staged files | none |
| stash | empty |
| `MERGE_HEAD` / `REBASE_HEAD` / `CHERRY_PICK_HEAD` / bisect | all absent |
| rebase directories | none |
| tags | one pre-existing (`bm-pre-rewrite-backup`); **none created** |
| untracked at start | exactly the **16** pre-existing research documents |

**FACT.** The 16 pre-existing untracked documents under `docs/design/` and
`docs/reviews/` were not touched, staged, renamed, formatted, deleted or
committed. They are still untracked and still unmodified.

**FACT.** The expected released Milestone CC state was verified rather than
copied: `CC_PREREGISTRATION_DIGEST` recomputes to
`ef6f39508a3d183c88618c727ba65fd8c6ffdcada4452660aaa4ad74a0021bac`, the CA seal
recomputes to `910cad28001ee18d9630f685e454bfd6bf24fb7d78b907e89172371b83f25e8a`,
the BZ seal is
`4d089ff43ec11e24e7e43e0a0f7ca377da996ee5a6391bb8f9c70d6922a3a175`, the BY seal
recomputes to its pinned value, and Milestone CB's requirement recomputes to
**467 clusters / 4,823 admissions** by calling `ca_required_information` rather
than by quoting. All four are asserted by
`tests/test_paired_dependence_architecture.py::TestProductionSafety`.

**FACT.** Production constants confirmed unchanged, by import, before and after:
`CONFIRMATION_LOOKBACK_BARS = 10`, `MINIMUM_AGREEING_FAMILIES = 2`,
`DEFAULT_TIMEFRAMES = 1w / 1d / 4h`, `DEFAULT_BACKTEST_LIMIT = 250`, and the
derived warm-up still **1,750 days**.

---

## 3. Architecture and reuse audit

**FACT.** The data path was traced end to end before any code was written:

```
market data → capture_for_window (BX/BY)   → GeometryCandidate + ThesisTimeline
            → PersistenceCaptureArtifact   (BZ)
            → study_from_capture           (CA)  → PairedRecord
            → PairedRecord.difference(24)  (CA)  → the estimand
            → ObservationRow               (CD)
            → intraclass_icc on two axes   (CD)
            → required_information         (CB)  → 467 clusters
            → effective_clusters           (CC)  → the saturation curve
```

**FACT — authoritative owners, called rather than duplicated.**

| Concept | Owner | How CD reaches it |
|---|---|---|
| admission identity | `fmis.swing_lab.admission` | via CA's own study loop |
| paired difference | `PairedRecord.difference` | **called**; never recomputed |
| primary horizon | `admission_preregistration.PRIMARY_HORIZON` | imported; a mismatch is refused |
| matching / randomisation | `admission_matching` | untouched; CA draws its own controls |
| sample boundaries | `swing_lab.preregistration.SAMPLES` | imported by identity |
| economic-asset identity | `fmis.universe.identity.economic_asset_id` | called |
| effective clusters | `fmis.universe.dependence.effective_clusters` | called |
| Pearson correlation | `fmis.universe.dependence.pearson` | called |
| cross-sectional demeaning | `fmis.universe.dependence.market_residuals` | called (as a control) |
| seed derivation | `fmis.research_design.numeric.derive_seed` | called |
| quantiles | `fmis.research_design.numeric.nearest_rank_quantile` | called |
| largest share | `fmis.research_design.numeric.largest_share` | called |
| design/power arithmetic | `fmis.research_design.resolution.required_information` | called |
| research verdict vocabulary | CA / CB / CC enums | preserved; CD adds two |

**FACT.** **No second power calculator, no second correlation primitive, no
second quantile rule, no second seed derivation and no second candle model was
written.** The only genuinely new mathematics is the one-way random-effects ICC
and the inversion of the saturation curve, neither of which existed anywhere in
the repository.

### 3.1 The one extraction, and why it was not an extraction

**FACT.** CD needed `PairedRecord`s and must not re-derive them from a copy of
CA's orchestration loop. Rather than extract that loop — which would have been a
behaviour-changing refactor of a sealed milestone — `study_from_capture` gained
**one additive keyword-only argument**, `record_observer`, defaulting to `None`,
called at exactly one site immediately after the primary-seed records are
collected. This is the pattern Milestone BZ already used on
`capture_geometry_candidates` for the identical reason, and the docstring says so.

**FACT.** Behaviour preservation is asserted, not argued:
`test_a_study_with_an_observer_is_identical_to_one_without` runs CA's study twice
over the same capture and compares `payload()` field for field. A second test
asserts the observer sees **only** the primary seed's records — the alternate-seed
draws, which exist solely to answer whether a sign is a property of the data or of
one draw, are not observed — and an architecture guard asserts the call site
appears exactly once and sits immediately after the primary-seed collection.

**FACT.** The whole diff to `admission_study.py` is **14 added lines**: one
parameter, an eleven-line docstring paragraph, and two lines of call.

### 3.2 The provenance gap CD had to close first

**FACT — and this is why CD was harder than it looked.** Milestone CA is a *pure
function of a saved Milestone BZ capture* and has no live path at all. **That
capture was never persisted into the repository.** `reports/artifacts/` held only
Milestone CC's two files. The runner that produced it during BZ was ad hoc and is
gone.

**INFERENCE.** That single missing file is the direct cause of Milestone CB's
limitation **CB-1** ("summary-statistic reproduction, not data-level") and
**CB-2** ("the intracluster correlation is unmeasured"), and of Milestone CC's
**CC-1**, which forced CC to substitute the price-return proxy that its own
review then showed could not answer the question. Three milestones were degraded
by one unwritten runner.

**FACT.** CD wrote the runner down — `fmis.paired_dependence.capture` — as a
composition of `capture_for_window`, `TimelineCollector` and `encode_capture`,
choosing no window, no symbol and no threshold of its own, and persisted the
result.

**CORRECTION — the gap is narrowed, not closed.** The first version said "closed".
Independent review pointed out that `capture_ca_sources` has **no CLI surface** and
is called from no committed code, so the *invocation* — universes, `run_at`,
transport, output path — is still ad hoc, which is the same class of omission that
caused the original gap. The runner and its windows are now tested and permanent;
the one-line invocation is recorded verbatim in §23.3 and disclosed as **CD-20**.

---

## 4. Pre-registration

**FACT.** `src/fmis/paired_dependence/preregistration.py` fixes the research
question, the estimand, the unit of evidence, the universe source, the identity
semantics, the sample boundaries, the primary horizon, the control family, the
handling of unmatched admissions, the repeated-observation rule, the overlapping-
window rule, the same-symbol overlap policy, the cross-asset contemporaneity
rule, the primary estimator, the secondary estimators, the uncertainty method,
five sample floors, the whole sensitivity grid, the winsorisation policy, the
calibration requirement and tolerance rule, five verdict rules, six requirement
rules, five interpretation rules, the non-promotion rule, the provider-mutability
statement, five artifact requirements and seven limitations.

**Seal: `28f8ebed0aa66dd77d16b08b8a8eecda86c922e5ded9db6da24881674c37c25d`.**

**FACT.** Determinism proven across four `PYTHONHASHSEED` values (`0`, `1`, `42`,
`1234567`) in **separate processes**. 47 mutation tests assert the digest moves
for every scientifically material field, including a reordering of the block
grid; an identical copy does not move it.

**FACT.** No result can enter the seal. `CdPreregistration` has no attribute that
could hold a correlation, an interval, a count or a verdict; the payload's key set
is **pinned** in the test file so adding one is a failure; and a guard asserts no
key name reads as a result, with a two-item allowlist (`measured_samples`,
`requirement_outcome_vocabulary`) that is itself asserted to hold design content.

### 4.1 The seal was pinned twice, and the second time is recorded

**FACT.** The seal was first fixed at `e2656f1f…` before the capture completed and
before any paired difference existed. It was re-pinned at `28f8ebed…` — **still
before any real estimate was computed** — because one sealed sentence named a
helper function by its identifier (`coverage_of`), and that identifier had to
change to satisfy the repository's zero-collision export invariant (§26). The
sentence now names the *concept*, so no future rename can move the digest.

**FACT.** The entire difference between the two digests is that one sentence. No
threshold, axis, floor, grid, rule, seed or verdict boundary differs. Both digests
are recorded in the module docstring so the change is auditable rather than
silent.

**LIMITATION.** A seal that had to be re-pinned is weaker evidence than one that
never moved. The mitigation is that the re-pin is dated, its cause is named, its
diff is one sentence, and it happened before any outcome existed — but a reader is
entitled to weigh it.

---

## 5. The exact estimand

**FACT.** For each admitted instant `i` under one sealed CA null family:

    D_i = admission_forward(24) - mean over that admission's own matched
                                  control draws of control_forward(24)

in ATR units, direction-normalised. This is
`fmis.swing_lab.admission_study.PairedRecord.difference(PRIMARY_HORIZON)`
**called**. `PRIMARY_HORIZON` is Milestone CA's sealed `24`, verified against
`FORWARD_HORIZONS = (1, 3, 6, 12, 24, 60)`; the pre-registration refuses to
construct itself if the two disagree.

**FACT.** Every persisted row stores `admission_forward`, `control_forward` and
`difference` separately, and `ObservationRow.__post_init__` re-checks that the
stored difference is still the arithmetic of its parts. A hand-edited paired
difference is refused on read, **before** the content digest is even consulted.

### 5.1 Two parameters, and they are not interchangeable

**FACT.** The same one-way random-effects ICC is applied on two grouping axes,
and the two results are different quantities:

| | grouping | member | what two members are | consumed by |
|---|---|---|---|---|
| `rho_w` | economic asset | one paired observation | two admissions on one exposure, generally at different times | CB's design effect `1 + (m-1)ρ` |
| `r_b` | time block | one (asset, block) cell value | two different exposures inside one contemporaneous window | the effective-cluster cap `1/r_b` |

**FACT.** `GroupingAxis` carries `.measures` and `.member_unit` so the distinction
survives into the payload and the report, and the renderer is guarded against
printing them in one column. Substituting one for the other would be wrong by
orders of magnitude **in the direction that flatters the design**, which is why the
sealed interpretation rules forbid it.

**FACT.** Neither is contemporaneity by assumption. Admissions land on whatever
4H bar production admitted them and two assets almost never share a bar; a *time
block* is what makes the comparison well posed, and its length is a sealed
sensitivity dimension precisely because that choice is a model and not a fact.

---

## 6. Unit of evidence, and the counts that must not be merged

**FACT.** One `(admitted instant, null family)` pair at the primary horizon is one
**row**. One admitted instant is one **admission** and produces up to five rows,
one per sealed family, measuring the same instant against different controls. One
economic exposure is one **economic asset**.

**FACT.** Every headline is computed **within one family on one sample**. Rows are
never pooled across families: five rows sharing an admission are one observation
measured five ways, and pooling them would multiply the apparent sample by five
without adding an instant. `PanelResult` has no field that could hold a pooled
number, and a test asserts every panel's coverage reports exactly one sample and
one family.

---

## 7. Universe

**FACT.** Milestone BY's three sealed sample specifications, imported by identity.
Development and validation are the same fifteen symbols over adjacent windows;
the holdout is twenty-one symbols no milestone before CA measured. CD adds no
symbol, removes none and re-orders nothing.

**FACT.** CD deliberately does **not** use Milestone CC's 38 eligible economic
assets. No paired admission-versus-control observation has ever been computed for
23 of them, and constructing some would require a 1,750-day warm-up replay of a
universe CC already proved cannot reach the requirement. CD measures the
dependence of the observations that **exist**.

**LIMITATION — CD-1.** The panel is fifteen and twenty-one assets, not
thirty-eight. Nothing here says what the dependence would be on a universe nobody
has measured.

---

## 8. The source capture — and what it says about the provider

**FACT.** CD replayed both CA universes fresh, on 2026-09-03, taking **80.3
minutes** of wall clock over two public unauthenticated endpoints
(`klines` only; no credential, no signature, no order path).

| universe | symbols | window | candidates | observations | bars |
|---|---|---|---|---|---|
| `primary` | 15 | 2023-06-01 → 2026-08-01 | **246** | 105,030 | 109,695 |
| `holdout` | 21 | 2024-06-01 → 2026-08-01 | **234** | 100,926 | 107,457 |

**CORRECTION — the gap is seven days, not three years.** The first version of
this report called this reproduction "three years and one provider generation"
old and "a stronger result than it was reasonable to expect". Report 0037 is dated
**2026-08-27**; CD's capture manifest reads `captured_at: 2026-09-03`. **The
elapsed time between the two captures is seven days.** The three years is the
*data window* (2023-06-01 → 2026-08-01), not the gap. Found by independent review.
The reproduction is real and worth reporting; it was framed as roughly 150×
stronger than it is, and "one provider generation" had no support at all.

**MEASUREMENT.** Report 0037 §4.1 published **246** candidates for primary and
**234** for the holdout. CD's fresh capture reproduces **both exactly**, and the
stage census sums to **104,130** and **99,666** measured instants — 0037 §4.1's
figures, to the unit. CA's matched admission counts reproduce exactly on all
three samples:

| sample | CD matched | CA published (report 0037 §10) | delta |
|---|---|---|---|
| development | 155 | 155 | **0** |
| validation | 91 | 91 | **0** |
| holdout | 234 | 234 | **0** |

**MEASUREMENT — and this is the part the first version *under*-claimed.** The
agreement is not only in counts. CD's reconstructed `ca_null_matched_timing`
effects are **−0.2028 / −0.3347 / −0.5337** on development / validation /
holdout — **identical to four decimal places to the point effects report 0037 §10
published**. The re-capture reproduced Milestone CA's *values*, not merely its
sample sizes, which is materially stronger evidence against CD-7 than the count
comparison the first version settled for.

**INFERENCE.** The provider's spot history for these 36 instruments over these
windows was stable across the seven-day gap, and the admission path is
deterministic. That is a real reproducibility finding, and it was **not** assumed:
the
pre-registration stated in advance that a divergence would be reported as a
provider finding rather than reconciled away, and Milestone CC had observed the
provider delist `ICXUSDT` — one of CA's fifteen — between two runs eight days
apart. `ICXUSDT` fetched normally on 2026-09-03.

**LIMITATION — CD-7.** The paired differences CD measures are nevertheless **not
bit-identical** to CA's, because CA's capture no longer exists to compare against.
Equality of counts is strong evidence and is not proof of equality of values.

**FACT.** The capture is persisted at
`reports/artifacts/0040_cd_source_capture.json.gz` (13,354,747 bytes, digest
`07b500c7…`, self-verifying). **No existing artifact was deleted or overwritten.**

---

## 9. The observation dataset

**FACT.** **2,390 observation-level paired differences** persisted, each carrying
observation identity, family, sample, captured universe, provider symbol, base
asset, economic asset, bar index, timestamp, direction, horizon, market segment,
volatility band, matching pool size, matching radius tier, control draw count,
admission forward, control forward, the paired difference, and the source
capture's content digest.

**FACT.** Base asset is derived by a sealed rule — strip a known quote asset,
and **refuse** a symbol ending in none of them rather than guess where the quote
begins, because a guessed split on `ETHBTC` would merge two exposures onto one
identity. Economic identity is then `economic_asset_id` called.

**FACT.** No outcome-based filtering exists. Every exclusion is a property of the
admission's identity or the panel's shape. `outcome_permutation_stable` permutes
every measured difference and asserts the panel's rows, assets, blocks, cells and
bar indices are **identical** — and a deliberately leaky shaper is asserted to
fail it, so the control is not vacuous.

---

## 10. Overlap structure and coverage — the headline panel

**MEASUREMENT.** Primary family `ca_null_matched_timing`, primary sample
`development`, at the sealed 60-bar block:

| dimension | value |
|---|---|
| rows | 155 |
| admissions | 155 |
| economic assets | **15** |
| provider symbols | 15 |
| time blocks occupied | 58 |
| blocks holding **2 or more** assets | **38** |
| (asset, block) cells | 148 |
| possible asset pairs | 105 |
| **measurable** asset pairs | **15** |
| pairs below the 4-shared-block floor | **90** |
| observations per asset | min 3, mean 10.3, max 14 |
| assets with 2+ observations | 15 |

**MEASUREMENT.** 33 of 155 admissions (21.3 %) fall within 60 bars of another
admission on the same economic asset. **This reproduces report 0037 §23's "33 of
155" exactly.**

**FACT.** Those 33 are **kept**, not dropped. Dropping them would select on the
timeline and would remove exactly the clustered admissions `rho_w` exists to
measure. They are counted, per family and per sample, and the share is reported.

**INFERENCE.** 90 of 105 asset pairs share fewer than four blocks. That is why
the pairwise correlation is a *secondary* estimator: a mean over the 15 survivors
would describe the densest corner of the panel rather than the panel.

---

## 11. The primary estimator, derived before it was run

**FACT.** Under `D_gm = mu + alpha_g + eps_gm`, two members of the same group have
correlation `rho = s2_a / (s2_a + s2_e)` and two members of different groups have
correlation zero. The unbalanced one-way ANOVA method of moments estimates it:

    SSB = sum_g n_g (mean_g - mean)^2        df_B = G - 1
    SSW = sum_g sum_m (y_gm - mean_g)^2      df_W = N - G
    k0  = (N - sum_g n_g^2 / N) / (G - 1)
    s2_a = (MSB - MSW) / k0     s2_e = MSW
    rho  = s2_a / (s2_a + s2_e)

**FACT.** No iteration, no optimisation, no starting value — nothing to tune.
`k0` reduces to the common group size when groups are balanced, asserted by test.
The weighted form reduces to the unweighted one **exactly** at unit weights,
asserted by test.

**FACT.** An undefined decomposition returns `None` **with a stated reason**,
never a zero: fewer than two groups, no group holding two members, a degenerate
`k0`, or a total variance of zero. "There is no correlation here" and "the
correlation is zero" are different claims and only one of them is evidence.

**FACT.** A negative estimate is **reported as measured** and truncated to `[0,1]`
only where downstream arithmetic requires it, with both values carried.

**FACT — why this is not Milestone CC's estimator.** CC removed the
cross-sectional mean and correlated the residuals. For `x_i = f + e_i` with an
exchangeable common factor, that removes `f` *exactly* and pins the residual
correlation at `−1/(K−1)` whatever the truth is. CD does not demean: the shared
component is the **quantity estimated**, as a variance component, not removed.

---

## 12. Estimator validation — synthetic calibration

**FACT.** Fourteen scenarios, 25 replicates each, generated with a stated
generative structure and no market data. The tolerance is **derived, not chosen**:
`1/(K−1)` is exactly the magnitude of the cross-sectional exchangeability
artefact at `K` assets, and an estimator cannot be asked to resolve finer than
that on a `K`-asset panel. At `K = 15` it is 0.0714.

| scenario | expected `r_b` | mean over 25 | within tolerance |
|---|---|---|---|
| independent | 0.0000 | +0.0007 | yes |
| weak_between | 0.0500 | +0.0573 | yes |
| moderate_between | 0.2000 | +0.2016 | yes |
| strong_between | 0.5000 | +0.4897 | yes |
| within_asset_only | 0.0000 | −0.0511 | yes |
| both_components | 0.3750 | +0.3676 | yes |
| unequal_observations | *none* | +0.8122 | ordering only |
| missing_overlap | 0.5000 | +0.4929 | yes |
| repeated_within_asset | 0.3750 | +0.3898 | yes |
| duplicated_identity | 0.2000 | +0.2290 | yes |
| dominant_market_factor | 0.7752 | +0.7900 | yes |
| **market_factor_removed** | **−0.071428** | **−0.071428** | yes |
| non_exchangeable_blocks | *none* | +0.3244 | ordering only |
| ca_shaped | 0.2000 | +0.2200 | yes |

**MEASUREMENT — the ordering is reproduced strictly**: 0.0007 < 0.0573 < 0.2016
< 0.4897, four distinct values for four distinct truths. An estimator that is
biased but monotone is still usable for a design question; one that scrambles a
known order is not, and the ordering gate is checked **first** in the verdict.

**MEASUREMENT — and a claim the first version made about it, withdrawn.**
`market_factor_removed` takes the dominant-factor panel, subtracts each block's
cross-sectional mean — Milestone CC's exact operation — and the estimator returns
**−0.071428**, which is `−1/(15−1)` to six decimal places.

**The first version called this "the decisive row … CC's failure reproduced with
CD's own machinery, exactly". Independent review showed it is an algebraic
identity.** After block-demeaning every group mean is exactly zero, so `SSB ≡ 0`
(measured at 1.3e-31) and `rho = −MSW/k0 / (1 − 1/k0) = −1/(k0−1)` for **any data
whatsoever**. The row would return −0.0714 even if the variance-component logic
were broken, and its acceptance band, [−0.143, 0.000], is wide enough to admit
zero.

**What it is worth, stated correctly.** It is a correct prediction and a check
that the code implements the ANOVA formula. It is **not** evidence that the
estimator can distinguish dependence. **The evidence for that is the ordering
row** — 0.0007 < 0.0573 < 0.2016 < 0.4897 for four known truths — and the real-data
comparison in §16, where CC's estimator spans less than 0.01 across true
correlations from 0 to 0.78 while CD's spans more than 0.4. Recorded as CD-14.

**LIMITATION — CD-13.** The calibration tolerance `1/(K−1)` = 0.0714 is **33×** the
`1/K*` = 0.002141 that every design conclusion turns on, and with 25 replicates
the calibration mean carries a Monte-Carlo standard error near 0.020 — ten times
the threshold. The gate certifies that the estimator recovers a known **ordering**.
It does not, and cannot, certify precision anywhere near the decision boundary.
Its derivation is also a non sequitur: `1/(K−1)` is the magnitude of the artefact
**CC's broken estimator** produces, which bounds nothing about this one.

**MEASUREMENT — a bias CD found in itself and reports.** `within_asset_only` has
a true `r_b` of zero and the estimator returns **−0.0511**. Strong asset-level
heterogeneity biases the block-axis estimate *downward*. **That is the
anti-conservative direction** — it understates cross-asset dependence and so
flatters feasibility. The real `rho_w` is ≈ 0 (§15), so the bias is small here,
but it is measured and stated rather than assumed away.

**FACT.** Two scenarios carry no point expectation by design — unequal cell sizes
(no single `r_b` describes a panel whose cell-mean noise differs per asset) and a
non-exchangeable block structure (the model's assumption is false by
construction). They are asserted by ordering alone rather than against a
fabricated target, and `has_point_expectation` says so in the type.

---

## 13. The real dependence estimate

### 13.1 Headline

**MEASUREMENT.** `ca_null_matched_timing` on `development`, 60-bar blocks,
cell-mean reduction, equal-cell weighting:

| quantity | value |
|---|---|
| groups (time blocks) / members (cells) | 58 / 148 |
| mean square between / within | 25.0710 / 15.4142 |
| `k0` | 2.5306 |
| variance components (between / within) | 3.8160 / 15.4142 |
| **`r_b`** | **+0.198438** |
| 95 % block bootstrap | **[−0.049065, +0.418073]** |
| half-width | 0.233569 |
| usable draws | 2000 / 2000 |

### 13.2 Every panel, never pooled

**MEASUREMENT.** Fifteen panels; `r_b` positive in all fifteen.

| family | sample | n | assets | `r_b` | 95 % CI | `rho_w` | CC residual |
|---|---|---|---|---|---|---|---|
| matched_timing | development | 155 | 15 | +0.1984 | [−0.0491, +0.4181] | −0.0355 | −0.0834 |
| matched_timing | validation | 91 | 15 | **+0.4782** | **[+0.1911, +0.6897]** | +0.0131 | −0.3250 |
| matched_timing | holdout | 234 | 21 | +0.1262 | [−0.0622, +0.2879] | +0.0321 | −0.2194 |
| eligible_but_rejected | development | 151 | 15 | +0.1968 | [−0.0155, +0.4038] | −0.0180 | −0.2804 |
| eligible_but_rejected | validation | 90 | 15 | **+0.3895** | **[+0.0490, +0.6410]** | +0.0222 | −0.2825 |
| eligible_but_rejected | holdout | 229 | 21 | +0.0951 | [−0.0853, +0.2587] | +0.0133 | −0.1540 |
| combined (timing+random dir) | development | 155 | 15 | +0.1935 | [−0.0444, +0.4321] | −0.0292 | +0.0045 |
| combined | validation | 91 | 15 | **+0.5142** | **[+0.2070, +0.7292]** | +0.0166 | −0.2228 |
| combined | holdout | 234 | 21 | +0.1483 | [−0.0254, +0.3022] | +0.0276 | −0.2329 |
| opposite_direction | development | 155 | 15 | +0.1876 | [−0.0657, +0.4001] | −0.0271 | −0.0466 |
| opposite_direction | validation | 91 | 15 | **+0.5355** | **[+0.2421, +0.7357]** | +0.0169 | −0.2703 |
| opposite_direction | holdout | 234 | 21 | +0.1590 | [−0.0160, +0.3117] | +0.0301 | −0.1958 |
| random_direction_same_bar | development | 155 | 15 | +0.2002 | [−0.0461, +0.4144] | −0.0245 | −0.1377 |
| random_direction_same_bar | validation | 91 | 15 | **+0.5492** | **[+0.2693, +0.7523]** | +0.0045 | −0.2709 |
| random_direction_same_bar | holdout | 234 | 21 | +0.1538 | [−0.0205, +0.3013] | +0.0322 | −0.1902 |

**MEASUREMENT.** Range +0.0951 to +0.5492, median +0.1968. **All fifteen above
the saturation threshold 0.002141.** Five of fifteen — every family on
**validation** — have a *lower bound* above it too.

**MEASUREMENT.** Validation is systematically the most dependent sample
(+0.39 to +0.55) and the holdout the least (+0.10 to +0.16).

**The first version of this report said the small-sample and regime explanations
"cannot be separated". Independent review separated them, using CD's own data.**
Twenty-nine contiguous 14-month sub-windows of **development**, each cut to
validation's own sample size (n = 76–96), give `r_b` **median +0.138, minimum
+0.034, maximum +0.308**. **None of the twenty-nine reaches validation's
+0.478.** Shortening the window does not inflate `r_b` on this data.

**INFERENCE.** The small-sample explanation is **refuted**. What remains is a
regime explanation — or a cause CD has not identified. The regime reading is
itself weakened by the holdout, whose window *contains* validation's and which
returns +0.126. Leave-one-out on validation spans +0.408 to +0.531 by asset, so
it is not one asset or one block either.

**LIMITATION.** CD does not know why validation is the most dependent sample, and
the five `UNREACHABLE` panels are all validation panels. They are reported, and
they are **not** the basis of any conclusion in §1.

### 13.3 Why the paired difference is not market-factor-free — **corrected**

**The first version of this section was wrong and is replaced.** It is kept as a
correction rather than deleted, because the wrong explanation drove the wrong
recommendation in §34.

**FACT — what the first version claimed.** That CA's controls sit 540–2160 bars
(90–360 days) from their admission, so the pairing is not contemporaneous.

**FACT — why that is wrong, three ways.**

1. **The inequality is inverted.** `fmis.swing_lab.admission_matching.eligible_pool`
   filters `if distance < separation or distance > radius: continue`. The radius
   is a **ceiling**. `match_admission` tries the tiers tightest-first and takes
   the first that fills the minimum pool, so a control sits between 60 bars (10
   days) and, for the overwhelming majority, 540 bars (90 days). Measured from
   CD's own artifact: **1,387 of 1,430** matched rows used tier 0, 23 used tier 1
   and 20 used tier 2.
2. **Two families have no calendar distance at all.**
   `ca_null_opposite_direction` and `ca_null_random_direction_same_bar` are
   `CaControlSource.SAME_BAR`: the control *is* the admission's own bar. All
   **960** of their rows carry `radius_tier: None`. The claimed mechanism cannot
   apply to 40 % of the dataset, and both families were counted in the
   "positive in every panel" corroboration.
3. **The control leg has almost no variance.** `control_forward` is the mean over
   **200** draws, so it collapses toward a per-admission near-constant. On the
   headline panel `sd(admission_forward) = 4.2233` against
   `sd(control_forward) = 0.7108` — the control carries **2.8 %** of the
   admission's variance — and `corr(D, admission_forward) = +0.9868`.

**MEASUREMENT — the estimand, compared against the raw admission leg alone:**

| family | sample | `r_b(D)` | `r_b(admission alone)` |
|---|---|---|---|
| matched_timing | development | +0.1984 | +0.1876 |
| matched_timing | validation | +0.4782 | +0.5355 |
| matched_timing | holdout | +0.1262 | +0.1590 |
| opposite_direction | dev / val / hold | +0.1876 / +0.5355 / +0.1590 | **identical** |
| eligible_but_rejected | development | +0.1968 | +0.1869 |

**FACT.** For `ca_null_opposite_direction`, `control_forward ≡ −admission_forward`
to 5.9e-14 and `difference ≡ 2 × admission_forward` to 6.0e-14. The ICC is
scale-invariant, so **that family's `r_b` is the raw-outcome `r_b` by
construction, not by approximation.**

**INFERENCE — the corrected mechanism.** The pairing does not neutralise the
market factor because **it barely changes the estimand at all**. `D` is
arithmetically close to the admission's own direction-normalised forward
excursion, and two assets admitted in the same window share that excursion's
common component. This is a property of averaging 200 controls, not of where
those controls sit in the calendar.

**INFERENCE — why this matters more than the wrong version did.** A redesign
aimed at "move the control closer in time" fixes nothing: CD already contains two
families whose control is at the *same instant*, and they return
`r_b` of +0.1876 and +0.2002. A redesign must change the control's **variance
structure**, not its calendar distance. §34 is rewritten accordingly.

**LIMITATION — recorded as CD-10.**

---

## 14. Uncertainty

**FACT.** Bootstrap resampling the axis each estimand's independent replicates lie
on, 2,000 draws, nearest-rank percentile bounds, **no interpolation** — an
interpolated bound reports a correlation no resample ever produced. A group drawn
twice becomes **two groups**; merging the copies would produce an interval too
narrow by exactly the resampling it was supposed to do, and a regression asserts
the relabelling.

**FACT.** Fisher-z is **refused**. Its variance formula assumes independent
bivariate normal pairs, which this panel violates on every count, and it would
give the narrowest interval on offer. The narrowness is the reason to refuse it.

**MEASUREMENT — headline panel, all four intervals:**

| estimand | resampled | point | 95 % interval | half-width |
|---|---|---|---|---|
| `r_b` | **blocks** (primary) | +0.198438 | [−0.049065, +0.418073] | 0.2336 |
| `r_b` | assets (sensitivity) | +0.198438 | [+0.255059, +0.714843] | 0.2299 |
| `rho_w` | **assets** (primary) | −0.035450 | [−0.077362, −0.006421] | 0.0355 |
| `rho_w` | blocks (sensitivity) | −0.035450 | [−0.034314, +0.185275] | 0.1098 |

**FACT — a disagreement, reported rather than resolved.** The asset-resampled
interval for `r_b` does **not contain its own point estimate**. That is expected
and is why the seal made block resampling primary: resampling assets duplicates
assets *within* blocks, duplicated assets are perfectly correlated with
themselves, within-block variance falls and `r_b` is pushed **upward in every
resample**. The asset-resampled interval is therefore **upward-biased by
construction for a between-asset statistic** and is reported as the
pre-registered sensitivity it is, not as an interval for `r_b`.

**FACT — and the first version reported one of these and not the other, which was
selective.** The same defect afflicts the *other* cross-axis interval:
`rho_w` resampled on **blocks** gives [−0.0343, +0.1853] around a point of
**−0.0355**, so the point sits *below* its own lower bound. Same mechanism — a
block drawn twice duplicates observations inside an asset and inflates `rho_w` in
every resample. The renderer now flags **any** interval that excludes its own
point, so neither can be reported without the other. Found by independent review.

**INFERENCE.** Read the primary intervals. The sensitivities are retained because
hiding a disagreement would be worse than explaining one.

**LIMITATION — CD-17.** Even the primary block bootstrap is anti-conservative
under structure this panel plausibly has. Simulated coverage at nominal 95 % is
0.95 with iid blocks and homogeneous loadings, but **0.83** with heterogeneous
factor loadings and **0.88** with AR(1) block factors — both ordinary for crypto.
No bootstrap on offer resamples the axis of generalisation, which is the universe
of hundreds of assets the estimand is meant to describe.

---

## 15. Within-asset dependence — Milestone CB's CB-2 is closed

**MEASUREMENT.** `rho_w = −0.035450`, 95 % asset-clustered bootstrap
**[−0.077362, −0.006421]**, on 15 groups and 155 members. Across all fifteen
panels `rho_w` lies in **[−0.0355, +0.0322]**.

**INFERENCE.** The within-asset intracluster correlation of the paired difference
is **indistinguishable from zero, and slightly negative on the headline panel**.
Milestone CB's design effect `1 + (m − 1)ρ` at `m = 10.33` and `ρ = 0` is exactly
**1.00**: clustering by symbol costs essentially no information *within* an asset.

**FACT.** This addresses Milestone CB's limitation **CB-2** — "the intracluster
correlation is unmeasured; the observation-level data needed to estimate one is
not persisted in this repository". The data is now persisted and the parameter is
measured.

**Three qualifications independent review required, and they matter.**

1. **"Closed" is too strong; "bounded near zero" is right.** The interval
   excludes zero on the negative side, but simulation of this estimator and
   bootstrap at a *true* `rho_w` of zero produces a zero-excluding interval in
   about **15 %** of runs. The prose reading — indistinguishable from zero — is
   the defensible one; the bolded exclusion of zero is not a 5 % event.
2. **Retaining the 33 overlapping admissions biases `rho_w` downward.** Dropping
   them gives −0.0135; the overlapping subset alone gives +0.0447. The design
   effect is 1.00 at the reported value and 1.42 at the overlapping subset's, and
   fifteen groups cannot separate those. Keeping them is still right — dropping
   them would select on the timeline — but the direction of the bias is toward
   the value that flatters Milestone CB, and it was not stated.
3. **`rho_w` is recorded, not consumed.** `assess_requirement` calls
   `cb_required_clusters` at the default `intracluster_correlation = 0.0`. That
   is harmless — Milestone CB's `MORE_CLUSTERS_SAME_DENSITY` path gives the same
   requirement at *every* correlation, and a regression asserts that invariance —
   but CB-2 is closed by **publishing** a number, not by feeding one into an
   arithmetic that would move if it changed.

**INFERENCE — and this is the sting, and it survives all three.** CB left `ρ` open
and worried it might be large. It is not. **The information was never lost inside
a symbol; it is lost between symbols**, on the axis CB's
`MORE_CLUSTERS_SAME_DENSITY` path assumes is independent.

**INFERENCE — and this is the sting.** CB left `ρ` open and worried it might be
large. It is not. **The information was never lost inside a symbol; it is lost
between symbols**, on the axis CB's `MORE_CLUSTERS_SAME_DENSITY` path assumed was
independent.

---

## 16. Cross-asset dependence, secondary views

**MEASUREMENT.** Pairwise Pearson correlation over shared blocks, headline panel:

| | value |
|---|---|
| possible pairs | 105 |
| measurable pairs (≥ 4 shared blocks) | 15 |
| pairs below the floor | 90 |
| mean over measurable pairs | +0.0420 |
| median | +0.1515 |
| minimum / maximum | −0.8772 / +0.9817 |

**INFERENCE.** The pairwise mean (+0.042) is far below the ICC (+0.198) and the
two are **not** in conflict: they are different estimands over different coverage.
The ICC pools all 58 blocks and 148 cells; the pairwise view sees only the 15
densest pairs, each over 4–7 shared blocks, where a correlation ranges from −0.88
to +0.98. **A mean of fifteen numbers that wide is not a measurement**, and that is
exactly why the seal makes it secondary.

**FACT — and most of the gap is the floor, which the first version did not
show.** At the sealed floor of 4 shared blocks, 15 pairs survive with a mean of
+0.042. At a floor of **2**, 66 pairs survive and the mean is **+0.117** — most of
the discrepancy closes. The floor was sealed in advance so this is not a search,
but presenting the gap as intrinsic when one coverage knob nearly removes it was a
transparency failure. Found by independent review.

**LIMITATION.** Reviewer A offered a competing explanation the report cannot
exclude: the top 5 of 58 blocks contribute **53 %** of `SSB`, and that
concentration is exactly the shape that inflates a between-group variance ratio
while leaving pair-level correlations unmoved. A rank-based or variance-stabilised
check would separate the two explanations. **None was run**, so the ICC/pairwise
gap is explained but not tested.

**MEASUREMENT — Milestone CC's estimator on CD's own data.** Applied to the
headline panel it returns **−0.083366**, against `−1/(15−1) = −0.071429`. Across
the fifteen panels it returns **−0.3250 to +0.0045**.

**CORRECTION.** The first version of this report described that range as
"−0.0466 to −0.3250 — negative everywhere". **That was false, and this report's
own §13.2 table printed the counterexample**: `ca_null_matched_timing_random_direction`
on development returns **+0.0045**. The stated range was taken over 14 of 15
values with the inconvenient one dropped. Found by independent review; the
artifact-pinning test now asserts the true maximum so the claim cannot recur.

**INFERENCE, restated honestly.** CC's estimator is *pinned near the demeaning
artefact and is uninformative about the truth* — 14 of 15 values lie in
[−0.325, −0.047] and the fifteenth is +0.0045, while the data those same panels
contain runs +0.095 to +0.549. It is reported as a comparison and no verdict
consults it. It is **not** "negative everywhere".

---

## 17. Sensitivity — the whole sealed grid

**MEASUREMENT.** All sixteen cells, headline panel, **after** the weighted-ICC
defect independent review found was fixed (§25, D-5). Every cell reported; none
selected after the fact.

| block bars | reduction | weighting | `r_b` | informative blocks |
|---|---|---|---|---|
| 24 | cell_mean | equal | +0.51365 | 36 |
| 24 | cell_mean | observation | +0.51421 | 36 |
| 24 | cell_first | equal | +0.51310 | 36 |
| 24 | cell_first | observation | +0.51333 | 36 |
| **60** | **cell_mean** | **equal** | **+0.19844** | **38** |
| 60 | cell_mean | observation | +0.20624 | 38 |
| 60 | cell_first | equal | +0.18379 | 38 |
| 60 | cell_first | observation | +0.18234 | 38 |
| 120 | cell_mean | equal | +0.19763 | 30 |
| 120 | cell_mean | observation | +0.21192 | 30 |
| 120 | cell_first | equal | +0.17506 | 30 |
| 120 | cell_first | observation | +0.16806 | 30 |
| 180 | cell_mean | equal | +0.17398 | 24 |
| 180 | cell_mean | observation | +0.19800 | 24 |
| 180 | cell_first | equal | +0.12173 | 24 |
| 180 | cell_first | observation | +0.13117 | 24 |

**MEASUREMENT.** `r_b` is positive in all sixteen cells, from **+0.1217 to
+0.5142**.

**FACT — `rho_w` is not a column in this grid, and the renderer no longer prints
one.** It is computed on the economic-asset axis, which reads no block length, no
reduction and no weighting, so it takes **one** value across the entire grid.
Printing it sixteen times reads as robustness when nothing was varied.
Independent review flagged it; the sensitivity table now carries `r_b` only, with
`rho_w` stated once beside it.

### 17.1 The block-width narrative, corrected

**The first version of this report drew three inferences here and all three were
wrong.** They are replaced rather than deleted.

*Withdrawn:* "the 24-bar block gives +0.51, **two and a half times the
headline**". *Withdrawn:* "dependence falls monotonically as blocks widen …
physically coherent: co-movement is strongest at short horizons". *Withdrawn:*
"the sealed choice of 60 bars is the conservative half of the grid".

**MEASUREMENT — why.** `q` and `r_b` move in opposite directions with block
width, and it is their **product** that the design consumes:

| block bars | `r_b` | `q` | **`q · r_b`** |
|---|---|---|---|
| 24 | +0.5137 | 0.0876 | **+0.0450** |
| 60 | +0.1984 | 0.2184 | **+0.0434** |
| 120 | +0.1976 | 0.3530 | **+0.0698** |
| 180 | +0.1740 | 0.5521 | **+0.0961** |

**INFERENCE.** The 24-bar and 60-bar cells carry **the same dependence** to
within 4 % — the 2.5× ratio was definitional, not physical. The design-relevant
quantity **rises** with block width rather than falling. And the sealed 60-bar
cell is at the **low** end of the grid on that quantity, not the conservative
end: the 180-bar cell implies roughly **2.2×** more dependence.

**LIMITATION.** CD does not know which block length is right. `q · r_b` varying
by 2.2× across the grid is itself a statement that the block length is a
material modelling choice (CD-2) rather than a detail.

### 17.2 Cell reduction

**MEASUREMENT.** Cell-mean minus cell-first ranges **+0.00056 to +0.06684** across
the eight (block, weighting) pairs, rising monotonically with block width. The
first version quoted "+0.015 to +0.062"; both endpoints were wrong.

**FACT — sealed limitation CD-3 states its direction backwards.** CD-3 says the
cell-mean reduction "biases `r_b` **DOWNWARD**". The module's own expectation
formula, `market² / (market² + asset² + noise²/c)`, is strictly **increasing** in
the cell size `c` — averaging shrinks the idiosyncratic term in the denominator
and so *raises* `r_b`. The measured cell-mean values sit **above** cell-first at
every block length, exactly as the algebra requires. The first version reported
this as an empirical surprise ("CD-3's stated direction is not confirmed"); the
correct reading is that **CD-3 is stated backwards**, and it is inside the digest,
so it is disclosed as post-review limitation **CD-8's** sibling rather than
edited.

**FACT.** Winsorisation: **none**, pre-registered. No paired difference was
trimmed, clipped or winsorised at any stage.

## 18. Concentration and tails

**MEASUREMENT.** Headline panel, share of total absolute paired-difference
magnitude by economic asset:

| asset | share | observations |
|---|---|---|
| QTUM | 0.1129 | 13 |
| XRP | 0.1098 | 13 |
| TRX | 0.0981 | 11 |
| ETH | 0.0795 | 6 |
| ADA | 0.0751 | 10 |
| IOTA | 0.0743 | 14 |

**MEASUREMENT.** Largest single-asset share **0.1129**, top-three share **0.3208**,
against Milestone CA's own 0.40 bound for a single asset.

**The inference the first version drew from this does not follow, and is
withdrawn.** It read: "This estimate is **not** driven by one or two assets."
Share of *absolute magnitude* is close to uninformative about the stability of a
**variance ratio**, and `r_b` is a variance ratio. Independent review supplied the
diagnostic that can answer the question.

**MEASUREMENT — leave-one-out, headline panel:**

| sweep | `r_b` range | ratio |
|---|---|---|
| drop one **economic asset** (15 drops) | **+0.1414 … +0.3122** | **2.21×** |
| drop one **time block** (58 drops) | **+0.1434 … +0.2635** | **1.84×** |

**INFERENCE, restated.** The estimate is not the product of *one* asset — no
single drop takes it below +0.14 or above +0.32, and it stays positive under every
one of the 73 drops. But it is **materially less stable than the concentration
figures suggest**: removing TRX alone raises it by 57 %, and removing ETC lowers it
by 29 %. A fifteen-asset panel cannot pin this quantity, which is the same
conclusion the interval reaches by a different route.

**FACT.** `leave_one_out` is now computed for every panel, carried in the artifact
and printed by the renderer, so the concentration claim can never again rest on a
statistic that cannot test it. Recorded as post-review limitation **CD-16**.

---

## 19. Pseudoreplication audit

**FACT.** The five counts are reported as five separate numbers on adjacent lines,
always: **155 rows, 155 admissions, 15 economic assets, 15 provider symbols, 38
informative blocks**. On the pooled five-family view the row count is 775 for the
same 155 admissions, and no statistic anywhere uses it.

**FACT.** Hostile controls, each with a non-vacuity counterpart:

| control | result | non-vacuity |
|---|---|---|
| duplicating every row | `r_b` +0.19844 → **+0.19844**, bit-identical | the row count **does** double |
| duplicating every row (asset axis) | `rho_w` −0.0355 → +0.0175 | a copy *is* perfectly correlated; the shift is upward and small |
| duplication → economic assets | 15 → **15** | — |
| duplication → effective clusters | unchanged, asserted `approx` | — |
| one exposure split across two symbols | 6 → 7 apparent clusters | collapsing restores 6 exactly |
| wrapped/renamed identity | `WBTCUSDT`→BTC, `VENUSDT`→VET: 3 symbols → **2 exposures** | `BTCUSDT` alone could not detect a no-op, and that gap was found by mutation |

**FACT.** Overlapping horizons are counted (33 of 155, 21.3 %), not assumed away
and not dropped.

---

## 20. Negative controls

**MEASUREMENT.** Headline panel:

| control | observed | under control | expectation | verdict |
|---|---|---|---|---|
| shuffled time blocks | +0.19844 | **−0.13847** | collapses | **passed** |
| shuffled asset identity | −0.03545 | −0.00637 | collapses | **passed** |
| duplicated rows (between) | +0.19844 | +0.19844 | unchanged | **passed** |
| duplicated rows (within) | −0.03545 | +0.01750 | ~unchanged | passed |
| CC residual estimator | +0.19844 | −0.08337 | pinned at −1/(K−1) | **passed** |

**INFERENCE.** The block shuffle is the one that matters: permuting each asset's
values across its **own** blocks — preserving every asset's observation count,
every value and every bar — destroys `r_b` completely (+0.198 → −0.138). So `r_b`
is measuring **contemporaneity**, not panel shape, not asset identity and not row
count.

**FACT — non-vacuity, proven on synthetic panels where the truth is known.**
The block shuffle takes `strong_between` from >0.4 to <0.1; the identity shuffle
takes `within_asset_only` from >0.3 to <0.05; and CC's residual estimator returns
values spanning **less than 0.01** across true correlations from 0 to 0.78 while
CD's own estimator spans **more than 0.4** over the same panels.

---

## 21. No-lookahead

**FACT.** Every paired-effect observation is produced by Milestone CA's own
sealed loop under CA's own semantics; CD computes no outcome and derives no
structure. The causal properties are BZ's and CA's, inherited unchanged:
`ThesisObservation` is built from the same narrow fact boundary the production
policy reads, at the instant whose close produced it, and holds no bar, no future
timestamp and no outcome.

**FACT.** CD's own additions are causally inert by construction and this is
asserted rather than claimed. `outcome_permutation_stable` permutes every measured
difference and asserts the panel's shape — rows, assets, blocks, cells, bar
indices — is **identical**; a deliberately leaky shaper that reads one difference
is asserted to **fail** the same control, so the test is not vacuous.

**FACT.** Blocks are cut from bar zero of the capture, absolutely, so a bar lands
in the same block for every asset and every sample. Anchoring blocks at each
sample's first admission would have made the boundaries depend on which asset
happened to admit first.

**LIMITATION.** CD adds no *new* lookahead proof for the admission path itself,
because it computes no admission. Report 0037 §18 remains the authority for that,
and CD ran with `causal_proven=False` throughout — the criterion blocks unless a
human states it, and no CD verdict can promote anything regardless.

---

## 22. Holdout safety

**FACT.** Milestone CA already opened the holdout and published its results
(report 0037 §10). CD therefore measures it under the **same sealed design** as
development and validation rather than withholding it: withholding protects
nothing once the design is frozen, and it would leave the milestone's most
informative sample — 234 admissions over 21 assets — unused for a question
starved of assets.

**FACT.** What the seal forbids is the reverse, and it is structural: **no CD
threshold, block length, reduction, weighting, floor or verdict boundary was
chosen, revised or inspected after any sample was read.** The seal was pinned
before the capture completed; the capture completed before any estimate existed.

**CORRECTION — one CD choice *was* outcome-informed, and the first version's claim
of a clean seal was true only because that choice was not on the list.** The
sealed comment on `CD_PRIMARY_FAMILY` justifies `ca_null_matched_timing` as "the
only one whose interval excluded zero on any sample" — and per report 0037 §10
**that sample is the holdout**. The primary family was therefore selected partly
by reading a realised holdout result.

**Material impact: none, and it is checkable.** Every one of the five families'
*development* intervals straddles zero (§13.2), so every family yields
`INCONCLUSIVE` on the sealed headline. The choice could not have changed the
verdict. But the claim that no CD decision consulted a sample is wrong as stated,
and the finding is recorded as **CD-12** rather than argued away. Found by
independent review.

**FACT.** The primary sample is `development`, fixed in the seal, and
`_assemble` **refuses** rather than substituting whichever panel happens to exist
if the sealed primary is absent — a defect found by self-review (§25) where a
bare `StopIteration` would previously have escaped.

**LIMITATION.** The five validation panels are the ones whose intervals exclude
zero, and validation is *semi-contaminated* by construction (BY-3): same fifteen
symbols, later window. Its stronger dependence is therefore **not** independent
confirmation from a fresh universe.

---

## 23. Artifact and reproducibility

**FACT.** Two artifacts, layered, neither overwriting anything:

| file | bytes | digest |
|---|---|---|
| `reports/artifacts/0040_cd_source_capture.json.gz` | 13,354,747 | `07b500c7…` |
| `reports/artifacts/0040_cd_paired_dependence.json.gz` | — | `754dccd6…` |

**FACT.** Four digests, answering four different questions: `preregistration_digest`
(did the rules change?), `capture_content_digest` (did the data change?),
`ca_preregistration_digest` (was CA's seal the same?), `content_digest` (was this
file edited?). Two runs that disagree can be attributed rather than argued about.

**FACT.** The content digest is taken over **canonical JSON**, never over the
file, so gzip's header and the filename cannot reach it — asserted by writing the
same payload to two different filenames and comparing.

**FACT.** The reader **fails closed** on every failure mode, each by name and none
by recomputing the missing value: a foreign kind, a foreign schema version, any
missing section, any missing manifest field, an empty observation list, any
observation missing any of 21 provenance fields, invalid JSON, a JSON array, a
truncated gzip, a digest mismatch, a foreign seal, a foreign pre-registration id,
and a foreign source capture. Seal mismatch and digest mismatch are **separate**
failures with separate messages, because a file can be perfectly intact and still
describe a different experiment.

**FACT.** `write_dependence_study` **refuses to overwrite**. Milestone CC lost an
artifact that way and recorded the incident; CD makes it impossible.

### 23.1 What the digest is, and is not

**FACT.** `run_at` is `datetime.now()` on the capture path and enters the
manifest, which enters `content_digest`. The study digest is therefore a **tamper
check, not a reproducibility check**: no re-run can produce the same digest, and
`write_dependence_study` refuses to overwrite. Reproducibility is established by
the payload comparison in §23.2, not by the digest. Found by independent review.

### 23.2 Offline reproduction, proven by making the alternatives fatal

**FACT.** `fmits research dependence --from-study` re-derives **every** figure
from the persisted rows. Its output is **byte-identical** to the capture-driven
run apart from two fields that legitimately differ — `run at` and `source`
(`capture` vs `artifact`).

**FACT.** Proven with both alternatives made fatal: `fetch_raw_klines` **and**
`fmis.swing_lab.admission_study.study_from_capture` monkeypatched to raise, then
the artifact read, its digest verified, its seal required, its source capture
required, and the study fully reproduced — 2,390 rows, `r_b` +0.19843843513559317,
`rho_w` −0.03545009224991663, verdict `inconclusive`. A run that reached the
network or replayed the capture would have raised rather than passed.

**FACT.** `tests/test_paired_dependence_artifact_pinned.py` now reads **the
published files themselves** — digest, seal, source identity, all 2,390 rows, the
five counts, every headline figure and the post-review correction — so a
corrupted or swapped artifact is a test failure. Milestone CC pinned its capture
this way; CD did not until independent review pointed it out.

### 23.3 The capture invocation, recorded

**LIMITATION — CD-20.** `fmis.paired_dependence.capture` is written down and
tested, but it has **no CLI surface** and is called from no committed code, so the
*invocation* that produced `0040_cd_source_capture.json.gz` is still ad hoc. The
next milestone is in a materially better position than CD was — the runner exists
— but not the position §3.2 first claimed. The invocation is therefore recorded
here verbatim:

```python
from datetime import datetime, timezone
from fmis.paired_dependence.capture import capture_ca_sources
from fmis.swing_lab.persistence_artifact import write_persistence_capture

payload = capture_ca_sources(run_at=datetime.now(timezone.utc))
write_persistence_capture(payload, "reports/artifacts/0040_cd_source_capture.json.gz")
```

Universes default to `("primary", "holdout")`, the evaluation window and candle
limit to production's, and the transport to the repository's own. Wall clock:
4,815.6 s.

---

## 24. Milestone CB re-integration

**FACT.** No second power calculator was written. `K*` is obtained by **calling**
`fmis.research_design.resolution.required_information` through
`fmis.swing_lab.admission_power.ca_required_information` on the
`MORE_CLUSTERS_SAME_DENSITY` path, and reproduces CB exactly:

| quantity | value |
|---|---|
| required **independent** clusters `K*` | **467** |
| required admissions | **4,823** |
| observations per cluster | 10.3333 |
| saturation threshold `1/K*` | **0.002141** |

**FACT — the arithmetic CD adds.** CB's requirement is stated in *independent*
clusters. With between-cluster correlation `r`, `K` real clusters supply
`K/(1 + (K−1)r)` independent ones, so `K*` is bought at

    K = K* (1 - r) / (1 - K* r)     and only while r < 1 / K*

At or above `1/K*` the effective count saturates **below** the requirement and no
universe of any size satisfies it. This is CC's `effective_clusters` inverted, and
a regression checks the inversion against the closed form and at the boundary.

**MEASUREMENT — the requirement across CD's interval, headline panel:**

| bound | `r_b` | reachable | required clusters | required admissions |
|---|---|---|---|---|
| lower | −0.049065 | yes | 467 | 4,826 |
| **point** | **+0.198438** | **NO** | — | — |
| upper | +0.418073 | **NO** | — | — |

**MEASUREMENT — outcome `INCONCLUSIVE`**, by the sealed rule: the interval spans
from at or below zero to at or above `1/K*`. The same data supports "no dependence
penalty at all" and "unreachable at any universe size".

**MEASUREMENT — across all fifteen panels: 10 `INCONCLUSIVE`, 5 `UNREACHABLE`.**
The five are every family on validation. `RESOLVABLE` and `UNDERPOWERED` do not
occur anywhere.

### 24.1 The correction independent review forced

**FACT — the sealed formula consumes the wrong correlation.** `effective_clusters`
documents its argument as "the mean pairwise correlation of `K` **series**" — a
cluster-level quantity. `r_b` is the correlation between two **individual**
contemporaneous observations. Feeding one into the other implicitly assumes every
admission of asset A is contemporaneous with every admission of asset B.

**MEASUREMENT — arbitrated by simulation, not by argument.** A CA-shaped panel
(15 assets, 10 admissions each scattered over 74 blocks, true per-observation
`r_b` = 0.20), 4,000 replications of the grand mean:

| quantity | value |
|---|---|
| estimator's `r_b` (mean over 200 panels) | +0.1960 |
| contemporaneity fraction `q` | 0.1419 |
| **measured true design effect** | **1.4266** |
| the sealed formula `1 + (K−1) r_b` | **3.7446** — 2.62× too large |
| overlap-corrected `1 + (K−1) q r_b` | **1.3895** — within 3 % |

**MEASUREMENT — effective clusters, sealed and corrected, across all 15 panels:**

| universe | nominal assets | sealed `K_eff` | **corrected `K_eff`** |
|---|---|---|---|
| CC eligible | 38 | 1.78 – 8.41 | **8.03 – 23.12** |
| CC entire-history ceiling | 106 | 1.81 – 9.65 | **9.14 – 37.49** |
| requirement | — | **467** | **467** |

On the headline panel, `q = 0.1880` and `q · r_b = +0.0373`.

**INFERENCE — what survives and what does not.**

- **Survives:** every one of the fifteen corrected values is still above
  `1/K* = 0.002141`, by a factor of **8 to 47**. `UNREACHABLE` at the point
  estimates stands, and `INCONCLUSIVE` overall stands.
- **Withdrawn:** "adding 68 more assets buys about one extra effective cluster."
  Corrected, going from 38 to 106 assets buys between **1 and 14** effective
  clusters.
- **Withdrawn:** "a shortfall of roughly 50–250×". Corrected, it is **12–51×**.
- **Withdrawn:** "the curve has already saturated." It has not; it binds well
  before 467, which is a weaker and true statement.

**FACT.** The sealed path is unchanged and still produces the sealed numbers in
the artifact. `contemporaneity_fraction` and `overlap_corrected_correlation` are
**additive**, are carried in the artifact for every panel, are printed by the
renderer under an explicit "POST-REVIEW CORRECTION (not sealed)" heading, and are
recorded as **CD-8**. Milestone CA disclosed a sealed statistical defect the same
way in report 0037 §22 rather than reopening its own seal.

---

## 25. Defects found and fixed

**FACT.** Four found by self-review before the hostile review, and five more by
the reviewers. All nine are fixed with regressions.

**Found by self-review:**

- **D-1 — a bare `StopIteration` where the sealed primary panel was absent.**
  `_assemble` used `next(generator)` to find the headline. Fixed to an explicit
  refusal stating the headline is fixed by the seal and is **not** substituted
  with whichever panel happens to exist. A holdout-safety defect, not a tidiness
  one: silently substituting a panel is how a primary sample gets chosen after
  the fact.
- **D-2 — three vacuous tests**, all found by mutation (§27).
- **D-3 — an unused import** in `controls.py`.
- **D-4 — the renderer emitted the word "recommends"**, which its own guard
  caught. **The guard was obeyed, not widened.**

**Found by independent review:**

- **D-5 — the observation-weighted ICC was wrong, and no test could see it.** It
  divided a weighted sum of squares by *unweighted* degrees of freedom and
  omitted the `σ²_e` coefficient in `E[MSB]`, so multiplying every weight by a
  constant moved the estimate: ρ = 0.860 at weight 1.0, 0.381 at weight 10.0. A
  correlation must be invariant to a change of units. **Fixed** to the exact
  weighted ANOVA, now scale-invariant to 1e-12 and reducing to the unweighted
  form exactly, including on unbalanced panels. Eight of the sixteen sensitivity
  cells moved; the headline is `EQUAL_CELL` and did not. The only weighted test
  used weights of exactly 1.0 — the single case that cannot detect it.
  **The fix also repaired a real pseudoreplication hole**: before it, duplicating
  every row moved the observation-weighted estimate by −48 %; now it does not.
- **D-6 — the "executable tier-closure" guards were circular.** §26 of the first
  version claimed CD had replaced Milestone CC's justifying *comment* with
  executable checks, "so widening the allowlist without widening the guarantee is
  a test failure". It was the opposite: the exemption set was **derived from the
  allowlist**, so adding a package simultaneously removed it from the guarantee;
  and the companion check asserted only that `test_<package>_architecture.py`
  *existed*, which an empty file satisfies. A reviewer demonstrated both by
  admitting a fake `shadow` package that imported the laboratory, using a
  two-line edit and a one-line placeholder. **Fixed**: `_RESEARCH_TIER` is now
  hard-coded and cross-checked against the allowlist, and a guard file must
  contain a named boundary test, name its own package, walk the source tree and
  hold at least ten assertions. **Both halves of the attack were re-run against
  the fix and both are now caught.**
- **D-7 — the observer hook was inert by convention, not by construction.**
  `PairedRecord` is frozen, but its horizon maps are plain dicts behind a
  `Mapping` annotation. A reviewer showed that
  `record.control_forward[24] = 99.0` changes `record.difference(24)` from +1.0 to
  −97.5 — and `collected` holds the same objects, so an observer that touched one
  would have moved **Milestone CA's published effect**. **Fixed**: the hook now
  hands out `MappingProxyType` copies. The regression asserts the copy refuses
  writes *and* that the raw record would have allowed them.
- **D-8 — reproduction depended on JSON array order.** `group_by_asset` preserves
  input order, so a reordered artifact moved `rho_w` at the last bit and with it
  the asset-axis bootstrap bounds — three distinct values across six shuffles.
  **Fixed**: `study_from_rows` sorts by `observation_id`.
- **D-9 — no committed test read CD's own artifacts.** Milestone CC pins its
  capture; CD did not, which made CD weaker than CC on the exact axis CD exists
  to fix. **Fixed**: `tests/test_paired_dependence_artifact_pinned.py` reads both
  published files, verifies digest, seal and source identity, and pins every
  headline figure §1 quotes — including the corrected `q · r_b`.

- **D-10 — the architecture guards enforced no invariant.** Two of four derived
  their exemption set from the allowlist they were checking. **Fixed** by finding
  and stating the invariant once, as a filesystem partition (§26).

**FACT.** Of these, only **D-5** moved a published number, and only the eight
observation-weighted sensitivity cells. No headline figure and no verdict changed.

### 25.2 Implementation repair versus methodological change

**The closure brief asks these to be kept apart, and they are.** The test is
simple: *would the seal, executed faithfully, have produced this?*

**Category A — implementation repair required to execute the seal faithfully.**
The code did not do what the seal specifies, so fixing it makes the sealed
estimator actually run.

- **D-5, the weighted ICC.** The seal specifies the ANOVA method of moments and
  declares `WEIGHTINGS` as a **sensitivity over the same estimator**. An estimator
  whose value changes when every weight is multiplied by a constant is not the
  same estimator — it is not an estimator of a correlation at all, since a
  correlation is dimensionless. The repair makes the weighted path (i) exactly
  scale-invariant and (ii) exactly equal to the sealed unweighted formula at unit
  weights. **The sealed unweighted path was never touched and never moved.** A
  regression reconstructs the *old* implementation and asserts it **fails** the
  invariance property, so the repair is provably not cosmetic.
- **D-7, the observer copies.** The seal says CD reads CA's records; it does not
  say CD may be able to alter them.
- **D-8, row-order canonicalisation.** The seal's estimator is a function of the
  observations, not of their order in a file.

**Category B — methodological correction that would change the sealed estimand.**
**None was made.** Every finding in this class is **disclosed** and its behaviour
**pinned**, never applied:

- **CD-8**, the effective-cluster correlation. The corrected `q · r_b` is computed
  and reported *beside* the sealed figure, in the artifact and in the renderer,
  under an explicit "POST-REVIEW CORRECTION (not sealed)" heading. The sealed path
  still produces the sealed number.
- **CD-9**, the straddle rule's wording.
- **CD-3**, the cell-mean bias direction.
- **CD-12**, the primary family's justification.
- **CD-13/14**, what the calibration gate certifies.

**FACT.** Changing any Category B item would have been a post-hoc edit to a
pre-registration after seeing results, which is the single thing the seal exists
to prevent. Milestone CA disclosed a sealed statistical defect the same way in
report 0037 §22 rather than reopening its own seal.

### 25.1 Findings disclosed rather than fixed

**FACT.** Five confirmed findings sit **inside the digest**. Changing a sealed
rule after seeing results is what a pre-registration exists to prevent, so each is
disclosed and its current behaviour is **pinned by a test** so it cannot drift.
Milestone CA did the same in report 0037 §22.

| finding | what is wrong | direction | fired? |
|---|---|---|---|
| **CD-8** | the sealed secondary estimator feeds `r_b` into a formula wanting a cluster-level correlation | overstates dependence ~3× | yes, corrected beside it |
| **CD-9** | the straddle rule tests `lower ≤ 0` when it should test `lower < 1/K*` | reports a definite `UNREACHABLE` where the honest answer is `INCONCLUSIVE` | **no** |
| **CD-3** | states the cell-mean bias direction backwards | none measured | n/a |
| **CD-12** | the primary family's justification cites a holdout result | none — every family gives the same verdict | n/a |
| **CD-13/14** | the calibration tolerance is 33× the decision threshold, and its "decisive" row is an algebraic identity | overstates what calibration certified | n/a |

## 26. Repository conventions CD violated and repaired

**FACT.** The first full-suite run failed **13 tests**, and every one was a
genuine violation by CD of a repository-wide invariant. None was a flake and none
was worked around.

- **Export-name collisions (10 failures).** `encode_study`, `write_study` and
  `coverage_of` collided with `fmis.swing_lab` and `fmis.universe`. The repository
  maintains a **zero public-name collision** invariant across every package.
  **CD renamed its own exports** — `encode_dependence_study`,
  `write_dependence_study`, `read_dependence_study`, `dependence_study_digest`,
  `verify_dependence_study_digest`, `dependence_rows_of`,
  `dependence_coverage_of`, `dependence_concentration_of`,
  `dependence_overlap_of` — and the invariant now holds with **zero** collisions
  repository-wide. (This rename is what forced the seal re-pin; see §4.1.)
- **Three import-reachability allowlists.** `fmis.swing_lab`, `fmis.universe`
  and `fmis.research_design` each guard that no *engine* imports them.
  `fmis.paired_dependence` is a research package at the same tier, importing them
  for exactly the reason those packages exist — to reuse CA's sealed constants,
  BY's windows, CC's identity rules and CB's arithmetic rather than retyping any
  of them. Milestone CC widened the same lists for the same reason.
- **The CLI's permitted-prefix list**, on the identical footing as
  `fmis.universe` before it.

**CORRECTION — the first version claimed these widenings were "strengthened, not
weakened", and for two of the four guards that claim was false.** Independent
review defeated them by admitting a fake package into the laboratory with a
two-line allowlist edit and an empty placeholder guard file.

### 26.1 The invariant, found and stated once

**FACT — the guards were not merely buggy; they were four restatements of one
invariant, two of which derived their own exemption set from the allowlist they
were checking.** A set that a test both consults and is checked against cannot
constrain anything. Patching the demonstrated example would have left the shape
intact.

**The invariant, written down once in `tests/architecture_tiers.py`:**

> Every package under `src/fmis` is either PRODUCTION or RESEARCH. Production may
> not import research. Research may import research. The only module outside the
> research tier permitted to import into it is the CLI, which is a research
> *surface*.

**FACT — what makes it non-circular is that it is a partition.** The two sets are
hard-coded, their intersection is asserted empty, and **their union is asserted to
equal the packages that actually exist on disk**. A new package is therefore not
admitted by silence:

* left unclassified → `assert_tier_partition_is_complete` fails;
* classified PRODUCTION → it may not import research, and the boundary guards fire;
* classified RESEARCH → it must carry a guard that really guards — a named
  boundary test, naming its own package, walking the source tree, and holding at
  least ten assertions.

The cheapest bypass is no longer an allowlist edit. It is a deliberate,
reviewable reclassification with a test obligation attached — which is what the
guard was always supposed to require.

**MEASUREMENT — the invariant, checked against the repository as it is:**

| research package | modules outside the tier importing it |
|---|---|
| `swing_lab` | `pipeline/cli.py` |
| `research_design` | `pipeline/cli.py` |
| `universe` | `pipeline/cli.py` |
| `paired_dependence` | `pipeline/cli.py` |

**56 packages on disk; 4 research, 52 production; union complete, intersection
empty.**

### 26.2 The bypass, reproduced and rejected

**FACT.** `tests/test_architecture_tiers.py` reproduces the reviewer's attack step
by step on synthetic trees under `tmp_path`, and asserts each step now fails:

| attack step | result |
|---|---|
| a new package nobody classified | **caught by the partition** (`in neither`) |
| classifying it PRODUCTION and importing research | **caught by the boundary guard** |
| an empty placeholder guard file | **rejected** (`guards nothing`) |
| a placeholder naming a boundary test but scanning nothing | **rejected** (`never scans the source tree`) |
| a placeholder that scans but barely asserts | **rejected** (`is not a guard`) |

**FACT — non-vacuity, proven live against the real tree.** Four unauthorized
dependencies were introduced into `src/` one at a time, the guards were run, and
every file was restored byte-identically with SHA-256 verification and
`__pycache__` cleared on both sides:

| probe | guards that fired |
|---|---|
| `today/builder.py` importing `fmis.paired_dependence` | 5 of 5 |
| `operator_dashboard/models.py` importing `fmis.universe` | 4 of 5 |
| `portfolio_risk/__init__.py` importing `fmis.swing_lab` | 4 of 5 |
| `paper/__init__.py` importing `fmis.research_design` | 5 of 5 |

**FACT — the two guards that always worked.** Independent review confirmed by
mutation that `test_no_production_module_imports_this_package` and
`test_the_research_package_allowed_above_is_itself_unreachable` fire on every
offending import. **The production boundary was never actually open.** What was
open was the *claim* that the two new guards protected it.

**FACT — no allowlist was widened to make a test pass.** The four package-specific
allowlists still enumerate exactly the modules that import each package, and the
partition is a new, stricter constraint layered over them.

---

## 27. Mutation testing — 43 probes, 43 killed, every survivor investigated

**FACT.** A rule-level harness replaces one scientifically material expression
with a plausible alternative and asserts at least one CD test fails. Every probed
file is restored **byte-identically** (SHA-256 verified) and every `__pycache__`
is cleared on **both** sides of every probe — Milestone BM's stale-bytecode
incident, avoided by construction.

**First pass: 34 probes, 25 killed, 8 survivors, 1 skipped on a bad anchor.**

**FACT.** Every survivor was investigated and closed with a regression. None was
rationalised as equivalent.

| survivor | why it survived | regression |
|---|---|---|
| drop the shared-block floor | test pair shared **zero** blocks; `pearson` refused it first | pair sharing 3 blocks vs a floor of 4, plus the non-vacuity half at 4 |
| one-sided tail | comparing 50 % vs 99 % widths survives — the *ordering* is unchanged | at 50 % confidence the width must be **positive**; a one-sided tail collapses both bounds onto the median |
| merge a twice-drawn cluster | nothing observed the resampled group count | two assets, one per block: relabelled copies keep every draw defined, merged ones make every draw undefined |
| bootstrap a single bucket | test reached the message via the **point estimate** being undefined | point defined on the asset axis, resampling axis degenerate |
| minority of draws | genuinely hard to reach: a single unlucky-bucket construction caps at `1/e ≈ 37 %` | **fault injection, labelled as such**, plus a non-vacuity test that the same panel without the fault yields an interval |
| ordering allows ties | no test made two scenario means equal | an estimator **pinned at one value — CC's exact failure mode** — must fail the ordering gate |
| calibration tolerance always passes | no test missed an expectation | a constant 0.9 must record failures |
| skip the economic identity collapse | `BTCUSDT` base == identity, so the call was indistinguishable from a no-op | `WBTCUSDT → BTC`, `VENUSDT → VET` |
| *(skipped)* perturb the ICC ratio | anchor text wrong | re-anchored |

**Re-probe: 9 probes, 9 killed, 0 survivors.**

**FACT — first campaign: 34 probes, 34 killed, 0 survivors, 0 unexplained.**

### 27.1 Second campaign, after the review fixes

**FACT.** Nine further probes were written against the code the review changed —
the weighted `E[MSB]` coefficient, the weighted within divisor, the
contemporaneity fraction, the shared-block counter, the overlap correction, the
leave-one-out axis and sweep, the row-order canonicalisation, and the duplication
control's weighting.

**First pass: 9 probes, 8 killed, 1 survivor.** The survivor —
*duplication control ignores the weighting* — survived for an instructive reason:
**after** the D-5 fix the estimator is scale-invariant, so on any panel whose
cells are all the same size the weighted and unweighted arms agree exactly, and
every existing fixture had uniform cells. A regression on a panel with **unequal**
cell sizes — the only shape where the two arms differ — closes it.

**Re-probe: 9 probes, 9 killed, 0 survivors.**

**FACT — across both campaigns: 43 probes, 43 killed, 0 survivors, 0 unexplained.**

### 27.2 Final re-run of the whole campaign against the post-review code

**FACT.** All 43 probes were re-run in one campaign against the final tree, after
every reviewer fix: **43 probes, 43 killed, 0 survivors, 0 skipped.** Every probed
file was restored byte-identically under SHA-256 verification, with every
`__pycache__` cleared on both sides of every probe — Milestone BM's stale-bytecode
incident, avoided by construction.

**FACT — a mutation is counted killed only when the intended invariant is what
failed.** Each probe names the rule it attacks, and the survivors of the first
pass were closed by regressions that assert the *rule*, not the arithmetic —
which is why three of them turned out to be vacuous tests rather than missing
ones.

### 27.3 An operational hazard the campaign itself exposed

**FACT, and it nearly produced a wrong published number.** The mutation harness
mutates source files **in place**. An offline-reproduction check was run
concurrently with a live campaign, imported a temporarily mutated
`uncertainty.py`, and reported a bootstrap interval collapsed to zero width
(`[+0.198438, +0.198438]`) and a verdict of `weakly_identified / unreachable`
instead of `inconclusive / inconclusive`.

**The cause was identified and is not a code defect.** The live probe was
*resample without replacement* (`drawn = list(keys)`), which makes every resample
equal to the original panel and collapses the interval onto the point estimate —
exactly the observed signature. Re-run against the restored tree, the reproduction
is **field-identical** to the published artifact.

**The rule this establishes**, recorded in the same spirit as Milestone BM's
`__pycache__` incident: **no analysis, reproduction check or figure-producing run
may execute while an in-place mutation harness is live.** The first output was not
trusted, was diagnosed, and is reported here rather than quietly re-run.



---

## 28. Milestone CC re-evaluated — its verdict preserved

**FACT.** Milestone CC's `INFEASIBLE` on binding constraint `cluster_count`
**stands unaltered**. What follows is recorded beside it, and every figure below
is the **overlap-corrected** one (§24.1), not the sealed one the first version of
this report used.

1. **Is CC's 106-cluster ceiling still below the required information?**
   **Yes.** In *nominal* terms CC reported a 4.4× shortfall (106 against 467). In
   **effective** terms, at the corrected dependence, 106 assets supply
   **9.1 – 37.5** effective clusters — a shortfall of **12 – 51×**.
   *(The first version said 50–250×, using the uncorrected arithmetic.)*

2. **Is 467 still a useful order-of-magnitude target?** **As a count of
   *independent* clusters, yes** — Milestone CB's arithmetic reproduces exactly.
   **As a count of assets to acquire, no**: at `q · r_b` above `1/467` no number of
   assets delivers 467 independent ones.

3. **Does positive dependence increase the requirement?** **Yes, and past
   `1/K* = 0.002141` it removes the requirement's finiteness.** All fifteen
   corrected point estimates (`q · r_b` from **+0.0174 to +0.1009**) are above that
   threshold, by a factor of 8 to 47.

4. **Does uncertainty make the target unidentifiable?** **Yes on the sealed
   headline** — the interval spans both worlds. **No on validation**, where all
   five families put the lower bound above the threshold. But validation is
   semi-contaminated by construction and its window is *contained by* the
   holdout's (CD-18), so it is corroboration, not confirmation.

5. **Would reducing warm-up materially help?** **No, on this evidence.** A shorter
   warm-up raises the number of assets clearing the depth requirement, which moves
   the **ceiling**, not the **requirement**. Where the correlation is above
   saturation the requirement is unreachable at any universe size.
   **CORRECTION:** the first version said going from 38 to 106 assets "buys about
   one extra effective cluster". Corrected, it buys between **1 and 14**. The
   conclusion is unchanged — 106 assets still supply at most ~37 effective
   clusters against 467 — but the margin is not as brutal as the first version
   claimed.

6. **Is a warm-up sensitivity milestone scientifically justified after CD?**
   **Not as the next milestone.** `warm_up_sensitivity_is_justified` computes
   `False` because the outcome is not `UNDERPOWERED`. CC recommended warm-up
   sensitivity as the next step; **CD removes that recommendation's premise**, and
   the correction in §24.1 does not restore it.

**LIMITATION — CD-11, and it runs against CD's own finding.** Every one of the 36
symbols resolves to a **single** bar-zero timestamp per universe, so the panel
contains no instrument that listed or delisted mid-window. Listings and
delistings are exactly the events that decorrelate a crypto panel, so a
survivor-only panel is close to the most co-moving panel obtainable and **`r_b` is
biased upward**. CC's 38-asset eligible universe, which is not survivor-filtered
in the same way, might not share it. Found by independent review; the word
"survivorship" did not appear anywhere in the first version of this report.

## 29. Scientific verdict

**`INCONCLUSIVE`**, by the sealed rules, read in the sealed order:

1. **Calibration passed** — the estimator recovers every point expectation within
   its declared tolerance and reproduces the known ordering strictly, so its real
   output may be read at all. (`INVALID_ESTIMATOR` not reached.) §12 records what
   that gate does and does **not** certify.
2. **Every sample floor is met** — 15 economic assets (floor 3), 38 informative
   blocks (floor 10), 58 between-asset groups (floor 10), 148 members (floor 30),
   15 within-asset groups, 155 within-asset members.
3. **The interval spans the saturation threshold** — [−0.0491, +0.4181] against
   `1/K* = 0.002141`. → **`INCONCLUSIVE`**.

**FACT.** `DependenceVerdict.INCONCLUSIVE.is_approved_for_trading` is `False`,
`earns_forward_test` is `False`, `says_nothing_about_the_hypothesis` is `True` —
as for every member of both new enums, asserted over the whole enums.

### 29.1 What survives independent review

Each of these was recomputed from the artifact by at least one reviewer, or
re-derived by me from source, and none was disturbed by any correction.

| claim | status |
|---|---|
| `r_b` = **+0.198438**, 95 % block bootstrap **[−0.049065, +0.418073]** | **SURVIVES** — three reviewers reproduced it exactly |
| `rho_w` = **−0.035450**, **[−0.077362, −0.006421]** | **SURVIVES** as a point estimate; its *interpretation* is weakened (§29.2) |
| `r_b` positive in **all 15 panels** and **all 16 grid cells** | **SURVIVES** |
| the verdict `INCONCLUSIVE`, and design outcome `INCONCLUSIVE` | **SURVIVES** — unchanged by every correction |
| 10 `INCONCLUSIVE` / 5 `UNREACHABLE` across the panels | **SURVIVES** |
| exact reproduction of Milestone CA: 246/234 candidates, 155/91/234 matched, and effects **−0.2028 / −0.3347 / −0.5337** to four decimals | **SURVIVES, and was strengthened** — the first version claimed only the counts |
| the estimator recovers a known ordering (0.0007 < 0.0573 < 0.2016 < 0.4897) | **SURVIVES** |
| Milestone CC's residual estimator is uninformative about the truth | **SURVIVES** — though not "negative everywhere" (§16) |
| the block shuffle destroys `r_b` (+0.198 → −0.138), so it measures contemporaneity | **SURVIVES** |
| the corrected dependence still exceeds `1/K*` in **all 15 panels** | **SURVIVES** |
| Milestone CB's requirement reproduces exactly: 467 clusters / 4,823 admissions | **SURVIVES** |
| **the qualitative conclusion: information does not accumulate across assets as CB's growth path assumes** | **SURVIVES every correction** |

### 29.2 What no longer survives review

**These are withdrawn. They are listed rather than deleted, because a wrong
mechanism drove a wrong recommendation and a reader is entitled to see that.**

| withdrawn claim | why | replaced by |
|---|---|---|
| "controls sit 90–360 days away, so the pairing is not contemporaneous" | the radius is a **ceiling**; 1,387/1,430 rows sit at 10–90 days; 960/2,390 rows have a **same-bar** control | the control-variance collapse (§13.3) |
| effective clusters of **1.78–8.41** at 38 assets | the sealed formula consumes a cluster-level correlation and was given an observation-level one | **8.03–23.12** (§24.1) |
| "a shortfall of roughly 50–250×" | same | **12–51×** |
| "adding 68 assets buys about one effective cluster" | same | **1 to 14** |
| "the curve has already saturated" | same | it binds well before 467 — weaker, and true |
| "the 24-bar block gives 2.5× the headline dependence" | `q · r_b` is the same to within 4 %; the ratio was definitional | §17.1 |
| "dependence falls monotonically as blocks widen" | the design-relevant quantity **rises** | §17.1 |
| "the sealed 60-bar choice is the conservative half of the grid" | it is at the **low** end on `q · r_b` | §17.1 |
| "CB-2 is closed … the design effect is exactly 1.00" | overlap retention biases `rho_w` down 0.022; a zero-excluding interval is a ~15 % event at a true zero; and `rho_w` is *recorded*, not consumed | "bounded near zero" (§15) |
| "CD cannot separate small-sample from regime on validation" | 29 development sub-windows at validation's n: median +0.138, max +0.308, **0/29** reach +0.478 | small-sample **refuted** (§13.2) |
| the CC residual control is "negative everywhere" | one panel is **+0.0045**, printed in this report's own table | §16 |
| "three years and one provider generation" | **seven days** between report 0037 and CD's capture | §8 |
| "the provenance gap is closed" | the capture *invocation* is still ad hoc | "narrowed"; invocation recorded (§23.3, CD-20) |
| "`market_factor_removed` is the decisive row … CC's failure reproduced exactly" | it is an algebraic identity: `SSB ≡ 0` after demeaning | the **ordering** row is the evidence (§12) |
| "the tier-closure guards make widening the allowlist a test failure" | they were **circular**; a reviewer bypassed them | a filesystem **partition** (§26) |
| "a same-instant control would difference out the factor" | two sealed families already do exactly that and are no better | §34.2 |
| "the estimate is not driven by one or two assets" | dropping one asset moves `r_b` by 2.2× | §18 |
| "no CD decision was chosen after reading a sample" | the primary family's justification cites a **holdout** result | §22, CD-12 |

### 29.3 The final verdict, question by question

**A. Is temporal/block dependence in the observed CA admission outcomes real?**
**Yes, with high confidence in the *sign* and low confidence in the *magnitude*.**
It is positive in 15/15 panels and 16/16 grid cells; the control that destroys
contemporaneity destroys the estimate (+0.198 → −0.138); and the estimator
recovers a known ordering on synthetic panels. But the headline interval contains
zero, one asset moves it 2.2×, and the panel is survivor-only, which biases it
upward. **Scenario language is the honest form**: on this evidence the true
per-observation contemporaneous correlation is very likely positive and plausibly
anywhere in roughly [0.02, 0.42].

**B. Is the measured dependence attributable to the paired-control design
itself?** **No — and this is the correction that matters most.** It is inherited
almost entirely from the raw admission outcome. `control_forward` averages 200
draws and retains 2.8 % of the admission leg's variance, so
`corr(D, admission) = +0.987`; for `ca_null_opposite_direction`, `D` is exactly
`2 × admission` and its `r_b` **is** the raw-outcome `r_b`. **CD did not measure
the dependence of a market-neutralised paired effect.** The pairing removes the
symbol, period and drift differences it was designed to remove; it does not remove
the contemporaneous market component, and the reason is variance collapse, not
calendar distance.

**C. Does the sealed CD estimator overstate or understate the relevant design
effect?** **It overstates it, by roughly 3×**, and the direction is confirmed by
simulation (measured design effect 1.4266; sealed formula 3.7446; overlap-corrected
1.3895). The sealed figure is preserved; the corrected diagnostic is reported
beside it. Two smaller biases run the other way and are stated: cell-mean
reduction raises `r_b` slightly, and the survivor-only panel raises it as well.

**D. Does the corrected diagnostic still threaten CB's required effective sample
size / cluster assumptions?** **Yes — materially, and the threat is not marginal.**
Every one of the fifteen corrected values (`q · r_b` from +0.0174 to +0.1009)
exceeds `1/K* = 0.002141` by a factor of **8 to 47**. CC's 38 eligible assets
supply **8–23** effective clusters and its entire-history ceiling of 106 supplies
**9–37**, against **467** — a **12–51×** shortfall. CB's
`MORE_CLUSTERS_SAME_DENSITY` path assumes independent clusters, and on this
evidence they are not. **What CD cannot say** is where in that range the truth
sits, or whether a non-survivor universe would behave the same way.

**E. Which conclusions are robust enough to carry forward?**
1. The observation-level dataset and the BZ capture exist, are digest-verified and
   reproduce Milestone CA's published effects to four decimals.
2. `rho_w` is bounded near zero: within-asset clustering costs essentially no
   information.
3. Between-asset contemporaneous dependence is **positive** and large enough that
   CB's independent-cluster assumption cannot be relied on.
4. The paired difference is **not** market-neutral, and the cause is the control
   leg's variance, not its timing.
5. Warm-up reduction moves the ceiling, not the requirement.

**F. Which conclusions must NOT be used downstream?**
1. **Any specific effective-cluster number.** The sealed ones are ~3× overstated;
   the corrected ones rest on a 15-asset survivor-only panel. Use the *range* and
   the *direction*, never a point.
2. **`r_b` as a calibrated quantity.** It is not resolved to the precision the
   `1/K*` decision needs, and it must never be fed into a live decision path —
   `CELL_MEAN` and the block grid are full-sample constructions.
3. **The five `UNREACHABLE` validation panels as independent confirmation.**
   Validation is semi-contaminated and its window is contained by the holdout's.
4. **The `rho_w` interval's exclusion of zero** as a significance claim.
5. **Any statement that CD measured a market-neutral paired effect.** It did not.
6. **Any trading, sizing, promotion or forward-test decision.** Both verdict enums
   refuse it for every member.

## 30. Independent hostile review — **performed, and it changed the science**

**FACT.** Three narrow reviewers attacked the milestone in parallel, on the three
dimensions the brief names. **Reviewers modified nothing**; `HEAD` was `f47cd05`
before and after. Thirty findings were returned. **Every finding was reproduced
independently before it was accepted** — none was taken on the reviewer's word,
and two were re-derived by simulation rather than by argument.

**The review was worth more than the suite.** 555 passing tests, 34 killed
mutants and a self-review pass did not find either critical error. Both were found
by reviewers, and both were in the report's *conclusions* rather than in its
arithmetic — which is exactly where a test suite cannot look.

### 30.1 The two critical findings

**A-S1 — the effective-cluster arithmetic was overstated ~3×.** Reviewer A
established that `r_b` is an observation-level correlation while
`K/(1+(K−1)r)` consumes a cluster-level one, and quantified the gap by Monte
Carlo. **I arbitrated it by an independent simulation** (§24.1): measured design
effect 1.4266, sealed formula 3.7446, corrected formula 1.3895. **CONFIRMED.**
Disclosed as CD-8, corrected computably beside the sealed value.

**B-F1 — the mechanism was wrong.** Reviewer B established that the matching
radius is a ceiling not a floor, that two families use same-bar controls, and
that the paired difference is arithmetically close to the raw admission outcome.
**I reproduced all three from source and from the artifact** (§13.3):
1,387/1,430 rows at tier 0; 960 rows with `radius_tier: None`;
`corr(D, admission) = +0.9868`; `D ≡ 2 × admission` to 6e-14 for the
opposite-direction family. **CONFIRMED.** Disclosed as CD-10; §1, §13.3, §28 and
§34 rewritten.

**C-H2 — a guard weakening claimed as a strengthening.** Reviewer C demonstrated
that CD's two new tier-closure guards were circular and could be defeated by a
two-line edit plus an empty file. **I reproduced the attack, fixed the guards, and
re-ran the attack against the fix — it now fails.** **CONFIRMED.** Fixed (D-6).

### 30.2 Every finding and its disposition

| # | reviewer | finding | verdict | disposition |
|---|---|---|---|---|
| A-S1 | statistics | `r_b` is not the correlation `effective_clusters` consumes; figures 3–4× overstated | **CONFIRMED by simulation** | disclosed CD-8; correction computed, persisted, rendered |
| A-S2 | statistics | §17's block-width narrative inverted — `q·r_b` **rises** with block width | **CONFIRMED** | §17.1 rewritten; three inferences withdrawn |
| A-S3 / C-H1 | statistics / engineering | weighted ICC not scale-invariant | **CONFIRMED** | **fixed** (D-5) + scale-invariance regression |
| A-S4 | statistics | headline fragile to single assets; §18's statistic cannot detect it | **CONFIRMED** | `leave_one_out` added; §18 inference withdrawn; CD-16 |
| A-S5 | statistics | bootstrap coverage 0.83–0.88 under heterogeneous loadings / AR(1); `rho_w` excludes zero ~15 % of the time at truth 0 | **CONFIRMED** | disclosed CD-17; §15 qualification 1 |
| A-S6 | statistics | calibration tolerance 33× the decision threshold; its derivation is a non sequitur | **CONFIRMED** | disclosed CD-13 |
| A-S6b | statistics | `market_factor_removed` is an algebraic identity (SSB ≡ 0), not a measurement | **CONFIRMED** | disclosed CD-14; §12's "decisive row" claim withdrawn |
| A-S7 | statistics | sealed straddle rule tests `lower ≤ 0`, not `lower < 1/K*` | **CONFIRMED** | disclosed CD-9, **not fixed** (sealed); behaviour pinned |
| A-S8 | statistics | CD-3 states its bias direction backwards | **CONFIRMED** | §17.2; sealed, disclosed |
| A-S9 | statistics | *hypothesis that the `within_asset_only` bias is amplified on a sparse panel* | **REFUTED by the reviewer's own simulation** | none — reported as a negative finding |
| A-S10 | statistics | pairwise-vs-ICC gap explained but untested | **PLAUSIBLE** | §16 softened |
| B-F1 | bias | the mechanism claim is wrong three ways | **CONFIRMED** | §13.3 rewritten; CD-10 |
| B-F2 | bias | "15 of 15 panels" ≈ 2 independent measurements; holdout window contains validation's | **CONFIRMED** | disclosed CD-18; §13.2 |
| B-F3 | bias | the validation anomaly is not small-sample, and CD had the test | **CONFIRMED** (29 sub-windows, 0 reach +0.478) | §13.2 rewritten; CD-19 |
| B-F4 | bias | survivor-only panel biases `r_b` **upward**; survivorship never mentioned | **CONFIRMED** (1 bar-zero timestamp per universe) | disclosed CD-11 |
| B-F5 | bias | the primary family's justification cites a realised holdout result | **CONFIRMED** | disclosed CD-12; §22 corrected |
| B-F6 | bias | overlap retention biases `rho_w` down 0.022 — the direction flattering CB | **CONFIRMED** | §15 qualification 2 |
| B-F7 | bias | audit of outcome-conditioned exclusion | **CLEAN — no finding** | none |
| B-F8 | bias | the §16 pairwise gap largely closes at a floor of 2 (+0.117) | **CONFIRMED** | §16 |
| B-F9 | bias | the reproduction claim is over-stated temporally and **under-stated** in value | **CONFIRMED both ways** | §8 corrected in both directions |
| B-F10 | bias | lookahead and block anchoring | **CLEAN — attack failed** | none |
| B-F11 | bias | THETA and TFUEL are mechanically linked and both in the holdout | **CONFIRMED, immaterial** (holdout `r_b` +0.1262 → +0.1202) | noted |
| C-H2 | engineering | tier-closure guards circular; placeholder guard file accepted | **CONFIRMED by attack** | **fixed** (D-6); attack re-run and now caught |
| C-H3 | engineering | "negative everywhere" false — one panel is **+0.0045**, printed in CD's own table | **CONFIRMED** | §16 corrected; pinned by test |
| C-M1 | engineering | "three years and one provider generation" is **seven days** | **CONFIRMED** | §8 corrected |
| C-M2 | engineering | observer could mutate CA's records | **CONFIRMED** | **fixed** (D-7) |
| C-M3 | engineering | two controls cannot fail | **CONFIRMED** | duplication control added on the arm where it can; disclosed |
| C-M4 | engineering | two more §17 numbers wrong | **CONFIRMED** | §17.2 corrected |
| C-M5 | engineering | `rho_w` printed 16× as if it varied | **CONFIRMED** | renderer fixed; regression |
| C-M6 | engineering | no committed test reads CD's own artifacts | **CONFIRMED** | **fixed** (D-9) |
| C-M7 | engineering | the *other* cross-axis interval also excludes its point; reporting one is selective | **CONFIRMED** | renderer now flags both |
| C-M8 | engineering | the capture *invocation* is still ad hoc | **CONFIRMED** | disclosed CD-20; invocation recorded verbatim in §23.2 |
| C-L1 | engineering | reproduction depends on row order | **CONFIRMED** | **fixed** (D-8) |
| C-L3 | engineering | `(None, True)` contract docstring wrong | **CONFIRMED** | fixed |
| C-L4 | engineering | `pytest.raises(Exception)` too broad | **CONFIRMED** | narrowed |
| C-L5 | engineering | `rho_w` "indistinguishable from zero" vs an interval excluding zero; and it is recorded, not consumed | **CONFIRMED** | §15 qualifications 1 and 3 |
| C-L6 | engineering | `run_at` in the digest makes it a tamper check, not a reproducibility check | **CONFIRMED** | §23 |

**FACT — nothing was rejected.** Unlike Milestone CC, which rejected two findings
with evidence, every confirmed finding here was accepted. One reviewer hypothesis
(A-S9) was refuted **by the reviewer's own simulation** and is reported as a
negative finding rather than as a fix.

**FACT — what the review did NOT change.** The headline `r_b` (+0.198438), the
headline `rho_w` (−0.035450), all four intervals, the fifteen-panel table, the
verdict `INCONCLUSIVE`, the design outcome `INCONCLUSIVE`, the 10/5
`INCONCLUSIVE`/`UNREACHABLE` split, and the reproduction of Milestone CA's counts
are all unchanged. Independent reviewers recomputed every one of them from the
artifact and confirmed them exactly.

## 31. Verification

**FACT.** Test counts are stated in §31.1 from the final run, after every review
fix. They are **not** the counts the first version of this report quoted: that
version was written before the review, and the suite has grown by the regressions
§25 describes.

**Coverage misses, named rather than rounded away.** Not 100 %: `capture.py` at **67 %** because
its fetch path reaches a provider and a test that mocked the transport deeply
enough to run it would be testing the mock (§23.3, CD-20); `synthetic.py` at 93 %
because several scenario-validation refusals are unreachable from the sealed
scenario list; and the remainder are defensive branches on malformed input.

**FACT.** Architecture guards: 188 assertions in
`tests/test_paired_dependence_architecture.py` alone, covering module inventory,
fresh-interpreter import, docstring presence, production unreachability, dashboard
independence, execution verbs, credentials, store writes, AI calls,
network isolation (only `capture.py`), filesystem isolation, clock isolation,
unseeded generators, module-level `random.*` calls, bare `except`, renderer purity
(no float constant, no threshold comparison, no measurement import, no trade
language), export declaration, composite-score refusal, verdict non-endorsement,
eight production constants and four milestone seals.

**FACT.** One guard **fired during development and was obeyed rather than
widened** (§25, D-4).

### 31.1 Full suite

**FACT — final run, after every review fix and every closure fix.**
`.venv/bin/python -m pytest -q -W error` → **`14049 passed in 657.56s`**. No
failures, no errors, no warnings escalated.

| | count |
|---|---|
| released baseline (Milestone CC) | 13,384 |
| **final** | **14,049** |
| added by Milestone CD | **665** |
| of which CD's own and the shared tier guard | **660** across 17 test modules plus two helpers |
| of which new/rewritten guards in existing architecture tests | 5 |

**FACT — coverage of `fmis.paired_dependence`: 96 % statement and branch.**

**FACT — the suite failed twice on the way here, and both are recorded rather
than hidden.**

1. An early run failed **13** tests, every one a genuine repository-convention
   violation by CD — three export-name collisions and four import allowlists.
   Dispositioned in §26.
2. A run after the review fixes failed **5**, all of them CD's own tests that had
   to be updated to match improved behaviour: the new negative control's id, the
   observer call site after the read-only projection was added, and the
   scale-invariance parametrisation before the exact weighted form landed.

A suite that only ever passed would say less about the guards than one that
caught something.

---

## 32. Production safety

**FACT.** Verified by import, asserted by test:

| constant | value |
|---|---|
| `CONFIRMATION_LOOKBACK_BARS` | 10 |
| `MINIMUM_AGREEING_FAMILIES` | 2 |
| `DEFAULT_TIMEFRAMES` | 1w / 1d / 4h |
| `DEFAULT_BACKTEST_LIMIT` | 250 |
| derived warm-up | 1,750 days |
| CA seal | `910cad28…` (recomputed) |
| BZ seal | `4d089ff4…` |
| BY seal | recomputed = pinned |
| CC seal | `ef6f3950…` (recomputed) |
| `CaVerdict` members | unchanged |
| `FeasibilityVerdict` members | unchanged |

**FACT.** No production module imports `fmis.paired_dependence`; only
`pipeline/cli.py` does, asserted from source. The operator dashboard depends on
nothing here. No credential was read, no order path exists, no exchange was
contacted for anything but public `klines`, and no AI model was called.

**FACT.** No strategy was tested, no threshold tuned, no setup promoted, no
position opened.

---

## 33. Changed-file scope

**Modified (4 tracked files, +358 / −16 lines):**

| file | change |
|---|---|
| `src/fmis/swing_lab/admission_study.py` | **+14**: one additive observer parameter, its docstring, two lines of call |
| `src/fmis/pipeline/cli.py` | +171 / −2: the `dependence` research area, two flags, one runner |
| `tests/test_swing_lab_architecture.py` | allowlist, plus tier guards rewired to the shared partition after review found the first pair circular |
| `tests/architecture_tiers.py` *(new)* | **the import-tier invariant, declared once, as a partition** |
| `tests/test_architecture_tiers.py` *(new)* | the reviewer's bypass, reproduced and rejected |
| `tests/test_universe_architecture.py` | allowlist + one executable reachability guard |
| `tests/test_research_design_architecture.py` | allowlist + one executable reachability guard |
| `tests/test_trade_capture_architecture.py` | CLI prefix, on `fmis.universe`'s footing |

**Added:** `src/fmis/paired_dependence/` (13 modules), **15 test modules plus one
helper**, **three** artifacts — the source capture, the study, and the pre-review
study preserved as `0040_cd_paired_dependence_prereview.json.gz` — and this
report.

**FACT.** The pre-review study artifact was **renamed, never deleted**. Milestone
CC lost an artifact by regenerating over it and recorded the incident; CD keeps
both runs so the effect of the review fixes is auditable from the files
themselves.

**Untouched:** every one of the 16 pre-existing untracked research documents; every
production package; `docs/`; the operator dashboard.

---

## 34. Recommended next milestone — **do not begin it**

**HYPOTHESIS, not a finding.** Milestone CC recommended *Warm-Up Requirement
Sensitivity*. **CD removes that recommendation's premise** (§28.5–6): warm-up
moves the *ceiling*, and the ceiling is not what binds.

### 34.1 The recommendation the first version made, and why it was wrong

**Withdrawn.** The first version proposed: *"A control drawn at the same instant
on a different asset … would difference out the contemporaneous factor by
construction."*

**That redesign is already in CD's own data and it does not work.** Two of the
five sealed families — `ca_null_opposite_direction` and
`ca_null_random_direction_same_bar` — draw a control at the **same instant**, and
they return `r_b` of **+0.1876** and **+0.2002** on development. A same-instant
control on the *same asset* in the opposite direction does not cancel the market
factor; it **doubles** it. Found by independent review, from CD's own artifact.

### 34.2 The question CD actually leaves open

> **Can an admission experiment be designed whose estimand has a control leg with
> real variance, contemporaneous with the admission and on a different exposure?**

**INFERENCE.** `r_b` is large because `D` is arithmetically close to the raw
admission outcome (§13.3): averaging 200 controls leaves the control leg with
2.8 % of the admission leg's variance, so `corr(D, admission) = +0.987`. Nothing
about the *calendar* fixes that. What would change it is an estimand whose control
carries comparable variance and shares the admission's market exposure at the same
instant — for example an excursion measured **relative to the cross-sectional
median move of the universe in that same window**, which subtracts a
contemporaneous quantity of similar magnitude rather than a near-constant.

**LIMITATION.** CD has **not tested** this, and CD-11 warns that its own panel is
survivor-only and therefore unusually co-moving. This is a hypothesis that must be
pre-registered before it is measured, and its first obligation would be to state
in advance what `r_b` it expects to achieve and what it would conclude if it did
not.

### 34.3 The alternative, which is equally live

**Stop this swing-admission research branch.** Five milestones (BW, BX, BY, BZ,
CA) searched for an edge and found none; CB showed the search could not have
resolved one; CC showed the universe cannot be built; CD now shows the information
does not accumulate across assets the way the design assumed — and that this is a
property of the *estimand*, not of the universe.

**Capital preservation says a `NO TRADE` that has survived five milestones is
itself a result.** Which of the two paths to take is the owner's decision, and
nothing in this milestone makes it.

**Not started. Not begun. Nothing about either exists in this repository.**

## 35. Assumptions

1. The one-way random-effects model posits **exchangeability within a group**. A
   panel whose dependence changes over the timeline has no single correct `r_b`;
   the `non_exchangeable_blocks` scenario shows the estimator returns an
   intermediate value there rather than failing loudly.
2. A **time block** is a modelling choice, not a fact (CD-2). The whole grid is
   reported because of it.
3. The **ANOVA ICC is a ratio of unbiased estimates, not an unbiased estimate**
   (CD-4). Its small-sample behaviour is quantified by calibration.
4. `effective_clusters` assumes **equicorrelation** across clusters. A universe
   with block structure — say, majors versus long-tail — would not be described by
   one `r`.
5. CB's `MORE_CLUSTERS_SAME_DENSITY` path assumes new clusters arrive **at the
   observed density** (10.33 admissions per asset). CC measured that density as
   stable to 1.1 % across two periods and two symbol sets.

---

## 36. Git state at completion

**FACT — verified read-only before any change was made:**

| check | value |
|---|---|
| `HEAD` = local `main` = `origin/main` = `git ls-remote` | `f47cd05ece1ee4812bef6d3ffea05aaaa17391ae` |
| ahead / behind | `0 / 0` |
| staged | none |
| stash | empty |
| `MERGE_HEAD` / `REBASE_HEAD` / `CHERRY_PICK_HEAD` / bisect / rebase dirs | all absent |
| tags | one pre-existing (`bm-pre-rewrite-backup`) |
| untracked | exactly the **16** pre-existing research documents |

**FACT — the milestone's scope, verified before commit:**

- **10 tracked files modified**, +670 / −34 lines.
- **38 files added**: 14 source modules, 17 test modules, 2 test helpers, 3 artifacts, this report.
- **`git diff --check`**: clean.
- **Secrets scan**: the only match anywhere is the architecture guard that *forbids* those tokens.
- **Generated/cache files**: none staged; `__pycache__` is gitignored and no `.coverage`,
  `.pyc`, `.DS_Store`, `.egg-info` or `build/` artefact is included.
- **Dashboard isolation**: `src/fmis/operator_dashboard/` is **untouched** — zero files modified,
  zero added. Dashboard work was scoped out of this milestone twice and remains not started.
- **The 16 pre-existing untracked research documents**: **untouched** — not staged, renamed,
  formatted, deleted or committed, and still untracked afterwards.

**FACT — what was done to history.** One commit, on top of `f47cd05`, then a push of `main`.
**No force, no force-with-lease, no reset, no revert, no clean, no stash, no amend, no rebase, no
squash, no merge, and no tag** at any point. The commit is a fast-forward from `origin/main`, and
the parent is the verified baseline above.

**The commit's own SHA is not quoted in this section**, because a report cannot contain the hash of
the commit that contains it. The parent is recorded instead, the milestone is delivered as exactly
one commit on top of it, and the index row in
[`reports/README.md`](README.md) carries the same statement.

## 37. Plain-language answer

> **NOW THAT FMITS MEASURES THE ACTUAL PAIRED EFFECT ACROSS ITS ELIGIBLE ASSETS,
> DO WE KNOW ENOUGH ABOUT CROSS-ASSET DEPENDENCE TO DESIGN AN HONEST +0.10 ATR
> SWING ADMISSION EXPERIMENT?**

## **PARTIALLY.**

**We know four things we did not know this morning.**

**First, the observations exist now.** 2,390 paired admission-versus-control
differences are persisted with the provenance to audit every one offline, and the
Milestone BZ capture behind them — the file whose absence degraded Milestones CB
and CC — is written down. Three milestones reasoned about this sample from
published summary statistics. Nobody has to again. And the re-capture reproduced
Milestone CA's effects to four decimal places, not merely its counts.

**Second, the within-asset question is answered.** `rho_w` = −0.035, interval
[−0.077, −0.006]. Repeated admissions on one asset are essentially independent, so
Milestone CB's design effect is 1.00 and clustering by symbol costs no
information. Read it as *bounded near zero* rather than *significantly negative* —
at a true value of zero this estimator produces a zero-excluding interval about
15 % of the time.

**Third, Milestone CC's central assumption is wrong — though not for the reason
this report first gave.** CC assumed a paired within-symbol difference removes the
market factor and measured a residual of +0.0023 by proxy. Measured on the actual
paired effects it is **+0.198**, positive in all fifteen panels and all sixteen
grid cells. The reason is **not** that CA's controls are far away in time — that
was this report's first explanation and it was wrong three ways. The reason is
that `control_forward` averages two hundred draws, which leaves the control leg
with under 3 % of the admission leg's variance, so the paired difference is
arithmetically close to the raw admission outcome and two assets admitted in the
same window simply share the market's move.

**Fourth, the design implication is severe, though a third as severe as this
report first said.** Independent review found that the effective-cluster
arithmetic consumed the wrong correlation and overstated the penalty roughly
threefold. Corrected, the design-relevant dependence is +0.037 rather than +0.198
— still **seventeen times** the 0.00214 at which the information requirement stops
being finite. Milestone CC's 38 eligible assets supply between **8 and 23**
effective independent clusters, and every asset the provider has ever listed
supplies between **9 and 37**, against 467.

**Here is what we still do not know, which is why the answer is not YES.** The
honest interval on the headline panel runs from −0.049 to +0.418 and contains
zero. Fifteen assets and 155 admissions cannot resolve a correlation to the third
decimal place, and the third decimal place is exactly where the threshold sits.
Dropping a single asset moves the estimate by a factor of 2.2. The panel is
survivor-only, which biases it upward. The five panels that *do* exclude zero are
all validation panels, and validation's window is contained by the holdout's, so
they are not an independent replication. So the same data supports "dependence
costs nothing" and "no universe of any size is enough", and CD refuses to pick
between them by reading a point estimate as though the interval were not there.

**And the answer is not NO, because the direction is no longer in doubt.** Fifteen
of fifteen panels, sixteen of sixteen grid cells, every one positive; the control
that destroys contemporaneity destroys the estimate with it (+0.198 → −0.138); and
the estimator recovers a known dependence on synthetic panels while Milestone CC's
returns nearly the same number whatever the truth is. **The sign is established.
The magnitude is not.**

**What this means for the owner, in one paragraph.** FMITS still has no measured
edge, and nothing here changes that — Milestone CA's `NO_EDGE` stands. What has
changed is the diagnosis of *why the question is hard to answer*. It is not
primarily that the universe is too small, which is what Milestone CC concluded; it
is that **the experiment's own unit of evidence carries a shared market component,
so assets do not supply independent information no matter how many are added**. A
bigger universe was never going to fix this, and neither will a shorter warm-up.
The next honest move is either to redesign the experimental unit so its control
leg has real, contemporaneous variance — which is *not* the "same-instant control"
this report first proposed, because CD already contains two families that do that
and they are no better — or to stop this research branch. That is the owner's
decision, not this milestone's.

**One more thing the owner should take from this.** The two most important errors
in this milestone were found by **independent review**, not by 555 passing tests,
43 killed mutants or a self-review pass. Both were in the report's conclusions
rather than its arithmetic. That is the third milestone in a row where review, not
the suite, produced the most consequential finding — and it is the strongest
argument for keeping the review step that exists.

## 38. What this milestone explicitly did not do

- **No dashboard work.** The Operator Dashboard refresh UX — progress,
  success/failure per source, data freshness, what changed — remains outstanding.
  It had been recorded as *not done* by Milestones BV, CA and CC in turn and was
  **never tracked as a backlog item**; it is now **EP-21**.
- **No warm-up sensitivity study**, and §28 now argues against one as the next
  step.
- **No test of the redesign §34.2 proposes.** It is a hypothesis and is labelled
  one.
- **No rank-based check** separating the two candidate explanations for the
  ICC/pairwise gap (§16).
- **No CLI surface for the capture runner** (CD-20); the invocation is recorded
  verbatim in §23.3 instead.
- **No trading, paper, shadow or live capability of any kind.**
- **No tag, no force, no rebase, no squash, no merge.** One commit and one push of `main`, on
  the owner's explicit instruction at closure.
