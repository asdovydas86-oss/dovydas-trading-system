"""The constraint engine: every scope, every boundary, and every refusal.

**The boundary tests are the point.** For each comparable scope there is a triple
— one unit below the limit, exactly at it, and one unit above — because `>` and
`>=` are the same code until a value lands exactly on the line, and the 2 %
ceiling is precisely the value an owner sizes to.

**The floor test is the second point.** `MIN_RESERVE` is the one limit where
*below* is the breach. Routing it through a ceiling comparison reports an account
with no reserve left as comfortably within its reserve limit.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from persistence_helpers import risk_budget, risk_limit
from portfolio_risk_helpers import (
    ETH,
    ETH_MARKET,
    EVEDEX_MARKET,
    SECOND_ACCOUNT,
    btc,
    groups,
    line,
    mark,
    owner,
    state,
    usdt,
)
from trade_domain_helpers import ACCOUNT, AT, BTC, MARKET, USDT

from fmis.accounts import Book
from fmis.money import Money, Quantity
from fmis.portfolio_risk import (
    CONSTRAINT_POLICY_VERSION,
    PERCENT_UNIT_CONVENTION,
    ConstraintResult,
    PortfolioConstraintCheck,
    evaluate_constraints,
    remaining_risk_capacity,
)
from fmis.positions import PositionDirection
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError
from fmis.risk import (
    LimitPeriod,
    LimitScope,
    LimitSeverity,
    LimitStatus,
    LimitUnit,
)

OWNER = owner()


def check(*limits: object, **state_kwargs: object) -> PortfolioConstraintCheck:
    """Evaluate a budget of the supplied limits against a state."""
    budget = risk_budget(limits=tuple(limits))
    lines = state_kwargs.pop("lines", ())
    candidate = state_kwargs.pop("candidate_risk", None)
    return evaluate_constraints(
        budget,
        state(*lines, **state_kwargs),  # type: ignore[arg-type]
        owner=OWNER,
        candidate_risk=candidate,  # type: ignore[arg-type]
    )


def status_of(*limits: object, **state_kwargs: object) -> object:
    result = check(*limits, **state_kwargs)
    return result.results[0].status


# -- per-trade risk: the 2 % ceiling ----------------------------------------

PER_TRADE = risk_limit(
    "per_trade", scope=LimitScope.PER_TRADE_RISK, value=Decimal("0.02"),
    unit=LimitUnit.PERCENT_OF_EQUITY,
)


def test_a_candidate_one_unit_below_the_two_percent_ceiling_is_within() -> None:
    assert (
        status_of(PER_TRADE, candidate_risk=usdt("1999"), equity=usdt("100000"))
        is LimitStatus.WITHIN
    )


def test_a_candidate_exactly_at_the_two_percent_ceiling_is_at_limit() -> None:
    """The boundary that separates `>` from `>=`. Exactly 2 % is *reached*, not
    breached — and it is reported as reached rather than as comfortable."""
    assert (
        status_of(PER_TRADE, candidate_risk=usdt("2000"), equity=usdt("100000"))
        is LimitStatus.AT_LIMIT
    )


def test_a_candidate_one_unit_above_the_two_percent_ceiling_is_exceeded() -> None:
    assert (
        status_of(PER_TRADE, candidate_risk=usdt("2001"), equity=usdt("100000"))
        is LimitStatus.EXCEEDED
    )


def test_the_ceiling_is_never_treated_as_a_target() -> None:
    """A limit with a stated default below it keeps both numbers: the ceiling is
    what is compared against, and the default is not silently promoted to it."""
    ceiling = risk_limit(
        "per_trade",
        scope=LimitScope.PER_TRADE_RISK,
        value=Decimal("0.02"),
        unit=LimitUnit.PERCENT_OF_EQUITY,
        default_below_ceiling=Decimal("0.01"),
    )
    assert ceiling.is_ceiling
    result = check(ceiling, candidate_risk=usdt("1500"), equity=usdt("100000"))
    assert result.results[0].limit_value == Decimal("0.02")
    assert result.results[0].status is LimitStatus.WITHIN


def test_without_a_candidate_per_trade_risk_measures_the_largest_position() -> None:
    """*"Is any position already over my ceiling"* is answered by the largest."""
    result = check(
        PER_TRADE,
        lines=(line(), line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), entry=Decimal("3000"), stop=Decimal("500"), mark=mark("3000"))),
        equity=usdt("100000"),
    )
    assert result.results[0].current_value == Decimal("0.025")  # 2500 / 100000
    assert result.results[0].status is LimitStatus.EXCEEDED


def test_the_largest_position_cannot_be_identified_if_one_is_unmeasurable() -> None:
    """The unmeasurable one might be the largest, so the answer is absent."""
    result = check(
        PER_TRADE,
        lines=(line(), line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), stop=Absent("no plan"))),
        equity=usdt("100000"),
    )
    assert isinstance(result.results[0].status, Absent)


def test_per_trade_risk_in_money_compares_money_directly() -> None:
    limit = risk_limit(
        "per_trade_money",
        scope=LimitScope.PER_TRADE_RISK,
        value=usdt("2000"),
        unit=LimitUnit.MONEY,
    )
    assert status_of(limit, candidate_risk=usdt("2001")) is LimitStatus.EXCEEDED
    assert status_of(limit, candidate_risk=usdt("2000")) is LimitStatus.AT_LIMIT
    assert status_of(limit, candidate_risk=usdt("1999")) is LimitStatus.WITHIN


def test_a_missing_equity_makes_a_percent_limit_indeterminate() -> None:
    result = check(
        PER_TRADE, candidate_risk=usdt("2001"), equity=Absent("no snapshot")
    )
    assert isinstance(result.results[0].status, Absent)
    assert "no snapshot" in result.results[0].status.reason


def test_an_indeterminate_result_is_never_counted_as_within() -> None:
    result = check(PER_TRADE, candidate_risk=usdt("1"), equity=Absent("no snapshot"))
    assert result.indeterminate
    assert result.binding_constraints == ()
    assert all(entry.status is not LimitStatus.WITHIN for entry in result.results)


# -- total open risk --------------------------------------------------------

TOTAL_MONEY = risk_limit(
    "total_open", scope=LimitScope.TOTAL_OPEN_RISK, value=usdt("1500"),
    unit=LimitUnit.MONEY,
)


def test_total_open_risk_sums_every_position() -> None:
    result = check(
        TOTAL_MONEY,
        lines=(line(), line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), entry=Decimal("3000"), stop=Decimal("2200"), mark=mark("3000"))),
    )
    assert result.results[0].current_value == usdt("1600")
    assert result.results[0].status is LimitStatus.EXCEEDED


@pytest.mark.parametrize(
    "quantity,expected",
    [
        ("0.9", LimitStatus.WITHIN),
        ("0.9375", LimitStatus.AT_LIMIT),
        ("0.95", LimitStatus.EXCEEDED),
    ],
)
def test_the_total_open_risk_boundary(quantity: str, expected: LimitStatus) -> None:
    """0.9375 BTC x 1600 = exactly 1500 USDT."""
    assert status_of(TOTAL_MONEY, lines=(line(quantity=btc(quantity)),)) is expected


def test_one_trade_cannot_bypass_the_total_open_risk_check() -> None:
    """Two positions each comfortably under the per-trade ceiling can still put
    the portfolio over its total. Both limits are evaluated, always."""
    budget = risk_budget(limits=(PER_TRADE, TOTAL_MONEY))
    result = evaluate_constraints(
        budget,
        state(
            line(quantity=btc("0.5")),
            line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), entry=Decimal("3000"), stop=Decimal("2200"), mark=mark("3000")),
        ),
        owner=OWNER,
    )
    per_trade, total = result.results
    assert per_trade.status is LimitStatus.WITHIN
    assert total.status is LimitStatus.EXCEEDED


def test_total_open_risk_as_a_fraction_of_equity() -> None:
    limit = risk_limit(
        "total_pct", scope=LimitScope.TOTAL_OPEN_RISK, value=Decimal("0.006"),
        unit=LimitUnit.PERCENT_OF_EQUITY,
    )
    result = check(limit, lines=(line(),), equity=usdt("100000"))
    assert result.results[0].current_value == Decimal("0.008")
    assert result.results[0].status is LimitStatus.EXCEEDED


def test_an_unstopped_position_makes_total_open_risk_indeterminate() -> None:
    """Not a smaller number. The unstopped position is the dangerous one."""
    result = check(TOTAL_MONEY, lines=(line(), line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), stop=Absent("no plan"))))
    assert isinstance(result.results[0].status, Absent)


# -- concentration ----------------------------------------------------------


def _concentration(key: str, value: str = "0.5") -> object:
    return risk_limit(
        "conc",
        scope=LimitScope.CONCENTRATION,
        value=Decimal(value),
        unit=LimitUnit.RATIO,
        key=key,
    )


def test_venue_concentration_measures_that_venues_share_of_gross() -> None:
    result = check(
        _concentration("venue:binance", "0.4"),
        lines=(line(), line(market=EVEDEX_MARKET)),
    )
    assert result.results[0].current_value == Decimal("0.5")
    assert result.results[0].status is LimitStatus.EXCEEDED


def test_account_concentration_measures_that_accounts_share() -> None:
    result = check(
        _concentration(f"account:{ACCOUNT.value}", "0.75"),
        lines=(line(), line(account=SECOND_ACCOUNT)),
    )
    assert result.results[0].current_value == Decimal("0.5")
    assert result.results[0].status is LimitStatus.WITHIN


def test_symbol_concentration_spans_venues() -> None:
    """The same pair at two venues is one symbol concentration."""
    result = check(
        _concentration("symbol:BTCUSDT", "0.9"),
        lines=(line(), line(market=EVEDEX_MARKET)),
    )
    assert result.results[0].current_value == Decimal("1")
    assert result.results[0].status is LimitStatus.EXCEEDED


def test_instrument_concentration_does_not_span_venues() -> None:
    result = check(
        _concentration("instrument:binance:BTCUSDT:spot", "0.9"),
        lines=(line(), line(market=EVEDEX_MARKET)),
    )
    assert result.results[0].current_value == Decimal("0.5")


def test_directional_concentration_reads_the_direction_axis() -> None:
    result = check(
        _concentration("direction:long", "0.6"),
        lines=(line(), line(market=ETH_MARKET, quantity=Quantity(Decimal("0.5"), ETH), direction=PositionDirection.SHORT, stop=Decimal("61600"), entry=Decimal("60000"), mark=mark("61000"))),
    )
    assert result.results[0].current_value == Decimal("0.5")
    assert result.results[0].status is LimitStatus.WITHIN


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0.51", LimitStatus.WITHIN),
        ("0.5", LimitStatus.AT_LIMIT),
        ("0.49", LimitStatus.EXCEEDED),
    ],
)
def test_the_concentration_boundary(value: str, expected: LimitStatus) -> None:
    assert (
        status_of(
            _concentration("venue:binance", value),
            lines=(line(), line(market=EVEDEX_MARKET)),
        )
        is expected
    )


def test_a_concentration_limit_with_no_key_is_indeterminate() -> None:
    limit = risk_limit(
        "conc", scope=LimitScope.CONCENTRATION, value=Decimal("0.5"),
        unit=LimitUnit.RATIO,
    )
    result = check(limit, lines=(line(),))
    assert isinstance(result.results[0].status, Absent)
    assert "names no key" in result.results[0].status.reason


def test_a_concentration_limit_naming_an_unknown_axis_is_indeterminate() -> None:
    result = check(_concentration("sector:banks"), lines=(line(),))
    assert isinstance(result.results[0].status, Absent)
    assert "does not measure" in result.results[0].status.reason


def test_a_malformed_concentration_key_is_indeterminate() -> None:
    result = check(_concentration("binance"), lines=(line(),))
    assert isinstance(result.results[0].status, Absent)
    assert "does not name an axis" in result.results[0].status.reason


def test_a_concentration_key_that_holds_nothing_is_indeterminate() -> None:
    result = check(_concentration("venue:kraken"), lines=(line(),))
    assert isinstance(result.results[0].status, Absent)


def test_concentration_may_be_measured_against_open_risk() -> None:
    limit = risk_limit(
        "conc",
        scope=LimitScope.CONCENTRATION,
        value=Decimal("0.4"),
        unit=LimitUnit.PERCENT_OF_OPEN_RISK,
        key="venue:binance",
    )
    result = check(limit, lines=(line(), line(market=EVEDEX_MARKET)))
    assert result.results[0].current_value == Decimal("0.5")
    assert result.results[0].status is LimitStatus.EXCEEDED


def test_concentration_in_money_compares_money() -> None:
    limit = risk_limit(
        "conc",
        scope=LimitScope.CONCENTRATION,
        value=usdt("20000"),
        unit=LimitUnit.MONEY,
        key="venue:binance",
    )
    result = check(limit, lines=(line(),))
    assert result.results[0].current_value == usdt("30500")
    assert result.results[0].status is LimitStatus.EXCEEDED


def test_concentration_in_a_count_is_not_a_unit_it_is_measured_in() -> None:
    limit = risk_limit(
        "conc", scope=LimitScope.CONCENTRATION, value=Decimal("2"),
        unit=LimitUnit.COUNT, key="venue:binance",
    )
    result = check(limit, lines=(line(),))
    assert isinstance(result.results[0].status, Absent)


# -- cluster / group exposure -----------------------------------------------


def test_cluster_exposure_reads_the_owners_classification() -> None:
    limit = risk_limit(
        "cluster", scope=LimitScope.CLUSTER_EXPOSURE, value=Decimal("0.6"),
        unit=LimitUnit.RATIO, key="l1",
    )
    result = check(
        limit,
        lines=(line(), line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), mark=mark("30500"))),
        classification=groups("owner-v1", BTC=["l1"], ETH=["l1"]),
    )
    assert result.results[0].current_value == Decimal("1")
    assert result.results[0].status is LimitStatus.EXCEEDED


def test_correlated_exposure_is_not_presented_as_diversification() -> None:
    """Two different instruments, one group: the cluster share is 1, not 0.5."""
    limit = risk_limit(
        "cluster", scope=LimitScope.CLUSTER_EXPOSURE, value=Decimal("0.5"),
        unit=LimitUnit.RATIO, key="l1",
    )
    result = check(
        limit,
        lines=(line(), line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), mark=mark("30500"))),
        classification=groups("owner-v1", BTC=["l1"], ETH=["l1"]),
    )
    assert result.results[0].current_value == Decimal("1")
    assert result.results[0].status is LimitStatus.EXCEEDED


def test_a_cluster_nothing_falls_in_is_indeterminate_not_zero() -> None:
    limit = risk_limit(
        "cluster", scope=LimitScope.CLUSTER_EXPOSURE, value=Decimal("0.5"),
        unit=LimitUnit.RATIO, key="ai",
    )
    result = check(limit, lines=(line(),), classification=groups("owner-v1", BTC=["l1"]))
    assert isinstance(result.results[0].status, Absent)
    assert "owner-v1" in result.results[0].status.reason


def test_a_cluster_limit_with_no_key_is_indeterminate() -> None:
    limit = risk_limit(
        "cluster", scope=LimitScope.CLUSTER_EXPOSURE, value=Decimal("0.5"),
        unit=LimitUnit.RATIO,
    )
    result = check(limit, lines=(line(),))
    assert isinstance(result.results[0].status, Absent)


def test_unclassified_exposure_falls_in_the_unclassified_bucket() -> None:
    limit = risk_limit(
        "cluster", scope=LimitScope.CLUSTER_EXPOSURE, value=Decimal("0.5"),
        unit=LimitUnit.RATIO, key="unclassified",
    )
    result = check(limit, lines=(line(),))
    assert result.results[0].current_value == Decimal("1")


# -- leverage, counts, reserve ----------------------------------------------


def test_leverage_is_gross_over_equity() -> None:
    limit = risk_limit(
        "lev", scope=LimitScope.LEVERAGE, value=Decimal("0.3"), unit=LimitUnit.RATIO
    )
    result = check(limit, lines=(line(),), equity=usdt("100000"))
    assert result.results[0].current_value == Decimal("0.305")
    assert result.results[0].status is LimitStatus.EXCEEDED


def test_a_leverage_limit_in_the_wrong_unit_is_indeterminate() -> None:
    limit = risk_limit(
        "lev", scope=LimitScope.LEVERAGE, value=Decimal("3"), unit=LimitUnit.COUNT
    )
    assert isinstance(status_of(limit, lines=(line(),)), Absent)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("3", LimitStatus.WITHIN),
        ("2", LimitStatus.AT_LIMIT),
        ("1", LimitStatus.EXCEEDED),
    ],
)
def test_the_concurrent_position_boundary(value: str, expected: LimitStatus) -> None:
    limit = risk_limit(
        "count", scope=LimitScope.MAX_CONCURRENT_POSITIONS, value=Decimal(value),
        unit=LimitUnit.COUNT,
    )
    assert (
        status_of(limit, lines=(line(), line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH))))
        is expected
    )


MIN_RESERVE = risk_limit(
    "reserve", scope=LimitScope.MIN_RESERVE, value=usdt("10000"),
    unit=LimitUnit.MONEY,
)


def test_a_reserve_below_the_floor_is_exceeded_not_within() -> None:
    """The inversion that makes a risk engine worse than none. A ceiling
    comparison here reports an empty account as comfortably reserved."""
    result = check(MIN_RESERVE, lines=(line(),), cash=usdt("9999"))
    assert result.results[0].is_floor
    assert result.results[0].status is LimitStatus.EXCEEDED


def test_a_reserve_exactly_at_the_floor_is_at_limit() -> None:
    assert status_of(MIN_RESERVE, lines=(line(),), cash=usdt("10000")) is LimitStatus.AT_LIMIT


def test_a_reserve_above_the_floor_is_within() -> None:
    assert status_of(MIN_RESERVE, lines=(line(),), cash=usdt("10001")) is LimitStatus.WITHIN


def test_a_floors_headroom_is_positive_when_there_is_room() -> None:
    """Positive means room on a floor and on a ceiling alike, so a reader never
    has to remember which way a particular limit runs."""
    floor = check(MIN_RESERVE, lines=(line(),), cash=usdt("12000")).results[0]
    ceiling = check(TOTAL_MONEY, lines=(line(),)).results[0]
    assert floor.headroom == usdt("2000")
    assert ceiling.headroom == usdt("700")


def test_a_reserve_with_no_cash_is_indeterminate() -> None:
    assert isinstance(
        status_of(MIN_RESERVE, lines=(line(),), cash=Absent("no snapshot")), Absent
    )


# -- the scopes this build does not measure ---------------------------------


def test_a_period_loss_limit_is_indeterminate_and_names_the_period() -> None:
    limit = risk_limit(
        "daily_loss", scope=LimitScope.PERIOD_LOSS, value=usdt("5000"),
        unit=LimitUnit.MONEY, period=LimitPeriod.DAY,
    )
    result = check(limit, lines=(line(),))
    assert isinstance(result.results[0].status, Absent)
    assert "period 2026-08-12" in result.results[0].status.reason


def test_a_drawdown_limit_is_indeterminate_and_names_the_missing_series() -> None:
    limit = risk_limit(
        "dd", scope=LimitScope.DRAWDOWN, value=Decimal("0.2"),
        unit=LimitUnit.PERCENT_FROM_PEAK,
    )
    result = check(limit, lines=(line(),))
    assert isinstance(result.results[0].status, Absent)
    assert "equity peak" in result.results[0].status.reason


# -- the check object -------------------------------------------------------


def test_every_limit_in_the_budget_appears_in_the_result() -> None:
    """A check that silently dropped a limit reads as a clean bill of health on
    exactly the constraint nobody could evaluate."""
    budget = risk_budget(
        limits=(PER_TRADE, TOTAL_MONEY, MIN_RESERVE, _concentration("venue:binance"))
    )
    result = evaluate_constraints(budget, state(line()), owner=OWNER)
    assert len(result.results) == 4
    assert [entry.limit_id for entry in result.results] == [
        limit.limit_id for limit in budget.limits
    ]


def test_binding_and_indeterminate_are_two_separate_lists() -> None:
    budget = risk_budget(limits=(TOTAL_MONEY, PER_TRADE))
    result = evaluate_constraints(
        budget, state(line(), equity=Absent("no snapshot")), owner=OWNER
    )
    assert [entry.limit_id for entry in result.binding_constraints] == []
    assert [entry.limit_id for entry in result.indeterminate] == ["per_trade"]


def test_the_check_cites_both_versions() -> None:
    result = check(PER_TRADE, candidate_risk=usdt("1"))
    assert result.policy_version == CONSTRAINT_POLICY_VERSION
    assert result.risk_policy_version == 1
    assert result.origin is ValueOrigin.POLICY_DERIVED


def test_the_check_holds_no_verdict_and_no_score() -> None:
    fields = set(PortfolioConstraintCheck.__dataclass_fields__)
    for forbidden in ("score", "grade", "rating", "health", "verdict", "decision"):
        assert not any(forbidden in name for name in fields)


def test_a_missing_limit_lookup_is_absent() -> None:
    result = check(PER_TRADE, candidate_risk=usdt("1"))
    assert isinstance(result.result("nothing"), Absent)
    assert not isinstance(result.result("per_trade"), Absent)


def test_the_check_serializes_with_its_conventions() -> None:
    payload = check(PER_TRADE, candidate_risk=usdt("1")).to_payload()
    assert payload["percent_unit_convention"] == PERCENT_UNIT_CONVENTION
    assert "risk_basis" in payload
    assert payload["results"][0]["limit_id"] == "per_trade"


def test_a_status_without_a_measurement_is_refused() -> None:
    """The pairing that stops an indeterminate result becoming a silent WITHIN."""
    with pytest.raises(DomainValidationError, match="silent 'within'"):
        ConstraintResult(
            limit_id="x",
            scope=LimitScope.PER_TRADE_RISK,
            unit=LimitUnit.PERCENT_OF_EQUITY,
            limit_value=Decimal("0.02"),
            current_value=Absent("not measured"),
            status=LimitStatus.WITHIN,
        )


def test_a_money_limit_measured_by_a_ratio_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="two different things"):
        ConstraintResult(
            limit_id="x",
            scope=LimitScope.TOTAL_OPEN_RISK,
            unit=LimitUnit.MONEY,
            limit_value=usdt("100"),
            current_value=Decimal("0.5"),
            status=LimitStatus.WITHIN,
        )


def test_a_limit_evaluated_twice_is_refused() -> None:
    result = check(PER_TRADE, candidate_risk=usdt("1")).results[0]
    with pytest.raises(DomainValidationError, match="evaluated twice"):
        PortfolioConstraintCheck(
            portfolio_id="main",
            budget_id="b",
            risk_policy_version=1,
            evaluated_at=AT(9),
            results=(result, result),
        )


def test_a_money_limit_in_another_currency_is_indeterminate_not_converted() -> None:
    limit = risk_limit(
        "total_open", scope=LimitScope.TOTAL_OPEN_RISK,
        value=Money(Decimal("1500"), BTC), unit=LimitUnit.MONEY,
    )
    result = check(limit, lines=(line(),))
    assert isinstance(result.results[0].status, Absent)
    assert "hide the rate" in result.results[0].status.reason


def test_an_uncomparable_limit_costs_that_limit_and_no_other() -> None:
    """Regression. One limit the owner stated in the wrong currency used to take
    the whole check down with it, which turns a mis-typed limit into a portfolio
    with no risk evaluation at all."""
    wrong_currency = risk_limit(
        "in_btc", scope=LimitScope.TOTAL_OPEN_RISK,
        value=Money(Decimal("1500"), BTC), unit=LimitUnit.MONEY,
    )
    budget = risk_budget(limits=(wrong_currency, TOTAL_MONEY, PER_TRADE))
    result = evaluate_constraints(budget, state(line()), owner=OWNER)
    assert len(result.results) == 3
    assert [entry.limit_id for entry in result.indeterminate] == ["in_btc"]
    assert result.result("total_open").status is LimitStatus.WITHIN


def test_an_uncomparable_measurement_is_not_carried_beside_an_absent_status() -> None:
    """A number rendered next to "could not be evaluated" reads as the
    evaluation. Both halves are demoted together."""
    wrong_currency = risk_limit(
        "in_btc", scope=LimitScope.TOTAL_OPEN_RISK,
        value=Money(Decimal("1500"), BTC), unit=LimitUnit.MONEY,
    )
    entry = check(wrong_currency, lines=(line(),)).results[0]
    assert isinstance(entry.current_value, Absent)
    assert isinstance(entry.headroom, Absent)


# -- remaining capacity -----------------------------------------------------


def test_remaining_risk_capacity_is_the_money_headroom() -> None:
    result = check(TOTAL_MONEY, lines=(line(),))
    assert remaining_risk_capacity(result, base=USDT) == usdt("700")


def test_remaining_risk_capacity_is_absent_for_a_fractional_limit() -> None:
    limit = risk_limit(
        "total_pct", scope=LimitScope.TOTAL_OPEN_RISK, value=Decimal("0.02"),
        unit=LimitUnit.PERCENT_OF_EQUITY,
    )
    capacity = remaining_risk_capacity(check(limit, lines=(line(),)), base=USDT)
    assert isinstance(capacity, Absent)
    assert "equity it was measured against" in capacity.reason


def test_remaining_risk_capacity_is_absent_when_the_budget_states_none() -> None:
    capacity = remaining_risk_capacity(
        check(PER_TRADE, candidate_risk=usdt("1")), base=USDT
    )
    assert isinstance(capacity, Absent)
    assert "gap in the owner's policy" in capacity.reason


def test_remaining_risk_capacity_goes_negative_when_the_budget_is_exceeded() -> None:
    """Reported as a negative headroom rather than clamped to zero: *how far*
    over is the number the owner needs."""
    result = check(TOTAL_MONEY, lines=(line(quantity=btc("1")),))
    assert remaining_risk_capacity(result, base=USDT) == usdt("-100")


# -- determinism ------------------------------------------------------------


def test_the_same_inputs_produce_an_equal_check_every_time() -> None:
    budget = risk_budget(limits=(PER_TRADE, TOTAL_MONEY, MIN_RESERVE))
    first = evaluate_constraints(budget, state(line()), owner=OWNER)
    second = evaluate_constraints(budget, state(line()), owner=OWNER)
    assert first == second


def test_the_engine_refuses_inputs_of_the_wrong_type() -> None:
    budget = risk_budget()
    with pytest.raises(TypeError):
        evaluate_constraints(budget, object(), owner=OWNER)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        evaluate_constraints(object(), state(), owner=OWNER)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        evaluate_constraints(budget, state(), owner=object())  # type: ignore[arg-type]


# -- units the engine accepts on each scope ---------------------------------


def test_concentration_may_be_measured_as_a_fraction_of_equity() -> None:
    limit = risk_limit(
        "conc",
        scope=LimitScope.CONCENTRATION,
        value=Decimal("0.2"),
        unit=LimitUnit.PERCENT_OF_EQUITY,
        key="venue:binance",
    )
    result = check(limit, lines=(line(),), equity=usdt("100000"))
    assert result.results[0].current_value == Decimal("0.305")
    assert result.results[0].status is LimitStatus.EXCEEDED


def test_cluster_exposure_may_be_measured_as_a_fraction_of_equity() -> None:
    limit = risk_limit(
        "cluster",
        scope=LimitScope.CLUSTER_EXPOSURE,
        value=Decimal("0.2"),
        unit=LimitUnit.PERCENT_OF_EQUITY,
        key="l1",
    )
    result = check(
        limit,
        lines=(line(),),
        equity=usdt("100000"),
        classification=groups("owner-v1", BTC=["l1"]),
    )
    assert result.results[0].current_value == Decimal("0.305")


def test_cluster_exposure_may_be_measured_in_money() -> None:
    limit = risk_limit(
        "cluster",
        scope=LimitScope.CLUSTER_EXPOSURE,
        value=usdt("20000"),
        unit=LimitUnit.MONEY,
        key="l1",
    )
    result = check(
        limit, lines=(line(),), classification=groups("owner-v1", BTC=["l1"])
    )
    assert result.results[0].current_value == usdt("30500")
    assert result.results[0].status is LimitStatus.EXCEEDED


def test_cluster_exposure_may_be_measured_against_open_risk() -> None:
    limit = risk_limit(
        "cluster",
        scope=LimitScope.CLUSTER_EXPOSURE,
        value=Decimal("0.5"),
        unit=LimitUnit.PERCENT_OF_OPEN_RISK,
        key="l1",
    )
    result = check(
        limit, lines=(line(),), classification=groups("owner-v1", BTC=["l1"])
    )
    assert result.results[0].current_value == Decimal("1")


def test_a_cluster_limit_in_a_count_is_not_a_unit_it_is_measured_in() -> None:
    limit = risk_limit(
        "cluster", scope=LimitScope.CLUSTER_EXPOSURE, value=Decimal("2"),
        unit=LimitUnit.COUNT, key="l1",
    )
    result = check(
        limit, lines=(line(),), classification=groups("owner-v1", BTC=["l1"])
    )
    assert isinstance(result.results[0].status, Absent)
    assert "not a unit a cluster exposure is measured in" in result.results[0].status.reason


def test_per_trade_risk_in_a_count_is_not_a_unit_it_is_measured_in() -> None:
    limit = risk_limit(
        "per_trade", scope=LimitScope.PER_TRADE_RISK, value=Decimal("2"),
        unit=LimitUnit.COUNT,
    )
    result = check(limit, candidate_risk=usdt("100"))
    assert isinstance(result.results[0].status, Absent)
    assert "not a unit per-trade risk is measured in" in result.results[0].status.reason


def test_total_open_risk_in_a_count_is_not_a_unit_it_is_measured_in() -> None:
    limit = risk_limit(
        "total_open", scope=LimitScope.TOTAL_OPEN_RISK, value=Decimal("2"),
        unit=LimitUnit.COUNT,
    )
    result = check(limit, lines=(line(),))
    assert isinstance(result.results[0].status, Absent)
    assert "not a unit total open risk is measured in" in result.results[0].status.reason


def test_a_reserve_in_a_ratio_unit_is_not_a_unit_it_is_measured_in() -> None:
    limit = risk_limit(
        "reserve", scope=LimitScope.MIN_RESERVE, value=Decimal("0.2"),
        unit=LimitUnit.RATIO,
    )
    result = check(limit, lines=(line(),), cash=usdt("40000"))
    assert isinstance(result.results[0].status, Absent)
    assert "not a unit a reserve is measured in" in result.results[0].status.reason


def test_a_reserve_may_be_measured_as_a_fraction_of_equity() -> None:
    limit = risk_limit(
        "reserve", scope=LimitScope.MIN_RESERVE, value=Decimal("0.5"),
        unit=LimitUnit.PERCENT_OF_EQUITY,
    )
    result = check(limit, lines=(line(),), cash=usdt("40000"), equity=usdt("100000"))
    assert result.results[0].current_value == Decimal("0.4")
    assert result.results[0].status is LimitStatus.EXCEEDED  # below the floor


def test_a_money_limit_cannot_be_stated_with_a_ratio_unit_at_all() -> None:
    """`_compare`'s money-versus-ratio branch is a defensive guard, not a live
    path, and this records why: `RiskLimit` already refuses the construction one
    layer down, so a budget that reached this engine cannot carry the mismatch.

    The guard stays because the engine picks its own measurement per scope, and a
    future scope that returned the wrong shape must produce one indeterminate
    result rather than a comparison between a price and a percentage.
    """
    with pytest.raises(TypeError, match="value is a Decimal"):
        risk_limit(
            "conc", scope=LimitScope.CONCENTRATION, value=usdt("100"),
            unit=LimitUnit.RATIO, key="venue:binance",
        )


def test_a_zero_equity_makes_a_fraction_indeterminate_rather_than_infinite() -> None:
    result = check(PER_TRADE, candidate_risk=usdt("100"), equity=usdt("0"))
    assert isinstance(result.results[0].status, Absent)
    assert "undefined rather than large" in result.results[0].status.reason


def test_a_result_is_policy_derived() -> None:
    assert check(PER_TRADE, candidate_risk=usdt("1")).results[0].origin is (
        ValueOrigin.POLICY_DERIVED
    )


def test_a_result_refuses_a_non_bool_floor_flag() -> None:
    with pytest.raises(TypeError, match="is_floor"):
        ConstraintResult(
            limit_id="x",
            scope=LimitScope.MIN_RESERVE,
            unit=LimitUnit.MONEY,
            limit_value=usdt("1"),
            current_value=usdt("1"),
            status=LimitStatus.AT_LIMIT,
            is_floor="yes",  # type: ignore[arg-type]
        )


def test_a_result_refuses_values_of_the_wrong_type() -> None:
    common = {
        "limit_id": "x",
        "scope": LimitScope.PER_TRADE_RISK,
        "unit": LimitUnit.PERCENT_OF_EQUITY,
    }
    with pytest.raises(TypeError, match="limit_value"):
        ConstraintResult(
            limit_value=object(), current_value=Decimal("1"),  # type: ignore[arg-type]
            status=LimitStatus.WITHIN, **common,
        )
    with pytest.raises(TypeError, match="current_value"):
        ConstraintResult(
            limit_value=Decimal("1"), current_value=object(),  # type: ignore[arg-type]
            status=LimitStatus.WITHIN, **common,
        )
    with pytest.raises(TypeError, match="status"):
        ConstraintResult(
            limit_value=Decimal("1"), current_value=Decimal("1"),
            status="within", **common,  # type: ignore[arg-type]
        )


def test_a_money_limit_and_measurement_in_two_currencies_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="one currency"):
        ConstraintResult(
            limit_id="x",
            scope=LimitScope.TOTAL_OPEN_RISK,
            unit=LimitUnit.MONEY,
            limit_value=usdt("1"),
            current_value=Money(Decimal("1"), BTC),
            status=LimitStatus.AT_LIMIT,
        )


def test_the_engine_refuses_a_candidate_risk_of_the_wrong_type() -> None:
    with pytest.raises(TypeError, match="candidate_risk"):
        evaluate_constraints(
            risk_budget(), state(), owner=OWNER, candidate_risk=Decimal("1"),  # type: ignore[arg-type]
        )


def test_remaining_capacity_refuses_something_that_is_not_a_check() -> None:
    with pytest.raises(TypeError, match="PortfolioConstraintCheck"):
        remaining_risk_capacity(object(), base=USDT)  # type: ignore[arg-type]


def test_remaining_capacity_in_another_currency_is_absent() -> None:
    limit = risk_limit(
        "total_open", scope=LimitScope.TOTAL_OPEN_RISK, value=usdt("1500"),
        unit=LimitUnit.MONEY,
    )
    capacity = remaining_risk_capacity(check(limit, lines=(line(),)), base=BTC)
    assert isinstance(capacity, Absent)
    assert "base currency is BTC" in capacity.reason


def test_an_evaluated_at_override_is_honoured() -> None:
    result = evaluate_constraints(
        risk_budget(limits=(PER_TRADE,)),
        state(line()),
        owner=OWNER,
        evaluated_at=AT(18, day=13),
    )
    assert result.evaluated_at == AT(18, day=13)


def test_a_limit_exactly_at_its_ceiling_is_binding() -> None:
    """Mutation N18. A reached ceiling is a binding constraint, not room left.
    Excluding `AT_LIMIT` here is the quietest possible way to turn the 2 % rule
    from a ceiling into a target.
    """
    result = check(PER_TRADE, candidate_risk=usdt("2000"), equity=usdt("100000"))
    entry = result.results[0]
    assert entry.status is LimitStatus.AT_LIMIT
    assert entry.is_binding
    assert [item.limit_id for item in result.binding_constraints] == ["per_trade"]
    assert entry.headroom == Decimal("0")


def test_a_reserve_exactly_at_its_floor_is_binding_too() -> None:
    result = check(MIN_RESERVE, lines=(line(),), cash=usdt("10000"))
    entry = result.results[0]
    assert entry.status is LimitStatus.AT_LIMIT
    assert entry.is_binding
    assert entry.headroom == usdt("0")


def test_a_within_result_is_not_binding() -> None:
    result = check(PER_TRADE, candidate_risk=usdt("1000"), equity=usdt("100000"))
    assert result.results[0].status is LimitStatus.WITHIN
    assert not result.results[0].is_binding
    assert result.binding_constraints == ()


def test_a_position_count_limit_in_the_wrong_unit_is_indeterminate() -> None:
    limit = risk_limit(
        "count", scope=LimitScope.MAX_CONCURRENT_POSITIONS, value=usdt("2"),
        unit=LimitUnit.MONEY,
    )
    result = check(limit, lines=(line(),))
    assert isinstance(result.results[0].status, Absent)
    assert "a position count is a count" in result.results[0].status.reason
