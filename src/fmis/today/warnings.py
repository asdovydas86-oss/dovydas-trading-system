"""The deterministic rules that produce this workspace's warnings.

**Every rule here is arithmetic over a value some engine already computed, or a
count of records the store already holds.** Nothing is estimated, nothing is
scored, and no rule consults a model. A rule that could not be written as *"this
count exceeds that count"* or *"this field is absent"* is not in this module.

**Every rule names its source.** `WorkspaceWarning.evidence` carries the
specification section, ADR or measured artifact the rule comes from, and a test
asserts no rule ships without one. The two rules backed by a measurement also
carry that measurement's full form — statement, `n` and caveat — because
`SWING_TRADING_MVP_BLUEPRINT_V1.md` §7.6 requires it:

    Every soft warning drawn from that chain must therefore be rendered with its
    `n` and a note that the sample is superseded — or the warning becomes the
    thing it exists to prevent: a confident number the owner acts on.

**Three registers, and they never share a list.** `BLOCK` means the system
refuses to produce a number — it places no orders and cannot stop the owner from
doing anything, and the taxonomy says so rather than implying otherwise.
`WARNING` qualifies a value and gates nothing. `INFORMATION` is neither: *an
absent input is information, never reassurance.*

**No rule reads a direction to decide anything.** `R-CLUSTER` counts how many
actionable setups share one side without ever naming which side that is — the
count is the fact, and this package holds no directional vocabulary of its own.
"""

from __future__ import annotations

from collections.abc import Sequence

from fmis.today.evidence import (
    RISK_REWARD_ASSOCIATION,
    RISK_REWARD_DISTRIBUTION,
    RISK_REWARD_ELEVATED,
    RISK_REWARD_P90,
)
from fmis.today.models import (
    FailedSymbol,
    OpportunityLine,
    PortfolioOverview,
    NotAvailable,
    WarningClass,
    WarningSeverity,
    WorkspaceWarning,
)

__all__ = [
    "CODES",
    "CLUSTER_MINIMUM",
    "INSUFFICIENT_SUFFICIENCY",
    "workspace_warnings",
    "warnings_for_opportunity",
]

#: The sufficiency state that forecloses a directional candidate unconditionally.
#: Read as a string rather than imported from `fmis.decision_context`, because
#: `OpportunityLine` already carries the engine's own `ContextState.value` and
#: re-importing the enum here would give this package a second opinion about a
#: judgement it does not own.
INSUFFICIENT_SUFFICIENCY = "insufficient"

#: How many same-side actionable setups make a concentration observation. Three
#: is not a chosen threshold: it is the count the live run that motivated this
#: rule actually produced — one CONFIRMED and two CANDIDATE setups on the same
#: side across three correlated majors — and the rule exists to make exactly that
#: shape visible. Below three there is no concentration to observe.
CLUSTER_MINIMUM = 3

#: Every code this module can raise. A test asserts the set is exactly what
#: ships, so a new rule is a visible edit here rather than a string appearing in
#: one branch nobody reads.
CODES: tuple[str, ...] = (
    "B-CONTEXT",
    "B-NO-STOP",
    "R-RR-DISTRIBUTION",
    "R-RR-ELEVATED",
    "R-CLUSTER",
    "R-NO-BUDGET",
    "M-NO-STORE",
    "M-NO-POSITIONS",
    "M-FAILED-SYMBOL",
    "I-UNREADABLE",
    "L-NO-FRESHNESS",
    "L-NO-SIZING",
)


def _block(
    code: str,
    kind: WarningClass,
    statement: str,
    evidence: str,
    subjects: tuple[str, ...],
) -> WorkspaceWarning:
    """A refusal to produce a number — never a claim that the setup is bad.

    FMITS places no orders and cannot stop the owner from doing anything. What a
    block means here is exactly and only that this system will not produce a
    size, a plan or a record for that entry, and the page says so.
    """
    return WorkspaceWarning(
        code=code,
        kind=kind,
        severity=WarningSeverity.BLOCK,
        statement=statement,
        evidence=evidence,
        subjects=subjects,
    )


def warnings_for_opportunity(
    opportunity: OpportunityLine,
) -> tuple[WorkspaceWarning, ...]:
    """Every rule that applies to one setup, in a fixed evaluation order.

    The order follows the blueprint's own pre-entry check: sufficiency first,
    because an insufficient analysis forecloses a candidate before any geometry
    is worth looking at; then the stop, because no stop means no risk
    denominator and therefore no size; then the two geometry observations.

    Blocks and warnings are returned in one tuple here and separated by the
    caller, so that the evaluation order stays readable as one sequence rather
    than being split across two functions that must be kept in step.
    """
    if not isinstance(opportunity, OpportunityLine):
        raise TypeError("opportunity must be an OpportunityLine")

    found: list[WorkspaceWarning] = []
    symbol = (opportunity.symbol,)

    if opportunity.sufficiency == INSUFFICIENT_SUFFICIENCY:
        found.append(
            _block(
                "B-CONTEXT",
                WarningClass.INCOMPLETE_ANALYSIS,
                "The decision context is insufficient: this analysis does not "
                "rest on enough trustworthy data to carry a directional "
                "candidate.",
                "ADR-0026; checked before the family tally in swing_setup policy",
                symbol,
            )
        )

    if opportunity.stop is None:
        found.append(
            _block(
                "B-NO-STOP",
                WarningClass.RISK,
                "No stop level was detected, so no risk denominator exists and "
                "no position size can be produced for this setup.",
                "AR-3 — a stop is a real detected level or explicitly absent",
                symbol,
            )
        )

    ratio = opportunity.risk_reward
    if ratio is not None and ratio > RISK_REWARD_P90:
        found.append(
            WorkspaceWarning(
                code="R-RR-DISTRIBUTION",
                kind=WarningClass.RISK,
                severity=WarningSeverity.WARNING,
                statement=(
                    "The displayed risk/reward is above the 90th percentile of "
                    "every risk/reward this policy has been measured producing."
                ),
                evidence=RISK_REWARD_DISTRIBUTION.source,
                subjects=symbol,
                detail=RISK_REWARD_DISTRIBUTION.rendered(),
            )
        )
    if ratio is not None and ratio >= RISK_REWARD_ELEVATED:
        found.append(
            WorkspaceWarning(
                code="R-RR-ELEVATED",
                kind=WarningClass.RISK,
                severity=WarningSeverity.WARNING,
                statement=(
                    "A large displayed risk/reward is not evidence of a better "
                    "trade. In the only measurement this repository has taken, "
                    "it was associated with a worse outcome."
                ),
                evidence=RISK_REWARD_ASSOCIATION.source,
                subjects=symbol,
                detail=RISK_REWARD_ASSOCIATION.rendered(),
            )
        )
    return tuple(found)


def _cluster_warning(
    actionable: Sequence[OpportunityLine],
) -> WorkspaceWarning | None:
    """One observation when several actionable setups share a side.

    Counts by `direction` without ever naming a side. Five individually
    acceptable positions can still be one bet, and no component in this system
    can currently observe that they are correlated — so the count is reported
    and the correlation is not claimed.
    """
    counts: dict[str, list[str]] = {}
    for line in actionable:
        if line.direction is None:
            continue
        counts.setdefault(line.direction, []).append(line.symbol)
    for side, symbols in counts.items():
        if len(symbols) >= CLUSTER_MINIMUM:
            return WorkspaceWarning(
                code="R-CLUSTER",
                kind=WarningClass.CORRELATION,
                severity=WarningSeverity.WARNING,
                statement=(
                    f"{len(symbols)} actionable setups share one side "
                    f"({side}). Taken together they may be one bet rather than "
                    "several, and nothing in this system can currently measure "
                    "whether these markets are correlated."
                ),
                evidence=(
                    "SPEC section 8.2 — individually acceptable positions can "
                    "still create excessive portfolio risk when correlated; "
                    "SWING_TRADING_READINESS_AUDIT_V1.md R-03"
                ),
                subjects=tuple(symbols),
            )
    return None


def workspace_warnings(
    *,
    actionable: Sequence[OpportunityLine],
    failed: Sequence[FailedSymbol],
    unreadable: Sequence[str],
    readable_declined: Sequence[str],
    portfolio: PortfolioOverview,
) -> tuple[WorkspaceWarning, ...]:
    """Every warning this run raises, in a fixed order the renderer preserves.

    Per-setup rules come first and are attributed to their symbol; run-wide
    rules follow. The order is fixed here rather than sorted anywhere, because a
    warning list reordered by severity reads as a warning list ordered by
    importance, and this package invents no importance.
    """
    if not isinstance(portfolio, PortfolioOverview):
        raise TypeError("portfolio must be a PortfolioOverview")

    found: list[WorkspaceWarning] = []
    for line in actionable:
        found.extend(warnings_for_opportunity(line))

    cluster = _cluster_warning(actionable)
    if cluster is not None:
        found.append(cluster)

    if not portfolio.store_present:
        found.append(
            WorkspaceWarning(
                code="M-NO-STORE",
                kind=WarningClass.MISSING_DATA,
                severity=WarningSeverity.WARNING,
                statement=(
                    "There is no durable store at this root, so nothing on this "
                    "page reflects positions, capital, decisions or journal "
                    "entries. Do not read the capital section as a statement "
                    "that you hold nothing."
                ),
                evidence="fmis.persistence — a missing store reads as empty",
                subjects=(portfolio.store_root,),
            )
        )
    elif not portfolio.open_positions:
        found.append(
            WorkspaceWarning(
                code="M-NO-POSITIONS",
                kind=WarningClass.MISSING_DATA,
                severity=WarningSeverity.WARNING,
                statement=(
                    "The store holds no open positions. If you are holding "
                    "anything at an exchange, this page does not know about it "
                    "and no risk figure below accounts for it."
                ),
                evidence="fmis.persistence — a position is a fold over the ledger",
            )
        )

    if isinstance(portfolio.budget_note, NotAvailable):
        found.append(
            WorkspaceWarning(
                code="R-NO-BUDGET",
                kind=WarningClass.RISK,
                severity=WarningSeverity.WARNING,
                statement=(
                    "No risk budget is in force, so no limit can bind and no "
                    "constraint check can refuse anything."
                ),
                evidence="SPEC section 8.2; AP section 15.4 — every limit is the owner's",
            )
        )

    if failed:
        found.append(
            WorkspaceWarning(
                code="M-FAILED-SYMBOL",
                kind=WarningClass.MISSING_DATA,
                severity=WarningSeverity.WARNING,
                statement=(
                    f"{len(failed)} symbol(s) produced no analysis at all. An "
                    "error is not a WAIT: nothing was read, so nothing was "
                    "declined."
                ),
                # Named in prose rather than by module path: the daily
                # workflow's own guard is a raw-text scan of every file outside
                # its permitted set, and this package does not import it. AT hit
                # the identical trap with a docstring reference; the reference
                # is reworded rather than the guard widened, because widening a
                # guard for a mention would weaken it for an import.
                evidence=(
                    "the daily workflow's own distinction: an insufficient "
                    "analysis happened and rests on too little; a failed one "
                    "did not happen"
                ),
                subjects=tuple(entry.symbol for entry in failed),
            )
        )

    if unreadable:
        found.append(
            WorkspaceWarning(
                code="I-UNREADABLE",
                kind=WarningClass.INCOMPLETE_ANALYSIS,
                severity=WarningSeverity.INFORMATION,
                statement=(
                    f"{len(unreadable)} symbol(s) were read but could not be "
                    f"classified, against {len(readable_declined)} the engine "
                    "read and declined. Silence here is not evidence of a quiet "
                    "market."
                ),
                evidence="SWING_TRADING_READINESS_AUDIT_V1.md R-12",
                subjects=tuple(unreadable),
            )
        )

    found.append(
        WorkspaceWarning(
            code="L-NO-FRESHNESS",
            kind=WarningClass.LIMITATION,
            severity=WarningSeverity.INFORMATION,
            statement=(
                "This page shows one analysis instant per symbol, not the age "
                "of each timeframe role. The context role gates whether any "
                "direction may exist and advances once a week, so it can be "
                "many days older than the execution bar beside it."
            ),
            evidence=(
                "TRADER_WORKSPACE_PRODUCT_ARCHITECTURE_V1.md section 2.1 — "
                "measured live at 8d 16h; SetupAssessment carries one as_of"
            ),
        )
    )
    found.append(
        WorkspaceWarning(
            code="L-NO-SIZING",
            kind=WarningClass.LIMITATION,
            severity=WarningSeverity.INFORMATION,
            statement=(
                "No position size, portfolio risk or leverage is computed "
                "anywhere on this page. Sizing continues to be the owner's own "
                "work, performed outside this system and unrecorded by it."
            ),
            evidence="AR-2; SPEC section 8.1 — 2% is a ceiling, not a default target",
        )
    )
    return tuple(found)
