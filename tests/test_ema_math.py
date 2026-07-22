"""Regression tests for the shared ema_series helper (extracted from EMA).

Independent hand values; no production algorithm copied.
"""

from __future__ import annotations

import pytest

from fmis.features.indicators.ema_math import ema_series


def test_seed_only_equals_sma() -> None:
    # Exactly `period` values -> single EMA equal to their mean.
    assert ema_series([1, 2, 3], 3) == [2.0]


def test_length_is_n_minus_period_plus_one() -> None:
    assert len(ema_series([1, 2, 3, 4, 5, 6], 3)) == 4


def test_known_recursive_series() -> None:
    # period=3, [1..6]: seed 2.0; k=0.5 -> 3.0, 4.0, 5.0
    assert ema_series([1, 2, 3, 4, 5, 6], 3) == pytest.approx([2.0, 3.0, 4.0, 5.0])


def test_period_one_returns_values_unchanged() -> None:
    # k = 1 -> each EMA equals its own value.
    assert ema_series([10, 20, 30], 1) == pytest.approx([10.0, 20.0, 30.0])


def test_insufficient_returns_empty() -> None:
    assert ema_series([1, 2], 3) == []
