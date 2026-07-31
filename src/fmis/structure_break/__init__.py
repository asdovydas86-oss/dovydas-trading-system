"""Break of structure — the first close beyond a level that was already knowable.

The first layer built entirely on **derived facts**. It consumes the structural
level set and the level-crossing history and reads **no candle at all** — this
package does not import `fmis.data`, so `Candle` is not a name it can reach, and
a test enforces it.

    ContextualSeries[PriceLevel]  +  ContextualSeries[LevelCrossingEvent]
                              │
                              ▼  contextual_structure_breaks(..., confirmation_bars=R)
                    ContextualSeries[StructureBreak]

**What a break of structure is here, in full:**

> the **first close beyond** the **reference** structural level for its side, at a
> bar where that level was **already knowable**.

Five conjuncts, each decided separately and each testable:

  1. the crossing's kind is `CrossingKind.CLOSE_BREACH`;
  2. its mechanism is not `CrossingMechanism.ALREADY_BEYOND`;
  3. the level carries provenance and the bar is at or after
     ``origin.index + confirmation_bars``;
  4. the level **is the reference** for its side at that bar;
  5. it is the **first** such crossing for that level.

**Only a close breaks structure.** A `TOUCH` reached the level without passing
it. A `WICK_BREACH` passed it and closed back inside — a rejection, not a break —
and a wick-based rule also cannot be non-repainting on a forming bar, which the
market-structure review §15 named as the deciding property. There is exactly one
qualifying kind and it is **not configurable**, because a setting would make
every historical break non-reproducible without it. A consumer wanting wick-based
breaks reads the crossing history, where `WICK_BREACH` is already a first-class
fact.

**The label does not decide anything.** An `EQUAL_HIGH`-derived level breaks when
a close goes beyond its price, exactly as a `HIGHER_HIGH`-derived one does. That
is not a claim that the two are the same; it is a statement about what the break
test measures — a close against a **price**. The label is carried through
unchanged on `StructureBreak.label`, so a consumer that wants to weigh them
differently can, in its own layer. Filtering here would silently discard breaks.

**The reference is the most recent eligible level on that side**, never the most
extreme. "Most extreme unbroken level" is protected-level and liquidity logic and
does not belong to a break primitive.

**Eligibility begins at the confirmation bar, and that is the milestone's one
sharp edge.** A pivot at bar ``o`` is knowable only once ``confirmation_bars``
further candles have closed, so a level becomes the reference at
``o + confirmation_bars`` — not at ``o``. Using the pivot bar instead is
**prefix-unstable**, measured at 30 violating prefixes across 40 seeded fixtures,
against 0 for this rule. The number itself is recorded on **no derived fact** in
the repository, so it is a **required keyword argument with no default**; a
default would silently bind this layer to `DEFAULT_RIGHT_BARS` and be wrong for
anyone who chose otherwise. Carrying it on `LevelOrigin` is the correct long-term
fix and needs its own milestone. See ADR-0020 §2.4 and deferred question D1.

A property that makes this safe rather than merely stable: **no breach can occur
inside a level's own confirmation window.** Detection requires every bar in that
window to stay at or inside the pivot's extreme, and ``close <= high``, so only a
`TOUCH` is possible there — verified over 11,608 in-window crossings, all
touches. Confirmation-based eligibility therefore never discards a reachable
break; it only fixes which level is the reference.

**Structure breaks once.** At most one break per level, ever. A second close
beyond an already-broken level is not a second break, and once the reference has
broken with no newer level on that side, there is no further break on that side
until a new swing forms. This is the level lifecycle ADR-0019 §2.7 deliberately
kept out of the crossing primitive, and it belongs here.

**Nothing is invalidated.** A break is a fact about a closed bar. "This break
failed" is a later reading over the break *sequence*, which is change-of-character
adjacent and two layers up.

**No direction enum, no bullish or bearish.** `StructureBreak.side` projects the
level's side, which already carries the only sense this layer knows. `UPPER` means
price closed above the level; it does not mean bullish, long, or a reason to
trade. This is ADR-0019 §D's rule applied unchanged.

**Order-invariant on both inputs, and it stays that way on purpose.** Levels and
crossings may arrive in any order and duplicated crossings collapse, because the
earliest qualifying crossing per level is selected rather than assumed.
Re-validating the crossing run's canonical order would be a second implementation
of a rule `fmis.level_crossing` owns — its ordering key is private for exactly
that reason. Output is ordered by ``(breaking bar index, level side)``, which is
total because at most one break exists per bar per side.

**Two breaks may share a bar** — one upper, one lower. Their order is the level
ordering and is **not** a claim about which happened first; OHLC cannot prove
that, and this layer inherits ADR-0019 §2.6's refusal to pretend otherwise.

**Prefix stability is exact.** Levels and crossings derived from a candle prefix
give exactly the breaks of the full run whose index falls inside that prefix, in
the same order. Measured at 0 violations.

**Identity is checked once**, through `require_same_identity(levels, crossings)`.
Mixed instruments and timeframes are rejected before any derivation; empty inputs
retain a full identity; no API accepts an identity argument.

**How a future change-of-character layer consumes this.** A CHoCH is *the first
break opposing the direction of the previous break*:

    tuple(b for a, b in zip(breaks, breaks[1:]) if a.side is not b.side)

— computed from the break sequence alone, touching no level, no crossing and no
candle. That is the market-structure review §15 ordering satisfied exactly: BOS
on levels, CHoCH over the BOS sequence, and trend a summary of both, defining
neither. Nothing here consults a trend, and a test enforces it.

Rules for anything added here:
  * **Never read a candle.** Every fact a break needs is already on a crossing. If
    something here would need OHLC, it belongs in `fmis.level_crossing` instead.
  * **Never re-derive.** Swing detection, labelling, level construction, the
    crossing rule, the crossing ordering and identity propagation each have
    exactly one implementation elsewhere, and none is repeated here.
  * **No interpretation.** No CHoCH, trend, regime, bias, protected level,
    inducement, liquidity sweep, support, resistance, signal, entry, exit, stop,
    target, size, strength or confidence. Reporting that a close went past a
    number is arithmetic; calling it a trade is not.
  * **No lifecycle beyond "breaks once".** No invalidation, no re-arming, no
    retest tracking.
  * **A model may never contradict its own fields.** `StructureBreak` validates
    its crossing's kind, mechanism, provenance and eligibility, so a break
    claiming a touch or an unknowable level cannot be constructed.
  * **Validate before deriving; reject, never repair.** An unrankable level set
    raises rather than dropping a level and silently changing every later
    reference.
  * **No global mutable state**, no cache, no registry, no wall clock, no
    randomness, no environment dependence.
  * **Imports only `fmis.level_crossing` and `fmis.series_context`** — and, for
    one label type, `fmis.market_structure`. Never `fmis.data`, never the
    structural-trend package, never `fmis.decision_support`, `fmis.evidence`,
    `fmis.providers` or `fmis.pipeline` — and nothing imports this package.

See ADR-0020 and `docs/design/BREAK_OF_STRUCTURE_FOUNDATION_V1.md`.
"""

from __future__ import annotations

from fmis.structure_break.breaks import derive_structure_breaks
from fmis.structure_break.models import (
    StructureBreak,
    StructureBreakError,
    StructureBreakInputError,
)
from fmis.structure_break.pipeline import contextual_structure_breaks

__all__ = [
    "StructureBreak",
    "StructureBreakError",
    "StructureBreakInputError",
    "derive_structure_breaks",
    "contextual_structure_breaks",
]
