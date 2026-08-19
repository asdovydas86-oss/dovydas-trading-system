"""Stable setup identity — the one place a setup's name is derived.

**The defect this module closes.** `AV`'s setup identity was keyed on
`Trigger.level.origin.index`, and that index is *window-relative*: the analysis
window slides forward one candle per instant, so a fixed swing's index falls by
one every bar. The identity therefore changed every bar even when nothing about
the market had. Measured over a real 400-day BTCUSDT run, **every single
directional observation reported a new setup** — 48 of 48 — and over the
corrected research window, **549 "unique setups" from 552 directional
observations**, a 1:1 ratio **[E]** report 0012 §7. One idea that persists for a
week becomes forty setups, forty rows on the morning page, and forty denominators
in every statistic computed over them.

**The rule used instead.** A setup's identity is its `Anchor` —
`(market, book, direction, invalidation_level_origin)` — and the origin
contributes **only fields that are absolute**: the pivot candle's timestamp, the
swing's own label, and the confirmation window that made it a level. The
window-relative index is deliberately **not** part of it.

That is the whole fix, and it is one line of policy: *an identity may only be
built from facts that do not move when the window moves.*

**Why `swing_index` is carried but not counted.** `LevelOriginRef.swing_index`
stays populated because it is real provenance — it says where in *this* window
the pivot sat, and a reader debugging a level wants it. But it is excluded from
`anchor_identity`, because including it would reproduce the exact `AV` failure
one layer up, this time with frozen artifacts pointing at it. `Anchor`'s own
docstring names that hazard; this module is what prevents it.

**Identity does not depend on policy version.** Nothing here reads a
`policy_id`, a `calculation_version` or a `VersionSet`. Two variants replayed
over the same candles decompose history into exactly the same setups, which is
the property that makes *"did this setup confirm under variant B?"* answerable at
all. The confirmation window **is** included, because ADR-0024 makes it
provenance rather than policy: a level derived under a different confirmation
window is a different level, not the same level renamed, and `LevelOrigin` has
recorded that distinction in its own equality since it was built.

**This module imports nothing from the market half.** The market's `LevelOrigin`
carries a `StructuralSwingLabel` and a `datetime`; both arrive here as
primitives, supplied by the composition root. The domain therefore keeps the
zero-engine-edge guard `tests/test_trade_domain_architecture.py` asserts, and the
adapter that reads a live `SetupAssessment` lives in `fmis.pipeline`, exactly
where `pipeline/prices.py` binds a provider to a mark.
"""

from __future__ import annotations

from datetime import datetime

from fmis.accounts import Book, MarketId
from fmis.archive.json_safe import encode_timestamp
from fmis.records import (
    content_digest_over,
    digest_prefix_of,
    require_int,
    require_text,
    require_utc,
)
from fmis.snapshotting import Anchor, LevelOriginRef, TradeDirection

__all__ = [
    "SETUP_VOCABULARY_ID",
    "SETUP_IDENTITY_VERSION",
    "stable_origin_id",
    "level_origin_ref",
    "anchor_of",
    "anchor_identity",
    "anchors_match",
]

#: §9.2's vocabulary. `SetupType` is not a new class: it is a `VersionedTerm` in
#: this vocabulary, which is the shape `TradePlan.setup_type` already carries and
#: `fmis.statistics.breakdown` already groups on. Naming the id here is what stops
#: a second spelling of the same vocabulary appearing in a third package.
SETUP_VOCABULARY_ID = "setup"

#: Bumping this re-derives every setup identity in the repository. It is safe to
#: bump **only** while nothing frozen points at one — §23.1's rule, and the reason
#: `SetupOccurrence` is a projection rather than a record.
SETUP_IDENTITY_VERSION = 1


def stable_origin_id(
    *,
    pivot_timestamp: datetime,
    label: str,
    confirmation_bars: int,
) -> str:
    """The window-independent name of one originating swing.

    Derived from the pivot candle's **timestamp** — an absolute instant — never
    from its index in whatever window happened to be loaded. Two calls with equal
    arguments return an equal string, always; a call made one bar later, on a
    window that has slid forward, returns the *same* string.

    The label is taken as text rather than as a `StructuralSwingLabel` so this
    module holds no market-half import. The composition root passes
    ``origin.label.value``.
    """
    stamp = require_utc(pivot_timestamp, "pivot_timestamp")
    text = require_text(label, "label")
    require_int(confirmation_bars, "confirmation_bars", minimum=1)
    return digest_prefix_of(
        content_digest_over(
            {
                "identity_version": SETUP_IDENTITY_VERSION,
                "pivot_timestamp": encode_timestamp(stamp),
                "label": text,
                "confirmation_bars": confirmation_bars,
            }
        )
    )


def level_origin_ref(
    *,
    pivot_timestamp: datetime,
    label: str,
    confirmation_bars: int,
    swing_index: int,
) -> LevelOriginRef:
    """A `LevelOriginRef` whose id is stable and whose index is only provenance.

    ``swing_index`` is recorded because it is a true fact about the window that
    produced this reading. It takes no part in `stable_origin_id`, so a reading
    taken ten bars later — with the same pivot now ten positions further back —
    produces a ref with a *different* ``swing_index`` and the *same* ``origin_id``.
    """
    return LevelOriginRef(
        origin_id=stable_origin_id(
            pivot_timestamp=pivot_timestamp,
            label=label,
            confirmation_bars=confirmation_bars,
        ),
        swing_index=swing_index,
        confirmation_bars=confirmation_bars,
    )


def anchor_of(
    *,
    market: MarketId,
    book: Book,
    direction: TradeDirection,
    invalidation_origin: LevelOriginRef,
) -> Anchor:
    """§9.4's anchor, assembled. Every component declared or `MEASURED`.

    A thin constructor rather than a computation: it exists so the one legal way
    to build an anchor passes through this module, and a caller cannot quietly
    assemble one from a level origin that was never put through
    `stable_origin_id`.
    """
    return Anchor(
        market=market,
        book=book,
        direction=direction,
        invalidation_origin=invalidation_origin,
    )


def anchor_identity(anchor: Anchor) -> str:
    """The stable key two observations of the same idea share.

    **Excludes `swing_index`** — see the module docstring. Includes the market,
    the book, the direction and the origin's stable id and confirmation window.

    Returned as a digest rather than as `Anchor.key`'s pipe-joined rendering
    because that property is documented as *"for logs and messages only"*, and a
    grouping key that doubles as a display string is a grouping key that will one
    day be changed for readability.
    """
    if not isinstance(anchor, Anchor):
        raise TypeError(f"anchor must be an Anchor, got {type(anchor).__name__}")
    # No `NO_TRADE` check here: `Anchor.__post_init__` already refuses one, so a
    # second guard would be a branch no test could ever reach.
    return content_digest_over(
        {
            "identity_version": SETUP_IDENTITY_VERSION,
            "market": anchor.market.to_payload(),
            "book": anchor.book.value,
            "direction": anchor.direction.value,
            "origin_id": anchor.invalidation_origin.origin_id,
            "confirmation_bars": anchor.invalidation_origin.confirmation_bars,
        }
    )


def anchors_match(left: Anchor, right: Anchor) -> bool:
    """Whether two anchors name the same idea.

    Used by creation rule 4 (`lifecycle.admit`) and by the read-time grouping in
    `occurrence.py`, so deduplication and counting can never disagree about what
    "the same setup" means. Structural `==` is deliberately *not* used: it
    includes `swing_index`, and two readings of one pivot taken on different bars
    differ in exactly that field.
    """
    return anchor_identity(left) == anchor_identity(right)
