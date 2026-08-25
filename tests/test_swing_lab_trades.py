"""The trade simulator, attacked at every boundary a backtest usually flatters itself at."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.models import LabExitReason, SwingLabError, TradeVerdict
from fmis.swing_lab.trades import (
    CONSERVATIVE_COSTS,
    FRICTIONLESS_COSTS,
    reprice,
    simulate_trade,
)
from fmis.swing_setup.models import Direction

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def bar(index: int, open_: str, high: str, low: str, close: str) -> PriceBar:
    return PriceBar(
        symbol="BTCUSDT",
        interval="4h",
        open_time=T0 + timedelta(hours=4 * index),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
    )


def run(
    bars,
    direction=Direction.LONG,
    *,
    stop="90",
    target="120",
    costs=FRICTIONLESS_COSTS,
    window=10,
    signal_index=0,
):
    return simulate_trade(
        bars,
        variant_id="v",
        symbol="BTCUSDT",
        setup_id="setup-1",
        direction=direction,
        signal_index=signal_index,
        signal_at=bars[signal_index].open_time,
        reference_price=Decimal("100"),
        stop_price=Decimal(stop),
        target_price=Decimal(target),
        planned_risk_reward=2.0,
        window_bars=window,
        costs=costs,
    )


SIGNAL = bar(0, "100", "101", "99", "100")


class TestOutcomes:
    def test_long_winner_is_exactly_the_planned_reward(self) -> None:
        trade = run([SIGNAL, bar(1, "100", "105", "98", "104"), bar(2, "104", "121", "103", "120")])
        assert trade.exit_reason is LabExitReason.TARGET
        assert trade.net_r == Decimal("2")
        assert trade.verdict is TradeVerdict.WIN
        assert trade.bars_held == 2

    def test_a_normal_exit_records_its_excursions_the_right_way_round(self) -> None:
        """MFE is the favourable extreme, MAE the adverse one — never swapped.

        Asserted on an ordinary target exit, not only on the ambiguous path: a
        swap confined to the normal return would otherwise be invisible, which
        is exactly what a mutation probe found.
        """
        trade = run([SIGNAL, bar(1, "100", "112", "94", "104"), bar(2, "104", "121", "103", "120")])
        assert trade.exit_reason is LabExitReason.TARGET
        # Entry 100, risk 10. Best seen 121 -> +2.1R. Worst seen 94 -> -0.6R.
        assert trade.mfe_r == Decimal("2.1")
        assert trade.mae_r == Decimal("-0.6")
        assert trade.mfe_r > 0 > trade.mae_r

    def test_a_short_trade_excursions_are_not_inverted(self) -> None:
        trade = run(
            [SIGNAL, bar(1, "100", "106", "88", "90"), bar(2, "90", "92", "79", "80")],
            Direction.SHORT, stop="110", target="80",
        )
        assert trade.exit_reason is LabExitReason.TARGET
        # Short from 100, risk 10. Best (lowest) 79 -> +2.1R. Worst (highest) 106 -> -0.6R.
        assert trade.mfe_r == Decimal("2.1")
        assert trade.mae_r == Decimal("-0.6")

    def test_a_loser_has_a_negative_mae_at_least_as_deep_as_the_stop(self) -> None:
        trade = run([SIGNAL, bar(1, "100", "102", "85", "91")])
        assert trade.exit_reason is LabExitReason.STOP
        assert trade.mae_r == Decimal("-1.5")
        assert trade.mfe_r == Decimal("0.2")

    def test_long_loser_is_exactly_minus_one_r(self) -> None:
        trade = run([SIGNAL, bar(1, "100", "102", "89", "91")])
        assert trade.exit_reason is LabExitReason.STOP
        assert trade.net_r == Decimal("-1")
        assert trade.verdict is TradeVerdict.LOSS

    def test_short_winner(self) -> None:
        trade = run(
            [SIGNAL, bar(1, "100", "102", "79", "80")],
            Direction.SHORT, stop="110", target="80",
        )
        assert trade.exit_reason is LabExitReason.TARGET
        assert trade.net_r == Decimal("2")

    def test_short_loser(self) -> None:
        trade = run(
            [SIGNAL, bar(1, "100", "111", "99", "110")],
            Direction.SHORT, stop="110", target="80",
        )
        assert trade.exit_reason is LabExitReason.STOP
        assert trade.net_r == Decimal("-1")

    def test_time_stop_exits_at_the_last_bar_close(self) -> None:
        trade = run(
            [SIGNAL, bar(1, "100", "102", "99", "101"), bar(2, "101", "103", "100", "102")],
            window=2,
        )
        assert trade.exit_reason is LabExitReason.TIME_STOP
        assert trade.net_r == Decimal("0.2")
        assert trade.bars_held == 2

    def test_no_entry_bar_when_history_ends_at_the_signal(self) -> None:
        trade = run([SIGNAL])
        assert trade.exit_reason is LabExitReason.NO_ENTRY_BAR
        assert trade.net_r is None
        assert trade.verdict is TradeVerdict.UNMEASURED


class TestAmbiguityIsRefusedNotResolved:
    def test_stop_and_target_on_one_bar_produces_no_r(self) -> None:
        trade = run([SIGNAL, bar(1, "100", "121", "89", "100")])
        assert trade.exit_reason is LabExitReason.AMBIGUOUS_SAME_BAR
        assert trade.net_r is None
        assert trade.gross_r is None
        assert not trade.is_measurable

    def test_ambiguity_is_not_resolved_by_candle_colour(self) -> None:
        """A green and a red bar reaching both levels must be judged identically."""
        green = run([SIGNAL, bar(1, "100", "121", "89", "119")])
        red = run([SIGNAL, bar(1, "100", "121", "89", "91")])
        assert green.exit_reason is red.exit_reason is LabExitReason.AMBIGUOUS_SAME_BAR
        assert green.net_r is red.net_r is None

    def test_ambiguous_trade_still_records_its_excursions(self) -> None:
        trade = run([SIGNAL, bar(1, "100", "121", "89", "100")])
        assert trade.mfe_r == Decimal("2.1")
        assert trade.mae_r == Decimal("-1.1")

    def test_an_ambiguous_bar_never_produces_a_target_exit_price(self) -> None:
        """The refusal is enforced twice, and this pins both halves.

        The both-hit branch sets no exit price, and the terminal branch refuses
        any trade that has none. A mutation flipping only the first of those is
        neutralised by the second — so this asserts the *observable* guarantee:
        no price, no reason other than ambiguous, and no R.
        """
        trade = run([SIGNAL, bar(1, "100", "121", "89", "100")])
        assert trade.exit_price is None
        assert trade.exit_reason is LabExitReason.AMBIGUOUS_SAME_BAR
        assert trade.gross_r is None and trade.net_r is None

    def test_an_ambiguous_bar_is_excluded_from_every_measurable_figure(self) -> None:
        from fmis.swing_lab.metrics import compute_lab_metrics

        ambiguous = run([SIGNAL, bar(1, "100", "121", "89", "100")])
        metrics = compute_lab_metrics((ambiguous,), label="one")
        assert metrics.trades == 1
        assert metrics.measurable_trades == 0
        assert metrics.ambiguous_trades == 1
        assert metrics.total_r == Decimal("0")
        assert metrics.wins == 0 and metrics.losses == 0


class TestGapsAreNeverFavourable:
    def test_a_gap_through_the_stop_fills_worse_than_the_stop(self) -> None:
        trade = run([SIGNAL, bar(1, "100", "101", "99", "100"), bar(2, "85", "86", "84", "85")])
        assert trade.exit_reason is LabExitReason.STOP
        assert trade.exit_price == Decimal("85")
        assert trade.net_r == Decimal("-1.5")

    def test_a_gap_through_the_target_fills_at_the_open_not_the_target(self) -> None:
        trade = run([SIGNAL, bar(1, "100", "101", "99", "100"), bar(2, "130", "131", "129", "130")])
        assert trade.exit_reason is LabExitReason.TARGET
        assert trade.exit_price == Decimal("130")
        assert trade.net_r == Decimal("3")

    def test_entry_gapping_through_the_stop_is_recorded_not_skipped(self) -> None:
        trade = run([SIGNAL, bar(1, "85", "86", "84", "85")])
        assert trade.exit_reason is LabExitReason.ENTRY_GAPPED_THROUGH_STOP
        assert trade.net_r == Decimal("-1")

    def test_entry_gapping_past_the_target_is_not_a_free_win(self) -> None:
        trade = run([SIGNAL, bar(1, "130", "131", "129", "130")])
        assert trade.exit_reason is LabExitReason.NO_ENTRY_BAR
        assert trade.net_r is None


class TestEntryTiming:
    def test_entry_is_the_next_bar_open_never_the_signal_close(self) -> None:
        """The signal bar closed at 100; the next bar opened at 103."""
        trade = run([SIGNAL, bar(1, "103", "125", "102", "124")])
        assert trade.entry_price == Decimal("103")
        assert trade.entry_at == T0 + timedelta(hours=4)
        # Risk is measured from the ACTUAL fill (103-90=13), not from the
        # planned reference price (100-90=10).
        assert trade.net_r == (Decimal("120") - Decimal("103")) / Decimal("13")

    def test_the_signal_bar_own_range_cannot_resolve_the_trade(self) -> None:
        """A signal bar that pierced both levels must not decide the outcome."""
        violent = bar(0, "100", "200", "50", "100")
        trade = run([violent, bar(1, "100", "102", "99", "101")], window=1)
        assert trade.exit_reason is LabExitReason.TIME_STOP


class TestCosts:
    def test_costs_reduce_a_winner_and_deepen_a_loser(self) -> None:
        winner = run(
            [SIGNAL, bar(1, "100", "105", "98", "104"), bar(2, "104", "121", "103", "120")],
            costs=CONSERVATIVE_COSTS,
        )
        assert winner.gross_r == Decimal("2")
        assert winner.net_r < winner.gross_r
        loser = run([SIGNAL, bar(1, "100", "102", "89", "91")], costs=CONSERVATIVE_COSTS)
        assert loser.net_r < Decimal("-1")

    def test_repricing_equals_a_direct_run_at_that_cost(self) -> None:
        bars = [SIGNAL, bar(1, "100", "105", "98", "104"), bar(2, "104", "121", "103", "120")]
        assert reprice(run(bars), CONSERVATIVE_COSTS).net_r == run(
            bars, costs=CONSERVATIVE_COSTS
        ).net_r

    def test_repricing_changes_only_the_cost_never_the_path(self) -> None:
        original = run([SIGNAL, bar(1, "100", "105", "98", "104"), bar(2, "104", "121", "103", "120")])
        costed = reprice(original, CONSERVATIVE_COSTS)
        assert costed.exit_price == original.exit_price
        assert costed.exit_reason is original.exit_reason
        assert costed.bars_held == original.bars_held
        assert costed.mfe_r == original.mfe_r
        assert costed.mae_r == original.mae_r
        assert costed.cost_policy_id == CONSERVATIVE_COSTS.policy_id

    def test_repricing_an_unmeasurable_trade_keeps_it_unmeasurable(self) -> None:
        ambiguous = run([SIGNAL, bar(1, "100", "121", "89", "100")])
        costed = reprice(ambiguous, CONSERVATIVE_COSTS)
        assert costed.net_r is None
        assert costed.cost_policy_id == CONSERVATIVE_COSTS.policy_id


class TestRefusals:
    def test_a_non_positive_window_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="positive int"):
            run([SIGNAL, bar(1, "100", "101", "99", "100")], window=0)

    def test_a_negative_price_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="must be positive"):
            run([SIGNAL, bar(1, "100", "101", "99", "100")], stop="-1")

    def test_costs_must_be_a_policy(self) -> None:
        with pytest.raises(TypeError, match="PaperCostPolicy"):
            run([SIGNAL, bar(1, "100", "101", "99", "100")], costs="free")


class TestDeterminism:
    def test_two_identical_runs_agree_exactly(self) -> None:
        bars = [SIGNAL, bar(1, "100", "105", "98", "104"), bar(2, "104", "121", "103", "120")]
        assert run(bars) == run(bars)
