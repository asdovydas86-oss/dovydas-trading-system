"""`RiskBudget` and `RiskBudgetState` — the owner's limits, and what is left of them.

**BG-D3.** Three reasons this is its own entity rather than a field group on a
portfolio, and the third is the binding one:

1. The specification requires a **maximum daily loss** and drawdown controls. A
   daily loss limit has a *period* and a *local calendar boundary*; a flat field
   set has no period concept.
2. A constraint check must cite the `risk_policy_version` it evaluated against, or
   a limit change silently reinterprets a past check. A version needs an object
   to sit on.
3. **The 2 % rule is a ceiling, not a target**, and expressing that — a limit with
   a ceiling semantic and a separate default below it — is not expressible as a
   number in a flat map.

**Two objects, deliberately.** `RiskBudget` is `ASSERTED` and versioned;
`RiskBudgetState` is `MEASURED` and recomputed. Merging them produces a record
whose limit appears to change whenever exposure changes — and the failure would be
invisible, because the merged object would always look internally consistent.

**This module contains no threshold.** Every value is the owner's, supplied at
construction. The precedent is the decision-context engine's `ContextPolicy`, the one
policy object in the repository carrying no numbers, asserted by a test that no
numeric literal beyond 0 and 1 appears in the evaluator. The same test is applied
here.

**Period boundaries are owner-local.** A "daily loss limit" measured on UTC days
for a Stockholm-based owner would reset in the middle of his evening, so a period
key is resolved through `OwnerContext.display_timezone` at read time and is never
a stored field.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fmis.accounts import OwnerContext
from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.money import Money, canonical_decimal_text, parse_decimal
from fmis.provenance import Absent, ValueOrigin, decode_maybe, encode_maybe
from fmis.records import (
    IDENTIFIER_PATTERN,
    DomainValidationError,
    PayloadDecodeError,
    RecordAudit,
    TradeDomainError,
    build_domain_record_id,
    content_digest_over,
    require_exact_keys,
    require_int,
    require_mapping,
    require_member,
    require_pattern,
    require_payload_version,
    require_text,
    require_tuple_of,
    require_unmodified,
    require_utc,
)

__all__ = [
    "RiskError",
    "RISK_BUDGET_SCHEMA_VERSION",
    "SUPPORTED_RISK_BUDGET_VERSIONS",
    "RISK_BUDGET_TYPE_SLUG",
    "RISK_BUDGET_KIND",
    "LimitScope",
    "LimitUnit",
    "LimitPeriod",
    "LimitSeverity",
    "LimitStatus",
    "RiskLimit",
    "RiskBudget",
    "LimitEvaluation",
    "RiskBudgetState",
    "effective_budget",
    "period_key",
    "evaluate_limit",
    "evaluate_budget",
]

RISK_BUDGET_SCHEMA_VERSION = 1
SUPPORTED_RISK_BUDGET_VERSIONS = frozenset({1})
RISK_BUDGET_TYPE_SLUG = "risk_budget"
RISK_BUDGET_KIND = "risk_budget"


class RiskError(TradeDomainError):
    """Base class for every risk-budget failure."""


class LimitScope(Enum):
    """What a limit constrains. Each is traced to a source rather than invented."""

    #: Per-trade risk as a share of equity. **A hard ceiling, not a default target.**
    PER_TRADE_RISK = "per_trade_risk"
    #: Total risk across all open positions.
    TOTAL_OPEN_RISK = "total_open_risk"
    #: Share of open risk in one key — asset, venue, book.
    CONCENTRATION = "concentration"
    #: Share of open risk in one correlated cluster.
    CLUSTER_EXPOSURE = "cluster_exposure"
    LEVERAGE = "leverage"
    #: *"A swing trader managing eight positions is day trading."*
    MAX_CONCURRENT_POSITIONS = "max_concurrent_positions"
    MIN_RESERVE = "min_reserve"
    #: The specification's required maximum daily loss, generalized to a period.
    PERIOD_LOSS = "period_loss"
    DRAWDOWN = "drawdown"


class LimitUnit(Enum):
    """What the limit's number means. There is no bare number in this domain."""

    PERCENT_OF_EQUITY = "percent_of_equity"
    PERCENT_OF_OPEN_RISK = "percent_of_open_risk"
    PERCENT_FROM_PEAK = "percent_from_peak"
    RATIO = "ratio"
    COUNT = "count"
    MONEY = "money"


class LimitPeriod(Enum):
    """The window a limit is measured over, with owner-local boundaries."""

    NONE = "none"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    ROLLING = "rolling"


class LimitSeverity(Enum):
    """What breaching costs.

    A `HARD_BLOCK` means the system refuses to produce the number or the record.
    It does not, and cannot, prevent the owner from trading anyway — and when he
    does, the override is recorded as a first-class datum. A block the owner can
    walk past, *which counts how often he walks past it*, is a stronger discipline
    than a block pretending to be absolute.
    """

    HARD_BLOCK = "hard_block"
    ADVISORY = "advisory"


class LimitStatus(Enum):
    """Where a measured value sits against its limit.

    **`Absent(reason)` is a first-class fourth answer and is never silently
    `WITHIN`.** No liquidity source, no correlation history, a stale snapshot —
    each is reported. An indeterminate result is *"third most likely to be
    ignored, because it looks like 'no problem found' unless rendered
    distinctly"*, which the data model can only support by making it a different
    value rather than a flag.
    """

    WITHIN = "within"
    AT_LIMIT = "at_limit"
    EXCEEDED = "exceeded"


@dataclass(frozen=True, slots=True)
class RiskLimit:
    """One limit the owner set. **This class supplies no value; it validates one.**"""

    limit_id: str
    scope: LimitScope
    value: Decimal | Money
    unit: LimitUnit
    period: LimitPeriod
    severity: LimitSeverity
    key: str | Absent = field(default_factory=lambda: Absent("applies portfolio-wide"))
    default_below_ceiling: Decimal | Absent = field(
        default_factory=lambda: Absent("no default below this ceiling")
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "limit_id", require_pattern(self.limit_id, IDENTIFIER_PATTERN, "limit_id")
        )
        require_member(self.scope, LimitScope, "scope")
        require_member(self.unit, LimitUnit, "unit")
        require_member(self.period, LimitPeriod, "period")
        require_member(self.severity, LimitSeverity, "severity")
        if self.unit is LimitUnit.MONEY:
            if not isinstance(self.value, Money):
                raise TypeError(
                    "a MONEY limit's value is a Money; a bare number would be an "
                    "amount with no asset, which does not exist in this domain"
                )
            if self.value.amount <= 0:
                raise DomainValidationError("a money limit must be positive")
        else:
            if not isinstance(self.value, Decimal):
                raise TypeError(
                    f"a {self.unit.value} limit's value is a Decimal, got "
                    f"{type(self.value).__name__}"
                )
            if self.value <= 0:
                raise DomainValidationError(
                    f"limit value must be positive, got {self.value}"
                )
            object.__setattr__(
                self, "value", Decimal(canonical_decimal_text(self.value))
            )
        if not isinstance(self.key, Absent):
            object.__setattr__(self, "key", require_text(self.key, "key"))
        if not isinstance(self.default_below_ceiling, Absent):
            if not isinstance(self.default_below_ceiling, Decimal):
                raise TypeError("default_below_ceiling must be a Decimal or Absent")
            if self.unit is LimitUnit.MONEY:
                raise DomainValidationError(
                    "default_below_ceiling expresses a fraction of the ceiling and "
                    "does not apply to a money limit"
                )
            if not Decimal(0) < self.default_below_ceiling < self.value:
                raise DomainValidationError(
                    f"default_below_ceiling {self.default_below_ceiling} must sit "
                    f"strictly between zero and the ceiling {self.value}. A default "
                    "at the ceiling is a target, and the ceiling is not a target"
                )
            object.__setattr__(
                self,
                "default_below_ceiling",
                Decimal(canonical_decimal_text(self.default_below_ceiling)),
            )
        if self.scope in _PERIODLESS_SCOPES and self.period is not LimitPeriod.NONE:
            raise DomainValidationError(
                f"{self.scope.value} is measured continuously and carries no "
                f"period; got {self.period.value}"
            )
        if self.scope is LimitScope.PERIOD_LOSS and self.period is LimitPeriod.NONE:
            raise DomainValidationError(
                "a period loss limit names its period; a loss limit with no period "
                "is the specification's requirement with its content removed"
            )

    @property
    def origin(self) -> ValueOrigin:
        """`ASSERTED` — the owner's policy, never the system's judgement."""
        return ValueOrigin.ASSERTED

    @property
    def is_ceiling(self) -> bool:
        """Whether a separate, lower default was stated beside this ceiling."""
        return not isinstance(self.default_below_ceiling, Absent)

    def to_payload(self) -> dict[str, Any]:
        return {
            "limit_id": self.limit_id,
            "scope": self.scope.value,
            "value": (
                self.value.to_payload()
                if isinstance(self.value, Money)
                else canonical_decimal_text(self.value)
            ),
            "unit": self.unit.value,
            "period": self.period.value,
            "severity": self.severity.value,
            "key": encode_maybe(self.key, str),
            "default_below_ceiling": encode_maybe(
                self.default_below_ceiling, canonical_decimal_text
            ),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> RiskLimit:
        mapping = require_mapping(raw, "risk limit")
        require_exact_keys(
            mapping,
            {
                "limit_id",
                "scope",
                "value",
                "unit",
                "period",
                "severity",
                "key",
                "default_below_ceiling",
            },
            "risk limit",
        )
        unit = _member(LimitUnit, mapping["unit"], "unit")
        value: Decimal | Money
        if unit is LimitUnit.MONEY:
            value = Money.from_payload(mapping["value"], "limit value")
        else:
            value = parse_decimal(mapping["value"], "limit value")
        return cls(
            limit_id=str(mapping["limit_id"]),
            scope=_member(LimitScope, mapping["scope"], "scope"),
            value=value,
            unit=unit,
            period=_member(LimitPeriod, mapping["period"], "period"),
            severity=_member(LimitSeverity, mapping["severity"], "severity"),
            key=decode_maybe(mapping["key"], str),
            default_below_ceiling=decode_maybe(
                mapping["default_below_ceiling"],
                lambda item: parse_decimal(item, "default_below_ceiling"),
            ),
        )


#: Scopes measured continuously rather than over a window.
_PERIODLESS_SCOPES: frozenset[LimitScope] = frozenset(
    {
        LimitScope.PER_TRADE_RISK,
        LimitScope.TOTAL_OPEN_RISK,
        LimitScope.CONCENTRATION,
        LimitScope.CLUSTER_EXPOSURE,
        LimitScope.LEVERAGE,
        LimitScope.MAX_CONCURRENT_POSITIONS,
        LimitScope.MIN_RESERVE,
    }
)


@dataclass(frozen=True, slots=True)
class RiskBudget:
    """One version of the owner's limit set, appended as a config event.

    Every past version stays readable and resolvable. A change **never**
    re-evaluates a frozen check: that check cited the version it ran against, and
    re-running it later answers a different question because both the limits and
    the portfolio have moved.
    """

    budget_id: str
    risk_policy_version: int
    effective_from: datetime
    limits: tuple[RiskLimit, ...]
    audit: RecordAudit
    note: str | Absent = field(default_factory=lambda: Absent("no note"))
    schema_version: int = RISK_BUDGET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "budget_id",
            require_pattern(self.budget_id, IDENTIFIER_PATTERN, "budget_id"),
        )
        require_int(self.risk_policy_version, "risk_policy_version", minimum=1)
        object.__setattr__(
            self, "effective_from", require_utc(self.effective_from, "effective_from")
        )
        require_tuple_of(self.limits, RiskLimit, "limits", minimum_length=1)
        identifiers = [limit.limit_id for limit in self.limits]
        if len(set(identifiers)) != len(identifiers):
            raise DomainValidationError(
                "a limit_id appears twice; one limit, one value, or a check has "
                "two answers"
            )
        require_unmodified(self.audit, "RiskBudget")
        if not isinstance(self.note, Absent):
            object.__setattr__(self, "note", require_text(self.note, "note"))
        if self.schema_version not in SUPPORTED_RISK_BUDGET_VERSIONS:
            raise DomainValidationError(
                f"risk budget schema_version {self.schema_version} is not one this "
                f"build writes ({sorted(SUPPORTED_RISK_BUDGET_VERSIONS)})"
            )

    @property
    def origin(self) -> ValueOrigin:
        return ValueOrigin.ASSERTED

    def limit(self, limit_id: str) -> RiskLimit | None:
        wanted = require_text(limit_id, "limit_id")
        for candidate in self.limits:
            if candidate.limit_id == wanted:
                return candidate
        return None

    def limits_for(self, scope: LimitScope) -> tuple[RiskLimit, ...]:
        require_member(scope, LimitScope, "scope")
        return tuple(limit for limit in self.limits if limit.scope is scope)

    @property
    def digest_basis(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "budget_id": self.budget_id,
            "risk_policy_version": self.risk_policy_version,
            "effective_from": encode_timestamp(self.effective_from),
            "limits": [limit.to_payload() for limit in self.limits],
            "note": encode_maybe(self.note, str),
        }

    @property
    def budget_record_id(self) -> str:
        return build_domain_record_id(
            type_slug=RISK_BUDGET_TYPE_SLUG,
            subject=self.budget_id,
            moment=self.effective_from,
            digest=content_digest_over(self.digest_basis),
        )

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload["budget_record_id"] = self.budget_record_id
        payload["audit"] = self.audit.to_payload()
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> RiskBudget:
        mapping = require_mapping(raw, "risk budget")
        version = require_payload_version(
            mapping, supported=SUPPORTED_RISK_BUDGET_VERSIONS, entity="risk budget"
        )
        require_exact_keys(
            mapping,
            {
                "schema_version",
                "budget_record_id",
                "budget_id",
                "risk_policy_version",
                "effective_from",
                "limits",
                "note",
                "audit",
            },
            "risk budget",
        )
        raw_limits = mapping["limits"]
        if not isinstance(raw_limits, list):
            raise PayloadDecodeError("risk budget limits must be a JSON array")
        decoded = cls(
            budget_id=str(mapping["budget_id"]),
            risk_policy_version=mapping["risk_policy_version"],
            effective_from=decode_timestamp(mapping["effective_from"]),
            limits=tuple(RiskLimit.from_payload(item) for item in raw_limits),
            audit=RecordAudit.from_payload(mapping["audit"]),
            note=decode_maybe(mapping["note"], str),
            schema_version=version,
        )
        if mapping["budget_record_id"] != decoded.budget_record_id:
            raise PayloadDecodeError(
                f"budget_record_id {mapping['budget_record_id']!r} does not match "
                f"the digest of the budget it identifies "
                f"({decoded.budget_record_id!r})"
            )
        return decoded


def effective_budget(
    budgets: Iterable[RiskBudget], at: datetime
) -> RiskBudget | Absent:
    """The budget in force at an instant — a fold over config events.

    A change never rewrites history: an evaluation dated before a bump resolves to
    the older version, which is the whole reason a frozen constraint check stays
    meaningful after the owner tightens a limit.
    """
    moment = require_utc(at, "at")
    candidates = [
        budget
        for budget in budgets
        if isinstance(budget, RiskBudget) and budget.effective_from <= moment
    ]
    if not candidates:
        return Absent(f"no risk budget was in force at {moment.isoformat()}")
    return max(
        candidates, key=lambda budget: (budget.effective_from, budget.risk_policy_version)
    )


def period_key(limit: RiskLimit, moment: datetime, owner: OwnerContext) -> str | Absent:
    """The owner-local bucket a periodic limit is measured over.

    A **read-time projection**, never a stored field. ADR-0001 is untouched: UTC
    stays canonical for storage, and this converts at the boundary so a relocation
    changes what future buckets mean without rewriting a single stored instant.
    """
    if not isinstance(limit, RiskLimit):
        raise TypeError("limit must be a RiskLimit")
    if not isinstance(owner, OwnerContext):
        raise TypeError("owner must be an OwnerContext")
    local = require_utc(moment, "moment").astimezone(owner.display_zone)
    if limit.period is LimitPeriod.NONE:
        return Absent(f"{limit.limit_id} is measured continuously and has no period")
    if limit.period is LimitPeriod.ROLLING:
        return Absent(
            f"{limit.limit_id} is measured over a rolling window, which has no "
            "calendar bucket"
        )
    if limit.period is LimitPeriod.DAY:
        return local.date().isoformat()
    if limit.period is LimitPeriod.WEEK:
        year, week, _ = local.isocalendar()
        return f"{year}-W{week:02d}"
    return f"{local.year}-{local.month:02d}"


@dataclass(frozen=True, slots=True)
class LimitEvaluation:
    """One limit, what was measured against it, and how much room is left."""

    limit_id: str
    limit_value: Decimal | Money
    current_value: Decimal | Money | Absent
    status: LimitStatus | Absent

    def __post_init__(self) -> None:
        object.__setattr__(self, "limit_id", require_text(self.limit_id, "limit_id"))
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
        if isinstance(self.current_value, Money) and isinstance(self.limit_value, Money):
            if self.current_value.asset != self.limit_value.asset:
                raise DomainValidationError(
                    "a money limit and its measurement are stated in one currency"
                )
        elif isinstance(self.current_value, Money) or isinstance(self.limit_value, Money):
            if not isinstance(self.current_value, Absent):
                raise DomainValidationError(
                    "a money limit is measured in money, and a ratio limit in a "
                    "ratio; mixing them compares two different things"
                )

    @property
    def headroom(self) -> Decimal | Money | Absent:
        """`limit − current`. A subtraction, never a ratio, and never stored."""
        if isinstance(self.current_value, Absent):
            return self.current_value
        if isinstance(self.limit_value, Money):
            assert isinstance(self.current_value, Money)  # validated above
            return self.limit_value - self.current_value
        assert isinstance(self.current_value, Decimal)  # validated above
        return self.limit_value - self.current_value

    def to_payload(self) -> dict[str, Any]:
        return {
            "limit_id": self.limit_id,
            "limit_value": _encode_amount(self.limit_value),
            "current_value": encode_maybe(self.current_value, _encode_amount),
            "status": encode_maybe(
                self.status, lambda status: status.value
            ),
        }


def evaluate_limit(
    limit: RiskLimit, current: Decimal | Money | Absent
) -> LimitEvaluation:
    """Compare a measured value against a limit. Pure arithmetic, no judgement.

    Returns **per-limit facts, never a verdict**. `EXCEEDED` on the open-risk
    budget is a fact; *"don't take this trade"* is the owner's conclusion.
    """
    if not isinstance(limit, RiskLimit):
        raise TypeError("limit must be a RiskLimit")
    if isinstance(current, Absent):
        return LimitEvaluation(
            limit_id=limit.limit_id,
            limit_value=limit.value,
            current_value=current,
            status=Absent(current.reason),
        )
    if isinstance(limit.value, Money):
        if not isinstance(current, Money):
            raise TypeError("a money limit is measured in Money")
        if current.asset != limit.value.asset:
            raise DomainValidationError(
                f"limit {limit.limit_id} is stated in {limit.value.asset} and the "
                f"measurement is in {current.asset}; a limit and its measurement "
                "are stated in one currency, and converting here would hide the "
                "rate that made them comparable"
            )
        exceeded = current > limit.value
        at_limit = current == limit.value
    else:
        if not isinstance(current, Decimal):
            raise TypeError("a numeric limit is measured with a Decimal")
        exceeded = current > limit.value
        at_limit = current == limit.value
    status = (
        LimitStatus.EXCEEDED
        if exceeded
        else LimitStatus.AT_LIMIT
        if at_limit
        else LimitStatus.WITHIN
    )
    return LimitEvaluation(
        limit_id=limit.limit_id,
        limit_value=limit.value,
        current_value=current,
        status=status,
    )


@dataclass(frozen=True, slots=True)
class RiskBudgetState:
    """What is left of each limit right now — the `MEASURED` half.

    Computed on demand, **never stored**, freely deletable. It reports the
    `risk_policy_version` it read so that a state and the policy behind it can
    never be mistaken for one object.
    """

    budget_id: str
    risk_policy_version: int
    evaluated_at: datetime
    evaluations: tuple[LimitEvaluation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "budget_id", require_text(self.budget_id, "budget_id"))
        require_int(self.risk_policy_version, "risk_policy_version", minimum=1)
        object.__setattr__(
            self, "evaluated_at", require_utc(self.evaluated_at, "evaluated_at")
        )
        require_tuple_of(
            self.evaluations, LimitEvaluation, "evaluations", minimum_length=1
        )
        identifiers = [entry.limit_id for entry in self.evaluations]
        if len(set(identifiers)) != len(identifiers):
            raise DomainValidationError("a limit must not be evaluated twice")

    @property
    def origin(self) -> ValueOrigin:
        """`MEASURED`. The policy it read is `ASSERTED`, and they are two objects."""
        return ValueOrigin.MEASURED

    @property
    def exceeded(self) -> tuple[LimitEvaluation, ...]:
        return tuple(
            entry for entry in self.evaluations if entry.status is LimitStatus.EXCEEDED
        )

    @property
    def indeterminate(self) -> tuple[LimitEvaluation, ...]:
        """Limits that could not be measured — reported, never counted as within."""
        return tuple(
            entry for entry in self.evaluations if isinstance(entry.status, Absent)
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "budget_id": self.budget_id,
            "risk_policy_version": self.risk_policy_version,
            "evaluated_at": encode_timestamp(self.evaluated_at),
            "evaluations": [entry.to_payload() for entry in self.evaluations],
        }


def evaluate_budget(
    budget: RiskBudget,
    measurements: dict[str, Decimal | Money | Absent],
    *,
    evaluated_at: datetime,
) -> RiskBudgetState:
    """Evaluate every limit in a budget against supplied measurements.

    A limit with no measurement becomes `Absent(reason)` rather than being
    skipped: a state that silently omits a limit reads as a clean bill of health.
    """
    if not isinstance(budget, RiskBudget):
        raise TypeError("budget must be a RiskBudget")
    if not isinstance(measurements, dict):
        raise TypeError("measurements must be a dict keyed by limit_id")
    unknown = set(measurements) - {limit.limit_id for limit in budget.limits}
    if unknown:
        raise DomainValidationError(
            f"measurements name limits this budget does not hold: {sorted(unknown)}"
        )
    entries = tuple(
        evaluate_limit(
            limit,
            measurements.get(
                limit.limit_id,
                Absent(f"{limit.limit_id} was not measured in this evaluation"),
            ),
        )
        for limit in budget.limits
    )
    return RiskBudgetState(
        budget_id=budget.budget_id,
        risk_policy_version=budget.risk_policy_version,
        evaluated_at=evaluated_at,
        evaluations=entries,
    )


def _encode_amount(value: Decimal | Money) -> Any:
    if isinstance(value, Money):
        return value.to_payload()
    return canonical_decimal_text(value)


def _member(enum_type: Any, value: Any, entity: str) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise PayloadDecodeError(
            f"{entity} {value!r} is not a known {enum_type.__name__}"
        ) from error
