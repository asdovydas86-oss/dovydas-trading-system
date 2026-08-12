"""The trading domain's error hierarchy.

One base — `TradeDomainError` — so a caller can catch every failure the owner
half of FMITS can raise as a group, exactly as `IngestError`,
`LevelCrossingError`, `MarketRegimeError` and `WorkspaceError` already let a
caller do for the market half. Each domain package then derives its own base
from this one, so `except LedgerError` and `except TradeDomainError` are both
meaningful and neither is a lie.

The three shared subclasses below exist because three failures recur in every
package and must never be conflated by a caller:

* **validation** — the values supplied cannot describe the thing at all;
* **state** — the values are individually fine and the *transition* is illegal;
* **payload version** — the bytes are readable and this build cannot read them.

The third is separate from the second precisely because `AP` §5.7's forward-only
contract requires an unknown version to be a **clean rejection** rather than a
best-effort parse, and a caller upgrading a build needs to tell that case apart
from corruption.
"""

from __future__ import annotations

__all__ = [
    "TradeDomainError",
    "DomainValidationError",
    "DomainStateError",
    "UnsupportedPayloadVersionError",
    "PayloadDecodeError",
]


class TradeDomainError(Exception):
    """Base class for every trading-domain failure."""


class DomainValidationError(TradeDomainError, ValueError):
    """The supplied values cannot describe this entity.

    Also a `ValueError`, matching `ContextInputError`, `StructureBreakInputError`
    and `RegimeInputError`, so a caller catching `ValueError` at a boundary keeps
    working.
    """


class DomainStateError(TradeDomainError, ValueError):
    """A transition the lifecycle does not permit.

    Distinct from `DomainValidationError` because the inputs are each valid: it
    is their *order* that is not. A caller that cannot tell "this event is
    malformed" from "this event cannot follow that one" will eventually paper
    over the second by re-validating the first.
    """


class PayloadDecodeError(TradeDomainError, ValueError):
    """A serialized payload is not the shape this record type requires."""


class UnsupportedPayloadVersionError(PayloadDecodeError):
    """A serialized payload names a schema version this build cannot read.

    A subclass of `PayloadDecodeError` so a caller that only wants "I could not
    read this" needs one `except`, and a caller that wants to distinguish "your
    build is too old" gets it without parsing a message.
    """
