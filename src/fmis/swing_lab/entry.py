"""Where a trade actually gets in. **Four rules, every one with a real fill.**

Milestone BX measured `entry_position_in_range` at a median of **0.537** — the
entry sits almost exactly halfway between its own stop and its own target — and
concluded the entry is *not* systematically late. That is a measurement of the
plan, not of the fill, and §7 of the BY brief asks the harder question: does
*when* a position is opened change the geometry it ends up with?

This module answers it with four pre-declared rules, and the rule that governs
all four is stated first because it is the one a backtest usually breaks:

> **Every entry price here is a price the market printed, at an instant strictly
> after the decision that asked for it.** There is no fill at the close that
> produced the signal, no fill at a price interpolated between two bars, and no
> "assume we got the midpoint". `fmis.paper.fills.fill_at_level` supplies the one
> non-market case — a resting limit — and it is the paper engine's own gap rule,
> called rather than restated.

=================================  ========================================================
`IMMEDIATE`                        the open of the bar after the signal — BW/BX's rule
`NEXT_BAR_CONTINUATION`            wait for one bar to close beyond the reference, then fill
`PULLBACK_LIMIT_AT_REFERENCE`      rest a limit at the decision price; fill only if reached
`ONE_HOUR_CONFIRMATION`            the same continuation test, on 1H candles
=================================  ========================================================

**A rule that does not fill is a result, not a gap.** `EntryMiss` is a named
outcome with a reason, and a study reports the miss rate beside the expectancy —
because a rule that improves the trades it takes by declining the ones that would
have lost is making a *selection* claim, and the two must be separable.

**`ONE_HOUR_CONFIRMATION` changes which series the outcome is walked over, and
that is deliberate.** An entry that fills partway through a 4H bar cannot have its
outcome measured against that whole bar: the bar's low may have occurred before
the fill, and a stop "hit" at a price the position did not yet exist at is a
fabricated loss. So the 1H rule declares `PathRole.REFINEMENT`, the walk runs on
1H candles, and the study runs `IMMEDIATE` on 1H as well — a control that
separates *the entry rule* from *the resolution it forced*.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Final

from fmis.paper.fills import fill_at_level
from fmis.paper.models import PriceBar
from fmis.snapshotting import TradeDirection
from fmis.swing_lab.models import SwingLabError
from fmis.swing_setup.models import Direction

__all__ = [
    "PULLBACK_VALID_BARS",
    "EntryRule",
    "PathRole",
    "EntryPolicy",
    "PRE_DECLARED_ENTRY_POLICIES",
    "MissReason",
    "EntryFill",
    "EntryMiss",
    "resolve_entry",
    "entry_policy_by_id",
]

#: How long a `PULLBACK_LIMIT_AT_REFERENCE` order rests, in execution bars. Six
#: 4H bars is one day — long enough that a normal retrace reaches it, short
#: enough that the thesis has not aged into a different market. Pre-declared and
#: **never swept**: a validity window chosen after seeing fill rates would be the
#: finding rather than a parameter of it.
PULLBACK_VALID_BARS: Final[int] = 6

_DIRECTION_TO_TRADE: Final[dict[Direction, TradeDirection]] = {
    Direction.LONG: TradeDirection.LONG,
    Direction.SHORT: TradeDirection.SHORT,
}


class EntryRule(str, Enum):
    """How the fill is obtained. Every member has deterministic historical semantics."""

    IMMEDIATE = "immediate"
    NEXT_BAR_CONTINUATION = "next_bar_continuation"
    PULLBACK_LIMIT_AT_REFERENCE = "pullback_limit_at_reference"
    ONE_HOUR_CONFIRMATION = "one_hour_confirmation"


class PathRole(str, Enum):
    """Which series a rule fills on, and therefore which series its outcome walks.

    `EXECUTION` is the setup's own execution timeframe — 4H under production.
    `REFINEMENT` is the rung below it. The distinction exists because a fill
    inside a coarse bar cannot be measured against that bar, and naming the
    consequence in the policy stops a study from pairing a 1H entry with a 4H
    outcome walk by accident.
    """

    EXECUTION = "execution"
    REFINEMENT = "refinement"


@dataclass(frozen=True, slots=True)
class EntryPolicy:
    """One pre-declared way of turning a confirmed setup into a fill."""

    policy_id: str
    title: str
    rule: EntryRule
    path: PathRole
    hypothesis: str
    valid_bars: int = PULLBACK_VALID_BARS

    def __post_init__(self) -> None:
        for name in ("policy_id", "title", "hypothesis"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SwingLabError(f"{name} must be a non-empty str")
        if not isinstance(self.rule, EntryRule):
            raise TypeError("rule must be an EntryRule")
        if not isinstance(self.path, PathRole):
            raise TypeError("path must be a PathRole")
        if isinstance(self.valid_bars, bool) or not isinstance(self.valid_bars, int):
            raise TypeError("valid_bars must be an int")
        if self.valid_bars <= 0:
            raise SwingLabError("valid_bars must be positive")
        if self.rule is EntryRule.ONE_HOUR_CONFIRMATION and self.path is not PathRole.REFINEMENT:
            raise SwingLabError(
                "ONE_HOUR_CONFIRMATION fills inside an execution bar, so its "
                "outcome must be walked on the refinement series; pairing it "
                "with PathRole.EXECUTION would measure a stop against a bar the "
                "position did not exist for"
            )

    @property
    def is_baseline(self) -> bool:
        return self.rule is EntryRule.IMMEDIATE and self.path is PathRole.EXECUTION

    def payload(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "title": self.title,
            "rule": self.rule.value,
            "path": self.path.value,
            "hypothesis": self.hypothesis,
            "valid_bars": self.valid_bars,
        }


PRE_DECLARED_ENTRY_POLICIES: Final[tuple[EntryPolicy, ...]] = (
    EntryPolicy(
        policy_id="entry_immediate",
        title="Market at the open of the next execution bar (control)",
        rule=EntryRule.IMMEDIATE,
        path=PathRole.EXECUTION,
        hypothesis=(
            "The rule Milestones BW and BX measured, unchanged. A CONTROL, not "
            "a candidate: it must reproduce simulate_trade's fill exactly, and "
            "if it does not, every entry comparison below is worthless."
        ),
    ),
    EntryPolicy(
        policy_id="entry_next_bar_continuation",
        title="Wait for one execution bar to close beyond the decision price",
        rule=EntryRule.NEXT_BAR_CONTINUATION,
        path=PathRole.EXECUTION,
        hypothesis=(
            "BX found 63.5% of trades resolved inside a single 4H bar, which is "
            "not swing trading. If the setup is being taken into immediate "
            "noise, requiring one bar to close in the thesis' own direction "
            "should remove the coin-flips. The cost is stated in advance and "
            "must be measured: the fill is one bar worse, so every surviving "
            "trade carries a wider risk and a nearer target."
        ),
    ),
    EntryPolicy(
        policy_id="entry_pullback_limit",
        title="Resting limit at the decision price, valid one day",
        rule=EntryRule.PULLBACK_LIMIT_AT_REFERENCE,
        path=PathRole.EXECUTION,
        hypothesis=(
            "The 'do not chase' rule. The decision was made at the reference "
            "price, so the order rests there rather than paying whatever the "
            "next open happens to be. This is the ONE rule here whose fill is "
            "not a printed trade of ours but an assumption that a touch fills a "
            "limit; it is reported with that assumption named, and its miss "
            "rate is reported beside its expectancy because a rule that only "
            "fills on retraces is also selecting which setups it takes."
        ),
    ),
    EntryPolicy(
        policy_id="entry_immediate_1h",
        title="Market at the next 1H open (resolution control)",
        rule=EntryRule.IMMEDIATE,
        path=PathRole.REFINEMENT,
        hypothesis=(
            "A CONTROL for entry_1h_confirmation, not a candidate. It takes the "
            "same setup at the same instant and differs only in walking the "
            "outcome on 1H candles. Any difference between this and "
            "entry_immediate is the RESOLUTION, not the entry rule — without it "
            "a 1H confirmation result cannot be attributed."
        ),
    ),
    EntryPolicy(
        policy_id="entry_1h_confirmation",
        title="Wait for one 1H bar to close beyond the decision price",
        rule=EntryRule.ONE_HOUR_CONFIRMATION,
        path=PathRole.REFINEMENT,
        hypothesis=(
            "The owner's timeframe hypothesis, in the only form the three-role "
            "engine can express it: 1W/1D/4H decide, and 1H refines the entry "
            "WITHOUT authority to reverse the thesis. It is the same "
            "continuation test as entry_next_bar_continuation at a quarter of "
            "the delay, so the pair separates 'confirmation helps' from "
            "'waiting a long time helps'."
        ),
    ),
)

_ENTRIES_BY_ID: Final[dict[str, EntryPolicy]] = {
    policy.policy_id: policy for policy in PRE_DECLARED_ENTRY_POLICIES
}

if len(_ENTRIES_BY_ID) != len(PRE_DECLARED_ENTRY_POLICIES):  # pragma: no cover
    raise SwingLabError("two pre-declared entry policies share a policy_id")


def entry_policy_by_id(policy_id: str) -> EntryPolicy:
    """Look one entry policy up by id, naming the alternatives when it is absent."""
    try:
        return _ENTRIES_BY_ID[policy_id]
    except KeyError:
        raise SwingLabError(
            f"no pre-declared entry policy {policy_id!r}; this milestone defines "
            f"{', '.join(sorted(_ENTRIES_BY_ID))}"
        ) from None


class MissReason(str, Enum):
    """Why a rule produced no fill. **Counted, never silently dropped.**"""

    NO_BARS_AFTER_SIGNAL = "no_bars_after_signal"
    CONTINUATION_NOT_CONFIRMED = "continuation_not_confirmed"
    LIMIT_NEVER_REACHED = "limit_never_reached"
    REFINEMENT_UNAVAILABLE = "refinement_unavailable"

    @property
    def statement(self) -> str:
        return _MISS_STATEMENTS[self]


_MISS_STATEMENTS: Final[dict[MissReason, str]] = {
    MissReason.NO_BARS_AFTER_SIGNAL: (
        "history ended before a fill could occur; a fact about the dataset, not "
        "about the rule"
    ),
    MissReason.CONTINUATION_NOT_CONFIRMED: (
        "the bar this rule waited on did not close beyond the decision price in "
        "the thesis' direction"
    ),
    MissReason.LIMIT_NEVER_REACHED: (
        "price never traded back to the decision price while the order rested"
    ),
    MissReason.REFINEMENT_UNAVAILABLE: (
        "the lower-timeframe series does not cover the instant this rule fills "
        "at; the rule is not measurable here and is not estimated"
    ),
}


@dataclass(frozen=True, slots=True)
class EntryFill:
    """A position opened, at a printed price, on a named bar of a named series."""

    index: int
    price: Decimal
    at: datetime
    interval: str
    bars_waited: int
    gapped: bool

    def __post_init__(self) -> None:
        if self.index < 0:
            raise SwingLabError("index must not be negative")
        if not isinstance(self.price, Decimal) or self.price <= 0:
            raise SwingLabError(f"price must be a positive Decimal, got {self.price!r}")


@dataclass(frozen=True, slots=True)
class EntryMiss:
    """A rule that declined or failed to fill, and the named reason."""

    reason: MissReason
    bars_waited: int

    @property
    def statement(self) -> str:
        return self.reason.statement


def _confirmed(bar: PriceBar, side: TradeDirection, reference: Decimal) -> bool:
    """Whether this bar CLOSED beyond the decision price in the thesis' direction.

    A close, not a touch: the whole point of a continuation test is that price
    finished the bar on the thesis' side, and a wick through the reference is
    exactly the noise the rule exists to decline.
    """
    return side.sign * (bar.close - reference) > 0


def _index_at_or_after(bars: Sequence[PriceBar], moment: datetime) -> int | None:
    for position, bar in enumerate(bars):
        if bar.open_time >= moment:
            return position
    return None


def resolve_entry(
    policy: EntryPolicy,
    *,
    path: Sequence[PriceBar],
    signal_at: datetime,
    signal_close_at: datetime,
    reference_price: Decimal,
    direction: Direction,
) -> EntryFill | EntryMiss:
    """Apply one entry rule and return a fill or a named refusal. **Pure and total.**

    ``path`` is the series the rule fills on — the execution series for
    `PathRole.EXECUTION`, the refinement series for `PathRole.REFINEMENT` — and
    ``signal_close_at`` is the instant the signal bar **closed**, which is the
    earliest moment any rule here may act. Passing the signal bar's *open* would
    be a four-hour lookahead, so the two instants are separate arguments and the
    boundary is asserted rather than derived from a convention.

    Deterministic and pure: no clock, no randomness, no network.

    Raises:
        TypeError: the arguments are not of the stated types. A market condition
            is never an exception here — it is an `EntryMiss`.
    """
    if not isinstance(policy, EntryPolicy):
        raise TypeError(f"policy must be an EntryPolicy, got {type(policy).__name__}")
    if direction not in _DIRECTION_TO_TRADE:
        raise SwingLabError(f"direction must be LONG or SHORT, got {direction!r}")
    if not isinstance(reference_price, Decimal) or reference_price <= 0:
        raise SwingLabError("reference_price must be a positive Decimal")
    if signal_close_at <= signal_at:
        raise SwingLabError(
            "signal_close_at must be after signal_at; a bar that closed before "
            "it opened is not a bar"
        )
    side = _DIRECTION_TO_TRADE[direction]

    # A series that begins AFTER this setup confirmed cannot fill it, and the
    # two causes are different facts: a refinement rung that does not reach back
    # this far is NOT MEASURABLE, while an execution series that does not is a
    # dataset shortfall. Reporting both as a lower-timeframe gap would blame the
    # 1H data for a 4H problem. Checked BEFORE the index lookup, because an
    # empty or late series makes that lookup return `None` and the distinction
    # would be lost behind a generic refusal.
    if not path or path[0].open_time > signal_close_at:
        return EntryMiss(
            reason=(
                MissReason.REFINEMENT_UNAVAILABLE
                if policy.path is PathRole.REFINEMENT
                else MissReason.NO_BARS_AFTER_SIGNAL
            ),
            bars_waited=0,
        )
    start = _index_at_or_after(path, signal_close_at)
    if start is None:
        return EntryMiss(reason=MissReason.NO_BARS_AFTER_SIGNAL, bars_waited=0)

    if policy.rule is EntryRule.IMMEDIATE:
        bar = path[start]
        return EntryFill(
            index=start, price=bar.open, at=bar.open_time,
            interval=bar.interval, bars_waited=0, gapped=False,
        )

    if policy.rule in (EntryRule.NEXT_BAR_CONTINUATION, EntryRule.ONE_HOUR_CONFIRMATION):
        watched = path[start]
        if not _confirmed(watched, side, reference_price):
            return EntryMiss(reason=MissReason.CONTINUATION_NOT_CONFIRMED, bars_waited=1)
        if start + 1 >= len(path):
            return EntryMiss(reason=MissReason.NO_BARS_AFTER_SIGNAL, bars_waited=1)
        bar = path[start + 1]
        return EntryFill(
            index=start + 1, price=bar.open, at=bar.open_time,
            interval=bar.interval, bars_waited=1, gapped=False,
        )

    # PULLBACK_LIMIT_AT_REFERENCE: a resting order, filled by the paper engine's
    # own gap rule. `favourable=False` because a buy limit for a long waits for
    # price to come DOWN to it, which is the adverse side of the trade.
    for offset in range(policy.valid_bars):
        position = start + offset
        if position >= len(path):
            return EntryMiss(reason=MissReason.NO_BARS_AFTER_SIGNAL, bars_waited=offset)
        bar = path[position]
        if not bar.reached(side, reference_price, favourable=False):
            continue
        price, gapped = fill_at_level(side, bar, reference_price, favourable=False)
        return EntryFill(
            index=position, price=price, at=bar.open_time,
            interval=bar.interval, bars_waited=offset, gapped=gapped,
        )
    return EntryMiss(reason=MissReason.LIMIT_NEVER_REACHED, bars_waited=policy.valid_bars)
