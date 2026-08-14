"""The text boundary: what the owner typed, and what it is refused for.

Every conversion here is a place a value can be mis-read — a price through a
float, a naive timestamp, a symbol split at the wrong character. This module is
where they are all tested, without a parser and without a store.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from trade_capture_helpers import capture_store, recorded
from trade_domain_helpers import AT, BTC, MARKET, USDT

from fmis.accounts import Book, MarketMode
from fmis.money import AssetCode, Money, Quantity
from fmis.persistence import TradingStore
from fmis.provenance import Absent
from fmis.records import TradeDomainError
from fmis.snapshotting import TradeDirection
from fmis.trade_capture import (
    BOOK_CHOICES,
    CAPTURE_ERRORS,
    DEFAULT_MARKET_MODE,
    DEFAULT_QUOTE_ASSET,
    DEFAULT_VENUE,
    DIRECTION_CHOICES,
    MARKET_MODE_CHOICES,
    STATUS_CHOICES,
    CaptureStatus,
    TradeCaptureError,
    capture_store_root,
    close_request_from_text,
    filters_from_text,
    note_request_from_text,
    open_store,
    record_request_from_text,
)

FILED = AT(11)

REQUIRED = {
    "symbol": "BTCUSDT",
    "direction": "long",
    "account": "binance_spot",
    "book": "swing",
    "entry": "60000",
    "stop": "58400",
    "size": "0.5",
    "fee": "15",
    "fx_rate": "10.5",
    "fx_source": "riksbank",
    "confidence": "moderate",
    "author": "owner",
    "filed_at": FILED,
}


def _request(**overrides):
    values = dict(REQUIRED)
    values.update(overrides)
    return record_request_from_text(**values)


@pytest.fixture()
def store(tmp_path: Path) -> TradingStore:
    return capture_store(tmp_path)


# --------------------------------------------------------------------------
# The choices a surface offers.
# --------------------------------------------------------------------------


def test_the_choices_are_derived_from_the_enums_not_retyped() -> None:
    assert BOOK_CHOICES == tuple(book.value for book in Book)
    assert MARKET_MODE_CHOICES == tuple(mode.value for mode in MarketMode)
    assert STATUS_CHOICES == tuple(state.value for state in CaptureStatus)


def test_no_trade_is_not_offered_as_a_direction() -> None:
    """A decision not to act has no stop to be wrong about."""
    assert DIRECTION_CHOICES == ("long", "short")
    assert "no_trade" not in DIRECTION_CHOICES


def test_the_defaults_name_the_only_venue_this_repository_has() -> None:
    assert DEFAULT_VENUE == "binance"
    assert DEFAULT_QUOTE_ASSET == "USDT"
    assert DEFAULT_MARKET_MODE == "spot"


def test_the_error_tuple_covers_both_layers_a_refusal_can_come_from() -> None:
    assert TradeCaptureError in CAPTURE_ERRORS
    assert TradeDomainError in CAPTURE_ERRORS


# --------------------------------------------------------------------------
# The store.
# --------------------------------------------------------------------------


def test_opening_a_store_on_a_missing_path_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "never-used"
    store = open_store(root)
    assert store.root == root
    assert not root.exists()


def test_opening_a_store_with_no_root_reaches_the_owners_own() -> None:
    """Asserted without touching it: this test must never write to the real store."""
    assert open_store(None).root == capture_store_root()


def test_the_store_folds_on_the_capture_packages_dust_policy(tmp_path: Path) -> None:
    from fmis.trade_capture import CAPTURE_DUST_POLICY

    assert open_store(tmp_path).dust == CAPTURE_DUST_POLICY


# --------------------------------------------------------------------------
# Recording.
# --------------------------------------------------------------------------


def test_a_complete_set_of_strings_becomes_a_valid_request() -> None:
    request = _request()
    assert request.market == MARKET
    assert request.book is Book.SWING
    assert request.direction is TradeDirection.LONG
    assert request.entry_price == Decimal("60000")
    assert request.quantity == Quantity(Decimal("0.5"), BTC)
    assert request.fee == Money(Decimal("15"), USDT)


def test_a_size_is_denominated_in_the_markets_base_asset() -> None:
    assert _request().quantity.asset == BTC


def test_a_fee_defaults_to_the_markets_quote_asset() -> None:
    assert _request().fee.asset == USDT


def test_a_fee_may_name_its_own_asset() -> None:
    request = _request(fee_asset="bnb", fee_fx_rate="6100")
    assert request.fee.asset == AssetCode("BNB")


def test_targets_are_taken_in_the_order_they_were_stated() -> None:
    request = _request(targets=["64000", "68000"])
    assert request.targets == (Decimal("64000"), Decimal("68000"))


def test_no_target_is_an_empty_ladder_rather_than_a_failure() -> None:
    assert _request(targets=None).targets == ()


@pytest.mark.parametrize("field", ["entry", "stop", "size", "fee", "fx_rate"])
def test_a_value_that_is_not_a_number_is_refused(field: str) -> None:
    with pytest.raises(TradeCaptureError, match="not a decimal number"):
        _request(**{field: "sixty thousand"})


@pytest.mark.parametrize("field", ["entry", "stop", "size"])
def test_an_empty_value_is_refused(field: str) -> None:
    with pytest.raises(TradeCaptureError, match="is required"):
        _request(**{field: ""})


def test_an_infinite_price_is_refused() -> None:
    with pytest.raises(TradeCaptureError, match="not a finite number"):
        _request(entry="Infinity")


def test_a_price_never_passes_through_a_float() -> None:
    """`Decimal('0.1')` and `Decimal(0.1)` are two different records."""
    assert _request(entry="0.1", stop="0.05").entry_price == Decimal("0.1")


def test_an_unknown_book_is_refused_with_the_legal_set_named() -> None:
    with pytest.raises(TradeCaptureError, match="not one of"):
        _request(book="scalping")


def test_an_unknown_market_mode_is_refused() -> None:
    with pytest.raises(TradeCaptureError, match="not one of"):
        _request(mode="options")


def test_a_direction_that_is_not_a_side_is_refused() -> None:
    with pytest.raises(TradeCaptureError, match="commits to a side"):
        _request(direction="no_trade")


def test_an_unknown_direction_is_refused() -> None:
    with pytest.raises(TradeCaptureError, match="not one of"):
        _request(direction="sideways")


def test_a_symbol_that_does_not_end_in_the_quote_is_refused() -> None:
    with pytest.raises(TradeCaptureError, match="will not guess the split"):
        _request(symbol="BTCUSDT", quote="USDC")


# --------------------------------------------------------------------------
# Instants.
# --------------------------------------------------------------------------


def test_an_omitted_instant_falls_back_to_the_filing_time() -> None:
    assert _request().occurred_at == FILED


def test_a_stated_instant_is_normalised_to_utc() -> None:
    request = _request(occurred_at="2026-08-12T12:00:00+02:00")
    assert request.occurred_at == datetime(2026, 8, 12, 10, tzinfo=timezone.utc)


def test_a_naive_instant_is_refused_rather_than_assumed_local() -> None:
    with pytest.raises(TradeCaptureError, match="timezone-aware"):
        _request(occurred_at="2026-08-12T10:00:00")


def test_an_instant_that_is_not_a_timestamp_is_refused() -> None:
    with pytest.raises(TradeCaptureError, match="not an ISO-8601 timestamp"):
        _request(occurred_at="yesterday")


def test_an_omitted_optional_instant_becomes_an_absence_with_a_reason() -> None:
    expires = _request().expires_at
    assert isinstance(expires, Absent)
    assert "does not expire" in expires.reason


def test_a_stated_expiry_is_carried_through() -> None:
    request = _request(expires="2026-08-20T09:00:00+00:00", occurred_at="2026-08-12T10:00:00+00:00")
    assert request.expires_at == datetime(2026, 8, 20, 9, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Optional text.
# --------------------------------------------------------------------------


def test_an_omitted_optional_string_becomes_an_absence_with_a_reason() -> None:
    request = _request()
    for value, phrase in (
        (request.thesis, "no thesis"),
        (request.setup_type, "no setup type"),
        (request.proposal_id, "not proposed"),
        (request.market_snapshot_id, "no market context"),
        (request.note, "no note"),
    ):
        assert isinstance(value, Absent)
        assert phrase in value.reason


def test_analysis_citations_are_carried_through_verbatim() -> None:
    record_id = "workspace-BTCUSDT-20260812T090000Z-0123456789abcdef"
    assert _request(analysis=[record_id]).analysis_record_ids == (record_id,)


def test_the_code_version_defaults_to_the_installed_build() -> None:
    assert _request().code_version == fmis_version()


def fmis_version() -> str:
    import fmis

    return fmis.__version__


# --------------------------------------------------------------------------
# Closing.
# --------------------------------------------------------------------------


def test_a_close_resolves_its_defaults_against_the_stored_commitment(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    request = close_request_from_text(
        store,
        plan_id=plan_id,
        price="63800",
        fee="16",
        fx_rate="10.6",
        fx_source="riksbank",
        reason="target_reached",
        author="owner",
        filed_at=AT(10, day=14),
    )
    assert request.fee.asset == USDT
    assert isinstance(request.quantity, Absent)
    assert isinstance(request.account, Absent)


def test_a_close_size_is_denominated_in_the_commitments_base_asset(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    request = close_request_from_text(
        store,
        plan_id=plan_id,
        price="63800",
        fee="16",
        fx_rate="10.6",
        fx_source="riksbank",
        reason="target_reached",
        author="owner",
        filed_at=AT(10, day=14),
        size="0.2",
    )
    assert request.quantity == Quantity(Decimal("0.2"), BTC)


def test_a_close_against_a_trade_that_is_not_stored_is_refused(
    store: TradingStore,
) -> None:
    from fmis.trade_capture import TradeNotFoundError

    with pytest.raises(TradeNotFoundError):
        close_request_from_text(
            store,
            plan_id="trade_plan-x-20260812T100000Z-0123456789abcdef",
            price="1",
            fee="0",
            fx_rate="1",
            fx_source="riksbank",
            reason="stopped_out",
            author="owner",
            filed_at=FILED,
        )


# --------------------------------------------------------------------------
# Notes and filters.
# --------------------------------------------------------------------------


def test_a_note_defaults_its_written_instant_to_the_filing_time() -> None:
    request = note_request_from_text(
        plan_id="trade_plan-x-20260812T100000Z-0123456789abcdef",
        body="a thought",
        author="owner",
        filed_at=FILED,
    )
    assert request.recorded_at == FILED
    assert isinstance(request.title, Absent)


def test_an_empty_filter_set_filters_on_nothing() -> None:
    assert filters_from_text().stated == ()


def test_every_filter_axis_is_parsed() -> None:
    filters = filters_from_text(
        status="open",
        symbol="BTCUSDT",
        account="binance_spot",
        direction="short",
        since="2026-08-01T00:00:00+00:00",
        until="2026-08-31T00:00:00+00:00",
    )
    assert filters.status is CaptureStatus.OPEN
    assert filters.direction is TradeDirection.SHORT
    assert filters.since == datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert filters.until == datetime(2026, 8, 31, tzinfo=timezone.utc)


def test_an_unknown_status_filter_is_refused() -> None:
    with pytest.raises(TradeCaptureError, match="not one of"):
        filters_from_text(status="pending")


def test_a_naive_filter_boundary_is_refused() -> None:
    with pytest.raises(TradeCaptureError, match="timezone-aware"):
        filters_from_text(since="2026-08-01")
