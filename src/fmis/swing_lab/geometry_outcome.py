"""After-the-fact measurements. **Nothing here may ever reach a decision.**

`fmis.swing_lab.geometry` promises that a geometry policy cannot read forward,
and it keeps that promise by holding no bar and no outcome. This module is where
the forward-looking measurements live instead — the ones §2 and §6 of the
milestone brief ask for and that cannot be answered without looking past the
decision instant:

* did price reach +0.5R / +1R / +1.5R / +2R **before** the trade ended;
* after a stop-out, did price then go on to reach the original target;
* which came first, the favourable excursion or the adverse one.

**The isolation is architectural, not a convention.** This module imports no
policy and no variant; `fmis.swing_lab.geometry` and
`fmis.swing_lab.geometry_variants` import nothing from here, and an architecture
guard asserts both directions. A `GeometryOutcome` is produced *from* a plan and
a trade and can never be an input to either. MFE and MAE are outcome statistics
and the type system is arranged so they cannot become admission criteria.

**Post-exit measurement is bounded by the evaluation window, not by hindsight.**
"Did the thesis eventually work" is unanswerable — *eventually* has no end. The
question this module answers is the bounded one: within the same evaluation
window the trade itself was given, did price reach the original target after the
stop was hit? A different bound would give a different answer, so the bound
travels on the result.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from fmis.paper.models import PriceBar
from fmis.snapshotting import TradeDirection
from fmis.swing_lab.geometry import GeometryPlan
from fmis.swing_lab.models import LabExitReason, LabTrade, SwingLabError
from fmis.swing_setup.models import Direction

__all__ = [
    "R_THRESHOLDS",
    "GeometryOutcome",
    "measure_outcome",
]

#: The R multiples the brief asks to be counted, where deterministically
#: measurable. Read from the excursion the trade already recorded, never from a
#: second walk over the bars — two walks could disagree about a touch.
R_THRESHOLDS: Final[tuple[Decimal, ...]] = (
    Decimal("0.5"), Decimal("1.0"), Decimal("1.5"), Decimal("2.0"),
)

_DIRECTION_TO_TRADE: Final[dict[Direction, TradeDirection]] = {
    Direction.LONG: TradeDirection.LONG,
    Direction.SHORT: TradeDirection.SHORT,
}


@dataclass(frozen=True, slots=True)
class GeometryOutcome:
    """What happened to one planned trade, measured only after it was planned."""

    policy_id: str
    symbol: str
    setup_id: str
    #: Which of `R_THRESHOLDS` the favourable excursion reached before the exit.
    reached_r: tuple[Decimal, ...]
    #: ``mfe_r - net_r``: how much of the best price seen was given back. Absent
    #: when the trade carries no R at all (ambiguous, or never entered).
    unrealised_giveback_r: Decimal | None
    #: For a stop-out only: did price reach the ORIGINAL target later in the same
    #: evaluation window? ``None`` when the trade did not stop out, so "no" and
    #: "not applicable" can never be counted together.
    target_reached_after_stop: bool | None
    #: Bars from the stop-out to that touch, when it happened.
    bars_from_stop_to_target: int | None
    #: Which came first at a half-R magnitude — ``"favourable"``, ``"adverse"``,
    #: ``"neither"``, or ``None`` when the trade has no risk denominator.
    first_half_r_excursion: str | None
    evaluation_window_bars: int

    @property
    def gave_back_a_full_r(self) -> bool:
        """Whether at least 1R of open profit was surrendered before the exit."""
        return (
            self.unrealised_giveback_r is not None
            and self.unrealised_giveback_r >= Decimal("1")
        )


def _first_half_r(
    bars: Sequence[PriceBar], side: TradeDirection, entry: Decimal, risk: Decimal
) -> str:
    """Which half-R magnitude a bar reached first, walking forward from the entry.

    A bar whose range covers both is reported as ``"neither"`` — the same refusal
    `fmis.swing_lab.trades` makes for a bar that touches the stop and the target
    together, and for the same reason: four prices cannot order an intrabar path,
    and guessing would answer the entry-quality question by coin flip.
    """
    threshold = risk / 2
    for bar in bars:
        favourable = side.sign * (bar.favourable_extreme(side) - entry) >= threshold
        adverse = side.sign * (bar.adverse_extreme(side) - entry) <= -threshold
        if favourable and adverse:
            return "neither"
        if favourable:
            return "favourable"
        if adverse:
            return "adverse"
    return "neither"


def measure_outcome(
    plan: GeometryPlan,
    trade: LabTrade,
    bars: Sequence[PriceBar],
    *,
    evaluation_window_bars: int,
) -> GeometryOutcome:
    """Measure one completed trade against its own plan. **Pure and deterministic.**

    ``bars`` is the symbol's full decoded series; the window examined is the same
    one the trade was given, starting at the bar after the signal. No bar outside
    that window is read, so a study run with a different window bound cannot be
    compared against this one — which is why the bound travels on the result.

    Raises:
        SwingLabError: the plan and the trade describe different setups, which
            would silently measure one trade against another's geometry.
    """
    if not isinstance(plan, GeometryPlan):
        raise TypeError("plan must be a GeometryPlan")
    if not isinstance(trade, LabTrade):
        raise TypeError("trade must be a LabTrade")
    if plan.candidate.setup_id != trade.setup_id or plan.candidate.symbol != trade.symbol:
        raise SwingLabError(
            f"plan describes {plan.candidate.symbol}/{plan.candidate.setup_id} but "
            f"the trade describes {trade.symbol}/{trade.setup_id}"
        )
    if (
        isinstance(evaluation_window_bars, bool)
        or not isinstance(evaluation_window_bars, int)
        or evaluation_window_bars <= 0
    ):
        raise SwingLabError("evaluation_window_bars must be a positive int")

    reached = (
        ()
        if trade.mfe_r is None
        else tuple(item for item in R_THRESHOLDS if trade.mfe_r >= item)
    )
    giveback = (
        None if trade.mfe_r is None or trade.net_r is None else trade.mfe_r - trade.net_r
    )

    side = _DIRECTION_TO_TRADE[trade.direction]
    signal_index = plan.candidate.signal_index
    window = bars[signal_index + 1 : signal_index + 1 + evaluation_window_bars]

    first_excursion: str | None = None
    if trade.entry_price is not None and trade.bars_held:
        risk = side.sign * (trade.entry_price - trade.initial_stop)
        if risk > 0:
            first_excursion = _first_half_r(
                window[: trade.bars_held], side, trade.entry_price, risk
            )

    # Did the thesis pay off after the stop took it out? Only asked of trades
    # that actually stopped out, and only inside the window the trade already
    # had — an unbounded "eventually" is not a measurable question.
    after_stop: bool | None = None
    bars_to_target: int | None = None
    if trade.exit_reason is LabExitReason.STOP and trade.bars_held:
        after_stop = False
        for offset, bar in enumerate(window[trade.bars_held :], start=1):
            if bar.reached(side, trade.target, favourable=True):
                after_stop = True
                bars_to_target = offset
                break

    return GeometryOutcome(
        policy_id=plan.policy_id,
        symbol=trade.symbol,
        setup_id=trade.setup_id,
        reached_r=reached,
        unrealised_giveback_r=giveback,
        target_reached_after_stop=after_stop,
        bars_from_stop_to_target=bars_to_target,
        first_half_r_excursion=first_excursion,
        evaluation_window_bars=evaluation_window_bars,
    )
