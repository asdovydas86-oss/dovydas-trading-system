"""Exact, asset-tagged money and quantity.

`AP` §5.3 and the investigation's Option C, implemented:

> **Every asserted money and quantity value is stored as canonical decimal text
> and preserved exactly, forever. Money sums are computed in `Decimal`. No
> quotient is ever a stored field.**

Three rules follow, and every entity card in the domain rests on them.

**There is no bare number.** A monetary field is always a pair `(amount, asset)`.
A field named `price` without an asset is a modelling error, and arithmetic
between two amounts in different assets raises rather than converting silently —
a conversion needs a dated rate with its own provenance, which is a decision, not
an implicit cast.

**The canonical text is part of identity.** `Decimal("0.10")` and `Decimal("0.1")`
are equal as values and produce *different* canonical bytes and therefore
different SHA-256 digests against this repository's own `canonical_dumps`. Since
`event_id` is derived from that digest, two spellings of one amount would be two
events. Canonicalizing at construction is what makes re-entering a fill after a
crash an idempotent success.

**`float` never crosses into an exact value.** Binary floating point cannot
represent `0.1`; three buys closed by three sells leave ~`1e-17` residue, and
under "flat means zero" that position never closes, never becomes an episode, and
quietly biases every aggregate. The market half keeps `float` (ADR-0013 §4 is
untouched); the conversion happens once, explicitly, at the record boundary via
`exact_from_market_price`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext
from typing import Any

from fmis.records import (
    DomainValidationError,
    PayloadDecodeError,
    TradeDomainError,
    require_int,
    require_text,
)

__all__ = [
    "MoneyError",
    "AssetMismatchError",
    "ASSET_CODE_PATTERN",
    "AssetCode",
    "canonical_decimal_text",
    "parse_decimal",
    "exact_from_market_price",
    "Money",
    "Quantity",
    "sum_money",
    "DustPolicy",
]

#: `AP` §8.1's rule, unchanged. A second asset with the same code and a different
#: kind is a rejection, never a merge; two venues calling different things `BTC`
#: is resolved by `Market` naming the venue, not by splitting the asset.
ASSET_CODE_PATTERN = re.compile(r"^[A-Z0-9]{1,20}$")

#: How many significant digits an exact amount may carry — IEEE decimal128's
#: precision. Not a policy threshold: it is the width at which the canonical form
#: stops being a faithful record of what the owner typed and starts being a
#: rounding decision, so exceeding it is a rejection rather than a silent
#: quantize.
_MAXIMUM_SIGNIFICANT_DIGITS = 34

#: **Every** decimal operation in this module runs in this context, never in the
#: ambient one. `getcontext()` is thread-local and mutable, so a caller who had
#: set `prec=6` for their own reasons would silently change what this domain
#: considers the canonical spelling of an amount — and therefore change a content
#: digest, and therefore change an `event_id`. Pinning it makes the bytes a
#: function of the values alone.
_CANONICAL_CONTEXT = Context(prec=_MAXIMUM_SIGNIFICANT_DIGITS, traps=[InvalidOperation])


class MoneyError(TradeDomainError):
    """Base class for every money and quantity failure."""


class AssetMismatchError(MoneyError, ValueError):
    """Arithmetic was attempted between two different assets.

    Its own class because the fix is never "cast": it is an explicit conversion
    carrying a dated rate and its provenance, and a caller must be able to catch
    exactly this and go find the rate.
    """


@dataclass(frozen=True, slots=True, order=True)
class AssetCode:
    """The canonical symbol of one thing that can be held or denominated in.

    A wrapper rather than a bare `str` so that `Money(amount, "BTC")` and
    `Money(amount, "btc")` cannot both exist, and so a function signature can say
    which strings it means.
    """

    code: str

    def __post_init__(self) -> None:
        text = require_text(self.code, "asset code")
        if not ASSET_CODE_PATTERN.fullmatch(text):
            raise DomainValidationError(
                f"asset code {text!r} must match {ASSET_CODE_PATTERN.pattern}; "
                "asset codes are upper-case so one asset cannot become two"
            )
        object.__setattr__(self, "code", text)

    def __str__(self) -> str:
        return self.code


def canonical_decimal_text(value: Decimal) -> str:
    """The one textual spelling of an exact amount.

    `0.10` → `0.1`, `1E+3` → `1000`, `-0` → `0`. Plain notation always, because
    exponent notation would give one value two spellings and therefore two
    digests. This function is the answer to AP-D1 Q2 and nothing else in the
    domain may produce amount text.
    """
    if not isinstance(value, Decimal):
        raise TypeError(f"amount must be a Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise DomainValidationError(
            f"amount {value!r} is not finite; NaN and Infinity are not amounts"
        )
    supplied = len(value.as_tuple().digits)
    if supplied > _MAXIMUM_SIGNIFICANT_DIGITS:
        raise DomainValidationError(
            f"amount carries {supplied} significant digits; the canonical form "
            f"holds at most {_MAXIMUM_SIGNIFICANT_DIGITS}, and rounding an "
            "asserted amount is a decision this layer will not make silently"
        )
    with localcontext(_CANONICAL_CONTEXT):
        normalized = value.normalize()
        if normalized == 0:
            return "0"
        return format(normalized, "f")


def parse_decimal(text: Any, name: str) -> Decimal:
    """Decode canonical amount text back to an exact `Decimal`.

    Rejects a JSON number as hard as it rejects a malformed string: a float in
    the serialized form would mean the writer had already lost the exact value,
    and accepting it here would hide where.
    """
    if isinstance(text, bool) or isinstance(text, (int, float)):
        raise PayloadDecodeError(
            f"{name} must be a decimal *string*, got {type(text).__name__}; a "
            "JSON number cannot carry an exact amount"
        )
    raw = require_text(text, name)
    try:
        value = Decimal(raw)
    except InvalidOperation as error:
        raise PayloadDecodeError(f"{name} {raw!r} is not a decimal") from error
    if canonical_decimal_text(value) != raw:
        raise PayloadDecodeError(
            f"{name} {raw!r} is not in canonical form "
            f"({canonical_decimal_text(value)!r}); two spellings of one amount "
            "would produce two digests"
        )
    return value


def exact_from_market_price(price: float, name: str = "price") -> Decimal:
    """The **one** `float` → exact crossing in the whole domain (AP-D1 Q3).

    A stop price originates in the level-crossing engine as a `float` and becomes a
    stored exact value. The conversion is via `repr`, which for a Python float is
    the shortest string that round-trips — so `0.1` becomes `Decimal("0.1")` and
    not `Decimal(0.1)`'s fifty-five digit expansion. Every other exact value in
    the domain is typed by the owner or read from a venue as text and never
    passes through a float at all.
    """
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        raise TypeError(f"{name} must be a float, got {type(price).__name__}")
    value = Decimal(repr(float(price)))
    if not value.is_finite():
        raise DomainValidationError(f"{name} {price!r} is not finite")
    return Decimal(canonical_decimal_text(value))


def _canonicalize(amount: Any, name: str) -> Decimal:
    if not isinstance(amount, Decimal):
        raise TypeError(
            f"{name} must be a Decimal, got {type(amount).__name__}; the trading "
            "domain never accepts a float for an exact value (AP §5.3)"
        )
    return Decimal(canonical_decimal_text(amount))


def _require_asset(asset: Any) -> AssetCode:
    if isinstance(asset, AssetCode):
        return asset
    if isinstance(asset, str):
        return AssetCode(asset)
    raise TypeError(f"asset must be an AssetCode, got {type(asset).__name__}")


@dataclass(frozen=True, slots=True)
class Money:
    """An exact amount of value, denominated in one asset.

    Signed: a fee is negative value to the owner and a proceeds line is positive,
    and forcing both through an unsigned field plus a direction flag would be two
    fields for one fact.
    """

    amount: Decimal
    asset: AssetCode

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", _canonicalize(self.amount, "amount"))
        object.__setattr__(self, "asset", _require_asset(self.asset))

    @property
    def text(self) -> str:
        """The canonical spelling — what is stored and what is digested."""
        return canonical_decimal_text(self.amount)

    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    def _same_asset(self, other: Money) -> None:
        if not isinstance(other, Money):
            raise TypeError(f"expected Money, got {type(other).__name__}")
        if self.asset != other.asset:
            raise AssetMismatchError(
                f"cannot combine {self.asset} and {other.asset} without an "
                "explicit conversion carrying a dated rate and its provenance"
            )

    def __add__(self, other: Money) -> Money:
        self._same_asset(other)
        with localcontext(_CANONICAL_CONTEXT):
            return Money(self.amount + other.amount, self.asset)

    def __sub__(self, other: Money) -> Money:
        self._same_asset(other)
        with localcontext(_CANONICAL_CONTEXT):
            return Money(self.amount - other.amount, self.asset)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.asset)

    def __abs__(self) -> Money:
        return Money(abs(self.amount), self.asset)

    def __lt__(self, other: Money) -> bool:
        self._same_asset(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._same_asset(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._same_asset(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._same_asset(other)
        return self.amount >= other.amount

    def scale(self, factor: Decimal) -> Money:
        """Multiply by an exact factor. Never by another `Money`."""
        if not isinstance(factor, Decimal):
            raise TypeError(f"factor must be a Decimal, got {type(factor).__name__}")
        with localcontext(_CANONICAL_CONTEXT):
            return Money(self.amount * factor, self.asset)

    def __str__(self) -> str:
        return f"{self.text} {self.asset}"

    def to_payload(self) -> dict[str, Any]:
        return {"amount": self.text, "asset": self.asset.code}

    @classmethod
    def from_payload(cls, raw: Any, name: str = "money") -> Money:
        mapping = _require_amount_mapping(raw, name)
        return cls(
            parse_decimal(mapping["amount"], f"{name}.amount"),
            AssetCode(str(mapping["asset"])),
        )

    @classmethod
    def zero(cls, asset: AssetCode | str) -> Money:
        return cls(Decimal(0), _require_asset(asset))


@dataclass(frozen=True, slots=True)
class Quantity:
    """An exact amount **of** an asset — units held, bought, sold or moved.

    A different type from `Money` on purpose. They are structurally identical and
    semantically incompatible: adding 0.4 BTC to 0.4 BTC of *value* is a
    category error that a shared type would let through, and the position fold
    adds quantities while the P&L fold adds money.
    """

    amount: Decimal
    asset: AssetCode

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", _canonicalize(self.amount, "amount"))
        object.__setattr__(self, "asset", _require_asset(self.asset))

    @property
    def text(self) -> str:
        return canonical_decimal_text(self.amount)

    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    def _same_asset(self, other: Quantity) -> None:
        if not isinstance(other, Quantity):
            raise TypeError(f"expected Quantity, got {type(other).__name__}")
        if self.asset != other.asset:
            raise AssetMismatchError(
                f"cannot combine quantities of {self.asset} and {other.asset}"
            )

    def __add__(self, other: Quantity) -> Quantity:
        self._same_asset(other)
        with localcontext(_CANONICAL_CONTEXT):
            return Quantity(self.amount + other.amount, self.asset)

    def __sub__(self, other: Quantity) -> Quantity:
        self._same_asset(other)
        with localcontext(_CANONICAL_CONTEXT):
            return Quantity(self.amount - other.amount, self.asset)

    def __neg__(self) -> Quantity:
        return Quantity(-self.amount, self.asset)

    def __abs__(self) -> Quantity:
        return Quantity(abs(self.amount), self.asset)

    def __lt__(self, other: Quantity) -> bool:
        self._same_asset(other)
        return self.amount < other.amount

    def __le__(self, other: Quantity) -> bool:
        self._same_asset(other)
        return self.amount <= other.amount

    def __gt__(self, other: Quantity) -> bool:
        self._same_asset(other)
        return self.amount > other.amount

    def __ge__(self, other: Quantity) -> bool:
        self._same_asset(other)
        return self.amount >= other.amount

    def scale(self, factor: Decimal) -> Quantity:
        if not isinstance(factor, Decimal):
            raise TypeError(f"factor must be a Decimal, got {type(factor).__name__}")
        with localcontext(_CANONICAL_CONTEXT):
            return Quantity(self.amount * factor, self.asset)

    def value_at(self, price: Decimal, quote_asset: AssetCode | str) -> Money:
        """`quantity × price`, producing `Money` in the quote asset.

        A multiplication, never a division: `AP` §5.3's quotient rule means the
        product may be computed and shown, while `average_entry` is a *pair* and
        never the division of one by the other.
        """
        if not isinstance(price, Decimal):
            raise TypeError(f"price must be a Decimal, got {type(price).__name__}")
        with localcontext(_CANONICAL_CONTEXT):
            return Money(self.amount * price, _require_asset(quote_asset))

    def __str__(self) -> str:
        return f"{self.text} {self.asset}"

    def to_payload(self) -> dict[str, Any]:
        return {"amount": self.text, "asset": self.asset.code}

    @classmethod
    def from_payload(cls, raw: Any, name: str = "quantity") -> Quantity:
        mapping = _require_amount_mapping(raw, name)
        return cls(
            parse_decimal(mapping["amount"], f"{name}.amount"),
            AssetCode(str(mapping["asset"])),
        )

    @classmethod
    def zero(cls, asset: AssetCode | str) -> Quantity:
        return cls(Decimal(0), _require_asset(asset))


def _require_amount_mapping(raw: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise PayloadDecodeError(
            f"{name} must be a JSON object, got {type(raw).__name__}"
        )
    if set(raw) != {"amount", "asset"}:
        raise PayloadDecodeError(
            f"{name} keys {sorted(raw)} != ['amount', 'asset']"
        )
    return raw


@dataclass(frozen=True, slots=True)
class DustPolicy:
    """Per-asset thresholds below which a residual holding counts as flat.

    A **named, versioned policy** (`AP` §5.3), not a constant, because a bump
    redraws where one position ends and the next begins — which is why
    `AP_ADR_DISCOVERY` AP-D8 rates position identity Critical and why §12.1 rule 8
    requires a captured artifact to reference an event-id set rather than a
    position's derived key.

    **An asset with no configured threshold uses exact zero.** That is not a
    chosen number: zero is the only tolerance that is not a policy decision, and
    inventing one here would violate the rule that this layer names policy
    parameters and chooses none.
    """

    policy_id: str
    version: int
    thresholds: tuple[tuple[AssetCode, Decimal], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", require_text(self.policy_id, "policy_id"))
        require_int(self.version, "version", minimum=1)
        if not isinstance(self.thresholds, tuple):
            raise TypeError("thresholds must be a tuple of (AssetCode, Decimal)")
        seen: set[str] = set()
        normalized: list[tuple[AssetCode, Decimal]] = []
        for position, entry in enumerate(self.thresholds):
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError(
                    f"thresholds[{position}] must be an (AssetCode, Decimal) pair"
                )
            asset = _require_asset(entry[0])
            threshold = _canonicalize(entry[1], f"thresholds[{position}] threshold")
            if threshold < 0:
                raise DomainValidationError(
                    f"dust threshold for {asset} cannot be negative, got {threshold}"
                )
            if asset.code in seen:
                raise DomainValidationError(
                    f"asset {asset} has two dust thresholds; one fact, one value"
                )
            seen.add(asset.code)
            normalized.append((asset, threshold))
        object.__setattr__(self, "thresholds", tuple(sorted(normalized, key=lambda e: e[0].code)))

    def threshold_for(self, asset: AssetCode | str) -> Decimal:
        wanted = _require_asset(asset)
        for candidate, threshold in self.thresholds:
            if candidate == wanted:
                return threshold
        return Decimal(0)

    def is_dust(self, quantity: Quantity) -> bool:
        """Whether a residual holding is close enough to zero to be flat."""
        if not isinstance(quantity, Quantity):
            raise TypeError(
                f"quantity must be a Quantity, got {type(quantity).__name__}"
            )
        return abs(quantity.amount) <= self.threshold_for(quantity.asset)

    def to_payload(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "thresholds": [
                {"asset": asset.code, "threshold": canonical_decimal_text(threshold)}
                for asset, threshold in self.thresholds
            ],
        }

    @classmethod
    def from_payload(cls, raw: Any) -> DustPolicy:
        if not isinstance(raw, Mapping):
            raise PayloadDecodeError(
                f"dust policy must be a JSON object, got {type(raw).__name__}"
            )
        if set(raw) != {"policy_id", "version", "thresholds"}:
            raise PayloadDecodeError(
                f"dust policy keys {sorted(raw)} != "
                "['policy_id', 'thresholds', 'version']"
            )
        raw_thresholds = raw["thresholds"]
        if not isinstance(raw_thresholds, list):
            raise PayloadDecodeError("dust policy thresholds must be a JSON array")
        entries: list[tuple[AssetCode, Decimal]] = []
        for item in raw_thresholds:
            if not isinstance(item, Mapping) or set(item) != {"asset", "threshold"}:
                raise PayloadDecodeError(
                    "dust threshold entries must be {'asset', 'threshold'} objects"
                )
            entries.append(
                (
                    AssetCode(str(item["asset"])),
                    parse_decimal(item["threshold"], "dust threshold"),
                )
            )
        return cls(
            policy_id=str(raw["policy_id"]),
            version=raw["version"],
            thresholds=tuple(entries),
        )


def sum_money(amounts: Iterable[Money], *, asset: AssetCode | str) -> Money:
    """Sum in `Decimal`, in one named asset, starting from an explicit zero.

    The explicit asset is what makes summing an empty sequence well defined —
    `sum([])` would be `0` with no asset, which is exactly the bare number §4.3
    says does not exist in this domain.
    """
    total = Money.zero(asset)
    for amount in amounts:
        total = total + amount
    return total
