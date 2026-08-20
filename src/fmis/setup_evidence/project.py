"""Project a `SetupAssessment` into structured, queryable evidence.

**A projection, not a second decision engine.** Every statement this module
emits was already produced by `fmis.swing_setup`; what happens here is grouping,
family attribution from the ADR-0011 vocabulary, and the correlation analysis
that stops one upstream fact being read as several. Nothing is re-decided, no
market quantity is computed, and no threshold is applied to any number.

The single hardest rule, stated once: **`decision_ready` is a function of
`SetupAssessment.sufficiency` and of nothing else.** `decision_ready_for` takes
the `ContextState` alone, so there is no input through which a second opinion
could enter. A test varies every other field on the assessment and asserts the
answer never moves.

What this module deliberately does not do:

  * recompute a level, a ratio, an indicator or a regime;
  * re-tally the directional factors, or second-guess which side won;
  * assign a strength, weight, score, confidence or rank to anything;
  * treat correlated readings as independent corroboration.

The last is the one a reader cannot check for themselves, which is why
`fmis.setup_evidence.correlation` holds it explicitly and this module never
counts agreement without consulting it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from fmis.decision_context import ContextState
from fmis.setup_evidence.correlation import (
    FACTOR_FAMILIES,
    KEY_CALIBRATION,
    KEY_CONFIRMATION,
    KEY_CONTEXT_TREND,
    KEY_GEOMETRY,
    KEY_REGIME_GATE,
    KNOWN_CORRELATIONS,
    correlated_keys_for,
    correlations_for,
    family_order,
    independent_pairs_exist,
    sorted_families,
)
from fmis.setup_evidence.models import (
    SETUP_EVIDENCE_PROJECTION_VERSION,
    ConfluenceSummary,
    EvidenceItem,
    SetupEvidenceStatus,
    FamilySummary,
    SetupEvidenceError,
    SetupEvidenceReport,
    SetupIdentityRef,
)
from fmis.swing_setup import Lean, SetupAssessment, SetupState
from fmis.swing_setup.policy import RESEARCH_POLICY_ID_PREFIX

__all__ = [
    "decision_ready_for",
    "DECISION_READY_REASONS",
    "project_setup_evidence",
]

#: Which `ContextState` values mean the analysis may continue. Written as a
#: complete mapping over the enum rather than as a negation, so a fourth
#: `ContextState` member added later fails loudly here instead of silently
#: defaulting to ready.
_READY_BY_STATE: dict[ContextState, bool] = {
    ContextState.SUFFICIENT: True,
    ContextState.LIMITED: True,
    ContextState.INSUFFICIENT: False,
}

#: The sentence printed beside each state. These restate `ContextState`'s own
#: documented meaning and add nothing to it — `LIMITED` is ready *with the named
#: limitation attached*, which is what that state already says.
DECISION_READY_REASONS: dict[ContextState, str] = {
    ContextState.SUFFICIENT: (
        "every requirement the layers below stated was met; the assessment "
        "rests on the data each of them said it needed"
    ),
    ContextState.LIMITED: (
        "nothing blocking is missing, but something is degraded; the assessment "
        "stands with the limitations below attached to it, not without them"
    ),
    ContextState.INSUFFICIENT: (
        "a blocking requirement is unmet; continuing from here would be "
        "reasoning from data the system already knows is not there"
    ),
}

def decision_ready_for(sufficiency: ContextState) -> bool:
    """Whether enough deterministic information exists. **Never a trade decision.**

    A total function of ``sufficiency`` alone. This is the whole rule, and it is
    deliberately not derived from the evidence groups, the confluence, the state
    or the direction: `fmis.decision_context` already decided whether the
    information is adequate, and a second computation here would be a second
    answer that could disagree with the first.

    `LIMITED` is ready. That is `ContextState`'s own meaning — nothing blocking
    is missing — and the degradation travels with the report as a limitation
    rather than as a veto.

    Raises:
        TypeError: ``sufficiency`` is not a `ContextState`.
    """
    if not isinstance(sufficiency, ContextState):
        raise TypeError(
            f"sufficiency must be a ContextState, got {type(sufficiency).__name__}"
        )
    return _READY_BY_STATE[sufficiency]


def _factor_items(assessment: SetupAssessment) -> tuple[tuple[EvidenceItem, ...], tuple[str, ...]]:
    """One item per directional factor, plus any warnings raised while mapping.

    Status is assigned by the factor's own lean and the assessment's own
    direction — never by re-tallying:

      * a lean that agrees with the assessment's direction is `SUPPORTING`;
      * a lean that opposes it is `CONFLICTING`. Policy v1 cannot produce one
        (a candidate requires zero opposing votes), so this branch is
        unreachable today; it is represented rather than assumed away, because
        an unrepresentable state is one a future policy change turns into a
        silent mis-grouping;
      * a lean present on a `WAIT` assessment is `SUPPORTING` of *that family's
        own reading only*, and its statement says so together with the quorum
        the policy did not reach;
      * `CONFLICTING` means the family disagreed with itself, which is a real
        conflict and not an absence;
      * `UNAVAILABLE` means nothing could be read.

    A lean is compared by its **runtime value**, never by naming a member.
    `fmis.setup_evidence` sits outside the one package ADR-0028 permits to spell
    a direction, so `factor.lean.value == direction_value` is how agreement is
    tested here; the answer is identical and the vocabulary boundary holds.
    """
    items: list[EvidenceItem] = []
    warnings: list[str] = []
    direction_value = None if assessment.direction is None else assessment.direction.value

    for factor in assessment.directional_factors:
        families = FACTOR_FAMILIES.get(factor.family)
        if families is None:
            families = ()
            warnings.append(
                f"Directional factor {factor.family!r} has no entry in the "
                "ADR-0011 family vocabulary, so it is reported without a family "
                "and can establish no independence. Adding one is a deliberate "
                "taxonomy change, never a guess made here."
            )
        key = f"factor:{factor.family}"

        if factor.lean is Lean.UNAVAILABLE:
            status = SetupEvidenceStatus.UNAVAILABLE
            statement = (
                f"{factor.family} could not be read at all, and cast no vote."
            )
        elif factor.lean is Lean.CONFLICTING:
            status = SetupEvidenceStatus.CONFLICTING
            statement = (
                f"{factor.family} disagrees with itself ({factor.observed}) and "
                "cast no vote. Something was read; it did not agree."
            )
        elif direction_value is None:
            status = SetupEvidenceStatus.SUPPORTING
            statement = (
                f"{factor.family} leans {factor.lean.value} ({factor.observed}), "
                "but no directional candidate was formed — the policy requires "
                "agreement from more than one independent family, with none "
                "opposing."
            )
        elif factor.lean.value == direction_value:
            status = SetupEvidenceStatus.SUPPORTING
            statement = (
                f"{factor.family} leans {factor.lean.value} ({factor.observed}), "
                "agreeing with the assessment."
            )
        else:
            status = SetupEvidenceStatus.CONFLICTING
            statement = (
                f"{factor.family} leans {factor.lean.value} ({factor.observed}), "
                "against the assessment."
            )

        notes = tuple(rule.reason for rule in correlations_for(key))
        items.append(
            EvidenceItem(
                key=key,
                families=families,
                status=status,
                statement=statement,
                observed=factor.observed,
                source=factor.source,
                scope=factor.source,
                as_of=assessment.as_of,
                inputs={"lean": factor.lean.value, "family": factor.family},
                correlated_with=correlated_keys_for(key),
                independence_note=" ".join(notes) if notes else None,
            )
        )
    return tuple(items), tuple(warnings)


def _regime_item(assessment: SetupAssessment) -> EvidenceItem | None:
    """The regime precondition, reported without re-deriving it.

    `SetupAssessment` carries the regime as rendered lines, not as enums, so the
    only honest readings available here are the two the assessment's own state
    proves:

      * a `CANDIDATE` or `CONFIRMED` result **proves** the precondition was met —
        `fmis.swing_setup.policy` returns `WAIT` before anything else when the
        context regime structure is not trending;
      * a `WAIT` result does **not** say which precondition stopped it, and this
        package will not parse the rendered line to find out. The item is
        reported `UNAVAILABLE` with the verbatim line, and the thesis — carried
        unchanged — states the actual reason.

    ``families`` is empty on purpose. `StructureState` classifies an
    *environment* and is explicitly not a direction (ADR-0025), so it maps to no
    ADR-0011 family, and inventing a catch-all family for it was ruled out. An
    item with no family can never establish independence, which is exactly right
    here: the precondition is not a second opinion about the trend, it is the
    same reading used as a gate.
    """
    if not assessment.regime_context:
        return None
    observed = assessment.regime_context[0]
    notes = tuple(rule.reason for rule in correlations_for(KEY_REGIME_GATE))
    if assessment.state is SetupState.WAIT:
        status = SetupEvidenceStatus.UNAVAILABLE
        statement = (
            "The regime precondition's outcome is not separately recorded on a "
            "WAIT assessment. The thesis states which condition stopped it."
        )
    else:
        status = SetupEvidenceStatus.SUPPORTING
        statement = (
            "The context-role regime precondition was met — a directional "
            "candidate exists, which this policy reaches only after the context "
            "regime structure reads as trending. A precondition, not a "
            "directional vote."
        )
    return EvidenceItem(
        key=KEY_REGIME_GATE,
        families=(),
        status=status,
        statement=statement,
        observed=observed,
        source="market_regime (context role)",
        as_of=assessment.as_of,
        inputs={"regime_context": assessment.regime_context},
        correlated_with=correlated_keys_for(KEY_REGIME_GATE),
        independence_note=" ".join(notes) if notes else None,
    )


def _confirmation_item(assessment: SetupAssessment) -> EvidenceItem | None:
    """The confirmation condition — occurred, or awaited. One item, never two.

    **The trigger is not projected separately, because it is not separate.**
    `fmis.swing_setup.policy` builds `Trigger.statement` from the very string it
    puts in `confirmation[0]`, on both branches, so emitting both would put one
    sentence in the report twice under two headings. The trigger's level and bar
    index — the parts that *are* additional — are carried in this item's inputs.
    """
    if not assessment.confirmation:
        return None
    statement = assessment.confirmation[0]
    occurred = assessment.state is SetupState.CONFIRMED
    trigger = assessment.trigger
    inputs: dict[str, object] = {"confirmation": assessment.confirmation}
    if trigger is not None:
        inputs["trigger_kind"] = trigger.kind.value
        if trigger.level is not None:
            inputs["trigger_level"] = trigger.level.price
        if trigger.bar_index is not None:
            inputs["trigger_bar_index"] = trigger.bar_index
    return EvidenceItem(
        key=KEY_CONFIRMATION,
        families=(),
        status=SetupEvidenceStatus.SUPPORTING if occurred else SetupEvidenceStatus.MISSING,
        statement=statement,
        observed=(
            "confirmation occurred" if occurred else "confirmation not yet occurred"
        ),
        source="fmis.swing_setup.policy",
        as_of=assessment.as_of,
        inputs=inputs,
        independence_note=" ".join(
            rule.reason for rule in correlations_for(KEY_CONFIRMATION)
        )
        or None,
    )


def _geometry_item(assessment: SetupAssessment) -> EvidenceItem | None:
    """Risk geometry as **one** item — the level, its restatement and the ratio.

    The protective level appears three times on a `SetupAssessment`: as `stop`,
    restated inside the `invalidation` line (whose own text says it is the same
    level), and again inside `risk_reward`. They are one geometric fact, and
    this projects them once.

    ``families`` is empty: risk geometry is not one of ADR-0011's ten subject
    areas, and RISK_GEOMETRY was considered and rejected as a new family for
    this milestone. An unfamilied item cannot inflate confluence, which is the
    correct outcome — a favourable ratio is not corroboration of a direction.
    """
    if assessment.direction is None:
        return None
    risk_reward = assessment.risk_reward
    if risk_reward is not None:
        status = SetupEvidenceStatus.SUPPORTING
        statement = (
            "Risk geometry is measurable: a protective level and a target both "
            "exist in the analysed window, so the ratio is computed rather than "
            "estimated."
        )
        observed = f"ratio {risk_reward.ratio:,.2f}"
        inputs = {
            "reference_price": risk_reward.entry,
            "protective_level": risk_reward.stop,
            "objective_level": risk_reward.target,
            "risk": risk_reward.risk,
            "reward": risk_reward.reward,
            "ratio": risk_reward.ratio,
        }
    elif assessment.stop is not None:
        status = SetupEvidenceStatus.MISSING
        statement = (
            "A protective level exists but no objective level was available in "
            "the analysed window, so no ratio is computed. Not estimated."
        )
        observed = "protective level only"
        inputs = {"protective_level": assessment.stop.price}
    else:
        status = SetupEvidenceStatus.MISSING
        statement = (
            "No structural protective level is available in the current "
            "execution-timeframe window, so no ratio is computed."
        )
        observed = "no protective level"
        inputs = {}
    notes = tuple(rule.reason for rule in correlations_for(KEY_GEOMETRY))
    return EvidenceItem(
        key=KEY_GEOMETRY,
        families=(),
        status=status,
        statement=statement,
        observed=observed,
        source="fmis.swing_setup.policy",
        as_of=assessment.as_of,
        inputs=inputs,
        independence_note=" ".join(notes) if notes else None,
    )


def _calibration_item(assessment: SetupAssessment) -> EvidenceItem:
    """The absence of a calibrated probability, stated rather than omitted."""
    return EvidenceItem(
        key=KEY_CALIBRATION,
        families=(),
        status=SetupEvidenceStatus.UNAVAILABLE,
        statement=(
            "No calibrated probability exists for this setup. This repository "
            "has no calibrated statistical model, so none is produced — the "
            "absence is reported, never filled with an estimate."
        ),
        observed=assessment.probability.status.value,
        source="fmis.swing_setup.models",
        as_of=assessment.as_of,
        inputs={"probability_value": assessment.probability.value},
    )


def _factor_restatement_lines(assessment: SetupAssessment) -> frozenset[str]:
    """The limitation lines that merely restate a factor already projected.

    `fmis.swing_setup.policy` appends one limitation per family that cast no
    vote, in two fixed forms. Every one of them restates a `DirectionalFactor`
    this projection has *already* emitted as a CONFLICTING or UNAVAILABLE item,
    so carrying both puts one fact in two sections of the page under two
    headings — which is the double-counting this package exists to prevent,
    appearing in the report's own layout rather than in its arithmetic. Found on
    the live `BTCUSDT` page, where all three factors were reported twice.

    **The lines are regenerated, never parsed.** The two forms are rebuilt from
    the assessment's own factors and matched exactly; nothing reads the text of
    a limitation to decide what it means. A test asserts the reconstruction
    still matches what the policy actually emits, so a change to that wording
    fails loudly instead of silently letting the duplicates return.
    """
    lines: set[str] = set()
    for factor in assessment.directional_factors:
        lines.add(
            f"{factor.family} conflicts with itself ({factor.observed}) and "
            "cast no vote."
        )
        lines.add(f"{factor.family} was unavailable and cast no vote.")
    return frozenset(lines)


def _limitation_items(assessment: SetupAssessment) -> tuple[EvidenceItem, ...]:
    """One item per **distinct** limitation line, in first-seen order.

    Limitations are inherited from every layer below and concatenated, so the
    same line can genuinely arrive twice. Repeats are collapsed here rather than
    reported as two separate gaps, and lines that restate an already-projected
    factor are dropped entirely — see `_factor_restatement_lines`.
    """
    items: list[EvidenceItem] = []
    seen: set[str] = set(_factor_restatement_lines(assessment))
    for line in assessment.limitations:
        if line in seen:
            continue
        seen.add(line)
        items.append(
            EvidenceItem(
                key=f"limitation:{len(items)}",
                families=(),
                status=SetupEvidenceStatus.UNAVAILABLE,
                statement=line,
                observed="limitation inherited or raised by this analysis",
                source=assessment.source,
                as_of=assessment.as_of,
                inputs={"text": line},
            )
        )
    return tuple(items)


def _deduplicate(items: Sequence[EvidenceItem]) -> tuple[EvidenceItem, ...]:
    """Collapse identical items; refuse to merge different ones sharing a key.

    Two items with the same key and the same content are one item observed
    twice, and keeping both would present a single fact as corroborating itself.
    Two items with the same key and *different* content are a defect in the
    projection, not a duplicate, and are raised rather than silently merged —
    picking a winner would hide whichever one was wrong.
    """
    by_key: dict[str, EvidenceItem] = {}
    ordered: list[EvidenceItem] = []
    for item in items:
        existing = by_key.get(item.key)
        if existing is None:
            by_key[item.key] = item
            ordered.append(item)
            continue
        if existing != item:
            raise SetupEvidenceError(
                f"two different evidence items share the key {item.key!r}; "
                "an evidence key must identify exactly one item"
            )
    return tuple(ordered)


def _prune_correlations(items: tuple[EvidenceItem, ...]) -> tuple[EvidenceItem, ...]:
    """Drop correlation links to items this report does not actually hold.

    A declared correlation names two keys, but either may be absent from a given
    report: an assessment carrying no regime context produces no regime item,
    and the context-trend factor would then point at nothing. `SetupEvidenceReport`
    rejects a dangling reference — correctly, because a page citing *"not
    independent of: regime:structure_gate"* beside no such entry is unreadable —
    so the link is pruned here rather than allowed to raise.

    Found by a test over an assessment with an empty ``regime_context``: the
    projection raised instead of producing a report. The item itself is never
    removed and its `independence_note` is untouched; only the cross-reference
    to an absent item goes.
    """
    present = {item.key for item in items}
    return tuple(
        item
        if set(item.correlated_with) <= present
        else replace(
            item,
            correlated_with=tuple(
                key for key in item.correlated_with if key in present
            ),
        )
        for item in items
    )


def _family_summary(items: tuple[EvidenceItem, ...]) -> tuple[FamilySummary, ...]:
    """Counts per family, in `EvidenceFamily` declaration order. Derived."""
    counts: dict[object, dict[str, int]] = {}
    for item in items:
        for family in item.families:
            bucket = counts.setdefault(
                family,
                {"supporting": 0, "conflicting": 0, "missing": 0, "unavailable": 0},
            )
            bucket[item.status.value] += 1
    return tuple(
        FamilySummary(
            family=family,
            supporting=bucket["supporting"],
            conflicting=bucket["conflicting"],
            missing=bucket["missing"],
            unavailable=bucket["unavailable"],
        )
        for family, bucket in sorted(
            counts.items(), key=lambda pair: family_order(pair[0])
        )
    )


def _confluence(
    supporting: tuple[EvidenceItem, ...],
    conflicting: tuple[EvidenceItem, ...],
    present_keys: frozenset[str],
) -> ConfluenceSummary:
    """Family-level agreement, computed from the items each time.

    Only items that carry a family take part; geometry, calibration and the
    regime precondition hold none and cannot inflate the count, by construction.

    Agreement is measured over *families*, never items. Three items that all
    draw on TREND are one family's worth of agreement — the distinction this
    whole module exists to preserve.

    On a `WAIT` assessment the supporting items can carry **different** leans,
    which is not an agreeing set at all. That case reports no agreeing families
    and says why, rather than summing leans that point different ways.
    """
    with_family = tuple(item for item in supporting if item.families)
    leans = {item.inputs.get("lean") for item in with_family}
    caveats: list[str] = []

    if len(leans) > 1:
        agreeing: tuple[EvidenceItem, ...] = ()
        caveats.append(
            "The families that could be read do not share one lean, so there is "
            "no agreeing set to summarise. Each is reported on its own above."
        )
    else:
        agreeing = with_family

    agreeing_families = sorted_families(
        [family for item in agreeing for family in item.families]
    )
    conflicting_families = sorted_families(
        [family for item in conflicting for family in item.families]
    )

    established = independent_pairs_exist(agreeing)
    for rule in KNOWN_CORRELATIONS:
        if not set(rule.keys) <= present_keys:
            continue
        if not set(rule.keys) & {item.key for item in agreeing}:
            continue
        caveats.append(rule.reason)

    if agreeing and not established:
        caveats.append(
            "No two agreeing items are independent readings: every pair either "
            "shares an evidence family or shares an upstream input named above. "
            "Read the agreement as one subject area seen more than once, not as "
            "corroboration from separate sources."
        )

    return ConfluenceSummary(
        agreeing_families=agreeing_families,
        conflicting_families=conflicting_families,
        agreeing_item_count=len(agreeing),
        independent_agreeing_families=len(agreeing_families),
        independence_established=established,
        derived_from=tuple(sorted(item.key for item in agreeing)),
        caveats=tuple(caveats),
    )


def project_setup_evidence(
    assessment: SetupAssessment,
    *,
    setup_identity: SetupIdentityRef | None = None,
) -> SetupEvidenceReport:
    """Project one `SetupAssessment` into a `SetupEvidenceReport`. Pure.

    Reads the assessment and nothing else: no network, no clock, no randomness,
    no engine call, no candle. Equal assessments always produce an equal report.

    ``setup_identity`` is supplied by the composition root when it has one. This
    package derives no identity — `fmis.proposal.setup_identity` owns that rule.

    Raises:
        TypeError: ``assessment`` is not a `SetupAssessment`, or
            ``setup_identity`` is not a `SetupIdentityRef` or ``None``.
        SetupEvidenceError: the projection produced two different items sharing
            one key, which is a defect rather than a duplicate.
    """
    if not isinstance(assessment, SetupAssessment):
        raise TypeError(
            f"assessment must be a SetupAssessment, got {type(assessment).__name__}"
        )
    if setup_identity is not None and not isinstance(setup_identity, SetupIdentityRef):
        raise TypeError(
            "setup_identity must be a SetupIdentityRef or None, got "
            f"{type(setup_identity).__name__}"
        )

    factor_items, warnings = _factor_items(assessment)
    optional = (
        _regime_item(assessment),
        _confirmation_item(assessment),
        _geometry_item(assessment),
    )
    items = _deduplicate(
        (
            *factor_items,
            *(item for item in optional if item is not None),
            _calibration_item(assessment),
            *_limitation_items(assessment),
        )
    )
    items = _prune_correlations(items)

    grouped = {status: tuple(i for i in items if i.status is status) for status in SetupEvidenceStatus}
    supporting = grouped[SetupEvidenceStatus.SUPPORTING]
    conflicting = grouped[SetupEvidenceStatus.CONFLICTING]
    missing = grouped[SetupEvidenceStatus.MISSING]
    unavailable = grouped[SetupEvidenceStatus.UNAVAILABLE]

    confluence = _confluence(
        supporting, conflicting, frozenset(item.key for item in items)
    )

    warning_lines = list(warnings)
    if assessment.policy_id.startswith(RESEARCH_POLICY_ID_PREFIX):
        warning_lines.append(
            "This assessment was produced under a research override and is not "
            "what the live product would have said. Policy: "
            f"{assessment.policy_id}."
        )
    if assessment.sufficiency is ContextState.LIMITED:
        warning_lines.append(
            "Decision context is LIMITED: the assessment stands with the "
            "limitations attached to it, not without them."
        )
    if confluence.agreeing_item_count and not confluence.independence_established:
        warning_lines.append(
            "Agreement among the readable families is not independent "
            "corroboration — see FAMILY CONFLUENCE for which inputs are shared."
        )
    if KEY_CONTEXT_TREND in {item.key for item in supporting} and (
        KEY_REGIME_GATE in {item.key for item in supporting}
    ):
        warning_lines.append(
            "The regime precondition and the context trend factor are the same "
            "reading used twice: once as a gate and once as a vote. Passing the "
            "gate guarantees the vote, so the two together are one fact."
        )

    # Derived from `missing` **only**, and deliberately not from `unavailable`.
    # An open question is one that still has an answer coming — an awaited
    # confirmation, a geometry that needs a level to appear. An unavailable item
    # has no answer pending: the data is not there, and listing it as a question
    # would suggest waiting would resolve it. Including both would also make
    # this an exact duplicate of two groups the report already carries.
    open_questions = tuple(f"{item.key}: {item.statement}" for item in missing)

    direction_text = (
        None if assessment.direction is None else assessment.direction.value.upper()
    )
    return SetupEvidenceReport(
        symbol=assessment.symbol,
        as_of=assessment.as_of,
        state_text=assessment.state.value.upper(),
        direction_text=direction_text,
        thesis=assessment.thesis,
        supporting=supporting,
        conflicting=conflicting,
        missing=missing,
        unavailable=unavailable,
        invalidation=assessment.invalidation,
        regime_context=assessment.regime_context,
        family_summary=_family_summary(items),
        confluence=confluence,
        sufficiency=assessment.sufficiency,
        decision_ready=decision_ready_for(assessment.sufficiency),
        decision_ready_reason=DECISION_READY_REASONS[assessment.sufficiency],
        warnings=tuple(warning_lines),
        open_questions=open_questions,
        setup_identity=setup_identity,
        provenance={
            "policy_id": assessment.policy_id,
            "source": assessment.source,
            "objective": assessment.objective,
            "setup_schema_version": assessment.schema_version,
            "projection_version": SETUP_EVIDENCE_PROJECTION_VERSION,
        },
    )
