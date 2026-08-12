"""`DecisionWindow` — the bounded closed-candle series a frozen figure used.

**BG-D8.** `AP` §25.3 states that MAE/MFE *must* be computed at close rather than
lazily, *"because kline history is not permanent and instruments get delisted."*
But nothing records **which** candles a frozen excursion figure was computed over,
so the figure becomes unverifiable the moment the history moves.

Two modes, and the choice is per artifact rather than global:

* **reference** — market, interval, first and last close, bar count, series
  digest. Makes a later figure checkable *if the data still exists*.
* **capture** — the same, plus the OHLCV rows themselves. Makes it checkable
  forever.

The size arithmetic, stated rather than assumed: 200 closed candles per role ×
3 roles at ~120 bytes ≈ **72 KB per decision**. Against ~15,000 proposals over a
decade that is ~1.1 GB; against ~2,000 *accepted* decisions and closed positions
it is ~144 MB. The data model's recommendation — capture on the decision chain
that reached a plan or a position, reference everywhere else — buys the
"what did this trade look like" capability at ~4 % of the cost of capturing
everything. **This module implements both and chooses neither.**

**Identity is the reference fields, never the rows.** `window_id` is derived from
market, interval, bounds, count and `series_digest` — and `series_digest` already
covers the rows. So a captured window and its pruned reference form share one id,
which is what makes pruning a documented *downgrade* of one record rather than a
silent replacement by a different one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fmis.accounts import MarketId
from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.money import canonical_decimal_text, parse_decimal
from fmis.provenance import Absent, decode_maybe, encode_maybe
from fmis.records import (
    DomainValidationError,
    PayloadDecodeError,
    RecordAudit,
    build_domain_record_id,
    content_digest_over,
    require_exact_keys,
    require_int,
    require_mapping,
    require_member,
    require_payload_version,
    require_text,
    require_tuple_of,
    require_unmodified,
    require_utc,
)
from fmis.versioning import VersionSet

__all__ = [
    "DECISION_WINDOW_SCHEMA_VERSION",
    "SUPPORTED_DECISION_WINDOW_VERSIONS",
    "DECISION_WINDOW_TYPE_SLUG",
    "DECISION_WINDOW_KIND",
    "WindowMode",
    "WindowBar",
    "DecisionWindow",
    "series_digest_of",
]

DECISION_WINDOW_SCHEMA_VERSION = 1
SUPPORTED_DECISION_WINDOW_VERSIONS = frozenset({1})
DECISION_WINDOW_TYPE_SLUG = "decision_window"
DECISION_WINDOW_KIND = "decision_window"


class WindowMode(Enum):
    """Whether the rows are here, or only the reference to them."""

    REFERENCE = "reference"
    CAPTURE = "capture"


@dataclass(frozen=True, slots=True)
class WindowBar:
    """One closed candle, exact.

    Exact rather than `float` because this is a *stored* value inside a captured
    artifact whose digest is its identity — the same reason every amount in the
    domain is exact. The market half keeps `float`; the conversion happens once at
    the composition root through `exact_from_market_price`.
    """

    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "close_time", require_utc(self.close_time, "close_time")
        )
        for name in ("open", "high", "low", "close", "volume"):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
            object.__setattr__(self, name, Decimal(canonical_decimal_text(value)))
        for name in ("open", "high", "low", "close"):
            if getattr(self, name) <= 0:
                raise DomainValidationError(
                    f"{name} must be positive, got {getattr(self, name)}"
                )
        if self.volume < 0:
            raise DomainValidationError(f"volume cannot be negative, got {self.volume}")
        if self.high < self.low:
            raise DomainValidationError(
                f"high {self.high} is below low {self.low}; this is not a candle"
            )
        if self.high < max(self.open, self.close) or self.low > min(
            self.open, self.close
        ):
            raise DomainValidationError(
                f"high/low {self.high}/{self.low} do not contain open/close "
                f"{self.open}/{self.close}"
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "close_time": encode_timestamp(self.close_time),
            "open": canonical_decimal_text(self.open),
            "high": canonical_decimal_text(self.high),
            "low": canonical_decimal_text(self.low),
            "close": canonical_decimal_text(self.close),
            "volume": canonical_decimal_text(self.volume),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> WindowBar:
        if not isinstance(raw, Mapping):
            raise PayloadDecodeError(
                f"bar must be a JSON object, got {type(raw).__name__}"
            )
        expected = {"close_time", "open", "high", "low", "close", "volume"}
        if set(raw) != expected:
            raise PayloadDecodeError(f"bar keys {sorted(raw)} != {sorted(expected)}")
        return cls(
            close_time=decode_timestamp(raw["close_time"]),
            open=parse_decimal(raw["open"], "open"),
            high=parse_decimal(raw["high"], "high"),
            low=parse_decimal(raw["low"], "low"),
            close=parse_decimal(raw["close"], "close"),
            volume=parse_decimal(raw["volume"], "volume"),
        )


def series_digest_of(bars: tuple[WindowBar, ...]) -> str:
    """`sha256:<hex>` over the canonical encoding of an ordered bar series.

    The digest algorithm is frozen with the canonical encoder, so a window
    captured in 2026 and one referenced in 2031 are comparable byte for byte.
    """
    require_tuple_of(bars, WindowBar, "bars")
    return content_digest_over({"bars": [bar.to_payload() for bar in bars]})


@dataclass(frozen=True, slots=True)
class DecisionWindow:
    """The candles a frozen computation used, identified and optionally contained."""

    market: MarketId
    interval: str
    first_close_time: datetime
    last_close_time: datetime
    bar_count: int
    series_digest: str
    mode: WindowMode
    version_set: VersionSet
    audit: RecordAudit
    bars: tuple[WindowBar, ...] = ()
    pruned_at: datetime | Absent = Absent("not pruned")
    schema_version: int = DECISION_WINDOW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.market, MarketId):
            raise TypeError(f"market must be a MarketId, got {type(self.market).__name__}")
        object.__setattr__(self, "interval", require_text(self.interval, "interval"))
        object.__setattr__(
            self,
            "first_close_time",
            require_utc(self.first_close_time, "first_close_time"),
        )
        object.__setattr__(
            self, "last_close_time", require_utc(self.last_close_time, "last_close_time")
        )
        require_int(self.bar_count, "bar_count", minimum=1)
        object.__setattr__(
            self, "series_digest", require_text(self.series_digest, "series_digest")
        )
        if not self.series_digest.startswith("sha256:") or len(
            self.series_digest
        ) != len("sha256:") + 64:
            raise DomainValidationError(
                f"series_digest must be a 'sha256:<64 hex>' string, got "
                f"{self.series_digest!r}"
            )
        require_member(self.mode, WindowMode, "mode")
        if not isinstance(self.version_set, VersionSet):
            raise TypeError("version_set must be a VersionSet")
        require_unmodified(self.audit, "DecisionWindow")
        require_tuple_of(self.bars, WindowBar, "bars")
        if not isinstance(self.pruned_at, Absent):
            object.__setattr__(
                self, "pruned_at", require_utc(self.pruned_at, "pruned_at")
            )
        if self.last_close_time < self.first_close_time:
            raise DomainValidationError(
                f"last_close_time {self.last_close_time.isoformat()} precedes "
                f"first_close_time {self.first_close_time.isoformat()}"
            )
        if self.schema_version not in SUPPORTED_DECISION_WINDOW_VERSIONS:
            raise DomainValidationError(
                f"decision window schema_version {self.schema_version} is not one "
                f"this build writes ({sorted(SUPPORTED_DECISION_WINDOW_VERSIONS)})"
            )
        if self.mode is WindowMode.CAPTURE:
            self._validate_capture()
        else:
            if self.bars:
                raise DomainValidationError(
                    "a reference-mode window holds no rows; a window that carries "
                    "rows is in capture mode and must say so"
                )
        if not isinstance(self.pruned_at, Absent) and self.mode is WindowMode.CAPTURE:
            raise DomainValidationError(
                "a pruned window is in reference mode; pruning is the documented "
                "downgrade from capture, not a state a captured window can hold"
            )

    def _validate_capture(self) -> None:
        if len(self.bars) != self.bar_count:
            raise DomainValidationError(
                f"bar_count {self.bar_count} disagrees with the {len(self.bars)} "
                "rows actually captured"
            )
        previous: datetime | None = None
        for position, bar in enumerate(self.bars):
            if previous is not None and bar.close_time <= previous:
                raise DomainValidationError(
                    f"bars[{position}] closes at {bar.close_time.isoformat()}, at "
                    f"or before bars[{position - 1}]; a candle series is strictly "
                    "ordered by close"
                )
            previous = bar.close_time
        if self.bars[0].close_time != self.first_close_time:
            raise DomainValidationError(
                "first_close_time disagrees with the first captured row"
            )
        if self.bars[-1].close_time != self.last_close_time:
            raise DomainValidationError(
                "last_close_time disagrees with the last captured row"
            )
        computed = series_digest_of(self.bars)
        if computed != self.series_digest:
            raise DomainValidationError(
                f"series_digest {self.series_digest} does not match the digest of "
                f"the rows it claims to cover ({computed})"
            )

    @property
    def identity_basis(self) -> dict[str, Any]:
        """The reference fields, and nothing else. The rows are covered by the digest."""
        return {
            "market": self.market.to_payload(),
            "interval": self.interval,
            "first_close_time": encode_timestamp(self.first_close_time),
            "last_close_time": encode_timestamp(self.last_close_time),
            "bar_count": self.bar_count,
            "series_digest": self.series_digest,
        }

    @property
    def window_id(self) -> str:
        return build_domain_record_id(
            type_slug=DECISION_WINDOW_TYPE_SLUG,
            subject=self.market.value,
            moment=self.last_close_time,
            digest=content_digest_over(self.identity_basis),
        )

    @property
    def is_verifiable_offline(self) -> bool:
        """Whether a later reviewer can recompute without refetching history."""
        return self.mode is WindowMode.CAPTURE

    def prune(self, moment: datetime) -> DecisionWindow:
        """Drop the rows, keep the reference. A downgrade, never a deletion.

        The metadata, the bounds and the digest stay forever, so a reader always
        learns that the rows existed and what they hashed to. `window_id` is
        unchanged, which is the whole point.
        """
        if self.mode is WindowMode.REFERENCE:
            raise DomainValidationError(
                "this window is already in reference mode; there is nothing to prune"
            )
        return DecisionWindow(
            market=self.market,
            interval=self.interval,
            first_close_time=self.first_close_time,
            last_close_time=self.last_close_time,
            bar_count=self.bar_count,
            series_digest=self.series_digest,
            mode=WindowMode.REFERENCE,
            version_set=self.version_set,
            audit=self.audit,
            bars=(),
            pruned_at=moment,
            schema_version=self.schema_version,
        )

    def to_payload(self) -> dict[str, Any]:
        payload = self.identity_basis
        payload.update(
            {
                "schema_version": self.schema_version,
                "window_id": self.window_id,
                "mode": self.mode.value,
                "version_set": self.version_set.to_payload(),
                "audit": self.audit.to_payload(),
                "bars": [bar.to_payload() for bar in self.bars],
                "pruned_at": encode_maybe(self.pruned_at, encode_timestamp),
            }
        )
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> DecisionWindow:
        mapping = require_mapping(raw, "decision window")
        version = require_payload_version(
            mapping,
            supported=SUPPORTED_DECISION_WINDOW_VERSIONS,
            entity="decision window",
        )
        require_exact_keys(
            mapping,
            {
                "schema_version",
                "window_id",
                "market",
                "interval",
                "first_close_time",
                "last_close_time",
                "bar_count",
                "series_digest",
                "mode",
                "version_set",
                "audit",
                "bars",
                "pruned_at",
            },
            "decision window",
        )
        raw_bars = mapping["bars"]
        if not isinstance(raw_bars, list):
            raise PayloadDecodeError("decision window bars must be a JSON array")
        try:
            mode = WindowMode(mapping["mode"])
        except ValueError as error:
            raise PayloadDecodeError(
                f"decision window mode {mapping['mode']!r} is not a known WindowMode"
            ) from error
        decoded = cls(
            market=MarketId.from_payload(mapping["market"], "decision window market"),
            interval=str(mapping["interval"]),
            first_close_time=decode_timestamp(mapping["first_close_time"]),
            last_close_time=decode_timestamp(mapping["last_close_time"]),
            bar_count=mapping["bar_count"],
            series_digest=str(mapping["series_digest"]),
            mode=mode,
            version_set=VersionSet.from_payload(mapping["version_set"]),
            audit=RecordAudit.from_payload(mapping["audit"]),
            bars=tuple(WindowBar.from_payload(item) for item in raw_bars),
            pruned_at=decode_maybe(mapping["pruned_at"], decode_timestamp),
            schema_version=version,
        )
        if mapping["window_id"] != decoded.window_id:
            raise PayloadDecodeError(
                f"window_id {mapping['window_id']!r} does not match the digest of "
                f"the window it claims to identify ({decoded.window_id!r})"
            )
        return decoded
