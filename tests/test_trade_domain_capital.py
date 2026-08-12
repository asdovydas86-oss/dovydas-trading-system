"""The position fold, the portfolio snapshot, and the risk budget.

Three packages, one theme: **capital is measured, and its limits are asserted**,
and the tests below are mostly about keeping those two kinds of value apart.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from trade_domain_helpers import (
    ACCOUNT,
    AT,
    BTC,
    MARKET,
    OTHER_MARKET,
    USDT,
    correction,
    dust_policy,
    money,
    owner_context,
    quantity,
    trade,
    version_set,
)

from fmis.accounts import AccountId, Book, MarketId, MarketMode, VenueId
from fmis.ledger import TradeSide, resolve
from fmis.money import AssetCode, Money, Quantity
from fmis.portfolio import (
    AllocationEntry,
    CashBalance,
    ExposureSummary,
    FlowSummary,
    Holding,
    MarkQuote,
    PortfolioSnapshot,
)
from fmis.positions import (
    POSITION_CALCULATION_VERSION,
    POSITION_STATE_TRANSITIONS,
    AverageCost,
    IllegalPositionTransitionError,
    PositionDirection,
    PositionKey,
    PositionState,
    ReconciliationState,
    advance_position_state,
    fold_positions,
    total_fees,
)
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError, PayloadDecodeError, RecordAudit
from fmis.risk import (
    LimitPeriod,
    LimitScope,
    LimitSeverity,
    LimitStatus,
    LimitUnit,
    RiskBudget,
    RiskBudgetState,
    RiskLimit,
    effective_budget,
    evaluate_budget,
    evaluate_limit,
    period_key,
)


def _fold(*trades, dust=None):
    return fold_positions(
        resolve(trades).resolved(), dust=dust if dust is not None else dust_policy()
    )


# --------------------------------------------------------------------------
# The position fold.
# --------------------------------------------------------------------------


def test_a_single_buy_opens_a_long_position() -> None:
    (position,) = _fold(trade())
    assert position.state is PositionState.OPEN
    assert position.direction is PositionDirection.LONG
    assert position.net_quantity == Quantity(Decimal("0.5"), BTC)
    assert position.is_open
    assert isinstance(position.closed_at, Absent)
    assert position.origin is ValueOrigin.MEASURED
    assert position.reconciliation is ReconciliationState.UNRECONCILED


def test_an_add_then_a_full_exit_closes_the_round_trip() -> None:
    (position,) = _fold(
        trade(occurred_at=AT(10)),
        trade(occurred_at=AT(11), price=Decimal("62000")),
        trade(
            occurred_at=AT(12),
            side=TradeSide.SELL,
            quantity=Quantity(Decimal("1"), BTC),
            price=Decimal("65000"),
        ),
    )
    assert position.state is PositionState.CLOSED
    assert position.direction is PositionDirection.FLAT
    assert position.trade_count == 3
    assert position.add_count == 2
    assert position.reduce_count == 1
    assert position.closed_at == AT(12)
    assert len(position.event_ids) == 3


def test_average_entry_is_a_pair_and_the_quotient_is_computed_at_read_time() -> None:
    (position,) = _fold(
        trade(occurred_at=AT(10)),
        trade(occurred_at=AT(11), price=Decimal("62000")),
    )
    assert position.average_entry.total_cost == Money(Decimal("61000"), USDT)
    assert position.average_entry.total_quantity == Quantity(Decimal("1"), BTC)
    assert position.average_entry.per_unit == Decimal("61000")
    assert position.average_entry.arithmetic == "61000 ÷ 1"
    assert "per_unit" not in position.average_entry.to_payload()


def test_an_average_over_nothing_is_undefined_rather_than_zero() -> None:
    average = AverageCost(Money(Decimal("0"), USDT), Quantity(Decimal("0"), BTC))
    assert isinstance(average.per_unit, Absent)


def test_a_negative_cost_basis_quantity_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="cannot be negative"):
        AverageCost(Money(Decimal("1"), USDT), Quantity(Decimal("-1"), BTC))


def test_gross_and_net_pnl_are_always_both_present_and_differ_by_fees() -> None:
    (position,) = _fold(
        trade(occurred_at=AT(10)),
        trade(occurred_at=AT(11), price=Decimal("62000")),
        trade(
            occurred_at=AT(12),
            side=TradeSide.SELL,
            quantity=Quantity(Decimal("1"), BTC),
            price=Decimal("65000"),
        ),
    )
    assert position.realized_pnl_gross == Money(Decimal("4000"), USDT)
    assert position.realized_pnl_net == Money(Decimal("3955"), USDT)
    assert position.fees == (Money(Decimal("45"), USDT),)
    assert position.fees_in(USDT) == Money(Decimal("45"), USDT)
    assert position.fees_in(BTC) == Money.zero(BTC)


def test_a_fee_in_a_third_asset_is_reported_and_never_silently_converted() -> None:
    (position,) = _fold(
        trade(
            fee=Money(Decimal("0.01"), AssetCode("BNB")),
            fee_fx_rate_to_tax_currency=Decimal("3000"),
        )
    )
    assert position.realized_pnl_gross == position.realized_pnl_net
    assert position.fees == (Money(Decimal("0.01"), AssetCode("BNB")),)


def test_a_direction_flip_splits_one_fill_into_two_positions() -> None:
    positions = _fold(
        trade(occurred_at=AT(10)),
        trade(
            occurred_at=AT(13),
            side=TradeSide.SELL,
            quantity=Quantity(Decimal("1.5"), BTC),
            price=Decimal("64000"),
        ),
    )
    closed, opened = positions
    assert closed.state is PositionState.CLOSED
    assert closed.closed_by_flip
    assert closed.realized_pnl_gross == Money(Decimal("2000"), USDT)
    assert opened.state is PositionState.OPEN
    assert opened.direction is PositionDirection.SHORT
    assert opened.net_quantity == Quantity(Decimal("-1"), BTC)
    assert closed.key.flat_crossing_ordinal == 0
    assert opened.key.flat_crossing_ordinal == 1


def test_a_flipping_fill_apportions_its_fee_between_the_two_positions() -> None:
    closed, opened = _fold(
        trade(occurred_at=AT(10), fee=Money(Decimal("0"), USDT)),
        trade(
            occurred_at=AT(13),
            side=TradeSide.SELL,
            quantity=Quantity(Decimal("1.5"), BTC),
            price=Decimal("64000"),
            fee=Money(Decimal("30"), USDT),
        ),
    )
    assert closed.fees == (Money(Decimal("10"), USDT),)
    assert opened.fees == (Money(Decimal("20"), USDT),)


def test_a_residue_within_dust_closes_the_position() -> None:
    positions = _fold(
        trade(occurred_at=AT(10)),
        trade(
            occurred_at=AT(11),
            side=TradeSide.SELL,
            quantity=Quantity(Decimal("0.499999999"), BTC),
            price=Decimal("61000"),
        ),
        dust=dust_policy("0.000001"),
    )
    assert positions[0].state is PositionState.CLOSED


def test_a_residue_above_dust_leaves_the_position_open() -> None:
    positions = _fold(
        trade(occurred_at=AT(10)),
        trade(
            occurred_at=AT(11),
            side=TradeSide.SELL,
            quantity=Quantity(Decimal("0.4"), BTC),
            price=Decimal("61000"),
        ),
    )
    assert positions[0].state is PositionState.OPEN
    assert positions[0].net_quantity == Quantity(Decimal("0.1"), BTC)


def test_each_market_and_book_pair_folds_separately() -> None:
    positions = _fold(
        trade(),
        trade(book=Book.INVESTING),
        trade(market=OTHER_MARKET, quantity=Quantity(Decimal("2"), AssetCode("ETH"))),
    )
    assert len(positions) == 3
    assert {position.book for position in positions} == {Book.SWING, Book.INVESTING}


def test_the_fold_is_pure_and_recomputes_identically() -> None:
    trades = (trade(occurred_at=AT(10)), trade(occurred_at=AT(11), price=Decimal("62000")))
    assert _fold(*trades) == _fold(*trades)


def test_the_fold_reads_the_corrected_value_and_not_the_original() -> None:
    original = trade()
    replacement = trade(quantity=Quantity(Decimal("0.6"), BTC))
    resolver = resolve((original,), (correction(original, replacement),))
    (position,) = fold_positions(resolver.resolved(), dust=dust_policy())
    assert position.net_quantity == Quantity(Decimal("0.6"), BTC)


def test_a_position_carries_the_event_ids_a_frozen_artifact_should_reference() -> None:
    (position,) = _fold(trade())
    assert position.event_ids == (trade().event_id,)
    assert str(position.key) == f"{MARKET.value}|swing|#0"


def test_a_position_names_the_calculation_and_dust_policy_versions_it_used() -> None:
    (position,) = _fold(trade())
    assert position.calculation_version == POSITION_CALCULATION_VERSION
    assert position.dust_policy_id == "dust-v1"
    assert position.dust_policy_version == 1


def test_unrealized_pnl_requires_a_mark_and_says_so_when_there_is_none() -> None:
    (position,) = _fold(trade())
    assert isinstance(position.unrealized_pnl(Absent("no mark"), USDT), Absent)
    assert position.unrealized_pnl(Decimal("62000"), USDT) == Money(
        Decimal("1000"), USDT
    )


def test_a_closed_position_has_no_unrealized_pnl() -> None:
    positions = _fold(
        trade(occurred_at=AT(10)),
        trade(
            occurred_at=AT(11),
            side=TradeSide.SELL,
            quantity=Quantity(Decimal("0.5"), BTC),
            price=Decimal("61000"),
        ),
    )
    assert isinstance(positions[0].unrealized_pnl(Decimal("62000"), USDT), Absent)


def test_a_position_duration_is_absent_while_it_is_open() -> None:
    (open_position,) = _fold(trade())
    assert isinstance(open_position.duration, Absent)


def test_the_fold_reports_max_exposure_and_serializes_for_export() -> None:
    (position,) = _fold(
        trade(occurred_at=AT(10)),
        trade(occurred_at=AT(11)),
        trade(
            occurred_at=AT(12),
            side=TradeSide.SELL,
            quantity=Quantity(Decimal("0.5"), BTC),
            price=Decimal("61000"),
        ),
    )
    assert position.max_exposure == Quantity(Decimal("1"), BTC)
    payload = position.to_payload()
    assert payload["state"] == "open"
    assert payload["dust_policy_id"] == "dust-v1"


def test_total_fees_sums_one_named_asset_across_positions() -> None:
    positions = _fold(trade(), trade(book=Book.INVESTING))
    assert total_fees(positions, USDT) == Money(Decimal("30"), USDT)


def test_a_closed_position_never_reopens() -> None:
    assert POSITION_STATE_TRANSITIONS[PositionState.CLOSED] == frozenset()
    with pytest.raises(IllegalPositionTransitionError, match="never reopens"):
        advance_position_state(PositionState.CLOSED, PositionState.OPEN)
    assert (
        advance_position_state(PositionState.OPEN, PositionState.CLOSED)
        is PositionState.CLOSED
    )


def test_the_fold_type_checks_its_inputs() -> None:
    with pytest.raises(TypeError, match="DustPolicy"):
        fold_positions((), dust="loose change")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        fold_positions(("not a resolved trade",), dust=dust_policy())  # type: ignore[arg-type]


def test_a_position_key_is_ordered_and_validated() -> None:
    assert PositionKey("m", "swing", 0) < PositionKey("m", "swing", 1)
    with pytest.raises(DomainValidationError):
        PositionKey("m", "swing", -1)


# --------------------------------------------------------------------------
# PortfolioSnapshot.
# --------------------------------------------------------------------------


def _snapshot(**overrides: object) -> PortfolioSnapshot:
    values: dict = {
        "portfolio_id": "main",
        "base_currency": USDT,
        "as_of": AT(9),
        "books_covered": (Book.SWING,),
        "holdings": (
            Holding(
                BTC,
                ACCOUNT,
                quantity("1.5"),
                MarkQuote(Decimal("60000"), USDT, "binance", AT(8)),
            ),
        ),
        "cash": (
            CashBalance(ACCOUNT, money("2500"), Absent("already the base currency")),
        ),
        "flows": FlowSummary(money("0"), money("0"), Absent("first snapshot")),
        "exposure": ExposureSummary(
            money("90000"), money("90000"), money("90000"), money("92500"), money("90000")
        ),
        "allocations": (
            AllocationEntry("asset", "BTC", money("90000"), money("92500"), "cls-v1"),
        ),
        "open_position_event_ids": (),
        "version_set": version_set(),
        "audit": RecordAudit.frozen_at(AT(9)),
    }
    values.update(overrides)
    return PortfolioSnapshot(**values)


def test_a_portfolio_snapshot_round_trips_and_verifies_its_own_id() -> None:
    snapshot = _snapshot()
    assert PortfolioSnapshot.from_payload(snapshot.to_payload()) == snapshot
    payload = snapshot.to_payload()
    payload["snapshot_id"] = "portfolio_snapshot-x-20260812T090000Z-0123456789abcdef"
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        PortfolioSnapshot.from_payload(payload)


def test_a_missing_mark_makes_the_total_absent_and_never_zero() -> None:
    snapshot = _snapshot(
        holdings=(
            Holding(
                BTC,
                ACCOUNT,
                quantity("1.5"),
                MarkQuote(Decimal("60000"), USDT, "binance", AT(8)),
            ),
            Holding(
                AssetCode("SOL"),
                ACCOUNT,
                Quantity(Decimal("10"), AssetCode("SOL")),
                Absent("no mark for SOL was available at 09:00"),
            ),
        )
    )
    total = snapshot.total_value()
    assert isinstance(total, Absent)
    assert "SOL" in total.reason
    assert len(snapshot.unmarked_holdings) == 1


def test_a_fully_marked_snapshot_totals_its_holdings_and_cash() -> None:
    assert _snapshot().total_value() == money("92500")


def test_a_mark_in_a_foreign_currency_without_a_rate_makes_the_total_absent() -> None:
    snapshot = _snapshot(
        holdings=(
            Holding(BTC, ACCOUNT, quantity("1"), MarkQuote(Decimal("500000"), AssetCode("SEK"), "riksbank", AT(8))),
        )
    )
    assert isinstance(snapshot.total_value(), Absent)


def test_cash_in_a_foreign_currency_needs_a_rate_and_its_source() -> None:
    with pytest.raises(DomainValidationError, match="rate without a source"):
        CashBalance(ACCOUNT, Money(Decimal("100"), AssetCode("SEK")), Decimal("0.1"))
    balance = CashBalance(
        ACCOUNT, Money(Decimal("100"), AssetCode("SEK")), Decimal("0.1"), "riksbank"
    )
    assert balance.value_in_base(USDT) == money("10")
    assert isinstance(
        CashBalance(
            ACCOUNT, Money(Decimal("100"), AssetCode("SEK")), Absent("no rate")
        ).value_in_base(USDT),
        Absent,
    )


def test_flows_are_required_because_a_deposit_would_otherwise_look_like_a_gain() -> None:
    with pytest.raises(TypeError, match="deposit looks like a gain"):
        _snapshot(flows=None)
    flows = FlowSummary(money("1000"), money("400"), AT(8))
    assert flows.net == money("600")
    assert FlowSummary.from_payload(flows.to_payload()) == flows


def test_flows_are_stated_as_positive_magnitudes_in_one_currency() -> None:
    with pytest.raises(DomainValidationError, match="positive magnitude"):
        FlowSummary(money("-1"), money("0"), Absent("first"))
    with pytest.raises(DomainValidationError, match="one currency"):
        FlowSummary(money("1"), Money(Decimal("1"), AssetCode("SEK")), Absent("first"))


def test_leverage_and_weight_are_pairs_with_the_division_done_at_read_time() -> None:
    snapshot = _snapshot()
    assert snapshot.exposure.leverage == Decimal("90000") / Decimal("92500")
    assert "leverage" not in snapshot.exposure.to_payload()
    assert snapshot.allocations[0].weight == Decimal("90000") / Decimal("92500")
    assert "weight" not in snapshot.allocations[0].to_payload()


def test_leverage_against_no_equity_is_undefined_rather_than_large() -> None:
    exposure = ExposureSummary(
        money("1"), money("1"), money("1"), money("0"), Absent("no positions")
    )
    assert isinstance(exposure.leverage, Absent)
    assert isinstance(
        ExposureSummary(
            money("1"), money("1"), money("1"), Absent("unknown"), Absent("unknown")
        ).leverage,
        Absent,
    )


def test_an_allocation_carries_the_classification_version_it_was_computed_under() -> None:
    snapshot = _snapshot()
    assert snapshot.allocations_for("asset")[0].classification_version == "cls-v1"
    assert snapshot.allocations_for("venue") == ()


def test_one_asset_and_account_pair_holds_one_quantity() -> None:
    holding = Holding(BTC, ACCOUNT, quantity("1"), Absent("no mark"))
    with pytest.raises(DomainValidationError, match="two answers to one question"):
        _snapshot(holdings=(holding, holding))


def test_a_holding_quantity_must_be_of_the_asset_it_claims() -> None:
    with pytest.raises(DomainValidationError, match="but the quantity is in"):
        Holding(BTC, ACCOUNT, quantity("1", USDT), Absent("no mark"))


def test_a_mark_dated_after_the_snapshot_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="dated after the snapshot"):
        _snapshot(
            holdings=(
                Holding(
                    BTC,
                    ACCOUNT,
                    quantity("1"),
                    MarkQuote(Decimal("60000"), USDT, "binance", AT(10)),
                ),
            )
        )


def test_a_mark_reports_its_own_staleness() -> None:
    mark = MarkQuote(Decimal("60000"), USDT, "binance", AT(8))
    assert mark.staleness_at(AT(9)).total_seconds() == 3600
    assert MarkQuote.from_payload(mark.to_payload()) == mark


def test_a_snapshot_is_frozen_at_the_instant_it_observes() -> None:
    with pytest.raises(DomainValidationError, match="must equal as_of"):
        _snapshot(audit=RecordAudit.frozen_at(AT(8)))


def test_a_snapshot_names_which_books_it_covers() -> None:
    assert _snapshot().books_covered == (Book.SWING,)
    with pytest.raises(DomainValidationError, match="must not repeat a book"):
        _snapshot(books_covered=(Book.SWING, Book.SWING))


def test_there_is_no_composite_portfolio_score_anywhere_on_a_snapshot() -> None:
    payload = _snapshot().to_payload()
    forbidden = {"score", "health", "grade", "rating", "risk_score"}
    assert not forbidden & set(payload)
    assert not any(forbidden & set(str(key) for key in payload))


def test_snapshot_staleness_is_derived_and_never_rewrites_the_record() -> None:
    subject = trade()
    snapshot = _snapshot(consumed_sources=(subject.as_consumed_source(),))
    assert snapshot.stale_inputs({subject.event_id: subject.content_digest}) == ()
    assert len(snapshot.stale_inputs({subject.event_id: "sha256:" + "0" * 64})) == 1
    with pytest.raises(TypeError):
        snapshot.stale_inputs([("a", "b")])  # type: ignore[arg-type]


def test_a_snapshot_can_be_cited_as_a_consumed_source() -> None:
    snapshot = _snapshot()
    assert snapshot.as_consumed_source().record_id == snapshot.snapshot_id


# --------------------------------------------------------------------------
# RiskBudget and RiskBudgetState.
# --------------------------------------------------------------------------


PER_TRADE = RiskLimit(
    "per_trade_risk",
    LimitScope.PER_TRADE_RISK,
    Decimal("0.02"),
    LimitUnit.PERCENT_OF_EQUITY,
    LimitPeriod.NONE,
    LimitSeverity.HARD_BLOCK,
    default_below_ceiling=Decimal("0.01"),
)
DAILY_LOSS = RiskLimit(
    "daily_loss",
    LimitScope.PERIOD_LOSS,
    Money(Decimal("500"), USDT),
    LimitUnit.MONEY,
    LimitPeriod.DAY,
    LimitSeverity.HARD_BLOCK,
)


def _budget(**overrides: object) -> RiskBudget:
    values: dict = {
        "budget_id": "swing_budget",
        "risk_policy_version": 1,
        "effective_from": AT(0),
        "limits": (PER_TRADE, DAILY_LOSS),
        "audit": RecordAudit.frozen_at(AT(0)),
    }
    values.update(overrides)
    return RiskBudget(**values)


def test_a_risk_budget_is_asserted_and_round_trips() -> None:
    budget = _budget()
    assert budget.origin is ValueOrigin.ASSERTED
    assert RiskBudget.from_payload(budget.to_payload()) == budget


def test_a_ceiling_may_carry_a_default_strictly_below_it() -> None:
    assert PER_TRADE.is_ceiling
    assert not DAILY_LOSS.is_ceiling
    with pytest.raises(DomainValidationError, match="the ceiling is not a target"):
        RiskLimit(
            "per_trade_risk",
            LimitScope.PER_TRADE_RISK,
            Decimal("0.02"),
            LimitUnit.PERCENT_OF_EQUITY,
            LimitPeriod.NONE,
            LimitSeverity.HARD_BLOCK,
            default_below_ceiling=Decimal("0.02"),
        )


def test_a_money_limit_carries_its_asset_and_a_ratio_limit_does_not() -> None:
    with pytest.raises(TypeError, match="a MONEY limit's value is a Money"):
        RiskLimit(
            "daily_loss",
            LimitScope.PERIOD_LOSS,
            Decimal("500"),
            LimitUnit.MONEY,
            LimitPeriod.DAY,
            LimitSeverity.HARD_BLOCK,
        )
    with pytest.raises(TypeError, match="limit's value is a Decimal"):
        RiskLimit(
            "leverage",
            LimitScope.LEVERAGE,
            Money(Decimal("2"), USDT),
            LimitUnit.RATIO,
            LimitPeriod.NONE,
            LimitSeverity.ADVISORY,
        )


def test_a_period_loss_limit_names_its_period_and_a_continuous_one_does_not() -> None:
    with pytest.raises(DomainValidationError, match="names its period"):
        RiskLimit(
            "daily_loss",
            LimitScope.PERIOD_LOSS,
            Money(Decimal("500"), USDT),
            LimitUnit.MONEY,
            LimitPeriod.NONE,
            LimitSeverity.HARD_BLOCK,
        )
    with pytest.raises(DomainValidationError, match="carries no period"):
        RiskLimit(
            "leverage",
            LimitScope.LEVERAGE,
            Decimal("2"),
            LimitUnit.RATIO,
            LimitPeriod.DAY,
            LimitSeverity.ADVISORY,
        )


def test_one_limit_id_holds_one_value() -> None:
    with pytest.raises(DomainValidationError, match="appears twice"):
        _budget(limits=(PER_TRADE, PER_TRADE))


def test_a_budget_finds_its_limits_by_id_and_by_scope() -> None:
    budget = _budget()
    assert budget.limit("per_trade_risk") is PER_TRADE
    assert budget.limit("nope") is None
    assert budget.limits_for(LimitScope.PERIOD_LOSS) == (DAILY_LOSS,)


def test_the_effective_budget_is_a_fold_over_config_events() -> None:
    first = _budget()
    second = _budget(risk_policy_version=2, effective_from=AT(9), limits=(PER_TRADE,))
    assert effective_budget((first, second), AT(10)) is second
    assert effective_budget((first, second), AT(1)) is first
    assert isinstance(effective_budget((first,), AT(0, day=1)), Absent)


def test_a_limit_evaluation_reports_facts_and_never_a_verdict() -> None:
    evaluation = evaluate_limit(PER_TRADE, Decimal("0.03"))
    assert evaluation.status is LimitStatus.EXCEEDED
    assert evaluation.headroom == Decimal("-0.01")
    payload = evaluation.to_payload()
    assert set(payload) == {"limit_id", "limit_value", "current_value", "status"}
    assert "recommendation" not in payload


@pytest.mark.parametrize(
    "current, expected",
    [
        (Decimal("0.01"), LimitStatus.WITHIN),
        (Decimal("0.02"), LimitStatus.AT_LIMIT),
        (Decimal("0.03"), LimitStatus.EXCEEDED),
    ],
)
def test_the_three_measured_statuses_are_produced_by_arithmetic(
    current: Decimal, expected: LimitStatus
) -> None:
    assert evaluate_limit(PER_TRADE, current).status is expected


def test_an_unmeasurable_limit_is_absent_and_never_silently_within() -> None:
    evaluation = evaluate_limit(PER_TRADE, Absent("no correlation history exists"))
    assert isinstance(evaluation.status, Absent)
    assert isinstance(evaluation.headroom, Absent)


def test_a_money_limit_is_measured_in_money() -> None:
    assert evaluate_limit(DAILY_LOSS, money("600")).status is LimitStatus.EXCEEDED
    with pytest.raises(TypeError, match="measured in Money"):
        evaluate_limit(DAILY_LOSS, Decimal("600"))
    with pytest.raises(TypeError, match="measured with a Decimal"):
        evaluate_limit(PER_TRADE, money("600"))


def test_a_limit_and_its_measurement_are_stated_in_one_currency() -> None:
    with pytest.raises(DomainValidationError, match="one currency"):
        evaluate_limit(DAILY_LOSS, Money(Decimal("600"), AssetCode("SEK")))


def test_an_unmeasured_limit_is_reported_rather_than_skipped() -> None:
    state = evaluate_budget(_budget(), {"per_trade_risk": Decimal("0.03")}, evaluated_at=AT(9))
    assert len(state.evaluations) == 2
    assert len(state.exceeded) == 1
    assert len(state.indeterminate) == 1
    assert state.origin is ValueOrigin.MEASURED


def test_a_measurement_for_a_limit_the_budget_does_not_hold_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="does not hold"):
        evaluate_budget(_budget(), {"telepathy": Decimal("1")}, evaluated_at=AT(9))


def test_the_state_reports_the_policy_version_it_read() -> None:
    state = evaluate_budget(_budget(), {}, evaluated_at=AT(9))
    assert state.risk_policy_version == 1
    assert state.to_payload()["risk_policy_version"] == 1


def test_a_limit_cannot_be_evaluated_twice_in_one_state() -> None:
    evaluation = evaluate_limit(PER_TRADE, Decimal("0.01"))
    with pytest.raises(DomainValidationError, match="evaluated twice"):
        RiskBudgetState("b", 1, AT(9), (evaluation, evaluation))


def test_period_boundaries_are_owner_local_and_never_stored() -> None:
    owner = owner_context()
    assert period_key(DAILY_LOSS, AT(22, minute=30), owner) == "2026-08-13"
    assert period_key(DAILY_LOSS, AT(9), owner) == "2026-08-12"
    assert isinstance(period_key(PER_TRADE, AT(9), owner), Absent)


def test_weekly_and_monthly_buckets_are_owner_local_too() -> None:
    weekly = RiskLimit(
        "weekly_loss",
        LimitScope.PERIOD_LOSS,
        Money(Decimal("2000"), USDT),
        LimitUnit.MONEY,
        LimitPeriod.WEEK,
        LimitSeverity.HARD_BLOCK,
    )
    monthly = RiskLimit(
        "monthly_loss",
        LimitScope.PERIOD_LOSS,
        Money(Decimal("5000"), USDT),
        LimitUnit.MONEY,
        LimitPeriod.MONTH,
        LimitSeverity.HARD_BLOCK,
    )
    rolling = RiskLimit(
        "drawdown",
        LimitScope.DRAWDOWN,
        Decimal("0.2"),
        LimitUnit.PERCENT_FROM_PEAK,
        LimitPeriod.ROLLING,
        LimitSeverity.ADVISORY,
    )
    owner = owner_context()
    assert period_key(weekly, AT(9), owner) == "2026-W33"
    assert period_key(monthly, AT(9), owner) == "2026-08"
    assert isinstance(period_key(rolling, AT(9), owner), Absent)


def test_period_key_type_checks_its_inputs() -> None:
    with pytest.raises(TypeError):
        period_key("per_trade", AT(9), owner_context())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        period_key(PER_TRADE, AT(9), "Europe/Stockholm")  # type: ignore[arg-type]


def test_a_budget_verifies_its_own_record_id_on_decode() -> None:
    payload = _budget().to_payload()
    payload["budget_record_id"] = "risk_budget-x-20260812T000000Z-0123456789abcdef"
    with pytest.raises(PayloadDecodeError, match="does not match"):
        RiskBudget.from_payload(payload)


def test_a_zero_fee_fill_adds_no_fee_line_to_the_position() -> None:
    """A position that paid nothing reports no fee, rather than a zero of some asset."""
    (position,) = _fold(trade(fee=Money(Decimal("0"), USDT)))
    assert position.fees == ()
    assert position.realized_pnl_gross == position.realized_pnl_net
