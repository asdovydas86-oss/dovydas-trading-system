"""The owner's declared risk policy, and the one place the specification's ceiling lives.

**This package exists because the risk domain had no first link.** `fmis.risk`
holds `RiskBudget` and `RiskLimit`; `fmis.position_sizing` holds `PositionSizer`
and `ApprovalEngine`; `fmis.portfolio_risk` holds every piece of the arithmetic.
All of it is complete, tested and correct — and before this package
``RiskBudget(`` and ``RiskLimit(`` appeared **nowhere in `src/`**. They were
constructed only in tests. No command, no configuration and no surface could
bring one into existence, so `per_trade_ceiling` was never consulted,
`SizingPolicy.fraction_for` never resolved, and the whole chain was unreachable
from the product. This module is the missing declaration boundary and nothing
more.

**The specification's 2 % is here, and it is here exactly once.**
`SPECIFICATION_PER_TRADE_CEILING` is `SPEC` §8.1 — *"A maximum of 2% portfolio
risk per trade is a hard ceiling, not a default target."* It cannot live in
`fmis.risk` or `fmis.position_sizing`: both are guarded to hold no numeric
literal beyond `0` and `1`, deliberately, so that *"every value is the owner's"*.
The ceiling is not an invented threshold — it is the owner's own specification —
but it is still a number, and a number belongs at the boundary where the owner's
words become a domain object rather than inside the engines that evaluate them.

**The ceiling is structural, not advisory.** A declaration stating more than
`SPECIFICATION_PER_TRADE_CEILING` is refused in `__post_init__`, so a fraction
above the ceiling cannot be represented at all — there is no object for a surface
to render, no branch for a caller to forget and no validation for a second entry
point to skip. Equality is permitted because the specification says *maximum*:
`<= 2 %` is inside it and `> 2 %` is not.

**Nothing here defaults.** A declaration that states no fraction carries
`Absent(reason)`, and every layer above it reports the missing input by name.
Defaulting to the ceiling would turn the specification's ceiling into the
specification's target with no one deciding to, which is the single failure
`fmis.position_sizing.policy` was built to prevent.

**Declared equity is asserted, never measured.** `PortfolioState.equity` is folded
from recorded fills and marks; the equity here is a figure the owner typed. They
are different facts about the same word, they can disagree, and `origin` says
which this one is so a surface can never present an assertion as a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.money import Money, canonical_decimal_text
from fmis.provenance import Absent, ValueOrigin
from fmis.records import (
    DomainValidationError,
    TradeDomainError,
    require_int,
    require_text,
    require_utc,
)

__all__ = [
    "RiskPolicyError",
    "SPECIFICATION_PER_TRADE_CEILING",
    "SPECIFICATION_CEILING_SOURCE",
    "RISK_POLICY_CONTRACT_VERSION",
    "SUPPORTED_RISK_POLICY_VERSIONS",
    "RiskPolicyDeclaration",
]


class RiskPolicyError(TradeDomainError):
    """A declaration the owner's own specification does not permit."""


#: `SPEC` §8.1 — *"A maximum of 2% portfolio risk per trade is a hard ceiling,
#: not a default target."* The one place this number appears in `src/`.
#:
#: A `Decimal`, never a float: `0.02` as binary floating point is
#: `0.0200000000000000004163336342344337026588618755340576171875`, and a ceiling
#: comparison against it decides a capital-preservation limit by representation
#: error. Every comparison against this value is exact decimal arithmetic.
SPECIFICATION_PER_TRADE_CEILING: Decimal = Decimal("0.02")

#: What a surface cites when it prints the ceiling. Carried as text so a page can
#: say *where the limit comes from* without the renderer knowing the document.
SPECIFICATION_CEILING_SOURCE = (
    "PROJECT_SPECIFICATION_V1 §8.1 — a maximum of 2% portfolio risk per trade is "
    "a hard ceiling, not a default target"
)

#: The declaration contract's own version. Risk limits will evolve, and a future
#: archived decision must be able to answer *"which policy evaluated this"*.
RISK_POLICY_CONTRACT_VERSION = 1
SUPPORTED_RISK_POLICY_VERSIONS = frozenset({1})


@dataclass(frozen=True, slots=True)
class RiskPolicyDeclaration:
    """What the owner declared: their planning capital, and what they risk of it.

    **Two values and one of them is optional.** `equity` is what a fraction is a
    fraction *of*; `per_trade_fraction` is the fraction. A declaration with no
    fraction is legitimate and complete — it says *"this is my capital; I have not
    chosen a per-trade risk"* — and every layer above reports that missing input
    by name rather than choosing one.

    **`per_trade_fraction` is bounded at construction.** Above
    `SPECIFICATION_PER_TRADE_CEILING` there is no object, so the ceiling cannot be
    bypassed by a caller that skipped a check, a surface that validated only its
    own form, or a future second entry point. `2.0000000001 %` is refused and
    `1.9999999999 %` is accepted, exactly, because both comparisons are decimal.

    **`equity` is `ASSERTED`.** Nothing here observes a balance, reaches a venue
    or reads an exchange account. The owner typed this figure and it is dated by
    `declared_at`, so a surface can state how old the number a size rests on is.
    """

    equity: Money
    declared_at: datetime
    per_trade_fraction: Decimal | Absent = field(
        default_factory=lambda: Absent(
            "the owner declared no per-trade risk fraction. No fraction is "
            "assumed in its place: the specification states a ceiling, and a "
            "system that sized at the ceiling by default would have made the "
            "ceiling the target"
        )
    )
    note: str | Absent = field(default_factory=lambda: Absent("no note"))
    contract_version: int = RISK_POLICY_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.equity, Money):
            raise TypeError(
                f"equity must be a Money, got {type(self.equity).__name__}; a "
                "bare number would be an amount with no asset, which does not "
                "exist in this domain"
            )
        if self.equity.amount <= 0:
            raise RiskPolicyError(
                f"declared equity is {self.equity}, and a fraction of it sizes "
                "nothing. A non-positive planning capital is a refusal to trade "
                "rather than a very small position"
            )
        object.__setattr__(
            self, "declared_at", require_utc(self.declared_at, "declared_at")
        )
        require_int(
            self.contract_version, "contract_version", minimum=1
        )
        if self.contract_version not in SUPPORTED_RISK_POLICY_VERSIONS:
            raise DomainValidationError(
                f"risk policy contract_version {self.contract_version} is not one "
                f"this build reads ({sorted(SUPPORTED_RISK_POLICY_VERSIONS)})"
            )
        if not isinstance(self.per_trade_fraction, Absent):
            if not isinstance(self.per_trade_fraction, Decimal):
                raise TypeError(
                    "per_trade_fraction must be a Decimal or Absent, got "
                    f"{type(self.per_trade_fraction).__name__}; a float fraction "
                    "would decide a capital-preservation ceiling by binary "
                    "representation error"
                )
            if not self.per_trade_fraction.is_finite():
                raise RiskPolicyError(
                    "per_trade_fraction is not finite; NaN and Infinity are not "
                    "fractions of anything"
                )
            if self.per_trade_fraction <= 0:
                raise RiskPolicyError(
                    f"per_trade_fraction must be positive, got "
                    f"{self.per_trade_fraction}. A zero or negative fraction is a "
                    "decision not to trade, which the owner makes by not trading "
                    "rather than by declaring a policy"
                )
            if self.per_trade_fraction > SPECIFICATION_PER_TRADE_CEILING:
                raise RiskPolicyError(
                    f"per_trade_fraction "
                    f"{canonical_decimal_text(self.per_trade_fraction)} exceeds "
                    f"the hard ceiling "
                    f"{canonical_decimal_text(SPECIFICATION_PER_TRADE_CEILING)}. "
                    f"{SPECIFICATION_CEILING_SOURCE}. The ceiling is not "
                    "negotiable by configuration, and leverage does not make a "
                    "loss beyond it acceptable"
                )
            object.__setattr__(
                self,
                "per_trade_fraction",
                Decimal(canonical_decimal_text(self.per_trade_fraction)),
            )
        if not isinstance(self.note, Absent):
            object.__setattr__(self, "note", require_text(self.note, "note"))

    @property
    def origin(self) -> ValueOrigin:
        """`ASSERTED` — the owner typed this. Nothing here measured anything."""
        return ValueOrigin.ASSERTED

    @property
    def states_a_fraction(self) -> bool:
        """Whether a fraction was declared. **Never whether it is a good one.**"""
        return not isinstance(self.per_trade_fraction, Absent)

    @property
    def fraction_text(self) -> str | Absent:
        """The declared fraction as canonical text, or the reason there is none.

        A property so a surface prints the owner's own spelling of the number
        rather than a renderer's `str()` of a `Decimal`, which is how `0.005`
        and `5E-3` become two spellings of one policy.
        """
        if isinstance(self.per_trade_fraction, Absent):
            return self.per_trade_fraction
        return canonical_decimal_text(self.per_trade_fraction)

    @property
    def ceiling_text(self) -> str:
        """The specification's hard maximum, as canonical text."""
        return canonical_decimal_text(SPECIFICATION_PER_TRADE_CEILING)

    @property
    def ceiling(self) -> Decimal:
        """The specification's hard maximum, whatever the owner declared."""
        return SPECIFICATION_PER_TRADE_CEILING

    def to_payload(self) -> dict[str, Any]:
        """The declaration as the owner's own file spells it."""
        return {
            "contract_version": self.contract_version,
            "equity": self.equity.to_payload(),
            "declared_at": self.declared_at.isoformat().replace("+00:00", "Z"),
            "per_trade_fraction": (
                None
                if isinstance(self.per_trade_fraction, Absent)
                else canonical_decimal_text(self.per_trade_fraction)
            ),
            "note": None if isinstance(self.note, Absent) else self.note,
        }
