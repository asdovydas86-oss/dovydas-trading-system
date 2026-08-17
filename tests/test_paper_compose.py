"""Milestone BO — the write path, against a real store on disk.

The properties these exercise are the ones only a store can prove.

**Re-running writes nothing.** Every id is a digest of its record's content and
every value the engine derives is a function of the bars alone, so a second run
over the same candles publishes nothing — asserted by comparing the store's bytes
before and after.

**A simulated fill is a real ledger `Trade` under `Book.PAPER`**, so the position
fold, the portfolio and the exposure engine all work with no new code.

**Every transition writes a journal entry.** No silent state change, taken
literally.

**The proposal's own stream is advanced, and only when that is legal.**
`ENTRY_TRIGGERED` requires `DECIDED`, so a proposal the owner never decided on is
left untouched and the skip is reported rather than forced.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from fmis.accounts import AccountId, Book
from fmis.ledger import LedgerSource
from fmis.money import AssetCode, Quantity
from fmis.persistence import RecordKind, TradingStore
from fmis.provenance import ValueOrigin
from fmis.snapshotting import TradeDirection
from fmis.trade_capture import PlanRequest, record_plan
from fmis.trade_lifecycle import (
    EntryType,
    ExitReason,
    StopManagement,
    TradeLifecycleKind,
    TradeLifecycleState,
)
from fmis.paper import (
    PAPER_AUTHOR,
    PAPER_DUST_POLICY,
    PAPER_FX_SOURCE,
    ActivateRequest,
    AmendStopRequest,
    CancelRequest,
    PaperRefusedError,
    PaperTradeNotFoundError,
    activate_trade,
    amend_stop,
    cancel_activation,
    fills_for_activation,
    list_paper_trades,
    load_paper_trade,
    run_simulation,
)
from paper_helpers import MARKET, START, at, bar, break_even


@pytest.fixture()
def store(tmp_path: Path) -> TradingStore:
    return TradingStore(tmp_path / "store", dust=PAPER_DUST_POLICY)


def committed_plan(store: TradingStore, **overrides):
    fields = {
        "market": MARKET,
        "book": Book.PAPER,
        "direction": TradeDirection.LONG,
        "stop": Decimal("95"),
        "targets": (Decimal("110"), Decimal("120")),
        "committed_at": START,
        "written_at": START,
        "author": "owner",
        "confidence": "medium",
        "code_version": "test",
    }
    fields.update(overrides)
    return record_plan(store, PlanRequest(**fields)).view.plan


def activate(store: TradingStore, plan_id: str, **overrides):
    fields = {
        "plan_id": plan_id,
        "account": AccountId("paper"),
        "quantity": Quantity(Decimal("1"), AssetCode("BTC")),
        "entry_type": EntryType.STOP_ENTRY,
        "entry_price": Decimal("100"),
        "interval": "1h",
        "activated_at": START,
        "written_at": START,
        "code_version": "test",
        "fractions": (Decimal("0.5"), Decimal("0.5")),
    }
    fields.update(overrides)
    return activate_trade(store, ActivateRequest(**fields))


WINNING_BARS = (
    bar(0, "98", "99", "97", "98"),
    bar(1, "99", "101", "98", "100"),
    bar(2, "100", "112", "99", "111"),
    bar(3, "111", "121", "110", "120"),
)


def simulate(store: TradingStore, bars=WINNING_BARS, *, hours: int = 8):
    return run_simulation(
        store,
        ran_at=at(hours),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": bars},
    )


def _digest(root: Path) -> str:
    sha = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            sha.update(str(path).encode())
            sha.update(path.read_bytes())
    return sha.hexdigest()


# --------------------------------------------------------------------------
# Activating
# --------------------------------------------------------------------------


def test_activating_writes_the_instruction_and_one_journal_entry(store) -> None:
    plan = committed_plan(store)
    outcome = activate(store, plan.plan_id)
    assert outcome.action == "activated"
    assert {kind for kind, _, _ in outcome.written} == {
        "trade_activation",
        "journal_entry",
    }
    assert outcome.created_any


def test_activating_writes_no_lifecycle_event(store) -> None:
    """An activation's stream begins at `PENDING`, which is the fold's starting
    state and not something an event has to assert."""
    plan = committed_plan(store)
    outcome = activate(store, plan.plan_id)
    assert store.activations.events_for(outcome.activation.activation_id) == ()
    assert (
        store.activations.state(outcome.activation.activation_id).state
        is TradeLifecycleState.PENDING
    )


def test_re_activating_the_identical_instruction_writes_nothing(store) -> None:
    plan = committed_plan(store)
    activate(store, plan.plan_id)
    before = _digest(store.root)
    again = activate(store, plan.plan_id)
    assert not again.created_any
    assert _digest(store.root) == before


def test_the_ladder_defaults_to_the_whole_position_at_the_first_target(store) -> None:
    plan = committed_plan(store)
    outcome = activate(store, plan.plan_id, fractions=())
    ladder = outcome.activation.ladder
    assert len(ladder.legs) == 1
    assert ladder.legs[0].target == Decimal("110")
    assert ladder.legs[0].fraction == Decimal("1")


def test_a_plan_naming_no_target_produces_a_ladder_that_runs_to_the_stop(store) -> None:
    plan = committed_plan(store, targets=())
    outcome = activate(store, plan.plan_id)
    assert outcome.activation.ladder.is_empty


def test_more_shares_than_targets_is_refused(store) -> None:
    plan = committed_plan(store, targets=(Decimal("110"),))
    with pytest.raises(PaperRefusedError, match="nothing to exit at"):
        activate(store, plan.plan_id, fractions=(Decimal("0.5"), Decimal("0.5")))


def test_activating_something_that_is_not_a_plan_is_refused(store) -> None:
    plan = committed_plan(store)
    outcome = activate(store, plan.plan_id)
    with pytest.raises(Exception):
        activate(store, outcome.activation.activation_id)


# --------------------------------------------------------------------------
# Simulating
# --------------------------------------------------------------------------


def test_a_full_run_reaches_a_resolution_and_freezes_an_outcome(store) -> None:
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    report = simulate(store)
    assert report.advanced == 1
    view = load_paper_trade(store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8))
    assert view.state is TradeLifecycleState.RESOLVED
    assert view.is_finished
    assert view.outcome.outcome.exit_reason is ExitReason.TARGET_HIT


def test_a_second_run_over_the_same_candles_writes_nothing(store) -> None:
    plan = committed_plan(store)
    activate(store, plan.plan_id)
    simulate(store)
    before = _digest(store.root)
    again = simulate(store, hours=9)
    assert not again.created_any
    assert _digest(store.root) == before


def test_a_second_run_over_a_still_live_trade_writes_nothing(store) -> None:
    """The case that matters, and the one a finished trade cannot exercise: a
    trade still waiting for bars is replayed from the beginning every time, so
    every event it already produced must be recognised rather than rewritten.

    The first run's `recorded_at` stands, which is correct — that is when this
    system actually learned of it.
    """
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    first = simulate(store, bars=WINNING_BARS[:3], hours=5)
    assert first.created_any
    before = _digest(store.root)
    again = simulate(store, bars=WINNING_BARS[:3], hours=6)
    assert not again.created_any
    assert again.runs[0].bars_advanced == 3
    assert _digest(store.root) == before
    assert (
        store.activations.state(subject.activation_id).state
        is TradeLifecycleState.PARTIALLY_EXITED
    )


def test_a_run_that_sees_more_bars_appends_only_the_new_events(store) -> None:
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    simulate(store, bars=WINNING_BARS[:3], hours=5)
    before = len(store.activations.events_for(subject.activation_id))
    simulate(store, bars=WINNING_BARS, hours=6)
    after = store.activations.events_for(subject.activation_id)
    assert len(after) > before
    assert (
        store.activations.state(subject.activation_id).state
        is TradeLifecycleState.RESOLVED
    )


def test_the_owner_may_move_a_stop_before_anything_has_filled(store) -> None:
    """Adjusting an invalidation while an entry is still waiting is an ordinary
    act, and the stop that results is the one the fill will be sized against."""
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    amend_stop(
        store,
        AmendStopRequest(
            activation_id=subject.activation_id,
            new_stop=Decimal("97"),
            reason="structure_changed",
            author="owner",
            occurred_at=at(1),
            written_at=at(1),
            code_version="test",
        ),
    )
    assert (
        store.activations.state(subject.activation_id).state
        is TradeLifecycleState.PENDING
    )
    assert (
        store.activations.stop_history(
            subject.activation_id,
            initial_stop=plan.initial_invalidation,
            direction=plan.direction,
        ).effective
        == Decimal("97")
    )


def test_a_simulated_fill_is_a_real_ledger_trade_under_the_paper_book(store) -> None:
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    simulate(store)
    fills = fills_for_activation(store, subject.activation_id)
    assert len(fills) == 3
    for entry in fills:
        assert entry.trade.book is Book.PAPER
        assert entry.trade.source is LedgerSource.PAPER_SIMULATION
        assert entry.trade.asserted_by == PAPER_AUTHOR
        assert entry.trade.fee.is_zero
        assert entry.trade.fx_source == PAPER_FX_SOURCE


def test_the_position_fold_works_on_a_paper_trade_with_no_new_code(store) -> None:
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    simulate(store)
    view = load_paper_trade(store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8))
    assert view.position.realized_pnl_net.amount == Decimal("15")
    assert view.monitor.realized_r == Decimal("3")


def test_every_transition_writes_a_journal_entry(store) -> None:
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    simulate(store)
    journal = store.journals.trade_journal("trade_activation", subject.activation_id)
    tagged = {
        tag.term.term_id
        for entry in journal.entries
        for tag in entry.tags
        if tag.term.vocabulary_id == "lifecycle_event"
    }
    assert {
        TradeLifecycleKind.ENTRY_TRIGGERED.value,
        TradeLifecycleKind.ENTRY_FILLED.value,
        TradeLifecycleKind.PARTIAL_EXIT_FILLED.value,
        TradeLifecycleKind.EXIT_FILLED.value,
    } <= tagged


def test_the_simulator_never_authors_an_idea(store) -> None:
    """An idea is the owner's, and a simulator that could author one would
    pollute the discipline metric that counts whether the owner wrote anything."""
    from fmis.journal import JournalKind

    plan = committed_plan(store)
    activate(store, plan.plan_id)
    simulate(store)
    authored = [
        entry
        for entry in store.journals.live_entries()
        if entry.author == PAPER_AUTHOR
    ]
    assert authored
    assert all(entry.kind is JournalKind.NOTE for entry in authored)


def test_an_activation_on_another_interval_is_skipped_and_the_page_says_so(store) -> None:
    plan = committed_plan(store)
    activate(store, plan.plan_id, interval="4h")
    report = simulate(store)
    assert report.runs == ()
    assert "excursions measured across two intervals" in report.skipped[0][1]


def test_a_market_with_no_candles_is_skipped_and_named(store) -> None:
    plan = committed_plan(store)
    activate(store, plan.plan_id)
    report = run_simulation(
        store, ran_at=at(8), code_version="test", interval="1h", bars_by_symbol={}
    )
    assert "no 1h candles for BTCUSDT" in report.skipped[0][1]


def test_a_fetch_failure_is_carried_onto_the_page_rather_than_dropped(store) -> None:
    report = run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={},
        failures={"ETHUSDT": "transport error"},
    )
    assert report.unreachable == (("ETHUSDT", "transport error"),)


def test_a_run_can_be_narrowed_to_named_markets(store) -> None:
    plan = committed_plan(store)
    activate(store, plan.plan_id)
    report = run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": WINNING_BARS},
        markets=("ETHUSDT",),
    )
    assert report.runs == ()


# --------------------------------------------------------------------------
# Stop management and cancellation
# --------------------------------------------------------------------------


def test_the_owner_can_move_a_stop_and_the_plan_is_untouched(store) -> None:
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    before = store.plans.load(plan.plan_id).to_payload()
    amend_stop(
        store,
        AmendStopRequest(
            activation_id=subject.activation_id,
            new_stop=Decimal("90"),
            reason="volatility_expanded",
            author="owner",
            occurred_at=at(1),
            written_at=at(1),
            code_version="test",
        ),
    )
    assert store.plans.load(plan.plan_id).to_payload() == before
    history = store.activations.stop_history(
        subject.activation_id,
        initial_stop=plan.initial_invalidation,
        direction=plan.direction,
    )
    assert history.effective == Decimal("90")
    assert history.widening_count == 1
    assert history.moves[0].origin is ValueOrigin.ASSERTED


def test_a_backdated_stop_move_is_refused(store) -> None:
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    request = dict(
        activation_id=subject.activation_id,
        reason="de_risking",
        author="owner",
        code_version="test",
    )
    amend_stop(
        store,
        AmendStopRequest(
            new_stop=Decimal("97"), occurred_at=at(3), written_at=at(3), **request
        ),
    )
    with pytest.raises(PaperRefusedError, match="before the last one"):
        amend_stop(
            store,
            AmendStopRequest(
                new_stop=Decimal("98"), occurred_at=at(1), written_at=at(1), **request
            ),
        )


def test_a_policy_move_is_recorded_with_its_policy_and_its_candle(store) -> None:
    plan = committed_plan(store)
    subject = activate(
        store, plan.plan_id, stop_management=break_even()
    ).activation
    simulate(store, bars=WINNING_BARS[:3])
    amendments = store.activations.live_amendments_for(subject.activation_id)
    assert len(amendments) == 1
    assert amendments[0].origin is ValueOrigin.POLICY_DERIVED
    assert amendments[0].policy_id == "fmits-paper-fill"
    assert amendments[0].reason.term_id == "break_even"


def test_an_owner_move_survives_the_next_replay(store) -> None:
    """A replay that ignored it would silently undo the owner's own decision."""
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    simulate(store, bars=WINNING_BARS[:2], hours=5)
    amend_stop(
        store,
        AmendStopRequest(
            activation_id=subject.activation_id,
            new_stop=Decimal("110"),
            reason="de_risking",
            author="owner",
            occurred_at=at(2),
            written_at=at(6),
            code_version="test",
        ),
    )
    simulate(store, bars=WINNING_BARS, hours=7)
    view = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
    )
    assert view.state is TradeLifecycleState.RESOLVED
    assert view.stop_history.effective == Decimal("110")


def test_cancelling_is_legal_before_a_fill_and_refused_after_one(store) -> None:
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    request = CancelRequest(
        activation_id=subject.activation_id,
        reason="thesis_invalidated",
        author="owner",
        occurred_at=at(1),
        written_at=at(1),
        code_version="test",
    )
    cancel_activation(store, request)
    assert (
        store.activations.state(subject.activation_id).state
        is TradeLifecycleState.CANCELLED
    )


def test_cancelling_an_open_position_raises_rather_than_abandoning_a_fill(store) -> None:
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    simulate(store, bars=WINNING_BARS[:2], hours=5)
    from fmis.trade_lifecycle import IllegalLifecycleTransitionError

    with pytest.raises(IllegalLifecycleTransitionError):
        cancel_activation(
            store,
            CancelRequest(
                activation_id=subject.activation_id,
                reason="thesis_invalidated",
                author="owner",
                occurred_at=at(6),
                written_at=at(6),
                code_version="test",
            ),
        )


# --------------------------------------------------------------------------
# The store's own rules
# --------------------------------------------------------------------------


def test_an_event_about_an_activation_nobody_wrote_is_refused(store) -> None:
    from fmis.persistence import RecordMissingError, WriteRequest, WriteSource
    from fmis.provenance import VersionedTerm
    from fmis.records import RecordAudit
    from fmis.trade_lifecycle import TradeLifecycleEvent
    from paper_helpers import activation as build

    orphan = TradeLifecycleEvent(
        activation_id=build().activation_id,
        kind=TradeLifecycleKind.ENTRY_TRIGGERED,
        occurred_at=at(1),
        recorded_at=at(1),
        audit=RecordAudit.frozen_at(at(1)),
        causing_close_time=at(1),
    )
    from fmis.paper import paper_version_set

    request = WriteRequest(
        written_at=at(1),
        source=WriteSource.POLICY_ENGINE,
        author="test",
        reason=VersionedTerm(
            vocabulary_id="write_reason", term_id="test", taxonomy_version=1
        ),
        version_set=paper_version_set(code_version="test"),
    )
    with pytest.raises(RecordMissingError, match="never be folded"):
        store.activations.create(orphan, request=request)


def test_an_activation_and_an_outcome_are_frozen(store) -> None:
    from fmis.persistence import FrozenRecordError

    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    with pytest.raises(FrozenRecordError, match="captured artifact"):
        store.activations.replace(subject.activation_id)


def test_the_store_verifies_after_a_full_simulation(store) -> None:
    plan = committed_plan(store)
    activate(store, plan.plan_id)
    simulate(store)
    verification = store.verify()
    assert verification.ok
    assert verification.journal_problems == ()
    assert verification.integrity_failures == ()
    assert verification.unjournalled_records == ()


def test_a_listing_can_be_narrowed_by_state_and_by_market(store) -> None:
    plan = committed_plan(store)
    activate(store, plan.plan_id)
    simulate(store)
    assert len(list_paper_trades(store, dust=PAPER_DUST_POLICY, at=at(8))) == 1
    assert (
        list_paper_trades(
            store,
            dust=PAPER_DUST_POLICY,
            at=at(8),
            states=(TradeLifecycleState.PENDING,),
        )
        == ()
    )
    assert (
        list_paper_trades(
            store, dust=PAPER_DUST_POLICY, at=at(8), market="ETHUSDT"
        )
        == ()
    )


def test_an_id_that_is_not_in_this_store_is_a_named_refusal(store) -> None:
    with pytest.raises(PaperTradeNotFoundError, match="fmits trade status"):
        load_paper_trade(
            store,
            "trade_activation-x-20260801T000000Z-" + "0" * 16,
            dust=PAPER_DUST_POLICY,
            at=at(8),
        )


def test_a_stop_run_records_a_stop_hit_outcome(store) -> None:
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    simulate(
        store,
        bars=(
            bar(0, "99", "101", "98", "100"),
            bar(1, "100", "101", "94", "95"),
        ),
    )
    view = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
    )
    assert view.outcome.outcome.exit_reason is ExitReason.STOP_HIT
    assert view.outcome.final_r == Decimal("-1")
    assert view.outcome.stop_hit


def test_an_expired_activation_freezes_an_outcome_that_held_no_position(store) -> None:
    plan = committed_plan(store)
    subject = activate(
        store,
        plan.plan_id,
        entry_type=EntryType.LIMIT,
        entry_price=Decimal("50"),
        expires_at=at(2),
    ).activation
    simulate(store, bars=(bar(0, "98", "99", "97", "98"), bar(2, "98", "99", "97", "98")))
    outcome = store.activations.outcome_for(subject.activation_id)
    assert outcome.exit_reason is ExitReason.EXPIRED
    assert not outcome.held_exposure
    assert outcome.fill_event_ids == ()


def test_the_new_record_kinds_are_all_registered(store) -> None:
    for kind in (
        RecordKind.TRADE_ACTIVATION,
        RecordKind.TRADE_LIFECYCLE_EVENT,
        RecordKind.STOP_AMENDMENT,
        RecordKind.TRADE_OUTCOME,
    ):
        assert kind in store.activations.kinds


def test_the_outcome_transition_writes_a_journal_entry_like_every_other(store) -> None:
    """Found by an adversarial review. The first draft wrote this transition to
    the lifecycle stream and not to the journal, so the one event that says a
    trade is over was the only one the owner's own history did not record."""
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    simulate(store)
    journal = store.journals.trade_journal("trade_activation", subject.activation_id)
    tagged = {
        tag.term.term_id
        for entry in journal.entries
        for tag in entry.tags
        if tag.term.vocabulary_id == "lifecycle_event"
    }
    assert TradeLifecycleKind.OUTCOME_RECORDED.value in tagged


def test_every_kind_the_engine_can_emit_reaches_the_journal(store) -> None:
    """The brief's §11 as a set comparison rather than a sample: whatever the
    engine records, the owner's history records too."""
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    simulate(store)
    stream = {
        event.kind.value
        for event in store.activations.live_events_for(subject.activation_id)
    }
    journal = store.journals.trade_journal("trade_activation", subject.activation_id)
    tagged = {
        tag.term.term_id
        for entry in journal.entries
        for tag in entry.tags
        if tag.term.vocabulary_id == "lifecycle_event"
    }
    assert stream <= tagged, sorted(stream - tagged)


def test_a_short_runs_its_whole_life_through_the_store_as_a_long_does(store) -> None:
    """The mirror, end to end rather than in the engine alone. Given a document
    that exists because of a recorded long bias, symmetry is a test."""
    plan = committed_plan(
        store,
        direction=TradeDirection.SHORT,
        stop=Decimal("105"),
        targets=(Decimal("90"), Decimal("80")),
    )
    subject = activate(
        store,
        plan.plan_id,
        entry_price=Decimal("100"),
        fractions=(Decimal("0.5"), Decimal("0.5")),
    ).activation
    run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={
            "BTCUSDT": (
                bar(0, "101", "102", "99", "100"),
                bar(1, "100", "101", "88", "89"),
                bar(2, "89", "90", "79", "80"),
            )
        },
    )
    view = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
    )
    assert view.state is TradeLifecycleState.RESOLVED
    assert view.outcome.outcome.exit_reason is ExitReason.TARGET_HIT
    assert view.outcome.entry_price == Decimal("100")
    assert view.outcome.exit_price == Decimal("85")
    assert view.outcome.realized_pnl_net.amount == Decimal("15")
    assert view.outcome.final_r == Decimal("3")
    assert [entry.trade.side.value for entry in view.fills] == ["sell", "buy", "buy"]


def test_a_paper_fill_never_reaches_a_real_money_aggregate(store) -> None:
    """`AP` R12's contamination hazard, asserted rather than described.
    `DEFAULT_EXCLUDED_BOOKS` holds `PAPER`, and the exposure fold honours it."""
    from fmis.accounts import DEFAULT_EXCLUDED_BOOKS
    from fmis.portfolio_risk import read_exposure_lines

    plan = committed_plan(store)
    activate(store, plan.plan_id)
    simulate(store, bars=WINNING_BARS[:2], hours=5)
    assert Book.PAPER in DEFAULT_EXCLUDED_BOOKS
    lines = read_exposure_lines(store)
    assert [line for line in lines if line.book is Book.PAPER] == []
    assert lines == ()


def test_a_run_advances_no_candle_that_closed_after_the_run_itself(store) -> None:
    """Found by an adversarial review. The fetch reaches back further than any
    activation and forward to the live edge; a past-dated run over live candles
    would otherwise write events whose `occurred_at` is later than their own
    `recorded_at` — a refusal the domain raises correctly and cryptically, two
    layers down. `--reference-time` is a replay clock, not a label."""
    plan = committed_plan(store)
    subject = activate(store, plan.plan_id).activation
    report = run_simulation(
        store,
        ran_at=at(2),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": WINNING_BARS},
    )
    assert report.runs[0].bars_advanced == 3
    assert store.activations.state(subject.activation_id).state is (
        TradeLifecycleState.PARTIALLY_EXITED
    )
    for event in store.activations.live_events_for(subject.activation_id):
        assert event.occurred_at <= at(2)


def test_a_run_advances_no_candle_that_opened_before_the_activation(store) -> None:
    """A provider page reaches back further than any activation. Counting those
    bars would make *'bars advanced'* a figure about the fetch, not the trade."""
    plan = committed_plan(store, committed_at=at(2), written_at=at(2))
    activate(store, plan.plan_id, activated_at=at(2), written_at=at(2))
    report = run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": WINNING_BARS},
    )
    assert report.runs[0].bars_advanced == 2


def test_the_window_helper_is_bounded_at_both_ends() -> None:
    from fmis.paper import bars_for_run
    from paper_helpers import activation as build

    subject = build(activated_at=at(1))
    windowed = bars_for_run(subject, WINNING_BARS, ran_at=at(2))
    assert [candle.open_time for candle in windowed] == [at(1), at(2)]
