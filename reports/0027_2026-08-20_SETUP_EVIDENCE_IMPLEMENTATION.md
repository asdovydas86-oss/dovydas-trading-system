# Report 0027 — Setup Evidence (Milestone BR) — Implementation Record

| | |
|---|---|
| **Report number** | 0027 |
| **Title** | Setup Evidence — the deterministic explanation layer (Milestone BR) |
| **Date** | 2026-08-20 |
| **Report type** | Implementation |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `main` / `2059ca7` (production code + tests), on top of `2c7bdc5` |
| **Status** | Final |

---

## 1. What was asked, and what the mandatory gate found

The milestone brief asked for `src/fmis/evidence/` — a deterministic evidence engine
answering *why is this setup good, why is it weak, what contradicts it, what is missing*.
It required a mandatory inspection step first, with three things to confirm: no existing
package owns the responsibility, no duplicated reasoning layer exists, no ADR is violated.

**All three confirmations failed**, and the work stopped before any code was written.

| Finding | Evidence |
|---|---|
| `src/fmis/evidence/` **already exists** — a taxonomy (`EvidenceFamily`, `EvidenceDescriptor`, a 6-entry catalog), 358 LOC, governed by ADR-0011 | `src/fmis/evidence/` |
| `fmis.decision_support` **already owns an `EvidenceReport`** with supporting/conflicting/unavailable groups, `Observation`, `OverallState`, `Scenario` | `decision_support/report.py:237` |
| `SetupAssessment` **already carries all five requested outputs** — `thesis`, `directional_factors`, `confirmation`, `invalidation`, `limitations`, `sufficiency` | `swing_setup/models.py:285` |
| ADR-0011 §4 **explicitly rejected** an enum combining SUPPORTING/CONFLICTING/NEUTRAL/UNAVAILABLE/INSUFFICIENT_DATA inside `fmis.evidence` | ADR-0011 §4 |
| ADR-0011 §8 forbids `fmis.evidence` importing `decision_support`, **test-enforced in both directions** | `tests/test_evidence_taxonomy.py` |
| Four guard tests would break on contact, including `__all__` pinned to exactly five names | `tests/test_evidence_taxonomy.py` |

The brief's `strength: STRONG/MEDIUM/WEAK/NEUTRAL` was additionally in tension with its own
"no hidden scoring" test requirement: a monotone four-level ordinal with no deterministic
rule per level is a score in an enum's clothing, and ADR-0011 §3 refuses score/weight/
confidence fields for exactly that reason.

**Owner decisions taken on the findings** (2026-08-20): drop the strength enum entirely;
confluence is not a family but a derived cross-family relationship; Context is not a family;
preserve the ADR-0011 taxonomy unchanged; build at the application tier as
`src/fmis/setup_evidence/`.

## 2. Architecture decision

**`src/fmis/setup_evidence/` — a projection at the `fmis.swing_setup` tier.**

It consumes a `SetupAssessment` and produces a `SetupEvidenceReport`. It is not a second
decision engine: it re-decides nothing, computes no market quantity, and applies no
threshold to any number.

Four `fmis` dependencies, pinned as a set by a guard test:

- `fmis.decision_context` — `ContextState`, the type `decision_ready` is a function of
- `fmis.evidence` — `EvidenceFamily`, used as ADR-0011 §7 intended ("shared vocabulary,
  separate interpretation"). **This package is that ADR's first real consumer.**
- `fmis.swing_setup` — the assessment being projected
- `fmis.swing_setup.policy` — the research-override marker, so a research artifact is
  warned about rather than silently explained as production

**`fmis.evidence` was not modified.** No family was added; a guard test asserts its `__all__`
and the ten `EvidenceFamily` members are unchanged.

**The report is `SetupEvidenceReport`, not `EvidenceReport`** — `fmis.decision_support`
already owns that name, and a guard asserts the two types are distinct.

**No direction is named in this package's source.** ADR-0028 permits that vocabulary only in
`fmis.swing_setup` and `pipeline/cli.py`. Agreement is tested by runtime value
(`factor.lean.value == direction_value`), never by naming a member.

## 3. Field mapping: `SetupAssessment` → `SetupEvidenceReport`

| Source field | Projected as | Rule |
|---|---|---|
| `symbol`, `as_of` | `symbol`, `as_of` | copied |
| `state`, `direction` | `state_text`, `direction_text` | `.value` carried as a string; the enums are not imported |
| `thesis` | `thesis` | **carried by reference**, never rebuilt |
| `invalidation` | `invalidation` | **by reference**, rendered as a *standing condition*, explicitly not a present conflict |
| `regime_context` | `regime_context` | **by reference** |
| `directional_factors[i]` | one `EvidenceItem`, key `factor:{family}` | status from the factor's own lean vs. the assessment's own direction — never re-tallied |
| `regime_context[0]` | `EvidenceItem` `regime:structure_gate` | SUPPORTING when state ≠ WAIT (which *proves* the gate passed); UNAVAILABLE on WAIT, because the assessment does not record which precondition stopped it and this package will not parse the rendered line |
| `confirmation[0]` + `trigger` | one `EvidenceItem` `confirmation` | SUPPORTING when CONFIRMED, MISSING when awaited. **The trigger is not a second item** — see §4 |
| `stop` + `invalidation` + `risk_reward` | one `EvidenceItem` `geometry:risk_reward` | **one item, not three** — see §4 |
| `probability` | `EvidenceItem` `calibration:probability` | always UNAVAILABLE; the absence is stated, never filled |
| `limitations[i]` | `EvidenceItem` `limitation:{n}` | de-duplicated; factor restatements dropped — see §4 |
| `sufficiency` | `sufficiency` (by reference) + `decision_ready` | **total function of `sufficiency` alone** |
| — | `family_summary`, `confluence` | derived on every call, stored nowhere |

**`decision_ready`** is `SUFFICIENT → True`, `LIMITED → True`, `INSUFFICIENT → False`, written
as a complete mapping over the enum so a fourth `ContextState` fails loudly rather than
defaulting to ready. `LIMITED` is ready because that is `ContextState`'s own documented
meaning — nothing blocking is missing. A test varies every other field on the assessment and
asserts the answer never moves.

## 4. Correlation and de-duplication — the core of the milestone

Two mechanisms, kept apart:

- **Structural independence** — computed from `EvidenceItem.families` set-disjointness.
- **Named correlations** — declared in `correlation.py`, because no family set can express
  "these read the same candles". Each carries its reason, and
  `tests/test_setup_evidence_architecture.py` §4 **proves each claim against the live code**.

### The six correlations found

1. **The regime gate *implies* the context trend vote.** `build_setup_inputs` derives
   `context_structural_trend` and `context_regime_structure` from the same context view;
   `market_regime` reads `subject.structural_trend` for the swing-structure family that
   STRUCTURE depends on; STRUCTURE is TRENDING only when that trend is sustained; a sustained
   trend is exactly what makes the factor vote. **So passing the gate guarantees the vote.**
   Proven exhaustively over every `StructuralTrendType`. This is the most consequential
   finding: it means `MINIMUM_AGREEING_FAMILIES = 2` is, in practice, *the gate's own family
   plus one other* — the "free confirmation, not corroboration" hazard `market_regime`'s own
   source warns about.
2. **The two structural trends** are the same method at two intervals — one family observed
   twice, not two independent families.
3. **Setup trend ↔ evidence alignment** read the same series; three of the five observations
   behind the dominant alignment are price-vs-EMA comparisons over it.
4. **MACD is internally double-counted upstream.** `histogram = macd_line - signal_line`
   (`features/indicators/macd.py:155`), so `macd_vs_signal` and `macd_histogram` are one fact
   that `decision_support` counts as two observations. The three EMA comparisons are
   transitive for the same reason. Both proven behaviourally.
5. **Trigger ≡ confirmation.** `policy.py` builds `Trigger.statement` from `confirmation[0]`
   on *both* branches. Projected as one item; the trigger's level and bar index — genuinely
   additional — are carried in that item's `inputs`.
6. **The protective level appears three times** — as `stop`, restated inside `invalidation`
   (whose own text says "the same level"), and inside `risk_reward`. Projected once.

### De-duplication

- Identical items sharing a key collapse; **different** items sharing a key raise rather than
  merge — picking a winner would hide whichever was wrong.
- Repeated limitation lines collapse.
- **Limitation lines that restate an already-projected factor are dropped.** Found on the live
  `BTCUSDT` page, where all three factors appeared twice — once as CONFLICTING items and again
  as UNAVAILABLE limitations. The lines are *regenerated and matched exactly*, never parsed; a
  test asserts the reconstruction still matches what the policy emits, so a wording change
  fails loudly instead of letting the duplicates return.

### Confluence

Derived on every call, stored nowhere, and measured over **families, not items**.
`independence_established` is `True` only when two agreeing items are family-disjoint *and*
not named together in a correlation rule. An item with no family can never establish
independence — unknown is not the same as different. Geometry, calibration and the regime
precondition carry no family and so cannot inflate it.

**On the live factor set, independence is never established**, and the page says so plainly.

## 5. Surfaces

**`fmits evidence SYMBOL`** — registered immediately after `setup`, running the same live
path so the page always explains a setup the owner could have seen on `fmits setup`.
Sections: WHY THIS SETUP EXISTS · SUPPORTING EVIDENCE · CONFLICTING EVIDENCE (with standing
invalidation kept separate) · MISSING CONFIRMATION · UNAVAILABLE / LIMITATIONS · FAMILY
CONFLUENCE · DECISION READINESS. Every line wrapped to 70 columns, test-enforced.

**`fmits today`** — one section-level `evidence_note` on `Opportunities`, derived from the
correlation registry. **A per-row figure was deliberately declined**: every line comes from
the same three factors, so a per-row independence flag is provably constant — zero
information, and a constant column reads either as a defect or as an invitation to rank.
`Opportunities`' own docstring already refuses to sort by any property of the analysis.

## 6. Verification

| Gate | Result |
|---|---|
| Focused BR suite | **163 passed** |
| `swing_setup` regressions | **418 passed** (includes the network-touching backtest and research suites) |
| Setup-identity regressions | **150 passed** |
| `decision_support` + `decision_context` regressions | **147 passed** |
| `proposal` / trade-domain regressions | **106 passed** |
| `statistics` regressions | **513 passed** |
| Pipeline / CLI regressions | **294 passed** |
| Evidence-taxonomy (ADR-0011) | **77 passed** |
| Vocabulary + architecture guards | **161 passed** |
| **Full repository, `-W error`** | **8,693 passed, 0 failed** (~191 s) |
| Coverage — statement | **94%** (`project.py` 99%, `render.py` 99%, `__init__.py` 100%) |
| Coverage — statement + branch | **92%** overall; the 29 uncovered statements are defensive validation `raise` lines, and the 3 partial branches are the two-condition guards above them |
| Mutation probes | **15/15 killed** |
| Import cycles | none introduced — `setup_evidence` imports 3 packages, never `fmis.pipeline`, and is imported only by `fmis.pipeline.cli` and `fmis.today.sections` |
| Export collisions | none involving this package |
| `pyproject.toml` / `uv.lock` | **unchanged** (0 diff lines) |
| `git diff --check` | clean |
| Markdown links | no broken relative links |
| Secret / artifact scan | none |
| Live demonstration | `fmits evidence ETHUSDT` (CONFIRMED), `fmits evidence BTCUSDT` (WAIT), `fmits today` |

Every regression group was run under `-W error`.

Net new tests: **+163** (the two new suites). Baseline before this milestone: **8,530**.

### Regressions fixed during the gate

Twenty-one pre-existing tests failed on first full run. All were caused by this milestone and
all are fixed:

- `EvidenceStatus` collided with `fmis.market_regime`'s existing export → renamed
  `SetupEvidenceStatus`.
- The CLI imported `fmis.proposal` (a trading-domain root it may not name) to stamp the
  vocabulary id and identity version onto `SetupIdentityRef` → **both fields dropped**, not
  the guard widened. The identity string comes from the already-permitted
  `fmis.setup_observation`.
- Three command rosters and one ordered registry needed the new `evidence` command.
- Two engine-layering guards are raw *text* scans that flagged prose mentions of
  `fmis.structural_trend` / `fmis.market_regime`. The package does not import either, so the
  **prose was reworded** rather than the guards weakened.
- `fmis.decision_context`'s layering guard was widened to admit `setup_evidence` as a fifth
  composition root — a legitimate upward dependency, following four prior precedents.
- `tests/test_trade_capture_architecture.py` admits `fmis.setup_evidence` as an
  application-layer prefix, with the `fmis.proposal` episode recorded in the comment.

### Defects found in this milestone's own code, by its own gates

- **Dead code**: `_is_directional` was defined and never called — found by coverage, removed.
- **A crash on a valid assessment**: an assessment with empty `regime_context` produced no
  regime item, leaving the context-trend factor pointing at an absent key, which the report's
  own validation rejected. Found by a coverage-driven test; fixed with `_prune_correlations`.
- **Double-reported factors on the live page** — found by the live demonstration, §4.
- **A test gap**: a mutation probe survived because the unfamilied-item test placed the item
  second, where an inner guard caught it. Both orderings are now asserted.
- **A misleading empty-state**: "independent corroboration: NOT established" printed beside an
  empty agreeing set read as a finding about evidence that was never examined; it now reads
  "not assessed — no agreeing evidence to compare".
- **A latent width overflow**: nothing bounds `SetupAssessment.symbol`, so a long one would
  push the header rule past the margin. The title is now truncated.

## 7. What the owner can do that was impossible before

Ask *why* — and get an answer that argues against itself. `fmits evidence ETHUSDT` on a live
CONFIRMED LONG reports two agreeing families, one **conflicting** family, and states that the
corroboration is **not independent**, naming which upstream inputs are shared. Previously the
same setup appeared on `fmits setup` as three agreeing "independent evidence families" with no
indication that the regime gate and one of those families are the same reading.

## 8. Limits of this milestone

- Only the **six** correlations listed in §4 are known. The registry is honest about being a
  registry: an unmapped future factor produces a visibly unclassified item and a warning,
  never a guess.
- `setup_evidence_alignment` maps to two families because `decision_support` does not report
  which of the two drove its dominant alignment. A finer attribution needs a change there.
- The regime precondition's outcome is not determinable from a `WAIT` assessment without
  parsing rendered text, which this package refuses to do. Recording the regime states as
  enums on `SetupAssessment` would close that gap.
- **Nothing here changes the Swing Setup policy.** The §4.1 finding argues that
  `MINIMUM_AGREEING_FAMILIES = 2` is weaker than it reads. Acting on that is a policy decision
  for the owner, and deliberately outside a projection's authority.

## 9. Policy preservation — explicitly verified

Changing the Swing Setup policy was **not authorized** for this milestone, and it was not changed.
Verified mechanically at the release gate:

- `git diff -- src/fmis/swing_setup/` → **0 lines**. The entire package is byte-identical.
- `MINIMUM_AGREEING_FAMILIES = 2` at `swing_setup/policy.py:71` — unchanged.
- `CONFIRMATION_LOOKBACK_BARS`, `_tally`, `_trend_lean`, `_evidence_lean` — unchanged.
- The 418-test `swing_setup` regression group passes unmodified under `-W error`.

**The regime-gate / context-trend structural dependency is recorded, not fixed.** It survives in
three places, none of which alters behaviour:

1. `KNOWN_CORRELATIONS[0]` in `setup_evidence/correlation.py`, with its full reasoning;
2. a caveat printed on every affected `fmits evidence` page, and a warning line beside it;
3. an open item in `FMITS_PRODUCT_BACKLOG.md` §5, marked as an unsequenced strategy/research
   decision for the owner.

A test — `test_claim_the_regime_gate_implies_the_context_trend_vote` — proves the dependency
exhaustively over every `StructuralTrendType`, so if a future change removes it, the now-false
caveat fails a test rather than continuing to print.
