"""Post-confirmation outcome evaluation — what price did after a setup confirmed.

Outcome evaluation runs entirely **after** the instant it is trying to
resolve: this is the one place in the harness that deliberately reads
candles later than the decision they judge, because judging what happened
after a decision requires exactly that. It never feeds back into a decision
— the no-lookahead guarantee in `fmis.swing_setup.backtest_replay` governs
observation, not this module.

**Same-bar ambiguity, following ADR-0021's own refusal.**
The change-of-character design record states plainly that two structural
events sharing one candle cannot be ordered from OHLC data alone — there is
no sub-bar path in this repository's data. The identical refusal applies
here: a candle whose high crosses the target *and* whose low crosses the stop
cannot be read as "target then stop" or "stop then target" without guessing
an intrabar path this system has no evidence for. `AMBIGUOUS_SAME_BAR` is
that refusal, made a first-class outcome rather than a coin flip or a
candle-colour guess.
"""

from __future__ import annotations

from datetime import datetime

from fmis.data import Candle, CandleSeries
from fmis.swing_setup.backtest_models import BacktestError, OutcomeStatus, SetupOutcome
from fmis.swing_setup.models import Direction

__all__ = ["evaluate_outcome"]


def _hits(direction: Direction, candle: Candle, *, stop_price: float, target_price: float) -> tuple[bool, bool]:
    """``(target_hit, stop_hit)`` for one candle, by touch — a wick counts.

    A touch, not a close-through: a stop or target is a price level, and the
    candle's high/low are the only honest record of whether price reached
    it. Requiring a close beyond the level would be a different, stricter
    question this function does not claim to answer.
    """
    if direction is Direction.LONG:
        return candle.high >= target_price, candle.low <= stop_price
    return candle.low <= target_price, candle.high >= stop_price


def evaluate_outcome(
    execution_series: CandleSeries,
    *,
    setup_id: str,
    symbol: str,
    direction: Direction,
    confirmed_at: datetime,
    reference_price: float,
    stop_price: float,
    target_price: float,
    risk_reward_ratio: float,
    window_bars: int,
) -> SetupOutcome:
    """Classify what happened after ``confirmed_at``, over the next ``window_bars`` candles.

    ``execution_series`` is the **full** historical closed-candle series for
    the confirming symbol and execution interval — not a lookahead-limited
    prefix, because this function's entire purpose is to look forward from a
    point already decided. ``confirmed_at`` must equal the ``timestamp``
    (open time) of one of its candles — the confirming candle itself, the
    same instant `HistoricalObservation.execution_last_timestamp` recorded.

    The window starts at the candle **after** ``confirmed_at``: the
    confirming candle's own close is the stated reference price, and
    checking that same candle's high/low against a stop or target derived
    from its own close would not be a forward-looking measurement.

    Walks the window in order and stops at the first candle where the target
    and/or the stop is touched (high/low, not close). Both on the same
    candle is `AMBIGUOUS_SAME_BAR`. Neither touched within the window is
    `NEITHER_WITHIN_WINDOW` — including when the historical dataset simply
    ends before the window does; this function does not distinguish "price
    never got there" from "the data ran out", and the harness's own
    limitations say so.

    Raises:
        BacktestError: ``confirmed_at`` does not match any candle in
            ``execution_series``, or ``window_bars`` is not positive.
    """
    if not isinstance(execution_series, CandleSeries):
        raise TypeError(
            f"execution_series must be a CandleSeries, got {type(execution_series).__name__}"
        )
    if isinstance(window_bars, bool) or not isinstance(window_bars, int) or window_bars <= 0:
        raise BacktestError("window_bars must be a positive int")

    candles = execution_series.candles
    confirmed_index = next(
        (i for i, candle in enumerate(candles) if candle.timestamp == confirmed_at), None
    )
    if confirmed_index is None:
        raise BacktestError(
            f"{symbol}: no candle at {confirmed_at.isoformat()} in the supplied "
            "execution series — confirmed_at must be a candle in this series"
        )

    window = candles[confirmed_index + 1 : confirmed_index + 1 + window_bars]

    status = OutcomeStatus.NEITHER_WITHIN_WINDOW
    resolved_at: datetime | None = None
    bars_to_resolution: int | None = None
    for position, candle in enumerate(window, start=1):
        target_hit, stop_hit = _hits(
            direction, candle, stop_price=stop_price, target_price=target_price
        )
        if target_hit and stop_hit:
            status = OutcomeStatus.AMBIGUOUS_SAME_BAR
        elif target_hit:
            status = OutcomeStatus.TARGET_FIRST
        elif stop_hit:
            status = OutcomeStatus.STOP_FIRST
        else:
            continue
        resolved_at = candle.timestamp
        bars_to_resolution = position
        break

    return SetupOutcome(
        setup_id=setup_id,
        symbol=symbol,
        direction=direction,
        confirmed_at=confirmed_at,
        reference_price=reference_price,
        stop_price=stop_price,
        target_price=target_price,
        risk_reward_ratio=risk_reward_ratio,
        evaluation_window_bars=window_bars,
        status=status,
        resolved_at=resolved_at,
        bars_to_resolution=bars_to_resolution,
    )
