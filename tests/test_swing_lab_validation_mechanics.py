"""Entry, exit and ambiguity studies over a hand-built capture and ladder.

The properties that matter are comparative rather than absolute — no fixture can
say what the *right* expectancy is — so what is asserted here is that the three
studies are **comparisons of one thing at a time**:

* every entry rule sees the same plans, from the same geometry, on the same
  setups, and is walked under the same exit mechanic;
* every exit mechanic sees the same entry, and the baseline is measured twice —
  with and without the ladder — so "the management helped" and "the finer data
  resolved trades the coarse simulator refused" stay separable;
* a missed entry is counted with a reason, never dropped, because a rule that
  improves its trades by declining the losers is making a selection claim.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.entry import PRE_DECLARED_ENTRY_POLICIES, MissReason, PathRole
from fmis.swing_lab.exits import PRE_DECLARED_EXIT_POLICIES
from fmis.swing_lab.geometry_replay import GeometryCapture
from fmis.swing_lab.models import LabExitReason, SwingLabError
from fmis.swing_lab.nonstructural import synthetic_policy
from fmis.swing_lab.trades import FRICTIONLESS_COSTS
from fmis.swing_lab.validation_mechanics import (
    LadderSet,
    ambiguity_reading,
    ladder_set,
    run_entry_study,
    run_exit_study,
    unresolved_spans,
    window_bars_for,
)

from tests.swing_lab_helpers import candidate

_UTC = timezone.utc
_T0 = datetime(2026, 1, 1, tzinfo=_UTC)
_WINDOW = 12

#: A LONG at 100 with execution ATR 1.0 → stop 99.5, target 101.0. Chosen so a
#: 4H bar spanning 99.4–101.1 reaches BOTH, which is the ambiguity under test.
GEOMETRY = synthetic_policy(0.5, 2.0)


def _bar(index: int, o: str, h: str, low: str, c: str, *, symbol="BTCUSDT", interval="4h"):
    step = timedelta(hours=4) if interval == "4h" else timedelta(hours=1)
    return PriceBar(
        symbol=symbol, interval=interval, open_time=_T0 + step * index,
        open=Decimal(o), high=Decimal(h), low=Decimal(low), close=Decimal(c),
    )


def _coarse(symbol: str = "BTCUSDT") -> tuple[PriceBar, ...]:
    """Bar 0 signals; bar 1 is the entry; bar 2 reaches both levels."""
    return (
        _bar(0, "100", "100.2", "99.8", "100", symbol=symbol),
        _bar(1, "100", "100.4", "99.6", "100", symbol=symbol),
        _bar(2, "100", "101.1", "99.4", "100", symbol=symbol),
        _bar(3, "100", "100.4", "99.6", "100", symbol=symbol),
        _bar(4, "100", "100.4", "99.6", "100", symbol=symbol),
    )


def _fine(symbol: str = "BTCUSDT") -> tuple[PriceBar, ...]:
    """1H cover of every 4H bar, with bar 2's span resolving TARGET first."""
    rows: list[PriceBar] = []
    for coarse_index in range(5):
        for offset in range(4):
            index = coarse_index * 4 + offset
            if coarse_index == 2 and offset == 1:
                rows.append(_bar(index, "100", "101.1", "99.9", "101", symbol=symbol, interval="1h"))
            elif coarse_index == 2 and offset == 2:
                rows.append(_bar(index, "101", "101.1", "99.4", "99.5", symbol=symbol, interval="1h"))
            else:
                rows.append(_bar(index, "100", "100.2", "99.8", "100", symbol=symbol, interval="1h"))
    return tuple(rows)


def _capture(symbol: str = "BTCUSDT", count: int = 1) -> GeometryCapture:
    return GeometryCapture(
        admission_variant_id="swing_current",
        admission_policy_id="swing-setup-v1",
        candidates=tuple(
            candidate(
                symbol=symbol, setup_id=f"{symbol}|long|seq{index}",
                signal_index=0, signal_at=_T0,
            )
            for index in range(count)
        ),
        bars_by_symbol={symbol: _coarse(symbol)},
        metadata={},
    )


def _ladders(*, with_refinement: bool = True) -> LadderSet:
    return ladder_set(
        _capture(),
        execution_interval="4h",
        refinement={"BTCUSDT": _fine()} if with_refinement else {},
        refinement_interval="1h",
    )


# ------------------------------------------------------------ the window ---


def test_the_evaluation_window_is_the_same_wall_clock_span_at_every_resolution() -> None:
    """A 1H walk over "180 bars" would cover 7.5 days where the 4H walk covers 30."""
    assert window_bars_for("4h", execution_interval="4h", execution_bars=180) == 180
    assert window_bars_for("1h", execution_interval="4h", execution_bars=180) == 720
    assert window_bars_for("15m", execution_interval="4h", execution_bars=180) == 2880


def test_a_resolution_that_does_not_divide_the_window_is_refused() -> None:
    """The realistic misuse: asking for a rung COARSER than the walk it covers."""
    with pytest.raises(SwingLabError, match="different windows"):
        window_bars_for("1d", execution_interval="4h", execution_bars=1)


# ------------------------------------------------------------- the ladder ---


def test_a_symbol_without_a_refinement_series_gets_a_one_rung_ladder() -> None:
    """It must behave exactly as BX did, never borrow another symbol's resolution."""
    ladders = _ladders(with_refinement=False)
    ladder = ladders.ladder("BTCUSDT", from_interval="4h")
    assert ladder.intervals == ("4h",)


def test_the_ladder_can_be_rooted_at_the_refinement_rung() -> None:
    """A 1H-path entry rule must walk a ladder whose TOP rung is 1H."""
    ladders = _ladders()
    assert ladders.ladder("BTCUSDT", from_interval="1h").intervals == ("1h",)
    assert ladders.ladder("BTCUSDT", from_interval="4h").intervals == ("4h", "1h")


def test_a_ladder_for_an_unknown_symbol_is_absent_rather_than_wrong() -> None:
    assert _ladders().ladder("ETHUSDT", from_interval="4h") is None


def test_a_fine_rung_needs_both_its_bars_and_its_interval() -> None:
    with pytest.raises(SwingLabError, match="both its bars and its interval"):
        ladder_set(
            _capture(), execution_interval="4h",
            refinement={}, refinement_interval="1h", fine={"BTCUSDT": ()},
        )


# -------------------------------------------------------------- ambiguity ---


def test_the_ladder_converts_bx_s_refusal_into_a_measured_trade() -> None:
    """§8's headline, on a fixture: a 4H ambiguity resolved by real 1H candles."""
    measurements = run_exit_study(
        _capture(), geometry=GEOMETRY, ladders=_ladders(),
        costs=FRICTIONLESS_COSTS, execution_window_bars=_WINDOW, sample="fixture",
    )
    reading = ambiguity_reading(measurements)
    assert reading.without_ladder == 1
    assert reading.with_ladder == 0
    assert reading.resolved == 1
    assert reading.resolution_rate == 1.0


def test_without_a_refinement_series_nothing_is_resolved() -> None:
    measurements = run_exit_study(
        _capture(), geometry=GEOMETRY, ladders=_ladders(with_refinement=False),
        costs=FRICTIONLESS_COSTS, execution_window_bars=_WINDOW, sample="fixture",
    )
    reading = ambiguity_reading(measurements)
    assert reading.resolved == 0
    assert reading.still_ambiguous == 1
    assert reading.unresolved_spans


def test_an_ambiguity_reading_needs_the_baseline_pair() -> None:
    """Without both halves the comparison would confound resolution with management."""
    with pytest.raises(SwingLabError, match="with and without a ladder"):
        ambiguity_reading(())


def test_unresolved_spans_name_the_symbol_and_the_bar() -> None:
    measurements = run_exit_study(
        _capture(), geometry=GEOMETRY, ladders=_ladders(with_refinement=False),
        costs=FRICTIONLESS_COSTS, execution_window_bars=_WINDOW, sample="fixture",
    )
    spans = unresolved_spans(measurements)
    assert spans
    assert all(symbol == "BTCUSDT" for symbol, _ in spans)


# ------------------------------------------------------------------ exits ---


def test_the_baseline_exit_is_measured_both_with_and_without_the_ladder() -> None:
    measurements = run_exit_study(
        _capture(), geometry=GEOMETRY, ladders=_ladders(),
        costs=FRICTIONLESS_COSTS, execution_window_bars=_WINDOW, sample="fixture",
    )
    baselines = [item for item in measurements if item.policy.is_baseline]
    assert {item.used_ladder for item in baselines} == {True, False}


def test_every_pre_declared_exit_mechanic_is_measured() -> None:
    measurements = run_exit_study(
        _capture(), geometry=GEOMETRY, ladders=_ladders(),
        costs=FRICTIONLESS_COSTS, execution_window_bars=_WINDOW, sample="fixture",
    )
    assert {item.policy.policy_id for item in measurements} == {
        item.policy_id for item in PRE_DECLARED_EXIT_POLICIES
    }


def test_two_mechanics_trades_can_never_be_summed_by_accident() -> None:
    measurements = run_exit_study(
        _capture(), geometry=GEOMETRY, ladders=_ladders(),
        costs=FRICTIONLESS_COSTS, execution_window_bars=_WINDOW, sample="fixture",
    )
    variants = {trade.variant_id for item in measurements for trade in item.trades}
    assert len(variants) == len(measurements)


def test_every_exit_mechanic_sees_the_same_setups() -> None:
    """A difference between two mechanics must not be a difference in what they took."""
    measurements = run_exit_study(
        _capture(count=3), geometry=GEOMETRY, ladders=_ladders(),
        costs=FRICTIONLESS_COSTS, execution_window_bars=_WINDOW, sample="fixture",
    )
    counts = {len(item.trades) for item in measurements}
    assert counts == {3}


# ----------------------------------------------------------------- entries ---


def test_every_pre_declared_entry_rule_is_measured() -> None:
    measurements = run_entry_study(
        _capture(), geometry=GEOMETRY, ladders=_ladders(),
        costs=FRICTIONLESS_COSTS, execution_window_bars=_WINDOW, sample="fixture",
    )
    assert {item.policy.policy_id for item in measurements} == {
        item.policy_id for item in PRE_DECLARED_ENTRY_POLICIES
    }


def test_every_entry_rule_starts_from_the_same_plans() -> None:
    """filled + missed must equal the plan count for EVERY rule."""
    measurements = run_entry_study(
        _capture(count=4), geometry=GEOMETRY, ladders=_ladders(),
        costs=FRICTIONLESS_COSTS, execution_window_bars=_WINDOW, sample="fixture",
    )
    for item in measurements:
        assert item.filled + item.missed == 4
        assert len(item.trades) == 4


def test_a_missed_entry_is_recorded_with_its_reason_and_carries_no_r() -> None:
    """A rule that declines the losers is SELECTING; the count makes that visible."""
    measurements = run_entry_study(
        _capture(), geometry=GEOMETRY, ladders=_ladders(),
        costs=FRICTIONLESS_COSTS, execution_window_bars=_WINDOW, sample="fixture",
    )
    missed = [item for item in measurements if item.missed]
    assert missed, "the flat fixture must decline at least one continuation rule"
    for item in missed:
        assert item.miss_reasons
        declined = [
            trade for trade in item.trades
            if trade.exit_reason is LabExitReason.ENTRY_NOT_TRIGGERED
        ]
        assert declined
        assert all(trade.net_r is None and trade.entry_price is None for trade in declined)


def test_a_rule_needing_a_missing_refinement_series_reports_it_rather_than_estimating() -> None:
    measurements = run_entry_study(
        _capture(), geometry=GEOMETRY, ladders=_ladders(with_refinement=False),
        costs=FRICTIONLESS_COSTS, execution_window_bars=_WINDOW, sample="fixture",
    )
    refined = [
        item for item in measurements if item.policy.path is PathRole.REFINEMENT
    ]
    assert refined
    for item in refined:
        assert dict(item.miss_reasons) == {
            MissReason.REFINEMENT_UNAVAILABLE.value: 1
        }


def test_the_fill_rate_is_absent_rather_than_zero_when_nothing_was_planned() -> None:
    empty = GeometryCapture(
        admission_variant_id="v", admission_policy_id="p",
        candidates=(), bars_by_symbol={"BTCUSDT": _coarse()}, metadata={},
    )
    measurements = run_entry_study(
        empty, geometry=GEOMETRY, ladders=_ladders(),
        costs=FRICTIONLESS_COSTS, execution_window_bars=_WINDOW, sample="fixture",
    )
    assert all(item.fill_rate is None for item in measurements)


def test_the_baseline_entry_fills_where_simulate_trade_fills() -> None:
    """The control. Drift here invalidates every entry comparison."""
    measurements = run_entry_study(
        _capture(), geometry=GEOMETRY, ladders=_ladders(),
        costs=FRICTIONLESS_COSTS, execution_window_bars=_WINDOW, sample="fixture",
    )
    baseline = next(item for item in measurements if item.policy.is_baseline)
    trade = baseline.trades[0]
    assert trade.entry_at == _coarse()[1].open_time
    assert trade.entry_price == _coarse()[1].open
