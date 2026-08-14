"""The three write paths, and everything they refuse to record.

`record_trade`, `close_trade` and `append_note`. What matters here is not that a
record reaches disk — the store's own suite proves that — but that **nothing
reaches disk when the owner's numbers cannot all be true at once**, and that
re-running a command never records a second trade.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from trade_capture_helpers import (
    CODE_VERSION,
    capture_store,
    close_request,
    closed,
    note_request,
    record_request,
    recorded,
)
from trade_domain_helpers import ACCOUNT, AT, BTC, MARKET, OTHER_MARKET, USDT

from fmis.accounts import AccountId, Book, MarketMode
from fmis.journal import JournalKind, LinkKind, TagOrigin
from fmis.ledger import TradeSide
from fmis.money import AssetCode, Money, Quantity
from fmis.persistence import TradingStore
from fmis.plan import PlanPlacementError, TradePlan
from fmis.provenance import Absent
from fmis.records import DomainValidationError
from fmis.snapshotting import TradeDirection
from fmis.trade_capture import (
    CAPTURE_DUST_POLICY,
    CLOSE_REASON,
    NOTE_REASON,
    RECORD_REASON,
    CaptureRefusedError,
    CaptureStatus,
    CloseRequest,
    NoteRequest,
    RecordRequest,
    TradeNotFoundError,
    append_note,
    capture_version_set,
    close_trade,
    load_trade,
    market_from_symbol,
    record_trade,
)
from fmis.versioning import VersionAxis


@pytest.fixture()
def store(tmp_path: Path) -> TradingStore:
    return capture_store(tmp_path)


# --------------------------------------------------------------------------
# Recording the happy path.
# --------------------------------------------------------------------------


def test_recording_writes_a_commitment_a_fill_and_nothing_else(
    store: TradingStore,
) -> None:
    outcome = recorded(store)
    assert [record.kind for record in outcome.written] == ["trade_plan", "trade"]
    assert all(record.created for record in outcome.written)
    assert outcome.action == "recorded"


def test_a_thesis_becomes_a_journal_entry_and_not_a_field(
    store: TradingStore,
) -> None:
    """§11.6 routes *thesis, reasoning, emotion* to `JournalEntry` by name."""
    outcome = recorded(store, thesis="the weekly retest held")
    assert [record.kind for record in outcome.written] == [
        "trade_plan",
        "trade",
        "journal_entry",
    ]
    assert "thesis" not in TradePlan.__dataclass_fields__
    entry = outcome.view.journal.entries[0]
    assert entry.kind is JournalKind.IDEA
    assert entry.body == "the weekly retest held"


def test_the_fill_carries_the_commitment_it_was_taken_under(
    store: TradingStore,
) -> None:
    outcome = recorded(store)
    fill = store.ledger.resolved()[0].trade
    assert fill.plan_id == outcome.plan_id
    assert fill.side is TradeSide.BUY
    assert fill.quantity == Quantity(Decimal("0.5"), BTC)
    assert fill.price == Decimal("60000")


def test_a_short_commitment_records_a_sell_as_its_entry(store: TradingStore) -> None:
    recorded(
        store,
        direction=TradeDirection.SHORT,
        stop=Decimal("62000"),
        targets=(Decimal("55000"),),
    )
    assert store.ledger.resolved()[0].trade.side is TradeSide.SELL


def test_the_thesis_entry_links_to_both_the_commitment_and_the_fill(
    store: TradingStore,
) -> None:
    outcome = recorded(store, thesis="a reason")
    entry = outcome.view.journal.entries[0]
    targets = {(link.target_kind, link.target_id) for link in entry.links}
    assert ("trade_plan", outcome.plan_id) in targets
    assert any(kind == "trade" for kind, _ in targets)
    assert {link.kind for link in entry.links} == {LinkKind.ABOUT}


def test_the_view_returned_reports_the_position_the_write_produced(
    store: TradingStore,
) -> None:
    view = recorded(store).view
    assert view.status is CaptureStatus.OPEN
    assert view.capital_at_risk == Money(Decimal("800"), USDT)
    assert view.entry_price == Decimal("60000")


def test_a_trade_recorded_without_a_thesis_leaves_the_journal_empty(
    store: TradingStore,
) -> None:
    """The discipline metric works only if it can read empty."""
    view = recorded(store).view
    assert view.journal.is_empty is True
    assert any(warning.code == "TC-W8" for warning in view.warnings)


# --------------------------------------------------------------------------
# Idempotency.
# --------------------------------------------------------------------------


def test_recording_the_identical_trade_twice_records_it_once(
    store: TradingStore,
) -> None:
    first = recorded(store, thesis="a reason")
    second = recorded(store, thesis="a reason")
    assert first.plan_id == second.plan_id
    assert second.was_already_stored is True
    assert store.plans.count() == 1
    assert len(store.ledger.resolved()) == 1


def test_an_idempotent_re_entry_appends_no_journal_event(
    store: TradingStore,
) -> None:
    recorded(store)
    before = len(store.write_journal.events())
    recorded(store)
    assert len(store.write_journal.events()) == before


def test_two_genuinely_different_trades_are_two_records(
    store: TradingStore,
) -> None:
    recorded(store)
    recorded(store, entry_price=Decimal("60500"), occurred_at=AT(12), written_at=AT(13))
    assert store.plans.count() == 2
    assert len(store.ledger.resolved()) == 2


# --------------------------------------------------------------------------
# What recording refuses.
# --------------------------------------------------------------------------


def test_a_stop_on_the_wrong_side_of_the_entry_is_refused(
    store: TradingStore,
) -> None:
    with pytest.raises(PlanPlacementError, match="is not below the entry"):
        recorded(store, stop=Decimal("61000"), targets=(Decimal("64000"),))


def test_a_refused_trade_writes_nothing_at_all(store: TradingStore) -> None:
    """Validation precedes publication, so a refusal leaves no orphan commitment."""
    with pytest.raises(PlanPlacementError):
        recorded(store, stop=Decimal("61000"), targets=(Decimal("64000"),))
    assert store.plans.count() == 0
    assert store.ledger.resolved() == ()
    assert store.journals.count() == 0


def test_a_size_in_the_quote_asset_is_refused(store: TradingStore) -> None:
    with pytest.raises(CaptureRefusedError, match="base asset"):
        recorded(store, quantity=Quantity(Decimal("30000"), USDT))


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-0.5")])
def test_a_size_that_is_not_positive_is_refused(amount: Decimal) -> None:
    with pytest.raises(CaptureRefusedError, match="must be positive"):
        record_request(quantity=Quantity(amount, BTC))


def test_a_negative_fee_is_refused_because_a_rebate_is_another_event() -> None:
    with pytest.raises(CaptureRefusedError, match="rebate"):
        record_request(fee=Money(Decimal("-1"), USDT))


def test_a_third_asset_fee_without_its_own_rate_is_refused(
    store: TradingStore,
) -> None:
    with pytest.raises(CaptureRefusedError, match="third asset"):
        recorded(store, fee=Money(Decimal("0.01"), AssetCode("BNB")))


def test_a_third_asset_fee_with_its_own_rate_is_accepted(
    store: TradingStore,
) -> None:
    outcome = recorded(
        store,
        fee=Money(Decimal("0.01"), AssetCode("BNB")),
        fee_fx_rate_to_tax_currency=Decimal("6100"),
    )
    assert outcome.written[1].kind == "trade"


@pytest.mark.parametrize("field", ["entry_price", "stop"])
def test_a_price_that_is_not_positive_is_refused(field: str) -> None:
    with pytest.raises(CaptureRefusedError, match="must be positive"):
        record_request(**{field: Decimal("0")})


def test_a_target_that_is_not_positive_is_refused() -> None:
    with pytest.raises(CaptureRefusedError, match="target 1 must be positive"):
        record_request(targets=(Decimal("0"),))


def test_a_fill_filed_before_it_happened_is_refused() -> None:
    with pytest.raises(CaptureRefusedError, match="before the"):
        record_request(occurred_at=AT(11), written_at=AT(10))


def test_a_commitment_dated_after_its_own_fill_is_refused() -> None:
    with pytest.raises(CaptureRefusedError, match="after the fill"):
        record_request(committed_at=AT(11), occurred_at=AT(10), written_at=AT(12))


def test_a_commitment_dated_before_the_fill_is_accepted() -> None:
    request = record_request(committed_at=AT(9), occurred_at=AT(10))
    assert request.commitment_instant == AT(9)


def test_an_empty_author_is_refused() -> None:
    with pytest.raises((DomainValidationError, TypeError)):
        record_request(author="")


def test_the_request_refuses_a_market_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="must be a MarketId"):
        record_request(market="BTCUSDT")


def test_the_request_refuses_an_account_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="must be an AccountId"):
        record_request(account="binance_spot")


def test_record_trade_refuses_something_that_is_not_a_request(
    store: TradingStore,
) -> None:
    with pytest.raises(TypeError, match="must be a RecordRequest"):
        record_trade(store, "a trade")  # type: ignore[arg-type]


def test_record_trade_refuses_something_that_is_not_a_store() -> None:
    with pytest.raises(TypeError, match="must be a TradingStore"):
        record_trade("a store", record_request())  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The symbol split.
# --------------------------------------------------------------------------


def test_a_symbol_is_split_at_the_quote_asset_the_owner_named() -> None:
    market = market_from_symbol("BTCUSDT", venue="binance", quote="USDT")
    assert market == MARKET


def test_a_symbol_that_does_not_end_in_the_stated_quote_is_refused() -> None:
    with pytest.raises(CaptureRefusedError, match="will not guess the split"):
        market_from_symbol("BTCUSDT", quote="USDC")


def test_a_symbol_that_is_only_the_quote_asset_is_refused() -> None:
    with pytest.raises(CaptureRefusedError, match="will not guess the split"):
        market_from_symbol("USDT", quote="USDT")


def test_a_symbol_is_read_case_insensitively() -> None:
    assert market_from_symbol("btcusdt", quote="usdt") == MARKET


def test_the_mode_is_part_of_the_market_identity() -> None:
    perpetual = market_from_symbol("BTCUSDT", mode=MarketMode.PERPETUAL)
    assert perpetual != MARKET
    assert perpetual.mode is MarketMode.PERPETUAL


# --------------------------------------------------------------------------
# The version set.
# --------------------------------------------------------------------------


def test_the_version_set_records_the_build_and_leaves_policy_absent() -> None:
    versions = capture_version_set(code_version="abc123")
    assert versions.require(VersionAxis.CODE_VERSION) == "abc123"
    assert versions.require(VersionAxis.CALCULATION_VERSION) == "position-fold-v1"
    policy = versions.value_of(VersionAxis.POLICY_VERSION)
    assert isinstance(policy, Absent)
    assert "the owner asserted it" in policy.reason


def test_a_model_axis_is_absent_because_no_model_authored_this() -> None:
    versions = capture_version_set(code_version="abc123")
    assert isinstance(versions.value_of(VersionAxis.MODEL_TEMPLATE_VERSION), Absent)


# --------------------------------------------------------------------------
# Closing.
# --------------------------------------------------------------------------


def test_closing_appends_an_exit_fill_and_a_reason(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    outcome = closed(store, plan_id)
    assert [record.kind for record in outcome.written] == ["trade", "journal_entry"]
    assert outcome.view.status is CaptureStatus.CLOSED


def test_the_exit_is_the_other_side_of_the_entry(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    closed(store, plan_id)
    sides = [entry.trade.side for entry in store.ledger.resolved()]
    assert sides == [TradeSide.BUY, TradeSide.SELL]


def test_closing_a_short_buys_it_back(store: TradingStore) -> None:
    outcome = recorded(
        store,
        direction=TradeDirection.SHORT,
        stop=Decimal("62000"),
        targets=(Decimal("55000"),),
    )
    closed(store, outcome.plan_id, exit_price=Decimal("56000"))
    sides = [entry.trade.side for entry in store.ledger.resolved()]
    assert sides == [TradeSide.SELL, TradeSide.BUY]


def test_nothing_already_stored_changes_when_a_trade_is_closed(
    store: TradingStore,
) -> None:
    """Append-only, asserted rather than promised."""
    outcome = recorded(store, thesis="a reason")
    plan_before = store.plans.load(outcome.plan_id)
    entry_before = store.ledger.resolved()[0].trade
    journal_before = store.journals.all()
    closed(store, outcome.plan_id)
    assert store.plans.load(outcome.plan_id) == plan_before
    assert store.ledger.resolved()[0].trade == entry_before
    assert store.journals.all()[: len(journal_before)] == journal_before


def test_the_exit_reason_is_a_counted_tag_in_the_owners_vocabulary(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    view = closed(store, plan_id, reason="thesis_invalidated").view
    tags = [tag for entry in view.journal.entries for tag in entry.tags]
    assert len(tags) == 1
    assert tags[0].term.qualified_id == "exit_reason:thesis_invalidated"
    assert tags[0].origin is TagOrigin.OWNER
    assert tags[0].is_counted is True


def test_a_partial_close_leaves_the_position_open(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    view = closed(
        store, plan_id, quantity=Quantity(Decimal("0.2"), BTC)
    ).view
    assert view.status is CaptureStatus.OPEN
    assert view.open_quantity == Quantity(Decimal("0.3"), BTC)


def test_closing_more_than_is_open_is_refused(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    with pytest.raises(CaptureRefusedError, match="more than the"):
        closed(store, plan_id, quantity=Quantity(Decimal("0.6"), BTC))


def test_closing_a_commitment_with_no_fill_is_refused(store: TradingStore) -> None:
    from persistence_helpers import write_request
    from trade_domain_helpers import trade_plan

    plan = trade_plan()
    store.plans.create(plan, request=write_request())
    with pytest.raises(CaptureRefusedError, match="no position to close"):
        closed(store, plan.plan_id)


def test_closing_an_already_flat_trade_is_refused(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    closed(store, plan_id)
    with pytest.raises(CaptureRefusedError, match="already flat"):
        closed(store, plan_id, occurred_at=AT(11, day=15), written_at=AT(12, day=15))


def test_closing_a_trade_that_is_not_stored_is_refused(store: TradingStore) -> None:
    with pytest.raises(TradeNotFoundError, match="no recorded trade"):
        closed(store, "trade_plan-x-20260812T100000Z-0123456789abcdef")


def test_a_close_size_in_the_wrong_asset_is_refused(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    with pytest.raises(CaptureRefusedError, match="stated in USDT"):
        closed(store, plan_id, quantity=Quantity(Decimal("0.1"), USDT))


def test_a_third_asset_exit_fee_without_a_rate_is_refused(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    with pytest.raises(CaptureRefusedError, match="neither side"):
        closed(store, plan_id, fee=Money(Decimal("0.01"), AssetCode("BNB")))


def test_a_close_that_is_not_positive_is_refused(store: TradingStore) -> None:
    with pytest.raises(CaptureRefusedError, match="must be positive"):
        close_request("trade_plan-x-20260812T100000Z-0123456789abcdef",
                      quantity=Quantity(Decimal("0"), BTC))


def test_a_close_filed_before_it_happened_is_refused() -> None:
    with pytest.raises(CaptureRefusedError, match="before the"):
        close_request(
            "trade_plan-x-20260812T100000Z-0123456789abcdef",
            occurred_at=AT(11),
            written_at=AT(10),
        )


def test_an_exit_reason_is_required() -> None:
    with pytest.raises((DomainValidationError, TypeError)):
        close_request("trade_plan-x-20260812T100000Z-0123456789abcdef", reason="")


def test_close_trade_refuses_something_that_is_not_a_request(
    store: TradingStore,
) -> None:
    with pytest.raises(TypeError, match="must be a CloseRequest"):
        close_trade(store, "an exit")  # type: ignore[arg-type]


def test_an_exit_defaults_to_the_account_the_entry_filled_in(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    closed(store, plan_id)
    assert {entry.trade.account for entry in store.ledger.resolved()} == {ACCOUNT}


def test_an_exit_may_name_a_different_account_explicitly(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    closed(store, plan_id, account=AccountId("binance_margin"))
    accounts = {entry.trade.account.value for entry in store.ledger.resolved()}
    assert accounts == {"binance_spot", "binance_margin"}


def test_an_exit_across_two_accounts_must_name_which_one(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    closed(
        store,
        plan_id,
        quantity=Quantity(Decimal("0.1"), BTC),
        account=AccountId("binance_margin"),
    )
    with pytest.raises(CaptureRefusedError, match="cannot tell which one"):
        closed(
            store,
            plan_id,
            quantity=Quantity(Decimal("0.1"), BTC),
            occurred_at=AT(11, day=15),
            written_at=AT(12, day=15),
        )


# --------------------------------------------------------------------------
# Notes.
# --------------------------------------------------------------------------


def test_a_note_is_appended_and_linked_to_the_commitment(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    outcome = append_note(store, note_request(plan_id))
    assert [record.kind for record in outcome.written] == ["journal_entry"]
    entry = outcome.view.journal.entries[-1]
    assert entry.kind is JournalKind.NOTE
    assert ("trade_plan", plan_id) in {
        (link.target_kind, link.target_id) for link in entry.links
    }


def test_notes_accumulate_and_nothing_is_replaced(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    append_note(store, note_request(plan_id, body="first"))
    outcome = append_note(
        store, note_request(plan_id, body="second", recorded_at=AT(13), written_at=AT(13))
    )
    bodies = [entry.body for entry in outcome.view.journal.entries]
    assert bodies == ["first", "second"]


def test_an_identical_note_at_the_same_instant_is_stored_once(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    append_note(store, note_request(plan_id))
    second = append_note(store, note_request(plan_id))
    assert second.was_already_stored is True
    assert len(second.view.journal.entries) == 1


def test_a_note_about_a_trade_that_is_not_stored_is_refused(
    store: TradingStore,
) -> None:
    with pytest.raises(TradeNotFoundError):
        append_note(
            store, note_request("trade_plan-x-20260812T100000Z-0123456789abcdef")
        )


def test_an_empty_note_body_is_refused() -> None:
    with pytest.raises((DomainValidationError, TypeError)):
        note_request("trade_plan-x-20260812T100000Z-0123456789abcdef", body="")


def test_a_note_filed_before_it_was_written_is_refused() -> None:
    with pytest.raises(CaptureRefusedError, match="before the"):
        note_request(
            "trade_plan-x-20260812T100000Z-0123456789abcdef",
            recorded_at=AT(13),
            written_at=AT(12),
        )


def test_append_note_refuses_something_that_is_not_a_request(
    store: TradingStore,
) -> None:
    with pytest.raises(TypeError, match="must be a NoteRequest"):
        append_note(store, "a note")  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The write journal.
# --------------------------------------------------------------------------


def test_every_write_names_why_it_happened(store: TradingStore) -> None:
    outcome = recorded(store, thesis="a reason")
    append_note(store, note_request(outcome.plan_id))
    closed(store, outcome.plan_id)
    reasons = {event.reason.term_id for event in store.write_journal.events()}
    assert reasons == {
        RECORD_REASON.term_id,
        NOTE_REASON.term_id,
        CLOSE_REASON.term_id,
    }


def test_the_write_journal_chain_survives_a_whole_trade(
    store: TradingStore,
) -> None:
    outcome = recorded(store, thesis="a reason")
    closed(store, outcome.plan_id)
    assert store.write_journal.verify().ok is True
    assert store.verify().ok is True


def test_every_record_is_attributed_to_the_owner(store: TradingStore) -> None:
    recorded(store, author="dovydas")
    assert {event.author for event in store.write_journal.events()} == {"dovydas"}


def test_a_trade_in_another_market_folds_separately(store: TradingStore) -> None:
    recorded(store)
    recorded(
        store,
        market=OTHER_MARKET,
        quantity=Quantity(Decimal("2"), AssetCode("ETH")),
        entry_price=Decimal("3000"),
        stop=Decimal("2800"),
        targets=(Decimal("3400"),),
    )
    assert store.plans.count() == 2
    for plan in store.plans.plans():
        view = load_trade(
            store, plan.plan_id, dust=CAPTURE_DUST_POLICY, at=AT(12)
        )
        assert len(view.fills) == 1


def test_the_paper_book_is_recorded_like_any_other(store: TradingStore) -> None:
    outcome = recorded(store, book=Book.PAPER)
    assert store.plans.load(outcome.plan_id).book is Book.PAPER


# --------------------------------------------------------------------------
# Type guards, and the two instants a request resolves for itself.
# --------------------------------------------------------------------------


def test_a_record_request_refuses_a_size_that_is_not_a_quantity() -> None:
    with pytest.raises(TypeError, match="must be a Quantity"):
        record_request(quantity=Decimal("0.5"))


def test_a_record_request_refuses_a_fee_that_is_not_money() -> None:
    with pytest.raises(TypeError, match="must be a Money"):
        record_request(fee=Decimal("15"))


def test_a_price_supplied_as_a_float_is_refused_at_the_request() -> None:
    with pytest.raises(TypeError, match="must be a Decimal"):
        record_request(entry_price=60000.0)


def test_a_stated_fx_instant_is_used_instead_of_the_fills() -> None:
    request = record_request(fx_timestamp=AT(9))
    assert request.fx_instant == AT(9)
    assert record_request().fx_instant == AT(10)


def test_a_close_request_refuses_a_fee_that_is_not_money() -> None:
    with pytest.raises(TypeError, match="must be a Money"):
        close_request("trade_plan-x-20260812T100000Z-0123456789abcdef", fee=Decimal("16"))


def test_a_close_request_refuses_a_negative_fee() -> None:
    with pytest.raises(CaptureRefusedError, match="must not be negative"):
        close_request(
            "trade_plan-x-20260812T100000Z-0123456789abcdef",
            fee=Money(Decimal("-1"), USDT),
        )


def test_a_close_request_refuses_a_size_of_the_wrong_type() -> None:
    with pytest.raises(TypeError, match="Quantity or Absent"):
        close_request(
            "trade_plan-x-20260812T100000Z-0123456789abcdef", quantity=Decimal("0.2")
        )


def test_a_close_request_refuses_an_account_of_the_wrong_type() -> None:
    with pytest.raises(TypeError, match="AccountId or Absent"):
        close_request(
            "trade_plan-x-20260812T100000Z-0123456789abcdef", account="binance_spot"
        )


def test_a_close_request_uses_a_stated_fx_instant() -> None:
    request = close_request(
        "trade_plan-x-20260812T100000Z-0123456789abcdef", fx_timestamp=AT(8, day=14)
    )
    assert request.fx_instant == AT(8, day=14)
    assert close_request("trade_plan-x-20260812T100000Z-0123456789abcdef").fx_instant == (
        AT(9, day=14)
    )
