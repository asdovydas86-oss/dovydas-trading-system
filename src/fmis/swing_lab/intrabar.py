"""Ordering two events inside one bar, using **real lower-timeframe candles**.

Milestone BX classified richer exit management as NOT MEASURABLE, and the reason
was precise rather than defeatist: `fmis.swing_lab.trades.simulate_trade` halts a
4H bar that reached both the stop and the target as `AMBIGUOUS_SAME_BAR`, because
four prices cannot say which came first. Adding a third level — a partial exit at
+1R — multiplies those cases instead of resolving them.

This module resolves them the only honest way: **by looking at the same span at a
finer resolution the provider actually has.** A 4H bar that touched both levels is
four 1H bars; usually only one of them touched either level, and the ordering is
then a fact rather than an assumption. When a 1H bar still contains both, the
ladder descends to 15m. When the finest available resolution still contains both,
the event stays `AMBIGUOUS` and is counted as such — **never guessed**.

**Two rules this module exists to obey.**

1. **Lower-timeframe data resolves an OUTCOME and never informs a DECISION.**
   Nothing here is reachable from `fmis.swing_lab.geometry` or
   `fmis.swing_lab.geometry_variants`, and an architecture guard asserts it. A
   `BarLadder` is handed to the simulator, never to a policy. The 1H series is
   consulted strictly *after* an entry exists, over the span the trade was
   already exposed for, and it can change **when** a level was hit — never
   whether the setup was taken, in which direction, or with which stop.
2. **Ordering is never inferred.** Two facts are used, both of which four prices
   genuinely contain: a bar that reached only one level reached that one, and a
   bar that **opened beyond** a level had already reached it at its first price
   (`fmis.paper.models.PriceBar.opened_beyond` — the repository reached this
   conclusion independently for the paper engine). Everything else descends or
   stays ambiguous.

**Why 1H before 15m.** Each rung costs a fetch and four times the rows. The ladder
is ordered coarsest-first and descends only for the bars that actually need it,
so the 15m series is requested for a handful of spans rather than for years.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Final

from fmis.paper.fills import fill_at_level
from fmis.paper.models import PriceBar
from fmis.snapshotting import TradeDirection
from fmis.swing_lab.models import SwingLabError
from fmis.swing_setup.research_models import interval_duration

__all__ = [
    "TouchLevel",
    "TouchKind",
    "Touch",
    "BarLadder",
    "AmbiguityLedger",
    "bars_within",
    "first_touch",
]


@dataclass(frozen=True, slots=True)
class TouchLevel:
    """One price a walk is watching for, and which side of the trade it sits on.

    ``favourable`` is the paper engine's own vocabulary: a target is favourable,
    a stop is not, and the flag decides which extreme of a bar is compared. It is
    carried rather than inferred from the price, because a break-even stop and a
    partial-exit target can both sit on the same side of the entry and only the
    caller knows which is which.
    """

    name: str
    price: Decimal
    favourable: bool

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise SwingLabError("name must be a non-empty str")
        if not isinstance(self.price, Decimal):
            raise TypeError("price must be a Decimal")
        if self.price <= 0:
            raise SwingLabError(f"price must be positive, got {self.price}")
        if not isinstance(self.favourable, bool):
            raise TypeError("favourable must be a bool")


class TouchKind(str, Enum):
    """How a walk ended.

    `AMBIGUOUS` is a **refusal**, exactly as `LabExitReason.AMBIGUOUS_SAME_BAR`
    is: the finest resolution available still held two levels in one bar, and no
    ordering can be stated. It is counted, reported, and never resolved by
    guessing.
    """

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Touch:
    """Which level was reached first, where it filled, and at what resolution.

    ``interval`` and ``descents`` are carried so a result can state *how much
    lower-timeframe evidence it needed*. A study reporting "we resolved 40 of 44
    ambiguous bars" must be able to say which rung did the work, because a
    resolution that only ever happens at 15m is a different claim about data
    availability from one that happens at 1H.
    """

    kind: TouchKind
    level: TouchLevel | None
    bar: PriceBar | None
    fill_price: Decimal | None
    gapped: bool
    interval: str | None
    descents: int

    @property
    def is_resolved(self) -> bool:
        return self.kind is TouchKind.RESOLVED


#: A walk that reached nothing at all, in any resolution.
_NO_TOUCH: Final[Touch] = Touch(
    kind=TouchKind.NONE,
    level=None,
    bar=None,
    fill_price=None,
    gapped=False,
    interval=None,
    descents=0,
)


@dataclass(frozen=True, slots=True)
class BarLadder:
    """One symbol's history at several resolutions, **coarsest first**.

    The ladder is the whole of this module's access to market data, and it is
    given to the simulator rather than assembled by it. ``rungs`` is validated to
    be strictly descending in bar duration at construction, because a ladder
    accidentally ordered fine-to-coarse would "descend" to a *longer* bar and
    manufacture ambiguity rather than resolve it — a failure that would look like
    a data problem in every report it reached.
    """

    symbol: str
    rungs: tuple[tuple[str, tuple[PriceBar, ...]], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise SwingLabError("symbol must be a non-empty str")
        if not self.rungs:
            raise SwingLabError("a ladder needs at least one rung")
        durations = [interval_duration(interval) for interval, _ in self.rungs]
        for finer, coarser in zip(durations[1:], durations[:-1], strict=True):
            if finer >= coarser:
                raise SwingLabError(
                    "ladder rungs must be strictly coarsest-first; "
                    f"{[interval for interval, _ in self.rungs]} is not"
                )
        for interval, bars in self.rungs:
            previous = None
            for bar in bars:
                if bar.symbol != self.symbol:
                    raise SwingLabError(
                        f"ladder for {self.symbol} holds a {bar.symbol} bar on "
                        f"the {interval} rung"
                    )
                # Ordering is validated ONCE here rather than on every
                # `bars_within` call: an unsorted rung would make the binary
                # search return a wrong slice silently, and paying O(n) per
                # search to catch it defeated the search.
                if previous is not None and bar.open_time < previous:
                    raise SwingLabError(
                        f"the {interval} rung of {self.symbol} is not ordered by "
                        f"open_time at {bar.open_time.isoformat()}"
                    )
                previous = bar.open_time

    @property
    def intervals(self) -> tuple[str, ...]:
        return tuple(interval for interval, _ in self.rungs)

    def finer_than(self, interval: str) -> tuple[str, tuple[PriceBar, ...]] | None:
        """The next rung below ``interval``, or ``None`` at the bottom of the ladder."""
        for position, (name, _) in enumerate(self.rungs):
            if name == interval:
                if position + 1 >= len(self.rungs):
                    return None
                return self.rungs[position + 1]
        raise SwingLabError(
            f"this ladder holds no {interval!r} rung; it holds "
            f"{', '.join(self.intervals)}"
        )

    def refine(self, bar: PriceBar) -> tuple[str, tuple[PriceBar, ...]] | None:
        """The finer bars covering one bar's span, or ``None`` when unavailable.

        ``None`` covers both reasons a descent can fail — the ladder has no finer
        rung, and the finer rung has a **gap** over this span — and they are the
        same fact to a caller: the ordering cannot be established. A partial
        cover is refused rather than walked, because a 4H span covered by three
        of its four 1H bars could place a level's first touch in the missing one.
        """
        below = self.finer_than(bar.interval)
        if below is None:
            return None
        interval, bars = below
        span = interval_duration(bar.interval)
        step = interval_duration(interval)
        window = bars_within(bars, bar.open_time, bar.open_time + span)
        if len(window) * step != span:
            return None
        return interval, window


def bars_within(
    bars: Sequence[PriceBar], start: datetime, end: datetime
) -> tuple[PriceBar, ...]:
    """Every bar whose open lies in ``[start, end)``, by binary search.

    **Precondition: ``bars`` is ordered by ``open_time``.** `BarLadder` validates
    that once, at construction, for every rung it holds — which is where the
    check belongs, because `refine` calls this once per multi-level bar against
    the complete finer series. The first version re-validated the whole sequence
    on every call: an O(n) scan and an O(n) key list in front of an O(log n)
    search, run thousands of times over ~26k 1H rows, which made the documented
    bisect decorative.
    """
    if end < start:
        raise SwingLabError("end must not precede start")
    times = _KeyView(bars)
    return tuple(bars[bisect_left(times, start) : bisect_right(times, end - _TICK)])


class _KeyView(Sequence):
    """A zero-copy ``open_time`` view, so `bisect` needs no materialised key list."""

    __slots__ = ("_bars",)

    def __init__(self, bars: Sequence[PriceBar]) -> None:
        self._bars = bars

    def __len__(self) -> int:
        return len(self._bars)

    def __getitem__(self, index):  # type: ignore[no-untyped-def]
        return self._bars[index].open_time


#: The smallest gap that keeps ``[start, end)`` half-open under `bisect_right`.
#: A bar opening exactly at ``end`` belongs to the *next* span, never this one.
_TICK: Final[timedelta] = timedelta(microseconds=1)


def _touched(bar: PriceBar, side: TradeDirection, levels: Sequence[TouchLevel]) -> list[TouchLevel]:
    return [
        level
        for level in levels
        if bar.reached(side, level.price, favourable=level.favourable)
    ]


def _opened_beyond(
    bar: PriceBar, side: TradeDirection, levels: Sequence[TouchLevel]
) -> list[TouchLevel]:
    return [
        level
        for level in levels
        if bar.opened_beyond(side, level.price, favourable=level.favourable)
    ]


def _resolve_bar(
    bar: PriceBar,
    side: TradeDirection,
    levels: Sequence[TouchLevel],
    ladder: BarLadder | None,
    descents: int,
) -> Touch:
    """Order the levels one bar reached, descending the ladder only if it must."""
    hits = _touched(bar, side, levels)
    if not hits:
        return _NO_TOUCH
    if len(hits) == 1:
        price, gapped = fill_at_level(side, bar, hits[0].price, favourable=hits[0].favourable)
        return Touch(
            kind=TouchKind.RESOLVED,
            level=hits[0],
            bar=bar,
            fill_price=price,
            gapped=gapped,
            interval=bar.interval,
            descents=descents,
        )

    # Two or more levels in one bar. The one fact four prices contain: a level
    # the bar OPENED beyond was reached at the bar's first price, so nothing
    # inside the bar can have preceded it. When several were opened beyond, the
    # open is past all of them simultaneously and no ordering exists between
    # them — that is genuine ambiguity and descending cannot fix it either.
    opened = _opened_beyond(bar, side, hits)
    if len(opened) == 1:
        price, gapped = fill_at_level(
            side, bar, opened[0].price, favourable=opened[0].favourable
        )
        return Touch(
            kind=TouchKind.RESOLVED,
            level=opened[0],
            bar=bar,
            fill_price=price,
            gapped=gapped,
            interval=bar.interval,
            descents=descents,
        )
    if len(opened) > 1:
        return Touch(
            kind=TouchKind.AMBIGUOUS, level=None, bar=bar, fill_price=None,
            gapped=False, interval=bar.interval, descents=descents,
        )

    finer = None if ladder is None else ladder.refine(bar)
    if finer is None:
        return Touch(
            kind=TouchKind.AMBIGUOUS, level=None, bar=bar, fill_price=None,
            gapped=False, interval=bar.interval, descents=descents,
        )
    _, window = finer
    for inner in window:
        result = _resolve_bar(inner, side, levels, ladder, descents + 1)
        if result.kind is not TouchKind.NONE:
            return result
    # The finer bars cover the same span, so one of them must contain the touch
    # the coarse bar recorded. Reaching here means the two rungs disagree about
    # the same span, which is a provider fault and is refused rather than
    # smoothed over.
    raise SwingLabError(
        f"{bar.symbol} {bar.interval} bar opening {bar.open_time.isoformat()} "
        f"reached {', '.join(level.name for level in hits)} but none of its "
        f"{len(window)} finer bars did; the two series disagree"
    )


def first_touch(
    path: Sequence[PriceBar],
    *,
    side: TradeDirection,
    levels: Sequence[TouchLevel],
    ladder: BarLadder | None = None,
) -> Touch:
    """Walk ``path`` and return the first level reached, descending when needed.

    Deterministic and pure: no clock, no randomness, no network. The ladder is
    already-fetched history, and two calls with equal arguments return an equal
    `Touch`.

    ``ladder`` may be ``None``, which is the **control**: with no ladder this
    reproduces `fmis.swing_lab.trades.simulate_trade`'s own resolution exactly,
    up to the one extra fact it does not use (`opened_beyond`). Milestone BY's
    baseline runs both so the effect of the lower-timeframe evidence is measured
    rather than assumed.

    Raises:
        SwingLabError: a coarse bar and its finer cover disagree, or the levels
            are not distinct by name.
    """
    if not levels:
        raise SwingLabError("at least one level must be watched")
    names = [level.name for level in levels]
    if len(set(names)) != len(names):
        raise SwingLabError(f"level names must be distinct, got {names}")
    for bar in path:
        result = _resolve_bar(bar, side, levels, ladder, 0)
        if result.kind is not TouchKind.NONE:
            return result
    return _NO_TOUCH


@dataclass(slots=True)
class AmbiguityLedger:
    """How much lower-timeframe evidence a study actually needed, and what it bought.

    Kept as a mutable tally rather than derived at the end because the events it
    counts are discovered one at a time deep inside a walk, and threading a
    return value out of every recursion to count them would change the walk's
    shape for a bookkeeping reason.
    """

    encountered: int = 0
    resolved: int = 0
    unresolved: int = 0
    by_interval: dict[str, int] = field(default_factory=dict)

    def record(self, touch: Touch) -> None:
        if touch.descents == 0 and touch.kind is not TouchKind.AMBIGUOUS:
            return
        self.encountered += 1
        if touch.kind is TouchKind.AMBIGUOUS:
            self.unresolved += 1
            return
        self.resolved += 1
        interval = touch.interval or "unknown"
        self.by_interval[interval] = self.by_interval.get(interval, 0) + 1

    def payload(self) -> Mapping[str, object]:
        return {
            "encountered": self.encountered,
            "resolved": self.resolved,
            "unresolved": self.unresolved,
            "resolved_by_interval": dict(sorted(self.by_interval.items())),
        }


#: Callable shape a caller may substitute for a ladder in a test. Named so the
#: signature of a stub is checked by the type reader rather than by a comment.
RefineFn = Callable[[PriceBar], "tuple[str, tuple[PriceBar, ...]] | None"]
