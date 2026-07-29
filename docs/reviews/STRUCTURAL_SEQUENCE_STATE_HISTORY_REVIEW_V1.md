# Structural Sequence State History — Independent Review (Z0 + Z1)

**Type:** independent review of two implementation milestones, before merge
**Date:** 2026-07-29
**Reviewed:** `682ca31` (Z0 — ordering unification) and `d1c0b3b` (Z1 — state history)
**Base:** `main` = `8535a98` (`Merge Market Structure Architecture Review v1`)
**Against:** [the approved design](../design/STRUCTURAL_SEQUENCE_STATE_HISTORY_DESIGN_V1.md),
[ADR-0016](../adr/ADR-0016-structural-sequence-state-history-foundation.md), ADR-0012 – ADR-0015,
[the architecture review](MARKET_STRUCTURE_ARCHITECTURE_REVIEW_V1.md), and the five resolved design
decisions (Q1–Q5)

---

## 1. Verdict

**Pass. No P0, no P1.** Two P3 findings, both recorded below; one produced a test improvement made during
this review, the other is an honest note about the review's own method.

Every load-bearing numeric claim in both commit messages was **re-derived here rather than trusted**.
All of them hold.

---

## 2. Re-derived claims

| Claim (from the commits) | Re-derived here | Verdict |
|---|---|---|
| one ordering core | `_validate_key_order` defined **1×**; the five message literals appear in `models.py` **only** | ✔ |
| ten messages byte-identical | differential vs the pre-Z0 modules: **5,888** point-adapter cases + **8,000** comparison-adapter cases, **0** mismatches | ✔ |
| history delegates, re-derives nothing | calls `_sequence_state_for` and `_validate_current_point_order`; **0** `BinOp` nodes; names **no** `StructuralSequenceStateType` member; calls none of detect/compare/label/single-state/`sorted` | ✔ |
| outside bars atomic | one snapshot for the pair; `state`/`index`/`timestamp` order-insensitive; no `CONTRACTED` transient on a falling outside bar | ✔ |
| prefix stability | 195 series, 24 outside-bar snapshots: candle prefixes **0** violations, complete-group **0**, arbitrary cuts **12** | ✔ |
| insufficient emitted | single-sided run → `insufficient_structure` snapshot, side retained | ✔ |
| projections not fields | fields are exactly `('state','triggers')`; `index`/`timestamp` are `property` with `fset is None` | ✔ |
| final-state equivalence | 346 non-empty random runs, **0** mismatches | ✔ |
| exports minimal | 19 exports, **0** submodule collisions, **0** private helpers reachable, **0** interpretive names | ✔ |
| test counts | full **2073**, market-structure **1227**, history **267**, ordering **33**, 26 modules | ✔ |
| doc table | `CURRENT_STATE` per-module table: 26 rows summing to **2073** | ✔ |
| documented names exist | only `StructuralSequenceTransition` is absent — and it appears solely in ADR-0016's "deliberately absent" list | ✔ |

---

## 3. Audit against the required checks

**One ordering core truly exists.** `relationships.compare_swing_sequence` no longer contains any
index/timestamp comparison of its own — an AST test asserts its only `Compare` operators are identity or
equality. Both adapters call the core. A third implementation cannot be added silently: the message-text
guard requires those literals to live in exactly one module.

**Exception messages byte-identical.** Verified by differential against the pre-Z0 modules loaded
side-by-side, not by reading the code. All five families × both adapters are additionally pinned with
`==` assertions, not substring matches.

**History delegates instead of re-deriving.** Enforced structurally, not by convention: no arithmetic, no
state member named, no lower-layer call. A future inlining "optimisation" fails the suite.

**Outside-bar groups atomic.** Confirmed behaviourally and by mutation: regrouping by `(index, type)`
splits the pair and fails **18** tests.

**Prefix stability stated narrowly and truthfully.** The claim in code, ADR-0016 §6, `REPOSITORY_MAP`,
`CURRENT_STATE` and `START_HERE_FOR_AI` is *candle-series extension and complete structural-group
extension* — never unconditional. The 12 arbitrary-cut violations measured here are exactly the
documented limitation, not a regression.

**Arbitrary inside-group cuts explicitly excluded.**
`test_an_arbitrary_cut_inside_an_outside_bar_group_is_outside_the_guarantee` asserts the divergence
(`SHIFTED_LOWER` whole vs `CONTRACTED` split) *and* that the same cut on a group boundary is stable. A
test that pins a limitation is worth as much as one pinning a guarantee.

**Insufficient snapshots emitted** (Q2), and a property test asserts they form a contiguous prefix —
once both sides exist, neither becomes unavailable again.

**`index`/`timestamp` are projections** (Q1), with no setter and no stored field.

**Final-state equivalence holds** (Q4), and `sequence_state.py` is AST-checked *not* to call the history
function — the cheap query stays cheap, exactly as the resolved decision required.

**Interpretation has not leaked.** No transition type, no `changed` flag, no direction, magnitude or
duration. The vocabulary scan was extended with `changed`, `improving`, `weakening`, `magnitude`,
`duration`, `bias`, `direction`, `uptrend`, `downtrend` and still passes across every module.

**Documentation matches code.** Names, pipeline, counts and stability wording all check out.

**Correlated rules double-counted?** One case, and it is deliberate: `_sequence_state_for` runs twice per
snapshot — once to build the state, once inside `StructuralSequenceState.__post_init__` to validate it.
That is one source of truth called twice, matching how `StructuralSwing` validates its label
(ADR-0014 §5). Not double-counting; not changed.

**Tests assert contracts, not implementation accidents.** The oracle is a fourth independent formulation
(raw price signs plus an independently written fold). One test was strengthened during this review — see
P3-1.

**No dependency added.** `pyproject` dependencies remain `[]`; hypothesis is not installed and was not
introduced, so the matrices are deterministic seeded ones per repository convention.

---

## 4. Mutation review

Each probe run individually, mutation confirmed live at runtime, caches cleared, files restored
byte-exact (`shasum -c` clean after every probe).

| Probe | Result |
|---|---|
| snapshot per swing rather than per group | 18 failed |
| grouping by `(index, type)` — outside bars split | **18 failed** |
| carry-forward dropped | 83 failed |
| first side instead of latest | 150 failed |
| deduplicate repeated states | 62 failed |
| silently sort input | 4 failed |
| suppress insufficient snapshots | 93 failed |
| drop the trigger/state coherence check | 1 failed |
| remove ordering validation | 5 failed |

---

## 5. Findings

### P0 — none. P1 — none.

### P3-1 — a test asserted less than its name claimed *(fixed during this review)*

`test_a_candle_prefix_never_splits_an_outside_bar_group` only checked that a snapshot's triggers had
distinct swing types — which the model already enforces on construction, so it could not have failed. It
now asserts the actual claim: for every candle prefix, a snapshot at some index holds **exactly** the
triggers the full history holds at that index, and the sample is required to contain outside bars to be
meaningful. Safe, in scope, and it strengthens rather than adds behaviour.

### P3-2 — two of this review's first mutation probes were no-ops *(method note, no code change)*

The first attempt at an atomicity probe swapped two independent statements; the second nulled a value and
then restored it through an `or` fallback. Both left behaviour unchanged, so "267 passed" meant *the
probe did nothing*, not *the tests missed it*. Recorded because a probe that cannot fail is worse than no
probe: it manufactures false confidence. The replacement — regrouping by `(index, type)` — is a real
break and is caught by 18 tests.

### Accepted, not defects

- The trigger/state coherence check is guarded by exactly one test (1 failure under mutation). That is
  one precisely targeted test for one narrow invariant, which is appropriate.
- `_sequence_state_for` running twice per snapshot is the repository's validate-don't-trust pattern.
- The history is event-indexed, not bar-indexed. Deliberate (ADR-0016 §1); a bar-indexed view would need
  a candle count this layer does not receive.

---

## 6. Performance

| candles | structures | snapshots | history derivation |
|---|---|---|---|
| 5,000 | 2,016 | 2,016 | 0.0028 s |
| 20,000 | 8,038 | 8,031 | 0.0107 s |
| 80,000 | 32,120 | 32,102 | 0.0565 s |

Linear, single pass, sharing every referenced object by identity. No optimisation warranted and none
attempted.

---

## 7. Validation

| Check | Result |
|---|---|
| focused history suite | 267 passed |
| focused ordering suite | 33 passed |
| market-structure suite | 1227 passed |
| full suite | 2073 passed |
| `python -W error -m pytest -q` | 2073 passed |
| `git diff --check` | clean |
| exports / collisions | 19 / none |
| `EvidenceFamily.MARKET_STRUCTURE` | empty, catalog 6 |
| dependencies added | none |

---

## 8. Recommended next milestone

**Trend Foundation v1** — the first layer that may consume the history, and the first that must state its
own policy (how many snapshots constitute a trend, and what an interleaved run means). It needs no new
facts and no candle access.

**Not** break of structure. As the architecture review §15 established and ADR-0016 §12 restates, BOS
needs a "price crossed level L at bar i" fact that no layer above `detect_swings` can currently produce.
That requires a new input contract and its own ADR — deciding close-versus-wick, protected levels, and
outside-bar grouping — and the recommendation remains a **sibling package** so `market_structure` keeps
the property that only its first stage touches candles.
