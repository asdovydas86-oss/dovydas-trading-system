"""The shapes a macro & cross-asset context is made of, and every rule they enforce.

This module defines *what can be said* about the macro picture, and nothing about
how to say it or how to obtain it. It computes no market quantity, reads no
clock, and imports no provider, no engine and no surface.

It follows `fmis.market_pulse.models` deliberately and closely — the same
absence-is-a-value discipline, the same *exactly one of value-or-reason* rule,
the same refusal to hold a number without the window it was measured over. What
it adds is the vocabulary a macro page needs and an orientation page does not:

  * **A level.** `fmits pulse` prints moves, because *"what is happening"* is a
    question about change. `fmits macro` must also print *"US 10-year: 4.69%"*,
    because *"what is the dollar doing"* is answered partly by where it is. So
    `MacroLevel` exists here and deliberately not in the pulse.
  * **A rate fact.** `RateFact` carries a yield's level and its move in basis
    points. It is a separate type from a price-like reading rather than a flag on
    one, so no code path can reach a yield's basis-point change through a field
    named for a percentage return.
  * **A refused comparison.** `CrossAssetRelationship` can hold a correlation or
    the exact reason there is none, and one of the available reasons is that the
    two series were never comparable in the first place.

**No interpretation is representable.** There is no field here named regime,
score, signal, bias, risk_on, tightening or easing, and none can be added without
deleting a docstring. A relationship holds a number, an observation count, a
window and an alignment record — and nothing that says what any of it means.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fmis.market_pulse import (
    Benchmark,
    FreshnessState,
    Horizon,
    MarketReading,
    MarketUnavailable,
    MarketUniverse,
    QuantityKind,
)
from fmis.macro.comparability import ComparabilityKey
from fmis.macro.rates import RateChange

__all__ = [
    "MacroError",
    "MacroReportError",
    "MacroLevel",
    "RateFact",
    "CrossAssetRelationship",
    "MacroContextReport",
    "MACRO_ORIENTATION_NOTE",
    "MACRO_SESSION_LIMITATION",
    "MACRO_RELATIONSHIP_CAVEAT",
    "MACRO_FRESHNESS_NOTE",
    "MACRO_RATE_NOTE",
]

_ZERO = timedelta(0)


class MacroError(Exception):
    """Base class for every failure raised by this package."""


class MacroReportError(MacroError, ValueError):
    """A macro context does not describe the universe it claims to describe.

    A distinct type for the same reason `PulseUniverseError` is one: this is a
    **construction** defect that no retry fixes, and it must fail loudly rather
    than produce a page that quietly omits a market or reports one twice.
    """


# ---------------------------------------------------------------- validation ---


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str, got {type(value).__name__}")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must not be blank")
    return stripped


def _utc(value: Any, name: str) -> datetime:
    """A timezone-aware, zero-offset instant — the canonical-time contract.

    Restated rather than imported from `fmis.data._timeutils`, for the reason
    `fmis.market_pulse.models` and `fmis.marks.models` both record for the
    identical helper: reaching into another package's private module is a
    coupling that survives until the day that module moves, and the rule is
    three lines.
    """
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime, got {type(value).__name__}")
    offset = value.utcoffset()
    if offset is None:
        raise ValueError(f"{name} must be timezone-aware")
    if offset != _ZERO:
        raise ValueError(f"{name} must represent UTC, got offset {offset}")
    return value


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return number


def _count(value: Any, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {type(value).__name__}")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {value}")
    return value


def _tuple_of(values: Any, expected: type, name: str) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        raise TypeError(f"{name} must be an iterable of {expected.__name__}")
    items = tuple(values)
    for item in items:
        if not isinstance(item, expected):
            raise TypeError(
                f"{name} must hold {expected.__name__} values, "
                f"got {type(item).__name__}"
            )
    return items


# --------------------------------------------------------------- vocabulary ---


#: The page's own statement of what it is for, printed at the top. A reader who
#: takes a macro page for a market view is the failure mode this whole surface
#: has to design against, and macro prose is where that failure is most tempting.
MACRO_ORIENTATION_NOTE = (
    "This page states measured macro and cross-asset facts. It contains no "
    "interpretation, no causal claim and no view: it will not tell you that a "
    "stronger dollar pressures risk assets, that rising yields are bearish, or "
    "that markets are risk-on or risk-off. Those are readings of the facts "
    "below, and this build does not make them. Nothing here is a signal, and no "
    "setup, plan, position or approval is read or changed by this command."
)

#: Printed above every window. The session limitation restated for a page whose
#: markets all close — where BT's crypto universe made the point mostly
#: theoretical, here it is the central caveat.
MACRO_SESSION_LIMITATION = (
    "Every market on this page closes, and this repository holds no trading "
    "calendar: no holiday table, no exchange timezone and no open/closed "
    "computation exists. Every window below is therefore a count of completed "
    "observations, which is well defined regardless of the calendar. No window "
    "is described in days or weeks, because five completed observations span "
    "seven calendar days in an ordinary week and nine across a holiday weekend, "
    "and this build cannot tell which it is looking at."
)

#: Printed above the cross-asset section.
MACRO_RELATIONSHIP_CAVEAT = (
    "A relationship below is the Pearson correlation of two markets' simple "
    "returns over one stated set of shared observation dates. It is a "
    "description of that window and nothing else: it is not causation, not a "
    "prediction, not a stable property of the pair, and not evidence that one "
    "market moved the other. Two markets can move together for a month and "
    "diverge the next day. Where the two series do not observe the same dates, "
    "the shared dates are used and the number of observations dropped from each "
    "side is stated. Two observations sharing a date are not necessarily "
    "simultaneous: a continuously traded market's daily observation covers the "
    "whole UTC day, while a US session market's covers that day's session, so a "
    "same-date pair describes the same day rather than the same hours."
)

#: Printed in the data-quality section.
MACRO_FRESHNESS_NOTE = (
    "Freshness is judged against each series' own publication schedule, not "
    "against one bound applied to everything. A daily macro series is not late "
    "because it did not update in an hour, and an hourly series is not current "
    "because it updated within a week. A reading is reported behind schedule "
    "only when it is older than its source's stated cadence and tolerance can "
    "explain; where no schedule is established, the age is stated and no verdict "
    "is given."
)

#: Printed above the rates section.
MACRO_RATE_NOTE = (
    "A yield is a rate, not a price, so its move is stated as a difference in "
    "basis points rather than as a percentage return. A move from 4.20% to "
    "4.30% is +10 basis points; calling it +2.38% would be arithmetically true "
    "and would answer a different question than the one a rates column asks. "
    "Where the relative change is also shown it is labelled as such and is never "
    "presented as the yield move."
)


# ------------------------------------------------------------------- levels ---


@dataclass(frozen=True, slots=True)
class MacroLevel:
    """Where one market currently is, with the unit that makes it mean anything.

    **The unit is not decoration and is never dropped.** `7674.37` is not a fact;
    *"7674.37 index points"* is. A macro page mixes index points, volatility
    points and percent per annum in one column of numbers, and a level printed
    without its unit invites the reader to compare two of them.

    `observed_at` is the **start** of the period the observation describes,
    following the convention `fmis.providers.fred` documents and
    `fmis.market_pulse.MarketReading.last_bar_open` already uses: it is the
    latest instant this repository can name honestly, and it makes an age
    overstated rather than understated.
    """

    benchmark_id: str
    display_name: str
    value: float
    unit: str
    quantity_kind: QuantityKind
    observed_at: datetime
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "benchmark_id", _text(self.benchmark_id, "benchmark_id")
        )
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        object.__setattr__(self, "value", _finite(self.value, "value"))
        object.__setattr__(self, "unit", _text(self.unit, "unit"))
        if not isinstance(self.quantity_kind, QuantityKind):
            raise TypeError(
                f"quantity_kind must be a QuantityKind, got "
                f"{type(self.quantity_kind).__name__}"
            )
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "source", _text(self.source, "source"))


# -------------------------------------------------------------------- rates ---


@dataclass(frozen=True, slots=True)
class RateFact:
    """One yield's level and its moves, stated in basis points.

    **A separate type from a price-like reading, on purpose.** A boolean on one
    shared type would let a yield's move reach a page through whatever field the
    renderer happened to read; two types mean the renderer must decide which it
    is holding, and the wrong branch does not typecheck rather than printing a
    plausible wrong number.

    `changes` maps a horizon id to the move over it. A horizon whose window the
    series could not fill is **absent** from the mapping rather than present with
    a zero: `changes_for` returns `None`, and the page prints the absence.
    """

    benchmark_id: str
    display_name: str
    level: MacroLevel
    changes: tuple[tuple[str, RateChange], ...]
    unavailable_horizons: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "benchmark_id", _text(self.benchmark_id, "benchmark_id")
        )
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        if not isinstance(self.level, MacroLevel):
            raise TypeError(
                f"level must be a MacroLevel, got {type(self.level).__name__}"
            )
        if self.level.quantity_kind is not QuantityKind.RATE_LIKE:
            raise MacroReportError(
                f"{self.benchmark_id} is reported as a rate fact but its level "
                f"is {self.level.quantity_kind.value}; a basis-point change of a "
                "price-like level is not a quantity this build states"
            )
        changes = tuple(self.changes)
        seen: set[str] = set()
        for entry in changes:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError(
                    f"changes must hold (horizon_id, RateChange) pairs, got {entry!r}"
                )
            horizon_id = _text(entry[0], "changes horizon_id")
            if not isinstance(entry[1], RateChange):
                raise TypeError(
                    "changes must hold RateChange values, got "
                    f"{type(entry[1]).__name__}"
                )
            if horizon_id in seen:
                raise MacroReportError(
                    f"{self.benchmark_id} reports horizon {horizon_id!r} twice; "
                    "one yield has one move per horizon, or a reader can choose "
                    "which one to believe"
                )
            seen.add(horizon_id)
        object.__setattr__(self, "changes", changes)

        unavailable = tuple(self.unavailable_horizons)
        for entry in unavailable:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError(
                    "unavailable_horizons must hold (horizon_id, reason) pairs, "
                    f"got {entry!r}"
                )
            horizon_id = _text(entry[0], "unavailable horizon_id")
            _text(entry[1], "unavailable reason")
            if horizon_id in seen:
                raise MacroReportError(
                    f"{self.benchmark_id} reports horizon {horizon_id!r} both as "
                    "a move and as unavailable; one window has one outcome"
                )
        object.__setattr__(self, "unavailable_horizons", unavailable)

    def change_for(self, horizon_id: str) -> RateChange | None:
        """The move over one horizon, or `None` when this yield has none for it."""
        wanted = _text(horizon_id, "horizon_id")
        for entry_id, change in self.changes:
            if entry_id == wanted:
                return change
        return None


# ------------------------------------------------------------ relationships ---


@dataclass(frozen=True, slots=True)
class CrossAssetRelationship:
    """How two markets moved together, or the exact reason they were not compared.

    **Three distinct outcomes are representable and they are not the same fact:**

      * a measured correlation, with the exact observation count and window;
      * *not comparable* — the two measurements were never the same question, and
        `comparability` names which components differed;
      * *not measurable* — comparable in principle, but the shared window was too
        short or the arithmetic was undefined over it.

    Collapsing the second into the third would tell the owner to wait for more
    data about a comparison that will never become valid.

    **Two counts, and conflating them is the mistake this type prevents.**
    `aligned_count` is how many dates the two series share in total;
    `observation_count` is how many of those the measured window actually used.
    A page printing one number would let *"21 observations"* stand for both, and
    a reader could not tell a pair with barely enough overlap from a pair with
    years of it. `subject_dropped` and `reference_dropped` record what alignment
    cost each side, so the reader knows the window was carved out of two
    different calendars.
    """

    subject_id: str
    reference_id: str
    metric: str
    value: float | None
    unavailable_reason: str | None
    observation_count: int
    aligned_count: int = 0
    comparability: ComparabilityKey | None = None
    not_comparable_detail: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    subject_dropped: int = 0
    reference_dropped: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", _text(self.subject_id, "subject_id"))
        object.__setattr__(
            self, "reference_id", _text(self.reference_id, "reference_id")
        )
        if self.subject_id == self.reference_id:
            raise MacroReportError(
                f"{self.subject_id} cannot be related to itself; a correlation of "
                "one market against itself is arithmetic, not information"
            )
        object.__setattr__(self, "metric", _text(self.metric, "metric"))

        if (self.value is None) == (self.unavailable_reason is None):
            raise MacroReportError(
                f"relationship {self.subject_id}/{self.reference_id} carries "
                "both a value and the reason it has none, or neither; one "
                "measurement has one outcome"
            )
        if self.value is not None:
            value = _finite(self.value, "value")
            if not -1.0 <= value <= 1.0:
                raise MacroReportError(
                    f"relationship {self.subject_id}/{self.reference_id} has "
                    f"value {value}, outside [-1, 1]; a Pearson correlation "
                    "cannot, so this is a broken reading"
                )
            object.__setattr__(self, "value", value)
        else:
            object.__setattr__(
                self,
                "unavailable_reason",
                _text(self.unavailable_reason, "unavailable_reason"),
            )

        object.__setattr__(
            self,
            "observation_count",
            _count(self.observation_count, "observation_count", minimum=0),
        )
        for name in ("aligned_count", "subject_dropped", "reference_dropped"):
            object.__setattr__(
                self, name, _count(getattr(self, name), name, minimum=0)
            )
        if self.observation_count > self.aligned_count:
            raise MacroReportError(
                f"relationship {self.subject_id}/{self.reference_id} reports a "
                f"window of {self.observation_count} observation(s) drawn from "
                f"{self.aligned_count} shared date(s); a window cannot use more "
                "observations than the two series share"
            )

        if self.comparability is not None and not isinstance(
            self.comparability, ComparabilityKey
        ):
            raise TypeError(
                "comparability must be a ComparabilityKey or None, got "
                f"{type(self.comparability).__name__}"
            )
        if self.not_comparable_detail is not None:
            object.__setattr__(
                self,
                "not_comparable_detail",
                _text(self.not_comparable_detail, "not_comparable_detail"),
            )
            if self.value is not None:
                raise MacroReportError(
                    f"relationship {self.subject_id}/{self.reference_id} states "
                    "a value and a reason the two sides are not comparable; a "
                    "refused comparison has no number"
                )

        measured = self.value is not None
        if measured:
            if self.window_start is None or self.window_end is None:
                raise MacroReportError(
                    f"relationship {self.subject_id}/{self.reference_id} produced "
                    "a value but names no window; a number over an unnamed window "
                    "is a number nobody can reconstruct"
                )
            start = _utc(self.window_start, "window_start")
            end = _utc(self.window_end, "window_end")
            if end < start:
                raise MacroReportError(
                    f"relationship {self.subject_id}/{self.reference_id} spans a "
                    f"window ending {end.isoformat()} before it starts "
                    f"{start.isoformat()}"
                )
            object.__setattr__(self, "window_start", start)
            object.__setattr__(self, "window_end", end)
        elif self.window_start is not None or self.window_end is not None:
            raise MacroReportError(
                f"relationship {self.subject_id}/{self.reference_id} states a "
                "window but produced no value; an unmeasured quantity spans "
                "nothing"
            )

    @property
    def is_measured(self) -> bool:
        return self.value is not None

    @property
    def is_refused(self) -> bool:
        """Whether this pair was never comparable, as opposed to not measurable."""
        return self.not_comparable_detail is not None


# -------------------------------------------------------------------- page ---


@dataclass(frozen=True, slots=True)
class MacroContextReport:
    """One frozen macro & cross-asset context, at one instant.

    **Every benchmark in the universe is accounted for exactly once** — in
    `readings`, in `unavailable`, or in the universe's own unsupported set. The
    constructor proves it, for the reason `MarketPulse` proves the same thing: a
    market that vanished between the stated scope and the page is an absence the
    page cannot report, which is precisely the failure this surface exists to
    prevent.

    **`as_of` is supplied, never read.** Nothing in this package touches a clock,
    so two runs over the same observations produce the same report — the property
    that makes the output testable, diffable and defensible.

    **There is no summary field.** No overall state, no count of markets "up", no
    regime and no score. A consumer wanting one must compute it from the facts
    and own the definition.
    """

    as_of: datetime
    universe: MarketUniverse
    levels: tuple[MacroLevel, ...]
    readings: tuple[MarketReading, ...]
    unavailable: tuple[MarketUnavailable, ...]
    rate_facts: tuple[RateFact, ...]
    relationships: tuple[CrossAssetRelationship, ...]
    horizons: tuple[Horizon, ...]
    relationship_reference: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", _utc(self.as_of, "as_of"))
        if not isinstance(self.universe, MarketUniverse):
            raise TypeError(
                f"universe must be a MarketUniverse, got "
                f"{type(self.universe).__name__}"
            )
        object.__setattr__(
            self, "levels", _tuple_of(self.levels, MacroLevel, "levels")
        )
        object.__setattr__(
            self, "readings", _tuple_of(self.readings, MarketReading, "readings")
        )
        object.__setattr__(
            self,
            "unavailable",
            _tuple_of(self.unavailable, MarketUnavailable, "unavailable"),
        )
        object.__setattr__(
            self, "rate_facts", _tuple_of(self.rate_facts, RateFact, "rate_facts")
        )
        object.__setattr__(
            self,
            "relationships",
            _tuple_of(
                self.relationships, CrossAssetRelationship, "relationships"
            ),
        )
        object.__setattr__(
            self, "horizons", _tuple_of(self.horizons, Horizon, "horizons")
        )

        expected = {entry.benchmark_id for entry in self.universe.supported}
        answered: set[str] = set()
        for entry in (*self.readings, *self.unavailable):
            if entry.benchmark_id in answered:
                raise MacroReportError(
                    f"{entry.benchmark_id} appears twice on one report; one "
                    "market has one reading or one reason, never both and never "
                    "two"
                )
            if entry.benchmark_id not in expected:
                raise MacroReportError(
                    f"{entry.benchmark_id} is not a supported member of universe "
                    f"{self.universe.name!r}; a report may not describe a market "
                    "its own stated scope does not contain"
                )
            answered.add(entry.benchmark_id)
        missing = sorted(expected - answered)
        if missing:
            raise MacroReportError(
                f"universe {self.universe.name!r} names {missing} as supported "
                "but the report holds neither a reading nor a reason for them; a "
                "market that disappears between the scope and the page is an "
                "absence the page cannot disclose"
            )

        for level in self.levels:
            if level.benchmark_id not in answered:
                raise MacroReportError(
                    f"a level is reported for {level.benchmark_id}, which this "
                    "report does not read; a number with no reading behind it "
                    "has no provenance"
                )
            if level.observed_at > self.as_of:
                raise MacroReportError(
                    f"the level for {level.benchmark_id} is observed "
                    f"{level.observed_at.isoformat()}, after the instant this "
                    f"report describes ({self.as_of.isoformat()}); a reading from "
                    "the future is a clock problem, not a reading"
                )
        for reading in self.readings:
            if reading.last_bar_open > self.as_of:
                raise MacroReportError(
                    f"the reading for {reading.benchmark_id} rests on an "
                    f"observation dated {reading.last_bar_open.isoformat()}, "
                    f"after the instant this report describes "
                    f"({self.as_of.isoformat()}); a reading from the future is a "
                    "clock problem, not a reading"
                )
        for fact in self.rate_facts:
            if fact.benchmark_id not in answered:
                raise MacroReportError(
                    f"a rate fact is reported for {fact.benchmark_id}, which "
                    "this report does not read"
                )

        seen_horizons: set[str] = set()
        for horizon in self.horizons:
            if horizon.horizon_id in seen_horizons:
                raise MacroReportError(
                    f"horizon {horizon.horizon_id!r} is declared twice; one "
                    "window has one definition"
                )
            seen_horizons.add(horizon.horizon_id)

        if self.relationship_reference is not None:
            reference = _text(
                self.relationship_reference, "relationship_reference"
            )
            object.__setattr__(self, "relationship_reference", reference)
        elif self.relationships:
            raise MacroReportError(
                "relationships are reported with no reference market named; a "
                "correlation against an unnamed series is not interpretable"
            )

    # -- projections, computed and never stored ------------------------------

    @property
    def read_count(self) -> int:
        return len(self.readings)

    @property
    def unsupported_count(self) -> int:
        """How many macro markets no source is configured for at all."""
        return len(self.universe.unsupported)

    @property
    def is_empty(self) -> bool:
        """No macro market could be read. **Not** the same as a quiet market."""
        return not self.readings

    def level_for(self, benchmark_id: str) -> MacroLevel | None:
        wanted = _text(benchmark_id, "benchmark_id")
        for level in self.levels:
            if level.benchmark_id == wanted:
                return level
        return None

    def reading_for(self, benchmark_id: str) -> MarketReading | None:
        wanted = _text(benchmark_id, "benchmark_id")
        for reading in self.readings:
            if reading.benchmark_id == wanted:
                return reading
        return None

    def rate_fact_for(self, benchmark_id: str) -> RateFact | None:
        wanted = _text(benchmark_id, "benchmark_id")
        for fact in self.rate_facts:
            if fact.benchmark_id == wanted:
                return fact
        return None

    def freshness_of(self, benchmark_id: str) -> FreshnessState | None:
        """One market's freshness at this report's instant, or `None` if unread.

        Delegates to `MarketReading.freshness_at`, so the macro page and the
        pulse page cannot answer this question differently for one reading.
        """
        reading = self.reading_for(benchmark_id)
        if reading is None:
            return None
        return reading.freshness_at(self.as_of)

    def readings_behind_schedule(self) -> tuple[MarketReading, ...]:
        """Every reading older than its own source's schedule explains."""
        return tuple(
            reading
            for reading in self.readings
            if reading.freshness_at(self.as_of) is FreshnessState.BEHIND_SCHEDULE
        )
