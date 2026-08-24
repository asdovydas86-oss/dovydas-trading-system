"""Milestone BU — yield-change arithmetic, and the three facts it keeps apart.

The failure this file guards against is not a crash. It is a page that prints
*"US10Y +2.38%"* under a heading a reader takes to mean basis points, using
arithmetic that is entirely correct. So the tests below pin the **scale**, the
**sign** and the **separation of the three quantities**, and each of them fails
loudly against a plausible mutation:

  * a scale of ``10_000`` instead of ``100`` — the number of basis points in a
    unit *fraction* rather than in a percentage point;
  * a flipped subtraction, which reports every rise as a fall;
  * a relative change reachable through the field a reader takes for *the* move.
"""

from __future__ import annotations

import math

import pytest

from fmis.macro import (
    BASIS_POINTS_PER_PERCENTAGE_POINT,
    RATE_LEVEL_UNIT,
    RateChange,
    RateChangeError,
    rate_change,
)


def bp(change: RateChange) -> float:
    """The basis-point figure rounded past floating-point noise.

    A yield is published to two decimal places in percent, so a difference is
    exact to whole basis points; six decimals is far below that and far above
    the ~1e-14 error binary subtraction introduces.
    """
    return round(change.basis_points, 6)


# --------------------------------------------------------------------------
# The scale
# --------------------------------------------------------------------------


def test_the_scale_is_a_hundred_and_is_an_exact_integer() -> None:
    """*The notorious way to get this wrong is a stray 10,000.*"""
    assert BASIS_POINTS_PER_PERCENTAGE_POINT == 100
    assert isinstance(BASIS_POINTS_PER_PERCENTAGE_POINT, int)
    assert not isinstance(BASIS_POINTS_PER_PERCENTAGE_POINT, bool)


def test_the_stated_level_unit_is_percent_per_annum() -> None:
    """A caller holding a decimal fraction must find the mismatch here."""
    assert RATE_LEVEL_UNIT == "percent per annum"


def test_the_milestone_s_own_example_produces_exactly_ten_basis_points() -> None:
    """4.20% -> 4.30% is +10 bp. The one figure the brief names."""
    change = rate_change(4.20, 4.30)
    assert bp(change) == 10.0
    assert round(change.percentage_points, 6) == 0.1


def test_the_reverse_move_produces_exactly_minus_ten_basis_points() -> None:
    change = rate_change(4.30, 4.20)
    assert bp(change) == -10.0
    assert round(change.percentage_points, 6) == -0.1


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (4.20, 4.30, 10.0),
        (4.30, 4.20, -10.0),
        (0.00, 0.25, 25.0),
        (2.00, 2.01, 1.0),
        (5.00, 4.00, -100.0),
        (1.00, 1.005, 0.5),
        (-0.50, -0.25, 25.0),
        (-0.25, -0.50, -25.0),
    ],
)
def test_basis_points_are_a_hundred_times_the_percentage_point_difference(
    start: float, end: float, expected: float
) -> None:
    """The scale, exercised across signs, zero and a sub-basis-point move.

    A mutation from 100 to 10,000 fails every row; a flipped subtraction fails
    every row whose expectation is signed.
    """
    change = rate_change(start, end)
    assert bp(change) == expected
    assert round(change.percentage_points * 100, 6) == expected


def test_a_rise_is_positive_and_a_fall_is_negative() -> None:
    """The sign convention, pinned on its own so a flip cannot hide."""
    assert rate_change(4.20, 4.30).basis_points > 0
    assert rate_change(4.30, 4.20).basis_points < 0
    assert rate_change(4.20, 4.30).percentage_points > 0
    assert rate_change(4.30, 4.20).percentage_points < 0


# --------------------------------------------------------------------------
# Zero change is a measurement, not an absence
# --------------------------------------------------------------------------


def test_an_unchanged_yield_reports_zero_and_says_it_is_unchanged() -> None:
    change = rate_change(4.19, 4.19)
    assert bp(change) == 0.0
    assert change.percentage_points == 0.0
    assert change.is_unchanged
    assert change.relative_change == 0.0
    assert change.relative_unavailable_reason is None


def test_a_changed_yield_is_not_reported_as_unchanged() -> None:
    assert not rate_change(4.19, 4.20).is_unchanged


def test_unchanged_is_decided_from_the_levels_and_not_from_the_difference() -> None:
    """Two equal levels are the same fact as a zero difference, and asking the
    inputs avoids resting an equality on a subtraction."""
    change = rate_change(0.1 + 0.2, 0.30000000000000004)
    assert change.from_value == change.to_value
    assert change.is_unchanged


# --------------------------------------------------------------------------
# The three quantities stay apart
# --------------------------------------------------------------------------


def test_the_relative_change_is_a_different_number_from_the_basis_point_move() -> None:
    """*Both are true and only one is what a rates column asks for.*"""
    change = rate_change(4.20, 4.30)
    assert bp(change) == 10.0
    assert change.relative_change == pytest.approx(0.023809523809, abs=1e-9)
    # The trap: 2.38% and 10 bp describe one move and are not interchangeable.
    assert change.relative_change != change.basis_points
    assert change.relative_change != change.percentage_points


def test_no_field_is_named_the_change() -> None:
    """*`RateChange` has no field called `the` change.*

    A default-named field is how the wrong quantity reaches a page: a renderer
    reads what looks canonical. Every field here names its own unit.
    """
    fields = set(RateChange.__dataclass_fields__)
    assert fields == {
        "from_value",
        "to_value",
        "basis_points",
        "percentage_points",
        "relative_change",
        "relative_unavailable_reason",
    }
    for banned in ("change", "value", "move", "delta", "pct", "percent"):
        assert banned not in fields


def test_a_zero_starting_level_has_no_relative_change_but_still_has_basis_points() -> None:
    """*A yield going from 0.00% to 0.25% moved 25 bp.*

    The ratio is undefined and the difference is not. Reporting the whole move
    as unavailable would lose a real fact to a division that was never needed.
    """
    change = rate_change(0.0, 0.25)
    assert bp(change) == 25.0
    assert change.percentage_points == 0.25
    assert change.relative_change is None
    assert "undefined" in change.relative_unavailable_reason
    assert "basis points" in change.relative_unavailable_reason


def test_a_negative_yield_is_a_real_yield_and_is_not_refused() -> None:
    """*Government yields have traded below zero within living memory.*"""
    change = rate_change(-0.75, -0.40)
    assert bp(change) == 35.0
    assert change.relative_change is not None


def test_crossing_zero_downward_is_measured_normally() -> None:
    change = rate_change(0.10, -0.10)
    assert bp(change) == -20.0


# --------------------------------------------------------------------------
# The value-or-reason rule
# --------------------------------------------------------------------------


def test_a_relative_change_with_both_a_value_and_a_reason_is_refused() -> None:
    with pytest.raises(RateChangeError, match="never both and never neither"):
        RateChange(
            from_value=1.0,
            to_value=2.0,
            basis_points=100.0,
            percentage_points=1.0,
            relative_change=1.0,
            relative_unavailable_reason="also a reason",
        )


def test_a_relative_change_with_neither_a_value_nor_a_reason_is_refused() -> None:
    with pytest.raises(RateChangeError, match="never both and never neither"):
        RateChange(
            from_value=1.0,
            to_value=2.0,
            basis_points=100.0,
            percentage_points=1.0,
            relative_change=None,
            relative_unavailable_reason=None,
        )


# --------------------------------------------------------------------------
# Inputs that are not rate levels
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["4.20", None, [4.2], {"v": 1}, object()])
def test_a_level_that_is_not_a_number_is_refused(bad: object) -> None:
    with pytest.raises(RateChangeError, match="must be a number"):
        rate_change(bad, 4.30)
    with pytest.raises(RateChangeError, match="must be a number"):
        rate_change(4.20, bad)


def test_a_boolean_is_not_a_rate_level() -> None:
    """`bool` is an `int` in Python; a yield of `True` is a defect, not 1%."""
    with pytest.raises(RateChangeError, match="must be a number"):
        rate_change(True, 4.30)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_a_non_finite_level_is_refused(bad: float) -> None:
    with pytest.raises(RateChangeError, match="must be finite"):
        rate_change(bad, 4.30)
    with pytest.raises(RateChangeError, match="must be finite"):
        rate_change(4.20, bad)


def test_an_integer_level_is_accepted_and_normalised_to_a_float() -> None:
    change = rate_change(4, 5)
    assert bp(change) == 100.0
    assert isinstance(change.from_value, float)
    assert isinstance(change.to_value, float)


# --------------------------------------------------------------------------
# Determinism and immutability
# --------------------------------------------------------------------------


def test_the_record_is_frozen() -> None:
    change = rate_change(4.20, 4.30)
    with pytest.raises(Exception):
        change.basis_points = 0.0


def test_two_calls_over_one_pair_produce_one_result() -> None:
    assert rate_change(4.20, 4.30) == rate_change(4.20, 4.30)


def test_a_very_large_level_is_measured_rather_than_refused() -> None:
    """Hostile review: an absurd but finite level is arithmetic, not an error.

    Nothing here caps a yield, because a cap would be a judgement about what
    markets may do rather than a fact about the arithmetic.
    """
    change = rate_change(1e6, 1e6 + 1)
    assert bp(change) == pytest.approx(100.0)
    assert math.isfinite(change.relative_change)
