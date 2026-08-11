# Research Harness Correction V1 — Hostile Review

| Field | Value |
|---|---|
| **Report number** | 0013 |
| **Title** | Research Harness Correction V1 — Hostile Review |
| **Date** | 2026-08-11 |
| **Report type** | Review |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | base `f9ddc54` + Milestone BC, committed locally, not pushed |
| **Status** | Final |

**Posture.** This review assumes the milestone is wrong and tries to prove it. Each attack in §2 is
stated as the strongest version of the accusation the evidence permits, then answered — with a
verdict of **refuted**, **partly upheld**, or **upheld**. Findings are in §3 with severities and
their disposition. Nothing is graded on effort.

Subject: [report 0012](0012_2026-08-11_RESEARCH_HARNESS_CORRECTION_IMPLEMENTATION.md) and
[the design record](../docs/design/RESEARCH_HARNESS_CORRECTION_V1.md).

---

## 1. Method

Read every new and modified source file line by line. Re-derived the warm-up arithmetic by hand
against `fmis.features`, `fmis.market_regime` and `fmis.pipeline.regime`. Re-ran the mutation suite.
Attacked the claims in the order the milestone brief lists them, then looked for the attacks the
brief does not list. Where an attack could be settled by measurement rather than argument, it was
measured.

---

## 2. Attacks

### 2.1 "The 'longer history' still has hidden warm-up truncation." — **refuted**

This is the attack that matters, because it is exactly what happened to AV, and a milestone that
merely *claims* to have fixed it deserves no credit.

The claim is not argued; it is instrumented. At **every measured instant**, for **every role**, the
harness records whether any feature returned no value and whether the role held fewer closed candles
than the harness requested. Across all seven runs of the 380-day, ten-symbol study:

```
measured_role_views_with_warming_features    0
measured_role_views_below_requested_window   0
insufficient_data_measured_instants          0
minimum_closed_candles_by_role               context 250, setup 250, execution 250
```

The minimum is the number that closes this attack. Not the mean — the minimum, over ~160,000
instants. If the derived prefix were short by a single weekly candle, the context role's minimum
would read 249.

Two further checks were made rather than trusted:

- **Is the derivation itself complete?** It reads each feature's own declared warm-up by computing it
  and inspecting the result metadata, and **raises** for a feature that declares none. A test
  (`test_a_feature_declaring_no_warmup_raises_rather_than_scoring_zero`) asserts the raise. A future
  feature therefore cannot warm up silently inside a measurement window.
- **Is the priming replay warm too?** This was a real gap, found during review and fixed before the
  evidence run — see finding F1. The prefix now covers it, and the synthetic fixture is built to
  reach back *exactly* as far as the derivation demands and not one bar further, so an off-by-one
  surfaces as an availability failure rather than a quietly shorter window.

**One residue, disclosed rather than defended.** The requested `limit` of 250 is treated as a warm-up
requirement, which is the strict reading. It is also the expensive one: it costs the study a year of
measurement window versus the EMA(200)-only reading. That choice is stated in the design record's
rejected-alternatives table, and it errs toward *more* warm-up, not less — the safe direction for
this attack.

### 2.2 "The research window is mislabeled." — **refuted**

`ResearchWindow` carries four instants; `is_warmup`/`is_measured`/`is_tail` partition time, and a test
asserts every instant satisfies exactly one. Measurement is half-open and the boundaries are exact to
the millisecond in test. The report states all four dates and the derived prefix beside them, and the
renderer prints them at the top of every page.

The label a hostile reader would attack — "380-day window" — is checked directly: the measured
observation count is 22,800, which is exactly 380 days × 6 four-hour bars × 10 symbols. Nothing is
lost to insufficiency, and nothing is counted that should not be.

### 2.3 "Tail data creates lookahead." — **refuted**

Stronger than a filter on output: the harness's instant list is built as
`priming_start <= instant < measurement_end` **before any composition call is made**, so there is no
code path on which a tail instant can produce an observation. Mutation M4 relaxes that bound and
dies.

The complementary property — that the tail is nonetheless readable for resolution — is tested by
construction rather than by luck: the test closes the measurement window two bars after a real
confirmation so the whole resolution path lies in the tail, then corrupts the tail. Observations come
back byte-identical; outcomes change. A test that merely corrupted "the end of the series" would pass
vacuously whenever every outcome resolved early, and would have here.

### 2.4 "The variant replay isn't really replay." — **refuted, by measurement**

The accusation would be that the override is applied somewhere downstream of the decision — a filter
in disguise. Three independent facts answer it:

1. `research_confirmation_max_age` is consumed inside `evaluate_setup`, at the line computing
   `break_is_stale`, before `state` is assigned. Mutation M7 shifts that comparison by one and dies.
2. Under a stricter bound the **`CANDIDATE` count rises** as the `CONFIRMED` count falls
   (3,002 → 4,803 and 1,966 → 165 from bound 10 to bound 0). A filter would delete confirmations and
   leave candidates untouched. Deferral is visible in the aggregates.
3. **28 confirmations at bound 0 occur at a different, later instant than the baseline's**, on the
   same opportunity, with a different reference price, stop and target. A filter cannot manufacture a
   row that was never in the baseline.

And the fidelity direction of the same attack — *does the override change anything it shouldn't?* —
is settled by replaying it at the production constant: 45 baseline confirmations, 45 variant
confirmations, 45 unchanged, 0 shifted, 0 lost, 0 new, identical outcomes across 22,860 observations.

### 2.5 "Production policy was accidentally changed." — **refuted**

Thirty tests, from four independent directions: default identity (field-by-field at five break ages),
signature containment (checked against real signatures, including a `**kwargs` check so an override
cannot arrive invisibly), call-site containment (a scan of `src/fmis/**`), and self-identification
(`policy_id` and a `RESEARCH OVERRIDE ACTIVE` limitation line). Mutations M5, M6 and M10 each attack
this from a different angle and all die.

The failure mode most likely to be missed — `research_confirmation_max_age=0` being folded to
production by a truthiness check — is mutation M5, and it dies.

One real defect existed here and was fixed before the evidence run: the research `policy_id` was not
applied on the `CANDIDATE`/`CONFIRMED` return path. See finding F2.

### 2.6 "The corrected baseline is no longer comparable to AV's." — **partly upheld, and the report says so first**

This is correct, and it is the most important honest statement in the milestone. Report 0012 §7 puts
the two columns side by side and then spends more words explaining why they must not be subtracted
than presenting them. Three things differ at once — window, identity, and the sample size that
follows from the identity — and only one is the window.

The attack's sharper form is: *does the milestone quietly bank the 8.7-point target-first difference
as an improvement?* It does not. The report states the difference "is not evidence of anything, and
is reported here only so nobody has to compute it and wonder." No product document, changelog entry
or backlog row cites it.

**Upheld portion:** the brief asked for differences "caused ONLY by corrected warm-up/window
semantics", and that decomposition is not available, because the identity correction is entangled
with the window correction in the same run. The report names the entanglement rather than pretending
to a clean attribution. A reader wanting the window effect alone cannot get it from this evidence.

### 2.7 "Setup identity across variants is dishonest." — **refuted, and it is the reverse**

An opportunity is a maximal run of same-direction observations. The accusation would be that this is
chosen to make variants look similar. The opposite is true, and it is checkable: because the key
depends only on direction — which the override provably cannot touch — the decomposition is
**identical across every variant** (52 unique opportunities, 22,800 measured observations, 17,832
`WAIT`, in all seven runs). A test asserts the invariance directly. It is that invariance which makes
"lost" and "confirmed later" mean anything; a key that shifted with the variant would let any
difference be explained away as re-identification.

The genuinely uncomfortable part is stated rather than buried: **AV's identity is broken**, measured
at 549 "unique setups" from 552 directional observations, and BC discloses it in its own
implementation report against its own predecessor's published numbers.

### 2.8 "Data concentration still invalidates generalization." — **partly upheld**

The improvement is real and measured: the largest five-day cluster falls from 49.0 % to 11.4 %,
distinct confirmation days rise from 23 to 35, and outcomes appear in 10 months across 2 calendar
years instead of 2 months in 1. The brief's own threshold — "do not claim generalization unless the
concentration materially improves" — is met on this measure.

**Upheld portion, and it is not small.** The sample is 44 outcomes. Ten crypto majors co-move; 60-bar
evaluation windows overlap; DOTUSDT alone contributes 25 % and AVAXUSDT contributes none; five
outcomes still fall inside one five-day span. Nothing in this milestone makes 44 correlated
observations sufficient for a policy decision, and nothing in it claims so. `BC-8` says this on every
report the harness prints.

### 2.9 "Denominators are misleading." — **refuted**

Every reported denominator reconciles, and the reconciliation is test-enforced rather than checked
once: state counts sum to measured observations; outcome statuses sum to evaluated outcomes; segment
observation counts and segment outcome counts each sum to their totals; symbol and side cohorts each
sum to evaluated outcomes; at most one outcome exists per opportunity. `VariantComparison` and
`PostFilterComparison` **refuse to be constructed** unless their fields reconcile, so a comparison
that does not add up is unrepresentable rather than merely unlikely.

The subtler attack — that "measured" quietly includes priming — is mutation M13, which dies on the
model's own invariant.

Two denominators required a definition rather than a proof, and both are now stated in the code:
`unique_opportunities` counts opportunities *present in* the window, not those beginning in it; and
an opportunity first confirmed during priming contributes no outcome. That second point was a real
defect during development — finding F3.

### 2.10 "The max_age = 2 result is being sold as better." — **refuted**

There is no ranking anywhere. `research_compare` computes differences and has no function that orders
variants. The renderer prints variants in the order supplied. The report labels the table "sensitivity
evidence" and states that no winner is selected.

The evidence also does not support such a sale even if someone wanted to make it. Target-first across
bounds reads 53.8 / 53.8 / 60.0 / 53.1 / 61.3 / 51.7 / 51.9 % — non-monotonic, on 31–44 outcomes per
row, with overlapping populations. Anyone reading a winner out of that is reading noise, and the
non-monotonicity is printed rather than smoothed.

### 2.11 Attacks the brief does not list

**"The post-filter comparison is rigged to make BA look bad."** Refuted by construction: at bound 10
the two methods agree 100 % (45/45), which is the correct answer and would not appear if the
comparison were biased. The disagreement grows only as the bound tightens, which is exactly where BB
predicted the method fails. At bound 2 the filter keeps 21 of 45 while the replay produces 39; 18
confirmations exist only in the replay; agreement is 53.8 %. Read as BA would have read it, the
filter reports 12/6 target/stop — 66.7 % — against the replay's 19/12 — 61.3 %, on a population
little more than half the size.

**"The performance optimisation changed the results."** `prepare_replay_index` is a binary search
replacing a linear scan. A test asserts byte-identical transport responses with and without it across
four instants and three intervals; mutation M14 perturbs the boundary by one and dies; unsorted input
is rejected rather than searched.

**"The evidence run used stale bytecode."** This is a live risk on this machine and was found during
the milestone — see finding F7. The entire evidence run was re-executed on freshly compiled bytecode
after the discovery.

---

## 3. Findings

Severity: **P0** wrong result reported as right · **P1** materially misleading · **P2** correctness or
honesty gap in a stated claim · **P3** clarity.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| F1 | **P1** | Identity-priming instants were replayed on a prefix that did not cover them, so the priming window itself analysed roles one to ten days short of the derived requirement. Priming is not counted, but the tracker it primes decides how the first opportunity at the boundary is attributed — reintroducing, one bar outside the window, the defect being removed inside it | **Fixed.** The prefix now covers `identity_priming_bars`; `required_from_by_interval` adds any warm-up beyond the derived prefix to every interval. The study's `measurement_start` moved 2025-07-07 → 2025-07-17 as a result, and the whole evidence run was redone |
| F2 | **P1** | The research `policy_id` was applied on the three `WAIT` return paths but **not** on the `CANDIDATE`/`CONFIRMED` path, so the assessments that actually differ under an override were the ones not marked as research output | **Fixed.** `policy_id` and the research limitation line are applied on every return path; a test asserts every observation in an override run carries the marker |
| F3 | **P1** | "First confirmation" was re-derived in metrics as "first *measured* `CONFIRMED` observation", which readmitted an opportunity whose real first confirmation happened during priming — a decision made outside the window counted inside it, and `confirmed_without_geometry` silently absorbing the discrepancy | **Fixed.** `is_first_confirmation` is recorded on the observation at the moment the tracker decides it; metrics read the flag. Two such opportunities exist in the study and are reported in run metadata |
| F4 | **P2** | Mutation M11 (every observation assigned to the first segment) **survived** the first mutation pass: the reconciliation tests were satisfied by a total misclassification, because the sums are the same either way | **Fixed.** A membership test asserts the recorded segment is the one that actually contains the instant, and that every segment is populated. M11 now dies |
| F5 | **P2** | `SeriesAvailability.candle_count` was presented as a measured count but is inferred from first and last candle at the interval — an upper bound that a provider gap would make wrong | **Fixed.** Renamed `implied_candle_count`, documented as an upper bound, with the note that the satisfiability decision rests on the reach-back date, not the count |
| F6 | **P2** | A series with no candles at all rendered its shortfall as `timedelta.max` — "short by 999999999 day(s)" — which reads as a bug rather than as missing data, in the one report a reader consults when something is wrong | **Fixed.** Empty series are reported separately as "no candle at all"; a test asserts the number never appears |
| F7 | **P2** | A git-ignored `__pycache__` entry for `scan_report.py`, dated 2026-08-07, was compiled from a source using `,.2g` where the tracked file says `,.6g`, with a recorded mtime and size matching the current file — so Python kept using it. It caused two test failures recorded on the product backlog since AU as "a float-formatting flake", and made `fmits scan` print prices in scientific notation on this machine | **Resolved, no source change.** Caches cleared; the full suite is green for the first time since AU. **The evidence run was re-executed from scratch on fresh bytecode**, because a measurement taken under unknown stale bytecode is not a measurement |
| F8 | **P3** | The report line listing measured observations per segment could exceed the 78-column page with many segments | **Fixed.** Wrapped |
| F9 | **P3** | `unique_opportunities` counts opportunities present in the window, not beginning in it, and can therefore exceed `confirmed_opportunities` for reasons other than missing geometry | **Fixed by documentation.** Stated on `ResearchMetrics` |

**Open, disclosed, not fixed** — each is a stated limitation rather than a defect:

| # | Item | Why not fixed |
|---|---|---|
| O1 | The common measurement window is 380 days because AVAXUSDT's weekly history begins 2020-09-21 | The data does not exist. A per-symbol window would be longer and would make symbols incomparable; the trade is recorded in the design record and as `BC-3` |
| O2 | 44 outcomes, ten co-moving symbols, overlapping evaluation windows | Not solvable by a harness. Reported on every page as `BC-8` |
| O3 | AV's window-relative identity remains broken **in AV** | Fixing it would silently rewrite a published milestone's numbers. Disclosed in report 0012 §7 instead |
| O4 | The window effect cannot be separated from the identity effect in this evidence | Would require a fourth run under AV's identity and BC's window. Named in §2.6 rather than glossed |

**No P0 findings. Every P1 and P2 is fixed.**

---

## 4. What would change this review's verdict

Stated so a later reader can check rather than trust:

- A measured instant reporting a non-zero warming-feature or short-window count would reopen §2.1.
- A production call site acquiring the override, or a live result carrying the research `policy_id`,
  would reopen §2.5 — both are test-enforced, so it would show as a failure first.
- Any document citing BC's 53.8 % target-first rate as an improvement over AV's 45.1 % would make
  §2.6's partly-upheld verdict a P1.
- A future feature with a longer warm-up than EMA(200) would lengthen the prefix automatically and
  shorten the common window; the derivation would report it, but nobody is watching for it.

---

## 5. Verdict

The milestone does what it says. The two BB findings are corrected, the corrections are measured
rather than argued — the per-instant warm-up verification and the bound-10 replay identity are the
two measurements that carry the milestone — and a third defect in AV was found and disclosed rather
than quietly worked around.

The uncomfortable results are reported in the same voice as the comfortable ones: the sample is
small, the symbols co-move, one symbol contributes a quarter of the outcomes and another contributes
none, the corrected baseline is not comparable to AV's, and the variant table is non-monotonic noise.
Nothing in the milestone recommends a policy change, and nothing in it should be read as supporting
one.
