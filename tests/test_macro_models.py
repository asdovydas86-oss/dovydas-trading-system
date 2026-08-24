"""Milestone BU — the macro models refuse everything they cannot represent.

The organizing rule, inherited from `fmis.market_pulse.models`: **absence is a
value, never a gap**, and a type that could hold a blank where a measurement
belongs is a type that will eventually print one. So every field is validated at
construction, and this file is the proof that each refusal exists — including the
ones a caller reaches only by making a mistake.

The brief's model section, point by point: a valid price observation, a valid
yield observation, an invalid unit, a negative value where one is invalid, yield
boundaries, duplicate ids, timezone-aware timestamps, naive-timestamp refusal and
future-timestamp refusal.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from fmis.macro import (
    CrossAssetRelationship,
    MacroContextReport,
    MacroError,
    MacroLevel,
    MacroReportError,
    RateFact,
    rate_change,
)
from fmis.market_pulse import (
    Horizon,
    MarketReading,
    MarketUniverse,
    QuantityKind,
    VolatilityReading,
)
from tests.macro_helpers import day, macro_benchmark, yield_benchmark

H5 = Horizon(horizon_id="h5", bars=5, description="five observations")
NAIVE = datetime(2026, 8, 20)
OFFSET = datetime(2026, 8, 20, tzinfo=timezone(timedelta(hours=2)))
LONDON = datetime(2026, 8, 20, tzinfo=ZoneInfo("Europe/London"))


def level(**kwargs) -> MacroLevel:
    base = dict(
        benchmark_id="SPX",
        display_name="S&P 500",
        value=7674.37,
        unit="index points",
        quantity_kind=QuantityKind.PRICE_LIKE,
        observed_at=day(35),
        source="fred SP500 1d",
    )
    base.update(kwargs)
    return MacroLevel(**base)


def relationship(**kwargs) -> CrossAssetRelationship:
    base = dict(
        subject_id="SPX",
        reference_id="BTC",
        metric="pearson_correlation",
        value=-0.42,
        unavailable_reason=None,
        observation_count=22,
        aligned_count=30,
        window_start=day(10),
        window_end=day(35),
    )
    base.update(kwargs)
    return CrossAssetRelationship(**base)


def reading(benchmark) -> MarketReading:
    return MarketReading(
        benchmark=benchmark,
        source="fred",
        interval="1d",
        last_bar_open=day(35),
        closed_bar_count=30,
        moves=(),
        volatility=VolatilityReading(
            value=0.01,
            unavailable_reason=None,
            metric="realized_volatility",
            observation_count=22,
            window_start=day(10),
            window_end=day(35),
        ),
    )


# --------------------------------------------------------------------------
# Valid observations
# --------------------------------------------------------------------------


def test_a_valid_price_level_is_accepted() -> None:
    entry = level()
    assert entry.value == 7674.37
    assert entry.quantity_kind is QuantityKind.PRICE_LIKE


def test_a_valid_yield_level_is_accepted() -> None:
    entry = level(
        benchmark_id="US10Y",
        value=4.69,
        unit="percent per annum",
        quantity_kind=QuantityKind.RATE_LIKE,
    )
    assert entry.value == 4.69
    assert entry.quantity_kind is QuantityKind.RATE_LIKE


def test_a_negative_yield_level_is_accepted_because_yields_go_negative() -> None:
    assert level(value=-0.43, quantity_kind=QuantityKind.RATE_LIKE).value == -0.43


def test_a_zero_level_is_a_measurement_and_not_an_absence() -> None:
    """A yield of exactly zero is a real print, not a missing one."""
    assert level(value=0.0, quantity_kind=QuantityKind.RATE_LIKE).value == 0.0


def test_a_level_is_frozen() -> None:
    with pytest.raises(Exception):
        level().value = 1.0


# --------------------------------------------------------------------------
# Text fields
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["benchmark_id", "display_name", "unit", "source"]
)
def test_a_text_field_that_is_not_text_is_refused(field: str) -> None:
    with pytest.raises(TypeError, match="must be a str"):
        level(**{field: 7})


@pytest.mark.parametrize(
    "field", ["benchmark_id", "display_name", "unit", "source"]
)
def test_a_blank_text_field_is_refused(field: str) -> None:
    """*A unit nobody stated is not a unit that means anything.*"""
    with pytest.raises(ValueError, match="must not be blank"):
        level(**{field: "   "})


def test_a_text_field_is_stripped_of_surrounding_whitespace() -> None:
    assert level(unit="  index points  ").unit == "index points"


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["7674.37", None, [1.0], {"v": 1}])
def test_a_level_value_that_is_not_a_number_is_refused(bad: object) -> None:
    with pytest.raises(TypeError, match="must be a number"):
        level(value=bad)


def test_a_boolean_level_value_is_refused() -> None:
    """`bool` is an `int` in Python; a level of `True` is a defect, not 1."""
    with pytest.raises(TypeError, match="must be a number"):
        level(value=True)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_a_non_finite_level_value_is_refused(bad: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        level(value=bad)


@pytest.mark.parametrize("bad", ["22", None, 2.5, True])
def test_a_count_that_is_not_an_integer_is_refused(bad: object) -> None:
    with pytest.raises(TypeError, match="must be an int"):
        relationship(observation_count=bad)


def test_a_negative_count_is_refused() -> None:
    with pytest.raises(ValueError, match="must be at least 0"):
        relationship(observation_count=-1, aligned_count=-1)


# --------------------------------------------------------------------------
# Timestamps — the canonical-time contract
# --------------------------------------------------------------------------


def test_a_timezone_aware_utc_timestamp_is_accepted() -> None:
    assert level(observed_at=day(35)).observed_at == day(35)


def test_a_naive_timestamp_is_refused() -> None:
    """*A naive datetime has no defined instant.*"""
    with pytest.raises(ValueError, match="must be timezone-aware"):
        level(observed_at=NAIVE)


def test_a_non_utc_offset_is_refused() -> None:
    with pytest.raises(ValueError, match="must represent UTC"):
        level(observed_at=OFFSET)


def test_a_regional_zone_that_is_zero_offset_only_in_winter_is_refused() -> None:
    """`Europe/London` is zero-offset in winter and +01:00 in summer; accepting
    it by momentary offset would be inconsistent."""
    with pytest.raises(ValueError, match="must represent UTC"):
        level(observed_at=LONDON)


@pytest.mark.parametrize("bad", ["2026-08-20", 1755648000, None])
def test_a_timestamp_that_is_not_a_datetime_is_refused(bad: object) -> None:
    with pytest.raises(TypeError, match="must be a datetime"):
        level(observed_at=bad)


def test_a_relationship_window_that_ends_before_it_starts_is_refused() -> None:
    with pytest.raises(MacroReportError, match="before it starts"):
        relationship(window_start=day(35), window_end=day(10))


def test_a_relationship_window_endpoint_must_be_utc() -> None:
    with pytest.raises(ValueError, match="must represent UTC"):
        relationship(window_start=OFFSET, window_end=day(35))


# --------------------------------------------------------------------------
# Quantity kind
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["price_like", None, 1])
def test_a_quantity_kind_that_is_not_one_is_refused(bad: object) -> None:
    with pytest.raises(TypeError, match="must be a QuantityKind"):
        level(quantity_kind=bad)


# --------------------------------------------------------------------------
# Rate facts
# --------------------------------------------------------------------------


def yield_fact(**kwargs) -> RateFact:
    base = dict(
        benchmark_id="US10Y",
        display_name="US 10-year Treasury yield",
        level=level(
            benchmark_id="US10Y",
            value=4.69,
            unit="percent per annum",
            quantity_kind=QuantityKind.RATE_LIKE,
        ),
        changes=(("h5", rate_change(4.63, 4.69)),),
    )
    base.update(kwargs)
    return RateFact(**base)


def test_a_valid_rate_fact_is_accepted_and_looks_its_horizon_up() -> None:
    fact = yield_fact()
    assert fact.change_for("h5") is not None
    assert fact.change_for("h21") is None


def test_a_rate_fact_refuses_a_level_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="must be a MacroLevel"):
        yield_fact(level="4.69%")


def test_a_rate_fact_refuses_a_change_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="must hold RateChange values"):
        yield_fact(changes=((("h5"), 0.06),))


def test_a_rate_fact_refuses_a_malformed_change_pair() -> None:
    with pytest.raises(TypeError, match=r"\(horizon_id, RateChange\) pairs"):
        yield_fact(changes=("h5",))


def test_a_rate_fact_refuses_a_malformed_unavailable_pair() -> None:
    with pytest.raises(TypeError, match=r"\(horizon_id, reason\) pairs"):
        yield_fact(unavailable_horizons=("h21",))


@pytest.mark.parametrize("field", ["benchmark_id", "display_name"])
def test_a_rate_fact_refuses_a_blank_identity(field: str) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        yield_fact(**{field: "  "})


# --------------------------------------------------------------------------
# Relationships
# --------------------------------------------------------------------------


def test_a_relationship_with_both_a_value_and_a_reason_is_refused() -> None:
    with pytest.raises(MacroReportError, match="one measurement has one outcome"):
        relationship(value=0.5, unavailable_reason="also a reason")


def test_a_relationship_with_neither_a_value_nor_a_reason_is_refused() -> None:
    with pytest.raises(MacroReportError, match="one measurement has one outcome"):
        relationship(
            value=None,
            unavailable_reason=None,
            window_start=None,
            window_end=None,
        )


def test_a_refused_comparison_may_not_also_carry_a_number() -> None:
    """*A refused comparison has no number.*"""
    with pytest.raises(MacroReportError, match="refused comparison has no number"):
        relationship(not_comparable_detail="different quantity kind")


def test_a_comparability_key_that_is_not_one_is_refused() -> None:
    with pytest.raises(TypeError, match="must be a ComparabilityKey or None"):
        relationship(comparability="price vs rate")


@pytest.mark.parametrize("field", ["subject_id", "reference_id", "metric"])
def test_a_relationship_refuses_a_blank_identity(field: str) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        relationship(**{field: "   "})


def test_a_refusal_must_state_its_reason() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        relationship(
            value=None,
            unavailable_reason="   ",
            window_start=None,
            window_end=None,
        )


# --------------------------------------------------------------------------
# The report's own invariants
# --------------------------------------------------------------------------


def report(**kwargs) -> MacroContextReport:
    spx = macro_benchmark()
    base = dict(
        as_of=day(40),
        universe=MarketUniverse(name="macro", benchmarks=(spx,)),
        levels=(level(),),
        readings=(reading(spx),),
        unavailable=(),
        rate_facts=(),
        relationships=(),
        horizons=(H5,),
    )
    base.update(kwargs)
    return MacroContextReport(**base)


def test_a_valid_report_is_accepted() -> None:
    built = report()
    assert built.read_count == 1
    assert not built.is_empty
    assert built.unsupported_count == 0


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("levels", "MacroLevel"),
        ("readings", "MarketReading"),
        ("unavailable", "MarketUnavailable"),
        ("rate_facts", "RateFact"),
        ("relationships", "CrossAssetRelationship"),
        ("horizons", "Horizon"),
    ],
)
def test_a_collection_holding_the_wrong_type_is_refused(
    field: str, expected: str
) -> None:
    with pytest.raises(TypeError, match=f"must hold {expected} values"):
        report(**{field: ("not one",)})


@pytest.mark.parametrize(
    "field",
    ["levels", "readings", "unavailable", "rate_facts", "relationships", "horizons"],
)
def test_a_collection_that_is_not_iterable_is_refused(field: str) -> None:
    with pytest.raises(TypeError, match="must be an iterable"):
        report(**{field: 7})


def test_a_universe_that_is_not_one_is_refused() -> None:
    with pytest.raises(TypeError, match="must be a MarketUniverse"):
        report(universe="macro")


def test_a_report_instant_must_be_utc() -> None:
    with pytest.raises(ValueError, match="must be timezone-aware"):
        report(as_of=NAIVE)


def test_one_horizon_declared_twice_is_refused() -> None:
    with pytest.raises(MacroReportError, match="declared twice"):
        report(horizons=(H5, H5))


def test_a_report_may_not_describe_a_market_outside_its_own_scope() -> None:
    stray = macro_benchmark("VIX", series_id="VIXCLS", display_name="VIX")
    with pytest.raises(MacroReportError, match="stated scope does not contain"):
        report(readings=(reading(stray),))


def test_a_rate_fact_for_an_unread_market_is_refused() -> None:
    with pytest.raises(MacroReportError, match="a rate fact is reported for"):
        report(rate_facts=(yield_fact(),))


def test_relationships_without_a_named_reference_are_refused() -> None:
    """*A correlation against an unnamed series is not interpretable.*"""
    with pytest.raises(MacroReportError, match="no reference market named"):
        report(relationships=(relationship(),))


def test_a_blank_reference_name_is_refused() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        report(relationships=(relationship(),), relationship_reference="  ")


# --------------------------------------------------------------------------
# Projections
# --------------------------------------------------------------------------


def test_a_lookup_returns_what_it_finds_and_none_otherwise() -> None:
    built = report()
    assert built.level_for("SPX").benchmark_id == "SPX"
    assert built.level_for("VIX") is None
    assert built.reading_for("SPX") is not None
    assert built.reading_for("VIX") is None
    assert built.rate_fact_for("SPX") is None


def test_freshness_of_an_unread_market_is_none_rather_than_a_verdict() -> None:
    built = report()
    assert built.freshness_of("VIX") is None
    assert built.freshness_of("SPX") is not None


def test_readings_behind_schedule_names_only_the_late_ones() -> None:
    spx = macro_benchmark()
    built = report(as_of=day(400), readings=(reading(spx),), levels=())
    late = built.readings_behind_schedule()
    assert [entry.benchmark_id for entry in late] == ["SPX"]


def test_no_reading_is_behind_schedule_on_a_current_page() -> None:
    assert report().readings_behind_schedule() == ()


def test_the_error_hierarchy_lets_one_except_catch_the_package() -> None:
    assert issubclass(MacroReportError, MacroError)
    assert issubclass(MacroReportError, ValueError)


def test_a_report_is_frozen() -> None:
    with pytest.raises(Exception):
        report().as_of = day(1)


def test_a_level_observed_after_the_report_s_instant_is_refused() -> None:
    """The level's own future-observation guard, distinct from the reading's.

    A level is what the page prints as *"where this market is"*, so a level from
    after the instant being described would be the most direct way for a clock
    defect to reach a reader as a fact.
    """
    with pytest.raises(MacroReportError, match="clock problem"):
        report(levels=(level(observed_at=day(90)),))
