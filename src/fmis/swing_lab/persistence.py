"""What happens to a swing thesis **after** the entry. Milestone BZ's vocabulary.

Three milestones have now searched setup geometry. BW rejected the timeframe
variants, BX rejected thirteen geometries, BY pre-declared the one geometry BX's
own evidence pointed at and refuted it on two independent generalisation tests.
The geometry search space is covered; the question this module exists to make
answerable is a different one:

    Does a valid swing setup exhibit measurable post-entry persistence, and can
    its deterioration be identified from information available at that instant?

**The distinction this module is built around, and it is the whole point.**

    DESCRIPTIVE   what winning and losing paths looked like, in hindsight
    CAUSAL        what was observable at bar t and could have decided at bar t

A sentence like *"trades that eventually won had an intact 1D structure"* is
descriptive: it conditions on the outcome and therefore contains the future. It
is **not** a trading rule, and a milestone that promotes one into a rule has
fitted its own history. Every type below is labelled with which of the two it
is, and `PostEntryCheckpoint` carries **only** facts confirmed by its own bar.

**Nothing here plans a trade.** This module is the post-entry twin of
`fmis.swing_lab.geometry_outcome`: it measures, it never admits. An architecture
guard asserts that `geometry.py`, `geometry_variants.py` and `nonstructural.py`
import nothing from here, so a persistence measurement can never become an
admission criterion by accident.

**The evaluation window is BW's, not a new one.** Every path is bounded by the
same `DEFAULT_EVALUATION_WINDOW_BARS` the three preceding milestones used, so a
BZ figure and a BY figure describe trades given the same amount of room. The
bound travels on every result, because a different bound would give a different
answer to every question about trade age.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Final

from fmis.paper.models import PriceBar
from fmis.snapshotting import TradeDirection
from fmis.swing_lab.geometry import LevelRef
from fmis.swing_lab.models import SwingLabError
from fmis.swing_setup.models import Direction

__all__ = [
    "CHECKPOINT_BARS",
    "EXCURSION_THRESHOLDS",
    "ADVERSE_THRESHOLD",
    "ThesisState",
    "ThesisObservation",
    "ThesisTimeline",
    "PostEntryCheckpoint",
    "PersistenceTrack",
    "thesis_state",
    "observe_path",
    "DESCRIPTIVE_NOT_CAUSAL",
]

DESCRIPTIVE_NOT_CAUSAL: Final[str] = (
    "A statement conditioned on how a trade ENDED is descriptive and contains "
    "the future. It may be reported as a path observation and it may never be "
    "read as a decision rule. Only a `PostEntryCheckpoint` — whose every field "
    "is confirmed by its own bar — is causal, and only a rule built from those "
    "fields is a rule this repository is entitled to test."
)

#: Bars after the entry at which a path is observed. **Pre-declared, and chosen
#: from the replay's own semantics rather than from a result.** The execution
#: role is 4H and the evaluation window is 60 of those bars, so the checkpoints
#: are dense where BX measured the typical trade to be decided (median 1 bar
#: held, p75 of 3) and thin afterwards, ending exactly at the window bound. A
#: checkpoint past the bound would be an observation of bars no trade was ever
#: given, which is why the last one is 60 and not 72.
CHECKPOINT_BARS: Final[tuple[int, ...]] = (1, 2, 3, 6, 12, 18, 24, 36, 48, 60)

#: The favourable excursions whose first arrival is timed. `1.0` is BX's own
#: give-back threshold and `0.5` is `geometry_outcome`'s first rung; both are
#: inherited rather than invented so BZ's counts can be read against BX's.
EXCURSION_THRESHOLDS: Final[tuple[Decimal, ...]] = (
    Decimal("0.5"), Decimal("1.0"), Decimal("1.5"), Decimal("2.0"),
)

#: The adverse excursion whose first arrival is timed. Half an R, matching
#: `geometry_outcome._first_half_r`'s magnitude so the two layers agree about
#: what "went against it first" means.
ADVERSE_THRESHOLD: Final[Decimal] = Decimal("0.5")

_DIRECTION_TO_TRADE: Final[dict[Direction, TradeDirection]] = {
    Direction.LONG: TradeDirection.LONG,
    Direction.SHORT: TradeDirection.SHORT,
}

#: Structural trend values that support a direction. Read from the production
#: enum's own vocabulary rather than restated as strings, so a renamed member is
#: an import error here instead of a silently never-matching comparison.
_SUPPORTS: Final[dict[Direction, str]] = {
    Direction.LONG: "sustained_higher",
    Direction.SHORT: "sustained_lower",
}
_OPPOSES: Final[dict[Direction, str]] = {
    Direction.LONG: "sustained_lower",
    Direction.SHORT: "sustained_higher",
}

#: The regime state under which the production gate admits a setup at all.
_TRENDING: Final[str] = "trending"


class ThesisState(str, Enum):
    """The post-entry standing of the thesis that opened the trade.

    **Derived from two observations and a direction, never asserted.** The
    comparison is always *this instant against the entry instant*, because
    "weakened" is a statement about a change and a single snapshot cannot make
    one. Six members, and the partition is total:

    * `INTACT` — the setup-timeframe structure still supports the direction and
      nothing below has fired. Not "healthy", not "working": the trade may be
      deeply underwater and its structure still intact, which is precisely the
      case an exit rule built on price alone cannot distinguish.
    * `STRENGTHENED` — support that was absent at entry has appeared, or the
      execution timeframe has joined a setup timeframe that already agreed.
    * `WEAKENED` — support present at entry has decayed to neutral or absent, or
      the context regime has left `TRENDING`. Weakening is not invalidation and
      the two are never merged: one is a thesis with less behind it, the other
      is a thesis whose own structure now says the opposite.
    * `CONFLICTED` — the setup and execution timeframes disagree in sign.
      Reported, never resolved, exactly as `market_regime` refuses to resolve a
      family disagreement.
    * `INVALIDATED` — the setup-timeframe structural trend now **opposes** the
      direction the trade was taken in. This is the strongest deterministic
      statement the existing engines make about a thesis being wrong.
    * `UNAVAILABLE` — no analysable instant exists at this bar. A stated
      absence, never a state: a rule that treats missing evidence as agreement
      would be reading a data gap as a market fact.
    """

    INTACT = "intact"
    STRENGTHENED = "strengthened"
    WEAKENED = "weakened"
    CONFLICTED = "conflicted"
    INVALIDATED = "invalidated"
    UNAVAILABLE = "unavailable"

    @property
    def is_adverse(self) -> bool:
        """Whether this state is one an exit mechanism may act on.

        `WEAKENED` is deliberately **excluded**. A rule exiting on weakening
        would exit almost every trade almost immediately — the setup trend
        passes through `NEUTRAL` constantly — and a mechanism that fires on
        nearly every trade is a time stop wearing a structure rule's clothes.
        """
        return self in _ADVERSE_STATES

    @property
    def is_known(self) -> bool:
        return self is not ThesisState.UNAVAILABLE


_ADVERSE_STATES: Final[frozenset[ThesisState]] = frozenset(
    {ThesisState.INVALIDATED, ThesisState.CONFLICTED}
)


@dataclass(frozen=True, slots=True)
class ThesisObservation:
    """One symbol's deterministic structural state at one 4H instant. **Causal.**

    Every field is a value `fmis.swing_setup.models.SetupInputs` already held at
    that instant, copied rather than recomputed. This module derives no
    structure, no trend and no regime: those are the production engines' output
    and BZ reads them exactly as the admission policy read them.

    ``bar_index`` is the position, in the symbol's decoded execution-bar array,
    of the bar whose **close** produced this observation — the same index
    `fmis.swing_lab.replay.ReplayInstant.signal_index` carries, so a trade
    entering at ``bar_index + 1`` and an observation at ``bar_index`` are
    describing the same instant from the two sides of the decision.

    ``protective_levels`` and ``objective_levels`` are the execution-timeframe
    levels **ordered as of this instant's close**, capped at
    `LEVELS_PER_SIDE`. They are what a structural trailing rule may consult at
    this bar and nothing else: a level confirmed later in the window is absent
    here because it did not exist yet.
    """

    symbol: str
    as_of: datetime
    bar_index: int
    context_structural_trend: str
    setup_structural_trend: str
    execution_structural_trend: str
    context_regime_structure: str
    evidence_state: str | None
    evidence_dominant_alignment: str | None
    decision_context_state: str
    setup_state: str
    setup_direction: str | None
    execution_close: float | None
    upper_levels: tuple[LevelRef, ...]
    lower_levels: tuple[LevelRef, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise SwingLabError("symbol must be a non-empty str")
        if isinstance(self.bar_index, bool) or not isinstance(self.bar_index, int):
            raise TypeError("bar_index must be an int")
        if self.bar_index < 0:
            raise SwingLabError("bar_index must be non-negative")

    def levels_for(self, side_is_upper: bool) -> tuple[LevelRef, ...]:
        """The ordered levels on one side. A selection, never a computation."""
        return self.upper_levels if side_is_upper else self.lower_levels

    def payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "as_of": self.as_of.isoformat(),
            "bar_index": self.bar_index,
            "context_structural_trend": self.context_structural_trend,
            "setup_structural_trend": self.setup_structural_trend,
            "execution_structural_trend": self.execution_structural_trend,
            "context_regime_structure": self.context_regime_structure,
            "evidence_state": self.evidence_state,
            "evidence_dominant_alignment": self.evidence_dominant_alignment,
            "decision_context_state": self.decision_context_state,
            "setup_state": self.setup_state,
            "setup_direction": self.setup_direction,
        }


#: How many ordered levels per side an observation carries. **Pre-declared.** A
#: structural trail consults the nearest few and never the whole book; carrying
#: every level for every one of ~100,000 instants would multiply the capture's
#: memory by an order of magnitude to hold levels no rule may reach.
LEVELS_PER_SIDE: Final[int] = 5


@dataclass(frozen=True, slots=True)
class ThesisTimeline:
    """Every analysable instant for one symbol, addressable by execution-bar index.

    Held per symbol rather than per trade because the replay produces it per
    symbol, and because two trades on the same symbol overlapping in time must
    read the **same** observation at the same bar. Building it per trade would
    let two trades disagree about what the market's structure was.

    **The lookup is exact, never nearest.** `at` returns ``None`` for a bar with
    no analysable instant rather than the closest one that has: silently
    substituting a neighbouring bar's structure is how a rule ends up reading a
    fact from one bar into a decision made on another.
    """

    symbol: str
    observations: Mapping[int, ThesisObservation]

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise SwingLabError("symbol must be a non-empty str")
        for index, observation in self.observations.items():
            if observation.bar_index != index:
                raise SwingLabError(
                    f"{self.symbol} timeline keys bar {index} with an observation "
                    f"whose own bar_index is {observation.bar_index}"
                )
            if observation.symbol != self.symbol:
                raise SwingLabError(
                    f"{self.symbol} timeline holds a {observation.symbol} observation"
                )

    def at(self, bar_index: int) -> ThesisObservation | None:
        """The observation confirmed by ``bar_index``'s close, or ``None``."""
        return self.observations.get(bar_index)

    @property
    def measured_bars(self) -> int:
        return len(self.observations)


def thesis_state(
    entry: ThesisObservation | None,
    current: ThesisObservation | None,
    direction: Direction,
) -> ThesisState:
    """Compare two instants and name the thesis' standing. **Pure and total.**

    The precedence is fixed and stated here rather than emerging from the order
    of a chain of ``if``s in a caller, because a rule whose precedence can be
    read two ways is a rule two milestones will measure differently:

        1. UNAVAILABLE   either instant is missing
        2. INVALIDATED   the setup timeframe now opposes the direction
        3. CONFLICTED    setup and execution disagree in sign
        4. WEAKENED      support present at entry is gone, or the regime left TRENDING
        5. STRENGTHENED  support absent at entry has appeared
        6. INTACT        none of the above

    Note that INVALIDATED is checked before CONFLICTED. A setup timeframe that
    has fully reversed is invalidation whatever the execution timeframe is
    doing, and reporting that case as a mere disagreement would understate it.
    """
    if direction not in _DIRECTION_TO_TRADE:
        raise SwingLabError(f"direction must be LONG or SHORT, got {direction!r}")
    if entry is None or current is None:
        return ThesisState.UNAVAILABLE

    supports = _SUPPORTS[direction]
    opposes = _OPPOSES[direction]

    if current.setup_structural_trend == opposes:
        return ThesisState.INVALIDATED

    setup_signed = current.setup_structural_trend in (supports, opposes)
    execution_signed = current.execution_structural_trend in (supports, opposes)
    if (
        setup_signed
        and execution_signed
        and current.setup_structural_trend != current.execution_structural_trend
    ):
        return ThesisState.CONFLICTED

    had_support = entry.setup_structural_trend == supports
    has_support = current.setup_structural_trend == supports
    if had_support and not has_support:
        return ThesisState.WEAKENED
    if (
        entry.context_regime_structure == _TRENDING
        and current.context_regime_structure != _TRENDING
    ):
        return ThesisState.WEAKENED
    if not had_support and has_support:
        return ThesisState.STRENGTHENED
    if (
        has_support
        and entry.execution_structural_trend != supports
        and current.execution_structural_trend == supports
    ):
        return ThesisState.STRENGTHENED
    return ThesisState.INTACT


@dataclass(frozen=True, slots=True)
class PostEntryCheckpoint:
    """One causal observation of an open position. **Every field is confirmed by its own bar.**

    ``mfe_r``, ``mae_r`` and ``peak_r`` are running figures over bars *up to and
    including* this one. ``close_r`` is the unrealised return at this bar's
    close. None of them reads a later bar, which is what makes a rule built from
    them implementable: a decision taken at this bar's close had exactly these
    numbers available and no others.

    ``giveback_r`` is ``peak_r - close_r`` and is therefore never negative. It
    is the quantity BX measured at 68.8 % and the quantity a profit-protection
    mechanism acts on.
    """

    bar: int
    at: datetime
    close_r: Decimal
    mfe_r: Decimal
    mae_r: Decimal
    peak_r: Decimal
    giveback_r: Decimal
    thesis: ThesisState

    def __post_init__(self) -> None:
        if isinstance(self.bar, bool) or not isinstance(self.bar, int) or self.bar < 1:
            raise SwingLabError("bar must be a positive int — bar 1 is the entry bar")
        if self.giveback_r < 0:
            raise SwingLabError(
                f"giveback_r is {self.giveback_r}; a peak cannot be below the "
                "close it is measured against"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "bar": self.bar,
            "at": self.at.isoformat(),
            "close_r": str(self.close_r),
            "mfe_r": str(self.mfe_r),
            "mae_r": str(self.mae_r),
            "peak_r": str(self.peak_r),
            "giveback_r": str(self.giveback_r),
            "thesis": self.thesis.value,
        }


@dataclass(frozen=True, slots=True)
class PersistenceTrack:
    """One trade's post-entry path. **Observational — this decides nothing.**

    The fields split cleanly into the two halves this milestone must not merge:

    * `checkpoints` are CAUSAL and are what an exit family may be built from;
    * `peak_r`, `bars_to_peak_r`, `final_close_r` and the `bars_to_*` timings
      are DESCRIPTIVE — each is a statement about the whole path and therefore
      about the future as seen from any bar inside it. They answer "what did
      paths look like", never "what should have been done at bar t".

    `DESCRIPTIVE_NOT_CAUSAL` states the rule; the split above is where it is
    enforced, and the renderer prints the two under separate headings so a
    reader cannot take one for the other.
    """

    symbol: str
    setup_id: str
    direction: Direction
    sample: str
    signal_at: datetime
    entry_at: datetime
    entry_price: Decimal
    initial_stop: Decimal
    target: Decimal
    risk: Decimal
    evaluation_window_bars: int
    checkpoints: tuple[PostEntryCheckpoint, ...]
    #: DESCRIPTIVE. First bar at which each of `EXCURSION_THRESHOLDS` was
    #: reached, absent when it never was.
    bars_to_excursion: Mapping[str, int]
    #: DESCRIPTIVE. First bar at which the adverse excursion reached
    #: `ADVERSE_THRESHOLD`.
    bars_to_adverse: int | None
    #: DESCRIPTIVE. The bar at which the favourable excursion peaked.
    bars_to_peak_r: int | None
    #: DESCRIPTIVE. The whole path's best favourable excursion.
    peak_r: Decimal
    #: DESCRIPTIVE. The unrealised return at the last observed bar.
    final_close_r: Decimal
    #: DESCRIPTIVE. `peak_r - final_close_r` over the whole path.
    total_giveback_r: Decimal
    #: The thesis state at entry, carried so a transition can be read without
    #: re-deriving it from a timeline the artifact may not hold.
    entry_thesis_known: bool

    @property
    def excursions_reached(self) -> tuple[Decimal, ...]:
        """Which of `EXCURSION_THRESHOLDS` the path ever reached. DESCRIPTIVE."""
        return tuple(
            item for item in EXCURSION_THRESHOLDS if str(item) in self.bars_to_excursion
        )

    @property
    def gave_back_a_full_r(self) -> bool:
        """BX's 68.8 % statistic, per path. DESCRIPTIVE."""
        return self.total_giveback_r >= Decimal("1")

    def checkpoint(self, bar: int) -> PostEntryCheckpoint | None:
        for item in self.checkpoints:
            if item.bar == bar:
                return item
        return None

    def payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "setup_id": self.setup_id,
            "direction": self.direction.value,
            "sample": self.sample,
            "signal_at": self.signal_at.isoformat(),
            "entry_at": self.entry_at.isoformat(),
            "entry_price": str(self.entry_price),
            "initial_stop": str(self.initial_stop),
            "target": str(self.target),
            "risk": str(self.risk),
            "evaluation_window_bars": self.evaluation_window_bars,
            "checkpoints": [item.payload() for item in self.checkpoints],
            "bars_to_excursion": dict(sorted(self.bars_to_excursion.items())),
            "bars_to_adverse": self.bars_to_adverse,
            "bars_to_peak_r": self.bars_to_peak_r,
            "peak_r": str(self.peak_r),
            "final_close_r": str(self.final_close_r),
            "total_giveback_r": str(self.total_giveback_r),
            "entry_thesis_known": self.entry_thesis_known,
        }


def observe_path(
    bars: Sequence[PriceBar],
    *,
    symbol: str,
    setup_id: str,
    direction: Direction,
    sample: str,
    signal_at: datetime,
    signal_index: int,
    entry_price: Decimal,
    initial_stop: Decimal,
    target: Decimal,
    evaluation_window_bars: int,
    timeline: ThesisTimeline | None = None,
    checkpoints: Sequence[int] = CHECKPOINT_BARS,
) -> PersistenceTrack:
    """Walk one entered position forward and record its causal path.

    **This walk takes no exit.** It observes the position as if it were held for
    the whole evaluation window, which is what makes it the shared input every
    exit family is measured against: a path truncated at the control's own exit
    could not answer "would a different rule have done better after that point".
    The control's exit is measured separately, by
    `fmis.swing_lab.trades.simulate_trade`, over the same bars.

    Deterministic and pure: no clock, no randomness, no network.

    ``signal_index`` is the bar whose close produced the signal; the entry bar is
    ``signal_index + 1``, matching `simulate_trade`'s own rule exactly rather
    than restating it. A checkpoint at bar ``n`` therefore observes
    ``bars[signal_index + n]``.

    Raises:
        SwingLabError: the geometry is unusable, or a checkpoint is not positive.
    """
    if direction not in _DIRECTION_TO_TRADE:
        raise SwingLabError(f"direction must be LONG or SHORT, got {direction!r}")
    if (
        isinstance(evaluation_window_bars, bool)
        or not isinstance(evaluation_window_bars, int)
        or evaluation_window_bars <= 0
    ):
        raise SwingLabError("evaluation_window_bars must be a positive int")
    wanted = tuple(checkpoints)
    for value in wanted:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise SwingLabError(f"every checkpoint must be a positive int, got {value!r}")
    side = _DIRECTION_TO_TRADE[direction]
    risk = side.sign * (entry_price - initial_stop)
    if risk <= 0:
        raise SwingLabError(
            f"the entry {entry_price} is at or beyond the stop {initial_stop}; "
            "there is no risk denominator to measure a path against"
        )

    window = bars[signal_index + 1 : signal_index + 1 + evaluation_window_bars]
    if not window:
        raise SwingLabError(
            f"{symbol} has no bar after signal index {signal_index}; a path "
            "cannot be observed for a position that never opened"
        )

    entry_observation = None if timeline is None else timeline.at(signal_index)
    wanted_set = set(wanted)

    best = worst = entry_price
    peak_r = Decimal(0)
    collected: list[PostEntryCheckpoint] = []
    bars_to_excursion: dict[str, int] = {}
    bars_to_adverse: int | None = None
    bars_to_peak: int | None = None
    close_r = Decimal(0)

    for position, bar in enumerate(window, start=1):
        favourable = bar.favourable_extreme(side)
        adverse = bar.adverse_extreme(side)
        if side.sign * (favourable - best) > 0:
            best = favourable
        if side.sign * (adverse - worst) < 0:
            worst = adverse

        mfe_r = side.sign * (best - entry_price) / risk
        mae_r = side.sign * (worst - entry_price) / risk
        close_r = side.sign * (bar.close - entry_price) / risk
        if mfe_r > peak_r:
            peak_r = mfe_r
            bars_to_peak = position

        for threshold in EXCURSION_THRESHOLDS:
            key = str(threshold)
            if key not in bars_to_excursion and mfe_r >= threshold:
                bars_to_excursion[key] = position
        if bars_to_adverse is None and mae_r <= -ADVERSE_THRESHOLD:
            bars_to_adverse = position

        if position in wanted_set:
            # The observation is read at `signal_index + position`, which is the
            # bar this checkpoint is measuring — its own close, never the next.
            current = (
                None if timeline is None else timeline.at(signal_index + position)
            )
            collected.append(
                PostEntryCheckpoint(
                    bar=position,
                    at=bar.open_time,
                    close_r=close_r,
                    mfe_r=mfe_r,
                    mae_r=mae_r,
                    peak_r=peak_r,
                    giveback_r=peak_r - close_r if peak_r > close_r else Decimal(0),
                    thesis=thesis_state(entry_observation, current, direction),
                )
            )

    return PersistenceTrack(
        symbol=symbol,
        setup_id=setup_id,
        direction=direction,
        sample=sample,
        signal_at=signal_at,
        entry_at=window[0].open_time,
        entry_price=entry_price,
        initial_stop=initial_stop,
        target=target,
        risk=risk,
        evaluation_window_bars=evaluation_window_bars,
        checkpoints=tuple(collected),
        bars_to_excursion=dict(bars_to_excursion),
        bars_to_adverse=bars_to_adverse,
        bars_to_peak_r=bars_to_peak,
        peak_r=peak_r,
        final_close_r=close_r,
        total_giveback_r=peak_r - close_r if peak_r > close_r else Decimal(0),
        entry_thesis_known=entry_observation is not None,
    )
