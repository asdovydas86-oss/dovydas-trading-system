"""Milestone BO — `ActivationRepository` and the candle fetcher behind `simulate`.

The repository is the eleventh over one store and owns four kinds. What these
check is the half its callers depend on and the scenario tests reach only
incidentally: the read verbs, the supersession path, the frozen refusals, and
the fact that **no state is stored** — every one of `state`, `stop_history` and
`outcome_for` is a fold or a lookup computed on the call.

The fetcher is the one place a venue is named for a replay, and it is checked
the way `fmis.pipeline.prices` already is: with the provider's own injection
points, network-free.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from fmis.accounts import AccountId, Book
from fmis.money import AssetCode, Quantity
from fmis.persistence import (
    FrozenRecordError,
    PersistenceError,
    RecordConflictError,
    RecordKind,
    RecordMissingError,
    SearchCriteria,
    TradingStore,
    WriteRequest,
    WriteSource,
)
from fmis.provenance import Absent, ValueOrigin, VersionedTerm
from fmis.records import RecordAudit
from fmis.snapshotting import TradeDirection
from fmis.trade_capture import PlanRequest, record_plan
from fmis.trade_lifecycle import (
    EntryType,
    ExitReason,
    StopAmendment,
    TradeLifecycleEvent,
    TradeLifecycleKind,
    TradeLifecycleState,
    TradeOutcome,
)
from fmis.paper import (
    PAPER_DUST_POLICY,
    PAPER_ZERO_COST_POLICY,
    ActivateRequest,
    activate_trade,
    paper_version_set,
    run_simulation,
)
from fmis.pipeline.candles import (
    SIMULATION_CANDLE_LIMIT,
    SIMULATION_INTERVAL,
    CandleFetch,
    fetch_simulation_candles,
)
from marks_helpers import failing_transport, klines_body, klines_transport
from paper_helpers import MARKET, START, VERSIONS, at, bar


@pytest.fixture()
def store(tmp_path: Path) -> TradingStore:
    return TradingStore(tmp_path / "store", dust=PAPER_DUST_POLICY)


def _request(hours: int = 0) -> WriteRequest:
    return WriteRequest(
        written_at=at(hours),
        source=WriteSource.POLICY_ENGINE,
        author="test",
        reason=VersionedTerm(
            vocabulary_id="write_reason", term_id="test", taxonomy_version=1
        ),
        version_set=paper_version_set(code_version="test"),
    )


def _activated(store: TradingStore, **overrides):
    plan = record_plan(
        store,
        PlanRequest(
            market=MARKET,
            book=Book.PAPER,
            direction=TradeDirection.LONG,
            stop=Decimal("95"),
            targets=(Decimal("110"), Decimal("120")),
            committed_at=START,
            written_at=START,
            author="owner",
            confidence="medium",
            code_version="test",
        ),
    ).view.plan
    fields = dict(
        plan_id=plan.plan_id,
        account=AccountId("paper"),
        quantity=Quantity(Decimal("1"), AssetCode("BTC")),
        entry_type=EntryType.STOP_ENTRY,
        entry_price=Decimal("100"),
        interval="1h",
        activated_at=START,
        written_at=START,
        code_version="test",
        fractions=(Decimal("1"),),
    )
    fields.update(overrides)
    return plan, activate_trade(store, ActivateRequest(**fields)).activation


def _event(subject, kind, *, hours: int, **overrides) -> TradeLifecycleEvent:
    fields = dict(
        activation_id=subject.activation_id,
        kind=kind,
        occurred_at=at(hours),
        recorded_at=at(hours),
        audit=RecordAudit.frozen_at(at(hours)),
        causing_close_time=at(hours),
    )
    fields.update(overrides)
    return TradeLifecycleEvent(**fields)


def _amendment(subject, previous: str, new: str, *, hours: int, **overrides):
    fields = dict(
        activation_id=subject.activation_id,
        previous_stop=Decimal(previous),
        new_stop=Decimal(new),
        reason=VersionedTerm(
            vocabulary_id="stop_amendment_reason",
            term_id="de_risking",
            taxonomy_version=1,
        ),
        origin=ValueOrigin.ASSERTED,
        author="owner",
        occurred_at=at(hours),
        recorded_at=at(hours),
        audit=RecordAudit.frozen_at(at(hours)),
    )
    fields.update(overrides)
    return StopAmendment(**fields)


# --------------------------------------------------------------------------
# What the repository owns
# --------------------------------------------------------------------------


def test_the_repository_owns_exactly_the_four_new_kinds(store) -> None:
    assert store.activations.kinds == (
        RecordKind.TRADE_ACTIVATION,
        RecordKind.TRADE_LIFECYCLE_EVENT,
        RecordKind.STOP_AMENDMENT,
        RecordKind.TRADE_OUTCOME,
    )
    assert store.activations.primary_kind is RecordKind.TRADE_ACTIVATION


def test_every_activation_of_one_commitment_groups_together(store) -> None:
    """Including a cancelled first attempt: *'I activated this twice'* is a
    behaviour, and a listing that hid it would make the second look like the
    only one."""
    plan, first = _activated(store)
    second = activate_trade(
        store,
        ActivateRequest(
            plan_id=plan.plan_id,
            account=AccountId("paper"),
            quantity=Quantity(Decimal("2"), AssetCode("BTC")),
            entry_type=EntryType.MARKET,
            interval="1h",
            activated_at=at(1),
            written_at=at(1),
            code_version="test",
        ),
    ).activation
    grouped = store.activations.activations_for_plan(plan.plan_id)
    assert {item.activation_id for item in grouped} == {
        first.activation_id,
        second.activation_id,
    }


def test_a_stream_is_ordered_by_the_candle_and_not_by_the_run(store) -> None:
    _, subject = _activated(store)
    store.activations.append_event(
        _event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=2),
        request=_request(5),
    )
    store.activations.append_event(
        _event(subject, TradeLifecycleKind.ENTRY_FILLED, hours=2, bar_sequence=1),
        request=_request(6),
    )
    stream = store.activations.events_for(subject.activation_id)
    assert [event.kind for event in stream] == [
        TradeLifecycleKind.ENTRY_TRIGGERED,
        TradeLifecycleKind.ENTRY_FILLED,
    ]
    assert store.activations.state(subject.activation_id).state is (
        TradeLifecycleState.OPEN
    )


def test_a_superseded_event_leaves_the_fold_and_stays_readable(store) -> None:
    _, subject = _activated(store)
    wrong = _event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1)
    store.activations.append_event(wrong, request=_request(1))
    correction = _event(
        subject,
        TradeLifecycleKind.ENTRY_TRIGGERED,
        hours=2,
        supersedes=wrong.event_id,
    )
    store.activations.replace(wrong.event_id, correction, request=_request(3))
    assert len(store.activations.events_for(subject.activation_id)) == 2
    live = store.activations.live_events_for(subject.activation_id)
    assert [event.event_id for event in live] == [correction.event_id]


def test_an_amendment_can_be_superseded_the_same_way(store) -> None:
    plan, subject = _activated(store)
    wrong = _amendment(subject, "95", "90", hours=1)
    store.activations.append_amendment(wrong, request=_request(1))
    correction = _amendment(
        subject, "95", "97", hours=2, supersedes=wrong.amendment_id
    )
    store.activations.replace(wrong.amendment_id, correction, request=_request(3))
    history = store.activations.stop_history(
        subject.activation_id,
        initial_stop=plan.initial_invalidation,
        direction=plan.direction,
    )
    assert history.effective == Decimal("97")
    assert history.widening_count == 0


def test_replace_refuses_everything_that_has_no_supersession_mechanism(store) -> None:
    _, subject = _activated(store)
    with pytest.raises(RecordMissingError, match="no record"):
        store.activations.replace("trade_activation-x-20260801T000000Z-" + "0" * 16)
    with pytest.raises(FrozenRecordError, match="captured artifact"):
        store.activations.replace(subject.activation_id)


def test_replace_needs_the_replacement_and_the_request(store) -> None:
    _, subject = _activated(store)
    wrong = _event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1)
    store.activations.append_event(wrong, request=_request(1))
    with pytest.raises(PersistenceError, match="needs the replacement"):
        store.activations.replace(wrong.event_id)
    with pytest.raises(TypeError, match="TradeLifecycleEvent"):
        store.activations.replace(
            wrong.event_id, _amendment(subject, "95", "97", hours=2), request=_request(2)
        )
    other = _event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=3)
    with pytest.raises(PersistenceError, match="not the record"):
        store.activations.replace(wrong.event_id, other, request=_request(3))


def test_appending_something_that_is_not_an_event_or_an_amendment_is_refused(
    store,
) -> None:
    _, subject = _activated(store)
    with pytest.raises(TypeError, match="TradeLifecycleEvent"):
        store.activations.append_event("an event", request=_request())
    with pytest.raises(TypeError, match="StopAmendment"):
        store.activations.append_amendment("an amendment", request=_request())


def test_a_second_outcome_for_one_activation_is_a_conflict(store) -> None:
    plan, subject = _activated(store)
    first = TradeOutcome(
        activation_id=subject.activation_id,
        plan_id=plan.plan_id,
        market=MARKET,
        exit_reason=ExitReason.EXPIRED,
        frozen_at=at(5),
        interval="1h",
        cost_policy=PAPER_ZERO_COST_POLICY,
        fill_policy_id="fmits-paper-fill",
        fill_policy_version=1,
        initial_stop=Decimal("95"),
        version_set=VERSIONS,
        audit=RecordAudit.frozen_at(at(5)),
    )
    store.activations.create(first, request=_request(5))
    second = TradeOutcome(
        activation_id=subject.activation_id,
        plan_id=plan.plan_id,
        market=MARKET,
        exit_reason=ExitReason.CANCELLED,
        frozen_at=at(6),
        interval="1h",
        cost_policy=PAPER_ZERO_COST_POLICY,
        fill_policy_id="fmits-paper-fill",
        fill_policy_version=1,
        initial_stop=Decimal("95"),
        version_set=VERSIONS,
        audit=RecordAudit.frozen_at(at(6)),
    )
    with pytest.raises(RecordConflictError, match="already has outcome"):
        store.activations.create(second, request=_request(6))
    assert store.activations.outcome_for(subject.activation_id) == first
    assert store.activations.outcomes() == (first,)


def test_a_record_naming_an_activation_this_store_lacks_is_refused(store) -> None:
    from paper_helpers import activation as build

    orphan = build(activated_at=at(4))
    with pytest.raises(RecordMissingError, match="never be folded"):
        store.activations.append_amendment(
            _amendment(orphan, "95", "97", hours=5), request=_request(5)
        )


def test_the_states_the_listings_report_are_folded_on_every_call(store) -> None:
    _, subject = _activated(store)
    assert store.activations.live_activations()[0][1].state is (
        TradeLifecycleState.PENDING
    )
    assert store.activations.halted_activations() == ()
    assert store.activations.finished() == ()
    store.activations.append_event(
        _event(subject, TradeLifecycleKind.AMBIGUOUS_BAR, hours=1, note="both"),
        request=_request(1),
    )
    assert store.activations.live_activations() == ()
    assert store.activations.halted_activations()[0][1].is_halted
    assert len(store.activations.states()) == 1


def test_a_finished_activation_is_reported_as_finished(store) -> None:
    _, subject = _activated(store)
    for kind, hours in (
        (TradeLifecycleKind.EXPIRED, 1),
        (TradeLifecycleKind.OUTCOME_RECORDED, 2),
    ):
        store.activations.append_event(
            _event(
                subject,
                kind,
                hours=hours,
                causing_close_time=(
                    at(hours)
                    if kind is TradeLifecycleKind.EXPIRED
                    else Absent("frozen by the run, not by a candle")
                ),
            ),
            request=_request(hours),
        )
    assert store.activations.finished()[0][1].state is TradeLifecycleState.RESOLVED


def test_the_state_a_store_would_have_reported_at_a_past_instant(store) -> None:
    _, subject = _activated(store)
    store.activations.append_event(
        _event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1),
        request=_request(4),
    )
    assert store.activations.state_as_known_at(
        subject.activation_id, at(3)
    ).state is TradeLifecycleState.PENDING
    assert store.activations.state_as_known_at(
        subject.activation_id, at(5)
    ).state is TradeLifecycleState.TRIGGERED


def test_reading_the_state_of_something_that_is_not_an_activation_is_refused(
    store,
) -> None:
    with pytest.raises(RecordMissingError, match="not in this store"):
        store.activations.state("trade_activation-x-20260801T000000Z-" + "0" * 16)


def test_a_criteria_narrows_the_listing_without_changing_the_fold(store) -> None:
    _, subject = _activated(store)
    assert store.activations.activations(SearchCriteria(book="paper")) != ()
    assert store.activations.activations(SearchCriteria(book="swing")) == ()
    assert store.activations.amendments_for(subject.activation_id) == ()
    assert store.activations.live_amendments_for(subject.activation_id) == ()


# --------------------------------------------------------------------------
# The candle fetcher
# --------------------------------------------------------------------------


def CLOCK() -> "datetime":
    """A fixed instant after the helper's own candles. Never `now()`."""
    from trade_domain_helpers import AT

    return AT(20)


def test_the_fetcher_returns_closed_candles_and_names_its_defaults() -> None:
    assert SIMULATION_INTERVAL == "1h"
    assert SIMULATION_CANDLE_LIMIT >= 1
    fetched = fetch_simulation_candles(
        ("BTCUSDT",),
        transport=klines_transport(1.0, 2.0, 3.0),
        clock=CLOCK,
    )
    assert fetched.fetched_symbols == ("BTCUSDT",)
    assert fetched.failed_symbols == ()
    candles = fetched.series["BTCUSDT"].candles
    assert len(candles) == 3
    assert all(candle.is_closed for candle in candles)


def test_a_forming_bar_is_dropped_before_a_simulation_can_see_it() -> None:
    """The no-lookahead boundary, checked at the fetch as well as in the
    converter — two independent mechanisms over one rule."""
    fetched = fetch_simulation_candles(
        ("BTCUSDT",),
        transport=klines_transport(1.0, 2.0, forming=True),
        clock=CLOCK,
    )
    candles = fetched.series["BTCUSDT"].candles
    assert len(candles) == 1
    assert all(candle.is_closed for candle in candles)


def test_duplicate_symbols_are_collapsed_preserving_first_seen_order() -> None:
    fetched = fetch_simulation_candles(
        ("BTCUSDT", "ETHUSDT", "BTCUSDT"),
        transport=klines_transport(1.0, 2.0),
        clock=CLOCK,
    )
    assert fetched.fetched_symbols == ("BTCUSDT", "ETHUSDT")


def test_one_symbols_outage_never_stops_the_others() -> None:
    def _selective(url: str):
        if "ETHUSDT" in url:
            return failing_transport("provider rejected the symbol")(url)
        return klines_transport(1.0, 2.0)(url)

    fetched = fetch_simulation_candles(
        ("BTCUSDT", "ETHUSDT"), transport=_selective, clock=CLOCK
    )
    assert fetched.fetched_symbols == ("BTCUSDT",)
    assert fetched.failed_symbols == ("ETHUSDT",)
    assert "BinanceTransportError" in fetched.failures["ETHUSDT"]


def test_asking_for_nothing_returns_an_empty_fetch_rather_than_failing() -> None:
    """A store with no live activation needs no candles, and that is an ordinary
    morning."""
    fetched = fetch_simulation_candles((), transport=klines_transport(1.0), clock=CLOCK)
    assert fetched.fetched_symbols == ()
    assert fetched.failed_symbols == ()


def test_the_window_reports_how_far_back_it_reached() -> None:
    """An activation older than the fetched window would otherwise be replayed
    from the middle of its own life."""
    fetched = fetch_simulation_candles(
        ("BTCUSDT",), transport=klines_transport(1.0, 2.0), clock=CLOCK
    )
    assert fetched.earliest_close_of("BTCUSDT") is not None
    assert fetched.earliest_close_of("ETHUSDT") is None
    assert CandleFetch(series={}, failures={}).earliest_close_of("BTCUSDT") is None


def test_an_empty_series_reports_no_earliest_bar() -> None:
    from fmis.data import CandleSeries

    empty = CandleFetch(
        series={"BTCUSDT": CandleSeries(symbol="BTCUSDT", timeframe="1h", candles=())},
        failures={},
    )
    assert empty.earliest_close_of("BTCUSDT") is None


def test_a_caller_error_becomes_a_failure_row_rather_than_an_abort() -> None:
    fetched = fetch_simulation_candles(
        ("BTCUSDT",), interval="not-an-interval", transport=klines_transport(1.0),
        clock=CLOCK,
    )
    assert fetched.failed_symbols == ("BTCUSDT",)


def test_a_base_url_is_forwarded_to_the_provider_unchanged() -> None:
    seen: list[str] = []

    def _recording(url: str):
        seen.append(url)
        return klines_transport(1.0, 2.0)(url)

    fetch_simulation_candles(
        ("BTCUSDT",),
        transport=_recording,
        clock=CLOCK,
        base_url="https://example.invalid/api/v3",
    )
    assert seen and seen[0].startswith("https://example.invalid/api/v3")
