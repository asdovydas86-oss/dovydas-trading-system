"""Classifying three market environments from facts the repository already computed.

One public function, `classify_regime`. It reads a `RegimeInput` and a
`RegimePolicy` and returns a `MarketRegime`. It computes no indicator, fetches
nothing, and reads no clock.

Semantics, stated in full because every one of them is a decision:

**Evidence votes by family, never by number.** A family is a group of measurements
that express the same thing: swing structure (structural trend and change of
character) is one family, moving averages (close against a fast and a slow EMA)
is another. Each family contributes **one** vote. This is the single most
important rule in the module, and `docs/analysis-notes.md` §1 says why: the v2
checklist counted "weekly trend" and "daily trend" as two independent
confirmations of the same thing, so one side of the book started every analysis
two points ahead. Counting correlated evidence twice is how a model becomes
confident without becoming right.

**Structure needs two families to agree.** One available family is not enough to
call trending or ranging; the result is `INSUFFICIENT`, with the reason recorded.
A single-family classification is precisely the free confirmation the post-mortem
identified, and refusing it costs only that the state is honest during warm-up.

**A change of character outranks both.** The repository already names this event:
a change of character *is* the structure changing. When one falls within the
policy's lookback, structure reports `TRANSITIONING` and both families are still
listed as evidence, so a reader sees what the transition interrupted.

**Nothing is read by two dimensions.** The EMAs feed structure only, the ATRs feed
volatility only, relative volume feeds participation only. No number can push two
dimensions the same way and look like corroboration.

**Unavailable is not negative.** A warming-up indicator produces an `UNAVAILABLE`
evidence item and never a `CONFLICTING` one. Silence is not disagreement.

**No direction, anywhere — including in the evidence.** The engine reads
`StructuralTrendType` to learn *whether* structure is sustained, never *which
way*. `SUSTAINED_HIGHER` and `SUSTAINED_LOWER` are treated identically, and a
test asserts that swapping them changes no regime and no evidence string.

The evidence therefore reports ``"structure sustained in one direction"`` rather
than the trend value itself. Echoing ``sustained_lower`` would put a direction
into the regime's own output — a fact the engine explicitly did not use, printed
where a reader would take it for part of the classification. Which way structure
points is on the fact sheet, one layer down, where it is a measurement rather
than a regime.
"""

from __future__ import annotations

from fmis.market_regime.models import (
    EvidenceStatus,
    MarketRegime,
    ParticipationState,
    RegimeDimension,
    RegimeDimensionName,
    RegimeEvidence,
    RegimeInput,
    StructureState,
    VolatilityState,
)
from fmis.market_regime.policy import DEFAULT_POLICY, RegimePolicy
from fmis.structural_trend import StructuralTrendType

__all__ = ["classify_regime"]

#: Evidence family names. Written once and shared by the classifier and the
#: tests, so a renamed family cannot silently become a second family that votes
#: again beside the first.
FAMILY_SWING_STRUCTURE = "swing structure"
FAMILY_MOVING_AVERAGES = "moving averages"
FAMILY_TRUE_RANGE = "true range"
FAMILY_VOLUME = "volume"

#: The two trend values that mean "structure is sustained in one direction".
#: Both, together, with no branch that distinguishes them — the asymmetry the v2
#: post-mortem blamed is unrepresentable if the code cannot tell them apart.
_SUSTAINED = (
    StructuralTrendType.SUSTAINED_HIGHER,
    StructuralTrendType.SUSTAINED_LOWER,
)


def _swing_structure_evidence(subject: RegimeInput) -> tuple[str | None, RegimeEvidence]:
    """The swing-structure family's reading: ``"trending"``, ``"ranging"`` or None.

    `INDETERMINATE` means the trend engine had too little to say, which is
    unavailable evidence rather than a vote for ranging — those are different
    facts and ADR-0017 keeps them apart for the same reason.
    """
    trend = subject.structural_trend
    if trend in _SUSTAINED:
        return "trending", RegimeEvidence(
            source=FAMILY_SWING_STRUCTURE,
            status=EvidenceStatus.CONSISTENT,
            observed="structure sustained in one direction",
        )
    if trend is StructuralTrendType.NEUTRAL:
        return "ranging", RegimeEvidence(
            source=FAMILY_SWING_STRUCTURE,
            status=EvidenceStatus.CONSISTENT,
            observed="structure not sustained",
        )
    return None, RegimeEvidence(
        source=FAMILY_SWING_STRUCTURE,
        status=EvidenceStatus.UNAVAILABLE,
        observed="structural trend indeterminate",
    )


def _moving_average_evidence(subject: RegimeInput) -> tuple[str | None, RegimeEvidence]:
    """The moving-average family's reading, from position alone — never ordering.

    Close beyond **both** averages reads as trending; close between them reads as
    ranging. Which side it is beyond is never asked, so this family cannot carry
    direction into the result.

    Ordering (fast above slow, or below) is deliberately not used: it is almost
    always true one way or the other, so it would vote on nearly every bar while
    carrying direction — the shape of the gate that produced the v2 bias.
    """
    close = subject.close
    fast = subject.ema_fast
    slow = subject.ema_slow
    if close is None or fast is None or slow is None:
        return None, RegimeEvidence(
            source=FAMILY_MOVING_AVERAGES,
            status=EvidenceStatus.UNAVAILABLE,
            observed="not available",
        )
    beyond_both = (close > fast and close > slow) or (close < fast and close < slow)
    if beyond_both:
        return "trending", RegimeEvidence(
            source=FAMILY_MOVING_AVERAGES,
            status=EvidenceStatus.CONSISTENT,
            observed="close beyond both averages",
            value=close,
        )
    return "ranging", RegimeEvidence(
        source=FAMILY_MOVING_AVERAGES,
        status=EvidenceStatus.CONSISTENT,
        observed="close between the averages",
        value=close,
    )


def _structure_dimension(
    subject: RegimeInput, policy: RegimePolicy
) -> RegimeDimension:
    """Trending, ranging, transitioning — or an honest refusal to say."""
    swing_reading, swing_evidence = _swing_structure_evidence(subject)
    average_reading, average_evidence = _moving_average_evidence(subject)

    transitioning = False
    if subject.latest_change_index is not None and subject.last_index is not None:
        bars_since = subject.last_index - subject.latest_change_index
        transitioning = bars_since <= policy.transition_lookback_bars
        if transitioning:
            change_evidence = RegimeEvidence(
                source=FAMILY_SWING_STRUCTURE,
                status=EvidenceStatus.CONSISTENT,
                observed=f"change of character {bars_since} bars ago",
                value=float(bars_since),
            )
        else:
            # Reported because a reader wants to know when structure last
            # changed, but counted for nothing: a stale event neither agrees nor
            # disagrees with trending or ranging, and calling it conflicting
            # would manufacture a disagreement that does not exist.
            change_evidence = RegimeEvidence(
                source=FAMILY_SWING_STRUCTURE,
                status=EvidenceStatus.CONTEXT,
                observed=(
                    f"change of character {bars_since} bars ago, outside the "
                    f"{policy.transition_lookback_bars}-bar lookback"
                ),
                value=float(bars_since),
            )
    else:
        change_evidence = RegimeEvidence(
            source=FAMILY_SWING_STRUCTURE,
            status=EvidenceStatus.UNAVAILABLE,
            observed="no change of character in this window",
        )

    if transitioning:
        # The recent change is the finding. The two families stay visible so a
        # reader sees what it interrupted, but they answer a different question
        # — trending or ranging — and are counted for neither.
        evidence = (
            change_evidence,
            _restated(swing_evidence, EvidenceStatus.CONTEXT),
            _restated(average_evidence, EvidenceStatus.CONTEXT),
        )
        return RegimeDimension(
            name=RegimeDimensionName.STRUCTURE,
            state=StructureState.TRANSITIONING,
            evidence=evidence,
        )

    readings = [r for r in (swing_reading, average_reading) if r is not None]
    if len(readings) < 2:
        return RegimeDimension(
            name=RegimeDimensionName.STRUCTURE,
            state=StructureState.INSUFFICIENT,
            evidence=(
                _restated(swing_evidence, EvidenceStatus.CONTEXT),
                _restated(average_evidence, EvidenceStatus.CONTEXT),
                change_evidence,
            ),
            reason=(
                "structure needs both evidence families to be readable; one "
                "family alone is a free confirmation, not corroboration"
            ),
        )
    if swing_reading != average_reading:
        return RegimeDimension(
            name=RegimeDimensionName.STRUCTURE,
            state=StructureState.INDETERMINATE,
            evidence=(
                _restated(swing_evidence, EvidenceStatus.CONFLICTING),
                _restated(average_evidence, EvidenceStatus.CONFLICTING),
                change_evidence,
            ),
            reason=(
                "the two evidence families disagree; reported rather than "
                "resolved, because no rule here outranks the other"
            ),
        )
    state = (
        StructureState.TRENDING if swing_reading == "trending" else StructureState.RANGING
    )
    return RegimeDimension(
        name=RegimeDimensionName.STRUCTURE,
        state=state,
        evidence=(swing_evidence, average_evidence, change_evidence),
    )


def _restated(evidence: RegimeEvidence, status: EvidenceStatus) -> RegimeEvidence:
    """The same observation under a different status. Unavailable stays unavailable.

    An unreadable indicator cannot become conflicting evidence just because the
    dimension settled on a state it did not vote for — that is exactly the
    "silence counted as disagreement" failure this package refuses.
    """
    if evidence.status is EvidenceStatus.UNAVAILABLE:
        return evidence
    return RegimeEvidence(
        source=evidence.source,
        status=status,
        observed=evidence.observed,
        value=evidence.value,
    )


def _volatility_dimension(
    subject: RegimeInput, policy: RegimePolicy
) -> RegimeDimension:
    """Recent true range against its own longer baseline, as a ratio."""
    fast = subject.atr_fast
    slow = subject.atr_slow
    if fast is None or slow is None or slow <= 0.0:
        return RegimeDimension(
            name=RegimeDimensionName.VOLATILITY,
            state=VolatilityState.INSUFFICIENT,
            evidence=(
                RegimeEvidence(
                    source=FAMILY_TRUE_RANGE,
                    status=EvidenceStatus.UNAVAILABLE,
                    observed="not available",
                ),
            ),
            reason=(
                "both true-range windows must be available and the baseline "
                "positive before a ratio means anything"
            ),
        )
    ratio = fast / slow
    if ratio >= policy.volatility_upper_edge:
        state = VolatilityState.EXPANDING
    elif ratio <= policy.volatility_lower_edge:
        state = VolatilityState.CONTRACTING
    else:
        state = VolatilityState.STEADY
    return RegimeDimension(
        name=RegimeDimensionName.VOLATILITY,
        state=state,
        evidence=(
            RegimeEvidence(
                source=FAMILY_TRUE_RANGE,
                status=EvidenceStatus.CONSISTENT,
                observed="fast / slow true-range ratio",
                value=ratio,
            ),
        ),
    )


def _participation_dimension(
    subject: RegimeInput, policy: RegimePolicy
) -> RegimeDimension:
    """Volume against its own recent average, as the ratio the feature already is."""
    relative = subject.participation_ratio
    if relative is None:
        return RegimeDimension(
            name=RegimeDimensionName.PARTICIPATION,
            state=ParticipationState.INSUFFICIENT,
            evidence=(
                RegimeEvidence(
                    source=FAMILY_VOLUME,
                    status=EvidenceStatus.UNAVAILABLE,
                    observed="not available",
                ),
            ),
            reason="relative volume is not available for this window",
        )
    if relative >= policy.participation_upper_edge:
        state = ParticipationState.ELEVATED
    elif relative <= policy.participation_lower_edge:
        state = ParticipationState.SUBDUED
    else:
        state = ParticipationState.TYPICAL
    return RegimeDimension(
        name=RegimeDimensionName.PARTICIPATION,
        state=state,
        evidence=(
            RegimeEvidence(
                source=FAMILY_VOLUME,
                status=EvidenceStatus.CONSISTENT,
                observed="volume against its own average",
                value=relative,
            ),
        ),
    )


def classify_regime(
    subject: RegimeInput, policy: RegimePolicy | None = None
) -> MarketRegime:
    """Three classified environments for one series at one instant.

    Args:
        subject: the facts to classify, already computed by the engines below.
        policy: the thresholds to apply; `DEFAULT_POLICY` when omitted. The
            policy is carried on the result, because a classification without
            its parameters cannot be reproduced.

    Returns:
        A `MarketRegime` whose dimensions are always **structure, volatility,
        participation**, in that order, each carrying its own evidence and its
        own reason when it declined to classify.

    Raises:
        TypeError: ``subject`` is not a `RegimeInput`, or ``policy`` is not a
            `RegimePolicy`.

    Pure: no state, no cache, no clock, no randomness, no network. The same input
    and policy always give the same result, and nothing about the machine it runs
    on can change it.
    """
    if not isinstance(subject, RegimeInput):
        raise TypeError(
            f"subject must be a RegimeInput, got {type(subject).__name__}"
        )
    if policy is None:
        policy = DEFAULT_POLICY
    if not isinstance(policy, RegimePolicy):
        raise TypeError(
            f"policy must be a RegimePolicy, got {type(policy).__name__}"
        )

    return MarketRegime(
        symbol=subject.symbol,
        timeframe=subject.timeframe,
        as_of=subject.as_of,
        dimensions=(
            _structure_dimension(subject, policy),
            _volatility_dimension(subject, policy),
            _participation_dimension(subject, policy),
        ),
        policy=policy,
        metadata=subject.metadata,
    )
