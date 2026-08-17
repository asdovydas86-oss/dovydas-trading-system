"""The shapes the simulator works in, and the two policies it works under.

Everything here is **exact**. A `PriceBar` is a candle whose four prices have
already crossed into `Decimal` through `fmis.money.exact_from_market_price`, and
`fmis.paper.bars` is the only module that performs that crossing. Nothing below
this line ever sees a `float`, which is what lets a simulated fill be compared
against a stop, folded into a position and digested into a record id without the
`1e-17` residue `fmis.money`'s own docstring warns about.

**Two policies, both named and both versioned.** `PAPER_FILL_POLICY_ID` decides
*where* a fill lands; `PAPER_ZERO_COST_POLICY` decides *what it costs*. Both are
recorded on every activation and every outcome, so the day either changes it is a
version bump and every figure already recorded still names the basis that
produced it.

**The zero in the cost policy is the whole reason the type exists.** A zero that
is a *policy* is a different object from a zero that is an omission: a later fee
model arrives as version 2, nothing silently changes meaning, and every surface
prints the basis beside the number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fmis.money import Quantity, canonical_decimal_text
from fmis.provenance import Absent
from fmis.records import (
    DomainValidationError,
    TradeDomainError,
    require_int,
    require_member,
    require_text,
    require_tuple_of,
    require_utc,
)
from fmis.snapshotting import TradeDirection
from fmis.trade_lifecycle import (
    PaperCostPolicy,
    TradeActivation,
    TradeLifecycleKind,
    TradeLifecycleState,
)

__all__ = [
    "PAPER_FILL_POLICY_ID",
    "PAPER_FILL_POLICY_VERSION",
    "PAPER_ZERO_COST_POLICY",
    "PAPER_AUTHOR_LABEL",
    "PAPER_LIMITATIONS",
    "PaperError",
    "PaperRefusedError",
    "PriceBar",
    "Excursion",
    "FillKind",
    "FillTrigger",
    "Fill",
    "StopMoveIntent",
    "LifecycleStep",
    "TradeRunState",
    "StepResult",
]

#: The rule set deciding where a simulated fill lands. Version 1 is the one
#: `PAPER_TRADING_AND_TRADE_LIFECYCLE_V1.md` §6.3 states in a table: a market
#: entry at the next bar's open, a level filled at the level or at the bar's open
#: when it gapped through, and the same gap rule applied identically to a
#: favourable and an unfavourable gap.
PAPER_FILL_POLICY_ID = "fmits-paper-fill"
PAPER_FILL_POLICY_VERSION = 1

#: Who a simulated record is asserted by. Not a person: the fill policy, by name
#: and version, so a fill can always be traced to the rule that produced it — and
#: so a reader can tell what the engine wrote from what the owner did.
PAPER_AUTHOR_LABEL = f"{PAPER_FILL_POLICY_ID}-v{PAPER_FILL_POLICY_VERSION}"

#: What a simulated fill costs in this build: nothing, stated.
PAPER_ZERO_COST_POLICY = PaperCostPolicy(
    policy_id="fmits-paper-zero-cost",
    version=1,
    fee_rate=Decimal(0),
    slippage_rate=Decimal(0),
)

#: Printed at the foot of every paper-trading surface, unchanged. The invariant
#: register: these qualify the whole page and belong once, at the bottom, rather
#: than beside a number where repetition teaches a reader to skip them. The
#: convention is `fmis.trade_capture.CAPTURE_LIMITATIONS`', reused.
PAPER_LIMITATIONS: tuple[tuple[str, str], ...] = (
    (
        "PT-1",
        "Nothing here reaches an exchange. A paper fill is what this system "
        "computes would have happened; it is not a trade, and no order was "
        "placed anywhere.",
    ),
    (
        "PT-2",
        "Fills are modelled at zero fee and zero slippage under a named, "
        "versioned policy. A real fill costs more, and this system holds no data "
        "that bounds by how much.",
    ),
    (
        "PT-3",
        "A level is filled on touch — at the level, or at the bar's open when "
        "the bar gapped through it. Whether real liquidity existed at that price "
        "is not modelled.",
    ),
    (
        "PT-4",
        "A bar that opens between the stop and a target and reaches both halts "
        "the trade. Intrabar order is unknowable without sub-bar data this "
        "system does not ingest, and none is inferred.",
    ),
    (
        "PT-5",
        "Perpetual funding, borrow cost, liquidation and spread are not "
        "modelled, and no data this system ingests bounds any of them.",
    ),
    (
        "PT-6",
        "Excursions are measured on the simulation interval's closed bars only. "
        "A wick on a finer interval is invisible to every figure here.",
    ),
    (
        "PT-7",
        "Paper is excluded from every real-money aggregate by default. A figure "
        "that includes it says so.",
    ),
    (
        "PT-8",
        "A paper fill carries a placeholder FX rate of 1 and a source that says "
        "so in words. This book has no tax consequence and no tax engine "
        "exists; when one arrives it must exclude the book, and that rate must "
        "never be read as a real one.",
    ),
    (
        "PT-9",
        "Every R multiple is an exact quotient, and one that does not terminate "
        "prints a long tail. Shortening it would be a rounding policy this "
        "system does not set.",
    ),
)


class PaperError(TradeDomainError):
    """Base class for every failure raised by the paper simulator."""


class PaperRefusedError(DomainValidationError, PaperError):
    """The simulator will not do what it was asked, and says which two values disagree."""


def _exact_price(value: Any, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if value <= 0:
        raise PaperRefusedError(
            f"{name} must be positive, got {value}; a zero or negative price is "
            "not a cheaper market, it is a broken reading"
        )
    return Decimal(canonical_decimal_text(value))


@dataclass(frozen=True, slots=True)
class PriceBar:
    """One closed candle, with every price already exact.

    `open_time` is the bar's **open**, which is the only instant the canonical
    `Candle` carries: the provider's close time is consumed to decide `is_closed`
    and is not part of the canonical record. `fmis.marks` reached the identical
    conclusion and stated the identical consequence — an instant derived from a
    bar is **overstated in age, never understated**, and that is the safe
    direction.

    `symbol` and `interval` travel with the prices so a bar from the wrong series
    cannot be fed to a run that is simulating another one. The engine checks it,
    rather than trusting a caller to have filtered correctly.
    """

    symbol: str
    interval: str
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", require_text(self.symbol, "symbol"))
        object.__setattr__(self, "interval", require_text(self.interval, "interval"))
        object.__setattr__(
            self, "open_time", require_utc(self.open_time, "open_time")
        )
        for name in ("open", "high", "low", "close"):
            object.__setattr__(self, name, _exact_price(getattr(self, name), name))
        if self.high < max(self.open, self.close, self.low):
            raise PaperRefusedError(
                f"high {canonical_decimal_text(self.high)} is below one of the "
                "other prices on the same bar; a bar whose extremes do not "
                "contain it is not a bar"
            )
        if self.low > min(self.open, self.close, self.high):
            raise PaperRefusedError(
                f"low {canonical_decimal_text(self.low)} is above one of the "
                "other prices on the same bar"
            )

    def favourable_extreme(self, direction: TradeDirection) -> Decimal:
        """The best price this bar reached for a commitment on that side."""
        return self.high if direction.sign > 0 else self.low

    def adverse_extreme(self, direction: TradeDirection) -> Decimal:
        """The worst price this bar reached for a commitment on that side."""
        return self.low if direction.sign > 0 else self.high

    def reached(self, direction: TradeDirection, level: Decimal, *, favourable: bool) -> bool:
        """Whether this bar's range touched a level on the stated side.

        A **touch**, not a close-through: a stop and a target are price levels,
        and the bar's extremes are the only honest record of whether price got
        there. `fmis.swing_setup.backtest_outcomes` made the identical choice for
        the identical reason and this reuses its rule rather than restating it
        differently.
        """
        wanted = _exact_price(level, "level")
        extreme = (
            self.favourable_extreme(direction)
            if favourable
            else self.adverse_extreme(direction)
        )
        reach = direction.sign * (extreme - wanted)
        return reach >= 0 if favourable else reach <= 0

    def opened_beyond(self, direction: TradeDirection, level: Decimal, *, favourable: bool) -> bool:
        """Whether the bar's **open** was already past a level.

        The one piece of intrabar ordering four numbers actually contain: a bar
        that opened past a level reached it at the first price of the bar, and
        nothing inside the bar can have preceded that. Using it removes most
        false ambiguity without inferring a path — §7.2 of the design record.
        """
        wanted = _exact_price(level, "level")
        reach = direction.sign * (self.open - wanted)
        return reach >= 0 if favourable else reach <= 0


@dataclass(frozen=True, slots=True)
class Excursion:
    """How far the trade ran either way, and over how many bars.

    Stored as **prices**, because a price is what a candle contains. Money needs
    a quantity that changed with every partial exit and R needs an entry the
    ledger owns; freezing either would freeze a quotient, which `AP` §5.3 says is
    never a stored field.
    """

    favourable: Decimal | Absent = field(
        default_factory=lambda: Absent("no bar has been observed while exposed")
    )
    adverse: Decimal | Absent = field(
        default_factory=lambda: Absent("no bar has been observed while exposed")
    )
    bars: int = 0

    def __post_init__(self) -> None:
        for name in ("favourable", "adverse"):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                object.__setattr__(self, name, _exact_price(value, name))
        require_int(self.bars, "bars", minimum=0)
        stated = [
            name
            for name in ("favourable", "adverse")
            if not isinstance(getattr(self, name), Absent)
        ]
        if len(stated) == 1:
            raise PaperRefusedError(
                "an excursion states both extremes or neither; one alone reads as "
                "a claim that the trade never went the other way"
            )
        if bool(stated) != bool(self.bars):
            raise PaperRefusedError(
                "an excursion over zero bars has no extremes, and one with "
                "extremes was measured over at least one bar"
            )

    @property
    def is_empty(self) -> bool:
        return self.bars == 0

    def extended(self, bar: PriceBar, direction: TradeDirection) -> Excursion:
        """This excursion plus one more bar. Returns a new value; nothing mutates."""
        if not isinstance(bar, PriceBar):
            raise TypeError("bar must be a PriceBar")
        best = bar.favourable_extreme(direction)
        worst = bar.adverse_extreme(direction)
        if not isinstance(self.favourable, Absent):
            if direction.sign * (self.favourable - best) > 0:
                best = self.favourable
        if not isinstance(self.adverse, Absent):
            if direction.sign * (self.adverse - worst) < 0:
                worst = self.adverse
        return Excursion(favourable=best, adverse=worst, bars=self.bars + 1)


class FillKind(Enum):
    """What a fill did to the exposure."""

    ENTRY = "entry"
    PARTIAL_EXIT = "partial_exit"
    EXIT = "exit"


class FillTrigger(Enum):
    """Which level, or which rule, produced the fill."""

    MARKET_OPEN = "market_open"
    ENTRY_LEVEL = "entry_level"
    TARGET_LEVEL = "target_level"
    STOP_LEVEL = "stop_level"


@dataclass(frozen=True, slots=True)
class Fill:
    """One simulated execution: a price, a size, and why it happened there."""

    kind: FillKind
    trigger: FillTrigger
    at: datetime
    price: Decimal
    quantity: Quantity
    gapped: bool = False
    leg_index: int | Absent = field(
        default_factory=lambda: Absent("this fill is not a rung of the ladder")
    )

    def __post_init__(self) -> None:
        require_member(self.kind, FillKind, "kind")
        require_member(self.trigger, FillTrigger, "trigger")
        object.__setattr__(self, "at", require_utc(self.at, "at"))
        object.__setattr__(self, "price", _exact_price(self.price, "price"))
        if not isinstance(self.quantity, Quantity):
            raise TypeError("quantity must be a Quantity")
        if self.quantity.amount <= 0:
            raise PaperRefusedError(
                f"a fill moves a positive size, got {self.quantity}; which way it "
                "moved is carried by `kind`"
            )
        if not isinstance(self.gapped, bool):
            raise TypeError("gapped must be a bool")
        if not isinstance(self.leg_index, Absent):
            require_int(self.leg_index, "leg_index", minimum=0)
        if (self.trigger is FillTrigger.TARGET_LEVEL) is isinstance(
            self.leg_index, Absent
        ):
            raise PaperRefusedError(
                "a fill at a target names the rung it came from, and a fill "
                "anywhere else names none"
            )

    @property
    def is_entry(self) -> bool:
        return self.kind is FillKind.ENTRY


@dataclass(frozen=True, slots=True)
class StopMoveIntent:
    """A stop move the engine derived from a rule the owner enabled.

    An *intent*, not a record: it carries no audit block and no author, because
    those belong to the moment it is written and this type is produced by a pure
    function. `fmis.paper.compose` turns it into a `StopAmendment`.
    """

    previous_stop: Decimal
    new_stop: Decimal
    term_id: str

    def __post_init__(self) -> None:
        for name in ("previous_stop", "new_stop"):
            object.__setattr__(self, name, _exact_price(getattr(self, name), name))
        object.__setattr__(self, "term_id", require_text(self.term_id, "term_id"))
        if self.previous_stop == self.new_stop:
            raise PaperRefusedError("a stop move that changes nothing is not a move")


@dataclass(frozen=True, slots=True)
class LifecycleStep:
    """One transition the engine derived from one bar, with what caused it."""

    kind: TradeLifecycleKind
    bar_sequence: int
    fill: Fill | Absent = field(
        default_factory=lambda: Absent("this transition moved no size")
    )
    note: str | Absent = field(default_factory=lambda: Absent("no note"))

    def __post_init__(self) -> None:
        require_member(self.kind, TradeLifecycleKind, "kind")
        require_int(self.bar_sequence, "bar_sequence", minimum=0)
        if not isinstance(self.fill, (Fill, Absent)):
            raise TypeError("fill must be a Fill or Absent")
        if not isinstance(self.note, Absent):
            object.__setattr__(self, "note", require_text(self.note, "note"))


@dataclass(frozen=True, slots=True)
class TradeRunState:
    """Everything the engine needs to advance one trade by one bar.

    Frozen and returned anew from every step, so a run is a fold rather than a
    mutation — the property that makes replaying the same bars twice produce the
    identical answer, and makes a partially-completed run impossible to observe.
    """

    activation: TradeActivation
    direction: TradeDirection
    initial_stop: Decimal
    effective_stop: Decimal
    state: TradeLifecycleState
    remaining: Quantity
    excursion: Excursion
    filled_legs: tuple[int, ...] = ()
    entry_price: Decimal | Absent = field(
        default_factory=lambda: Absent("no fill has opened this trade")
    )
    opened_at: datetime | Absent = field(
        default_factory=lambda: Absent("no fill has opened this trade")
    )
    last_bar_time: datetime | Absent = field(
        default_factory=lambda: Absent("no bar has been advanced yet")
    )

    def __post_init__(self) -> None:
        if not isinstance(self.activation, TradeActivation):
            raise TypeError("activation must be a TradeActivation")
        require_member(self.direction, TradeDirection, "direction")
        for name in ("initial_stop", "effective_stop"):
            object.__setattr__(self, name, _exact_price(getattr(self, name), name))
        require_member(self.state, TradeLifecycleState, "state")
        if not isinstance(self.remaining, Quantity):
            raise TypeError("remaining must be a Quantity")
        if self.remaining.amount < 0:
            raise PaperRefusedError(
                f"remaining size cannot be negative, got {self.remaining}"
            )
        if not isinstance(self.excursion, Excursion):
            raise TypeError("excursion must be an Excursion")
        require_tuple_of(self.filled_legs, int, "filled_legs")
        if len(set(self.filled_legs)) != len(self.filled_legs):
            raise PaperRefusedError("one rung of the ladder cannot fill twice")
        if not isinstance(self.entry_price, Absent):
            object.__setattr__(
                self, "entry_price", _exact_price(self.entry_price, "entry_price")
            )
        for name in ("opened_at", "last_bar_time"):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                object.__setattr__(self, name, require_utc(value, name))

    @property
    def risk_distance(self) -> Decimal | Absent:
        """`|entry − initial stop|`, with the sign rule applied, or its absence.

        The denominator every R figure in this run rests on. Measured against the
        **initial** stop and never the effective one: an R multiple that shrank
        every time the stop was tightened would make good management look like a
        smaller trade.
        """
        if isinstance(self.entry_price, Absent):
            return Absent("no fill has established an entry to measure risk from")
        distance = self.direction.sign * (self.entry_price - self.initial_stop)
        if distance <= 0:
            return Absent(
                "the entry is not on the far side of the initial stop, so there is "
                "no risk distance; reporting its magnitude would turn a "
                "transposition into a risk figure"
            )
        return distance

    def is_leg_filled(self, index: int) -> bool:
        return index in self.filled_legs


@dataclass(frozen=True, slots=True)
class StepResult:
    """What one closed candle did to one trade, and the state it left behind.

    The steps are already in the order the fold will apply them, and their
    `bar_sequence` values are dense from zero — so two rungs of one ladder filling
    on one bar are ordered by the geometry that put the nearer rung first, and
    never by an assumption about the intrabar path.
    """

    bar: PriceBar
    next_state: TradeRunState
    steps: tuple[LifecycleStep, ...] = ()
    stop_move: StopMoveIntent | Absent = field(
        default_factory=lambda: Absent("no rule moved the stop on this bar")
    )

    def __post_init__(self) -> None:
        if not isinstance(self.bar, PriceBar):
            raise TypeError("bar must be a PriceBar")
        if not isinstance(self.next_state, TradeRunState):
            raise TypeError("next_state must be a TradeRunState")
        require_tuple_of(self.steps, LifecycleStep, "steps")
        if not isinstance(self.stop_move, (StopMoveIntent, Absent)):
            raise TypeError("stop_move must be a StopMoveIntent or Absent")
        sequences = [step.bar_sequence for step in self.steps]
        if sequences != list(range(len(sequences))):
            raise PaperRefusedError(
                f"bar sequences {sequences} are not dense from zero; a gap or a "
                "repeat would leave two events on one bar with no order the fold "
                "can apply"
            )
        moved = [
            step for step in self.steps if step.kind is TradeLifecycleKind.STOP_AMENDED
        ]
        if len(moved) > 1:
            raise PaperRefusedError(
                "a bar produces at most one stop amendment; two rules that both "
                "fire on one bar resolve to the tighter stop before anything is "
                "recorded, so the history holds one move per bar"
            )
        if bool(moved) != (not isinstance(self.stop_move, Absent)):
            raise PaperRefusedError(
                "a STOP_AMENDED step and the move it records are stated together "
                "or not at all"
            )

    @property
    def changed(self) -> bool:
        """Whether this bar produced anything worth writing."""
        return bool(self.steps)

    @property
    def fills(self) -> tuple[Fill, ...]:
        return tuple(
            step.fill for step in self.steps if not isinstance(step.fill, Absent)
        )
