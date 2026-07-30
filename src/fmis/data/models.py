"""Normalized OHLCV data contract.

Immutable, validated primitives that every higher layer (features, strategies,
risk, backtesting) consumes. This module defines only the *shape* of market
data and its invariants — no indicator math, no strategy logic, no I/O.

Design decision — numeric type:
    OHLCV values use ``float``. Market data, technical indicators, and
    backtesting are tolerant of tiny binary-floating-point rounding and benefit
    from float's speed and standard-library simplicity. ``Decimal`` is
    deliberately deferred and will be reconsidered later for money, accounting,
    order sizing, and execution, where exact decimal arithmetic matters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from fmis.data._timeutils import validate_utc_timestamp

__all__ = ["Candle", "CandleSeries", "SeriesIdentity"]

_PRICE_FIELDS = ("open", "high", "low", "close", "volume")


def _require_identity_label(value: object, *, field: str) -> None:
    """Validate one identity label — the one authoritative rule.

    Deliberately **no stricter in value than `CandleSeries` already is**: present,
    a ``str``, and not blank. That is a compatibility constraint, not a
    preference. `CandleSeries` accepts ``" BTCUSDT "``, so a stricter rule here
    would make `CandleSeries.identity` raise for a series that is already valid,
    and a projection that can fail on a valid object is not a projection.

    The type check *is* stricter, and safely so: `CandleSeries` already rejects a
    non-``str`` symbol, just via ``AttributeError`` from ``.strip()``, so no valid
    series can hold one. Naming the failure is an improvement with no reachable
    behaviour change.

    Nothing is normalized. Surrounding whitespace is preserved and yields a
    *different* identity, case is significant, and no alias is translated. This is
    inherited policy, not a new decision: the evidence-descriptor layer records why
    identity strings are rejected rather than rewritten (ADR-0011), and the
    trading-analysis context layer records that ``"4h"`` and ``"4H"`` are two
    different labels because the system has no canonical timeframe vocabulary
    (ADR-0009).

    The direction of the resulting error is deliberate. Refusing to normalize makes
    this contract **over-reject** — ``" BTCUSDT"`` will not combine with
    ``"BTCUSDT"``. Over-rejection is safe; under-rejection is the silent mixing the
    contract exists to prevent.
    """
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a str, got {type(value).__name__}")
    if not value or not value.strip():
        raise ValueError(f"{field} cannot be empty")


@dataclass(frozen=True, slots=True)
class SeriesIdentity:
    """What uniquely identifies one analytical market series: symbol + timeframe.

    This type does not *introduce* identity — it **extracts** the identity
    `CandleSeries` has always carried, so that derived facts can keep it. Before
    it, a `SwingPoint`, `StructuralSequenceStateSnapshot` and
    `StructuralTrendSnapshot` were identity-free, and two instruments' histories
    could be concatenated with nothing able to object.

    Exactly two fields, and the omissions are the substance:

      * **no venue or exchange** — nothing in the repository stores, validates or
        compares one, and inferring which venue a symbol belongs to would be a
        mapping this layer must not invent;
      * **no data source or provider** — that describes *how data arrived*, not
        *what the series is*, and it belongs to pipeline metadata; including it
        would make two identical series from two providers incomparable;
      * **no market type, quote currency, price type or contract identifier** —
        each needs parsing or resolution rules that do not exist here.

    A field earns inclusion only if something in the repository today would be
    wrong without it. Symbol and timeframe both do; nothing else does.

    **Equality is structural and exact.** Two identities are equal iff both strings
    are equal by ``==``. No case folding, no trimming, no Unicode normalization, no
    alias translation: ``"BTCUSDT"``, ``"btcusdt"`` and ``" BTCUSDT"`` are three
    identities, and so are ``"4h"``, ``"4H"`` and ``"240m"``. See
    `_require_identity_label` for why, and for the deliberate direction of that
    error.

    **A timeframe label is opaque.** ``"banana"`` is accepted, because validating
    the grammar would require a canonical vocabulary the system does not have
    (ADR-0009). Nothing here infers a timeframe from timestamps, and nothing infers
    identity from prices.

    Frozen, slotted and hashable, so an identity cannot drift, can key a dict, and
    can be shared by reference across a whole pipeline without any copy.
    """

    symbol: str
    timeframe: str

    def __post_init__(self) -> None:
        _require_identity_label(self.symbol, field="symbol")
        _require_identity_label(self.timeframe, field="timeframe")


@dataclass(frozen=True, slots=True)
class Candle:
    """A single OHLCV bar for one symbol and timeframe.

    Frozen (immutable) so a validated candle can never drift out of its
    invariants after construction. `is_closed` distinguishes a completed bar
    from a still-forming one; only closed bars are safe for reproducible
    signals.
    """

    timestamp: datetime
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if not self.timeframe or not self.timeframe.strip():
            raise ValueError("timeframe cannot be empty")

        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        validate_utc_timestamp(self.timestamp)

        for name in _PRICE_FIELDS:
            value = getattr(self, name)
            if not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
            if value < 0:
                raise ValueError(f"{name} cannot be negative")

        if self.high < self.open or self.high < self.close or self.high < self.low:
            raise ValueError("high must be >= open, close, and low")
        if self.low > self.open or self.low > self.close or self.low > self.high:
            raise ValueError("low must be <= open, close, and high")


@dataclass(frozen=True, slots=True)
class CandleSeries:
    """An ordered, single-symbol/single-timeframe collection of candles.

    Candles are normalized to a tuple so the container stays immutable. Every
    candle must match the series `symbol` and `timeframe`, and timestamps must
    be strictly increasing (no duplicates, no gaps backwards in time).
    """

    symbol: str
    timeframe: str
    candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if not self.timeframe or not self.timeframe.strip():
            raise ValueError("timeframe cannot be empty")

        # Accept any iterable at construction; store an immutable tuple.
        object.__setattr__(self, "candles", tuple(self.candles))

        previous: datetime | None = None
        for candle in self.candles:
            if candle.symbol != self.symbol:
                raise ValueError(
                    f"candle symbol {candle.symbol!r} does not match "
                    f"series symbol {self.symbol!r}"
                )
            if candle.timeframe != self.timeframe:
                raise ValueError(
                    f"candle timeframe {candle.timeframe!r} does not match "
                    f"series timeframe {self.timeframe!r}"
                )
            if previous is not None and candle.timestamp <= previous:
                raise ValueError("candle timestamps must be strictly increasing")
            previous = candle.timestamp

    @property
    def identity(self) -> SeriesIdentity:
        """This series' `SeriesIdentity` — a **projection, not a stored field**.

        Built from ``symbol`` and ``timeframe`` on access, following ADR-0016 §4:
        a stored copy of a value one attribute away is somewhere for it to drift.
        So there is exactly one place a candle-derived pipeline's identity comes
        from, and no synchronization problem can exist.

        Never raises for a valid series — `SeriesIdentity`'s value validation is
        deliberately no stricter than this class's own.
        """
        return SeriesIdentity(symbol=self.symbol, timeframe=self.timeframe)

    def closed(self) -> CandleSeries:
        """Return a new series containing only completed (closed) candles."""
        return CandleSeries(
            symbol=self.symbol,
            timeframe=self.timeframe,
            candles=tuple(c for c in self.candles if c.is_closed),
        )
