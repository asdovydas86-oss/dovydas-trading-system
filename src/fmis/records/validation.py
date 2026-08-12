"""Shared field validators — written once so thirteen packages cannot disagree.

Every helper here raises `DomainValidationError` (a `ValueError`) or `TypeError`
following the convention already established across the repository: a wrong
*type* is a `TypeError`, a wrong *value* is the package's own input error.

**Timestamps are normalized to UTC, not merely required to be aware.** ADR-0001
makes UTC canonical for storage; content-derived identity makes the point sharp.
`2026-08-12T09:00:00+02:00` and `2026-08-12T07:00:00+00:00` are the same instant,
and if both were storable the same fill re-entered from two clients would produce
two digests and therefore two events. Normalizing at construction makes two
spellings of one instant one value — the same reasoning `AP_ADR_DISCOVERY` AP-D7
applies to two spellings of one amount.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, TypeVar

from fmis.records.errors import DomainValidationError

__all__ = [
    "require_text",
    "require_optional_text",
    "require_utc",
    "require_optional_utc",
    "require_int",
    "require_bool",
    "require_member",
    "require_tuple_of",
    "require_pattern",
    "require_ordered",
    "IDENTIFIER_PATTERN",
    "SLUG_PATTERN",
]

T = TypeVar("T")

#: A declared identifier the owner types at a CLI (§4.1, "Declared" scheme).
#: Lowercase, because a scheme that accepts `Swing` and `swing` as two portfolios
#: is a collision waiting to be reported as a bug.
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

#: A record-id component. Narrow on purpose: these are joined onto filesystem
#: paths downstream, so the pattern carries the path-traversal defence.
SLUG_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,32}$")


def require_text(value: Any, name: str) -> str:
    """A non-empty string, returned stripped of surrounding whitespace.

    Stripping is deliberate and is a normalization, not a convenience: a trailing
    space in a reason tag would produce a second digest for the same assertion.
    """
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str, got {type(value).__name__}")
    stripped = value.strip()
    if not stripped:
        raise DomainValidationError(f"{name} must be a non-empty str")
    return stripped


def require_optional_text(value: Any, name: str) -> str | None:
    """`None`, or a non-empty string.

    An empty string is rejected rather than coerced to `None`: Law 4 says absence
    is a value with a reason, so a caller who means "nothing was said" says
    `None`, and `""` is a mistake worth surfacing.
    """
    if value is None:
        return None
    return require_text(value, name)


def require_utc(value: Any, name: str) -> datetime:
    """A timezone-aware datetime, normalized to UTC."""
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime, got {type(value).__name__}")
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise DomainValidationError(
            f"{name} must be timezone-aware; a naive instant cannot be ordered "
            "against a venue timestamp"
        )
    return value.astimezone(timezone.utc)


def require_optional_utc(value: Any, name: str) -> datetime | None:
    if value is None:
        return None
    return require_utc(value, name)


def require_int(value: Any, name: str, *, minimum: int | None = None) -> int:
    """An `int` that is not a `bool`, optionally bounded below."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise DomainValidationError(f"{name} must be at least {minimum}, got {value}")
    return value


def require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a bool, got {type(value).__name__}")
    return value


def require_member(value: Any, enum_type: type, name: str) -> Any:
    """A member of a closed enumeration, never its raw value.

    Accepting the string would let an unknown member arrive as a plausible-looking
    value; `AP` §5.7 rule 3 requires an unknown member to be a clean rejection.
    """
    if not isinstance(value, enum_type):
        raise TypeError(
            f"{name} must be a {enum_type.__name__}, got {type(value).__name__}"
        )
    return value


def require_tuple_of(
    value: Any, item_type: type, name: str, *, minimum_length: int = 0
) -> tuple[Any, ...]:
    """A tuple — never a list — of the given type.

    The tuple-not-list rule is the repository's own (`fmis.archive.json_safe`
    states it): a list would not round-trip to an equal value, and equality is
    what every identity and idempotency claim in this domain rests on.
    """
    if not isinstance(value, tuple):
        raise TypeError(
            f"{name} must be a tuple of {item_type.__name__}, got "
            f"{type(value).__name__}"
        )
    for position, item in enumerate(value):
        if not isinstance(item, item_type):
            raise TypeError(
                f"{name}[{position}] must be a {item_type.__name__}, got "
                f"{type(item).__name__}"
            )
    if len(value) < minimum_length:
        raise DomainValidationError(
            f"{name} must hold at least {minimum_length} item(s), got {len(value)}"
        )
    return value


def require_pattern(value: Any, pattern: re.Pattern[str], name: str) -> str:
    text = require_text(value, name)
    if not pattern.fullmatch(text):
        raise DomainValidationError(
            f"{name} {text!r} does not match {pattern.pattern}"
        )
    return text


def require_ordered(
    moments: Iterable[datetime], name: str, *, strict: bool = False
) -> None:
    """Reject an out-of-order sequence of instants.

    `strict` distinguishes "must increase" from "must not decrease". Two events
    caused by the *same* closed candle legitimately share an instant (§10.2's
    same-bar refusal), so most callers want the non-strict form.
    """
    previous: datetime | None = None
    for position, moment in enumerate(moments):
        if previous is not None:
            if moment < previous or (strict and moment == previous):
                raise DomainValidationError(
                    f"{name} must be ordered by time; item {position} at "
                    f"{moment.isoformat()} follows {previous.isoformat()}"
                )
        previous = moment
