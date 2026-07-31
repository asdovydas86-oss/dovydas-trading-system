"""The safe pipeline boundary: an identity-preserving wrapper over this package.

One function. It does exactly three things:

    1. reject a bare payload passed where an envelope belongs,
    2. call the **existing** context-free production function, unchanged,
    3. re-wrap the result under the input's own identity object.

**Nothing analytical happens here.** The predecessor rule, the two-sided-bar
suppression, the duplicate policy, the conflict rejection and the ordering all
keep their single implementation in `changes.py` and `models.py`. This module
performs no arithmetic, names no side, groups nothing, and re-implements no rule —
all enforced by AST tests, so a future "small optimisation" that inlines a step
fails the suite rather than quietly creating a second source of truth.

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

**`require_same_identity` is deliberately not called.** It is the rule for
reconciling *two or more* subjects, and there is exactly one here. Calling it with
a single subject would return that subject's identity while implying a check that
is not happening — a false guarantee is worse than none. This is the single-input
shape `contextual_structural_state_history` and `contextual_structural_trend_history`
already established, followed exactly; `contextual_structure_breaks`' two-input
shape does not apply.
"""

from __future__ import annotations

from fmis.change_of_character.changes import derive_changes_of_character
from fmis.change_of_character.models import ChangeOfCharacter
from fmis.series_context import ContextualSeries
from fmis.structure_break import StructureBreak

__all__ = ["contextual_changes_of_character"]


def contextual_changes_of_character(
    breaks: ContextualSeries[StructureBreak],
) -> ContextualSeries[ChangeOfCharacter]:
    """Changes of character from a contextual break sequence, in context.

    Args:
        breaks: a `ContextualSeries` of `StructureBreak`, as
            `fmis.structure_break.contextual_structure_breaks` returns.

    Returns:
        A `ContextualSeries` under the **same identity object**, whose payload is
        exactly ``derive_changes_of_character(breaks.values)``.

    Raises:
        TypeError: ``breaks`` is not a `ContextualSeries`, or the delegate
            rejects a payload element.
        ChangeOfCharacterInputError: raised by the delegate, with its message
            unchanged.

    The predecessor rule, the indeterminate-prior-bar suppression and the
    duplicate policy are **entirely the delegate's**. This wrapper adds no
    validation of its own beyond the envelope type, so a conflict surfaces with
    the exact message and position the context-free function already produced.

    The returned envelope carries ``breaks.identity`` itself, by reference.

    Empty input still carries identity: no breaks yields an envelope with
    ``values == ()`` and the identity intact.
    """
    _require_envelope(breaks, name="breaks")
    return ContextualSeries(
        identity=breaks.identity,
        values=derive_changes_of_character(breaks.values),
    )


def _require_envelope(subject: object, *, name: str) -> None:
    """Reject a bare payload passed where an envelope belongs.

    Without this, a caller could pass the context-free tuple straight in and get a
    `TypeError` from deep inside the delegate — or, worse, silently lose the
    identity the whole contract exists to carry. Validating the envelope **before**
    any analytical work also keeps failures deterministic and partial results
    impossible.

    Deliberately **private**: it is an argument check, not a public predicate. Its
    message matches `fmis.series_context.pipeline._require_envelope`,
    `fmis.level_crossing.pipeline._require_envelope` and
    `fmis.structure_break.pipeline._require_envelope` exactly, because a caller
    moving between the four pipelines should not meet four wordings of one rule.
    """
    if not isinstance(subject, ContextualSeries):
        raise TypeError(
            f"{name} must be a ContextualSeries, got {type(subject).__name__}"
        )
