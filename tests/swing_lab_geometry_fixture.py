"""A synthetic world that actually produces swing setups. **Shared, and slow on purpose.**

Milestone BX's no-lookahead proof needs a fixture that reaches *first
confirmations inside the measurement window*, which the Milestone BW fixture does
not: its price path trends in one direction, so its single opportunity opens
during the identity-priming prefix and never reopens. Every measured bar then
carries ``is_first_confirmation=False`` and no trade is ever admitted — a
perfectly good fixture for BW's question (does an observation change?) and a
useless one for BX's (does a *geometry* change?).

So the path here is built to **turn over**: a slow macro sine short enough to
reverse the weekly structural trend several times inside the window, with the
secular drift removed so the sine is what decides direction rather than being
swamped by it. Two symbols with different periods are replayed together, chosen
so one produces LONG opportunities and the other SHORT — a geometry bug that
inverted a side would otherwise hide behind a single-direction fixture.

The warm-up is the real one: 250 weekly candles is what production's analysis
window binds at, and shortening it would test a harness production does not run.
That is why this fixture is expensive, and why every module using it caches.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fmis.swing_setup.backtest_replay import prepare_replay_index
from fmis.swing_setup.research_harness import (
    DEFAULT_IDENTITY_PRIMING_BARS,
    ResearchDataset,
    build_segments,
)
from fmis.swing_setup.research_models import ResearchWindow

from tests.test_swing_setup_backtest import (
    _FOUR_HOURS_MS,
    resampled_rows,
    zigzag_rows,
)

__all__ = [
    "BASE", "FOUR_HOURS", "LIMIT", "WARM_BARS", "MEASURED_BARS", "TAIL_BARS",
    "MEASUREMENT_START", "MEASUREMENT_END", "SYMBOLS", "RUN_AT",
    "rows_for", "dataset_for", "window_for", "segments_for", "scale",
]

_UTC = timezone.utc
BASE = datetime(2024, 1, 1, tzinfo=_UTC)
FOUR_HOURS = timedelta(hours=4)
_BARS_PER_DAY = 6
_BARS_PER_WEEK = 42

#: 200, for the reason `tests.test_swing_lab_nolookahead` records: `derive_warmup`
#: takes the maximum over the production dependencies and EMA(200) binds at 200
#: bars however small the requested analysis window is.
LIMIT = 200
WARM_BARS = LIMIT * _BARS_PER_WEEK + DEFAULT_IDENTITY_PRIMING_BARS
MEASURED_BARS = 500
TAIL_BARS = 40
_TOTAL_BARS = WARM_BARS + MEASURED_BARS + TAIL_BARS + 20

MEASUREMENT_START = BASE + WARM_BARS * FOUR_HOURS
MEASUREMENT_END = MEASUREMENT_START + MEASURED_BARS * FOUR_HOURS
RUN_AT = datetime(2030, 1, 1, tzinfo=_UTC)

#: Two symbols with deliberately different macro periods. Measured, not hoped
#: for: BTCUSDT's path yields LONG opportunities and ETHUSDT's yields SHORT ones,
#: and `test_swing_lab_geometry_nolookahead` asserts both are present so a
#: regression that lost one fails loudly rather than quietly halving the proof.
SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
_MACRO: dict[str, tuple[float, int]] = {
    "BTCUSDT": (60.0, 150),
    "ETHUSDT": (80.0, 200),
}


def rows_for(symbol: str, count: int = _TOTAL_BARS) -> dict[str, list[list]]:
    """One 4H path, resampled up — so the three roles are genuinely correlated."""
    amplitude, period = _MACRO[symbol]
    rows_4h = zigzag_rows(
        count,
        start_ms=int(BASE.timestamp() * 1000),
        interval_ms=_FOUR_HOURS_MS,
        base=100.0,
        macro_amplitude=amplitude,
        macro_period=period,
        # Zero, so the macro sine decides the weekly trend rather than being
        # swamped by a secular drift. This is the one parameter that decides
        # whether the fixture ever changes its mind.
        linear_drift_per_bar=0.0,
    )
    return {
        "4h": rows_4h,
        "1d": resampled_rows(rows_4h, bars_per_period=_BARS_PER_DAY),
        "1w": resampled_rows(rows_4h, bars_per_period=_BARS_PER_WEEK),
    }


def all_rows() -> dict[str, dict[str, list[list]]]:
    return {symbol: rows_for(symbol) for symbol in SYMBOLS}


def dataset_for(rows: dict[str, dict[str, list[list]]]) -> ResearchDataset:
    cache = {
        (symbol, interval): data
        for symbol, per_symbol in rows.items()
        for interval, data in per_symbol.items()
    }
    return ResearchDataset(
        cache=cache,
        index=prepare_replay_index(cache),
        boundaries=(),
        fetch_starts={},
        fetched_at=RUN_AT,
    )


def window_for(measurement_end: datetime = MEASUREMENT_END) -> ResearchWindow:
    return ResearchWindow(
        warmup_start=BASE,
        measurement_start=MEASUREMENT_START,
        measurement_end=measurement_end,
        outcome_tail_end=measurement_end + TAIL_BARS * FOUR_HOURS,
    )


def segments_for(window: ResearchWindow):
    return build_segments(window)


def scale(rows: list[list], start: int, factor: float) -> list[list]:
    """Every price from ``start`` onward, multiplied. Open/high/low/close alike."""
    mutated = [list(row) for row in rows]
    for row in mutated[start:]:
        for price_index in (1, 2, 3, 4):
            row[price_index] = f"{float(row[price_index]) * factor:.8f}"
    return mutated


def scale_all(
    rows: dict[str, dict[str, list[list]]], start: int, factor: float, *, intervals=("4h",)
) -> dict[str, dict[str, list[list]]]:
    """Mutate the named intervals of every symbol from ``start`` onward."""
    return {
        symbol: {
            interval: (
                scale(data, start, factor) if interval in intervals else data
            )
            for interval, data in per_symbol.items()
        }
        for symbol, per_symbol in rows.items()
    }
