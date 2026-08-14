"""The arithmetic every risk figure rests on, including every boundary of it.

The sign tests here are the ones mutation testing targets first: swapping
`entry − stop` for `stop − entry` on one branch produces a suite that still
passes unless a *short* is exercised with its own expected number, so every long
assertion below has a short twin with a different arithmetic answer.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from portfolio_risk_helpers import btc, usdt
from trade_domain_helpers import BTC, USDT

from fmis.money import Money, Quantity
from fmis.portfolio_risk import (
    RISK_BASIS,
    PortfolioRiskError,
    RiskGeometryError,
    capital_at_risk_of,
    maximum_quantity_for_risk,
    risk_fraction_of_equity,
    stop_distance,
)
from fmis.positions import PositionDirection
from fmis.records import DomainValidationError, TradeDomainError

LONG = PositionDirection.LONG
SHORT = PositionDirection.SHORT


# -- stop_distance ----------------------------------------------------------


def test_a_long_measures_entry_minus_stop() -> None:
    assert stop_distance(LONG, entry=Decimal("100"), stop=Decimal("90")) == Decimal("10")


def test_a_short_measures_stop_minus_entry() -> None:
    """The twin of the test above, with a different answer for the same inputs
    reversed. A single-branch sign mutation cannot satisfy both."""
    assert stop_distance(SHORT, entry=Decimal("90"), stop=Decimal("100")) == Decimal("10")


def test_the_two_directions_are_not_interchangeable() -> None:
    """Same numbers, opposite sides: one is a valid trade and one is a
    transposition. A formula using `abs()` would accept both."""
    assert stop_distance(LONG, entry=Decimal("100"), stop=Decimal("90")) == Decimal("10")
    with pytest.raises(RiskGeometryError):
        stop_distance(SHORT, entry=Decimal("100"), stop=Decimal("90"))


def test_a_long_stop_above_the_entry_is_refused() -> None:
    with pytest.raises(RiskGeometryError, match="not below the entry"):
        stop_distance(LONG, entry=Decimal("90"), stop=Decimal("100"))


def test_a_short_stop_below_the_entry_is_refused() -> None:
    with pytest.raises(RiskGeometryError, match="not above the entry"):
        stop_distance(SHORT, entry=Decimal("100"), stop=Decimal("90"))


def test_a_stop_exactly_at_the_entry_is_refused_on_both_sides() -> None:
    """The `> 0` boundary. A `>= 0` guard would let a zero distance through and
    every figure derived from it becomes a division by zero."""
    for direction in (LONG, SHORT):
        with pytest.raises(RiskGeometryError, match="distance of zero"):
            stop_distance(direction, entry=Decimal("100"), stop=Decimal("100"))


def test_one_unit_of_distance_is_enough() -> None:
    """One tick below the refused boundary is a valid trade, not a rounding case."""
    assert stop_distance(
        LONG, entry=Decimal("100.01"), stop=Decimal("100")
    ) == Decimal("0.01")


def test_a_flat_direction_has_no_risk_distance() -> None:
    with pytest.raises(RiskGeometryError, match="flat position"):
        stop_distance(
            PositionDirection.FLAT, entry=Decimal("100"), stop=Decimal("90")
        )


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("-1")])
def test_a_non_positive_price_is_refused(price: Decimal) -> None:
    with pytest.raises(DomainValidationError):
        stop_distance(LONG, entry=price, stop=Decimal("-2"))


def test_a_float_price_is_refused() -> None:
    """One float in a price path is a fifty-five-digit digest away from a bug."""
    with pytest.raises(TypeError):
        stop_distance(LONG, entry=100.0, stop=Decimal("90"))  # type: ignore[arg-type]


# -- capital_at_risk_of -----------------------------------------------------


def test_capital_at_risk_on_a_long() -> None:
    risk = capital_at_risk_of(
        LONG,
        entry=Decimal("60000"),
        stop=Decimal("58400"),
        quantity=btc("0.5"),
        quote_asset=USDT,
    )
    assert risk == usdt("800")


def test_capital_at_risk_on_a_short_is_the_same_magnitude_mirrored() -> None:
    risk = capital_at_risk_of(
        SHORT,
        entry=Decimal("58400"),
        stop=Decimal("60000"),
        quantity=btc("0.5"),
        quote_asset=USDT,
    )
    assert risk == usdt("800")


def test_a_short_with_the_long_geometry_is_refused_rather_than_negated() -> None:
    """The understatement hazard: silently negating here would report this
    position's risk as `-800` and a total open risk *lower* than the truth."""
    with pytest.raises(RiskGeometryError):
        capital_at_risk_of(
            SHORT,
            entry=Decimal("60000"),
            stop=Decimal("58400"),
            quantity=btc("0.5"),
            quote_asset=USDT,
        )


def test_capital_at_risk_is_denominated_in_the_quote_asset() -> None:
    risk = capital_at_risk_of(
        LONG,
        entry=Decimal("60000"),
        stop=Decimal("58400"),
        quantity=btc("1"),
        quote_asset=USDT,
    )
    assert risk.asset == USDT


@pytest.mark.parametrize("amount", ["0", "-0.5"])
def test_a_non_positive_quantity_is_refused(amount: str) -> None:
    with pytest.raises(DomainValidationError, match="quantity must be positive"):
        capital_at_risk_of(
            LONG,
            entry=Decimal("60000"),
            stop=Decimal("58400"),
            quantity=Quantity(Decimal(amount), BTC),
            quote_asset=USDT,
        )


def test_a_money_quantity_is_refused() -> None:
    with pytest.raises(TypeError):
        capital_at_risk_of(
            LONG,
            entry=Decimal("60000"),
            stop=Decimal("58400"),
            quantity=usdt("1"),  # type: ignore[arg-type]
            quote_asset=USDT,
        )


# -- risk_fraction_of_equity ------------------------------------------------


def test_a_two_percent_risk_is_the_fraction_zero_point_zero_two() -> None:
    """The unit convention, asserted rather than assumed."""
    assert risk_fraction_of_equity(usdt("2000"), usdt("100000")) == Decimal("0.02")


def test_the_fraction_divides_risk_by_equity_and_not_the_other_way() -> None:
    """A numerator/denominator swap would produce 50 here instead of 0.02."""
    assert risk_fraction_of_equity(usdt("2000"), usdt("100000")) < Decimal(1)


def test_two_currencies_cannot_be_divided() -> None:
    with pytest.raises(DomainValidationError, match="dated rate"):
        risk_fraction_of_equity(usdt("2000"), Money(Decimal("100000"), BTC))


@pytest.mark.parametrize("equity", ["0", "-1"])
def test_a_non_positive_equity_is_undefined_rather_than_large(equity: str) -> None:
    with pytest.raises(DomainValidationError, match="undefined rather than"):
        risk_fraction_of_equity(usdt("2000"), usdt(equity))


# -- maximum_quantity_for_risk ----------------------------------------------


def test_the_sizing_primitive_inverts_capital_at_risk_exactly() -> None:
    """Size for 800 USDT of risk, then price that size: the same 800 comes back."""
    quantity = maximum_quantity_for_risk(
        LONG,
        allowed_risk=usdt("800"),
        entry=Decimal("60000"),
        stop=Decimal("58400"),
        base_asset=BTC,
    )
    assert quantity == btc("0.5")
    assert (
        capital_at_risk_of(
            LONG,
            entry=Decimal("60000"),
            stop=Decimal("58400"),
            quantity=quantity,
            quote_asset=USDT,
        )
        == usdt("800")
    )


def test_the_sizing_primitive_uses_the_short_geometry_for_a_short() -> None:
    quantity = maximum_quantity_for_risk(
        SHORT,
        allowed_risk=usdt("800"),
        entry=Decimal("58400"),
        stop=Decimal("60000"),
        base_asset=BTC,
    )
    assert quantity == btc("0.5")


def test_the_sizing_primitive_refuses_a_non_positive_allowance() -> None:
    with pytest.raises(DomainValidationError, match="refusal to trade"):
        maximum_quantity_for_risk(
            LONG,
            allowed_risk=usdt("0"),
            entry=Decimal("60000"),
            stop=Decimal("58400"),
            base_asset=BTC,
        )


def test_the_sizing_primitive_refuses_broken_geometry() -> None:
    with pytest.raises(RiskGeometryError):
        maximum_quantity_for_risk(
            LONG,
            allowed_risk=usdt("800"),
            entry=Decimal("58400"),
            stop=Decimal("60000"),
            base_asset=BTC,
        )


def test_the_sizing_primitive_reads_no_equity_and_no_portfolio() -> None:
    """It is a primitive, not a sizing product: `AP` §15.4 keeps Buying Power out
    of the portfolio boundary, and a signature that took a portfolio would have
    quietly built it."""
    import inspect

    parameters = set(inspect.signature(maximum_quantity_for_risk).parameters)
    assert parameters == {"direction", "allowed_risk", "entry", "stop", "base_asset"}


# -- the basis --------------------------------------------------------------


def test_the_risk_basis_names_every_cost_it_excludes() -> None:
    for excluded in ("fee", "slippage", "funding", "liquidation", "gap"):
        assert excluded in RISK_BASIS.lower()


def test_the_error_hierarchy_lets_a_caller_catch_either_way() -> None:
    error = RiskGeometryError("x")
    assert isinstance(error, PortfolioRiskError)
    assert isinstance(error, DomainValidationError)
    assert isinstance(error, TradeDomainError)
