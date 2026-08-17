"""Driving the engine over a sequence of bars — the fold, and nothing more.

`replay_bars` is `advance` applied in order until the trade stops being live or
the bars run out. That is the whole of it, and the smallness is the point: the
same function drives a historical replay, a live run over newly closed candles and
a future shadow-mode run, because the only thing that differs between them is
where the bars came from.

**It stops rather than continuing past a halt.** A trade that reached
`AMBIGUOUS` is waiting for the owner, not for the next bar, and feeding it more
candles would require inventing the intrabar order the engine has just refused to
invent.

**It writes nothing and reads nothing.** No store, no clock, no provider. What
comes back is a value, and `fmis.paper.compose` decides what to do with it — which
is why a replay can be exercised in a test with six hand-built bars and no
filesystem at all.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from fmis.provenance import Absent
from fmis.records import require_tuple_of, require_utc
from fmis.trade_lifecycle import TradeLifecycleState
from fmis.paper.engine import advance
from fmis.paper.models import Fill, LifecycleStep, PriceBar, StepResult, TradeRunState

__all__ = ["ReplayResult", "replay_bars"]


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Every step one replay produced, and the state it left the trade in."""

    final_state: TradeRunState
    results: tuple[StepResult, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.final_state, TradeRunState):
            raise TypeError("final_state must be a TradeRunState")
        require_tuple_of(self.results, StepResult, "results")

    @property
    def bars_advanced(self) -> int:
        return len(self.results)

    @property
    def changed(self) -> bool:
        """Whether any bar produced something worth writing."""
        return any(result.changed for result in self.results)

    @property
    def steps(self) -> tuple[LifecycleStep, ...]:
        return tuple(step for result in self.results for step in result.steps)

    @property
    def fills(self) -> tuple[Fill, ...]:
        return tuple(fill for result in self.results for fill in result.fills)

    @property
    def halted(self) -> bool:
        return self.final_state.state is TradeLifecycleState.AMBIGUOUS

    @property
    def last_bar(self) -> PriceBar | Absent:
        if not self.results:
            return Absent("this replay advanced no bar")
        return self.results[-1].bar


def replay_bars(
    state: TradeRunState,
    bars: Iterable[PriceBar],
    *,
    owner_moves: Iterable[tuple[datetime, Decimal]] = (),
) -> ReplayResult:
    """Advance one trade through bars in order, stopping when it stops being live.

    Deterministic and total: the same state, the same bars and the same owner
    moves produce the same result, and a bar that changes nothing still costs one
    step with an empty step list rather than being skipped — so *"the engine
    looked at this candle and had nothing to say"* and *"the engine never saw
    it"* stay different facts.

    **`owner_moves` are stop amendments the owner already made and the store
    already holds.** They are applied to the run at the first bar that opened at
    or after each one, and they emit nothing: the record exists, and a replay that
    wrote it again would count one decision twice in the widening metric. The
    engine's own rules then continue from the stop the owner left, which is what
    makes *"I moved my stop and the trail took over from there"* replay correctly.
    """
    if not isinstance(state, TradeRunState):
        raise TypeError(f"state must be a TradeRunState, got {type(state).__name__}")
    pending = sorted(_validated_moves(owner_moves), key=lambda move: move[0])
    current = state
    results: list[StepResult] = []
    for bar in bars:
        if current.state not in {
            TradeLifecycleState.PENDING,
            TradeLifecycleState.TRIGGERED,
            TradeLifecycleState.OPEN,
            TradeLifecycleState.PARTIALLY_EXITED,
        }:
            break
        while pending and pending[0][0] <= bar.open_time:
            current = replace(current, effective_stop=pending.pop(0)[1])
        result = advance(current, bar)
        results.append(result)
        current = result.next_state
    return ReplayResult(final_state=current, results=tuple(results))


def _validated_moves(
    moves: Iterable[tuple[datetime, Decimal]]
) -> tuple[tuple[datetime, Decimal], ...]:
    """Each move unpacked by name, so a mis-shaped pair fails here and not later.

    Unpacked rather than length-checked: a `ValueError` from the unpacking says
    the same thing, and this package holds no numeric literal beyond `0` and `1`
    — a rule a hand-written arity check would be the only exception to.
    """
    checked: list[tuple[datetime, Decimal]] = []
    for move in moves:
        if not isinstance(move, tuple):
            raise TypeError("each owner move is an (instant, stop) pair")
        try:
            when, stop = move
        except ValueError as error:
            raise TypeError(
                "each owner move is an (instant, stop) pair"
            ) from error
        checked.append((require_utc(when, "owner move instant"), stop))
    return tuple(checked)
