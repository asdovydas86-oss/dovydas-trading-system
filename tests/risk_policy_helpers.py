"""Builders for the risk-policy tests. **No expected value is computed here.**

Every figure a test asserts against is hand-calculated in the test itself and
written as a literal. Nothing in this module calls `plan_for`, `budget_from`,
`PositionSizer` or any arithmetic under test, so a test cannot accidentally
assert that the implementation agrees with itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fmis.money import AssetCode, Money
from fmis.risk_policy import RiskPolicyDeclaration

__all__ = [
    "MOMENT",
    "usdt",
    "declaration",
    "assessment",
]

#: One fixed instant. Every test uses it, so no test result depends on a clock.
MOMENT = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def usdt(amount: str) -> Money:
    """A quote-denominated amount, from text. Never from a float."""
    return Money(Decimal(amount), AssetCode("USDT"))


def declaration(
    *,
    equity: str = "10000",
    fraction: str | None = "0.005",
    at: datetime | None = None,
    note: Any = None,
) -> RiskPolicyDeclaration:
    """The owner's declaration, with the fraction optional exactly as it is."""
    kwargs: dict[str, Any] = {
        "equity": usdt(equity),
        "declared_at": MOMENT if at is None else at,
    }
    if fraction is not None:
        kwargs["per_trade_fraction"] = Decimal(fraction)
    if note is not None:
        kwargs["note"] = note
    return RiskPolicyDeclaration(**kwargs)


class _Direction:
    def __init__(self, value: str) -> None:
        self.value = value


class _Level:
    def __init__(self, price: float) -> None:
        self.price = price


class _Assessment:
    """The three fields the planning layer duck-types over, and nothing else.

    Deliberately **not** a real `SetupAssessment`: the layer under test imports
    nothing from `fmis.swing_setup` and compares no `SetupState`, and a stand-in
    carrying only `symbol`, `direction`, `reference_price`, `stop` and `targets`
    is what proves it.
    """

    def __init__(
        self,
        symbol: str,
        direction: str | None,
        reference_price: float | None,
        stop: float | None,
        targets: tuple[float, ...],
    ) -> None:
        self.symbol = symbol
        self.direction = None if direction is None else _Direction(direction)
        self.reference_price = reference_price
        self.stop = None if stop is None else _Level(stop)
        self.targets = tuple(_Level(price) for price in targets)


def assessment(
    symbol: str = "BTCUSDT",
    *,
    direction: str | None = "long",
    reference_price: float | None = 60000.0,
    stop: float | None = 58000.0,
    targets: tuple[float, ...] = (66000.0,),
) -> Any:
    """One assessment-shaped object. Every field is a parameter."""
    return _Assessment(symbol, direction, reference_price, stop, targets)
