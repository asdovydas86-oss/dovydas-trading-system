"""Building price levels from confirmed structural swings.

One function, `structural_levels`. It turns each labelled swing into a
`PriceLevel` at that swing's own extreme price, on the side its own type implies,
carrying its own index, timestamp and label as provenance.

**It delegates in full and reinterprets nothing.** Detection, the plateau policy,
the confirmation window, the exact price comparison and the label mapping all keep
their single implementation in `fmis.market_structure`. This module reads
``swing.comparison.current`` and ``swing.label`` and performs no arithmetic on a
price beyond copying it.

**A swing is never renamed.** An `EQUAL_HIGH` becomes an `UPPER` level carrying
the `EQUAL_HIGH` label, not a "double top", "resistance", "liquidity" or a
"protected high". Nothing here marks a level protected, active or BOS-relevant;
the level's side is the only thing derived, and it comes from one authoritative
mapping.

**Equal prices stay distinct.** Two swings at exactly the same price produce two
levels, because their origins differ. Collapsing them would destroy exactly the
structure a later layer wants — the same reasoning `detect_swings` uses to keep
separated equal highs apart.

**Known limitation (ADR-0019 D2).** A `StructuralSwing` names a *pairing*, so its
``comparison.current`` covers every confirmed swing **except the first of each
type**: the first swing high and the first swing low are only ever a ``previous``
and therefore have no label and no `StructuralSwing`. Those two points yield no
level here. A caller needing them constructs a `PriceLevel` from the `SwingPoint`
directly with ``origin=None``. Widening this would require making
`LevelOrigin.label` optional, which v1 declines to decide speculatively.
"""

from __future__ import annotations

from collections.abc import Sequence

from fmis.level_crossing.models import (
    LevelOrigin,
    PriceLevel,
    _SIDE_BY_LABEL,
)
from fmis.market_structure import StructuralSwing

__all__ = ["structural_levels"]


def structural_levels(
    swings: Sequence[StructuralSwing],
) -> tuple[PriceLevel, ...]:
    """A `PriceLevel` for each labelled swing, in input order.

    Args:
        swings: confirmed labelled swings, as `label_swing_sequence` returns.

    Returns:
        An immutable tuple with one `PriceLevel` per swing, **in the input's
        order**, each at that swing's ``comparison.current.price``, on the side
        its label implies, with a `LevelOrigin` carrying the pivot's index,
        the pivot's timestamp, the swing's own label and the confirmation window
        the pivot was detected under.

        The confirmation window is **copied off the swing**, never taken as an
        argument. A ``confirmation_bars`` parameter here would let a caller record
        a window the swings were not detected under, which is the ADR-0020 D1
        hazard relocated one layer up and dressed as provenance — the approach
        ADR-0024 records as explicitly rejected.

        Input order is preserved rather than canonicalised because this function
        is a projection, not a derivation: reordering here would silently
        disagree with the run the caller passed. `derive_level_crossings` applies
        the canonical order itself, so nothing downstream depends on this one.

        Empty for an empty run.

    Raises:
        TypeError: ``swings`` is not a non-string sequence, or an element is not
            a `StructuralSwing`.

    Ordering is **not** validated here. A `StructuralSwing` run's ordering rule
    already has exactly one implementation, in
    `fmis.market_structure.models._validate_key_order`, reached through
    `label_swing_sequence` and `derive_structural_sequence_state_history`;
    re-checking it here would be a second implementation of a rule this package
    does not own, and `derive_level_crossings` does not depend on level order.

    The price is **copied, never recomputed**. A swing high's level sits at the
    candle's ``high``, which is what `SwingPoint.price` already stores — no
    midpoint, no average, no rounding, no offset.

    Pure: no state, no cache, no clock, no randomness.
    """
    if isinstance(swings, (str, bytes)) or not isinstance(swings, Sequence):
        raise TypeError(
            f"swings must be a sequence of StructuralSwing, got "
            f"{type(swings).__name__}"
        )
    for position, swing in enumerate(swings):
        if not isinstance(swing, StructuralSwing):
            raise TypeError(
                f"swings[{position}] must be a StructuralSwing, got "
                f"{type(swing).__name__}"
            )

    return tuple(
        PriceLevel(
            price=swing.comparison.current.price,
            side=_SIDE_BY_LABEL[swing.label],
            origin=LevelOrigin(
                index=swing.comparison.current.index,
                timestamp=swing.comparison.current.timestamp,
                label=swing.label,
                confirmation_bars=swing.comparison.current.confirmation_bars,
            ),
        )
        for swing in swings
    )
