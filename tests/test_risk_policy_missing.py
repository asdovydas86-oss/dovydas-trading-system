"""Missing inputs stay missing. **No zero, no default, no invented geometry.**

The failure this file exists to prevent is the one `AP` §14.3 names: *"a zero
makes the total look plausible and survives for years."* Every branch below
either produces a real figure or produces a stated absence carrying the reason —
never a blank, never a `None` a caller could read as nothing, and never a number
the engines did not produce.
"""

from __future__ import annotations

import pytest
from risk_policy_helpers import assessment, declaration

from fmis.money import Money, Quantity
from fmis.provenance import Absent
from fmis.risk_policy import PlanningStatus, TradeRiskPlan, plan_for, plans_for_results


def _plan(**kwargs):
    decl = kwargs.pop("decl", None) or declaration()
    return plan_for(assessment(**kwargs), declaration=decl)


# ---------------------------------------------------------------------------
# WAIT — the state of most of the watchlist
# ---------------------------------------------------------------------------


def test_a_symbol_with_no_direction_gets_no_trade_plan_and_no_figures() -> None:
    """§14's rule. A `WAIT` symbol shown with an entry, a stop and a size beside
    it reads as almost a trade, and it is not almost anything."""
    plan = _plan(direction=None, stop=None, targets=())
    assert plan.status is PlanningStatus.NO_TRADE_PLAN
    for name in (
        "entry",
        "invalidation",
        "risk_per_unit",
        "money_at_risk",
        "quantity",
        "notional",
    ):
        assert isinstance(getattr(plan, name), Absent), name


def test_no_trade_plan_names_nothing_as_missing() -> None:
    """Nothing *is* missing. The engine concluded there is no trade here, and
    reporting that as an unmet prerequisite would ask the owner to fix a
    correct answer."""
    plan = _plan(direction=None, stop=None, targets=())
    assert plan.missing == ()


def test_a_waiting_symbol_still_gets_a_plan_record_rather_than_being_dropped() -> None:
    """A symbol absent from the mapping renders as one nobody planned."""

    class _Result:
        def __init__(self, item: object) -> None:
            self.assessment = item
            self.requested_symbol = item.symbol

    plans = plans_for_results(
        [
            _Result(assessment("BTCUSDT")),
            _Result(assessment("ETHUSDT", direction=None, stop=None, targets=())),
        ],
        declaration=declaration(),
    )
    assert set(plans) == {"BTCUSDT", "ETHUSDT"}
    assert plans["ETHUSDT"].status is PlanningStatus.NO_TRADE_PLAN


# ---------------------------------------------------------------------------
# A directional candidate whose inputs are incomplete
# ---------------------------------------------------------------------------


def test_a_candidate_with_no_stop_is_not_evaluable_and_says_so() -> None:
    """No stop is no risk denominator. **No stop is invented** — not from ATR,
    not from a multiple, not from anything."""
    plan = _plan(stop=None, targets=())
    assert plan.status is PlanningStatus.NOT_EVALUABLE
    assert isinstance(plan.quantity, Absent)
    assert any("no stop level" in item for item in plan.missing)


def test_a_candidate_with_no_reference_price_is_not_evaluable() -> None:
    plan = _plan(reference_price=None, targets=())
    assert plan.status is PlanningStatus.NOT_EVALUABLE
    assert any("no reference price" in item for item in plan.missing)


def test_a_candidate_with_no_declared_fraction_is_not_evaluable() -> None:
    """Even a complete geometry produces no size when the owner declared no
    fraction — and the missing input is named, not filled in."""
    plan = _plan(decl=declaration(fraction=None))
    assert plan.status is PlanningStatus.NOT_EVALUABLE
    assert isinstance(plan.quantity, Absent)
    assert any("per_trade_fraction" in item for item in plan.missing)


def test_a_candidate_with_no_target_is_still_sized_and_has_no_reward_risk() -> None:
    """**No target is assumed.** Not 2R, not 3R, not anything: the reward:risk is
    unavailable and the size is unaffected, because reward never sized anything."""
    plan = _plan(targets=())
    assert plan.status is PlanningStatus.PLANNED
    assert isinstance(plan.reward_risk, Absent)
    assert plan.quantity.text == "0.025"


def test_a_not_evaluable_plan_always_names_at_least_one_missing_input() -> None:
    """Structural: `TradeRiskPlan` refuses the combination outright."""
    with pytest.raises(ValueError, match="names what is missing"):
        TradeRiskPlan(symbol="BTCUSDT", status=PlanningStatus.NOT_EVALUABLE)


# ---------------------------------------------------------------------------
# A quantity can never appear beside a status that did not produce one
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        PlanningStatus.NO_TRADE_PLAN,
        PlanningStatus.NOT_EVALUABLE,
        PlanningStatus.REFUSED,
    ],
)
def test_only_a_planned_status_may_carry_a_quantity(status: PlanningStatus) -> None:
    from fmis.money import AssetCode
    from decimal import Decimal

    with pytest.raises(ValueError, match="carries a quantity"):
        TradeRiskPlan(
            symbol="BTCUSDT",
            status=status,
            missing=("x",),
            reason="x",
            quantity=Quantity(Decimal("1"), AssetCode("BTC")),
        )


def test_a_planned_status_cannot_be_held_without_a_quantity() -> None:
    with pytest.raises(ValueError, match="carries a quantity"):
        TradeRiskPlan(symbol="BTCUSDT", status=PlanningStatus.PLANNED)


def test_a_refused_plan_states_the_reason_it_was_refused() -> None:
    with pytest.raises(ValueError, match="carries the reason"):
        TradeRiskPlan(symbol="BTCUSDT", status=PlanningStatus.REFUSED)


# ---------------------------------------------------------------------------
# Unknown portfolio risk is never zero
# ---------------------------------------------------------------------------


def test_portfolio_impact_is_always_a_stated_absence_and_never_a_number() -> None:
    """§21's invariant. A plan inside the per-trade ceiling is **not** thereby a
    plan the book has room for, and a page that printed zero open risk here
    would say exactly that."""
    plan = _plan()
    assert isinstance(plan.portfolio_impact, Absent)
    assert "not the same as their being zero" in plan.portfolio_impact.reason


def test_portfolio_impact_cannot_be_set_to_a_measured_looking_value() -> None:
    with pytest.raises(TypeError, match="portfolio_impact is an Absent"):
        TradeRiskPlan(
            symbol="BTCUSDT",
            status=PlanningStatus.NO_TRADE_PLAN,
            portfolio_impact=0,
        )


def test_no_figure_on_a_plan_is_ever_a_bare_zero() -> None:
    """Every absent money figure is an `Absent` carrying a reason — never
    `Money(0)`, never `None`, never an empty string."""
    plan = _plan(stop=None, targets=())
    for name in ("risk_per_unit", "money_at_risk", "notional"):
        value = getattr(plan, name)
        assert isinstance(value, Absent)
        assert value.reason.strip()
        assert not isinstance(value, Money)


@pytest.mark.parametrize(
    "name", ["money_at_risk", "notional", "quantity", "risk_fraction"]
)
def test_a_figure_the_sizer_could_not_produce_is_absent_not_zero(name: str) -> None:
    """**The path the no-stop case does not reach.**

    A candidate with no stop never reaches the sizer at all — `plan_for` returns
    before it — so the test above proves nothing about what happens to a figure
    the sizer *ran* and could not produce. This is that case: complete geometry,
    no declared fraction, so the arithmetic is attempted and yields nothing.

    A targeted mutation that replaced the absent `money_at_risk` with
    `Money(0, quote)` survived the suite until this test existed. A zero here is
    the exact failure `AP` §14.3 names — it makes the total look plausible and
    survives for years.
    """
    plan = _plan(decl=declaration(fraction=None))
    value = getattr(plan, name)
    assert isinstance(value, Absent), f"{name} was {value!r}"
    assert value.reason.strip()
    assert not isinstance(value, (Money, Quantity))
    assert getattr(value, "amount", None) is None


# ---------------------------------------------------------------------------
# Equity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("equity", ["0", "-1", "-10000"])
def test_a_non_positive_declared_capital_is_refused_at_declaration(equity: str) -> None:
    from fmis.risk_policy import RiskPolicyError

    with pytest.raises(RiskPolicyError, match="sizes nothing"):
        declaration(equity=equity)


def test_equity_in_the_wrong_asset_refuses_rather_than_converting() -> None:
    """A conversion needs a dated rate with its own provenance. Silently
    treating BTC-denominated capital as USDT would size a trade off a number
    a hundred thousand times too small."""
    from decimal import Decimal

    from fmis.money import AssetCode, Money
    from fmis.risk_policy import RiskPolicyDeclaration
    from risk_policy_helpers import MOMENT

    decl = RiskPolicyDeclaration(
        equity=Money(Decimal("1"), AssetCode("BTC")),
        declared_at=MOMENT,
        per_trade_fraction=Decimal("0.005"),
    )
    plan = plan_for(assessment(), declaration=decl)
    assert isinstance(plan.quantity, Absent)
    assert plan.status is not PlanningStatus.PLANNED


def test_plans_are_keyed_on_the_symbol_the_consumer_looks_them_up_by() -> None:
    """A decision record is filed under the **assessment's** symbol, and the
    projection looks a plan up by that same name.

    `plans_for_results` reads a scan result, which carries *both* the symbol that
    was requested and the symbol the engine concluded about. Keying the mapping
    on the request would produce a dict whose every lookup missed for any symbol
    where the two differ — silently, with the page simply showing no planning
    section and no reason. Asserted with the two names deliberately different.
    """

    class _Result:
        def __init__(self, item: object, requested: str) -> None:
            self.assessment = item
            self.requested_symbol = requested

    plans = plans_for_results(
        [_Result(assessment("BTCUSDT"), requested="btcusdt")],
        declaration=declaration(),
    )
    assert set(plans) == {"BTCUSDT"}
    assert plans["BTCUSDT"].symbol == "BTCUSDT"


def test_a_symbol_answered_twice_produces_one_plan_and_it_is_the_first() -> None:
    """`symbol_decisions` keeps the first of two records for one symbol. The plan
    mapping keeps the first too, so the decision and its plan cannot describe two
    different readings of the same market."""

    class _Result:
        def __init__(self, item: object) -> None:
            self.assessment = item
            self.requested_symbol = item.symbol

    first = assessment("BTCUSDT", stop=58000.0)
    second = assessment("BTCUSDT", stop=55000.0)
    plans = plans_for_results(
        [_Result(first), _Result(second)], declaration=declaration()
    )
    assert set(plans) == {"BTCUSDT"}
    # 10000 x 0.005 = 50 at risk; 60000 - 58000 = 2000 per unit -> 0.025.
    # The second result's wider stop would have given 0.01.
    assert plans["BTCUSDT"].quantity.text == "0.025"
