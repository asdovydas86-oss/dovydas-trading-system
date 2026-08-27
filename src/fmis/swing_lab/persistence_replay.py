"""Collecting the post-entry thesis timeline from the **same** replay pass.

Milestone BZ needs to know what the structural engines said at every 4H bar,
not only at the bars that admitted a setup. The expensive way to get that is a
second replay; the wrong way is a second replay, because two walks over the same
history can differ for provider reasons and every BZ claim about a state
*transition* would then rest on comparing two different datasets.

So `fmis.swing_lab.geometry_replay.capture_geometry_candidates` grew one
additive argument — an ``observer`` sink — and this module is what fills it. One
pass, two outputs:

    replay ──┬──► GeometryCandidate per admitted setup   (what BX and BY read)
             └──► ThesisObservation per analysable bar   (what BZ reads)

**The observer cannot change the study.** It returns nothing, it is called after
the admission assessment is already fixed, and `capture_geometry_candidates`
constructs it not at all when no observer is supplied. A regression asserts that
a capture taken with a collector attached is equal, candidate for candidate, to
one taken without it.

**Every observation is causal by construction.** A `ThesisObservation` is built
from `fmis.swing_setup.models.SetupInputs` — the same narrow fact boundary the
production policy reads — at the instant whose close produced it. It holds no
bar, no future timestamp and no outcome, exactly as a `GeometryCandidate` does.
The levels it carries are ordered against *that instant's* close by
`fmis.swing_setup.policy.ordered_levels`, production's own ordering, called.
"""

from __future__ import annotations

from collections.abc import Mapping

from fmis.level_crossing import LevelSide
from fmis.swing_lab.geometry import level_refs
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.persistence import (
    LEVELS_PER_SIDE,
    ThesisObservation,
    ThesisTimeline,
)
from fmis.swing_lab.replay import ReplayInstant
from fmis.swing_setup.policy import ordered_levels

__all__ = [
    "TimelineCollector",
    "observation_from",
]


def observation_from(instant: ReplayInstant) -> ThesisObservation:
    """Freeze one analysable instant's structural state. **A copy, never a calculation.**

    Every value is read from `SetupInputs` or from the assessment already bound
    onto the instant. This function derives no structure, no trend, no regime
    and no direction: those are production's output and BZ reads them exactly as
    the admission policy did.

    Raises:
        SwingLabError: the instant carries no bar index, so nothing could
            address the observation afterwards.
    """
    if not isinstance(instant, ReplayInstant):
        raise TypeError(
            f"instant must be a ReplayInstant, got {type(instant).__name__}"
        )
    if instant.signal_index is None:
        raise SwingLabError(
            f"{instant.symbol} at {instant.as_of.isoformat()} has no bar index; "
            "an observation with no index cannot be addressed by a path walk"
        )
    inputs = instant.inputs
    assessment = instant.baseline_assessment
    close = inputs.execution_close

    def side_levels(side: LevelSide, above: bool) -> tuple:
        # A missing close means the view is still warming up. Ordering against a
        # substituted price would invent a distance, so the side is reported
        # EMPTY — a stated absence, which `ThesisState.UNAVAILABLE` and the
        # structural trail both already know how to refuse.
        if close is None:
            return ()
        return level_refs(
            ordered_levels(
                tuple(inputs.execution_levels), side=side, close=close, above=above
            )[:LEVELS_PER_SIDE],
            interval=inputs.execution_interval,
        )

    direction = assessment.direction
    return ThesisObservation(
        symbol=instant.symbol,
        as_of=instant.as_of,
        bar_index=instant.signal_index,
        context_structural_trend=inputs.context_structural_trend.value,
        setup_structural_trend=inputs.setup_structural_trend.value,
        execution_structural_trend=inputs.execution_structural_trend.value,
        context_regime_structure=inputs.context_regime_structure.value,
        evidence_state=(
            None if inputs.evidence_state is None else inputs.evidence_state.value
        ),
        evidence_dominant_alignment=(
            None
            if inputs.evidence_dominant_alignment is None
            else inputs.evidence_dominant_alignment.value
        ),
        decision_context_state=inputs.decision_context_state.value,
        setup_state=assessment.state.value,
        setup_direction=None if direction is None else direction.value,
        execution_close=close,
        upper_levels=side_levels(LevelSide.UPPER, above=True),
        lower_levels=side_levels(LevelSide.LOWER, above=False),
    )


class TimelineCollector:
    """An ``observer`` sink that accumulates one `ThesisTimeline` per symbol.

    Mutable, and deliberately so: the replay discovers instants one at a time
    over tens of minutes, and threading an accumulator through every level of
    that walk would change the walk's shape for a bookkeeping reason —
    `fmis.swing_lab.intrabar.AmbiguityLedger` reached the same conclusion for the
    same reason.

    **A repeated bar index is an error, not a last-write-wins.** Two
    observations for one symbol at one bar means the replay yielded the same
    instant twice, which would make every downstream count of state transitions
    wrong in a way no total would reveal. It is refused loudly.
    """

    __slots__ = ("_by_symbol", "_seen")

    def __init__(self) -> None:
        self._by_symbol: dict[str, dict[int, ThesisObservation]] = {}
        self._seen = 0

    def __call__(self, instant: ReplayInstant) -> None:
        observation = observation_from(instant)
        bucket = self._by_symbol.setdefault(observation.symbol, {})
        existing = bucket.get(observation.bar_index)
        if existing is not None:
            raise SwingLabError(
                f"{observation.symbol} yielded two instants for execution bar "
                f"{observation.bar_index} ({existing.as_of.isoformat()} and "
                f"{observation.as_of.isoformat()}); a duplicated instant would "
                "double-count every state transition measured over it"
            )
        bucket[observation.bar_index] = observation
        self._seen += 1

    @property
    def observed(self) -> int:
        """How many instants were recorded, across every symbol."""
        return self._seen

    def timelines(self) -> Mapping[str, ThesisTimeline]:
        """One timeline per symbol. **Snapshot, safe to keep past the replay.**"""
        return {
            symbol: ThesisTimeline(
                symbol=symbol, observations=dict(observations)
            )
            for symbol, observations in sorted(self._by_symbol.items())
        }
