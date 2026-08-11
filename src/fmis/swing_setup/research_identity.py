"""Cross-variant opportunity lineage — research bookkeeping, not a trading concept.

**The problem AV's identity cannot solve.** `fmis.swing_setup.backtest_identity`
keys a setup on `Trigger.level.origin.index`, and that index is *window-relative*:
the analysis window slides forward one candle per instant, so a fixed swing's
index falls by one every bar. The identity therefore changes every bar even when
nothing about the market has. Measured over a real 400-day BTCUSDT run, **every
single directional observation reports ``is_new_setup=True``** — 48 of 48 — so
AV's "unique setups" count is really a count of directional bars, and its
"first confirmation" flag fires on essentially every confirmed bar rather than
once per setup.

**The rule used here instead.** An *opportunity* is a maximal run of consecutive
observations for one symbol that carry the same `Direction`, uninterrupted by a
`WAIT` or a direction flip. Its key is the symbol, the direction, and the
instant the run began.

That rule has the one property cross-variant comparison actually requires:
**it is invariant to the confirmation-age override.** The override changes only
`break_is_stale`, which decides `CONFIRMED` versus `CANDIDATE`
(`policy.py`). It cannot change whether a direction exists — that is settled
earlier, by the decision-context gate, the context-role regime gate and the
family tally, none of which the override touches. So two variants replayed over
the same candles decompose history into exactly the same opportunities, and a
reader can ask "did *this* opportunity confirm later, or not at all?" rather
than only "were there fewer confirmations?".

This is research lineage and nothing more. It defines no trading object, is
never read by the live product, and makes no claim that one run of directional
bars is one trade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from fmis.swing_setup.models import Direction, SetupState

__all__ = ["opportunity_key", "OpportunityTracker"]


def opportunity_key(symbol: str, direction: Direction | None, started_at: datetime) -> str | None:
    """The deterministic key of one directional run, or ``None`` for `WAIT`.

    Two calls with equal arguments return an equal string, always. ``started_at``
    is the run's *first* observation instant, never the current one, which is
    what makes the key stable for the run's whole life.
    """
    if direction is None:
        return None
    return f"{symbol}|{direction.value}|from={started_at.isoformat()}"


@dataclass(slots=True)
class _ActiveOpportunity:
    key: str
    direction: Direction
    started_at: datetime
    confirmed_already: bool = False


@dataclass(slots=True)
class OpportunityTracker:
    """Walks one symbol's observations in chronological order, stateful by design.

    Call `observe` once per replayed instant, strictly in increasing instant
    order, one symbol at a time. Symbols are isolated: an opportunity is never
    compared across two of them.
    """

    _active: dict[str, _ActiveOpportunity] = field(default_factory=dict)

    def reset(self, symbol: str) -> None:
        """Forget ``symbol``'s active opportunity, e.g. before replaying it again."""
        self._active.pop(symbol, None)

    def observe(
        self,
        symbol: str,
        direction: Direction | None,
        status: SetupState,
        instant: datetime,
    ) -> tuple[str | None, bool, bool]:
        """Classify one observation against this symbol's running opportunity.

        Returns ``(key, is_new_opportunity, is_first_confirmation)``:

        * ``key`` — `opportunity_key`'s result, or ``None`` for `WAIT`.
        * ``is_new_opportunity`` — ``True`` exactly on the run's first bar.
        * ``is_first_confirmation`` — ``True`` exactly once per run: the first
          bar at which it reaches `CONFIRMED`. This is what keeps one
          opportunity from being outcome-evaluated many times, and it is the
          flag AV's index-based identity could not deliver.

        A `WAIT` clears the symbol's active opportunity: the policy stopped
        standing behind the thesis, so a later return is a new occurrence. A
        direction flip likewise starts a new one.
        """
        if direction is None:
            self._active.pop(symbol, None)
            return None, False, False

        active = self._active.get(symbol)
        is_new = active is None or active.direction is not direction
        if is_new:
            active = _ActiveOpportunity(
                key=opportunity_key(symbol, direction, instant),
                direction=direction,
                started_at=instant,
            )
            self._active[symbol] = active

        is_first_confirmation = False
        if status is SetupState.CONFIRMED and not active.confirmed_already:
            active.confirmed_already = True
            is_first_confirmation = True

        return active.key, is_new, is_first_confirmation
