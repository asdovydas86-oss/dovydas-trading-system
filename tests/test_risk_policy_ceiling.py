"""The 2 % ceiling. **Structural, exact, and never a default.**

`SPEC` §8.1 — *"A maximum of 2% portfolio risk per trade is a hard ceiling, not
a default target."* Three separate claims, tested separately:

1. **`> 2 %` cannot be represented.** Not refused by a surface, not refused by a
   caller who remembered to check — refused in `__post_init__`, so no object
   exists for any layer to render.
2. **The comparison is exact.** `2.0000000001 %` is above and
   `1.9999999999 %` is below, and neither answer comes from float rounding.
3. **The ceiling is never used as a value.** No code path substitutes it for a
   fraction the owner did not state.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from risk_policy_helpers import MOMENT, declaration, usdt

from fmis.provenance import Absent
from fmis.risk_policy import (
    SPECIFICATION_PER_TRADE_CEILING,
    RiskPolicyDeclaration,
    RiskPolicyError,
    budget_from,
    sizing_policy_from,
)


def test_the_ceiling_is_two_percent_exactly_and_is_a_decimal() -> None:
    """Hand-written, not derived. `0.02` as a float is `0.0200000000000000004…`,
    and a ceiling compared against that decides a capital-preservation limit by
    representation error."""
    assert SPECIFICATION_PER_TRADE_CEILING == Decimal("0.02")
    assert isinstance(SPECIFICATION_PER_TRADE_CEILING, Decimal)


@pytest.mark.parametrize(
    "fraction",
    ["0.0001", "0.0025", "0.005", "0.0075", "0.01", "0.019999999999", "0.02"],
)
def test_a_fraction_at_or_below_the_ceiling_is_accepted(fraction: str) -> None:
    """`<= 2 %` is inside a *maximum*. The exact ceiling is included: the
    specification says maximum, and no accepted decision says otherwise."""
    declared = declaration(fraction=fraction)
    assert declared.per_trade_fraction == Decimal(fraction)


@pytest.mark.parametrize(
    "fraction",
    ["0.020000000001", "0.0201", "0.021", "0.03", "0.05", "0.1", "1", "2"],
)
def test_a_fraction_above_the_ceiling_cannot_be_constructed(fraction: str) -> None:
    """Above the ceiling there is no object — not a warning, not a capped value."""
    with pytest.raises(RiskPolicyError, match="exceeds the hard ceiling"):
        declaration(fraction=fraction)


def test_the_boundary_is_exact_on_both_sides() -> None:
    """The pair that a float comparison would get wrong, asserted together."""
    assert declaration(fraction="0.019999999999").per_trade_fraction < Decimal("0.02")
    with pytest.raises(RiskPolicyError):
        declaration(fraction="0.020000000001")


def test_a_float_fraction_is_refused_rather_than_converted() -> None:
    """`0.02` as a float is *above* `Decimal('0.02')`. Accepting one would make
    the ceiling's own value fail its own check, or pass it, depending on the
    caller's literal — so a float never enters."""
    with pytest.raises(TypeError, match="Decimal or Absent"):
        RiskPolicyDeclaration(
            equity=usdt("10000"), declared_at=MOMENT, per_trade_fraction=0.02
        )


@pytest.mark.parametrize("fraction", ["0", "-0.001", "-1"])
def test_a_non_positive_fraction_is_refused(fraction: str) -> None:
    with pytest.raises(RiskPolicyError, match="must be positive"):
        declaration(fraction=fraction)


def test_a_non_finite_fraction_is_refused() -> None:
    """No NaN and no Infinity reaches a money contract."""
    for value in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(RiskPolicyError):
            RiskPolicyDeclaration(
                equity=usdt("10000"),
                declared_at=MOMENT,
                per_trade_fraction=Decimal(value),
            )


# ---------------------------------------------------------------------------
# The ceiling is not a default
# ---------------------------------------------------------------------------


def test_a_declaration_with_no_fraction_states_an_absence_not_the_ceiling() -> None:
    declared = declaration(fraction=None)
    assert isinstance(declared.per_trade_fraction, Absent)
    assert declared.states_a_fraction is False
    assert declared.per_trade_fraction.reason != str(SPECIFICATION_PER_TRADE_CEILING)


def test_the_budget_carries_the_ceiling_with_no_default_below_it() -> None:
    """`RiskLimit.default_below_ceiling` is the field a system would default
    from. It stays `Absent`, so `SizingPolicy.fraction_for`'s source 2 is empty
    and there is nothing to fall back to."""
    budget = budget_from(declaration(fraction=None))
    (limit,) = budget.limits
    assert limit.value == SPECIFICATION_PER_TRADE_CEILING
    assert isinstance(limit.default_below_ceiling, Absent)
    assert limit.is_ceiling is False


def test_no_fraction_declared_resolves_to_no_fraction_at_all() -> None:
    """The whole point. A system that sized at the ceiling by default would have
    turned the specification's ceiling into its target with nobody deciding to."""
    declared = declaration(fraction=None)
    choice = sizing_policy_from(declared).fraction_for(budget_from(declared))
    assert isinstance(choice.fraction, Absent)
    assert choice.fraction != SPECIFICATION_PER_TRADE_CEILING


def test_a_declared_fraction_is_used_unchanged_and_is_not_raised_to_the_ceiling() -> None:
    declared = declaration(fraction="0.0025")
    choice = sizing_policy_from(declared).fraction_for(budget_from(declared))
    assert choice.fraction == Decimal("0.0025")
    assert choice.capped is False
    assert choice.ceiling == SPECIFICATION_PER_TRADE_CEILING
