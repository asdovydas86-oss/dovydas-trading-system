"""Shared, dependency-free trailing-mean math for the volume features.

Kept as a small pure function (not a class, not a base abstraction) so that
average volume and relative volume use exactly the same arithmetic over exactly
the same window. This is the **single source of truth** for the volume baseline;
no other module — not a feature, not the pipeline, not decision support — may
re-implement it.

The window convention is the whole point of this module: the baseline is the
``lookback`` values **preceding** the most recent one, which is therefore
excluded. A value compared against a baseline it is itself part of would dilute
its own comparison, and the dilution grows worse as the lookback shrinks.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["trailing_mean", "required_values"]


def required_values(lookback: int) -> int:
    """Values needed for a trailing mean: the lookback window plus the current one.

    Stated as a function so features, their metadata, and tests all quote the same
    number instead of each repeating ``lookback + 1``.
    """
    return lookback + 1


def trailing_mean(values: Sequence[float], lookback: int) -> float | None:
    """Mean of the ``lookback`` values immediately **preceding** the last one.

    With ``values = [v0 … v9]`` and ``lookback = 3`` the mean is taken over
    ``v6, v7, v8`` — ``v9`` is deliberately excluded, so a caller may compare
    ``v9`` against a baseline it did not contribute to.

    Returns ``None`` when there are fewer than ``required_values(lookback)``
    values, leaving it to the caller to report insufficient data in whatever way
    its layer's conventions demand. Raises ``ValueError`` for a non-positive
    lookback, which is a caller error rather than a data condition.

    Pure arithmetic — deterministic and reproducible. It applies no weighting and
    performs no validation of the values themselves: the canonical `Candle`
    contract already guarantees volume is finite and non-negative.
    """
    if lookback < 1:
        raise ValueError(f"lookback must be at least 1, got {lookback}")
    if len(values) < required_values(lookback):
        return None
    window = values[-required_values(lookback) : -1]
    return sum(window) / lookback
