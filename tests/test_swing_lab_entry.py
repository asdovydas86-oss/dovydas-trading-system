"""Entry rules, and the one thing that would invalidate all of them.

Every test below is ultimately about the same property: **no rule fills at a
price the market had not yet printed, at an instant before the decision existed.**
The control (`entry_immediate`) is pinned to `simulate_trade`'s own fill, the
confirmation rules are shown to consume a bar before acting, and the resting
limit is shown to use the paper engine's gap rule rather than a kinder one.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.entry import (
    PRE_DECLARED_ENTRY_POLICIES,
    PULLBACK_VALID_BARS,
    EntryFill,
    EntryMiss,
    EntryPolicy,
    EntryRule,
    MissReason,
    PathRole,
    entry_policy_by_id,
    resolve_entry,
)
from fmis.swing_lab.models import SwingLabError
from fmis.swing_setup.models import Direction

_UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=_UTC)
FOUR_HOURS = timedelta(hours=4)
REFERENCE = Decimal("100")

IMMEDIATE = entry_policy_by_id("entry_immediate")
CONTINUATION = entry_policy_by_id("entry_next_bar_continuation")
PULLBACK = entry_policy_by_id("entry_pullback_limit")
ONE_HOUR = entry_policy_by_id("entry_1h_confirmation")


def _bar(index: int, o: str, h: str, low: str, c: str, *, interval: str = "4h") -> PriceBar:
    step = FOUR_HOURS if interval == "4h" else timedelta(hours=1)
    return PriceBar(
        symbol="BTCUSDT", interval=interval, open_time=T0 + step * index,
        open=Decimal(o), high=Decimal(h), low=Decimal(low), close=Decimal(c),
    )


def _resolve(policy: EntryPolicy, path, *, direction=Direction.LONG, signal_index: int = 0):
    """The signal bar is ``path[signal_index]``; it CLOSES one interval later."""
    step = FOUR_HOURS if policy.path is PathRole.EXECUTION else timedelta(hours=1)
    return resolve_entry(
        policy,
        path=path,
        signal_at=path[signal_index].open_time,
        signal_close_at=path[signal_index].open_time + step,
        reference_price=REFERENCE,
        direction=direction,
    )


# ---------------------------------------------------------------- control ---


def test_immediate_fills_at_the_open_of_the_bar_after_the_signal() -> None:
    """Pinned to `simulate_trade`'s rule. Any drift here invalidates every comparison."""
    path = (
        _bar(0, "100", "101", "99", "100"),    # the signal bar
        _bar(1, "102", "103", "101", "102"),   # the entry bar
        _bar(2, "102", "104", "101", "103"),
    )
    fill = _resolve(IMMEDIATE, path)
    assert isinstance(fill, EntryFill)
    assert fill.index == 1
    assert fill.price == Decimal("102")
    assert fill.at == path[1].open_time
    assert fill.bars_waited == 0


def test_immediate_never_fills_on_the_signal_bar_itself() -> None:
    """Filling at the close you were looking at is a one-bar lookahead in costume."""
    path = (_bar(0, "100", "101", "99", "100"), _bar(1, "102", "103", "101", "102"))
    fill = _resolve(IMMEDIATE, path)
    assert fill.at > path[0].open_time


def test_a_rule_refuses_a_signal_that_closes_before_it_opens() -> None:
    path = (_bar(0, "100", "101", "99", "100"), _bar(1, "102", "103", "101", "102"))
    with pytest.raises(SwingLabError, match="must be after signal_at"):
        resolve_entry(
            IMMEDIATE, path=path, signal_at=T0, signal_close_at=T0,
            reference_price=REFERENCE, direction=Direction.LONG,
        )


# ----------------------------------------------------------- continuation ---


def test_continuation_waits_a_bar_and_then_fills_at_the_next_open() -> None:
    path = (
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "104", "99", "103"),    # closes beyond 100 → confirmed
        _bar(2, "103", "105", "102", "104"),   # the fill
    )
    fill = _resolve(CONTINUATION, path)
    assert isinstance(fill, EntryFill)
    assert fill.index == 2
    assert fill.price == Decimal("103")
    assert fill.bars_waited == 1


def test_continuation_declines_when_the_bar_closes_the_wrong_side() -> None:
    """A miss is a RESULT with a reason, never a silent absence."""
    path = (
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "104", "96", "98"),     # closed below the reference
        _bar(2, "98", "105", "97", "104"),
    )
    miss = _resolve(CONTINUATION, path)
    assert isinstance(miss, EntryMiss)
    assert miss.reason is MissReason.CONTINUATION_NOT_CONFIRMED
    assert "did not close beyond" in miss.statement


def test_continuation_requires_a_close_and_not_a_wick() -> None:
    """A wick through the reference is exactly the noise this rule declines."""
    path = (
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "99", "108", "98", "100"),     # touched 108, closed AT 100
        _bar(2, "100", "105", "99", "104"),
    )
    assert isinstance(_resolve(CONTINUATION, path), EntryMiss)


def test_continuation_reads_the_other_way_for_a_short() -> None:
    path = (
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "101", "95", "96"),     # closed BELOW → confirms a short
        _bar(2, "96", "97", "94", "95"),
    )
    fill = _resolve(CONTINUATION, path, direction=Direction.SHORT)
    assert isinstance(fill, EntryFill)
    assert fill.price == Decimal("96")


def test_continuation_confirmed_at_the_last_bar_has_nowhere_to_fill() -> None:
    """History running out is a fact about the dataset, not a refusal by the rule."""
    path = (_bar(0, "100", "101", "99", "100"), _bar(1, "100", "104", "99", "103"))
    miss = _resolve(CONTINUATION, path)
    assert miss.reason is MissReason.NO_BARS_AFTER_SIGNAL


# -------------------------------------------------------------- pullback ---


def test_the_pullback_limit_fills_at_its_own_price_when_touched() -> None:
    path = (
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "102", "103", "101", "102"),   # never came back
        _bar(2, "102", "103", "99", "101"),    # traded down through 100
    )
    fill = _resolve(PULLBACK, path)
    assert isinstance(fill, EntryFill)
    assert fill.index == 2
    assert fill.price == REFERENCE
    assert fill.gapped is False
    assert fill.bars_waited == 1


def test_the_pullback_limit_uses_the_paper_engine_gap_rule() -> None:
    """A bar opening past the limit fills at the OPEN — a better price, and a real one."""
    path = (
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "97", "98", "96", "97"),       # gapped below the limit
    )
    fill = _resolve(PULLBACK, path)
    assert fill.price == Decimal("97")
    assert fill.gapped is True


def test_the_pullback_limit_expires_and_says_so() -> None:
    path = (_bar(0, "100", "101", "99", "100"),) + tuple(
        _bar(index, "102", "103", "101", "102")
        for index in range(1, PULLBACK_VALID_BARS + 3)
    )
    miss = _resolve(PULLBACK, path)
    assert miss.reason is MissReason.LIMIT_NEVER_REACHED
    assert miss.bars_waited == PULLBACK_VALID_BARS


def test_the_pullback_limit_does_not_outlive_its_validity_window() -> None:
    """A retrace on the bar AFTER expiry must not fill. Off-by-one guard."""
    path = (_bar(0, "100", "101", "99", "100"),) + tuple(
        _bar(index, "102", "103", "101", "102")
        for index in range(1, PULLBACK_VALID_BARS + 1)
    ) + (_bar(PULLBACK_VALID_BARS + 1, "102", "103", "95", "99"),)
    assert isinstance(_resolve(PULLBACK, path), EntryMiss)


def test_the_pullback_limit_for_a_short_waits_for_price_to_rise() -> None:
    path = (
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "97", "98", "96", "97"),       # a long's fill, not a short's
        _bar(2, "97", "101", "96", "100"),     # traded back UP through 100
    )
    fill = _resolve(PULLBACK, path, direction=Direction.SHORT)
    assert fill.index == 2
    assert fill.price == REFERENCE


# ------------------------------------------------------------- refinement ---


def test_the_1h_rule_reads_1h_bars_and_waits_one_of_them() -> None:
    """A quarter of the delay of the 4H continuation, which is the point of the pair."""
    path = tuple(
        _bar(index, "100", "104", "99", "103", interval="1h") for index in range(4)
    )
    fill = resolve_entry(
        ONE_HOUR, path=path, signal_at=T0 - FOUR_HOURS, signal_close_at=T0,
        reference_price=REFERENCE, direction=Direction.LONG,
    )
    assert isinstance(fill, EntryFill)
    assert fill.interval == "1h"
    assert fill.index == 1
    assert fill.bars_waited == 1


def test_the_1h_rule_reports_an_absent_refinement_series_rather_than_estimating() -> None:
    """A missing series is NOT MEASURABLE. It is never approximated from 4H."""
    late = tuple(
        _bar(index, "100", "104", "99", "103", interval="1h")
        for index in range(100, 104)
    )
    miss = resolve_entry(
        ONE_HOUR, path=late, signal_at=T0 - FOUR_HOURS, signal_close_at=T0,
        reference_price=REFERENCE, direction=Direction.LONG,
    )
    assert miss.reason is MissReason.REFINEMENT_UNAVAILABLE


def test_an_empty_path_is_a_miss_and_not_a_crash() -> None:
    miss = resolve_entry(
        IMMEDIATE, path=(), signal_at=T0, signal_close_at=T0 + FOUR_HOURS,
        reference_price=REFERENCE, direction=Direction.LONG,
    )
    assert miss.reason is MissReason.NO_BARS_AFTER_SIGNAL


# ----------------------------------------------------------------- policy ---


def test_a_1h_rule_may_not_declare_the_execution_path() -> None:
    """Pairing a 1H fill with a 4H walk measures a stop against a bar it predates."""
    with pytest.raises(SwingLabError, match="did not exist for"):
        EntryPolicy(
            policy_id="broken", title="t", rule=EntryRule.ONE_HOUR_CONFIRMATION,
            path=PathRole.EXECUTION, hypothesis="h",
        )


def test_exactly_one_entry_policy_is_the_baseline_control() -> None:
    baselines = [item for item in PRE_DECLARED_ENTRY_POLICIES if item.is_baseline]
    assert len(baselines) == 1
    assert baselines[0].policy_id == "entry_immediate"


def test_the_family_carries_a_resolution_control_for_the_1h_rule() -> None:
    """Without it a 1H result cannot be attributed to the entry rather than the data."""
    ids = {item.policy_id for item in PRE_DECLARED_ENTRY_POLICIES}
    assert {"entry_immediate_1h", "entry_1h_confirmation"} <= ids
    control = entry_policy_by_id("entry_immediate_1h")
    assert control.rule is EntryRule.IMMEDIATE
    assert control.path is PathRole.REFINEMENT


def test_an_unknown_policy_id_names_the_alternatives() -> None:
    with pytest.raises(SwingLabError, match="no pre-declared entry policy"):
        entry_policy_by_id("entry_perfect_limit")


def test_validity_must_be_positive() -> None:
    with pytest.raises(SwingLabError, match="valid_bars must be positive"):
        EntryPolicy(
            policy_id="x", title="t", rule=EntryRule.PULLBACK_LIMIT_AT_REFERENCE,
            path=PathRole.EXECUTION, hypothesis="h", valid_bars=0,
        )


def test_resolve_refuses_a_non_policy() -> None:
    with pytest.raises(TypeError, match="must be an EntryPolicy"):
        resolve_entry(
            object(), path=(), signal_at=T0, signal_close_at=T0 + FOUR_HOURS,
            reference_price=REFERENCE, direction=Direction.LONG,
        )


def test_resolve_refuses_a_float_reference_price() -> None:
    with pytest.raises(SwingLabError, match="positive Decimal"):
        resolve_entry(
            IMMEDIATE, path=(), signal_at=T0, signal_close_at=T0 + FOUR_HOURS,
            reference_price=100.0, direction=Direction.LONG,
        )


def test_a_fill_refuses_a_negative_index() -> None:
    with pytest.raises(SwingLabError, match="must not be negative"):
        EntryFill(
            index=-1, price=Decimal("1"), at=T0, interval="4h",
            bars_waited=0, gapped=False,
        )
