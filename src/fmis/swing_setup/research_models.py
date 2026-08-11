"""Value types for the corrected research harness (Milestone BC).

Milestone BB found two research-validity defects in the AV–BA chain, and both
are shapes-of-data problems before they are algorithm problems:

1. **The research window meant the wrong thing.** AV fetched exactly the
   requested window and called all of it the measurement period. The
   context-role weekly EMA(50) then consumed the first ~350 days of it, so a
   "400-day backtest" produced ~43 calendar days in which the policy was even
   *capable* of reaching `CONFIRMED`. Nothing in AV's models could express the
   difference, so nothing caught it.
2. **A counterfactual was emulated by deletion.** BA answered "what would a
   stricter confirmation-age bound have produced?" by removing already-observed
   stale confirmations. That is not the counterfactual: under a stricter bound
   the candidate survives as `CANDIDATE` and can confirm later on a *different*
   break, at a different bar, price, stop and target.

Every type here exists to make one of those two mistakes hard to make again.
`ResearchWindow` carries four boundaries rather than two, so "the period we
measured" can never silently mean "the data we fetched". `ResearchPolicyVariant`
names a counterfactual explicitly and carries the `policy_id` its results will
be stamped with, so a research number can never be filed as a production one.

**Nothing here computes a market quantity.** These are windows, boundaries,
labels and counts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final

from fmis.swing_setup.backtest_models import (
    BacktestError,
    DataBoundary,
    HistoricalObservation,
    SetupOutcome,
)
from fmis.swing_setup.models import SetupState
from fmis.swing_setup.policy import (
    CONFIRMATION_LOOKBACK_BARS,
    SETUP_POLICY_ID,
    research_policy_id,
)

__all__ = [
    "RESEARCH_SCHEMA_VERSION",
    "ResearchError",
    "INTERVAL_DURATIONS",
    "interval_duration",
    "WarmupComponent",
    "RoleWarmup",
    "WarmupRequirement",
    "ResearchWindow",
    "TemporalSegment",
    "ResearchPolicyVariant",
    "PRODUCTION_BASELINE_VARIANT",
    "SeriesAvailability",
    "AvailabilityReport",
    "ResearchObservation",
    "ResearchBacktestRun",
    "ConfirmationRecord",
    "VariantComparison",
    "PostFilterComparison",
]

#: Bumped when the serialized shape of a research run changes in a way a
#: consumer must notice. Separate from `BACKTEST_SCHEMA_VERSION`: an AV run and
#: a BC run are different artifacts and must never be compared field by field
#: on the assumption that they are the same one.
RESEARCH_SCHEMA_VERSION: Final[int] = 1


class ResearchError(BacktestError):
    """Base class for every research-harness failure.

    Subclasses `BacktestError` so a caller already catching backtest failures
    keeps working, while a caller that wants to distinguish a research-window
    problem from an ordinary fetch failure can.
    """


#: Exact durations of the fixed-length provider intervals. ``"1M"`` is
#: deliberately absent: a calendar month is not a fixed duration, and a
#: warm-up prefix derived by multiplying a bar count by an *approximate* month
#: would be a silent truncation of exactly the kind this milestone exists to
#: remove. Asking for it raises rather than guessing 30 days.
INTERVAL_DURATIONS: Final[Mapping[str, timedelta]] = MappingProxyType(
    {
        "1s": timedelta(seconds=1),
        "1m": timedelta(minutes=1),
        "3m": timedelta(minutes=3),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "30m": timedelta(minutes=30),
        "1h": timedelta(hours=1),
        "2h": timedelta(hours=2),
        "4h": timedelta(hours=4),
        "6h": timedelta(hours=6),
        "8h": timedelta(hours=8),
        "12h": timedelta(hours=12),
        "1d": timedelta(days=1),
        "3d": timedelta(days=3),
        "1w": timedelta(weeks=1),
    }
)


def interval_duration(interval: str) -> timedelta:
    """The exact wall-clock length of one candle at ``interval``.

    Raises:
        ResearchError: ``interval`` is not a fixed-length provider interval.
            ``"1M"`` is rejected by name — see `INTERVAL_DURATIONS`.
    """
    try:
        return INTERVAL_DURATIONS[interval]
    except (KeyError, TypeError):
        raise ResearchError(
            f"interval {interval!r} has no exact fixed duration; a warm-up "
            "prefix cannot be derived from it. Supported: "
            f"{', '.join(sorted(INTERVAL_DURATIONS))}"
        ) from None


@dataclass(frozen=True, slots=True)
class WarmupComponent:
    """One named production dependency contributing to a role's warm-up requirement.

    Recorded individually, and rendered individually, because the whole failure
    BB found was a warm-up requirement nobody had written down. A single number
    with no breakdown is exactly as auditable as no number at all.
    """

    name: str
    bars: int
    source: str

    def __post_init__(self) -> None:
        for attribute in ("name", "source"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ResearchError(f"{attribute} must be a non-empty str")
        if isinstance(self.bars, bool) or not isinstance(self.bars, int):
            raise TypeError("bars must be an int")
        if self.bars < 0:
            raise ResearchError("bars cannot be negative")


@dataclass(frozen=True, slots=True)
class RoleWarmup:
    """How many closed candles one role needs before the measurement window opens.

    ``required_bars`` is the maximum over ``components`` — a role is warm only
    when *every* dependency that reads it is warm, so the binding one wins.
    ``duration`` is that count scaled by the role's own interval, which is why
    the same bar count costs 200 days at ``1d`` and 200 weeks at ``1w``.
    """

    role: str
    interval: str
    required_bars: int
    duration: timedelta
    components: tuple[WarmupComponent, ...]

    def __post_init__(self) -> None:
        for attribute in ("role", "interval"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ResearchError(f"{attribute} must be a non-empty str")
        if isinstance(self.required_bars, bool) or not isinstance(self.required_bars, int):
            raise TypeError("required_bars must be an int")
        if self.required_bars <= 0:
            raise ResearchError("required_bars must be positive")
        if not isinstance(self.duration, timedelta):
            raise TypeError("duration must be a timedelta")
        if not isinstance(self.components, tuple) or not self.components:
            raise ResearchError("components must be a non-empty tuple of WarmupComponent")
        for item in self.components:
            if not isinstance(item, WarmupComponent):
                raise TypeError("every components entry must be a WarmupComponent")
        binding = max(item.bars for item in self.components)
        if self.required_bars != binding:
            raise ResearchError(
                f"required_bars ({self.required_bars}) must equal the largest "
                f"component ({binding}); a role is warm only when every "
                "dependency reading it is warm"
            )
        if self.duration != self.required_bars * interval_duration(self.interval):
            raise ResearchError(
                "duration must equal required_bars scaled by the role's own "
                "interval; a warm-up prefix measured in the wrong unit is the "
                "defect this milestone exists to remove"
            )


@dataclass(frozen=True, slots=True)
class WarmupRequirement:
    """Every role's warm-up requirement, and the single prefix that satisfies them all.

    ``prefix`` is the longest of the per-role durations: fetching that much
    history before ``measurement_start`` leaves every role warm at the first
    measured instant. It is derived, never assumed — `research_warmup.derive_warmup`
    reads each contributing number out of the production object that owns it.
    """

    by_role: tuple[RoleWarmup, ...]
    prefix: timedelta

    def __post_init__(self) -> None:
        if not isinstance(self.by_role, tuple) or not self.by_role:
            raise ResearchError("by_role must be a non-empty tuple of RoleWarmup")
        for item in self.by_role:
            if not isinstance(item, RoleWarmup):
                raise TypeError("every by_role entry must be a RoleWarmup")
        if not isinstance(self.prefix, timedelta):
            raise TypeError("prefix must be a timedelta")
        longest = max(item.duration for item in self.by_role)
        if self.prefix != longest:
            raise ResearchError(
                f"prefix ({self.prefix}) must equal the longest per-role "
                f"warm-up ({longest})"
            )

    def for_interval(self, interval: str) -> timedelta:
        """The warm-up prefix one interval needs, for a per-interval fetch start.

        Fetching every interval from the *global* prefix would pull ~250 weeks
        of 4H candles to satisfy a weekly requirement — tens of thousands of
        rows that no execution-role decision can ever read. Each interval is
        fetched from its own requirement instead, which is both cheaper and
        exactly as warm.
        """
        matching = [item.duration for item in self.by_role if item.interval == interval]
        if not matching:
            raise ResearchError(f"no role uses interval {interval!r}")
        return max(matching)


@dataclass(frozen=True, slots=True)
class ResearchWindow:
    """The four boundaries a historical research run must keep apart.

    ::

        warmup_start        measurement_start   measurement_end   outcome_tail_end
             |───── warm-up ──────|──── measured ─────|───── tail ─────|
             indicators warm here  observations count  outcomes resolve
             nothing is counted    setups form here    no setup forms

    **Measurement is half-open**: an instant ``T`` is measured exactly when
    ``measurement_start <= T < measurement_end``. Half-open rather than closed
    so chronological segments tile the window without a shared endpoint that
    would be counted twice, and so ``measurement_end`` names one unambiguous
    instant — the first instant that is *not* measured.

    Candles in the warm-up prefix legitimately change later state: that is what
    a warm-up is for. Candles in the outcome tail may resolve an already-frozen
    setup and may never create one. Both properties are test-enforced
    (`tests/test_swing_setup_research.py`).
    """

    warmup_start: datetime
    measurement_start: datetime
    measurement_end: datetime
    outcome_tail_end: datetime

    def __post_init__(self) -> None:
        for attribute in (
            "warmup_start", "measurement_start", "measurement_end", "outcome_tail_end",
        ):
            value = getattr(self, attribute)
            if not isinstance(value, datetime):
                raise TypeError(f"{attribute} must be a datetime")
            if value.utcoffset() is None:
                raise ResearchError(f"{attribute} must be timezone-aware (ADR-0001)")
        if self.warmup_start >= self.measurement_start:
            raise ResearchError(
                "warmup_start must be strictly before measurement_start; a "
                "window with no warm-up prefix is the AV defect this type exists "
                "to make unrepresentable"
            )
        if self.measurement_start >= self.measurement_end:
            raise ResearchError("measurement_start must be strictly before measurement_end")
        if self.outcome_tail_end < self.measurement_end:
            raise ResearchError("outcome_tail_end cannot precede measurement_end")

    @property
    def warmup_duration(self) -> timedelta:
        return self.measurement_start - self.warmup_start

    @property
    def measurement_duration(self) -> timedelta:
        return self.measurement_end - self.measurement_start

    @property
    def tail_duration(self) -> timedelta:
        return self.outcome_tail_end - self.measurement_end

    def is_measured(self, instant: datetime) -> bool:
        """``True`` exactly when an analysis instant falls in the measured half-open window."""
        return self.measurement_start <= instant < self.measurement_end

    def is_warmup(self, instant: datetime) -> bool:
        """``True`` for an instant that may initialize state but must not be counted."""
        return instant < self.measurement_start

    def is_tail(self, instant: datetime) -> bool:
        """``True`` for an instant that may resolve an outcome but must not form a setup."""
        return instant >= self.measurement_end


@dataclass(frozen=True, slots=True)
class TemporalSegment:
    """One chronological slice of the measurement window, fixed before any result is seen.

    Half-open ``[start, end)``, matching `ResearchWindow`, so a set of segments
    tiles the measurement window exactly and every measured instant belongs to
    exactly one. Boundaries are calendar-derived — never chosen by looking at
    where the outcomes fell, which would be the subgroup-shopping this whole
    milestone exists to make impossible.
    """

    label: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ResearchError("label must be a non-empty str")
        for attribute in ("start", "end"):
            value = getattr(self, attribute)
            if not isinstance(value, datetime):
                raise TypeError(f"{attribute} must be a datetime")
            if value.utcoffset() is None:
                raise ResearchError(f"{attribute} must be timezone-aware (ADR-0001)")
        if self.start >= self.end:
            raise ResearchError("start must be strictly before end")

    def contains(self, instant: datetime) -> bool:
        return self.start <= instant < self.end


@dataclass(frozen=True, slots=True)
class ResearchPolicyVariant:
    """One explicitly named policy under which history is replayed. Research only.

    ``max_confirmation_age`` of ``None`` means "apply the production constant",
    and is the only variant whose results are the production policy's own. Any
    other value is a counterfactual: it is forwarded to
    `fmis.swing_setup.policy.evaluate_setup`'s ``research_confirmation_max_age``
    parameter, which stamps `research_policy_id` on every assessment it
    produces.

    **This type cannot change production behaviour.** It holds no mutable
    state, is never read by `evaluate_setup` (which takes an ``int``, not this
    object), and is imported by nothing on the live path. The only thing it can
    do is describe a run.
    """

    variant_id: str
    max_confirmation_age: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.variant_id, str) or not self.variant_id.strip():
            raise ResearchError("variant_id must be a non-empty str")
        if self.max_confirmation_age is not None:
            if isinstance(self.max_confirmation_age, bool) or not isinstance(
                self.max_confirmation_age, int
            ):
                raise TypeError("max_confirmation_age must be an int or None")
            if self.max_confirmation_age < 0:
                raise ResearchError("max_confirmation_age cannot be negative")

    @property
    def is_production_baseline(self) -> bool:
        """``True`` only for the variant that applies the unmodified production constant."""
        return self.max_confirmation_age is None

    @property
    def effective_max_age(self) -> int:
        """The staleness bound actually applied, production constant included."""
        return (
            CONFIRMATION_LOOKBACK_BARS
            if self.max_confirmation_age is None
            else self.max_confirmation_age
        )

    @property
    def policy_id(self) -> str:
        """The ``policy_id`` every assessment under this variant will carry."""
        return (
            SETUP_POLICY_ID
            if self.max_confirmation_age is None
            else research_policy_id(self.max_confirmation_age)
        )

    @classmethod
    def counterfactual(cls, max_confirmation_age: int) -> ResearchPolicyVariant:
        """A named counterfactual variant at one staleness bound."""
        return cls(
            variant_id=f"max_age_{max_confirmation_age}",
            max_confirmation_age=max_confirmation_age,
        )


#: The one variant that is not a counterfactual: production's own constant,
#: applied through the production code path with no override supplied.
PRODUCTION_BASELINE_VARIANT: Final[ResearchPolicyVariant] = ResearchPolicyVariant(
    variant_id="production_baseline", max_confirmation_age=None
)


@dataclass(frozen=True, slots=True)
class SeriesAvailability:
    """What history the provider actually holds for one (symbol, interval), measured.

    ``satisfies_window`` answers the only question that matters before a run:
    does this series reach back far enough that the requested measurement
    window opens on a fully warm role? ``shortfall`` states by how much it does
    not, so an insufficiency is a number rather than an adjective.

    ``implied_candle_count`` is named for what it is: the count the first and
    last candle *imply* at this interval, which is an upper bound. Establishing
    the true count would mean paging the whole series, and the probe exists
    precisely so a run does not have to. A provider gap would make the real
    count lower — never the reach-back date, which is what the satisfiability
    decision actually rests on.
    """

    symbol: str
    interval: str
    earliest_open: datetime | None
    latest_open: datetime | None
    implied_candle_count: int
    required_from: datetime
    satisfies_window: bool
    shortfall: timedelta

    def __post_init__(self) -> None:
        for attribute in ("symbol", "interval"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ResearchError(f"{attribute} must be a non-empty str")
        for attribute in ("earliest_open", "latest_open"):
            value = getattr(self, attribute)
            if value is not None and not isinstance(value, datetime):
                raise TypeError(f"{attribute} must be a datetime or None")
        if (self.earliest_open is None) != (self.latest_open is None):
            raise ResearchError("earliest_open and latest_open must both be set or both None")
        if not isinstance(self.required_from, datetime):
            raise TypeError("required_from must be a datetime")
        if isinstance(self.implied_candle_count, bool) or not isinstance(
            self.implied_candle_count, int
        ):
            raise TypeError("implied_candle_count must be an int")
        if self.implied_candle_count < 0:
            raise ResearchError("implied_candle_count cannot be negative")
        if not isinstance(self.satisfies_window, bool):
            raise TypeError("satisfies_window must be a bool")
        if not isinstance(self.shortfall, timedelta):
            raise TypeError("shortfall must be a timedelta")
        if self.satisfies_window != (self.shortfall == timedelta(0)):
            raise ResearchError(
                "satisfies_window is True exactly when shortfall is zero; the "
                "two fields must never disagree"
            )


@dataclass(frozen=True, slots=True)
class AvailabilityReport:
    """Measured provider history for every (symbol, interval) a run needs.

    ``is_satisfiable`` is the run's own gate: a research run whose window is not
    satisfiable returns this report rather than quietly measuring a shorter
    period and reporting it under the requested dates — which is precisely what
    made a 400-day claim mean 43 days.
    """

    series: tuple[SeriesAvailability, ...]
    probed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.series, tuple):
            raise TypeError("series must be a tuple of SeriesAvailability")
        for item in self.series:
            if not isinstance(item, SeriesAvailability):
                raise TypeError("every series entry must be a SeriesAvailability")
        if not isinstance(self.probed_at, datetime):
            raise TypeError("probed_at must be a datetime")

    @property
    def is_satisfiable(self) -> bool:
        return all(item.satisfies_window for item in self.series)

    @property
    def unsatisfied(self) -> tuple[SeriesAvailability, ...]:
        return tuple(item for item in self.series if not item.satisfies_window)

    @property
    def worst_shortfall(self) -> timedelta:
        return max((item.shortfall for item in self.series), default=timedelta(0))


@dataclass(frozen=True, slots=True)
class ResearchObservation:
    """One historical observation, plus the bookkeeping BC needs and AV did not carry.

    The AV `HistoricalObservation` is held **whole and unmodified** rather than
    re-specified: every field on it means exactly what AV's own record means,
    and an AV consumer can read `observation` without a translation layer.

    The four fields beside it are the ones this milestone found missing:

    * ``in_measurement`` — whether this observation counts toward any reported
      statistic. Warm-up and identity-priming observations carry ``False`` and
      are excluded from every denominator.
    * ``opportunity_key`` — cross-variant lineage (see
      `fmis.swing_setup.research_identity`). AV's ``setup_id`` cannot serve:
      it is built from the level's *window-relative* bar index, which shifts by
      one every bar, so it is unstable within a single run and meaningless
      across two.
    * ``confirmation_break_age_bars`` — how many bars old the confirming break
      was. BB noted this was never persisted, which is why a real counterfactual
      could not be checked against a post-filtered one.
    * ``segment`` — which predefined chronological segment this instant fell in.

    ``is_first_confirmation`` is recorded rather than re-derived because the
    distinction it draws cannot be recovered afterwards: an opportunity whose
    *first* confirmation happened during the priming window has measured
    confirmed bars but was not a decision this window observed being made, and
    counting its first *measured* confirmed bar would silently readmit a
    decision the window boundary excluded.
    """

    observation: HistoricalObservation
    in_measurement: bool
    opportunity_key: str | None
    is_new_opportunity: bool
    is_first_confirmation: bool
    confirmation_break_age_bars: int | None
    segment: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.observation, HistoricalObservation):
            raise TypeError("observation must be a HistoricalObservation")
        for attribute in ("in_measurement", "is_new_opportunity", "is_first_confirmation"):
            if not isinstance(getattr(self, attribute), bool):
                raise TypeError(f"{attribute} must be a bool")
        if self.opportunity_key is not None and (
            not isinstance(self.opportunity_key, str) or not self.opportunity_key.strip()
        ):
            raise ResearchError("opportunity_key must be a non-empty str or None")
        if (self.opportunity_key is None) != (self.observation.direction is None):
            raise ResearchError(
                "opportunity_key is None if and only if the observation has no "
                "direction, matching setup_id's own invariant"
            )
        if self.is_new_opportunity and self.opportunity_key is None:
            raise ResearchError("is_new_opportunity requires an opportunity_key")
        if self.is_first_confirmation and self.observation.status is not SetupState.CONFIRMED:
            raise ResearchError(
                "is_first_confirmation may only be set on a CONFIRMED observation"
            )
        if self.confirmation_break_age_bars is not None:
            if isinstance(self.confirmation_break_age_bars, bool) or not isinstance(
                self.confirmation_break_age_bars, int
            ):
                raise TypeError("confirmation_break_age_bars must be an int or None")
            if self.confirmation_break_age_bars < 0:
                raise ResearchError("confirmation_break_age_bars cannot be negative")
        if self.segment is not None and (
            not isinstance(self.segment, str) or not self.segment.strip()
        ):
            raise ResearchError("segment must be a non-empty str or None")
        if self.in_measurement and self.segment is None:
            raise ResearchError(
                "a measured observation must fall in exactly one predefined "
                "segment; segments tile the measurement window by construction"
            )
        if not self.in_measurement and self.segment is not None:
            raise ResearchError("an unmeasured observation cannot belong to a segment")

    @property
    def symbol(self) -> str:
        return self.observation.symbol

    @property
    def as_of(self) -> datetime:
        return self.observation.as_of

    @property
    def status(self):  # -> SetupState; annotated loosely to avoid a re-export
        return self.observation.status

    @property
    def direction(self):  # -> Direction | None
        return self.observation.direction


@dataclass(frozen=True, slots=True)
class ResearchBacktestRun:
    """One complete replay of history under exactly one `ResearchPolicyVariant`.

    Distinct from `BacktestRun` on purpose. An AV run and a BC run answer
    different questions over different windows, and giving them one type would
    invite exactly the comparison BB warns against — reading a corrected number
    as a regression against an under-warmed one.

    Two runs over the same fetched dataset, the same window and the same variant
    are equal, ``created_at`` aside.
    """

    schema_version: int
    created_at: datetime
    symbols: tuple[str, ...]
    timeframes: Mapping[str, str]
    window: ResearchWindow
    warmup: WarmupRequirement
    segments: tuple[TemporalSegment, ...]
    availability: AvailabilityReport
    variant: ResearchPolicyVariant
    evaluation_window_bars: int
    identity_priming_bars: int
    data_boundaries: tuple[DataBoundary, ...]
    context_policy_id: str
    observations: tuple[ResearchObservation, ...]
    outcomes: tuple[SetupOutcome, ...]
    limitations: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("schema_version must be an int")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if not isinstance(self.symbols, tuple) or not self.symbols:
            raise ResearchError("symbols must be a non-empty tuple of str")
        for symbol in self.symbols:
            if not isinstance(symbol, str) or not symbol.strip():
                raise ResearchError("every symbol must be a non-empty str")
        if not isinstance(self.timeframes, Mapping) or not self.timeframes:
            raise ResearchError("timeframes must be a non-empty mapping")
        if not isinstance(self.window, ResearchWindow):
            raise TypeError("window must be a ResearchWindow")
        if not isinstance(self.warmup, WarmupRequirement):
            raise TypeError("warmup must be a WarmupRequirement")
        if not isinstance(self.segments, tuple) or not self.segments:
            raise ResearchError("segments must be a non-empty tuple of TemporalSegment")
        for item in self.segments:
            if not isinstance(item, TemporalSegment):
                raise TypeError("every segments entry must be a TemporalSegment")
        if not isinstance(self.availability, AvailabilityReport):
            raise TypeError("availability must be an AvailabilityReport")
        if not isinstance(self.variant, ResearchPolicyVariant):
            raise TypeError("variant must be a ResearchPolicyVariant")
        for attribute in ("evaluation_window_bars", "identity_priming_bars"):
            value = getattr(self, attribute)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{attribute} must be an int")
        if self.evaluation_window_bars <= 0:
            raise ResearchError("evaluation_window_bars must be positive")
        if self.identity_priming_bars < 0:
            raise ResearchError("identity_priming_bars cannot be negative")
        if not isinstance(self.data_boundaries, tuple):
            raise TypeError("data_boundaries must be a tuple of DataBoundary")
        for item in self.data_boundaries:
            if not isinstance(item, DataBoundary):
                raise TypeError("every data_boundaries entry must be a DataBoundary")
        if not isinstance(self.context_policy_id, str) or not self.context_policy_id.strip():
            raise ResearchError("context_policy_id must be a non-empty str")
        if not isinstance(self.observations, tuple):
            raise TypeError("observations must be a tuple of ResearchObservation")
        for item in self.observations:
            if not isinstance(item, ResearchObservation):
                raise TypeError("every observations entry must be a ResearchObservation")
        if not isinstance(self.outcomes, tuple):
            raise TypeError("outcomes must be a tuple of SetupOutcome")
        for item in self.outcomes:
            if not isinstance(item, SetupOutcome):
                raise TypeError("every outcomes entry must be a SetupOutcome")
        if not isinstance(self.limitations, tuple):
            raise TypeError("limitations must be a tuple of str")
        for item in self.limitations:
            if not isinstance(item, str) or not item.strip():
                raise ResearchError("every limitations entry must be a non-empty str")
        object.__setattr__(self, "timeframes", MappingProxyType(dict(self.timeframes)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def measured(self) -> tuple[ResearchObservation, ...]:
        """Only the observations that count. Every reported statistic starts here."""
        return tuple(item for item in self.observations if item.in_measurement)

    @property
    def policy_id(self) -> str:
        """The ``policy_id`` every assessment in this run carries."""
        return self.variant.policy_id


@dataclass(frozen=True, slots=True)
class ConfirmationRecord:
    """One first confirmation of one opportunity, reduced to what a comparison needs.

    The identity is ``(symbol, opportunity_key)``; the payload is when it
    confirmed and on what geometry. Two variants' records join on the identity,
    which is what lets a reader answer "same opportunity, different confirmation
    time?" rather than only "how many confirmations were there?".
    """

    symbol: str
    opportunity_key: str
    confirmed_at: datetime
    direction: str
    confirmation_break_age_bars: int | None
    reference_price: float | None
    risk_reward_ratio: float | None
    segment: str | None

    def __post_init__(self) -> None:
        for attribute in ("symbol", "opportunity_key", "direction"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ResearchError(f"{attribute} must be a non-empty str")
        if not isinstance(self.confirmed_at, datetime):
            raise TypeError("confirmed_at must be a datetime")

    @property
    def identity(self) -> tuple[str, str]:
        return (self.symbol, self.opportunity_key)


@dataclass(frozen=True, slots=True)
class VariantComparison:
    """How one variant's confirmed population differs from the baseline's.

    Answers, by counts and by named examples, the five lineage questions the
    milestone brief asks: same opportunity at a different time, opportunity
    gone, candidate confirming later, confirmation lost entirely, confirmation
    created by a later break. These are **differences**, never a verdict: no
    field here says one variant is better.
    """

    baseline_variant_id: str
    variant_id: str
    baseline_confirmations: int
    variant_confirmations: int
    unchanged: int
    shifted_later: int
    shifted_earlier: int
    removed: int
    added: int
    shifted_examples: tuple[tuple[str, str, datetime, datetime], ...] = ()

    def __post_init__(self) -> None:
        for attribute in ("baseline_variant_id", "variant_id"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ResearchError(f"{attribute} must be a non-empty str")
        for attribute in (
            "baseline_confirmations", "variant_confirmations", "unchanged",
            "shifted_later", "shifted_earlier", "removed", "added",
        ):
            value = getattr(self, attribute)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{attribute} must be an int")
            if value < 0:
                raise ResearchError(f"{attribute} cannot be negative")
        shifted = self.shifted_later + self.shifted_earlier
        if self.unchanged + shifted + self.removed != self.baseline_confirmations:
            raise ResearchError(
                "unchanged + shifted + removed must reconcile to "
                "baseline_confirmations; every baseline confirmation is exactly "
                "one of kept, moved, or lost"
            )
        if self.unchanged + shifted + self.added != self.variant_confirmations:
            raise ResearchError(
                "unchanged + shifted + added must reconcile to "
                "variant_confirmations; every variant confirmation is exactly "
                "one of kept, moved, or new"
            )


@dataclass(frozen=True, slots=True)
class PostFilterComparison:
    """BA's post-filter emulation set beside the true replay, at one staleness bound.

    This is BB finding #2, quantified. ``post_filter_kept`` is what BA's method
    produces: baseline confirmations whose recorded break age already satisfied
    the bound. ``replay_confirmations`` is what actually replaying the policy
    under that bound produces. ``only_in_replay`` is the population BA's method
    is structurally incapable of seeing — confirmations that exist *because* a
    stricter bound deferred a candidate until a later, fresher break.
    """

    max_confirmation_age: int
    baseline_confirmations: int
    post_filter_kept: int
    replay_confirmations: int
    in_both: int
    only_in_post_filter: int
    only_in_replay: int
    post_filter_target_first: int
    post_filter_stop_first: int
    replay_target_first: int
    replay_stop_first: int

    def __post_init__(self) -> None:
        for attribute in (
            "max_confirmation_age", "baseline_confirmations", "post_filter_kept",
            "replay_confirmations", "in_both", "only_in_post_filter", "only_in_replay",
            "post_filter_target_first", "post_filter_stop_first",
            "replay_target_first", "replay_stop_first",
        ):
            value = getattr(self, attribute)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{attribute} must be an int")
            if value < 0:
                raise ResearchError(f"{attribute} cannot be negative")
        if self.in_both + self.only_in_post_filter != self.post_filter_kept:
            raise ResearchError(
                "in_both + only_in_post_filter must reconcile to post_filter_kept"
            )
        if self.in_both + self.only_in_replay != self.replay_confirmations:
            raise ResearchError(
                "in_both + only_in_replay must reconcile to replay_confirmations"
            )

    @property
    def agreement_rate(self) -> float | None:
        """Fraction of the union both methods agree on. ``None`` when both are empty."""
        union = self.in_both + self.only_in_post_filter + self.only_in_replay
        if union == 0:
            return None
        return self.in_both / union
