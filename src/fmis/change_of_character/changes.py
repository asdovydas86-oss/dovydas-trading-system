"""Deterministic change-of-character derivation over the break sequence.

One public function, `derive_changes_of_character`. It consumes the one fact that
already exists — the break-of-structure sequence — and reports where structure
changed character.

**No candle, no level and no crossing is ever read.** This module cannot read a
candle: the package does not import `fmis.data`, so `Candle` is not a name it can
reach. It never names a level or a crossing either; the only thing it reads off a
`StructureBreak` is its ``index`` and its ``side``, and the break object itself is
carried through by reference so nothing is re-derived.

Semantics, stated in full because every one of them is a decision:

**A change of character is a break whose side differs from the side broken at the
most recent strictly earlier break-bearing bar, when that bar broke exactly one
side.** Four conjuncts, each independently decided in ADR-0021: the subject is a
`StructureBreak`; a prior break-bearing bar exists **strictly earlier**; that bar
broke **exactly one** side; and the subject's side **differs** from it.

**The predecessor is chosen by bar, not by position in the sequence.** ADR-0020
§7 sketched this layer as ``zip(breaks, breaks[1:])`` over adjacent elements. That
sketch is superseded, because two breaks may share a bar and ADR-0019 §2.6 and
ADR-0020 §3.5 both state that **their order is the level ordering, not a claim
about which happened first**. Adjacency would therefore infer a change of
character from an ordering the layer below refuses to read as temporal —
demonstrated on a constructible case in the design §2.3, and pinned by a test.

**A two-sided prior bar leaves character indeterminate**, so no change is claimed
at the next break bar. Choosing one of that bar's two breaks to be "the" prior
character is the intrabar claim reintroduced one step later. Indeterminacy
**suppresses without persisting**: the next single-sided break bar restores a
determinate character.

**Character is the most recent break bar only**, never an accumulated run. Three
consecutive upper breaks give the same character as one. Accumulation is trend's
job, and `MINIMUM_DIRECTIONAL_SHIFTS` already owns that idea one package over.

**Nothing is invalidated.** A change of character is a fact about two closed bars;
nothing later revises it, and there is no "failed CHoCH".

**No trend is consulted.** Trend is a *summary of* break of structure and change
of character and defines neither — the market-structure architecture review §15
fixed that ordering, and a test enforces that this package cannot reach the trend
package at all.

**Order-invariant on its input, and duplicate-invariant.** Breaks may arrive in
any order and duplicated equal breaks collapse, because the sequence is rebuilt by
bar rather than assumed. Re-validating the break run's canonical order would be a
second implementation of a rule `fmis.structure_break` already owns.

**Empty input is not an error.** No breaks, or one break, yields an empty tuple.
"Character did not change" is a true answer to a well-formed question.

**No configuration of any kind.** No ``confirmation_bars``, no minimum spacing, no
threshold, no qualifying-side policy. Eligibility was resolved one layer down and
is already baked into which breaks exist; a setting here would make every
historical result non-reproducible without it (ADR-0019 §2.2's rule).
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

from fmis.change_of_character.models import (
    ChangeOfCharacter,
    ChangeOfCharacterInputError,
)
from fmis.level_crossing import LevelSide
from fmis.structure_break import StructureBreak

__all__ = ["derive_changes_of_character"]


def _breaks_by_bar(
    breaks: Sequence[StructureBreak],
) -> dict[int, dict[LevelSide, StructureBreak]]:
    """The break run rebuilt as ``{bar index: {side: break}}``.

    **This is the one place the sequence is reconstructed**, and doing it by bar
    rather than by position is what makes the derivation independent of the input
    order — see the module docstring. The inner mapping has at most two entries,
    one per side, which is the fact the fold in `derive_changes_of_character`
    relies on.

    Validates, never repairs:

      * an element that is not a `StructureBreak` — rejected, because a
        hand-built element cannot be trusted to satisfy the break conjuncts;
      * two **distinct** breaks sharing a bar and a side — rejected, because
        "the break at that bar on that side" would be ambiguous and picking one
        would change the character at every later bar without saying so.

    Two **equal** breaks are not a conflict: duplicated facts are one fact and
    collapse silently, exactly as duplicated crossings do one layer down
    (ADR-0020 §3.8). Equality is structural on a frozen dataclass, so this holds
    for a rebuilt-but-equal break as well as for the same object twice. The
    **first** of a set of equal breaks is the one kept, so the object a change
    carries is the earliest one the caller supplied rather than an equal
    substitute chosen by input order — the same guarantee `derive_structure_breaks`
    makes about the level object it attaches, and a test asserts it with ``is``.

    `derive_structure_breaks` can produce neither failure: it emits at most one
    break per (bar, side). Both therefore mean a hand-built run, where guessing
    would be inventing behaviour.

    Deliberately **private**: it is the sequence-reconstruction rule, and a public
    version would let a caller group breaks by hand and grow a second contract.
    """
    grouped: dict[int, dict[LevelSide, StructureBreak]] = {}

    for position, subject in enumerate(breaks):
        if not isinstance(subject, StructureBreak):
            raise TypeError(
                f"breaks[{position}] must be a StructureBreak, got "
                f"{type(subject).__name__}"
            )
        at_bar = grouped.setdefault(subject.index, {})
        existing = at_bar.get(subject.side)
        if existing is None:
            at_bar[subject.side] = subject
        elif existing != subject:
            raise ChangeOfCharacterInputError(
                f"breaks[{position}] shares bar index {subject.index} and side "
                f"{subject.side.value} with a different break; the previous "
                "break at that bar would be ambiguous"
            )
    return grouped


def derive_changes_of_character(
    breaks: Sequence[StructureBreak],
) -> tuple[ChangeOfCharacter, ...]:
    """Every change of character implied by ``breaks``.

    Args:
        breaks: the break-of-structure sequence, as `derive_structure_breaks`
            returns. Order is **not** part of the contract, and duplicated equal
            breaks collapse. No two distinct breaks may share a bar index and a
            side.

    Returns:
        An immutable tuple of `ChangeOfCharacter`, ordered by **changing candle
        index** alone, ascending. That key is total **and strictly increasing**,
        because at most one change exists per bar: both breaks at a two-sided bar
        are tested against the same prior side and they are each other's
        opposite, so at most one can differ from it. Empty when character never
        changed.

    Raises:
        TypeError: ``breaks`` is not a non-string sequence, or an element is not
            a `StructureBreak`.
        ChangeOfCharacterInputError: two distinct breaks share a bar index and a
            side.

    The result is a pure function of the input **as a multiset**: the same breaks
    always give the same output, permuting them changes nothing, duplicating them
    changes nothing, and extending the underlying series never alters a change
    already returned.

    The output is built in ascending bar order and is **never sorted**. Sorting
    would be dead code: `_breaks_by_bar` is walked over ``sorted`` bar indices and
    emits at most one change per bar, so the ordering guarantee is a property of
    the construction rather than a step that could silently be removed.

    **No side ordering exists anywhere in this package.** Because the key is the
    index alone, `fmis.structure_break`'s private side rank is neither imported
    nor restated — the one ordering rule this layer could plausibly have
    duplicated is structurally absent.

    Pure: no state, no cache, no clock, no randomness, no global registry — and no
    candle, no level and no crossing.
    """
    if isinstance(breaks, (str, bytes)) or not isinstance(breaks, Sequence):
        raise TypeError(
            "breaks must be a sequence of StructureBreak, got "
            f"{type(breaks).__name__}"
        )

    # Validate and regroup before deriving, so a failure is deterministic and no
    # partial result is ever built.
    grouped = _breaks_by_bar(breaks)

    found: list[ChangeOfCharacter] = []
    for earlier, bar in pairwise(sorted(grouped)):
        prior = grouped[earlier]
        # A bar that broke both sides leaves character indeterminate: choosing
        # one of its two breaks to be "the" prior character would be a claim
        # about intrabar order that OHLC cannot support. Suppress, do not
        # persist — the next single-sided bar restores a determinate character.
        if len(prior) != 1:
            continue
        ((prior_side, prior_break),) = prior.items()
        for side, subject in grouped[bar].items():
            # At most one of a bar's (at most two) sides can differ from a single
            # prior side, so this appends at most once and the iteration order of
            # the inner mapping — which follows the input order — cannot change
            # the result.
            if side is not prior_side:
                found.append(
                    ChangeOfCharacter(subject=subject, previous=prior_break)
                )
    return tuple(found)
