"""The section providers, and the registry that orders them.

Each provider turns already-computed facts into one `Section`, or returns an
`Unavailable` naming the milestone that will build it. **No provider computes a
market quantity** — every number here was produced by an engine and is copied.

A future milestone fills a slot by replacing one entry in `SECTION_PROVIDERS`.
That is the whole extension mechanism, and it is the same registry idiom AG used
for CLI commands and AI used for evidence ordering.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable

from fmis.decision_context import ContextState, DecisionContext, Severity
from fmis.decision_support import Alignment, EvidenceReport, Observation
from fmis.evidence import EvidenceFamily, descriptors_for, find
from fmis.market_regime import (
    MarketRegime,
    RegimeDimensionName,
)
from fmis.pipeline.multi_timeframe import MultiTimeframeFactSheet, TimeframeRole
from fmis.pipeline.structural_facts import Limitation
from fmis.workspace.conflicts import Conflict
from fmis.workspace.models import (
    NoteBlock,
    Provenance,
    Row,
    RowBlock,
    Section,
    SectionId,
    SectionStatus,
    TableBlock,
    Tier,
    Unavailable,
    WorkspaceSection,
)

__all__ = [
    "WorkspaceInputs",
    "SectionProvider",
    "SECTION_PROVIDERS",
    "build_sections",
]

_ABSENT = "—"


def _number(value: object, places: int = 2) -> str:
    """Format a number for display, or the absence marker when there is none.

    Absence renders as an em dash rather than ``0`` or a blank: a zero is a
    measurement and a blank is ambiguous, while the dash says "not there" and
    cannot be mistaken for either.
    """
    if value is None:
        return _ABSENT
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _ABSENT
    return f"{value:,.{places}f}"


@dataclass(frozen=True, slots=True)
class WorkspaceInputs:
    """Everything the providers may read. Facts only — nothing to be computed.

    Assembled by the builder from the existing composition roots, so a provider
    cannot reach a provider's engine, a candle, or the network. Passing one
    frozen bundle rather than a growing argument list is what lets a future
    provider read a field it did not ask for without changing every signature.
    """

    symbol: str
    objective: str
    source: str
    sheet: MultiTimeframeFactSheet
    regimes: Mapping[TimeframeRole, MarketRegime]
    primary_role: TimeframeRole
    conflicts: tuple[Conflict, ...]
    evidence: EvidenceReport | None
    context: DecisionContext | None
    limitations: tuple[Limitation, ...]

    @property
    def primary_view(self):
        """The view carrying the objective's primary timeframe."""
        return self.sheet.by_role[self.primary_role]

    @property
    def primary_regime(self) -> MarketRegime:
        return self.regimes[self.primary_role]

    @property
    def primary_label(self) -> str:
        view = self.primary_view
        return f"{view.role.value} · {view.interval}"


#: A provider reads the bundle and returns one section. Registered, not called
#: directly, so the page's composition is data rather than control flow.
SectionProvider = Callable[[WorkspaceInputs], WorkspaceSection]


# ───────────────────────────── §1 instrument ──────────────────────────────


def instrument_section(inputs: WorkspaceInputs) -> WorkspaceSection:
    """Identity, freshness, window and warm-up — the section that gates the rest.

    First on the page because every reasoning failure recorded in
    `docs/analysis-notes.md` happened on top of data the reader assumed was
    sound. A short window or a warming-up indicator invalidates what follows, and
    both are cheap to state.
    """
    sheet = inputs.sheet
    rows = [
        Row("Asset", sheet.symbol, sheet.source),
        Row("Objective", inputs.objective, inputs.primary_label + " primary"),
        Row("Timeframes", " · ".join(sheet.intervals), f"{len(sheet.views)} views"),
        Row(
            "Newest closed candle",
            sheet.newest_as_of.isoformat(),
            "not a shared instant",
        ),
    ]

    records = []
    warming: list[str] = []
    for view in sheet.views:
        window = view.sheet.window
        records.append(
            (
                f"{view.role.value} · {view.interval}",
                view.sheet.as_of.isoformat(),
                f"{window.closed_count}/{window.fetched_count}",
                str(window.excluded_forming_count),
                str(len(view.sheet.warming_up)),
            )
        )
        for name in view.sheet.warming_up:
            warming.append(f"{view.interval}:{name}")

    body: list = [
        RowBlock(tuple(rows)),
        TableBlock(
            columns=("role · timeframe", "as of", "closed/fetched", "forming", "warm-up"),
            records=tuple(records),
            heading="PER VIEW",
        ),
    ]
    if warming:
        body.append(
            NoteBlock(
                (
                    "Warming up: " + ", ".join(sorted(warming)),
                    "A warming-up feature is absent, not zero and not neutral.",
                )
            )
        )

    return Section(
        id=SectionId.INSTRUMENT,
        title="INSTRUMENT & DATA QUALITY",
        status=SectionStatus.AVAILABLE if not warming else SectionStatus.PARTIAL,
        summary=(
            f"{sheet.symbol} · {len(sheet.views)} views · newest "
            f"{sheet.newest_as_of.isoformat()}",
        ),
        body=tuple(body),
        caveats=(
            "Views are fetched at different instants and are not aligned in time.",
        ),
        provenance=Provenance(
            engine="fmis.pipeline.multi_timeframe", as_of=sheet.newest_as_of
        ),
    )


# ────────────────────────────── §2 regime ─────────────────────────────────


def regime_section(inputs: WorkspaceInputs) -> WorkspaceSection:
    """The environment, per role, with the primary role's evidence in full.

    Second on the page for two independent reasons that agree: `SPEC` §5 puts the
    higher timeframe's regime before the setup, and the v3 prompt's first
    recorded correction was "regime classification first".

    Every role's states are tabulated so no timeframe is privileged, and only the
    **primary** role's evidence is expanded — three full evidence blocks would
    bury the section, and `fmits regime --multi` already prints them.
    """
    records = []
    for view in inputs.sheet.views:
        regime = inputs.regimes[view.role]
        states = {d.name: d.state.value for d in regime.dimensions}
        records.append(
            (
                f"{view.role.value} · {view.interval}",
                states[RegimeDimensionName.STRUCTURE],
                states[RegimeDimensionName.VOLATILITY],
                states[RegimeDimensionName.PARTICIPATION],
            )
        )

    primary = inputs.primary_regime
    evidence_rows: list[Row] = []
    for dimension in primary.dimensions:
        evidence_rows.append(
            Row(dimension.name.value, dimension.state.value, tier=Tier.DERIVED)
        )
        for item in dimension.evidence:
            evidence_rows.append(
                Row(
                    f"  {item.status.value}",
                    item.observed,
                    f"{item.source} {_number(item.value)}".strip(),
                    tier=Tier.ABSENCE
                    if item.status.value == "unavailable"
                    else Tier.FACT,
                )
            )
        if dimension.reason is not None:
            evidence_rows.append(
                Row("  why", dimension.reason, tier=Tier.DERIVED)
            )

    policy = primary.policy
    return Section(
        id=SectionId.REGIME,
        title="MARKET REGIME",
        status=SectionStatus.AVAILABLE,
        summary=tuple(
            f"{record[0]}: {record[1]} · {record[2]} · {record[3]}"
            for record in records
        ),
        body=(
            TableBlock(
                columns=("role · timeframe", "structure", "volatility", "participation"),
                records=tuple(records),
                heading="BY ROLE",
            ),
            RowBlock(tuple(evidence_rows), heading=f"EVIDENCE — {inputs.primary_label}"),
        ),
        caveats=(
            "A regime is an environment, not a direction. Trending does not mean rising.",
            "Each timeframe is classified alone; nothing is derived from the combination.",
        ),
        provenance=Provenance(
            engine="fmis.market_regime",
            policy_id=policy.policy_id,
            as_of=primary.as_of,
        ),
    )


# ───────────────────────────── §3 structure ───────────────────────────────


def structure_section(inputs: WorkspaceInputs) -> WorkspaceSection:
    """What price is doing on each role's timeframe, side by side.

    After regime, so a reader learns the environment before forming a directional
    impression inside it. Restates AG's view without deriving anything from the
    set, which ADR-0023 forbids.
    """
    records = []
    counts: list[str] = []
    for view in inputs.sheet.views:
        structure = view.sheet.structure
        latest_break = structure.latest_break
        latest_change = structure.latest_change
        records.append(
            (
                f"{view.role.value} · {view.interval}",
                structure.trend.value,
                f"{latest_break.side.value} @ {latest_break.index}"
                if latest_break is not None
                else _ABSENT,
                f"{latest_change.side.value} @ {latest_change.index}"
                if latest_change is not None
                else _ABSENT,
            )
        )
        counts.append(
            f"{view.role.value}: {len(structure.breaks)} breaks, "
            f"{len(structure.changes)} changes"
        )

    return Section(
        id=SectionId.STRUCTURE,
        title="STRUCTURE BY ROLE",
        status=SectionStatus.AVAILABLE,
        summary=tuple(f"{r[0]}: {r[1]}" for r in records),
        body=(
            # Four columns, not six. The break and change counts moved into a
            # note because six columns ran past the page width, and a wrapped
            # table row reads as a different value.
            TableBlock(
                columns=(
                    "role · timeframe",
                    "structural trend",
                    "latest break",
                    "latest change",
                ),
                records=tuple(records),
            ),
            NoteBlock(("In window — " + " · ".join(counts) + ".",)),
        ),
        caveats=(
            "Reported side by side. Nothing is derived from the combination.",
            "A break is never invalidated; a 'failed break' is a later reading.",
        ),
        provenance=Provenance(
            engine="fmis.structure_break + fmis.change_of_character",
            as_of=inputs.sheet.newest_as_of,
        ),
    )


# ────────────────────────────── §4 levels ─────────────────────────────────


def levels_section(inputs: WorkspaceInputs) -> WorkspaceSection:
    """Where price sits relative to the levels the structural chain found.

    Reported as nearest above and nearest below, never as support or resistance —
    ADR-0019 §I reserves that naming for a layer that does not exist.
    """
    view = inputs.primary_view
    sheet = view.sheet
    near = sheet.nearest_levels

    def describe(level) -> tuple[str, str]:
        if level is None:
            return _ABSENT, "none in this window"
        origin = level.origin
        note = (
            f"{level.side.value} · {origin.label.value} @ bar {origin.index}"
            if origin is not None
            else level.side.value
        )
        return _number(level.price), note

    above_value, above_note = describe(near.above)
    below_value, below_note = describe(near.below)

    return Section(
        id=SectionId.LEVELS,
        title="LEVELS & PROXIMITY",
        status=SectionStatus.AVAILABLE,
        summary=(
            f"{inputs.primary_label}: {len(sheet.structure.levels)} levels, "
            f"nearest above {above_value}, nearest below {below_value}",
        ),
        body=(
            RowBlock(
                (
                    Row("Timeframe", f"{view.role.value} · {view.interval}"),
                    Row("Last close", _number(sheet.window.last_close)),
                    Row("Nearest above close", above_value, above_note),
                    Row("Nearest below close", below_value, below_note),
                    Row(
                        "Levels in window",
                        str(len(sheet.structure.levels)),
                        f"{near.upper_count} upper · {near.lower_count} lower",
                    ),
                    Row(
                        "Confirmation window",
                        f"{sheet.detection.right_bars} bars",
                        "carried on every level (ADR-0024)",
                        tier=Tier.DERIVED,
                    ),
                )
            ),
        ),
        caveats=(
            "Levels are reported as nearest above and below. Not support or resistance.",
            "The first swing high and low carry no label, so they yield no level.",
        ),
        provenance=Provenance(
            engine="fmis.level_crossing", as_of=sheet.as_of
        ),
    )


# ───────────────────────────── §5 evidence ────────────────────────────────

#: Every family the taxonomy defines, in its own declaration order. Families with
#: no descriptor are rendered with zeros rather than omitted: four of the ten
#: have no engine in this repository, and hiding them would misrepresent the
#: system's coverage as complete.
_FAMILIES: tuple[EvidenceFamily, ...] = tuple(EvidenceFamily)


def _family_of(observation: Observation) -> EvidenceFamily | None:
    """Which family an observation belongs to, from the catalogue — never guessed.

    `fmis.evidence` owns the mapping and `Observation.key` is already the
    descriptor name, so this is a lookup. Inferring a family from the key's
    spelling would be a second, drifting implementation of a rule the taxonomy
    package exists to hold.
    """
    descriptor = find(observation.key)
    return None if descriptor is None else descriptor.family


def evidence_section(inputs: WorkspaceInputs) -> WorkspaceSection:
    """Classified evidence, grouped by the taxonomy's families.

    Reads `fmis.decision_support`'s report and `fmis.evidence`'s catalogue, and
    computes nothing. This is the **first production consumer** either package
    has ever had.

    Families with no descriptor are shown with zeros, and the coverage column says
    **"no descriptor"** rather than "no engine" — the two are different failures
    and conflating them would misstate the system. ADR-0011 §1 earns a descriptor
    by being *classified*, not merely *calculated*: volume and volatility are
    computed today and deliberately not yet classified, while macro, news,
    sentiment and liquidity have no engine at all. A table that omitted either
    kind would imply coverage the repository does not have.
    """
    report = inputs.evidence
    if report is None:
        return Section(
            id=SectionId.EVIDENCE,
            title="EVIDENCE",
            status=SectionStatus.FAILED,
            summary=("No evidence report could be built for the primary view.",),
            reason="the primary view produced no analysable snapshot",
            caveats=("Absent evidence is not neutral evidence.",),
            provenance=Provenance(engine="fmis.decision_support"),
        )

    groups = report.groups
    buckets: dict[EvidenceFamily, dict[str, int]] = {
        family: {"consistent": 0, "conflicting": 0, "unavailable": 0, "non_directional": 0}
        for family in _FAMILIES
    }
    uncatalogued = 0

    def place(observation: Observation, bucket: str) -> None:
        nonlocal uncatalogued
        family = _family_of(observation)
        if family is None:
            uncatalogued += 1
            return
        buckets[family][bucket] += 1

    for observation in groups.supporting:
        place(observation, "consistent")
    for observation in groups.conflicting:
        place(observation, "conflicting")
    for observation in groups.unavailable:
        place(observation, "unavailable")
    for observation in _all_observations(report):
        if observation.alignment is Alignment.NOT_DIRECTIONAL:
            place(observation, "non_directional")

    records = tuple(
        (
            family.value,
            str(counts["consistent"]),
            str(counts["conflicting"]),
            str(counts["unavailable"]),
            str(counts["non_directional"]),
        )
        for family, counts in buckets.items()
    )

    empty = tuple(f.value for f in _FAMILIES if not _catalogued(f))
    status = SectionStatus.PARTIAL if empty else SectionStatus.AVAILABLE

    notes = [
        f"Dominant alignment: {groups.dominant_alignment.value}. "
        "A tie is reported, never broken.",
        "An oscillator band is reported but never counted as directional evidence.",
    ]
    if empty:
        notes.append(
            f"{len(empty)} of {len(_FAMILIES)} families carry no descriptor in the "
            f"evidence catalogue: {', '.join(empty)}. ADR-0011 earns a descriptor "
            "by being classified, not merely calculated — volume and volatility "
            "are computed today but not yet classified, while macro, news, "
            "sentiment and liquidity have no engine at all."
        )
    if uncatalogued:
        notes.append(
            f"{uncatalogued} observation(s) are not in the evidence catalogue and "
            "are counted in no family."
        )

    return Section(
        id=SectionId.EVIDENCE,
        title="EVIDENCE BY FAMILY",
        status=status,
        summary=(
            f"{len(groups.supporting)} consistent · {len(groups.conflicting)} "
            f"conflicting · {len(groups.unavailable)} unavailable · state "
            f"{report.state.value}",
        ),
        body=(
            TableBlock(
                # Five columns, not six: a "coverage" column pushed the table
                # past the page width, and the note beneath already names every
                # family that carries no descriptor.
                columns=(
                    "family",
                    "consistent",
                    "conflicting",
                    "unavailable",
                    "not directional",
                ),
                records=records,
            ),
            NoteBlock(tuple(notes)),
        ),
        caveats=(
            "Evidence is classified, never scored. There is no ranking here.",
            "Dominant alignment is the grouping key the evidence layer used, "
            "not a view about price.",
            "Absent evidence is not negative evidence.",
        ),
        provenance=Provenance(
            engine="fmis.decision_support + fmis.evidence",
            as_of=report.context.as_of,
        ),
    )


def _catalogued(family: EvidenceFamily) -> bool:
    """Does the evidence catalogue register any descriptor for this family?

    Asked of the taxonomy rather than inferred from whether observations landed
    in the bucket: a family can be catalogued and still contribute nothing on a
    given bar, and reporting that as "no descriptor" would be wrong.
    """
    return bool(descriptors_for(family))


def _all_observations(report: EvidenceReport) -> tuple[Observation, ...]:
    """Every observation the report holds, including non-directional ones.

    The grouped tuples deliberately exclude `NOT_DIRECTIONAL` observations, so
    counting those requires reading the evidence blocks directly. They are read,
    never re-derived.
    """
    return (
        report.trend.price_vs_ema_fast,
        report.trend.price_vs_ema_slow,
        report.trend.ema_fast_vs_ema_slow,
        report.momentum.rsi_zone,
        report.momentum.macd_vs_signal,
        report.momentum.macd_histogram,
    )


# ───────────────────────────── §6 conflicts ───────────────────────────────


def conflicts_section(inputs: WorkspaceInputs) -> WorkspaceSection:
    """Every disagreement the facts contain, listed and left unresolved.

    Its own section rather than a footnote because `SPEC` §6 requires conflicting
    evidence as a first-class output and `SPEC` §7 requires the opposing case to
    be constructed. Conflicts buried under agreement is how confirmation bias is
    rendered rather than resisted.
    """
    conflicts = inputs.conflicts
    if not conflicts:
        return Section(
            id=SectionId.CONFLICTS,
            title="CONFLICTS & MISSING EVIDENCE",
            status=SectionStatus.AVAILABLE,
            summary=("No disagreement observed among the facts on this page.",),
            body=(
                NoteBlock(
                    (
                        "No conflict does not mean agreement is meaningful: "
                        "evidence may simply be sparse.",
                    )
                ),
            ),
            caveats=("This system reports conflicts. It never resolves them.",),
            provenance=Provenance(engine="fmis.workspace.conflicts"),
        )

    # Rows, not a table: a conflict statement names two roles and a reason, and a
    # three-column table of them runs past the page width, which would wrap into
    # something a reader parses as a different value.
    rows: list[Row] = []
    for conflict in conflicts:
        rows.append(Row(conflict.kind.value, conflict.statement, tier=Tier.DERIVED))
        rows.append(Row("  participants", " · ".join(conflict.participants)))
    return Section(
        id=SectionId.CONFLICTS,
        title="CONFLICTS & MISSING EVIDENCE",
        status=SectionStatus.AVAILABLE,
        summary=(
            f"{len(conflicts)} disagreement(s) observed. None is resolved here.",
        ),
        body=(
            RowBlock(tuple(rows)),
            NoteBlock(
                (
                    "No rule here outranks another. A tie remains a tie.",
                    "Reconciling timeframes that disagree is a later layer's decision.",
                )
            ),
        ),
        caveats=("This system reports conflicts. It never resolves them.",),
        provenance=Provenance(engine="fmis.workspace.conflicts"),
    )


# ───────────────────────────── §7 decision context ────────────────────────

#: How each state reads on the page. An explicit mapping, never the enum's
#: definition order or a formatted enum value, so renaming a member fails here
#: rather than silently changing what the reader is told.
_CONTEXT_SUMMARY: Mapping[ContextState, str] = {
    ContextState.SUFFICIENT: (
        "Every requirement is met. This analysis rests on the data each layer "
        "said it needed."
    ),
    ContextState.LIMITED: (
        "Nothing blocking is missing, but the analysis is degraded in the ways "
        "named below."
    ),
    ContextState.INSUFFICIENT: (
        "A blocking requirement is unmet. Continuing toward a setup from here "
        "would be reasoning from data the system knows is not there."
    ),
}


def context_section(inputs: WorkspaceInputs) -> WorkspaceSection:
    """Whether the page above contains enough to continue — the gate, not a verdict.

    Placed immediately after conflicts because it judges everything above it, and
    immediately before the planning sections because it guards them. It is a
    statement about *information*, never about the market: `SUFFICIENT` says the
    data each layer asked for is present, and says nothing whatever about price.
    """
    context = inputs.context
    if context is None:
        return Section(
            id=SectionId.CONTEXT,
            title="DECISION CONTEXT",
            status=SectionStatus.FAILED,
            summary=("The decision context could not be evaluated.",),
            reason="the workspace produced no evaluable context input",
            caveats=("An unevaluated context is not a met one.",),
            provenance=Provenance(engine="fmis.decision_context"),
        )

    rows = [
        Row(check.requirement.value, "met" if check.met else "not met",
            check.statement, tier=Tier.DERIVED)
        for check in context.checks
    ]
    sources = NoteBlock(
        tuple(
            f"{check.requirement.value} — rule owned by {check.source}"
            for check in context.checks
        )
    )
    notes = [
        f"{len(context.blocking)} blocking · {len(context.limiting)} limiting "
        f"gap(s). Every requirement checked is listed, met ones included.",
        "Conflicts do not affect this judgement. Sufficiency is about what is "
        "available, not about whether it agrees.",
    ]

    return Section(
        id=SectionId.CONTEXT,
        title="DECISION CONTEXT",
        status=(
            SectionStatus.AVAILABLE
            if context.state is ContextState.SUFFICIENT
            else SectionStatus.PARTIAL
        ),
        summary=(
            f"{context.state.value}",
            _CONTEXT_SUMMARY[context.state],
        ),
        body=(
            RowBlock(tuple(rows), heading="REQUIREMENTS"),
            sources,
            NoteBlock(tuple(notes)),
        ),
        caveats=(
            "This judges the information, not the market. It is not a direction "
            "and not a recommendation.",
            "A met requirement means the data each layer asked for is present, "
            "not that the analysis is correct.",
        ),
        provenance=Provenance(
            engine="fmis.decision_context",
            policy_id=context.policy.policy_id,
            as_of=context.as_of,
        ),
    )


# ─────────────────────── §8–§11 the unbuilt sections ──────────────────────


def risk_section(inputs: WorkspaceInputs) -> WorkspaceSection:
    return Unavailable(
        id=SectionId.RISK,
        title="RISK",
        owner="EP-04 (Portfolio & Risk)",
        reason=(
            "Position risk, portfolio heat, correlation and concentration are not "
            "computed by this system."
        ),
        prohibition=(
            "No position size shown here would be legitimate. Do not infer one."
        ),
    )


def portfolio_section(inputs: WorkspaceInputs) -> WorkspaceSection:
    return Unavailable(
        id=SectionId.PORTFOLIO,
        title="PORTFOLIO",
        owner="EP-04 (Portfolio & Risk)",
        reason=(
            "Holdings, open risk and correlation with existing positions are not "
            "known to this system."
        ),
        prohibition=(
            "This analysis is instrument-only. It cannot tell you whether you "
            "already hold correlated exposure."
        ),
    )


def trade_plan_section(inputs: WorkspaceInputs) -> WorkspaceSection:
    return Unavailable(
        id=SectionId.TRADE_PLAN,
        title="TRADE PLAN",
        owner="EP-13 (Strategy)",
        reason=(
            "Entry, invalidation, stop, target and risk/reward are not computed "
            "by this system."
        ),
        prohibition=(
            "Nothing on this page is a trade recommendation, and no direction is "
            "expressed or implied."
        ),
    )


def interpretation_section(inputs: WorkspaceInputs) -> WorkspaceSection:
    return Unavailable(
        id=SectionId.INTERPRETATION,
        title="AI INTERPRETATION",
        owner="EP-20 (AI interpretation)",
        reason="No interpretation layer is wired to this workspace.",
        prohibition=(
            "Everything above is deterministic. No narrative has been generated, "
            "and none should be inferred."
        ),
    )


# ──────────────────────────── §11 limitations ─────────────────────────────


def limitations_section(inputs: WorkspaceInputs) -> WorkspaceSection:
    """Every limitation the underlying engines declare, plus the workspace's own.

    Inherited verbatim, each citing the ADR that owns it, so a limitation cannot
    be softened on its way to the page.
    """
    rows = tuple(
        Row(item.code, item.text, tier=Tier.ABSENCE)
        for item in inputs.limitations
    )
    return Section(
        id=SectionId.LIMITATIONS,
        title="LIMITATIONS & PROVENANCE",
        status=SectionStatus.AVAILABLE,
        summary=(f"{len(rows)} declared limitations apply to this page.",),
        body=(RowBlock(rows),),
        caveats=(),
        provenance=Provenance(engine="fmis.workspace"),
    )


#: The page, as data. A future milestone replaces one entry; nothing else moves.
SECTION_PROVIDERS: tuple[tuple[SectionId, SectionProvider], ...] = (
    (SectionId.INSTRUMENT, instrument_section),
    (SectionId.REGIME, regime_section),
    (SectionId.STRUCTURE, structure_section),
    (SectionId.LEVELS, levels_section),
    (SectionId.EVIDENCE, evidence_section),
    (SectionId.CONFLICTS, conflicts_section),
    (SectionId.CONTEXT, context_section),
    (SectionId.RISK, risk_section),
    (SectionId.PORTFOLIO, portfolio_section),
    (SectionId.TRADE_PLAN, trade_plan_section),
    (SectionId.INTERPRETATION, interpretation_section),
    (SectionId.LIMITATIONS, limitations_section),
)


def build_sections(inputs: WorkspaceInputs) -> tuple[WorkspaceSection, ...]:
    """Run every registered provider, in registry order.

    A provider that returned the wrong section id is rejected here rather than
    producing a page whose order silently disagrees with `SECTION_ORDER`.
    """
    built: list[WorkspaceSection] = []
    for section_id, provider in SECTION_PROVIDERS:
        section = provider(inputs)
        if section.id is not section_id:
            raise TypeError(
                f"provider for {section_id.value} returned section "
                f"{section.id.value}"
            )
        built.append(section)
    return tuple(built)

