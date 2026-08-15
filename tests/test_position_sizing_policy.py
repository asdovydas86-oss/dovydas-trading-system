"""`SizingPolicy` and the three-step fraction resolution.

The most important assertion in this file is a negative one: **with no fraction
stated and no default below the ceiling, no fraction is resolved.** The ceiling
is not used as a target, because the specification calls it *"a hard ceiling, not
a default target"* and a system that sized at it would have converted one into
the other with nobody deciding to.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from persistence_helpers import risk_limit
from position_sizing_helpers import budget_with, ceiling, policy, total_risk_limit
from trade_domain_helpers import USDT

from fmis.money import Money
from fmis.position_sizing import (
    SIZING_POLICY_VERSION,
    FractionChoice,
    SizingPolicy,
    per_trade_ceiling,
)
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError
from fmis.risk import LimitScope, LimitUnit


# ==========================================================================
# 1. The policy object itself
# ==========================================================================


def test_a_policy_states_nothing_it_was_not_configured_with() -> None:
    """Every field is `Absent(reason)` by default, and the reason names the gap."""
    bare = policy()
    for value in (
        bare.risk_fraction,
        bare.max_equity_age,
        bare.max_mark_age,
        bare.minimum_risk_reward,
    ):
        assert isinstance(value, Absent)
        assert value.reason


def test_a_policy_is_asserted_because_it_is_the_owners_own() -> None:
    assert policy().origin is ValueOrigin.ASSERTED
    assert policy().version == SIZING_POLICY_VERSION


def test_the_percent_convention_is_read_from_the_portfolio_engine() -> None:
    """One convention, one definition — two readings of `0.02` would be fatal."""
    from fmis.portfolio_risk import PERCENT_UNIT_CONVENTION

    assert policy().percent_unit_convention == PERCENT_UNIT_CONVENTION


def test_the_policy_id_must_be_an_identifier() -> None:
    with pytest.raises(DomainValidationError):
        SizingPolicy(policy_id="not an identifier!")


@pytest.mark.parametrize("field", ["risk_fraction", "minimum_risk_reward"])
def test_a_stated_ratio_must_be_a_positive_decimal(field: str) -> None:
    with pytest.raises(TypeError):
        policy(**{field: 0.01})
    with pytest.raises(DomainValidationError, match="refusal to trade"):
        policy(**{field: Decimal("0")})


def test_a_stated_ratio_is_canonicalized() -> None:
    assert policy(risk_fraction=Decimal("0.0100")).risk_fraction == Decimal("0.01")


@pytest.mark.parametrize("field", ["max_equity_age", "max_mark_age"])
def test_a_staleness_bound_must_be_a_positive_duration(field: str) -> None:
    with pytest.raises(TypeError):
        policy(**{field: "36h"})
    with pytest.raises(DomainValidationError, match="positive duration"):
        policy(**{field: timedelta()})
    assert policy(**{field: timedelta(hours=36)})


def test_a_policy_exports_its_bounds_and_its_convention() -> None:
    payload = policy(
        risk_fraction=Decimal("0.01"), max_mark_age=timedelta(hours=36)
    ).to_payload()
    assert payload["risk_fraction"] == {"value": "0.01"}
    assert payload["max_mark_age"] == {"value": "1 day, 12:00:00"}
    assert payload["max_equity_age"]["absent"]
    assert payload["minimum_risk_reward"]["absent"]
    assert "fraction" in payload["percent_unit_convention"]


# ==========================================================================
# 2. Finding the ceiling
# ==========================================================================


def test_the_ceiling_is_the_one_per_trade_limit_stated_as_a_fraction() -> None:
    found = per_trade_ceiling(budget_with(ceiling("0.02")))
    assert found.value == Decimal("0.02")


def test_a_budget_with_no_such_ceiling_says_so_as_a_policy_gap() -> None:
    absent = per_trade_ceiling(budget_with(total_risk_limit(Money(Decimal("6000"), USDT))))
    assert isinstance(absent, Absent)
    assert "gap in the owner's own policy" in absent.reason


def test_two_ceilings_are_a_contradiction_and_neither_is_chosen() -> None:
    """Picking one would resolve a contradiction in the owner's policy silently."""
    second = risk_limit(
        "second_ceiling", value=Decimal("0.03"), scope=LimitScope.PER_TRADE_RISK
    )
    absent = per_trade_ceiling(budget_with(ceiling("0.02"), second))
    assert isinstance(absent, Absent)
    assert "per_trade_risk, second_ceiling" in absent.reason


def test_a_money_per_trade_limit_is_not_this_ceiling() -> None:
    """A money cap is measured by the constraint engine; sizing needs a fraction."""
    money_cap = risk_limit(
        "per_trade_money",
        value=Money(Decimal("2000"), USDT),
        unit=LimitUnit.MONEY,
        scope=LimitScope.PER_TRADE_RISK,
    )
    assert isinstance(per_trade_ceiling(budget_with(money_cap)), Absent)


def test_the_ceiling_lookup_type_checks_its_argument() -> None:
    with pytest.raises(TypeError, match="RiskBudget"):
        per_trade_ceiling("swing_budget")  # type: ignore[arg-type]


# ==========================================================================
# 3. Resolving the fraction — the three steps, in order
# ==========================================================================


def test_the_owners_stated_fraction_wins_and_names_itself() -> None:
    choice = policy(risk_fraction=Decimal("0.005")).fraction_for(
        budget_with(ceiling("0.02"))
    )
    assert choice.fraction == Decimal("0.005")
    assert "the owner stated for this trade" in choice.basis
    assert not choice.capped


def test_with_no_stated_fraction_the_default_below_the_ceiling_is_used() -> None:
    choice = policy().fraction_for(budget_with(ceiling("0.02", default="0.01")))
    assert choice.fraction == Decimal("0.01")
    assert "default 0.01 the owner set below their ceiling" in choice.basis


def test_with_neither_there_is_no_fraction_and_the_ceiling_is_not_a_target() -> None:
    """The negative assertion this whole module exists for."""
    choice = policy().fraction_for(budget_with(ceiling("0.02", default=None)))
    assert isinstance(choice.fraction, Absent)
    assert "ceiling is a ceiling and not a target" in choice.fraction.reason
    assert choice.ceiling == Decimal("0.02")


def test_with_no_ceiling_at_all_and_no_stated_fraction_there_is_none() -> None:
    choice = policy().fraction_for(
        budget_with(total_risk_limit(Money(Decimal("6000"), USDT)))
    )
    assert isinstance(choice.fraction, Absent)
    assert "no per-trade ceiling carries a default below it" in choice.fraction.reason
    assert isinstance(choice.ceiling, Absent)


def test_a_stated_fraction_survives_a_budget_with_no_ceiling() -> None:
    """An unbounded policy still sizes; the coverage gap is reported elsewhere."""
    choice = policy(risk_fraction=Decimal("0.01")).fraction_for(
        budget_with(total_risk_limit(Money(Decimal("6000"), USDT)))
    )
    assert choice.fraction == Decimal("0.01")
    assert isinstance(choice.ceiling, Absent)
    assert not choice.capped


def test_a_fraction_above_the_ceiling_is_reduced_to_it_and_the_ceiling_is_named() -> None:
    choice = policy(risk_fraction=Decimal("0.05")).fraction_for(
        budget_with(ceiling("0.02"))
    )
    assert choice.fraction == Decimal("0.02")
    assert choice.capped
    assert "reduced to the ceiling 0.02" in choice.basis
    assert "'per_trade_risk'" in choice.basis


def test_a_fraction_exactly_at_the_ceiling_is_not_reported_as_capped() -> None:
    """A stated maximum is not breached by touching it."""
    choice = policy(risk_fraction=Decimal("0.02")).fraction_for(
        budget_with(ceiling("0.02"))
    )
    assert choice.fraction == Decimal("0.02")
    assert not choice.capped


# ==========================================================================
# 4. FractionChoice
# ==========================================================================


def test_a_choice_cannot_claim_a_cap_without_naming_the_ceiling() -> None:
    with pytest.raises(DomainValidationError, match="ceiling that is not"):
        FractionChoice(fraction=Decimal("0.01"), basis="somewhere", capped=True)


def test_a_choice_is_asserted_and_canonicalizes_its_numbers() -> None:
    choice = FractionChoice(fraction=Decimal("0.0100"), basis="stated")
    assert choice.origin is ValueOrigin.ASSERTED
    assert choice.fraction == Decimal("0.01")


@pytest.mark.parametrize("field", ["fraction", "ceiling"])
def test_a_choice_refuses_a_non_positive_or_non_decimal_value(field: str) -> None:
    values = {"fraction": Decimal("0.01"), "basis": "stated"}
    values[field] = 0.01  # type: ignore[assignment]
    with pytest.raises(TypeError):
        FractionChoice(**values)  # type: ignore[arg-type]
    values[field] = Decimal("0")  # type: ignore[assignment]
    with pytest.raises(DomainValidationError, match="must be positive"):
        FractionChoice(**values)  # type: ignore[arg-type]


def test_a_choice_requires_a_basis() -> None:
    with pytest.raises(Exception):
        FractionChoice(fraction=Decimal("0.01"), basis="")


def test_the_capped_flag_is_a_bool() -> None:
    with pytest.raises(TypeError, match="capped"):
        FractionChoice(
            fraction=Decimal("0.01"),
            basis="stated",
            ceiling=Decimal("0.02"),
            capped="yes",  # type: ignore[arg-type]
        )
