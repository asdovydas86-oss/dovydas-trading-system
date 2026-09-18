"""The secondary study: regime windows, cross-asset transfer, and D2-M.

Separate from `run.py` because it asks different questions of the same data and
because keeping the main grid's output schema stable matters more than saving a
pass over the capture.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from research.zone_semantics import d2, dataset, metrics  # noqa: E402
from research.zone_semantics.policies import (  # noqa: E402
    G_ANCHOR,
    T_ANCHOR,
    W_ATR,
    W_STRUCT_CAUSAL,
    Candidate,
    WidthScale,
)
from research.zone_semantics.structure import atr_by_index, levels_for  # noqa: E402

WINDOW_BARS = {"1w": 60, "1d": 260, "4h": 900}
K_GRID = (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 0.80, 1.00)


def _windows(series, size: int):
    candles = series.closed().candles
    for start in range(0, len(candles) - size + 1, size):
        yield series.__class__(
            symbol=series.symbol,
            timeframe=series.timeframe,
            candles=candles[start : start + size],
        )


def _regime(window) -> dict:
    """Describe a window by realised volatility and net displacement.

    Both are computed from the window's own candles. Nothing is excluded for
    looking untidy, and no window is labelled by eye: the buckets in the report
    are quantiles of whatever the sample turned out to contain.
    """
    candles = window.closed().candles
    closes = [c.close for c in candles]
    atr = atr_by_index(window)
    if not atr or not closes:
        return {}
    ratios = [atr[i] / candles[i].close for i in sorted(atr) if candles[i].close]
    return {
        "vol_ratio": median(ratios) if ratios else None,
        "displacement": (closes[-1] - closes[0]) / closes[0] if closes[0] else None,
        "range_ratio": (
            (max(c.high for c in candles) - min(c.low for c in candles)) / closes[0]
            if closes[0]
            else None
        ),
    }


def main() -> None:
    target = Path(
        sys.argv[1]
        if len(sys.argv) > 1
        else "reports/artifacts/0050_zone_semantics_secondary.json"
    )
    regime_rows: list[dict] = []
    d2_rows: list[dict] = []

    for item in dataset.load_capture():
        for role, timeframe, series in dataset.role_series(item):
            # ---- D2-M, on the whole run -------------------------------------
            if timeframe in ("1w", "1d"):
                levels = levels_for(series)
                atr = atr_by_index(series)
                if levels and atr:
                    last_index = len(series.closed().candles) - 1
                    counts = d2.interaction_counts(series, levels)
                    for k in (0.30, 0.50, 0.80):
                        candidate = Candidate(
                            scale=WidthScale(W_ATR, k, T_ANCHOR), geometry=G_ANCHOR
                        )
                        zones = candidate.zones(
                            levels, atr=atr, last_index=last_index
                        )
                        row = {
                            "symbol": item.symbol,
                            "universe": item.universe,
                            "role": role,
                            "timeframe": timeframe,
                            "k": k,
                        }
                        row.update(
                            d2.disagreement(
                                zones,
                                counts,
                                series.closed().candles[-1].close,
                            )
                        )
                        row.update(d2.sided_history(series, zones))
                        d2_rows.append(row)

            # ---- regime windows ---------------------------------------------
            size = WINDOW_BARS[timeframe]
            for position, window in enumerate(_windows(series, size)):
                levels = levels_for(window)
                atr = atr_by_index(window)
                if len(levels) < 8 or not atr:
                    continue
                last_index = len(window.closed().candles) - 1
                base = {
                    "symbol": item.symbol,
                    "universe": item.universe,
                    "role": role,
                    "timeframe": timeframe,
                    "window": position,
                    "start": window.closed().candles[0].timestamp.isoformat(),
                }
                base.update(_regime(window))
                for scale_kind in (W_ATR, W_STRUCT_CAUSAL):
                    for k in K_GRID:
                        scale = WidthScale(scale_kind, k, T_ANCHOR)
                        candidate = Candidate(scale=scale, geometry=G_ANCHOR)
                        zones = candidate.zones(
                            levels, atr=atr, last_index=last_index
                        )
                        row = dict(base)
                        row["scale"] = scale_kind
                        row["k"] = k
                        row.update(
                            metrics.describe(
                                zones,
                                levels,
                                reference_atr=atr[max(atr)],
                                reference_price=window.closed().candles[-1].close,
                            )
                        )
                        regime_rows.append(row)
        print(f"  {item.symbol} done", flush=True)

    payload = {
        "schema_version": 1,
        "window_bars": WINDOW_BARS,
        "k_grid": list(K_GRID),
        "capture_digest": dataset.capture_digest(),
        "regime_rows": regime_rows,
        "d2_rows": d2_rows,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    print(
        f"wrote {target} ({target.stat().st_size} bytes, "
        f"{len(regime_rows)} regime rows, {len(d2_rows)} d2 rows)"
    )


if __name__ == "__main__":
    main()
