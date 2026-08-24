"""Yield-change arithmetic: the one place a rate move is turned into a number.

A yield is not a price, and this module exists because treating it as one is the
most convincing wrong answer this repository could produce. When the 10-year
moves from 4.20% to 4.30%, three different true statements are available:

    +10 basis points        the difference, in hundredths of a percentage point
    +0.10 percentage points the same difference, in whole points
    +2.38 percent           the *ratio* — the change relative to the old level

All three are correct. Only the first is what a reader means by *"the ten-year
moved ten"*, and printing the third under that sentence would be a lie made
entirely of true arithmetic. So this module computes all three, names each
separately, and never lets one wear another's label. `RateChange` has no field
called *the* change.

**Why this is not in `fmis.relative_value`.** That engine's whole subject is
*relative* value — ratios of levels, and its five metrics are all built on
``P_t / P_{t-1} - 1`` (ADR-0004). A yield difference is a *level* difference, a
different quantity class with different units, and adding it there would make
"simple returns only" false for the package that states it. This is a new engine
for a new quantity, with its own tests.

**Scale is stated once, as an exact integer.** `BASIS_POINTS_PER_PERCENTAGE_POINT`
is ``100`` and appears nowhere else; the notorious way to get this wrong is a
stray ``10_000``, which is the number of basis points in a *unit fraction* rather
than in a percentage point. Yields here are quoted in percent per annum — 4.30
means 4.30%, not 0.0430 — so the scale is a hundred and a test pins it.

**Floating point, stated rather than hidden.** These are ordinary binary floats,
as every number in this repository is. ``4.30 - 4.20`` is not exactly ``0.10``,
so a basis-point figure carries a few parts in ten-thousand-trillion of error.
That is far below any precision a yield is quoted to, and the renderer rounds to
one decimal place for display; no value is scaled twice, and nothing here
compares a computed change against a threshold for equality.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

__all__ = [
    "BASIS_POINTS_PER_PERCENTAGE_POINT",
    "RATE_LEVEL_UNIT",
    "RateChangeError",
    "RateChange",
    "rate_change",
]

#: Basis points in one percentage point. Exact, integral, and the only scale
#: factor in this module. See the module docstring for the ``10_000`` trap.
BASIS_POINTS_PER_PERCENTAGE_POINT = 100

#: The unit a rate level must be quoted in for this module's arithmetic to mean
#: what it says. Stated so a caller holding a decimal fraction (``0.0430``)
#: discovers the mismatch here rather than by reading a figure a hundred times
#: too small on a page.
RATE_LEVEL_UNIT = "percent per annum"


class RateChangeError(ValueError):
    """A rate change could not be computed from the values supplied.

    A `ValueError` subclass because every case is a caller supplying something
    that is not a pair of finite rate levels. A *market* fact — a yield that did
    not move, or a level of zero — is never this error; those are ordinary
    results, and `RateChange` represents them.
    """


def _level(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RateChangeError(
            f"{name} must be a number, got {type(value).__name__}"
        )
    number = float(value)
    if not math.isfinite(number):
        raise RateChangeError(f"{name} must be finite, got {value!r}")
    return number


@dataclass(frozen=True, slots=True)
class RateChange:
    """One yield's move between two levels, in every unit it is honestly stated in.

    **Three named quantities and no default one.** `basis_points` and
    `percentage_points` are the same difference at two scales and always exist.
    `relative_change` is a different quantity — the ratio — and is `None` when
    the starting level is zero, carrying `relative_unavailable_reason` instead.
    That is the same *value-or-reason, never both, never neither* rule
    `fmis.market_pulse.HorizonMove` enforces, and for the same purpose: a page
    cannot print a blank where a measurement belongs.

    **A negative yield is a real yield.** Nothing here refuses one, and nothing
    treats zero as missing. Government yields have traded below zero within
    living memory of this repository's subject matter, and a model that refused
    them would fail on real data rather than on bad data.
    """

    from_value: float
    to_value: float
    basis_points: float
    percentage_points: float
    relative_change: float | None
    relative_unavailable_reason: str | None

    def __post_init__(self) -> None:
        if (self.relative_change is None) == (
            self.relative_unavailable_reason is None
        ):
            raise RateChangeError(
                "a relative change is a number or the stated reason there is "
                "none — never both and never neither"
            )

    @property
    def is_unchanged(self) -> bool:
        """Whether the two levels are identical.

        Compares the *levels*, not the computed difference against zero: a
        difference of ``0.0`` and two equal levels are the same fact, and asking
        the question of the inputs avoids resting an equality on subtraction.
        """
        return self.from_value == self.to_value


def rate_change(from_value: float, to_value: float) -> RateChange:
    """The move from one yield level to another, in basis points and in ratio.

    Both levels are quoted in **percent per annum** (`RATE_LEVEL_UNIT`): pass
    ``4.20`` for 4.20%, never ``0.0420``.

    The sign convention is the obvious one and is pinned by a test: a yield that
    rose has a **positive** basis-point change.

        >>> change = rate_change(4.20, 4.30)
        >>> round(change.basis_points, 6)
        10.0
        >>> round(change.percentage_points, 6)
        0.1

    Args:
        from_value: the earlier level, in percent per annum.
        to_value: the later level, in percent per annum.

    Returns:
        A `RateChange` carrying the difference at both scales, and the relative
        change or the reason it is undefined.

    Raises:
        RateChangeError: either level is not a finite number.
    """
    start = _level(from_value, "from_value")
    end = _level(to_value, "to_value")

    percentage_points = end - start
    basis_points = percentage_points * BASIS_POINTS_PER_PERCENTAGE_POINT

    if start == 0:
        # A ratio against a zero base is undefined, and this is emphatically not
        # a change of zero: a yield going from 0.00% to 0.25% moved 25 bp.
        return RateChange(
            from_value=start,
            to_value=end,
            basis_points=basis_points,
            percentage_points=percentage_points,
            relative_change=None,
            relative_unavailable_reason=(
                "the relative change is undefined because the earlier level is "
                "zero; the move is still stated in basis points, which need no "
                "base"
            ),
        )

    relative = end / start - 1.0
    if not math.isfinite(relative):  # pragma: no cover - finite/nonzero inputs
        return RateChange(
            from_value=start,
            to_value=end,
            basis_points=basis_points,
            percentage_points=percentage_points,
            relative_change=None,
            relative_unavailable_reason=(
                "the relative change is not a finite number over these levels"
            ),
        )
    return RateChange(
        from_value=start,
        to_value=end,
        basis_points=basis_points,
        percentage_points=percentage_points,
        relative_change=relative,
        relative_unavailable_reason=None,
    )
