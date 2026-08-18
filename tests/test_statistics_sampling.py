"""The `n` guard — the boundary `AP` §20.7 rule 2 requires.

The most important file in this milestone's suite. Everything else computes a
number; this decides whether a number may be stated at all, and the two ways it
can be wrong are opposite and equally bad: stating a rate over three trades, and
refusing to state a count over three trades.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from fmis.money import AssetCode, Money
from fmis.provenance import Absent
from fmis.statistics import (
    Sample,
    SamplePolicy,
    StatisticsRefusedError,
    Tally,
    collect_values,
    count_of,
    extremum_or_absent,
    mean_duration_or_absent,
    mean_or_absent,
    median_duration_or_absent,
    median_or_absent,
    ordered_values,
    ratio_or_absent,
    share_or_absent,
    total_or_absent,
)

USDT = AssetCode("USDT")
FLOOR = SamplePolicy(minimum_sample=5)


def money(raw: str) -> Money:
    return Money(Decimal(raw), USDT)


def sample(*values: object, missing: int = 0, reasons: tuple[str, ...] = ()) -> Sample:
    return Sample(
        subject="thing", values=tuple(values), missing=missing, reasons=reasons
    )


# --------------------------------------------------------------------------
# The policy itself
# --------------------------------------------------------------------------


def test_the_default_floor_is_stated_and_is_not_one() -> None:
    """A floor of one is no floor. Pinned so lowering it is a visible edit."""
    assert SamplePolicy().minimum_sample == 30


def test_the_floor_admits_exactly_at_the_boundary_and_refuses_below_it() -> None:
    assert not FLOOR.admits(4)
    assert FLOOR.admits(5)
    assert FLOOR.admits(6)


def test_a_refusal_carries_n_so_a_reader_can_tell_three_from_none() -> None:
    refusal = FLOOR.insufficient("win rate", 3)
    assert isinstance(refusal, Absent)
    assert refusal.sample_size == 3
    assert "3 observation(s)" in refusal.reason
    assert "floor of 5" in refusal.reason


def test_the_refusal_states_that_passing_the_floor_establishes_nothing() -> None:
    """The sentence is the whole defence against the floor being read as a
    sufficiency threshold."""
    assert "establishes nothing" in FLOOR.insufficient("x", 1).reason


def test_a_floor_below_one_is_refused() -> None:
    with pytest.raises(Exception):
        SamplePolicy(minimum_sample=0)


def test_the_policy_is_versioned_and_names_itself() -> None:
    policy = SamplePolicy()
    assert policy.policy_id == "fmits.statistics"
    assert policy.policy_version >= 1


# --------------------------------------------------------------------------
# Tally — a count is a fact at any n
# --------------------------------------------------------------------------


def test_a_count_carries_its_population() -> None:
    tally = count_of((1, 2, 3, 4), lambda value: value % 2 == 0, "even")
    assert (tally.count, tally.total) == (2, 4)


def test_a_count_over_a_population_it_exceeds_is_refused() -> None:
    with pytest.raises(StatisticsRefusedError, match="does not hold"):
        Tally(subject="impossible", count=5, total=4)


def test_a_counts_share_is_a_rate_and_is_therefore_floored() -> None:
    """The distinction the whole module rests on: the count renders, the share
    does not."""
    tally = Tally(subject="win rate", count=2, total=3)
    assert tally.count == 2
    assert isinstance(tally.share(FLOOR), Absent)


def test_a_share_over_a_large_enough_population_is_stated() -> None:
    assert Tally(subject="win rate", count=3, total=6).share(FLOOR) == Decimal("0.5")


# --------------------------------------------------------------------------
# Sample — what contributed, and what did not
# --------------------------------------------------------------------------


def test_collecting_separates_the_values_from_the_absences_and_keeps_the_reasons() -> None:
    items = (Decimal(1), Absent("simulated only"), Decimal(3), Absent("simulated only"))
    collected = collect_values(items, lambda value: value, "R multiple")
    assert collected.size == 2
    assert collected.missing == 2
    assert collected.reasons == ("simulated only", "simulated only")


def test_a_partial_sample_says_how_many_contributed_and_why_the_rest_did_not() -> None:
    collected = collect_values(
        (Decimal(1), Absent("nobody simulated it")), lambda value: value, "MAE"
    )
    note = collected.coverage_note
    assert not isinstance(note, Absent)
    assert "1 of 2 contributed" in note
    assert "nobody simulated it" in note


def test_a_complete_sample_says_so_as_an_absence_rather_than_an_empty_note() -> None:
    """`Absent` here means *"there is no coverage gap"*, which is different from
    a blank a renderer would print as an unexplained gap."""
    collected = collect_values((Decimal(1),), lambda value: value, "R")
    assert isinstance(collected.coverage_note, Absent)
    assert not collected.is_partial


def test_a_samples_population_is_what_contributed_plus_what_did_not() -> None:
    collected = sample(Decimal(1), Decimal(2), missing=3, reasons=("gone",))
    assert (collected.size, collected.missing, collected.population) == (2, 3, 5)


# --------------------------------------------------------------------------
# Totals refuse to omit; distributions report their n
# --------------------------------------------------------------------------


def test_a_total_with_a_missing_contributor_is_absent_not_smaller() -> None:
    """`PortfolioSnapshot`'s rule, reused: a partial total looks complete."""
    total = total_or_absent(
        (money("10"), Absent("this one could not be valued")),
        asset=USDT,
        subject="gross profit",
    )
    assert isinstance(total, Absent)
    assert "could not be valued" in total.reason


def test_a_total_over_complete_values_is_the_sum() -> None:
    assert total_or_absent(
        (money("10"), money("5")), asset=USDT, subject="gross profit"
    ) == money("15")


def test_a_total_over_nothing_is_an_explicit_zero_in_its_asset() -> None:
    """Different from an absence: no winning trade genuinely means zero gross
    profit, and the asset must survive so the figure can still be added to."""
    total = total_or_absent((), asset=USDT, subject="gross profit")
    assert total == Money.zero(USDT)


def test_a_mean_is_not_floored_because_it_describes_the_values_in_hand() -> None:
    """*"The three R multiples I have average 0.4"* is exactly true at n = 3."""
    mean = mean_or_absent(sample(Decimal(1), Decimal(0), Decimal("0.2")), FLOOR)
    assert mean == Decimal("0.4")


def test_a_mean_over_nothing_is_absent_with_a_sample_size_of_zero() -> None:
    mean = mean_or_absent(sample(missing=2, reasons=("no excursion",)), FLOOR)
    assert isinstance(mean, Absent)
    assert mean.sample_size == 0
    assert "no excursion" in mean.reason


def test_the_median_of_an_odd_sample_is_the_middle_value() -> None:
    assert median_or_absent(
        sample(Decimal(5), Decimal(1), Decimal(3)), FLOOR
    ) == Decimal(3)


def test_the_median_of_an_even_sample_is_the_exact_mean_of_the_two_middles() -> None:
    assert median_or_absent(
        sample(Decimal(1), Decimal(2), Decimal(3), Decimal(4)), FLOOR
    ) == Decimal("2.5")


def test_the_median_does_not_depend_on_the_order_it_was_given() -> None:
    forwards = median_or_absent(sample(Decimal(1), Decimal(9), Decimal(2)), FLOOR)
    backwards = median_or_absent(sample(Decimal(2), Decimal(9), Decimal(1)), FLOOR)
    assert forwards == backwards == Decimal(2)


def test_the_extremum_takes_the_top_or_the_bottom_as_asked() -> None:
    values = sample(Decimal(-3), Decimal(7), Decimal(1))
    assert extremum_or_absent(values, FLOOR, largest=True) == Decimal(7)
    assert extremum_or_absent(values, FLOOR, largest=False) == Decimal(-3)


def test_an_extremum_over_nothing_is_absent_rather_than_a_value_error() -> None:
    absent = extremum_or_absent(sample(), FLOOR, largest=True)
    assert isinstance(absent, Absent)
    assert absent.sample_size == 0


def test_a_non_boolean_largest_is_refused_rather_than_coerced() -> None:
    with pytest.raises(TypeError, match="largest"):
        extremum_or_absent(sample(Decimal(1)), FLOOR, largest=1)


def test_durations_average_and_median_exactly() -> None:
    spans = sample(timedelta(days=1), timedelta(days=3))
    assert mean_duration_or_absent(spans, FLOOR) == timedelta(days=2)
    assert median_duration_or_absent(spans, FLOOR) == timedelta(days=2)


def test_an_odd_duration_sample_takes_its_middle() -> None:
    spans = sample(timedelta(days=1), timedelta(days=9), timedelta(days=4))
    assert median_duration_or_absent(spans, FLOOR) == timedelta(days=4)


def test_a_duration_reduction_over_nothing_is_absent() -> None:
    assert isinstance(mean_duration_or_absent(sample(), FLOOR), Absent)
    assert isinstance(median_duration_or_absent(sample(), FLOOR), Absent)


def test_ordered_values_are_sorted_for_a_histogram() -> None:
    assert ordered_values(sample(Decimal(3), Decimal(1))) == [Decimal(1), Decimal(3)]


# --------------------------------------------------------------------------
# Ratios — the floored family
# --------------------------------------------------------------------------


def test_a_ratio_below_the_floor_is_refused_and_carries_n() -> None:
    refused = ratio_or_absent(Decimal(3), Decimal(1), "profit factor", 4, FLOOR)
    assert isinstance(refused, Absent)
    assert refused.sample_size == 4


def test_a_ratio_at_the_floor_is_stated() -> None:
    assert ratio_or_absent(
        Decimal(3), Decimal(2), "profit factor", 5, FLOOR
    ) == Decimal("1.5")


def test_a_zero_denominator_is_undefined_rather_than_large() -> None:
    """The usual way profit factor lies: a corpus with no loser."""
    absent = ratio_or_absent(Decimal(9), Decimal(0), "profit factor", 9, FLOOR)
    assert isinstance(absent, Absent)
    assert "undefined rather than large" in absent.reason
    assert absent.sample_size == 9


def test_the_floor_is_checked_before_the_denominator() -> None:
    """Both refusals apply; the sample one is the actionable one, so it wins."""
    absent = ratio_or_absent(Decimal(1), Decimal(0), "profit factor", 2, FLOOR)
    assert "below the stated floor" in absent.reason


def test_a_share_is_the_ratio_form_of_a_count() -> None:
    assert share_or_absent(3, 6, "win rate", FLOOR) == Decimal("0.5")
    assert isinstance(share_or_absent(1, 2, "win rate", FLOOR), Absent)


def test_a_share_of_an_empty_population_is_absent_not_zero() -> None:
    absent = share_or_absent(0, 0, "win rate", SamplePolicy(minimum_sample=1))
    assert isinstance(absent, Absent)


# --------------------------------------------------------------------------
# The types the guard refuses
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda: mean_or_absent("not a sample", FLOOR),
        lambda: median_or_absent(sample(), "not a policy"),
        lambda: extremum_or_absent("no", FLOOR, largest=True),
        lambda: mean_duration_or_absent("no", FLOOR),
        lambda: median_duration_or_absent(sample(), "no"),
        lambda: ratio_or_absent(1, Decimal(1), "x", 1, FLOOR),
        lambda: ratio_or_absent(Decimal(1), 1, "x", 1, FLOOR),
        lambda: ordered_values("no"),
        lambda: Sample(subject="x", values=[], missing=0),
        lambda: Sample(subject="x", values=(), missing=0, reasons=["no"]),
    ],
)
def test_a_wrong_type_is_refused_rather_than_coerced(call) -> None:
    with pytest.raises(TypeError):
        call()
