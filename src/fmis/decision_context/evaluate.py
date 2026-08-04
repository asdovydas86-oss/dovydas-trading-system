"""Evaluating whether an analysis rests on enough trustworthy information.

One public function, `evaluate_context`. It reads a `ContextInput` and a
`ContextPolicy` and returns a `DecisionContext`. It fetches nothing, computes no
market quantity, and reads no clock.

**Every requirement delegates.** Not one threshold is invented here: depth is
compared against the caller's own `required_candles`, warm-up against the feature
engine's own metadata, regime determinacy against `fmis.market_regime`'s
`INSUFFICIENT` state, structure against whether `fmis.level_crossing` produced a
level, and evidence against the verdict ADR-0008 §7 already reached. A reader who
disagrees with an answer goes to the layer that produced it.

**Conflicts are read and never counted.** They are carried into the result's
metadata so a page can show them beside the verdict, and they do not move the
verdict by one step. Sufficiency is a statement about what is *available*; a
market whose timeframes disagree is still analysable, and penalising
disagreement would reward pages that look tidy by being one-sided — the shape of
failure `docs/analysis-notes.md` records. A test asserts that varying the
conflict count changes no state and no check.

**The judgement is about the primary view.** The other views contribute their
own adequacy to the result's metadata, but the question — *can this analysis be
continued* — is asked of the timeframe the objective calls primary, because that
is the one a setup would be built on.
"""

from __future__ import annotations

from fmis.decision_context.models import (
    SEVERITY,
    ContextInput,
    ContextState,
    DecisionContext,
    Requirement,
    RequirementCheck,
    Severity,
    REQUIREMENT_ORDER,
)
from fmis.decision_context.policy import DEFAULT_CONTEXT_POLICY, ContextPolicy

__all__ = ["evaluate_context", "SOURCES"]

#: Which layer owns each rule. Rendered beside every check, so the delegation is
#: visible to a reader rather than merely true in the source.
SOURCES: dict[Requirement, str] = {
    Requirement.PRIMARY_DATA_DEPTH: "fmis.market_structure.required_candles",
    Requirement.WARM_UP_COMPLETE: "fmis.features (warm-up metadata)",
    Requirement.REGIME_DETERMINATE: "fmis.market_regime (ADR-0025)",
    Requirement.STRUCTURE_PRESENT: "fmis.level_crossing",
    Requirement.EVIDENCE_PRESENT: "fmis.decision_support (ADR-0008 §7)",
}


def _depth(subject: ContextInput) -> RequirementCheck:
    view = subject.primary
    met = view.has_enough_candles
    statement = (
        f"{view.label} has {view.closed_candles} closed candles; detection "
        f"requires {view.required_candles}"
    )
    return RequirementCheck(
        requirement=Requirement.PRIMARY_DATA_DEPTH,
        met=met,
        severity=SEVERITY[Requirement.PRIMARY_DATA_DEPTH],
        statement=statement,
        source=SOURCES[Requirement.PRIMARY_DATA_DEPTH],
    )


def _warm_up(subject: ContextInput) -> RequirementCheck:
    view = subject.primary
    met = view.warming_up == 0
    statement = (
        f"{view.label} has no feature still warming up"
        if met
        else f"{view.label} has {view.warming_up} feature(s) still warming up"
    )
    return RequirementCheck(
        requirement=Requirement.WARM_UP_COMPLETE,
        met=met,
        severity=SEVERITY[Requirement.WARM_UP_COMPLETE],
        statement=statement,
        source=SOURCES[Requirement.WARM_UP_COMPLETE],
    )


def _regime(subject: ContextInput) -> RequirementCheck:
    view = subject.primary
    met = view.dimensions_insufficient == 0
    statement = (
        f"{view.label} classified every regime dimension"
        if met
        else (
            f"{view.label} could not classify {view.dimensions_insufficient} "
            "regime dimension(s) for want of evidence"
        )
    )
    return RequirementCheck(
        requirement=Requirement.REGIME_DETERMINATE,
        met=met,
        severity=SEVERITY[Requirement.REGIME_DETERMINATE],
        statement=statement,
        source=SOURCES[Requirement.REGIME_DETERMINATE],
    )


def _structure(subject: ContextInput) -> RequirementCheck:
    view = subject.primary
    met = view.level_count > 0
    statement = (
        f"{view.label} produced {view.level_count} structural level(s)"
        if met
        else f"{view.label} produced no structural level to read price against"
    )
    return RequirementCheck(
        requirement=Requirement.STRUCTURE_PRESENT,
        met=met,
        severity=SEVERITY[Requirement.STRUCTURE_PRESENT],
        statement=statement,
        source=SOURCES[Requirement.STRUCTURE_PRESENT],
    )


def _evidence(subject: ContextInput) -> RequirementCheck:
    met = not subject.evidence_is_insufficient
    statement = (
        "the evidence layer had enough directional observations to speak"
        if met
        else "the evidence layer reported insufficient directional observations"
    )
    return RequirementCheck(
        requirement=Requirement.EVIDENCE_PRESENT,
        met=met,
        severity=SEVERITY[Requirement.EVIDENCE_PRESENT],
        statement=statement,
        source=SOURCES[Requirement.EVIDENCE_PRESENT],
    )


#: One evaluator per requirement, in reporting order. A registry rather than a
#: sequence of calls, so a future requirement is one entry and its absence from
#: `REQUIREMENT_ORDER` fails loudly instead of silently going unreported.
_EVALUATORS = {
    Requirement.PRIMARY_DATA_DEPTH: _depth,
    Requirement.WARM_UP_COMPLETE: _warm_up,
    Requirement.REGIME_DETERMINATE: _regime,
    Requirement.STRUCTURE_PRESENT: _structure,
    Requirement.EVIDENCE_PRESENT: _evidence,
}


def evaluate_context(
    subject: ContextInput, policy: ContextPolicy | None = None
) -> DecisionContext:
    """Whether this analysis contains enough trustworthy information to continue.

    Args:
        subject: the facts to judge, already produced by the layers below.
        policy: the ruleset to cite; `DEFAULT_CONTEXT_POLICY` when omitted. Under
            ``strict`` every limiting gap is treated as blocking.

    Returns:
        A `DecisionContext` reporting **every** requirement — met ones included,
        because a reader needs to know what was checked, not only what failed —
        in `REQUIREMENT_ORDER`, with the policy carried on the result.

    Raises:
        TypeError: ``subject`` is not a `ContextInput`, or ``policy`` is not a
            `ContextPolicy`.

    Pure: no state, no cache, no clock, no randomness, no network. The same input
    and policy always give the same result.
    """
    if not isinstance(subject, ContextInput):
        raise TypeError(
            f"subject must be a ContextInput, got {type(subject).__name__}"
        )
    if policy is None:
        policy = DEFAULT_CONTEXT_POLICY
    if not isinstance(policy, ContextPolicy):
        raise TypeError(
            f"policy must be a ContextPolicy, got {type(policy).__name__}"
        )

    checks = tuple(_EVALUATORS[requirement](subject) for requirement in REQUIREMENT_ORDER)

    unmet = [check for check in checks if not check.met]
    blocking = [
        check
        for check in unmet
        if check.severity is Severity.BLOCKING or policy.strict
    ]

    if blocking:
        state = ContextState.INSUFFICIENT
    elif unmet:
        state = ContextState.LIMITED
    else:
        state = ContextState.SUFFICIENT

    return DecisionContext(
        symbol=subject.symbol,
        as_of=subject.as_of,
        state=state,
        checks=checks,
        policy=policy,
        metadata={
            "primary_role": subject.primary_role,
            "view_count": len(subject.views),
            # Carried so a page can show conflicts beside the verdict, and
            # deliberately not read by any rule above.
            "conflict_count": subject.conflict_count,
            **dict(subject.metadata),
        },
    )
