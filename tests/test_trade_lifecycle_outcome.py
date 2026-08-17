"""Milestone BO — `TradeOutcome`, and what it deliberately does not store.

`AP` §25.2 splits the figures a finished trade produces into two classes, and
this record is the line between them. MAE, MFE, the bar count and the exit reason
are frozen *"because kline history is not permanent and instruments get
delisted"*; realized P&L, average entry and quantity are projections over a
ledger that is, and storing them here would be the fourth place one fact lives.

The other property these check is that half a record is refused. An outcome
carrying a close time and no excursions would read as *"this trade never went
against us"*, which is a claim about the market rather than about what was
recorded.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError, PayloadDecodeError, RecordAudit
from fmis.trade_lifecycle import (
    EXPOSED_EXIT_REASONS,
    ExitReason,
    OutcomeError,
    TradeOutcome,
)
from fmis.paper import PAPER_ZERO_COST_POLICY
from paper_helpers import MARKET, VERSIONS, activation, at, plan


def outcome(**overrides) -> TradeOutcome:
    subject = activation()
    fill_id = "trade-binance_BTCUSDT_spot-20260801T010000Z-" + "a" * 16
    fields = {
        "activation_id": subject.activation_id,
        "plan_id": subject.plan_id,
        "market": MARKET,
        "exit_reason": ExitReason.TARGET_HIT,
        "frozen_at": at(8),
        "interval": "1h",
        "cost_policy": PAPER_ZERO_COST_POLICY,
        "fill_policy_id": "fmits-paper-fill",
        "fill_policy_version": 1,
        "initial_stop": Decimal("95"),
        "version_set": VERSIONS,
        "audit": RecordAudit.frozen_at(at(8)),
        "opened_at": at(1),
        "closed_at": at(4),
        "bars_held": 3,
        "max_favourable_price": Decimal("121"),
        "max_adverse_price": Decimal("98"),
        "effective_stop_at_exit": Decimal("100"),
        "fill_event_ids": (fill_id,),
    }
    fields.update(overrides)
    if "audit" not in overrides and "frozen_at" in overrides:
        fields["audit"] = RecordAudit.frozen_at(fields["frozen_at"])
    return TradeOutcome(**fields)


def unexposed(**overrides) -> TradeOutcome:
    absent = Absent("no fill ever opened this trade")
    fields = {
        "exit_reason": ExitReason.EXPIRED,
        "opened_at": absent,
        "closed_at": absent,
        "bars_held": absent,
        "max_favourable_price": absent,
        "max_adverse_price": absent,
        "effective_stop_at_exit": absent,
        "fill_event_ids": (),
    }
    fields.update(overrides)
    return outcome(**fields)


def test_an_outcome_round_trips_through_its_payload_exactly() -> None:
    original = outcome()
    assert TradeOutcome.from_payload(original.to_payload()) == original
    unfilled = unexposed()
    assert TradeOutcome.from_payload(unfilled.to_payload()) == unfilled


def test_the_record_stores_the_excursions_and_no_figure_the_ledger_answers() -> None:
    fields = set(TradeOutcome.__dataclass_fields__)
    assert {
        "max_favourable_price",
        "max_adverse_price",
        "bars_held",
        "exit_reason",
        "effective_stop_at_exit",
    } <= fields
    for absent in ("realized_pnl", "average_entry", "r_multiple", "pnl_percent"):
        assert absent not in fields, absent


def test_the_excursions_are_prices_because_a_price_is_what_a_candle_holds() -> None:
    """Money needs a quantity that changed with every partial exit and R needs an
    entry the ledger owns; freezing either would freeze a quotient."""
    assert outcome().max_favourable_price == Decimal("121")
    assert isinstance(outcome().max_favourable_price, Decimal)


def test_the_three_exposed_reasons_are_the_ones_that_imply_a_position() -> None:
    assert EXPOSED_EXIT_REASONS == {
        ExitReason.TARGET_HIT,
        ExitReason.STOP_HIT,
        ExitReason.MANUAL_CLOSE,
    }


def test_an_outcome_that_held_a_position_states_every_fact_about_it() -> None:
    with pytest.raises(OutcomeError, match="must state"):
        outcome(max_favourable_price=Absent("none"))
    with pytest.raises(OutcomeError, match="must name them"):
        outcome(fill_event_ids=())


def test_an_outcome_that_never_opened_states_none_of_them() -> None:
    """An excursion over a position that never opened is absent, not zero."""
    with pytest.raises(OutcomeError, match="must state none of"):
        unexposed(opened_at=at(1))
    with pytest.raises(OutcomeError, match="folded none"):
        unexposed(
            fill_event_ids=("trade-binance_BTCUSDT_spot-20260801T010000Z-" + "a" * 16,)
        )


def test_an_ending_cannot_be_recorded_before_it_happened() -> None:
    with pytest.raises(OutcomeError, match="before the"):
        outcome(frozen_at=at(2))
    with pytest.raises(OutcomeError, match="precedes opened_at"):
        outcome(opened_at=at(4), closed_at=at(1))


def test_the_audit_block_must_agree_with_the_moment_it_was_frozen() -> None:
    with pytest.raises(DomainValidationError, match="audit.created_at"):
        outcome(audit=RecordAudit.frozen_at(at(7)))


def test_an_outcome_knows_whether_the_stop_had_been_moved_when_it_ended() -> None:
    assert outcome().stop_was_moved
    assert not outcome(effective_stop_at_exit=Decimal("95")).stop_was_moved
    assert not unexposed().stop_was_moved


def test_holding_time_is_computed_and_absent_when_nothing_was_held() -> None:
    assert outcome().holding_time().total_seconds() == 3 * 60 * 60
    assert isinstance(unexposed().holding_time(), Absent)


def test_an_outcome_is_measured_over_frozen_inputs() -> None:
    assert outcome().origin is ValueOrigin.MEASURED
    assert outcome().held_exposure
    assert not unexposed().held_exposure


def test_the_fill_ids_are_sorted_and_deduplicated() -> None:
    first = "trade-binance_BTCUSDT_spot-20260801T010000Z-" + "a" * 16
    second = "trade-binance_BTCUSDT_spot-20260801T020000Z-" + "b" * 16
    subject = outcome(fill_event_ids=(second, first, first))
    assert subject.fill_event_ids == (first, second)


def test_a_payload_whose_id_does_not_match_its_content_is_refused() -> None:
    payload = outcome().to_payload()
    payload["outcome_id"] = "trade_outcome-x-20260801T000000Z-" + "0" * 16
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        TradeOutcome.from_payload(payload)


def test_an_unknown_exit_reason_read_from_disk_is_a_clean_rejection() -> None:
    payload = outcome().to_payload()
    payload["exit_reason"] = "liquidated"
    with pytest.raises(PayloadDecodeError, match="clean rejection"):
        TradeOutcome.from_payload(payload)


def test_an_outcome_cites_itself_as_a_consumed_source() -> None:
    source = outcome().as_consumed_source()
    assert source.kind == "trade_outcome"
    assert source.record_id == outcome().outcome_id


def test_a_schema_version_this_build_does_not_write_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        outcome(schema_version=99)
