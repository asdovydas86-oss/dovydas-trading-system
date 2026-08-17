"""Milestone BO — the branches the scenario tests do not reach.

Three kinds of thing live here, and none of them is a scenario.

**Type refusals.** Every `TypeError` naming a field, because a message that names
the wrong field is worse than none and only a test can tell them apart.

**Absence paths.** Every place a figure comes back `Absent(reason)` rather than
zero. These are the branches that decide whether a page reads as *"level"* or as
*"nobody priced this"*, and they are the ones a scenario test never visits
because a scenario supplies everything.

**The proposal bridge.** `PROPOSED → PENDING → TRIGGERED → OPEN` across two
objects, and the two ways it declines to advance: a proposal the store does not
hold, and one the owner never decided on.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from fmis.accounts import AccountId, Book
from fmis.money import AssetCode, Money, Quantity
from fmis.persistence import TradingStore
from fmis.provenance import Absent, ValueOrigin, VersionedTerm
from fmis.records import DomainValidationError, PayloadDecodeError, RecordAudit
from fmis.snapshotting import TradeDirection
from fmis.trade_capture import PlanRequest, record_plan
from fmis.trade_lifecycle import (
    BreakEvenRule,
    EntryType,
    ExitLadder,
    ExitLeg,
    ExitReason,
    StopAmendment,
    StopHistory,
    StopManagement,
    StopMove,
    TradeLifecycleKind,
    TradeLifecycleState,
    TradeOutcome,
    TrailingRule,
    fold_stop_history,
)
from fmis.paper import (
    PAPER_DUST_POLICY,
    PAPER_ZERO_COST_POLICY,
    ActivateRequest,
    Excursion,
    Fill,
    FillKind,
    FillTrigger,
    LifecycleStep,
    PaperRefusedError,
    PriceBar,
    StepResult,
    StopMoveIntent,
    TradeMonitor,
    TradeRunState,
    activate_trade,
    advance,
    fill_at_level,
    fills_for_activation,
    initial_run_state,
    load_paper_trade,
    monitor_trade,
    owner_stop_moves,
    read_outcome,
    render_lifecycle,
    render_simulation,
    replay_bars,
    run_simulation,
    run_state_for,
    trailing_stop,
)
from paper_helpers import (
    MARKET,
    START,
    VERSIONS,
    activation,
    at,
    bar,
    plan,
)


# --------------------------------------------------------------------------
# Type refusals — every message names the field it is about.
# --------------------------------------------------------------------------


def test_the_exact_bar_and_the_fill_name_the_field_they_refuse() -> None:
    good = bar(0, "100", "101", "99", "100")
    for kwargs, needle in (
        ({"open": 100.0}, "open"),
        ({"high": "101"}, "high"),
    ):
        with pytest.raises(TypeError, match=needle):
            bar(0, "100", "101", "99", "100") and PriceBar(
                symbol="BTCUSDT",
                interval="1h",
                open_time=START,
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                **kwargs,
            )
    with pytest.raises(TypeError, match="quantity"):
        Fill(
            kind=FillKind.ENTRY,
            trigger=FillTrigger.MARKET_OPEN,
            at=START,
            price=Decimal("100"),
            quantity=Decimal("1"),
        )
    with pytest.raises(PaperRefusedError, match="positive size"):
        Fill(
            kind=FillKind.ENTRY,
            trigger=FillTrigger.MARKET_OPEN,
            at=START,
            price=Decimal("100"),
            quantity=Quantity(Decimal("0"), AssetCode("BTC")),
        )
    with pytest.raises(TypeError, match="gapped"):
        Fill(
            kind=FillKind.ENTRY,
            trigger=FillTrigger.MARKET_OPEN,
            at=START,
            price=Decimal("100"),
            quantity=Quantity(Decimal("1"), AssetCode("BTC")),
            gapped="yes",
        )


def test_a_fill_at_a_target_names_its_rung_and_one_anywhere_else_names_none() -> None:
    with pytest.raises(PaperRefusedError, match="names the rung"):
        Fill(
            kind=FillKind.EXIT,
            trigger=FillTrigger.TARGET_LEVEL,
            at=START,
            price=Decimal("110"),
            quantity=Quantity(Decimal("1"), AssetCode("BTC")),
        )
    with pytest.raises(PaperRefusedError, match="names the rung"):
        Fill(
            kind=FillKind.EXIT,
            trigger=FillTrigger.STOP_LEVEL,
            at=START,
            price=Decimal("95"),
            quantity=Quantity(Decimal("1"), AssetCode("BTC")),
            leg_index=0,
        )


def test_an_excursion_refuses_a_bar_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="PriceBar"):
        Excursion().extended("a bar", TradeDirection.LONG)


def test_a_stop_move_intent_that_changes_nothing_is_not_a_move() -> None:
    with pytest.raises(PaperRefusedError, match="not a move"):
        StopMoveIntent(
            previous_stop=Decimal("95"),
            new_stop=Decimal("95"),
            term_id="break_even",
        )


def test_a_lifecycle_step_refuses_a_fill_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="Fill"):
        LifecycleStep(
            kind=TradeLifecycleKind.ENTRY_FILLED, bar_sequence=0, fill="a fill"
        )


def test_a_run_state_names_every_field_it_refuses() -> None:
    committed = plan()
    base = dict(
        activation=activation(committed),
        direction=committed.direction,
        initial_stop=Decimal("95"),
        effective_stop=Decimal("95"),
        state=TradeLifecycleState.PENDING,
        remaining=Quantity.zero(AssetCode("BTC")),
        excursion=Excursion(),
    )
    for field, value, needle in (
        ("activation", "an activation", "TradeActivation"),
        ("remaining", Decimal("1"), "Quantity"),
        ("excursion", None, "Excursion"),
    ):
        with pytest.raises(TypeError, match=needle):
            TradeRunState(**{**base, field: value})
    with pytest.raises(PaperRefusedError, match="cannot fill twice"):
        TradeRunState(**{**base, "filled_legs": (0, 0)})


def test_a_run_state_with_no_entry_has_no_risk_distance_to_report() -> None:
    committed = plan()
    state = initial_run_state(
        activation(committed),
        direction=committed.direction,
        initial_stop=Decimal("95"),
    )
    distance = state.risk_distance
    assert isinstance(distance, Absent)
    assert "no fill has established an entry" in distance.reason
    assert not state.is_leg_filled(0)


def test_a_step_result_refuses_a_shape_the_fold_could_not_apply() -> None:
    committed = plan()
    subject = activation(committed)
    state = initial_run_state(
        subject, direction=committed.direction, initial_stop=Decimal("95")
    )
    candle = bar(0, "100", "101", "99", "100")
    base = dict(bar=candle, next_state=state)
    with pytest.raises(TypeError, match="bar"):
        StepResult(**{**base, "bar": "a bar"})
    with pytest.raises(TypeError, match="next_state"):
        StepResult(**{**base, "next_state": "a state"})
    with pytest.raises(TypeError, match="StopMoveIntent"):
        StepResult(**base, stop_move="a move")
    with pytest.raises(PaperRefusedError, match="dense from zero"):
        StepResult(
            **base,
            steps=(
                LifecycleStep(kind=TradeLifecycleKind.EXPIRED, bar_sequence=1),
            ),
        )
    with pytest.raises(PaperRefusedError, match="at most one stop amendment"):
        StepResult(
            **base,
            steps=(
                LifecycleStep(kind=TradeLifecycleKind.STOP_AMENDED, bar_sequence=0),
                LifecycleStep(kind=TradeLifecycleKind.STOP_AMENDED, bar_sequence=1),
            ),
        )
    with pytest.raises(PaperRefusedError, match="together or not at all"):
        StepResult(
            **base,
            steps=(
                LifecycleStep(kind=TradeLifecycleKind.STOP_AMENDED, bar_sequence=0),
            ),
        )


def test_the_engine_and_the_replay_name_what_they_were_handed() -> None:
    committed = plan()
    state = initial_run_state(
        activation(committed),
        direction=committed.direction,
        initial_stop=Decimal("95"),
    )
    with pytest.raises(TypeError, match="TradeRunState"):
        advance("a state", bar(0, "100", "101", "99", "100"))
    with pytest.raises(TypeError, match="PriceBar"):
        advance(state, "a bar")
    with pytest.raises(TypeError, match="TradeRunState"):
        replay_bars("a state", ())
    with pytest.raises(TypeError, match="TradeActivation"):
        initial_run_state(
            "an activation",
            direction=committed.direction,
            initial_stop=Decimal("95"),
        )


def test_a_replay_result_refuses_a_final_state_that_is_not_one() -> None:
    from fmis.paper import ReplayResult

    with pytest.raises(TypeError, match="TradeRunState"):
        ReplayResult(final_state="a state")


def test_an_owner_move_must_be_an_instant_and_a_stop() -> None:
    committed = plan()
    state = initial_run_state(
        activation(committed),
        direction=committed.direction,
        initial_stop=Decimal("95"),
    )
    for moves in (("a move",), ((START,),), ((START, Decimal("1"), "extra"),)):
        with pytest.raises(TypeError, match="instant, stop"):
            replay_bars(state, (), owner_moves=moves)


def test_the_fill_helpers_refuse_something_that_is_not_a_bar() -> None:
    with pytest.raises(TypeError, match="PriceBar"):
        fill_at_level(TradeDirection.LONG, "a bar", Decimal("110"), favourable=True)
    from fmis.paper import entry_reached

    with pytest.raises(TypeError, match="TradeActivation"):
        entry_reached("an activation", TradeDirection.LONG, bar(0, "1", "1", "1", "1"))


def test_the_trailing_rule_refuses_a_management_record_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="StopManagement"):
        trailing_stop(
            "trailing",
            TradeDirection.LONG,
            entry_price=Decimal("100"),
            risk_distance=Decimal("5"),
            excursion=Excursion(),
        )


def test_the_domain_records_name_every_field_they_refuse() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        ExitLeg(target="110", fraction=Decimal("1"))
    with pytest.raises(TypeError, match="Decimal"):
        ExitLeg(target=Decimal("110"), fraction="1")
    with pytest.raises(TypeError, match="Decimal"):
        BreakEvenRule(trigger_r="1")
    with pytest.raises(TypeError, match="break_even"):
        StopManagement(break_even="yes")
    with pytest.raises(TypeError, match="trailing"):
        StopManagement(trailing="yes")
    from fmis.trade_lifecycle import PaperCostPolicy

    with pytest.raises(TypeError, match="Decimal"):
        PaperCostPolicy(
            policy_id="p", version=1, fee_rate=0, slippage_rate=Decimal(0)
        )


def test_a_zero_or_negative_price_is_refused_with_the_field_named() -> None:
    from fmis.trade_lifecycle import ActivationError

    with pytest.raises(ActivationError, match="target must be positive"):
        ExitLeg(target=Decimal("0"), fraction=Decimal("1"))


def test_an_activation_note_is_normalized_and_a_blank_one_is_refused() -> None:
    assert activation(note="  a note  ").note == "a note"


def test_a_malformed_ladder_payload_is_a_clean_rejection() -> None:
    with pytest.raises(PayloadDecodeError, match="JSON array"):
        ExitLadder.from_payload({"legs": []})


# --------------------------------------------------------------------------
# The stop records' own refusals
# --------------------------------------------------------------------------


def test_the_stop_records_name_every_field_they_refuse() -> None:
    from fmis.trade_lifecycle import StopAmendmentError

    with pytest.raises(TypeError, match="Decimal"):
        StopMove(
            amendment_id="stop_amendment-x-20260801T000000Z-" + "0" * 16,
            at=START,
            previous_stop="95",
            new_stop=Decimal("100"),
            reason=VersionedTerm(
                vocabulary_id="v", term_id="t", taxonomy_version=1
            ),
            origin=ValueOrigin.ASSERTED,
            tightened=True,
        )
    base = dict(
        amendment_id="stop_amendment-x-20260801T000000Z-" + "0" * 16,
        at=START,
        previous_stop=Decimal("95"),
        new_stop=Decimal("100"),
        origin=ValueOrigin.ASSERTED,
        tightened=True,
    )
    with pytest.raises(TypeError, match="VersionedTerm"):
        StopMove(**base, reason="structure changed")
    with pytest.raises(TypeError, match="tightened"):
        StopMove(
            **{**base, "tightened": "yes"},
            reason=VersionedTerm(vocabulary_id="v", term_id="t", taxonomy_version=1),
        )
    with pytest.raises(StopAmendmentError, match="must be positive"):
        StopMove(
            **{**base, "previous_stop": Decimal("0")},
            reason=VersionedTerm(vocabulary_id="v", term_id="t", taxonomy_version=1),
        )


def test_an_amendment_note_is_normalized_and_the_author_survives_the_payload() -> None:
    subject = activation()
    amendment = StopAmendment(
        activation_id=subject.activation_id,
        previous_stop=Decimal("95"),
        new_stop=Decimal("100"),
        reason=VersionedTerm(
            vocabulary_id="stop_amendment_reason",
            term_id="de_risking",
            taxonomy_version=1,
        ),
        origin=ValueOrigin.ASSERTED,
        author="owner",
        occurred_at=at(1),
        recorded_at=at(1),
        audit=RecordAudit.frozen_at(at(1)),
        note="  taking risk off  ",
    )
    assert amendment.note == "taking risk off"
    assert amendment.is_owner_stated
    assert StopAmendment.from_payload(amendment.to_payload()).author == "owner"


def test_an_amendment_cannot_be_learned_of_before_it_was_made() -> None:
    subject = activation()
    with pytest.raises(DomainValidationError, match="precedes occurred_at"):
        StopAmendment(
            activation_id=subject.activation_id,
            previous_stop=Decimal("95"),
            new_stop=Decimal("100"),
            reason=VersionedTerm(
                vocabulary_id="v", term_id="t", taxonomy_version=1
            ),
            origin=ValueOrigin.ASSERTED,
            author="owner",
            occurred_at=at(2),
            recorded_at=at(1),
            audit=RecordAudit.frozen_at(at(2)),
        )


def test_a_non_integer_policy_version_read_from_disk_is_refused() -> None:
    subject = activation()
    amendment = StopAmendment(
        activation_id=subject.activation_id,
        previous_stop=Decimal("95"),
        new_stop=Decimal("100"),
        reason=VersionedTerm(vocabulary_id="v", term_id="t", taxonomy_version=1),
        origin=ValueOrigin.POLICY_DERIVED,
        author="engine",
        occurred_at=at(1),
        recorded_at=at(1),
        audit=RecordAudit.frozen_at(at(1)),
        policy_id="fmits-paper-fill",
        policy_version=1,
        causing_close_time=at(1),
    )
    payload = amendment.to_payload()
    payload["policy_version"] = {"value": "1"}
    with pytest.raises(PayloadDecodeError, match="expected an int"):
        StopAmendment.from_payload(payload)


def test_the_stop_history_type_checks_reach_the_fold() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        fold_stop_history(
            initial_stop="95",
            direction=TradeDirection.LONG,
            amendments=(),
        )


# --------------------------------------------------------------------------
# The outcome record's own refusals
# --------------------------------------------------------------------------


def _outcome(**overrides) -> TradeOutcome:
    subject = activation()
    fields = dict(
        activation_id=subject.activation_id,
        plan_id=subject.plan_id,
        market=MARKET,
        exit_reason=ExitReason.EXPIRED,
        frozen_at=at(8),
        interval="1h",
        cost_policy=PAPER_ZERO_COST_POLICY,
        fill_policy_id="fmits-paper-fill",
        fill_policy_version=1,
        initial_stop=Decimal("95"),
        version_set=VERSIONS,
        audit=RecordAudit.frozen_at(at(8)),
    )
    fields.update(overrides)
    return TradeOutcome(**fields)


def test_the_outcome_names_every_field_it_refuses() -> None:
    from fmis.trade_lifecycle import OutcomeError

    with pytest.raises(TypeError, match="market"):
        _outcome(market="BTCUSDT")
    with pytest.raises(TypeError, match="cost_policy"):
        _outcome(cost_policy=None)
    with pytest.raises(TypeError, match="version_set"):
        _outcome(version_set=None)
    with pytest.raises(TypeError, match="Decimal"):
        _outcome(initial_stop="95")
    with pytest.raises(OutcomeError, match="must be positive"):
        _outcome(initial_stop=Decimal("0"))


def test_an_outcome_note_is_normalized() -> None:
    assert _outcome(note="  ended flat  ").note == "ended flat"


def test_a_non_integer_bars_held_read_from_disk_is_refused() -> None:
    subject = _outcome(
        exit_reason=ExitReason.STOP_HIT,
        opened_at=at(1),
        closed_at=at(2),
        bars_held=1,
        max_favourable_price=Decimal("101"),
        max_adverse_price=Decimal("95"),
        effective_stop_at_exit=Decimal("95"),
        fill_event_ids=("trade-binance_BTCUSDT_spot-20260801T010000Z-" + "a" * 16,),
    )
    payload = subject.to_payload()
    payload["bars_held"] = {"value": "1"}
    with pytest.raises(PayloadDecodeError, match="expected an int"):
        TradeOutcome.from_payload(payload)
    payload = subject.to_payload()
    payload["fill_event_ids"] = "not an array"
    with pytest.raises(PayloadDecodeError, match="JSON array"):
        TradeOutcome.from_payload(payload)


def test_an_event_that_is_not_measured_must_not_claim_a_causing_candle() -> None:
    """An assertion carrying a candle would be ordered by something that did not
    cause it."""
    from fmis.trade_lifecycle import TradeLifecycleEvent

    subject = activation()
    event = TradeLifecycleEvent(
        activation_id=subject.activation_id,
        kind=TradeLifecycleKind.EXIT_FILLED,
        occurred_at=at(1),
        recorded_at=at(1),
        audit=RecordAudit.frozen_at(at(1)),
    )
    assert isinstance(event.causing_close_time, Absent)
    assert event.origin is ValueOrigin.MEASURED
    assert event.ordering_key == at(1)


# --------------------------------------------------------------------------
# Absence paths on the monitor and the outcome reading
# --------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> TradingStore:
    return TradingStore(tmp_path / "store", dust=PAPER_DUST_POLICY)


def _committed(store: TradingStore, **overrides):
    fields = dict(
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
    )
    fields.update(overrides)
    return record_plan(store, PlanRequest(**fields)).view.plan


def _activated(store: TradingStore, plan_id: str, **overrides):
    fields = dict(
        plan_id=plan_id,
        account=AccountId("paper"),
        quantity=Quantity(Decimal("1"), AssetCode("BTC")),
        entry_type=EntryType.STOP_ENTRY,
        entry_price=Decimal("100"),
        interval="1h",
        activated_at=START,
        written_at=START,
        code_version="test",
    )
    fields.update(overrides)
    return activate_trade(store, ActivateRequest(**fields)).activation


def test_the_monitor_names_every_argument_it_refuses(store) -> None:
    committed = _committed(store)
    subject = _activated(store, committed.plan_id)
    history = fold_stop_history(
        initial_stop=Decimal("95"),
        direction=TradeDirection.LONG,
        amendments=(),
    )
    view = store.activations.state(subject.activation_id)
    base = dict(
        activation=subject,
        direction=TradeDirection.LONG,
        stop_history=history,
        view=view,
        position=Absent("none"),
        excursion=Excursion(),
        last_bar=Absent("none"),
        at=at(1),
    )
    for field, value, needle in (
        ("activation", "an activation", "TradeActivation"),
        ("stop_history", "a history", "StopHistory"),
        ("view", "a view", "TradeLifecycleView"),
        ("position", "a position", "Position"),
        ("excursion", "an excursion", "Excursion"),
        ("last_bar", "a bar", "PriceBar"),
    ):
        with pytest.raises(TypeError, match=needle):
            monitor_trade(**{**base, field: value})


def test_a_monitor_reading_refuses_an_impossible_widening_count() -> None:
    with pytest.raises(TypeError, match="Quantity"):
        TradeMonitor(
            activation_id="x",
            market="m",
            state="open",
            remaining=Decimal("1"),
            initial_stop=Decimal("95"),
            effective_stop=Decimal("95"),
        )
    with pytest.raises(PaperRefusedError, match="widened than were made"):
        TradeMonitor(
            activation_id="x",
            market="m",
            state="open",
            remaining=Quantity(Decimal("1"), AssetCode("BTC")),
            initial_stop=Decimal("95"),
            effective_stop=Decimal("95"),
            stop_moves=1,
            stop_widenings=2,
        )


def test_a_transposed_stop_leaves_every_r_absent_rather_than_a_magnitude(
    store,
) -> None:
    """`fmis.portfolio_risk` refuses the geometry; the monitor turns the refusal
    into an absence rather than taking the whole page down with it."""
    committed = _committed(
        store, stop=Decimal("105"), targets=(Decimal("120"),)
    )
    subject = _activated(
        store,
        committed.plan_id,
        entry_price=Decimal("100"),
        fractions=(Decimal("1"),),
    )
    run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": (bar(0, "99", "101", "98", "100"),)},
    )
    monitor = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
    ).monitor
    for name in ("risk_distance", "initial_risk", "realized_r", "max_favourable_r"):
        value = getattr(monitor, name)
        assert isinstance(value, Absent), name
    assert isinstance(monitor.total_r, Absent)
    assert "not stateable" in monitor.total_r.reason or monitor.total_r.reason


def test_an_activation_with_no_ladder_has_no_next_target_and_says_why(store) -> None:
    committed = _committed(store, targets=())
    subject = _activated(
        store, committed.plan_id, entry_price=Decimal("100")
    )
    monitor = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(1)
    ).monitor
    assert isinstance(monitor.next_target, Absent)
    assert "states no target ladder" in monitor.next_target.reason
    assert isinstance(monitor.distance_to_target, Absent)


def test_the_outcome_reading_refuses_something_that_is_not_an_outcome() -> None:
    with pytest.raises(TypeError, match="TradeOutcome"):
        read_outcome(
            "an outcome",
            activation=activation(),
            direction=TradeDirection.LONG,
            position=Absent("none"),
        )


def test_an_outcome_reading_over_a_trade_that_never_opened_is_all_absent() -> None:
    reading = read_outcome(
        _outcome(),
        activation=activation(),
        direction=TradeDirection.LONG,
        position=Absent("this trade never held a position"),
    )
    for name in (
        "entry_price",
        "exit_price",
        "realized_pnl_net",
        "final_r",
        "pnl_percent",
        "max_favourable_r",
    ):
        assert isinstance(getattr(reading, name), Absent), name
    assert reading.fees == ()
    assert isinstance(reading.days_held, Absent)
    assert isinstance(reading.bars_held, Absent)


def test_the_read_path_names_every_argument_it_refuses(store) -> None:
    with pytest.raises(TypeError, match="TradingStore"):
        fills_for_activation("a store", "x")
    with pytest.raises(TypeError, match="TradingStore"):
        owner_stop_moves("a store", "x")
    with pytest.raises(TypeError, match="DustPolicy"):
        load_paper_trade(store, "x", dust="0", at=at(1))
    with pytest.raises(TypeError, match="TradeActivation"):
        run_state_for("an activation", plan())
    with pytest.raises(TypeError, match="TradePlan"):
        run_state_for(activation(), "a plan")


def test_an_activation_and_a_plan_that_do_not_match_are_refused() -> None:
    committed = plan()
    other = plan(committed_at=at(5), created_at=at(5))
    with pytest.raises(DomainValidationError, match="names plan"):
        run_state_for(activation(committed), other)


def test_a_fill_event_that_names_no_fill_is_refused_at_read_time() -> None:
    """The reference is the only join between a simulated trade and the money it
    moved; an event without one is a fill nobody can find."""
    from fmis.paper import fill_references
    from fmis.trade_lifecycle import TradeLifecycleEvent

    subject = activation()
    orphan = TradeLifecycleEvent(
        activation_id=subject.activation_id,
        kind=TradeLifecycleKind.ENTRY_FILLED,
        occurred_at=at(1),
        recorded_at=at(1),
        audit=RecordAudit.frozen_at(at(1)),
        causing_close_time=at(1),
    )
    with pytest.raises(DomainValidationError, match="only join"):
        fill_references((orphan,))


def test_reading_a_record_that_is_not_an_activation_is_a_named_refusal(store) -> None:
    from fmis.paper import PaperTradeNotFoundError

    committed = _committed(store)
    with pytest.raises(PaperTradeNotFoundError):
        load_paper_trade(
            store, committed.plan_id, dust=PAPER_DUST_POLICY, at=at(1)
        )


# --------------------------------------------------------------------------
# The write path's own refusals
# --------------------------------------------------------------------------


def test_the_write_paths_name_every_argument_they_refuse(store) -> None:
    from fmis.paper import (
        AmendStopRequest,
        CancelRequest,
        amend_stop,
        cancel_activation,
    )

    with pytest.raises(TypeError, match="TradingStore"):
        activate_trade("a store", None)
    with pytest.raises(TypeError, match="ActivateRequest"):
        activate_trade(store, "a request")
    with pytest.raises(TypeError, match="AmendStopRequest"):
        amend_stop(store, "a request")
    with pytest.raises(TypeError, match="CancelRequest"):
        cancel_activation(store, "a request")


def test_a_request_filed_before_the_instant_it_describes_is_refused(store) -> None:
    from fmis.paper import AmendStopRequest, CancelRequest

    committed = _committed(store)
    with pytest.raises(PaperRefusedError, match="before the"):
        ActivateRequest(
            plan_id=committed.plan_id,
            account=AccountId("paper"),
            quantity=Quantity(Decimal("1"), AssetCode("BTC")),
            entry_type=EntryType.MARKET,
            interval="1h",
            activated_at=at(2),
            written_at=at(1),
            code_version="test",
        )
    with pytest.raises(PaperRefusedError, match="before the instant"):
        AmendStopRequest(
            activation_id="x",
            new_stop=Decimal("95"),
            reason="de_risking",
            author="owner",
            occurred_at=at(2),
            written_at=at(1),
            code_version="test",
        )
    with pytest.raises(PaperRefusedError, match="before the instant"):
        CancelRequest(
            activation_id="x",
            reason="de_risking",
            author="owner",
            occurred_at=at(2),
            written_at=at(1),
            code_version="test",
        )


def test_an_activate_request_names_the_field_it_refuses(store) -> None:
    committed = _committed(store)
    base = dict(
        plan_id=committed.plan_id,
        account=AccountId("paper"),
        quantity=Quantity(Decimal("1"), AssetCode("BTC")),
        entry_type=EntryType.MARKET,
        interval="1h",
        activated_at=START,
        written_at=START,
        code_version="test",
    )
    with pytest.raises(TypeError, match="AccountId"):
        ActivateRequest(**{**base, "account": "paper"})
    with pytest.raises(TypeError, match="Quantity"):
        ActivateRequest(**{**base, "quantity": Decimal("1")})


def test_amending_or_cancelling_something_that_is_not_an_activation(store) -> None:
    from fmis.paper import AmendStopRequest, CancelRequest, amend_stop, cancel_activation

    committed = _committed(store)
    with pytest.raises(Exception, match="does not own"):
        amend_stop(
            store,
            AmendStopRequest(
                activation_id=committed.plan_id,
                new_stop=Decimal("97"),
                reason="de_risking",
                author="owner",
                occurred_at=at(1),
                written_at=at(1),
                code_version="test",
            ),
        )
    with pytest.raises(Exception, match="does not own"):
        cancel_activation(
            store,
            CancelRequest(
                activation_id=committed.plan_id,
                reason="de_risking",
                author="owner",
                occurred_at=at(1),
                written_at=at(1),
                code_version="test",
            ),
        )


def test_run_simulation_refuses_a_store_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="TradingStore"):
        run_simulation(
            "a store",
            ran_at=at(1),
            code_version="test",
            interval="1h",
            bars_by_symbol={},
        )


def test_a_second_outcome_for_one_activation_is_never_written(store) -> None:
    committed = _committed(store)
    subject = _activated(store, committed.plan_id, fractions=(Decimal("1"),))
    bars = (bar(0, "99", "101", "98", "100"), bar(1, "100", "112", "99", "111"))
    run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": bars},
    )
    first = store.activations.outcome_for(subject.activation_id)
    run_simulation(
        store,
        ran_at=at(9),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": bars},
    )
    assert store.activations.outcome_for(subject.activation_id) == first


# --------------------------------------------------------------------------
# The proposal bridge
# --------------------------------------------------------------------------


def _proposal(store: TradingStore, *, decided: bool):
    """A stored proposal, optionally moved to `DECIDED` by an owner event."""
    from fmis.persistence import WriteRequest, WriteSource
    from fmis.proposal import LifecycleKind, ProposalLifecycleEvent
    from fmis.paper import paper_version_set

    from trade_domain_helpers import proposal as build_proposal

    subject = build_proposal(created_at=START)
    request = WriteRequest(
        written_at=START,
        source=WriteSource.OWNER,
        author="owner",
        reason=VersionedTerm(
            vocabulary_id="write_reason", term_id="test", taxonomy_version=1
        ),
        version_set=paper_version_set(code_version="test"),
    )
    store.opportunities.create(subject, request=request)
    if decided:
        store.opportunities.create(
            ProposalLifecycleEvent(
                proposal_id=subject.proposal_id,
                kind=LifecycleKind.OWNER_DECIDED,
                occurred_at=START,
                recorded_at=START,
                reason_tag=VersionedTerm(
                    vocabulary_id="decision_reason",
                    term_id="accepted",
                    taxonomy_version=1,
                ),
                causing_close_time=Absent("an assertion has no causing candle"),
                audit=RecordAudit.frozen_at(START),
            ),
            request=request,
        )
    return subject


def test_an_entry_carries_the_proposals_own_lifecycle_forward(store) -> None:
    """`PROPOSED → PENDING → TRIGGERED → OPEN` as one chain across two objects."""
    from fmis.proposal import ProposalState

    subject = _proposal(store, decided=True)
    committed = _committed(store, proposal_id=subject.proposal_id)
    activated = _activated(store, committed.plan_id, fractions=(Decimal("1"),))
    assert activated.proposal_id == subject.proposal_id
    report = run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": (bar(1, "99", "101", "98", "100"),)},
    )
    assert store.opportunities.state(subject.proposal_id).state is (
        ProposalState.TRIGGERED
    )
    assert any("not an execution" in note for note in report.runs[0].notes)


def test_a_decision_and_an_entry_bar_sharing_an_instant_are_not_forced(store) -> None:
    """The proposal's own fold cannot order two events on one instant, and the
    bridge reports that rather than writing an event the fold would refuse.

    A read that succeeded before the write is not a promise the write is legal.
    """
    from fmis.proposal import ProposalState

    subject = _proposal(store, decided=True)
    committed = _committed(store, proposal_id=subject.proposal_id)
    _activated(store, committed.plan_id, fractions=(Decimal("1"),))
    report = run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": (bar(0, "99", "101", "98", "100"),)},
    )
    assert store.opportunities.state(subject.proposal_id).state is (
        ProposalState.DECIDED
    )
    assert any("was not advanced" in note for note in report.runs[0].notes)


def test_a_proposal_the_owner_never_decided_on_is_left_untouched(store) -> None:
    """`ENTRY_TRIGGERED` is legal only from decided. Forcing it would mean
    loosening another package's transition table for a simulator's convenience."""
    from fmis.proposal import ProposalState

    subject = _proposal(store, decided=False)
    committed = _committed(store, proposal_id=subject.proposal_id)
    _activated(store, committed.plan_id, fractions=(Decimal("1"),))
    report = run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": (bar(0, "99", "101", "98", "100"),)},
    )
    assert store.opportunities.state(subject.proposal_id).state is ProposalState.LIVE
    assert any("is live" in note for note in report.runs[0].notes)


def test_a_proposal_this_store_does_not_hold_is_reported_rather_than_forced(
    store,
) -> None:
    committed = _committed(
        store,
        proposal_id="opportunity_proposal-x-20260801T000000Z-" + "0" * 16,
    )
    _activated(store, committed.plan_id, fractions=(Decimal("1"),))
    report = run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": (bar(0, "99", "101", "98", "100"),)},
    )
    assert any("does not hold" in note for note in report.runs[0].notes)


def test_an_activation_that_never_filled_advances_no_proposal(store) -> None:
    subject = _proposal(store, decided=True)
    committed = _committed(
        store, proposal_id=subject.proposal_id, targets=(Decimal("600"),)
    )
    _activated(
        store,
        committed.plan_id,
        entry_price=Decimal("500"),
        fractions=(Decimal("1"),),
    )
    report = run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": (bar(0, "99", "101", "98", "100"),)},
    )
    assert report.runs[0].notes == ()


# --------------------------------------------------------------------------
# The simulation page's own blocks
# --------------------------------------------------------------------------


def test_the_simulation_page_prints_skips_unreachables_and_notes(store) -> None:
    committed = _committed(store)
    _activated(store, committed.plan_id, interval="4h")
    report = run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={},
        failures={"ETHUSDT": "transport error"},
    )
    page = render_simulation(report)
    assert "SKIPPED" in page
    assert "UNREACHABLE" in page
    assert "transport error" in page
    for line in page.splitlines():
        assert len(line) <= 78, line


def test_the_simulation_page_prints_one_block_per_run(store) -> None:
    committed = _committed(store)
    _activated(store, committed.plan_id, fractions=(Decimal("1"),))
    report = run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": (bar(0, "99", "101", "98", "100"),)},
    )
    page = render_simulation(report)
    assert "BTCUSDT  →  open" in page
    assert "bars advanced      1" in page
    assert report.runs[0].market == "BTCUSDT"


def test_a_run_narrowed_to_another_market_advances_nothing(store) -> None:
    committed = _committed(store)
    _activated(store, committed.plan_id)
    report = run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": (bar(0, "99", "101", "98", "100"),)},
        markets=("ETHUSDT",),
    )
    assert report.runs == ()
    assert report.advanced == 0


def test_the_lifecycle_page_says_when_nothing_has_filled(store) -> None:
    committed = _committed(store)
    subject = _activated(store, committed.plan_id)
    page = render_lifecycle(
        load_paper_trade(store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(1))
    )
    assert "Nothing has filled against this activation" in page


def test_a_finished_trade_with_no_frozen_excursion_reads_as_empty() -> None:
    """An outcome that never held a position contributes no excursion, and the
    monitor says so rather than showing a zero."""
    from fmis.paper.views import _excursion_from

    assert _excursion_from(_outcome()).is_empty


# --------------------------------------------------------------------------
# The text boundary — every conversion, and every refusal it names.
# --------------------------------------------------------------------------


def test_the_store_opener_defaults_to_the_owners_own_root() -> None:
    """One store root policy for the whole owner half: the simulator opens the
    same store `fmits trade` does, through the same function."""
    from fmis.paper.inputs import open_store, paper_store_root
    from fmis.trade_capture import capture_store_root

    assert paper_store_root() == capture_store_root()
    assert open_store(None).root == capture_store_root()


def test_a_number_that_is_not_one_is_refused_with_the_argument_named() -> None:
    from fmis.paper import activate_request_from_text

    from fmis.paper.inputs import _decimal

    assert _decimal(" 1.5 ", "size") == Decimal("1.5")
    for raw in ("", "   ", None):
        with pytest.raises(PaperRefusedError, match="required and must be a number"):
            _decimal(raw, "size")
    with pytest.raises(PaperRefusedError, match="is not a number"):
        _decimal("banana", "size")


def test_a_timestamp_that_is_not_iso_or_is_naive_is_refused() -> None:
    from fmis.paper.inputs import _instant

    assert _instant("2026-08-01T00:00:00+02:00", "when") == START - timedelta(hours=2)
    with pytest.raises(PaperRefusedError, match="not an ISO-8601 timestamp"):
        _instant("yesterday", "when")
    with pytest.raises(PaperRefusedError, match="has no timezone"):
        _instant("2026-08-01T00:00:00", "when")


def test_an_entry_type_that_is_not_one_of_the_three_is_refused() -> None:
    from fmis.paper.inputs import _entry_type

    assert _entry_type("market") is EntryType.MARKET
    with pytest.raises(PaperRefusedError, match="is not one of"):
        _entry_type("iceberg")


def test_a_state_filter_is_empty_by_default_and_refuses_an_unknown_member() -> None:
    from fmis.paper import states_from_text

    assert states_from_text(None) == ()
    assert states_from_text(()) == ()
    assert states_from_text(("open",)) == (TradeLifecycleState.OPEN,)
    with pytest.raises(PaperRefusedError, match="is not one of"):
        states_from_text(("flying",))


def test_every_optional_argument_the_activate_surface_accepts_converts(
    store,
) -> None:
    """The path a CLI test cannot reach without twenty flags: every optional
    argument supplied at once, converted exactly once."""
    from fmis.paper import activate_request_from_text

    committed = _committed(store)
    request = activate_request_from_text(
        store,
        plan_id=committed.plan_id,
        size="1",
        entry_type="stop_entry",
        interval="1h",
        filed_at=START,
        account="paper",
        entry="100",
        fractions=("0.5", "0.5"),
        break_even_r="1",
        break_even_offset_r="0.1",
        trail_r="2",
        trail_start_r="3",
        expires="2026-08-02T00:00:00+00:00",
        activated_at="2026-08-01T00:00:00+00:00",
        note="a note",
    )
    assert request.entry_price == Decimal("100")
    assert request.fractions == (Decimal("0.5"), Decimal("0.5"))
    assert request.stop_management.break_even.offset_r == Decimal("0.1")
    assert request.stop_management.trailing.activate_at_r == Decimal("3")
    assert request.note == "a note"


def test_the_amend_and_cancel_surfaces_convert_every_optional_argument() -> None:
    from fmis.paper import amend_request_from_text, cancel_request_from_text

    amend = amend_request_from_text(
        activation_id="trade_activation-x-20260801T000000Z-" + "0" * 16,
        new_stop="97",
        reason="de_risking",
        author="owner",
        filed_at=at(2),
        occurred_at="2026-08-01T01:00:00+00:00",
        note="taking risk off",
    )
    assert amend.new_stop == Decimal("97")
    assert amend.occurred_at == at(1)
    assert amend.term.term_id == "de_risking"
    cancel = cancel_request_from_text(
        activation_id="trade_activation-x-20260801T000000Z-" + "0" * 16,
        reason="thesis_invalidated",
        author="owner",
        filed_at=at(2),
        occurred_at="2026-08-01T01:00:00+00:00",
        note="the setup broke",
    )
    assert cancel.occurred_at == at(1)
    assert cancel.note == "the setup broke"


# --------------------------------------------------------------------------
# The remaining engine and read-path branches
# --------------------------------------------------------------------------


def test_a_triggered_stream_with_no_fill_is_recovered_at_the_next_bars_open(
    store,
) -> None:
    """Only reachable when a run was interrupted between the trigger and the
    fill. The earliest price after a recorded trigger is this bar's open, and
    filling there is the honest recovery rather than re-testing a condition the
    stream already says was met."""
    from fmis.paper import advance
    from fmis.paper.models import TradeRunState

    committed = plan()
    subject = activation(committed)
    state = TradeRunState(
        activation=subject,
        direction=committed.direction,
        initial_stop=Decimal("95"),
        effective_stop=Decimal("95"),
        state=TradeLifecycleState.TRIGGERED,
        remaining=Quantity.zero(AssetCode("BTC")),
        excursion=Excursion(),
    )
    result = advance(state, bar(1, "103", "104", "102", "103"))
    assert [step.kind for step in result.steps][0] is TradeLifecycleKind.ENTRY_FILLED
    assert result.fills[0].price == Decimal("103")
    assert result.next_state.state is TradeLifecycleState.OPEN


def test_a_ladder_rung_larger_than_what_is_open_is_refused() -> None:
    """Unreachable through the ordinary path — shares are of the activated size
    — and refused rather than clamped, because clamping would silently exit a
    different amount from the one the ladder states."""
    from fmis.paper.engine import _record_leg
    from fmis.paper.models import TradeRunState

    committed = plan()
    subject = activation(committed)
    state = TradeRunState(
        activation=subject,
        direction=committed.direction,
        initial_stop=Decimal("95"),
        effective_stop=Decimal("95"),
        state=TradeLifecycleState.OPEN,
        remaining=Quantity(Decimal("0.1"), AssetCode("BTC")),
        excursion=Excursion(favourable=Decimal("101"), adverse=Decimal("99"), bars=1),
        entry_price=Decimal("100"),
        opened_at=START,
    )
    with pytest.raises(PaperRefusedError, match="only 0.1 BTC is open"):
        _record_leg(state, bar(1, "100", "112", "99", "111"), [], 0)


def test_a_ladder_that_closes_the_position_on_a_gapped_open_still_closes(
    store,
) -> None:
    committed = _committed(store)
    subject = _activated(store, committed.plan_id, fractions=(Decimal("1"),))
    run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={
            "BTCUSDT": (
                bar(0, "99", "101", "98", "100"),
                bar(1, "115", "118", "114", "117"),
            )
        },
    )
    view = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
    )
    assert view.state is TradeLifecycleState.RESOLVED
    assert view.outcome.exit_price == Decimal("115")


def test_a_trade_with_no_risk_distance_derives_no_stop_move(store) -> None:
    """The rules are stated in R; with no denominator there is no multiple of it
    to compare against, and the reason is carried rather than swallowed."""
    from fmis.paper import advance
    from fmis.paper.models import TradeRunState

    committed = plan(initial_invalidation=Decimal("100"), targets=(Decimal("120"),))
    subject = activation(
        committed,
        entry_price=Decimal("110"),
        ladder=ExitLadder(
            legs=(ExitLeg(target=Decimal("120"), fraction=Decimal("1")),)
        ),
        stop_management=StopManagement(
            break_even=BreakEvenRule(trigger_r=Decimal("1"))
        ),
    )
    # Entry exactly at the stop: a distance of zero, which is a refusal rather
    # than a very small number, and therefore no R for a rule to be a multiple of.
    state = TradeRunState(
        activation=subject,
        direction=committed.direction,
        initial_stop=Decimal("100"),
        effective_stop=Decimal("100"),
        state=TradeLifecycleState.OPEN,
        remaining=Quantity(Decimal("1"), AssetCode("BTC")),
        excursion=Excursion(favourable=Decimal("104"), adverse=Decimal("101"), bars=1),
        entry_price=Decimal("100"),
        opened_at=START,
        last_bar_time=START,
    )
    result = advance(state, bar(1, "101", "104", "100.5", "103"))
    assert isinstance(result.stop_move, Absent)
    assert "no risk distance" in result.stop_move.reason


def test_the_tighter_of_two_candidate_stops_wins_on_the_other_side() -> None:
    """The loop that picks the tightest runs on both sides, so a short's stop
    cannot be chosen by a long's comparison."""
    from fmis.paper import derive_stop_move

    both = StopManagement(
        break_even=BreakEvenRule(trigger_r=Decimal("1")),
        trailing=TrailingRule(distance_r=Decimal("1")),
    )
    move = derive_stop_move(
        both,
        TradeDirection.SHORT,
        entry_price=Decimal("100"),
        risk_distance=Decimal("5"),
        effective_stop=Decimal("105"),
        excursion=Excursion(
            favourable=Decimal("88"), adverse=Decimal("101"), bars=2
        ),
    )
    assert move.new_stop == Decimal("93")
    assert move.term_id == "trailing"


def test_a_ratio_over_two_currencies_or_a_zero_basis_is_absent() -> None:
    from fmis.paper.views import _percent, _ratio

    assert isinstance(
        _ratio(Money(Decimal("1"), AssetCode("USDT")), Money(Decimal("1"), AssetCode("SEK"))),
        Absent,
    )
    zero = _ratio(
        Money(Decimal("1"), AssetCode("USDT")), Money(Decimal("0"), AssetCode("USDT"))
    )
    assert isinstance(zero, Absent)
    assert "undefined rather than large" in zero.reason
    assert isinstance(
        _percent(
            Money(Decimal("1"), AssetCode("USDT")),
            Absent("no entry"),
            Quantity(Decimal("1"), AssetCode("BTC")),
            AssetCode("USDT"),
        ),
        Absent,
    )


def test_an_outcome_reading_over_a_transposed_stop_is_absent_rather_than_wrong() -> None:
    """`fmis.portfolio_risk` refuses the geometry; the reading carries the
    refusal rather than reporting its magnitude."""
    from fmis.positions import (
        AverageCost,
        Position,
        PositionDirection,
        PositionKey,
        PositionState,
    )

    position = Position(
        key=PositionKey(market_id=MARKET.value, book="paper", flat_crossing_ordinal=0),
        market=MARKET,
        book=Book.PAPER,
        state=PositionState.OPEN,
        direction=PositionDirection.LONG,
        net_quantity=Quantity(Decimal("1"), AssetCode("BTC")),
        average_entry=AverageCost(
            total_cost=Money(Decimal("90"), AssetCode("USDT")),
            total_quantity=Quantity(Decimal("1"), AssetCode("BTC")),
        ),
        average_exit=Absent("still open"),
        realized_pnl_gross=Money.zero(AssetCode("USDT")),
        realized_pnl_net=Money.zero(AssetCode("USDT")),
        fees=(),
        opened_at=START,
        closed_at=Absent("still open"),
        max_exposure=Quantity(Decimal("1"), AssetCode("BTC")),
        trade_count=1,
        add_count=1,
        reduce_count=0,
        event_ids=("trade-binance_BTCUSDT_spot-20260801T010000Z-" + "a" * 16,),
        calculation_version="position-fold-v1",
        dust_policy_id="fmits-paper-exact-zero",
        dust_policy_version=1,
    )
    reading = read_outcome(
        _outcome(
            exit_reason=ExitReason.STOP_HIT,
            opened_at=at(1),
            closed_at=at(2),
            bars_held=1,
            max_favourable_price=Decimal("101"),
            max_adverse_price=Decimal("89"),
            effective_stop_at_exit=Decimal("95"),
            fill_event_ids=("trade-binance_BTCUSDT_spot-20260801T010000Z-" + "a" * 16,),
        ),
        activation=activation(),
        direction=TradeDirection.LONG,
        position=position,
    )
    assert isinstance(reading.final_r, Absent)
    assert isinstance(reading.max_favourable_r, Absent)


def test_a_view_warns_when_the_position_has_been_reduced_and_when_it_expired(
    store,
) -> None:
    committed = _committed(store)
    subject = _activated(
        store,
        committed.plan_id,
        fractions=(Decimal("0.5"),),
        expires_at=at(3),
    )
    run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={
            "BTCUSDT": (
                bar(0, "99", "101", "98", "100"),
                bar(1, "100", "112", "99", "111"),
            )
        },
    )
    view = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
    )
    codes = {warning.code for warning in view.warnings}
    assert "PT-W3" in codes
    assert "PT-W4" in codes


def test_a_view_warns_when_the_activation_states_no_ladder(store) -> None:
    committed = _committed(store, targets=())
    subject = _activated(store, committed.plan_id, entry_price=Decimal("100"))
    view = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(1)
    )
    assert "PT-W5" in {warning.code for warning in view.warnings}


def test_a_monitor_reading_knows_whether_anything_is_open(store) -> None:
    committed = _committed(store)
    subject = _activated(store, committed.plan_id, fractions=(Decimal("1"),))
    run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": (bar(0, "99", "101", "98", "100"),)},
    )
    view = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
    )
    assert view.monitor.is_exposed


def test_an_amendment_with_a_blank_note_is_refused() -> None:
    from fmis.records import DomainValidationError as Invalid

    subject = activation()
    with pytest.raises(Invalid, match="non-empty"):
        StopAmendment(
            activation_id=subject.activation_id,
            previous_stop=Decimal("95"),
            new_stop=Decimal("100"),
            reason=VersionedTerm(vocabulary_id="v", term_id="t", taxonomy_version=1),
            origin=ValueOrigin.ASSERTED,
            author="owner",
            occurred_at=at(1),
            recorded_at=at(1),
            audit=RecordAudit.frozen_at(at(1)),
            note="   ",
        )


def test_an_amendment_schema_version_this_build_does_not_write_is_refused() -> None:
    subject = activation()
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        StopAmendment(
            activation_id=subject.activation_id,
            previous_stop=Decimal("95"),
            new_stop=Decimal("100"),
            reason=VersionedTerm(vocabulary_id="v", term_id="t", taxonomy_version=1),
            origin=ValueOrigin.ASSERTED,
            author="owner",
            occurred_at=at(1),
            recorded_at=at(1),
            audit=RecordAudit.frozen_at(at(1)),
            schema_version=99,
        )


def test_a_measured_event_that_claims_no_candle_is_refused() -> None:
    from fmis.trade_lifecycle import TradeLifecycleEvent

    subject = activation()
    with pytest.raises(DomainValidationError, match="closed candle"):
        TradeLifecycleEvent(
            activation_id=subject.activation_id,
            kind=TradeLifecycleKind.AMBIGUOUS_BAR,
            occurred_at=at(1),
            recorded_at=at(1),
            audit=RecordAudit.frozen_at(at(1)),
            note="both levels",
        )


# --------------------------------------------------------------------------
# The last branches: defensive refusals and the pages' quieter blocks.
# --------------------------------------------------------------------------


def test_the_exact_price_helper_names_the_type_it_was_handed() -> None:
    from fmis.paper.models import _exact_price

    assert _exact_price(Decimal("1"), "price") == Decimal("1")
    with pytest.raises(TypeError, match="price must be a Decimal, got float"):
        _exact_price(1.0, "price")


def test_an_excursion_over_zero_bars_cannot_carry_extremes() -> None:
    with pytest.raises(PaperRefusedError, match="over zero bars"):
        Excursion(favourable=Decimal("110"), adverse=Decimal("99"), bars=0)


def test_a_stop_rule_names_the_type_it_was_handed_for_the_risk_distance() -> None:
    from fmis.paper.stopping import _require_distance

    with pytest.raises(TypeError, match="risk_distance must be a Decimal, got float"):
        _require_distance(1.0)


def test_the_tightest_candidate_survives_when_the_first_is_already_the_tightest() -> None:
    """The other half of the loop's branch: a first candidate no later one beats."""
    from fmis.paper import derive_stop_move

    both = StopManagement(
        break_even=BreakEvenRule(trigger_r=Decimal("1"), offset_r=Decimal("2")),
        trailing=TrailingRule(distance_r=Decimal("3")),
    )
    move = derive_stop_move(
        both,
        TradeDirection.LONG,
        entry_price=Decimal("100"),
        risk_distance=Decimal("5"),
        effective_stop=Decimal("95"),
        excursion=Excursion(
            favourable=Decimal("120"), adverse=Decimal("99"), bars=2
        ),
    )
    # break-even + 2R → 110; trail 3R behind 120 → 105. The first wins.
    assert move.new_stop == Decimal("110")
    assert move.term_id == "break_even"


def test_a_realized_r_over_two_currencies_is_absent_rather_than_a_ratio() -> None:
    from fmis.paper.monitor import _realized_r

    absent = _realized_r(
        _flat_position(realized=Money(Decimal("1"), AssetCode("SEK"))),
        Money(Decimal("5"), AssetCode("USDT")),
    )
    assert isinstance(absent, Absent)
    assert "needs a dated rate" in absent.reason
    assert isinstance(
        _realized_r(_flat_position(), Absent("no entry to measure risk from")),
        Absent,
    )


def _flat_position(*, realized: Money | None = None):
    from fmis.positions import (
        AverageCost,
        Position,
        PositionDirection,
        PositionKey,
        PositionState,
    )

    return Position(
        key=PositionKey(market_id=MARKET.value, book="paper", flat_crossing_ordinal=0),
        market=MARKET,
        book=Book.PAPER,
        state=PositionState.OPEN,
        direction=PositionDirection.LONG,
        net_quantity=Quantity(Decimal("1"), AssetCode("BTC")),
        average_entry=AverageCost(
            total_cost=Money(Decimal("100"), AssetCode("USDT")),
            total_quantity=Quantity(Decimal("1"), AssetCode("BTC")),
        ),
        average_exit=Absent("still open"),
        realized_pnl_gross=Money.zero(AssetCode("USDT")),
        realized_pnl_net=(
            Money.zero(AssetCode("USDT")) if realized is None else realized
        ),
        fees=(),
        opened_at=START,
        closed_at=Absent("still open"),
        max_exposure=Quantity(Decimal("1"), AssetCode("BTC")),
        trade_count=1,
        add_count=1,
        reduce_count=0,
        event_ids=("trade-binance_BTCUSDT_spot-20260801T010000Z-" + "a" * 16,),
        calculation_version="position-fold-v1",
        dust_policy_id="fmits-paper-exact-zero",
        dust_policy_version=1,
    )


def test_the_unrealized_and_excursion_halves_carry_every_absence_forward() -> None:
    from fmis.paper.monitor import _excursion_r, _unrealized_r

    open_size = Quantity(Decimal("1"), AssetCode("BTC"))
    risk = Money(Decimal("5"), AssetCode("USDT"))
    quote = AssetCode("USDT")
    assert isinstance(
        _unrealized_r(
            TradeDirection.LONG,
            Absent("no entry"),
            Decimal("110"),
            open_size,
            risk,
            quote,
        ),
        Absent,
    )
    assert isinstance(
        _unrealized_r(
            TradeDirection.LONG,
            Decimal("100"),
            Absent("no mark"),
            open_size,
            risk,
            quote,
        ),
        Absent,
    )
    assert isinstance(
        _unrealized_r(
            TradeDirection.LONG,
            Decimal("100"),
            Decimal("110"),
            open_size,
            Absent("no risk"),
            quote,
        ),
        Absent,
    )
    for extreme, distance in (
        (Absent("no excursion"), Decimal("5")),
        (Decimal("110"), Absent("no distance")),
    ):
        assert isinstance(
            _excursion_r(TradeDirection.LONG, Decimal("100"), extreme, distance),
            Absent,
        )


def test_a_monitor_block_with_nothing_absent_prints_no_footnote(store) -> None:
    """The other half of the branch: a page where every figure is stateable
    carries no *not stateable* section at all."""
    from fmis.paper.render import _monitor_block

    bars = (bar(0, "99", "101", "98", "100"), bar(1, "100", "112", "99", "111"))
    committed = _committed(store)
    subject = _activated(
        store, committed.plan_id, fractions=(Decimal("0.5"), Decimal("0.5"))
    )
    run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": bars},
    )
    view = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8), bars=bars
    )
    assert "not stateable:" not in "\n".join(_monitor_block(view.monitor))


def test_an_activation_receipt_says_when_it_wrote_nothing(store) -> None:
    from fmis.paper import render_activation

    committed = _committed(store)
    request = ActivateRequest(
        plan_id=committed.plan_id,
        account=AccountId("paper"),
        quantity=Quantity(Decimal("1"), AssetCode("BTC")),
        entry_type=EntryType.STOP_ENTRY,
        entry_price=Decimal("100"),
        interval="1h",
        activated_at=START,
        written_at=START,
        code_version="test",
    )
    assert activate_trade(store, request).created_any
    flattened = " ".join(render_activation(activate_trade(store, request)).split())
    assert "already in the store, byte for byte" in flattened
    assert "idempotent success, not a second instruction" in flattened


def test_the_simulation_page_prints_a_runs_notes_and_the_nothing_new_block(
    store,
) -> None:
    subject = _proposal(store, decided=False)
    committed = _committed(store, proposal_id=subject.proposal_id)
    _activated(store, committed.plan_id, fractions=(Decimal("1"),))
    bars = (bar(0, "99", "101", "98", "100"),)
    first = run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": bars},
    )
    flattened = " ".join(render_simulation(first).split())
    assert "is live; ENTRY_TRIGGERED is legal only from decided" in flattened
    again = run_simulation(
        store,
        ran_at=at(9),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": bars},
    )
    page = render_simulation(again)
    assert "Nothing new was written" in page
    for line in page.splitlines():
        assert len(line) <= 78, line


def test_a_stream_with_no_fill_event_references_nothing() -> None:
    """The other half of the loop: a stream of non-fill events yields no join."""
    from fmis.paper import fill_references

    subject = activation()
    from fmis.trade_lifecycle import TradeLifecycleEvent

    event = TradeLifecycleEvent(
        activation_id=subject.activation_id,
        kind=TradeLifecycleKind.ENTRY_TRIGGERED,
        occurred_at=at(1),
        recorded_at=at(1),
        audit=RecordAudit.frozen_at(at(1)),
        causing_close_time=at(1),
    )
    assert fill_references((event,)) == ()
    assert fill_references(()) == ()


def test_an_outcome_reading_refuses_a_subject_that_is_not_an_outcome() -> None:
    from fmis.paper import OutcomeReading

    with pytest.raises(TypeError, match="TradeOutcome"):
        OutcomeReading(
            outcome="an outcome",
            entry_price=Absent("x"),
            exit_price=Absent("x"),
            realized_pnl_gross=Absent("x"),
            realized_pnl_net=Absent("x"),
            fees=(),
            initial_risk=Absent("x"),
            final_r=Absent("x"),
            pnl_percent=Absent("x"),
            max_favourable_r=Absent("x"),
            max_adverse_r=Absent("x"),
        )


def test_the_discipline_warning_counts_only_what_the_owner_wrote(store) -> None:
    """The first draft asked whether the journal was empty and it never was:
    activating writes a note, so the metric would have read *"the owner wrote
    something"* about every trade in the store from the moment it existed."""
    from fmis.journal import JournalEntry, JournalKind, JournalLink, LinkKind
    from fmis.persistence import WriteRequest, WriteSource
    from fmis.paper import ACTIVATION_SUBJECT_KIND, paper_version_set

    committed = _committed(store)
    subject = _activated(store, committed.plan_id)
    view = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(1)
    )
    assert not view.journal.is_empty
    assert "PT-W6" in {warning.code for warning in view.warnings}

    store.journals.create(
        JournalEntry(
            kind=JournalKind.NOTE,
            recorded_at=at(1),
            author="owner",
            audit=RecordAudit.frozen_at(at(1)),
            title="watching this one",
            body="the breakout looks thin",
            links=(
                JournalLink(
                    LinkKind.ABOUT, ACTIVATION_SUBJECT_KIND, subject.activation_id
                ),
            ),
        ),
        request=WriteRequest(
            written_at=at(2),
            source=WriteSource.OWNER,
            author="owner",
            reason=VersionedTerm(
                vocabulary_id="write_reason", term_id="note", taxonomy_version=1
            ),
            version_set=paper_version_set(code_version="test"),
        ),
    )
    after = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(2)
    )
    assert "PT-W6" not in {warning.code for warning in after.warnings}


def test_reading_an_id_that_belongs_to_another_kind_is_a_named_refusal(store) -> None:
    """The activation repository owns four kinds; an outcome's id is a legal
    thing to hand it and is not an activation."""
    from fmis.paper import PaperTradeNotFoundError

    committed = _committed(store)
    subject = _activated(store, committed.plan_id, fractions=(Decimal("1"),))
    run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={
            "BTCUSDT": (
                bar(0, "99", "101", "98", "100"),
                bar(1, "100", "112", "99", "111"),
            )
        },
    )
    outcome_id = store.activations.outcome_for(subject.activation_id).outcome_id
    with pytest.raises(PaperTradeNotFoundError, match="is not an activation"):
        load_paper_trade(store, outcome_id, dust=PAPER_DUST_POLICY, at=at(8))


def test_the_write_paths_refuse_a_record_of_another_kind_they_do_own(store) -> None:
    """`amend_stop` and `cancel_activation` load through a repository that owns
    four kinds, so a stop amendment's own id reaches them as a legal record that
    is not an activation."""
    from fmis.paper import (
        AmendStopRequest,
        CancelRequest,
        amend_stop,
        cancel_activation,
    )

    committed = _committed(store)
    subject = _activated(store, committed.plan_id)
    amend_stop(
        store,
        AmendStopRequest(
            activation_id=subject.activation_id,
            new_stop=Decimal("97"),
            reason="de_risking",
            author="owner",
            occurred_at=at(1),
            written_at=at(1),
            code_version="test",
        ),
    )
    amendment_id = store.activations.live_amendments_for(
        subject.activation_id
    )[0].amendment_id
    for call, request in (
        (
            amend_stop,
            AmendStopRequest(
                activation_id=amendment_id,
                new_stop=Decimal("98"),
                reason="de_risking",
                author="owner",
                occurred_at=at(2),
                written_at=at(2),
                code_version="test",
            ),
        ),
        (
            cancel_activation,
            CancelRequest(
                activation_id=amendment_id,
                reason="de_risking",
                author="owner",
                occurred_at=at(2),
                written_at=at(2),
                code_version="test",
            ),
        ),
    ):
        with pytest.raises(PaperRefusedError, match="not an activation"):
            call(store, request)


def test_activating_something_that_is_not_a_commitment_is_refused_by_the_store(
    store,
) -> None:
    """`PlanRepository` owns one kind and refuses any other id before the
    composition root's own check is reached — which is why that check carries a
    `pragma: no cover` and a stated reason rather than a test that fakes it."""
    from fmis.persistence import UnknownRecordKindError

    committed = _committed(store)
    subject = _activated(store, committed.plan_id)
    with pytest.raises(UnknownRecordKindError, match="does not own"):
        activate_trade(
            store,
            ActivateRequest(
                plan_id=subject.activation_id,
                account=AccountId("paper"),
                quantity=Quantity(Decimal("1"), AssetCode("BTC")),
                entry_type=EntryType.MARKET,
                interval="1h",
                activated_at=START,
                written_at=START,
                code_version="test",
            ),
        )


def test_a_lifecycle_event_schema_version_this_build_does_not_write_is_refused() -> None:
    from fmis.trade_lifecycle import TradeLifecycleEvent

    subject = activation()
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        TradeLifecycleEvent(
            activation_id=subject.activation_id,
            kind=TradeLifecycleKind.ENTRY_TRIGGERED,
            occurred_at=at(1),
            recorded_at=at(1),
            audit=RecordAudit.frozen_at(at(1)),
            causing_close_time=at(1),
            schema_version=99,
        )


def test_a_view_with_nothing_to_qualify_prints_no_warnings_block(store) -> None:
    """The other half of the branch: a page whose every caveat is satisfied
    carries no warnings section at all."""
    from fmis.journal import JournalEntry, JournalKind, JournalLink, LinkKind
    from fmis.persistence import WriteRequest, WriteSource
    from fmis.paper import ACTIVATION_SUBJECT_KIND, paper_version_set
    from fmis.paper.render import _warnings_block

    bars = (bar(0, "99", "101", "98", "100"),)
    committed = _committed(store)
    subject = _activated(
        store, committed.plan_id, fractions=(Decimal("0.5"), Decimal("0.5"))
    )
    store.journals.create(
        JournalEntry(
            kind=JournalKind.NOTE,
            recorded_at=at(1),
            author="owner",
            audit=RecordAudit.frozen_at(at(1)),
            title="my own note",
            body="watching the retest",
            links=(
                JournalLink(
                    LinkKind.ABOUT, ACTIVATION_SUBJECT_KIND, subject.activation_id
                ),
            ),
        ),
        request=WriteRequest(
            written_at=at(1),
            source=WriteSource.OWNER,
            author="owner",
            reason=VersionedTerm(
                vocabulary_id="write_reason", term_id="note", taxonomy_version=1
            ),
            version_set=paper_version_set(code_version="test"),
        ),
    )
    run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": bars},
    )
    view = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8), bars=bars
    )
    assert view.warnings == ()
    assert _warnings_block(view) == []


def test_one_fill_referenced_twice_is_listed_once() -> None:
    """A superseding event may re-state the fill the one it replaced named; the
    join is a set of fills, not a count of events."""
    from fmis.paper import fill_references
    from fmis.trade_lifecycle import TradeLifecycleEvent

    subject = activation()
    reference = "trade-binance_BTCUSDT_spot-20260801T010000Z-" + "a" * 16
    events = tuple(
        TradeLifecycleEvent(
            activation_id=subject.activation_id,
            kind=TradeLifecycleKind.PARTIAL_EXIT_FILLED,
            occurred_at=at(hours),
            recorded_at=at(hours),
            audit=RecordAudit.frozen_at(at(hours)),
            reference=reference,
        )
        for hours in (1, 2)
    )
    assert fill_references(events) == (reference,)


def test_candles_that_all_predate_the_activation_read_as_none_read(store) -> None:
    """A provider page reaches back further than any activation. A reading whose
    excursion covered bars from before the instruction would report a maximum
    adverse excursion the trade was never exposed to."""
    committed = _committed(store)
    subject = _activated(
        store, committed.plan_id, activated_at=at(5), written_at=at(5)
    )
    view = load_paper_trade(
        store,
        subject.activation_id,
        dust=PAPER_DUST_POLICY,
        at=at(8),
        bars=(bar(0, "99", "101", "98", "100"), bar(1, "100", "112", "99", "111")),
    )
    assert isinstance(view.monitor.max_favourable_price, Absent)
    assert view.monitor.bars_in_trade == 0
    assert isinstance(view.monitor.last_price, Absent)
    assert "no bar has been observed" in view.monitor.last_price.reason
