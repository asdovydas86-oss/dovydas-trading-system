"""Builders for sizing and approval fixtures.

Extends `tests/trade_domain_helpers.py`, `tests/persistence_helpers.py` and
`tests/portfolio_risk_helpers.py` rather than duplicating any of them: the
market, the account, the assets, the exposure line, the portfolio state and the
risk-budget builders are all already defined there, and a second definition of
*"a valid limit"* would drift from the first.

**Every threshold is passed in by the test that cares about it.** There is no
default risk fraction here, because there is none in the product: a fixture that
supplied one would let a test pass against a number the production path refuses
to invent.

**No clock and no network.** Every instant is `AT(...)`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from persistence_helpers import risk_budget, risk_limit
from portfolio_risk_helpers import line, no_groups, owner, state
from trade_domain_helpers import ACCOUNT, MARKET

from fmis.accounts import Book
from fmis.position_sizing import (
    ApprovalEngine,
    PositionProposal,
    PositionSizer,
    SizingPolicy,
    engine_for,
)
from fmis.risk import LimitScope, LimitSeverity, LimitUnit
from fmis.snapshotting import TradeDirection

__all__ = [
    "owner",
    "line",
    "state",
    "no_groups",
    "proposal",
    "policy",
    "sizer",
    "engine",
    "budget_with",
    "ceiling",
    "total_risk_limit",
    "concentration_limit",
    "cluster_limit",
    "evaluate",
]


def proposal(**overrides: Any) -> PositionProposal:
    """A candidate at 60 000 with a 58 400 stop and a 64 000 target.

    A risk distance of 1 600 and a reward distance of 4 000 — the same geometry
    `portfolio_risk_helpers.proposal` uses, so a figure computed here and one
    computed there are comparable by inspection.
    """
    values: dict[str, Any] = {
        "account": ACCOUNT,
        "market": MARKET,
        "book": Book.SWING,
        "direction": TradeDirection.LONG,
        "entry": Decimal("60000"),
        "stop": Decimal("58400"),
        "targets": (Decimal("64000"),),
    }
    values.update(overrides)
    return PositionProposal(**values)


def policy(**overrides: Any) -> SizingPolicy:
    """A policy that states **nothing** unless the test states it.

    The honest default, and the same one the product ships: every bound is
    `Absent` until the owner configures it.
    """
    values: dict[str, Any] = {"policy_id": "owner_sizing"}
    values.update(overrides)
    return SizingPolicy(**values)


def sizer(**overrides: Any) -> PositionSizer:
    return PositionSizer(policy(**overrides))


def engine(classification: Any = None, **overrides: Any) -> ApprovalEngine:
    return engine_for(
        policy(**overrides), no_groups() if classification is None else classification
    )


def ceiling(value: str = "0.02", default: str | None = "0.01", **overrides: Any) -> Any:
    """A per-trade risk ceiling as a fraction of equity, hard by default.

    The stated default *below* the ceiling is `0.01` rather than absent, because
    that is the shape the specification describes — *"2 % is a hard ceiling, not
    a default target"* — and a fixture whose ceiling doubled as its target would
    make every sizing test agree with a rule the product refuses.
    """
    values: dict[str, Any] = {"value": Decimal(value)}
    if default is not None:
        values["default_below_ceiling"] = Decimal(default)
    values.update(overrides)
    return risk_limit("per_trade_risk", **values)


def total_risk_limit(value: Any, **overrides: Any) -> Any:
    """A total-open-risk limit. Money or a fraction, whichever the test needs."""
    values: dict[str, Any] = {
        "scope": LimitScope.TOTAL_OPEN_RISK,
        "value": value,
        "unit": (
            LimitUnit.MONEY if not isinstance(value, Decimal) else LimitUnit.PERCENT_OF_EQUITY
        ),
        "severity": LimitSeverity.HARD_BLOCK,
    }
    values.update(overrides)
    return risk_limit("total_open_risk", **values)


def concentration_limit(key: str, value: Decimal, **overrides: Any) -> Any:
    """A concentration limit keyed `{axis}:{value}`, as a share of gross exposure."""
    values: dict[str, Any] = {
        "scope": LimitScope.CONCENTRATION,
        "value": value,
        "unit": LimitUnit.RATIO,
        "key": key,
        "severity": LimitSeverity.HARD_BLOCK,
    }
    values.update(overrides)
    return risk_limit(key.replace(":", "_").replace("-", "_").lower(), **values)


def cluster_limit(group: str, value: Decimal, **overrides: Any) -> Any:
    values: dict[str, Any] = {
        "scope": LimitScope.CLUSTER_EXPOSURE,
        "value": value,
        "unit": LimitUnit.RATIO,
        "key": group,
        "severity": LimitSeverity.HARD_BLOCK,
    }
    values.update(overrides)
    return risk_limit(f"cluster_{group}", **values)


def budget_with(*limits: Any, **overrides: Any) -> Any:
    """A budget over the supplied limits, or over one hard 2 % ceiling."""
    return risk_budget(limits=limits or (ceiling(),), **overrides)


def evaluate(
    candidate: PositionProposal | None = None,
    *,
    portfolio: Any = None,
    budget: Any = None,
    approval_engine: ApprovalEngine | None = None,
    **kwargs: Any,
) -> Any:
    """Run one approval with everything defaulted to the simplest valid case.

    The default portfolio holds **one marked, stopped position** rather than
    nothing, so `open_risk_before` is a real number and the before/after
    comparison is exercised on every call rather than only in the tests that
    remember to set one up.
    """
    return (engine() if approval_engine is None else approval_engine).evaluate(
        proposal() if candidate is None else candidate,
        state=state(line()) if portfolio is None else portfolio,
        budget=budget_with() if budget is None else budget,
        owner=owner(),
        **kwargs,
    )
