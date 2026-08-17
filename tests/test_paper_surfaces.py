"""Milestone BO — the surfaces the other files reach only at their edges.

`fmits today`'s paper section with a trade that has actually filled, the two
commands' failure paths, and `fmits trade plan`'s own refusals. Small, and each
one is a branch that decides what a page says rather than what it computes.
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
from fmis.swing_setup import SetupRunResult
from fmis.today import (
    NotAvailable,
    PaperTradeLine,
    PaperTrading,
    build_today,
    paper_trading,
    read_store,
    render_today,
)
from fmis.trade_capture import PlanRequest, record_plan
from fmis.trade_lifecycle import EntryType
from fmis.paper import (
    PAPER_DUST_POLICY,
    ActivateRequest,
    AmendStopRequest,
    activate_trade,
    amend_stop,
    load_paper_trade,
    run_simulation,
)
from fmis.pipeline import cli as cli_module
from paper_helpers import MARKET, START, at, bar


@pytest.fixture()
def store(tmp_path: Path) -> TradingStore:
    return TradingStore(tmp_path / "store", dust=PAPER_DUST_POLICY)


def _open_paper_trade(store: TradingStore, **overrides):
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
        fractions=(Decimal("0.5"), Decimal("0.5")),
    )
    fields.update(overrides)
    subject = activate_trade(store, ActivateRequest(**fields)).activation
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
    return plan, subject


def _page(store: TradingStore, root: Path, *, at_hours: int = 8) -> str:
    reading = read_store(root, at=at(at_hours), archive_root=root / "archive")
    results = (SetupRunResult(requested_symbol="BTCUSDT", failure="offline"),)
    return render_today(
        build_today(
            results, reading, reference_time=at(at_hours), source="offline test"
        )
    )


# --------------------------------------------------------------------------
# `fmits today`'s paper section, with a trade that has filled
# --------------------------------------------------------------------------


def test_the_days_page_shows_a_partially_exited_trade_with_its_figures(
    store, tmp_path: Path
) -> None:
    _open_paper_trade(store)
    page = _page(store, tmp_path / "store")
    assert "5. PAPER TRADING" in page
    assert "PARTIALLY EXITED (1)" in page
    assert "entry 100" in page
    assert "held " in page
    for line in page.splitlines():
        assert len(line) <= 78, line


def test_a_widened_stop_is_named_on_the_days_page(store, tmp_path: Path) -> None:
    _, subject = _open_paper_trade(store)
    amend_stop(
        store,
        AmendStopRequest(
            activation_id=subject.activation_id,
            new_stop=Decimal("90"),
            reason="emotional",
            author="owner",
            occurred_at=at(6),
            written_at=at(9),
            code_version="test",
        ),
    )
    page = _page(store, tmp_path / "store", at_hours=10)
    assert "widened 1 time(s)" in " ".join(page.split())
    assert "committed 95" in page


def test_a_halted_trade_is_named_on_the_days_page(store, tmp_path: Path) -> None:
    plan = record_plan(
        store,
        PlanRequest(
            market=MARKET,
            book=Book.PAPER,
            direction=TradeDirection.LONG,
            stop=Decimal("95"),
            targets=(Decimal("110"),),
            committed_at=START,
            written_at=START,
            author="owner",
            confidence="medium",
            code_version="test",
        ),
    ).view.plan
    activate_trade(
        store,
        ActivateRequest(
            plan_id=plan.plan_id,
            account=AccountId("paper"),
            quantity=Quantity(Decimal("1"), AssetCode("BTC")),
            entry_type=EntryType.MARKET,
            interval="1h",
            activated_at=START,
            written_at=START,
            code_version="test",
        ),
    )
    run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={
            "BTCUSDT": (
                bar(0, "100", "101", "99", "100"),
                bar(1, "100", "115", "94", "96"),
            )
        },
    )
    flattened = " ".join(_page(store, tmp_path / "store").split())
    assert "HALTED" in flattened
    assert "waiting for you, not for the market" in flattened
    assert "1 trade(s) are halted" in flattened


def test_an_unread_store_says_it_did_not_look_rather_than_that_there_is_none() -> None:
    section = paper_trading((), read=False)
    assert section.is_empty
    assert isinstance(section.note, NotAvailable)
    assert "This page did not look" in section.note.forbidden_inference


def test_a_read_store_with_no_paper_trade_says_so_plainly() -> None:
    section = paper_trading((), read=True)
    assert section.is_empty
    assert not isinstance(section.note, NotAvailable)
    assert section.live == ()
    assert section.halted == ()


# --------------------------------------------------------------------------
# The line's own rules
# --------------------------------------------------------------------------


def _line(**overrides) -> PaperTradeLine:
    fields = dict(
        activation_id="trade_activation-x-20260801T000000Z-" + "0" * 16,
        market="BTCUSDT",
        state="open",
        open_size="1 BTC",
        entry="100",
        stop="95",
        initial_stop="95",
        total_r="0.5",
        holding="1:00:00",
        bars_in_trade=2,
        stop_widenings=0,
    )
    fields.update(overrides)
    return PaperTradeLine(**fields)


def test_halted_and_stop_moved_are_derived_and_never_stored_beside_the_state() -> None:
    """One fact, one place: a second field could disagree with the state."""
    assert not _line().halted
    assert _line(state="ambiguous").halted
    assert not _line().stop_moved
    assert _line(stop="100").stop_moved


def test_a_line_accepts_a_stated_figure_and_a_stated_absence_alike() -> None:
    absent = NotAvailable(
        reason="no bar has been observed",
        owned_by="fmis.paper",
        forbidden_inference="that the figure is zero",
    )
    assert isinstance(_line(entry=absent).entry, NotAvailable)
    assert _line().entry == "100"
    with pytest.raises(Exception):
        _line(entry="   ")


def test_a_section_refuses_a_line_that_is_not_one() -> None:
    with pytest.raises(TypeError):
        PaperTrading(pending=("BTCUSDT",))


# --------------------------------------------------------------------------
# The commands' failure paths
# --------------------------------------------------------------------------


def test_simulate_reports_a_corrupt_store_and_exits_non_zero(
    capsys, tmp_path: Path, store
) -> None:
    """A refusal is not a crash and is reported as neither: a script can tell
    *"FMITS would not simulate that"* from *"FMITS broke"*.

    A corrupt store is the realistic case — a payload written by a newer build,
    or hand-edited — and it must never be rendered as *"nothing to simulate"*.
    """
    _, subject = _open_paper_trade(store)
    root = tmp_path / "store"
    payload = next(
        path
        for path in (root / "records" / "trade_activation").rglob("*.json")
    )
    payload.write_text('{"schema_version": 999}', encoding="utf-8")
    code = cli_module.main(
        [
            "simulate",
            "--store-root",
            str(root),
            "--reference-time",
            "2026-08-01T08:00:00+00:00",
        ]
    )
    captured = capsys.readouterr()
    assert code == cli_module.EXIT_FAILURE
    assert "fmits simulate:" in captured.out + captured.err


def test_the_trade_dispatcher_refuses_a_subcommand_it_does_not_have() -> None:
    """The registry and the dispatcher cannot drift apart silently."""
    import argparse

    args = argparse.Namespace(trade_command="teleport", store_root=None)
    with pytest.raises(AssertionError, match="unreachable trade_command"):
        cli_module._dispatch_trade(args, filed_at=at(1))


# --------------------------------------------------------------------------
# `fmits trade plan`'s own refusals
# --------------------------------------------------------------------------


def test_a_plan_request_names_the_field_it_refuses(store) -> None:
    base = dict(
        market=MARKET,
        book=Book.PAPER,
        direction=TradeDirection.LONG,
        stop=Decimal("95"),
        committed_at=START,
        written_at=START,
        author="owner",
        confidence="medium",
        code_version="test",
    )
    with pytest.raises(TypeError, match="market must be a MarketId"):
        PlanRequest(**{**base, "market": "BTCUSDT"})
    with pytest.raises(TypeError, match="PlanRequest"):
        record_plan(store, "a request")
    with pytest.raises(TypeError, match="TradingStore"):
        record_plan("a store", PlanRequest(**base))


def test_a_commitment_with_a_thesis_writes_the_owners_own_idea(store) -> None:
    """Routed to the journal by name, because an idea auto-filled onto every
    plan would make the discipline metric read 100 % forever."""
    from fmis.journal import JournalKind

    outcome = record_plan(
        store,
        PlanRequest(
            market=MARKET,
            book=Book.PAPER,
            direction=TradeDirection.LONG,
            stop=Decimal("95"),
            targets=(Decimal("110"),),
            committed_at=START,
            written_at=START,
            author="owner",
            confidence="medium",
            code_version="test",
            thesis="the retest held",
        ),
    )
    assert {record.kind for record in outcome.written} == {
        "trade_plan",
        "journal_entry",
    }
    entries = store.journals.live_entries()
    assert [entry.kind for entry in entries] == [JournalKind.IDEA]
    assert entries[0].author == "owner"


def test_a_decision_not_to_act_has_no_sign_a_price_can_be_compared_against() -> None:
    """`TradeDirection.sign` is the rule this milestone's arithmetic rests on.
    A zero for `NO_TRADE` would silently make every comparison against it true."""
    from fmis.records import DomainValidationError
    from fmis.snapshotting import TradeDirection

    assert TradeDirection.LONG.sign == Decimal(1)
    assert TradeDirection.SHORT.sign == Decimal(-1)
    with pytest.raises(DomainValidationError, match="no side and therefore no sign"):
        TradeDirection.NO_TRADE.sign


def test_a_populated_section_whose_note_is_an_absence_prints_no_note() -> None:
    """Defensive: an unread store produces an *empty* section, so this pairing
    cannot arise from the builder. Checked so the renderer cannot print a
    `NotAvailable` object into the page if one ever does."""
    from fmis.today.render import _paper_block

    section = PaperTrading(
        open_trades=(_line(),),
        note=NotAvailable(
            reason="the store was not read",
            owned_by="fmis.paper",
            forbidden_inference="that no paper trade is running",
        ),
    )
    rendered = "\n".join(_paper_block(section))
    assert "OPEN (1)" in rendered
    assert "NotAvailable" not in rendered
    assert "the store was not read" not in rendered


# --------------------------------------------------------------------------
# Every lifecycle state must be visible on the day's page
# --------------------------------------------------------------------------


def test_every_lifecycle_state_lands_in_a_list_the_page_renders() -> None:
    """Found by the release gate. The first draft hard-coded six bucket keys and
    read five of them, so a finished trade — which folds to `RESOLVED`, because
    the engine freezes an outcome the moment a trade closes — landed in a key
    nothing read and was **invisible on every page**.

    Asserted as a set comparison against the enum, so a state added later fails
    here rather than disappearing.
    """
    from fmis.today.sections import _FINISHED_STATES
    from fmis.trade_lifecycle import TradeLifecycleState

    live = {"pending", "triggered", "open", "partially_exited", "ambiguous"}
    covered = live | set(_FINISHED_STATES)
    assert covered == {state.value for state in TradeLifecycleState}


def test_a_finished_trade_appears_under_recently_closed(store, tmp_path: Path) -> None:
    """The regression the gate caught: a resolved trade on the day's page."""
    plan = record_plan(
        store,
        PlanRequest(
            market=MARKET,
            book=Book.PAPER,
            direction=TradeDirection.LONG,
            stop=Decimal("95"),
            targets=(Decimal("110"),),
            committed_at=START,
            written_at=START,
            author="owner",
            confidence="medium",
            code_version="test",
        ),
    ).view.plan
    activate_trade(
        store,
        ActivateRequest(
            plan_id=plan.plan_id,
            account=AccountId("paper"),
            quantity=Quantity(Decimal("1"), AssetCode("BTC")),
            entry_type=EntryType.STOP_ENTRY,
            entry_price=Decimal("100"),
            interval="1h",
            activated_at=START,
            written_at=START,
            code_version="test",
        ),
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
    from fmis.trade_lifecycle import TradeLifecycleState
    from fmis.paper import load_paper_trade

    activation_id = store.activations.activations()[0].activation_id
    assert load_paper_trade(
        store, activation_id, dust=PAPER_DUST_POLICY, at=at(8)
    ).state is TradeLifecycleState.RESOLVED

    page = _page(store, tmp_path / "store")
    assert "RECENTLY CLOSED (1)" in page
    for line in page.splitlines():
        assert len(line) <= 78, line


def test_a_cancelled_and_an_expired_trade_are_both_visible(store, tmp_path: Path) -> None:
    """`CANCELLED`, `EXPIRED` and `SUPERSEDED` end a trade too. A page showing
    none of them would answer *'what happened to the ones I activated'* with
    silence."""
    from fmis.paper import CancelRequest, cancel_activation

    plan = record_plan(
        store,
        PlanRequest(
            market=MARKET,
            book=Book.PAPER,
            direction=TradeDirection.LONG,
            stop=Decimal("95"),
            targets=(Decimal("600"),),
            committed_at=START,
            written_at=START,
            author="owner",
            confidence="medium",
            code_version="test",
        ),
    ).view.plan
    subject = activate_trade(
        store,
        ActivateRequest(
            plan_id=plan.plan_id,
            account=AccountId("paper"),
            quantity=Quantity(Decimal("1"), AssetCode("BTC")),
            entry_type=EntryType.STOP_ENTRY,
            entry_price=Decimal("500"),
            interval="1h",
            activated_at=START,
            written_at=START,
            code_version="test",
        ),
    ).activation
    cancel_activation(
        store,
        CancelRequest(
            activation_id=subject.activation_id,
            reason="thesis_invalidated",
            author="owner",
            occurred_at=at(1),
            written_at=at(1),
            code_version="test",
        ),
    )
    section = paper_trading(
        (
            load_paper_trade(
                store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(2)
            ),
        ),
        read=True,
    )
    assert len(section.recently_closed) == 1
    assert not section.is_empty
    assert "RECENTLY CLOSED (1)" in _page(store, tmp_path / "store", at_hours=2)
