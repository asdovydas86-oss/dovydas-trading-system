"""The owner's declaration, turned into the objects the risk engines already take.

    declaration  ──►  budget_from()          ──►  RiskBudget      (fmis.risk)
                 ──►  sizing_policy_from()   ──►  SizingPolicy    (fmis.position_sizing)
                 ──►  plan_for()             ──►  TradeRiskPlan

**This module computes no risk arithmetic.** Not one multiplication, division or
comparison of money happens here. The risk distance, the capital at risk, the
maximum quantity for an allowance and the ceiling that bounds it are
`fmis.portfolio_risk.geometry`'s and `fmis.position_sizing.sizing`'s, reached
through `PositionSizer.size` — the single call in the repository where the
sizing quotient is taken. What this module contributes is the two objects that
call has always required and nothing in `src/` ever built.

**Sizing in isolation, and it says so.** `PositionSizer.size` documents
``remaining_open_risk=None`` as *"the caller is sizing in isolation and states no
portfolio"*, distinct from `Absent` which means *"a portfolio was read and its
headroom could not be measured"*. This module passes `None`, because a planning
figure computed with no portfolio is exactly that, and `TradeRiskPlan.portfolio_impact`
carries the consequence as a stated absence. **Unknown portfolio risk never
becomes zero**, and a plan that fits the per-trade ceiling is never presented as
one the book has room for.

**The ceiling reaches the budget; the owner's fraction does not.** The
`RiskBudget` this builds carries the specification's `PER_TRADE_RISK` ceiling and
**no** `default_below_ceiling`, because the specification states a maximum and no
default, and `RiskLimit` is explicit that *"a default at the ceiling is a target,
and the ceiling is not a target"*. The owner's declared fraction travels on the
`SizingPolicy` instead — source 1 of `fraction_for`, *"the owner's own choice"* —
which is what it is. A declaration with no fraction therefore resolves to no
fraction at all, and the plan reports the missing input by name.

**Entry is the engine's reference price, and the caveat travels with it.** The
swing engine deliberately fabricates no order price; `reference_price` is the
execution-timeframe close its stop and targets were measured against.
`fmis.position_sizing.inputs` already makes that the proposal's entry and states
the caveat, and `ENTRY_CAVEAT` carries it onto the page rather than letting a
size imply an order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fmis.accounts import AccountId, Book
from fmis.money import Money, Quantity, canonical_decimal_text
from fmis.position_sizing import (
    PositionProposal,
    PositionRecommendation,
    PositionSizer,
    SizingOutcome,
    SizingPolicy,
    proposals_from_results,
)
from fmis.provenance import Absent
from fmis.records import RecordAudit, require_text, require_utc
from fmis.risk import (
    LimitPeriod,
    LimitScope,
    LimitSeverity,
    LimitUnit,
    RiskBudget,
    RiskLimit,
)
from fmis.risk_policy.models import (
    RISK_POLICY_CONTRACT_VERSION,
    SPECIFICATION_CEILING_SOURCE,
    SPECIFICATION_PER_TRADE_CEILING,
    RiskPolicyDeclaration,
)

__all__ = [
    "PLANNING_ACCOUNT",
    "PLANNING_BOOK",
    "PLANNING_BUDGET_ID",
    "PLANNING_POLICY_ID",
    "CEILING_LIMIT_ID",
    "ENTRY_CAVEAT",
    "PLANNING_LIMITATIONS",
    "PlanningStatus",
    "TradeRiskPlan",
    "budget_from",
    "sizing_policy_from",
    "plan_for",
    "plans_for_results",
]

#: The account a planning figure is scoped to. **A planning scope, never a real
#: account.** Sizing needs an `AccountId` because a `PositionProposal` is scoped
#: to one, and this build reaches no exchange and holds no account of the
#: owner's. Naming it `planning` rather than reusing a stored account id is what
#: stops a figure computed against declared capital from being read as one
#: computed against a recorded book.
PLANNING_ACCOUNT = "planning"

#: The book a planning figure is filed under. Swing, because this is the swing
#: product's surface, and `AP` §5.5 makes the book an economic classification
#: that never shares capacity with the long-term investing book.
PLANNING_BOOK = Book.SWING

PLANNING_BUDGET_ID = "specification_per_trade"
PLANNING_POLICY_ID = "owner_declared_planning"
CEILING_LIMIT_ID = "per_trade_risk_ceiling"

#: Printed wherever an entry price is. The engine's own caveat, carried rather
#: than restated: a size derived from a close is not an order at that close.
ENTRY_CAVEAT = (
    "The entry is the execution-timeframe close the stop and targets were "
    "measured against — a recorded fact, not an order price. The engine "
    "fabricates no exact entry, and a fill at another price changes every figure "
    "below."
)

#: What a planning figure is not, printed beside it rather than left to be
#: discovered. Every entry is a property of this build.
PLANNING_LIMITATIONS = (
    (
        "no portfolio",
        "Every figure is for this trade alone, against declared capital. No "
        "position, exposure, correlation or open risk is read, so nothing here "
        "says the book has room for it. Total open risk is not measured and is "
        "reported as not evaluated, never as zero.",
    ),
    (
        "planned, not worst case",
        "The risk figure assumes the stop is honoured at exactly the stated "
        "price. A gap through it, slippage, or a venue outage loses more. This "
        "is defined risk at invalidation, not maximum possible loss.",
    ),
    (
        "before costs",
        "No fee, funding, spread or conversion is included. The figure is the "
        "price distance times the quantity and nothing else.",
    ),
    (
        "linear spot-like instruments only",
        "The arithmetic assumes one unit of the base asset gains or loses the "
        "quote-denominated price difference. It is not correct for inverse "
        "contracts, dated futures with a multiplier, or options, and no leverage "
        "is modelled — leverage magnifies a loss and never makes one inside a "
        "ceiling that it is outside of.",
    ),
    (
        "not an opinion",
        "A size is how much, never whether. Nothing here ranks a setup, claims "
        "an edge or says a trade is worth taking, and no risk figure changes the "
        "engine's decision for the symbol.",
    ),
)


class PlanningStatus(Enum):
    """Why a symbol does or does not carry trade-planning figures.

    **Four members, and none of them is a verdict about the trade.** They say
    what could be computed, never whether the result is good. `NO_TRADE_PLAN` and
    `NOT_EVALUABLE` are deliberately different: the first is the engine's own
    conclusion that there is no directional idea here at all, the second is a
    directional idea whose planning inputs are incomplete. Rendered as one, a
    quiet market and an unconfigured system would be indistinguishable.
    """

    #: The engine states no direction for this symbol, so there is no trade to
    #: plan. The normal state of most of the watchlist, and not a failure.
    NO_TRADE_PLAN = "no_trade_plan"
    #: There is a directional idea and at least one planning input is missing.
    #: `missing` names each one.
    NOT_EVALUABLE = "not_evaluable"
    #: Every input was present and the arithmetic ran.
    PLANNED = "planned"
    #: Every input was present and the arithmetic produced nothing usable — a
    #: stop the entry has already passed is the case that produces it.
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class TradeRiskPlan:
    """One symbol's deterministic risk arithmetic, or exactly why there is none.

    **Every figure is a property already computed by an engine.** Nothing on this
    object is derived here; `_from_recommendation` copies what `PositionSizer`
    produced. A figure that could not be produced is `Absent(reason)` and never a
    zero — `AP` §14.3: *"a zero makes the total look plausible and survives for
    years."*

    ``portfolio_impact`` is always an `Absent` in this build and that is the
    contract, not an oversight: no portfolio was read, so nothing is known about
    what this position would do to one. It is a field rather than an omission
    because a page silent about portfolio risk reads as a page reporting none.

    ``status`` is `NO_TRADE_PLAN` for every symbol the engine gave no direction,
    which is most of them. Those carry no figures at all — not a zero size, not an
    empty size, nothing — because a `WAIT` symbol with a position size beside it
    reads as almost a trade.
    """

    symbol: str
    status: PlanningStatus
    #: Every planning input the **owner** has not declared, named one by one.
    #: Empty when the status is `PLANNED` or `NO_TRADE_PLAN`, and empty for a
    #: `REFUSED` plan — nothing is missing there, the geometry is invalid.
    missing: tuple[str, ...] = ()
    #: The **engine's** own sentence for why there is no number, verbatim. Empty
    #: only when there is one. Separate from `missing` because the two have
    #: separate remedies: *"declare this"* and *"this candidate's geometry does
    #: not admit a size"* are not the same request of the reader.
    reason: str = ""
    direction: str | Absent = field(
        default_factory=lambda: Absent("the engine states no direction")
    )
    entry: Decimal | Absent = field(
        default_factory=lambda: Absent("no reference price was produced")
    )
    invalidation: Decimal | Absent = field(
        default_factory=lambda: Absent("no structural stop level was produced")
    )
    risk_per_unit: Money | Absent = field(
        default_factory=lambda: Absent("no risk distance could be measured")
    )
    equity: Money | Absent = field(
        default_factory=lambda: Absent("no planning capital is declared")
    )
    risk_fraction: Decimal | Absent = field(
        default_factory=lambda: Absent("no per-trade risk fraction is declared")
    )
    money_at_risk: Money | Absent = field(
        default_factory=lambda: Absent("no capital at risk could be computed")
    )
    quantity: Quantity | Absent = field(
        default_factory=lambda: Absent("no quantity could be produced")
    )
    notional: Money | Absent = field(
        default_factory=lambda: Absent("no position value could be computed")
    )
    reward_risk: str | Absent = field(
        default_factory=lambda: Absent(
            "no target level was produced, so there is no reward to compare "
            "against the risk. None is assumed"
        )
    )
    portfolio_impact: Absent = field(
        default_factory=lambda: Absent(
            "no portfolio was read for this figure. Total open risk, "
            "concentration and correlation are not evaluated — which is not the "
            "same as their being zero, and a plan inside the per-trade ceiling is "
            "not thereby one the book has room for"
        )
    )
    #: The specification's hard maximum, printed whatever the owner declared.
    ceiling: Decimal = SPECIFICATION_PER_TRADE_CEILING
    ceiling_source: str = SPECIFICATION_CEILING_SOURCE
    #: One sentence naming where `risk_fraction` came from. Empty before one was
    #: resolved. A fraction with no stated provenance is a number something chose.
    basis: str = ""
    #: The ceilings that actually reduced the size, in the order applied.
    caps: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    #: The contract this plan was computed under, so a future reader can ask
    #: which policy produced a figure they are looking at.
    contract_version: int = RISK_POLICY_CONTRACT_VERSION
    #: When the declaration behind `equity` and `risk_fraction` was made.
    declared_at: datetime | Absent = field(
        default_factory=lambda: Absent("no declaration was read")
    )

    def __post_init__(self) -> None:
        require_text(self.symbol, "symbol")
        if not isinstance(self.status, PlanningStatus):
            raise TypeError(
                f"status must be a PlanningStatus, got {type(self.status).__name__}"
            )
        if not isinstance(self.missing, tuple):
            raise TypeError("missing must be a tuple of str")
        for item in self.missing:
            require_text(item, "missing entry")
        if self.status is PlanningStatus.REFUSED and not self.reason:
            raise ValueError(
                "a REFUSED trade plan carries the reason it was refused; a "
                "refusal with no stated cause is indistinguishable from silence"
            )
        if self.status is PlanningStatus.PLANNED and self.reason:
            raise ValueError(
                "a PLANNED trade plan carries a size and no reason for having "
                "none; holding both says two different things"
            )
        if self.reason:
            require_text(self.reason, "reason")
        if self.status is PlanningStatus.NOT_EVALUABLE and not self.missing:
            raise ValueError(
                "a NOT_EVALUABLE plan names what is missing; one that named "
                "nothing would read as a system that simply declined"
            )
        if self.status is PlanningStatus.PLANNED and not isinstance(
            self.quantity, Quantity
        ):
            raise ValueError(
                "a PLANNED trade plan carries a quantity; reporting a status "
                "that disagrees with the value is how a refusal becomes a number"
            )
        if self.status is not PlanningStatus.PLANNED and isinstance(
            self.quantity, Quantity
        ):
            raise ValueError(
                f"a {self.status.value} trade plan carries a quantity; a size "
                "beside a plan that was not produced reads as a trade that was"
            )
        if not isinstance(self.portfolio_impact, Absent):
            raise TypeError(
                "portfolio_impact is an Absent in this build: no portfolio is "
                "read, and a measured-looking value here would claim otherwise"
            )
        if not isinstance(self.declared_at, Absent):
            object.__setattr__(
                self, "declared_at", require_utc(self.declared_at, "declared_at")
            )

    @property
    def has_figures(self) -> bool:
        """Whether the arithmetic ran and produced a size. Never *whether good*."""
        return self.status is PlanningStatus.PLANNED

    @property
    def fraction_text(self) -> str | Absent:
        """The declared fraction as canonical text, for a surface to print."""
        if isinstance(self.risk_fraction, Absent):
            return self.risk_fraction
        return canonical_decimal_text(self.risk_fraction)

    @property
    def ceiling_text(self) -> str:
        return canonical_decimal_text(self.ceiling)


def budget_from(
    declaration: RiskPolicyDeclaration,
    *,
    budget_id: str = PLANNING_BUDGET_ID,
    risk_policy_version: int = RISK_POLICY_CONTRACT_VERSION,
) -> RiskBudget:
    """The specification's per-trade ceiling, as the `RiskBudget` the engines take.

    **The first producer of a `RiskBudget` in `src/`.** Before this function the
    type existed, was persisted, was versioned and was evaluated against — and was
    constructed only in tests, so no product surface could reach any of it.

    The budget carries exactly one limit: `PER_TRADE_RISK`, as
    `PERCENT_OF_EQUITY`, valued at `SPECIFICATION_PER_TRADE_CEILING`, severity
    `HARD_BLOCK`, and **no `default_below_ceiling`**. The specification states a
    maximum and states no default; supplying one here would invent the owner's
    risk appetite at exactly the point the specification declines to.

    ``effective_from`` and the audit block are the declaration's own instant, so
    the same declaration produces the same budget forever — no clock is read.
    """
    if not isinstance(declaration, RiskPolicyDeclaration):
        raise TypeError(
            f"declaration must be a RiskPolicyDeclaration, got "
            f"{type(declaration).__name__}"
        )
    ceiling = RiskLimit(
        limit_id=CEILING_LIMIT_ID,
        scope=LimitScope.PER_TRADE_RISK,
        value=SPECIFICATION_PER_TRADE_CEILING,
        unit=LimitUnit.PERCENT_OF_EQUITY,
        period=LimitPeriod.NONE,
        severity=LimitSeverity.HARD_BLOCK,
    )
    return RiskBudget(
        budget_id=budget_id,
        risk_policy_version=risk_policy_version,
        effective_from=declaration.declared_at,
        limits=(ceiling,),
        audit=RecordAudit.frozen_at(declaration.declared_at),
        note=SPECIFICATION_CEILING_SOURCE,
    )


def sizing_policy_from(
    declaration: RiskPolicyDeclaration,
    *,
    policy_id: str = PLANNING_POLICY_ID,
) -> SizingPolicy:
    """The owner's declared fraction, as the `SizingPolicy` the sizer takes.

    The fraction travels here rather than onto the budget's ceiling because that
    is what it is: `fraction_for`'s source 1, *"the owner's own choice"*. A
    declaration with no fraction produces a policy whose `risk_fraction` is
    `Absent`, and the sizer then resolves nothing and says so — which is the
    behaviour `fmis.position_sizing.policy` exists to guarantee.

    The staleness bounds stay `Absent`. The owner has configured none, and an age
    judged against a bound this function chose would be a threshold invented at
    exactly the point the specification declines to state one.
    """
    if not isinstance(declaration, RiskPolicyDeclaration):
        raise TypeError(
            f"declaration must be a RiskPolicyDeclaration, got "
            f"{type(declaration).__name__}"
        )
    return SizingPolicy(
        policy_id=policy_id,
        risk_fraction=declaration.per_trade_fraction,
    )


def _no_trade_plan(symbol: str, reason: str) -> TradeRiskPlan:
    return TradeRiskPlan(
        symbol=symbol,
        status=PlanningStatus.NO_TRADE_PLAN,
        direction=Absent(reason),
    )


def _missing_declared_inputs(declaration: RiskPolicyDeclaration) -> tuple[str, ...]:
    """Which values the owner has not declared. **Named, never defaulted.**

    Equity cannot appear here: a declaration validates it positive at
    construction, so a declaration that exists has capital. The fraction can, and
    it is the one input this system will not choose on the owner's behalf.
    """
    if declaration.states_a_fraction:
        return ()
    return (
        "a per-trade risk fraction. Declare `per_trade_fraction` — a fraction, "
        f"not a percentage, at most "
        f"{canonical_decimal_text(SPECIFICATION_PER_TRADE_CEILING)}. None is "
        "assumed: the specification states a ceiling and no default, and sizing "
        "at the ceiling would make the ceiling the target",
    )


def _from_recommendation(
    symbol: str,
    recommendation: PositionRecommendation,
    declaration: RiskPolicyDeclaration,
) -> TradeRiskPlan:
    """Copy what the sizer produced. **Nothing is recomputed here.**

    `missing` names the owner's own un-declared inputs; `reason` is the engine's
    own sentence for why there is no number. They are separate because they have
    separate remedies: one is *"declare this"* and one is *"this candidate's
    geometry does not admit a size"*, and a surface that merged them would ask
    the owner to configure their way out of a transposed stop.
    """
    proposal = recommendation.proposal
    quote = proposal.market.quote_asset
    risk_distance = proposal.risk_distance
    risk_per_unit: Money | Absent = (
        Money(risk_distance, quote)
        if isinstance(risk_distance, Decimal)
        else risk_distance
    )
    reward_risk: str | Absent
    if isinstance(recommendation.planned_risk_reward, Absent):
        reward_risk = recommendation.planned_risk_reward
    else:
        reading = recommendation.planned_risk_reward
        # The division shown, not merely its result: `AR`-3's rule, and the
        # reason `RiskRewardReading` stores the pair rather than a quotient.
        reward_risk = f"{canonical_decimal_text(reading.ratio)} ({reading.arithmetic})"
    reason = ""
    if isinstance(recommendation.quantity, Absent):
        reason = recommendation.quantity.reason
    if recommendation.outcome is SizingOutcome.SIZED:
        status = PlanningStatus.PLANNED
        missing: tuple[str, ...] = ()
    elif recommendation.outcome is SizingOutcome.UNDETERMINED:
        status = PlanningStatus.NOT_EVALUABLE
        # The declared inputs first, because those are the ones the owner can
        # act on. The engine's own sentence is kept in `reason` and is never
        # dropped, so an undetermined result this function did not anticipate
        # still arrives on the page with its cause attached.
        missing = _missing_declared_inputs(declaration) or (reason,)
    else:
        status = PlanningStatus.REFUSED
        missing = ()
    return TradeRiskPlan(
        symbol=symbol,
        status=status,
        missing=missing,
        reason=reason,
        direction=proposal.direction.value,
        entry=proposal.entry,
        invalidation=proposal.stop,
        risk_per_unit=risk_per_unit,
        equity=recommendation.equity,
        risk_fraction=recommendation.risk_fraction,
        money_at_risk=recommendation.money_at_risk,
        quantity=recommendation.quantity,
        notional=recommendation.expected_exposure,
        reward_risk=reward_risk,
        basis=recommendation.basis,
        caps=tuple(recommendation.caps),
        notes=tuple(recommendation.notes),
        declared_at=declaration.declared_at,
    )


def plan_for(
    assessment: Any,
    *,
    declaration: RiskPolicyDeclaration,
    account: AccountId | None = None,
    book: Book = PLANNING_BOOK,
) -> TradeRiskPlan:
    """One assessment's trade plan, or exactly which input it has not got.

    Duck-typed over the assessment exactly as `fmis.position_sizing.inputs` and
    `fmis.today.sections` already read the same objects: this function imports
    nothing from `fmis.swing_setup` and compares no `SetupState`. *"Has a
    direction"* is the engine's own fact and is the only thing consulted — a
    `WAIT` result falls out of it without this layer naming the state.
    """
    if not isinstance(declaration, RiskPolicyDeclaration):
        raise TypeError(
            f"declaration must be a RiskPolicyDeclaration, got "
            f"{type(declaration).__name__}"
        )
    symbol = require_text(getattr(assessment, "symbol", ""), "symbol")
    if getattr(assessment, "direction", None) is None:
        return _no_trade_plan(
            symbol,
            "The engine states no direction for this symbol, so there is no "
            "trade to plan. Nothing is missing and nothing is wrong.",
        )
    scoped = AccountId(PLANNING_ACCOUNT) if account is None else account
    proposals = plans_source(assessment, account=scoped, book=book)
    if isinstance(proposals, Absent):
        return TradeRiskPlan(
            symbol=symbol,
            status=PlanningStatus.NOT_EVALUABLE,
            missing=(proposals.reason,) + _missing_declared_inputs(declaration),
            reason=proposals.reason,
            direction=assessment.direction.value,
            equity=declaration.equity,
            risk_fraction=declaration.per_trade_fraction,
            declared_at=declaration.declared_at,
        )
    sizer = PositionSizer(policy=sizing_policy_from(declaration))
    recommendation = sizer.size(
        proposals,
        equity=declaration.equity,
        budget=budget_from(declaration),
        # `None`, never `Absent`: no portfolio was read at all, which is a
        # different fact from a portfolio whose headroom could not be measured.
        remaining_open_risk=None,
    )
    return _from_recommendation(symbol, recommendation, declaration)


@dataclass(frozen=True, slots=True)
class _OneResult:
    """The two attributes `proposals_from_results` duck-types over, and no more.

    A named shape rather than a dynamically-built object: the fields this shim
    has to supply are then visible, and a change to what that function reads
    fails here instead of at an attribute lookup inside it.
    """

    assessment: Any

    @property
    def requested_symbol(self) -> str:
        return self.assessment.symbol


def plans_source(
    assessment: Any, *, account: AccountId, book: Book
) -> PositionProposal | Absent:
    """One assessment as a candidate, through the package that already does it.

    A one-element call into `proposals_from_results` rather than a second reading
    of the same fields: the refusals *"has no stop"* and *"states no reference
    price"* are `fmis.position_sizing.inputs`' own wording, and a second
    implementation would be a second place they could drift.
    """
    found = proposals_from_results(
        [_OneResult(assessment)], account=account, book=book
    )
    return found[assessment.symbol]


def plans_for_results(
    results: Any,
    *,
    declaration: RiskPolicyDeclaration,
    account: AccountId | None = None,
    book: Book = PLANNING_BOOK,
) -> dict[str, TradeRiskPlan]:
    """A plan for every scanned symbol that produced an assessment.

    **Every symbol, not every candidate.** A symbol dropped from this mapping
    would render as one nobody planned, and the whole point of the surface above
    is that a `WAIT` says so in its own words instead of being silent.
    """
    plans: dict[str, TradeRiskPlan] = {}
    for result in results:
        assessment = getattr(result, "assessment", None)
        if assessment is None:
            continue
        # Keyed on the **assessment's** symbol, not the requested one, because
        # that is the key the consumer looks a plan up by: a decision record is
        # what was *concluded* and is filed under the assessment's name, exactly
        # as `fmis.swing_workspace.sections.symbol_decisions` files it. Keying on
        # the request would silently produce a mapping whose every lookup missed
        # for any symbol whose request and conclusion spell it differently.
        #
        # First wins, for the same reason that function keeps the first: a symbol
        # requested twice is one market answered twice, and two plans under one
        # key would mean the page shows whichever arrived last.
        if assessment.symbol in plans:
            continue
        plans[assessment.symbol] = plan_for(
            assessment, declaration=declaration, account=account, book=book
        )
    return plans
