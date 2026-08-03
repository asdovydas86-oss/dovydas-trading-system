"""The safe pipeline boundary: an identity-preserving wrapper over this package.

One function. It does exactly three things:

    1. take the identity both inputs share — through `require_same_identity`,
    2. call the **existing** context-free production function, unchanged,
    3. re-wrap the result under that same identity object.

**Nothing analytical happens here.** The qualifying-kind rule, the mechanism
exclusion, the eligibility rule, reference selection, the first-break-per-level
rule and the ordering all keep their single implementation in `breaks.py` and
`models.py`. This module performs no arithmetic, reads no price, names no kind or
mechanism, and re-implements no rule — all enforced by AST tests, so a future
"small optimisation" that inlines a step fails the suite rather than quietly
creating a second source of truth.

Because the payload is passed straight through, **adding context cannot change a
result**. That is proved rather than claimed: the equivalence tests compare this
wrapper's payload against the bare function's return across every fixture class.

**Identity is carried by reference, never rebuilt.** A wrapper that reconstructed
an equal identity would pass every ``==`` test while severing the link to the
series the payload came from, so propagation is by object identity and the tests
assert ``is``.

**There is no argument through which identity can be substituted.** The function
takes no identity parameter: the only place identity can come from is the input,
which makes silent replacement unrepresentable rather than merely discouraged.

This is the shape ADR-0018 §6.1 designed and ADR-0019 §2.10 reused. Both inputs
are already `ContextualSeries`, so **one call covers both sides** and this package
needs no identity logic of its own.
"""

from __future__ import annotations

from fmis.level_crossing import LevelCrossingEvent, PriceLevel
from fmis.series_context import ContextualSeries, require_same_identity
from fmis.structure_break.breaks import derive_structure_breaks
from fmis.structure_break.models import StructureBreak

__all__ = ["contextual_structure_breaks"]


def contextual_structure_breaks(
    levels: ContextualSeries[PriceLevel],
    crossings: ContextualSeries[LevelCrossingEvent],
) -> ContextualSeries[StructureBreak]:
    """Breaks of structure from contextual levels and crossings, in context.

    Args:
        levels: a `ContextualSeries` of `PriceLevel`, as
            `fmis.level_crossing.contextual_structural_levels` returns.
        crossings: a `ContextualSeries` of `LevelCrossingEvent`, as
            `fmis.level_crossing.contextual_level_crossings` returns. Its identity
            must match ``levels``'.
    There is **no ``confirmation_bars`` argument**: since Milestone AH the delay
    travels on each level's own origin, so this wrapper has nothing to forward and
    no way to introduce a mismatch the delegate would not see. See ADR-0024.

    Returns:
        A `ContextualSeries` under the identity both inputs share, whose payload is
        exactly ``derive_structure_breaks(levels.values, crossings.values)``.

    Raises:
        TypeError: an argument is not a `ContextualSeries`, or the delegate rejects
            a payload element.
        SeriesIdentityMismatchError: the levels and the crossings describe
            different analytical series — a different instrument or a different
            timeframe. Raised, never repaired and never resolved by picking a side.
        StructureBreakInputError: raised by the delegate, with its message
            unchanged.

    Comparing BTCUSDT levels against ETHUSDT crossings, or 4h levels against 1h
    crossings, is the silent mixing ADR-0018 exists to prevent, and it is refused
    here **before any derivation happens**, so a mismatch costs nothing and no
    partial result is ever built.

    The returned envelope carries the identity object `require_same_identity`
    returned — ``levels``' own, by reference.

    Empty inputs still carry identity: no levels, or no crossings, yields an
    envelope with ``values == ()`` and the identity intact.
    """
    _require_envelope(levels, name="levels")
    _require_envelope(crossings, name="crossings")
    identity = require_same_identity(levels, crossings)
    return ContextualSeries(
        identity=identity,
        values=derive_structure_breaks(levels.values, crossings.values),
    )


def _require_envelope(subject: object, *, name: str) -> None:
    """Reject a bare payload passed where an envelope belongs.

    Without this, a caller could pass the context-free tuple straight in and get a
    `TypeError` from deep inside the delegate — or, worse, silently lose the
    identity the whole contract exists to carry. Validating **both** envelopes
    before any analytical work also keeps failures deterministic and partial
    results impossible.

    Deliberately **private**: it is an argument check, not a public predicate. Its
    message matches `fmis.series_context.pipeline._require_envelope` and
    `fmis.level_crossing.pipeline._require_envelope` exactly, because a caller
    moving between the three pipelines should not meet three wordings of one rule.
    """
    if not isinstance(subject, ContextualSeries):
        raise TypeError(
            f"{name} must be a ContextualSeries, got {type(subject).__name__}"
        )
