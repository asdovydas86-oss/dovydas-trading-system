# AP-D1 / AP-D2 Investigation — Independent Hostile Review

**Milestone:** AQ (ADR Phase 1)
**Audited artifact:** [`docs/design/AP_D1_D2_INVESTIGATION.md`](../design/AP_D1_D2_INVESTIGATION.md)
(904 lines, untracked at review time)
**Audited commit:** `75a4f40`, working tree clean apart from the artifact under review
**Contracts checked against:** [`TRADING_DOMAIN_ARCHITECTURE_V1.md`](../design/TRADING_DOMAIN_ARCHITECTURE_V1.md)
v1.2 · [ADR-0027](../adr/ADR-0027-memory-and-decision-archive-persistence-schema.md) ·
[ADR-0019](../adr/ADR-0019-level-crossing-foundation-v1.md) ·
[ADR-0006](../adr/ADR-0006-provider-adapter-contract.md) ·
[ADR-0005](../adr/ADR-0005-ingestion-boundary-strictness.md) ·
[ADR-0016](../adr/ADR-0016-structural-sequence-state-history-foundation.md) ·
[ADR-0013](../adr/ADR-0013-swing-relationship-foundation.md) · the live source under `src/fmis/`

**Method.** Adversarial by construction. Both decisions were re-derived from first principles without
reading the investigation's recommendations first; the investigation was then treated as an external
proposal to be falsified. Every numeric or behavioural claim — the investigation's and this review's —
was **executed against this repository's own code**, not reasoned about. Eight probes were run in a
throwaway interpreter session; each is reproduced inline below with its output. **No file in the
repository was modified. No ADR was written. Nothing was committed.**

---

## Table of contents

- [1. Executive verdict](#1-executive-verdict)
- [2. Major findings](#2-major-findings)
- [3. Critical issues](#3-critical-issues)
- [4. Strong recommendations](#4-strong-recommendations)
- [5. Minor improvements](#5-minor-improvements)
- [6. Long-horizon failures](#6-long-horizon-failures)
- [7. ADR and principle compliance audit](#7-adr-and-principle-compliance-audit)
- [8. Things that should NOT be changed](#8-things-that-should-not-be-changed)
- [9. Final recommendation](#9-final-recommendation)

---

## 1. Executive verdict

**Both headline recommendations survive falsification — but neither survives as written, and the
investigation's own risk ranking is wrong.**

| | Verdict |
|---|---|
| **AP-D1 → exactness by durability class** | **Survives.** Attacked from six directions and did not break. But its Part 4 statement contains one rule — *"no quotient is ever a stated field"* — that **directly contradicts three mandatory rows of `AP` §25.2** and would make the Swedish tax capture contract unimplementable if adopted verbatim (**C2**) |
| **AP-D2 → forward-only read-time upcasting** | **Survives as a mechanism.** But as literally stated it **violates ADR-0027 §2**, the only reproduction guarantee AO shipped (**C3**), and it is **mutually incompatible with the investigation's own golden-test recommendation** (**C4**) |
| **The risk register** | **Mis-ranked.** N1 (`0.10` vs `0.1`) is presented as the top critical. It is real, but it is a *narrow instance* of a larger defect the investigation did not find: **`AP` §11.2's authoritative field set breaks Trade idempotency in three independent ways**, demonstrated below (**C1**) |
| **The option matrix** | **Structurally unsound.** Options A and C are not alternatives — the investigation says so itself in a footnote and then scores them against each other anyway, awarding C an advantage ("smallest blast radius") that is provably identical for both (**M1**, **M2**) |

**The single most important finding.** The investigation frames its top risk as a hazard to be closed
by a clause. Probe 4 shows the opposite: **`float` normalises `0.10` and `0.1` to identical bytes by
construction; exact-decimal-as-text does not.** The identity hazard is not inherited from the status
quo — it is *created by the recommendation*. That does not make the recommendation wrong, but it
belongs in the matrix as a cost of exactness, not in an appendix as a clause to remember.

**What this review did not find.** No circular dependency, no import-direction violation, and no
contradiction with ADR-0005, ADR-0006, ADR-0013 or ADR-0016. Two recommendations were attacked
specifically for ADR compliance and came back clean (§7).

---

## 2. Major findings

| # | Severity | Finding | Investigation's position |
|---|---|---|---|
| **C1** | **Critical** | `AP` §11.2's authoritative field set makes `event_id` depend on `recorded_at`, `source` and `capture_schema_version`. **Trade idempotency is broken three ways**, demonstrated by digest. A third decision — *what the identity digest covers* — sits between AP-D1 and AP-D2 and is scheduled nowhere | **Missed.** Found only the narrow `0.10`/`0.1` instance |
| **C2** | **Critical** | *"No quotient is ever a stored field"* contradicts `AP` §25.2 rows for `fx_rate_to_tax_currency`, reward acquisition value and `HypotheticalOutcome.r` — all three **mandatory, all three frozen, all three quotients** | **Self-contradictory.** §1.3.6 lists them as quotients; Part 4 forbids storing quotients |
| **C3** | **Critical** | Forward-only upcasting **violates ADR-0027 §2** as written: `decode(read(path)) == the value that was archived` is false once a v3 reader upcasts a v1 record | **Missed** |
| **C4** | **Critical** | The recommended byte-identical goldens require a **writer** per historical version, not a reader. `AP` §5.7 rule 2 promises readers only. Q1 and Q11 are mutually incompatible as stated | **Missed.** Q11 is proposed as the cheap way to protect Q8 |
| **C5** | **High** | Mixed `Decimal`/`float` **`==` is `False`** — so ADR-0019's *"exact equality is a `TOUCH`"* becomes **structurally unreachable** across the boundary, silently, inside §8.5's counterfactual evaluator | **Understated** as "exact-but-surprising" for `>` |
| **S2** | **High** | §24.3's CI test **cannot** detect a rebuildable projection disagreeing with a frozen artifact after a policy-version change — it recomputes both sides under the current policy | Missed |
| **S3** | **High** | The migration guarantee guarantees *readability*, not *computability*. The genuinely irreversible risk is **capture completeness in v1**, not the migration mechanism | Partially seen (§2.3.3), not generalised |
| **S4** | Medium | The stated reason for rejecting a hash chain — *"backfilling a forgotten trade invalidates every subsequent link"* — is **factually wrong** for a chain over insertion order | Wrong justification, right conclusion |
| **S6** | Medium | A `Correction` to an old event **silently changes an already-filed tax year's figures** under average-cost basis. Neither document names it | Missed by both |

---

## 3. Critical issues

### C1 — Trade idempotency is broken three ways, and the investigation found only the fourth

**Claim under test.** `AP` §11.5: *"`event_id` is derived from the canonical digest of the
authoritative fields… Re-submitting the same trade produces the identical `event_id`."*

**§11.2's authoritative field list includes `recorded_at`, `source`, `asserted_by` and
`capture_schema_version`.** None of those is a property of the economic event. Probe 3, run against
this repository's own `canonical_dumps`:

```
same fill, different recorded_at : 56f6736253948c92  81777ac6c1d470e6   *** DIFFERENT ***
same fill, MANUAL vs EXCHANGE_API: 56f6736253948c92  159e5be480c24016   *** DIFFERENT ***
same fill, capture v1 vs v2      : 56f6736253948c92  99a3f99e2fbbd560   *** DIFFERENT ***
```

Three separate, ordinary scenarios each produce a **second position-moving ledger event** for one
fill:

| Scenario | Frequency | Consequence |
|---|---|---|
| The owner re-enters a trade after a crash, twenty minutes later | Routine | Position doubled. §11.5's promised idempotent no-op does not fire |
| §32 step 4's exchange sync imports a fill the owner already typed | **Certain, by design** | Every manually-recorded trade double-counts on the day sync ships |
| A `capture_schema_version` bump re-records the same fill | Once per version | Identity is version-dependent, so `event_id` is not stable across AP-D2's own migration |

The second is the worst: `AP` §12.5 and §23.3 *plan* for reconciliation between manual entry and
exchange import, and the identity scheme guarantees the two can never be recognised as the same event.

**Why the investigation missed it.** It reasoned about the *representation* of amounts (N1) without
asking **what the digest covers**. That is a third question, and it belongs to neither AP-D1 nor
AP-D2:

- AP-D1 decides *how an amount is written*.
- AP-D2 decides *how a record evolves*.
- **Nothing decides which fields constitute economic identity** — yet `AP` §11.5 already assumes an
  answer, and §31.1 assigns it to no ADR. AP-D3 (ledger event taxonomy) is the closest owner and its
  one-line scope does not mention identity.

**This makes the investigation's sequencing claim (§4.3) incomplete rather than wrong.** AP-D1 does
precede AP-D2. But an unscheduled decision sits between them, and it is the one that determines
whether the ledger can count.

**The repair, stated as a shape and not a decision.** ADR-0027 §3 already solved this exact problem
once: `content_digest` deliberately **excludes** `archived_at` because *"a filing timestamp must not
affect whether two archive calls of the same analysis are recognised as duplicates."* `recorded_at`
is `archived_at` under a different name. The precedent is in the repository; it simply was not carried
across to the ledger.

### C2 — "No quotient is ever a stored field" contradicts the design's own freezing policy

**The investigation's Part 4 states the rule as binding.** `AP` §25.2 mandates storing three
quotients, each marked *"Never"* recomputable:

| §25.2 row | Is it a quotient? | Why it must be frozen |
|---|---|---|
| `FX rate to tax currency` — captured at capture | **Yes**, definitionally (quote ÷ SEK) | §22.2 item 10: re-deriving later changes completed reports |
| `Reward acquisition value` — captured at capture | **Yes** (value per unit at receipt) | §22.2 item 9: *"uncomputable retroactively"* |
| `Hypothetical outcome and its path` — frozen at horizon | **Yes** — `HypotheticalOutcome(r, …)` carries an R-multiple (§17.3) | §25.3: candle history may become unfetchable |

So the rule, adopted verbatim, **forbids the two fields §22.2 calls the urgent reason the capture
contract cannot wait**. That is not a wording problem; it inverts the design's most load-bearing
tax requirement.

**The distinction the rule is missing** is one the investigation actually draws in §1.3.6 and then
loses in Part 4: the question is not *"is this value a quotient?"* but *"is this value **computed by
us** from inputs we still hold?"*

| Kind | Example | Store it? |
|---|---|---|
| **Asserted quotient** — supplied by a venue or a rate source, not computed here | `fx_rate_to_tax_currency`, reward acquisition value | **Must be stored.** It is an `ASSERTED` fact (§5.2), and its inputs were never ours |
| **Frozen derived quotient** — computed here, from inputs that will not survive | `HypotheticalOutcome.r`, MAE/MFE | **Must be stored**, and §25 says exactly why |
| **Recomputable derived quotient** — computed here, from inputs we permanently hold | `average_entry`, expectancy, weights, headroom | **Must not be stored.** This is the real rule |

Only the third class was ever the target. The correct formulation is therefore something closer to:

> **No quotient is stored *in place of* the exact inputs it came from.** Where a quotient must be
> frozen (§25), the exact inputs that produced it are frozen beside it.

That preserves the investigation's genuine insight — the average-entry drift chain in §1.3.5 — without
breaking §22.

### C3 — Forward-only upcasting violates ADR-0027 §2

**ADR-0027 §2, the only reproduction guarantee AO shipped:**

> **Snapshot reproduction** — `decode(read(path)) == the value that was archived`, structurally, by the
> model's own `__eq__`. **Guaranteed.** This is the whole of AO v1.

Under read-time upcasting, a v1 record decoded by a v3 build returns a **v3 model instance**. A v3
model with three added fields is not `__eq__` to the v1 value that was archived — it cannot be; the v1
class may no longer exist. **The guarantee is false the moment the first version bump ships.**

This is not fatal and it is not an argument against Option A. It is an argument that **AP-D2 must
restate capability 1**, because the current wording will silently become untrue:

| Formulation | Survives upcasting? |
|---|---|
| *"`decode(read(path))` equals the archived value by `__eq__`"* (ADR-0027 §2 today) | **No** |
| *"the archived **bytes** are unchanged, re-readable, and digest-verifiable forever"* | **Yes** — and this is what Option A actually delivers |
| *"the archived value is recoverable **at its own version**"* | Yes, but only with a version-pinned reader **and** model retained — see C4 |

The investigation asserts in its matrix that Option A preserves *"capability 1 unconditionally."*
**That is the claim this review breaks.** Option A preserves *byte* reproduction unconditionally and
*model* reproduction not at all. The distinction is exactly the kind ADR-0027 §2 was written to be
honest about, and it must not be lost on the way into AP-D2.

### C4 — The two AP-D2 recommendations are mutually incompatible

The investigation recommends both:

- **Q1** — forward-only read-time upcasting (Option A);
- **Q11** — golden tests asserting *decode → re-encode → **byte-identical***, praised as *"the cheapest
  possible way to make Q8's hazard impossible."*

Probe 7 runs the combination against this repository's own encoder:

```
v1 on disk : {  "price": "59020.13",  "quantity": "0.15",  "schema_version": 1 }
re-encoded : {  "fx_absent_reason": "not captured before v2",  "fx_rate_to_tax_currency": null,
                "price": "59020.13",  "quantity": "0.15",  "schema_version": 3 }
byte-identical re-encode possible? False
```

An upcasting reader **cannot** re-encode to the original bytes, because upcasting is precisely the act
of producing a different (newer) shape. To keep byte-identical goldens the project must retain a
**version-pinned writer for every historical version** — which is strictly more than `AP` §5.7 rule 2
promises (*"ships a reader for all prior versions"*) and materially changes Option A's maintenance
cost, the axis on which the investigation's matrix scores it best.

**Three consistent resolutions exist; the ADR must pick one.**

| Resolution | Protects Q8 (frozen encoder)? | Cost |
|---|---|---|
| Goldens assert **decode succeeds and matches a frozen expected structure** | **No** — the encoder is unprotected, which was the whole point of Q11 | Cheapest |
| Goldens assert **the stored bytes re-hash to the stored digest** (no re-encode at all) | **Yes**, and better — it tests the actual invariant | Cheap. **This appears to be the right answer** |
| Keep per-version writers and assert byte-identical re-encode | Yes | Doubles §5.7 rule 2's obligation |

The third is what the investigation implicitly recommends without noticing. The second achieves Q8's
goal directly: if `canonical_dumps` changes, the stored digests stop matching, and the golden corpus
fails loudly — which is the guard that was wanted.

### C5 — Mixed `Decimal`/`float` equality silently disables ADR-0019's `TOUCH`

The investigation notes that mixed comparison is *"exact-but-surprising"* and gives `>` as the
example. Probe 5 shows the sharper case:

```
Decimal('59020.13') >  59020.13  ->  True
Decimal('59020.13') == 59020.13  ->  False      (the float is really 59020.12999999999738065…)
```

ADR-0019 makes exact equality **load-bearing**: *"exact equality is a `TOUCH` and only strict `>`/`<`
is a breach."* If a proposal's `stop_loss` is an exact decimal and the counterfactual evaluator
(§8.5) compares it against `float` candle prices from `fmis.level_crossing`, then:

- `TOUCH` becomes **structurally unreachable** — it can essentially never fire;
- every touch silently classifies as either a breach or nothing;
- `AMBIGUOUS_BAR` (§8.5's carefully-designed honest answer) is reached less often than it should be.

This lands on the exact code path the design is proudest of reusing — §34.5 calls the evaluator *"a
consumer of `fmis.level_crossing` rather than adding mathematics."* The reuse is correct; the
type boundary silently changes the engine's semantics.

**This raises the priority of the investigation's own Q3** (the named crossing rule) from a clause to
a correctness precondition: *convert once at a named point, and never compare across the boundary* is
not tidiness — it is what keeps ADR-0019's contract intact.

---

## 4. Strong recommendations

**S1 — Carry the identity hazard as a cost of exactness, not as a clause.** Probe 4:

```
float:   "0.10" and "0.1"  ->  identical canonical bytes  (True)
decimal text: "0.10" vs "0.1" ->  different canonical bytes (False)
```

`float` normalises by construction. The proposed fix **introduces** a corruption class the status quo
does not have. The recommendation still wins on other grounds, but a matrix that omits this is
selling.

**S2 — §24.3's CI test gives false assurance across policy versions.** The test *"deletes every
rebuildable projection and disposable aggregate, recomputes them, and asserts identical results."* It
recomputes **both sides under the current policy**, so it cannot detect the failure that actually
matters over ten years: a dust-threshold or classification policy version changing, a re-fold
producing different Positions, and **frozen Decision Episodes derived from the old fold silently
disagreeing with the live projection**. The archive would then hold two incompatible truths with
nothing reporting it. A second test is needed — one that re-folds under each historical policy version
and asserts agreement with the artifacts frozen under it.

**S3 — The blocking risk is capture completeness, not migration mechanism.** `AP` §5.7 promises
*"never breaking a reader."* The product need is *"never losing the ability to compute."* These
diverge: a v1 record missing `fx_rate_to_tax_currency` upcasts perfectly to v3 and is **still
permanently untaxable**. The migration guarantee does nothing for that class, and §22.2 items 9–10 are
already the design's acknowledgement of it — locally, without generalising. The generalisation is the
ADR-worthy statement: *any field that is unrecoverable if missed must be in v1, and no migration
mechanism can substitute.* This slightly **de-escalates** AP-D2's mechanism choice (all three options
are survivable) and **escalates** the capture-contract field list, which is the genuinely irreversible
half. The investigation gets the ordering of urgency backwards.

**S4 — The hash-chain rejection uses a wrong reason.** The investigation rejects it because *"any
repair, re-order or backfill of a historically missed trade invalidates every subsequent link."*
A chain over **insertion order** (`recorded_at`) is not invalidated by backfill: a forgotten trade
discovered in 2029 appends at the end with a 2026 `occurred_at`, and the chain over insertion order is
untouched. §5.1's corrections are appends too, and equally harmless. The conclusion (don't build one)
is probably right for a single-user system; the stated reason should not survive into an ADR, because
a future reviewer will check it and correctly conclude the analysis was thin.

**S5 — `code_version` must be excluded from the identity digest, explicitly.** The investigation
recommends stamping it on every captured artifact (its N13) without saying where. Probe 8:

```
without code_version      : c805b8509d899c04
with code_version 75a4f40 : 67247d33080aea28
with code_version a1b2c3d : 4bffd6a2b5a4fb62
```

Inside a content-derived identity, the same economic fact acquires a new `event_id` **on every
checkout**. The recommendation is good; unqualified, it is C1 with a fourth mechanism.

**S6 — A correction silently rewrites an already-filed tax year.** Under §22.4's average-cost basis,
basis is a running quotient over the entire ledger. A `Correction` to a 2026 event therefore changes
2027–2031 basis and every figure in years already reported. The design archives issued reports (§25.2)
and versions rule sets (§22.3) — both correct — but **nothing detects or reports that a re-run now
disagrees with a filed report**. §22.5's completeness report covers unclassifiable events, not this.
A "reports affected by this correction" check is a small addition and an audit requirement if any
obligation is later confirmed.

**S7 — Specify the decode grammar, not only the encode form.** The investigation's Q2 fixes the
canonical form for *writing*. ADR-0005 §3's ethic — *"numeric strings are rejected: silently parsing
`1e3` or `1,000` is exactly the repair this layer exists to prevent"* — demands the mirror rule for
*reading*: a decoder must reject `" 0.1"`, `"+0.1"`, `"1e-1"` and any non-canonical spelling rather
than accept-and-normalise. Digest verification catches a hand-edited record, but not a
non-canonical value arriving through a statement-import adapter.

**S8 — "No published byte is ever rewritten" is already false, and needs its carve-out.**
`append_manifest_entry` (`src/fmis/archive/manifest.py:125`) *"atomically rewrit[es] the whole file"*
on every single append, and §24.4 plans to re-partition it. The manifest is legitimately a rebuildable
projection — but **ADR-0027 assigns it no durability class**, and Option A's absolute framing will
collide with the first manifest change. State it: records and ledger files are never rewritten; the
manifest is a rebuildable index and may be.

---

## 5. Minor improvements

**M1 — The matrix conflates two orthogonal axes.** AP-D1's real decision space is two-dimensional:

| | Axis 1 — representation | Axis 2 — what is stored |
|---|---|---|
| | `Decimal` · integer minor units · `float` | asserted values only · all values including derived |

Options A and B differ on axis 1; option C is a position on axis 2. The investigation admits this
(*"A and C are not exclusive"*) and scores them against each other anyway, which hides legitimate
combinations — integer minor units **with** durability-class storage is never considered.

**M2 — C's "smallest blast radius" advantage is unearned.** Both A and C keep `Decimal` above L7, so
both leave the three guard tests untouched and `fmis.data` unchanged. The differentiator awarded in
the matrix is identical for both options.

**M3 — The performance benchmark used the fast path, but the conclusion holds.** The investigation
measured repeated addition of one same-exponent constant. Re-measured on harder workloads (probe 1):

```
same-exp Decimal add :  42.9 ns/op                                   (what was measured)
mixed-exp Decimal add:  52.3 ns/op   float add: 37.4 ns/op   -> 1.4x
Decimal mul+quantize : 153.9 ns/op   float mul+round: 188.5 ns/op -> 0.8x   (Decimal is FASTER)
200k Decimal(str)    :   13 ms       200k float(str):  9 ms      -> 1.4x
projected cold-start fold, 28k events x ~6 amounts:  ~11 ms
```

The conclusion — performance is a non-argument — **is confirmed and strengthened**: `Decimal`
multiply-and-quantize is *faster* than `float` multiply-and-round, and the §24.2 cold-start fold costs
about 11 ms at ten-year volumes. The method was thin; the answer was right.

**M4 — Option B's registry mutation is not hypothetical.** The investigation notes a wrong exponent as
a silent corruption risk. Sharper: `AP` §11.7 lists **`Adjustment` — split, rebase, rename** as an
anticipated event kind, so re-denomination is a *modelled domain event*, not an edge case. Under
integer minor units, a rebase retroactively reinterprets every stored integer for that asset.

**M5 — Integer minor units break the export contract, not just the registry.** Probe 6:

```
wei as JSON int : 1000000000000000007   (survives Python round-trip: True)
exceeds 2^53    : True  ->  as float: 1e+18, loss: 7 units
```

Any JSON-float consumer — JavaScript, Excel, most CSV tooling — silently truncates. This affects §23's
column contract under **every** option, since exported amounts must be text regardless; but it is an
additional strike against B.

---

## 6. Long-horizon failures

Failures that appear only after time, versions, volume or model generations.

| Horizon | Failure | Detected by anything today? |
|---|---|---|
| **~5 years / 3–4 versions** | The v-N domain model has accreted a dozen optional fields whose absence is version-dependent; every consumer must branch on each. This is Option A's real cost and the investigation gives it one line | No |
| **~5 years** | A cohort spanning schema versions: a dimension introduced in v3 yields *absent*, not zero, for pre-v3 episodes. §20.2 gives **tag terms** an `introduced_at` so coverage gaps are reported — there is **no analogue for schema fields**, and §20.3's `InsufficientSample` guard does not fire because `n` is large. **Every bias metric silently degrades across a version boundary** | **No — and this is the sharpest AI-learning consequence found** |
| **~5 years** | A policy version change (dust threshold, classification) makes the live fold disagree with frozen episodes. §24.3's CI test passes anyway (**S2**) | No |
| **~10 years** | A record type written for three months and abandoned still requires a maintained reader forever under Option A's "never remove." Frozen generations (Option C) handle this; the investigation treats C as an escalation for breaking changes only | No |
| **~10 years / thousands of trades** | Manual entry and exchange sync double-count every overlapping fill (**C1**), and the divergence is only visible as a reconciliation gap the design classifies as `DISPUTED` — a symptom, not the cause | No |
| **Multiple ADR revisions** | ADR-0027 §2's guarantee quietly becomes untrue at the first version bump (**C3**) with no test asserting it | No |
| **Multiple AI model generations** | Once a `PersonalInsight` is `CONFIRMED`, §18.2 feeds it into every subsequent context package, which shapes proposals, which become episodes, which become that insight's later evidence. **After confirmation the sample is no longer independent**, so §20.5's lesson-effectiveness metric measures *compliance*, not truth. R14 covers ossification and §20.7 covers look-ahead; **neither covers feedback contamination** | No |

The last one is outside both documents' declared scope and is recorded here so it is not lost: it is a
statistics problem, not a schema problem, and it will not be visible until several model generations
have run.

---

## 7. ADR and principle compliance audit

Every recommendation in the investigation's Part 4 was checked against the accepted ADRs.

| Recommendation | Verdict |
|---|---|
| Exactness by durability class | **Compliant.** Extends §24.3's classes and ADR-0016 §4's rejected stored count |
| Canonical textual form, fixed-point | **Compliant**, and required by ADR-0027 §1's determinism argument |
| One named `float`→exact crossing rule | **Compliant, and now a correctness precondition** for ADR-0019 (**C5**) |
| **"No quotient is ever a stored field"** | **VIOLATES `AP` §25.2 and §22.2 items 9–10** (**C2**) |
| Record-not-validate venue precision | **Compliant.** Consistent with §5.1 corrections and §11.3's friction budget |
| Adapters capture the venue's original text | **Compliant, and better supported than the investigation argues.** ADR-0006 §2 already names the adapter as the sole owner of *"only the adapter knows they are plain decimal and never locale-formatted"* — capturing that text is an extension of an existing responsibility, not a new one |
| Rounding owned by the tax rule set, never the money kernel | **Compliant.** §12.4's one-owner-per-question |
| **Forward-only upcasting** | **VIOLATES ADR-0027 §2** as literally worded (**C3**) |
| Freeze the canonical encoder, byte-identical goldens | **Internally inconsistent with upcasting** (**C4**) |
| Enum addition is a version bump | **Compliant.** Correctly derives from ADR-0005 strictness |
| Two version namespaces | **Compliant.** Restores ADR-0027 §3's design |
| `code_version` on captured artifacts | **Compliant only if excluded from the identity digest** (**S5**). Also must be *injected* by a composition root, not read from the environment — three packages ban `os.environ`/`getenv` by test (`tests/test_structure_break.py`, `test_no_environment_dependence`) |
| Tax report names consumed `event_id`s | **Compliant.** Direction is tax→ledger, respecting §22.1 |
| Backup as a product requirement | Compliant; unowned in both documents |

**Import direction, circular dependencies, layer violations: none found.** The proposed `fmis.money`
and `fmis.provenance` kernels import nothing, matching `fmis.data`'s precedent, and no recommendation
requires an L0–L7 module to import anything from the trading domain.

---

## 8. Things that should NOT be changed

Attacked deliberately, and each survived. Changing these would make the investigation worse.

**8.1 — AP-D1's core recommendation. It survives, and here is why.** Three attacks were attempted:

1. *"Option C is not achievable either, because a stored FX rate is a quotient."* — **This attack
   succeeds against the Part 4 wording (C2) and fails against the idea.** Once restated as *"no
   quotient is stored in place of its exact inputs,"* the guarantee holds for every §25.2 row.
2. *"Option C invites two consumers to compute the same derived value in different types and
   disagree."* — Real, and closed by §12.4's existing one-owner-per-question rule plus §5.1's single
   enforced read path. It needs stating in the ADR; it is not a defect in the choice.
3. *"Option A is simpler and equally good."* — Fails on the measured fact that `avg × qty ≠ cost`
   under every decimal context. A guarantee of *"all arithmetic is exact"* is false in the first hour
   of use; *"every asserted value is preserved exactly and no recomputable derived value is frozen"*
   is true indefinitely. **An achievable guarantee beats an aspirational one**, and this is the
   strongest single argument in the whole investigation.

**8.2 — AP-D2's Option A as the mechanism.** The strongest attack available is C3, and C3 is a
*wording* defect, not a mechanism defect: restating capability 1 as byte reproduction repairs it
completely. Option B's collision with content-derived identity — the investigation's N2 — is real and
was independently re-derived here; it stands.

**8.3 — Rejecting Option B (integer minor units).** Strengthened by M4 and M5, not weakened.

**8.4 — Rejecting a hash chain.** Right conclusion. Replace the reason (**S4**).

**8.5 — Rejecting Option D (schemaless).** Correct and correctly argued.

**8.6 — The performance finding.** Independently re-measured on harder workloads and **confirmed**
(**M3**). Performance must not enter either ADR as an argument.

**8.7 — Adapters capturing venue text.** ADR-0006 §2 supports it more directly than the investigation
claims. Cheap now, unrecoverable later.

**8.8 — The two-name split for the full dump versus the export suite.** The investigation identifies a
genuine contradiction between `AP` §4 Finding 1 and §23.1/§24.3, and the proposed split resolves it
cleanly. This review found no better resolution.

**8.9 — AP-D1 before AP-D2.** Correct, and now *more* strongly supported: C1 shows a third decision
sits between them, so the ordering constraint is tighter than the investigation states, not looser.

---

## 9. Final recommendation

**The investigation is sound enough to build ADRs on, and not sound enough to build them from
verbatim.** It is a genuinely useful document: its central reframing — that both one-line decisions
contain many sub-decisions, and that AP-D1's stated guarantee is unachievable — is correct, was
independently re-derived here, and is the most valuable thing either document contains.

**Before either ADR is written, four things must be repaired.** All four are wording or scope
repairs; none requires reopening the option choice.

| # | Repair | Why it blocks |
|---|---|---|
| **1** | **Schedule the identity-scope decision** and exclude `recorded_at`, `source`, `asserted_by` and `capture_schema_version` from `event_id` — following ADR-0027 §3's own precedent for `archived_at` | Without it, exchange sync double-counts every manually-entered fill, and §11.5's central promise is false |
| **2** | **Restate the quotient rule** as *"no quotient is stored in place of its exact inputs"* | As written it forbids the two fields §22.2 calls unrecoverable |
| **3** | **Restate capability 1 as byte reproduction** in AP-D2, and note that ADR-0027 §2's wording is superseded by it | Otherwise the archive's only shipped guarantee becomes silently untrue at the first version bump |
| **4** | **Replace byte-identical re-encode goldens with digest-verification goldens** | The recommended pair is mutually incompatible, and the replacement protects the frozen encoder better anyway |

**Two further items should be resolved in the ADRs rather than deferred**, because both are cheap now
and unrecoverable later: the `float`→exact crossing rule (**C5** promotes it from tidiness to an
ADR-0019 correctness precondition), and `code_version` placement outside the identity digest (**S5**).

**One item should be escalated above the migration mechanism.** **S3**: all three AP-D2 mechanisms are
survivable, but a field missing from capture v1 is not. The ADR effort is better spent on the capture
contract's field list than on the migration machinery, and the current framing has that backwards.

**Verdict: proceed to ADRs, with the four repairs applied first.** Neither headline recommendation was
broken. Both were bent, and both bend back.

---

**No file was modified. No ADR was written. Nothing was committed. Eight probes were run against the
live repository at `75a4f40`; every output quoted above is reproducible from the code as it stands.**
