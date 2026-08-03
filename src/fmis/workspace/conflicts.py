"""Deterministic conflict detection across timeframes, regimes and evidence.

**This module reports disagreement. It never resolves it, ranks it, scores it, or
recommends anything about it.**

That restraint is the whole design. ADR-0023 fixed that nothing may be derived
from the combination of timeframe views, and ADR-0025 that a regime's dimensions
are never collapsed. Both of those refusals leave a real gap: nothing in the
repository has ever *said out loud* that the weekly and the four-hour views
disagree, even though both facts are printed side by side.

Stating that they differ is not deriving something from their combination — the
values compared are already on the page, and no third value is produced. What
would cross the line is picking a winner, weighting one timeframe over another,
or emitting a net direction. None of those appears here, and a test asserts the
module contains no such vocabulary.

**A tie remains a tie**, inherited verbatim from ADR-0008 §5: when evidence has
no dominant alignment, that absence is itself reported as a conflict rather than
broken by a rule.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from fmis.decision_support import Alignment, EvidenceReport
from fmis.market_regime import MarketRegime, RegimeDimensionName, StructureState
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.structural_trend import StructuralTrendType

__all__ = [
    "ConflictKind",
    "Conflict",
    "detect_conflicts",
]

#: Explicit role rank, so a pair is always described in the same order however
#: the caller supplied it. Without this, reversing the input reversed which
#: participant a statement names first and produced a *different string* for the
#: same disagreement — two runs over identical facts disagreeing about their own
#: output. Declared here rather than imported, because the ordering it mirrors is
#: private to `fmis.pipeline.multi_timeframe` and reaching into a private would
#: create a second contract that could drift from it.
_ROLE_RANK: Mapping[TimeframeRole, int] = {
    TimeframeRole.CONTEXT: 0,
    TimeframeRole.SETUP: 1,
    TimeframeRole.EXECUTION: 2,
}


class ConflictKind(str, Enum):
    """What kind of disagreement was observed.

    Deliberately absent: any member naming a severity, a winner, or a resolution.
    `MAJOR`, `MINOR`, `DOMINANT` and `OVERRIDES` are category errors here — they
    would be judgements about which fact matters more, which is the decision this
    layer exists not to make.
    """

    #: Two roles' structural trends are sustained in opposite senses.
    STRUCTURAL_TREND = "structural_trend"
    #: Two roles' regime structure states differ (trending vs ranging).
    REGIME_STRUCTURE = "regime_structure"
    #: One role's regime could not classify because its own families disagreed.
    REGIME_INDETERMINATE = "regime_indeterminate"
    #: Directional observations disagree with the dominant alignment.
    EVIDENCE_DISAGREEMENT = "evidence_disagreement"
    #: Directional observations are evenly split, so no alignment dominates.
    EVIDENCE_TIE = "evidence_tie"


_KIND_ORDER: tuple[ConflictKind, ...] = (
    ConflictKind.STRUCTURAL_TREND,
    ConflictKind.REGIME_STRUCTURE,
    ConflictKind.REGIME_INDETERMINATE,
    ConflictKind.EVIDENCE_DISAGREEMENT,
    ConflictKind.EVIDENCE_TIE,
)

_RANK: Mapping[ConflictKind, int] = {
    kind: rank for rank, kind in enumerate(_KIND_ORDER)
}

#: The two trend values that point in opposite senses. Compared as a pair rather
#: than by name so the module never branches on *which* of them a series shows —
#: the asymmetry `docs/analysis-notes.md` blames for the v2 bias is not
#: expressible if the code cannot prefer one member.
_OPPOSED = frozenset({StructuralTrendType.SUSTAINED_HIGHER, StructuralTrendType.SUSTAINED_LOWER})


@dataclass(frozen=True, slots=True)
class Conflict:
    """One observed disagreement, its participants, and nothing else.

    ``statement`` is a plain restatement of what differs. It contains no verb of
    recommendation and no comparative judgement: "1w and 4h report opposite
    sustained trends" is a fact about two printed values, while "the weekly view
    should be trusted" would be an interpretation this layer may not hold.

    Frozen and hashable, so a run of conflicts can go in a set when a later layer
    diffs two workspaces — which is exactly what a Telegram alert will do.
    """

    kind: ConflictKind
    statement: str
    participants: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ConflictKind):
            raise TypeError(
                f"kind must be a ConflictKind, got {type(self.kind).__name__}"
            )
        if not isinstance(self.statement, str) or not self.statement.strip():
            raise ValueError("statement must be a non-empty str")
        if not isinstance(self.participants, tuple) or not self.participants:
            raise ValueError("participants must be a non-empty tuple")
        for item in self.participants:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("every participant must be a non-empty str")


def _role_label(role: TimeframeRole, interval: str) -> str:
    return f"{role.value} · {interval}"


def _structural_trend_conflicts(
    trends: Sequence[tuple[str, StructuralTrendType]],
) -> list[Conflict]:
    """Pairs of roles whose sustained trends run in opposite senses.

    Only *sustained* pairs qualify. `NEUTRAL` does not conflict with a trend — it
    is the absence of one — and `INDETERMINATE` is unavailable evidence, which
    ADR-0025 forbids counting as disagreement. Reporting either as a conflict
    would manufacture one from silence.
    """
    found: list[Conflict] = []
    for position, (label, trend) in enumerate(trends):
        for other_label, other_trend in trends[position + 1 :]:
            if trend not in _OPPOSED or other_trend not in _OPPOSED:
                continue
            if trend is other_trend:
                continue
            found.append(
                Conflict(
                    kind=ConflictKind.STRUCTURAL_TREND,
                    statement=(
                        f"{label} reports {trend.value} while {other_label} "
                        f"reports {other_trend.value}"
                    ),
                    participants=(label, other_label),
                )
            )
    return found


def _regime_structure_conflicts(
    states: Sequence[tuple[str, StructureState]],
) -> list[Conflict]:
    """Pairs of roles whose regime structure states differ decisively.

    Only `TRENDING` against `RANGING` counts. `TRANSITIONING`, `INDETERMINATE`
    and `INSUFFICIENT` are not opposites of anything — they are statements about
    change or about absence, and pairing them would invent a disagreement.
    """
    decisive = (StructureState.TRENDING, StructureState.RANGING)
    found: list[Conflict] = []
    for position, (label, state) in enumerate(states):
        for other_label, other_state in states[position + 1 :]:
            if state not in decisive or other_state not in decisive:
                continue
            if state is other_state:
                continue
            found.append(
                Conflict(
                    kind=ConflictKind.REGIME_STRUCTURE,
                    statement=(
                        f"{label} regime structure is {state.value} while "
                        f"{other_label} is {other_state.value}"
                    ),
                    participants=(label, other_label),
                )
            )
    return found


def _regime_indeterminate_conflicts(
    regimes: Sequence[tuple[str, MarketRegime]],
) -> list[Conflict]:
    """A single role whose regime declined to classify because families disagreed.

    `INDETERMINATE` means evidence was present and contradicted itself, which is
    a conflict the reader must see. `INSUFFICIENT` means evidence was absent,
    which belongs under missing evidence and is deliberately not reported here.
    """
    found: list[Conflict] = []
    for label, regime in regimes:
        dimension = regime.by_dimension[RegimeDimensionName.STRUCTURE]
        if dimension.state is not StructureState.INDETERMINATE:
            continue
        families = tuple(sorted({item.source for item in dimension.conflicting}))
        found.append(
            Conflict(
                kind=ConflictKind.REGIME_INDETERMINATE,
                statement=(
                    f"{label} regime structure is indeterminate: its evidence "
                    "families disagree with each other"
                ),
                participants=(label,) + families,
            )
        )
    return found


def _evidence_conflicts(label: str, report: EvidenceReport) -> list[Conflict]:
    """What the evidence layer already found, surfaced rather than recomputed.

    `fmis.decision_support` has grouped observations into supporting, conflicting
    and unavailable since ADR-0008, and reports **no dominant alignment on a
    tie**. Both facts are read here and neither is re-derived: a second
    implementation of the grouping rule is exactly the drift this repository's
    single-source discipline exists to prevent.
    """
    found: list[Conflict] = []
    groups = report.groups
    if groups.conflicting:
        keys = tuple(sorted(item.key for item in groups.conflicting))
        found.append(
            Conflict(
                kind=ConflictKind.EVIDENCE_DISAGREEMENT,
                statement=(
                    f"{label} has {len(groups.conflicting)} directional "
                    "observation(s) disagreeing with the dominant alignment"
                ),
                participants=(label,) + keys,
            )
        )
    directional = groups.supporting + groups.conflicting
    if directional and groups.dominant_alignment in (
        Alignment.NEUTRAL,
        Alignment.NOT_DIRECTIONAL,
        Alignment.UNAVAILABLE,
    ):
        found.append(
            Conflict(
                kind=ConflictKind.EVIDENCE_TIE,
                statement=(
                    f"{label} directional evidence has no dominant alignment; "
                    "the tie is reported, not broken"
                ),
                participants=(label,),
            )
        )
    return found


def detect_conflicts(
    *,
    trends: Sequence[tuple[TimeframeRole, str, StructuralTrendType]],
    regimes: Sequence[tuple[TimeframeRole, str, MarketRegime]],
    evidence: tuple[str, EvidenceReport] | None = None,
) -> tuple[Conflict, ...]:
    """Every disagreement observable across the supplied facts.

    Args:
        trends: ``(role, interval, structural trend)`` per timeframe view.
        regimes: ``(role, interval, regime)`` per timeframe view.
        evidence: the evidence report and the label it describes, when one was
            produced. ``None`` when the evidence layer had nothing to read.

    Returns:
        Conflicts ordered by kind rank then by statement — a total, content-only
        order. Permuting the inputs cannot change the output: roles are sorted
        into canonical order before any pair is described, so the same two facts
        always produce the same sentence. Empty when nothing disagrees, which is
        a true answer and not a failure.

    Raises:
        TypeError: an argument is not a non-string sequence, or an element has
            the wrong shape.

    Pure: no state, no clock, no network, no randomness.
    """
    for name, value in (("trends", trends), ("regimes", regimes)):
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise TypeError(f"{name} must be a non-string sequence")

    # Canonical role order first: the output must depend on the facts, not on the
    # order a caller happened to pass them in.
    ordered_trends = sorted(trends, key=lambda item: _ROLE_RANK[item[0]])
    ordered_regimes = sorted(regimes, key=lambda item: _ROLE_RANK[item[0]])

    trend_pairs = [
        (_role_label(role, interval), trend)
        for role, interval, trend in ordered_trends
    ]
    structure_states = [
        (
            _role_label(role, interval),
            regime.by_dimension[RegimeDimensionName.STRUCTURE].state,
        )
        for role, interval, regime in ordered_regimes
    ]
    labelled_regimes = [
        (_role_label(role, interval), regime)
        for role, interval, regime in ordered_regimes
    ]

    found: list[Conflict] = []
    found.extend(_structural_trend_conflicts(trend_pairs))
    found.extend(_regime_structure_conflicts(structure_states))
    found.extend(_regime_indeterminate_conflicts(labelled_regimes))
    if evidence is not None:
        label, report = evidence
        found.extend(_evidence_conflicts(label, report))

    found.sort(key=lambda conflict: (_RANK[conflict.kind], conflict.statement))
    return tuple(found)
