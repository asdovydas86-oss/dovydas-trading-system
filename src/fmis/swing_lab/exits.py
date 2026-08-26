"""Exit management, measured rather than assumed. **Four mechanics, no threshold mining.**

Milestone BX measured that **68.8 % of trades gave back at least a full R of open
profit** and then declined to test any fix, because
`fmis.swing_lab.trades.simulate_trade` resolves exactly one stop against exactly
one target and a partial exit adds a third level to bars it already could not
order. `fmis.swing_lab.intrabar` removes that obstacle with real lower-timeframe
candles, so the question is now answerable — and this module answers it with the
**smallest** set of rules that can, because the brief is explicit that ten
trailing variants would be threshold mining rather than research.

===========================  ==========================================================
`FULL_TARGET`                the control: BW/BX's own rule, one stop and one target
`PARTIAL_AT_1R`              half off at +1R, the remainder to the structural target
`BREAK_EVEN_AT_1R`           the stop moves to the entry once +1R has been reached
`TRAIL_PRIOR_BAR_EXTREME`    once armed at +1R, the stop trails the prior bar's extreme
===========================  ==========================================================

**One convention decides what these numbers mean, and it is stated rather than
buried: a state change takes effect from the bar AFTER the bar that triggered
it.** A break-even stop armed by a bar's high is not also tested against that
same bar's low, because four prices cannot say whether the low came before or
after the high, and `fmis.swing_lab.intrabar` exists precisely so this module
never guesses. Where the ladder *can* order two events — the bar touched both the
trigger and the stop — the walk descends to 1H, then 15m, and only then refuses.
The convention therefore applies at the **finest resolution the data supports**,
not at 4H.

**What is deliberately absent.**

* No trailing threshold is swept. `TRAIL_PRIOR_BAR_EXTREME` arms at +1R because
  that is the same number `PARTIAL_AT_1R` and `BREAK_EVEN_AT_1R` use — the R at
  which BX measured the give-back — not because 1R won a comparison.
* No mechanic may *widen* a stop. Every state change tightens or exits, and the
  loop asserts it: a "management" rule that moved a stop away from the entry
  would be improving a losing trade's odds by taking more risk than the plan
  declared, which is not exit management.
* No mechanic reads a level this module derived. The structural stop and target
  arrive from `fmis.swing_lab.geometry`, already selected.

**The partial exit and `LabTrade` are exactly compatible, which is why no new
metrics layer exists.** A trade leaving in two pieces at prices ``p1`` and ``p2``
with weights ``f`` and ``1-f`` has gross return ``sign × (f·p1 + (1-f)·p2 − e)``
and fees ``rate × (e + f·p1 + (1-f)·p2)``. Both are functions of the
notional-weighted average exit alone, so recording that average as
`LabTrade.exit_price` reproduces the leg arithmetic **exactly** — and
`fmis.swing_lab.trades.reprice` then costs a partial-exit trade correctly without
knowing it was one. A test asserts the identity leg-by-leg rather than trusting
the algebra here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Final

from fmis.paper.fills import fill_at_level
from fmis.paper.models import PriceBar
from fmis.snapshotting import TradeDirection
from fmis.swing_lab.intrabar import BarLadder, TouchLevel
from fmis.swing_lab.models import LabExitReason, LabTrade, SwingLabError
from fmis.swing_setup.models import Direction
from fmis.trade_lifecycle import PaperCostPolicy

__all__ = [
    "ARMING_R",
    "DEFAULT_PARTIAL_FRACTION",
    "ExitMechanic",
    "ExitPolicy",
    "PRE_DECLARED_EXIT_POLICIES",
    "ExitLeg",
    "ManagedResult",
    "simulate_managed_trade",
    "exit_policy_by_id",
]

#: The R multiple at which every managed mechanic arms. **One number, shared.**
#: Using the same arming point for the partial, the break-even and the trail is
#: what keeps this a comparison of *mechanics* rather than a sweep of a
#: threshold: three rules that differ only in what they do at +1R can be read
#: against each other, and three rules that also differ in *when* cannot.
ARMING_R: Final[Decimal] = Decimal("1")

#: How much of the position `PARTIAL_AT_1R` realises. Half, pre-declared, never
#: swept: a fraction chosen after seeing results would be the whole finding.
DEFAULT_PARTIAL_FRACTION: Final[Decimal] = Decimal("0.5")

_DIRECTION_TO_TRADE: Final[dict[Direction, TradeDirection]] = {
    Direction.LONG: TradeDirection.LONG,
    Direction.SHORT: TradeDirection.SHORT,
}

_STOP: Final[str] = "stop"
_TARGET: Final[str] = "target"
_ARM: Final[str] = "arm"


class ExitMechanic(str, Enum):
    """How an open position is managed between the entry and a terminal exit."""

    FULL_TARGET = "full_target"
    PARTIAL_AT_1R = "partial_at_1r"
    BREAK_EVEN_AT_1R = "break_even_at_1r"
    TRAIL_PRIOR_BAR_EXTREME = "trail_prior_bar_extreme"

    @property
    def arms(self) -> bool:
        """Whether this mechanic watches for `ARMING_R` at all."""
        return self is not ExitMechanic.FULL_TARGET


@dataclass(frozen=True, slots=True)
class ExitPolicy:
    """One pre-declared exit mechanic, with the only parameter any of them takes."""

    policy_id: str
    title: str
    mechanic: ExitMechanic
    hypothesis: str
    partial_fraction: Decimal = DEFAULT_PARTIAL_FRACTION

    def __post_init__(self) -> None:
        for name in ("policy_id", "title", "hypothesis"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SwingLabError(f"{name} must be a non-empty str")
        if not isinstance(self.mechanic, ExitMechanic):
            raise TypeError("mechanic must be an ExitMechanic")
        if not isinstance(self.partial_fraction, Decimal):
            raise TypeError("partial_fraction must be a Decimal")
        if not Decimal(0) < self.partial_fraction < Decimal(1):
            raise SwingLabError(
                "partial_fraction must lie strictly between 0 and 1, got "
                f"{self.partial_fraction}; 0 and 1 are the two mechanics that "
                "already have their own names"
            )

    @property
    def is_baseline(self) -> bool:
        return self.mechanic is ExitMechanic.FULL_TARGET

    def payload(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "title": self.title,
            "mechanic": self.mechanic.value,
            "hypothesis": self.hypothesis,
            "partial_fraction": str(self.partial_fraction),
        }


PRE_DECLARED_EXIT_POLICIES: Final[tuple[ExitPolicy, ...]] = (
    ExitPolicy(
        policy_id="exit_full_target",
        title="Full position to the structural target (control)",
        mechanic=ExitMechanic.FULL_TARGET,
        hypothesis=(
            "The rule Milestones BW and BX measured, unchanged: one stop, one "
            "target, no management. A CONTROL, not a candidate. Run over the "
            "same ladder as every other mechanic so the comparison isolates "
            "management rather than resolution — and run a second time WITHOUT "
            "a ladder, where it must reproduce simulate_trade exactly."
        ),
    ),
    ExitPolicy(
        policy_id="exit_partial_1r",
        title="Half off at +1R, remainder to the structural target",
        mechanic=ExitMechanic.PARTIAL_AT_1R,
        hypothesis=(
            "BX measured 68.8% of trades giving back a full R of open profit "
            "and 85.7% of target exits paying under +1R. If the target is "
            "systematically too near, realising half the position at +1R should "
            "convert some of that give-back into a booked return. The risk this "
            "rule runs is the one that must be reported beside its expectancy: "
            "it halves the position before every large winner too, so a "
            "positive-tail strategy can be made worse by it."
        ),
    ),
    ExitPolicy(
        policy_id="exit_break_even_1r",
        title="Stop to break-even once +1R is reached",
        mechanic=ExitMechanic.BREAK_EVEN_AT_1R,
        hypothesis=(
            "The cheapest possible answer to the give-back finding: keep the "
            "whole position, but refuse to let a trade that was a full R ahead "
            "become a full R loss. It cannot improve a winner and cannot "
            "worsen the entry; it can only convert some losers into scratches "
            "and some winners into scratches, and which of those dominates is "
            "exactly what is being measured."
        ),
    ),
    ExitPolicy(
        policy_id="exit_trail_prior_bar",
        title="Trail the prior execution bar's extreme once armed at +1R",
        mechanic=ExitMechanic.TRAIL_PRIOR_BAR_EXTREME,
        hypothesis=(
            "The only trailing rule tested, and it is deliberately the dumbest "
            "one that is fully deterministic: once +1R has been reached, the "
            "stop becomes the previous CLOSED execution-timeframe bar's adverse "
            "extreme and never loosens. It is NOT a structural trail — the "
            "prior bar's low is a price, not a level the structural engines "
            "produced — and it is labelled that way wherever it is reported."
        ),
    ),
)

_EXITS_BY_ID: Final[dict[str, ExitPolicy]] = {
    policy.policy_id: policy for policy in PRE_DECLARED_EXIT_POLICIES
}

if len(_EXITS_BY_ID) != len(PRE_DECLARED_EXIT_POLICIES):  # pragma: no cover
    raise SwingLabError("two pre-declared exit policies share a policy_id")


def exit_policy_by_id(policy_id: str) -> ExitPolicy:
    """Look one exit policy up by id, naming the alternatives when it is absent."""
    try:
        return _EXITS_BY_ID[policy_id]
    except KeyError:
        raise SwingLabError(
            f"no pre-declared exit policy {policy_id!r}; this milestone defines "
            f"{', '.join(sorted(_EXITS_BY_ID))}"
        ) from None


@dataclass(frozen=True, slots=True)
class ExitLeg:
    """One piece of a position leaving, at one price, for one named reason."""

    fraction: Decimal
    price: Decimal
    at: datetime
    reason: LabExitReason
    interval: str

    def payload(self) -> dict[str, object]:
        return {
            "fraction": str(self.fraction),
            "price": str(self.price),
            "at": self.at.isoformat(),
            "reason": self.reason.value,
            "interval": self.interval,
        }


@dataclass(frozen=True, slots=True)
class ManagedResult:
    """One managed trade, plus how much lower-timeframe evidence it consumed."""

    trade: LabTrade
    legs: tuple[ExitLeg, ...]
    descents: int
    ambiguous_bar_at: datetime | None
    armed_at: datetime | None


@dataclass(slots=True)
class _State:
    """Everything the walk mutates. Separated so the loop reads as a state machine."""

    side: TradeDirection
    entry: Decimal
    risk: Decimal
    stop: Decimal
    target: Decimal
    policy: ExitPolicy
    armed: bool = False
    armed_at: datetime | None = None
    remaining: Decimal = Decimal(1)
    legs: list[ExitLeg] = field(default_factory=list)
    descents: int = 0

    @property
    def arming_price(self) -> Decimal:
        return self.entry + self.side.sign * ARMING_R * self.risk

    def levels(self) -> tuple[TouchLevel, ...]:
        watched = [
            TouchLevel(name=_STOP, price=self.stop, favourable=False),
            TouchLevel(name=_TARGET, price=self.target, favourable=True),
        ]
        if self.policy.mechanic.arms and not self.armed:
            price = self.arming_price
            # The arming price can coincide with the target when the structural
            # objective pays exactly 1R. Watching two levels at one price would
            # be permanent, unresolvable ambiguity invented by this module, so
            # the arming level is dropped: the target is the stronger event and
            # reaching it ends the trade anyway.
            if price != self.target:
                watched.append(TouchLevel(name=_ARM, price=price, favourable=True))
        return tuple(watched)

    def tighten(self, price: Decimal) -> None:
        """Move the stop toward the entry, never away from it. Asserted, not assumed."""
        if self.side.sign * (price - self.stop) < 0:
            raise SwingLabError(
                f"an exit mechanic tried to move the stop from {self.stop} to "
                f"{price}, which is further from the entry; management may only "
                "tighten or exit"
            )
        self.stop = price

    def close(self, fraction: Decimal, price: Decimal, at: datetime, reason: LabExitReason, interval: str) -> None:
        self.legs.append(
            ExitLeg(fraction=fraction, price=price, at=at, reason=reason, interval=interval)
        )
        self.remaining -= fraction


class _Step(str, Enum):
    CONTINUE = "continue"
    TERMINAL = "terminal"
    AMBIGUOUS = "ambiguous"


def _apply(state: _State, level: TouchLevel, bar: PriceBar, price: Decimal) -> _Step:
    """One resolved touch, turned into a state change or a terminal exit."""
    if level.name == _TARGET:
        state.close(state.remaining, price, bar.open_time, LabExitReason.TARGET, bar.interval)
        return _Step.TERMINAL
    if level.name == _STOP:
        state.close(state.remaining, price, bar.open_time, LabExitReason.STOP, bar.interval)
        return _Step.TERMINAL

    state.armed = True
    state.armed_at = bar.open_time
    mechanic = state.policy.mechanic
    if mechanic is ExitMechanic.PARTIAL_AT_1R:
        # A resting limit at +1R: it fills at its own price when touched, which
        # is what `fill_at_level` returns unless the bar gapped past it.
        state.close(
            state.policy.partial_fraction, price, bar.open_time,
            LabExitReason.TARGET, bar.interval,
        )
        return _Step.CONTINUE
    if mechanic is ExitMechanic.BREAK_EVEN_AT_1R:
        state.tighten(state.entry)
        return _Step.CONTINUE
    # TRAIL_PRIOR_BAR_EXTREME arms here and moves at each execution-bar
    # boundary; there is no prior bar inside this bar to trail to yet.
    return _Step.CONTINUE


def _process(
    bar: PriceBar, state: _State, ladder: BarLadder | None, depth: int
) -> _Step:
    """Resolve every event inside one bar, descending the ladder only when it must.

    **A state change takes effect from the next bar at this resolution.** A single
    resolved touch therefore returns `CONTINUE` rather than re-examining the same
    bar: re-testing a freshly armed break-even stop against the same bar's low
    would compare it to a price that may have occurred *before* the high that
    armed it, which is the exact intrabar guess this package refuses to make. The
    descent below is what recovers the resolution that convention costs.
    """
    levels = state.levels()
    hits = [
        level for level in levels
        if bar.reached(state.side, level.price, favourable=level.favourable)
    ]
    if not hits:
        return _Step.CONTINUE
    if len(hits) == 1:
        price, _ = fill_at_level(state.side, bar, hits[0].price, favourable=hits[0].favourable)
        state.descents = max(state.descents, depth)
        return _apply(state, hits[0], bar, price)

    # Two or more levels in one bar. A level the bar OPENED beyond was reached at
    # the bar's first price and nothing inside it can have preceded that; several
    # such levels are past the open simultaneously and cannot be ordered at all.
    opened = [
        level for level in hits
        if bar.opened_beyond(state.side, level.price, favourable=level.favourable)
    ]
    if len(opened) == 1:
        price, _ = fill_at_level(
            state.side, bar, opened[0].price, favourable=opened[0].favourable
        )
        state.descents = max(state.descents, depth)
        return _apply(state, opened[0], bar, price)
    if len(opened) > 1:
        return _Step.AMBIGUOUS

    finer = None if ladder is None else ladder.refine(bar)
    if finer is None:
        return _Step.AMBIGUOUS
    _, window = finer
    for inner in window:
        step = _process(inner, state, ladder, depth + 1)
        if step is not _Step.CONTINUE:
            return step
    return _Step.CONTINUE


def _weighted_exit(legs: Sequence[ExitLeg]) -> Decimal:
    """The notional-weighted average exit price. The whole reason no new type exists."""
    return sum((leg.fraction * leg.price for leg in legs), start=Decimal(0))


def simulate_managed_trade(
    bars: Sequence[PriceBar],
    *,
    variant_id: str,
    symbol: str,
    setup_id: str,
    direction: Direction,
    entry_index: int,
    entry_price: Decimal,
    entry_at: datetime,
    signal_at: datetime,
    reference_price: Decimal,
    stop_price: Decimal,
    target_price: Decimal,
    planned_risk_reward: float,
    window_bars: int,
    costs: PaperCostPolicy,
    policy: ExitPolicy,
    ladder: BarLadder | None = None,
    segment: str | None = None,
    context_regime_structure: str = "",
    context_structural_trend: str = "",
    setup_structural_trend: str = "",
) -> ManagedResult:
    """Walk an already-entered trade under one exit mechanic.

    ``entry_index`` is the position of the bar the entry filled **on**, and
    ``entry_price`` its fill — both decided by `fmis.swing_lab.entry`, never here.
    Separating them is what lets an entry rule and an exit mechanic be measured
    independently rather than as one compound change.

    Deterministic and pure: no clock, no randomness, no network. The ladder is
    already-fetched history.

    Raises:
        SwingLabError: the geometry is unusable, or the ladder and the coarse
            bars disagree about a span.
    """
    if isinstance(window_bars, bool) or not isinstance(window_bars, int) or window_bars <= 0:
        raise SwingLabError("window_bars must be a positive int")
    if not isinstance(costs, PaperCostPolicy):
        raise TypeError("costs must be a PaperCostPolicy")
    if not isinstance(policy, ExitPolicy):
        raise TypeError("policy must be an ExitPolicy")
    if direction not in _DIRECTION_TO_TRADE:
        raise SwingLabError(f"direction must be LONG or SHORT, got {direction!r}")
    if entry_index < 0 or entry_index >= len(bars):
        raise SwingLabError("entry_index must address a bar in the series")
    side = _DIRECTION_TO_TRADE[direction]

    def _record(
        exit_price: Decimal | None,
        exit_at: datetime | None,
        reason: LabExitReason,
        held: int,
        gross: Decimal | None,
        net: Decimal | None,
        mfe: Decimal | None,
        mae: Decimal | None,
        state: _State | None,
        ambiguous_at: datetime | None,
    ) -> ManagedResult:
        legs = () if state is None else tuple(state.legs)
        return ManagedResult(
            trade=LabTrade(
                variant_id=variant_id, symbol=symbol, setup_id=setup_id,
                direction=direction, signal_at=signal_at, entry_at=entry_at,
                entry_price=entry_price, initial_stop=stop_price, target=target_price,
                planned_reference_price=reference_price, exit_at=exit_at,
                exit_price=exit_price, exit_reason=reason, bars_held=held,
                gross_r=gross, net_r=net, mfe_r=mfe, mae_r=mae,
                cost_policy_id=costs.policy_id,
                planned_risk_reward=planned_risk_reward, segment=segment,
                context_regime_structure=context_regime_structure,
                context_structural_trend=context_structural_trend,
                setup_structural_trend=setup_structural_trend,
                metadata={
                    "exit_policy_id": policy.policy_id,
                    "exit_mechanic": policy.mechanic.value,
                    "legs": [leg.payload() for leg in legs],
                },
            ),
            legs=legs,
            descents=0 if state is None else state.descents,
            ambiguous_bar_at=ambiguous_at,
            armed_at=None if state is None else state.armed_at,
        )

    risk = side.sign * (entry_price - stop_price)
    if risk <= 0:
        # The entry is already at or beyond the stop. Recorded as a full loss at
        # the fill, exactly as `simulate_trade` does — never skipped, because
        # skipping deletes precisely the worst fills.
        return _record(
            entry_price, entry_at, LabExitReason.ENTRY_GAPPED_THROUGH_STOP, 0,
            Decimal("-1"), Decimal("-1"), Decimal("0"), Decimal("0"), None, None,
        )
    if side.sign * (target_price - entry_price) <= 0:
        return _record(None, None, LabExitReason.NO_ENTRY_BAR, 0, None, None, None, None, None, None)

    state = _State(
        side=side, entry=entry_price, risk=risk, stop=stop_price,
        target=target_price, policy=policy,
    )
    window = bars[entry_index : entry_index + window_bars]
    best = worst = entry_price
    previous: PriceBar | None = None
    held = 0
    ambiguous_at: datetime | None = None
    step = _Step.CONTINUE

    for position, bar in enumerate(window, start=1):
        held = position
        if (
            state.armed
            and policy.mechanic is ExitMechanic.TRAIL_PRIOR_BAR_EXTREME
            and previous is not None
        ):
            candidate = previous.adverse_extreme(side)
            # Only ever tighten. A prior bar whose extreme sits beyond the
            # current stop is ignored rather than obeyed.
            if side.sign * (candidate - state.stop) > 0:
                state.tighten(candidate)
        favourable = bar.favourable_extreme(side)
        adverse = bar.adverse_extreme(side)
        if side.sign * (favourable - best) > 0:
            best = favourable
        if side.sign * (adverse - worst) < 0:
            worst = adverse
        step = _process(bar, state, ladder, 0)
        if step is _Step.AMBIGUOUS:
            ambiguous_at = bar.open_time
            break
        if step is _Step.TERMINAL:
            break
        previous = bar
    else:
        step = _Step.CONTINUE

    mfe = side.sign * (best - entry_price) / risk
    mae = side.sign * (worst - entry_price) / risk

    if step is _Step.AMBIGUOUS:
        return _record(
            None, ambiguous_at, LabExitReason.AMBIGUOUS_SAME_BAR, held,
            None, None, mfe, mae, state, ambiguous_at,
        )

    if step is not _Step.TERMINAL:
        if not window:  # pragma: no cover - entry_index addresses a bar
            return _record(None, None, LabExitReason.NO_ENTRY_BAR, 0, None, None, None, None, state, None)
        last = window[-1]
        state.close(
            state.remaining, last.close, last.open_time, LabExitReason.TIME_STOP, last.interval
        )

    legs = tuple(state.legs)
    average = _weighted_exit(legs)
    gross = side.sign * (average - entry_price)
    fees = costs.fee_rate * (entry_price + average)
    final = legs[-1]
    return _record(
        average, final.at, final.reason, held,
        gross / risk, (gross - fees) / risk, mfe, mae, state, None,
    )
