"""`PortfolioConstraintCheck` — how one portfolio sat against the owner's limits.

`AP` §15.5's one contract, built. Four properties make it safe and all four are
structural here rather than disciplinary:

1. **It returns per-constraint facts, never a verdict.** `EXCEEDED` on the
   open-risk budget is a fact; *"don't take this trade"* is the owner's
   conclusion. There is no field on any type in this module that could hold a
   recommendation, and a guard test asserts the package names none.
2. **`Absent(reason)` is first-class and is never silently `WITHIN`.** A limit
   this engine cannot measure carries the reason it could not, and
   `binding_constraints` and `indeterminate` are two separate lists so a surface
   physically cannot render the second as the first.
3. **It invents no threshold.** Every value compared against is a `RiskLimit`
   the owner wrote. A test asserts no numeric literal beyond 0 and 1 appears in
   this package, which is the same test `fmis.risk` already passes.
4. **It is not stored.** The data model classes a frozen check as a captured
   artifact belonging to a proposal (entity 34); nothing in this build creates a
   proposal from a portfolio reading, so freezing one here would persist a record
   with no owner. `to_payload` exists for export and there is deliberately no
   decoder — the day a proposal freezes one, that is the milestone that adds a
   record kind, a spec row and a repository.

**Two comparison semantics, and conflating them is the bug this module exists to
avoid.** Almost every limit is a **ceiling**: above it is a breach. `MIN_RESERVE`
is a **floor**: *below* it is the breach. Routing a floor through a ceiling
comparison reports an account with no reserve left as comfortably within its
reserve limit — the exact inversion that makes a risk engine worse than none. The
two are named in `_FLOOR_SCOPES` and the comparison branches on it once.

**`PERCENT_OF_EQUITY` means a fraction, and the convention is stated because the
domain does not fix it.** `RiskLimit` validates that a percent limit is a
positive `Decimal` and says nothing about whether `2` means 2 % or 200 %. This
engine reads every `PERCENT_*` limit as a **fraction** — the owner's 2 % ceiling
is `Decimal("0.02")` — because that is what every other ratio in the repository
already is: `ExposureSummary.leverage`, `AllocationEntry.weight` and
`RiskRewardReading.ratio` are all fractions, and a second convention would make
one of them wrong. `PERCENT_UNIT_CONVENTION` is the sentence a surface prints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.accounts import OwnerContext
from fmis.money import AssetCode, Money, canonical_decimal_text
from fmis.provenance import Absent, ValueOrigin
from fmis.records import (
    DomainValidationError,
    require_int,
    require_member,
    require_text,
    require_tuple_of,
    require_utc,
)
from fmis.risk import (
    LimitScope,
    LimitStatus,
    LimitUnit,
    RiskBudget,
    RiskLimit,
    period_key,
)

from fmis.portfolio_risk.geometry import RISK_BASIS, risk_fraction_of_equity
from fmis.portfolio_risk.models import ExposureDimension, PortfolioState

__all__ = [
    "CONSTRAINT_POLICY_VERSION",
    "PERCENT_UNIT_CONVENTION",
    "ConstraintResult",
    "PortfolioConstraintCheck",
    "evaluate_constraints",
    "remaining_risk_capacity",
]

#: This build's constraint-evaluation rule version. Cited on every check, because
#: a later build that measures a scope differently must produce a *visibly*
#: different reading rather than silently reinterpreting an old one.
CONSTRAINT_POLICY_VERSION = "portfolio-constraint-v1"

#: How a percent limit's number is read, stated once and printed beside the
#: figures. Not a threshold — a unit convention, which the domain leaves open and
#: which two engines reading it differently would make catastrophic.
PERCENT_UNIT_CONVENTION = (
    "a percent limit is a fraction: the 2 % per-trade ceiling is stated as 0.02, "
    "matching every other ratio in this repository"
)

#: The one scope whose limit is a floor. Below it is the breach, so the
#: comparison is inverted — and it is a named set rather than a conditional so a
#: future floor scope is added deliberately rather than inheriting the wrong
#: semantics by default.
_FLOOR_SCOPES: frozenset[LimitScope] = frozenset({LimitScope.MIN_RESERVE})

#: Which exposure axis a `CONCENTRATION` limit's key names. The key is written
#: `{dimension}:{value}` — `venue:binance`, `symbol:BTCUSDT` — so one limit set
#: can constrain several axes without the engine guessing which was meant.
_CONCENTRATION_DIMENSIONS: tuple[ExposureDimension, ...] = (
    ExposureDimension.ACCOUNT,
    ExposureDimension.VENUE,
    ExposureDimension.BOOK,
    ExposureDimension.INSTRUMENT,
    ExposureDimension.SYMBOL,
    ExposureDimension.ASSET,
    ExposureDimension.DIRECTION,
)


@dataclass(frozen=True, slots=True)
class ConstraintResult:
    """One limit, what was measured against it, and where that sits.

    `status` and `current_value` are `Absent` together or present together: a
    status attached to a value that could not be measured is precisely how an
    indeterminate result becomes a silent `WITHIN`. `LimitEvaluation` enforces the
    same pairing one layer down, and this repeats it because this type is
    constructed here rather than by that one.
    """

    limit_id: str
    scope: LimitScope
    unit: LimitUnit
    limit_value: Decimal | Money
    current_value: Decimal | Money | Absent
    status: LimitStatus | Absent
    key: str | Absent = field(
        default_factory=lambda: Absent("this limit applies portfolio-wide")
    )
    #: Whether the limit is a floor. Carried onto the result so a reader knows
    #: which direction `EXCEEDED` means without having to know the scope table.
    is_floor: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "limit_id", require_text(self.limit_id, "limit_id"))
        require_member(self.scope, LimitScope, "scope")
        require_member(self.unit, LimitUnit, "unit")
        if not isinstance(self.limit_value, (Decimal, Money)):
            raise TypeError("limit_value must be a Decimal or Money")
        if not isinstance(self.current_value, (Decimal, Money, Absent)):
            raise TypeError("current_value must be a Decimal, Money or Absent")
        if not isinstance(self.status, (LimitStatus, Absent)):
            raise TypeError("status must be a LimitStatus or Absent")
        if isinstance(self.current_value, Absent) != isinstance(self.status, Absent):
            raise DomainValidationError(
                "an unmeasurable limit has no status and a measured one has one; "
                "reporting a status for a value that could not be measured is how "
                "an indeterminate result becomes a silent 'within'"
            )
        if isinstance(self.current_value, Money) != isinstance(self.limit_value, Money):
            if not isinstance(self.current_value, Absent):
                raise DomainValidationError(
                    "a money limit is measured in money and a ratio limit in a "
                    "ratio; comparing them compares two different things"
                )
        if isinstance(self.current_value, Money) and isinstance(self.limit_value, Money):
            if self.current_value.asset != self.limit_value.asset:
                raise DomainValidationError(
                    "a money limit and its measurement are stated in one currency"
                )
        if not isinstance(self.key, Absent):
            object.__setattr__(self, "key", require_text(self.key, "key"))
        if not isinstance(self.is_floor, bool):
            raise TypeError("is_floor must be a bool")

    @property
    def origin(self) -> ValueOrigin:
        """`POLICY_DERIVED` — a measured fact read against an asserted limit."""
        return ValueOrigin.POLICY_DERIVED

    @property
    def is_binding(self) -> bool:
        """Whether the limit is reached or breached. `Absent` is **not** binding
        and is not within either — it is reported in its own list."""
        return self.status in (LimitStatus.AT_LIMIT, LimitStatus.EXCEEDED)

    @property
    def headroom(self) -> Decimal | Money | Absent:
        """How much room is left. A subtraction, never a ratio, never stored.

        On a ceiling it is `limit − current`; on a floor it is `current − limit`,
        so *positive means room* on both and a reader never has to remember which
        way a particular limit runs.
        """
        if isinstance(self.current_value, Absent):
            return self.current_value
        if self.is_floor:
            return self.current_value - self.limit_value  # type: ignore[operator]
        return self.limit_value - self.current_value  # type: ignore[operator]

    def to_payload(self) -> dict[str, Any]:
        return {
            "limit_id": self.limit_id,
            "scope": self.scope.value,
            "unit": self.unit.value,
            "key": (
                {"absent": self.key.to_payload()}
                if isinstance(self.key, Absent)
                else {"value": self.key}
            ),
            "limit_value": _encode_amount(self.limit_value),
            "current_value": (
                {"absent": self.current_value.to_payload()}
                if isinstance(self.current_value, Absent)
                else {"value": _encode_amount(self.current_value)}
            ),
            "status": (
                {"absent": self.status.to_payload()}
                if isinstance(self.status, Absent)
                else {"value": self.status.value}
            ),
            "is_floor": self.is_floor,
        }


@dataclass(frozen=True, slots=True)
class PortfolioConstraintCheck:
    """Every configured limit, evaluated against one portfolio at one instant.

    **Not a verdict and not a score.** The object holds one result per limit and
    three read-time views over them — binding, exceeded, indeterminate — and
    nothing that combines them into a number. `AP` §15.2: *"a single number would
    collapse all three strata into one value whose meaning no one could
    recover."*
    """

    portfolio_id: str
    budget_id: str
    risk_policy_version: int
    evaluated_at: datetime
    results: tuple[ConstraintResult, ...]
    policy_version: str = CONSTRAINT_POLICY_VERSION

    def __post_init__(self) -> None:
        for name in ("portfolio_id", "budget_id", "policy_version"):
            object.__setattr__(self, name, require_text(getattr(self, name), name))
        require_int(self.risk_policy_version, "risk_policy_version", minimum=1)
        object.__setattr__(
            self, "evaluated_at", require_utc(self.evaluated_at, "evaluated_at")
        )
        require_tuple_of(self.results, ConstraintResult, "results")
        identifiers = [result.limit_id for result in self.results]
        if len(set(identifiers)) != len(identifiers):
            raise DomainValidationError("a limit must not be evaluated twice")

    @property
    def origin(self) -> ValueOrigin:
        return ValueOrigin.POLICY_DERIVED

    @property
    def binding_constraints(self) -> tuple[ConstraintResult, ...]:
        """Limits that are `AT_LIMIT` or `EXCEEDED`, in the budget's own order."""
        return tuple(result for result in self.results if result.is_binding)

    @property
    def exceeded(self) -> tuple[ConstraintResult, ...]:
        return tuple(
            result for result in self.results if result.status is LimitStatus.EXCEEDED
        )

    @property
    def indeterminate(self) -> tuple[ConstraintResult, ...]:
        """Limits that could not be measured — reported, never counted as within."""
        return tuple(
            result for result in self.results if isinstance(result.status, Absent)
        )

    def result(self, limit_id: str) -> ConstraintResult | Absent:
        wanted = require_text(limit_id, "limit_id")
        for candidate in self.results:
            if candidate.limit_id == wanted:
                return candidate
        return Absent(f"this check did not evaluate a limit {wanted!r}")

    @property
    def risk_basis(self) -> str:
        return RISK_BASIS

    def to_payload(self) -> dict[str, Any]:
        """For export and rendering. There is deliberately no decoder."""
        return {
            "portfolio_id": self.portfolio_id,
            "budget_id": self.budget_id,
            "risk_policy_version": self.risk_policy_version,
            "policy_version": self.policy_version,
            "evaluated_at": self.evaluated_at.isoformat(),
            "results": [result.to_payload() for result in self.results],
            "binding_constraints": [
                result.limit_id for result in self.binding_constraints
            ],
            "indeterminate": [result.limit_id for result in self.indeterminate],
            "percent_unit_convention": PERCENT_UNIT_CONVENTION,
            "risk_basis": self.risk_basis,
        }


# ---------------------------------------------------------------------------
# Measurement: one function per scope, each returning a value or its absence.
# ---------------------------------------------------------------------------


def _as_fraction(
    amount: Money | Absent, equity: Money | Absent, subject: str
) -> Decimal | Absent:
    if isinstance(amount, Absent):
        return Absent(f"{subject} is not known: {amount.reason}")
    if isinstance(equity, Absent):
        return Absent(
            f"{subject} as a fraction of equity needs equity, which is not known: "
            f"{equity.reason}"
        )
    try:
        return risk_fraction_of_equity(amount, equity)
    except DomainValidationError as error:
        return Absent(str(error))


def _largest_line_risk(state: PortfolioState) -> Money | Absent:
    """The biggest single position's capital at risk, or why there is no answer.

    Used for a `PER_TRADE_RISK` limit when no candidate is being evaluated: the
    question *"is any position over my per-trade ceiling"* is answered by the
    largest, and a portfolio with one unmeasurable position cannot answer it at
    all — because the unmeasurable one might be the largest.
    """
    if not state.lines:
        return Money.zero(state.base_currency)
    largest: Money | None = None
    for line in state.lines:
        risk = line.capital_at_risk(state.base_currency)
        if isinstance(risk, Absent):
            return Absent(
                f"the largest single position's risk cannot be identified while "
                f"{line.market.value} in {line.account.value} is unmeasurable: "
                f"{risk.reason}"
            )
        if largest is None or risk > largest:
            largest = risk
    assert largest is not None  # guarded by the empty check above
    return largest


def _keyed_dimension(limit: RiskLimit) -> tuple[ExposureDimension, str] | Absent:
    """Read `{dimension}:{value}` off a concentration limit's key."""
    if isinstance(limit.key, Absent):
        return Absent(
            f"limit {limit.limit_id} names no key, so which exposure it "
            "constrains is not stated. A concentration limit's key is written "
            "'{dimension}:{value}', where dimension is one of "
            f"{', '.join(sorted(item.value for item in _CONCENTRATION_DIMENSIONS))}"
        )
    head, separator, tail = limit.key.partition(":")
    if not separator or not tail:
        return Absent(
            f"limit {limit.limit_id} has key {limit.key!r}, which does not name an "
            "axis. Write it as '{dimension}:{value}', for example 'symbol:BTCUSDT'"
        )
    for dimension in _CONCENTRATION_DIMENSIONS:
        if dimension.value == head:
            return dimension, tail
    return Absent(
        f"limit {limit.limit_id} names axis {head!r}, which this engine does not "
        f"measure. Known axes: "
        f"{', '.join(sorted(item.value for item in _CONCENTRATION_DIMENSIONS))}"
    )


def _concentration(
    limit: RiskLimit, state: PortfolioState
) -> tuple[Decimal | Money | Absent, str | Absent]:
    resolved = _keyed_dimension(limit)
    if isinstance(resolved, Absent):
        return resolved, limit.key
    dimension, key = resolved
    breakdown = state.breakdown(dimension)
    if isinstance(breakdown, Absent):
        return breakdown, limit.key
    if limit.unit is LimitUnit.PERCENT_OF_OPEN_RISK:
        return breakdown.risk_share(key), limit.key
    if limit.unit is LimitUnit.PERCENT_OF_EQUITY:
        entry = breakdown.entry(key)
        gross = entry if isinstance(entry, Absent) else entry.gross
        return _as_fraction(gross, state.equity, f"{key!r} gross exposure"), limit.key
    if limit.unit is LimitUnit.RATIO:
        return breakdown.gross_share(key), limit.key
    if limit.unit is LimitUnit.MONEY:
        entry = breakdown.entry(key)
        return (entry if isinstance(entry, Absent) else entry.gross), limit.key
    return (
        Absent(
            f"limit {limit.limit_id} is stated in {limit.unit.value}, which is not "
            "a unit a concentration is measured in"
        ),
        limit.key,
    )


def _group_concentration(
    limit: RiskLimit, state: PortfolioState
) -> tuple[Decimal | Money | Absent, str | Absent]:
    if isinstance(limit.key, Absent):
        return (
            Absent(
                f"limit {limit.limit_id} names no cluster, so which group it "
                "constrains is not stated"
            ),
            limit.key,
        )
    breakdown = state.breakdown(ExposureDimension.GROUP)
    if isinstance(breakdown, Absent):
        return breakdown, limit.key
    if limit.key not in breakdown.keys:
        return (
            Absent(
                f"no exposure in this portfolio falls in the owner's group "
                f"{limit.key!r} under classification "
                f"{breakdown.classification_version!r}"
            ),
            limit.key,
        )
    if limit.unit is LimitUnit.PERCENT_OF_OPEN_RISK:
        return breakdown.risk_share(limit.key), limit.key
    if limit.unit is LimitUnit.RATIO:
        return breakdown.gross_share(limit.key), limit.key
    if limit.unit is LimitUnit.PERCENT_OF_EQUITY:
        entry = breakdown.entry(limit.key)
        gross = entry if isinstance(entry, Absent) else entry.gross
        return (
            _as_fraction(gross, state.equity, f"group {limit.key!r} gross exposure"),
            limit.key,
        )
    if limit.unit is LimitUnit.MONEY:
        entry = breakdown.entry(limit.key)
        return (entry if isinstance(entry, Absent) else entry.gross), limit.key
    return (
        Absent(
            f"limit {limit.limit_id} is stated in {limit.unit.value}, which is not "
            "a unit a cluster exposure is measured in"
        ),
        limit.key,
    )


def _measure(
    limit: RiskLimit,
    state: PortfolioState,
    *,
    candidate_risk: Money | Absent | None,
    owner: OwnerContext,
) -> tuple[Decimal | Money | Absent, str | Absent]:
    """One limit's current value, and the key it was measured on.

    `candidate_risk` is the proposed trade's capital at risk when a candidate is
    being evaluated, and `None` when the portfolio is being read on its own. The
    distinction changes what `PER_TRADE_RISK` means and nothing else: with a
    candidate it is *this trade's* risk, without one it is the largest position
    already held.
    """
    scope = limit.scope
    if scope is LimitScope.PER_TRADE_RISK:
        measured: Money | Absent = (
            _largest_line_risk(state) if candidate_risk is None else candidate_risk
        )
        if limit.unit is LimitUnit.MONEY:
            return measured, limit.key
        if limit.unit is LimitUnit.PERCENT_OF_EQUITY:
            return (
                _as_fraction(measured, state.equity, "the trade's capital at risk"),
                limit.key,
            )
        return (
            Absent(
                f"limit {limit.limit_id} is stated in {limit.unit.value}, which is "
                "not a unit per-trade risk is measured in"
            ),
            limit.key,
        )
    if scope is LimitScope.TOTAL_OPEN_RISK:
        if limit.unit is LimitUnit.MONEY:
            return state.open_risk, limit.key
        if limit.unit is LimitUnit.PERCENT_OF_EQUITY:
            return (
                _as_fraction(state.open_risk, state.equity, "total open risk"),
                limit.key,
            )
        return (
            Absent(
                f"limit {limit.limit_id} is stated in {limit.unit.value}, which is "
                "not a unit total open risk is measured in"
            ),
            limit.key,
        )
    if scope is LimitScope.CONCENTRATION:
        return _concentration(limit, state)
    if scope is LimitScope.CLUSTER_EXPOSURE:
        return _group_concentration(limit, state)
    if scope is LimitScope.LEVERAGE:
        if limit.unit is not LimitUnit.RATIO:
            return (
                Absent(
                    f"limit {limit.limit_id} is stated in {limit.unit.value}; "
                    "leverage is a ratio of gross exposure to equity"
                ),
                limit.key,
            )
        return state.leverage, limit.key
    if scope is LimitScope.MAX_CONCURRENT_POSITIONS:
        if limit.unit is not LimitUnit.COUNT:
            return (
                Absent(
                    f"limit {limit.limit_id} is stated in {limit.unit.value}; a "
                    "position count is a count"
                ),
                limit.key,
            )
        return Decimal(state.open_position_count), limit.key
    if scope is LimitScope.MIN_RESERVE:
        available = state.available_capital
        if limit.unit is LimitUnit.MONEY:
            return available, limit.key
        if limit.unit is LimitUnit.PERCENT_OF_EQUITY:
            return (
                _as_fraction(available, state.equity, "available capital"),
                limit.key,
            )
        return (
            Absent(
                f"limit {limit.limit_id} is stated in {limit.unit.value}, which is "
                "not a unit a reserve is measured in"
            ),
            limit.key,
        )
    if scope is LimitScope.PERIOD_LOSS:
        bucket = period_key(limit, state.as_of, owner)
        window = bucket.reason if isinstance(bucket, Absent) else f"period {bucket}"
        return (
            Absent(
                f"a period loss is the realized result of the round trips closed "
                f"in {window}; this engine reads the open portfolio and holds no "
                "closed-trip series. Nothing about the limit is wrong — it is not "
                "measured here"
            ),
            limit.key,
        )
    return (
        Absent(
            f"a drawdown is measured against an equity peak, and no equity series "
            "exists: every point on it needs a mark for every holding, and no "
            "mark source is built"
        ),
        limit.key,
    )


def _compare(
    limit: RiskLimit, current: Decimal | Money | Absent
) -> tuple[Decimal | Money | Absent, LimitStatus | Absent]:
    """Where a measurement sits, with the floor scopes compared the other way.

    **Returns the value and the status together, and demotes both when the
    comparison is impossible.** A measurement that *exists* but cannot be compared
    — a limit in SEK against a portfolio in USDT — is not a measurement of that
    limit, and carrying the number beside an absent status would either be refused
    by `ConstraintResult` (taking the whole check down over one bad limit) or,
    worse, be rendered as if the comparison had happened. One limit the owner
    mis-stated must cost exactly that limit and nothing else.
    """
    if isinstance(current, Absent):
        return current, Absent(current.reason)
    if isinstance(limit.value, Money) != isinstance(current, Money):
        reason = Absent(
            f"limit {limit.limit_id} is stated in "
            f"{'money' if isinstance(limit.value, Money) else 'a ratio'} and was "
            f"measured in {'money' if isinstance(current, Money) else 'a ratio'}; "
            "comparing them would compare two different things"
        )
        return reason, Absent(reason.reason)
    if isinstance(limit.value, Money) and isinstance(current, Money):
        if limit.value.asset != current.asset:
            reason = Absent(
                f"limit {limit.limit_id} is stated in {limit.value.asset} and was "
                f"measured in {current.asset}; converting here would hide the rate "
                "that made them comparable"
            )
            return reason, Absent(reason.reason)
    if current == limit.value:
        return current, LimitStatus.AT_LIMIT
    if limit.scope in _FLOOR_SCOPES:
        return current, (
            LimitStatus.EXCEEDED if current < limit.value else LimitStatus.WITHIN
        )
    return current, (
        LimitStatus.EXCEEDED if current > limit.value else LimitStatus.WITHIN
    )


def evaluate_constraints(
    budget: RiskBudget,
    state: PortfolioState,
    *,
    owner: OwnerContext,
    candidate_risk: Money | Absent | None = None,
    evaluated_at: datetime | None = None,
) -> PortfolioConstraintCheck:
    """Evaluate every limit in the budget against one portfolio state.

    **Every limit in the budget appears in the result.** A limit this engine
    cannot measure is `Absent(reason)` rather than omitted: a check that silently
    dropped a limit would read as a clean bill of health on exactly the constraint
    nobody could evaluate.
    """
    if not isinstance(budget, RiskBudget):
        raise TypeError("budget must be a RiskBudget")
    if not isinstance(state, PortfolioState):
        raise TypeError("state must be a PortfolioState")
    if not isinstance(owner, OwnerContext):
        raise TypeError("owner must be an OwnerContext")
    if candidate_risk is not None and not isinstance(candidate_risk, (Money, Absent)):
        raise TypeError("candidate_risk must be a Money, Absent or None")
    moment = state.as_of if evaluated_at is None else require_utc(
        evaluated_at, "evaluated_at"
    )
    results: list[ConstraintResult] = []
    for limit in budget.limits:
        measured, key = _measure(
            limit, state, candidate_risk=candidate_risk, owner=owner
        )
        current, status = _compare(limit, measured)
        results.append(
            ConstraintResult(
                limit_id=limit.limit_id,
                scope=limit.scope,
                unit=limit.unit,
                limit_value=limit.value,
                current_value=current,
                status=status,
                key=key,
                is_floor=limit.scope in _FLOOR_SCOPES,
            )
        )
    return PortfolioConstraintCheck(
        portfolio_id=state.portfolio_id,
        budget_id=budget.budget_id,
        risk_policy_version=budget.risk_policy_version,
        evaluated_at=moment,
        results=tuple(results),
    )


def remaining_risk_capacity(
    check: PortfolioConstraintCheck, *, base: AssetCode
) -> Money | Absent:
    """What is left of the total-open-risk budget, in money.

    Answerable only when a `TOTAL_OPEN_RISK` limit is stated in money, because a
    fraction's headroom is a fraction and turning it back into money needs the
    equity that produced it — a second division this function will not do
    silently. A caller who wants the fractional headroom reads
    `ConstraintResult.headroom`, which is exact.
    """
    if not isinstance(check, PortfolioConstraintCheck):
        raise TypeError("check must be a PortfolioConstraintCheck")
    for result in check.results:
        if result.scope is not LimitScope.TOTAL_OPEN_RISK:
            continue
        if result.unit is not LimitUnit.MONEY:
            return Absent(
                f"the total-open-risk limit {result.limit_id!r} is stated in "
                f"{result.unit.value}; its headroom is a fraction, and converting "
                "it to money needs the equity it was measured against"
            )
        headroom = result.headroom
        if isinstance(headroom, Absent):
            return headroom
        assert isinstance(headroom, Money)  # a money limit has a money headroom
        if headroom.asset != base:
            return Absent(
                f"the total-open-risk headroom is stated in {headroom.asset} and "
                f"the portfolio's base currency is {base}"
            )
        return headroom
    return Absent(
        "this budget states no total-open-risk limit, so there is no capacity to "
        "report. That is a gap in the owner's policy, not a measurement failure"
    )


def _encode_amount(value: Decimal | Money) -> Any:
    if isinstance(value, Money):
        return value.to_payload()
    return canonical_decimal_text(value)
