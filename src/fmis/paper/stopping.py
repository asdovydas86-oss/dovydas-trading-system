"""Break-even and trailing: the two stop rules, and the one law they obey.

> **A rule this system applies may only ever tighten the stop.**

Widening is the owner's own act, reaches the store as an `ASSERTED` amendment
carrying their own reason, and is counted by `StopHistory.widening_count`.
`fold_stop_history` refuses a `POLICY_DERIVED` amendment that widened, so the law
is enforced twice — once here where the move is derived, and once at read time
where a store containing one would otherwise be quietly measured.

**Both rules are stated in R, not in price units.** A price offset needs the
market's tick size, which is venue reference data this domain declines to hold,
and an offset typed in the wrong instrument's units is invisible until it has
already moved a stop somewhere it should not be. `R` is the initial risk distance
the trade was sized against, so *"break even plus a tenth of the risk"* means the
same thing on BTC and on a memecoin.

**The trail follows the excursion the outcome freezes**, not a second extreme
accumulated separately. One definition of *"the best price this trade saw"*, so a
trailing stop and the `MFE` printed beside it can never disagree.

**When both rules fire on one bar the tighter wins, and only one move is
recorded.** Two amendments on one candle would give the stop history two entries
for one decision, and `AP` §20.5's widening counter would start reading the number
of *rules enabled* rather than the number of *moves made*.
"""

from __future__ import annotations

from decimal import Decimal

from fmis.provenance import Absent
from fmis.records import require_member
from fmis.snapshotting import TradeDirection
from fmis.trade_lifecycle import BREAK_EVEN_TERM, TRAILING_TERM, StopManagement
from fmis.paper.models import Excursion, PaperRefusedError, StopMoveIntent

__all__ = [
    "break_even_stop",
    "trailing_stop",
    "derive_stop_move",
]


def _require_distance(risk_distance: object) -> Decimal:
    if not isinstance(risk_distance, Decimal):
        raise TypeError(
            f"risk_distance must be a Decimal, got {type(risk_distance).__name__}"
        )
    if risk_distance <= 0:
        raise PaperRefusedError(
            "a stop rule stated in R needs a positive risk distance; without one "
            "every multiple of it is undefined rather than zero"
        )
    return risk_distance


def break_even_stop(
    management: StopManagement,
    direction: TradeDirection,
    *,
    entry_price: Decimal,
    risk_distance: Decimal,
    excursion: Excursion,
) -> Decimal | Absent:
    """Where break-even would put the stop, or why it does not apply yet.

    The trigger is measured against the **maximum favourable excursion**, not the
    latest close: a trade that reached the trigger and came back has already been
    that far in front, and re-testing it against the current price would move the
    stop back and forth as a function of where each bar happened to close.
    """
    if not isinstance(management, StopManagement):
        raise TypeError("management must be a StopManagement")
    require_member(direction, TradeDirection, "direction")
    rule = management.break_even
    if isinstance(rule, Absent):
        return Absent("no break-even rule was stated")
    if isinstance(excursion.favourable, Absent):
        return Absent("no bar has been observed while exposed")
    distance = _require_distance(risk_distance)
    reached = direction.sign * (excursion.favourable - entry_price)
    if reached < rule.trigger_r * distance:
        return Absent(
            "the trade has not reached the break-even trigger this activation "
            "stated"
        )
    return entry_price + direction.sign * rule.offset_r * distance


def trailing_stop(
    management: StopManagement,
    direction: TradeDirection,
    *,
    entry_price: Decimal,
    risk_distance: Decimal,
    excursion: Excursion,
) -> Decimal | Absent:
    """Where the trail would put the stop, or why it does not apply yet."""
    if not isinstance(management, StopManagement):
        raise TypeError("management must be a StopManagement")
    require_member(direction, TradeDirection, "direction")
    rule = management.trailing
    if isinstance(rule, Absent):
        return Absent("no trailing rule was stated")
    if isinstance(excursion.favourable, Absent):
        return Absent("no bar has been observed while exposed")
    distance = _require_distance(risk_distance)
    if not isinstance(rule.activate_at_r, Absent):
        reached = direction.sign * (excursion.favourable - entry_price)
        if reached < rule.activate_at_r * distance:
            return Absent(
                "the trade has not reached the level this activation stated the "
                "trail should start from"
            )
    return excursion.favourable - direction.sign * rule.distance_r * distance


def derive_stop_move(
    management: StopManagement,
    direction: TradeDirection,
    *,
    entry_price: Decimal,
    risk_distance: Decimal,
    effective_stop: Decimal,
    excursion: Excursion,
) -> StopMoveIntent | Absent:
    """The single move both rules together justify, or the reason there is none.

    The tighter of the two wins, a move that would loosen is discarded rather than
    applied, and at most one intent is returned — so the stop history holds one
    move per bar and the widening counter keeps counting moves rather than rules.
    """
    candidates: list[tuple[Decimal, str]] = []
    for level, term in (
        (
            break_even_stop(
                management,
                direction,
                entry_price=entry_price,
                risk_distance=risk_distance,
                excursion=excursion,
            ),
            BREAK_EVEN_TERM.term_id,
        ),
        (
            trailing_stop(
                management,
                direction,
                entry_price=entry_price,
                risk_distance=risk_distance,
                excursion=excursion,
            ),
            TRAILING_TERM.term_id,
        ),
    ):
        if isinstance(level, Absent):
            continue
        if direction.sign * (level - effective_stop) > 0:
            candidates.append((level, term))
    if not candidates:
        return Absent("no stop rule the owner enabled would tighten the stop here")
    tightest, term_id = candidates[0]
    for level, term in candidates[1:]:
        if direction.sign * (level - tightest) > 0:
            tightest, term_id = level, term
    return StopMoveIntent(
        previous_stop=effective_stop, new_stop=tightest, term_id=term_id
    )
