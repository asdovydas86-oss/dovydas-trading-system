"""Comparing a commitment against what the fills actually did.

Every function here is **pure arithmetic over values it is given**, and nothing
it produces is ever stored. That is not a style preference: capital at risk, the
planned risk/reward and the exit divergence are all products or differences over
fields two records already hold, and a fourth copy would be the one that
disagrees the first time a `Correction` moves a fill price.

**This module takes plain values, not records.** It receives a `TradePlan`, an
exact price and a `Quantity` — never a `Trade` and never a `ResolvedTrade` — so
`fmis.plan` never imports `fmis.ledger`. A plan is valid with no fill against it
at all (§9.1: *"an unproposed, unexecuted plan is equally valid"*), and a package
that needed the ledger to describe itself would have quietly made that false.

**The placement check is here rather than on `TradePlan` because it needs three
numbers and the record holds two.** A plan knows its stop and its targets and
refuses a ladder that steps the wrong way at construction; only the composition
root also knows the entry price, and only with all three can *"the stop is on the
wrong side of the entry"* be said at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fmis.money import AssetCode, Money, Quantity, canonical_decimal_text
from fmis.plan.models import PlanError, TradePlan
from fmis.provenance import Absent
from fmis.records import DomainValidationError
from fmis.snapshotting import RiskRewardReading, TradeDirection

__all__ = [
    "PlanPlacementError",
    "ExitDivergence",
    "check_placement",
    "risk_distance",
    "capital_at_risk",
    "planned_risk_reward",
    "nearest_planned_level",
    "exit_divergence",
]


class PlanPlacementError(DomainValidationError, PlanError):
    """A stop, a target and an entry price that cannot all be true at once.

    Its own class because the remedy is never *"store it and warn"*: a stop above
    the entry on a long is a transposition, and a plan recorded with one would
    report a negative risk distance forever. Both a `DomainValidationError` and a
    `PlanError`, so neither `except` clause is a lie.
    """


def _require_plan(plan: Any) -> TradePlan:
    if not isinstance(plan, TradePlan):
        raise TypeError(f"plan must be a TradePlan, got {type(plan).__name__}")
    return plan


def _require_price(value: Any, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if value <= 0:
        raise DomainValidationError(f"{name} must be positive, got {value}")
    return Decimal(canonical_decimal_text(value))


def check_placement(plan: TradePlan, entry_price: Decimal) -> None:
    """Refuse a commitment whose three prices contradict each other.

    Two rules, and each has exactly one reading:

    * **The stop is on the losing side of the entry.** Below it on a long, above
      it on a short. A stop the price is already past is not a stop.
    * **Every target is on the winning side of the entry.** A "target" the trade
      reaches by going wrong is a stop with the wrong label, and a plan holding
      one would report a negative reward distance.

    Equality is refused in both cases and not treated as a boundary to be
    tolerated: a stop *at* the entry gives a risk distance of zero, and every
    figure derived from it — capital at risk, R-multiple, risk/reward — is then a
    division by zero rather than a large number.
    """
    _require_plan(plan)
    entry = _require_price(entry_price, "entry_price")
    is_long = plan.direction is TradeDirection.LONG
    stop = plan.initial_invalidation
    stop_ok = stop < entry if is_long else stop > entry
    if not stop_ok:
        expected = "below" if is_long else "above"
        raise PlanPlacementError(
            f"the stop {canonical_decimal_text(stop)} is not {expected} the entry "
            f"{canonical_decimal_text(entry)} on a {plan.direction.value} trade. "
            "A stop the entry has already passed is not a stop, and a stop at the "
            "entry gives a risk distance of zero"
        )
    for position, target in enumerate(plan.targets):
        target_ok = target > entry if is_long else target < entry
        if not target_ok:
            expected = "above" if is_long else "below"
            raise PlanPlacementError(
                f"targets[{position}] {canonical_decimal_text(target)} is not "
                f"{expected} the entry {canonical_decimal_text(entry)} on a "
                f"{plan.direction.value} trade. A target reached by the trade "
                "going wrong is a stop with the wrong label"
            )


def risk_distance(plan: TradePlan, entry_price: Decimal) -> Decimal:
    """`|entry − stop|` — the denominator every risk figure in this system rests on."""
    check_placement(plan, entry_price)
    entry = Decimal(canonical_decimal_text(entry_price))
    return abs(entry - plan.initial_invalidation)


def capital_at_risk(
    plan: TradePlan, *, entry_price: Decimal, quantity: Quantity
) -> Money:
    """`|entry − stop| × quantity`, in the market's quote asset.

    A **product**, computed here and stored nowhere. This is what the owner
    actually put at risk if the stop is honoured, and it is the whole content of
    the brief's *capital at risk* — derived from three asserted numbers rather
    than typed as a fourth that could disagree with them.

    It is not a claim about what will be lost. A gap through the stop loses more,
    and this system ingests no data that could bound that; the surface says so.
    """
    _require_plan(plan)
    if not isinstance(quantity, Quantity):
        raise TypeError(f"quantity must be a Quantity, got {type(quantity).__name__}")
    if quantity.amount <= 0:
        raise DomainValidationError(
            f"quantity must be positive, got {quantity}; direction is carried by "
            "the plan, and a signed quantity would be the same fact twice"
        )
    if quantity.asset != plan.market.base_asset:
        raise DomainValidationError(
            f"quantity is denominated in {quantity.asset} but the plan's market "
            f"trades {plan.market.base_asset} as its base asset"
        )
    distance = risk_distance(plan, entry_price)
    return quantity.value_at(distance, plan.market.quote_asset)


def planned_risk_reward(
    plan: TradePlan, entry_price: Decimal
) -> RiskRewardReading | Absent:
    """The pair `(risk distance, reward distance)` against the **nearest** target.

    A pair, never a quotient — `RiskRewardReading` is the domain's own type for
    exactly this and it computes the ratio at read time. The nearest target is
    used because it is the first thing the trade can reach; a plan's later
    targets describe how much of the position runs, which this milestone does not
    model.

    `Absent` when the plan names no target: a reward distance over no target is
    not zero, it is undefined, and a zero would make every ratio look terrible.
    """
    _require_plan(plan)
    target = plan.first_target
    if isinstance(target, Absent):
        return target
    distance = risk_distance(plan, entry_price)
    entry = Decimal(canonical_decimal_text(entry_price))
    return RiskRewardReading(risk_distance=distance, reward_distance=abs(target - entry))


@dataclass(frozen=True, slots=True)
class ExitDivergence:
    """How far an exit fill landed from the planned level nearest to it.

    **`reference` is chosen by proximity, and that is a stated convention rather
    than a claim about intent.** FMITS cannot know which level the owner was
    aiming at — the exit-reason vocabulary is the owner's own and this package
    holds no members of it — so it names the level it measured against instead of
    inferring one. A reader who disagrees with the choice can see both numbers.
    """

    reference_label: str
    reference_price: Decimal
    exit_price: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.reference_label, str) or not self.reference_label:
            raise TypeError("reference_label must be a non-empty str")
        for name in ("reference_price", "exit_price"):
            object.__setattr__(self, name, _require_price(getattr(self, name), name))

    @property
    def difference(self) -> Decimal:
        """`exit − reference`. Signed, because the sign is the whole information."""
        return self.exit_price - self.reference_price

    @property
    def arithmetic(self) -> str:
        """The subtraction shown, not merely its result."""
        return (
            f"{canonical_decimal_text(self.exit_price)} − "
            f"{canonical_decimal_text(self.reference_price)}"
        )

    def as_money(self, quantity: Quantity, quote: AssetCode) -> Money:
        """The divergence over a filled quantity, in the quote asset."""
        if not isinstance(quantity, Quantity):
            raise TypeError(f"quantity must be a Quantity, got {type(quantity).__name__}")
        return quantity.value_at(self.difference, quote)


def nearest_planned_level(plan: TradePlan, price: Decimal) -> tuple[str, Decimal]:
    """The plan level closest to `price`, and the name it goes by.

    Ties resolve to the **stop**, deliberately. A price equidistant from the stop
    and a target is the one case where the choice matters most, and reporting the
    exit against the stop is the reading that cannot flatter the owner.
    """
    _require_plan(plan)
    wanted = _require_price(price, "price")
    best_label = "stop"
    best_price = plan.initial_invalidation
    best_gap = abs(wanted - best_price)
    for position, target in enumerate(plan.targets, start=1):
        gap = abs(wanted - target)
        if gap < best_gap:
            best_label = f"target {position}"
            best_price = target
            best_gap = gap
    return best_label, best_price


def exit_divergence(plan: TradePlan, exit_price: Decimal) -> ExitDivergence:
    """Where an exit landed against the nearest level the plan committed to.

    Always answerable: `initial_invalidation` is required, so every plan holds at
    least one level to measure against.
    """
    label, reference = nearest_planned_level(plan, exit_price)
    return ExitDivergence(
        reference_label=label,
        reference_price=reference,
        exit_price=Decimal(canonical_decimal_text(exit_price)),
    )
