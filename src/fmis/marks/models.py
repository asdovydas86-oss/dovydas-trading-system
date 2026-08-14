"""The shapes a price snapshot is made of, and every rule they enforce.

Four types. `PriceBasis` says *how* a price was chosen; `PriceReading` is one
market's price with the provenance needed to defend it; `PriceUnavailable` is one
market's absence with the reason; `PriceSnapshot` is the frozen bundle of both.

**Why a bundle rather than a bare mapping.** A portfolio valued from a dictionary
of prices can only say *"BTCUSDT is missing"*; a portfolio valued from a snapshot
can say *"BTCUSDT was requested, the fetch failed with a transport error, the
other four are priced from 1h closes taken at 09:00Z"*. The second is what a
reader needs to decide whether to trust the total, and it costs one type.

**Every field that could be unknown is present or explicitly absent.** There is
no `None` price, no zero standing in for "we could not read it", and no reading
without a `source` — an unattributable price is a number nobody can check.

**Schema-versioned from the first line.** `to_payload`/`from_payload` round-trip
exactly, and a version this build does not write is a clean rejection rather than
a partial decode. A stored snapshot is how a valuation stays reproducible after
the provider that produced it has changed its mind, disappeared, or backfilled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

__all__ = [
    "MarksError",
    "PriceUnreadableError",
    "PriceBasis",
    "PriceReading",
    "PriceUnavailable",
    "PriceSnapshot",
    "PRICE_SNAPSHOT_SCHEMA_VERSION",
    "SUPPORTED_PRICE_SNAPSHOT_VERSIONS",
]

#: This build's price-snapshot payload version. Bumped only when the shape
#: changes, never when a value does.
PRICE_SNAPSHOT_SCHEMA_VERSION = 1

#: Versions this build can decode. A payload outside the set is refused rather
#: than read partially: a snapshot written by a newer build and decoded by
#: ignoring the fields this one does not know is a valuation missing prices it
#: cannot see it is missing.
SUPPORTED_PRICE_SNAPSHOT_VERSIONS = frozenset({1})

_ZERO = timedelta(0)


class MarksError(Exception):
    """Base class for every failure raised by this package."""


class PriceUnreadableError(MarksError, ValueError):
    """A series carried no closed candle, so no price can be read from it.

    A distinct type rather than a bare `ValueError` because the caller's correct
    response is specific: record the symbol as `PriceUnavailable` and carry on
    valuing everything else. A run that stopped because one market was
    unreadable would make a portfolio page hostage to its least liquid holding.
    """


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str, got {type(value).__name__}")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must not be blank")
    return stripped


def _utc(value: Any, name: str) -> datetime:
    """A timezone-aware, zero-offset instant. The canonical-time contract.

    Checked here rather than imported from `fmis.data`, whose implementation is a
    private module: reaching into another package's private helper is a coupling
    that survives until the day that helper moves. The rule is one line and the
    duplication is the smaller cost.
    """
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime, got {type(value).__name__}")
    offset = value.utcoffset()
    if offset is None:
        raise ValueError(f"{name} must be timezone-aware")
    if offset != _ZERO:
        raise ValueError(f"{name} must represent UTC, got offset {offset}")
    return value


def _positive_price(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    price = float(value)
    if not math.isfinite(price):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if price <= 0:
        raise ValueError(
            f"{name} must be positive, got {price}; a zero or negative price is "
            "not a cheaper market, it is a broken reading"
        )
    return price


def _count(value: Any, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {type(value).__name__}")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {value}")
    return value


class PriceBasis(Enum):
    """How a price was chosen from a series. **One member, deliberately.**

    An enum with one value is not indecision; it is the statement that the basis
    is a *choice* rather than an implicit consequence of the code. The day a
    mid-price, a volume-weighted price or a forming-bar last trade is added, it
    arrives as a second member that every stored snapshot can be read against —
    not as a silent change of meaning for prices already recorded.
    """

    #: The close of the last **closed** candle on a stated interval. A forming
    #: bar is never read, so the same history always yields the same price.
    LAST_CLOSED_CANDLE_CLOSE = "last_closed_candle_close"


@dataclass(frozen=True, slots=True)
class PriceReading:
    """One market's price, and everything needed to defend it later.

    `observed_at` is the **open** timestamp of the bar the price closed. The
    canonical `Candle` carries no close time — the provider's close time is
    consumed to decide `is_closed` and is not part of the canonical record — so
    the latest instant this package can honestly name is the bar's open. The
    consequence is stated rather than hidden: a mark's age is **overstated** by
    up to one interval, never understated, which is the safe direction for a
    staleness figure and the reason the interval travels beside it.
    """

    symbol: str
    interval: str
    price: float
    observed_at: datetime
    basis: PriceBasis
    source: str
    #: How many closed candles the series held. A price read from a one-candle
    #: series is a fact about a very thin window, and a reader is entitled to
    #: know that without re-fetching.
    closed_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _text(self.symbol, "symbol"))
        object.__setattr__(self, "interval", _text(self.interval, "interval"))
        object.__setattr__(self, "price", _positive_price(self.price, "price"))
        object.__setattr__(
            self, "observed_at", _utc(self.observed_at, "observed_at")
        )
        if not isinstance(self.basis, PriceBasis):
            raise TypeError(
                f"basis must be a PriceBasis, got {type(self.basis).__name__}"
            )
        object.__setattr__(self, "source", _text(self.source, "source"))
        object.__setattr__(
            self, "closed_count", _count(self.closed_count, "closed_count", minimum=1)
        )

    @property
    def provenance(self) -> str:
        """One line naming where this price came from and how it was chosen.

        Assembled here so every surface prints the same sentence, and so a price
        can never appear beside a shorter description that omits the basis.
        """
        return (
            f"{self.source} · {self.interval} · {self.basis.value} · "
            f"bar opened {self.observed_at.isoformat()}"
        )

    def age_at(self, moment: datetime) -> timedelta:
        """How stale this reading is at an instant — computed, never stored."""
        return _utc(moment, "moment") - self.observed_at

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "price": self.price,
            "observed_at": self.observed_at.isoformat(),
            "basis": self.basis.value,
            "source": self.source,
            "closed_count": self.closed_count,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> PriceReading:
        mapping = _mapping(raw, "price reading")
        _exact_keys(
            mapping,
            {
                "symbol",
                "interval",
                "price",
                "observed_at",
                "basis",
                "source",
                "closed_count",
            },
            "price reading",
        )
        return cls(
            symbol=str(mapping["symbol"]),
            interval=str(mapping["interval"]),
            price=mapping["price"],
            observed_at=_decode_instant(mapping["observed_at"], "observed_at"),
            basis=_decode_basis(mapping["basis"]),
            source=str(mapping["source"]),
            closed_count=mapping["closed_count"],
        )


@dataclass(frozen=True, slots=True)
class PriceUnavailable:
    """One market this snapshot was asked for and could not price, and why.

    Carried rather than dropped. *"The symbol was never requested"* and *"the
    request failed"* are different facts, and a total computed without knowing
    which one applies is a total nobody can act on.
    """

    symbol: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _text(self.symbol, "symbol"))
        object.__setattr__(self, "reason", _text(self.reason, "reason"))

    def to_payload(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "reason": self.reason}

    @classmethod
    def from_payload(cls, raw: Any) -> PriceUnavailable:
        mapping = _mapping(raw, "price unavailability")
        _exact_keys(mapping, {"symbol", "reason"}, "price unavailability")
        return cls(symbol=str(mapping["symbol"]), reason=str(mapping["reason"]))


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    """Every price one valuation rested on, frozen at one instant.

    **A symbol appears exactly once**, in `readings` or in `unavailable` and
    never in both. Two answers for one market would let a reader pick the one
    they preferred, which is the same rule `MarketSnapshot` states for a
    timeframe role.

    **No reading may be dated after the snapshot.** A price from the snapshot's
    own future is not a price; it is a clock problem, and catching it here is
    cheaper than explaining a negative staleness on a page.
    """

    taken_at: datetime
    source: str
    basis: PriceBasis
    readings: tuple[PriceReading, ...] = ()
    unavailable: tuple[PriceUnavailable, ...] = ()
    schema_version: int = PRICE_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "taken_at", _utc(self.taken_at, "taken_at"))
        object.__setattr__(self, "source", _text(self.source, "source"))
        if not isinstance(self.basis, PriceBasis):
            raise TypeError(
                f"basis must be a PriceBasis, got {type(self.basis).__name__}"
            )
        object.__setattr__(self, "readings", _tuple_of(self.readings, PriceReading))
        object.__setattr__(
            self, "unavailable", _tuple_of(self.unavailable, PriceUnavailable)
        )
        if self.schema_version not in SUPPORTED_PRICE_SNAPSHOT_VERSIONS:
            raise ValueError(
                f"price snapshot schema_version {self.schema_version} is not one "
                f"this build writes ({sorted(SUPPORTED_PRICE_SNAPSHOT_VERSIONS)})"
            )
        seen: set[str] = set()
        for entry in (*self.readings, *self.unavailable):
            if entry.symbol in seen:
                raise ValueError(
                    f"{entry.symbol} appears twice in one price snapshot; one "
                    "market has one price or one reason, never both and never two"
                )
            seen.add(entry.symbol)
        for reading in self.readings:
            if reading.observed_at > self.taken_at:
                raise ValueError(
                    f"the reading for {reading.symbol} is dated "
                    f"{reading.observed_at.isoformat()}, after the snapshot was "
                    f"taken at {self.taken_at.isoformat()}; a price from the "
                    "future is a clock problem, not a price"
                )
            if reading.basis is not self.basis:
                raise ValueError(
                    f"the reading for {reading.symbol} was chosen on "
                    f"{reading.basis.value} and this snapshot states "
                    f"{self.basis.value}; one snapshot has one basis, or the "
                    "prices in it are not comparable"
                )

    # -- projections, computed and never stored ------------------------------

    @property
    def is_empty(self) -> bool:
        """No price was read. **Not** the same as no price being asked for."""
        return not self.readings

    @property
    def requested_count(self) -> int:
        return len(self.readings) + len(self.unavailable)

    @property
    def priced_symbols(self) -> tuple[str, ...]:
        return tuple(reading.symbol for reading in self.readings)

    @property
    def unpriced_symbols(self) -> tuple[str, ...]:
        return tuple(entry.symbol for entry in self.unavailable)

    def reading_for(self, symbol: str) -> PriceReading | None:
        """One market's reading, or `None` when this snapshot has no price for it.

        `None` rather than a raise, because "not priced" is an ordinary outcome
        every caller must handle; the *reason* is what `reason_for` returns.
        """
        wanted = _text(symbol, "symbol")
        for reading in self.readings:
            if reading.symbol == wanted:
                return reading
        return None

    def reason_for(self, symbol: str) -> str | None:
        """Why one market has no price, or `None` if it was never asked for.

        Two distinct absences, kept distinct: a recorded failure and a symbol
        outside this snapshot's scope are different facts about a portfolio.
        """
        wanted = _text(symbol, "symbol")
        for entry in self.unavailable:
            if entry.symbol == wanted:
                return entry.reason
        return None

    def oldest_reading(self) -> PriceReading | None:
        """The reading a total's staleness is bounded by, or `None` if none.

        A portfolio is only as fresh as its stalest mark, so the figure a page
        should print is this one rather than an average — an average staleness
        makes one six-hour-old holding disappear behind nine fresh ones.
        """
        if not self.readings:
            return None
        oldest = self.readings[0]
        for reading in self.readings[1:]:
            if reading.observed_at < oldest.observed_at:
                oldest = reading
        return oldest

    # -- serialization -------------------------------------------------------

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "taken_at": self.taken_at.isoformat(),
            "source": self.source,
            "basis": self.basis.value,
            "readings": [reading.to_payload() for reading in self.readings],
            "unavailable": [entry.to_payload() for entry in self.unavailable],
        }

    @classmethod
    def from_payload(cls, raw: Any) -> PriceSnapshot:
        mapping = _mapping(raw, "price snapshot")
        _exact_keys(
            mapping,
            {
                "schema_version",
                "taken_at",
                "source",
                "basis",
                "readings",
                "unavailable",
            },
            "price snapshot",
        )
        version = mapping["schema_version"]
        if version not in SUPPORTED_PRICE_SNAPSHOT_VERSIONS:
            raise ValueError(
                f"price snapshot schema_version {version!r} is not one this build "
                f"can read ({sorted(SUPPORTED_PRICE_SNAPSHOT_VERSIONS)}); it was "
                "written by a newer build, and decoding it while ignoring what "
                "this build does not know would drop prices silently"
            )
        return cls(
            taken_at=_decode_instant(mapping["taken_at"], "taken_at"),
            source=str(mapping["source"]),
            basis=_decode_basis(mapping["basis"]),
            readings=tuple(
                PriceReading.from_payload(item)
                for item in _array(mapping["readings"], "readings")
            ),
            unavailable=tuple(
                PriceUnavailable.from_payload(item)
                for item in _array(mapping["unavailable"], "unavailable")
            ),
            schema_version=version,
        )


def _mapping(raw: Any, entity: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError(f"{entity} must be a mapping, got {type(raw).__name__}")
    return raw


def _array(raw: Any, entity: str) -> list[Any]:
    if not isinstance(raw, list):
        raise TypeError(f"{entity} must be a list, got {type(raw).__name__}")
    return raw


def _exact_keys(mapping: dict[str, Any], expected: set[str], entity: str) -> None:
    present = set(mapping)
    missing = expected - present
    unknown = present - expected
    if missing or unknown:
        raise ValueError(
            f"{entity} payload is not this build's shape: "
            f"missing {sorted(missing)}, unknown {sorted(unknown)}"
        )


def _decode_instant(raw: Any, name: str) -> datetime:
    if not isinstance(raw, str):
        raise TypeError(f"{name} must be an ISO-8601 str, got {type(raw).__name__}")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware, got {raw!r}")
    return parsed.astimezone(timezone.utc)


def _decode_basis(raw: Any) -> PriceBasis:
    try:
        return PriceBasis(raw)
    except ValueError as error:
        raise ValueError(
            f"price basis {raw!r} is not one this build knows "
            f"({sorted(member.value for member in PriceBasis)}); an unknown basis "
            "is a clean rejection, because a price chosen a way this build cannot "
            "describe is not comparable with one it can"
        ) from error


def _tuple_of(values: Any, expected: type) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        raise TypeError(f"expected an iterable of {expected.__name__}")
    items = tuple(values)
    for item in items:
        if not isinstance(item, expected):
            raise TypeError(
                f"expected {expected.__name__} values, got {type(item).__name__}"
            )
    return items
