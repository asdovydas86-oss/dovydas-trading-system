"""The four arithmetic facts every figure in this package is built from.

Capital at risk, the risk distance behind it, the fraction of equity a risk
amount represents, and the quantity a risk amount buys. Pure functions over
values, computed here and stored nowhere — the same rule `fmis.plan.adherence`
states for the plan-side version of the identical arithmetic.

**The sign is the whole content and is written once.** On a long the stop sits
below the entry and the distance is `entry − stop`; on a short it sits above and
the distance is `stop − entry`. Two expressions, one function, so a short's risk
can never be computed by a caller who reached for the long formula — the failure
mode that makes a portfolio's largest position look like its smallest.

**Invalid geometry raises rather than returning a magnitude.** A stop on the
wrong side of the entry gives a negative distance, and `abs()` over it reports a
transposition as a risk figure. `fmis.plan.adherence.check_placement` refuses the
same shape for the same reason; this refuses it again because a position folded
from real fills can drift its average entry to the stop's side after an add, and
at that moment there genuinely is no risk distance to report.

**Every figure here is pre-cost and pre-funding.** It assumes the stop is
honoured at the stated price. A gap through it loses more, a perpetual accrues
funding, and a liquidation is a different event entirely — this system ingests no
data that bounds any of the three, and `RISK_BASIS` is the sentence every surface
prints beside the number.
"""

from __future__ import annotations

from decimal import Decimal

from fmis.money import AssetCode, Money, Quantity, canonical_decimal_text
from fmis.positions import PositionDirection
from fmis.records import DomainValidationError, TradeDomainError

__all__ = [
    "PortfolioRiskError",
    "RiskGeometryError",
    "RISK_BASIS",
    "stop_distance",
    "capital_at_risk_of",
    "risk_fraction_of_equity",
    "maximum_quantity_for_risk",
]


class PortfolioRiskError(TradeDomainError):
    """Base class for every portfolio and risk-engine failure."""


class RiskGeometryError(DomainValidationError, PortfolioRiskError):
    """An entry, a stop and a direction that cannot all be true at once.

    Its own class because a caller has two legitimate responses and they are not
    the same: a composition root turns it into `Absent(reason)` and keeps
    building the rest of the portfolio, while a sizing call must propagate it.
    Both a `DomainValidationError` and a `PortfolioRiskError`, so neither
    `except` clause is a lie.
    """


#: What every capital-at-risk figure in this package assumes, stated once. It is
#: not a caveat about precision: fees, funding and slippage are real costs this
#: system holds no data for, and a figure that silently excluded them while
#: reading as complete is the failure the sentence exists to prevent.
RISK_BASIS = (
    "pre-cost and pre-funding, and assumes the stop is honoured at the stated "
    "price. Fees, slippage, funding and liquidation are not included, and no "
    "data this system ingests bounds a gap through the stop"
)


def _require_price(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if value <= 0:
        raise DomainValidationError(f"{name} must be positive, got {value}")
    return Decimal(canonical_decimal_text(value))


def _require_open_direction(direction: object) -> PositionDirection:
    if not isinstance(direction, PositionDirection):
        raise TypeError(
            f"direction must be a PositionDirection, got {type(direction).__name__}"
        )
    if direction is PositionDirection.FLAT:
        raise RiskGeometryError(
            "a flat position has no exposure and therefore no capital at risk; "
            "a risk figure over it would be a number about nothing"
        )
    return direction


def stop_distance(
    direction: PositionDirection, *, entry: Decimal, stop: Decimal
) -> Decimal:
    """`entry − stop` on a long, `stop − entry` on a short.

    The denominator every risk figure in this system rests on, and the one place
    the sign is decided. A non-positive result is a refusal rather than an
    absolute value: a stop the price has already passed is not a stop, and
    reporting `|entry − stop|` would turn the worst-placed trade into a
    well-sized one.
    """
    side = _require_open_direction(direction)
    entry_price = _require_price(entry, "entry")
    stop_price = _require_price(stop, "stop")
    if side is PositionDirection.LONG:
        distance = entry_price - stop_price
    else:
        distance = stop_price - entry_price
    if distance <= 0:
        expected = "below" if side is PositionDirection.LONG else "above"
        raise RiskGeometryError(
            f"the stop {canonical_decimal_text(stop_price)} is not {expected} the "
            f"entry {canonical_decimal_text(entry_price)} on a {side.value} "
            "position, so there is no risk distance. A stop at the entry gives a "
            "distance of zero, and every figure derived from it would be a "
            "division by zero rather than a large number"
        )
    return distance


def capital_at_risk_of(
    direction: PositionDirection,
    *,
    entry: Decimal,
    stop: Decimal,
    quantity: Quantity,
    quote_asset: AssetCode,
) -> Money:
    """`risk distance × quantity`, in the market's quote asset.

    A **product**, never a quotient, and never a stored field — the rule
    `fmis.plan.adherence.capital_at_risk` states for a plan's version of this
    figure, applied to a folded position. `quantity` is a positive magnitude
    because the direction is already carried by `direction`, and a signed
    quantity would be the same fact in two places.
    """
    if not isinstance(quantity, Quantity):
        raise TypeError(f"quantity must be a Quantity, got {type(quantity).__name__}")
    if quantity.amount <= 0:
        raise DomainValidationError(
            f"quantity must be positive, got {quantity}; direction is carried by "
            "`direction`, and a signed quantity would be the same fact twice"
        )
    distance = stop_distance(direction, entry=entry, stop=stop)
    return quantity.value_at(distance, quote_asset)


def risk_fraction_of_equity(risk: Money, equity: Money) -> Decimal:
    """`risk ÷ equity` — the fraction a limit stated in equity is compared against.

    A quotient computed at read time and stored nowhere. Both sides are stated in
    one currency: converting here would hide the rate that made them comparable,
    which is `Money`'s own rule and not this function's invention.
    """
    for name, value in (("risk", risk), ("equity", equity)):
        if not isinstance(value, Money):
            raise TypeError(f"{name} must be a Money, got {type(value).__name__}")
    if risk.asset != equity.asset:
        raise DomainValidationError(
            f"risk is stated in {risk.asset} and equity in {equity.asset}; a "
            "fraction over two currencies needs a dated rate this function does "
            "not carry"
        )
    if equity.amount <= 0:
        raise DomainValidationError(
            f"equity is {equity}, so a fraction of it is undefined rather than "
            "large. A zero denominator here would report every trade as within "
            "every limit or outside all of them, depending only on rounding"
        )
    return risk.amount / equity.amount


def maximum_quantity_for_risk(
    direction: PositionDirection,
    *,
    allowed_risk: Money,
    entry: Decimal,
    stop: Decimal,
    base_asset: AssetCode,
) -> Quantity:
    """The largest quantity whose capital at risk does not exceed `allowed_risk`.

    **This is a primitive, not a position-sizing product.** `AP` §15.4 places
    Buying Power in the risk layer and states plainly that it is *not* built at
    the portfolio boundary, *"because placing it in Portfolio would give the
    portfolio object a recommendation"*. This function computes one quotient and
    returns a quantity; it reads no equity, resolves no limit, consults no
    portfolio and recommends nothing. What it deliberately does **not** do is
    decide what `allowed_risk` should be — that needs an equity contract this
    build does not have, because equity requires a mark for every holding and no
    mark source exists yet.

    Exact division with no rounding and no lot-size step. A venue's step size is
    reference data this domain declines to hold, so the quantity returned is the
    arithmetic answer and the owner rounds it **down** at the venue.
    """
    if not isinstance(allowed_risk, Money):
        raise TypeError(
            f"allowed_risk must be a Money, got {type(allowed_risk).__name__}"
        )
    if allowed_risk.amount <= 0:
        raise DomainValidationError(
            f"allowed_risk must be positive, got {allowed_risk}; a non-positive "
            "risk allowance sizes no trade and is a refusal to trade, which is "
            "the owner's decision rather than an arithmetic result"
        )
    distance = stop_distance(direction, entry=entry, stop=stop)
    return Quantity(allowed_risk.amount / distance, base_asset)
