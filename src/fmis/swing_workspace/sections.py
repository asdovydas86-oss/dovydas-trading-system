"""Adapting what already exists into the workspace's nine sections.

**Nothing in this module computes a market quantity, a monetary one or a
statistic.** Every value it produces is read off an object another package
already built: a `SetupAssessment` from `fmis.swing_setup`, a
`SetupEvidenceReport` from `fmis.setup_evidence`, a `SetupOccurrence` identity
from `fmis.setup_observation`, a `TradeMonitor` from `fmis.paper`, an
`ExposureBreakdown` from `fmis.portfolio_risk`, and the six section objects
`fmis.today` already assembles. Where a value would need a computation this
layer is not permitted to perform, the section carries a `NotAvailable` naming
the missing input and the inference its absence forbids — never a zero.

**The three states partition the page, and the mapping is the engine's own.**

    SetupState.CONFIRMED   ──►  TOP OPPORTUNITIES   (actionable now)
    SetupState.CANDIDATE   ──►  WAIT LIST           (a thesis, awaiting its
                                                     confirmation)
    SetupState.WAIT        ──►  NO TRADE            (no directional candidate)
    no assessment at all   ──►  COULD NOT BE READ   (never a market statement)

No new policy decides membership: `SetupState`'s own documentation defines
`CANDIDATE` as *"a directional thesis exists, but the execution-timeframe
confirmation this policy requires has not occurred"*, which is exactly *close but
not ready*, and `WAIT` as *"no directional candidate exists"*, which is exactly
*no trade*. A symbol therefore appears in exactly one section by construction,
and `SwingWorkspace` re-checks it.

**Duck-typed, like `fmis.today.sections` and for the same reason.** An `Absent`
carries a `reason` and a `Money` does not; reaching into a domain package for an
`isinstance` would give this layer a second place that vocabulary lives.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import fmis
from fmis.money import canonical_decimal_text
from fmis.provenance import Absent
from fmis.setup_evidence import (
    SetupEvidenceError,
    SetupIdentityRef,
    project_setup_evidence,
)
from fmis.risk_policy import SPECIFICATION_PER_TRADE_CEILING, plans_for_results
from fmis.setup_observation import observe_setup_series
from fmis.swing_setup import summarise_decision
from fmis.swing_workspace.models import (
    BookExposure,
    EvidenceDigest,
    EvidenceLine,
    FactorLine,
    GlobalSummary,
    NoTradeGroup,
    PaperPosition,
    RankedSetup,
    SwingWorkspaceError,
    SymbolDecision,
    TimeframeLine,
    UnanalysedSymbol,
)
from fmis.swing_workspace.ranking import rank_setups
from fmis.today import (
    MarketOverview,
    NotAvailable,
    OpportunityLine,
    PortfolioOverview,
    WorkspaceWarning,
    WarningClass,
    WarningSeverity,
)
from fmis.trade_capture import CAPTURE_ERRORS, market_from_symbol

__all__ = [
    "ONE_READING_GAP_BARS",
    "BOOK_AXIS",
    "PAPER_LIVE_STATES",
    "evidence_digest_for",
    "identity_ref_for",
    "paper_status_for",
    "holding_for",
    "ranked_setups",
    "no_trade_groups",
    "trade_plans",
    "symbol_decisions",
    "unanalysed_from",
    "paper_positions",
    "books_from",
    "risk_state_of",
    "global_summary",
    "aggregated_warnings",
    "require_actionable_split",
]

#: The occurrence gap tolerance this page groups readings under. **Zero, and the
#: value cannot matter here**: one run observes one bar per symbol, so there is
#: no gap for a tolerance to span. Named rather than inlined so the choice is
#: visible — a surface that one day passes a *series* has to revisit it, and the
#: data model is explicit that no value for this parameter has been validated.
#: `fmis.pipeline.cli` holds the identical constant for the single-symbol
#: commands, for the identical reason; neither can be shared without one of the
#: two importing the other, and a cycle is a worse price than a stated zero.
ONE_READING_GAP_BARS = 0

#: `ExposureDimension.BOOK.value`. Compared as a string rather than imported as
#: an enum member, exactly as `fmis.today.sections` compares `SetupState` values:
#: reaching into `fmis.portfolio_risk` for the vocabulary would give this package
#: a second place the axis is named.
BOOK_AXIS = "book"

#: The folded lifecycle states in which a simulated trade still holds, or may yet
#: hold, exposure. Spelled as strings for the same reason as `BOOK_AXIS`, and
#: kept as a set rather than derived from a terminal-state list because the
#: owner's question is *"is this still running"*, which is what the page shows.
PAPER_LIVE_STATES: frozenset[str] = frozenset(
    {"pending", "triggered", "open", "partially_exited", "ambiguous"}
)

_NO_IDENTITY = NotAvailable(
    reason=(
        "this symbol could not be resolved to a market, so no stable identity "
        "could be built for it"
    ),
    owned_by="fmis.setup_observation (via fmis.trade_capture.market_from_symbol)",
    forbidden_inference=(
        "Do not read this as a new setup. It means this page cannot tell you "
        "whether it is the same idea you saw yesterday."
    ),
)

_NO_OCCURRENCE = NotAvailable(
    reason=(
        "the reading produced no occurrence, so there is no idea to name — a "
        "reading with no directional thesis has no identity to carry"
    ),
    owned_by="fmis.setup_observation",
    forbidden_inference=(
        "Do not read this as a new setup. Nothing was named, in either "
        "direction."
    ),
)

_NO_PAPER_READ = NotAvailable(
    reason="the store was not read, so no simulated trade could be matched",
    owned_by="fmis.paper",
    forbidden_inference=(
        "that this setup is not already running as a paper trade. This page did "
        "not look."
    ),
)

#: What a row says when the paper book holds nothing on this market. It names
#: the book, because *"none"* alone beside a real open position answers *"am I
#: already in this?"* with the wrong half of the truth — the hostile case that
#: produced `held` below.
_NO_PAPER_TRADE = "none in the paper book"

_NO_HOLDING = "none recorded, in any book"

_NO_STORE_READ = NotAvailable(
    reason="the store was not read, so no recorded position could be matched",
    owned_by="the durable store (drop --no-records)",
    forbidden_inference=(
        "that you hold nothing in this market. This page did not look."
    ),
)


# ---------------------------------------------------------------------------
# 1. Per-setup attachments: evidence, identity, paper status
# ---------------------------------------------------------------------------


def identity_ref_for(assessment: Any) -> tuple[Any, str | NotAvailable]:
    """The stable identity of one reading: the reference, and the text to print.

    **Reuses the identity `fmits setup` and `fmits evidence` already print**,
    through the same `observe_setup_series` call, so no two surfaces in this
    repository can disagree about what a setup is called. This package derives no
    identity — `fmis.proposal.setup_identity` owns that rule.

    Returns `(None, NotAvailable)` for a symbol that cannot be resolved to a
    market, and for a reading that produced no occurrence. Both are ordinary
    outcomes rather than failures: `market_from_symbol` refuses to guess where
    `BTCUSDT` divides into base and quote, and a reading with no directional
    thesis names no idea.
    """
    try:
        market = market_from_symbol(assessment.symbol)
    except (*CAPTURE_ERRORS, TypeError, ValueError):
        return None, _NO_IDENTITY
    run = observe_setup_series(
        [assessment],
        market=market,
        code_version=fmis.__version__,
        occurrence_gap_bars=ONE_READING_GAP_BARS,
    )
    if not run.occurrences:
        return None, _NO_OCCURRENCE
    identity = run.occurrences[-1].identity
    return SetupIdentityRef(setup_id=identity), identity


def evidence_digest_for(
    assessment: Any, *, identity: Any = None
) -> EvidenceDigest | NotAvailable:
    """One assessment's evidence report, reduced to counts and two flags.

    **The projection is called, never re-implemented.** Every count is `len()` of
    a group `fmis.setup_evidence` produced, and both booleans are its own.

    A projection that refuses is isolated to this one row. `SetupEvidenceError`
    is the error that package raises for a report it declines to build, and
    catching it here keeps one symbol's unprojectable evidence from removing the
    evidence of every other symbol on the page. Anything else — a `TypeError`, an
    `AttributeError`, a defect in this file — still propagates, because a surface
    that swallows those renders a clean page over broken code.
    """
    try:
        report = project_setup_evidence(assessment, setup_identity=identity)
    except SetupEvidenceError as failure:
        return NotAvailable(
            reason=f"the evidence projection refused this setup: {failure}",
            owned_by="fmis.setup_evidence (fmits evidence SYMBOL)",
            forbidden_inference=(
                "Do not read this as a setup with no evidence behind it. The "
                "evidence exists and could not be summarised."
            ),
        )
    confluence = report.confluence
    return EvidenceDigest(
        supporting=len(report.supporting),
        conflicting=len(report.conflicting),
        missing=len(report.missing),
        unavailable=len(report.unavailable),
        agreeing_families=tuple(
            family.value for family in confluence.agreeing_families
        ),
        conflicting_families=tuple(
            family.value for family in confluence.conflicting_families
        ),
        independence_established=confluence.independence_established,
        decision_ready=report.decision_ready,
        decision_ready_reason=report.decision_ready_reason,
        caveats=(
            () if confluence.independence_established else tuple(confluence.caveats)
        ),
    )


def paper_status_for(
    symbol: str, positions: Sequence[PaperPosition], *, read: bool
) -> str | NotAvailable:
    """Whether a simulated trade is already running on this market.

    A **lookup**, not a computation: the states were folded by `fmis.paper` and
    are compared here by market. It answers the question a page that shows a
    setup and a paper book separately cannot — *am I already in this?* — and
    prevents the owner opening a second position in a market the simulator is
    already running.

    ``read=False`` produces a stated absence rather than `"none"`. *"There is no
    paper trade"* and *"this page did not look"* are different facts, and only
    the first is a statement about what the owner has open.
    """
    if not read:
        return _NO_PAPER_READ
    live = tuple(
        position
        for position in positions
        if position.market == symbol and position.state in PAPER_LIVE_STATES
    )
    if not live:
        return _NO_PAPER_TRADE
    return " · ".join(
        f"{position.state} ({position.activation_id})" for position in live
    )


def holding_for(
    symbol: str, positions: Sequence[Any], *, read: bool
) -> str | NotAvailable:
    """Whether the owner already holds this market, in any book.

    A **lookup** over the position lines this page is already showing — folded by
    `fmis.positions`, formatted by `fmis.today`, and neither recomputed nor
    re-summed here. It exists because a row that reports only its *simulated*
    exposure reads as a complete answer to *"am I already in this?"*, and the
    owner's real position is the half that costs money.

    Books are named individually rather than totalled: `AP` §5.5 makes the book
    the economic classification, and adding a simulated position to a real one
    would put play money into a statement about the owner's capital.
    """
    if not read:
        return _NO_STORE_READ
    held = tuple(
        position for position in positions if position.market == symbol
    )
    if not held:
        return _NO_HOLDING
    return " · ".join(
        f"{position.book}: {position.quantity} @ {position.average_entry}"
        for position in held
    )


def ranked_setups(
    lines: Sequence[OpportunityLine],
    *,
    watchlist: Sequence[str],
    assessments: Mapping[str, Any],
    paper: Sequence[PaperPosition],
    positions: Sequence[Any] = (),
    store_read: bool,
) -> tuple[RankedSetup, ...]:
    """Order one group of actionable lines and attach what hangs off each row.

    ``assessments`` maps a symbol to the `SetupAssessment` the scan produced for
    it, which is what the evidence projection and the identity both need. A line
    whose assessment is not supplied still ranks — the ordering reads only the
    line — and its two attachments become stated absences rather than the row
    disappearing.

    ``position`` is stamped here, from the row's index after ordering, so the
    number on the page and the order of the tuple cannot disagree.
    """
    ordered = rank_setups(lines, watchlist=watchlist)
    rows: list[RankedSetup] = []
    for index, (line, key) in enumerate(ordered):
        assessment = assessments.get(line.symbol)
        if assessment is None:
            identity: str | NotAvailable = NotAvailable(
                reason=(
                    "no assessment was supplied for this row, so neither its "
                    "identity nor its evidence could be projected"
                ),
                owned_by="the composition root",
                forbidden_inference=(
                    "Do not read this as a setup with nothing behind it."
                ),
            )
            evidence: EvidenceDigest | NotAvailable = identity
        else:
            reference, identity = identity_ref_for(assessment)
            evidence = evidence_digest_for(assessment, identity=reference)
        rows.append(
            RankedSetup(
                opportunity=line,
                key=key,
                position=index + 1,
                evidence=evidence,
                identity=identity,
                paper_status=paper_status_for(line.symbol, paper, read=store_read),
                held=holding_for(line.symbol, positions, read=store_read),
            )
        )
    return tuple(rows)


# ---------------------------------------------------------------------------
# 2. NO TRADE and the symbols that produced no analysis
# ---------------------------------------------------------------------------

#: The two ways a `WAIT` arises, in the words the page prints. The split is
#: `fmis.today.MarketOverview`'s own — a symbol whose decision context was
#: insufficient was never classified; one whose context was sufficient or limited
#: was read and declined — and shown as one number a quiet system and a quiet
#: market are indistinguishable.
_READ_AND_DECLINED = "read and declined"
_NOT_CLASSIFIABLE = "could not be classified"

#: `ContextState.INSUFFICIENT.value`, spelled as a string for the reason
#: `BOOK_AXIS` gives.
_INSUFFICIENT = "insufficient"

#: `SetupState.WAIT.value`, likewise.
_WAIT = "wait"

#: What a row says when the engine stated no thesis at all. Named once because
#: the grouped section and the per-symbol section must reach the same string:
#: two literals is how one page starts calling a symbol something the other does
#: not.
_NO_REASON_STATED = "no reason stated"


def no_trade_groups(results: Sequence[Any]) -> tuple[NoTradeGroup, ...]:
    """Every `WAIT` result, grouped on the engine's own verbatim reason.

    Groups are ordered by how many symbols reached each reason, largest first —
    a distribution over already-stated reasons, not a ranking of opportunities,
    and the identical rule `fmis.today.sections` applies to the same population.
    Ties keep scan order, because `sorted` is stable.

    A group is keyed on `(reason, classification)` rather than on the reason
    alone: two symbols can reach one sentence from a sufficient and from an
    insufficient context, and merging them would report a system failure as a
    market observation.
    """
    groups: dict[tuple[str, str], list[str]] = {}
    for result in results:
        assessment = result.assessment
        if assessment is None or assessment.state.value != _WAIT:
            continue
        groups.setdefault(
            (_reason_of(assessment), _classification_of(assessment)), []
        ).append(result.requested_symbol)
    ordered = sorted(groups.items(), key=lambda item: len(item[1]), reverse=True)
    return tuple(
        NoTradeGroup(reason=reason, classification=classification, symbols=tuple(symbols))
        for (reason, classification), symbols in ordered
    )


def _classification_of(assessment: Any) -> str:
    """`no_trade_groups`' own split, extracted so the two cannot disagree.

    Called by both, so a symbol classified *could not be classified* in the
    grouped section is classified identically on its own row. Two copies of one
    two-branch rule is how the grouped page and the per-symbol page start
    describing the same symbol differently.
    """
    return (
        _NOT_CLASSIFIABLE
        if assessment.sufficiency.value == _INSUFFICIENT
        else _READ_AND_DECLINED
    )


def _reason_of(assessment: Any) -> str:
    """The engine's own first thesis line — the string `no_trade_groups` keys on."""
    return assessment.thesis[0] if assessment.thesis else _NO_REASON_STATED


def _evidence_lines(items: Sequence[Any]) -> tuple[EvidenceLine, ...]:
    """One group of the evidence report, item for item. **Nothing is summarised.**

    Every field is copied off an `EvidenceItem` `fmis.setup_evidence` already
    built — including ``correlated_with`` and ``independence_note``, which are
    the two that make the difference between showing evidence and claiming
    corroboration.
    """
    return tuple(
        EvidenceLine(
            key=item.key,
            status=item.status.value,
            statement=item.statement,
            observed=item.observed,
            source=item.source,
            families=tuple(family.value for family in item.families),
            scope=item.scope,
            as_of=item.as_of,
            correlated_with=tuple(item.correlated_with),
            independence_note=item.independence_note,
        )
        for item in items
    )


def _trend_value(trend: Any) -> str | None:
    """A structural trend's own enum value, or `None`. Read at runtime.

    This package names no trend member and no producing module: the vocabulary
    belongs to the engine that computed it, and spelling either here would give
    it a second home — which a repository guard forbids by scanning for the
    module's name as text.
    """
    return None if trend is None else trend.value


def _timeframe_lines(readings: Any, reference: Any) -> tuple[TimeframeLine, ...]:
    """The per-role reading instants, with the age each one has on this page.

    **The age is asked for, never computed.** `TimeframeReading.age_at` owns the
    subtraction, beside the instant it measures; this package holds no
    arithmetic operator at all and a guard asserts it. ``reference`` is the
    page's own instant, so every age on one page is measured against one clock.

    A `None` reference yields instants with no age rather than no instants: the
    time a market was last read is a fact whether or not anything has been
    measured against it.
    """
    if readings is None:
        return ()
    return tuple(
        TimeframeLine(
            role=reading.role,
            interval=reading.interval,
            as_of=reading.as_of,
            closed_count=reading.closed_count,
            age=None if reference is None else reading.age_at(reference),
            structural_trend=_trend_value(
                readings.structural_trend_for(reading.role)
            ),
        )
        for reading in readings.timeframes
    )


def trade_plans(
    results: Sequence[Any], *, declaration: Any | None
) -> tuple[Mapping[str, Any] | None, str | NotAvailable]:
    """A trade plan per scanned symbol, or the stated reason there are none.

    **The whole population, not the actionable part of it.** Every symbol that
    produced an assessment gets a plan, and for the great majority — everything
    the engine gave no direction — that plan says *there is no trade to plan*
    in its own words. A mapping that held only the candidates would leave a
    `WAIT` symbol's planning section blank, and a blank where a plan belongs
    reads as a plan nobody produced rather than as a symbol with no trade in it.

    Returns the mapping and the note that explains it. `None` and a
    `NotAvailable` when no policy is declared: *"the owner has declared no risk
    policy"* is a true, actionable and extremely common state, and it is stated
    rather than rendered as an empty section.

    **This function computes nothing.** `fmis.risk_policy.plans_for_results`
    owns the arithmetic, and it reaches `fmis.position_sizing` for every
    quotient. Nothing here multiplies, divides or compares an amount of money.
    """
    if declaration is None:
        return None, NotAvailable(
            reason=(
                "no risk policy is declared, so no trade-planning figure can be "
                "produced for any symbol. Nothing is assumed in its place — not "
                "a capital figure, and above all not a risk fraction. Declare "
                "one in ~/.fmits/risk_policy.json: the capital you plan against, "
                "and the fraction of it you risk per trade (at most "
                f"{canonical_decimal_text(SPECIFICATION_PER_TRADE_CEILING)}, "
                "which is a ceiling and not a target)"
            ),
            owned_by=(
                "the owner — write ~/.fmits/risk_policy.json with the capital "
                "you plan against and the fraction of it you risk per trade"
            ),
            forbidden_inference=(
                "Do not read a symbol with no planning figures as one that "
                "carries no risk, and do not read the absence of a size as a "
                "size of nothing."
            ),
        )
    plans = plans_for_results(results, declaration=declaration)
    fraction = declaration.fraction_text
    stated = (
        f"risking {fraction} of it per trade"
        if isinstance(fraction, str)
        else "with no per-trade risk fraction declared, so no size is produced"
    )
    return plans, (
        f"{len(plans)} symbol(s) planned against declared capital "
        f"{declaration.equity.text} {declaration.equity.asset}, {stated}. The "
        f"hard ceiling is "
        f"{canonical_decimal_text(declaration.ceiling)} of equity per trade and "
        "is not a target. Every figure is for one trade in isolation: no "
        "portfolio, position, exposure or correlation is read, so total open "
        "risk is not evaluated — which is not the same as its being zero."
    )


def symbol_decisions(
    results: Sequence[Any],
    *,
    reference_time: Any = None,
    plans: Mapping[str, Any] | None = None,
) -> tuple[SymbolDecision, ...]:
    """**One decision record per scanned symbol, in scan order.**

    The seam this milestone exists to close. `ranked_setups` attaches an evidence
    digest to *actionable* rows only, and `no_trade_groups` folds every `WAIT`
    into a group keyed on one shared sentence — so for a `WAIT` symbol the
    directional factors the policy tallied, the regime lines it read, and the
    entire evidence report `project_setup_evidence` is perfectly able to produce
    were computed on every run and then discarded at this layer.

    This calls the identical projection `evidence_digest_for` calls, on the
    identical assessment, and carries the report's items instead of counting
    them. No assessment is re-evaluated and no market value is read: given the
    same results this returns an equal tuple, with no clock and no network.

    **Order is scan order and nothing else.** Results are read in the sequence
    they arrive, which is the sequence the owner requested the symbols in. This
    function does not sort, does not group and does not partition — ordering
    these rows by any property of the analysis would be the opportunity ranking
    no measurement in this repository supports.

    A result that produced no assessment yields no record: a symbol that could
    not be read has no decision, and the `unanalysed` section is where it is
    stated. A projection that refuses is isolated to its own row, exactly as it
    is in `evidence_digest_for` and for the same reason.

    ``plans`` maps a symbol to its `fmis.risk_policy.TradeRiskPlan`. A parameter
    rather than a derivation, and the direction of the arrow is the point: a plan
    is computed **from** a decision and is attached to it here, at the projection
    seam. Nothing in this function reads a plan to decide anything about a
    record, and `None` — no risk policy declared — changes no other field.

    ``reference_time`` is the page's own instant, used only to ask each
    `TimeframeReading` how old it is. It is never compared to a threshold: this
    milestone carries per-role instants and ages and deliberately publishes no
    freshness verdict, because no validated staleness bound exists for any role.

    **No `setup_identity` is derived here, deliberately.** `ranked_setups` passes
    one because its rows *print* it; the projection only stores the reference on
    the report and reads it nowhere, this record carries no identity field, and
    for a `WAIT` assessment `identity_ref_for` has nothing to return anyway — a
    reading with no directional thesis names no idea. Deriving one per scanned
    symbol would be an `observe_setup_series` call per row whose result is
    discarded.

    **A record is keyed on the assessment's symbol, not the requested one.**
    `no_trade_groups` lists `requested_symbol`, because a group is a record of
    what was *asked*; a decision is a record of what was *concluded*, and the
    detail route resolves it against the same name the actionable rows and their
    links already carry (`OpportunityLine.symbol`, which is the assessment's).
    Keying it on the request would give one symbol two names across two sections
    of one page.

    **A symbol requested twice produces one record, not two.** `fmits workspace
    BTCUSDT BTCUSDT` asks about one market twice and the scan answers twice;
    the actionable sections carry both answers, because two identical rows are
    the honest rendering of what was requested. This section cannot, and the
    difference is not an inconsistency: a decision record is what the detail
    surface looks up *by name*, and two records for one symbol would mean the
    page silently shows whichever came first. The first is kept, so the record
    and the first row of the actionable section describe the same reading.
    """
    decisions: list[SymbolDecision] = []
    seen: set[str] = set()
    for result in results:
        assessment = result.assessment
        if assessment is None or assessment.symbol in seen:
            continue
        seen.add(assessment.symbol)
        readings = getattr(result, "readings", None)
        summary = summarise_decision(assessment, readings)
        common: dict[str, Any] = dict(
            symbol=assessment.symbol,
            # Looked up by the assessment's own symbol, the same key this record
            # is filed under, so a decision and its plan can never describe two
            # different markets. `None` when no policy was declared.
            plan=None if plans is None else plans.get(assessment.symbol),
            developing=summary.developing,
            blocker=summary.blocker,
            # Read off the result the same way `readings` is, and carried
            # through untouched. `getattr` rather than attribute access for the
            # reason `readings` uses it: a hand-built result from before the
            # field existed is still a valid result, and its decision states the
            # absence rather than failing to assemble.
            technical=getattr(result, "technical", None),
            timeframes=_timeframe_lines(readings, reference_time),
            state=assessment.state.value,
            classification=_classification_of(assessment),
            reason=_reason_of(assessment),
            sufficiency=assessment.sufficiency.value,
            as_of=assessment.as_of,
            direction=(
                None if assessment.direction is None else assessment.direction.value
            ),
            thesis=tuple(assessment.thesis),
            regime_context=tuple(assessment.regime_context),
            confirmation=tuple(assessment.confirmation),
            invalidation=tuple(assessment.invalidation),
            factors=tuple(
                FactorLine(
                    family=factor.family,
                    lean=factor.lean.value,
                    observed=factor.observed,
                    source=factor.source,
                )
                for factor in assessment.directional_factors
            ),
        )
        try:
            report = project_setup_evidence(assessment)
        except SetupEvidenceError as failure:
            decisions.append(
                SymbolDecision(
                    evidence_reason=(
                        f"the evidence projection refused this setup: {failure}"
                    ),
                    **common,
                )
            )
            continue
        confluence = report.confluence
        decisions.append(
            SymbolDecision(
                supporting=_evidence_lines(report.supporting),
                conflicting=_evidence_lines(report.conflicting),
                missing=_evidence_lines(report.missing),
                unavailable=_evidence_lines(report.unavailable),
                agreeing_families=tuple(
                    family.value for family in confluence.agreeing_families
                ),
                conflicting_families=tuple(
                    family.value for family in confluence.conflicting_families
                ),
                independence_established=confluence.independence_established,
                independence_caveats=(
                    ()
                    if confluence.independence_established
                    else tuple(confluence.caveats)
                ),
                evidence_warnings=tuple(report.warnings),
                open_questions=tuple(report.open_questions),
                decision_ready=report.decision_ready,
                decision_ready_reason=report.decision_ready_reason,
                **common,
            )
        )
    return tuple(decisions)


def unanalysed_from(failed: Sequence[Any]) -> tuple[UnanalysedSymbol, ...]:
    """`fmis.today`'s failed symbols, in its own order, under this page's type.

    Re-typed rather than re-derived: the failure text, the isolation and the
    empty-message fallback are all `fmis.today.sections`' work, and this converts
    the result so that a no-trade group and an outage can never be held in one
    tuple by mistake.
    """
    return tuple(
        UnanalysedSymbol(symbol=entry.symbol, detail=entry.detail) for entry in failed
    )


# ---------------------------------------------------------------------------
# 3. The paper book
# ---------------------------------------------------------------------------


def _decimal_or_absence(value: Any, *, subject: str) -> str | NotAvailable:
    """One exact figure in the domain's canonical spelling, or its stated reason."""
    if isinstance(value, Absent):
        return NotAvailable(
            reason=value.reason,
            owned_by="fmis.paper",
            forbidden_inference=(
                f"that {subject} is zero, or that this trade never moved that "
                "way. It is a figure the simulator could not state"
            ),
        )
    return canonical_decimal_text(value)


def _money_or_absence(value: Any, *, subject: str) -> str | NotAvailable:
    if isinstance(value, Absent):
        return NotAvailable(
            reason=value.reason,
            owned_by="fmis.paper",
            forbidden_inference=f"that {subject} is zero",
        )
    return f"{value.text} {value.asset}"


def _paper_position(view: Any) -> PaperPosition:
    """One `PaperTradeView`, reduced to the seven figures this page shows.

    Every one of them is already on the `TradeMonitor` the paper package's own
    read path produced. This function selects and formats; it divides nothing and
    compares nothing.
    """
    monitor = view.monitor
    return PaperPosition(
        activation_id=view.activation_id,
        market=view.activation.market.pair_symbol,
        state=view.state.value,
        open_size=str(monitor.remaining),
        bars_in_trade=monitor.bars_in_trade,
        stop_widenings=monitor.stop_widenings,
        entry=_decimal_or_absence(monitor.entry_price, subject="the entry"),
        initial_risk=_money_or_absence(monitor.initial_risk, subject="the risk"),
        total_r=_decimal_or_absence(monitor.total_r, subject="the R multiple"),
        max_favourable_r=_decimal_or_absence(
            monitor.max_favourable_r, subject="the favourable excursion"
        ),
        max_adverse_r=_decimal_or_absence(
            monitor.max_adverse_r, subject="the adverse excursion"
        ),
        stop=canonical_decimal_text(monitor.effective_stop),
        initial_stop=canonical_decimal_text(monitor.initial_stop),
    )


def paper_positions(
    views: Sequence[Any], *, read: bool
) -> tuple[tuple[PaperPosition, ...], str | NotAvailable]:
    """Every simulated trade the store holds, and the note that qualifies them.

    Order is the store's own — the order `fmis.paper`'s read path returned the
    activations in. Nothing here sorts by result, by R multiple or by age: a
    paper book ordered by outcome is a leaderboard, and the one lesson a paper
    book exists to teach is what happened to *all* of them.
    """
    if not read:
        return (), NotAvailable(
            reason=(
                "the store was not read, so whether any paper trade is running "
                "is unknown"
            ),
            owned_by="fmis.paper",
            forbidden_inference="that no paper trade is running. This page did not look",
        )
    positions = tuple(_paper_position(view) for view in views)
    return positions, (
        "every activation this store holds was folded from its own event "
        "stream; no state is stored. This page reads no simulation candle, so "
        "an excursion on an unfinished trade is absent here rather than zero — "
        "`fmits trade status` fetches the bars that would state one"
    )


# ---------------------------------------------------------------------------
# 4. Capital: books, risk state, exposure
# ---------------------------------------------------------------------------


def books_from(
    portfolio: PortfolioOverview, valuation: Any | None
) -> tuple[BookExposure, ...]:
    """One row per book the owner holds something in. **No total is computed.**

    When a valuation exists, the figure comes from `fmis.portfolio_risk`'s own
    `BOOK` breakdown — one of the eight axes `build_state` already folds — so the
    number on this page is the number that engine produced and not a second sum
    over the same positions.

    When none exists, the count of positions per book is still a fact and is
    shown; the money is a stated absence. Counting positions is not arithmetic on
    money, and a page that hid the count because it could not price it would hide
    that the owner is exposed at all.
    """
    if not isinstance(portfolio, PortfolioOverview):
        raise TypeError(
            f"portfolio must be a PortfolioOverview, got {type(portfolio).__name__}"
        )
    counts: dict[str, int] = {}
    for position in portfolio.open_positions:
        counts[position.book] = counts.get(position.book, 0) + 1

    priced: dict[str, Any] = {}
    if valuation is not None:
        for breakdown in getattr(valuation.state, "breakdowns", ()):
            if breakdown.dimension.value != BOOK_AXIS:
                continue
            for entry in breakdown.entries:
                priced[entry.key] = entry.gross

    unpriced = NotAvailable(
        reason="no price source was consulted for this page",
        owned_by="the valuation layer",
        forbidden_inference="Do not read an unvalued book as an empty one.",
    )
    return tuple(
        BookExposure(
            label=book,
            open_positions=count,
            market_value=(
                unpriced
                if book not in priced
                else _money_or_absence(priced[book], subject="this book's exposure")
            ),
        )
        for book, count in counts.items()
    )


def risk_state_of(portfolio: PortfolioOverview) -> str | NotAvailable:
    """What limits are recorded, and how many were actually measured.

    **Never a traffic light.** No layer in this repository measures a limit yet —
    `fmis.today` renders every one of them as indeterminate with its reason — so a
    green/amber/red headline would be an invention, and an invented one at the top
    of the page is the most expensive place to put it. This states the two counts
    and the budget they came from, which is the whole of what is known.
    """
    if isinstance(portfolio.budget_note, NotAvailable):
        return portfolio.budget_note
    measured = sum(
        1 for limit in portfolio.limits if not isinstance(limit.status, NotAvailable)
    )
    return (
        f"{portfolio.budget_note} · {len(portfolio.limits)} limit(s) recorded · "
        f"{measured} measured against this page"
    )


def global_summary(
    *,
    market: MarketOverview,
    confirmed: int,
    candidates: int,
    waiting: int,
    unanalysed: int,
    portfolio: PortfolioOverview,
    paper: Sequence[PaperPosition],
    store_read: bool,
) -> GlobalSummary:
    """The header block: eight counts and two already-produced values.

    Every count is of something a section below states in full, so the header
    removes work from the page rather than adding a claim to it. Nothing here is
    a judgement, and there is no field one could be written into.
    """
    if not isinstance(market, MarketOverview):
        raise TypeError(f"market must be a MarketOverview, got {type(market).__name__}")
    live = tuple(
        position for position in paper if position.state in PAPER_LIVE_STATES
    )
    return GlobalSummary(
        scanned=market.scanned,
        confirmed=confirmed,
        candidates=candidates,
        waiting=waiting,
        unanalysed=unanalysed,
        open_positions=portfolio.open_count,
        paper_positions=len(live),
        breadth=market.breadth,
        regime_note=market.regime_note,
        risk_state=risk_state_of(portfolio),
        open_exposure=(
            portfolio.exposure
            if store_read
            else NotAvailable(
                reason="the store was not read, so no exposure could be stated",
                owned_by="the durable store (drop --no-records)",
                forbidden_inference=(
                    "Do not read an unstated exposure as no exposure."
                ),
            )
        ),
        analysis_as_of=market.analysis_as_of,
    )


# ---------------------------------------------------------------------------
# 5. Warnings
# ---------------------------------------------------------------------------

#: What a paper-book warning is classified as on this page. `fmis.paper` states
#: its warnings without a class or a severity, and both are required here; a
#: halted trade and a widened stop are facts about a position the owner holds,
#: which is what `RISK` means in `fmis.today`'s own vocabulary.
_PAPER_WARNING_CLASS = WarningClass.RISK
_PAPER_WARNING_SEVERITY = WarningSeverity.WARNING
_PAPER_WARNING_SOURCE = "fmis.paper — the simulator's own warning, verbatim"


def aggregated_warnings(
    warnings: Sequence[WorkspaceWarning], views: Sequence[Any]
) -> tuple[WorkspaceWarning, ...]:
    """Every warning this run raised, in one list, each appearing once.

    **No warning is invented here.** The first group is `fmis.today`'s own,
    unchanged and in its own order; the second is `fmis.paper`'s per-trade
    warnings, which the day's page never surfaced — a halted simulated trade is
    waiting for the *owner* rather than for the market, and a page that only
    showed it inside the paper section let it scroll off.

    **Deduplicated on `(code, subjects)`.** Two activations halted for the same
    reason are two subjects of one warning, not two warnings; a page that printed
    the same sentence four times teaches the reader to skip the section. The
    first occurrence keeps its position and later subjects join it, so order is
    the order each rule first fired.
    """
    ordered: list[WorkspaceWarning] = []
    seen: dict[str, int] = {}

    def _admit(warning: WorkspaceWarning) -> None:
        index = seen.get(warning.code)
        if index is None:
            seen[warning.code] = len(ordered)
            ordered.append(warning)
            return
        existing = ordered[index]
        merged = existing.subjects + tuple(
            subject for subject in warning.subjects if subject not in existing.subjects
        )
        if merged == existing.subjects:
            return
        ordered[index] = WorkspaceWarning(
            code=existing.code,
            kind=existing.kind,
            severity=existing.severity,
            statement=existing.statement,
            evidence=existing.evidence,
            subjects=merged,
            detail=existing.detail,
        )

    for warning in warnings:
        if not isinstance(warning, WorkspaceWarning):
            raise TypeError("every warning must be a WorkspaceWarning")
        _admit(warning)
    for view in views:
        market = view.activation.market.pair_symbol
        for raised in view.warnings:
            _admit(
                WorkspaceWarning(
                    code=raised.code,
                    kind=_PAPER_WARNING_CLASS,
                    severity=_PAPER_WARNING_SEVERITY,
                    statement=raised.text,
                    evidence=_PAPER_WARNING_SOURCE,
                    subjects=(f"{market} · {view.activation_id}",),
                )
            )
    return tuple(ordered)


def require_actionable_split(
    confirmed: Sequence[OpportunityLine], candidates: Sequence[OpportunityLine]
) -> None:
    """Refuse a split in which one symbol reached both actionable states.

    `fmis.today` builds the two groups from one pass over the scan, so this
    cannot happen from that source — which is exactly why it is checked here
    rather than assumed: this function is what a *second* source of lines would
    have to satisfy, and the failure it prevents is a setup the owner sizes twice.
    """
    left = {line.symbol for line in confirmed}
    shared = sorted(left & {line.symbol for line in candidates})
    if shared:
        raise SwingWorkspaceError(
            f"{shared} reached both actionable states in one scan; a symbol has "
            "one state, and a page showing it twice invites the owner to act on "
            "it twice"
        )
