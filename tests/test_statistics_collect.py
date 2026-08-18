"""Reading a real store — the mapping into one vocabulary, and its refusals.

Every store here is written through the **product's own** write path
(`fmis.trade_capture`), never by hand-building records: a fixture that
constructed a `Trade` directly would exercise a shape the product cannot
produce, and would keep passing after the write path stopped producing it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from fmis.accounts import AccountId, Book, MarketId, MarketMode, VenueId
from fmis.money import AssetCode, DustPolicy, Money, Quantity
from fmis.provenance import Absent
from fmis.snapshotting import TradeDirection
from fmis.statistics import (
    COLLECT_DUST_POLICY,
    PHASE_OF_CAPTURE_STATUS,
    PHASE_OF_LIFECYCLE_STATE,
    LifecyclePhase,
    StatSource,
    CorpusUnreadableError,
    collect_trades,
    open_risk_limit,
    quote_assets_of,
    stat_from_paper,
    stat_from_recorded,
)
from fmis.trade_capture import CaptureStatus, CloseRequest, RecordRequest, close_trade, record_trade
from fmis.trade_lifecycle import TradeLifecycleState

EPOCH = datetime(2026, 3, 1, tzinfo=timezone.utc)
USDT = AssetCode("USDT")


def at(days: int) -> datetime:
    return EPOCH + timedelta(days=days)


def market(symbol: str = "BTC") -> MarketId:
    return MarketId(
        venue=VenueId("binance"),
        base_asset=AssetCode(symbol),
        quote_asset=USDT,
        mode=MarketMode.SPOT,
    )


def store_at(root: Path):
    from fmis.persistence import TradingStore

    return TradingStore(root, dust=COLLECT_DUST_POLICY)


def write_trade(
    root: Path,
    *,
    symbol: str = "BTC",
    direction: TradeDirection = TradeDirection.LONG,
    entry: str = "100",
    stop: str = "90",
    size: str = "10",
    day: int = 0,
    setup: str | None = "breakout",
    book: Book = Book.SWING,
) -> str:
    """Record one commitment and its entry fill through the capture path."""
    request = RecordRequest(
        market=market(symbol),
        book=book,
        account=AccountId("main"),
        direction=direction,
        entry_price=Decimal(entry),
        stop=Decimal(stop),
        quantity=Quantity(Decimal(size), AssetCode(symbol)),
        fee=Money(Decimal("0"), USDT),
        fx_rate_to_tax_currency=Decimal("10"),
        fx_source="riksbank",
        occurred_at=at(day),
        written_at=at(day),
        author="test",
        confidence="moderate",
        code_version="test",
        targets=(Decimal(entry) + Decimal(20),)
        if direction is TradeDirection.LONG
        else (Decimal(entry) - Decimal(20),),
        setup_type=(
            Absent("no setup type was named") if setup is None else setup
        ),
    )
    outcome = record_trade(store_at(root), request)
    return outcome.plan_id


def close(root: Path, plan_id: str, *, price: str, day: int) -> None:
    close_trade(
        store_at(root),
        CloseRequest(
            plan_id=plan_id,
            exit_price=Decimal(price),
            fee=Money(Decimal("0"), USDT),
            fx_rate_to_tax_currency=Decimal("10"),
            fx_source="riksbank",
            occurred_at=at(day),
            written_at=at(day),
            author="test",
            reason="target_reached",
            code_version="test",
        ),
    )


# --------------------------------------------------------------------------
# The store boundary
# --------------------------------------------------------------------------


def test_a_missing_store_is_an_empty_corpus_and_not_a_failure(tmp_path: Path) -> None:
    """An owner who has recorded nothing has no statistics, which is a page."""
    collected = collect_trades(tmp_path / "nowhere", at=at(1))
    assert collected.is_empty
    assert collected.present is False
    assert collected.refused == ()


def test_a_corrupt_store_is_a_failure_and_not_an_empty_page(tmp_path: Path) -> None:
    """Rendering it empty would turn a detected corruption into a statement
    that the owner has never traded."""
    root = tmp_path / "store"
    write_trade(root)
    index = next(root.rglob("*index*"), None) or next(root.rglob("*.jsonl"))
    index.write_text("{ this is not valid json\n", encoding="utf-8")
    with pytest.raises(CorpusUnreadableError, match="exists and could not be read"):
        collect_trades(root, at=at(5))


def test_a_recorded_trade_becomes_a_stat_with_its_plan_and_market(tmp_path: Path) -> None:
    root = tmp_path / "store"
    plan_id = write_trade(root, entry="100", stop="90", size="10", day=0)
    collected = collect_trades(root, at=at(5))
    assert len(collected.trades) == 1
    found = collected.trades[0]
    assert found.trade_ref == plan_id
    assert found.plan_id == plan_id
    assert found.source is StatSource.RECORDED
    assert found.market.base_asset.code == "BTC"
    assert found.setup_type == "breakout"


def test_an_open_recorded_trade_has_no_final_r_multiple(tmp_path: Path) -> None:
    """A running R averaged beside finished ones mixes *"what this trade did"*
    with *"what it has done so far"*."""
    root = tmp_path / "store"
    write_trade(root)
    found = collect_trades(root, at=at(5)).trades[0]
    assert found.phase is LifecyclePhase.OPEN
    assert isinstance(found.r_multiple, Absent)
    assert "has not closed" in found.r_multiple.reason


def test_a_closed_recorded_trade_gets_its_r_from_the_capture_paths_own_risk(
    tmp_path: Path,
) -> None:
    """Entry 100, stop 90, size 10 → risk 100. Exit 120 → net +200 → R = 2."""
    root = tmp_path / "store"
    plan_id = write_trade(root, entry="100", stop="90", size="10", day=0)
    close(root, plan_id, price="120", day=3)
    found = collect_trades(root, at=at(5)).trades[0]
    assert found.phase is LifecyclePhase.CLOSED
    assert found.realized_pnl_net == Money(Decimal(200), USDT)
    assert found.initial_risk == Money(Decimal(100), USDT)
    assert found.r_multiple == Decimal(2)


def test_a_short_recorded_trade_takes_the_other_side_of_the_risk_distance(
    tmp_path: Path,
) -> None:
    """Entry 100, stop 110, size 10 → risk 100. Exit 80 → net +200 → R = 2."""
    root = tmp_path / "store"
    plan_id = write_trade(
        root, direction=TradeDirection.SHORT, entry="100", stop="110", size="10"
    )
    close(root, plan_id, price="80", day=3)
    found = collect_trades(root, at=at(5)).trades[0]
    assert found.realized_pnl_net == Money(Decimal(200), USDT)
    assert found.r_multiple == Decimal(2)


def test_a_recorded_trade_has_no_excursion_and_no_bar_count(tmp_path: Path) -> None:
    """`ST-2`, at the source: nothing froze one, so nothing is invented."""
    root = tmp_path / "store"
    plan_id = write_trade(root)
    close(root, plan_id, price="120", day=3)
    found = collect_trades(root, at=at(5)).trades[0]
    for value in (found.max_adverse_r, found.max_favourable_r, found.bars_held):
        assert isinstance(value, Absent)
    assert "recorded" in found.exit_reason.reason or isinstance(found.exit_reason, Absent)


def test_a_plan_with_no_setup_type_carries_the_absence_forward(tmp_path: Path) -> None:
    root = tmp_path / "store"
    write_trade(root, setup=None)
    assert isinstance(collect_trades(root, at=at(5)).trades[0].setup_type, Absent)


def test_the_holding_time_comes_from_the_position_fold(tmp_path: Path) -> None:
    root = tmp_path / "store"
    plan_id = write_trade(root, day=0)
    close(root, plan_id, price="120", day=4)
    found = collect_trades(root, at=at(9)).trades[0]
    assert found.holding_time == timedelta(days=4)


# --------------------------------------------------------------------------
# Point-in-time
# --------------------------------------------------------------------------


def test_a_trade_committed_after_the_cut_did_not_exist_then(tmp_path: Path) -> None:
    root = tmp_path / "store"
    write_trade(root, symbol="BTC", day=0)
    write_trade(root, symbol="ETH", day=10)
    collected = collect_trades(root, at=at(20), as_of=at(5))
    assert [s.market.base_asset.code for s in collected.trades] == ["BTC"]


def test_a_trade_that_closed_after_the_cut_is_dropped_not_reported_open(
    tmp_path: Path,
) -> None:
    """Reconstructing what its monitor said then would need the candle history
    this package refuses to fetch."""
    root = tmp_path / "store"
    plan_id = write_trade(root, day=0)
    close(root, plan_id, price="120", day=8)
    assert collect_trades(root, at=at(20), as_of=at(4)).trades == ()
    assert len(collect_trades(root, at=at(20), as_of=at(9)).trades) == 1


def test_without_a_cut_every_trade_is_collected(tmp_path: Path) -> None:
    root = tmp_path / "store"
    write_trade(root, symbol="BTC", day=0)
    write_trade(root, symbol="ETH", day=10)
    assert len(collect_trades(root, at=at(20)).trades) == 2


# --------------------------------------------------------------------------
# The phase tables
# --------------------------------------------------------------------------


def test_every_lifecycle_state_the_simulator_can_fold_to_has_a_phase() -> None:
    """A state added to `TradeLifecycleState` fails here rather than falling
    into a silent default."""
    assert {state.value for state in TradeLifecycleState} == set(
        PHASE_OF_LIFECYCLE_STATE
    )


def test_every_capture_status_has_a_phase() -> None:
    assert {status.value for status in CaptureStatus} == set(PHASE_OF_CAPTURE_STATUS)


def test_every_phase_the_tables_map_to_is_a_real_phase() -> None:
    for table in (PHASE_OF_LIFECYCLE_STATE, PHASE_OF_CAPTURE_STATUS):
        for phase in table.values():
            assert isinstance(phase, LifecyclePhase)


def test_a_finished_simulated_trade_maps_to_closed_from_either_state() -> None:
    """The engine freezes an outcome the instant a trade closes, so a finished
    trade is almost always read as `RESOLVED` rather than `CLOSED` — BO's own
    tenth finding, guarded here at the layer that consumes it."""
    assert PHASE_OF_LIFECYCLE_STATE["closed"] is LifecyclePhase.CLOSED
    assert PHASE_OF_LIFECYCLE_STATE["resolved"] is LifecyclePhase.CLOSED


def test_a_partially_exited_trade_is_open_because_it_still_holds_exposure() -> None:
    assert PHASE_OF_LIFECYCLE_STATE["partially_exited"] is LifecyclePhase.OPEN


def test_a_planned_capture_is_pending_rather_than_a_phase_of_its_own() -> None:
    assert PHASE_OF_CAPTURE_STATUS["planned"] is LifecyclePhase.PENDING


# --------------------------------------------------------------------------
# Quote assets, the ceiling, and the refusals
# --------------------------------------------------------------------------


def test_quote_assets_come_back_sorted_so_the_first_one_is_stable(
    tmp_path: Path,
) -> None:
    from statistics_helpers import stat

    trades = (stat("a", quote="USDT"), stat("b", symbol="ETH", quote="BTC"))
    assert [asset.code for asset in quote_assets_of(trades)] == ["BTC", "USDT"]


def test_a_store_with_no_risk_budget_has_no_ceiling_and_says_which_gap(
    tmp_path: Path,
) -> None:
    root = tmp_path / "store"
    write_trade(root)
    absent = open_risk_limit(store_at(root), at=at(5))
    assert isinstance(absent, Absent)
    assert "gap in the owner's policy" in absent.reason


def test_the_collected_payload_names_what_was_refused(tmp_path: Path) -> None:
    root = tmp_path / "store"
    write_trade(root)
    payload = collect_trades(root, at=at(5)).to_payload()
    assert payload["present"] is True
    assert payload["refused"] == []
    assert len(payload["trades"]) == 1


def test_collecting_refuses_a_wrong_dust_policy_type(tmp_path: Path) -> None:
    root = tmp_path / "store"
    write_trade(root)
    with pytest.raises(TypeError, match="dust"):
        collect_trades(root, at=at(5), dust="exact zero")


def test_collecting_refuses_a_wrong_as_of_type(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="as_of"):
        collect_trades(tmp_path, at=at(5), as_of="yesterday")


def test_the_mappers_refuse_a_view_of_the_wrong_type() -> None:
    with pytest.raises(TypeError, match="PaperTradeView"):
        stat_from_paper("not a view")
    with pytest.raises(TypeError, match="TradeView"):
        stat_from_recorded("not a view")


def test_the_default_dust_policy_is_exact_zero() -> None:
    """The only tolerance that is not a policy decision."""
    assert COLLECT_DUST_POLICY.thresholds == ()
    assert isinstance(COLLECT_DUST_POLICY, DustPolicy)


# --------------------------------------------------------------------------
# The simulated half — a paper trade, run to completion, then collected
# --------------------------------------------------------------------------
#
# Added after a mutation probe survived: nothing here drove a **finished paper
# trade** through `collect_trades`, so reading an excursion off the live monitor
# instead of off the frozen outcome was undetectable. Everything below goes
# through the product's own activate-and-simulate path with hand-built bars, so
# no candle is fetched and the run is byte-for-byte repeatable.


def paper_store(root: Path):
    from fmis.paper import PAPER_DUST_POLICY
    from fmis.persistence import TradingStore

    return TradingStore(root, dust=PAPER_DUST_POLICY)


def simulated_trade(root: Path, *, bars, hours: int = 8) -> str:
    """A paper commitment, activated and replayed over the bars given."""
    from fmis.accounts import AccountId, Book
    from fmis.money import Quantity
    from fmis.paper import ActivateRequest, activate_trade, run_simulation
    from fmis.trade_lifecycle import EntryType
    from fmis.trade_capture import PlanRequest, record_plan
    from paper_helpers import MARKET, START

    store = paper_store(root)
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
    outcome = activate_trade(
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
            fractions=(Decimal("0.5"), Decimal("0.5")),
        ),
    )
    from paper_helpers import at as bar_at

    run_simulation(
        store,
        ran_at=bar_at(hours),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": bars},
    )
    return outcome.activation.activation_id


WINNING_BARS = (
    __import__("paper_helpers").bar(0, "98", "99", "97", "98"),
    __import__("paper_helpers").bar(1, "99", "101", "98", "100"),
    __import__("paper_helpers").bar(2, "100", "112", "99", "111"),
    __import__("paper_helpers").bar(3, "111", "121", "110", "120"),
)


def collect_paper(root: Path):
    from fmis.paper import PAPER_DUST_POLICY
    from paper_helpers import at as bar_at

    return collect_trades(root, at=bar_at(9), dust=PAPER_DUST_POLICY)


def test_a_finished_paper_trade_is_collected_as_a_simulated_stat(tmp_path: Path) -> None:
    root = tmp_path / "store"
    activation_id = simulated_trade(root, bars=WINNING_BARS)
    trades = collect_paper(root).trades
    assert len(trades) == 1
    found = trades[0]
    assert found.source is StatSource.SIMULATED
    assert found.trade_ref == activation_id
    assert found.book is Book.PAPER
    assert found.phase is LifecyclePhase.CLOSED


def test_a_finished_paper_trades_excursion_comes_from_the_frozen_outcome(
    tmp_path: Path,
) -> None:
    """`AP` §25.3: MAE and MFE are frozen at close because kline history is not
    permanent. Reading them from the live monitor instead would make a past
    statistic depend on what the venue still serves — and the two differ, which
    is what makes this assertion able to tell them apart."""
    root = tmp_path / "store"
    simulated_trade(root, bars=WINNING_BARS)
    found = collect_paper(root).trades[0]
    outcome = paper_store(root).activations.outcome_for(found.trade_ref)
    assert outcome is not None
    assert not isinstance(found.max_favourable_r, Absent)
    assert not isinstance(found.max_adverse_r, Absent)
    assert not isinstance(found.bars_held, Absent)
    assert found.bars_held == outcome.bars_held
    assert found.exit_reason == outcome.exit_reason.value


def test_a_finished_paper_trade_carries_a_final_r_and_its_interval(
    tmp_path: Path,
) -> None:
    root = tmp_path / "store"
    simulated_trade(root, bars=WINNING_BARS)
    found = collect_paper(root).trades[0]
    assert not isinstance(found.r_multiple, Absent)
    assert found.interval == "1h"
    assert found.account == "paper"


def test_a_still_running_paper_trade_has_no_final_r_and_no_frozen_excursion(
    tmp_path: Path,
) -> None:
    """The other side: an unfinished trade contributes no result, and its
    excursion is absent rather than read from the monitor."""
    root = tmp_path / "store"
    simulated_trade(root, bars=WINNING_BARS[:2])
    found = collect_paper(root).trades[0]
    assert found.phase is not LifecyclePhase.CLOSED
    assert isinstance(found.r_multiple, Absent)
    assert isinstance(found.max_favourable_r, Absent)
    assert isinstance(found.bars_held, Absent)


def test_a_plan_that_reached_the_simulator_is_counted_once_not_twice(
    tmp_path: Path,
) -> None:
    """The commitment exists in both read paths. Counting it twice would double
    every figure derived from it, and the simulated view is the one carrying an
    excursion and a bar count."""
    root = tmp_path / "store"
    simulated_trade(root, bars=WINNING_BARS)
    collected = collect_paper(root)
    assert len(collected.trades) == 1
    assert {entry.source for entry in collected.trades} == {StatSource.SIMULATED}


def test_a_store_holding_both_kinds_collects_each_exactly_once(
    tmp_path: Path,
) -> None:
    root = tmp_path / "store"
    # The recorded trade first: its instants are months earlier than the paper
    # helpers', and the store's write journal is append-only — filing a record
    # behind the journal head is refused, correctly.
    write_trade(root, symbol="ETH", entry="50", stop="45", size="20", day=0)
    simulated_trade(root, bars=WINNING_BARS)
    collected = collect_paper(root)
    assert len(collected.trades) == 2
    assert {entry.source for entry in collected.trades} == {
        StatSource.SIMULATED,
        StatSource.RECORDED,
    }


def test_collecting_a_paper_trade_writes_nothing_to_the_store(tmp_path: Path) -> None:
    import hashlib

    root = tmp_path / "store"
    simulated_trade(root, bars=WINNING_BARS)

    def fingerprint() -> str:
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()

    before = fingerprint()
    collect_paper(root)
    collect_paper(root)
    assert fingerprint() == before
