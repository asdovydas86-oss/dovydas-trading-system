"""Value types for the deterministic structural trend.

A `StructuralTrendType` names how a *run* of structural sequence states stands:
whether it contains a sustained same-direction structural shift, whether the
directional evidence in it conflicts, or whether there is not yet enough of it to
say anything. That is a statement about a sequence of already-settled facts — it
is not a market view.

A `StructuralTrendSnapshot` fixes one such statement to the state snapshot it was
computed at, so a run of them is a sequence of historical readings rather than a
value that keeps changing.

``index`` is a position into the **closed** candles of the series the underlying
swings were detected from, inherited unchanged from
`StructuralSequenceStateSnapshot`. It is only meaningful relative to that series,
and two timeframes' indices are never comparable — ``timestamp`` is the only
cross-timeframe key.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType

from fmis.market_structure import (
    StructuralSequenceStateSnapshot,
    StructuralSequenceStateType,
)

__all__ = [
    "MINIMUM_DIRECTIONAL_SHIFTS",
    "StructuralTrendType",
    "StructuralTrendSnapshot",
]


#: How many same-direction structural shifts a run must contain before it is
#: called sustained.
#:
#: **This is a policy, not a measurement.** No number here can be derived from
#: anything: "how many shifts make a trend" has no objective answer, so the value
#: is stated in the open rather than buried in a conditional. Two is the smallest
#: integer that expresses *repetition* — one shift is a single already-settled
#: fact about one candle, and calling that a trend would rename a fact rather than
#: read a sequence. Any larger value is a strictly more arbitrary choice.
#:
#: It is deliberately **not** a function parameter. A parameter would invite
#: per-call tuning, and two results derived under different thresholds are not
#: comparable — the prefix-stability guarantee is stated per-threshold. Changing
#: this constant changes the meaning of every result and requires its own decision
#: record. See the design, §4.2 and §8.3.
MINIMUM_DIRECTIONAL_SHIFTS = 2


class StructuralTrendType(str, Enum):
    """How a run of structural sequence states stands. Four members, no catch-all.

    The partition is built from two questions: has the current run of
    same-direction shifts reached `MINIMUM_DIRECTIONAL_SHIFTS`, and has the run
    ever been opposed? Those two answers cover every case with no overlap and no
    leftovers, which is why there is no `MIXED`, `OTHER` or `AMBIGUOUS` member — a
    catch-all would be the place ambiguous cases quietly accumulate.

      * `SUSTAINED_HIGHER` — at least `MINIMUM_DIRECTIONAL_SHIFTS` snapshots whose
        state was `SHIFTED_HIGHER`, with no `SHIFTED_LOWER` between them. It says
        the same two-sided shift happened more than once and nothing reversed it.
        It does **not** mean uptrend, bullish, strong, likely to continue, or a
        reason to buy.
      * `SUSTAINED_LOWER` — the same, lower. Not bearish, not weakness, not a
        reason to sell.
      * `NEUTRAL` — directional evidence exists **on both sides** and the current
        run has not reached the minimum. Evidence exists and conflicts. Not
        balance, not equilibrium, not a range, not indecision.
      * `INDETERMINATE` — there is not yet enough directional evidence to say
        anything, and nothing has conflicted. Evidence is *absent*, not
        contradictory.

    `NEUTRAL` and `INDETERMINATE` are **not interchangeable**, and folding them
    together would be the exact ambiguity-hiding this layer exists to avoid: one
    says the structure has moved both ways, the other says it has barely moved at
    all, and a consumer that cannot tell them apart cannot tell a choppy market
    from a quiet one.

    "Sustained" is used in the strict sense of *maintained by repetition*. It
    carries no claim about strength, momentum, durability, or what happens next.

    Deliberately absent: UPTREND, DOWNTREND, BULLISH, BEARISH, ADVANCING_UP,
    ADVANCING_DOWN, BALANCED, STRONG, WEAK, RANGING, LONG, SHORT, BUY, SELL,
    CONTINUATION, REVERSAL, and anything carrying a confidence, score, rank or
    probability.
    """

    SUSTAINED_HIGHER = "sustained_higher"
    SUSTAINED_LOWER = "sustained_lower"
    NEUTRAL = "neutral"
    INDETERMINATE = "indeterminate"


#: The one authoritative mapping from a *directional* structural sequence state to
#: the sustained trend it accumulates toward.
#:
#: Exactly two entries, because exactly two of the six `StructuralSequenceStateType`
#: members say both structural sides moved the same way in price (ADR-0015 §2).
#: `EXPANDED` (outward, nothing inward), `CONTRACTED` (inward, nothing outward) and
#: `UNCHANGED` (nothing moved) are explicitly not directional, and
#: `INSUFFICIENT_STRUCTURE` says one side does not exist yet. Reading a direction
#: out of any of those four would invent one where ADR-0015 §5 says none is
#: present.
#:
#: Written out cell by cell rather than derived from the member names, so reading
#: it is the same as reading the design's table, and an immutable mapping so the
#: vocabulary cannot be re-pointed at runtime — following
#: `market_structure.models._STATE_BY_LABEL_PAIR` (ADR-0015 §10).
_TREND_BY_DIRECTIONAL_STATE: Mapping[
    StructuralSequenceStateType, StructuralTrendType
] = MappingProxyType(
    {
        StructuralSequenceStateType.SHIFTED_HIGHER: (
            StructuralTrendType.SUSTAINED_HIGHER
        ),
        StructuralSequenceStateType.SHIFTED_LOWER: (
            StructuralTrendType.SUSTAINED_LOWER
        ),
    }
)


def _is_directional_state(state: StructuralSequenceStateType) -> bool:
    """Whether a state carries a direction at all — the one authoritative test.

    Membership of `_TREND_BY_DIRECTIONAL_STATE`, so the set of directional states
    and the mapping to their sustained members can never disagree.

    Deliberately **private**. A public predicate would let a caller build its own
    parallel notion of "directional", which is how two layers end up with
    definitions that agree today and diverge in a year.
    """
    return state in _TREND_BY_DIRECTIONAL_STATE


def _trend_for_directional_state(
    state: StructuralSequenceStateType,
) -> StructuralTrendType:
    """The sustained member a directional state accumulates toward.

    Deliberately **private**, following `market_structure.models._sequence_state_for`
    (ADR-0015 §10). A public ``trend_for(state)`` would name a sustained trend for
    a *single* state, which is exactly the one-fact-renamed-as-a-trend move this
    layer exists to refuse: a trend is a property of a run, never of one snapshot.

    Raises:
        KeyError: ``state`` is not directional. Callers guard with
            `_is_directional_state`; reaching here with a non-directional state is
            a programming error and is deliberately not softened into a default.
    """
    return _TREND_BY_DIRECTIONAL_STATE[state]


def _validate_snapshot_history_order(
    snapshots: Sequence[StructuralSequenceStateSnapshot], subject: str
) -> None:
    """Ordering rule for a run of state snapshots: strictly increasing, both keys.

    Checked on each snapshot's projected ``index`` and ``timestamp``:

      * ``index`` is **strictly** increasing across the whole run;
      * ``timestamp`` is strictly increasing with it.

    Strictness is global here, unlike the rule one layer down. That is not an
    oversight and not a copy with a tweak: `derive_structural_sequence_state_history`
    emits exactly one snapshot per distinct candle index, having already collapsed
    each same-candle HIGH/LOW group into one atomic entry (ADR-0016 §1–§2). So a
    valid snapshot history has no repeated index, and there is no `SwingType` to be
    strict *within* — the per-type strictness that
    `market_structure.models._validate_key_order` exists to express has no meaning
    over snapshots. Reusing that rule would accept two snapshots at one index,
    which no valid history contains.

    Order is validated, **never repaired**. Sorting silently would hide a caller
    bug and fold the wrong prefixes together, changing the answer (ADR-0013 §5,
    unchanged).

    Deliberately **private**. ``subject`` names the caller's parameter in error
    messages so a message points at the argument the caller actually passed.

    Args:
        snapshots: the run to check, already materialised in input order.
        subject: the caller's parameter name, used in error text.

    Raises:
        ValueError: the run is not ordered.
    """
    previous: tuple[int, datetime] | None = None

    for position, snapshot in enumerate(snapshots):
        index = snapshot.index
        timestamp = snapshot.timestamp
        if previous is not None:
            earlier_index, earlier_timestamp = previous
            if index <= earlier_index:
                raise ValueError(
                    f"{subject} must be ordered by strictly increasing index; "
                    f"{subject}[{position}] has index {index} after "
                    f"{earlier_index}"
                )
            if timestamp <= earlier_timestamp:
                raise ValueError(
                    f"{subject} must be ordered by strictly increasing timestamp; "
                    f"{subject}[{position}] has {timestamp.isoformat()} after "
                    f"{earlier_timestamp.isoformat()}"
                )
        previous = (index, timestamp)


@dataclass(frozen=True, slots=True)
class StructuralTrendSnapshot:
    """The structural trend as at one state snapshot. Exactly two fields.

    ``trend`` is the `StructuralTrendType` implied by every state snapshot up to
    and including this one.

    ``state_snapshot`` is the `StructuralSequenceStateSnapshot` this reading was
    taken at, embedded **whole** and held **by identity**, never copied. It already
    validates that its own fields agree (ADR-0016 §3), so re-exposing its
    ``state`` or ``triggers`` here would create a second place for them to disagree
    — the hazard ADR-0014 §5 removed.

    ``index`` and ``timestamp`` are **computed projections, not fields**,
    delegating to the state snapshot, for ADR-0016 §4's reasons: a stored copy of a
    value one attribute away is somewhere for it to drift.

    **What this type deliberately cannot validate.** `StructuralSwing.label` and
    `StructuralSequenceState.state` are each checked against the object's own other
    fields. ``trend`` cannot be, because a trend is a property of the whole
    **prefix**, not of one snapshot: the very same state snapshot legitimately
    carries a different trend depending on what preceded it. So this type validates
    types only, and the correctness of ``trend`` is a property of the derivation,
    tested there. Recording that honestly is better than claiming a validation that
    cannot exist.

    Deliberately absent: any run length, count, strength, confidence, score, rank,
    direction flag, duration, or "changed" marker. A run length is a confidence by
    another name, and it would invite threshold-shopping over a policy that is
    already stated once (`MINIMUM_DIRECTIONAL_SHIFTS`).

    Frozen, slotted and hashable, matching every value type in
    `fmis.market_structure`.
    """

    trend: StructuralTrendType
    state_snapshot: StructuralSequenceStateSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.trend, StructuralTrendType):
            raise TypeError(
                "trend must be a StructuralTrendType, got "
                f"{type(self.trend).__name__}"
            )
        if not isinstance(self.state_snapshot, StructuralSequenceStateSnapshot):
            raise TypeError(
                "state_snapshot must be a StructuralSequenceStateSnapshot, got "
                f"{type(self.state_snapshot).__name__}"
            )

    @property
    def index(self) -> int:
        """The closed-candle index this reading was taken at.

        A projection of ``state_snapshot.index``, not stored.
        """
        return self.state_snapshot.index

    @property
    def timestamp(self) -> datetime:
        """The timestamp of the bar this reading was taken at.

        A projection of ``state_snapshot.timestamp``, not stored.
        """
        return self.state_snapshot.timestamp
