"""Value types for the Swing Setup historical backtest harness (Milestone AV).

This module records **measurements**, never a trade record and never a claim
of profitability. It is the one place besides `models.py`, `policy.py`,
`render.py` and `compose.py` where this file lives directly inside
`fmis/swing_setup/` and may therefore use directional vocabulary
(ADR-0028 §5 exempts every file whose parent directory is `fmis/swing_setup/`
— see `tests/test_directional_vocabulary_boundary.py`).

**Nothing here is computed.** Every field on `HistoricalObservation` is copied
from a `SetupAssessment`/`SetupInputs` pair the production composition path
(`fmis.swing_setup.compose`) already produced for a historical closed-candle
prefix. This module states what happened; it does not decide anything.

**No probability, no expected value, no win rate is ever stored.** `SetupOutcome`
records what price did after confirmation as one of four honest, symmetric
outcomes — never a fabricated realized return.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

from fmis.swing_setup.models import Direction, SetupState, SwingSetupError

__all__ = [
    "BACKTEST_SCHEMA_VERSION",
    "BacktestError",
    "DataBoundary",
    "FamilyLean",
    "HistoricalObservation",
    "OutcomeStatus",
    "SetupOutcome",
    "BacktestRun",
]

#: Bumped when the serialized shape changes in a way a consumer must notice.
BACKTEST_SCHEMA_VERSION = 1


class BacktestError(SwingSetupError):
    """Base class for every backtest-harness failure."""


@dataclass(frozen=True, slots=True)
class DataBoundary:
    """The exact historical window one (symbol, interval) series was built from.

    Recorded so a run is reproducible and auditable rather than silently
    depending on "whatever Binance returns today": a reader can see precisely
    which candles a run's results rest on.
    """

    symbol: str
    interval: str
    source: str
    first_candle: datetime | None
    last_candle: datetime | None
    candle_count: int
    fetched_at: datetime

    def __post_init__(self) -> None:
        for name in ("symbol", "interval", "source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise BacktestError(f"{name} must be a non-empty str")
        for name in ("first_candle", "last_candle"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, datetime):
                raise TypeError(f"{name} must be a datetime or None")
        if (self.first_candle is None) != (self.last_candle is None):
            raise BacktestError(
                "first_candle and last_candle must both be set, or both be "
                "None (an empty window)"
            )
        if not isinstance(self.fetched_at, datetime):
            raise TypeError("fetched_at must be a datetime")
        if isinstance(self.candle_count, bool) or not isinstance(self.candle_count, int):
            raise TypeError("candle_count must be an int")
        if self.candle_count < 0:
            raise BacktestError("candle_count cannot be negative")
        if self.candle_count == 0 and self.first_candle is not None:
            raise BacktestError("candle_count is 0 but first_candle/last_candle are set")


@dataclass(frozen=True, slots=True)
class FamilyLean:
    """One independent evidence family's lean at one historical instant.

    A flattened, JSON-safe restatement of `fmis.swing_setup.models.DirectionalFactor`
    — copied, not recomputed — kept beside the observation so the
    independence/double-counting audit can be run without re-deriving anything.
    """

    family: str
    lean: str

    def __post_init__(self) -> None:
        for name in ("family", "lean"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise BacktestError(f"{name} must be a non-empty str")


@dataclass(frozen=True, slots=True)
class HistoricalObservation:
    """One deterministic Swing Setup observation at one historical closed-candle prefix.

    Every field is a **fact copied from** the `SetupInputs`/`SetupAssessment`
    pair the production composition path produced for this instant — nothing is
    computed here. ``setup_id``/``is_new_setup`` are the harness's own
    freshness bookkeeping (`fmis.swing_setup.backtest_identity`), the one piece
    of state genuinely new to this module.

    ``execution_last_timestamp`` is the execution-role view's own last closed
    candle — the same instant `reference_price` was read from — carried so
    outcome evaluation can locate the confirming candle in the full historical
    series without re-deriving an index.
    """

    symbol: str
    as_of: datetime
    status: SetupState
    direction: Direction | None
    setup_id: str | None
    is_new_setup: bool
    directional_factors: tuple[FamilyLean, ...]
    thesis: tuple[str, ...]
    confirmation: tuple[str, ...]
    trigger_kind: str | None
    trigger_price: float | None
    reference_price: float | None
    stop_price: float | None
    target_price: float | None
    risk_reward_ratio: float | None
    sufficiency: str
    context_regime_structure: str
    context_regime_volatility: str
    context_regime_participation: str
    execution_last_timestamp: datetime | None
    policy_id: str
    schema_version: int = BACKTEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise BacktestError("symbol must be a non-empty str")
        if not isinstance(self.as_of, datetime):
            raise TypeError("as_of must be a datetime")
        if not isinstance(self.status, SetupState):
            raise TypeError(f"status must be a SetupState, got {type(self.status).__name__}")
        if self.direction is not None and not isinstance(self.direction, Direction):
            raise TypeError("direction must be a Direction or None")
        if (self.direction is None) != (self.status is SetupState.WAIT):
            raise BacktestError(
                "direction is None if and only if status is WAIT, matching "
                "SetupAssessment's own invariant"
            )
        if (self.setup_id is None) != (self.direction is None):
            raise BacktestError(
                "setup_id is None if and only if direction is None; a WAIT "
                "observation has no setup to identify"
            )
        if not isinstance(self.is_new_setup, bool):
            raise TypeError("is_new_setup must be a bool")
        if self.is_new_setup and self.setup_id is None:
            raise BacktestError("is_new_setup requires a setup_id")
        if not isinstance(self.directional_factors, tuple):
            raise TypeError("directional_factors must be a tuple of FamilyLean")
        for item in self.directional_factors:
            if not isinstance(item, FamilyLean):
                raise TypeError("every directional_factors entry must be a FamilyLean")
        for name in ("thesis", "confirmation"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple of str")
        if self.trigger_kind is not None and not isinstance(self.trigger_kind, str):
            raise TypeError("trigger_kind must be a str or None")
        for name in (
            "trigger_price", "reference_price", "stop_price", "target_price",
            "risk_reward_ratio",
        ):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise TypeError(f"{name} must be a number or None")
        for name in (
            "sufficiency", "context_regime_structure", "context_regime_volatility",
            "context_regime_participation", "policy_id",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise BacktestError(f"{name} must be a non-empty str")
        if self.execution_last_timestamp is not None and not isinstance(
            self.execution_last_timestamp, datetime
        ):
            raise TypeError("execution_last_timestamp must be a datetime or None")


class OutcomeStatus(str, Enum):
    """What happened after a setup confirmed, honestly classified.

    Four members, symmetric across `Direction`. `AMBIGUOUS_SAME_BAR` follows
    ADR-0021's own refusal to read an intrabar path from OHLC data alone
    (the change-of-character package's same-bar break ordering is the level
    ordering, never a claim about which happened first) — the identical
    discipline applied to a stop and a target rather than to two breaks.
    """

    TARGET_FIRST = "target_first"
    STOP_FIRST = "stop_first"
    AMBIGUOUS_SAME_BAR = "ambiguous_same_bar"
    NEITHER_WITHIN_WINDOW = "neither_within_window"


@dataclass(frozen=True, slots=True)
class SetupOutcome:
    """What happened after one uniquely identified setup first confirmed.

    ``resolved_at``/``bars_to_resolution`` are ``None`` exactly when
    ``status`` is `NEITHER_WITHIN_WINDOW` — nothing resolved inside the
    evaluation window, so there is nothing to date.

    This is outcome **classification**, not realized PnL: fees, slippage,
    spread and execution delay are not modelled (see the harness's own
    limitations), and ``risk_reward_ratio`` restates the printed R:R at
    confirmation, never a realized return.
    """

    setup_id: str
    symbol: str
    direction: Direction
    confirmed_at: datetime
    reference_price: float
    stop_price: float
    target_price: float
    risk_reward_ratio: float
    evaluation_window_bars: int
    status: OutcomeStatus
    resolved_at: datetime | None
    bars_to_resolution: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.setup_id, str) or not self.setup_id.strip():
            raise BacktestError("setup_id must be a non-empty str")
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise BacktestError("symbol must be a non-empty str")
        if not isinstance(self.direction, Direction):
            raise TypeError(f"direction must be a Direction, got {type(self.direction).__name__}")
        if not isinstance(self.confirmed_at, datetime):
            raise TypeError("confirmed_at must be a datetime")
        for name in ("reference_price", "stop_price", "target_price", "risk_reward_ratio"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
        if isinstance(self.evaluation_window_bars, bool) or not isinstance(
            self.evaluation_window_bars, int
        ):
            raise TypeError("evaluation_window_bars must be an int")
        if self.evaluation_window_bars <= 0:
            raise BacktestError("evaluation_window_bars must be positive")
        if not isinstance(self.status, OutcomeStatus):
            raise TypeError(f"status must be an OutcomeStatus, got {type(self.status).__name__}")
        resolved = self.status is not OutcomeStatus.NEITHER_WITHIN_WINDOW
        if resolved != (self.resolved_at is not None):
            raise BacktestError(
                "resolved_at is set if and only if status is not "
                "NEITHER_WITHIN_WINDOW"
            )
        if resolved != (self.bars_to_resolution is not None):
            raise BacktestError(
                "bars_to_resolution is set if and only if status is not "
                "NEITHER_WITHIN_WINDOW"
            )
        if self.resolved_at is not None and not isinstance(self.resolved_at, datetime):
            raise TypeError("resolved_at must be a datetime or None")
        if self.bars_to_resolution is not None:
            if isinstance(self.bars_to_resolution, bool) or not isinstance(
                self.bars_to_resolution, int
            ):
                raise TypeError("bars_to_resolution must be an int or None")
            if not 1 <= self.bars_to_resolution <= self.evaluation_window_bars:
                raise BacktestError(
                    "bars_to_resolution must be between 1 and "
                    "evaluation_window_bars"
                )


@dataclass(frozen=True, slots=True)
class BacktestRun:
    """One complete, reproducible backtest run: inputs, observations, outcomes.

    ``policy_id``/``context_policy_id`` are carried so a stored run states
    exactly which policy version produced it — the same discipline every
    `SetupAssessment` already applies to itself.

    Two runs over the same historical dataset and the same code produce an
    equal `BacktestRun` (`created_at` and `metadata['duration_seconds']`
    excepted, which are the two fields the caller stamps rather than derives).
    """

    schema_version: int
    created_at: datetime
    symbols: tuple[str, ...]
    timeframes: Mapping[str, str]
    evaluation_window_bars: int
    data_boundaries: tuple[DataBoundary, ...]
    policy_id: str
    context_policy_id: str
    observations: tuple[HistoricalObservation, ...]
    outcomes: tuple[SetupOutcome, ...]
    limitations: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool):
            raise TypeError("schema_version must be an int")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if not isinstance(self.symbols, tuple) or not self.symbols:
            raise BacktestError("symbols must be a non-empty tuple of str")
        for symbol in self.symbols:
            if not isinstance(symbol, str) or not symbol.strip():
                raise BacktestError("every symbol must be a non-empty str")
        if not isinstance(self.timeframes, Mapping) or not self.timeframes:
            raise BacktestError("timeframes must be a non-empty mapping")
        if isinstance(self.evaluation_window_bars, bool) or not isinstance(
            self.evaluation_window_bars, int
        ):
            raise TypeError("evaluation_window_bars must be an int")
        if self.evaluation_window_bars <= 0:
            raise BacktestError("evaluation_window_bars must be positive")
        if not isinstance(self.data_boundaries, tuple):
            raise TypeError("data_boundaries must be a tuple of DataBoundary")
        for item in self.data_boundaries:
            if not isinstance(item, DataBoundary):
                raise TypeError("every data_boundaries entry must be a DataBoundary")
        for name in ("policy_id", "context_policy_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise BacktestError(f"{name} must be a non-empty str")
        if not isinstance(self.observations, tuple):
            raise TypeError("observations must be a tuple of HistoricalObservation")
        for item in self.observations:
            if not isinstance(item, HistoricalObservation):
                raise TypeError("every observations entry must be a HistoricalObservation")
        if not isinstance(self.outcomes, tuple):
            raise TypeError("outcomes must be a tuple of SetupOutcome")
        for item in self.outcomes:
            if not isinstance(item, SetupOutcome):
                raise TypeError("every outcomes entry must be a SetupOutcome")
        if not isinstance(self.limitations, tuple):
            raise TypeError("limitations must be a tuple of str")
        for item in self.limitations:
            if not isinstance(item, str) or not item.strip():
                raise BacktestError("every limitations entry must be a non-empty str")
        object.__setattr__(self, "timeframes", MappingProxyType(dict(self.timeframes)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
