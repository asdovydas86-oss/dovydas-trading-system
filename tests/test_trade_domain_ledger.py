"""`Trade`, `TradeStatus`, `Correction`, the resolver and `balance_effects`.

The brief's *Trade* and *TradeStatus*. Two properties matter more than any other
here and both are tested first: **identical content is one event**, and **nothing
is ever edited**.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from trade_domain_helpers import (
    ACCOUNT,
    AT,
    BTC,
    MARKET,
    USDT,
    correction,
    money,
    quantity,
    reason_tag,
    trade,
)

from fmis.accounts import AccountId, Book
from fmis.money import AssetCode, Money, Quantity
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError, PayloadDecodeError, RecordAudit
from fmis.ledger import (
    STORABLE_TRADE_STATUSES,
    TRADE_STATUS_TRANSITIONS,
    Correction,
    DanglingCorrectionError,
    IllegalTradeTransitionError,
    LedgerEventKind,
    LedgerResolver,
    LedgerSource,
    ResolvedTrade,
    SupersessionError,
    Trade,
    TradeSide,
    TradeStatus,
    advance_trade_status,
    balance_effects,
    resolve,
)


# --------------------------------------------------------------------------
# Identity: economic fields only.
# --------------------------------------------------------------------------


def test_identical_content_produces_one_event_id() -> None:
    assert trade().event_id == trade().event_id


@pytest.mark.parametrize(
    "override",
    [
        {"recorded_at": AT(20)},
        {"source": LedgerSource.EXCHANGE_API},
        {"asserted_by": "binance sync"},
        {"venue_trade_id": "9911223"},
        {"note": "typed from the app"},
    ],
)
def test_a_non_economic_field_does_not_create_a_second_event(override: dict) -> None:
    assert trade().event_id == trade(**override).event_id


@pytest.mark.parametrize(
    "override",
    [
        {"quantity": Quantity(Decimal("0.6"), BTC)},
        {"price": Decimal("60001")},
        {"fee": Money(Decimal("16"), USDT)},
        {"book": Book.INVESTING},
        {"side": TradeSide.SELL},
        {"occurred_at": AT(11)},
        {"occurrence_index": 2},
        {"plan_id": "plan-7"},
        {"is_maker": True},
        {"fx_rate_to_tax_currency": Decimal("10.6")},
    ],
)
def test_an_economic_field_does_create_a_different_event(override: dict) -> None:
    assert trade().event_id != trade(**override).event_id


def test_two_spellings_of_one_amount_are_one_event() -> None:
    left = trade(quantity=Quantity(Decimal("0.50"), BTC), price=Decimal("60000.0"))
    right = trade(quantity=Quantity(Decimal("0.5"), BTC), price=Decimal("60000"))
    assert left.event_id == right.event_id


def test_a_trade_round_trips_and_verifies_its_own_id() -> None:
    subject = trade()
    assert Trade.from_payload(subject.to_payload()) == subject
    payload = subject.to_payload()
    payload["event_id"] = "trade-x-20260812T100000Z-0123456789abcdef"
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        Trade.from_payload(payload)


def test_a_payload_that_is_not_a_trade_is_rejected() -> None:
    payload = trade().to_payload()
    payload["kind"] = "transfer"
    with pytest.raises(PayloadDecodeError, match="is not a trade"):
        Trade.from_payload(payload)


def test_an_unknown_enum_member_on_decode_is_a_clean_rejection() -> None:
    payload = trade().to_payload()
    payload["side"] = "hodl"
    with pytest.raises(PayloadDecodeError, match="TradeSide"):
        Trade.from_payload(payload)


# --------------------------------------------------------------------------
# Validation.
# --------------------------------------------------------------------------


def test_a_trade_is_asserted_and_is_the_one_value_class_that_can_be_wrong() -> None:
    assert trade().origin is ValueOrigin.ASSERTED
    assert trade().kind is LedgerEventKind.TRADE


def test_direction_lives_on_side_and_never_in_a_signed_quantity() -> None:
    with pytest.raises(DomainValidationError, match="direction is carried by"):
        trade(quantity=Quantity(Decimal("-0.5"), BTC))


def test_the_quantity_is_denominated_in_the_market_base_asset() -> None:
    with pytest.raises(DomainValidationError, match="base asset"):
        trade(quantity=Quantity(Decimal("0.5"), USDT))


def test_a_negative_fee_is_a_different_economic_fact() -> None:
    with pytest.raises(DomainValidationError, match="rebate"):
        trade(fee=Money(Decimal("-1"), USDT))


def test_the_tax_rate_is_required_from_the_first_record() -> None:
    with pytest.raises(DomainValidationError, match="unrecoverable retroactively"):
        trade(fx_rate_to_tax_currency=Decimal("0"))


def test_a_trade_recorded_before_it_happened_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="before it happened"):
        trade(recorded_at=AT(9))


def test_a_price_must_be_positive() -> None:
    with pytest.raises(DomainValidationError, match="price must be positive"):
        trade(price=Decimal("0"))


def test_a_trade_is_frozen_at_creation() -> None:
    with pytest.raises(DomainValidationError, match="frozen at creation"):
        trade(audit=RecordAudit.frozen_at(AT(10)).appended_at(AT(11)))


def test_an_occurrence_index_starts_at_one_and_is_the_owners_tie_break() -> None:
    assert isinstance(trade().occurrence_index, Absent)
    assert trade(occurrence_index=2).occurrence_index == 2
    with pytest.raises(DomainValidationError, match="at least 1"):
        trade(occurrence_index=0)


# --------------------------------------------------------------------------
# The fee rule.
# --------------------------------------------------------------------------


def test_a_third_asset_fee_requires_its_own_rate() -> None:
    with pytest.raises(DomainValidationError, match="its own FX rate"):
        trade(fee=Money(Decimal("0.01"), AssetCode("BNB")))


def test_a_third_asset_fee_with_a_rate_is_accepted() -> None:
    subject = trade(
        fee=Money(Decimal("0.01"), AssetCode("BNB")),
        fee_fx_rate_to_tax_currency=Decimal("3000"),
    )
    assert subject.fee.asset == AssetCode("BNB")
    assert Trade.from_payload(subject.to_payload()) == subject


def test_a_fee_on_either_side_must_not_carry_a_separate_rate() -> None:
    with pytest.raises(DomainValidationError, match="applies only to a fee in a third"):
        trade(fee_fx_rate_to_tax_currency=Decimal("3000"))


def test_a_third_asset_fee_rate_must_be_positive() -> None:
    with pytest.raises(DomainValidationError, match="must be positive"):
        trade(
            fee=Money(Decimal("0.01"), AssetCode("BNB")),
            fee_fx_rate_to_tax_currency=Decimal("-1"),
        )


# --------------------------------------------------------------------------
# TradeStatus — the brief's own name, for the ledger half.
# --------------------------------------------------------------------------


def test_only_draft_and_recorded_are_ever_stored() -> None:
    assert STORABLE_TRADE_STATUSES == {TradeStatus.DRAFT, TradeStatus.RECORDED}
    with pytest.raises(DomainValidationError, match="derived from the correction chain"):
        trade(status=TradeStatus.SUPERSEDED)


def test_a_draft_becomes_recorded_through_the_status_machine() -> None:
    draft = trade(status=TradeStatus.DRAFT)
    recorded = draft.recorded()
    assert recorded.status is TradeStatus.RECORDED
    assert recorded.event_id == draft.event_id


@pytest.mark.parametrize(
    "current, target",
    [
        (TradeStatus.DRAFT, TradeStatus.SUPERSEDED),
        (TradeStatus.RECORDED, TradeStatus.DRAFT),
        (TradeStatus.SUPERSEDED, TradeStatus.RECORDED),
        (TradeStatus.RECORDED, TradeStatus.RECORDED),
    ],
)
def test_an_illegal_status_transition_fails(
    current: TradeStatus, target: TradeStatus
) -> None:
    with pytest.raises(IllegalTradeTransitionError, match="cannot become"):
        advance_trade_status(current, target)


def test_the_legal_transitions_are_exactly_two() -> None:
    assert TRADE_STATUS_TRANSITIONS[TradeStatus.DRAFT] == {TradeStatus.RECORDED}
    assert TRADE_STATUS_TRANSITIONS[TradeStatus.RECORDED] == {TradeStatus.SUPERSEDED}
    assert TRADE_STATUS_TRANSITIONS[TradeStatus.SUPERSEDED] == frozenset()


def test_advancing_from_a_non_status_is_a_type_error() -> None:
    with pytest.raises(TypeError):
        advance_trade_status("recorded", TradeStatus.SUPERSEDED)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# balance_effects — derived, never stored.
# --------------------------------------------------------------------------


def test_a_buy_produces_base_in_quote_out_and_the_fee() -> None:
    effects = balance_effects(trade())
    assert [str(effect.quantity) for effect in effects] == [
        "0.5 BTC",
        "-30000 USDT",
        "-15 USDT",
    ]
    assert all(effect.account == ACCOUNT for effect in effects)
    assert effects[0].asset == BTC


def test_a_sell_reverses_the_first_two_movements() -> None:
    effects = balance_effects(trade(side=TradeSide.SELL))
    assert [str(effect.quantity) for effect in effects][:2] == [
        "-0.5 BTC",
        "30000 USDT",
    ]


def test_a_zero_fee_produces_no_fee_movement() -> None:
    effects = balance_effects(trade(fee=Money(Decimal("0"), USDT)))
    assert len(effects) == 2


def test_a_third_asset_fee_produces_its_own_disposal() -> None:
    effects = balance_effects(
        trade(
            fee=Money(Decimal("0.01"), AssetCode("BNB")),
            fee_fx_rate_to_tax_currency=Decimal("3000"),
        )
    )
    assert str(effects[-1].quantity) == "-0.01 BNB"


def test_balance_effects_is_a_function_and_not_a_field() -> None:
    assert "balance_effects" not in trade().to_payload()
    assert "postings" not in trade().to_payload()


def test_balance_effects_rejects_a_non_trade() -> None:
    with pytest.raises(TypeError, match="must be a Trade"):
        balance_effects("a trade")  # type: ignore[arg-type]


def test_the_gross_consideration_is_a_product_and_not_a_stored_field() -> None:
    assert trade().gross_consideration == Money(Decimal("30000"), USDT)
    assert "gross_consideration" not in trade().to_payload()


# --------------------------------------------------------------------------
# Correction.
# --------------------------------------------------------------------------


def test_a_correction_carries_the_replacement_in_full_and_round_trips() -> None:
    original = trade()
    replacement = trade(quantity=Quantity(Decimal("0.6"), BTC))
    subject = correction(original, replacement)
    assert subject.kind is LedgerEventKind.CORRECTION
    assert Correction.from_payload(subject.to_payload()) == subject


def test_a_correction_replacing_identical_content_is_not_a_correction() -> None:
    original = trade()
    with pytest.raises(DomainValidationError, match="idempotent success"):
        correction(original, trade())


def test_a_correction_requires_a_reason_from_a_vocabulary() -> None:
    with pytest.raises(TypeError, match="VersionedTerm"):
        correction(
            trade(),
            trade(price=Decimal("60001")),
            reason="I fat-fingered it",
        )


def test_a_correction_cannot_put_a_draft_into_the_ledger() -> None:
    with pytest.raises(DomainValidationError, match="recorded event"):
        correction(
            trade(),
            trade(price=Decimal("60001"), status=TradeStatus.DRAFT),
        )


def test_a_correction_payload_that_is_not_a_correction_is_rejected() -> None:
    payload = correction(trade(), trade(price=Decimal("60001"))).to_payload()
    payload["kind"] = "trade"
    with pytest.raises(PayloadDecodeError, match="is not a correction"):
        Correction.from_payload(payload)


def test_a_tampered_correction_id_is_rejected() -> None:
    payload = correction(trade(), trade(price=Decimal("60001"))).to_payload()
    payload["event_id"] = "correction-x-20260812T110000Z-0123456789abcdef"
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        Correction.from_payload(payload)


# --------------------------------------------------------------------------
# The resolver — the one enforced read path.
# --------------------------------------------------------------------------


def test_a_resolved_trade_cannot_be_constructed_by_a_consumer() -> None:
    with pytest.raises(SupersessionError, match="cannot be constructed directly"):
        ResolvedTrade(token=object(), trade=trade(), chain=("x",))


def test_re_entering_a_fill_after_a_crash_is_an_idempotent_success() -> None:
    resolver = resolve((trade(), trade()))
    assert len(resolver.resolved()) == 1


def test_a_correction_replaces_what_the_trade_currently_says() -> None:
    original = trade()
    replacement = trade(quantity=Quantity(Decimal("0.6"), BTC))
    resolver = resolve((original,), (correction(original, replacement),))
    (entry,) = resolver.resolved()
    assert entry.was_corrected
    assert entry.trade.quantity == Quantity(Decimal("0.6"), BTC)
    assert entry.original_event_id == original.event_id
    assert entry.status is TradeStatus.RECORDED


def test_a_correction_chain_extends_and_never_branches() -> None:
    original = trade()
    first = correction(original, trade(quantity=Quantity(Decimal("0.6"), BTC)))
    second = correction(original, trade(price=Decimal("60001")), occurred_at=AT(12))
    with pytest.raises(SupersessionError, match="never branches"):
        resolve((original,), (first, second))


def test_a_chain_of_two_corrections_resolves_to_the_last() -> None:
    original = trade()
    second_trade = trade(quantity=Quantity(Decimal("0.6"), BTC))
    third_trade = trade(quantity=Quantity(Decimal("0.7"), BTC))
    first = correction(original, second_trade)
    second = Correction(
        supersedes=first.event_id,
        replacement=third_trade,
        reason=reason_tag("typed_the_wrong_quantity", "correction_reason"),
        author="owner",
        occurred_at=AT(12),
        recorded_at=AT(12),
        audit=RecordAudit.frozen_at(AT(12)),
    )
    resolver = resolve((original,), (first, second))
    (entry,) = resolver.resolved()
    assert entry.trade.quantity == Quantity(Decimal("0.7"), BTC)
    assert len(entry.chain) == 3


def test_a_correction_naming_an_absent_event_is_a_detected_gap() -> None:
    orphan = Correction(
        supersedes="trade-BTCUSDT-20200101T000000Z-0123456789abcdef",
        replacement=trade(price=Decimal("60001")),
        reason=reason_tag("typed_the_wrong_quantity", "correction_reason"),
        author="owner",
        occurred_at=AT(12),
        recorded_at=AT(12),
        audit=RecordAudit.frozen_at(AT(12)),
    )
    with pytest.raises(DanglingCorrectionError, match="not in this stream"):
        resolve((trade(),), (orphan,))


def test_the_resolver_reports_the_status_of_any_event_in_the_stream() -> None:
    original = trade()
    replacement = trade(quantity=Quantity(Decimal("0.6"), BTC))
    fix = correction(original, replacement)
    resolver = resolve((original,), (fix,))
    assert resolver.status_of(original.event_id) is TradeStatus.SUPERSEDED
    assert resolver.status_of(fix.event_id) is TradeStatus.RECORDED
    with pytest.raises(DanglingCorrectionError):
        resolver.status_of("trade-X-20200101T000000Z-0123456789abcdef")


def test_the_superseded_digest_map_is_what_a_frozen_artifact_compares_against() -> None:
    original = trade()
    replacement = trade(quantity=Quantity(Decimal("0.6"), BTC))
    resolver = resolve((original,), (correction(original, replacement),))
    stale = resolver.superseded_digests()
    assert stale == {original.event_id: replacement.content_digest}


def test_an_uncorrected_stream_reports_nothing_stale() -> None:
    assert resolve((trade(),)).superseded_digests() == {}


def test_a_draft_is_not_in_the_ledger() -> None:
    with pytest.raises(DomainValidationError, match="is a draft"):
        resolve((trade(status=TradeStatus.DRAFT),))


def test_the_resolver_selects_one_market_and_book_pair_for_the_fold() -> None:
    swing = trade()
    investing = trade(book=Book.INVESTING)
    resolver = resolve((swing, investing))
    assert len(resolver.resolved()) == 2
    assert len(resolver.for_market_and_book(MARKET, Book.SWING)) == 1


def test_resolved_trades_expose_their_balance_effects() -> None:
    (entry,) = resolve((trade(),)).resolved()
    assert len(entry.balance_effects()) == 3


def test_the_resolver_orders_by_when_the_fill_happened() -> None:
    late = trade(occurred_at=AT(12))
    early = trade(occurred_at=AT(10))
    resolver = resolve((late, early))
    assert [entry.trade.occurred_at for entry in resolver.resolved()] == [AT(10), AT(12)]


def test_the_resolver_type_checks_its_inputs() -> None:
    with pytest.raises(TypeError):
        LedgerResolver(trades=(trade(),), corrections=("not a correction",))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        LedgerResolver(trades=["a list, not a tuple"])  # type: ignore[arg-type]


def test_a_trade_can_be_cited_as_a_consumed_source() -> None:
    subject = trade()
    source = subject.as_consumed_source()
    assert source.record_id == subject.event_id
    assert source.content_digest == subject.content_digest
    assert source.kind == "trade"


def test_a_proposal_link_on_a_trade_must_be_a_real_record_id() -> None:
    with pytest.raises(DomainValidationError, match="expected shape"):
        trade(proposal_id="the one from tuesday")
