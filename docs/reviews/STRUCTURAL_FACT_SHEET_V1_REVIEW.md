# Structural Fact Sheet v1 — Independent Review

**Milestone:** AF — First Light
**Reviews:** [ADR-0022](../adr/ADR-0022-structural-fact-sheet-composition-root.md), [design](../design/STRUCTURAL_FACT_SHEET_V1.md)
**Date:** 2026-08-02
**Verdict:** no P0, no P1, **one P2 found and fixed**, four P3 documented

Every claim below was re-derived from production code. Counts, timings and mutation results were
measured in this review, not copied from the design document.

---

## 1. Scope of the review

Four questions, in order of consequence:

1. Does the milestone's central guarantee — the ADR-0020 D1 containment — actually hold?
2. Is the hazard it contains real, and how bad is it?
3. Is the root genuinely a root: no calculation, no clock, no interpretation, nothing importing it?
4. Does anything ship untested?

---

## 2. Is the D1 hazard real? — measured

ADR-0020 asserts a mismatched `confirmation_bars` is *undetectable*. Re-derived independently over
**300 seeded irregular series × 5 wrong delay values = 1,500 mismatched calls**, comparing against the
correct `confirmation_bars = right_bars = 3`:

| Outcome | Count | Share |
|---|---:|---:|
| **Materially different breaks** (different side/bar set) | **541** | **36.1 %** |
| Provenance-only drift (same breaks, different `eligible_from`) | 959 | 63.9 % |
| **Errors raised** | **0** | **0 %** |

Of the 541 material cases, **155 also changed the number of changes of character** — the hazard
propagates a full layer up.

**The hazard is confirmed, quantified, and worse than a count comparison suggests.** An early check
that compared only break *counts* found no difference on one series and would have concluded the
hazard was theoretical; comparing break *identity* shows every single mismatched call produced a
different result, and a third of them a materially different one. Anyone assessing this hazard should
compare identity, not counts.

## 3. Does the containment hold? — verified two ways

**Structurally.** `build_structural_facts` has no `confirmation_bars` parameter. The only way to set
the delay is `DetectionSettings.right_bars`, which simultaneously sets detection. Two different values
are unrepresentable through this root:

```
build_structural_facts params: ['series', 'features', 'detection', 'source', 'window', 'metadata']
'confirmation_bars' in params: False
DetectionSettings fields:      ['left_bars', 'right_bars']
```

**Behaviourally.** The root's breaks equal `derive_structure_breaks` called directly with the matching
delay — asserted on an independent path in `test_breaks_agree_with_a_hand_matched_direct_call`.

**Correctly scoped.** The claim is containment, not a fix, and both the ADR and the printed sheet say
so. Verified that every *other* caller of `derive_structure_breaks` remains exposed — there are
currently none besides this root and the test suite, which is why Milestone AG is not urgent but is
owed.

## 4. Is the root a root? — verified

| Claim | Method | Result |
|---|---|---|
| No arithmetic at all | AST walk for any arithmetic `BinOp` | **0** — one stricter than ADR-0007 §2 allows `market_analysis` |
| No maths imports | AST import scan | no `math`, `statistics`, `decimal`, `fractions`, `random` |
| No clock | source scan | no `datetime.now`, `utcnow`, `time.time`, `time.monotonic` |
| Nothing below imports it | tree walk over `src/fmis` excluding `pipeline` | **0** references |
| Importing an engine does not load it | cold import of `fmis.market_structure` | no `fmis.pipeline` in `sys.modules` |
| No foreign private modules reached | AST import scan | none |
| Reuse is real, not restated | root output compared with engines called directly | swings, labels, levels, crossings all equal |

**Cross-process determinism.** The rendered sheet hashes identically under `PYTHONHASHSEED` 0, 1, 42
and 12345 in fresh processes: `1074475eb249772f` in all four.

## 5. Findings

### P2-1 — the change-of-character render branch was executed by no test *(found and fixed)*

Coverage of `render.py` was 95 %, and the uncovered lines were the branch that prints an *existing*
change of character (lines 182–186).

The cause was fixture blindness rather than oversight: **all three series fixtures in the suite —
the committed 20-candle `btcusdt_4h.json`, the regular `wave` zig-zag, and the irregular walk — produce
zero changes of character.** Every test therefore exercised only the "none in this window" path. A
defect in the rendering of an actual change would have shipped, and the live BTCUSDT run produces
eight of them, so it would have shipped into the first real use.

**Fixed.** A fourth fixture (`choch_series`, a committed walk found by search) produces changes;
five tests were added covering the change branch, the change count, an origin-less level, and the
non-numeric value formatters. A guard test asserts the fixture still produces changes, so the gap
cannot silently reopen. `render.py` is now **100 %**.

Four mutation probes were added for the newly covered path, all detected.

### P3-1 — `build_structural_facts` gained a public `window` parameter

`structural_facts_for_symbol` reuses `_fetch_closed`, which returns an already-closed series. Without
an override the sheet would report `excluded_forming_count=0` and silently lose the fact that the
provider returned a forming bar — caught by a test during implementation.

The parameter is public and unvalidated: a caller may pass a window inconsistent with the series. The
mitigation is that it changes **what is reported, never what is computed** — the candles analysed are
always `series.closed()` — and this is stated in the docstring. Recorded rather than fixed, because
validating consistency would mean re-deriving the window, which is the duplication the parameter
exists to avoid.

### P3-2 — `_level_sort_key` restates the shape of a private ordering key

`fmis.level_crossing.models._level_key` is the authoritative level ordering and is private to its
package, so it cannot be imported. The root needed a total order for tie-breaking and defined its own
with the same shape.

Two orderings for one concept is a smell. It is contained: the root's key is private, used only for
nearest-level selection, and deliberately **not** distance-based. If a third consumer needs level
ordering, the right fix is to make `_level_key` public rather than write a third copy.

### P3-3 — quadratic runtime, inherited

Measured, five runs each, median:

| candles | median | crossings | growth |
|---:|---:|---:|---:|
| 100 | 1.5 ms | 668 | — |
| 500 | 18.2 ms | 4,068 | ×4.37 |
| 1,000 | 61.4 ms | 8,318 | ×3.37 |
| 2,000 | 223.1 ms | 16,818 | ×3.64 |
| 5,000 | 1,318.9 ms | 42,318 | ×5.91 |

Attributed by stage, `derive_level_crossings` is **90.6 %** of total at 1,000 candles, **94.9 %** at
2,000 and **97.2 %** at 4,000. Every other stage is linear; the composition root's own overhead is
negligible.

This is ADR-0019's documented `O(candles × levels)` with levels growing linearly in candles —
**inherited, not introduced by this milestone**. A single 5,000-candle sheet at ~1.3 s is acceptable
for a CLI. A scanner over many symbols is not viable without a level-selection policy, which is
Phase 3's support/resistance work.

### P3-4 — six import guards were widened

Each named its permitted consumers explicitly and each failed when `fmis.pipeline` became a consumer.
The guards behaved exactly as designed: they forced ADR-0022 to exist rather than allowing a silent
new dependency. Every widening is documented in the guard's own docstring, and the direction rule each
guard exists for — no engine may import upward — is unchanged.

Verified by re-reading all six: no guard was weakened beyond naming `fmis.pipeline`, and the two
`market_structure` guards retain every other scanned package.

## 6. A defect the existing suite caught

`__main__.py` originally ran `raise SystemExit(main())` at module level. Several suites walk the
package tree and import every module to check export collisions; that import **ran the CLI against
pytest's own `sys.argv`**, surfacing as an argparse error inside four unrelated tests.

Fixed with a `__name__` guard, now documented in the module as load-bearing rather than boilerplate.
Worth recording because the failure appeared nowhere near its cause, and because it is a defect the
new milestone's own tests would not have found — the pre-existing guards did.

## 7. Adversarial inputs

| Input | Result |
|---|---|
| Empty series | `InsufficientDataError`, naming the shortfall |
| One candle | `InsufficientDataError` |
| Exactly the required 5 candles | Succeeds; 0 swings, `indeterminate` trend |
| All prices identical (40 candles) | Succeeds; 0 swings — strict-left detection, as specified |
| Monotonic ramp (no swings) | Succeeds; 0 swings |
| Values near 1e-8 | Succeeds; no overflow or formatting failure |
| Values near 1e12 | Succeeds |
| Level exactly at the close | Neither above nor below — asserted |
| Two levels at one price | Deterministic tie-break in any input order |
| Reference time before the data | "reference precedes the data", not a negative age |
| Naive `--reference-time` | Rejected with a message naming the requirement |

## 8. Mutation results

**39 probes, 39 detected, 0 survivors, 0 no-ops.**

Six survived the first round. **All six were test-suite gaps, not equivalent mutants**, and each was
closed rather than tolerated:

| Probe | Why it survived | Closure |
|---|---|---|
| `left_bars` replaced by the delay | Every fixture used a symmetric bar pair, making the swap invisible | Asymmetric pair (L3 R5) over a committed irregular walk, plus an assertion that the swapped pair genuinely differs |
| Tie-break loses the origin index | The tied levels had different labels, so the label alone decided | Same label on both, making the index the deciding field |
| Per-row warm-up note removed | The section header also contains "warming up" | Assert the note on the `ema_50` row specifically |
| Break presence inverted | Only the row label was asserted | Assert the rendered side and bar; plus a no-break case |
| Nearest above/below swapped | The fixture has `above=None` | A series where both exist and differ, asserting values per line |
| `--no-age` ignored | Absence was never asserted | Assert absent with the flag, present without |

The pattern in five of the six is the same and worth naming: **an assertion that a *label* appears is
not an assertion that the *fact* is right.** Four of the closures replaced a presence check with a
value check.

## 9. Live verification

`fmits facts BTCUSDT --interval 4h --limit 200` against the real Binance endpoint returned a complete
sheet: 199 closed candles with 1 forming excluded, all six features ready, 50 swings (48 labelled),
`sustained_lower` trend, 18 breaks, 8 changes of character, 48 levels, 1,355 crossing events, nearest
level each side of the close, and six limitations.

Notably the nearest level *below* the close is an **UPPER** level — a former swing high price has
traded through. This is the concrete case ADR-0022 §5 was written to protect: naming it "support"
would assert something the data does not say.

## 10. Verdict

| Severity | Count | Detail |
|---|---:|---|
| **P0** | 0 | — |
| **P1** | 0 | — |
| **P2** | 1 | Change-of-character render branch untested — **fixed**, coverage now 100 % |
| **P3** | 4 | Public `window` parameter · duplicated ordering-key shape · inherited quadratic runtime · six widened guards |

**3,305 tests pass**, identically under `-W error`. New-module coverage: `cli.py` 100 %,
`structural_facts.py` 100 %, `render.py` 100 %.

The milestone does what it claimed: it connects 51.2 % of the codebase to real market data without
adding an engine, and the structural contracts required **no change** to accommodate their first real
caller — which is the strongest available evidence that the ten milestones beneath it were layered
correctly.

**The one thing this review would not let pass silently** is the D1 framing. "Contained" is accurate
and "fixed" would not be; the ADR, the module docstring and the printed sheet all say contained. That
distinction should survive into Milestone AG rather than being quietly upgraded.
