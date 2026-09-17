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

__all__ = ["trailing_mean", "trailing_mean_series", "required_values"]


def _mean_of(window: Sequence[float], lookback: int) -> float:
    """The one arithmetic in this module. **Every mean here goes through it.**

    Extracted so that the latest-value mean and the historical one are not two
    expressions that happen to agree: they are one expression, evaluated over
    different windows, which is what makes the final point of a trailing-mean
    series **bit-identical** to `trailing_mean` over the same values rather than
    merely close to it (ADR-0031 §6).
    """
    return sum(window) / lookback


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
    return _mean_of(window, lookback)


def trailing_mean_series(
    values: Sequence[float], lookback: int
) -> list[tuple[int, float]]:
    """Every trailing mean this window convention defines, with its position.

    Returns ``(position, mean)`` pairs, where ``position`` is the index of the
    value the mean is a baseline **for** — so the pair at position ``t`` holds
    the mean of ``values[t - lookback : t]``, the same window `trailing_mean`
    takes over the values up to and including ``t``, with ``values[t]`` excluded
    from its own comparison exactly as that function documents.

    The first pair is at position ``lookback``; earlier positions have no
    baseline and are **absent rather than padded**, because a padded zero and a
    real zero baseline are different facts and only one of them is undefined.

    The position is returned rather than left implicit because a caller placing
    these values on a candle timeline must not have to re-derive the offset —
    re-deriving it is exactly the off-by-one this shape exists to prevent.

    Equal by construction to `trailing_mean` at the last position: both means go
    through `_mean_of`, over the same slice, in the same order.

    Raises ``ValueError`` for a non-positive lookback, matching `trailing_mean`:
    that is a caller error, not a data condition.
    """
    if lookback < 1:
        raise ValueError(f"lookback must be at least 1, got {lookback}")
    return [
        (position, _mean_of(values[position - lookback : position], lookback))
        for position in range(lookback, len(values))
    ]
