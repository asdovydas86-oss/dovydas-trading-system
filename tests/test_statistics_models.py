"""`TradeStat` — the unit, its derived answers, and what it refuses to hold.

The derived properties are where this milestone's honesty lives: `result`
decides a win on the one figure both sources produce, `capture_efficiency`
refuses a zero denominator, and `risk_fraction_of` refuses a baseline this
system does not record.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from fmis.accounts import Book
from fmis.money import AssetCode, Money
from fmis.provenance import Absent, ValueOrigin
from fmis.snapshotting import TradeDirection
from fmis.statistics import (
    STATISTICS_LIMITATIONS,
    LifecyclePhase,
    StatSource,
    StatisticsRefusedError,
    TradeResult,
    TradeStat,
)
from statistics_helpers import ABSENT, at, money, stat

USDT = AssetCode("USDT")


# --------------------------------------------------------------------------
# result — the win/loss basis
# --------------------------------------------------------------------------


def test_a_closed_trade_with_a_profit_is_a_win() -> None:
    assert stat(net="10").result is TradeResult.WIN


def test_a_closed_trade_with_a_loss_is_a_loss() -> None:
    assert stat(net="-10").result is TradeResult.LOSS


def test_a_closed_trade_at_exactly_zero_is_a_scratch_and_not_a_loss() -> None:
    """A scratch is its own member: folding it into losses would overstate the
    loss rate of a system that gets out flat."""
    assert stat(net="0").result is TradeResult.SCRATCH


def test_an_open_trade_is_unresolved_however_much_it_is_up() -> None:
    assert stat(phase=LifecyclePhase.OPEN, closed_day=None, net="500").result is (
        TradeResult.UNRESOLVED
    )


def test_a_closed_trade_with_no_stateable_result_is_unresolved_not_a_loss() -> None:
    """The single most important line in this file. Treating an unknown profit
    and loss as zero would make it a scratch; treating it as missing would make
    it a loss on any `if pnl < 0` written later. It is neither."""
    assert stat(net=None).result is TradeResult.UNRESOLVED


def test_the_result_is_decided_on_net_and_not_on_gross() -> None:
    """A trade whose fees ate the profit is not a win."""
    assert stat(net="-1", gross="10").result is TradeResult.LOSS


def test_a_missing_gross_does_not_make_a_stateable_net_unresolved() -> None:
    """The absence that decides `UNRESOLVED` is **net**'s, not gross's. A trade
    whose gross figure is unavailable but whose net one is not is still a
    result. Found by a mutation probe that swapped the two and survived, because
    the fixture made gross default to net."""
    assert stat(net="10", gross=ABSENT).result is TradeResult.WIN
    assert stat(net="-10", gross=ABSENT).result is TradeResult.LOSS


def test_the_result_is_decided_on_money_and_not_on_the_r_multiple() -> None:
    """Deciding on R would make every hand-recorded trade unresolved."""
    assert stat(source=StatSource.RECORDED, net="10", r_multiple=None).result is (
        TradeResult.WIN
    )


# --------------------------------------------------------------------------
# paper is a book, not a source
# --------------------------------------------------------------------------


def test_paper_follows_the_book_and_not_the_simulator() -> None:
    """`AP` §5.5 makes the book the economic classification. A simulated fill in
    a real book is representable and must not read as paper."""
    assert stat(source=StatSource.SIMULATED, book=Book.SWING).is_paper is False
    assert stat(source=StatSource.RECORDED, book=Book.PAPER).is_paper is True


# --------------------------------------------------------------------------
# excursion and capture
# --------------------------------------------------------------------------


def test_the_excursion_range_adds_both_extremes_as_magnitudes() -> None:
    assert stat(mfe="3", mae="-0.5").excursion_range_r == Decimal("3.5")


@pytest.mark.parametrize("missing", ["mfe", "mae"])
def test_an_excursion_range_needs_both_extremes(missing: str) -> None:
    """A range from one of them is a smaller number that reads as complete."""
    assert isinstance(stat(**{missing: None}).excursion_range_r, Absent)


def test_capture_efficiency_is_the_final_r_over_the_favourable_excursion() -> None:
    assert stat(r_multiple="2", mfe="4").capture_efficiency == Decimal("0.5")


def test_a_trade_that_never_went_in_front_has_no_capture_efficiency() -> None:
    """Zero would read as *"captured none of a large move"*; the truth is that
    there was no move to capture."""
    absent = stat(r_multiple="-1", mfe="0").capture_efficiency
    assert isinstance(absent, Absent)
    assert "no favourable excursion" in absent.reason


def test_a_negative_favourable_excursion_is_refused_the_same_way() -> None:
    assert isinstance(stat(r_multiple="-1", mfe="-0.2").capture_efficiency, Absent)


@pytest.mark.parametrize("missing", ["r_multiple", "mfe"])
def test_capture_efficiency_carries_forward_whichever_half_is_missing(
    missing: str,
) -> None:
    absent = stat(**{missing: None}).capture_efficiency
    assert isinstance(absent, Absent)


# --------------------------------------------------------------------------
# risk as a fraction of equity
# --------------------------------------------------------------------------


def test_a_risk_fraction_needs_a_baseline_this_system_does_not_record() -> None:
    absent = stat(risk="50").risk_fraction_of(Absent("none supplied"))
    assert isinstance(absent, Absent)
    assert "records no equity at the time of a trade" in absent.reason


def test_a_supplied_baseline_produces_the_fraction() -> None:
    assert stat(risk="50").risk_fraction_of(money("1000")) == Decimal("0.05")


def test_a_baseline_in_another_asset_is_refused_rather_than_converted() -> None:
    absent = stat(risk="50").risk_fraction_of(Money(Decimal(1000), AssetCode("BTC")))
    assert isinstance(absent, Absent)
    assert "no rate to cross them" in absent.reason or "cross them" in absent.reason


def test_a_baseline_of_zero_has_no_fraction_of_it() -> None:
    assert isinstance(stat(risk="50").risk_fraction_of(money("0")), Absent)


def test_a_trade_with_no_risk_figure_has_no_fraction() -> None:
    assert isinstance(stat(risk=None).risk_fraction_of(money("1000")), Absent)


def test_a_non_money_baseline_is_refused() -> None:
    with pytest.raises(TypeError, match="equity"):
        stat().risk_fraction_of(Decimal(1000))


# --------------------------------------------------------------------------
# the invariants a stat refuses to violate
# --------------------------------------------------------------------------


def test_a_trade_that_closed_without_opening_is_refused() -> None:
    with pytest.raises(StatisticsRefusedError, match="measured from nothing"):
        stat(opened_day=None, closed_day=1)


def test_a_trade_that_closed_before_it_opened_is_refused() -> None:
    with pytest.raises(StatisticsRefusedError, match="closed before it opened"):
        stat(opened_day=5, closed_day=1)


@pytest.mark.parametrize(
    "phase", [LifecyclePhase.CANCELLED, LifecyclePhase.EXPIRED]
)
def test_a_never_exposed_phase_may_not_record_an_opening(phase) -> None:
    with pytest.raises(StatisticsRefusedError, match="never held exposure"):
        stat(phase=phase, opened_day=0, closed_day=None)


def test_more_widenings_than_moves_is_refused() -> None:
    with pytest.raises(StatisticsRefusedError, match="not a separate count"):
        stat(stop_moves=1, stop_widenings=2)


def test_a_regime_map_of_the_wrong_shape_is_refused() -> None:
    with pytest.raises(TypeError, match="regime_states"):
        stat(regime_states=[("trend", "up")])


# --------------------------------------------------------------------------
# projections and provenance
# --------------------------------------------------------------------------


def test_a_stat_is_measured_and_asserts_nothing() -> None:
    assert stat().origin is ValueOrigin.MEASURED


def test_open_and_closed_and_exposure_are_derived_and_agree() -> None:
    running = stat(phase=LifecyclePhase.OPEN, closed_day=None)
    assert running.is_open and not running.is_closed and running.held_exposure
    finished = stat()
    assert finished.is_closed and not finished.is_open


def test_a_cancelled_trade_never_held_exposure() -> None:
    assert not stat(
        phase=LifecyclePhase.CANCELLED, opened_day=None, closed_day=None
    ).held_exposure


def test_the_payload_is_exportable_and_carries_every_absence_as_null() -> None:
    payload = stat(r_multiple=None, mfe=None, bars=None).to_payload()
    assert payload["r_multiple"] is None
    assert payload["max_favourable_r"] is None
    assert payload["bars_held"] is None
    assert payload["result"] == "win"
    assert payload["source"] == "simulated"


def test_the_payload_has_no_decoder_because_a_statistic_is_never_stored() -> None:
    """`AP` §25.2 classes these as `Aggregate` — recomputable, disposable. A
    `from_payload` here would be an invitation to persist one."""
    assert not hasattr(TradeStat, "from_payload")


def test_the_holding_time_matches_the_two_instants() -> None:
    assert stat(opened_day=0, closed_day=3).holding_time == timedelta(days=3)


# --------------------------------------------------------------------------
# the limitations register
# --------------------------------------------------------------------------


def test_every_limitation_has_a_unique_code_and_a_sentence() -> None:
    codes = [code for code, _ in STATISTICS_LIMITATIONS]
    assert len(codes) == len(set(codes))
    for code, text in STATISTICS_LIMITATIONS:
        assert code.startswith("ST-")
        assert len(text) > 40, code


def test_the_limitations_name_the_two_facts_a_reader_most_needs() -> None:
    """The sample floor is not sufficiency, and excursions are simulated-only.
    Both are the difference between a page that informs and one that flatters."""
    joined = " ".join(text for _, text in STATISTICS_LIMITATIONS)
    assert "establishes nothing" in joined
    assert "simulated trades" in joined
