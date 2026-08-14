"""The value types: what each one refuses to be constructed as.

Nothing here touches a store. These are the invariants that keep a view from
reporting something the records do not say — a status that disagrees with the
fill list, a listing that shows more rows than it counted, an outcome that wrote
nothing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from trade_domain_helpers import ACCOUNT, AT, BTC, MARKET, USDT, trade_plan

from fmis.accounts import Book
from fmis.journal import TradeJournal
from fmis.ledger import TradeSide
from fmis.money import Money, Quantity
from fmis.provenance import Absent
from fmis.snapshotting import TradeDirection
from fmis.trade_capture import (
    CaptureOutcome,
    CaptureRefusedError,
    CaptureStatus,
    CaptureWarning,
    FillLine,
    TradeCaptureError,
    TradeFilters,
    TradeListing,
    TradeNotFoundError,
    TradeRow,
    TradeView,
    WrittenRecord,
)

EMPTY_JOURNAL = TradeJournal(subject_kind="trade_plan", subject_id="x", entries=())


def _fill(**overrides) -> FillLine:
    values = {
        "event_id": "trade-binance_BTCUSDT_spot-20260812T100000Z-0123456789abcdef",
        "occurred_at": AT(10),
        "side": TradeSide.BUY,
        "quantity": Quantity(Decimal("0.5"), BTC),
        "price": Decimal("60000"),
        "fee": Money(Decimal("15"), USDT),
        "account": ACCOUNT.value,
        "was_corrected": False,
    }
    values.update(overrides)
    return FillLine(**values)


def _view(**overrides) -> TradeView:
    values = {
        "plan": trade_plan(),
        "status": CaptureStatus.PLANNED,
        "fills": (),
        "position": Absent("nothing has filled against this commitment"),
        "entry_price": Absent("no fill has established an average entry"),
        "capital_at_risk": Absent("no fill has established an average entry"),
        "planned_risk_reward": Absent("no fill has established an average entry"),
        "journal": EMPTY_JOURNAL,
        "accounts": (),
    }
    values.update(overrides)
    return TradeView(**values)


# --------------------------------------------------------------------------
# The error hierarchy.
# --------------------------------------------------------------------------


def test_every_capture_failure_is_catchable_as_one_group() -> None:
    for error in (CaptureRefusedError, TradeNotFoundError):
        assert issubclass(error, TradeCaptureError)


def test_a_refusal_and_a_missing_record_are_different_classes() -> None:
    """The owner's remedy differs: one is a mistyped id, the other a mis-stated trade."""
    assert not issubclass(TradeNotFoundError, CaptureRefusedError)
    assert not issubclass(CaptureRefusedError, TradeNotFoundError)


# --------------------------------------------------------------------------
# Status.
# --------------------------------------------------------------------------


def test_planned_is_a_state_of_its_own_and_not_a_kind_of_closed() -> None:
    """*How often do I plan and not act* is unanswerable if the two are merged."""
    assert {state.value for state in CaptureStatus} == {"planned", "open", "closed"}


def test_no_status_is_stored_on_any_record() -> None:
    from fmis.plan import TradePlan

    assert "status" not in TradePlan.__dataclass_fields__


# --------------------------------------------------------------------------
# The view.
# --------------------------------------------------------------------------


def test_a_planned_view_holds_no_fill_and_says_why() -> None:
    view = _view()
    assert view.status is CaptureStatus.PLANNED
    assert isinstance(view.realized_pnl_net, Absent)
    assert isinstance(view.open_quantity, Absent)


def test_a_status_that_disagrees_with_the_fills_is_refused() -> None:
    with pytest.raises(ValueError, match="two places"):
        _view(status=CaptureStatus.OPEN)


def test_a_planned_view_with_fills_is_refused() -> None:
    with pytest.raises(ValueError, match="two places"):
        _view(fills=(_fill(),))


def test_the_view_refuses_a_plan_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="must be a TradePlan"):
        _view(plan="a plan")


def test_the_view_refuses_a_journal_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="must be a TradeJournal"):
        _view(journal=())


def test_the_view_refuses_a_position_that_is_neither_folded_nor_absent() -> None:
    with pytest.raises(TypeError, match="Position or Absent"):
        _view(position="open")


def test_the_view_forwards_the_plans_own_id() -> None:
    plan = trade_plan()
    assert _view(plan=plan).plan_id == plan.plan_id


# --------------------------------------------------------------------------
# A fill line.
# --------------------------------------------------------------------------


def test_a_fill_line_computes_its_consideration_as_a_product() -> None:
    assert _fill().consideration == Money(Decimal("30000"), USDT)


def test_a_fill_line_refuses_a_price_that_is_not_exact() -> None:
    with pytest.raises(TypeError, match="must be a Decimal"):
        _fill(price=60000.0)


def test_a_fill_line_refuses_a_size_that_is_not_a_quantity() -> None:
    with pytest.raises(TypeError, match="must be a Quantity"):
        _fill(quantity=Decimal("0.5"))


def test_a_fill_line_refuses_a_naive_instant() -> None:
    from datetime import datetime

    with pytest.raises(Exception):
        _fill(occurred_at=datetime(2026, 8, 12, 10))


def test_a_fill_line_refuses_a_correction_flag_that_is_not_a_bool() -> None:
    with pytest.raises(TypeError, match="must be a bool"):
        _fill(was_corrected="yes")


# --------------------------------------------------------------------------
# Written records.
# --------------------------------------------------------------------------


def test_a_written_record_reports_whether_anything_was_created() -> None:
    record = WrittenRecord(
        kind="trade_plan", record_id="x", created=True, relative_path="records/x.json"
    )
    assert record.created is True


def test_a_written_record_refuses_a_created_flag_that_is_not_a_bool() -> None:
    with pytest.raises(TypeError, match="must be a bool"):
        WrittenRecord(kind="k", record_id="x", created="yes", relative_path="p")


# --------------------------------------------------------------------------
# The outcome.
# --------------------------------------------------------------------------


def _outcome(**overrides) -> CaptureOutcome:
    values = {
        "action": "recorded",
        "written": (
            WrittenRecord(
                kind="trade_plan", record_id="x", created=True, relative_path="p"
            ),
        ),
        "view": _view(),
    }
    values.update(overrides)
    return CaptureOutcome(**values)


def test_an_outcome_that_wrote_nothing_is_refused() -> None:
    """A command that reported success and named no record would be a lie."""
    with pytest.raises((ValueError, TypeError)):
        _outcome(written=())


def test_an_outcome_knows_when_every_record_was_already_stored() -> None:
    already = WrittenRecord(
        kind="trade_plan", record_id="x", created=False, relative_path="p"
    )
    assert _outcome(written=(already,)).was_already_stored is True
    assert _outcome().was_already_stored is False


def test_a_partly_created_outcome_is_not_an_idempotent_re_entry() -> None:
    records = (
        WrittenRecord(kind="trade_plan", record_id="x", created=False, relative_path="p"),
        WrittenRecord(kind="trade", record_id="y", created=True, relative_path="q"),
    )
    assert _outcome(written=records).was_already_stored is False


# --------------------------------------------------------------------------
# Rows, filters and listings.
# --------------------------------------------------------------------------


def _row(**overrides) -> TradeRow:
    values = {
        "plan_id": "trade_plan-x-20260812T100000Z-0123456789abcdef",
        "committed_at": AT(10),
        "market": MARKET,
        "book": Book.SWING,
        "direction": TradeDirection.LONG,
        "status": CaptureStatus.OPEN,
        "stop": Decimal("58400"),
        "first_target": Decimal("64000"),
        "accounts": (ACCOUNT.value,),
        "capital_at_risk": Money(Decimal("800"), USDT),
        "realized_pnl_net": Absent("still open"),
    }
    values.update(overrides)
    return TradeRow(**values)


def test_a_row_accepts_an_absent_target() -> None:
    assert isinstance(_row(first_target=Absent("no target")).first_target, Absent)


def test_a_row_refuses_a_stop_that_is_not_exact() -> None:
    with pytest.raises(TypeError, match="must be a Decimal"):
        _row(stop=58400.0)


def test_a_row_refuses_a_money_figure_that_is_neither_money_nor_absent() -> None:
    with pytest.raises(TypeError, match="Money or Absent"):
        _row(capital_at_risk="800")


def test_a_listing_states_what_it_excluded() -> None:
    listing = TradeListing(rows=(_row(),), filters=TradeFilters(), total=4)
    assert listing.excluded == 3


def test_a_listing_showing_more_than_it_counted_is_refused() -> None:
    with pytest.raises(ValueError, match="out of a stated total"):
        TradeListing(rows=(_row(), _row()), filters=TradeFilters(), total=1)


def test_a_listing_refuses_a_filter_set_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="must be a TradeFilters"):
        TradeListing(rows=(), filters="open", total=0)


def test_the_filters_report_only_the_axes_actually_applied() -> None:
    filters = TradeFilters(status=CaptureStatus.OPEN, account="binance_spot")
    assert filters.stated == (("status", "open"), ("account", "binance_spot"))


def test_the_filter_axes_are_reported_in_a_fixed_order() -> None:
    filters = TradeFilters(
        direction=TradeDirection.LONG,
        symbol="BTCUSDT",
        status=CaptureStatus.OPEN,
        account="binance_spot",
    )
    assert [axis for axis, _ in filters.stated] == [
        "status", "symbol", "account", "direction"
    ]


def test_a_filter_refuses_an_empty_string_it_would_match_nothing_with() -> None:
    with pytest.raises((TypeError, ValueError)):
        TradeFilters(symbol="")


# --------------------------------------------------------------------------
# Warnings.
# --------------------------------------------------------------------------


def test_a_warning_carries_a_code_and_a_statement_and_nothing_else() -> None:
    """No severity: this layer produces no ranking, and severity is where one starts."""
    assert set(CaptureWarning.__dataclass_fields__) == {"code", "statement"}


def test_a_warning_refuses_an_empty_statement() -> None:
    with pytest.raises((TypeError, ValueError)):
        CaptureWarning(code="TC-W1", statement="")


def test_warnings_sort_by_code() -> None:
    first = CaptureWarning("TC-W1", "a")
    second = CaptureWarning("TC-W2", "b")
    assert sorted((second, first)) == [first, second]


# --------------------------------------------------------------------------
# Type guards. Defensive, and exercised so they cannot rot into always-true.
# --------------------------------------------------------------------------


def test_a_fill_line_refuses_a_fee_that_is_not_money() -> None:
    with pytest.raises(TypeError, match="must be a Money"):
        _fill(fee=Decimal("15"))


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("entry_price", 60000.0, "Decimal or Absent"),
        ("capital_at_risk", "800 USDT", "Money or Absent"),
        ("planned_risk_reward", "2.5", "RiskRewardReading or Absent"),
    ],
)
def test_the_view_refuses_a_derived_figure_of_the_wrong_type(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(TypeError, match=message):
        _view(**{field: value})


def test_a_row_refuses_a_market_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="must be a MarketId"):
        _row(market="binance:BTCUSDT:spot")


def test_a_row_refuses_a_target_of_the_wrong_type() -> None:
    with pytest.raises(TypeError, match="Decimal or Absent"):
        _row(first_target=64000.0)


def test_an_outcome_refuses_a_view_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="must be a TradeView"):
        _outcome(view="a trade")
