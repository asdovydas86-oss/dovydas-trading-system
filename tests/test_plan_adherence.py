"""`fmis.plan.adherence` — the three numbers a commitment and a fill produce together.

Capital at risk, the planned risk/reward pair and the exit divergence. None is
stored, all three are arithmetic, and every one of them is undefined for at least
one real arrangement of prices — which is what most of these tests are about.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from trade_domain_helpers import BTC, MARKET, USDT, trade_plan

from fmis.money import Money, Quantity
from fmis.plan import (
    ExitDivergence,
    PlanError,
    PlanPlacementError,
    capital_at_risk,
    check_placement,
    exit_divergence,
    nearest_planned_level,
    planned_risk_reward,
    risk_distance,
)
from fmis.provenance import Absent
from fmis.records import DomainValidationError
from fmis.snapshotting import RiskRewardReading, TradeDirection

LONG = trade_plan(targets=(Decimal("64000"), Decimal("68000")))
SHORT = trade_plan(
    direction=TradeDirection.SHORT,
    initial_invalidation=Decimal("62000"),
    targets=(Decimal("58000"), Decimal("55000")),
)


# --------------------------------------------------------------------------
# Placement.
# --------------------------------------------------------------------------


def test_a_long_stop_below_the_entry_is_accepted() -> None:
    assert check_placement(LONG, Decimal("60000")) is None


def test_a_short_stop_above_the_entry_is_accepted() -> None:
    assert check_placement(SHORT, Decimal("60000")) is None


def test_a_long_stop_above_the_entry_is_refused() -> None:
    with pytest.raises(PlanPlacementError, match="is not below the entry"):
        check_placement(LONG, Decimal("58000"))


def test_a_short_stop_below_the_entry_is_refused() -> None:
    with pytest.raises(PlanPlacementError, match="is not above the entry"):
        check_placement(SHORT, Decimal("63000"))


def test_a_stop_at_the_entry_is_refused_rather_than_tolerated() -> None:
    """Equality is a division by zero downstream, not a boundary to round off."""
    with pytest.raises(PlanPlacementError, match="risk distance of zero"):
        check_placement(LONG, Decimal("58400"))


def test_a_long_target_below_the_entry_is_refused() -> None:
    plan = trade_plan(targets=(Decimal("59000"),))
    with pytest.raises(PlanPlacementError, match="is not above the entry"):
        check_placement(plan, Decimal("60000"))


def test_a_short_target_above_the_entry_is_refused() -> None:
    plan = trade_plan(
        direction=TradeDirection.SHORT,
        initial_invalidation=Decimal("62000"),
        targets=(Decimal("61000"),),
    )
    with pytest.raises(PlanPlacementError, match="is not below the entry"):
        check_placement(plan, Decimal("60000"))


def test_a_target_at_the_entry_is_refused() -> None:
    plan = trade_plan(targets=(Decimal("60000"),))
    with pytest.raises(PlanPlacementError, match="is not above the entry"):
        check_placement(plan, Decimal("60000"))


def test_a_placement_error_is_both_a_validation_error_and_a_plan_error() -> None:
    assert issubclass(PlanPlacementError, DomainValidationError)
    assert issubclass(PlanPlacementError, PlanError)


def test_placement_refuses_a_non_plan() -> None:
    with pytest.raises(TypeError, match="must be a TradePlan"):
        check_placement("a plan", Decimal("60000"))  # type: ignore[arg-type]


@pytest.mark.parametrize("entry", [Decimal("0"), Decimal("-1")])
def test_placement_refuses_an_entry_that_is_not_a_price(entry: Decimal) -> None:
    with pytest.raises(DomainValidationError, match="must be positive"):
        check_placement(LONG, entry)


def test_placement_refuses_a_float_entry() -> None:
    with pytest.raises(TypeError, match="must be a Decimal"):
        check_placement(LONG, 60000.0)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Risk distance and capital at risk.
# --------------------------------------------------------------------------


def test_the_risk_distance_is_the_gap_between_entry_and_stop() -> None:
    assert risk_distance(LONG, Decimal("60000")) == Decimal("1600")
    assert risk_distance(SHORT, Decimal("60000")) == Decimal("2000")


def test_capital_at_risk_is_the_distance_times_the_quantity_in_the_quote_asset() -> None:
    money = capital_at_risk(
        LONG, entry_price=Decimal("60000"), quantity=Quantity(Decimal("0.5"), BTC)
    )
    assert money == Money(Decimal("800"), USDT)
    assert money.asset == MARKET.quote_asset


def test_capital_at_risk_is_the_same_for_a_short() -> None:
    money = capital_at_risk(
        SHORT, entry_price=Decimal("60000"), quantity=Quantity(Decimal("2"), BTC)
    )
    assert money == Money(Decimal("4000"), USDT)


def test_capital_at_risk_refuses_a_size_in_the_wrong_asset() -> None:
    with pytest.raises(DomainValidationError, match="base asset"):
        capital_at_risk(
            LONG,
            entry_price=Decimal("60000"),
            quantity=Quantity(Decimal("0.5"), USDT),
        )


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-0.5")])
def test_capital_at_risk_refuses_a_size_that_is_not_positive(amount: Decimal) -> None:
    with pytest.raises(DomainValidationError, match="must be positive"):
        capital_at_risk(
            LONG, entry_price=Decimal("60000"), quantity=Quantity(amount, BTC)
        )


def test_capital_at_risk_refuses_a_bare_number_for_a_size() -> None:
    with pytest.raises(TypeError, match="must be a Quantity"):
        capital_at_risk(LONG, entry_price=Decimal("60000"), quantity=Decimal("0.5"))  # type: ignore[arg-type]


def test_capital_at_risk_refuses_a_plan_whose_stop_is_on_the_wrong_side() -> None:
    with pytest.raises(PlanPlacementError):
        capital_at_risk(
            LONG, entry_price=Decimal("58000"), quantity=Quantity(Decimal("1"), BTC)
        )


def test_capital_at_risk_is_exact_at_awkward_sizes() -> None:
    """No float touches this product, so an odd size does not drift."""
    money = capital_at_risk(
        LONG, entry_price=Decimal("60000"), quantity=Quantity(Decimal("0.13"), BTC)
    )
    assert money.text == "208"


# --------------------------------------------------------------------------
# The planned risk/reward pair.
# --------------------------------------------------------------------------


def test_the_planned_pair_is_measured_against_the_nearest_target() -> None:
    reading = planned_risk_reward(LONG, Decimal("60000"))
    assert isinstance(reading, RiskRewardReading)
    assert reading.risk_distance == Decimal("1600")
    assert reading.reward_distance == Decimal("4000")
    assert reading.ratio == Decimal("2.5")


def test_the_pair_is_stored_as_two_numbers_and_divided_at_read_time() -> None:
    reading = planned_risk_reward(LONG, Decimal("60000"))
    assert reading.arithmetic == "4000 ÷ 1600"


def test_the_planned_pair_works_for_a_short() -> None:
    reading = planned_risk_reward(SHORT, Decimal("60000"))
    assert reading.risk_distance == Decimal("2000")
    assert reading.reward_distance == Decimal("2000")


def test_a_plan_with_no_target_has_no_pair_rather_than_a_zero_one() -> None:
    absent = planned_risk_reward(trade_plan(targets=()), Decimal("60000"))
    assert isinstance(absent, Absent)
    assert "no target" in absent.reason


def test_the_planned_pair_refuses_a_stop_on_the_wrong_side() -> None:
    with pytest.raises(PlanPlacementError):
        planned_risk_reward(LONG, Decimal("58000"))


def test_the_planned_pair_refuses_a_non_plan() -> None:
    with pytest.raises(TypeError, match="must be a TradePlan"):
        planned_risk_reward("a plan", Decimal("60000"))  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Exit divergence.
# --------------------------------------------------------------------------


def test_the_nearest_level_to_an_exit_is_named_not_inferred() -> None:
    assert nearest_planned_level(LONG, Decimal("63800")) == ("target 1", Decimal("64000"))
    assert nearest_planned_level(LONG, Decimal("58500")) == ("stop", Decimal("58400"))
    assert nearest_planned_level(LONG, Decimal("67900")) == ("target 2", Decimal("68000"))


def test_a_tie_resolves_to_the_stop_because_that_reading_cannot_flatter() -> None:
    plan = trade_plan(initial_invalidation=Decimal("58000"), targets=(Decimal("62000"),))
    assert nearest_planned_level(plan, Decimal("60000")) == ("stop", Decimal("58000"))


def test_an_exit_short_of_the_target_reports_a_negative_difference() -> None:
    divergence = exit_divergence(LONG, Decimal("63800"))
    assert divergence.reference_label == "target 1"
    assert divergence.reference_price == Decimal("64000")
    assert divergence.difference == Decimal("-200")
    assert divergence.arithmetic == "63800 − 64000"


def test_an_exit_beyond_the_target_reports_a_positive_difference() -> None:
    assert exit_divergence(LONG, Decimal("64300")).difference == Decimal("300")


def test_a_divergence_over_a_size_is_money_in_the_quote_asset() -> None:
    divergence = exit_divergence(LONG, Decimal("63800"))
    assert divergence.as_money(Quantity(Decimal("0.5"), BTC), USDT) == Money(
        Decimal("-100"), USDT
    )


def test_a_divergence_refuses_a_bare_number_for_a_size() -> None:
    with pytest.raises(TypeError, match="must be a Quantity"):
        exit_divergence(LONG, Decimal("63800")).as_money(Decimal("0.5"), USDT)  # type: ignore[arg-type]


def test_a_plan_always_has_at_least_the_stop_to_measure_against() -> None:
    divergence = exit_divergence(trade_plan(targets=()), Decimal("59000"))
    assert divergence.reference_label == "stop"


def test_a_divergence_refuses_a_label_that_is_not_text() -> None:
    with pytest.raises(TypeError, match="reference_label"):
        ExitDivergence(
            reference_label="",
            reference_price=Decimal("1"),
            exit_price=Decimal("1"),
        )


def test_a_divergence_refuses_a_price_that_is_not_a_price() -> None:
    with pytest.raises(DomainValidationError, match="must be positive"):
        ExitDivergence(
            reference_label="stop",
            reference_price=Decimal("0"),
            exit_price=Decimal("1"),
        )


def test_the_nearest_level_refuses_a_non_plan() -> None:
    with pytest.raises(TypeError, match="must be a TradePlan"):
        nearest_planned_level("a plan", Decimal("1"))  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Nothing here is stored.
# --------------------------------------------------------------------------


def test_no_derived_figure_is_a_field_on_the_commitment() -> None:
    """The money rule, asserted: *no quotient is ever a stored field*."""
    fields = set(trade_plan().__dataclass_fields__)
    assert not fields & {
        "capital_at_risk",
        "intended_risk",
        "risk_distance",
        "risk_reward",
        "ratio",
        "r_multiple",
    }
