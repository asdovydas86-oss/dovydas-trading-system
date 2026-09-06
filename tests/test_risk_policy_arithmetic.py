"""The arithmetic, against independently hand-calculated vectors.

**Every expected value below was calculated by hand and is written as a
literal.** Not one is produced by calling the code under test, by re-deriving it
with the same formula in the test, or by rounding whatever came back. A test
that computes its own expectation with the implementation's own arithmetic
asserts only that the code is self-consistent.

The relation being checked, stated once:

    risk amount   = equity × fraction
    risk per unit = |entry − invalidation|      (signed by direction, never abs())
    quantity      = risk amount ÷ risk per unit
    notional      = quantity × entry
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from risk_policy_helpers import assessment, declaration

from fmis.provenance import Absent
from fmis.risk_policy import PlanningStatus, plan_for


def _plan(**kwargs):
    decl = kwargs.pop("decl", None) or declaration()
    return plan_for(assessment(**kwargs), declaration=decl)


# ---------------------------------------------------------------------------
# Vector A — the worked example, long
#
#   equity 10,000 USDT · fraction 0.005 · entry 60,000 · stop 58,000
#   risk amount   = 10000 × 0.005 = 50 USDT
#   risk per unit = 60000 − 58000 = 2000 USDT per BTC
#   quantity      = 50 ÷ 2000     = 0.025 BTC
#   notional      = 0.025 × 60000 = 1500 USDT
#   reward        = 66000 − 60000 = 6000 ; reward:risk = 6000 ÷ 2000 = 3
# ---------------------------------------------------------------------------


def test_vector_a_long() -> None:
    plan = _plan()
    assert plan.status is PlanningStatus.PLANNED
    assert plan.money_at_risk.text == "50"
    assert plan.money_at_risk.asset.code == "USDT"
    assert plan.risk_per_unit.text == "2000"
    assert plan.quantity.text == "0.025"
    assert plan.quantity.asset.code == "BTC"
    assert plan.notional.text == "1500"
    assert plan.reward_risk.startswith("3 (")


# ---------------------------------------------------------------------------
# Vector B — a wider stop, same capital and fraction
#
#   entry 60,000 · stop 55,000
#   risk per unit = 5000 ; quantity = 50 ÷ 5000 = 0.01 BTC
#   notional      = 0.01 × 60000 = 600 USDT
# ---------------------------------------------------------------------------


def test_vector_b_wider_stop_buys_less() -> None:
    plan = _plan(stop=55000.0, targets=())
    assert plan.money_at_risk.text == "50"
    assert plan.risk_per_unit.text == "5000"
    assert plan.quantity.text == "0.01"
    assert plan.notional.text == "600"


# ---------------------------------------------------------------------------
# Vector C — short geometry
#
#   entry 180 · stop 190  (stop ABOVE entry on a short)
#   risk per unit = 190 − 180 = 10 USDT per SOL
#   quantity      = 50 ÷ 10   = 5 SOL
#   notional      = 5 × 180   = 900 USDT
# ---------------------------------------------------------------------------


def test_vector_c_short() -> None:
    plan = _plan(
        symbol="SOLUSDT",
        direction="short",
        reference_price=180.0,
        stop=190.0,
        targets=(150.0,),
    )
    assert plan.status is PlanningStatus.PLANNED
    assert plan.risk_per_unit.text == "10"
    assert plan.quantity.text == "5"
    assert plan.quantity.asset.code == "SOL"
    assert plan.notional.text == "900"


# ---------------------------------------------------------------------------
# Vector D — the exact ceiling as the declared fraction
#
#   equity 10,000 · fraction 0.02 -> risk amount = 200 USDT
#   risk per unit 2000 -> quantity = 200 ÷ 2000 = 0.1 BTC
# ---------------------------------------------------------------------------


def test_vector_d_at_the_exact_ceiling() -> None:
    plan = _plan(decl=declaration(fraction="0.02"))
    assert plan.money_at_risk.text == "200"
    assert plan.quantity.text == "0.1"
    assert plan.risk_fraction == Decimal("0.02")


# ---------------------------------------------------------------------------
# Vector E — a very small price and a very small quantity
#
#   equity 500 USDT · fraction 0.01 -> risk amount = 5 USDT
#   entry 0.00004 · stop 0.00003 -> risk per unit = 0.00001
#   quantity = 5 ÷ 0.00001 = 500000 SHIB
#   notional = 500000 × 0.00004 = 20 USDT
# ---------------------------------------------------------------------------


def test_vector_e_small_prices() -> None:
    plan = _plan(
        symbol="SHIBUSDT",
        reference_price=0.00004,
        stop=0.00003,
        targets=(),
        decl=declaration(equity="500", fraction="0.01"),
    )
    assert plan.money_at_risk.text == "5"
    assert plan.risk_per_unit.text == "0.00001"
    assert plan.quantity.text == "500000"
    assert plan.notional.text == "20"


# ---------------------------------------------------------------------------
# Vector F — a high-priced instrument and a fractional quantity
#
#   equity 250000 USDT · fraction 0.002 -> risk amount = 500 USDT
#   entry 96000 · stop 92000 -> risk per unit = 4000
#   quantity = 500 ÷ 4000 = 0.125 BTC ; notional = 0.125 × 96000 = 12000
# ---------------------------------------------------------------------------


def test_vector_f_large_capital_high_price() -> None:
    plan = _plan(
        reference_price=96000.0,
        stop=92000.0,
        targets=(),
        decl=declaration(equity="250000", fraction="0.002"),
    )
    assert plan.money_at_risk.text == "500"
    assert plan.quantity.text == "0.125"
    assert plan.notional.text == "12000"


# ---------------------------------------------------------------------------
# Directional geometry is signed, never absolute-valued
# ---------------------------------------------------------------------------


def test_a_long_whose_stop_is_above_the_entry_is_refused_not_absolute_valued() -> None:
    """`abs()` over the distance would report a transposed stop as a risk figure
    — the failure that makes the largest position look like the smallest."""
    plan = _plan(reference_price=58000.0, stop=60000.0, targets=())
    assert plan.status is PlanningStatus.REFUSED
    assert isinstance(plan.quantity, Absent)
    assert "not below the entry" in plan.reason


def test_a_short_whose_stop_is_below_the_entry_is_refused() -> None:
    plan = _plan(direction="short", reference_price=60000.0, stop=58000.0, targets=())
    assert plan.status is PlanningStatus.REFUSED
    assert isinstance(plan.quantity, Absent)


def test_a_stop_equal_to_the_entry_never_yields_an_infinite_quantity() -> None:
    """A zero denominator. The answer is a refusal, not a very large number."""
    plan = _plan(reference_price=60000.0, stop=60000.0, targets=())
    assert plan.status is PlanningStatus.REFUSED
    assert isinstance(plan.quantity, Absent)


# ---------------------------------------------------------------------------
# Properties. Each is a relation, checked over hand-chosen pairs.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("smaller,larger", [("0.0025", "0.005"), ("0.005", "0.01")])
def test_a_smaller_fraction_never_produces_a_larger_risk_amount(
    smaller: str, larger: str
) -> None:
    low = _plan(decl=declaration(fraction=smaller)).money_at_risk
    high = _plan(decl=declaration(fraction=larger)).money_at_risk
    assert low.amount < high.amount


@pytest.mark.parametrize("near,far", [(58000.0, 55000.0), (55000.0, 50000.0)])
def test_a_wider_stop_never_produces_a_larger_quantity(near: float, far: float) -> None:
    tight = _plan(stop=near, targets=()).quantity
    wide = _plan(stop=far, targets=()).quantity
    assert wide.amount < tight.amount


def test_the_risk_amount_never_exceeds_the_declared_fraction_of_equity() -> None:
    """The invariant the whole package exists for, over every accepted fraction."""
    for fraction in ("0.0001", "0.001", "0.005", "0.01", "0.02"):
        decl = declaration(fraction=fraction)
        plan = _plan(decl=decl)
        assert plan.money_at_risk.amount <= decl.equity.amount * Decimal(fraction)


def test_the_same_inputs_produce_the_same_result_every_time() -> None:
    """No clock, no randomness, no store. Determinism, asserted rather than hoped."""
    first = _plan()
    second = _plan()
    assert first == second


def test_evaluation_does_not_mutate_the_declaration() -> None:
    decl = declaration()
    before = decl.to_payload()
    _plan(decl=decl)
    _plan(decl=decl)
    assert decl.to_payload() == before
