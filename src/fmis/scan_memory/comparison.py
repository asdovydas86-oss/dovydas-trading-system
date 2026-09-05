"""Two `ScanRecord`s in, one `ScanComparison` out. **Deterministic, and pure.**

**Structured state only.** Every dimension is read from a named field an engine
already decided. Not one sentence, paragraph, thesis line, blocker statement or
rendered fragment is compared anywhere in this module — a difference between two
English sentences is a difference in wording, and the operator would be told the
market changed because a message did.

**Nothing here can influence a decision.** The comparator reads two finished
records and returns a description of how they differ. It calls no policy, holds
no threshold and produces no input that any assessment consumes; a guard test
asserts that no module which computes a trading conclusion imports this package.

**Nothing here ranks.** Changed symbols come out in the scan's own universe
order, which is the order the operator asked for the symbols in. There is no
score, no weight, no urgency, no closeness and no field one could be written
into — a partition into *changed* and *not changed* is the whole of the
attention this surface provides.
"""

from __future__ import annotations

from fmis.scan_memory.models import (
    ABSENT,
    CHANGE_DIMENSIONS,
    PRESENT,
    STRUCTURE_DIMENSIONS,
    NOT_STATED,
    ChangeDimension,
    ComparisonStatus,
    ScanComparison,
    ScanMemoryError,
    ScanRecord,
    StateTransition,
    SymbolChange,
    SymbolState,
)

__all__ = [
    "INDEPENDENCE_ESTABLISHED",
    "INDEPENDENCE_NOT_ESTABLISHED",
    "EVIDENCE_PROJECTED",
    "EVIDENCE_DECLINED",
    "incomparable_reason",
    "dimension_values",
    "transitions_between",
    "compare_scans",
]

INDEPENDENCE_ESTABLISHED = "established"
INDEPENDENCE_NOT_ESTABLISHED = "not established"
EVIDENCE_PROJECTED = "the evidence projection ran"
EVIDENCE_DECLINED = "the evidence projection declined"


def _composition(state: SymbolState) -> str:
    """The four evidence groups as counts. **Counts, and never confidence.**

    `supporting 1 → supporting 2` is one more item in a group. It is not
    *stronger*, not *more likely* and not *closer to a trade*, and the wording
    here says nothing that could be read as any of the three.
    """
    return (
        f"supporting {state.supporting} · conflicting {state.conflicting} · "
        f"missing {state.missing} · unavailable {state.unavailable}"
    )


def dimension_values(state: SymbolState) -> dict[ChangeDimension, str]:
    """Every compared dimension of one symbol state, as text.

    The returned mapping's keys are exactly `CHANGE_DIMENSIONS` minus
    `PRESENCE`, which is a property of the *pair* rather than of one state. A
    test asserts that equality, so a dimension added to the enum and not read
    here fails rather than silently never firing.
    """
    values = {
        ChangeDimension.DECISION: state.state,
        ChangeDimension.POLICY_DIRECTION: state.direction or NOT_STATED,
        ChangeDimension.DECISION_CONTEXT: state.sufficiency,
        ChangeDimension.DEVELOPING_EVIDENCE: _developing(state),
        ChangeDimension.BLOCKER: state.blocker_kind or NOT_STATED,
        ChangeDimension.EVIDENCE_INDEPENDENCE: (
            INDEPENDENCE_ESTABLISHED
            if state.independence_established
            else INDEPENDENCE_NOT_ESTABLISHED
        ),
        ChangeDimension.EVIDENCE_AVAILABILITY: (
            EVIDENCE_PROJECTED if state.evidence_available else EVIDENCE_DECLINED
        ),
        ChangeDimension.EVIDENCE_COMPOSITION: _composition(state),
    }
    for role, dimension in STRUCTURE_DIMENSIONS:
        values[dimension] = state.trend_for(role) or NOT_STATED
    return values


def _developing(state: SymbolState) -> str:
    """The developing-evidence state and the side it names, as one dimension.

    They are one dimension because they are one fact: *which way did what could
    be read point*. Reporting them separately would let a page show a side
    changing with no state beside it, which is the developing-evidence summary
    detached from the policy conclusion it must never be shown without.
    """
    if state.developing_state is None:
        return NOT_STATED
    if state.developing_lean is None:
        return state.developing_state
    return f"{state.developing_state} · {state.developing_lean}"


def incomparable_reason(previous: ScanRecord, current: ScanRecord) -> str:
    """Why these two scans may not be compared, or `""` when they may.

    **A previous scan is comparable when everything except the instant matches.**
    Schema, watchlist and timeframe roles are the three, and each one is a
    reason a delta between the two records would describe a different question
    rather than a changed market.
    """
    if previous.identity.schema_version != current.identity.schema_version:
        return (
            f"the previous scan was recorded under schema "
            f"{previous.identity.schema_version} and this build writes schema "
            f"{current.identity.schema_version}"
        )
    if previous.identity.universe != current.identity.universe:
        return (
            "the previous scan covered a different watchlist, so a difference "
            "between the two would describe a different scan rather than a "
            "changed market"
        )
    if previous.identity.timeframes != current.identity.timeframes:
        return (
            "the previous scan was run over different timeframe roles, so its "
            "structural states answer a different question"
        )
    if not previous.complete:
        return (
            "the previous scan did not cover every symbol its watchlist asked "
            "for, so it is not a baseline"
        )
    if previous.scan_id == current.scan_id:
        return "the previous record is this same scan"
    return ""


def transitions_between(
    previous: SymbolState, current: SymbolState
) -> tuple[StateTransition, ...]:
    """Every dimension on which two states of one symbol differ.

    In `CHANGE_DIMENSIONS` order, which is declaration order and **not** an
    importance order. Only differing dimensions produce a transition, so an
    unchanged dimension can never appear as changed.
    """
    if previous.symbol != current.symbol:
        raise ScanMemoryError(
            f"cannot compare {previous.symbol} with {current.symbol}; a "
            "transition is one market's two states, never two markets"
        )
    before = dimension_values(previous)
    after = dimension_values(current)
    return tuple(
        StateTransition(dimension=dimension, previous=before[dimension], current=after[dimension])
        for dimension in CHANGE_DIMENSIONS
        if dimension in before and before[dimension] != after[dimension]
    )


def _presence(dimension_previous: str, dimension_current: str) -> StateTransition:
    return StateTransition(
        dimension=ChangeDimension.PRESENCE,
        previous=dimension_previous,
        current=dimension_current,
    )


def compare_scans(previous: ScanRecord, current: ScanRecord) -> ScanComparison:
    """This scan beside the previous comparable completed one.

    **Neither argument is mutated and neither is read for anything but its own
    fields.** `compare_scans(record, record)` is refused by
    `incomparable_reason` — it is the same scan — and two *equal* records under
    different identities produce zero changes, which is the invariant the
    property tests assert.

    Symbols come out in the current scan's own universe order. Changed symbols
    are separated from unchanged ones because the operator needs to find them,
    and that partition is the only ordering this function performs.
    """
    for name, record in (("previous", previous), ("current", current)):
        if not isinstance(record, ScanRecord):
            raise ScanMemoryError(f"{name} must be a ScanRecord")
    reason = incomparable_reason(previous, current)
    if reason:
        return ScanComparison(
            status=ComparisonStatus.NOT_COMPARABLE,
            current_scan_at=current.identity.reference_time,
            reason=reason,
        )

    changes: list[SymbolChange] = []
    unchanged: list[str] = []
    for symbol in current.identity.universe:
        before = previous.state_for(symbol)
        after = current.state_for(symbol)
        if before is None and after is None:
            unchanged.append(symbol)
            continue
        if before is None and after is not None:
            changes.append(
                SymbolChange(
                    symbol=symbol,
                    state=after.state,
                    previous_state=ABSENT,
                    transitions=(_presence(ABSENT, PRESENT),),
                )
            )
            continue
        if after is None:
            changes.append(
                SymbolChange(
                    symbol=symbol,
                    state=ABSENT,
                    previous_state=before.state,
                    transitions=(_presence(PRESENT, ABSENT),),
                )
            )
            continue
        transitions = transitions_between(before, after)
        if transitions:
            changes.append(
                SymbolChange(
                    symbol=symbol,
                    state=after.state,
                    previous_state=before.state,
                    transitions=transitions,
                )
            )
        else:
            unchanged.append(symbol)

    return ScanComparison(
        status=ComparisonStatus.COMPARED,
        current_scan_at=current.identity.reference_time,
        previous_scan_at=previous.identity.reference_time,
        changes=tuple(changes),
        unchanged=tuple(unchanged),
    )
