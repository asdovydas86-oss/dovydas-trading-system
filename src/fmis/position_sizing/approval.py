"""`ApprovalEngine` — *can I take this trade*, answered as arithmetic.

**Not *is this setup good*.** The setup already exists and this engine never
looks at it: no confidence, no probability, no readiness state, no risk/reward
threshold of this package's own invention reaches any branch below. What it
answers is narrower and entirely deterministic — *given the owner's own limits,
their own equity and the positions they have already recorded, does a position of
the recommended size sit inside every ceiling they set?*

**Three answers and the third is not a soft first.** `APPROVED` · `BLOCKED` ·
`INDETERMINATE`. There is no `TAKE`, no `SKIP` and no field either could be
written into; a guard test asserts the package names neither word. `AP` §15.5:
*"`EXCEEDED` on the open-risk budget is a fact; 'don't take this trade' is the
owner's conclusion."*

**Two evaluations, run independently, reported separately.**

*Portfolio* — every limit in the owner's budget, measured against the portfolio
**as it would be with this position open**, by `evaluate_constraints` through
`evaluate_impact`. Total open risk, instrument, asset, account and group
concentration are five of those limits and are not re-measured here; this module
maps each result onto a reason and adds one more thing the constraint engine
cannot know — *whether the owner configured a limit on that axis at all*. An
unconstrained axis is reported, because *"nothing was checked"* reads exactly
like *"nothing was wrong"* on a page that stays silent about it.

*Trade* — the candidate's own arithmetic: the stop's placement, whether a size
could be produced at all, how old the equity and the marks behind the figures
are, whether any open position is unmarked or unstopped, the planned risk/reward
against the owner's own minimum, and whether this bet is already held elsewhere.

**Severity is the owner's, not this engine's.** Every `RiskLimit` carries a
`LimitSeverity` the owner set, and it decides the class of the reason: a
`HARD_BLOCK` limit that is `EXCEEDED` blocks, an `ADVISORY` one warns, and a
limit that could not be measured is indeterminate or a warning by the same rule.
This module chooses no severity and holds no threshold — a test asserts it
contains no numeric literal beyond `0` and `1`.

**`AT_LIMIT` warns; `EXCEEDED` blocks.** A ceiling stated as *at most 2 %* is not
breached by a measurement that equals it, so a candidate landing exactly on the
line is approved with the headroom named — and the *next* one is blocked, which
is the arithmetic doing what the owner asked. Conflating the two would refuse a
trade the owner's own policy permits, which is the direction of error that
teaches an owner to stop reading the page.

**Blocking outranks indeterminate.** *"This breaches a limit you set"* and *"this
could not be measured"* can both be true, and reporting the second would drop a
known breach in favour of an unknown one. The ordering is enforced by
`ApprovalResult` itself, not by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fmis.accounts import OwnerContext
from fmis.money import Money, canonical_decimal_text
from fmis.portfolio_risk import (
    ClassificationMap,
    ConstraintResult,
    ExposureDimension,
    PortfolioConstraintCheck,
    PortfolioImpact,
    PortfolioRiskError,
    PortfolioState,
    evaluate_constraints,
    evaluate_impact,
    remaining_risk_capacity,
)
from fmis.provenance import Absent
from fmis.records import require_utc
from fmis.risk import LimitScope, LimitSeverity, LimitStatus, RiskBudget

from fmis.position_sizing.models import (
    ApprovalReason,
    ApprovalResult,
    ApprovalStatus,
    PositionProposal,
    PositionRecommendation,
    ReasonClass,
    ReasonScope,
    SizingOutcome,
)
from fmis.position_sizing.sizing import PositionSizer

__all__ = [
    "APPROVAL_POLICY_VERSION",
    "REQUIRED_AXES",
    "ApprovalEngine",
]

#: This build's approval rule version. Cited on every result, because a later
#: build that classes a reason differently must produce a *visibly* different
#: reading rather than silently reinterpreting an old one.
APPROVAL_POLICY_VERSION = "trade-approval-v1"

#: The concentration axes an approval states a coverage answer for, and the
#: `ExposureDimension` each one is measured on. A closed tuple rather than an
#: open scan of the budget, because the question is *"did the owner constrain
#: this axis"* and a question can only be asked about an axis somebody named.
#: The four here are the ones a single candidate lands on: the instrument it
#: trades, the asset it is a bet on, the account it consumes capacity in, and the
#: owner's own groups the asset belongs to.
REQUIRED_AXES: tuple[ExposureDimension, ...] = (
    ExposureDimension.INSTRUMENT,
    ExposureDimension.ASSET,
    ExposureDimension.ACCOUNT,
)


@dataclass(frozen=True, slots=True)
class ApprovalEngine:
    """The owner's sizer and the owner's classification, applied to one candidate.

    Frozen and configured once. A surface that built a fresh engine per candidate
    could size two candidates on one page under two different rules, and nothing
    on the page would say so.
    """

    sizer: PositionSizer
    classification: ClassificationMap

    def __post_init__(self) -> None:
        if not isinstance(self.sizer, PositionSizer):
            raise TypeError(
                f"sizer must be a PositionSizer, got {type(self.sizer).__name__}"
            )
        if not isinstance(self.classification, ClassificationMap):
            raise TypeError(
                f"classification must be a ClassificationMap, got "
                f"{type(self.classification).__name__}"
            )

    def evaluate(
        self,
        proposal: PositionProposal,
        *,
        state: PortfolioState,
        budget: RiskBudget,
        owner: OwnerContext,
        mark_age: timedelta | Absent | None = None,
        evaluated_at: datetime | None = None,
    ) -> ApprovalResult:
        """Size the candidate, then check what the portfolio would look like.

        Args:
            proposal: the candidate. Unsized — producing the size is step one.
            state: the portfolio as it stands, folded by
                `fmis.portfolio_risk`. Supplies the equity the fraction applies
                to, the exposure the limits are measured against, and the
                markets that are unmarked or unstopped.
            budget: the owner's limit generation in force at this instant.
            owner: for the owner-local calendar boundaries a periodic limit is
                measured over. Never for a threshold.
            mark_age: how old the oldest price behind `state` is, or `Absent`
                when nothing was priced, or `None` when no price source was
                consulted at all. The three are different facts and the third is
                not a failure.
            evaluated_at: the instant this answer describes. Defaults to the
                state's own `as_of`, because an approval of a portfolio reading
                is dated by that reading and nothing here reads a clock.

        Returns:
            An `ApprovalResult` — always. A candidate that cannot be sized comes
            back `BLOCKED` or `INDETERMINATE` with the reason attached.

        Raises:
            TypeError: an argument is of the wrong type.
        """
        if not isinstance(proposal, PositionProposal):
            raise TypeError(
                f"proposal must be a PositionProposal, got {type(proposal).__name__}"
            )
        if not isinstance(state, PortfolioState):
            raise TypeError(f"state must be a PortfolioState, got {type(state).__name__}")
        if not isinstance(budget, RiskBudget):
            raise TypeError(f"budget must be a RiskBudget, got {type(budget).__name__}")
        if not isinstance(owner, OwnerContext):
            raise TypeError(f"owner must be an OwnerContext, got {type(owner).__name__}")
        if mark_age is not None and not isinstance(mark_age, (timedelta, Absent)):
            raise TypeError("mark_age must be a timedelta, Absent or None")
        moment = (
            state.as_of if evaluated_at is None else require_utc(evaluated_at, "evaluated_at")
        )

        before_check = evaluate_constraints(budget, state, owner=owner)
        recommendation = self.sizer.size(
            proposal,
            equity=state.equity,
            budget=budget,
            remaining_open_risk=_binding_capacity(before_check, budget, state),
        )
        impact, impact_refusal = self._impact_of(
            recommendation, state=state, budget=budget, owner=owner
        )
        check = before_check if isinstance(impact, Absent) else impact.after_check

        reasons = self._trade_reasons(
            proposal,
            recommendation,
            state=state,
            impact=impact,
            impact_refusal=impact_refusal,
            mark_age=mark_age,
        ) + self._portfolio_reasons(
            proposal, check=check, budget=budget, impact=impact
        )
        return ApprovalResult(
            proposal=proposal,
            recommendation=recommendation,
            status=_status_of(reasons),
            reasons=reasons,
            state=state,
            before_check=before_check,
            impact=impact,
            evaluated_at=moment,
            policy_version=APPROVAL_POLICY_VERSION,
        )

    # -- the after-state ----------------------------------------------------

    def _impact_of(
        self,
        recommendation: PositionRecommendation,
        *,
        state: PortfolioState,
        budget: RiskBudget,
        owner: OwnerContext,
    ) -> tuple[PortfolioImpact | Absent, str | None]:
        """What the portfolio becomes, or why that question has no answer here.

        Returns the impact and, separately, a *blocking* refusal when the
        candidate could be sized but not evaluated — a book the reading does not
        cover is the one such case, and it is a block rather than an indeterminate
        result because books never share capacity: evaluating a `SWING` candidate
        against an `INVESTING` reading would move risk between two capacity pools
        that the whole design keeps apart.
        """
        sized = recommendation.sized_trade()
        if isinstance(sized, Absent):
            return Absent(sized.reason), None
        try:
            return (
                evaluate_impact(
                    proposed=sized,
                    before=state,
                    budget=budget,
                    owner=owner,
                    classification=self.classification,
                ),
                None,
            )
        except PortfolioRiskError as error:
            return Absent(str(error)), str(error)

    # -- the candidate's own arithmetic -------------------------------------

    def _trade_reasons(
        self,
        proposal: PositionProposal,
        recommendation: PositionRecommendation,
        *,
        state: PortfolioState,
        impact: PortfolioImpact | Absent,
        impact_refusal: str | None,
        mark_age: timedelta | Absent | None,
    ) -> tuple[ApprovalReason, ...]:
        """Everything about the idea, in a fixed order rather than a ranked one.

        Fixed because ordering by severity would make the list read as a ranking
        by importance, and this package ranks nothing. The three registers are
        already separate lists on `ApprovalResult`.
        """
        found: list[ApprovalReason] = []
        distance = proposal.risk_distance
        if isinstance(distance, Absent):
            found.append(
                ApprovalReason(
                    code="TR-STOP",
                    scope=ReasonScope.TRADE,
                    classification=ReasonClass.BLOCKING,
                    statement=(
                        f"this candidate has no risk distance, so no size can be "
                        f"produced from it: {distance.reason}"
                    ),
                    source="fmis.portfolio_risk.stop_distance",
                    subject=proposal.market.value,
                )
            )
        elif recommendation.outcome is SizingOutcome.REFUSED:
            found.append(
                ApprovalReason(
                    code="TR-SIZE",
                    scope=ReasonScope.TRADE,
                    classification=ReasonClass.BLOCKING,
                    statement=_unsized_statement(recommendation),
                    source=f"sizing policy {self.sizer.policy.policy_id!r}",
                    subject=proposal.market.value,
                )
            )
        elif recommendation.outcome is SizingOutcome.UNDETERMINED:
            found.append(
                ApprovalReason(
                    code="TR-SIZE",
                    scope=ReasonScope.TRADE,
                    classification=ReasonClass.INDETERMINATE,
                    statement=_unsized_statement(recommendation),
                    source=f"sizing policy {self.sizer.policy.policy_id!r}",
                    subject=proposal.market.value,
                )
            )
        if impact_refusal is not None:
            found.append(
                ApprovalReason(
                    code="TR-BOOK",
                    scope=ReasonScope.TRADE,
                    classification=ReasonClass.BLOCKING,
                    statement=impact_refusal,
                    source="fmis.portfolio_risk.evaluate_impact",
                    subject=proposal.book.value,
                )
            )
        if recommendation.caps:
            found.append(
                ApprovalReason(
                    code="TR-CAP",
                    scope=ReasonScope.TRADE,
                    classification=ReasonClass.WARNING,
                    statement=(
                        "this size is smaller than the fraction alone would give, "
                        "because a ceiling reduced it: " + " · ".join(recommendation.caps)
                    ),
                    source=f"sizing policy {self.sizer.policy.policy_id!r}",
                    subject=proposal.market.value,
                )
            )
        found.extend(self._freshness_reasons(state, mark_age=mark_age))
        found.extend(_coverage_reasons(state))
        found.extend(self._risk_reward_reason(recommendation))
        found.extend(_duplicate_reasons(impact))
        return tuple(found)

    def _freshness_reasons(
        self, state: PortfolioState, *, mark_age: timedelta | Absent | None
    ) -> list[ApprovalReason]:
        """How old the two figures every limit rests on are.

        Equity dates every percent-of-equity limit; the oldest mark dates every
        exposure figure. `SWING_TRADING_MVP_BLUEPRINT_V1` §7.2 H-4 makes a
        balance older than *the owner's configured staleness bound* a hard block
        on sizing — so with no bound configured the age is **reported and not
        judged**, because a bound this package chose would be a threshold
        invented at exactly the point the specification says not to.
        """
        found: list[ApprovalReason] = []
        if not isinstance(state.equity, Absent):
            found.extend(
                _age_reason(
                    code="TR-EQUITY-AGE",
                    label="the equity figure this trade is sized from",
                    age=state.equity_staleness,
                    bound=self.sizer.policy.max_equity_age,
                    source="SWING_TRADING_MVP_BLUEPRINT_V1 §7.2 H-4",
                )
            )
        if mark_age is not None:
            found.extend(
                _age_reason(
                    code="TR-MARK-AGE",
                    label="the oldest price behind every exposure figure",
                    age=mark_age,
                    bound=self.sizer.policy.max_mark_age,
                    source="SWING_TRADING_MVP_BLUEPRINT_V1 §7.2 H-4",
                )
            )
        return found

    def _risk_reward_reason(
        self, recommendation: PositionRecommendation
    ) -> list[ApprovalReason]:
        """The planned ratio against the owner's own minimum, if they set one.

        **A warning and never a block**, which is the blueprint's own placement:
        every risk/reward condition in §7.3 is a soft warning, and none is in
        §7.2's hard-block table. A block means the system refuses to produce a
        number, and it can produce a perfectly correct size for a candidate whose
        reward is thin — the ratio is printed beside it and the owner decides.
        """
        reading = recommendation.planned_risk_reward
        if isinstance(reading, Absent):
            return [
                ApprovalReason(
                    code="TR-RR",
                    scope=ReasonScope.TRADE,
                    classification=ReasonClass.WARNING,
                    statement=(
                        "no planned risk/reward could be stated for this "
                        f"candidate: {reading.reason}. An absent ratio is not a "
                        "poor one and is not a good one"
                    ),
                    source="fmis.snapshotting.RiskRewardReading",
                )
            ]
        minimum = self.sizer.policy.minimum_risk_reward
        if isinstance(minimum, Absent):
            return []
        if reading.ratio >= minimum:
            return []
        return [
            ApprovalReason(
                code="TR-RR",
                scope=ReasonScope.TRADE,
                classification=ReasonClass.WARNING,
                statement=(
                    f"the planned risk/reward {reading.arithmetic} is below the "
                    f"minimum {canonical_decimal_text(minimum)} the owner stated. "
                    "This is shown beside the size and does not reduce it: the "
                    "size comes from the risk rule and the stop distance, never "
                    "from the quality of the idea"
                ),
                source=f"sizing policy {self.sizer.policy.policy_id!r}",
            )
        ]

    # -- the portfolio's own limits ------------------------------------------

    def _portfolio_reasons(
        self,
        proposal: PositionProposal,
        *,
        check: PortfolioConstraintCheck,
        budget: RiskBudget,
        impact: PortfolioImpact | Absent,
    ) -> tuple[ApprovalReason, ...]:
        """One reason per limit that is not comfortably within, plus coverage.

        The limits are evaluated by `fmis.portfolio_risk`, never here: this
        function reads `ConstraintResult`s and classifies them by the severity the
        owner attached to each limit. Re-measuring any of them would give the
        product two answers to *"is my open risk over budget"* and no way to say
        which was right.
        """
        resulting = not isinstance(impact, Absent)
        newly = impact.newly_binding if resulting else ()
        found: list[ApprovalReason] = []
        for result in check.results:
            reason = _limit_reason(
                result, budget=budget, newly_binding=newly, resulting=resulting
            )
            if reason is not None:
                found.append(reason)
        found.extend(self._coverage_gap_reasons(proposal, budget=budget))
        return tuple(found)

    def _coverage_gap_reasons(
        self, proposal: PositionProposal, *, budget: RiskBudget
    ) -> list[ApprovalReason]:
        """Axes the owner's budget says nothing about, named rather than passed over.

        The thing a constraint check structurally cannot report: it evaluates the
        limits that exist, and a page showing every one of them `WITHIN` reads as
        a portfolio checked on every axis. It was checked on the axes the owner
        wrote down.
        """
        found: list[ApprovalReason] = []
        keys = {
            limit.key
            for limit in budget.limits_for(LimitScope.CONCENTRATION)
            if not isinstance(limit.key, Absent)
        }
        for dimension in REQUIRED_AXES:
            wanted = f"{dimension.value}:{_axis_value(proposal, dimension)}"
            if wanted in keys:
                continue
            found.append(
                ApprovalReason(
                    code=f"PF-UNCONSTRAINED-{dimension.value.upper()}",
                    scope=ReasonScope.PORTFOLIO,
                    classification=ReasonClass.WARNING,
                    statement=(
                        f"budget {budget.budget_id!r} states no concentration "
                        f"limit keyed {wanted!r}, so this candidate's "
                        f"{dimension.value} exposure was not checked against one. "
                        "An unchecked axis is not an axis that was found "
                        "acceptable"
                    ),
                    source=f"budget {budget.budget_id!r}",
                    subject=wanted,
                )
            )
        found.extend(self._group_coverage(proposal, budget=budget))
        if not budget.limits_for(LimitScope.TOTAL_OPEN_RISK):
            found.append(
                ApprovalReason(
                    code="PF-UNCONSTRAINED-TOTAL-RISK",
                    scope=ReasonScope.PORTFOLIO,
                    classification=ReasonClass.WARNING,
                    statement=(
                        f"budget {budget.budget_id!r} states no total-open-risk "
                        "limit, so this size was bounded by the per-trade ceiling "
                        "alone. Five individually acceptable positions can still "
                        "create excessive portfolio risk"
                    ),
                    source=f"budget {budget.budget_id!r}",
                )
            )
        return found

    def _group_coverage(
        self, proposal: PositionProposal, *, budget: RiskBudget
    ) -> list[ApprovalReason]:
        """Whether any cluster limit covers a group this asset belongs to.

        Two distinct gaps, reported as two distinct statements: the asset is in no
        group the owner named, or it is in groups no limit constrains. Collapsing
        them would tell an owner who has written no taxonomy the same thing it
        tells one who wrote a taxonomy and no limits.
        """
        asset = proposal.market.base_asset
        groups = self.classification.groups_for(asset)
        if isinstance(groups, Absent):
            return [
                ApprovalReason(
                    code="PF-UNCONSTRAINED-GROUP",
                    scope=ReasonScope.PORTFOLIO,
                    classification=ReasonClass.WARNING,
                    statement=(
                        f"{asset} belongs to no group under the owner's "
                        f"classification {self.classification.version!r}: "
                        f"{groups.reason}. Its group exposure was therefore not "
                        "measured, which is not the same as measuring it and "
                        "finding none"
                    ),
                    source=f"classification {self.classification.version!r}",
                    subject=asset.code,
                )
            ]
        constrained = {
            limit.key
            for limit in budget.limits_for(LimitScope.CLUSTER_EXPOSURE)
            if not isinstance(limit.key, Absent)
        }
        uncovered = sorted(set(groups) - constrained)
        if not uncovered:
            return []
        return [
            ApprovalReason(
                code="PF-UNCONSTRAINED-GROUP",
                scope=ReasonScope.PORTFOLIO,
                classification=ReasonClass.WARNING,
                statement=(
                    f"{asset} is in {', '.join(repr(group) for group in uncovered)}, "
                    f"which budget {budget.budget_id!r} states no cluster limit "
                    "for. Correlated positions are the failure a cluster limit "
                    "exists to catch, and none was applied here"
                ),
                source=f"budget {budget.budget_id!r}",
                subject=asset.code,
            )
        ]


# ---------------------------------------------------------------------------
# Classification of one measured limit, and of one measured age.
# ---------------------------------------------------------------------------


def _limit_reason(
    result: ConstraintResult,
    *,
    budget: RiskBudget,
    newly_binding: tuple[str, ...],
    resulting: bool,
) -> ApprovalReason | None:
    """One limit's result as a reason, or `None` when it is comfortably within.

    The severity is the owner's — `RiskLimit.severity`, set by them and read here
    — so this function chooses nothing. A limit whose severity cannot be looked
    up is treated as `HARD_BLOCK`: a check evaluating a limit the budget does not
    hold is a defect, and the safe reading of a defect in a risk engine is the
    strict one.

    ``resulting`` says which portfolio was measured — the one with this position
    open, or the one that exists because no size could be produced. Naming it in
    every statement is what stops *"your concentration cap is exceeded"* being
    read as a fact about the book when it is a fact about the book plus a trade
    that has not happened.
    """
    limit = budget.limit(result.limit_id)
    severity = LimitSeverity.HARD_BLOCK if limit is None else limit.severity
    hard = severity is LimitSeverity.HARD_BLOCK
    where = (
        "the portfolio with this position open" if resulting else "this portfolio"
    )
    if isinstance(result.status, Absent):
        return ApprovalReason(
            code=f"PF-LIMIT-{result.limit_id}",
            scope=ReasonScope.PORTFOLIO,
            classification=(
                ReasonClass.INDETERMINATE if hard else ReasonClass.WARNING
            ),
            statement=(
                f"limit {result.limit_id!r} ({result.scope.value}, "
                f"{severity.value}) could not be measured against "
                f"{where}: {result.status.reason}. An unmeasured limit is not a "
                "limit that was met"
            ),
            source=f"limit {result.limit_id!r}",
            subject=result.limit_id,
        )
    if result.status is LimitStatus.EXCEEDED:
        return ApprovalReason(
            code=f"PF-LIMIT-{result.limit_id}",
            scope=ReasonScope.PORTFOLIO,
            classification=ReasonClass.BLOCKING if hard else ReasonClass.WARNING,
            statement=(
                f"limit {result.limit_id!r} ({result.scope.value}) is "
                f"{result.status.value} in {where}: "
                f"{_amount_text(result.current_value)} against a stated "
                f"{'floor' if result.is_floor else 'ceiling'} of "
                f"{_amount_text(result.limit_value)}"
                + (
                    ". This trade is what moves it there"
                    if result.limit_id in newly_binding
                    else ", and it was already binding before this trade"
                    if resulting
                    else ""
                )
            ),
            source=f"limit {result.limit_id!r}",
            subject=result.limit_id,
        )
    if result.status is LimitStatus.AT_LIMIT:
        return ApprovalReason(
            code=f"PF-LIMIT-{result.limit_id}",
            scope=ReasonScope.PORTFOLIO,
            classification=ReasonClass.WARNING,
            statement=(
                f"limit {result.limit_id!r} ({result.scope.value}) is reached "
                f"exactly in {where}: {_amount_text(result.current_value)} against "
                f"a stated {_amount_text(result.limit_value)}. A stated maximum is "
                "not breached by touching it, and there is no room left after this"
            ),
            source=f"limit {result.limit_id!r}",
            subject=result.limit_id,
        )
    return None


def _binding_capacity(
    check: PortfolioConstraintCheck, budget: RiskBudget, state: PortfolioState
) -> Money | Absent:
    """The open-risk headroom, but only when the owner made that limit binding.

    **Severity is the owner's here too.** A `HARD_BLOCK` total-open-risk budget
    bounds the size and can refuse it outright —
    `SWING_TRADING_MVP_BLUEPRINT_V1` §7.2 H-3. An `ADVISORY` one does not: the
    owner has said that breaching it is something to be told about, not something
    to be stopped by, and a sizer that reduced the position anyway would be
    applying a severity they did not choose. The breach is still reported, by
    `_limit_reason`, as the warning they asked for.

    Deciding this here rather than inside `PositionSizer` keeps the sizer a pure
    function of what it is handed: one policy read, in the layer that reads
    policy.
    """
    hard = [
        limit
        for limit in budget.limits_for(LimitScope.TOTAL_OPEN_RISK)
        if limit.severity is LimitSeverity.HARD_BLOCK
    ]
    if not hard:
        return Absent(
            f"budget {budget.budget_id!r} states no hard total-open-risk limit, "
            "so no portfolio budget bounds this size. Any advisory limit on it is "
            "reported beside the size rather than applied to it"
        )
    return remaining_risk_capacity(check, base=state.base_currency)


def _unsized_statement(recommendation: PositionRecommendation) -> str:
    """The sizer's own reason, carried verbatim rather than paraphrased.

    Re-wording it here would give the product two sentences for one refusal, and
    the day they drift the owner reads whichever surface they happened to open.
    """
    quantity = recommendation.quantity
    assert isinstance(quantity, Absent)  # an unsized recommendation carries a reason
    return quantity.reason


def _age_reason(
    *,
    code: str,
    label: str,
    age: Any,
    bound: timedelta | Absent,
    source: str,
) -> list[ApprovalReason]:
    """A figure's age against the owner's own staleness bound, or without one.

    **The severity of an unknown age tracks whether anything was checking it.**
    With a bound configured, an age nobody can state means the owner's own check
    could not run — `INDETERMINATE`. With no bound, nothing was being checked, so
    an unknown age is a warning rather than a demotion of the whole approval:
    reporting it as indeterminate would make every page indeterminate for a rule
    the owner never asked for, and an `INDETERMINATE` that fires unconditionally
    is an `INDETERMINATE` nobody reads.
    """
    if isinstance(age, Absent) and not isinstance(bound, Absent):
        return [
            ApprovalReason(
                code=code,
                scope=ReasonScope.TRADE,
                classification=ReasonClass.INDETERMINATE,
                statement=(
                    f"how old {label} is cannot be stated, so the {bound} bound "
                    f"the owner configured could not be applied: {age.reason}"
                ),
                source=source,
            )
        ]
    if isinstance(age, Absent):
        return [
            ApprovalReason(
                code=code,
                scope=ReasonScope.TRADE,
                classification=ReasonClass.WARNING,
                statement=(
                    f"how old {label} is cannot be stated: {age.reason}. "
                    f"Nothing was checking it, because {bound.reason} — the age "
                    "is reported rather than judged"
                ),
                source=source,
            )
        ]
    if isinstance(bound, Absent):
        return [
            ApprovalReason(
                code=code,
                scope=ReasonScope.TRADE,
                classification=ReasonClass.WARNING,
                statement=(
                    f"{label} is {age} old. This age is reported and not "
                    f"judged, because {bound.reason} — a staleness bound is a "
                    "policy and this system sets none on the owner's behalf"
                ),
                source=source,
            )
        ]
    if age > bound:
        return [
            ApprovalReason(
                code=code,
                scope=ReasonScope.TRADE,
                classification=ReasonClass.BLOCKING,
                statement=(
                    f"{label} is {age} old, past the {bound} bound the owner "
                    "configured. A figure older than its own bound is not a "
                    "figure this trade may be sized against"
                ),
                source=source,
            )
        ]
    return []


def _coverage_reasons(state: PortfolioState) -> list[ApprovalReason]:
    """The two lists that make every risk figure on the page absent when non-empty."""
    found: list[ApprovalReason] = []
    if state.unmarked:
        markets = ", ".join(sorted(line.market.value for line in state.unmarked))
        found.append(
            ApprovalReason(
                code="TR-MARKS",
                scope=ReasonScope.TRADE,
                classification=ReasonClass.INDETERMINATE,
                statement=(
                    f"{len(state.unmarked)} open position(s) have no price, so "
                    "every exposure figure this approval rests on is absent "
                    f"rather than smaller: {markets}"
                ),
                source="fmis.portfolio_risk.PortfolioState.unmarked",
                subject=markets,
            )
        )
    if state.unstopped:
        markets = ", ".join(sorted(line.market.value for line in state.unstopped))
        found.append(
            ApprovalReason(
                code="TR-STOPS",
                scope=ReasonScope.TRADE,
                classification=ReasonClass.INDETERMINATE,
                statement=(
                    f"{len(state.unstopped)} open position(s) have no recorded "
                    "stop, so total open risk cannot be stated and every limit "
                    f"measured against it is unmeasurable: {markets}"
                ),
                source="fmis.portfolio_risk.PortfolioState.unstopped",
                subject=markets,
            )
        )
    return found


def _duplicate_reasons(impact: PortfolioImpact | Absent) -> list[ApprovalReason]:
    """Whether this bet is already held — a warning, and the blueprint's own S-1.

    **Correlation is never measured anywhere in this repository and this reason
    does not claim it is.** It reports that the same instrument, or the same base
    asset under another pair, is already open somewhere — which is *duplication*,
    a fact, rather than *correlation*, an inference this system has no data for.

    The sentences are `fmis.portfolio_risk`'s own impact notes, carried verbatim
    rather than re-worded, so the owner reads the identical wording here and on
    the portfolio page. Where the overlap is in the candidate's own scope there is
    no note to carry — that case is a scale-in, and the effect names it.
    """
    if isinstance(impact, Absent) or not impact.overlap.is_duplicate:
        return []
    overlap = impact.overlap
    parts: list[str] = []
    if not isinstance(overlap.matched, Absent):
        effect = (
            overlap.effect.reason
            if isinstance(overlap.effect, Absent)
            else f"the effect on it is {overlap.effect.value}"
        )
        parts.append(
            f"{overlap.matched.quantity} is already open in "
            f"{overlap.matched.market.value} in book "
            f"{overlap.matched.book.value} in account "
            f"{overlap.matched.account.value}, and {effect}"
        )
    parts.extend(
        note.statement for note in impact.notes if note.code in _DUPLICATE_NOTES
    )
    return [
        ApprovalReason(
            code="TR-DUP",
            scope=ReasonScope.TRADE,
            classification=ReasonClass.WARNING,
            statement="this bet is already held: " + " ".join(parts),
            source="fmis.portfolio_risk.PositionOverlap",
        )
    ]


#: The impact notes that describe exposure duplicated *elsewhere* in the book —
#: the same pair at another venue, account or book, and the same base asset under
#: another quote. Named rather than re-derived, so the sentence the owner reads
#: here is the identical sentence the portfolio page prints, produced once.
_DUPLICATE_NOTES = frozenset({"PR-N1", "PR-N10"})


def _axis_value(proposal: PositionProposal, dimension: ExposureDimension) -> str:
    """How this candidate's key on one axis is written, matching the exposure engine."""
    if dimension is ExposureDimension.INSTRUMENT:
        return proposal.market.value
    if dimension is ExposureDimension.ASSET:
        return proposal.market.base_asset.code
    return proposal.account.value


def _amount_text(value: Money | Decimal) -> str:
    """A limit's value or its measurement, in money or as a bare number.

    **There is no `Absent` branch here, and its absence is the invariant showing
    through.** `ConstraintResult` refuses a present status beside an absent
    value — *"reporting a status for a value that could not be measured is how an
    indeterminate result becomes a silent 'within'"* — and `_limit_reason` reaches
    this function only after branching on a present status. An `Absent` branch
    would be an `except` clause no input can reach, which reads as a case that was
    handled rather than one that cannot occur.
    """
    if isinstance(value, Money):
        return f"{value.text} {value.asset}"
    return canonical_decimal_text(value)


def _status_of(reasons: tuple[ApprovalReason, ...]) -> ApprovalStatus:
    """Blocking outranks indeterminate outranks approved. Stated once, here.

    `ApprovalResult` re-derives and re-checks this, so the rule is asserted twice
    on purpose: once where the answer is produced, once where it is constructed.
    A future second producer of results cannot skip the second.
    """
    classes = {reason.classification for reason in reasons}
    if ReasonClass.BLOCKING in classes:
        return ApprovalStatus.BLOCKED
    if ReasonClass.INDETERMINATE in classes:
        return ApprovalStatus.INDETERMINATE
    return ApprovalStatus.APPROVED
