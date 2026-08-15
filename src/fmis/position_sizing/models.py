"""The shapes an approval is made of: a candidate, a size, a reason, a verdict.

**`ApprovalResult` is a deterministic fact, not an opinion.** Every value on it is
arithmetic over the owner's own limits and the portfolio the store already holds.
No model is consulted, no probability is attached, and there is no field on any
type in this module that could hold *"take this trade"* or *"skip this trade"* —
a guard test asserts the package names neither. `APPROVED` means *the owner's own
limits permit a position of this size*; it does not mean the trade is a good idea,
and nothing here claims to know.

**Three statuses, and the third is not a soft second.** `APPROVED` · `BLOCKED` ·
`INDETERMINATE`. `AP` §15.5 property 2 is the rule this module makes structural
rather than disciplinary: an indeterminate result *"looks like 'no problem found'
unless rendered distinctly"*, so it is a different member of a different enum and
`ApprovalResult` refuses to be `APPROVED` while holding a single indeterminate
reason. The refusal is in `__post_init__`, so a surface cannot construct the
flattering combination even by accident.

**A reason carries its own class and its own scope, and the two are different
questions.** The class — blocking, warning, indeterminate — is *what it costs*.
The scope — portfolio or trade — is *what it is about*. Collapsing them into one
severity ladder would make *"your open-risk budget is spent"* and *"this stop is
on the wrong side of the entry"* comparable, and they are not: one is about the
book and one is about the idea.

**A size is a product and every figure derived from it is recomputed from the
size that was actually produced**, never from the allowance that produced it.
A recommendation whose `money_at_risk` was the allowance rather than
`risk distance × quantity` would be right in every test with exact arithmetic and
wrong the first time a venue's lot size forced the owner to round down.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fmis.accounts import AccountId, Book, MarketId
from fmis.money import AssetCode, Money, Quantity, canonical_decimal_text
from fmis.plan import TradePlan
from fmis.portfolio_risk import (
    RISK_BASIS,
    PortfolioConstraintCheck,
    PortfolioImpact,
    PortfolioRiskError,
    PortfolioState,
    ProposedTrade,
    RiskGeometryError,
    direction_of,
    stop_distance,
)
from fmis.positions import PositionDirection
from fmis.provenance import Absent, ValueOrigin
from fmis.records import (
    DomainValidationError,
    require_member,
    require_text,
    require_tuple_of,
    require_utc,
)
from fmis.snapshotting import RiskRewardReading, TradeDirection

__all__ = [
    "PositionSizingError",
    "SizingRefusedError",
    "ApprovalStatus",
    "ReasonScope",
    "ReasonClass",
    "SizingOutcome",
    "ApprovalReason",
    "PositionProposal",
    "PositionRecommendation",
    "ApprovalResult",
]


class PositionSizingError(PortfolioRiskError):
    """Base class for every sizing and approval failure.

    A `PortfolioRiskError` rather than a new root, because a caller catching
    *"something in the risk layer refused"* must not have to learn a second name
    the day sizing arrived. The refusals themselves are values on
    `ApprovalResult`, not exceptions — an exception is what happens when the
    engine cannot be **run**, and a block is what happens when it runs and says
    no.
    """


class SizingRefusedError(DomainValidationError, PositionSizingError):
    """A sizing call whose arguments cannot all be true at once.

    Both a `DomainValidationError` and a `PositionSizingError`, so neither
    `except` clause is a lie — the same pairing `RiskGeometryError` and
    `PlanPlacementError` already use one layer down.
    """


class ApprovalStatus(Enum):
    """What the owner's own limits say about a position of the proposed size.

    **`INDETERMINATE` is never a milder `APPROVED`.** It means the engine could
    not measure something it was asked to measure — an unmarked holding, an
    unrecorded stop, an equity figure nobody has observed — and the honest
    reading is *"this was not checked"*, not *"this was checked and was fine"*.
    """

    APPROVED = "approved"
    BLOCKED = "blocked"
    INDETERMINATE = "indeterminate"


class ReasonScope(Enum):
    """What a reason is *about*.

    Two members, because the milestone's two evaluations are independent: the
    portfolio's own state against the owner's limits, and the candidate's own
    arithmetic. A reason that could be either would let a portfolio breach be
    read as a defect in the idea.
    """

    PORTFOLIO = "portfolio"
    TRADE = "trade"


class ReasonClass(Enum):
    """What a reason *costs*.

    `BLOCKING` — the system refuses to state that this size is within the
    owner's limits. It cannot, and does not claim to, stop the owner trading
    anyway; `SWING_TRADING_MVP_BLUEPRINT_V1` §7.1 defines a hard block in exactly
    those terms.

    `WARNING` — shown beside the value it qualifies, never a gate.

    `INDETERMINATE` — something could not be measured. Its own member rather than
    a flag on `WARNING`, because a warning is a statement about the trade and this
    is a statement about the engine's own reach.
    """

    BLOCKING = "blocking"
    WARNING = "warning"
    INDETERMINATE = "indeterminate"


class SizingOutcome(Enum):
    """Why a recommendation does or does not carry a quantity.

    The distinction the approval status depends on, and the reason it is a stored
    member rather than inferred from `quantity is Absent`. *"The arithmetic is
    impossible"* and *"an input is not known"* both leave no quantity, and they
    are a block and an indeterminate result respectively — inferring one from the
    other would make a portfolio with no recorded equity look like a portfolio
    with a transposed stop.
    """

    SIZED = "sized"
    #: The arithmetic ran and produced nothing usable: a stop the entry has
    #: already passed, or a risk allowance that is not positive.
    REFUSED = "refused"
    #: An input the size depends on is not known, so no arithmetic was attempted.
    UNDETERMINED = "undetermined"


@dataclass(frozen=True, slots=True)
class ApprovalReason:
    """One deterministic statement about this candidate, with its own provenance.

    ``code`` is stable and greppable so a surface, a test and a future report can
    all name the same rule. ``source`` names where the rule comes from — an
    owner-configured limit id, a design section, an arithmetic refusal. **A reason
    with no stated source would be a judgement this package invented, and there
    are none.**
    """

    code: str
    scope: ReasonScope
    classification: ReasonClass
    statement: str
    source: str
    subject: str | Absent = field(
        default_factory=lambda: Absent("this reason names no single subject")
    )

    def __post_init__(self) -> None:
        for name in ("code", "statement", "source"):
            object.__setattr__(self, name, require_text(getattr(self, name), name))
        require_member(self.scope, ReasonScope, "scope")
        require_member(self.classification, ReasonClass, "classification")
        if not isinstance(self.subject, Absent):
            object.__setattr__(self, "subject", require_text(self.subject, "subject"))

    @property
    def origin(self) -> ValueOrigin:
        """`POLICY_DERIVED` — a measured fact read against an asserted limit."""
        return ValueOrigin.POLICY_DERIVED

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "scope": self.scope.value,
            "classification": self.classification.value,
            "statement": self.statement,
            "source": self.source,
            "subject": (
                {"absent": self.subject.to_payload()}
                if isinstance(self.subject, Absent)
                else {"value": self.subject}
            ),
        }


@dataclass(frozen=True, slots=True)
class PositionProposal:
    """A candidate before it has a size — what the owner is considering.

    **Deliberately not a `ProposedTrade`, and the missing field is the point.**
    `fmis.portfolio_risk.ProposedTrade` requires a quantity, because portfolio
    impact is a question about exposure that already has a number. This is the
    input to the step *before* that one: the market, the side, the entry, the
    stop and the targets, with the quantity absent because producing it is this
    package's entire job. `sized()` turns one into the other, and it is the only
    way a quantity reaches the portfolio engine from here.

    **A stop on the wrong side of the entry is accepted here and refused later.**
    It would be easy to raise in `__post_init__`, and it would be wrong: *"is this
    trade takeable"* is the question the owner asked, and a transposed stop is one
    of the answers. `risk_distance` returns `Absent(reason)` and the approval
    engine turns it into a blocking reason with the arithmetic printed — which is
    a usable answer, where a traceback is not.

    `ASSERTED` throughout. Everything on it is the owner's statement of intent,
    and intent can be wrong.
    """

    account: AccountId
    market: MarketId
    book: Book
    direction: TradeDirection
    entry: Decimal
    stop: Decimal
    targets: tuple[Decimal, ...] = ()
    plan_id: str | Absent = field(
        default_factory=lambda: Absent("this candidate is not a recorded commitment")
    )

    def __post_init__(self) -> None:
        if not isinstance(self.account, AccountId):
            raise TypeError("account must be an AccountId")
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        require_member(self.book, Book, "book")
        require_member(self.direction, TradeDirection, "direction")
        if not self.direction.is_directional:
            raise DomainValidationError(
                "a decision not to act proposes no exposure, has no stop to be "
                "wrong about and needs no size; it is a proposal outcome rather "
                "than a candidate for sizing"
            )
        for name in ("entry", "stop"):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
            if value <= 0:
                raise DomainValidationError(f"{name} must be positive, got {value}")
            object.__setattr__(self, name, Decimal(canonical_decimal_text(value)))
        require_tuple_of(self.targets, Decimal, "targets")
        normalized = []
        for position, target in enumerate(self.targets):
            if target <= 0:
                raise DomainValidationError(
                    f"targets[{position}] must be positive, got {target}"
                )
            normalized.append(Decimal(canonical_decimal_text(target)))
        object.__setattr__(self, "targets", tuple(normalized))
        if not isinstance(self.plan_id, Absent):
            object.__setattr__(self, "plan_id", require_text(self.plan_id, "plan_id"))

    # -- identity -----------------------------------------------------------

    @property
    def origin(self) -> ValueOrigin:
        """`ASSERTED`. A proposal is intent, and intent can be wrong."""
        return ValueOrigin.ASSERTED

    @property
    def side(self) -> PositionDirection:
        """The candidate's side in the position vocabulary the geometry speaks.

        Read through `fmis.portfolio_risk.direction_of` rather than mapped here,
        so the one place `NO_TRADE` is refused a direction stays one place.
        """
        return direction_of(self.direction)

    @property
    def scope(self) -> tuple[str, str, str]:
        """`(account, market, book)` — the triple one open position lives in."""
        return (self.account.value, self.market.value, self.book.value)

    @property
    def quote_asset(self) -> AssetCode:
        return self.market.quote_asset

    # -- geometry, or the reason there is none ------------------------------

    @property
    def risk_distance(self) -> Decimal | Absent:
        """`entry − stop` the right way round, or why there is no distance.

        Delegated to `fmis.portfolio_risk.stop_distance`, which owns the sign
        rule for the whole repository. A second expression of *"below the entry
        on one side, above it on the other"* is the failure mode that makes a
        portfolio's largest position look like its smallest, and this package
        does not write one.
        """
        try:
            return stop_distance(self.side, entry=self.entry, stop=self.stop)
        except RiskGeometryError as error:
            return Absent(str(error))

    @property
    def first_target(self) -> Decimal | Absent:
        if not self.targets:
            return Absent("this candidate states no target")
        return self.targets[0]

    @property
    def reward_distance(self) -> Decimal | Absent:
        """The distance to the nearest target, or why it is not a reward at all.

        **The same subtraction as the risk distance, with the entry and the target
        exchanged.** `stop_distance(side, entry=target, stop=entry)` is
        `target − entry` on one side and `entry − target` on the other, which is
        exactly the reward distance — and it refuses a target sitting on the
        stop's side of the entry for the identical reason it refuses a stop
        sitting on the target's side. One implementation of the sign rule, used
        twice, rather than two implementations that agree until they do not.
        """
        target = self.first_target
        if isinstance(target, Absent):
            return target
        try:
            return stop_distance(self.side, entry=target, stop=self.entry)
        except RiskGeometryError:
            return Absent(
                f"the nearest target {canonical_decimal_text(target)} is on the "
                f"stop's side of the entry {canonical_decimal_text(self.entry)}; a "
                "target the trade reaches by going wrong is a stop with the wrong "
                "label, and the reward distance over it would be negative"
            )

    @property
    def planned_risk_reward(self) -> RiskRewardReading | Absent:
        """The pair `(risk distance, reward distance)` — never a stored quotient.

        `RiskRewardReading` is the domain's own type for exactly this and divides
        at read time, which is `AP` §5.3's rule (*"no quotient is ever a stored
        field"*) and the same shape `fmis.plan.adherence.planned_risk_reward`
        returns for a recorded commitment.
        """
        risk = self.risk_distance
        if isinstance(risk, Absent):
            return Absent(f"there is no risk distance: {risk.reason}")
        reward = self.reward_distance
        if isinstance(reward, Absent):
            return reward
        return RiskRewardReading(risk_distance=risk, reward_distance=reward)

    # -- projections ---------------------------------------------------------

    def sized(self, quantity: Quantity) -> ProposedTrade:
        """This candidate with a size, as the portfolio engine's own input type.

        The single crossing from *"what the owner is considering"* to *"what the
        portfolio would then hold"*. Every impact figure downstream is computed by
        `fmis.portfolio_risk`, so a size produced here and an exposure computed
        there can never be two different candidates.
        """
        if not isinstance(quantity, Quantity):
            raise TypeError(
                f"quantity must be a Quantity, got {type(quantity).__name__}"
            )
        return ProposedTrade(
            account=self.account,
            market=self.market,
            book=self.book,
            direction=self.direction,
            entry=self.entry,
            stop=self.stop,
            quantity=quantity,
            plan_id=self.plan_id,
        )

    @classmethod
    def from_plan(
        cls, plan: TradePlan, *, account: AccountId, entry: Decimal
    ) -> PositionProposal:
        """Size a commitment the owner already recorded, without retyping it.

        The market, the book, the side, **the stop** and the target ladder all
        come from the plan and cannot be overridden: `initial_invalidation` is the
        field the whole plan entity exists to keep immutable, and a sizing helper
        that let a caller pass a different stop would be the edit path it was
        built to prevent. `ProposedTrade.from_plan` states the identical rule for
        the sized half.
        """
        if not isinstance(plan, TradePlan):
            raise TypeError(f"plan must be a TradePlan, got {type(plan).__name__}")
        return cls(
            account=account,
            market=plan.market,
            book=plan.book,
            direction=plan.direction,
            entry=entry,
            stop=plan.initial_invalidation,
            targets=plan.targets,
            plan_id=plan.plan_id,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "account": self.account.value,
            "market": self.market.to_payload(),
            "book": self.book.value,
            "direction": self.direction.value,
            "entry": canonical_decimal_text(self.entry),
            "stop": canonical_decimal_text(self.stop),
            "targets": [canonical_decimal_text(target) for target in self.targets],
            "plan_id": (
                {"absent": self.plan_id.to_payload()}
                if isinstance(self.plan_id, Absent)
                else {"value": self.plan_id}
            ),
        }


@dataclass(frozen=True, slots=True)
class PositionRecommendation:
    """A size, everything derived from it, and what decided it.

    **A recommendation about *how much*, never about *whether*.** The name is the
    brief's own and the distinction is load-bearing: this object answers *"a
    position of what size would put the owner's stated fraction of equity at
    risk, under their own ceilings"*. Whether to open it at all is
    `ApprovalStatus`, and whether to want to is the owner's.

    **`caps` is why the number is smaller than the owner asked for.** A size
    silently reduced by an open-risk headroom the owner never saw is the failure
    `SWING_TRADING_MVP_BLUEPRINT_V1` §9.4 refusal 3 names — *"never size past a
    binding limit without displaying the binding limit"*. It holds only the
    ceilings that actually **reduced** the size, in the order they were applied,
    so a surface can ask whether the tuple is empty rather than parse prose; the
    arithmetic that produced the unreduced allowance is in `notes`.
    """

    proposal: PositionProposal
    outcome: SizingOutcome
    quantity: Quantity | Absent
    risk_fraction: Decimal | Absent
    money_at_risk: Money | Absent
    expected_exposure: Money | Absent
    planned_risk_reward: RiskRewardReading | Absent
    equity: Money | Absent
    #: One sentence naming where `risk_fraction` came from — the owner's flag,
    #: the ceiling's stated default, or the ceiling itself. A fraction with no
    #: stated provenance is a number this package would have chosen.
    basis: str
    caps: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, PositionProposal):
            raise TypeError("proposal must be a PositionProposal")
        require_member(self.outcome, SizingOutcome, "outcome")
        if not isinstance(self.quantity, (Quantity, Absent)):
            raise TypeError("quantity must be a Quantity or Absent")
        if (self.outcome is SizingOutcome.SIZED) != isinstance(self.quantity, Quantity):
            raise DomainValidationError(
                "a SIZED recommendation carries a quantity and an unsized one "
                "carries the reason it has none; reporting an outcome that "
                "disagrees with the value is how a refusal becomes a number"
            )
        if isinstance(self.quantity, Quantity):
            if self.quantity.amount <= 0:
                raise DomainValidationError(
                    f"a recommended quantity must be positive, got {self.quantity}; "
                    "a non-positive size is a refusal to size and is reported as "
                    "one rather than as a number"
                )
            if self.quantity.asset != self.proposal.market.base_asset:
                raise DomainValidationError(
                    f"the recommended quantity is denominated in "
                    f"{self.quantity.asset} but the market trades "
                    f"{self.proposal.market.base_asset} as its base asset"
                )
        if not isinstance(self.risk_fraction, (Decimal, Absent)):
            raise TypeError("risk_fraction must be a Decimal or Absent")
        if isinstance(self.risk_fraction, Decimal):
            if self.risk_fraction <= 0:
                raise DomainValidationError(
                    f"risk_fraction must be positive, got {self.risk_fraction}; a "
                    "non-positive fraction is a refusal to trade, which is the "
                    "owner's decision rather than an arithmetic result"
                )
            object.__setattr__(
                self,
                "risk_fraction",
                Decimal(canonical_decimal_text(self.risk_fraction)),
            )
        for name in ("money_at_risk", "expected_exposure", "equity"):
            if not isinstance(getattr(self, name), (Money, Absent)):
                raise TypeError(f"{name} must be a Money or Absent")
        if not isinstance(self.planned_risk_reward, (RiskRewardReading, Absent)):
            raise TypeError("planned_risk_reward must be a RiskRewardReading or Absent")
        object.__setattr__(self, "basis", require_text(self.basis, "basis"))
        require_tuple_of(self.caps, str, "caps")
        require_tuple_of(self.notes, str, "notes")

    @property
    def origin(self) -> ValueOrigin:
        """`POLICY_DERIVED` — measured equity read against an asserted rule."""
        return ValueOrigin.POLICY_DERIVED

    @property
    def is_sized(self) -> bool:
        return self.outcome is SizingOutcome.SIZED

    @property
    def expected_r_multiple(self) -> Decimal | Absent:
        """Reward ÷ risk against the **nearest** target. Divided here, stored nowhere.

        **Not a probability and not an expectation in the statistical sense.**
        It is what one unit of risk buys if the nearest target is reached and the
        stop is honoured, and this system has no calibrated likelihood of either —
        `Probability` is `NOT_CALIBRATED` everywhere in this repository and
        nothing here changes that.
        """
        if isinstance(self.planned_risk_reward, Absent):
            return self.planned_risk_reward
        return self.planned_risk_reward.ratio

    @property
    def risk_basis(self) -> str:
        """What every capital-at-risk figure here assumes, stated once."""
        return RISK_BASIS

    def sized_trade(self) -> ProposedTrade | Absent:
        """The candidate at the recommended size, for the portfolio engine."""
        if not isinstance(self.quantity, Quantity):
            return Absent(
                f"no size was produced: {self.quantity.reason}"
            )
        return self.proposal.sized(self.quantity)

    def to_payload(self) -> dict[str, Any]:
        """For export and rendering. **There is deliberately no decoder.**"""
        return {
            "proposal": self.proposal.to_payload(),
            "outcome": self.outcome.value,
            "quantity": _maybe(self.quantity, lambda value: value.to_payload()),
            "risk_fraction": _maybe(self.risk_fraction, canonical_decimal_text),
            "money_at_risk": _maybe(
                self.money_at_risk, lambda value: value.to_payload()
            ),
            "expected_exposure": _maybe(
                self.expected_exposure, lambda value: value.to_payload()
            ),
            "planned_risk_reward": _maybe(
                self.planned_risk_reward, lambda value: value.to_payload()
            ),
            "expected_r_multiple": _maybe(
                self.expected_r_multiple, canonical_decimal_text
            ),
            "equity": _maybe(self.equity, lambda value: value.to_payload()),
            "basis": self.basis,
            "caps": list(self.caps),
            "notes": list(self.notes),
            "risk_basis": self.risk_basis,
        }


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    """The whole answer: a status, the reasons behind it, and the size it is about.

    **The status is derived from the reasons and is checked against them here.**
    A result cannot be `APPROVED` while holding a blocking or an indeterminate
    reason, and cannot be `BLOCKED` or `INDETERMINATE` while holding none of the
    corresponding class. That invariant lives in `__post_init__` rather than in
    the engine, so a second caller building one by hand — a test fixture, a future
    surface, a replay — cannot produce the flattering combination the engine
    refuses to.

    **An impact requires a size, and a size does not guarantee an impact.** A
    portfolio impact is a question about exposure with a number attached, and
    there is no number to attach when the candidate could not be sized. The
    converse does not hold: a candidate in a book this reading does not cover is
    perfectly sizeable and still has no impact against *this* portfolio, because
    books never share capacity and evaluating it here would move risk between two
    pools the whole design keeps apart. The invariant is therefore one-directional
    and is asserted in that direction only.
    """

    proposal: PositionProposal
    recommendation: PositionRecommendation
    status: ApprovalStatus
    reasons: tuple[ApprovalReason, ...]
    state: PortfolioState
    before_check: PortfolioConstraintCheck
    impact: PortfolioImpact | Absent
    evaluated_at: datetime
    policy_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, PositionProposal):
            raise TypeError("proposal must be a PositionProposal")
        if not isinstance(self.recommendation, PositionRecommendation):
            raise TypeError("recommendation must be a PositionRecommendation")
        if self.recommendation.proposal != self.proposal:
            raise DomainValidationError(
                "the recommendation sizes a different candidate from the one this "
                "result is about; two candidates in one answer is an answer to "
                "neither"
            )
        require_member(self.status, ApprovalStatus, "status")
        require_tuple_of(self.reasons, ApprovalReason, "reasons")
        codes = [reason.code for reason in self.reasons]
        if len(set(codes)) != len(codes):
            raise DomainValidationError(
                f"a reason code appears twice ({sorted(codes)}); one rule, one "
                "statement, or a reader counts the same objection as two"
            )
        if not isinstance(self.state, PortfolioState):
            raise TypeError("state must be a PortfolioState")
        if not isinstance(self.before_check, PortfolioConstraintCheck):
            raise TypeError("before_check must be a PortfolioConstraintCheck")
        if not isinstance(self.impact, (PortfolioImpact, Absent)):
            raise TypeError("impact must be a PortfolioImpact or Absent")
        if isinstance(self.impact, PortfolioImpact) and not self.recommendation.is_sized:
            raise DomainValidationError(
                "a portfolio impact needs a size; an impact over no size would "
                "report the portfolio as unchanged, which is true and useless"
            )
        if (
            isinstance(self.impact, PortfolioImpact)
            and self.impact.before is not self.state
        ):
            raise DomainValidationError(
                "the impact was computed against a different portfolio reading "
                "from the one this result carries; two readings of one portfolio "
                "in one answer is how a before/after comparison stops being one"
            )
        object.__setattr__(
            self, "evaluated_at", require_utc(self.evaluated_at, "evaluated_at")
        )
        object.__setattr__(
            self, "policy_version", require_text(self.policy_version, "policy_version")
        )
        self._validate_status()

    def _validate_status(self) -> None:
        """The one rule that makes this object safe, enforced rather than trusted.

        Blocking outranks indeterminate: *"this breaches a limit you set"* and
        *"this could not be measured"* can both be true at once, and reporting the
        second would drop a known breach in favour of an unknown one.
        """
        if self.blocking:
            expected = ApprovalStatus.BLOCKED
        elif self.indeterminate:
            expected = ApprovalStatus.INDETERMINATE
        else:
            expected = ApprovalStatus.APPROVED
        if self.status is not expected:
            raise DomainValidationError(
                f"this result is {self.status.value} but its reasons make it "
                f"{expected.value}: {len(self.blocking)} blocking and "
                f"{len(self.indeterminate)} indeterminate reason(s). A status that "
                "disagrees with its own reasons is the one failure this object "
                "exists to prevent"
            )

    # -- the three registers, kept in three lists ---------------------------

    @property
    def blocking(self) -> tuple[ApprovalReason, ...]:
        return self._of(ReasonClass.BLOCKING)

    @property
    def warnings(self) -> tuple[ApprovalReason, ...]:
        return self._of(ReasonClass.WARNING)

    @property
    def indeterminate(self) -> tuple[ApprovalReason, ...]:
        return self._of(ReasonClass.INDETERMINATE)

    def _of(self, classification: ReasonClass) -> tuple[ApprovalReason, ...]:
        return tuple(
            reason
            for reason in self.reasons
            if reason.classification is classification
        )

    def scoped(self, scope: ReasonScope) -> tuple[ApprovalReason, ...]:
        """Every reason about the portfolio, or every reason about the trade."""
        require_member(scope, ReasonScope, "scope")
        return tuple(reason for reason in self.reasons if reason.scope is scope)

    @property
    def origin(self) -> ValueOrigin:
        return ValueOrigin.POLICY_DERIVED

    @property
    def is_approved(self) -> bool:
        return self.status is ApprovalStatus.APPROVED

    # -- the figures a surface prints beside the status ---------------------

    @property
    def open_risk_before(self) -> Money | Absent:
        """Total capital at risk across open positions, as the book stands.

        Answerable even when the candidate could not be sized, because it is a
        fact about the portfolio rather than about the trade — and a page that
        lost the owner's *current* open risk because one candidate had a
        transposed stop would be hiding the more important of the two numbers.
        """
        return self.state.open_risk

    @property
    def open_risk_after(self) -> Money | Absent:
        """Total capital at risk if this position were opened at this size.

        `Absent` rather than the current figure when no size was produced: a
        portfolio's risk *after* a trade nobody could size is not the risk before
        it, it is undefined, and printing the before-figure under the after-label
        is the one substitution a risk page must never make.
        """
        if isinstance(self.impact, Absent):
            return Absent(
                "no size was produced, so there is no resulting open risk: "
                f"{self.impact.reason}"
            )
        return self.impact.resulting_open_risk

    @property
    def recommended_quantity(self) -> Quantity | Absent:
        return self.recommendation.quantity

    @property
    def risk_basis(self) -> str:
        return self.recommendation.risk_basis

    def to_payload(self) -> dict[str, Any]:
        """For export and rendering. **There is deliberately no decoder.**

        `to_payload` without `from_payload` is the shape `PortfolioState`,
        `PortfolioImpact` and `Position` already use: exportable, and impossible
        to read back into the store as truth. An approval is a projection over the
        ledger and the owner's limits — recompute it and it is equal; store it and
        it drifts the first time either moves.
        """
        return {
            "status": self.status.value,
            "proposal": self.proposal.to_payload(),
            "recommendation": self.recommendation.to_payload(),
            "reasons": [reason.to_payload() for reason in self.reasons],
            "blocking": [reason.code for reason in self.blocking],
            "warnings": [reason.code for reason in self.warnings],
            "indeterminate": [reason.code for reason in self.indeterminate],
            "open_risk_before": _maybe(
                self.open_risk_before, lambda value: value.to_payload()
            ),
            "open_risk_after": _maybe(
                self.open_risk_after, lambda value: value.to_payload()
            ),
            "before_check": self.before_check.to_payload(),
            "impact": (
                {"absent": self.impact.to_payload()}
                if isinstance(self.impact, Absent)
                else {"value": self.impact.to_payload()}
            ),
            "evaluated_at": self.evaluated_at.isoformat(),
            "policy_version": self.policy_version,
            "risk_basis": self.risk_basis,
        }


def _maybe(value: Any, encode: Any) -> dict[str, Any]:
    if isinstance(value, Absent):
        return {"absent": value.to_payload()}
    return {"value": encode(value)}
