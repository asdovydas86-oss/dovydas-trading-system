# Trend Foundation v1 — Independent Review (Milestone AA)

**Date:** 2026-07-29
**Reviewing:** `Add Trend Foundation v1 design` (`8ef685e`) and `Add Trend Foundation v1` (`d440739`)
**Scope:** the new package `fmis.structural_trend`, its tests, [ADR-0017](../adr/ADR-0017-structural-trend-foundation.md),
[the design](../design/TREND_FOUNDATION_DESIGN_V1.md), and the documentation touched by the milestone
**Method:** every count, export, mutation result and stability figure **re-derived from scratch**. No number
from the design, the ADR, the commit messages or the previous milestone's review was taken on trust.

---

## 1. Verdict

**Accept, after one P1 fix applied during this review.**

The chosen policy is defensible, deterministic, and — most importantly for this milestone — **stated as a
policy rather than presented as a discovery**. The layer consumes nothing but
`StructuralSequenceStateSnapshot`, re-derives nothing, and reports ambiguity instead of resolving it. All
nine mutation probes are detected and none is a no-op.

One P1 was found and fixed: a headline prefix-stability figure measured one thing and was documented as
though it measured another. No P0. Three P3s recorded, two of them inherited limitations rather than
defects of this layer.

## 2. Re-derived claims

| Claim | Source's figure | Re-derived | Verdict |
|---|---|---|---|
| full suite | 2425 | **2425 passed** | ✅ |
| full suite, `-W error` | 2425 | **2425 passed** | ✅ |
| trend module | 352 | **352 passed** | ✅ |
| market_structure suite | 1227 | **1227 passed** | ✅ unchanged from baseline |
| state-history module | 267 | **267 passed** | ✅ unchanged |
| ordering module | 33 | **33 passed** | ✅ unchanged |
| baseline before milestone | 2073 | **2073** (2425 − 352) | ✅ |
| total package exports | 105 | **105** across 21 packages | ✅ (baseline 100 + 5) |
| export collisions | none | **none** | ✅ |
| `market_structure` exports | 19 | **19** | ✅ unchanged |
| `structural_trend` exports | 5 | **5**, no overlap with any existing export | ✅ |
| runtime dependencies added | none | **none** — `dependencies = []`, no `pyproject.toml` or `uv.lock` change | ✅ |
| production files changed outside the new package | none | **none** — the diff against `main` touches only the three new files | ✅ |
| exception messages changed | none | **`git diff main -- src/fmis/market_structure/` is empty (0 lines)** | ✅ |
| `EvidenceFamily` / catalog | unchanged, 6 descriptors, `MARKET_STRUCTURE` empty | **confirmed**, and pinned by three tests | ✅ |
| mode 1 prefix stability | 2,000 prefixes / 0 violations | **2,000 / 0**, re-measured against the *shipped* function | ✅ |
| mode 2 prefix stability | 739 prefixes / 0 violations | **739 / 0**, likewise | ✅ |
| mode 3 inside-group cut | "891 splits / 133 divergences" | **891 splits; 891 snapshot divergences, 133 value divergences** | ❌ **P1-1** |
| threshold sensitivity | 1,286 / 350 / 84 over 1,627 | **1,286 / 351 / 85** on an independently reconstructed corpus | ⚠️ **P3-1** |
| corpus composition | 13 + 1,555 + 61 = 1,629 | **13 + 1,555 + 61 = 1,629**; 1,627 non-empty | ✅ |
| equivalence contract | holds | **0 violations** over every valid synthetic spec | ✅ |
| mutation probes | 9/9 detected, none a no-op | **9/9 detected**, re-run independently; sources restored byte-exactly and post-restore suite green | ✅ |

**Important methodological note.** The design's stability and sensitivity figures were produced by a
*scratch reimplementation* of the policy, not by the shipped code. This review re-measured all of them
through `derive_structural_trend` / `derive_structural_trend_history` themselves. That is what surfaced
P1-1: a reimplementation compared trend *values*, while the shipped function returns *snapshots*.

## 3. Audit against the required checks

### Duplicated logic — **clean**
The one plausible duplication is the ordering rule, since `market_structure.models._validate_key_order`
already exists. Measured: `difflib` similarity between the two implementations is **0.29**, and the longest
shared substring is **5 characters**. They are not variants of one rule.

They are also semantically different, and the difference matters: the swing-run rule permits a
*non-decreasing* index (an outside bar yields two swings at one index) with strictness only within a
`SwingType`; a snapshot history has already collapsed those groups, so its rule is globally strict and
there is no `SwingType` to be strict within. Reusing the looser rule would **accept a two-snapshots-at-one-
index history that `derive_structural_sequence_state_history` cannot produce** — verified by test
(`test_a_repeated_index_is_rejected`). ADR-0017 §15 records this, and recording it was the right call
because "reuse the shared rule" is the correct instinct and is wrong here.

Beyond that: `_sequence_state_for`, `_label_for`, `_relation_for` and `_validate_key_order` are never
called, never re-implemented, and never named. The state mapping is not copied — this layer reads
`snapshot.state.state` and derives nothing from labels.

### Architectural layering — **clean**
Internal imports are exactly `{fmis.market_structure, fmis.structural_trend.models,
fmis.structural_trend.trend}`. No import of `fmis.data`, `fmis.decision_support`, `fmis.evidence`,
`fmis.providers`, `fmis.pipeline`, `fmis.ingest`, `fmis.trading_context`, `fmis.relative_value`,
`fmis.features`, `fmis.alignment`. No reach into `market_structure`'s private submodules — only its public
surface. Standard library only. Nothing below imports this package (asserted by a test that scans every
other `.py` under `src/fmis`).

The sibling-package placement is correct and, better, *enforced*: a test asserts `market_structure` still
contains no trend vocabulary, so the reason this package is a sibling cannot decay into folklore.

### Ambiguity handling — **clean, and the strongest part of the design**
`NEUTRAL` (evidence exists on both sides and conflicts) and `INDETERMINATE` (evidence absent) are distinct
and both reachable. A strictly alternating history reports `INDETERMINATE` once, then `NEUTRAL` forever —
never a direction. Three of the four candidate policies could not express both members, and the design
rejected them partly on that ground, which is the right weighting.

`contested` is monotone, so `INDETERMINATE` never returns after an opposition. Verified by test and by
exhaustive matrix.

### Persistence — **clean, and the limitation is honestly stated**
All four non-directional states are transparent, individually and combined, at length 1 and at length 500.
The consequence — a trend followed by 500 contracting snapshots still reads as sustained — is stated in the
package docstring, the design §7.2, ADR-0017 §7 and the handoff document, and is pinned by
`test_persistence_across_five_hundred_neutral_snapshots`. This is documented rather than patched with an
arbitrary decay constant, which is the correct choice at a layer with no basis for one.

### Invalidation — **clean**
Exactly one opposing shift invalidates, immediately, and yields `NEUTRAL` rather than the opposite
sustained trend. A 40-shift run is invalidated by one opposing shift. Intervening neutral states do not
delay it. The "require two opposing shifts" alternative is rejected in ADR-0017 §7 with the right reason:
it would report `SUSTAINED_HIGHER` while the newest fact says both sides moved lower.

### Outside-bar handling — **clean**
The state history already resolves groups atomically (ADR-0016 §2), so this layer adds no split: one
reading per state snapshot, verified on synthetic outside-bar histories and on candle-derived series with an
engulfing bar every third candle. Both trigger orders give the same trend history. The "one reading per
trigger" mutation is detected by 156 tests.

### Prefix stability — **clean after the P1 fix**
Modes 1 and 2 re-measured at 0 violations over 2,000 and 739 prefixes respectively, against the shipped
function. The proof in ADR-0017 §8 is correct: a left fold whose step reads only the accumulator and the
current state, and whose classification is a pure function of the accumulator.

The five stated limitations are each real and each correctly *outside* the guarantee. §9.4 — "the guarantee
is that an emitted reading never changes, not that the trend keeps its value" — is the one most likely to be
misread by a consumer, and it is pinned by its own test.

### Deterministic replay — **clean**
Pure, no I/O, no clock, no randomness, no global mutable state. Input materialised once and never mutated,
sorted or reordered; `sorted` and `reversed` are AST-forbidden. Results compare `==` across calls and are
not `is`. Source snapshots carried by identity. Generators accepted and fully consumed.

### Forbidden interpretation — **clean**
No BOS, CHoCH, support, resistance, protected level, liquidity, sweep, signal, LONG/SHORT, price
prediction, probability, confidence, score, strength, rank, magnitude or duration. The accumulator's run
length is private and appears on no public type — the review specifically checked that `StructuralTrendSnapshot`
exposes no count, since a run length is a confidence score by another name.

No `EvidenceDescriptor` added; `EvidenceFamily` enum, its members and the 6-descriptor catalog all
unchanged and pinned. The AST vocabulary scan covers 40 forbidden tokens including `candle`, `price`,
`level` and `decay`.

Trend is not an input to anything below it, and nothing below imports this package — so the architecture
review §15 ordering (BOS on levels → CHoCH on BOS → trend as a summary) is preserved.

### Documentation accuracy — **one P1, one P3, otherwise accurate**
Every other figure in the design and ADR re-derived correctly. The two Z1 staleness fixes the milestone made
in passing (the module tree was missing `state_history.py` and `StructuralSequenceStateSnapshot`; the
`market_structure` section still said "state history is deliberately postponed") were verified as genuine
corrections.

## 4. Mutation review

Nine probes, each applied to production source, verified to be a real byte change (a no-op probe is rejected
outright by the harness), suite run, source restored byte-exactly, restore verified by SHA-256, and the
post-restore suite confirmed green. Re-run independently for this review with identical results.

| Probe | Detected by | Verdict |
|---|---|---|
| forced upward | 69 tests | ✅ |
| forced downward | 84 tests | ✅ |
| ignored ambiguity (`NEUTRAL` folded into `INDETERMINATE`) | 75 tests | ✅ |
| ignored persistence (non-directional resets the run) | 83 tests | ✅ |
| removed invalidation (opposing shift extends the run) | 76 tests | ✅ |
| removed ordering validation | 9 tests | ✅ |
| broken prefix stability (classification reads the whole run) | 144 tests | ✅ |
| broken outside-bar handling (one reading per trigger) | 156 tests | ✅ |
| duplicated structural-state logic (re-derive state from labels) | 100 tests | ✅ |

**On the method.** The previous milestone's review (§P3-2) recorded that two of its own first probes turned
out to be no-ops. That was treated as a standing requirement here: the harness asserts the source digest
changed before running the suite and refuses to report a probe that did not modify anything. No probe in
this milestone was a no-op.

The "removed ordering validation" probe is detected by only 9 tests, which is correct rather than weak — it
is the narrowest behaviour change of the nine, and the 9 tests are precisely the ordering rejections.

## 5. Findings

### P0 — none.

### P1-1 — a headline prefix-stability figure measured the wrong thing *(fixed during this review)*

ADR-0017 §9.1 and the design §8.3/§8.4 stated the excluded inside-group cut as **"133 divergences over 891
split groups (15%)"**. Re-measuring against the shipped code gives:

| Compared as | Divergences |
|---|---|
| whole `StructuralTrendSnapshot` tuples — **the guarantee's own equality** | **891 / 891** |
| trend *value* only | 133 / 891 |

The guarantee in §8 is stated over `derive_structural_trend_history`'s **return value**, which embeds the
state snapshot. A split group produces a genuinely different state snapshot for that candle, so the readings
differ as objects even where the trend value coincides. The design's scratch probe compared values, and the
figure was carried into the ADR as though it measured the guarantee.

This matters beyond arithmetic: 15% reads as "an edge case that usually does not bite", whereas the true
figure for the stated guarantee is **always**. A consumer sizing the risk from the documented number would
have sized it wrong by a factor of six.

**Fixed:** both documents now state both figures with their exact meanings, and
`test_the_arbitrary_inside_group_cut_is_outside_the_guarantee` was strengthened from a weak
`divergences > 0` to pinning both — `divergent_snapshots == split` and `0 < divergent_values < split` — so
the two can never again be silently substituted for one another.

### P2 — none.

### P3-1 — a sensitivity figure depended on a non-reproducible fixture *(fixed during this review)*

The threshold-sensitivity table cited exact counts (1,286 / 350 / 84 over 1,627 sequences) from a corpus
whose 61st member is a hand-built candle fixture. Reconstructing the corpus independently gave
1,286 / **351** / **85**. The percentages (79 / 22 / 5) and the conclusion are unaffected, but a cited
integer that cannot be reproduced is a cited integer that will be doubted.

**Fixed:** both documents now quote the **exhaustive enumeration alone** — every state sequence of length
1–4 over all six members (1,554 sequences), giving 78.1% / 18.9% / 2.4%, plus the length-1–6 enumeration
(55,986) for the trend — which anyone can reproduce with no fixture. The design also records the
discrepancy and why the enumeration is quoted in preference.

### P3-2 — two instruments' histories can be concatenated undetected *(inherited; documented, no code change)*

A `StructuralSequenceStateSnapshot` carries no symbol or timeframe. This is deliberate — the architecture
review §16 records that such context belongs in an envelope, not on atomic facts. The consequence is that a
caller concatenating two instruments' histories can produce a run with increasing indices and timestamps
that passes ordering validation and is folded into a single trend. Verified: indices 1, 2, 11, 12 drawn from
two "instruments" yields `SUSTAINED_HIGHER` with no error.

Not a defect of this layer, and not fixable here without the metadata the package deliberately does not
carry. **Recorded in ADR-0017's consequences**, with the standing rule that any multi-symbol or
multi-timeframe layer must join on **timestamp**, never index, and must not concatenate.

### P3-3 — the policy constant has one inert rebinding path and one live one *(documented, no code change)*

`trend.py` binds `MINIMUM_DIRECTIONAL_SHIFTS` into its own namespace at import. So rebinding
`fmis.structural_trend.MINIMUM_DIRECTIONAL_SHIFTS` is **inert**, while rebinding
`fmis.structural_trend.trend.MINIMUM_DIRECTIONAL_SHIFTS` is **live** — verified both ways.

Neither is a supported way to change the policy (ADR-0017 §4 makes it a constant precisely so it is not a
dial), so no code change is warranted. But the asymmetry is a trap for anyone who tries the obvious one and
concludes the constant does nothing. **Recorded in ADR-0017's consequences.**

### Accepted, not defects

- **`_advance`'s `contested=run.contested` in the no-run-yet branch is always `False`**, since `contested`
  can only become `True` once a run exists and a run never returns to `None`. Writing the general form
  rather than a literal `False` is preferred: it asserts no invariant the step function would have to
  maintain, and it survives a future change to when `contested` can be set.
- **`_classify`'s `run.state is not None` guard is redundant** with `length >= 2` (length is 0 exactly when
  state is `None`). It is type-narrowing for the checker and documents the pairing; keeping it is right.
- **The scalar form is not `history[-1]`.** Duplication risk is real and is closed the right way — one
  shared `_advance` and one shared `_classify`, an AST test asserting both public functions call both, and a
  tested equivalence contract. This follows ADR-0016 §10 rather than re-deciding it.
- **`StructuralTrendSnapshot` cannot validate its own `trend`.** Correct and correctly documented
  (ADR-0017 §14): a trend is a property of a prefix, not of a snapshot. The compensating control — an
  independent oracle in the tests — is the right substitute for a self-check that cannot exist.
- **The trend history is event-indexed**, inherited from ADR-0016. A consumer wanting a value per bar must
  join itself. Documented.

## 6. Performance

The derivation is a single left fold with an O(1) frozen-dataclass allocation per snapshot: O(n) time, O(n)
output for the history form and O(1) auxiliary for the scalar form. The full 352-test module runs in ~0.3 s
and the whole suite in ~1.7 s, against ~1.4 s at baseline. Nothing here warrants an incremental adapter, and
the architecture review §12's instruction stands: **do not build one speculatively.**

## 7. Validation

| Check | Result |
|---|---|
| full suite | **2425 passed** |
| `python -W error -m pytest -q` | **2425 passed** |
| market_structure suite | **1227 passed** (unchanged) |
| trend module | **352 passed** |
| state-history module | **267 passed** (unchanged) |
| ordering module | **33 passed** (unchanged) |
| deterministic replay | equal across calls, not identical, identity carry-forward confirmed |
| prefix stability — candle-series extension | 2,000 prefixes, **0 violations** |
| prefix stability — complete-group extension | 739 prefixes, **0 violations** |
| inside-group cut (excluded) | 891 splits, 891 snapshot / 133 value divergences, both pinned |
| outside-bar validation | one reading per state snapshot; both trigger orders agree |
| exports / collisions | **105 / none**; `market_structure` still 19; `structural_trend` 5 |
| dependency validation | **none added**; `pyproject.toml` and `uv.lock` untouched |
| exception messages | **unchanged** (`git diff main -- src/fmis/market_structure/` empty) |
| `EvidenceFamily` / catalog | unchanged; `MARKET_STRUCTURE` empty; 6 descriptors |
| `git diff --check` | clean |
| mutation probes | **9/9 detected, 0 no-ops**, sources restored byte-exactly |

## 8. Recommended next milestone

**Level-Crossing Foundation v1** — a new sibling package producing the one fact the whole structural stack
is missing: *"price crossed level L at bar i"*.

**Why this and not break of structure directly.** BOS is a conclusion; the crossing fact is the primitive it
needs, and the architecture review §15 established that no layer above `detect_swings` can currently produce
it. Separating them keeps the pattern every milestone from V onward has followed: ship the fact, then ship
the reading, and never both in one commit.

**Why not trend-derived evidence** (`EvidenceFamily.MARKET_STRUCTURE`): still premature by ADR-0011 §1.
Summarising a run of settled facts is not classification, and `SUSTAINED_HIGHER` is not an evidence
descriptor.

**The decisions its ADR must make before any code** (architecture review §15, unchanged):
close-versus-wick crossing; which level is protected and when it stops being; whether an `EQUAL_HIGH`
crosses anything; how an outside bar crossing both sides is grouped and ordered; whether a crossing is
reported at the crossing bar or at the next confirmed swing; and what happens when a level is crossed inside
a later swing's confirmation window.

**The architectural decision it must respect:** it is the first layer since `detect_swings` to need a
`CandleSeries`, so it must be a **sibling package** consuming both candles and swings — not a new stage
inside `fmis.market_structure`, which keeps the property that only its first stage touches a candle. And the
ordering stands: BOS on levels, CHoCH over the BOS sequence, **trend as an input to neither**.
