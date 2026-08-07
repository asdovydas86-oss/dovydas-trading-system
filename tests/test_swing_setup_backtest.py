"""Milestone AV — Swing Setup Historical Backtest Harness v1.

Fully deterministic and network-free. No test derives its expected value by
calling a production helper on the same fixture the assertion checks — each
expectation is reasoned by hand from the fixture's own construction.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from fmis.data import Candle, CandleSeries
from fmis.level_crossing import LevelOrigin, LevelSide, PriceLevel
from fmis.market_structure import StructuralSwingLabel
from fmis.pipeline.market_analysis import InsufficientDataError
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.providers.binance import HttpResponse
from fmis.swing_setup.backtest_harness import (
    DEFAULT_EVALUATION_WINDOW_BARS,
    BACKTEST_LIMITATIONS,
    run_backtest,
)
from fmis.swing_setup.backtest_identity import IdentityTracker, setup_identity
from fmis.swing_setup.backtest_metrics import MIN_SAMPLE_FOR_RATE, compute_metrics
from fmis.swing_setup.backtest_models import (
    BacktestError,
    BacktestRun,
    DataBoundary,
    FamilyLean,
    HistoricalObservation,
    OutcomeStatus,
    SetupOutcome,
)
from fmis.swing_setup.backtest_outcomes import evaluate_outcome
from fmis.swing_setup.backtest_render import render_backtest_report
from fmis.swing_setup.backtest_replay import (
    DEFAULT_REPLAY_LIMIT,
    build_replay_transport,
    fetch_historical_dataset,
    fetch_raw_klines,
    from_epoch_ms,
    to_epoch_ms,
)
from fmis.swing_setup.models import Direction, SetupState, Trigger, TriggerKind

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


# =============================== shared fixtures ================================


def _origin(
    index: int,
    label: StructuralSwingLabel = StructuralSwingLabel.HIGHER_HIGH,
    *,
    confirmation_bars: int = 2,
) -> LevelOrigin:
    return LevelOrigin(
        index=index,
        timestamp=_BASE + timedelta(hours=4 * index),
        label=label,
        confirmation_bars=confirmation_bars,
    )


def _level(price: float, side: LevelSide, origin: LevelOrigin | None = None) -> PriceLevel:
    return PriceLevel(price=price, side=side, origin=origin)


def _trigger_confirmed(level: PriceLevel, bar_index: int) -> Trigger:
    return Trigger(
        kind=TriggerKind.CONFIRMED_STRUCTURE_BREAK,
        statement="confirmed",
        level=level,
        bar_index=bar_index,
    )


def _trigger_awaiting(level: PriceLevel | None = None) -> Trigger:
    return Trigger(kind=TriggerKind.AWAITING_STRUCTURE_BREAK, statement="awaiting", level=level)


_FOUR_HOURS_MS = 4 * 60 * 60 * 1000
_OPEN_TIME_INDEX = 0
_CLOSE_TIME_INDEX = 6


def raw_kline(open_ms: int, o: float, h: float, l: float, c: float, *, interval_ms: int = _FOUR_HOURS_MS) -> list:
    close_ms = open_ms + interval_ms - 1
    return [
        open_ms,
        f"{o:.8f}",
        f"{h:.8f}",
        f"{l:.8f}",
        f"{c:.8f}",
        "10.0",
        close_ms,
        "1000.0", 100, "500.0", "500.0", "0",
    ]


def zigzag_rows(
    count: int,
    *,
    start_ms: int = to_epoch_ms(_BASE),
    interval_ms: int = _FOUR_HOURS_MS,
    base: float = 100.0,
    leg: int = 6,
    step: float = 2.0,
    down_fraction: float = 2.0,
    macro_amplitude: float = 40.0,
    macro_period: int = 120,
    linear_drift_per_bar: float = 0.15,
) -> list[list]:
    """A deterministic, multi-scale price path with real swings at every scale.

    Three additive components, all closed-form functions of the bar index (no
    RNG, no state beyond ``i``):

    * a **net-zero** fast zigzag (``leg`` up bars of ``step``, half as many
      down bars of ``step * down_fraction`` — net-zero by default, since
      ``down_fraction=2.0`` with half as many bars cancels exactly) giving
      the finest role its own short-horizon structure;
    * a slow sine wave (``macro_amplitude`` over ``macro_period`` bars) that
      survives OHLC resampling into real, alternating higher-highs and
      higher-lows at every coarser timeframe;
    * a small linear drift, deliberately kept smaller than the sine
      amplitude, so the series trends overall without swamping the sine
      wave's alternation the way a large zigzag-only secular drift would.

    A fine-only zigzag with net secular drift resamples into an almost
    monotonic higher-timeframe series — no local peak within any small
    window, no detected swing, no structural level, decision context stays
    INSUFFICIENT forever — which is exactly the failure this construction
    avoids.
    """
    import math

    rows = []
    price = base
    direction = 1.0
    remaining_in_leg = leg
    for i in range(count):
        macro_now = macro_amplitude * math.sin(2 * math.pi * i / macro_period)
        macro_next = macro_amplitude * math.sin(2 * math.pi * (i + 1) / macro_period)
        micro_move = step if direction > 0 else -step * down_fraction
        move = micro_move + (macro_next - macro_now) + linear_drift_per_bar
        open_ = price
        close = open_ + move
        high = max(open_, close) + 0.1
        low = min(open_, close) - 0.1
        rows.append(raw_kline(start_ms + i * interval_ms, open_, high, low, close, interval_ms=interval_ms))
        price = close
        remaining_in_leg -= 1
        if remaining_in_leg <= 0:
            direction *= -1
            remaining_in_leg = leg if direction > 0 else max(2, leg // 2)
    return rows


def mirrored_rows(rows: list[list], *, pivot: float | None = None) -> list[list]:
    """Reflect a raw kline series' prices around ``pivot`` — an uptrend becomes a downtrend.

    ``pivot`` defaults to the series' own maximum high, which guarantees every
    reflected price stays strictly positive (the reflection of the maximum is
    the smallest value the mapping can produce, and it lands at exactly 0 only
    in the degenerate single-price case — headroom below is added on top).
    Timestamps, volume and every non-price field are untouched; only OHLC are
    reflected, and high/low are swapped back into (higher, lower) order.
    """
    if pivot is None:
        pivot = max(float(row[2]) for row in rows) * 1.05
    mirrored = []
    for row in rows:
        o, h, l, c = (2 * pivot - float(row[1]), 2 * pivot - float(row[3]), 2 * pivot - float(row[2]), 2 * pivot - float(row[4]))
        new_row = list(row)
        new_row[1] = f"{o:.8f}"
        new_row[2] = f"{h:.8f}"
        new_row[3] = f"{l:.8f}"
        new_row[4] = f"{c:.8f}"
        mirrored.append(new_row)
    return mirrored


def resampled_rows(fine_rows: list[list], *, bars_per_period: int) -> list[list]:
    """Standard OHLC resampling: open=first, high=max, low=min, close=last.

    Builds a coarser role's series from the *same* underlying price path a
    finer role already used, so the three roles this fixture feeds into the
    harness are genuinely correlated — the same discipline real markets show
    across timeframes of one instrument, unlike three independently-phased
    zigzags that happen to share nothing but a name.
    """
    rows = []
    for start in range(0, len(fine_rows) - bars_per_period + 1, bars_per_period):
        group = fine_rows[start : start + bars_per_period]
        open_ = float(group[0][1])
        close = float(group[-1][4])
        high = max(float(r[2]) for r in group)
        low = min(float(r[3]) for r in group)
        open_ms = group[0][_OPEN_TIME_INDEX]
        close_ms = group[-1][_CLOSE_TIME_INDEX]
        rows.append(
            [
                open_ms, f"{open_:.8f}", f"{high:.8f}", f"{low:.8f}", f"{close:.8f}",
                "10.0", close_ms, "1000.0", 100, "500.0", "500.0", "0",
            ]
        )
    return rows


def fake_transport_for(cache: dict[tuple[str, str], list[list]]):
    """A `Transport` standing in for the real Binance endpoint over a fixed cache.

    Used only for `run_backtest`'s **historical fetch** phase
    (`fetch_historical_dataset`/`fetch_raw_klines`), which pages with real
    ``startTime``/``endTime``/``limit`` query parameters — `run_backtest`
    itself builds a *different*, no-lookahead replay transport internally
    for the actual per-instant composition calls. This fake must honour
    those three parameters the same way the real endpoint does; a fake that
    ignores them and always returns the full series makes the harness's own
    pagination loop fetch (and duplicate) the same rows forever.
    """
    import urllib.parse

    def _transport(url: str) -> HttpResponse:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        symbol = query.get("symbol", [""])[0]
        interval = query.get("interval", [""])[0]
        rows = cache.get((symbol, interval), [])
        start_ms = int(query["startTime"][0]) if "startTime" in query else None
        end_ms = int(query["endTime"][0]) if "endTime" in query else None
        limit = int(query["limit"][0]) if "limit" in query else DEFAULT_REPLAY_LIMIT
        filtered = [
            row for row in rows
            if (start_ms is None or row[_OPEN_TIME_INDEX] >= start_ms)
            and (end_ms is None or row[_CLOSE_TIME_INDEX] <= end_ms)
        ]
        return HttpResponse(status=200, body=json.dumps(filtered[:limit]).encode())

    return _transport


def _decode_series(symbol: str, interval: str, rows: list[list]) -> CandleSeries:
    from fmis.ingest import decode_candle_series
    from fmis.providers.binance import map_kline

    now_ms = to_epoch_ms(datetime(2100, 1, 1, tzinfo=timezone.utc))
    records = [
        map_kline(raw, symbol=symbol, interval=interval, now_ms=now_ms, index=i)
        for i, raw in enumerate(rows)
    ]
    return decode_candle_series(records, symbol=symbol, timeframe=interval).closed()


# =============================== backtest_identity ===============================


class TestSetupIdentity:
    def test_none_direction_has_no_identity(self) -> None:
        assert setup_identity("BTCUSDT", None, None) is None

    def test_deterministic_for_equal_inputs(self) -> None:
        level = _level(105.0, LevelSide.UPPER, _origin(4))
        trigger = _trigger_confirmed(level, 10)
        a = setup_identity("BTCUSDT", Direction.LONG, trigger)
        b = setup_identity("BTCUSDT", Direction.LONG, trigger)
        assert a == b

    def test_different_origin_is_a_different_identity(self) -> None:
        level_a = _level(105.0, LevelSide.UPPER, _origin(4))
        level_b = _level(105.0, LevelSide.UPPER, _origin(9))
        id_a = setup_identity("BTCUSDT", Direction.LONG, _trigger_confirmed(level_a, 10))
        id_b = setup_identity("BTCUSDT", Direction.LONG, _trigger_confirmed(level_b, 12))
        assert id_a != id_b

    def test_direction_flip_is_a_different_identity_even_at_the_same_level(self) -> None:
        # A LONG stop/UPPER level vs a SHORT confirming UPPER level: contrived,
        # but the point is only that direction participates in the key.
        level = _level(105.0, LevelSide.UPPER, _origin(4))
        id_long = setup_identity("BTCUSDT", Direction.LONG, _trigger_confirmed(level, 10))
        id_short = setup_identity("BTCUSDT", Direction.SHORT, _trigger_confirmed(level, 10))
        assert id_long != id_short

    def test_symbol_participates_in_identity(self) -> None:
        level = _level(105.0, LevelSide.UPPER, _origin(4))
        trigger = _trigger_confirmed(level, 10)
        assert setup_identity("BTCUSDT", Direction.LONG, trigger) != setup_identity(
            "ETHUSDT", Direction.LONG, trigger
        )

    def test_falls_back_to_price_when_no_origin(self) -> None:
        level = _level(105.0, LevelSide.UPPER, origin=None)
        trigger = _trigger_confirmed(level, 10)
        result = setup_identity("BTCUSDT", Direction.LONG, trigger)
        assert "price=105.0" in result

    def test_falls_back_to_no_level_marker(self) -> None:
        trigger = _trigger_awaiting(level=None)
        result = setup_identity("BTCUSDT", Direction.LONG, trigger)
        assert result == "BTCUSDT|long|no-level"

    def test_none_trigger_also_falls_back(self) -> None:
        assert setup_identity("BTCUSDT", Direction.LONG, None) == "BTCUSDT|long|no-level"


class TestIdentityTracker:
    def test_first_directional_observation_is_new(self) -> None:
        tracker = IdentityTracker()
        level = _level(105.0, LevelSide.UPPER, _origin(4))
        trigger = _trigger_awaiting(level)
        setup_id, is_new, is_first_confirmation = tracker.observe(
            "BTCUSDT", Direction.LONG, trigger, SetupState.CANDIDATE
        )
        assert setup_id is not None
        assert is_new is True
        assert is_first_confirmation is False

    def test_repeated_bar_same_level_is_not_new(self) -> None:
        tracker = IdentityTracker()
        level = _level(105.0, LevelSide.UPPER, _origin(4))
        trigger = _trigger_awaiting(level)
        tracker.observe("BTCUSDT", Direction.LONG, trigger, SetupState.CANDIDATE)
        _, is_new, _ = tracker.observe("BTCUSDT", Direction.LONG, trigger, SetupState.CANDIDATE)
        assert is_new is False

    def test_confirmation_is_flagged_exactly_once_across_repeated_confirmed_bars(self) -> None:
        tracker = IdentityTracker()
        level = _level(105.0, LevelSide.UPPER, _origin(4))
        watch_trigger = _trigger_awaiting(level)
        confirmed_trigger = _trigger_confirmed(level, 10)
        tracker.observe("BTCUSDT", Direction.LONG, watch_trigger, SetupState.CANDIDATE)
        _, _, first = tracker.observe(
            "BTCUSDT", Direction.LONG, confirmed_trigger, SetupState.CONFIRMED
        )
        _, _, second = tracker.observe(
            "BTCUSDT", Direction.LONG, confirmed_trigger, SetupState.CONFIRMED
        )
        _, _, third = tracker.observe(
            "BTCUSDT", Direction.LONG, confirmed_trigger, SetupState.CONFIRMED
        )
        assert (first, second, third) == (True, False, False)

    def test_wait_resets_identity_so_a_later_return_is_a_new_occurrence(self) -> None:
        tracker = IdentityTracker()
        level = _level(105.0, LevelSide.UPPER, _origin(4))
        trigger = _trigger_awaiting(level)
        id_first, _, _ = tracker.observe("BTCUSDT", Direction.LONG, trigger, SetupState.CANDIDATE)
        tracker.observe("BTCUSDT", None, None, SetupState.WAIT)
        id_second, is_new_second, _ = tracker.observe(
            "BTCUSDT", Direction.LONG, trigger, SetupState.CANDIDATE
        )
        assert id_first == id_second  # identity text is the same level
        assert is_new_second is True  # but it is a new occurrence

    def test_symbols_are_isolated(self) -> None:
        tracker = IdentityTracker()
        level = _level(105.0, LevelSide.UPPER, _origin(4))
        trigger = _trigger_awaiting(level)
        tracker.observe("BTCUSDT", Direction.LONG, trigger, SetupState.CANDIDATE)
        _, is_new, _ = tracker.observe("ETHUSDT", Direction.LONG, trigger, SetupState.CANDIDATE)
        assert is_new is True

    def test_wait_observation_returns_no_identity(self) -> None:
        tracker = IdentityTracker()
        setup_id, is_new, is_first_confirmation = tracker.observe(
            "BTCUSDT", None, None, SetupState.WAIT
        )
        assert (setup_id, is_new, is_first_confirmation) == (None, False, False)


# =============================== backtest_outcomes ================================


def _series(candles: list[Candle], symbol: str = "BTCUSDT", interval: str = "4h") -> CandleSeries:
    return CandleSeries(symbol=symbol, timeframe=interval, candles=tuple(candles))


def _candle(i: int, *, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(
        timestamp=_BASE + timedelta(hours=4 * i),
        symbol="BTCUSDT",
        timeframe="4h",
        open=o,
        high=h,
        low=l,
        close=c,
        volume=1.0,
        is_closed=True,
    )


class TestEvaluateOutcome:
    def _run(self, candles: list[Candle], *, direction: Direction, stop: float, target: float, window: int = 10) -> SetupOutcome:
        series = _series(candles)
        return evaluate_outcome(
            series,
            setup_id="s1",
            symbol="BTCUSDT",
            direction=direction,
            confirmed_at=candles[0].timestamp,
            reference_price=candles[0].close,
            stop_price=stop,
            target_price=target,
            risk_reward_ratio=2.0,
            window_bars=window,
        )

    def test_target_first_long(self) -> None:
        confirming = _candle(0, o=100, h=100, l=100, c=100)
        after = _candle(1, o=100, h=110, l=99, c=105)  # touches target 108, not stop 95
        outcome = self._run([confirming, after], direction=Direction.LONG, stop=95.0, target=108.0)
        assert outcome.status is OutcomeStatus.TARGET_FIRST
        assert outcome.bars_to_resolution == 1

    def test_stop_first_long(self) -> None:
        confirming = _candle(0, o=100, h=100, l=100, c=100)
        after = _candle(1, o=100, h=101, l=90, c=95)
        outcome = self._run([confirming, after], direction=Direction.LONG, stop=95.0, target=120.0)
        assert outcome.status is OutcomeStatus.STOP_FIRST

    def test_ambiguous_same_bar_long(self) -> None:
        confirming = _candle(0, o=100, h=100, l=100, c=100)
        after = _candle(1, o=100, h=120, l=80, c=100)  # crosses both 95 and 108
        outcome = self._run([confirming, after], direction=Direction.LONG, stop=95.0, target=108.0)
        assert outcome.status is OutcomeStatus.AMBIGUOUS_SAME_BAR

    def test_neither_within_window(self) -> None:
        confirming = _candle(0, o=100, h=100, l=100, c=100)
        after = _candle(1, o=100, h=101, l=99, c=100)
        outcome = self._run(
            [confirming, after], direction=Direction.LONG, stop=50.0, target=200.0, window=1
        )
        assert outcome.status is OutcomeStatus.NEITHER_WITHIN_WINDOW
        assert outcome.resolved_at is None
        assert outcome.bars_to_resolution is None

    def test_data_running_out_before_window_ends_is_neither(self) -> None:
        confirming = _candle(0, o=100, h=100, l=100, c=100)
        outcome = self._run([confirming], direction=Direction.LONG, stop=50.0, target=200.0, window=10)
        assert outcome.status is OutcomeStatus.NEITHER_WITHIN_WINDOW

    def test_exact_boundary_touch_counts_as_a_hit(self) -> None:
        confirming = _candle(0, o=100, h=100, l=100, c=100)
        after = _candle(1, o=100, h=108.0, l=99, c=101)  # high exactly equals target
        outcome = self._run([confirming, after], direction=Direction.LONG, stop=95.0, target=108.0)
        assert outcome.status is OutcomeStatus.TARGET_FIRST

    def test_confirming_bar_itself_is_never_checked(self) -> None:
        # The confirming bar's own high/low would hit both if it were checked;
        # it must be skipped, so the outcome comes from the *next* bar only.
        confirming = _candle(0, o=100, h=120, l=80, c=100)
        after = _candle(1, o=100, h=108.0, l=99, c=101)
        outcome = self._run([confirming, after], direction=Direction.LONG, stop=95.0, target=108.0)
        assert outcome.status is OutcomeStatus.TARGET_FIRST
        assert outcome.bars_to_resolution == 1

    def test_long_short_symmetry(self) -> None:
        confirming = _candle(0, o=100, h=100, l=100, c=100)
        long_after = _candle(1, o=100, h=110, l=99, c=105)
        outcome_long = self._run(
            [confirming, long_after], direction=Direction.LONG, stop=95.0, target=108.0
        )
        short_after = _candle(1, o=100, h=101, l=90, c=95)
        outcome_short = self._run(
            [confirming, short_after], direction=Direction.SHORT, stop=105.0, target=92.0
        )
        assert outcome_long.status is OutcomeStatus.TARGET_FIRST
        assert outcome_short.status is OutcomeStatus.TARGET_FIRST

    def test_unknown_confirmed_at_raises(self) -> None:
        confirming = _candle(0, o=100, h=100, l=100, c=100)
        series = _series([confirming])
        with pytest.raises(BacktestError):
            evaluate_outcome(
                series,
                setup_id="s1",
                symbol="BTCUSDT",
                direction=Direction.LONG,
                confirmed_at=_BASE + timedelta(days=999),
                reference_price=100.0,
                stop_price=95.0,
                target_price=108.0,
                risk_reward_ratio=2.0,
                window_bars=5,
            )

    def test_window_bars_must_be_positive(self) -> None:
        confirming = _candle(0, o=100, h=100, l=100, c=100)
        series = _series([confirming])
        with pytest.raises(BacktestError):
            evaluate_outcome(
                series,
                setup_id="s1",
                symbol="BTCUSDT",
                direction=Direction.LONG,
                confirmed_at=confirming.timestamp,
                reference_price=100.0,
                stop_price=95.0,
                target_price=108.0,
                risk_reward_ratio=2.0,
                window_bars=0,
            )


# =============================== backtest_replay =================================


class TestReplayNoLookahead:
    def test_a_candle_closing_after_now_is_never_served(self) -> None:
        rows = zigzag_rows(20)
        cache = {("BTCUSDT", "4h"): rows}
        # `now` set to exactly the close time of row index 9 (inclusive boundary
        # excluded, matching `close_time < now` everywhere in production).
        boundary_close_ms = rows[9][_CLOSE_TIME_INDEX]
        now = from_epoch_ms(boundary_close_ms)  # NOT +1: still forming at this instant
        transport = build_replay_transport(cache, now=now)
        response = transport("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=4h&limit=100")
        served = json.loads(response.body)
        assert len(served) == 9  # rows 0..8 strictly closed before `now`
        assert all(row[_CLOSE_TIME_INDEX] < boundary_close_ms for row in served)

    def test_one_millisecond_later_the_boundary_candle_appears(self) -> None:
        rows = zigzag_rows(20)
        cache = {("BTCUSDT", "4h"): rows}
        boundary_close_ms = rows[9][_CLOSE_TIME_INDEX]
        now = from_epoch_ms(boundary_close_ms + 1)
        transport = build_replay_transport(cache, now=now)
        response = transport("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=4h&limit=100")
        served = json.loads(response.body)
        assert len(served) == 10

    def test_limit_is_respected_and_takes_the_most_recent(self) -> None:
        rows = zigzag_rows(50)
        cache = {("BTCUSDT", "4h"): rows}
        now = from_epoch_ms(rows[-1][_CLOSE_TIME_INDEX] + 1)
        transport = build_replay_transport(cache, now=now)
        response = transport("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=4h&limit=5")
        served = json.loads(response.body)
        assert len(served) == 5
        assert served[-1][_OPEN_TIME_INDEX] == rows[-1][_OPEN_TIME_INDEX]

    def test_default_limit_matches_binance_default_when_omitted(self) -> None:
        rows = zigzag_rows(3)
        cache = {("BTCUSDT", "4h"): rows}
        now = from_epoch_ms(rows[-1][_CLOSE_TIME_INDEX] + 1)
        transport = build_replay_transport(cache, now=now)
        response = transport("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=4h")
        served = json.loads(response.body)
        assert len(served) == 3  # fewer available than DEFAULT_REPLAY_LIMIT

    def test_unknown_series_answers_with_a_binance_shaped_error(self) -> None:
        transport = build_replay_transport({}, now=_BASE)
        response = transport("https://api.binance.com/api/v3/klines?symbol=NOPE&interval=4h")
        assert response.status == 400
        payload = json.loads(response.body)
        assert payload["code"] == -1121

    def test_now_must_be_timezone_aware(self) -> None:
        with pytest.raises(BacktestError):
            build_replay_transport({}, now=datetime(2024, 1, 1))


class TestFetchRawKlines:
    def test_pages_across_multiple_batches(self) -> None:
        full = zigzag_rows(2500)  # forces >1 page at MAX_LIMIT=1000

        def paged_transport(url: str) -> HttpResponse:
            import urllib.parse

            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            start_ms = int(query["startTime"][0])
            end_ms = int(query["endTime"][0])
            limit = int(query["limit"][0])
            batch = [
                row for row in full
                if start_ms <= row[_OPEN_TIME_INDEX] and row[_CLOSE_TIME_INDEX] <= end_ms
            ][:limit]
            return HttpResponse(status=200, body=json.dumps(batch).encode())

        fetched = fetch_raw_klines(
            "BTCUSDT", "4h",
            start_time=from_epoch_ms(full[0][_OPEN_TIME_INDEX]),
            end_time=from_epoch_ms(full[-1][_CLOSE_TIME_INDEX]),
            transport=paged_transport,
        )
        assert len(fetched) == 2500
        assert fetched[0][_OPEN_TIME_INDEX] == full[0][_OPEN_TIME_INDEX]
        assert fetched[-1][_OPEN_TIME_INDEX] == full[-1][_OPEN_TIME_INDEX]

    def test_provider_error_payload_raises(self) -> None:
        def erroring(url: str) -> HttpResponse:
            return HttpResponse(status=400, body=json.dumps({"code": -1121, "msg": "bad"}).encode())

        with pytest.raises(BacktestError):
            fetch_raw_klines(
                "NOPE", "4h", start_time=_BASE, end_time=_BASE + timedelta(days=1), transport=erroring
            )

    def test_empty_range_returns_no_rows(self) -> None:
        def empty_transport(url: str) -> HttpResponse:
            return HttpResponse(status=200, body=b"[]")

        fetched = fetch_raw_klines(
            "BTCUSDT", "4h", start_time=_BASE, end_time=_BASE + timedelta(days=1),
            transport=empty_transport,
        )
        assert fetched == []

    def test_start_after_end_rejected(self) -> None:
        with pytest.raises(BacktestError):
            fetch_raw_klines(
                "BTCUSDT", "4h",
                start_time=_BASE + timedelta(days=1), end_time=_BASE,
            )


class TestFetchHistoricalDataset:
    def test_records_exact_boundaries(self) -> None:
        rows = zigzag_rows(30)
        cache_source = fake_transport_for({("BTCUSDT", "4h"): rows})
        cache, boundaries = fetch_historical_dataset(
            ["BTCUSDT"], ["4h"],
            start_time=from_epoch_ms(rows[0][_OPEN_TIME_INDEX]),
            end_time=from_epoch_ms(rows[-1][_CLOSE_TIME_INDEX]),
            fetched_at=_BASE,
            transport=cache_source,
        )
        assert len(boundaries) == 1
        boundary = boundaries[0]
        assert boundary.candle_count == 30
        assert boundary.first_candle == from_epoch_ms(rows[0][_OPEN_TIME_INDEX])
        assert boundary.last_candle == from_epoch_ms(rows[-1][_OPEN_TIME_INDEX])
        assert boundary.fetched_at == _BASE


# =============================== backtest_models ==================================


class TestBacktestModels:
    def test_data_boundary_requires_both_or_neither_candle(self) -> None:
        with pytest.raises(BacktestError):
            DataBoundary(
                symbol="BTCUSDT", interval="4h", source="binance-spot",
                first_candle=_BASE, last_candle=None, candle_count=0, fetched_at=_BASE,
            )

    def test_historical_observation_direction_matches_state(self) -> None:
        with pytest.raises(BacktestError):
            HistoricalObservation(
                symbol="BTCUSDT", as_of=_BASE, status=SetupState.WAIT,
                direction=Direction.LONG, setup_id=None, is_new_setup=False,
                directional_factors=(), thesis=(), confirmation=(),
                trigger_kind=None, trigger_price=None, reference_price=None,
                stop_price=None, target_price=None, risk_reward_ratio=None,
                sufficiency="sufficient", context_regime_structure="trending",
                context_regime_volatility="steady", context_regime_participation="typical",
                execution_last_timestamp=None, policy_id="swing-setup-v1",
            )

    def test_setup_outcome_resolved_fields_are_all_or_nothing(self) -> None:
        with pytest.raises(BacktestError):
            SetupOutcome(
                setup_id="s1", symbol="BTCUSDT", direction=Direction.LONG,
                confirmed_at=_BASE, reference_price=100.0, stop_price=95.0,
                target_price=110.0, risk_reward_ratio=2.0, evaluation_window_bars=10,
                status=OutcomeStatus.TARGET_FIRST, resolved_at=None, bars_to_resolution=None,
            )

    def test_setup_outcome_neither_has_no_resolution(self) -> None:
        outcome = SetupOutcome(
            setup_id="s1", symbol="BTCUSDT", direction=Direction.LONG,
            confirmed_at=_BASE, reference_price=100.0, stop_price=95.0,
            target_price=110.0, risk_reward_ratio=2.0, evaluation_window_bars=10,
            status=OutcomeStatus.NEITHER_WITHIN_WINDOW, resolved_at=None, bars_to_resolution=None,
        )
        assert outcome.resolved_at is None


# =============================== backtest_metrics =================================


def _obs(
    symbol: str = "BTCUSDT",
    *,
    status: SetupState = SetupState.WAIT,
    direction: Direction | None = None,
    setup_id: str | None = None,
    is_new_setup: bool = False,
    factors: tuple[FamilyLean, ...] = (),
    thesis: tuple[str, ...] = (),
    stop_price: float | None = None,
    target_price: float | None = None,
    reference_price: float | None = None,
    risk_reward_ratio: float | None = None,
    structure: str = "trending",
    exec_ts: datetime | None = None,
    as_of: datetime = _BASE,
) -> HistoricalObservation:
    return HistoricalObservation(
        symbol=symbol, as_of=as_of, status=status, direction=direction,
        setup_id=setup_id, is_new_setup=is_new_setup, directional_factors=factors,
        thesis=thesis, confirmation=(), trigger_kind=None, trigger_price=None,
        reference_price=reference_price, stop_price=stop_price, target_price=target_price,
        risk_reward_ratio=risk_reward_ratio, sufficiency="sufficient",
        context_regime_structure=structure, context_regime_volatility="steady",
        context_regime_participation="typical", execution_last_timestamp=exec_ts,
        policy_id="swing-setup-v1",
    )


def _outcome(
    symbol: str = "BTCUSDT",
    *,
    direction: Direction = Direction.LONG,
    status: OutcomeStatus = OutcomeStatus.TARGET_FIRST,
    confirmed_at: datetime = _BASE,
    rr: float = 2.0,
) -> SetupOutcome:
    resolved = status is not OutcomeStatus.NEITHER_WITHIN_WINDOW
    return SetupOutcome(
        setup_id="s1", symbol=symbol, direction=direction, confirmed_at=confirmed_at,
        reference_price=100.0, stop_price=95.0, target_price=110.0, risk_reward_ratio=rr,
        evaluation_window_bars=10, status=status,
        resolved_at=confirmed_at + timedelta(hours=4) if resolved else None,
        bars_to_resolution=1 if resolved else None,
    )


def _run(observations, outcomes) -> BacktestRun:
    return BacktestRun(
        schema_version=1, created_at=_BASE, symbols=("BTCUSDT", "ETHUSDT"),
        timeframes={"context": "1w", "setup": "1d", "execution": "4h"},
        evaluation_window_bars=10,
        data_boundaries=(),
        policy_id="swing-setup-v1", context_policy_id="context-v1",
        observations=tuple(observations), outcomes=tuple(outcomes),
        limitations=BACKTEST_LIMITATIONS,
    )


class TestComputeMetrics:
    def test_counts_reconcile_exactly(self) -> None:
        observations = [
            _obs(status=SetupState.WAIT),
            _obs(status=SetupState.CANDIDATE, direction=Direction.LONG, setup_id="a", is_new_setup=True),
            _obs(status=SetupState.CONFIRMED, direction=Direction.LONG, setup_id="a", is_new_setup=False),
        ]
        outcomes = [_outcome(status=OutcomeStatus.TARGET_FIRST)]
        metrics = compute_metrics(_run(observations, outcomes))
        assert metrics.total_observations == 3
        assert metrics.wait_count == 1
        assert metrics.candidate_count == 1
        assert metrics.confirmed_count == 1
        assert metrics.unique_setups == 1
        assert metrics.unique_confirmed_setups == 1
        assert metrics.evaluated_outcomes == 1
        assert metrics.confirmed_without_geometry == 0

    def test_repeated_confirmed_bars_count_as_one_unique_setup(self) -> None:
        observations = [
            _obs(status=SetupState.CANDIDATE, direction=Direction.LONG, setup_id="a", is_new_setup=True),
            _obs(status=SetupState.CONFIRMED, direction=Direction.LONG, setup_id="a", is_new_setup=False),
            _obs(status=SetupState.CONFIRMED, direction=Direction.LONG, setup_id="a", is_new_setup=False),
            _obs(status=SetupState.CONFIRMED, direction=Direction.LONG, setup_id="a", is_new_setup=False),
        ]
        metrics = compute_metrics(_run(observations, []))
        assert metrics.unique_setups == 1
        assert metrics.unique_confirmed_setups == 1
        assert metrics.confirmed_count == 3  # raw bar count is NOT deduplicated

    def test_confirmed_without_geometry_reconciles(self) -> None:
        observations = [
            _obs(status=SetupState.CONFIRMED, direction=Direction.LONG, setup_id="a", is_new_setup=True),
            _obs(status=SetupState.CONFIRMED, direction=Direction.SHORT, setup_id="b", is_new_setup=True),
        ]
        outcomes = [_outcome(status=OutcomeStatus.TARGET_FIRST)]  # only one evaluated
        metrics = compute_metrics(_run(observations, outcomes))
        assert metrics.unique_confirmed_setups == 2
        assert metrics.evaluated_outcomes == 1
        assert metrics.confirmed_without_geometry == 1

    def test_target_first_rate_excludes_ambiguous_and_unresolved(self) -> None:
        outcomes = (
            [_outcome(status=OutcomeStatus.TARGET_FIRST)] * 6
            + [_outcome(status=OutcomeStatus.STOP_FIRST)] * 4
            + [_outcome(status=OutcomeStatus.AMBIGUOUS_SAME_BAR)] * 5
            + [_outcome(status=OutcomeStatus.NEITHER_WITHIN_WINDOW)] * 5
        )
        metrics = compute_metrics(_run([], outcomes))
        assert metrics.target_first_rate == pytest.approx(0.6)
        assert metrics.stop_first_rate == pytest.approx(0.4)

    def test_risk_reward_mean_and_median_are_computed_correctly(self) -> None:
        outcomes = [
            _outcome(status=OutcomeStatus.TARGET_FIRST, rr=1.0),
            _outcome(status=OutcomeStatus.STOP_FIRST, rr=2.0),
            _outcome(status=OutcomeStatus.TARGET_FIRST, rr=3.0),
        ]
        metrics = compute_metrics(_run([], outcomes))
        assert metrics.risk_reward_mean == pytest.approx(2.0)  # (1+2+3)/3
        assert metrics.risk_reward_median == pytest.approx(2.0)

    def test_insufficient_sample_reports_none(self) -> None:
        outcomes = [_outcome(status=OutcomeStatus.TARGET_FIRST)] * (MIN_SAMPLE_FOR_RATE - 1)
        metrics = compute_metrics(_run([], outcomes))
        assert metrics.target_first_rate is None

    def test_by_symbol_and_by_side_split_correctly(self) -> None:
        outcomes = [
            _outcome(symbol="BTCUSDT", direction=Direction.LONG, status=OutcomeStatus.TARGET_FIRST),
            _outcome(symbol="ETHUSDT", direction=Direction.SHORT, status=OutcomeStatus.STOP_FIRST),
        ]
        metrics = compute_metrics(_run([], outcomes))
        by_symbol = {c.label: c for c in metrics.by_symbol}
        assert by_symbol["BTCUSDT"].total == 1
        assert by_symbol["ETHUSDT"].total == 1
        by_side = {c.label: c for c in metrics.by_side}
        assert by_side["long"].target_first == 1
        assert by_side["short"].stop_first == 1

    def test_pair_agreement_counts_only_directional_leans(self) -> None:
        factors = (
            FamilyLean(family="a", lean="long"),
            FamilyLean(family="b", lean="long"),
            FamilyLean(family="c", lean="unavailable"),
        )
        observations = [_obs(factors=factors, direction=None)]
        metrics = compute_metrics(_run(observations, []))
        pair_ab = next(p for p in metrics.pair_agreement if {p.family_a, p.family_b} == {"a", "b"})
        assert pair_ab.both_directional == 1
        assert pair_ab.agree == 1
        pair_ac = next(p for p in metrics.pair_agreement if {p.family_a, p.family_b} == {"a", "c"})
        assert pair_ac.both_directional == 0

    def test_blocked_only_by_regime_matches_the_recorded_thesis(self) -> None:
        marker = (
            "Context-role (1w) regime structure is ranging, not trending. A "
            "directional swing thesis requires a trending higher-timeframe "
            "environment; this package does not infer a direction from a "
            "regime, which classifies environment only.",
        )
        observations = [
            _obs(status=SetupState.WAIT, thesis=marker),
            _obs(status=SetupState.WAIT, thesis=("Decision context is INSUFFICIENT: x.",)),
        ]
        metrics = compute_metrics(_run(observations, []))
        assert metrics.blocked_only_by_regime == 1

    def test_regime_change_rate_over_two_symbols(self) -> None:
        observations = [
            _obs(symbol="BTCUSDT", structure="trending", as_of=_BASE),
            _obs(symbol="BTCUSDT", structure="ranging", as_of=_BASE + timedelta(hours=4)),
            _obs(symbol="ETHUSDT", structure="trending", as_of=_BASE),
            _obs(symbol="ETHUSDT", structure="trending", as_of=_BASE + timedelta(hours=4)),
        ]
        metrics = compute_metrics(_run(observations, []))
        assert metrics.regime_change_rate == pytest.approx(0.5)

    def test_empty_run_produces_zeroed_metrics_not_an_error(self) -> None:
        metrics = compute_metrics(_run([], []))
        assert metrics.total_observations == 0
        assert metrics.target_first_rate is None
        assert metrics.risk_reward_mean is None


class TestRenderBacktestReport:
    def test_renders_within_page_width_and_prints_limitations(self) -> None:
        observations = [_obs(status=SetupState.WAIT)]
        report = render_backtest_report(_run(observations, []), compute_metrics(_run(observations, [])))
        for line in report.splitlines():
            assert len(line) <= 78
        assert "LIMITATIONS" in report
        for limitation in BACKTEST_LIMITATIONS:
            assert limitation.split(":")[0] in report

    def test_renders_within_page_width_for_the_full_default_symbol_set(self) -> None:
        # Regression: a real 10-symbol run overflowed the SYMBOLS/TIMEFRAME
        # ROLES header lines, caught only by the live Binance demonstration —
        # every unit fixture up to this point used at most two short symbols.
        from fmis.swing_setup.backtest_harness import DEFAULT_BACKTEST_SYMBOLS

        run = BacktestRun(
            schema_version=1, created_at=_BASE, symbols=DEFAULT_BACKTEST_SYMBOLS,
            timeframes={"context": "1w", "setup": "1d", "execution": "4h"},
            evaluation_window_bars=60, data_boundaries=(),
            policy_id="swing-setup-v1", context_policy_id="context-v1",
            observations=(), outcomes=(), limitations=BACKTEST_LIMITATIONS,
        )
        report = render_backtest_report(run, compute_metrics(run))
        for line in report.splitlines():
            assert len(line) <= 78
        for symbol in DEFAULT_BACKTEST_SYMBOLS:
            assert symbol in report


# =============================== backtest_harness (integration) ===================


def _build_cache(symbol: str, rows_by_interval: dict[str, list[list]]) -> dict[tuple[str, str], list[list]]:
    return {(symbol, interval): rows for interval, rows in rows_by_interval.items()}


def _three_role_rows(symbol: str, *, count_4h: int = 400, base_price: float = 100.0, mirror: bool = False):
    """Three genuinely correlated role series, all resampled from one fine 4h path.

    The 1d and 1w series are standard OHLC resamples of the *same* 4h master
    path (6 and 42 four-hour bars per period), not independently phased
    zigzags — real timeframes of one instrument agree with each other far
    more than three unrelated random walks would, and a fixture that ignores
    that makes CONFIRMED a near-impossible accident.
    """
    rows_4h = zigzag_rows(count_4h, start_ms=to_epoch_ms(_BASE), interval_ms=_FOUR_HOURS_MS, base=base_price, leg=6, step=2.0)
    rows_1d = resampled_rows(rows_4h, bars_per_period=6)
    rows_1w = resampled_rows(rows_4h, bars_per_period=42)
    if mirror:
        rows_4h = mirrored_rows(rows_4h)
        rows_1d = mirrored_rows(rows_1d)
        rows_1w = mirrored_rows(rows_1w)
    return {"4h": rows_4h, "1d": rows_1d, "1w": rows_1w}


class TestRunBacktestIntegration:
    def _transport_over(self, cache: dict[tuple[str, str], list[list]]):
        return fake_transport_for(cache)

    def test_empty_symbols_rejected(self) -> None:
        with pytest.raises(BacktestError):
            run_backtest([], start_time=_BASE, end_time=_BASE + timedelta(days=1), run_at=_BASE)

    def test_start_must_precede_end(self) -> None:
        with pytest.raises(BacktestError):
            run_backtest(
                ["BTCUSDT"], start_time=_BASE, end_time=_BASE, run_at=_BASE
            )

    def test_insufficient_warmup_produces_no_observations_for_a_tiny_window(self) -> None:
        rows = _three_role_rows("BTCUSDT", count_4h=3)
        cache = _build_cache("BTCUSDT", rows)
        run = run_backtest(
            ["BTCUSDT"],
            start_time=_BASE,
            end_time=from_epoch_ms(rows["4h"][-1][_CLOSE_TIME_INDEX] + 1),
            run_at=_BASE,
            transport=self._transport_over(cache),
        )
        assert run.observations == ()
        assert run.outcomes == ()

    def test_empty_dataset_produces_an_empty_but_valid_run(self) -> None:
        cache = {("BTCUSDT", i): [] for i in ("1w", "1d", "4h")}
        run = run_backtest(
            ["BTCUSDT"], start_time=_BASE, end_time=_BASE + timedelta(days=1), run_at=_BASE,
            transport=self._transport_over(cache),
        )
        assert run.observations == ()
        assert all(b.candle_count == 0 for b in run.data_boundaries)

    def test_deterministic_rerun_is_byte_identical(self) -> None:
        rows = _three_role_rows("BTCUSDT", count_4h=250)
        cache = _build_cache("BTCUSDT", rows)
        kwargs = dict(
            start_time=_BASE,
            end_time=from_epoch_ms(rows["4h"][-1][_CLOSE_TIME_INDEX] + 1),
            run_at=_BASE,
            transport=self._transport_over(cache),
        )
        run_a = run_backtest(["BTCUSDT"], **kwargs)
        run_b = run_backtest(["BTCUSDT"], **kwargs)
        assert run_a == run_b

    def test_symbol_isolation_one_symbols_data_does_not_affect_another(self) -> None:
        rows_a = _three_role_rows("BTCUSDT", count_4h=250, base_price=100.0)
        rows_b = _three_role_rows("ETHUSDT", count_4h=250, base_price=3000.0)
        cache = {**_build_cache("BTCUSDT", rows_a), **_build_cache("ETHUSDT", rows_b)}
        end = from_epoch_ms(rows_a["4h"][-1][_CLOSE_TIME_INDEX] + 1)
        run_both = run_backtest(
            ["BTCUSDT", "ETHUSDT"], start_time=_BASE, end_time=end, run_at=_BASE,
            transport=self._transport_over(cache),
        )
        run_solo = run_backtest(
            ["BTCUSDT"], start_time=_BASE, end_time=end, run_at=_BASE,
            transport=self._transport_over(cache),
        )
        btc_from_both = [o for o in run_both.observations if o.symbol == "BTCUSDT"]
        assert tuple(o.status for o in btc_from_both) == tuple(o.status for o in run_solo.observations)
        assert tuple(o.direction for o in btc_from_both) == tuple(o.direction for o in run_solo.observations)

    def test_no_lookahead_a_changed_future_candle_does_not_alter_an_earlier_decision(self) -> None:
        rows = _three_role_rows("BTCUSDT", count_4h=300)
        cache_a = _build_cache("BTCUSDT", rows)
        end = from_epoch_ms(rows["4h"][200][_CLOSE_TIME_INDEX] + 1)  # stop well before the series ends

        run_original = run_backtest(
            ["BTCUSDT"], start_time=_BASE, end_time=end, run_at=_BASE,
            transport=self._transport_over(cache_a),
        )

        # Corrupt every candle strictly AFTER the analysis cutoff — a real
        # lookahead bug would leak this into observations at or before `end`.
        mutated_4h = [list(r) for r in rows["4h"]]
        for row in mutated_4h[201:]:
            for price_index in (1, 2, 3, 4):  # open, high, low, close together
                row[price_index] = f"{float(row[price_index]) * 1000:.8f}"
        mutated_rows = dict(rows)
        mutated_rows["4h"] = mutated_4h
        cache_b = _build_cache("BTCUSDT", mutated_rows)

        run_mutated = run_backtest(
            ["BTCUSDT"], start_time=_BASE, end_time=end, run_at=_BASE,
            transport=self._transport_over(cache_b),
        )

        assert run_original.observations == run_mutated.observations

    def test_no_lookahead_a_changed_future_candle_does_not_alter_an_already_frozen_outcome(self) -> None:
        rows = _three_role_rows("BTCUSDT", count_4h=2600)
        cache_a = _build_cache("BTCUSDT", rows)
        end = from_epoch_ms(rows["4h"][-1][_CLOSE_TIME_INDEX] + 1)

        run_original = run_backtest(
            ["BTCUSDT"], start_time=_BASE, end_time=end, run_at=_BASE,
            transport=self._transport_over(cache_a), evaluation_window_bars=5,
        )
        if not run_original.outcomes:
            pytest.skip("fixture produced no confirmed, evaluable setup to test against")

        # Pick an outcome that resolved well within its window, then corrupt
        # candles far beyond that resolution point.
        resolved = [o for o in run_original.outcomes if o.bars_to_resolution is not None]
        if not resolved:
            pytest.skip("fixture produced no resolved outcome to test against")
        target_outcome = resolved[0]

        mutated_4h = [list(r) for r in rows["4h"]]
        # Corrupt the tail of the series, far beyond any 5-bar window.
        for row in mutated_4h[-10:]:
            row[2] = f"{float(row[2]) * 1000:.8f}"
            row[3] = "0.00000001"
        mutated_rows = dict(rows)
        mutated_rows["4h"] = mutated_4h
        cache_b = _build_cache("BTCUSDT", mutated_rows)

        run_mutated = run_backtest(
            ["BTCUSDT"], start_time=_BASE, end_time=end, run_at=_BASE,
            transport=self._transport_over(cache_b), evaluation_window_bars=5,
        )
        matching = [o for o in run_mutated.outcomes if o.setup_id == target_outcome.setup_id and o.confirmed_at == target_outcome.confirmed_at]
        assert matching and matching[0].status == target_outcome.status
        assert matching[0].bars_to_resolution == target_outcome.bars_to_resolution

    def test_long_short_symmetry_of_direction_counts(self) -> None:
        rows_up = _three_role_rows("BTCUSDT", count_4h=2600, mirror=False)
        rows_down = _three_role_rows("BTCUSDT", count_4h=2600, mirror=True)
        end = from_epoch_ms(rows_up["4h"][-1][_CLOSE_TIME_INDEX] + 1)

        run_up = run_backtest(
            ["BTCUSDT"], start_time=_BASE, end_time=end, run_at=_BASE,
            transport=self._transport_over(_build_cache("BTCUSDT", rows_up)),
        )
        run_down = run_backtest(
            ["BTCUSDT"], start_time=_BASE, end_time=end, run_at=_BASE,
            transport=self._transport_over(_build_cache("BTCUSDT", rows_down)),
        )

        long_count_up = sum(1 for o in run_up.observations if o.direction is Direction.LONG)
        short_count_up = sum(1 for o in run_up.observations if o.direction is Direction.SHORT)
        long_count_down = sum(1 for o in run_down.observations if o.direction is Direction.LONG)
        short_count_down = sum(1 for o in run_down.observations if o.direction is Direction.SHORT)

        assert len(run_up.observations) == len(run_down.observations)
        assert long_count_up > 0 and short_count_down > 0  # not a vacuous pass
        # The uptrend fixture leans LONG and the mirrored downtrend fixture
        # leans SHORT — a non-directional harness must flip with the market
        # it is fed, never favour one side regardless of the data.
        assert long_count_up >= short_count_up
        assert short_count_down >= long_count_down

    def test_full_report_renders_over_a_real_pipeline_run(self) -> None:
        rows = _three_role_rows("BTCUSDT", count_4h=300)
        cache = _build_cache("BTCUSDT", rows)
        end = from_epoch_ms(rows["4h"][-1][_CLOSE_TIME_INDEX] + 1)
        run = run_backtest(
            ["BTCUSDT"], start_time=_BASE, end_time=end, run_at=_BASE,
            transport=self._transport_over(cache),
        )
        from fmis.swing_setup.backtest_metrics import compute_metrics as cm

        report = render_backtest_report(run, cm(run))
        assert "BACKTEST SUMMARY" in report
        for line in report.splitlines():
            assert len(line) <= 78
