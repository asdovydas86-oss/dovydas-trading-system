"""Reading a recorded trade back: the assembly, the folds, and the warnings.

The interesting cases are all absences and anomalies. A commitment with no fill,
a position reduced below its maximum, fills across two accounts, an entry that
has drifted past its own stop — every one of them happens, and every one of them
must produce a stated reason rather than a plausible number.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from persistence_helpers import write_request
from trade_capture_helpers import capture_store, closed, note_request, recorded
from trade_domain_helpers import ACCOUNT, AT, BTC, MARKET, OTHER_MARKET, USDT, trade_plan

from fmis.accounts import AccountId
from fmis.money import AssetCode, Money, Quantity
from fmis.persistence import TradingStore
from fmis.plan import TradePlan
from fmis.positions import PositionState
from fmis.provenance import Absent
from fmis.snapshotting import RiskRewardReading, TradeDirection
from fmis.trade_capture import (
    CAPTURE_DUST_POLICY,
    CAPTURE_LIMITATIONS,
    PLAN_SUBJECT_KIND,
    TRADE_SUBJECT_KIND,
    CaptureStatus,
    TradeFilters,
    TradeNotFoundError,
    append_note,
    fills_for_plan,
    list_trades,
    load_plan,
    load_trade,
)

AT_READ = AT(12)


@pytest.fixture()
def store(tmp_path: Path) -> TradingStore:
    return capture_store(tmp_path)


def _view(store: TradingStore, plan_id: str, *, at=AT_READ):
    return load_trade(store, plan_id, dust=CAPTURE_DUST_POLICY, at=at)


# --------------------------------------------------------------------------
# The assembly.
# --------------------------------------------------------------------------


def test_a_recorded_trade_assembles_from_three_records(store: TradingStore) -> None:
    outcome = recorded(store, thesis="a reason")
    view = _view(store, outcome.plan_id)
    assert isinstance(view.plan, TradePlan)
    assert len(view.fills) == 1
    assert len(view.journal.entries) == 1


def test_the_status_of_an_open_trade_comes_from_the_fold(
    store: TradingStore,
) -> None:
    view = _view(store, recorded(store).plan_id)
    assert view.status is CaptureStatus.OPEN
    assert view.position.state is PositionState.OPEN


def test_a_closed_trade_reports_the_folds_realized_figures(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    closed(store, plan_id)
    view = _view(store, plan_id, at=AT(10, day=14))
    assert view.status is CaptureStatus.CLOSED
    assert view.position.realized_pnl_gross == Money(Decimal("1900"), USDT)
    assert view.realized_pnl_net == Money(Decimal("1869"), USDT)


def test_a_commitment_with_no_fill_is_planned_and_says_why(
    store: TradingStore,
) -> None:
    plan = trade_plan()
    store.plans.create(plan, request=write_request())
    view = _view(store, plan.plan_id)
    assert view.status is CaptureStatus.PLANNED
    assert view.fills == ()
    for absent in (view.position, view.entry_price, view.capital_at_risk):
        assert isinstance(absent, Absent)
        assert "nothing has filled" in absent.reason or "no fill" in absent.reason


def test_the_entry_price_is_the_folds_own_weighted_division(
    store: TradingStore,
) -> None:
    """Two fills under one commitment average by cost, not by price.

    `AverageCost.per_unit` is the domain's own division and is reused rather than
    recomputed here — a second definition of "the average entry" would be the one
    figure nobody could reconcile against the pair it came from.
    """
    outcome = recorded(store)
    recorded(
        store,
        entry_price=Decimal("62000"),
        occurred_at=AT(11),
        written_at=AT(12),
        committed_at=outcome.view.plan.committed_at,
    )
    view = _view(store, outcome.plan_id)
    assert len(view.fills) == 2
    assert view.entry_price == Decimal("61000")
    assert view.position.average_entry.arithmetic == "61000 ÷ 1"


def test_capital_at_risk_and_the_pair_are_both_derived(store: TradingStore) -> None:
    view = _view(store, recorded(store).plan_id)
    assert view.capital_at_risk == Money(Decimal("800"), USDT)
    assert isinstance(view.planned_risk_reward, RiskRewardReading)
    assert view.planned_risk_reward.ratio == Decimal("2.5")


def test_a_commitment_with_no_target_has_no_pair_and_warns(
    store: TradingStore,
) -> None:
    view = _view(store, recorded(store, targets=()).plan_id)
    assert isinstance(view.planned_risk_reward, Absent)
    assert any(warning.code == "TC-W7" for warning in view.warnings)


def test_the_fills_carry_the_account_and_the_correction_state(
    store: TradingStore,
) -> None:
    view = _view(store, recorded(store).plan_id)
    fill = view.fills[0]
    assert fill.account == ACCOUNT.value
    assert fill.was_corrected is False
    assert fill.consideration == Money(Decimal("30000"), USDT)


def test_accounts_are_reported_as_the_set_the_fills_actually_used(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    closed(
        store,
        plan_id,
        quantity=Quantity(Decimal("0.2"), BTC),
        account=AccountId("binance_margin"),
    )
    view = _view(store, plan_id, at=AT(10, day=14))
    assert view.accounts == ("binance_margin", "binance_spot")


# --------------------------------------------------------------------------
# Fill selection.
# --------------------------------------------------------------------------


def test_only_fills_carrying_the_plan_id_are_folded(store: TradingStore) -> None:
    """Two commitments in one market and one book must not fold into each other."""
    first = recorded(store)
    second = recorded(
        store,
        entry_price=Decimal("61000"),
        occurred_at=AT(13),
        written_at=AT(14),
        committed_at=AT(13),
    )
    assert len(_view(store, first.plan_id, at=AT(14)).fills) == 1
    assert len(_view(store, second.plan_id, at=AT(14)).fills) == 1


def test_a_fill_with_no_plan_id_belongs_to_no_recorded_trade(
    store: TradingStore,
) -> None:
    """A fill imported without a commitment is invisible to every recorded trade."""
    from trade_domain_helpers import trade

    plan_id = recorded(store).plan_id
    store.trades.create(
        trade(occurred_at=AT(13), price=Decimal("61000")),
        request=write_request(),
    )
    assert len(store.ledger.resolved()) == 2
    assert len(_view(store, plan_id, at=AT(14)).fills) == 1


def test_fills_for_plan_is_a_pure_filter_over_a_resolved_stream(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    resolved = store.ledger.resolved()
    assert len(fills_for_plan(resolved, plan_id)) == 1
    assert fills_for_plan(resolved, "trade_plan-x-20260812T100000Z-0123456789abcdef") == ()


# --------------------------------------------------------------------------
# The warnings.
# --------------------------------------------------------------------------


def test_a_reduced_position_says_the_risk_figure_describes_the_maximum(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    closed(store, plan_id, quantity=Quantity(Decimal("0.2"), BTC))
    view = _view(store, plan_id, at=AT(10, day=14))
    assert any(warning.code == "TC-W5" for warning in view.warnings)
    assert view.position.max_exposure == Quantity(Decimal("0.5"), BTC)


def test_fills_in_two_accounts_are_warned_about(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    closed(
        store,
        plan_id,
        quantity=Quantity(Decimal("0.2"), BTC),
        account=AccountId("binance_margin"),
    )
    view = _view(store, plan_id, at=AT(10, day=14))
    assert any(warning.code == "TC-W3" for warning in view.warnings)


def test_an_expired_commitment_with_an_open_position_is_warned_about(
    store: TradingStore,
) -> None:
    plan_id = recorded(store, expires_at=AT(9, day=13)).plan_id
    view = _view(store, plan_id, at=AT(9, day=14))
    assert any(warning.code == "TC-W6" for warning in view.warnings)


def test_an_expired_commitment_that_is_already_flat_is_not_warned_about(
    store: TradingStore,
) -> None:
    plan_id = recorded(store, expires_at=AT(9, day=13)).plan_id
    closed(store, plan_id)
    view = _view(store, plan_id, at=AT(9, day=20))
    assert not any(warning.code == "TC-W6" for warning in view.warnings)


def test_an_empty_journal_is_the_discipline_metric_and_is_reported(
    store: TradingStore,
) -> None:
    view = _view(store, recorded(store).plan_id)
    assert any(warning.code == "TC-W8" for warning in view.warnings)


def test_writing_a_note_clears_the_discipline_warning(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    append_note(store, note_request(plan_id))
    view = _view(store, plan_id, at=AT(13))
    assert not any(warning.code == "TC-W8" for warning in view.warnings)


def test_an_entry_that_drifted_past_its_stop_refuses_a_risk_figure(
    store: TradingStore,
) -> None:
    """Adding to a loser below the stop is real, and the number then does not exist."""
    from trade_domain_helpers import trade

    outcome = recorded(store, stop=Decimal("59000"), targets=(Decimal("64000"),))
    # `record_trade` refuses this add, and rightly: an entry below the stop is a
    # commitment the owner cannot have meant. It still *reaches* the store by
    # other routes — a statement import, a hand-written record — so the read path
    # must report the absence rather than a plausible negative distance.
    store.trades.create(
        trade(
            occurred_at=AT(13),
            price=Decimal("57000"),
            quantity=Quantity(Decimal("2"), BTC),
            plan_id=outcome.plan_id,
        ),
        request=write_request(),
    )
    view = _view(store, outcome.plan_id, at=AT(14))
    assert isinstance(view.capital_at_risk, Absent)
    assert isinstance(view.planned_risk_reward, Absent)
    assert any(warning.code == "TC-W1" for warning in view.warnings)


def test_a_flip_folds_into_two_round_trips_and_says_so(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    closed(store, plan_id, quantity=Quantity(Decimal("0.5"), BTC))
    recorded(
        store,
        occurred_at=AT(11, day=15),
        written_at=AT(12, day=15),
        committed_at=_view(store, plan_id, at=AT(12, day=15)).plan.committed_at,
    )
    view = _view(store, plan_id, at=AT(12, day=15))
    assert any(warning.code == "TC-W2" for warning in view.warnings)


def test_a_correction_to_a_fill_is_reported_on_the_page(store: TradingStore) -> None:
    from trade_domain_helpers import correction

    plan_id = recorded(store).plan_id
    original = store.ledger.resolved()[0].trade
    replacement = store.trades.load(original.event_id)
    corrected = _corrected(replacement)
    store.trades.replace(
        original.event_id,
        correction=correction(original, corrected, occurred_at=AT(13)),
        request=write_request(),
    )
    view = _view(store, plan_id, at=AT(14))
    assert view.fills[0].was_corrected is True
    assert any(warning.code == "TC-W4" for warning in view.warnings)


def _corrected(trade):
    """The same fill with a different quantity, keeping its plan link."""
    from dataclasses import replace as _replace

    return _replace(trade, quantity=Quantity(Decimal("0.6"), BTC))


def test_the_warning_order_is_fixed_rather_than_ranked(store: TradingStore) -> None:
    plan_id = recorded(store, targets=()).plan_id
    codes = [warning.code for warning in _view(store, plan_id).warnings]
    assert codes == sorted(codes)


# --------------------------------------------------------------------------
# Loading and refusals.
# --------------------------------------------------------------------------


def test_loading_a_trade_that_is_not_stored_names_the_command_that_lists_them(
    store: TradingStore,
) -> None:
    with pytest.raises(TradeNotFoundError, match="fmits trade list"):
        load_plan(store, "trade_plan-x-20260812T100000Z-0123456789abcdef")


def test_loading_refuses_something_that_is_not_a_store() -> None:
    with pytest.raises(TypeError, match="must be a TradingStore"):
        load_plan("a store", "x")  # type: ignore[arg-type]


def test_loading_refuses_a_missing_dust_policy(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    with pytest.raises(TypeError, match="DustPolicy"):
        load_trade(store, plan_id, dust=None, at=AT_READ)  # type: ignore[arg-type]


def test_the_subject_kinds_match_the_persisted_record_kinds() -> None:
    assert PLAN_SUBJECT_KIND == "trade_plan"
    assert TRADE_SUBJECT_KIND == "trade"


def test_the_invariant_limitations_are_five_and_carry_codes() -> None:
    assert len(CAPTURE_LIMITATIONS) == 5
    assert [code for code, _ in CAPTURE_LIMITATIONS] == [
        "TC-1", "TC-2", "TC-3", "TC-4", "TC-5",
    ]


# --------------------------------------------------------------------------
# The listing.
# --------------------------------------------------------------------------


def test_an_empty_store_lists_nothing_and_says_so(store: TradingStore) -> None:
    listing = list_trades(store, dust=CAPTURE_DUST_POLICY, at=AT_READ)
    assert listing.rows == ()
    assert listing.total == 0
    assert listing.excluded == 0


def test_every_recorded_trade_appears_once(store: TradingStore) -> None:
    recorded(store)
    recorded(store, entry_price=Decimal("61000"), occurred_at=AT(13), written_at=AT(14))
    listing = list_trades(store, dust=CAPTURE_DUST_POLICY, at=AT(14))
    assert len(listing.rows) == 2
    assert listing.total == 2


def test_rows_are_ordered_by_when_the_commitment_was_made(
    store: TradingStore,
) -> None:
    recorded(store, occurred_at=AT(14), written_at=AT(15))
    recorded(store, occurred_at=AT(10), written_at=AT(15))
    listing = list_trades(store, dust=CAPTURE_DUST_POLICY, at=AT(15))
    assert [row.committed_at for row in listing.rows] == [AT(10), AT(14)]


def test_a_row_carries_the_figures_already_computed(store: TradingStore) -> None:
    recorded(store)
    row = list_trades(store, dust=CAPTURE_DUST_POLICY, at=AT_READ).rows[0]
    assert row.market == MARKET
    assert row.direction is TradeDirection.LONG
    assert row.stop == Decimal("58400")
    assert row.first_target == Decimal("64000")
    assert row.capital_at_risk == Money(Decimal("800"), USDT)


@pytest.mark.parametrize(
    "filters, expected",
    [
        (TradeFilters(status=CaptureStatus.OPEN), 1),
        (TradeFilters(status=CaptureStatus.CLOSED), 0),
        (TradeFilters(symbol="BTCUSDT"), 1),
        (TradeFilters(symbol="btcusdt"), 1),
        (TradeFilters(symbol="ETHUSDT"), 0),
        (TradeFilters(account="binance_spot"), 1),
        (TradeFilters(account="kraken_spot"), 0),
        (TradeFilters(direction=TradeDirection.LONG), 1),
        (TradeFilters(direction=TradeDirection.SHORT), 0),
        (TradeFilters(since=AT(9)), 1),
        (TradeFilters(since=AT(11)), 0),
        (TradeFilters(until=AT(11)), 1),
        (TradeFilters(until=AT(9)), 0),
    ],
)
def test_each_filter_axis_selects_what_it_names(
    store: TradingStore, filters: TradeFilters, expected: int
) -> None:
    recorded(store)
    listing = list_trades(
        store, dust=CAPTURE_DUST_POLICY, at=AT_READ, filters=filters
    )
    assert len(listing.rows) == expected
    assert listing.total == 1
    assert listing.excluded == 1 - expected


def test_the_market_identity_matches_as_well_as_the_pair_symbol(
    store: TradingStore,
) -> None:
    recorded(store)
    listing = list_trades(
        store,
        dust=CAPTURE_DUST_POLICY,
        at=AT_READ,
        filters=TradeFilters(symbol=MARKET.value),
    )
    assert len(listing.rows) == 1


def test_the_total_counts_everything_recorded_not_everything_shown(
    store: TradingStore,
) -> None:
    recorded(store)
    recorded(
        store,
        market=OTHER_MARKET,
        quantity=Quantity(Decimal("2"), AssetCode("ETH")),
        entry_price=Decimal("3000"),
        stop=Decimal("2800"),
        targets=(Decimal("3400"),),
    )
    listing = list_trades(
        store,
        dust=CAPTURE_DUST_POLICY,
        at=AT_READ,
        filters=TradeFilters(symbol="BTCUSDT"),
    )
    assert len(listing.rows) == 1
    assert listing.total == 2
    assert listing.excluded == 1


def test_the_filters_applied_travel_with_the_listing(store: TradingStore) -> None:
    recorded(store)
    listing = list_trades(
        store,
        dust=CAPTURE_DUST_POLICY,
        at=AT_READ,
        filters=TradeFilters(status=CaptureStatus.OPEN, symbol="BTCUSDT"),
    )
    assert listing.filters.stated == (("status", "open"), ("symbol", "BTCUSDT"))


def test_no_filter_states_nothing(store: TradingStore) -> None:
    assert list_trades(store, dust=CAPTURE_DUST_POLICY, at=AT_READ).filters.stated == ()


def test_a_listing_refuses_something_that_is_not_a_filter(
    store: TradingStore,
) -> None:
    with pytest.raises(TypeError, match="must be a TradeFilters"):
        list_trades(store, dust=CAPTURE_DUST_POLICY, at=AT_READ, filters="open")  # type: ignore[arg-type]


def test_a_filter_window_that_runs_backwards_is_refused() -> None:
    with pytest.raises(ValueError, match="precedes since"):
        TradeFilters(since=AT(12), until=AT(10))
