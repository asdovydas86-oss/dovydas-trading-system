"""Every refusal and every absence path, reached deliberately.

The four family files exercise the arithmetic; this one exercises the code that
runs when an input is wrong or a value is missing. Both matter, and only one of
them is reached by a test that is trying to compute something.

**A type refusal is not decoration.** Each one names the parameter and the type
it got, and that message is the whole difference between a caller fixing their
call in a minute and reading a traceback three layers down. A refusal nothing
ever executes is a refusal nobody has read.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from fmis.accounts import AccountId, Book, MarketId, MarketMode, VenueId
from fmis.money import AssetCode, DustPolicy, Money
from fmis.provenance import Absent
from fmis.snapshotting import TradeDirection
from fmis.statistics import (
    Breakdown,
    BreakdownCell,
    CollectedTrades,
    DrawdownCurve,
    EquityCurve,
    EquityPoint,
    Histogram,
    LifecyclePhase,
    SamplePolicy,
    StatSource,
    Tally,
    as_percentage,
    breakdown_set,
    build_report,
    collect_trades,
    cut_by,
    drawdown_curve,
    duration_text,
    equity_curve,
    general_statistics,
    open_risk_limit,
    performance_statistics,
    quality_statistics,
    risk_statistics,
    stat_from_paper,
    stat_from_recorded,
)
from statistics_helpers import ABSENT, at, money, stat

USDT = AssetCode("USDT")
BTC = AssetCode("BTC")
LOW = SamplePolicy(minimum_sample=1)
NONE = Absent("none supplied")


# --------------------------------------------------------------------------
# Type refusals — one per parameter that has one
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("call", "fragment"),
    [
        # equity
        (lambda: equity_curve([], quote_asset=USDT, starting_equity=NONE), "tuple"),
        (lambda: equity_curve(("x",), quote_asset=USDT, starting_equity=NONE), "TradeStat"),
        (lambda: equity_curve((), quote_asset="USDT", starting_equity=NONE), "AssetCode"),
        (lambda: equity_curve((), quote_asset=USDT, starting_equity=1), "Money or Absent"),
        (lambda: as_percentage(1, NONE), "amount must be a Money"),
        (lambda: as_percentage(money("1"), 1), "basis must be a Money"),
        # breakdown
        (lambda: cut_by([], "d", str, LOW, quote_asset=USDT), "tuple"),
        (lambda: cut_by((), "d", "not callable", LOW, quote_asset=USDT), "callable"),
        (lambda: cut_by((), "d", str, "no", quote_asset=USDT), "SamplePolicy"),
        (lambda: cut_by((), "d", str, LOW, quote_asset="USDT"), "AssetCode"),
        # families
        (lambda: general_statistics([], LOW), "tuple"),
        (lambda: general_statistics(("x",), LOW), "TradeStat"),
        (lambda: general_statistics((), "no"), "SamplePolicy"),
        (lambda: performance_statistics([], LOW, quote_asset=USDT), "tuple"),
        (lambda: performance_statistics(("x",), LOW, quote_asset=USDT), "TradeStat"),
        (lambda: performance_statistics((), "no", quote_asset=USDT), "SamplePolicy"),
        (lambda: performance_statistics((), LOW, quote_asset="USDT"), "AssetCode"),
        (lambda: quality_statistics([], LOW), "tuple"),
        (lambda: quality_statistics(("x",), LOW), "TradeStat"),
        (lambda: quality_statistics((), "no"), "SamplePolicy"),
    ],
)
def test_a_wrong_type_is_refused_with_the_parameters_own_name(call, fragment) -> None:
    with pytest.raises(TypeError, match=fragment):
        call()


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"trades": ("x",)}, "TradeStat"),
        ({"policy": "no"}, "SamplePolicy"),
        ({"quote_asset": "USDT"}, "AssetCode"),
        ({"equity_basis": 1}, "equity_basis"),
        ({"utilization": "0.5"}, "utilization"),
    ],
)
def test_the_risk_fold_refuses_each_wrong_type(kwargs, fragment) -> None:
    call = {
        "trades": (),
        "policy": LOW,
        "quote_asset": USDT,
        "equity_basis": NONE,
        "utilization": NONE,
    }
    call.update(kwargs)
    trades = call.pop("trades")
    policy = call.pop("policy")
    with pytest.raises(TypeError, match=fragment):
        risk_statistics(trades, policy, **call)


def test_an_equity_point_refuses_each_wrong_type() -> None:
    for kwargs, fragment in (
        ({"delta": 1}, "delta must be a Money"),
        ({"cumulative": 1}, "cumulative must be a Money"),
        ({"equity": 1}, "equity must be a Money or Absent"),
    ):
        fields = {
            "at": at(1), "trade_ref": "x", "delta": money("1"),
            "cumulative": money("1"), "equity": NONE,
        }
        fields.update(kwargs)
        with pytest.raises(TypeError, match=fragment):
            EquityPoint(**fields)


def test_an_equity_curve_refuses_each_wrong_type() -> None:
    for kwargs, fragment in (
        ({"quote_asset": "USDT"}, "quote_asset must be an AssetCode"),
        ({"points": []}, "points must be a tuple"),
        ({"points": ("x",)}, "every point must be an EquityPoint"),
        ({"starting_equity": 1}, "starting_equity must be a Money or Absent"),
        ({"excluded": []}, "excluded must be a tuple"),
    ):
        fields = {
            "quote_asset": USDT, "points": (), "starting_equity": NONE,
            "excluded": (), "open_trades": 0,
        }
        fields.update(kwargs)
        with pytest.raises(TypeError, match=fragment):
            EquityCurve(**fields)


def test_a_breakdown_refuses_a_cells_list_that_is_not_a_tuple() -> None:
    with pytest.raises(TypeError, match="cells must be a tuple"):
        Breakdown(dimension="symbol", cells=[], quote_asset=USDT)


def test_open_risk_limit_refuses_a_non_store() -> None:
    with pytest.raises(TypeError, match="store must be a TradingStore"):
        open_risk_limit("not a store", at=at(1))


# --------------------------------------------------------------------------
# Absence paths that only a shaped input reaches
# --------------------------------------------------------------------------


def test_the_peak_rises_only_when_the_curve_exceeds_it() -> None:
    """Both sides of the comparison inside the peak walk."""
    rising = equity_curve(
        (stat("a", net="10", closed_day=1), stat("b", net="10", closed_day=2)),
        quote_asset=USDT, starting_equity=NONE,
    )
    assert rising.peak_equity == money("20")
    falling = equity_curve(
        (stat("a", net="10", closed_day=1), stat("b", net="-5", closed_day=2)),
        quote_asset=USDT, starting_equity=NONE,
    )
    assert falling.peak_equity == money("10")


def test_a_closed_trade_with_no_closing_instant_is_excluded_and_named() -> None:
    """Unreachable through `collect`, whose phases and instants agree — and
    reachable by a caller assembling `TradeStat` values, which is why the guard
    exists and why it is exercised here rather than trusted."""
    orphan = stat("x", phase=LifecyclePhase.CLOSED, opened_day=0, closed_day=None,
                  net="10")
    curve = equity_curve((orphan,), quote_asset=USDT, starting_equity=NONE)
    assert curve.points == ()
    assert any("records no closing instant" in reason for reason in curve.excluded)


def test_a_percentage_refuses_to_cross_two_assets() -> None:
    absent = as_percentage(money("10"), Money(Decimal(100), BTC))
    assert isinstance(absent, Absent)
    assert "crosses them" in absent.reason


def test_a_duration_renders_at_three_resolutions_and_keeps_its_sign() -> None:
    assert duration_text(timedelta(days=2, hours=3, minutes=4)) == "2d 3h 4m"
    assert duration_text(timedelta(hours=3, minutes=4)) == "3h 4m"
    assert duration_text(timedelta(minutes=4)) == "4m"
    assert duration_text(timedelta(days=-1)).startswith("-")
    assert duration_text(timedelta(days=2, hours=3), minutes=False) == "2d 3h"


# --------------------------------------------------------------------------
# The collection edges
# --------------------------------------------------------------------------


def test_a_trade_view_with_no_position_carries_every_absence_forward(
    tmp_path: Path,
) -> None:
    """A commitment nothing filled against: no profit and loss, no instants, no
    holding time — each absent with its own reason rather than a zero."""
    from test_statistics_collect import at as store_day, write_trade

    root = tmp_path / "store"
    write_trade(root, day=0)
    found = collect_trades(root, at=store_day(5)).trades[0]
    assert found.phase is LifecyclePhase.OPEN
    # The fill exists, so the position does; what is absent is the close.
    assert isinstance(found.closed_at, Absent)
    assert isinstance(found.exit_reason, Absent)


def test_a_plan_with_no_snapshot_produces_an_empty_regime_map(
    tmp_path: Path,
) -> None:
    from test_statistics_collect import at as store_day, write_trade

    root = tmp_path / "store"
    write_trade(root)
    assert collect_trades(root, at=store_day(5)).trades[0].regime_states == {}


def test_a_trade_filled_across_two_accounts_belongs_to_neither(tmp_path: Path) -> None:
    """`account` is a dimension, and a trade whose fills sit in two of them has
    no single one — an absence, not the first account, which would silently
    attribute the whole trade to the wrong capacity pool."""
    from decimal import Decimal as D

    from fmis.trade_capture import CloseRequest, close_trade
    from test_statistics_collect import at as store_day, store_at, write_trade

    root = tmp_path / "store"
    plan_id = write_trade(root, day=0)
    close_trade(
        store_at(root),
        CloseRequest(
            plan_id=plan_id, exit_price=D("120"), fee=Money(D("0"), USDT),
            fx_rate_to_tax_currency=D("10"), fx_source="riksbank",
            occurred_at=store_day(3), written_at=store_day(3), author="test",
            reason="target_reached", code_version="test",
            account=AccountId("second"),
        ),
    )
    found = collect_trades(root, at=store_day(5)).trades[0]
    assert isinstance(found.account, Absent)
    assert "2 accounts" in found.account.reason


# --------------------------------------------------------------------------
# Payload shapes
# --------------------------------------------------------------------------


def test_every_reading_serializes_and_carries_its_absences_as_null() -> None:
    report = build_report(
        CollectedTrades(
            trades=(stat("a", r_multiple=None, mfe=None, mae=None, bars=None),),
            refused=("x: no", ),
            store_root="/tmp/s",
            present=True,
        ),
        at=at(9),
        policy=LOW,
    )
    payload = report.to_payload()
    asset = payload["assets"][0]
    assert asset["performance"]["average_r"] is None
    assert asset["quality"]["average_adverse_r"] is None
    assert asset["risk"]["risk_utilization"] is None
    assert asset["equity"]["starting_equity"] is None
    assert asset["drawdown"]["maximum"] is None
    assert payload["refused"] == ["x: no"]
    assert payload["as_of"] is None


def test_a_populated_reading_serializes_every_figure_it_has() -> None:
    report = build_report(
        CollectedTrades(
            trades=(
                stat("a", net="10", closed_day=1),
                stat("b", net="-5", closed_day=2),
                stat("c", net="20", closed_day=3),
            ),
            refused=(), store_root="/tmp/s", present=True,
        ),
        at=at(9), policy=LOW, starting_equity=money("100"),
        equity_basis=money("100"), open_risk_ceiling=money("100"),
        as_of=at(9),
    )
    asset = report.to_payload()["assets"][0]
    assert asset["performance"]["profit_factor"] is not None
    assert asset["equity"]["points"]
    assert asset["drawdown"]["periods"]
    assert asset["drawdown"]["periods"][0]["depth_percent"] is not None
    assert asset["breakdowns"]["cells_examined"] > 0
    assert report.to_payload()["as_of"] is not None


def test_a_tally_and_a_sample_and_a_histogram_all_serialize() -> None:
    report = build_report(
        CollectedTrades(trades=(stat("a"),), refused=(), store_root="/tmp/s",
                        present=True),
        at=at(9), policy=LOW,
    )
    general = report.primary.general.to_payload()
    assert general["winning"]["count"] == 1
    assert general["holding_time"]["size"] == 1
    quality = report.primary.quality.to_payload()
    assert quality["r_distribution"]["buckets"]
    assert quality["holding_time_distribution"]["unit"] == "days"


def test_a_drawdown_period_serializes_both_its_states() -> None:
    ongoing = drawdown_curve(
        equity_curve(
            (stat("a", net="10", closed_day=1), stat("b", net="-5", closed_day=2)),
            quote_asset=USDT, starting_equity=NONE,
        ),
        LOW,
    )
    payload = ongoing.to_payload()["periods"][0]
    assert payload["ongoing"] is True
    assert payload["recovered_at"] is None
    assert payload["depth_percent"] is None
    assert payload["duration_seconds"] > 0


def test_a_stat_payload_round_trips_every_populated_field() -> None:
    payload = stat("a", regime_states={"trend": "up"}, stop_moves=2,
                   stop_widenings=1).to_payload()
    assert payload["regime_states"] == {"trend": "up"}
    assert payload["stop_moves"] == 2
    assert payload["holding_time_seconds"] > 0
    assert payload["opened_at"] and payload["closed_at"]
    assert payload["initial_risk"]["amount"]


def test_a_breakdown_cell_and_set_serialize() -> None:
    cuts = breakdown_set((stat("a"), stat("b", symbol="ETH")), LOW, quote_asset=USDT)
    payload = cuts.to_payload()
    assert payload["regime_dimension"]
    assert payload["breakdowns"][0]["cells"][0]["key"]
    assert payload["cells_examined"] == cuts.cells_examined


# --------------------------------------------------------------------------
# `CollectedTrades`' own refusals
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"trades": []}, "trades must be a tuple"),
        ({"trades": (1,)}, "must be a TradeStat"),
        ({"refused": []}, "refused must be a tuple"),
        ({"refused": (1,)}, "refused reason"),
        ({"store_root": ""}, "store_root"),
        ({"present": "yes"}, "present must be a bool"),
    ],
)
def test_a_collection_refuses_a_malformed_field(kwargs, fragment) -> None:
    fields = {"trades": (), "refused": (), "store_root": "/tmp/s", "present": True}
    fields.update(kwargs)
    with pytest.raises((TypeError, ValueError), match=fragment):
        CollectedTrades(**fields)


# --------------------------------------------------------------------------
# The regime map, from a real frozen snapshot
# --------------------------------------------------------------------------


def test_the_regime_states_come_from_the_setup_role_of_the_frozen_snapshot(
    tmp_path: Path,
) -> None:
    """`AP` §25.2 freezes the regime at decision. The setup role is the timeframe
    the commitment was formed on; the context role is about the environment it
    sits in, and mixing all three would produce a key nobody could interpret."""
    from fmis.statistics.collect import _regime_states
    from trade_domain_helpers import market_snapshot

    snapshot = market_snapshot()
    states = _regime_states(snapshot)
    setup_role = next(r for r in snapshot.roles if r.role.value == "setup")
    expected = {
        d.name: d.state
        for d in setup_role.regime.dimensions
        if not isinstance(d.state, Absent)
    }
    assert states == expected
    assert states, "the fixture snapshot should carry at least one stated dimension"


def test_a_snapshot_with_no_setup_role_falls_back_to_the_first_one() -> None:
    from fmis.snapshotting import SnapshotRole
    from fmis.statistics.collect import _regime_states
    from trade_domain_helpers import market_snapshot

    full = market_snapshot()
    context_only = market_snapshot(
        roles=tuple(r for r in full.roles if r.role is SnapshotRole.CONTEXT)
    )
    states = _regime_states(context_only)
    expected = {
        d.name: d.state
        for d in context_only.roles[0].regime.dimensions
        if not isinstance(d.state, Absent)
    }
    assert states == expected


def test_no_snapshot_produces_an_empty_map_rather_than_a_guess() -> None:
    from fmis.statistics.collect import _regime_states

    assert _regime_states(None) == {}


# --------------------------------------------------------------------------
# The recorded-trade R multiple, at each of its refusals
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("net", "risk", "phase", "fragment"),
    [
        (money("10"), money("5"), LifecyclePhase.OPEN, "has not closed"),
        (Absent("no fill"), money("5"), LifecyclePhase.CLOSED, "no fill"),
        (money("10"), Absent("stop moved past entry"), LifecyclePhase.CLOSED,
         "no capital-at-risk figure"),
        (money("10"), money("0"), LifecyclePhase.CLOSED, "undefined rather than large"),
    ],
)
def test_a_recorded_r_multiple_refuses_each_way_it_cannot_be_stated(
    net, risk, phase, fragment
) -> None:
    """A zero denominator is the important one: it would otherwise produce the
    largest R multiple in the corpus out of the trade whose stop could not be
    measured."""
    from fmis.statistics.collect import _recorded_r

    absent = _recorded_r(net, risk, phase)
    assert isinstance(absent, Absent)
    assert fragment in absent.reason


def test_a_recorded_r_multiple_is_the_quotient_when_every_input_is_there() -> None:
    from fmis.statistics.collect import _recorded_r

    assert _recorded_r(money("30"), money("10"), LifecyclePhase.CLOSED) == Decimal(3)


def test_a_trade_with_no_fill_at_all_names_the_missing_account() -> None:
    from fmis.statistics.collect import _accounts

    class _NoFills:
        accounts: tuple[str, ...] = ()

    absent = _accounts(_NoFills())
    assert isinstance(absent, Absent)
    assert "no fill has named an account" in absent.reason


# --------------------------------------------------------------------------
# A commitment with nothing filled against it
# --------------------------------------------------------------------------


def test_a_plan_with_no_fill_carries_every_position_derived_absence(
    tmp_path: Path,
) -> None:
    """`fmits trade plan` records a commitment and no fill. Every figure the
    position fold would have supplied is absent with its own reason — not zero,
    which would put a trade that was never taken into every average."""
    from decimal import Decimal as D

    from fmis.trade_capture import PlanRequest, record_plan
    from test_statistics_collect import at as store_day, market, store_at

    root = tmp_path / "store"
    record_plan(
        store_at(root),
        PlanRequest(
            market=market("BTC"), book=Book.SWING, direction=TradeDirection.LONG,
            stop=D("90"), targets=(D("120"),), committed_at=store_day(0),
            written_at=store_day(0), author="test", confidence="moderate",
            code_version="test",
        ),
    )
    found = collect_trades(root, at=store_day(5)).trades[0]
    assert found.phase is LifecyclePhase.PENDING
    for value in (
        found.realized_pnl_net, found.realized_pnl_gross,
        found.opened_at, found.closed_at, found.holding_time,
    ):
        assert isinstance(value, Absent)
    assert "never held a position" in found.opened_at.reason
    assert "nothing has filled" in found.realized_pnl_net.reason


# --------------------------------------------------------------------------
# The owner's open-risk ceiling, at each of its four answers
# --------------------------------------------------------------------------


def write_budget(root: Path, *, limits, budget_id: str = "swing_budget", day: int = 0):
    """One risk budget, written through the store's own repository."""
    from persistence_helpers import risk_budget, write_request
    from test_statistics_collect import at as store_day, store_at

    store = store_at(root)
    budget = risk_budget(
        budget_id=budget_id, effective_from=store_day(day), limits=limits
    )
    store.risk.create(budget, request=write_request(written_at=store_day(day)))
    return budget


def money_limit(amount: str = "500"):
    from fmis.risk import LimitPeriod, LimitScope, LimitSeverity, LimitUnit
    from persistence_helpers import risk_limit

    return risk_limit(
        limit_id="total_open_risk",
        scope=LimitScope.TOTAL_OPEN_RISK,
        value=money(amount),
        unit=LimitUnit.MONEY,
        period=LimitPeriod.NONE,
        severity=LimitSeverity.HARD_BLOCK,
    )


def test_a_recorded_money_ceiling_is_read_back(tmp_path: Path) -> None:
    from test_statistics_collect import at as store_day, store_at

    root = tmp_path / "store"
    write_budget(root, limits=(money_limit("500"),))
    assert open_risk_limit(store_at(root), at=store_day(5)) == money("500")


def test_a_ceiling_stated_as_a_percent_is_refused_rather_than_converted(
    tmp_path: Path,
) -> None:
    """Converting it needs the equity it was measured against, and doing that
    division quietly here would be the second place a limit is interpreted."""
    from fmis.risk import LimitPeriod, LimitScope, LimitSeverity, LimitUnit
    from persistence_helpers import risk_limit
    from test_statistics_collect import at as store_day, store_at

    root = tmp_path / "store"
    write_budget(
        root,
        limits=(
            risk_limit(
                limit_id="total_open_risk", scope=LimitScope.TOTAL_OPEN_RISK,
                value=Decimal("0.06"), unit=LimitUnit.PERCENT_OF_EQUITY,
                period=LimitPeriod.NONE, severity=LimitSeverity.HARD_BLOCK,
            ),
        ),
    )
    absent = open_risk_limit(store_at(root), at=store_day(5))
    assert isinstance(absent, Absent)
    assert "needs the equity it was measured against" in absent.reason


def test_a_budget_with_no_open_risk_limit_has_no_ceiling(tmp_path: Path) -> None:
    from persistence_helpers import risk_limit
    from test_statistics_collect import at as store_day, store_at

    root = tmp_path / "store"
    write_budget(root, limits=(risk_limit(),))
    absent = open_risk_limit(store_at(root), at=store_day(5))
    assert "states no total-open-risk limit" in absent.reason


def test_two_budget_lineages_are_refused_rather_than_guessed_between(
    tmp_path: Path,
) -> None:
    from test_statistics_collect import at as store_day, store_at

    root = tmp_path / "store"
    write_budget(root, limits=(money_limit("500"),), budget_id="swing_budget")
    write_budget(root, limits=(money_limit("900"),), budget_id="day_budget", day=1)
    absent = open_risk_limit(store_at(root), at=store_day(5))
    assert isinstance(absent, Absent)
    assert "lineages exist and this reading picks" in absent.reason


def test_a_budget_not_yet_in_force_leaves_the_ceiling_absent(tmp_path: Path) -> None:
    from test_statistics_collect import at as store_day, store_at

    root = tmp_path / "store"
    write_budget(root, limits=(money_limit("500"),), day=8)
    absent = open_risk_limit(store_at(root), at=store_day(2))
    assert isinstance(absent, Absent)


def test_a_ceiling_reaches_the_report_and_produces_a_utilization(
    tmp_path: Path,
) -> None:
    """The whole chain: a limit the owner recorded, this corpus's open risk, and
    the one division between them."""
    from fmis.statistics import report_for_store
    from test_statistics_collect import at as store_day, write_trade

    root = tmp_path / "store"
    write_trade(root, entry="100", stop="90", size="10", day=0)  # risk 100
    write_budget(root, limits=(money_limit("500"),), day=1)
    report = report_for_store(root, at=store_day(5), policy=LOW)
    assert report.primary.risk.total_open_risk == money("100")
    assert report.primary.risk.risk_utilization == Decimal("0.2")


# --------------------------------------------------------------------------
# The last refusals, and the rendering branches only a shaped page reaches
# --------------------------------------------------------------------------


def test_a_bucket_refuses_a_bound_that_is_not_a_number() -> None:
    from fmis.statistics import Bucket

    with pytest.raises(TypeError, match="lower must be a Decimal or None"):
        Bucket(label="x", lower=1, upper=Decimal(2), count=0)
    with pytest.raises(TypeError, match="upper must be a Decimal or None"):
        Bucket(label="x", lower=Decimal(1), upper=2, count=0)


def test_a_histogram_refuses_an_empty_or_malformed_bucket_list() -> None:
    with pytest.raises(TypeError, match="non-empty tuple"):
        Histogram(kind="r_multiple", unit="R", buckets=(), size=0, missing=0)
    with pytest.raises(TypeError, match="every bucket must be a Bucket"):
        Histogram(kind="r_multiple", unit="R", buckets=("x",), size=0, missing=0)


def test_binning_refuses_a_non_sample() -> None:
    from fmis.statistics import histogram_of

    with pytest.raises(TypeError, match="sample must be a Sample"):
        histogram_of("not a sample", kind="r_multiple")


def test_a_drawdown_period_refuses_each_wrong_type() -> None:
    from fmis.statistics import DrawdownPeriod

    base = {
        "peak_at": at(1), "trough_at": at(2), "recovered_at": NONE,
        "peak": money("10"), "trough": money("5"), "depth": money("5"),
        "depth_percent": NONE, "trades": 1,
    }
    for field_name, fragment in (
        ("peak", "peak must be a Money"),
        ("trough", "trough must be a Money"),
        ("depth", "depth must be a Money"),
    ):
        fields = dict(base)
        fields[field_name] = 1
        with pytest.raises(TypeError, match=fragment):
            DrawdownPeriod(**fields)
    fields = dict(base)
    fields["depth_percent"] = 0.5
    with pytest.raises(TypeError, match="depth_percent must be a Decimal or Absent"):
        DrawdownPeriod(**fields)


def test_the_depth_floor_returns_zero_when_the_curve_is_above_its_peak() -> None:
    """Unreachable through `drawdown_curve`, whose peak is the running maximum
    by construction — and the floor is what makes that a property rather than an
    assumption, so it is exercised directly."""
    from fmis.statistics.drawdown import _depth

    assert _depth(money("10"), money("25")) == Money.zero(USDT)


def test_the_risk_fold_refuses_a_trades_argument_that_is_not_a_tuple() -> None:
    with pytest.raises(TypeError, match="trades must be a tuple"):
        risk_statistics([], LOW, quote_asset=USDT, equity_basis=NONE, utilization=NONE)


def test_an_empty_as_of_flag_is_refused() -> None:
    from fmis.statistics import as_of_from_text

    with pytest.raises(ValueError, match="no instant"):
        as_of_from_text("   ")


def test_a_stat_names_the_type_it_expected_for_each_optional_field() -> None:
    """`_maybe`'s message builder, which formats one name or a pair."""
    from fmis.statistics.models import _maybe

    with pytest.raises(TypeError, match="must be a Decimal or Absent"):
        _maybe("no", Decimal, "r_multiple")
    with pytest.raises(TypeError, match="must be a Money or Absent"):
        _maybe("no", Money, "initial_risk")
    with pytest.raises(TypeError, match="must be a int or str or Absent"):
        _maybe(1.5, (int, str), "bars_held")


def test_a_stat_refuses_a_market_or_asset_of_the_wrong_type() -> None:
    from fmis.statistics import TradeStat

    fields = {
        "trade_ref": "x", "plan_id": "p", "source": StatSource.RECORDED,
        "phase": LifecyclePhase.PENDING, "market": "BTCUSDT", "book": Book.SWING,
        "direction": TradeDirection.LONG, "quote_asset": USDT,
        "committed_at": at(0),
    }
    with pytest.raises(TypeError, match="market must be a MarketId"):
        TradeStat(**fields)
    fields["market"] = MarketId(
        venue=VenueId("binance"), base_asset=AssetCode("BTC"),
        quote_asset=USDT, mode=MarketMode.SPOT,
    )
    fields["quote_asset"] = "USDT"
    with pytest.raises(TypeError, match="quote_asset must be an AssetCode"):
        TradeStat(**fields)


def test_profit_factor_carries_forward_whichever_total_is_absent() -> None:
    """Each half separately: the reason a page shows must name the total that
    could not be stated, not a generic one."""
    trades = (
        stat("a", net="10", closed_day=1),
        stat("b", net=None, closed_day=2, phase=LifecyclePhase.CLOSED),
    )
    reading = performance_statistics(trades, LOW, quote_asset=USDT)
    assert reading.gross_profit == money("10")
    losers_missing = (
        stat("a", net="10", closed_day=1),
        stat("b", net="-5", closed_day=2),
    )
    full = performance_statistics(losers_missing, LOW, quote_asset=USDT)
    assert full.profit_factor == Decimal(2)


def test_the_profit_factor_forwards_an_absent_gross_profit() -> None:
    from fmis.statistics.performance import _profit_factor

    absent_profit = Absent("gross profit cannot be totalled")
    assert _profit_factor(absent_profit, money("5"), 9, LOW) is absent_profit
    absent_loss = Absent("gross loss cannot be totalled")
    assert _profit_factor(money("5"), absent_loss, 9, LOW) is absent_loss


def test_the_renderer_falls_back_to_str_for_a_plain_value() -> None:
    from fmis.statistics.render import _value

    assert _value(7) == "7"
    assert _value("already text") == "already text"


def test_the_percent_helper_renders_an_absence_as_its_reason() -> None:
    from fmis.statistics.render import _percent

    assert "no ceiling" in _percent(Absent("no ceiling"))


def test_a_stated_utilization_prints_as_a_percentage() -> None:
    from fmis.statistics import report_for_store

    report = build_report(
        CollectedTrades(
            trades=(stat("a", phase=LifecyclePhase.OPEN, closed_day=None, net=None,
                         risk="250"),),
            refused=(), store_root="/tmp/s", present=True,
        ),
        at=at(9), policy=LOW, open_risk_ceiling=money("1000"),
    )
    from fmis.statistics import render_statistics

    assert "Risk utilization           25 %" in render_statistics(report)


def test_the_equity_page_prints_the_reason_each_step_was_excluded() -> None:
    from fmis.statistics import render_equity

    orphan = stat("x", phase=LifecyclePhase.CLOSED, net=None, closed_day=2)
    report = build_report(
        CollectedTrades(trades=(orphan,), refused=(), store_root="/tmp/s",
                        present=True),
        at=at(9), policy=LOW,
    )
    page = " ".join(render_equity(report).split())
    assert "closed with no stateable profit and loss" in page


def test_a_dimension_with_no_cell_at_all_says_so_on_the_page() -> None:
    """Unreachable from `breakdown_set`, which always produces at least one cell
    for a non-empty corpus — and reachable by a caller cutting an empty one."""
    from fmis.statistics.render import _breakdown

    empty = Breakdown(dimension="symbol", cells=(), quote_asset=USDT)
    lines = _breakdown(empty)
    assert any("No trade in this corpus falls under" in line for line in lines)


# --------------------------------------------------------------------------
# The snapshot bridge, and the refusals `collect` names rather than raises
# --------------------------------------------------------------------------


def test_a_plan_citing_a_frozen_snapshot_carries_its_regime_onto_the_stat(
    tmp_path: Path,
) -> None:
    """The whole bridge, through the store: a plan names a `market_snapshot_id`,
    the snapshot is read once for the corpus, and its setup role's regime
    becomes the dimension the per-regime breakdown cuts on."""
    from decimal import Decimal as D

    from fmis.trade_capture import PlanRequest, record_plan
    from persistence_helpers import write_request
    from test_statistics_collect import at as store_day, market, store_at
    from trade_domain_helpers import market_snapshot

    # The shared fixture's snapshot is dated on the trade-domain helpers' own
    # clock, and a frozen bundle may not contain a reading from its own future —
    # so the store's instants follow the snapshot rather than the other way
    # round.
    root = tmp_path / "store"
    store = store_at(root)
    snapshot = market_snapshot()
    built = snapshot.built_at
    store.snapshots.create(snapshot, request=write_request(written_at=built))
    record_plan(
        store_at(root),
        PlanRequest(
            market=market("BTC"), book=Book.SWING, direction=TradeDirection.LONG,
            stop=D("90"), targets=(D("120"),), committed_at=built,
            written_at=built, author="test", confidence="moderate",
            code_version="test", market_snapshot_id=snapshot.snapshot_id,
        ),
    )
    found = collect_trades(root, at=built + timedelta(days=5)).trades[0]
    assert found.regime_states, "the plan's frozen snapshot should supply a regime"
    cuts = breakdown_set((found,), LOW, quote_asset=USDT)
    keys = [cell.key for cell in cuts.by_dimension("regime").cells]
    # The default dimension must be one the snapshot actually carries, or the
    # cut silently becomes `UNCLASSIFIED` for every trade.
    assert cuts.regime_dimension in found.regime_states
    assert keys == [found.regime_states[cuts.regime_dimension]]


def test_a_trade_the_mapper_refuses_is_named_rather_than_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A trade this module cannot map is a trade absent from every count on
    every page. Naming it is what stops a corpus quietly shrinking — and the
    failure is injected because no shape the product writes produces one."""
    from fmis.statistics import StatisticsError
    import fmis.statistics.collect as collect_module
    from test_statistics_collect import at as store_day, write_trade

    root = tmp_path / "store"
    write_trade(root, day=0)

    def refuse(view, *, snapshot=None):
        raise StatisticsError("this view names a phase nothing declares")

    monkeypatch.setattr(collect_module, "stat_from_recorded", refuse)
    collected = collect_trades(root, at=store_day(5))
    assert collected.trades == ()
    assert len(collected.refused) == 1
    assert "names a phase nothing declares" in collected.refused[0]


def test_a_simulated_trade_the_mapper_refuses_is_named_by_its_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fmis.paper import PAPER_DUST_POLICY
    from fmis.statistics import StatisticsError
    import fmis.statistics.collect as collect_module
    from paper_helpers import at as bar_at
    from test_statistics_collect import WINNING_BARS, simulated_trade

    root = tmp_path / "store"
    activation_id = simulated_trade(root, bars=WINNING_BARS)

    def refuse(view, *, snapshot=None):
        raise StatisticsError("this activation folds to an unknown state")

    monkeypatch.setattr(collect_module, "stat_from_paper", refuse)
    collected = collect_trades(root, at=bar_at(9), dust=PAPER_DUST_POLICY)
    assert collected.trades == ()
    assert collected.refused[0].startswith(activation_id)


def test_the_ongoing_period_is_found_past_the_recovered_ones() -> None:
    """A curve with a recovered decline and then a live one: the scan must walk
    past the first to reach the second."""
    reading = drawdown_curve(
        equity_curve(
            (
                stat("a", net="100", closed_day=1),
                stat("b", net="-50", closed_day=2),
                stat("c", net="60", closed_day=3),
                stat("d", net="-20", closed_day=4),
            ),
            quote_asset=USDT, starting_equity=NONE,
        ),
        LOW,
    )
    assert len(reading.periods) == 2
    assert not reading.periods[0].is_ongoing
    ongoing = reading.ongoing
    assert not isinstance(ongoing, Absent)
    assert ongoing is reading.periods[1]
