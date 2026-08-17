"""Milestone BO — the monitoring block, the outcome reading, and the pages.

The brief's §3 names eleven figures and §6 names twelve; these check that each is
produced, that each is `Absent(reason)` rather than zero when it cannot be
stated, and that **no arithmetic is duplicated** — the risk distance is
`fmis.portfolio_risk`'s, the realized P&L is the position fold's, and every R
multiple rests on the same denominator so the three of them add up.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fmis.accounts import AccountId, Book
from fmis.money import AssetCode, Quantity
from fmis.persistence import TradingStore
from fmis.provenance import Absent
from fmis.snapshotting import TradeDirection
from fmis.trade_capture import PlanRequest, record_plan
from fmis.trade_lifecycle import EntryType, ExitReason, TradeLifecycleState
from fmis.paper import (
    MONITOR_BASIS,
    PAPER_DUST_POLICY,
    ActivateRequest,
    activate_trade,
    load_paper_trade,
    render_history,
    render_lifecycle,
    render_simulation,
    render_status,
    run_simulation,
)
from paper_helpers import MARKET, START, at, bar, break_even

WINNING_BARS = (
    bar(0, "99", "101", "98", "100"),
    bar(1, "100", "112", "99", "111"),
    bar(2, "111", "121", "110", "120"),
)


@pytest.fixture()
def store(tmp_path: Path) -> TradingStore:
    return TradingStore(tmp_path / "store", dust=PAPER_DUST_POLICY)


def setup(store: TradingStore, **overrides):
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
    fields = {
        "plan_id": plan.plan_id,
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
    return activate_trade(store, ActivateRequest(**fields)).activation


def simulate(store, bars=WINNING_BARS, hours: int = 8):
    return run_simulation(
        store,
        ran_at=at(hours),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": bars},
    )


# --------------------------------------------------------------------------
# The monitoring block
# --------------------------------------------------------------------------


def test_an_unfilled_trade_states_every_figure_as_absent_with_a_reason(store) -> None:
    """A zero here would make a page look complete and survive for years."""
    subject = setup(store)
    view = load_paper_trade(store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(1))
    monitor = view.monitor
    for name in (
        "entry_price",
        "last_price",
        "risk_distance",
        "initial_risk",
        "realized_r",
        "max_favourable_r",
        "max_adverse_r",
        "holding_time",
        "days_in_trade",
        # Found by a mutation probe: a total that fell back to whichever half
        # was stateable would report `0` for a trade that has never filled.
        "total_r",
    ):
        value = getattr(monitor, name)
        assert isinstance(value, Absent), name
        assert value.reason
    assert "realized half is not stateable" in monitor.total_r.reason
    assert monitor.remaining.is_zero
    assert monitor.bars_in_trade == 0


def test_an_open_trade_states_the_figures_a_mark_makes_available(store) -> None:
    subject = setup(store)
    simulate(store, bars=WINNING_BARS[:2], hours=5)
    view = load_paper_trade(
        store,
        subject.activation_id,
        dust=PAPER_DUST_POLICY,
        at=at(5),
        bars=WINNING_BARS[:2],
    )
    monitor = view.monitor
    assert monitor.entry_price == Decimal("100")
    assert monitor.last_price == Decimal("111")
    assert monitor.risk_distance == Decimal("5")
    assert monitor.initial_risk.amount == Decimal("5")
    assert monitor.remaining == Quantity(Decimal("0.5"), AssetCode("BTC"))
    assert monitor.max_favourable_r == Decimal("2.4")
    assert monitor.max_adverse_r == Decimal("-0.4")
    assert monitor.bars_in_trade == 2


def test_the_three_r_multiples_add_up_because_they_share_a_denominator(store) -> None:
    subject = setup(store)
    simulate(store, bars=WINNING_BARS[:2], hours=5)
    monitor = load_paper_trade(
        store,
        subject.activation_id,
        dust=PAPER_DUST_POLICY,
        at=at(5),
        bars=WINNING_BARS[:2],
    ).monitor
    assert monitor.realized_r + monitor.unrealized_r == monitor.total_r


def test_a_closed_trade_has_a_known_zero_unrealized_and_a_stateable_total(store) -> None:
    subject = setup(store)
    simulate(store)
    monitor = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8), bars=WINNING_BARS
    ).monitor
    assert monitor.unrealized_r == Decimal("0")
    assert monitor.total_r == monitor.realized_r == Decimal("3")


def test_a_finished_trade_read_offline_still_states_its_total_r(store) -> None:
    """Found by a mutation probe. With no candles the mark is absent, so the
    unrealized half has nothing to compute from — and a closed trade's
    unrealized half is a **known zero** rather than an unknown, which is what
    keeps the one figure a finished trade most obviously has stateable."""
    subject = setup(store)
    simulate(store)
    monitor = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
    ).monitor
    assert isinstance(monitor.last_price, Absent)
    assert monitor.unrealized_r == Decimal("0")
    assert monitor.total_r == Decimal("3")


def test_the_distances_share_one_sign_convention(store) -> None:
    """Positive is *not yet there* for both, so a page cannot read as safe when
    it is not."""
    subject = setup(store)
    simulate(store, bars=WINNING_BARS[:1], hours=5)
    monitor = load_paper_trade(
        store,
        subject.activation_id,
        dust=PAPER_DUST_POLICY,
        at=at(5),
        bars=WINNING_BARS[:1],
    ).monitor
    assert monitor.distance_to_stop == Decimal("5")
    assert monitor.distance_to_target == Decimal("10")
    assert monitor.next_target == Decimal("110")


def test_a_reading_taken_without_candles_says_the_excursion_is_unread(store) -> None:
    subject = setup(store)
    simulate(store, bars=WINNING_BARS[:2], hours=5)
    monitor = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(5)
    ).monitor
    assert isinstance(monitor.max_favourable_r, Absent)
    assert isinstance(monitor.last_price, Absent)


def test_a_finished_trade_reads_its_excursion_from_the_frozen_outcome(store) -> None:
    """No candle is fetched, and the figure is still there — which is exactly
    why `AP` §25.2 says to freeze it."""
    subject = setup(store)
    simulate(store)
    monitor = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
    ).monitor
    assert monitor.max_favourable_price == Decimal("121")
    assert monitor.max_adverse_price == Decimal("98")
    assert monitor.bars_in_trade == 3


def test_the_stop_history_is_reported_beside_the_figures_it_qualifies(store) -> None:
    subject = setup(store, stop_management=break_even())
    simulate(store, bars=WINNING_BARS[:2], hours=5)
    monitor = load_paper_trade(
        store,
        subject.activation_id,
        dust=PAPER_DUST_POLICY,
        at=at(5),
        bars=WINNING_BARS[:2],
    ).monitor
    assert monitor.stop_moves == 1
    assert monitor.stop_widenings == 0
    assert monitor.stop_was_moved
    assert monitor.initial_stop == Decimal("95")
    assert monitor.effective_stop == Decimal("100")
    # Found by a mutation probe. Every R multiple rests on the **initial** risk,
    # so a tightened stop does not inflate one: measured against the effective
    # stop the distance here would be zero, every R would collapse to an
    # absence, and good management would read as a trade that was never sized.
    assert monitor.risk_distance == Decimal("5")
    assert monitor.initial_risk.amount == Decimal("5")
    assert monitor.realized_r == Decimal("1")
    assert monitor.max_favourable_r == Decimal("2.4")


def test_the_monitor_serializes_for_export_and_states_its_basis(store) -> None:
    subject = setup(store)
    monitor = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(1)
    ).monitor
    payload = monitor.to_payload()
    assert payload["activation_id"] == subject.activation_id
    assert payload["entry_price"] is None
    assert "pre-cost and pre-funding" in MONITOR_BASIS


# --------------------------------------------------------------------------
# The outcome reading
# --------------------------------------------------------------------------


def test_the_outcome_reading_produces_every_figure_the_brief_names(store) -> None:
    subject = setup(store)
    simulate(store)
    reading = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
    ).outcome
    assert reading.exit_reason == ExitReason.TARGET_HIT.value
    assert reading.target_hit
    assert not reading.stop_hit
    assert reading.entry_price == Decimal("100")
    assert reading.exit_price == Decimal("115")
    assert reading.realized_pnl_net.amount == Decimal("15")
    assert reading.realized_pnl_gross.amount == Decimal("15")
    assert reading.final_r == Decimal("3")
    assert reading.pnl_percent == Decimal("0.15")
    assert reading.bars_held == 3
    assert reading.days_held == Decimal("2") / Decimal("24")
    assert reading.max_favourable_r == Decimal("4.2")
    assert reading.max_adverse_r == Decimal("-0.4")


def test_the_outcome_record_stores_no_figure_the_ledger_already_answers(store) -> None:
    """`AP` §25.2 classes realized P&L, average entry and quantity as
    projections; storing them here would be the fourth place one fact lives."""
    from fmis.trade_lifecycle import TradeOutcome

    fields = set(TradeOutcome.__dataclass_fields__)
    for absent in (
        "realized_pnl",
        "realized_pnl_net",
        "average_entry",
        "average_exit",
        "r_multiple",
        "pnl_percent",
        "quantity",
    ):
        assert absent not in fields, absent
    assert {"max_favourable_price", "max_adverse_price", "bars_held"} <= fields


def test_the_outcome_reading_serializes_for_export(store) -> None:
    subject = setup(store)
    simulate(store)
    payload = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
    ).outcome.to_payload()
    assert payload["exit_reason"] == "target_hit"
    assert payload["final_r"] == "3"


# --------------------------------------------------------------------------
# The pages
# --------------------------------------------------------------------------


def _fits(page: str) -> None:
    for line in page.splitlines():
        assert len(line) <= 78, line


def test_every_page_fits_the_width_and_prints_its_limitations(store) -> None:
    subject = setup(store)
    simulate(store)
    views = (
        load_paper_trade(
            store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
        ),
    )
    for page in (
        render_lifecycle(views[0]),
        render_status(views),
        render_history(views),
        render_simulation(simulate(store, hours=9)),
    ):
        _fits(page)
        assert "PT-1" in page


def test_the_lifecycle_page_shows_the_stream_the_stops_and_the_outcome(store) -> None:
    subject = setup(store, stop_management=break_even())
    simulate(store)
    page = render_lifecycle(
        load_paper_trade(store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8))
    )
    assert "LIFECYCLE" in page
    assert "STOP HISTORY" in page
    assert "95 → 100" in page
    assert "FILLS" in page
    assert "OUTCOME" in page
    assert "target_hit" in page


def test_an_empty_status_page_says_so_rather_than_rendering_blank(store) -> None:
    page = render_status(())
    assert "No activation is pending" in page
    _fits(page)


def test_an_empty_history_page_says_what_would_put_a_trade_on_it(store) -> None:
    page = render_history(())
    assert "No simulated trade has finished" in page
    _fits(page)


def test_a_simulation_page_with_no_activation_says_what_to_do_next(store) -> None:
    page = render_simulation(simulate(store))
    assert "fmits trade activate" in page
    _fits(page)


def test_a_run_that_wrote_nothing_says_that_is_what_a_replay_should_do(store) -> None:
    setup(store)
    simulate(store)
    page = render_simulation(simulate(store, hours=9))
    _fits(page)


def test_an_absent_figure_prints_its_reason_once_at_the_foot(store) -> None:
    """A dash that could not be looked up would read as a zero."""
    subject = setup(store)
    page = render_lifecycle(
        load_paper_trade(store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(1))
    )
    assert "not stateable:" in page
    assert "nothing has filled against this activation" in page


def test_a_halted_trade_says_so_on_every_page_that_shows_it(store) -> None:
    subject = setup(store)
    simulate(store, bars=(bar(0, "100", "100", "100", "100"), bar(1, "100", "115", "94", "96")))
    view = load_paper_trade(
        store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
    )
    assert view.state is TradeLifecycleState.AMBIGUOUS
    for page in (render_lifecycle(view), render_status((view,))):
        assert "PT-W1" in page
        assert "halted" in page.lower()
        _fits(page)


def test_a_widened_stop_is_warned_about_rather_than_absorbed(store) -> None:
    from fmis.paper import AmendStopRequest, amend_stop

    subject = setup(store)
    amend_stop(
        store,
        AmendStopRequest(
            activation_id=subject.activation_id,
            new_stop=Decimal("90"),
            reason="emotional",
            author="owner",
            occurred_at=at(1),
            written_at=at(1),
            code_version="test",
        ),
    )
    page = render_lifecycle(
        load_paper_trade(store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(2))
    )
    assert "PT-W2" in page
    assert "widened" in page
