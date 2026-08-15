"""`PositionSizer` — how much, and nothing about whether.

**One quotient, taken once, in a function this package does not own.**
`fmis.portfolio_risk.geometry.maximum_quantity_for_risk` is described there as
*"a primitive, not a position-sizing product... what it deliberately does not do
is decide what `allowed_risk` should be — that needs an equity contract this
build does not have"*. This module is the missing half and nothing more: it
resolves the allowance from the owner's equity, their chosen fraction and their
own ceilings, hands it to that primitive, and reports what came back. The
division is still written in exactly one place in the repository.

**Every derived figure is recomputed from the quantity that was produced**, never
carried over from the allowance that produced it. `money_at_risk` is
`risk distance × recommended quantity` through `capital_at_risk_of` — the same
function the portfolio engine uses for a held position — so the risk printed
beside a size is the risk *of that size*. Reporting the allowance instead would
agree with the truth under exact arithmetic and disagree the first time anything
rounded.

**Four refusals, and each is a value rather than an exception.**
`SWING_TRADING_MVP_BLUEPRINT_V1` §9.4 names them; here they are:

1. **Never size from setup quality or confidence.** No confidence, probability,
   risk/reward or state reaches this function's arithmetic at all — the planned
   risk/reward is carried onto the recommendation for the reader and is never an
   input to the quantity. A guard test asserts the sizing call graph names none
   of those words.
2. **Never size without a risk distance.** A stop the entry has already passed
   gives no denominator, and the result is `REFUSED` with the geometry printed.
3. **Never size past a binding limit without displaying the binding limit.**
   Every ceiling that touched the arithmetic is listed in `caps`, in the order it
   was applied.
4. **Never use `float` for money.** Nothing here constructs one; every value is a
   `Decimal`, a `Money` or a `Quantity`, and a repository-wide guard asserts this
   package holds no float literal at all.

**The quantity is exact and is not rounded to a venue's lot size.** A step size
is reference data this domain declines to hold, so the arithmetic answer is what
is reported and the owner rounds it **down** at the venue — the rule
`maximum_quantity_for_risk` already states, repeated on the page rather than
silently inherited.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fmis.money import Money, Quantity, canonical_decimal_text
from fmis.portfolio_risk import capital_at_risk_of, maximum_quantity_for_risk
from fmis.provenance import Absent
from fmis.risk import RiskBudget

from fmis.position_sizing.models import (
    PositionProposal,
    PositionRecommendation,
    SizingOutcome,
)
from fmis.position_sizing.policy import SizingPolicy

__all__ = ["ROUNDING_NOTE", "PositionSizer"]

#: Printed beside every recommended quantity. Not a caveat about precision: a
#: venue's minimum step is a real constraint this domain holds no field for, and
#: a quantity rounded *up* to reach one would put more at risk than the owner's
#: own fraction allows.
ROUNDING_NOTE = (
    "the recommended quantity is exact and is not rounded to any venue's lot or "
    "step size, which this system records nowhere. Round it DOWN at the venue: "
    "rounding up puts more at risk than the fraction this size was computed from"
)


@dataclass(frozen=True, slots=True)
class PositionSizer:
    """The owner's sizing rule, applied to one candidate at a time.

    A frozen object holding a `SizingPolicy` rather than a bare function, because
    the policy is the thing a surface configures once and applies many times, and
    threading it through every call site is how two candidates on one page end up
    sized under two different rules.
    """

    policy: SizingPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.policy, SizingPolicy):
            raise TypeError(
                f"policy must be a SizingPolicy, got {type(self.policy).__name__}"
            )

    def size(
        self,
        proposal: PositionProposal,
        *,
        equity: Money | Absent,
        budget: RiskBudget,
        remaining_open_risk: Money | Absent | None = None,
    ) -> PositionRecommendation:
        """The largest position whose capital at risk stays inside every ceiling.

        Args:
            proposal: the candidate, with its entry, its stop and its targets.
            equity: what the owner's stated fraction is a fraction *of*. An
                argument rather than a derivation: this package reaches no venue
                and holds no balance, and `Absent(reason)` is the correct answer
                when nothing has observed one.
            budget: the owner's limit generation, read for the per-trade ceiling.
            remaining_open_risk: what is left of the total-open-risk budget, from
                `fmis.portfolio_risk.remaining_risk_capacity`. `None` means the
                caller is sizing in isolation and states no portfolio; `Absent`
                means a portfolio was read and its headroom could not be
                measured, and the two are different facts with different
                consequences.

        Returns:
            A `PositionRecommendation` — always. A candidate that cannot be sized
            comes back with `SizingOutcome.REFUSED` or `UNDETERMINED` and the
            reason attached, because *"why is there no number"* is the answer the
            owner actually needs.

        Raises:
            TypeError: an argument is of the wrong type. A malformed call is a
                programming error and is not dressed up as a refusal.
        """
        if not isinstance(proposal, PositionProposal):
            raise TypeError(
                f"proposal must be a PositionProposal, got {type(proposal).__name__}"
            )
        if not isinstance(equity, (Money, Absent)):
            raise TypeError("equity must be a Money or Absent")
        if not isinstance(budget, RiskBudget):
            raise TypeError(f"budget must be a RiskBudget, got {type(budget).__name__}")
        if remaining_open_risk is not None and not isinstance(
            remaining_open_risk, (Money, Absent)
        ):
            raise TypeError("remaining_open_risk must be a Money, Absent or None")

        choice = self.policy.fraction_for(budget)
        planned = proposal.planned_risk_reward
        notes: list[str] = [ROUNDING_NOTE]
        caps: list[str] = []
        if choice.capped:
            # The cap says *what reduced the size*; `basis` says *where the
            # fraction came from*. Repeating the basis verbatim here printed the
            # same paragraph twice on the live page — the two are one fact seen
            # from two sides, and the reader needs each stated once.
            caps.append(
                f"reduced to the per-trade ceiling "
                f"{canonical_decimal_text(choice.ceiling)}, which the owner's "
                "own limit sets and a candidate cannot argue with"
            )

        allowance, outcome, refusal = self._allowance(
            proposal,
            equity=equity,
            fraction=choice.fraction,
            remaining_open_risk=remaining_open_risk,
            caps=caps,
            notes=notes,
        )
        if isinstance(allowance, Absent):
            return PositionRecommendation(
                proposal=proposal,
                outcome=outcome,
                quantity=Absent(refusal),
                risk_fraction=choice.fraction,
                money_at_risk=Absent(refusal),
                expected_exposure=Absent(refusal),
                planned_risk_reward=planned,
                equity=equity,
                basis=choice.basis,
                caps=tuple(caps),
                notes=tuple(notes),
            )

        # Neither call below is wrapped, and that is deliberate: both raise
        # `RiskGeometryError` on a stop the entry has already passed, and
        # `_allowance` has already turned that exact case into a REFUSED
        # recommendation above. Catching it here would be an `except` clause no
        # input can reach, which is worse than none — it would look like the
        # geometry was handled twice rather than once.
        quantity = maximum_quantity_for_risk(
            proposal.side,
            allowed_risk=allowance,
            entry=proposal.entry,
            stop=proposal.stop,
            base_asset=proposal.market.base_asset,
        )
        return PositionRecommendation(
            proposal=proposal,
            outcome=SizingOutcome.SIZED,
            quantity=quantity,
            risk_fraction=choice.fraction,
            money_at_risk=capital_at_risk_of(
                proposal.side,
                entry=proposal.entry,
                stop=proposal.stop,
                quantity=quantity,
                quote_asset=proposal.quote_asset,
            ),
            expected_exposure=quantity.value_at(proposal.entry, proposal.quote_asset),
            planned_risk_reward=planned,
            equity=equity,
            basis=choice.basis,
            caps=tuple(caps),
            notes=tuple(notes),
        )

    # -- the allowance, and every way there is not one ----------------------

    def _allowance(
        self,
        proposal: PositionProposal,
        *,
        equity: Money | Absent,
        fraction: Decimal | Absent,
        remaining_open_risk: Money | Absent | None,
        caps: list[str],
        notes: list[str],
    ) -> tuple[Money | Absent, SizingOutcome, str]:
        """How much money this trade may put at risk, or why that is unanswerable.

        Returns the allowance, the outcome a missing one implies, and the reason.
        The outcome is carried out of here rather than inferred by the caller
        because the distinction it encodes — *the arithmetic is impossible*
        against *an input is not known* — is decided by which branch was taken,
        and reconstructing it afterwards from an `Absent` reason string would be
        a parse of prose.
        """
        distance = proposal.risk_distance
        if isinstance(distance, Absent):
            return (
                distance,
                SizingOutcome.REFUSED,
                f"no size can be produced: {distance.reason}",
            )
        if isinstance(fraction, Absent):
            return (
                fraction,
                SizingOutcome.UNDETERMINED,
                f"no size can be produced: {fraction.reason}",
            )
        if isinstance(equity, Absent):
            return (
                equity,
                SizingOutcome.UNDETERMINED,
                "no size can be produced: a fraction of equity needs equity, and "
                f"none is known — {equity.reason}",
            )
        if equity.asset != proposal.quote_asset:
            reason = (
                f"equity is stated in {equity.asset} and {proposal.market.value} "
                f"is quoted in {proposal.quote_asset}; sizing across the two "
                "needs a dated rate this system holds nowhere, so no size is "
                "produced rather than one computed at an invented rate"
            )
            return Absent(reason), SizingOutcome.UNDETERMINED, reason
        if equity.amount <= 0:
            reason = (
                f"equity is {equity}, so a fraction of it sizes nothing. A "
                "non-positive equity is a refusal to trade rather than a small "
                "position"
            )
            return Absent(reason), SizingOutcome.REFUSED, reason

        allowance = equity.scale(fraction)
        # The arithmetic is a note, not a cap: `caps` holds only the ceilings
        # that **reduced** the size, so a surface can say "this size was cut by
        # something" by asking whether the tuple is empty rather than by reading
        # prose. The multiplication itself is shown, not merely its result.
        notes.append(
            f"{canonical_decimal_text(fraction)} of equity {equity.text} "
            f"{equity.asset} = {allowance.text} {allowance.asset} at risk"
        )
        return self._bounded_by_portfolio(
            allowance, remaining_open_risk=remaining_open_risk, caps=caps, notes=notes
        )

    def _bounded_by_portfolio(
        self,
        allowance: Money,
        *,
        remaining_open_risk: Money | Absent | None,
        caps: list[str],
        notes: list[str],
    ) -> tuple[Money | Absent, SizingOutcome, str]:
        """Reduce the allowance to what the total-open-risk budget still permits.

        `SWING_TRADING_MVP_BLUEPRINT_V1` §7.2 H-3: a budget already spent refuses
        *any* size that increases open risk, and `AP` §15.6's rule behind it is
        that *"total portfolio risk outranks any single setup's quality"*. A
        headroom that could not be measured does **not** refuse a size — it leaves
        the size standing and the approval `INDETERMINATE` on that limit, which is
        the honest split between *"your budget is spent"* and *"nobody could tell
        whether it is"*.
        """
        if remaining_open_risk is None:
            notes.append(
                "no portfolio was supplied, so this size was bounded by the "
                "per-trade ceiling alone and not by any total-open-risk budget"
            )
            return allowance, SizingOutcome.SIZED, ""
        if isinstance(remaining_open_risk, Absent):
            notes.append(
                "the total-open-risk headroom could not be measured, so this size "
                f"is bounded by the per-trade ceiling alone: "
                f"{remaining_open_risk.reason}"
            )
            return allowance, SizingOutcome.SIZED, ""
        if remaining_open_risk.asset != allowance.asset:
            notes.append(
                f"the total-open-risk headroom is stated in "
                f"{remaining_open_risk.asset} and this trade risks "
                f"{allowance.asset}; the two were not compared, because "
                "converting here would hide the rate that made them comparable"
            )
            return allowance, SizingOutcome.SIZED, ""
        if remaining_open_risk.amount <= 0:
            reason = (
                f"the total-open-risk budget has {remaining_open_risk.text} "
                f"{remaining_open_risk.asset} of headroom left, so no size "
                "increases open risk without breaching it. Total portfolio risk "
                "outranks any single candidate's quality"
            )
            caps.append(reason)
            return Absent(reason), SizingOutcome.REFUSED, reason
        if remaining_open_risk < allowance:
            caps.append(
                f"reduced to the {remaining_open_risk.text} "
                f"{remaining_open_risk.asset} left in the total-open-risk budget, "
                f"which is less than the {allowance.text} {allowance.asset} the "
                "per-trade fraction alone would allow"
            )
            return remaining_open_risk, SizingOutcome.SIZED, ""
        return allowance, SizingOutcome.SIZED, ""
