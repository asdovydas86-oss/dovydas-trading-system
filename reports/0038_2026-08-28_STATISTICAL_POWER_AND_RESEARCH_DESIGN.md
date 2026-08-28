# Statistical Power & Research Design Foundation — Implementation and Research Record

| Field | Value |
|---|---|
| **Report number** | 0038 |
| **Title** | Statistical Power & Research Design Foundation (Milestone CB) |
| **Date** | 2026-08-28 |
| **Report type** | Implementation + Research |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | base `d1735bb`; this milestone's work is **uncommitted** in the working tree |
| **Status** | Final |

**Milestone:** CB — Statistical Power & Research Design Foundation.

**Scope guard.** No production trading policy changed. `CONFIRMATION_LOOKBACK_BARS`
is still `10` and `MINIMUM_AGREEING_FAMILIES` is still `2`, verified by import at
the close of the milestone. `swing_setup` does not appear in the changed-file
list. **No strategy was tested, no threshold tuned, no admission rule altered, no
order placed, no exchange contacted, no credential read, and no AI called.** CB
builds a research instrument; it does not use it to invent a strategy.

**Vocabulary used throughout.** `FACT` — checkable from the repository.
`MEASUREMENT` — produced by code in this milestone. `ASSUMPTION` — an input that
was declared rather than measured. `POST-HOC RESOLUTION` — computed from a
completed study's own uncertainty. `PROSPECTIVE POWER` — computed before a study
runs, from an assumed dispersion. `INTERPRETATION` — my reading. `LIMITATION` —
what this cannot do.

---

## 1. The answer, first

> **Why was Milestone CA underpowered, and what would it take to test a +0.10 ATR
> swing admission effect honestly?**

**CA's own figure is REPRODUCED, and it is right — under an assumption CA never
stated.** Report 0037 §1 publishes *"roughly 4,800 matched admissions per
sample"*, derived as `(0.558 / 0.10)² × 155`. An independent recomputation
through a general layer that knows nothing about CA gives **4,827** from the
half-width CA quotes and **4,823** from the interval bounds CA tabulates. Both are
within 0.6 % of the published figure. **Disposition: REPRODUCED.**

**What CB adds is that the figure is a statement about one growth path, and CA
does not say which.**

| how the extra admissions arrive | required to resolve +0.10 ATR | reachable? |
|---|---|---|
| **more symbols at the same density** | **467 symbols / 4,823 admissions** | **yes — and the count is identical at every assumed clustering** |
| **more years on the same 15 symbols** | **— no size suffices —** | **NO, at any intracluster correlation above zero** |
| every observation independent *(CA's implicit assumption)* | 4,823 admissions | yes, by assumption |

**The second row is the milestone's finding.** With the cluster count fixed at 15,
the symbol-clustered half-width approaches a **floor** that depends on the cluster
count alone and never goes below it:

| assumed intracluster correlation | half-width floor at 15 symbols | vs the 0.10 ATR bar |
|---|---|---|
| 0.00 | 0.0000 | reachable |
| **0.05** | **0.3311** | **3.3× the bar** |
| **0.10** | **0.4078** | **4.1× the bar** |
| 0.20 | 0.4736 | 4.7× the bar |
| 0.50 | 0.5326 | 5.3× the bar |

**Even the mildest clustering makes "run it for more years" incapable of answering
this question at any sample size.** Only at *exactly* zero — every admission on
every symbol independent of every other — does more history work, and that is the
one value the data is least likely to take.

**And CA's ~4,800 is itself the optimistic reading.** It is an
`INTERVAL_EXCLUDES_ZERO` criterion: met about half the time when the true effect
equals the declared magnitude. A real 80 % power guarantee costs
`((z_c + z_β)/z_c)² = 2.043×` the information — **954 symbols and 9,854
admissions**.

**Verdict on the CA-style research design: `UNDERPOWERED`, binding dimension
`cluster_count`.** Not "underpowered, collect more data" — underpowered in a way
that a specific kind of data cannot fix.

---

## 2. Starting git state

The brief named `d1735bb74160f66d4a513263845963e16e71fca9` as the released
end-state of Milestone CA. **It was correct**, and every check agreed:

```
branch            main
HEAD              d1735bb74160f66d4a513263845963e16e71fca9
                  docs(product): record swing admission edge study
local main        d1735bb   (identical)
origin/main       d1735bb   (identical)
git ls-remote     d1735bb   refs/heads/main
ahead / behind    0 / 0
stash             empty
staged files      none
unresolved ops    none — no MERGE_HEAD, REBASE_HEAD, CHERRY_PICK_HEAD or BISECT
working tree      clean apart from 16 pre-existing untracked AP/BB-era research
                  documents under docs/design/ and docs/reviews/
```

**Those 16 documents were not staged, modified, deleted, renamed, moved or
absorbed.** They appear in §28's `git status` exactly as they appeared before this
milestone began.

**Baseline suite before any CB code was written: 12,380 passing under
`-W error`** — the figure report 0037 §28 records at the close of CA.

---

## 3. Architecture and reuse audit

The brief requires the existing owners of every statistical concern to be mapped
before code is written. They were.

| Concern | Existing owner | What CB did |
|---|---|---|
| bootstrap / resampling | `swing_lab.admission_study._bootstrap_interval` (private) | **definition reused, not the function** — see §3.2 |
| quantile | `swing_lab.metrics.nearest_rank_quantile` | **extracted**; the laboratory now calls the extraction |
| deterministic seeds | `swing_lab.admission_matching.derive_seed` | **extracted**; the laboratory now calls the extraction |
| concentration | `swing_lab.robustness.concentration_of_magnitudes` | **extracted**; the laboratory now calls the extraction |
| sample floors | `swing_lab.metrics.SAMPLE_FLOOR`, `statistics.sampling` | **neither reused nor duplicated** — see §3.3 |
| walk-forward blocks | `swing_lab.validation_study.walk_forward_boundaries` | **imported** by the CA adapter for the time-block count |
| sample boundaries | `swing_lab.preregistration.SAMPLES` | **imported by identity**; a test asserts every CB window is BY's |
| effect threshold | `swing_lab.admission_preregistration.MIN_ADMISSION_EDGE_ATR` | **imported by identity**, never retyped |
| concentration bound | `swing_lab.geometry_verdict.MAX_SINGLE_SYMBOL_SHARE` | **imported by identity** |
| research question | `admission_preregistration.CA_RESEARCH_QUESTION` | **imported by identity** |
| artifact digest scheme | `swing_lab.admission_artifact` | **pattern reused, code not shared** — see §3.4 |
| result surface | `pipeline.cli` `research` area | one new choice, `design` |

**No second bootstrap, no second quantile, no second seed framework, no second
concentration formula and no second sample-floor system were created.**

### 3.1 The three extractions, and why they were necessary

CB's core must be reusable outside swing research, which means it **cannot import
`fmis.swing_lab`** — an architecture guard already asserts that no production
module does, and a "general" package that reached into the laboratory would be a
swing module with a different name. The three primitives it needs already lived
there. Each was **extracted rather than copied**:

| extracted to `research_design.numeric` | from | the laboratory now |
|---|---|---|
| `derive_seed(master, parts)` | `admission_matching.derive_seed` | calls it with CA's identity fields |
| `nearest_rank_quantile` | `metrics.nearest_rank_quantile` | delegates |
| `largest_share` | `robustness.concentration_of_magnitudes` | delegates |

**All three are behaviour-preserving and are proven so.**
`tests/test_research_design_extraction.py` pins the seed against a hand-computed
SHA-256 of the joined identity string, asserts the laboratory wrapper and the
general function return the identical value, and asserts each wrapper keeps its
own `SwingLabError` type **and its own message**. `MEASUREMENT:` the three sealed
digests are byte-identical afterwards —

```
BY  a81b6ab8314bd3cf2e8a6358f3a19cf8d6bb6c152cef9efd55fbffd9883d640a
BZ  4d089ff43ec11e24e7e43e0a0f7ca377da996ee5a6391bb8f9c70d6922a3a175
CA  910cad28001ee18d9630f685e454bfd6bf24fb7d78b907e89172371b83f25e8a
```

— each matching what report 0037 §28 recorded, and each asserted by a regression
in `tests/test_swing_lab_admission_power.py`.

The extraction **added one guard the original lacked**: an identity part
containing the `|` separator is now refused, because two different identities
could otherwise join to one string and share a seed. No CA input contains one, so
no draw moved.

### 3.2 Why the bootstrap definition was reused but the function was not

`_bootstrap_interval` is private to `admission_study` and is welded to a
`PairedRecord` — a CA type carrying an admission, a control and a horizon.
Extracting it would have meant either dragging that type into the general layer or
rewriting the function's signature, and rewriting a sealed estimator's signature is
how a sealed estimator quietly stops being the sealed one.

`research_design.resolution.cluster_bootstrap` therefore implements **the same
definition** over a general `ClusteredObservation`: draw `K` cluster labels with
replacement from the `K` present, pool every observation of every drawn cluster,
take the plain mean, read the interval off nearest-rank quantiles. That it is the
same definition is checked numerically rather than asserted — §7.

### 3.3 Why the sample floor was NOT reused

`SAMPLE_FLOOR = 20` governs *when a figure may be stated*. CB asks a different
question — *can this design resolve this effect* — and a design with 19
observations is not "unmeasurable", it is measurable and hopeless, which is a more
useful answer. `DesignTarget` instead carries `minimum_clusters`,
`minimum_time_blocks` and `maximum_cluster_share` as **declared, auditable values
supplied by the caller**, so the framework validates a floor rather than owning one.

### 3.4 The artifact pattern, reused without sharing code

`research_design.artifact` follows `admission_artifact`'s rules exactly — SHA-256
over canonical JSON, the digest excluding the slot it is written into, a `kind`
and a `schema_version` that are never upgraded silently. It shares no code,
because `admission_artifact` also writes gzip files and **CB opens no file at
all** (§13).

---

## 4. The statistical-design architecture

`src/fmis/research_design/` — 8 modules, 1,066 statements.

| module | owns |
|---|---|
| `models.py` | the vocabulary: unit, effect, sample frame, dependence, estimator, target, mode, verdict, limiting factor, growth path |
| `numeric.py` | the four shared primitives: seed, quantile, share, normal quantile |
| `dependence.py` | the information profile and the design effect |
| `resolution.py` | both methodologies: the cluster bootstrap, and the analytic projection |
| `verdict.py` | the gate |
| `artifact.py` | encoding, digesting, and the pre-registration citation seam |
| `render.py` | the plain-language report |
| `__init__.py` | the package's declared surface |

`src/fmis/swing_lab/admission_power.py` — the **CA adapter**, and the only place
the general layer meets ATR, symbols and Milestone CA.

**The core knows nothing about trading.** An architecture guard asserts that no
identifier and no runtime string in `research_design` contains `atr`, `btcusdt`,
`crypto`, `candle`, `ohlc`, `bps` or `usdt` — checked over the **parsed tree**, so
that the docstrings remain free to explain that CA's bar was +0.10 ATR while the
code cannot know what an ATR is. A separate test asserts that distinction is
deliberate and holds from both ends.

---

## 5. The unit of evidence

**Made explicit as a required, non-empty field.** `DependenceModel.unit_of_evidence`
cannot be constructed empty. For CA it reads:

> *one admitted decision instant — the first confirmation of a swing opportunity,
> deduplicated by Milestone AR's opportunity tracker*

**`InformationProfile` reports several dimensions and refuses to collapse them
without an assumption.** For CA's three samples:

| sample | role | observations | clusters | obs/cluster | time blocks | units | largest cluster share |
|---|---|---|---|---|---|---|---|
| development | development | 155 | 15 | 10.3 | 4 | 155 | 0.113 |
| validation | validation | 91 | 15 | 6.1 | 3 | 91 | *not published* |
| holdout | holdout | 234 | 21 | 11.1 | 5 | 234 | *not published* |

**No single effective sample size is offered for any of them**, because CA
measured no intracluster correlation and the framework refuses to invent one. The
derivation printed in its place says so in words. Where a correlation *is*
declared, `effective_observations = n / (1 + (m − 1)ρ)` is offered **with its
derivation and its equal-cluster-size assumption attached as a value**, not as a
comment.

`ASSUMPTION:` this is the honest treatment. Report 0037 §12.3 withdrew a headline
claim built on 8,793 four-hourly instants sharing 23 of 24 forward bars. Those
were rows, not evidence, and no scalar could have said so.

---

## 6. The dependence and clustering model

Six axes, each a field:

| field | CA's value | consequence |
|---|---|---|
| `cluster_axis` | `symbol` | the bootstrap resamples symbols |
| `overlapping_horizon` | 60 bars | fires a caveat: rows overstate distinct experiments |
| `repeated_measurements` | `False` | each admission is a distinct setup |
| `intracluster_correlation` | **`None`** | every projection is reported across a declared range instead |
| `correlation_source` | `None` | required whenever a correlation *is* declared, so a measurement and a guess are distinguishable |
| `assumptions` | 3 sentences, required non-empty | including the **residual dependence CA's own §23 counts**: 33 of 155 development admissions fall within 60 bars of another admission on the same symbol, which the symbol cluster does **not** price, making every interval here mildly optimistic |

`MEASUREMENT:` the framework detects pseudoreplication structurally. A hostile
probe grows rows a hundredfold inside a fixed 10 clusters and asserts the interval
does **not** behave like a hundredfold increase in information; another grows the
cluster count to 100 with perfectly correlated data and shows the bootstrap
reports a **zero-width** interval, which the resolution layer then **refuses** —
so perfectly correlated clusters can never be reported as resolving everything.

---

## 7. Both methodologies, and the proof they agree

**Empirical, preferred whenever observation-level data exists.**
`cluster_bootstrap` assumes no distribution. `empirical_design_curve` sub-samples
**real clusters** and refuses to go above the cluster count present — asking it to
raises rather than silently extrapolating.

**Analytic, used when only a published summary survives.** For a mean over `K`
clusters of `m` observations, dispersion `σ`, correlation `ρ`:

```
standard error² = σ² · (ρ + (1 − ρ)/m) / K
half_width      = z(confidence) · standard error
```

**`MEASUREMENT:` the two agree.** On synthetic data with a *known* variance
decomposition — 40 clusters × 20 observations — the measured bootstrap half-width
matches the analytic prediction within 15 % at ρ = 0.00, 0.20 and 0.50, and the
inversion round-trips a dispersion to 12 decimal places. That agreement is what
entitles the analytic path to describe designs the empirical one cannot reach.

**One property worth recording**, found by a surviving mutation and pinned as a
test: **`z(confidence)` cancels exactly** between inverting an observed width and
projecting a new design, so every projected width is identical at 50 %, 95 % and
99 %. Only the *bar* moves with the target. The consequence is a real constraint —
the curve **cannot detect** a width supplied at the wrong confidence — and it is
now stated in the docstring as the caller's invariant rather than left implicit.

---

## 8. Prospective and post-hoc, separated structurally

**This is the distinction the brief calls out and it is unreachable rather than
discouraged.**

* `PostHocResolution` is produced **only** by a function handed a width a realised
  measurement produced.
* `ProspectiveDesign` is produced **only** by a function handed an *assumed*
  dispersion and a required `dispersion_source` saying where it came from.
* Neither has a `mode` **field**. `mode` is a read-only property returning a
  constant. `assess_research_design` takes **no mode argument at all** — asserted
  by a test that inspects its signature.

`MEASUREMENT:` two mutation probes relabelled each class's mode; **both were
killed**. A third replaced the resolution with the string `"prospective"`; it is
refused with *"the mode is carried by the object and cannot be passed as a label"*.

**CA's calculation is POST-HOC and every surface says so.** The report's first
line is `POST-HOC RESOLUTION DIAGNOSTIC — … This is NOT the power calculation that
justified running the study, and it must never be quoted as one.` It is not
relabelled as prospective power anywhere.

---

## 9. The minimum meaningful effect

**The framework owns no threshold.** `MeaningfulEffect` requires a magnitude, a
unit, a direction, a **rationale** and a **source**, and refuses a zero or
negative magnitude by name — a negative one is redirected to `direction` rather
than accepted as a sign convention.

`magnitude` is `Decimal`, because a *declared* bar must render and digest exactly;
everything computed is a float, and the boundary between them is one conversion.

CA's bar is imported by identity from `MIN_ADMISSION_EDGE_ATR` and carries its
own provenance sentence from report 0037 §9. A mutation replacing it with a
literal `0.60` was killed.

**Unit consistency is a verdict, not a crash.** An effect in `r` compared against
an interval in `atr` returns `MISALIGNED_UNIT` with limiting factor
`UNIT_MISMATCH`, and it does so **even when the interval is narrow enough to
resolve the effect** — the mismatch beats every other finding in the ordering.

---

## 10. CA reproduction, and the disposition of the ~4,800 estimate

**Disposition: `REPRODUCED`.**

| | value |
|---|---|
| published claim (report 0037 §1, CA-8) | **~4,800** admissions per sample |
| published half-width | 0.558 |
| half-width **derived from the tabulated bounds** (−0.7494, +0.3662) | **0.5578** |
| recomputed from the published half-width | **4,827** |
| recomputed from the interval bounds | **4,823** |
| relative difference vs the published figure | **0.0056** |

Both recomputations run through
`required_information(GrowthPath.INDEPENDENT_OBSERVATIONS, …)` in the general
layer, which has no knowledge of CA. The classification rule is stated in code and
was fixed before the numbers were read: agreement within 5 % is `reproduced`.

**`INTERPRETATION:` the published figure is correct as stated. What CB adds is the
name of the assumption it rests on** — it is the independent-observations path,
and CA's report does not distinguish that path from the two others that give
materially different answers (§1, §11).

**Two things this reproduction is NOT.** It is a **summary-statistic**
reproduction: CA's 155 paired differences are not persisted in this repository and
are not recoverable without a fresh network replay that would produce a different
dataset — the failure BZ recorded as BZ-D2. And it uses **one family's** interval,
`ca_null_matched_timing`, the family CA-8 is stated against; three of the other
four sealed families have wider intervals, so a design assessment of those would be
no more favourable. Both are recorded as CB-1 and CB-3.

---

## 11. Required information, and the more-symbols-vs-more-years finding

`MEASUREMENT:`, from CA's development sample (155 admissions, 15 symbols,
half-width 0.5578, bar 0.10 ATR):

| growth path | ρ | reachable | required clusters | required observations |
|---|---|---|---|---|
| independent observations | — | yes | *not modelled* | **4,823** |
| more clusters, same density | 0.00 | yes | 467 | 4,823 |
| more clusters, same density | 0.05 | yes | 467 | 4,823 |
| more clusters, same density | 0.10 | yes | 467 | 4,823 |
| more clusters, same density | 0.20 | yes | 467 | 4,823 |
| more clusters, same density | 0.50 | yes | 467 | 4,823 |
| more observations, same 15 clusters | 0.00 | yes | 15 | 4,823 |
| **more observations, same 15 clusters** | **0.05** | **NO** | — | **floor 0.3311** |
| **more observations, same 15 clusters** | **0.10** | **NO** | — | **floor 0.4078** |
| **more observations, same 15 clusters** | **0.20** | **NO** | — | **floor 0.4736** |
| **more observations, same 15 clusters** | **0.50** | **NO** | — | **floor 0.5326** |

**Two results, and the second is the one that matters.**

1. **Scaling by adding symbols at the observed density costs exactly what the
   naive rule predicts, at every correlation.** This is algebra, not coincidence:
   growing `K` at fixed `m` scales the whole variance by `1/K`, so `ρ` cancels.
   `MEASUREMENT:` a test asserts the required count is the identical `4,823` for
   ρ ∈ {0, 0.05, 0.1, 0.2, 0.5, 1.0}. **CA's figure is exactly right on this path.**

2. **Adding history inside the same 15 symbols has a floor and cannot reach the
   bar at any size**, for every correlation above zero. The half-width approaches
   `h · √(ρ / (ρ + (1−ρ)/m))` and stops there.

`INTERPRETATION:` "collect more data" is not an answer to CA. **More *years* is
not more information for this question; more *symbols* is.** That distinction is
invisible to CA's own arithmetic because that arithmetic has no term for it.

`ASSUMPTION:` the more-clusters path assumes new symbols are exchangeable with the
current 15 — that a 467-symbol universe carries the same per-symbol dispersion and
the same between-symbol correlation. In a market where the marginal added symbol is
progressively more correlated with the existing set, the true requirement is
**higher** than 467, never lower. This is stated in the path's own `note` field.

---

## 12. Design curves

Modelled, and every point beyond the observed 155 carries `extrapolated=True`.

**More clusters at the same density (identical at ρ = 0.00 and ρ = 0.10):**

| admissions | symbols | half-width | resolves +0.10? |
|---|---|---|---|
| 103 | 10 | 0.6832 | no |
| **155** | **15** | **0.5578** *(the observed point)* | no |
| 207 | 20 | 0.4831 | no |
| 506 | 49 | 0.3086 | no |
| 1,002 | 97 | 0.2194 | no |
| 2,005 | 194 | 0.1551 | no |
| **5,001** | **484** | **0.0982** | **yes** |
| 10,003 | 968 | 0.0694 | yes |

**More observations inside the same 15 symbols, at ρ = 0.10:**

| admissions | symbols | half-width | resolves? |
|---|---|---|---|
| 155 | 15 | 0.5578 | no |
| 500 | 15 | 0.4596 | no |
| 1,000 | 15 | 0.4345 | no |
| 5,000 | 15 | 0.4133 | no |
| **10,000** | **15** | **0.4105** | **no — and it never will** |

**The curve flattens onto the 0.4078 floor.** A sixty-fold increase in admissions
buys a 26 % reduction in the half-width and then stops.

**`LIMITATION` CB-4: this curve is modelled, not measured.** Without
observation-level data the empirical sub-sampling path is unavailable for CA. The
empirical path exists, is tested on synthetic data with a known decomposition, and
**refuses** to go beyond the clusters present.

---

## 13. Sensitivity to clustering assumptions

The question the brief asks — *how sensitive is the answer to cluster
assumptions?* — has a two-part answer.

**Not at all, on the more-clusters path.** 4,823 at every ρ (§11).

**Completely, on the more-years path.** Reachable at ρ = 0; unreachable at every
ρ > 0. The design's fate is decided by a quantity CA never measured, which is why
the framework decides the binding dimension at the **least favourable** member of
the declared range and says so in its assumptions.

**`LIMITATION` CB-6, and a finding of my own that I withdrew.** A first probe
compared the analytic model against a measured bootstrap on a deliberately unequal
cluster-size profile and appeared to show a 40 % bias. **Averaged over 15
realisations the bias vanished** — median model/measured ratios of 1.08, 1.04,
1.01 and 1.07 across equal, CA-like, moderate and extreme size profiles. The claim
is withdrawn. What survives is the **scatter**: the ratio ranges 0.70–1.89 across
realisations, so a half-width measured once over 15 clusters carries roughly ±30 %
uncertainty *before* any modelling assumption applies. **`4,823` should be read as
an order of magnitude, not as four significant figures.**

---

## 14. The design gate

`assess_research_design` returns one of six verdicts by a stated, ordered rule.
The first condition that holds decides.

| # | verdict | fires when |
|---|---|---|
| 1 | `NOT_MEASURABLE` | fewer than two observations, or no cluster |
| 2 | `MISALIGNED_UNIT` | the effect and the uncertainty carry different unit codes |
| 3 | `INSUFFICIENT_INDEPENDENCE` | clusters or time blocks below the declared floor; one cluster above the declared concentration bound; or an estimator that ignores a declared dependence |
| 4 | `UNDERPOWERED` | the uncertainty is wider than the effect requires |
| 5 | `LIMITED` | resolves it, with stated caveats |
| 6 | `READY` | resolves it, with none |

**No member says anything about the hypothesis.**
`DesignVerdict.says_nothing_about_the_hypothesis` is `True` for every member,
asserted over the whole enum — the device Milestone CA uses for
`is_approved_for_trading`. A further test asserts the assessment payload contains
no field naming an edge, a profit, an approval, a promotion or a forward test.

**Boundaries are inclusive and are now pinned.** "Minimum" and "maximum" mean what
they say: a design holding exactly the declared minimum cluster count passes, and
one at exactly the maximum concentration passes. Both were **mutation survivors**
before this milestone closed (§17).

---

## 15. Holdout discipline

**The framework never requires the holdout to be opened, and refuses to let it
decide a design.**

* Every input to `InformationProfile` is sample **metadata** — counts, boundaries,
  declared structure — so a holdout can be profiled without being measured. A test
  asserts exactly that.
* `ProspectiveDesign` consumes an **assumed** dispersion, so a holdout can be
  *planned for* without being opened. `MEASUREMENT:` CA's holdout returns
  `UNDERPOWERED` under a prospective assessment built from development's own
  published dispersion.
* A **post-hoc** resolution measured on a holdout is **refused** as a gate input,
  by name: *"the holdout's own outcomes are the one thing a design assessment must
  not consult — a design justified by them has already spent it."* Two mutations
  disabled that check; **both were killed.**

`SampleFrame` additionally refuses a validation window that overlaps a development
window **of the same population**, while permitting overlap across populations —
without which CA's holdout, which runs 2024-06→2026-08 over 21 symbols the primary
universe never held, would have been rejected.

---

## 16. Future pre-registration integration

**No sealed document was touched.** BY's, BZ's and CA's digests are byte-identical
(§3.1). The seam is **forward only**.

`citation_for(payload)` returns five strings — assessment id, content digest,
mode, verdict, limiting factor — that a future seal embeds. Deliberately no
numbers: a seal holding a second copy of the effect threshold and the sample
counts is a second copy that can drift.

**The absence of a cycle is proven from both ends**, in one test:

* embedding the citation **changes** the pre-registration's digest — so the seal
  really records that it cited a design;
* the assessment's own digest is **unchanged** and still verifies — so nothing
  feeds back.

A further test asserts the assessment payload names no pre-registration digest
anywhere, which is the first half of any cycle.

---

## 17. Hostile review and mutation testing

### Hostile review — 52 probes, 0 failures

Every probe the brief names, as a readable checklist:
N=0, N=1, one cluster, one symbol at 99 %, perfectly identical observations, all
positive, all negative, zero variance, huge variance, heavy tails, an extreme
outlier, malformed units, an effect exactly at the resolution boundary, a
confidence exactly on the supported boundary, an impossible confidence, repeated
overlapping windows, every observation in one time block, symbols growing with
perfectly correlated data, rows growing while clusters do not,
development/validation overlap, a holdout leak, a changed seed, changed
`PYTHONHASHSEED`, artifact tampering, a post-hoc assessment labelled prospective,
and a design that can never meet its target.

**The most valuable one.** Perfectly correlated clusters produce a **zero-width**
bootstrap interval — the bootstrap cannot see dependence it has no variation to
detect — and a zero-width interval resolves every effect. The framework **fails
closed**: `post_hoc_resolution` refuses a non-positive width, so that data can
never be reported as `READY`.

### Mutation testing — 42 probes, 41 killed, 1 equivalent

Files were snapshotted as **bytes** and restored from those bytes; `git checkout --`
was never used. **`MEASUREMENT:` all nine files verified byte-identical after the
pass.**

Mutations covered every item the brief lists: effect sign, effect unit, threshold,
confidence, cluster count, concentration, bootstrap quantile, sample count, sample
identity, holdout exclusion, the prospective/post-hoc label, verdict boundaries,
the seed, the repetition count, the interval width, the required-information
calculation and the artifact digest.

**Three survivors, all investigated, none dismissed.**

| survivor | investigation | disposition |
|---|---|---|
| `clusters < minimum` → `<=` | The boundary case `clusters == minimum` is the only input that distinguishes them, and nothing pinned it. Current behaviour (inclusive) is correct — "minimum" means what it says. | **TEST GAP. Three boundary tests added** (cluster floor, concentration bound, and the time-block floor, which would also have survived). All three now killed. |
| `share > maximum` → `>=` | Same class. | **TEST GAP, fixed as above.** |
| curve confidence hardcoded to 0.5 | `z(confidence)` cancels between the inversion and the projection, so the mutation cannot change any number. Verified numerically at 0.50/0.80/0.95/0.99 — identical to 12 decimal places. | **EQUIVALENT MUTANT.** The property is now pinned as a test and stated in the docstring. |

---

## 18. Independent code review

**`FACT:` no subagent was used** — the session's operating instructions forbid it
unless the owner asks. The review was an adversarial pass I ran myself against the
finished code, briefed on the brief's own attack list, with **every finding
verified by a separate script before being accepted**.

**Three findings. One was a real defect, one was a real defect of a lesser kind,
and one was wrong and is withdrawn.**

| # | finding | verification | disposition |
|---|---|---|---|
| 1 | `prospective_design` accepts an estimator and a target that disagree about the confidence level, while `post_hoc_resolution` refuses the same mismatch | **CONFIRMED** — reproduced: a 0.80 estimator against a 0.95 target was accepted and returned a width | **FIXED — defect CB-D2.** The same rule now applies in both modes; 2 regressions added; a mutation disabling it is killed |
| 2 | `analytic_design_curve` takes a `confidence` separate from its target, so the widths and the `resolves` column could describe different intervals | **REFUTED by my own verification.** `z` cancels between inversion and projection; widths are identical at 0.50/0.80/0.95/0.99. The argument could never change a number. My original evidence compared two runs on **different size grids** and I misread the difference as caused by the confidence | **WITHDRAWN as a defect.** The redundant argument was still removed — a parameter that appears to control something and cannot is a trap — and the real invariant (*the width must have been measured at the target's confidence*) is now documented and pinned |
| 3 | the equal-cluster-size approximation biases the analytic model by ~40 % on unequal profiles | **REFUTED by my own verification** — the 40 % came from a single realisation; over 15 realisations the median ratio is 1.00–1.08 across four size profiles | **WITHDRAWN.** What replaced it is CB-6, the ±30 % realisation scatter, which is real and is now a stated limitation |

**Two of my three findings did not survive verification.** That is the process
working: report 0037 §29 records the same experience from the other side, and
recording a withdrawn claim is cheaper than acting on a wrong one.

**Defects found and fixed in this milestone:**

* **CB-D1** — the test helper drew cluster offsets and within-cluster noise from
  one interleaved generator, so the cluster **means changed whenever the density
  changed** and any comparison across densities was comparing different clusters.
  Found by a hostile probe that failed for the right reason. Fixed by seeding the
  offsets independently of `per_cluster`; the fix is documented in the helper.
* **CB-D2** — the prospective/post-hoc confidence asymmetry above.
* **CB-D3** *(withdrawn as a defect, kept as a cleanup)* — the redundant curve
  confidence argument.
* **Dead code removed** — a `SampleFrame` guard for "observations present but a
  zero cluster share" that **could not fire**: the malformed-frame check
  guarantees a cluster exists, and the uniform-share check then rejects a zero
  share. A guard that cannot fire reads as coverage that is not there.
* **A non-monotonicity that was a property, not a bug** — the empirical design
  curve is not monotone at small cluster counts with few sub-samples. Rather than
  assert a guarantee the estimator does not make, `DesignPoint` now carries
  `subsample_spread` and `overlaps()`, so a wobble reads as noise instead of as a
  finding.

---

## 19. CLI and research surface

```
fmits research design
```

**It reads nothing.** No network, no capture, no store, no market data of any
kind — every input is published sample metadata and a published interval, which
is what makes it safe to run *before* a study rather than after. Two tests hold
that from the outside: one makes `fetch_raw_klines` raise and requires the command
to still succeed; the other runs it from an empty directory.

It refuses `--start`, `--end`, `--from-capture`, `--save-capture`, a positional
universe and `--holdout`, each by name. `--save-study` writes a verifiable
artifact and never overwrites.

The output answers the brief's template in order: Question · Minimum meaningful
effect · Available information · Dependence/clustering · Current uncertainty ·
What this design can resolve · What it cannot · Verdict · What additional
information would help · Assumptions · Caveats — followed by the CA reproduction,
the design curves, the post-hoc reading of all three samples, and what the
assessment cannot do. **346 lines, none wider than 78 characters, byte-identical
across runs.**

**No dashboard page.** The brief permits a thin read-only addition and CB declines
it, for the reason CA declined it: the dashboard's seam takes *study* artifacts of
a different shape, and CB's value is in tables a terminal renders better than a
card. Recorded as **not done** rather than half-done. The dashboard's 30–45 s
refresh was left untouched, as instructed.

---

## 20. Artifact, reproducibility and determinism

**The artifact is recomputable and disposable, and no durable `RecordKind` was
added.** `research_design` **opens no file at all** — an architecture guard
asserts it imports no `pathlib`, `os`, `io`, `gzip`, `shutil`, `tempfile` or
`subprocess`, and calls no `open`, `Path`, `write_text` or `mkdir`. That is a
stronger guarantee than `swing_lab`'s, which permits one artifact module per
milestone to touch a file.

| gate | result |
|---|---|
| encoded assessment verifies against its own digest | **passes** |
| two encodings of one assessment | **byte-identical** |
| written twice through the CLI | **byte-identical files** |
| an edited verdict / limiting factor / mode / primary sample | **each caught** |
| an edited effect threshold | **caught** |
| an edited manifest field | **caught** |
| a foreign `kind` | **refused by name** |
| a foreign schema version | **refused, never upgraded silently** |
| the digest covers the slot it is written into | **no** — asserted |
| the artifact carries market data | **no** — no series key, and no numeric list longer than 20 |
| **CB design-assessment digest** | `d1ea2ffd92581336e690dbabe7d6de591edc2a01c6238aaac76cfa135cfb5288` |

**Determinism.** Every draw is seeded by SHA-256 over its own identity; Python's
salted `hash` is never used. `MEASUREMENT:` the bootstrap reading and the **whole
CA assessment digest** are asserted identical under `PYTHONHASHSEED` 0, 1 and
12345, each in a fresh interpreter. Changing the master seed moves the interval
and **never** moves the point estimate — asserted separately, because a seed that
moved a point estimate would mean the statistic depended on the resampling.

---

## 21. Verification

| gate | result |
|---|---|
| **Full repository under `-W error`** | **12,952 passing**, 0 failures (from **12,380** at the start of CB; **+572**) |
| Focused CB suite | **565 tests** across 11 new files |
| **Hostile review** | **52 probes, 0 failures** |
| **Mutation testing** | **42 probes, 41 killed, 1 equivalent mutant**; all files restored byte-identical |
| **Independent code review** | **3 findings: 1 defect FIXED, 2 claims WITHDRAWN after my own verification** |
| Architecture guards (`research_design`) | **124 passing** |
| Architecture guards (`swing_lab`) | roster extended by one module |
| BY / BZ / CA pinned seals | **byte-identical** |
| Determinism across `PYTHONHASHSEED` | **stable**, including the whole assessment digest |
| New runtime dependencies | **0** — `pyproject.toml` and `uv.lock` unchanged |
| ADRs required | **0** — consistent with CA, which also required none |
| Guards weakened | **0** |
| Guards **strengthened** | **3** — see below |
| Guards widened | **1** — the CLI import allowlist, that guard's designed extension point |

### Three guards were strengthened rather than accepted

Six of my own architecture guards failed on first run because they matched
**prose in docstrings**: `atr` in the sentence explaining why the package exists,
`recommend` in *"No trading recommendation appears anywhere"*, and `Path(`
matching `GrowthPath(Enum)`. Widening them would have forced the package to stop
explaining itself. Instead:

* the trading-vocabulary guard now checks **identifiers and runtime strings**
  parsed from the AST, plus a **second** guard over emitted strings alone;
* the filesystem guard now checks **imports and called names**, which is decisive
  rather than approximate;
* the renderer's no-recommendation guard now checks its **non-docstring string
  constants** — which *are* its output, so it tests the property rather than a
  proxy for it.

A further test asserts the docstrings *are* allowed to name ATR, so the
distinction cannot be lost by a future widening.

### The one widening

`test_the_cli_reaches_neither_the_domain_nor_the_store` admits
`fmis.research_design` alongside the seven application-layer packages already
listed. The note records that it admits **strictly less** than the `fmis.swing_lab`
entry above it: that package opens a file in one module; this one opens none
anywhere and cannot reach the laboratory.

### Coverage — statement **and** branch, over CB's scope

| module | cover | uncovered |
|---|---|---|
| `research_design/__init__.py` | **100 %** | — |
| `research_design/artifact.py` | **100 %** | — |
| `research_design/dependence.py` | **100 %** | — |
| `research_design/numeric.py` | **100 %** | — |
| `research_design/render.py` | **100 %** | — |
| `research_design/resolution.py` | **100 %** | — |
| `research_design/verdict.py` | **100 %** | — |
| `research_design/models.py` | **99 %** | one partial branch: a validation loop that always runs to completion |
| `swing_lab/admission_power.py` | **98 %** | one line: a defensive raise for a `None` required-count, unreachable for a positive half-width and a positive effect |
| **total** | **99 %** | **1 statement and 2 partial branches of 1,171 / 408** |

**No coverage exclusion was added anywhere**, and the two misses are named rather
than excused. This is not 100 % and is not claimed to be.

---

## 22. Limitations

`CA_LIMITATIONS` (CB-1 … CB-6) travels inside the adapter and prints on every run.

- **CB-1 — SUMMARY-STATISTIC REPRODUCTION, NOT DATA-LEVEL.** CA's 155 paired
  differences are not persisted in this repository, so the per-observation
  dispersion is *inverted* from the published interval under an assumed
  correlation rather than measured.
- **CB-2 — THE INTRACLUSTER CORRELATION IS UNMEASURED.** Every projection is
  reported across a declared range, and the binding dimension is decided at the
  least favourable member of it.
- **CB-3 — THE INPUT INTERVAL IS ONE FAMILY'S**, `ca_null_matched_timing`. Three
  of the other four sealed families are wider.
- **CB-4 — NO EMPIRICAL DESIGN CURVE** for CA. The curve is modelled; points beyond
  155 carry `extrapolated=True`.
- **CB-5 — THIS ASSESSMENT CHANGES NO CA VERDICT.** `NO_EDGE` stands exactly as
  sealed.
- **CB-6 — THE INPUT INTERVAL IS ITSELF UNCERTAIN.** ±30 % realisation scatter at
  15 clusters; `4,823` is an order of magnitude, not four significant figures.

Additionally, and outside the adapter's list:

- **The more-clusters path assumes new symbols are exchangeable with the current
  15** (§11). If added symbols are progressively more correlated, 467 is a floor.
- **CB assesses a design; it cannot assess whether the design's question is the
  right one.** That +0.10 ATR is the bar, and that a 24-bar horizon measures a
  swing, are CA's decisions and are carried through unexamined.

---

## 23. The ten questions the brief asks

1. **Why was CA underpowered?** Its sealed criteria required a half-width below
   0.10 ATR and its design produces 0.5578 — a 5.6× shortfall. The binding
   dimension is the **cluster count**, not the observation count.
2. **Can CA's ~4,800 be reproduced?** **Yes — `REPRODUCED`.** 4,827 from the
   quoted half-width, 4,823 from the tabulated bounds, 0.6 % from the published
   figure.
3. **What is the actual limiting information dimension?** **The number of
   symbols.** `LimitingFactor.CLUSTER_COUNT`.
4. **Is "more symbols" better than "more years" here?** **Decisively.** More
   symbols reaches the bar at 467; more years cannot reach it at any size for any
   correlation above zero.
5. **How much effect can the current design resolve?** **0.5578 ATR** on
   development, 0.6915 on validation, 0.4581 on the holdout — every one of them
   4.6× to 6.9× the sealed bar.
6. **How much data would +0.10 ATR require?** 4,823 admissions **arriving as 467
   symbols**; 9,854 across 954 symbols for a genuine 80 % power guarantee.
7. **How sensitive is that to cluster assumptions?** Not at all on the
   more-clusters path; total on the more-years path (§13). Plus ±30 % realisation
   scatter on the input interval itself.
8. **Can the framework reject an impossible study before it runs?** **Yes.**
   `UNDERPOWERED` with a stated floor and a `reachable=False` growth path, from a
   prospective assessment that reads no outcome.
9. **Can future pre-registrations record the design assessment?** **Yes**, via a
   five-string citation, with the absence of a digest cycle proven from both ends.
10. **Is the framework reusable outside Swing?** **Yes.** The core names no
    instrument, no unit and no universe, in code — guarded by AST inspection.
    `admission_power.py` is one adapter, and the only place ATR appears.

---

## 24. The final decision

> **Research design verdict for the CA-style experiment: `UNDERPOWERED`.**
> **Binding dimension: `cluster_count`.**

> **IF WE WANTED TO TEST A +0.10 ATR SWING ADMISSION EFFECT HONESTLY, WHAT WOULD
> HAVE TO CHANGE?**

**Not "collect more data". Four things, and the first is not optional.**

1. **More SYMBOLS — roughly 467 at CA's observed density, from 15.** This is the
   binding constraint and the only one that moves the floor. More years on the
   current universe cannot resolve this effect at any sample size unless the
   between-symbol correlation is *exactly* zero. If added symbols are more
   correlated than the current set, 467 is a lower bound.
2. **Or a LARGER declared effect.** The current design resolves ~0.56 ATR on
   development. A study pre-registering a bar the sample can actually reach would
   be answerable today — and would be answering a different, much weaker question,
   since 0.56 ATR is 5.6× the round-trip cost.
3. **Or a DIFFERENT EXPERIMENTAL UNIT with more independent clusters.** Not more
   rows on the same symbols — report 0037 §12.3 already withdrew a claim built
   from 8,793 overlapping instants. The unit must add *clusters*.
4. **And, whichever is chosen, a PRE-REGISTERED DESIGN ASSESSMENT.** CA's seal
   carried no power calculation, and that omission cost the milestone its
   headline. The seam now exists and the gate runs without opening a holdout.

**`INTERPRETATION:` the most useful thing CB establishes is a negative one.** A
sixth, seventh and eighth hypothesis tested at n=155 on 15 symbols would each
return `NO_EDGE`, and each would mean nothing — **not because the hypotheses are
wrong but because no realisation of this universe can distinguish a +0.10 ATR
effect from zero.** That is now checkable before the compute is spent, from a
command that reads no market data.

---

## 25. Recommended next milestone — **do not begin it**

**CC — Universe expansion, scoped by the number CB produced.**

CA's §26 recommended widening the universe and estimated "roughly a 30×
increase — probably out of reach". CB sharpens that into an actionable target and
changes its shape: the requirement is **~467 symbols**, not ~30× the history, and
whether ~467 tradable symbols with sufficient depth *exist* in this market is a
question that can be answered in an afternoon by counting, before any replay.

**If they do not exist, that is the finding**, and it should be recorded before
another hypothesis is pre-registered — because it would mean this question is not
answerable on this market at this effect size, and the honest response is to change
the effect size or the unit rather than to keep testing.

Two smaller items CB leaves for whoever runs the next study: **measure the
intracluster correlation** (one number, obtainable from any run that persists its
paired differences, and it collapses the entire sensitivity table to one row), and
**persist observation-level differences** so the empirical design curve becomes
available and CB-1 and CB-4 both close.

---

## 26. Changed files

**New (`src/fmis/research_design/`):** `__init__.py`, `models.py`, `numeric.py`,
`dependence.py`, `resolution.py`, `verdict.py`, `artifact.py`, `render.py`

**New (`src/fmis/swing_lab/`):** `admission_power.py`

**Modified (`src/`):**
- `swing_lab/admission_matching.py` — `derive_seed` delegates; behaviour preserved
- `swing_lab/metrics.py` — `nearest_rank_quantile` delegates; behaviour preserved
- `swing_lab/robustness.py` — `concentration_of_magnitudes` delegates; behaviour preserved
- `pipeline/cli.py` — `fmits research design`

**New (`tests/`)** — 11 test files and 1 helper:
`research_design_helpers.py`, `test_research_design_models.py`,
`test_research_design_resolution.py`, `test_research_design_verdict.py`,
`test_research_design_artifact.py`, `test_research_design_render.py`,
`test_research_design_guards.py`, `test_research_design_hostile.py`,
`test_research_design_extraction.py`, `test_research_design_architecture.py`,
`test_swing_lab_admission_power.py`, `test_pipeline_cli_research_design.py`

**Modified (`tests/`):** `test_swing_lab_architecture.py` (module roster),
`test_trade_capture_architecture.py` (CLI import allowlist)

**Documentation:** this report; `reports/README.md`;
`docs/AI_HANDOFF/CURRENT_STATE.md`; `FMITS_PRODUCT_BACKLOG.md`.

`FMITS_PRODUCT_CHANGELOG.md` is **not** updated. CB delivers research
infrastructure — an instrument the owner can point at a study — and the product
policy reserves the changelog for user-visible trading capability. `fmits research
design` is a research surface on the same footing as `fmits research admission`,
which CA also declined to record.

---

## 27. Production safety

**CB altered no production decision, and the claim is checked rather than made.**

* `swing_setup`, `paper`, `trade_lifecycle`, `positions`, `portfolio`,
  `portfolio_risk`, `position_sizing`, `journal`, `market_regime`,
  `structural_trend`, `decision_context`, `evidence`, `risk`, `ledger`,
  `accounts`, `money` and `persistence` are **untouched** — none appears in the
  changed-file list.
* `CONFIRMATION_LOOKBACK_BARS` is `10` and `MINIMUM_AGREEING_FAMILIES` is `2`,
  verified by import after the milestone.
* BY's, BZ's and CA's pinned seals are byte-identical.
* `research_design` opens no file, reaches no network, reads no clock, calls no AI
  model and names no execution verb — each asserted.
* The dependency runs one way: `research_design` cannot import `swing_lab`, so a
  design gate can never become reachable from a trading engine.
* No order was placed, no exchange API contacted, no credential read, no
  portfolio, paper or risk state modified, and no risk limit changed.

---

## 28. Commit boundary

**Nothing was committed and nothing was pushed.**

`HEAD` remains `d1735bb`, `origin/main` remains `d1735bb`, 0 ahead / 0 behind.
The 16 pre-existing untracked research documents under `docs/design/` and
`docs/reviews/` are untouched.

Two commits are **prepared but not created**:

```
Commit A   feat(research): add statistical power and design framework
           src/ and tests/ only

Commit B   docs(product): record statistical power milestone
           documentation only
```
