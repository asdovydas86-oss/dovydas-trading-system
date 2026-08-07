"""Deterministic setup identity — telling one persisting setup from a new one.

A `CANDIDATE`/`CONFIRMED` result can repeat, unchanged in substance, across
many consecutive historical bars: the policy re-reads the same structural
level every time it is asked, because nothing about the market has moved on
from it yet. Counting every repeated bar as an independent observation would
inflate sample size and double-count a single trade idea as many.

**The identity rule, stated once.** Two observations for the same symbol are
the *same* setup when they agree on direction and on the structural level
being watched or that confirmed them — read from `Trigger.level.origin`, the
same swing-point provenance `fmis.level_crossing.LevelOrigin` already
carries. A different level, a direction flip, or an intervening `WAIT` all
start a new identity. This is deliberately the smallest rule the historical
observations already support: no clustering, no price-proximity heuristic, no
new structural concept.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fmis.swing_setup.models import Direction, SetupState, Trigger

__all__ = ["setup_identity", "IdentityTracker"]


def setup_identity(symbol: str, direction: Direction | None, trigger: Trigger | None) -> str | None:
    """The deterministic identity of a directional candidate, or ``None`` for `WAIT`.

    Built from `trigger.level.origin` — the confirming (`CONFIRMED`) or
    watched (`CANDIDATE`) structural level's own swing-point index and label,
    the same reference `fmis.swing_setup.policy` already selected. Two calls
    with equal arguments return an equal string, always.

    Falls back to the level's own price when it carries no ``origin`` (a
    level built from the earliest, unlabelled swing — ADR-0019 D2), and
    further to a direction-only key when no level is available at all (an
    `AWAITING_STRUCTURE_BREAK` trigger in a window with no candidate level).
    Both fallbacks are named explicitly in the harness's own limitations:
    identity in either case cannot distinguish two genuinely different setups
    that happen to share a price or to both lack a level.
    """
    if direction is None:
        return None
    if trigger is None or trigger.level is None:
        return f"{symbol}|{direction.value}|no-level"
    level = trigger.level
    if level.origin is not None:
        return (
            f"{symbol}|{direction.value}|{level.side.value}|"
            f"origin={level.origin.index}:{level.origin.label.value}"
        )
    return f"{symbol}|{direction.value}|{level.side.value}|price={level.price!r}"


@dataclass(slots=True)
class _ActiveSetup:
    setup_id: str
    confirmed_already: bool = False


@dataclass(slots=True)
class IdentityTracker:
    """Walks one symbol's observations in chronological order, stateful by design.

    Call `observe` once per historical instant, strictly in increasing
    ``as_of`` order, for one symbol at a time — the harness owns that
    ordering; this class only tracks what it is told. A separate tracker (or
    a call to `reset`) is required per symbol: identity is never compared
    across symbols.
    """

    _active: dict[str, _ActiveSetup] = field(default_factory=dict)

    def reset(self, symbol: str) -> None:
        """Forget ``symbol``'s active setup, e.g. before replaying it from the start."""
        self._active.pop(symbol, None)

    def observe(
        self,
        symbol: str,
        direction: Direction | None,
        trigger: Trigger | None,
        status: SetupState,
    ) -> tuple[str | None, bool, bool]:
        """Classify one observation against this symbol's running identity.

        Returns ``(setup_id, is_new_setup, is_first_confirmation)``:

        * ``setup_id`` — `setup_identity`'s result, or ``None`` for `WAIT`.
        * ``is_new_setup`` — ``True`` exactly when this identity differs from
          the symbol's previously active one (including "there was none").
        * ``is_first_confirmation`` — ``True`` exactly once per active
          identity's lifetime: the first bar at which it is `CONFIRMED`.
          Repeated `CONFIRMED` bars for the same identity report ``False``,
          which is what prevents one confirmed setup from being outcome-
          evaluated more than once.

        A `WAIT` observation clears the symbol's active identity: a thesis
        that lapsed and later re-forms — even referencing the same level — is
        a new occurrence, not a continuation, because the policy itself
        stopped standing behind it in between.
        """
        if direction is None:
            self._active.pop(symbol, None)
            return None, False, False

        candidate_id = setup_identity(symbol, direction, trigger)
        active = self._active.get(symbol)
        is_new = active is None or active.setup_id != candidate_id
        if is_new:
            active = _ActiveSetup(setup_id=candidate_id)
            self._active[symbol] = active

        is_first_confirmation = False
        if status is SetupState.CONFIRMED and not active.confirmed_already:
            active.confirmed_already = True
            is_first_confirmation = True

        return candidate_id, is_new, is_first_confirmation
