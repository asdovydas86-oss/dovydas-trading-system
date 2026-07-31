"""Level crossing — deterministic facts about price meeting a level.

The first layer to read **both** candles and derived structure. It answers one
question and refuses the next one:

    Did price cross a specific structural price level, when did it happen,
    how did it happen, and under which explicit policy?

Value types and pure functions in two stages, plus a safe context-aware boundary:

    StructuralSwings -> structural_levels        -> tuple[PriceLevel, ...]
    CandleSeries + PriceLevels
                     -> derive_level_crossings   -> tuple[LevelCrossingEvent, ...]

**Facts, not structure.** A `LevelCrossingEvent` says that at *this* candle,
*this* level was touched, breached by an extreme, or breached by a close, and
whether price demonstrably reached the level or arrived on the far side without
trading at it. That is arithmetic about two numbers and one bar. It does not say
that structure broke, that character changed, that a trend exists, that a level
was protected, or that anything should be traded.

**Why crossing is separated from BOS and CHoCH.** A crossing is a geometric fact.
Break of Structure is an *interpretation* built from a crossing plus a decision
about which level was protected, when protection ends, and whether an
`EQUAL_HIGH`-derived level breaks anything. Change of Character is a further
interpretation over the *sequence* of those decisions. The market-structure
architecture review §15 fixed the ordering and it stands: **BOS is defined purely
on levels, CHoCH over the BOS sequence, and trend is a summary of both, defining
neither.** Any definition in which trend is an input to BOS is rejected on sight —
which is why this package imports the structural-trend package nowhere, and a
test enforces it. (Its dotted name is deliberately not spelled anywhere in this
package's source, prose included, so that package's own text-scan guard stays
crude and unweakened.)

The practical consequence: a crossing event must be usable by a BOS layer that
*disagrees* with any particular protected-level policy. So v1 has no lifecycle at
all.

**The crossing policy, in full, and it is not configurable.** For an `UPPER`
level at price ``L``:

    high <  L                  -> nothing
    high == L                  -> TOUCH
    high >  L and close <= L   -> WICK_BREACH
    high >  L and close >  L   -> CLOSE_BREACH

Mirrored on ``low`` for a `LOWER` level. The three kinds are mutually exclusive
and exhaustive over "an interaction occurred". Touch, wick breach and close
breach are three *facts on the event*, not three settings: a configurable rule
would make every historical event non-reproducible without its setting, which is
the argument review §9 uses to keep tolerance out of comparison. A consumer that
only trusts closes filters on `CrossingKind.CLOSE_BREACH` and gets a stronger
guarantee than a setting would have given it.

**Exact equality is a touch, never a breach.** Comparison is exact on stored
floats — no epsilon, tolerance, percentage band, ATR scaling, rounding or
`Decimal` — inheriting ADR-0013 §4 and review §9, which record that tolerance is
a claim about instrument precision and belongs at ingestion, behind a tick-size
model that does not exist. The consequence is deterministic and documented: with
a level at ``0.3``, a high of ``0.1 + 0.2`` is a strict breach.

**How the candle came to be there is a separate, orthogonal fact.**
`CrossingMechanism` distinguishes price *reaching* the level within the candle's
range from price *arriving beyond it* without trading there — a gap — and from a
series that simply *starts* beyond it. ``open`` is never consulted, because an
open beyond a level whose low came back through it did trade at the level.

**No intrabar path is ever claimed.** An outside bar breaching an upper and a
lower level produces two events sharing one index and one timestamp, and their
relative order in the output is the *level* ordering, not a claim about which
happened first. OHLC data cannot prove that. There is deliberately no path field
and no "order unknown" flag: intrabar order is never known, for every event, so a
flag that never varies carries no information and would imply that its absence
means "known".

**Ordering is explicit, total and validated.** Events are ordered by

    (crossing candle index, level side, level price, level origin,
     level origin label)

with `UPPER` before `LOWER`, from explicit rank mappings — never enum definition
order, ``.value`` string order, set order or hash order. Input *level* order is
not part of the contract: permuting a level set produces byte-identical output.
Input *candle* order is `CandleSeries`' own guarantee.

**Prefix stability is exact, with no exceptions.** An event at candle ``i`` is a
function of candle ``i``, candle ``i - 1`` and the level set. Nothing reads
forward and there is no confirmation delay, so deriving over a prefix gives
precisely the events of the full derivation whose index falls inside that prefix,
in the same order — unlike `detect_swings`, which cannot yet classify its newest
``right_bars`` candles.

**Identity is checked once, through the existing contract.** The safe pipeline
calls `require_same_identity(series, levels)`, which accepts a `CandleSeries`
through its projection and a `ContextualSeries` through its field, so one call
covers both sides and this package needs no identity logic of its own. Mixing
instruments or timeframes is refused before any arithmetic. Empty data still
carries a full identity.

Guarantees this package is built on, all inherited rather than re-implemented:
`CandleSeries` already enforces strictly increasing UTC timestamps, a single
symbol and timeframe, finite non-negative OHLCV and ``high >= low``.
`fmis.market_structure` already owns detection, the plateau policy, comparison,
labelling and the sequence-ordering rule. `fmis.series_context` already owns
identity propagation and mismatch rejection.

Rules for anything added here:
  * **Closed candles only**, always. A forming bar's high, low and close can still
    move, and a crossing that can change is not a fact.
  * **Never read forward.** An event may depend on the crossing candle and its
    immediate predecessor, and on nothing later. That is what makes prefix
    stability exact rather than approximate.
  * **No interpretation.** No BOS, CHoCH, protected level, inducement, liquidity
    sweep, support, resistance, regime, bias, signal, entry, exit, stop, target,
    size, strength, confidence or ranking. Comparing a price to a number is
    arithmetic; calling the result a break is not, and only the first belongs
    here.
  * **No lifecycle.** No level is active, spent, protected or invalidated, and no
    candle is skipped for preceding a level's origin. Activation is a policy
    decision belonging to BOS, which can apply it by filtering on fields it
    already holds. See ADR-0019 deferred question D1.
  * **Never fabricate a path.** If OHLC cannot prove it, the model must not be
    able to express it.
  * **No tolerance.** Exact comparison, always. Tolerance needs tick-size metadata
    that exists nowhere in this repository, and adding it here would make
    equality a property of a setting rather than of the data.
  * **One authoritative rule per concept, kept private** — `models._crossing_kind`
    for the policy, `models._is_wholly_beyond` for the range test,
    `models._level_key` for the order, `models._SIDE_BY_LABEL` for a level's
    side. A public variant would offer a shortcut past the invariants each type
    enforces.
  * **A model may never contradict its own fields.** `LevelCrossingEvent`
    validates its ``kind`` and ``mechanism`` against its candle and level, and
    `PriceLevel` validates its ``side`` against its provenance, so a wrong event
    cannot be constructed at all.
  * **Validate before deriving; reject, never repair.** Duplicate levels raise
    rather than collapse, and a mismatched identity raises rather than resolving
    to one side.
  * **Delegate, never re-derive.** Swing detection, comparison, labelling,
    ordering and identity propagation each have exactly one implementation
    elsewhere, and none of them is repeated here.
  * **No global mutable state**, no cache, no registry, no wall clock, no
    randomness, no environment dependence.
  * **Imports only `fmis.data`, `fmis.market_structure` and
    `fmis.series_context`.** Never the structural-trend package,
    `fmis.decision_support`, `fmis.evidence`, `fmis.providers`, `fmis.pipeline`,
    or anything to do with AI, execution or portfolios — and nothing imports this
    package.

See ADR-0019 and `docs/design/LEVEL_CROSSING_FOUNDATION_V1.md`.
"""

from __future__ import annotations

from fmis.level_crossing.crossing import crossing_kind, derive_level_crossings
from fmis.level_crossing.levels import structural_levels
from fmis.level_crossing.models import (
    CrossingKind,
    CrossingMechanism,
    DuplicateLevelError,
    LevelCrossingError,
    LevelCrossingEvent,
    LevelOrigin,
    LevelSide,
    PriceLevel,
)
from fmis.level_crossing.pipeline import (
    contextual_level_crossings,
    contextual_structural_levels,
)

__all__ = [
    "LevelSide",
    "CrossingKind",
    "CrossingMechanism",
    "LevelOrigin",
    "PriceLevel",
    "LevelCrossingEvent",
    "LevelCrossingError",
    "DuplicateLevelError",
    "crossing_kind",
    "derive_level_crossings",
    "structural_levels",
    "contextual_structural_levels",
    "contextual_level_crossings",
]
