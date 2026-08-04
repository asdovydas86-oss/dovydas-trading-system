"""Value types for the Deterministic Daily Workflow.

A `DailyRun` is a **first-class object**, not terminal text. The compact
renderer, and every future Telegram, JSON or persistence consumer, read this
model and nothing else.

**One result per requested symbol, always.** A symbol that failed produces a
`SymbolResult` carrying the failure rather than vanishing from the run — a
missing row is indistinguishable from a symbol nobody asked about, and a daily
routine that silently drops instruments is worse than one that reports nothing.

**Nothing here ranks.** There is no score, no ordering by attractiveness, and no
member naming a direction. The run preserves the order the caller asked for, and
`SPEC` §7's warning about excessive confidence applies to a list exactly as it
applies to a page: a sorted list *is* a claim.

**Readiness is not opportunity.** `ContextState` is carried through unchanged
from `fmis.decision_context`. `SUFFICIENT` says the analysis rests on the data
each layer asked for; it says nothing about whether the instrument is worth
trading, and a test asserts no such word appears anywhere in this package.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

__all__ = [
    "DAILY_SCHEMA_VERSION",
    "ResultCategory",
    "FailureKind",
    "SymbolFailure",
    "SymbolResult",
    "DailyRun",
    "DailyRunError",
    "MAXIMUM_SYMBOLS",
    "require_symbols",
]

#: Bumped when the serialized shape changes in a way a consumer must notice.
DAILY_SCHEMA_VERSION = 1

#: The largest universe one run accepts. A stated policy, not a measurement, in
#: the sense ADR-0017 established: the workspace fetches three timeframes per
#: symbol, so 50 symbols is 150 sequential provider calls, and a run large
#: enough to be rate-limited halfway is a run whose failures are the tool's fault
#: rather than the market's. A caller with a larger universe splits it, which is
#: visible, rather than discovering the limit as a provider error.
MAXIMUM_SYMBOLS = 50


class DailyRunError(Exception):
    """Base class for every daily-workflow failure.

    Follows the package-error convention `IngestError`, `WorkspaceError` and
    `DecisionContextError` established elsewhere, so a caller can catch this
    layer's failures as a group.

    Raised for failures of the **run**, never of a symbol: a symbol that could
    not be analysed becomes a `SymbolResult`, because one instrument's outage is
    not a reason to discard the other nineteen.
    """


class ResultCategory(str, Enum):
    """What happened to one requested symbol.

    The first three mirror `ContextState` exactly and are **derived from it**,
    never re-decided here — AL owns that judgement and ADR-0026 forbids adding
    thresholds around it. `FAILED` is a different kind of thing altogether: the
    analysis did not happen, as opposed to happening and resting on too little.

    Conflating those two is the error this enum exists to prevent. An
    insufficient analysis is a fact about the market's data; a provider outage is
    a fact about the network, and a reader must be able to tell which morning
    they are having.
    """

    SUFFICIENT = "sufficient"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"
    FAILED = "failed"


class FailureKind(str, Enum):
    """Why a symbol produced no workspace.

    Deliberately excludes any member for a programming defect. An unexpected
    exception is **not** converted into a result — it propagates, because a
    daily report that renders an internal bug as an ordinary market failure
    teaches the owner to ignore it.
    """

    #: The provider rejected the symbol, or the caller supplied something the
    #: provider cannot address. User-actionable.
    INVALID_SYMBOL = "invalid_symbol"
    #: The request could not be completed — network, timeout, provider error.
    #: Not the caller's fault and usually transient.
    PROVIDER_FAILURE = "provider_failure"
    #: The provider answered, but with too few candles to analyse at all.
    #: Distinct from `INSUFFICIENT`, which means an analysis *was* produced.
    INSUFFICIENT_DATA = "insufficient_data"
    #: The response could not be decoded into the canonical model.
    MALFORMED_DATA = "malformed_data"


@dataclass(frozen=True, slots=True)
class SymbolFailure:
    """Why one symbol produced no analysis, in the caller's terms.

    ``detail`` is the underlying exception's message, carried verbatim rather
    than rewritten: a provider's own wording is more useful to whoever has to
    fix it than a paraphrase this layer invented.

    ``exception_type`` names the class, so a reader can tell a rejected symbol
    from a timed-out one without parsing prose.
    """

    kind: FailureKind
    detail: str
    exception_type: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FailureKind):
            raise TypeError(
                f"kind must be a FailureKind, got {type(self.kind).__name__}"
            )
        for name in ("detail", "exception_type"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DailyRunError(f"{name} must be a non-empty str")


@dataclass(frozen=True, slots=True)
class SymbolResult:
    """Exactly one outcome for exactly one requested symbol.

    ``requested_symbol`` is what the caller typed and is **never** overwritten.
    ``resolved_symbol`` is what the provider answered about. They are separate
    fields so a future normalising provider makes the difference visible rather
    than silently answering about something else — the same reasoning ADR-0023
    applied to a requested interval against a returned one.

    ``workspace`` and ``context`` are carried by reference when the analysis
    completed, so the compact index and a full page read the *same* objects and
    cannot disagree. Both are ``None`` exactly when ``category`` is `FAILED`.
    """

    requested_symbol: str
    category: ResultCategory
    resolved_symbol: str | None = None
    workspace: Any = None
    context: Any = None
    failure: SymbolFailure | None = None
    #: The primary view's three regime dimensions, already reduced to a display
    #: string by the composition root. Carried as **data** so the renderer needs
    #: no lookup into a workspace section — a renderer that reached into another
    #: model's sections would be doing composition, and would couple the index to
    #: the page's internal shape.
    regime_summary: str | None = None
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.requested_symbol, str) or not self.requested_symbol.strip():
            raise DailyRunError("requested_symbol must be a non-empty str")
        if not isinstance(self.category, ResultCategory):
            raise TypeError(
                f"category must be a ResultCategory, got {type(self.category).__name__}"
            )
        failed = self.category is ResultCategory.FAILED
        if failed:
            if self.failure is None:
                raise DailyRunError(
                    "a failed symbol must carry its failure; a failure without a "
                    "reason is indistinguishable from an empty result"
                )
            if self.workspace is not None or self.context is not None:
                raise DailyRunError(
                    "a failed symbol cannot carry a workspace or a context"
                )
        else:
            if self.workspace is None or self.context is None:
                raise DailyRunError(
                    f"a {self.category.value} symbol must carry both its "
                    "workspace and its decision context"
                )
            if self.failure is not None:
                raise DailyRunError(
                    "a completed symbol cannot also carry a failure"
                )
        if self.failure is not None and not isinstance(self.failure, SymbolFailure):
            raise TypeError("failure must be a SymbolFailure or None")
        if self.regime_summary is not None and not isinstance(self.regime_summary, str):
            raise TypeError("regime_summary must be a str or None")
        if self.resolved_symbol is not None and (
            not isinstance(self.resolved_symbol, str) or not self.resolved_symbol.strip()
        ):
            raise DailyRunError("resolved_symbol must be a non-empty str or None")
        if self.duration_seconds is not None:
            if isinstance(self.duration_seconds, bool) or not isinstance(
                self.duration_seconds, (int, float)
            ):
                raise TypeError("duration_seconds must be a number or None")
            if self.duration_seconds < 0:
                raise DailyRunError("duration_seconds cannot be negative")

    @property
    def completed(self) -> bool:
        """Whether an analysis was produced, whatever it then concluded."""
        return self.category is not ResultCategory.FAILED


@dataclass(frozen=True, slots=True)
class DailyRun:
    """One pass over a requested universe, in the order it was requested.

    ``results`` holds exactly one entry per requested symbol, in **input order**.
    That order is the contract: reordering by any property of the analysis would
    be a ranking, and a list sorted by readiness reads as a list sorted by
    attractiveness however it is labelled.

    ``reference_time`` is supplied by the outer boundary. Nothing in this package
    reads a clock, so two runs over the same stored candles are identical.

    Counts are **projections** over ``results``, never stored beside them —
    ADR-0016 §4, applied to an aggregate: a stored count is somewhere for the
    total to disagree with its own members.
    """

    reference_time: datetime
    results: tuple[SymbolResult, ...]
    objective: str
    source: str
    schema_version: int = DAILY_SCHEMA_VERSION
    limitations: tuple[tuple[str, str], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.reference_time, datetime):
            raise TypeError(
                f"reference_time must be a datetime, got "
                f"{type(self.reference_time).__name__}"
            )
        for name in ("objective", "source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DailyRunError(f"{name} must be a non-empty str")
        if not isinstance(self.results, tuple):
            raise TypeError("results must be a tuple of SymbolResult")
        for position, result in enumerate(self.results):
            if not isinstance(result, SymbolResult):
                raise TypeError(
                    f"results[{position}] must be a SymbolResult, got "
                    f"{type(result).__name__}"
                )
        if not self.results:
            raise DailyRunError(
                "a run needs at least one result; an empty universe is a caller "
                "error rather than a run with nothing in it"
            )
        if not isinstance(self.schema_version, int) or isinstance(
            self.schema_version, bool
        ):
            raise TypeError("schema_version must be an int")
        if not isinstance(self.limitations, tuple):
            raise TypeError("limitations must be a tuple of (code, text) pairs")
        if not self.limitations:
            raise DailyRunError(
                "a run must state its limitations; a page of results with no "
                "caveats is the excessive confidence SPEC §7 warns against"
            )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def requested_symbols(self) -> tuple[str, ...]:
        """What the caller asked for, in the order they asked."""
        return tuple(result.requested_symbol for result in self.results)

    @property
    def requested_count(self) -> int:
        return len(self.results)

    @property
    def completed_count(self) -> int:
        return sum(1 for result in self.results if result.completed)

    @property
    def failed_count(self) -> int:
        return sum(1 for result in self.results if not result.completed)

    def count_of(self, category: ResultCategory) -> int:
        """How many results fell into one category — derived, never stored."""
        if not isinstance(category, ResultCategory):
            raise TypeError(
                f"category must be a ResultCategory, got {type(category).__name__}"
            )
        return sum(1 for result in self.results if result.category is category)

    def by_symbol(self, symbol: str) -> SymbolResult | None:
        """The result for one requested symbol, or ``None`` if it was not asked for.

        Matches on ``requested_symbol`` — what the caller typed — because that is
        what they will type again to look it up.
        """
        for result in self.results:
            if result.requested_symbol == symbol:
                return result
        return None


def require_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    """Validate a requested universe, preserving order and rejecting ambiguity.

    Rejects rather than repairs, following the rule `DuplicateLevelError`
    established: a duplicate symbol is a caller mistake, and silently collapsing
    it would change the row count the caller expected without saying so.

    Raises:
        TypeError: ``symbols`` is not a non-string sequence, or an element is not
            a string.
        DailyRunError: the universe is empty, contains a blank entry, repeats a
            symbol, or exceeds `MAXIMUM_SYMBOLS`.
    """
    if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence):
        raise TypeError(
            f"symbols must be a non-string sequence, got {type(symbols).__name__}"
        )
    cleaned: list[str] = []
    for position, symbol in enumerate(symbols):
        if not isinstance(symbol, str):
            raise TypeError(
                f"symbols[{position}] must be a str, got {type(symbol).__name__}"
            )
        if not symbol.strip():
            raise DailyRunError(f"symbols[{position}] is blank")
        cleaned.append(symbol.strip())
    if not cleaned:
        raise DailyRunError("at least one symbol is required")
    if len(set(cleaned)) != len(cleaned):
        repeated = sorted({s for s in cleaned if cleaned.count(s) > 1})
        raise DailyRunError(
            f"symbols must not repeat: {', '.join(repeated)}. A repeat is "
            "rejected rather than collapsed, because collapsing would change "
            "the row count without saying so"
        )
    if len(cleaned) > MAXIMUM_SYMBOLS:
        raise DailyRunError(
            f"{len(cleaned)} symbols exceeds the maximum of {MAXIMUM_SYMBOLS}; "
            "split the universe rather than risk a run failing halfway through"
        )
    return tuple(cleaned)
