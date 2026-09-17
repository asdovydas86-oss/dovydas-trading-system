"""Shared, dependency-free RSI math: gains and losses, the ratio, the series.

The single source of truth for the Wilder RSI arithmetic. Both the latest-value
path (`RelativeStrengthIndex.compute`) and the historical path
(`RelativeStrengthIndex.compute_series`) read what this module produces, so the
zero-gain/zero-loss policy in particular exists in exactly one place — a policy
restated in two branches is a policy that eventually differs in one of them
(ADR-0031 §6).

Alignment, stated once:

    gains[j] / losses[j]  describe closed candle  j + 1   (a change needs a predecessor)
    rsi_series[k]         describes closed candle  k + period

so with ``period`` = 14 the first RSI describes closed candle index 14, matching
the ``warmup_candles = period + 1`` the feature has always reported.
"""

from __future__ import annotations

from collections.abc import Sequence

from fmis.features.indicators.wilder_math import wilder_series

__all__ = ["gains_and_losses", "relative_strength_index", "rsi_series"]


def gains_and_losses(prices: Sequence[float]) -> tuple[list[float], list[float]]:
    """Per-candle upward and downward moves, both reported as magnitudes.

        change_t = P_t - P_{t-1}
        gain_t   = max(change_t, 0)
        loss_t   = max(-change_t, 0)

    Defined from the **second** price onward, so ``N`` prices yield ``N - 1``
    pairs and element ``j`` describes candle ``j + 1``.
    """
    gains: list[float] = []
    losses: list[float] = []
    for position in range(1, len(prices)):
        change = prices[position] - prices[position - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    return gains, losses


def relative_strength_index(average_gain: float, average_loss: float) -> float:
    """RSI from one smoothed gain/loss pair, with the zero policy stated.

        average_loss == 0 and average_gain  > 0 -> 100.0
        average_gain == 0 and average_loss  > 0 ->   0.0
        average_gain == 0 and average_loss == 0 ->  50.0   (flat: neither strength)
        otherwise: RS = gain / loss ; RSI = 100 - (100 / (1 + RS))

    The all-flat case is **50.0 by policy, not by arithmetic**: with no movement
    either way there is no strength to report and no ratio to compute, and a
    division would be undefined rather than neutral.
    """
    if average_loss == 0.0 and average_gain > 0.0:
        return 100.0
    if average_gain == 0.0 and average_loss > 0.0:
        return 0.0
    if average_gain == 0.0 and average_loss == 0.0:
        return 50.0
    strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + strength))


def rsi_series(prices: Sequence[float], period: int) -> list[float]:
    """Wilder RSI for every candle at which it is defined.

    ``rsi_series(...)[k]`` describes closed candle ``k + period``. Empty when
    there are fewer than ``period + 1`` prices.
    """
    gains, losses = gains_and_losses(prices)
    smoothed_gains = wilder_series(gains, period)
    smoothed_losses = wilder_series(losses, period)
    return [
        relative_strength_index(gain, loss)
        for gain, loss in zip(smoothed_gains, smoothed_losses)
    ]
