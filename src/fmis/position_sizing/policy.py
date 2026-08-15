"""`SizingPolicy` — the owner's sizing rule. **This module contains no number.**

Every threshold a size is decided by is the owner's: the fraction of equity they
chose to risk, the ceiling they set, the staleness bounds they configured, the
minimum risk/reward they will look at. A test asserts no numeric literal beyond
`0` and `1` appears anywhere in this package, which is the same test
`fmis.risk` and `fmis.portfolio_risk` already pass, and it is the whole reason
this file exists as a separate object rather than as constants in the sizer.

**The fraction is resolved, not defaulted, and there are exactly three places it
can come from.** In order:

1. **The owner's own choice for this trade**, stated on the policy.
2. **`RiskLimit.default_below_ceiling`** — the field the domain already carries
   for exactly this, described in `fmis.risk` as *"a limit with a ceiling
   semantic and a separate default below it"*. `SPEC` §8.1's rule is that 2 % is
   *"a hard ceiling, not a default target"*, so a system that sized at the
   ceiling by default would have converted the specification's ceiling into the
   specification's target with no one deciding to.
3. **Nothing.** If the owner stated no fraction and their ceiling states no
   default below it, there is no fraction, and the answer is `Absent(reason)`
   rather than the ceiling. `Absent` produces an `INDETERMINATE` approval naming
   the missing input, which is a true and actionable answer; sizing at the
   ceiling would be this package choosing a number on the owner's behalf, which
   is the one thing `AP` §15.4 forbids it to do.

**The ceiling is read from the budget and is applied whatever the owner asked
for.** A fraction above the ceiling is reduced to the ceiling and the reduction
is named on the recommendation — *"the sizer returns the ceiling-bound size and
names the ceiling"*, `SWING_TRADING_MVP_BLUEPRINT_V1` §7.2 H-2, adopted
verbatim.

**A percent limit is a fraction here, as it is everywhere else in this
repository.** `fmis.portfolio_risk.constraints.PERCENT_UNIT_CONVENTION` states
the convention and this module reuses that constant rather than restating it, so
two engines cannot read the owner's `0.02` two different ways.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any

from fmis.money import canonical_decimal_text
from fmis.portfolio_risk import PERCENT_UNIT_CONVENTION
from fmis.provenance import Absent, ValueOrigin
from fmis.records import (
    IDENTIFIER_PATTERN,
    DomainValidationError,
    require_pattern,
    require_text,
)
from fmis.risk import LimitScope, LimitUnit, RiskBudget, RiskLimit

#: `PERCENT_UNIT_CONVENTION` is imported and re-read, never re-exported. The
#: repository holds zero public-name collisions as a measured invariant, and
#: `fmis.portfolio_risk` already owns that name — a second export of it would be
#: a second place the convention appears to be defined.
__all__ = [
    "SIZING_POLICY_VERSION",
    "FractionChoice",
    "SizingPolicy",
    "per_trade_ceiling",
]

#: This build's sizing rule version. Cited on every recommendation, because a
#: later build that resolves the fraction differently must produce a *visibly*
#: different reading rather than silently reinterpreting an old one — the same
#: discipline `CONSTRAINT_POLICY_VERSION` already carries one layer down.
SIZING_POLICY_VERSION = "position-sizing-v1"


@dataclass(frozen=True, slots=True)
class FractionChoice:
    """The fraction a size was computed at, and the whole story of where it came from.

    Four fields rather than one number, because *"2 % of equity"* and *"1 % of
    equity, because that is the default you set below your 2 % ceiling"* and
    *"1 % of equity, because your ceiling refused the 3 % you asked for"* are
    three different facts that a bare `Decimal` cannot tell apart — and the third
    is the one the owner most needs to see.
    """

    fraction: Decimal | Absent
    basis: str
    ceiling: Decimal | Absent = field(
        default_factory=lambda: Absent("no per-trade risk ceiling is configured")
    )
    capped: bool = False

    def __post_init__(self) -> None:
        for name in ("fraction", "ceiling"):
            value = getattr(self, name)
            if isinstance(value, Absent):
                continue
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal or Absent")
            if value <= 0:
                raise DomainValidationError(f"{name} must be positive, got {value}")
            object.__setattr__(self, name, Decimal(canonical_decimal_text(value)))
        object.__setattr__(self, "basis", require_text(self.basis, "basis"))
        if not isinstance(self.capped, bool):
            raise TypeError("capped must be a bool")
        if self.capped and isinstance(self.ceiling, Absent):
            raise DomainValidationError(
                "a fraction cannot have been capped by a ceiling that is not "
                "stated; naming the cap without naming the limit is the shape "
                "that makes a reduced size look like the owner's own choice"
            )

    @property
    def origin(self) -> ValueOrigin:
        """`ASSERTED`. Every number here is the owner's, none is this build's."""
        return ValueOrigin.ASSERTED


def per_trade_ceiling(budget: RiskBudget) -> RiskLimit | Absent:
    """The one `PER_TRADE_RISK` limit stated as a fraction of equity, or why not.

    **More than one is an `Absent`, not a choice.** A budget holding two per-trade
    ceilings has two answers to *"how much may this trade risk"*, and picking the
    smaller would be defensible, picking the first would be an id sort nobody
    wrote down, and picking either would hide from the owner that their own
    policy contradicts itself.

    A ceiling stated in money rather than as a fraction of equity is not this
    limit: it is a per-trade *money* cap, which `evaluate_constraints` already
    measures and reports on its own. Sizing needs a fraction, and reading a money
    limit as one would be a unit error with a plausible-looking result.
    """
    if not isinstance(budget, RiskBudget):
        raise TypeError(f"budget must be a RiskBudget, got {type(budget).__name__}")
    found = [
        limit
        for limit in budget.limits_for(LimitScope.PER_TRADE_RISK)
        if limit.unit is LimitUnit.PERCENT_OF_EQUITY
    ]
    if not found:
        return Absent(
            f"budget {budget.budget_id!r} (policy version "
            f"{budget.risk_policy_version}) states no per-trade risk ceiling as a "
            "fraction of equity. That is a gap in the owner's own policy, not a "
            "measurement failure, and no ceiling is invented in its place"
        )
    if len(found) > 1:
        names = ", ".join(sorted(limit.limit_id for limit in found))
        return Absent(
            f"budget {budget.budget_id!r} states {len(found)} per-trade risk "
            f"ceilings ({names}); which one bounds this trade is not stated by "
            "anything the owner recorded, and choosing one would resolve a "
            "contradiction in their policy without telling them it exists"
        )
    return found[0]


@dataclass(frozen=True, slots=True)
class SizingPolicy:
    """The owner's sizing rule: what fraction, and what counts as too stale.

    **Every field defaults to `Absent`, and that is the design.** A policy the
    owner has not configured produces `INDETERMINATE` approvals naming exactly
    which input is missing — which is a working product that tells them what to
    set, rather than a working product that quietly chose for them.

    `max_equity_age` and `max_mark_age` are the owner's *staleness bounds*.
    `SWING_TRADING_MVP_BLUEPRINT_V1` §7.2 H-4 makes an equity figure older than
    the configured bound a hard block on sizing, and the phrase *"the owner's
    configured staleness bound"* is why there is no bound here until they
    configure one: an age this package judged against a number it chose would be
    a threshold invented at exactly the point the specification says not to.
    """

    policy_id: str
    risk_fraction: Decimal | Absent = field(
        default_factory=lambda: Absent(
            "the owner stated no risk fraction for this trade"
        )
    )
    max_equity_age: timedelta | Absent = field(
        default_factory=lambda: Absent("the owner configured no equity staleness bound")
    )
    max_mark_age: timedelta | Absent = field(
        default_factory=lambda: Absent("the owner configured no mark staleness bound")
    )
    minimum_risk_reward: Decimal | Absent = field(
        default_factory=lambda: Absent("the owner stated no minimum risk/reward")
    )
    version: str = SIZING_POLICY_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_id",
            require_pattern(self.policy_id, IDENTIFIER_PATTERN, "policy_id"),
        )
        for name in ("risk_fraction", "minimum_risk_reward"):
            value = getattr(self, name)
            if isinstance(value, Absent):
                continue
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal or Absent")
            if value <= 0:
                raise DomainValidationError(
                    f"{name} must be positive, got {value}; a non-positive value "
                    "is a refusal to trade, which is the owner's decision rather "
                    "than an arithmetic result"
                )
            object.__setattr__(self, name, Decimal(canonical_decimal_text(value)))
        for name in ("max_equity_age", "max_mark_age"):
            value = getattr(self, name)
            if isinstance(value, Absent):
                continue
            if not isinstance(value, timedelta):
                raise TypeError(f"{name} must be a timedelta or Absent")
            if value <= timedelta():
                raise DomainValidationError(
                    f"{name} must be a positive duration, got {value}; a bound of "
                    "zero would make every figure stale the instant after it was "
                    "true, which is a refusal to read rather than a bound"
                )
        for name in ("version",):
            object.__setattr__(self, name, require_text(getattr(self, name), name))

    @property
    def origin(self) -> ValueOrigin:
        """`ASSERTED` — the owner's policy, never the system's judgement."""
        return ValueOrigin.ASSERTED

    @property
    def percent_unit_convention(self) -> str:
        return PERCENT_UNIT_CONVENTION

    def fraction_for(self, budget: RiskBudget) -> FractionChoice:
        """Resolve the fraction of equity this trade may risk, and say why.

        The three-step resolution the module docstring states, in one place, with
        the ceiling applied last so that no path through this function can return
        a fraction above the owner's own limit.
        """
        ceiling_limit = per_trade_ceiling(budget)
        ceiling: Decimal | Absent
        if isinstance(ceiling_limit, Absent):
            ceiling = Absent(ceiling_limit.reason)
        else:
            assert isinstance(ceiling_limit.value, Decimal)  # PERCENT_OF_EQUITY
            ceiling = ceiling_limit.value

        chosen, basis = self._chosen(ceiling_limit)
        if isinstance(chosen, Absent):
            return FractionChoice(fraction=chosen, basis=basis, ceiling=ceiling)
        if isinstance(ceiling, Decimal) and chosen > ceiling:
            assert not isinstance(ceiling_limit, Absent)  # a ceiling has a limit
            return FractionChoice(
                fraction=ceiling,
                basis=(
                    f"{basis}, reduced to the ceiling "
                    f"{canonical_decimal_text(ceiling)} set by limit "
                    f"{ceiling_limit.limit_id!r}. A ceiling is not a number a "
                    "candidate can argue with"
                ),
                ceiling=ceiling,
                capped=True,
            )
        return FractionChoice(fraction=chosen, basis=basis, ceiling=ceiling)

    def _chosen(
        self, ceiling_limit: RiskLimit | Absent
    ) -> tuple[Decimal | Absent, str]:
        """What the owner asked for, before any ceiling is applied."""
        if not isinstance(self.risk_fraction, Absent):
            return (
                self.risk_fraction,
                f"the fraction {canonical_decimal_text(self.risk_fraction)} the "
                f"owner stated for this trade under policy {self.policy_id!r}",
            )
        if isinstance(ceiling_limit, Absent):
            return (
                Absent(
                    "no fraction of equity is stated for this trade and no "
                    f"per-trade ceiling carries a default below it: "
                    f"{ceiling_limit.reason}. No size is produced, because "
                    "choosing a fraction here would be this system deciding how "
                    "much of the owner's money to risk"
                ),
                "no fraction could be resolved",
            )
        default = ceiling_limit.default_below_ceiling
        if isinstance(default, Absent):
            return (
                Absent(
                    f"the owner stated no fraction for this trade, and their "
                    f"per-trade ceiling {ceiling_limit.limit_id!r} states no "
                    f"default below it: {default.reason}. The ceiling is a "
                    "ceiling and not a target, so it is not used as one"
                ),
                "no fraction could be resolved",
            )
        return (
            default,
            f"the default {canonical_decimal_text(default)} the owner set below "
            f"their ceiling {ceiling_limit.limit_id!r}",
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "risk_fraction": _maybe(self.risk_fraction, canonical_decimal_text),
            "minimum_risk_reward": _maybe(
                self.minimum_risk_reward, canonical_decimal_text
            ),
            "max_equity_age": _maybe(self.max_equity_age, _duration_text),
            "max_mark_age": _maybe(self.max_mark_age, _duration_text),
            "percent_unit_convention": self.percent_unit_convention,
        }


def _duration_text(value: timedelta) -> str:
    return str(value)


def _maybe(value: Any, encode: Any) -> dict[str, Any]:
    if isinstance(value, Absent):
        return {"absent": value.to_payload()}
    return {"value": encode(value)}
