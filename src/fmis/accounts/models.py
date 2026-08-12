"""Where an event happened, and which discipline it belongs to.

Four types, and `AP` §27's constraint is the line every one of them is written
against: *"Reference data stays minimal. `Market` and `Account` are identifiers
with attributes, not a registry with lifecycle management."*

So this package deliberately holds **identifiers**, not a registry. `MarketId`,
`AccountId` and `VenueId` are validated, typed, comparable references; the
`Asset` / `Market` / `Venue` / `Account` / `Custody` *records* — Family A of the
data model, with their config-event folds and their `retired_at` fields — are not
built here, because nothing in this milestone reads them and a registry that must
be kept current for every venue is exactly what §8.1 declines to build.

`Book` is the exception and is a full type, because it is a closed four-member
set that every economic event must name and that **may never be inferred**.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fmis.money import AssetCode
from fmis.records import (
    IDENTIFIER_PATTERN,
    DomainValidationError,
    PayloadDecodeError,
    TradeDomainError,
    require_pattern,
    require_text,
)

__all__ = [
    "AccountsError",
    "Book",
    "BOOK_ORDER",
    "DEFAULT_EXCLUDED_BOOKS",
    "MarketMode",
    "VenueId",
    "AccountId",
    "MarketId",
    "OwnerContext",
]


class AccountsError(TradeDomainError):
    """Base class for every accounts and reference-identifier failure."""


class Book(Enum):
    """Which discipline an event belongs to. **Books never share capacity.**

    `AP` §5.5's four members, closed. Adding a fifth is an enum extension and
    therefore a capture-schema version bump, with an unknown member a clean
    rejection — never a silent default.

    Named on every economic event at record time and **never inferred**. Moving a
    position between books is structurally unrepresentable, because it would
    silently move risk between two capacity pools.
    """

    INVESTING = "investing"
    SWING = "swing"
    DAY = "day"
    PAPER = "paper"


#: Reporting order, from the longest horizon to the shortest, with the
#: non-economic book last. Never enum definition order by accident.
BOOK_ORDER: tuple[Book, ...] = (Book.INVESTING, Book.SWING, Book.DAY, Book.PAPER)

#: What an aggregate excludes unless a caller explicitly asks for it. `PAPER` is
#: excluded because *paper and live contamination* (`AP` R12) is detectable only
#: if every aggregate states which books it covers and the default is the honest
#: one.
DEFAULT_EXCLUDED_BOOKS: frozenset[Book] = frozenset({Book.PAPER})


class MarketMode(Enum):
    """Spot, perpetual, margin or dated — and it is part of identity, not decor.

    A perpetual position accrues funding, can be liquidated, and has different tax
    treatment from spot. Three event kinds behave differently based on it, so a
    field that changes which events are legal is identity. Merging a perpetual and
    a spot pair on the same symbols makes funding fees unattributable.
    """

    SPOT = "spot"
    PERPETUAL = "perpetual"
    MARGIN = "margin"
    FUTURES_DATED = "futures_dated"


@dataclass(frozen=True, slots=True, order=True)
class VenueId:
    """Where an event happened, and who the counterparty risk is against."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "value", require_pattern(self.value, IDENTIFIER_PATTERN, "venue id")
        )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class AccountId:
    """One place balances actually sit — a sub-account, a wallet, a bank account.

    A *wallet* is not a separate concept: it is an account whose venue is
    self-custody. Modelling wallets separately would produce two objects with the
    same balance semantics and two places to fold.

    No private key, seed phrase, address-with-balance or API secret is a field on
    this type or on any other type in this domain, and none ever will be
    (`SPEC` §20).
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "value", require_pattern(self.value, IDENTIFIER_PATTERN, "account id")
        )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class MarketId:
    """One tradeable pair at one venue in one mode.

    The thing a `Trade`, a `Position` and a market snapshot are all *about*.

    **There is no `parse` from the rendered string, and that is deliberate.**
    `AP` §8.2 renders the identity as `{venue}:{base}{quote}:{mode}`, and
    `BTCUSDT` cannot be split back into base and quote without an asset registry
    this package declines to hold — `BTCU`/`SDT` is a legal reading of the same
    characters. So the rendered form is what a record *cites* and a surface shows;
    the four components are the identity, and `from_payload` reads them
    separately. Guessing the split would be an invented fact in the one place the
    whole domain is keyed on.
    """

    venue: VenueId
    base_asset: AssetCode
    quote_asset: AssetCode
    mode: MarketMode

    def __post_init__(self) -> None:
        if not isinstance(self.venue, VenueId):
            object.__setattr__(self, "venue", VenueId(require_text(self.venue, "venue")))
        if not isinstance(self.base_asset, AssetCode):
            object.__setattr__(self, "base_asset", AssetCode(self.base_asset))
        if not isinstance(self.quote_asset, AssetCode):
            object.__setattr__(self, "quote_asset", AssetCode(self.quote_asset))
        if not isinstance(self.mode, MarketMode):
            raise TypeError(
                f"mode must be a MarketMode, got {type(self.mode).__name__}; it has "
                "no default, because a perpetual and a spot pair on the same "
                "symbols are two markets"
            )
        if self.base_asset == self.quote_asset:
            raise DomainValidationError(
                f"base and quote asset are both {self.base_asset}; a market "
                "exchanges one asset for another"
            )

    @property
    def value(self) -> str:
        """`{venue}:{base}{quote}:{mode}` — the citation form (`AP` §8.2)."""
        return (
            f"{self.venue}:{self.base_asset}{self.quote_asset}:{self.mode.value}"
        )

    @property
    def pair_symbol(self) -> str:
        """`BTCUSDT` — the venue-facing symbol, for reaching the market half."""
        return f"{self.base_asset}{self.quote_asset}"

    def __str__(self) -> str:
        return self.value

    def to_payload(self) -> dict[str, Any]:
        return {
            "venue": self.venue.value,
            "base_asset": self.base_asset.code,
            "quote_asset": self.quote_asset.code,
            "mode": self.mode.value,
        }

    @classmethod
    def from_payload(cls, raw: Any, name: str = "market") -> MarketId:
        if not isinstance(raw, Mapping):
            raise PayloadDecodeError(
                f"{name} must be a JSON object, got {type(raw).__name__}"
            )
        expected = {"venue", "base_asset", "quote_asset", "mode"}
        if set(raw) != expected:
            raise PayloadDecodeError(f"{name} keys {sorted(raw)} != {sorted(expected)}")
        try:
            mode = MarketMode(raw["mode"])
        except ValueError as error:
            raise PayloadDecodeError(
                f"{name} mode {raw['mode']!r} is not a known MarketMode"
            ) from error
        return cls(
            venue=VenueId(str(raw["venue"])),
            base_asset=AssetCode(str(raw["base_asset"])),
            quote_asset=AssetCode(str(raw["quote_asset"])),
            mode=mode,
        )


_ROUTINE_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass(frozen=True, slots=True)
class OwnerContext:
    """Who and where the owner is — for presentation and calendar boundaries only.

    **ADR-0001 is untouched: UTC stays canonical for storage.** This record exists
    because `AP` §20.3 requires time-of-day and weekday cohorts, and a "daily loss
    limit" measured on UTC days for a Stockholm-based owner would reset in the
    middle of his evening. The owner-local date is computed at *read time* from the
    stored UTC instant plus this context, and is never a stored field — which is
    the only version of it that survives the owner relocating.

    `display_timezone` is deliberately a different field from `tax_period_timezone`.
    They coincide today and diverge the moment the owner relocates while remaining
    Swedish-taxed.
    """

    display_timezone: str
    base_currency: AssetCode
    tax_period_timezone: str
    routine_times: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("display_timezone", "tax_period_timezone"):
            value = require_text(getattr(self, name), name)
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as error:
                raise DomainValidationError(
                    f"{name} {value!r} is not a valid IANA time zone"
                ) from error
            object.__setattr__(self, name, value)
        if not isinstance(self.base_currency, AssetCode):
            object.__setattr__(self, "base_currency", AssetCode(self.base_currency))
        if not isinstance(self.routine_times, tuple):
            raise TypeError("routine_times must be a tuple of 'HH:MM' str")
        times = []
        for position, moment in enumerate(self.routine_times):
            text = require_text(moment, f"routine_times[{position}]")
            if not _ROUTINE_TIME_PATTERN.fullmatch(text):
                raise DomainValidationError(
                    f"routine_times[{position}] {text!r} must be 'HH:MM' in the "
                    "owner's display timezone"
                )
            times.append(text)
        if len(set(times)) != len(times):
            raise DomainValidationError("routine_times must not repeat a time")
        object.__setattr__(self, "routine_times", tuple(sorted(times)))

    @property
    def display_zone(self) -> ZoneInfo:
        return ZoneInfo(self.display_timezone)

    def local_date(self, moment: Any) -> str:
        """The owner-local calendar date of a UTC instant, as `YYYY-MM-DD`.

        A **projection**, computed here and stored nowhere. Every period boundary
        in `fmis.risk` resolves through this method for exactly that reason.
        """
        from datetime import datetime  # local: keeps the module import list honest

        if not isinstance(moment, datetime):
            raise TypeError(f"moment must be a datetime, got {type(moment).__name__}")
        if moment.tzinfo is None:
            raise DomainValidationError(
                "moment must be timezone-aware; a naive instant has no local date"
            )
        return moment.astimezone(self.display_zone).date().isoformat()

    def to_payload(self) -> dict[str, Any]:
        return {
            "display_timezone": self.display_timezone,
            "base_currency": self.base_currency.code,
            "tax_period_timezone": self.tax_period_timezone,
            "routine_times": list(self.routine_times),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> OwnerContext:
        if not isinstance(raw, Mapping):
            raise PayloadDecodeError(
                f"owner context must be a JSON object, got {type(raw).__name__}"
            )
        expected = {
            "display_timezone",
            "base_currency",
            "tax_period_timezone",
            "routine_times",
        }
        if set(raw) != expected:
            raise PayloadDecodeError(
                f"owner context keys {sorted(raw)} != {sorted(expected)}"
            )
        routine = raw["routine_times"]
        if not isinstance(routine, list):
            raise PayloadDecodeError("owner context routine_times must be an array")
        return cls(
            display_timezone=str(raw["display_timezone"]),
            base_currency=AssetCode(str(raw["base_currency"])),
            tax_period_timezone=str(raw["tax_period_timezone"]),
            routine_times=tuple(str(item) for item in routine),
        )
