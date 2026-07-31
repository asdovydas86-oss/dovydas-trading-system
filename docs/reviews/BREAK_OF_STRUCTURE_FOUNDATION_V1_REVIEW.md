# Break of Structure Foundation v1 — Independent Review

**Reviewed:** `fmis.structure_break` as merged into local `main` at
`73e61e2b570b3ccd18ee9780d5789230365e95e4` (*Merge Break of Structure Foundation v1*).
**Method:** every claim below was **re-derived from the shipped package**. No design claim, test count,
ordering claim, stability claim or documentation example was taken on trust. The 48 adversarial cases,
the complexity instrumentation and the mutation harness were written against the shipped code and run
independently of the milestone's own suite.

---

## 1. Verdict

**One real defect found and fixed: the reference lookup was a linear scan per crossing**, making the
derivation O(crossings × levels-per-side) — measured at **125,000,000 inner iterations** for 5,000 levels
against 50,000 crossings. Replacing it with an exact binary search cut that case from ~1.3 s to **0.026 s**
and made runtime independent of the level count.

Everything else held. **48/48 adversarial cases pass**, prefix stability is exact at 0 violations across
every fixture class and four confirmation delays, and the two central claims — that BOS reads no candle,
and that a break is non-repainting — are true **structurally**, not merely by discipline.

| Severity | Found | Fixed |
|---|---|---|
| **P0** | 0 | — |
| **P1** | 0 | — |
| **P2** | 1 | 1 |
| **P3** | 3 | 1 (2 documented) |

---

## 2. Findings

### P2-1 — Reference lookup was linear per crossing *(fixed)*

`breaks._reference` walked the side's level list for **every** qualifying crossing. Because the list is
sorted by `eligible_from` and a crossing's index is usually beyond every level's eligibility, the loop's
early `break` almost never fired, so each call scanned the whole side.

Instrumented against the shipped code:

| Levels × crossings | `_reference` calls | Inner iterations |
|---|---|---|
| 100 × 10,000 | 10,000 | 500,000 |
| 1,000 × 10,000 | 10,000 | 5,000,000 |
| 5,000 × 50,000 | 50,000 | **125,000,000** |

Growth is the **product**, not linear in either factor — a shape that would bite exactly when it matters
least visibly: a long series with many swings.

**Fix.** `bisect_right` with a key over the same list. The list is sorted by `eligible_from`, and those
values are **strictly increasing within a side** because `_levels_by_side` rejects two levels sharing an
origin index — which is what makes the binary search find the *same element* the scan did, not merely a
similar one. `bisect` is standard library; no dependency was added.

Measured after the fix, same shapes:

| Levels × crossings | Before | After |
|---|---|---|
| 100 × 10,000 | 0.021 s | **0.003 s** |
| 1,000 × 10,000 | 0.207 s | **0.003 s** |
| 5,000 × 50,000 | ~1.28 s | **0.026 s** |
| 20,000 × 200,000 | *(not attempted)* | **0.089 s** |

Runtime is now linear in crossings and effectively independent of the level count.

**Verified, not asserted.** `test_the_reference_lookup_matches_an_exhaustive_linear_reference` compares the
binary search against a deliberately naive linear implementation over **every** arrangement of up to four
levels at nine possible origins, four confirmation delays and seventeen as-of indices — 5,000+ comparisons,
including the empty list and indices before any eligibility.
`test_the_reference_lookup_is_sublinear_in_the_level_count` pins the complexity itself by counting index
probes at 16 and 1,024 levels. Three new mutation probes (12, 13, 14, plus off-by-one and empty-guard
variants) target the replacement.

### P3-1 — A `confirmation_bars` mismatch is undetectable in one direction *(documented)*

The design names this as D1. The review quantified it: detecting swings with `right_bars=3` and then
passing `confirmation_bars=2` produces a **different break set** from the correct call, with no error.

The review then asked whether it is detectable, and found it is — **but only halfway**. Since no breach can
occur inside a level's true confirmation window (§3), observing a *breach* at `index - origin.index <
confirmation_bars` proves the supplied delay is **too large**. Supplying one that is too *small* leaves no
trace.

**Deliberately not implemented.** Enforcing it would reject legitimate hand-built level sets whose origins
did not come from swing detection at all — including several of this milestone's own tests, which pair a
level at origin 5 with a crossing at bar 6. Half a check that breaks a valid use case is worse than an
honest limitation. Recorded as **D1**, and the real fix remains carrying the delay on `LevelOrigin`.

### P3-2 — Crossing indices are unbounded *(documented, inherent)*

A crossing at index 1,000,000 against a level at origin 5 yields a break, with no candle series that long.
BOS cannot detect this **because it never sees candles** — which is the mission, not an oversight.
`derive_level_crossings` already guarantees indices are positions in its own closed-candle sequence, so the
guarantee is inherited rather than re-checked. Re-checking would require the dependency the package exists
to avoid. Recorded as a limitation.

### P3-3 — The redundant eligibility check *(fixed during implementation)*

Worth recording because it was found by mutation, not by reading. `derive_structure_breaks` originally
carried an explicit `origin.index + bars > crossing.index` test **beside** the reference test. Probes 7 and
9 survived, and the reason was not a test gap: `_reference` returns a level only when its `eligible_from <=
index`, so the explicit check was **provably unreachable** — an equivalent mutant by construction. It was
removed rather than papered over with a contrived test, leaving the eligibility arithmetic in exactly one
place (`_levels_by_side`), where three probes now target it directly.

---

## 3. Re-derived contract verification

Each row was checked against source and behaviour, not documentation.

| Claim | Verdict |
|---|---|
| **BOS reads no candle** | ✅ **structural** — `fmis.data` is not imported at all; `Candle` is not a reachable name; no `open`/`high`/`low`/`close`/`volume` attribute access anywhere. Imports are exactly `fmis.level_crossing`, `fmis.series_context`, `fmis.market_structure` |
| **No trend dependency** | ✅ absent from imports **and** source text |
| `CLOSE_BREACH` required | ✅ `TOUCH` and `WICK_BREACH` never break, on both sides |
| policy not configurable | ✅ the signature admits only `levels`, `crossings`, `confirmation_bars` |
| `GAPPED_BEYOND` qualifies | ✅ and the mechanism is carried through, not used to filter |
| `ALREADY_BEYOND` excluded | ✅ by mechanism, and separately unreachable by eligibility — both tested |
| equality / label policy | ✅ all six labels produce a break; `EQUAL_HIGH` and `EQUAL_LOW` carried unchanged; break counts identical across labels, proving the label is never read |
| eligibility = origin + delay | ✅ exact at 0, 1, 2 and 7 bars; not eligible at `origin+delay-1`, eligible at `origin+delay` |
| `confirmation_bars` required | ✅ keyword-only, no default; negative rejected |
| reference = most **recent** eligible | ✅ superseded levels never break; a *lower* high becomes the reference once confirmed |
| reference respects the as-of index | ✅ the older level is still the reference while the newer one is unconfirmed |
| sides independent | ✅ |
| **structure breaks once** | ✅ per level, and earliest-wins under every input permutation |
| never invalidated | ✅ no field, and appending later crossings never withdraws a break |
| no direction / bullish enum | ✅ `side` projects the level's side; nothing else |
| validation rejects, never repairs | ✅ unprovenanced level, ambiguous origin index, unknown-level crossing — all raise, with exact messages |
| **membership is by identity** | ✅ an equal-valued but distinct level object is rejected, not silently accepted |
| model self-validation | ✅ a break claiming a touch, a wick, `ALREADY_BEYOND`, no provenance, or a bar before eligibility cannot be constructed |
| immutability / hashing / pickle | ✅ frozen+slots; attribute set and new attribute both raise; round-trips equal and hash-equal |
| **ordering** | ✅ `(bar, side)` with `UPPER` first from an explicit rank; strictly increasing; index order is timestamp order |
| **input-order invariance** | ✅ 15 random shuffles of **both** inputs, plus full reversal, plus 3× duplicated crossings — all byte-identical |
| **prefix stability** | ✅ **0 violations**: 121 prefixes on a seeded fixture, delays 1–4, the documented counterexample, handcrafted edge cases, the real fixture |
| replay determinism | ✅ identical across 5 runs and across rebuilt pipelines |
| context integrity | ✅ mismatch rejected **before** derivation (proved by pairing a bad level set with a mismatched identity — the identity error wins); identity by reference; empty result keeps the **levels'** identity object; no identity argument exists |
| one bar breaking both sides | ✅ reachable, `UPPER` then `LOWER`, one shared timestamp, no path field |
| public exports | ✅ 5 names; **0 collisions** across the whole `fmis` tree |
| **future CHoCH** | ✅ 2 character changes derived from 4 breaks using `side` and order alone |

---

## 4. Adversarial cases — 48/48 pass

Semantics 1–6 · eligibility 7–10 · reference selection 11–15 · lifecycle 16–19 · labels 20–23 ·
validation 24–27 · model self-validation 28–31 · ordering and invariance 32–35 · prefix stability 36–38 ·
context 39–43 · architecture 44–46 · CHoCH 47 · exports 48.

Selected results:

| Case | Result |
|---|---|
| unprovenanced level | `levels[0] carries no origin (upper 100.0); a break needs provenance to place the level in time` |
| ambiguous origin index | `levels[1] shares origin index 5 with another upper level; the reference level at that point would be ambiguous` |
| unknown-level crossing | `crossings[0] references a level absent from levels (upper 200.0)` |
| break before eligibility | `crossing index (6) precedes eligible_from (7); the level was not yet knowable` |
| instrument mismatch | `subjects[1] has identity 'ETHUSDT'/'4h', expected 'BTCUSDT'/'4h'` |
| timeframe mismatch | `subjects[1] has identity 'BTCUSDT'/'1h', expected 'BTCUSDT'/'4h'` |
| input-order invariance | 4 breaks from 79 levels / 2,472 crossings, stable over 15 shuffles of both |
| prefix stability | 0 violations, 121 prefixes; 0 across delays 1–4; 0 on the counterexample |
| equal-valued distinct level object | rejected — no identity leak |
| huge `confirmation_bars` (10⁶) | `()` — every level permanently ineligible, no crash |
| level origin beyond every crossing | `()` |
| zero `confirmation_bars` | `eligible_from == origin.index`, permitted |
| `StructureBreakError` as a group | catchable |

---

## 5. Performance

Measured on the shipped implementation after the P2 fix, each run repeated to confirm determinism.

| Levels × crossings | Runtime | Breaks | Peak memory | Repeatable |
|---|---|---|---|---|
| 100 × 10,000 | 0.003 s | 2 | <0.1 MB | ✅ |
| 1,000 × 10,000 | 0.003 s | 2 | 0.2 MB | ✅ |
| 100 × 100,000 | 0.025 s | 2 | <0.1 MB | ✅ |
| 5,000 × 50,000 | 0.026 s | 2 | 1.4 MB | ✅ |
| 20,000 × 200,000 | 0.089 s | 2 | — | ✅ |

Doubling the level count at fixed crossings costs nothing; the cost tracks crossings alone. Memory is
small because breaks hold levels and crossings **by reference** — no OHLC value is copied.

No further optimisation is recommended, and the repository defines no benchmark threshold.

---

## 6. Mutation validation after the review fix — 42/42 detected

Re-run independently after the fix, with the three `_reference` probes re-anchored on the binary search and
two variants added (off-by-one via `bisect_left`, and dropping the empty guard).

| Result | |
|---|---|
| probes | **42** |
| no-ops (SHA unchanged) | **0** |
| survivors (undetected) | **0** |
| restore failures | **0** |
| final SHA-256 match, all three sources | ✅ |

```
models.py    3774f556c8d1fc3adef3e9e97ef200251280eb29ed8362b2372dd9745bb16fb0  match=True
breaks.py    ed3f0a138e741ec18341848096fd48d51bed5835ff8afeffcb22dc8ae713a499  match=True
pipeline.py  09f0e3e4577c9f6bf132412a8c6f6ecc66d79b0d85670d08180136bfc0235967  match=True
```

Probes cover: accepting `TOUCH`/`WICK_BREACH`, rejecting `CLOSE_BREACH`, accepting `ALREADY_BEYOND`,
rejecting `GAPPED_BEYOND`, pivot-bar and ±1 eligibility, ignoring the delay, dropping or corrupting the
reference rule, first-vs-most-recent and most-extreme references, ranking by price, merging the two sides,
all-crossings and last-crossing lifecycles, ignoring each of the three input validations, reversing and
skipping the sort, side-before-index ordering, swapping the side ranks, defaulting `confirmation_bars`,
accepting a negative delay, dropping each of the model's three self-validations, projecting the wrong
timestamp or side, making the model mutable, skipping or weakening the identity check, rebuilding rather
than carrying identity, losing identity on an empty result, adding an identity-override argument, **reading
a candle field**, and importing the structural-trend package.

Two survivors were recorded and resolved during implementation rather than papered over: the redundant
eligibility check (§P3-3, removed as an equivalent mutant) and an empty-result identity test that passed a
single shared identity object, making a wrapper returning the *crossings'* identity indistinguishable —
now two equal-but-distinct objects, so `is` actually discriminates.

---

## 7. Validation results

| Check | Result |
|---|---|
| full suite | **3033 passed** |
| full suite, `-W error` | **3033 passed** |
| `tests/test_structure_break.py` | **175** |
| `tests/test_level_crossing.py` | **247** (246 + 1 added guard) |
| `tests/test_series_context.py` | **185** (183 + 2 added guards) |
| `tests/test_market_structure_*.py` | **1227** (unchanged) |
| `tests/test_structural_trend.py` | **353** (unchanged) |
| export collisions across `fmis` | **0** |
| `git diff --check` | clean |
| `pyproject.toml`, `uv.lock` | **unchanged** |
| runtime dependencies added | **none** — `bisect` is standard library |
| existing analytical behaviour changed | **none** |

---

## 8. What was *not* changed, and why

- **No `confirmation_bars` default was added.** The footgun is real (P3-1) but a default makes it silent
  for anyone who chose a different `right_bars`, which is strictly worse than an argument they must think
  about.
- **The half-detectable mismatch check was not implemented** — it would reject valid hand-built level sets
  (§P3-1).
- **No invalidation, no "failed break", no most-extreme reference.** Each is a later reading or a
  protected-level policy, and each belongs to a layer that does not exist yet.
- **The crossing run's canonical order is still not re-validated.** BOS is order-invariant instead, which
  keeps the ordering contract's single implementation in `fmis.level_crossing`.

---

## 9. Remaining P2 / P3

| | Item | Status |
|---|---|---|
| P3-1 | `confirmation_bars` mismatch undetectable in the under-supplied direction | **Open, documented (D1).** Real fix is carrying the delay on `LevelOrigin`, in its own milestone. |
| P3-2 | crossing indices unbounded — BOS cannot check, having no candles | **Open, inherent.** Guarantee inherited from `derive_level_crossings`. |
| — | D2 first-swing levels, D3 no invalidation, D4 exact floats, D5 most-recent reference, D6 per-side independence | **Open by design**, each recorded in ADR-0020 §6. |

No P0, P1 or P2 remains.

---

## 10. Recommended next milestone

**Change of Character Foundation v1.** Adversarial case 47 derives 2 character changes from a 4-break
sequence using **`side` and ordering alone** — no level, no crossing, no candle. Review §15's ordering is
therefore complete and available: BOS on levels, CHoCH over the BOS sequence, trend a summary of both.

What CHoCH must decide, all left open here: whether one opposing break constitutes a change or a run of
them; how the first break is treated, having no predecessor; whether an `EQUAL_*`-derived break counts
(using the label BOS carries but never reads); whether two breaks sharing a bar can constitute a change,
**given that their order is not a time claim**; and whether a change is ever invalidated, which BOS
deliberately has no notion of.

**Worth scheduling first:** carrying the confirmation delay on `LevelOrigin` (D1). It removes the one
undetectable failure mode in the current pipeline and changes a shipped model, so it needs its own ADR.
