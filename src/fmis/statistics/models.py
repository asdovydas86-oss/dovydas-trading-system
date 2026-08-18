"""The one record every statistic in this package is computed over.

A finished or unfinished trade, normalized from whichever of the two sources
recorded it, with **every field either a value or an `Absent` carrying its
reason**. Nothing here is stored: `AP` §25.2 classes cohort statistics as
`Aggregate` — *recomputable, disposable* — which is why this package has no
record kind, no repository and no write path at all.

**Two sources, and the difference between them is the honesty problem this
milestone exists around.**

* `SIMULATED` — `fmis.paper`. A frozen `TradeOutcome` and the `OutcomeReading`
  folded over it: an R multiple, an excursion in both directions, a bar count.
* `RECORDED` — `fmis.trade_capture`. A plan, its fills and the position they
  fold to: realized profit and loss, and **no R, no excursion and no bar
  count**, because nobody simulated the trade and `AP` §25.3 requires an
  excursion to be frozen at close or not to exist.

A corpus mixing the two is the normal case. An average MAE computed over it
without saying so would let the simulated trades' excursions stand for every
trade the owner ever took, which is the exact shape of false authority `SPEC`
§7 is written against. So every aggregate in this package reports the `n` that
actually contributed and names what did not.

**Win and loss are decided on realized net profit and loss**, the one figure
both sources produce. Not on the R multiple, which only one of them has. A
trade whose profit and loss is not stateable is `UNRESOLVED` and is counted as
neither — never as a loss, which is what a `None`-treated-as-zero would make
it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from fmis.accounts import Book, MarketId
from fmis.money import AssetCode, Money, canonical_decimal_text
from fmis.provenance import Absent, ValueOrigin
from fmis.records import (
    DomainValidationError,
    TradeDomainError,
    require_int,
    require_member,
    require_text,
    require_utc,
)
from fmis.snapshotting import TradeDirection

__all__ = [
    "StatisticsError",
    "StatisticsRefusedError",
    "StatSource",
    "TradeResult",
    "LifecyclePhase",
    "SamplePolicy",
    "DEFAULT_SAMPLE_POLICY",
    "SAMPLE_FLOOR_BASIS",
    "TradeStat",
    "STATISTICS_LIMITATIONS",
    "STATISTICS_POLICY_ID",
    "STATISTICS_POLICY_VERSION",
]

#: The named, versioned policy every reading in this package cites. A statistic
#: is arithmetic under a definition, and two definitions of "expectancy" that
#: disagree are worse than one that is merely arguable — so the definitions move
#: together, under one version, printed on every page.
STATISTICS_POLICY_ID = "fmits.statistics"
STATISTICS_POLICY_VERSION = 1


class StatisticsError(TradeDomainError):
    """Base class for every failure in this package."""


class StatisticsRefusedError(DomainValidationError, StatisticsError):
    """Inputs that cannot all be true at once, or a corpus that cannot be summed."""


class StatSource(Enum):
    """Which half of the system produced this trade's record.

    A dimension in its own right, because *"the figures I have about my paper
    trades"* and *"the figures I have about the money I actually moved"* are
    different populations, and a page that could not tell them apart would let
    the first speak for the second.
    """

    SIMULATED = "simulated"
    RECORDED = "recorded"


class TradeResult(Enum):
    """Won, lost, scratched, or not answerable yet.

    `UNRESOLVED` is a first-class member rather than an absence, for the reason
    `TradeDirection.NO_TRADE` is: *"still running"* and *"finished with a profit
    and loss nothing can state"* both mean **do not count this one**, and a
    reader who could not see them would read every count as complete.
    """

    WIN = "win"
    LOSS = "loss"
    SCRATCH = "scratch"
    UNRESOLVED = "unresolved"


class LifecyclePhase(Enum):
    """Where a trade stands, in the vocabulary the counts in the brief use.

    Deliberately **not** `TradeLifecycleState`, and deliberately not
    `CaptureStatus`: this is the union both sources fold into, and it exists so
    that *"how many did I cancel"* has one answer over a store holding both. The
    mapping from each source's own vocabulary is written once, in `collect`.
    """

    PENDING = "pending"
    TRIGGERED = "triggered"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    AMBIGUOUS = "ambiguous"


#: The phases in which exposure has ended and a result can be asked for.
FINISHED_PHASES: frozenset[LifecyclePhase] = frozenset({LifecyclePhase.CLOSED})

#: The phases in which the trade never held exposure and never will.
NEVER_EXPOSED_PHASES: frozenset[LifecyclePhase] = frozenset(
    {LifecyclePhase.CANCELLED, LifecyclePhase.EXPIRED}
)


#: Why the floor exists and what it is not. Printed beside every rate this
#: package refuses to render, because a guard whose reason is in a document is a
#: guard the reader resolves in favour of the number they wanted.
SAMPLE_FLOOR_BASIS = (
    "A floor, never a sufficiency claim. AP section 20.1 puts genuine "
    "conditional analysis at 5,000 resolved episodes and calls 100 'almost "
    "nothing statistically'. This floor marks only the point below which a rate "
    "is arithmetic about a handful of trades rather than a property of a "
    "process. Passing it establishes nothing."
)


@dataclass(frozen=True, slots=True)
class SamplePolicy:
    """The minimum `n` below which a rate is refused, and the reason it exists.

    `AP` §20.7 rule 2 requires the guard **at the boundary, so no surface can
    route around it**. Carrying it as a value that every reading holds — rather
    than as an `if` inside each statistic — is what makes that structural: a
    caller cannot compute a win rate without having named a floor, and every
    page prints the floor it used.

    The floor governs **rates and expectancies only**. A count is a fact at any
    `n`: *"you closed three trades and lost on all three"* is true, and refusing
    to say it would be a different dishonesty from overstating it.
    """

    minimum_sample: int = 30
    basis: str = SAMPLE_FLOOR_BASIS
    policy_id: str = STATISTICS_POLICY_ID
    policy_version: int = STATISTICS_POLICY_VERSION

    def __post_init__(self) -> None:
        require_int(self.minimum_sample, "minimum_sample", minimum=1)
        object.__setattr__(self, "basis", require_text(self.basis, "basis"))
        object.__setattr__(
            self, "policy_id", require_text(self.policy_id, "policy_id")
        )
        require_int(self.policy_version, "policy_version", minimum=1)

    def admits(self, sample_size: int) -> bool:
        """Whether a rate computed over this many observations may be stated."""
        require_int(sample_size, "sample_size", minimum=0)
        return sample_size >= self.minimum_sample

    def insufficient(self, subject: str, sample_size: int) -> Absent[Any]:
        """The refusal, carrying `n` — `AP` §20.3's `InsufficientSample(n)`."""
        return Absent(
            f"{subject} rests on {sample_size} observation(s), below the stated "
            f"floor of {self.minimum_sample}. {self.basis}",
            sample_size=sample_size,
        )


#: The floor in force when a caller names none.
DEFAULT_SAMPLE_POLICY = SamplePolicy()


def _maybe(value: Any, kind: type | tuple[type, ...], name: str) -> Any:
    if not isinstance(value, Absent) and not isinstance(value, kind):
        expected = (
            kind.__name__
            if isinstance(kind, type)
            else " or ".join(entry.__name__ for entry in kind)
        )
        raise TypeError(f"{name} must be a {expected} or Absent")
    return value


@dataclass(frozen=True, slots=True)
class TradeStat:
    """One trade, normalized. The unit every statistic in this package folds.

    A **projection** in `AP` §24.3's sense — delete every one of these, rebuild
    from the plan, the ledger, the lifecycle stream and the frozen outcome, and
    the answers are identical. Nothing here is written anywhere.

    The identifiers are two, not one: `trade_ref` is what the owner types to see
    this trade again, and `plan_id` is the commitment both sources hang off, so
    a simulated and a recorded trade against the same plan group together
    without either pretending to be the other.
    """

    trade_ref: str
    plan_id: str
    source: StatSource
    phase: LifecyclePhase
    market: MarketId
    book: Book
    direction: TradeDirection
    quote_asset: AssetCode
    committed_at: datetime
    opened_at: datetime | Absent = field(
        default_factory=lambda: Absent("this trade never held a position")
    )
    closed_at: datetime | Absent = field(
        default_factory=lambda: Absent("this trade has not closed")
    )
    realized_pnl_net: Money | Absent = field(
        default_factory=lambda: Absent("nothing has been realized")
    )
    realized_pnl_gross: Money | Absent = field(
        default_factory=lambda: Absent("nothing has been realized")
    )
    initial_risk: Money | Absent = field(
        default_factory=lambda: Absent("no entry to measure risk from")
    )
    r_multiple: Decimal | Absent = field(
        default_factory=lambda: Absent("no R multiple has been measured")
    )
    max_favourable_r: Decimal | Absent = field(
        default_factory=lambda: Absent("no excursion was frozen for this trade")
    )
    max_adverse_r: Decimal | Absent = field(
        default_factory=lambda: Absent("no excursion was frozen for this trade")
    )
    bars_held: int | Absent = field(
        default_factory=lambda: Absent("no bar count was frozen for this trade")
    )
    holding_time: timedelta | Absent = field(
        default_factory=lambda: Absent("this trade never held a position")
    )
    exit_reason: str | Absent = field(
        default_factory=lambda: Absent("this trade has not ended")
    )
    account: str | Absent = field(
        default_factory=lambda: Absent("no fill has named an account")
    )
    interval: str | Absent = field(
        default_factory=lambda: Absent("no timeframe is recorded for this trade")
    )
    setup_type: str | Absent = field(
        default_factory=lambda: Absent("no setup type was named on the plan")
    )
    regime_states: Mapping[str, str] = field(default_factory=dict)
    stop_moves: int = 0
    stop_widenings: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_ref", require_text(self.trade_ref, "trade_ref"))
        object.__setattr__(self, "plan_id", require_text(self.plan_id, "plan_id"))
        require_member(self.source, StatSource, "source")
        require_member(self.phase, LifecyclePhase, "phase")
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        require_member(self.book, Book, "book")
        require_member(self.direction, TradeDirection, "direction")
        if not isinstance(self.quote_asset, AssetCode):
            raise TypeError("quote_asset must be an AssetCode")
        object.__setattr__(
            self, "committed_at", require_utc(self.committed_at, "committed_at")
        )
        for name in ("opened_at", "closed_at"):
            value = _maybe(getattr(self, name), datetime, name)
            if not isinstance(value, Absent):
                object.__setattr__(self, name, require_utc(value, name))
        for name in ("realized_pnl_net", "realized_pnl_gross", "initial_risk"):
            _maybe(getattr(self, name), Money, name)
        for name in ("r_multiple", "max_favourable_r", "max_adverse_r"):
            _maybe(getattr(self, name), Decimal, name)
        bars = _maybe(self.bars_held, int, "bars_held")
        if not isinstance(bars, Absent):
            require_int(bars, "bars_held", minimum=0)
        _maybe(self.holding_time, timedelta, "holding_time")
        for name in ("exit_reason", "account", "interval", "setup_type"):
            value = _maybe(getattr(self, name), str, name)
            if not isinstance(value, Absent):
                object.__setattr__(self, name, require_text(value, name))
        if not isinstance(self.regime_states, Mapping):
            raise TypeError("regime_states must be a mapping of dimension to state")
        for key, value in self.regime_states.items():
            require_text(key, "regime dimension")
            require_text(value, f"regime state for {key}")
        object.__setattr__(
            self, "regime_states", MappingProxyType(dict(self.regime_states))
        )
        for name in ("stop_moves", "stop_widenings"):
            require_int(getattr(self, name), name, minimum=0)
        if self.stop_widenings > self.stop_moves:
            raise StatisticsRefusedError(
                "more stop moves widened than were made; a widening is one kind of "
                "move, not a separate count"
            )
        self._require_consistent()

    def _require_consistent(self) -> None:
        """The pairs of fields that cannot disagree without one of them lying."""
        opened = not isinstance(self.opened_at, Absent)
        closed = not isinstance(self.closed_at, Absent)
        if closed and not opened:
            raise StatisticsRefusedError(
                f"{self.trade_ref} states when it closed but not when it opened; a "
                "holding time derived from that pair would be measured from nothing"
            )
        if closed and self.closed_at < self.opened_at:
            raise StatisticsRefusedError(
                f"{self.trade_ref} closed before it opened"
            )
        if self.phase in NEVER_EXPOSED_PHASES and opened:
            raise StatisticsRefusedError(
                f"{self.trade_ref} is {self.phase.value} but records an opening "
                "instant; a trade that never held exposure has none"
            )

    # -- projections ---------------------------------------------------------

    @property
    def origin(self) -> ValueOrigin:
        """`MEASURED` over recorded inputs. This package asserts nothing."""
        return ValueOrigin.MEASURED

    @property
    def is_open(self) -> bool:
        return self.phase is LifecyclePhase.OPEN

    @property
    def is_closed(self) -> bool:
        return self.phase in FINISHED_PHASES

    @property
    def is_paper(self) -> bool:
        """Paper is a **book**, not a source.

        `AP` §5.5 makes the book the economic classification and
        `DEFAULT_EXCLUDED_BOOKS` already keeps it out of every real-money
        aggregate. A simulated fill in a real book, or an owner-recorded fill in
        the paper book, are both representable — so the two axes stay separate
        and this one follows the money.
        """
        return self.book is Book.PAPER

    @property
    def result(self) -> TradeResult:
        """Won, lost, scratched or unresolved — decided on realized net money.

        The one figure both sources produce. Deciding it on the R multiple would
        make every recorded trade unresolved, and deciding it on gross would
        report a trade whose fees ate the profit as a win.
        """
        if not self.is_closed or isinstance(self.realized_pnl_net, Absent):
            return TradeResult.UNRESOLVED
        if self.realized_pnl_net.amount > 0:
            return TradeResult.WIN
        if self.realized_pnl_net.amount < 0:
            return TradeResult.LOSS
        return TradeResult.SCRATCH

    @property
    def held_exposure(self) -> bool:
        return not isinstance(self.opened_at, Absent)

    @property
    def excursion_range_r(self) -> Decimal | Absent:
        """How far the trade travelled in total, in R, favourable plus adverse.

        `Absent` unless **both** extremes were frozen: a range computed from one
        of them is a smaller number that reads as a complete one.
        """
        if isinstance(self.max_favourable_r, Absent):
            return self.max_favourable_r
        if isinstance(self.max_adverse_r, Absent):
            return self.max_adverse_r
        return self.max_favourable_r + abs(self.max_adverse_r)

    @property
    def capture_efficiency(self) -> Decimal | Absent:
        """What the trade kept of the best it ever showed — `final R ÷ MFE in R`.

        `Absent` when the favourable excursion is zero rather than a division by
        it, and `Absent` when either half is unfrozen. A trade that never moved
        in the owner's favour has no efficiency to report; a zero there would
        read as *"captured none of a large move"*.
        """
        if isinstance(self.r_multiple, Absent):
            return self.r_multiple
        if isinstance(self.max_favourable_r, Absent):
            return self.max_favourable_r
        if self.max_favourable_r <= 0:
            return Absent(
                "this trade never traded in front of its entry, so there was no "
                "favourable excursion to capture a share of"
            )
        return self.r_multiple / self.max_favourable_r

    def risk_fraction_of(self, equity: Money | Absent) -> Decimal | Absent:
        """Initial risk as a fraction of a stated equity basis.

        The equity **at the time of the trade** is recorded nowhere in this
        system — no snapshot is written per trade — so the caller supplies one
        basis for the whole corpus and the page says which. That is a different
        and weaker statement than *"the risk I took as a share of what I had
        then"*, and calling it the same would be the quiet substitution this
        package exists to avoid.
        """
        if isinstance(self.initial_risk, Absent):
            return self.initial_risk
        if isinstance(equity, Absent):
            return Absent(
                "no equity basis was supplied, and this system records no equity "
                "at the time of a trade, so a risk percentage has no denominator"
            )
        if not isinstance(equity, Money):
            raise TypeError("equity must be a Money or Absent")
        if equity.asset != self.initial_risk.asset:
            return Absent(
                f"the equity basis is in {equity.asset.code} and this trade's risk "
                f"is in {self.initial_risk.asset.code}; this system holds no rate "
                "to cross them"
            )
        if equity.amount == 0:
            return Absent("an equity basis of zero has no fraction of it")
        return self.initial_risk.amount / equity.amount

    def to_payload(self) -> dict[str, Any]:
        """Exportable, with **no decoder** — a projection that could be read back
        would be a stored statistic, which `AP` §25.2 says this is not."""
        return {
            "trade_ref": self.trade_ref,
            "plan_id": self.plan_id,
            "source": self.source.value,
            "phase": self.phase.value,
            "result": self.result.value,
            "market": self.market.value,
            "book": self.book.value,
            "direction": self.direction.value,
            "quote_asset": self.quote_asset.code,
            "committed_at": self.committed_at.isoformat(),
            "opened_at": _instant(self.opened_at),
            "closed_at": _instant(self.closed_at),
            "realized_pnl_net": _money(self.realized_pnl_net),
            "realized_pnl_gross": _money(self.realized_pnl_gross),
            "initial_risk": _money(self.initial_risk),
            "r_multiple": _number(self.r_multiple),
            "max_favourable_r": _number(self.max_favourable_r),
            "max_adverse_r": _number(self.max_adverse_r),
            "bars_held": None if isinstance(self.bars_held, Absent) else self.bars_held,
            "holding_time_seconds": (
                None
                if isinstance(self.holding_time, Absent)
                else self.holding_time.total_seconds()
            ),
            "exit_reason": _plain(self.exit_reason),
            "account": _plain(self.account),
            "interval": _plain(self.interval),
            "setup_type": _plain(self.setup_type),
            "regime_states": dict(self.regime_states),
            "stop_moves": self.stop_moves,
            "stop_widenings": self.stop_widenings,
        }


def _instant(value: datetime | Absent) -> str | None:
    return None if isinstance(value, Absent) else value.isoformat()


def _money(value: Money | Absent) -> dict[str, Any] | None:
    return None if isinstance(value, Absent) else value.to_payload()


def _number(value: Decimal | Absent) -> str | None:
    return None if isinstance(value, Absent) else canonical_decimal_text(value)


def _plain(value: str | Absent) -> str | None:
    return None if isinstance(value, Absent) else value


#: What is wrong with every figure this package produces, stated on the page
#: rather than in this file. `AP` §20.1's own scaling table is the first of them
#: and the most important: the owner is funding a measurement, not harvesting an
#: edge, and the page has to say so while the sample is small.
STATISTICS_LIMITATIONS: tuple[tuple[str, str], ...] = (
    (
        "ST-1",
        "Every rate on these pages is refused below a stated sample floor, and "
        "passing that floor establishes nothing. AP section 20.1 puts genuine "
        "conditional analysis at 5,000 resolved trades. Below that, a rate is "
        "arithmetic about a handful of trades.",
    ),
    (
        "ST-2",
        "R multiples, maximum favourable and adverse excursions and bar counts "
        "exist only for simulated trades. A trade the owner recorded by hand has "
        "none of them, because AP section 25.3 requires an excursion to be frozen "
        "at close and nothing froze one. Every statistic over them reports the "
        "number of trades that actually contributed.",
    ),
    (
        "ST-3",
        "The equity curve is realized closed-trade profit and loss, not "
        "marked-to-market portfolio value. No mark history is retained by this "
        "system, so a marked equity curve cannot be reconstructed for any past "
        "instant. Drawdown is therefore drawdown of realized equity.",
    ),
    (
        "ST-4",
        "The owner's opening capital is recorded nowhere. Without a stated "
        "starting equity the curve is cumulative realized profit and loss, and "
        "the drawdown figures on it are absolute amounts rather than percentages.",
    ),
    (
        "ST-5",
        "Figures are never summed across quote assets. A store holding trades "
        "settled in two assets produces one set of figures per asset, and this "
        "system ingests no rate that would let it produce one.",
    ),
    (
        "ST-6",
        "Risk as a percentage uses one equity basis supplied for the whole "
        "corpus. The equity at the time of each trade is not recorded, so this is "
        "a weaker statement than 'the risk I took as a share of what I then had'.",
    ),
    (
        "ST-7",
        "Breakdowns apply no multiplicity correction. The number of cells "
        "examined is printed beside them, because with enough segmentations a "
        "striking-looking cell appears by arithmetic alone.",
    ),
    (
        "ST-8",
        "Calendar periods are UTC. The owner's local weekday and time of day are "
        "a dimension AP section 20.3 names and this milestone does not build.",
    ),
    (
        "ST-9",
        "Costs are whatever the fills recorded. A simulated trade carries the "
        "zero-cost paper policy by name, so its profit and loss is pre-fee and "
        "pre-slippage and is not comparable with a recorded trade's without "
        "saying so.",
    ),
    (
        "ST-10",
        "A quotient that does not terminate is printed to the full precision of "
        "the arithmetic rather than rounded, because shortening it would be a "
        "rounding policy this system does not set. Breakdown tables therefore "
        "show the division as a pair of counts, which is exact at any width.",
    ),
    (
        "ST-11",
        "Average capture efficiency is a mean of ratios and is dominated by "
        "trades whose favourable excursion was small: a trade that showed 0.1 R "
        "and lost 1 R contributes minus ten. The median is the more readable "
        "summary and both are shown.",
    ),
)
