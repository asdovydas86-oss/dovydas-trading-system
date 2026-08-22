"""The shapes a market pulse is made of, and every rule they enforce.

This module defines *what can be said* about a market on an orientation page,
and nothing about how to say it or how to obtain it. It computes no market
quantity, reads no clock, and imports no provider, no engine and no surface.

**The organizing rule is that absence is a value, never a gap.** Every type
that can fail to produce a number carries the reason it could not, and the
constructor refuses to hold both a number and a reason, or neither. A page
assembled from these types cannot print a blank where a measurement should be,
because there is no way to build one.

**Five distinct absences are representable, and they are not interchangeable:**

  * *unsupported* — `Benchmark.unsupported_reason`: no provider is configured
    for this market at all. DXY is not missing today; it is not wired up.
  * *unavailable* — `MarketUnavailable`: a configured provider was asked and
    the request failed, with the provider's own words carried through.
  * *insufficient window* — `HorizonMove.unavailable_reason`: the market
    answered, but with fewer closed bars than the horizon names.
  * *mathematically undefined* — the same field, carrying the Relative Value
    Engine's own `UndefinedReason`. A zero denominator is not a zero move.
  * *not comparable* — `HorizonRanking.excluded` and
    `CoMovement.unavailable_reason`: the number exists and the comparison does
    not, because the two sides are quoted in different units or measured over
    different bars.

A zero move is none of those. It is `value == 0.0` with no reason attached, and
that distinction is the whole reason these types are shaped this way.

**No score exists here, and none can be added without deleting a docstring.**
`HorizonRanking` carries `ordering_quantity` — the name of the single measured
quantity that produced the order — and a ranking is constructed from exactly
one horizon's moves. There is no field a second quantity could enter through,
no weight, no total and no rank number. See `fmis.market_pulse.pulse` for the
ordering rule itself.

**Directional and interpretive vocabulary is absent by construction.** Nothing
here is named or valued `bullish`, `bearish`, `risk_on`, `risk_off`, `strong`,
`weak`, `high` or `elevated`. A move is a signed number over a named window; a
volatility reading is a number the repository has no baseline to classify, and
`VOLATILITY_CLASSIFICATION_NOTE` is what the page prints instead of a label.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

__all__ = [
    "MarketPulseError",
    "PulseUniverseError",
    "MarketCategory",
    "TradingSchedule",
    "ProviderInstrument",
    "Benchmark",
    "MarketUniverse",
    "Horizon",
    "HorizonMove",
    "VolatilityReading",
    "MarketReading",
    "MarketUnavailable",
    "RankedMove",
    "HorizonRanking",
    "CoMovement",
    "MarketPulse",
    "SCHEDULE_LIMITATION",
    "VOLATILITY_CLASSIFICATION_NOTE",
    "CO_MOVEMENT_CAVEAT",
    "PULSE_ORIENTATION_NOTE",
]

_ZERO = timedelta(0)


class MarketPulseError(Exception):
    """Base class for every failure raised by this package."""


class PulseUniverseError(MarketPulseError, ValueError):
    """A market universe is not a set of distinct, resolvable markets.

    A distinct type because the caller's correct response differs from every
    other failure here: a duplicate benchmark id or two markets sharing one
    provider instrument is a **configuration** defect that no amount of retrying
    or waiting fixes, and it must fail loudly at construction rather than
    produce a page that silently shows one market twice.
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

    Restated here rather than imported from `fmis.data._timeutils`, for the
    reason `fmis.marks.models` records for the identical helper: reaching into
    another package's private module is a coupling that survives until the day
    that module moves, and the rule is three lines.
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


def _exactly_one(
    value: float | None, reason: str | None, *, subject: str
) -> tuple[float | None, str | None]:
    """A measurement is a number **or** a stated reason it is not — never both.

    The load-bearing check of this module. Permitting both would let a page show
    a figure beside the sentence explaining why there is no figure; permitting
    neither would put a blank on an orientation page, which reads as *"nothing
    is happening"* rather than *"nothing was measured"*.
    """
    if value is None and reason is None:
        raise ValueError(
            f"{subject} has neither a value nor a reason; an unmeasured "
            "quantity is stated, never left blank"
        )
    if value is not None and reason is not None:
        raise ValueError(
            f"{subject} carries both a value and the reason it has none; one "
            "measurement has one outcome"
        )
    if value is None:
        return None, _text(reason, f"{subject} reason")
    return _finite(value, f"{subject} value"), None


def _window(
    first: Any, last: Any, *, subject: str, measured: bool
) -> tuple[datetime | None, datetime | None]:
    """The bar-open instants a measurement actually spanned.

    Required whenever a value exists — a number over an unnamed window is a
    number nobody can reconstruct — and permitted to be absent only when the
    measurement itself is absent, because a failed window has no span.
    """
    if not measured:
        if first is None and last is None:
            return None, None
        raise ValueError(
            f"{subject} states a window but produced no value; an unmeasured "
            "quantity spans nothing"
        )
    if first is None or last is None:
        raise ValueError(
            f"{subject} produced a value but names no window; a number over an "
            "unnamed window is a number nobody can reconstruct"
        )
    start = _utc(first, f"{subject} window start")
    end = _utc(last, f"{subject} window end")
    if end < start:
        raise ValueError(
            f"{subject} window ends {end.isoformat()} before it starts "
            f"{start.isoformat()}"
        )
    return start, end


# --------------------------------------------------------------- vocabulary ---


class MarketCategory(Enum):
    """What kind of market a benchmark is, as a closed vocabulary.

    Categories exist so the page can group readings and so a later adapter can
    add a market to a category that already reads correctly. **A category
    carries no behaviour**: nothing in this package branches on it to compute a
    number, and no category is privileged over another.

    Six members, chosen because each names a market the owner asked to be able
    to see. Five of them have no configured provider in this build, and that is
    reported rather than hidden — a category with no live member is exactly the
    honest statement `fmits pulse` exists to make.
    """

    CRYPTO = "crypto"
    EQUITY_INDEX = "equity_index"
    CURRENCY = "currency"
    COMMODITY = "commodity"
    RATES = "rates"
    VOLATILITY_INDEX = "volatility_index"


class TradingSchedule(Enum):
    """Whether a market trades continuously, on a calendar, or unknown.

    **This is the minimum session vocabulary, and it is deliberately not a
    calendar.** FMITS has no trading-calendar engine: no holiday table, no
    half-day rule, no exchange timezone and no open/closed computation exists
    anywhere in this repository. Building one is a milestone of its own.

    What this enum prevents is the architectural mistake of assuming every
    market is 24/7. A horizon on this page is defined in **closed bars**, which
    is well-defined for any market. Only a `CONTINUOUS` market may additionally
    have that window described in wall-clock terms, because only there does one
    bar reliably equal one interval of elapsed time. For a `SESSION_BOUND`
    market, twenty-four hourly bars are not twenty-four hours and this package
    will not say they are — see `SCHEDULE_LIMITATION`.
    """

    #: Trades without interruption; bar count and elapsed time coincide.
    CONTINUOUS = "continuous"
    #: Trades on a calendar this repository does not model.
    SESSION_BOUND = "session_bound"
    #: Schedule not established. Treated exactly as `SESSION_BOUND` is: no
    #: wall-clock equivalence is claimed. Unknown is never optimistic.
    UNKNOWN = "unknown"


#: Printed on every page. The session limitation stated once, in full, where a
#: reader cannot miss it — rather than implied by the absence of an open/closed
#: indicator, which a reader would reasonably read as *"everything is open"*.
SCHEDULE_LIMITATION = (
    "This repository holds no trading calendar: no holiday table, no exchange "
    "timezone and no open/closed computation exists. Every horizon below is "
    "defined as a count of closed bars, which is well defined for any market. "
    "A wall-clock equivalent is stated only for continuously traded markets, "
    "where one bar is one interval of elapsed time. For any other market no "
    "such equivalence is claimed and none should be inferred."
)

#: Printed beside every volatility figure. The repository has no distribution of
#: past volatility to compare a reading against, so it prints the number and
#: refuses the adjective — *"elevated"* without a baseline is a word, not a
#: measurement.
VOLATILITY_CLASSIFICATION_NOTE = (
    "Volatility is reported as a measured number and is deliberately not "
    "classified. Calling a reading low, normal or elevated requires a baseline "
    "distribution of this market's own past volatility, which this build does "
    "not compute or store. Compare the figures below with each other over the "
    "stated window; do not read any of them as high or low on its own."
)

#: Printed above the cross-asset section. Every clause is a limitation a reader
#: would otherwise supply for themselves, wrongly.
CO_MOVEMENT_CAVEAT = (
    "Co-movement is the Pearson correlation of two markets' simple returns "
    "over one stated window of closed bars. It is a description of that window "
    "and nothing else: it is not causation, not a prediction, not a stable "
    "property of the pair, and not evidence that one market moved the other. "
    "Two markets can co-move for a week and diverge the next hour."
)

#: The page's own statement of what it is for. Printed at the top, because a
#: reader who takes an orientation page for a recommendation is the failure mode
#: this whole surface has to design against.
PULSE_ORIENTATION_NOTE = (
    "This page is orientation, not a recommendation. It states what tracked "
    "markets did over named windows, what could not be measured, and when each "
    "reading was taken. It contains no view, no signal and no suggested "
    "action, and nothing on it should be read as one."
)


# ------------------------------------------------------------------ universe ---


@dataclass(frozen=True, slots=True)
class ProviderInstrument:
    """How one benchmark is obtained: a provider, its exact symbol, an interval.

    **This is the only place in the package a provider is named**, and it is a
    label rather than a capability: nothing here fetches, and no module in this
    package imports an adapter. A composition root reads this record to decide
    what to ask for, which is what keeps every payload shape, every error type
    and every retry policy on the far side of the boundary.

    `symbol` is exact and is never normalized. `"BTCUSDT"` and `"btcusdt"` are
    two different instruments, which is the identical rule `SeriesIdentity`
    states for the same reason: a symbol is an identifier, not a search term.
    """

    provider: str
    symbol: str
    interval: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _text(self.provider, "provider"))
        object.__setattr__(self, "symbol", _text(self.symbol, "symbol"))
        object.__setattr__(self, "interval", _text(self.interval, "interval"))

    @property
    def label(self) -> str:
        """One line naming exactly what was asked for, printed as provenance."""
        return f"{self.provider} {self.symbol} {self.interval}"


@dataclass(frozen=True, slots=True)
class Benchmark:
    """One market this page tracks, whether or not it can currently be read.

    **A benchmark with no provider is a first-class member of the universe, not
    an omission.** `instrument` and `unsupported_reason` are exclusive and
    exactly one must be present: a market is either wired to a provider or it
    carries the sentence explaining why it is not. That is what lets the page
    say *"DXY — unavailable: no configured provider"* instead of quietly
    pretending the dollar does not exist, which is the difference between an
    honest orientation and a flattering one.

    `quote_unit` is what the market is priced in (`"USDT"`, `"USD"`, `"index
    points"`, `"percent"`). It is not decoration: it is what
    `fmis.market_pulse.pulse` uses to refuse a comparison between markets whose
    returns are not denominated in the same thing.
    """

    benchmark_id: str
    display_name: str
    category: MarketCategory
    schedule: TradingSchedule
    quote_unit: str
    instrument: ProviderInstrument | None = None
    unsupported_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "benchmark_id", _text(self.benchmark_id, "benchmark_id")
        )
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        if not isinstance(self.category, MarketCategory):
            raise TypeError(
                f"category must be a MarketCategory, got "
                f"{type(self.category).__name__}"
            )
        if not isinstance(self.schedule, TradingSchedule):
            raise TypeError(
                f"schedule must be a TradingSchedule, got "
                f"{type(self.schedule).__name__}"
            )
        object.__setattr__(self, "quote_unit", _text(self.quote_unit, "quote_unit"))
        if self.instrument is not None and not isinstance(
            self.instrument, ProviderInstrument
        ):
            raise TypeError(
                f"instrument must be a ProviderInstrument or None, got "
                f"{type(self.instrument).__name__}"
            )
        if self.instrument is None and self.unsupported_reason is None:
            raise PulseUniverseError(
                f"{self.benchmark_id} names no provider instrument and states "
                "no reason it has none; a market this build cannot read is "
                "reported with its reason, never dropped from the universe"
            )
        if self.instrument is not None and self.unsupported_reason is not None:
            raise PulseUniverseError(
                f"{self.benchmark_id} names both a provider instrument and a "
                "reason it is unsupported; a market is wired up or it is not"
            )
        if self.unsupported_reason is not None:
            object.__setattr__(
                self,
                "unsupported_reason",
                _text(self.unsupported_reason, "unsupported_reason"),
            )

    @property
    def is_supported(self) -> bool:
        """Whether any provider is configured for this market at all.

        **Not** whether it can be read right now: a supported market whose fetch
        fails becomes a `MarketUnavailable`, and the page keeps the two apart.
        """
        return self.instrument is not None

    @property
    def claims_wall_clock_horizons(self) -> bool:
        """Whether a bar count may also be described in elapsed time.

        True only for `CONTINUOUS`. `UNKNOWN` deliberately answers the same as
        `SESSION_BOUND`: a schedule nobody established is not a schedule that
        happens to be 24/7.
        """
        return self.schedule is TradingSchedule.CONTINUOUS


@dataclass(frozen=True, slots=True)
class MarketUniverse:
    """An ordered, distinct set of benchmarks — the page's stated scope.

    **Order is configuration and is preserved exactly.** Nothing sorts a
    universe: the sections that rank do so explicitly, by a named quantity, and
    everything else prints markets in the order the owner configured them. A
    universe that reordered itself would make *"which market is listed first"*
    an accidental signal.

    **Three distinctness rules, and each closes a way a page can lie:**

      * duplicate `benchmark_id` — the same market would appear twice and could
        rank against itself;
      * duplicate `display_name` — two different markets would be
        indistinguishable to the reader, who has only the name;
      * duplicate `ProviderInstrument` — two benchmarks reading one instrument
        are one fact printed twice, and a ranking over them is a ranking with a
        rigged tie.

    All three raise `PulseUniverseError` at construction, because a
    misconfigured universe must fail before a page is built rather than produce
    a plausible one.
    """

    name: str
    benchmarks: tuple[Benchmark, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "name"))
        object.__setattr__(
            self, "benchmarks", _tuple_of(self.benchmarks, Benchmark, "benchmarks")
        )
        if not self.benchmarks:
            raise PulseUniverseError(
                f"universe {self.name!r} holds no benchmark; an empty universe "
                "produces a page that asks nothing and therefore proves nothing"
            )
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        seen_instruments: dict[ProviderInstrument, str] = {}
        for benchmark in self.benchmarks:
            if benchmark.benchmark_id in seen_ids:
                raise PulseUniverseError(
                    f"benchmark id {benchmark.benchmark_id!r} appears twice in "
                    f"universe {self.name!r}; one market has one entry"
                )
            seen_ids.add(benchmark.benchmark_id)
            if benchmark.display_name in seen_names:
                raise PulseUniverseError(
                    f"display name {benchmark.display_name!r} appears twice in "
                    f"universe {self.name!r}; a reader has only the name, so two "
                    "markets sharing one are two facts nobody can tell apart"
                )
            seen_names.add(benchmark.display_name)
            if benchmark.instrument is None:
                continue
            owner = seen_instruments.get(benchmark.instrument)
            if owner is not None:
                raise PulseUniverseError(
                    f"{benchmark.benchmark_id} and {owner} both read "
                    f"{benchmark.instrument.label}; two benchmarks over one "
                    "instrument are one reading printed twice, and ranking them "
                    "against each other is a rigged tie"
                )
            seen_instruments[benchmark.instrument] = benchmark.benchmark_id

    @property
    def supported(self) -> tuple[Benchmark, ...]:
        """The benchmarks a provider is configured for, in universe order."""
        return tuple(entry for entry in self.benchmarks if entry.is_supported)

    @property
    def unsupported(self) -> tuple[Benchmark, ...]:
        """The benchmarks no provider is configured for, in universe order."""
        return tuple(entry for entry in self.benchmarks if not entry.is_supported)

    def benchmark_for(self, benchmark_id: str) -> Benchmark | None:
        """One benchmark by id, or `None` when this universe has no such market."""
        wanted = _text(benchmark_id, "benchmark_id")
        for entry in self.benchmarks:
            if entry.benchmark_id == wanted:
                return entry
        return None


# ------------------------------------------------------------------ horizons ---


@dataclass(frozen=True, slots=True)
class Horizon:
    """A measurement window, defined in **closed bars** and never in wall time.

    This is the design decision that makes the page correct for markets that do
    not trade continuously. *"The move over the last 24 closed 1h bars"* is well
    defined for a market with any schedule; *"the move over the last 24 hours"*
    is only well defined for one that never closes, and computing it by
    subtracting timestamps would silently span a weekend for anything else.

    `wall_clock_equivalent` is the phrase a market may print beside the bar
    count, and `wall_clock_span` is the duration that phrase asserts. **Both or
    neither**, because a phrase with nothing to check it against is a claim
    nobody can falsify.

    **The span is what makes the phrase safe to print.** A bar count equals an
    elapsed duration only when the series has no gap, and a `CandleSeries`
    permits forward gaps: a provider that omitted bars for maintenance returns
    168 hourly bars spanning eleven days, not seven. The phrase is therefore
    *nominal*, and a consumer must compare it against a move's own
    `measured_span` before printing it — `fmis.market_pulse.render` does, and a
    test proves a gapped series falls back to the bar count.

    Carried rather than derived, because deriving the span would require parsing
    the interval label, and ADR-0009 records that this repository has no
    canonical timeframe vocabulary to parse.

    `bars` is the number of *moves*, so the window needs `bars + 1` closed
    prices. A one-bar horizon compares the last close with the one before it.
    """

    horizon_id: str
    bars: int
    description: str
    wall_clock_equivalent: str | None = None
    wall_clock_span: timedelta | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "horizon_id", _text(self.horizon_id, "horizon_id"))
        object.__setattr__(self, "bars", _count(self.bars, "bars", minimum=1))
        object.__setattr__(self, "description", _text(self.description, "description"))
        if (self.wall_clock_equivalent is None) != (self.wall_clock_span is None):
            raise ValueError(
                f"horizon {self.horizon_id!r} states a wall-clock equivalent "
                "without the span that would confirm it, or the reverse; a "
                "phrase with nothing to check it against is a claim nobody can "
                "falsify"
            )
        if self.wall_clock_equivalent is not None:
            object.__setattr__(
                self,
                "wall_clock_equivalent",
                _text(self.wall_clock_equivalent, "wall_clock_equivalent"),
            )
            if not isinstance(self.wall_clock_span, timedelta):
                raise TypeError(
                    "wall_clock_span must be a timedelta, got "
                    f"{type(self.wall_clock_span).__name__}"
                )
            if self.wall_clock_span <= _ZERO:
                raise ValueError(
                    f"horizon {self.horizon_id!r} states a wall-clock span of "
                    f"{self.wall_clock_span}; a window spans forward"
                )

    @property
    def required_observations(self) -> int:
        """Closed prices needed to measure this horizon: one more than `bars`."""
        return self.bars + 1


@dataclass(frozen=True, slots=True)
class HorizonMove:
    """One market's measured move over one horizon, or the reason there is none.

    `value` is a **fraction**, not a percentage: `0.0125` is a move of one and a
    quarter percent. The renderer converts once, so no intermediate value is
    ever scaled twice.

    `metric` names the function that produced the number — `"period_return"`,
    the Relative Value Engine's own. It travels on the record so a figure on the
    page can be traced to an engine with tests over its behaviour rather than to
    this package, which computes nothing.

    `observation_count` is how many closed prices were actually read, which is
    what makes a value reconstructable: it, the window instants and the metric
    name are together enough to recompute the figure from the same history.
    """

    horizon_id: str
    bars: int
    value: float | None
    unavailable_reason: str | None
    metric: str
    observation_count: int
    window_start: datetime | None = None
    window_end: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "horizon_id", _text(self.horizon_id, "horizon_id"))
        object.__setattr__(self, "bars", _count(self.bars, "bars", minimum=1))
        subject = f"move {self.horizon_id!r}"
        value, reason = _exactly_one(self.value, self.unavailable_reason, subject=subject)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "unavailable_reason", reason)
        object.__setattr__(self, "metric", _text(self.metric, "metric"))
        object.__setattr__(
            self,
            "observation_count",
            _count(self.observation_count, "observation_count", minimum=0),
        )
        start, end = _window(
            self.window_start,
            self.window_end,
            subject=subject,
            measured=value is not None,
        )
        object.__setattr__(self, "window_start", start)
        object.__setattr__(self, "window_end", end)
        if value is not None and self.observation_count < self.bars + 1:
            raise ValueError(
                f"{subject} reports a value from {self.observation_count} "
                f"observation(s) but a {self.bars}-bar horizon needs "
                f"{self.bars + 1}; a shorter window is a different measurement"
            )

    @property
    def is_measured(self) -> bool:
        return self.value is not None

    @property
    def measured_span(self) -> timedelta | None:
        """How much time this window actually covered, or `None` if unmeasured.

        **The check that stops a bar count being printed as a duration.** A
        horizon of 168 hourly bars is seven days only when the provider returned
        every bar; a gap makes the same 168 bars span longer, and a page that
        printed *"7 days"* over an eleven-day window would be stating something
        the data does not say. Computed, never stored — there is no second copy
        to drift from the window it describes.
        """
        if self.window_start is None or self.window_end is None:
            return None
        return self.window_end - self.window_start


@dataclass(frozen=True, slots=True)
class VolatilityReading:
    """One market's realized volatility over a stated window, or why there is none.

    **Deliberately unclassified.** There is no `regime`, `level` or `is_elevated`
    field, and adding one would require a baseline distribution this build
    neither computes nor stores. `VOLATILITY_CLASSIFICATION_NOTE` is what the
    page prints in place of an adjective.

    `metric` names the Relative Value Engine function that produced the value —
    `"realized_volatility"`, the sample standard deviation of simple returns,
    unannualized. This package writes no volatility formula of its own, and does
    not reimplement `fmis.features.indicators.atr`: an absolute price range in a
    market's own quote currency is not comparable across markets, and the whole
    point of this reading is that it appears beside other markets' readings.
    """

    value: float | None
    unavailable_reason: str | None
    metric: str
    observation_count: int
    window_start: datetime | None = None
    window_end: datetime | None = None

    def __post_init__(self) -> None:
        subject = "volatility"
        value, reason = _exactly_one(
            self.value, self.unavailable_reason, subject=subject
        )
        if value is not None and value < 0:
            raise ValueError(
                f"{subject} value {value} is negative; a standard deviation is "
                "not signed, and a negative one is a broken reading"
            )
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "unavailable_reason", reason)
        object.__setattr__(self, "metric", _text(self.metric, "metric"))
        object.__setattr__(
            self,
            "observation_count",
            _count(self.observation_count, "observation_count", minimum=0),
        )
        start, end = _window(
            self.window_start,
            self.window_end,
            subject=subject,
            measured=value is not None,
        )
        object.__setattr__(self, "window_start", start)
        object.__setattr__(self, "window_end", end)

    @property
    def is_measured(self) -> bool:
        return self.value is not None


# ------------------------------------------------------------------ readings ---


@dataclass(frozen=True, slots=True)
class MarketReading:
    """Everything this page knows about one market that could be read.

    **Provenance is not optional and is not assembled at render time.** `source`
    names the provider, `interval` the bar size, `last_bar_open` the instant the
    most recent closed bar opened, and `closed_bar_count` how much history that
    rests on. A reading cannot exist without all four.

    `last_bar_open` is the bar's **open**, following `fmis.marks.PriceReading`
    exactly and for the same reason: the canonical `Candle` carries no close
    time, so the latest instant this repository can honestly name is the bar's
    open. The consequence is stated rather than hidden — a reading's age is
    **overstated** by up to one interval and never understated, which is the safe
    direction for a staleness figure and the reason `interval` travels beside it.

    **A move per horizon, at most once each.** Two answers for one horizon would
    let a reader pick the one they preferred, which is the rule
    `PriceSnapshot` states for a timeframe role and `MarketUniverse` states for
    a benchmark id.
    """

    benchmark: Benchmark
    source: str
    interval: str
    last_bar_open: datetime
    closed_bar_count: int
    moves: tuple[HorizonMove, ...]
    volatility: VolatilityReading

    def __post_init__(self) -> None:
        if not isinstance(self.benchmark, Benchmark):
            raise TypeError(
                f"benchmark must be a Benchmark, got {type(self.benchmark).__name__}"
            )
        if not self.benchmark.is_supported:
            raise ValueError(
                f"{self.benchmark.benchmark_id} carries no provider instrument, "
                "so it cannot have produced a reading; an unsupported market is "
                "reported as unsupported, never as read"
            )
        object.__setattr__(self, "source", _text(self.source, "source"))
        object.__setattr__(self, "interval", _text(self.interval, "interval"))
        object.__setattr__(
            self, "last_bar_open", _utc(self.last_bar_open, "last_bar_open")
        )
        object.__setattr__(
            self,
            "closed_bar_count",
            _count(self.closed_bar_count, "closed_bar_count", minimum=1),
        )
        object.__setattr__(
            self, "moves", _tuple_of(self.moves, HorizonMove, "moves")
        )
        if not isinstance(self.volatility, VolatilityReading):
            raise TypeError(
                f"volatility must be a VolatilityReading, got "
                f"{type(self.volatility).__name__}"
            )
        seen: set[str] = set()
        for move in self.moves:
            if move.horizon_id in seen:
                raise ValueError(
                    f"{self.benchmark.benchmark_id} reports horizon "
                    f"{move.horizon_id!r} twice; one market has one move per "
                    "horizon, or a reader can choose which one to believe"
                )
            seen.add(move.horizon_id)

    @property
    def benchmark_id(self) -> str:
        return self.benchmark.benchmark_id

    @property
    def provenance(self) -> str:
        """One line naming where this reading came from and what it rests on."""
        return (
            f"{self.source} · {self.interval} · {self.closed_bar_count} closed "
            f"bars · last bar opened {self.last_bar_open.isoformat()}"
        )

    def age_at(self, moment: datetime) -> timedelta:
        """How old this reading is at an instant — computed, never stored."""
        return _utc(moment, "moment") - self.last_bar_open

    def move_for(self, horizon_id: str) -> HorizonMove | None:
        """One horizon's move, or `None` when this reading has none for it."""
        wanted = _text(horizon_id, "horizon_id")
        for move in self.moves:
            if move.horizon_id == wanted:
                return move
        return None


@dataclass(frozen=True, slots=True)
class MarketUnavailable:
    """One market that a configured provider was asked for and did not deliver.

    Distinct from `Benchmark.unsupported_reason`, and the distinction is the
    point: *"there is no provider for the dollar index"* is a permanent property
    of this build, and *"Binance refused this request"* is a condition that will
    probably be gone in a minute. A page collapsing them would teach the owner
    to ignore both.

    `reason` carries the provider's own words, including its exception type. A
    reason this package paraphrased would be a reason nobody can act on.
    """

    benchmark: Benchmark
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.benchmark, Benchmark):
            raise TypeError(
                f"benchmark must be a Benchmark, got {type(self.benchmark).__name__}"
            )
        if not self.benchmark.is_supported:
            raise ValueError(
                f"{self.benchmark.benchmark_id} carries no provider instrument, "
                "so no provider can have failed for it; a market with no "
                "provider is unsupported, which is a different fact"
            )
        object.__setattr__(self, "reason", _text(self.reason, "reason"))

    @property
    def benchmark_id(self) -> str:
        return self.benchmark.benchmark_id


# ------------------------------------------------------------------ ordering ---


@dataclass(frozen=True, slots=True)
class RankedMove:
    """One row of an ordering: a market, and the single number that placed it."""

    benchmark_id: str
    display_name: str
    value: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "benchmark_id", _text(self.benchmark_id, "benchmark_id")
        )
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        object.__setattr__(self, "value", _finite(self.value, "value"))


@dataclass(frozen=True, slots=True)
class HorizonRanking:
    """Markets ordered by **one** measured quantity over **one** horizon.

    **This is an ordering, not a score.** `ordering_quantity` names the single
    figure that produced the order and it is printed on the page; there is no
    weight, no total, no rank number and no second input. Every row's `value` is
    the same measurement as every other row's, so two adjacent rows can be
    compared by reading them.

    `quote_unit` scopes the comparison. A ranking mixes only markets denominated
    in the same unit, because a return quoted in one currency and a return
    quoted in another are not the same quantity — the second silently contains
    the exchange rate between them.

    `excluded` carries every market left out **with its reason**. A ranking that
    quietly dropped what it could not compare would read as a complete picture
    of the universe, and it is not one.
    """

    horizon_id: str
    quote_unit: str
    ordering_quantity: str
    ordered: tuple[RankedMove, ...]
    excluded: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "horizon_id", _text(self.horizon_id, "horizon_id"))
        object.__setattr__(self, "quote_unit", _text(self.quote_unit, "quote_unit"))
        object.__setattr__(
            self,
            "ordering_quantity",
            _text(self.ordering_quantity, "ordering_quantity"),
        )
        object.__setattr__(
            self, "ordered", _tuple_of(self.ordered, RankedMove, "ordered")
        )
        seen: set[str] = set()
        for row in self.ordered:
            if row.benchmark_id in seen:
                raise ValueError(
                    f"{row.benchmark_id} is placed twice in the {self.horizon_id} "
                    "ordering; one market has one position"
                )
            seen.add(row.benchmark_id)
        excluded = tuple(self.excluded)
        for entry in excluded:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError(
                    "excluded must hold (benchmark_id, reason) pairs, got "
                    f"{entry!r}"
                )
            benchmark_id = _text(entry[0], "excluded benchmark_id")
            _text(entry[1], "excluded reason")
            if benchmark_id in seen:
                raise ValueError(
                    f"{benchmark_id} is both placed in and excluded from the "
                    f"{self.horizon_id} ordering; one market has one outcome"
                )
        object.__setattr__(self, "excluded", excluded)

    @property
    def is_empty(self) -> bool:
        """No market could be ordered. **Not** the same as no market moving."""
        return not self.ordered

    @property
    def leader(self) -> RankedMove | None:
        """The highest measured value, or `None` when nothing could be ordered."""
        return self.ordered[0] if self.ordered else None

    @property
    def laggard(self) -> RankedMove | None:
        """The lowest measured value, or `None` when nothing could be ordered."""
        return self.ordered[-1] if self.ordered else None


@dataclass(frozen=True, slots=True)
class CoMovement:
    """How two markets' returns moved together over one window of closed bars.

    A description of a window, and the type refuses to be read as more: it holds
    no p-value, no significance flag, no lead/lag and no direction of influence,
    because none of those is computed and each would invite a causal reading.
    `CO_MOVEMENT_CAVEAT` is printed above every one of these.

    `metric` names the Relative Value Engine function that produced it —
    `"pearson_correlation"`. The engine requires the two series to be aligned
    and never aligns them itself; a pair whose bars do not line up exactly is
    reported here as unavailable with that reason rather than quietly
    intersected, because an intersection is a *different* window than the one
    the page names.
    """

    subject_id: str
    reference_id: str
    value: float | None
    unavailable_reason: str | None
    metric: str
    observation_count: int
    window_start: datetime | None = None
    window_end: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", _text(self.subject_id, "subject_id"))
        object.__setattr__(
            self, "reference_id", _text(self.reference_id, "reference_id")
        )
        if self.subject_id == self.reference_id:
            raise ValueError(
                f"{self.subject_id} cannot co-move with itself; a correlation of "
                "one market against itself is arithmetic, not information"
            )
        subject = f"co-movement {self.subject_id}/{self.reference_id}"
        value, reason = _exactly_one(
            self.value, self.unavailable_reason, subject=subject
        )
        if value is not None and not -1.0 <= value <= 1.0:
            raise ValueError(
                f"{subject} value {value} lies outside [-1, 1]; a Pearson "
                "correlation cannot, so this is a broken reading"
            )
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "unavailable_reason", reason)
        object.__setattr__(self, "metric", _text(self.metric, "metric"))
        object.__setattr__(
            self,
            "observation_count",
            _count(self.observation_count, "observation_count", minimum=0),
        )
        start, end = _window(
            self.window_start,
            self.window_end,
            subject=subject,
            measured=value is not None,
        )
        object.__setattr__(self, "window_start", start)
        object.__setattr__(self, "window_end", end)

    @property
    def is_measured(self) -> bool:
        return self.value is not None


# --------------------------------------------------------------------- page ---


@dataclass(frozen=True, slots=True)
class MarketPulse:
    """One frozen orientation across a configured universe, at one instant.

    **Every benchmark in the universe is accounted for exactly once**, in
    `readings`, in `unavailable`, or in the universe's own unsupported set. The
    constructor proves it: a market that vanished between the universe and the
    page would be an absence the page cannot report, which is precisely the
    failure this surface exists to prevent.

    **`as_of` is supplied, never read.** Nothing in this package touches a
    clock, so two runs over the same history produce the same page — the
    property that makes the output testable, diffable and defensible.

    `co_movement_reference` names the market every co-movement is measured
    against, or is `None` when no reference could be established. It is a
    stated choice rather than an emergent one, and the page prints it.
    """

    as_of: datetime
    universe: MarketUniverse
    readings: tuple[MarketReading, ...]
    unavailable: tuple[MarketUnavailable, ...]
    rankings: tuple[HorizonRanking, ...]
    horizons: tuple[Horizon, ...]
    co_movements: tuple[CoMovement, ...] = ()
    co_movement_reference: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", _utc(self.as_of, "as_of"))
        if not isinstance(self.universe, MarketUniverse):
            raise TypeError(
                f"universe must be a MarketUniverse, got "
                f"{type(self.universe).__name__}"
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
            self, "rankings", _tuple_of(self.rankings, HorizonRanking, "rankings")
        )
        object.__setattr__(
            self, "horizons", _tuple_of(self.horizons, Horizon, "horizons")
        )
        object.__setattr__(
            self,
            "co_movements",
            _tuple_of(self.co_movements, CoMovement, "co_movements"),
        )

        expected = {entry.benchmark_id for entry in self.universe.supported}
        answered: set[str] = set()
        for entry in (*self.readings, *self.unavailable):
            if entry.benchmark_id in answered:
                raise ValueError(
                    f"{entry.benchmark_id} appears twice on one pulse; one "
                    "market has one reading or one reason, never both and "
                    "never two"
                )
            if entry.benchmark_id not in expected:
                raise ValueError(
                    f"{entry.benchmark_id} is not a supported member of universe "
                    f"{self.universe.name!r}; a page may not report a market its "
                    "own stated scope does not contain"
                )
            answered.add(entry.benchmark_id)
        missing = sorted(expected - answered)
        if missing:
            raise ValueError(
                f"universe {self.universe.name!r} names {missing} as supported "
                "but the pulse reports neither a reading nor a reason for them; "
                "a market that disappears between the scope and the page is an "
                "absence the page cannot disclose"
            )

        for reading in self.readings:
            if reading.last_bar_open > self.as_of:
                raise ValueError(
                    f"the reading for {reading.benchmark_id} rests on a bar that "
                    f"opened {reading.last_bar_open.isoformat()}, after the "
                    f"instant this pulse describes ({self.as_of.isoformat()}); a "
                    "reading from the future is a clock problem, not a reading"
                )

        seen_horizons: set[str] = set()
        for horizon in self.horizons:
            if horizon.horizon_id in seen_horizons:
                raise ValueError(
                    f"horizon {horizon.horizon_id!r} is declared twice; one "
                    "window has one definition"
                )
            seen_horizons.add(horizon.horizon_id)
        for ranking in self.rankings:
            if ranking.horizon_id not in seen_horizons:
                raise ValueError(
                    f"the {ranking.horizon_id!r} ordering names a horizon this "
                    "pulse does not declare; an ordering over an undefined "
                    "window cannot be reconstructed"
                )
        if self.co_movement_reference is not None:
            reference = _text(self.co_movement_reference, "co_movement_reference")
            object.__setattr__(self, "co_movement_reference", reference)
            if reference not in answered:
                raise ValueError(
                    f"co-movement reference {reference!r} is not a market this "
                    "pulse reports"
                )
        elif self.co_movements:
            raise ValueError(
                "co-movements are reported with no reference market named; a "
                "correlation against an unnamed series is not interpretable"
            )

    # -- projections, computed and never stored ------------------------------

    @property
    def read_count(self) -> int:
        return len(self.readings)

    @property
    def requested_count(self) -> int:
        """How many markets a provider was asked for — read plus failed."""
        return len(self.readings) + len(self.unavailable)

    @property
    def unsupported_count(self) -> int:
        """How many markets no provider is configured for at all."""
        return len(self.universe.unsupported)

    @property
    def is_empty(self) -> bool:
        """No market could be read. **Not** the same as a quiet market."""
        return not self.readings

    def reading_for(self, benchmark_id: str) -> MarketReading | None:
        wanted = _text(benchmark_id, "benchmark_id")
        for reading in self.readings:
            if reading.benchmark_id == wanted:
                return reading
        return None

    def ranking_for(self, horizon_id: str) -> HorizonRanking | None:
        """The first ordering for a horizon, or `None` if there is none.

        *First*, because a universe spanning several quote units produces one
        ordering per unit for the same horizon; `rankings` holds them all and
        this convenience is for the single-unit case the default universe is.
        """
        wanted = _text(horizon_id, "horizon_id")
        for ranking in self.rankings:
            if ranking.horizon_id == wanted:
                return ranking
        return None

    def oldest_reading(self) -> MarketReading | None:
        """The reading this page's freshness is bounded by, or `None` if none.

        The page is only as current as its stalest market, so this is the figure
        to print rather than an average — an average age makes one six-hour-old
        reading disappear behind nine fresh ones.
        """
        if not self.readings:
            return None
        oldest = self.readings[0]
        for reading in self.readings[1:]:
            if reading.last_bar_open < oldest.last_bar_open:
                oldest = reading
        return oldest
