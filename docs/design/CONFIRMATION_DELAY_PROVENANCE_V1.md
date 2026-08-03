# Confirmation-Delay Provenance v1 — Design

**Milestone:** AH
**Status:** Implemented by [ADR-0024](../adr/ADR-0024-confirmation-delay-provenance.md)
**Date:** 2026-08-03
**Closes:** ADR-0020 deferred question **D1**

---

## 1. The problem, measured

`derive_structure_breaks` required a `confirmation_bars` argument that had to equal the `right_bars`
used to detect the underlying swings. Nothing checked that, and nothing could: the number was on none
of the inputs.

A wrong value is **not** a crash and not obviously wrong output. It changes which level is the
reference at every bar, and therefore:

| What changes | How |
|---|---|
| Level eligibility | a level becomes the reference earlier or later than it was knowable |
| Reference selection | a different level is "most recent eligible" at a given bar |
| Breaks of structure | different breaks exist |
| Changes of character | derived from the break run, so they change with it |
| Everything above | trend context, fact sheets, and any future regime call |

Measured across 300 seeded series against five wrong delays: **36.1 % produced materially different
breaks**, 155 of those also changed the change-of-character count, and **zero raised an error**.

Two milestones contained it locally — AF by reading `DetectionSettings.right_bars` once and handing
one value to both consumers, AG by passing one `DetectionSettings` to all three views. Containment
protects callers who use those roots. The Market Regime Engine is the second consumer of
`derive_structure_breaks`, and it is not one of them.

## 2. Scope

**In:** carrying the delay on the models that already carry provenance · deriving eligibility from it
· removing the argument from every public entry point · rejecting conflicting provenance · the
migration · tests · this design · an ADR · an independent review.

**Out, and asserted:** the Market Regime Engine · trend agreement · signals · direction vocabulary ·
portfolio · risk · AI · persistence · scanner · scheduling · new indicators · new market-structure
concepts · sub-bar reconstruction · BOS invalidation · failed CHoCH.

## 3. The design questions, resolved from the repository

### 3.1 Should `LevelOrigin` store `confirmation_bars`?

**Yes — but storing it there alone is not enough.**

`structural_levels` builds every origin from a swing. If only `LevelOrigin` carried the window, that
function would need it as a parameter, and a caller could then record a window the swings were not
detected under. That is the same hazard one layer up, and worse, because a wrong value would look
like recorded provenance. ADR-0022 already named this the *fake fix*, and the backlog carried it as
the explicitly rejected approach before this milestone began.

So the window must be stamped where it is known — in `detect_swings` — and copied outward. That means
`SwingPoint` carries it too, which is the shipped-model change the milestone was sized around.

### 3.2 Should it store `eligible_from` directly?

**No.** Two reasons, both from existing rules.

ADR-0016 §4: a stored copy of a value one attribute away is somewhere for it to drift. `eligible_from`
is `index + confirmation_bars`; storing both duplicates a derivable value, and storing only
`eligible_from` throws away the window, which is the auditable fact.

And *eligibility* is break-of-structure vocabulary. `fmis.structure_break` decides that a level
becomes eligible at its confirmation bar; the level layer must not pre-empt that decision by naming a
field after it.

### 3.3 So what is the property called?

`knowable_from` — the bar at which the pivot became knowable. It is a fact about **detection**, not a
policy about what may be done there.

The name is the repository's own: `swings.py`'s module docstring already says *"A swing at `i` is
knowable only once `right_bars` further candles have closed."* It also passes
`fmis.market_structure`'s vocabulary guard, which bans `confirmed` as an interpretation word — a
first attempt named it `confirmed_at` and that guard rejected it. The guard was right and the name
changed; the guard was not weakened.

### 3.4 Is a compatibility path safe?

**No, and this is the decision the milestone turns on.**

Keeping `confirmation_bars` as an optional argument — defaulting to the level's own provenance,
overridable — would leave two sources of truth and preserve the exact hazard. The brief says so
directly: *do not merely add a runtime warning while continuing to accept two independent sources of
truth.* The argument is removed outright.

### 3.5 What becomes impossible to represent?

| Was representable | Now |
|---|---|
| A break derived under a delay that disagrees with detection | Unrepresentable — no entry point takes one |
| A `StructureBreak` whose `eligible_from` contradicts its own level | Unrepresentable — it is a projection |
| A confirmation window of 0 | Rejected at both models |
| A break at bar 0 | Unrepresentable — the earliest knowable bar is 1 |
| A level set mixing two detection windows | Rejected as `StructureBreakInputError` |
| A `SwingComparison` spanning two detection windows | Rejected at construction |

The bar-0 case is worth stating plainly: it was only ever reachable from a hand-built fixture, since
`detect_swings` rejects a window below 1. A test now pins that it is impossible.

### 3.6 Why must one level set share one window?

`_reference` is a binary search. Its equivalence to the linear scan it replaced (proved by test over
an exhaustive small space) rests on `eligible_from` being **strictly increasing within a side**, which
follows from strictly increasing origin indices *when the window is shared*. Mixed windows break it:
a later pivot detected under a shorter window can become knowable before an earlier one.

The single-test eligibility rule rests on the same property — `_reference(...) is level` implies
`level.origin.knowable_from <= crossing.index` only because eligibility values increase with origin
index. Accepting mixed windows would silently weaken both, so a mixed set is rejected instead.

## 4. Migration

Every construction site of a shipped model had to state the window it means. There is no default, on
purpose, so this is mechanical but not silent.

| Site | Count | How |
|---|---:|---|
| `SwingPoint(...)` in tests | 69 | AST-positioned insertion of `confirmation_bars=CB` |
| `LevelOrigin(...)` in tests | 11 | same |
| `derive_structure_breaks(..., confirmation_bars=…)` | 106 | AST-positioned removal of the keyword |
| `StructureBreak(..., eligible_from=…)` | 17 | same |
| `_levels_by_side(levels, bars)` | 4 | window moved onto the fixture levels |
| `SwingPoint(...)` in production | 2 | `confirmation_bars=right` in `detect_swings` |
| `LevelOrigin(...)` in production | 1 | copied off the swing in `structural_levels` |

The insertions and removals were done by **AST position**, not regex: a keyword argument is valid
whether the call was written positionally or by keyword, and editing by node position preserves the
surrounding formatting whether the call is on one line or wrapped.

Three test-suite changes were **semantic**, not mechanical, and each is a behaviour that genuinely
changed:

1. `_require_bars` moved from `swings.py` to `models.py`. `SwingPoint` must apply the same rule, and
   `swings` imports `models`, so importing back would close a cycle. Detection and provenance now
   share one validator and one wording.
2. Fixtures that built break runs starting at bar 0 shift to bar 1. Bar 0 is no longer breakable.
3. Two import-direction guards that scan raw source text now blank docstrings first. Milestone AH
   gave `SwingPoint` and `LevelOrigin` docstrings that *name* the layer above to explain which layer
   owns eligibility — precisely the boundary those guards defend. A guard that forbade naming the
   rule it enforces would push the explanation out of the code. Comments and non-docstring literals
   are still scanned, so a dynamic `importlib.import_module(...)` remains caught.

## 5. Invariants, each test-enforced

| # | Invariant | How |
|---|---|---|
| I1 | Detection stamps its own `right_bars` on every point | four windows over seeded series |
| I2 | The window survives swing → comparison → label → level unchanged | three windows, every level checked |
| I3 | `knowable_from` is a projection on both models | not in `__dataclass_fields__`; is a `property` |
| I4 | No public entry point accepts a confirmation delay | `inspect.signature` over all three |
| I5 | Behaviour is unchanged where the old delay matched | pre-AH algorithm reimplemented and compared |
| I6 | A mixed-window level set is rejected, deterministically | exact message, asserted five times |
| I7 | Prefix stability is preserved | 20 series × every 10-bar prefix, 0 violations |
| I8 | No clock and no provider in the deterministic layer | docstring-stripped source scan |
| I9 | The public export surface is unchanged | 13 / 19 / 5 names, asserted |

## 6. Measured results

**Correctness.** 3,449 tests pass, identically under `-W error` (3,404 before AH; **+45**).
Coverage on every module AH touched is **100 %**, except `market_structure/models.py` and
`pipeline/structural_facts.py` at 99 %, whose single uncovered lines each predate this milestone
(`d1c0b3b0` and `1505dd8a`). Public exports **154**, zero collisions — **unchanged**, because AH adds
fields and properties, not names. Import cycles **0**. Runtime dependencies **0**. `pyproject.toml`
and `uv.lock` untouched.

**Mutation.** 42 probes across seven modules: **41 detected, 1 proven-equivalent survivor, 0 no-ops**,
with byte-identical source restoration verified by SHA-256.

The survivor is `structural_levels` reading `previous` instead of `current` for the window. It cannot
be detected by any test, because `SwingComparison` now rejects a pair whose windows disagree, making
the two expressions provably equal. It is reported as an equivalent mutant rather than counted as
zero, and the invariant that makes it equivalent is asserted directly.

Two probes that survived their first run were **real gaps**, both fixed — see
[the review](../reviews/CONFIRMATION_DELAY_PROVENANCE_V1_REVIEW.md) §5: the rendered detection row
could not distinguish `left_bars` from `right_bars` while every fixture used `L2 R2`, and the
cross-window rejection message was asserted only by substring.

**Regression.** The pre-AH algorithm, reimplemented independently, agrees with the new derivation on
every break across 40 seeded series at four detection windows. On the same fixtures a wrong delay
changes the answer on more than a third of them — the defect and the proof that fixing it changed
nothing else, measured on one data set.

**Live.** `fmits facts BTCUSDT --interval 4h --limit 200` and `fmits mtf BTCUSDT -n 260` both render
correctly against real Binance data, now printing **six** limitations rather than seven, with
`ADR-0020 D1` absent from both.

## 7. What it does not claim

The delay is now carried, not *interpreted*. Nothing here decides whether a level is support, whether
a break matters, or whether timeframes agree. `fmis.structure_break` still owns the rule that
eligibility begins at the confirmation bar; this milestone only ensures that the bar it reads is the
one detection actually earned.
