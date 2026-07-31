"""The safe pipeline boundary: identity-preserving wrappers over this package.

Two functions, one per stage. Each one does exactly three things:

    1. take the identity from its input — through `require_same_identity`,
    2. call the **existing** context-free production function, unchanged,
    3. re-wrap the result under that same identity object.

**Nothing analytical happens here.** The crossing rule, the mechanism rule, the
duplicate check, the canonical ordering and the swing-to-level projection all keep
their single implementation in `crossing.py`, `levels.py` and `models.py`. This
module performs no arithmetic, reads no candle field and names no kind or
mechanism — all enforced by AST tests, so a future "small optimisation" that
inlines a step fails the suite rather than quietly creating a second source of
truth.

Because the payload is passed straight through, **adding context cannot change a
result**. That is proved rather than claimed: the equivalence tests compare these
wrappers' payloads against the bare functions' returns across every fixture class.

**Identity is carried by reference, never rebuilt.** A wrapper that reconstructed
an equal identity would pass every ``==`` test while severing the link to the
series the payload came from, so propagation is by object identity and the tests
assert ``is``.

**There is no argument through which identity can be substituted.** Neither
function takes an identity parameter: the only place identity can come from is the
input, which makes silent replacement unrepresentable rather than merely
discouraged.

This is the shape ADR-0018 §6.1 designed for. `require_same_identity` accepts a
`CandleSeries` (through its ``identity`` projection) and a `ContextualSeries`
(through its field) interchangeably, so **one call covers both sides** and this
package needs no identity logic of its own — and no dependency on the
structural-trend package.
"""

from __future__ import annotations

from fmis.data import CandleSeries
from fmis.level_crossing.crossing import derive_level_crossings
from fmis.level_crossing.levels import structural_levels
from fmis.level_crossing.models import LevelCrossingEvent, PriceLevel
from fmis.market_structure import StructuralSwing
from fmis.series_context import ContextualSeries, require_same_identity

__all__ = ["contextual_structural_levels", "contextual_level_crossings"]


def contextual_structural_levels(
    swings: ContextualSeries[StructuralSwing],
) -> ContextualSeries[PriceLevel]:
    """Structural levels from contextual swings, in context.

    Args:
        swings: a `ContextualSeries` of `StructuralSwing`, as
            `fmis.series_context.contextual_structural_swings` returns.

    Returns:
        A `ContextualSeries` under the **same identity object**, whose payload is
        exactly ``structural_levels(swings.values)``.

    Raises:
        TypeError: ``swings`` is not a `ContextualSeries`, or its payload is
            rejected by the delegate.

    The projection — which side a label implies, which price and provenance are
    carried, and the first-of-type limitation — is **entirely the delegate's**.
    This wrapper adds no validation of its own beyond the envelope type.

    Identity comes from ``swings`` and nowhere else, read through
    `require_same_identity` so that the single choke point is used even for one
    subject rather than a hand-written attribute access.
    """
    _require_envelope(swings, name="swings")
    identity = require_same_identity(swings)
    return ContextualSeries(
        identity=identity, values=structural_levels(swings.values)
    )


def contextual_level_crossings(
    series: CandleSeries, levels: ContextualSeries[PriceLevel]
) -> ContextualSeries[LevelCrossingEvent]:
    """Level crossings from candles and contextual levels, in context.

    Args:
        series: the candle series to replay. Its ``identity`` projection must
            match ``levels``' identity.
        levels: a `ContextualSeries` of `PriceLevel`, as
            `contextual_structural_levels` returns — or built by a caller from
            levels of any origin.

    Returns:
        A `ContextualSeries` under the identity both inputs share, whose payload
        is exactly ``derive_level_crossings(series, levels.values)``.

    Raises:
        TypeError: ``series`` is not a `CandleSeries`, or ``levels`` is not a
            `ContextualSeries`.
        SeriesIdentityMismatchError: the candles and the levels describe
            different analytical series — a different instrument or a different
            timeframe. Raised, never repaired and never resolved by picking a
            side.
        DuplicateLevelError: raised by the delegate, with its message unchanged.

    **This is the point of the whole context contract.** Comparing a BTCUSDT price
    to an ETHUSDT level, or a 4h level to a 1h candle, is the silent mixing
    ADR-0018 exists to prevent, and it is refused here before any arithmetic
    happens.

    The identity check runs **before** derivation, so a mismatch costs nothing and
    no partial result is ever built. The returned envelope carries the identity
    object `require_same_identity` returned — the candle series' projection, by
    reference.

    Empty inputs still carry identity: no candles, or no levels, yields an
    envelope with ``values == ()`` and the identity intact.
    """
    if not isinstance(series, CandleSeries):
        raise TypeError(f"series must be a CandleSeries, got {type(series).__name__}")
    _require_envelope(levels, name="levels")
    identity = require_same_identity(series, levels)
    return ContextualSeries(
        identity=identity, values=derive_level_crossings(series, levels.values)
    )


def _require_envelope(subject: object, *, name: str) -> None:
    """Reject a bare payload passed where an envelope belongs.

    Without this, a caller could pass the context-free tuple straight in and get a
    `TypeError` from deep inside a delegate — or, worse, silently lose the
    identity the whole contract exists to carry. Validating the envelope
    **before** any analytical work also keeps failures deterministic and partial
    results impossible.

    Deliberately **private**: it is an argument check, not a public predicate.
    Matches `fmis.series_context.pipeline._require_envelope`'s message exactly,
    because a caller moving between the two pipelines should not meet two
    wordings of one rule.
    """
    if not isinstance(subject, ContextualSeries):
        raise TypeError(
            f"{name} must be a ContextualSeries, got {type(subject).__name__}"
        )
