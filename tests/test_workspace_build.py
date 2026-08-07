"""Milestone AK — conflict detection, section providers, and the builder.

The load-bearing claims here: conflicts are **reported and never resolved**, the
builder **computes nothing**, evidence comes from the two packages that already
own it, and the page's empty slots stay visible.
"""

from __future__ import annotations

import ast
import pathlib
import random
from datetime import datetime, timedelta, timezone

import pytest

from fmis.data import Candle, CandleSeries
from fmis.decision_support import Alignment, build_evidence_report
from fmis.evidence import EvidenceFamily, descriptors_for
from fmis.market_regime import (
    MarketRegime,
    RegimeDimensionName,
    RegimePolicy,
    StructureState,
    classify_regime,
)
from fmis.pipeline.multi_timeframe import (
    TimeframeRole,
    build_multi_timeframe_facts,
)
from fmis.pipeline.regime import regime_features, regime_for_sheet
from fmis.pipeline.structural_facts import DetectionSettings, build_structural_facts
from fmis.structural_trend import StructuralTrendType
from fmis.trading_context import TradingObjective
from fmis.workspace import (
    SECTION_PROVIDERS,
    Conflict,
    ConflictKind,
    SectionId,
    SectionStatus,
    Unavailable,
    Workspace,
    build_workspace,
    detect_conflicts,
    snapshot_from_sheet,
)
from fmis.workspace.builder import WORKSPACE_LIMITATIONS

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "fmis"


# ============================ fixtures =======================================


def seeded_series(count: int = 260, seed: int = 5, symbol: str = "BTCUSDT",
                  timeframe: str = "4h") -> CandleSeries:
    rng = random.Random(seed)
    candles = []
    for i in range(count):
        open_ = rng.uniform(95.0, 105.0)
        close = rng.uniform(95.0, 105.0)
        candles.append(
            Candle(
                timestamp=_BASE + timedelta(hours=4 * i),
                symbol=symbol,
                timeframe=timeframe,
                open=open_,
                high=max(open_, close) + rng.uniform(0.0, 3.0),
                low=min(open_, close) - rng.uniform(0.0, 3.0),
                close=close,
                volume=rng.uniform(0.5, 5.0),
                is_closed=True,
            )
        )
    return CandleSeries(symbol=symbol, timeframe=timeframe, candles=tuple(candles))


def facts(seed: int = 5, count: int = 260, **kwargs):
    return build_structural_facts(
        seeded_series(count=count, seed=seed),
        features=regime_features(),
        source="fixture",
        **kwargs,
    )


def multi(seeds: tuple[int, int, int] = (1, 5, 9)):
    """A three-view sheet whose views come from different seeds, so they differ."""
    return build_multi_timeframe_facts(
        {
            TimeframeRole.CONTEXT: facts(seed=seeds[0]),
            TimeframeRole.SETUP: facts(seed=seeds[1]),
            TimeframeRole.EXECUTION: facts(seed=seeds[2]),
        },
        intervals={
            TimeframeRole.CONTEXT: "1w",
            TimeframeRole.SETUP: "1d",
            TimeframeRole.EXECUTION: "4h",
        },
        source="fixture",
    )


def regime_of(trend: StructuralTrendType, **overrides) -> MarketRegime:
    from tests.test_market_regime import make_input

    return classify_regime(make_input(structural_trend=trend, **overrides))


# ============ 1. conflicts are reported, never resolved =====================


def test_opposed_sustained_trends_are_reported() -> None:
    conflicts = detect_conflicts(
        trends=[
            (TimeframeRole.CONTEXT, "1w", StructuralTrendType.SUSTAINED_HIGHER),
            (TimeframeRole.SETUP, "1d", StructuralTrendType.SUSTAINED_LOWER),
        ],
        regimes=[],
    )
    assert len(conflicts) == 1
    assert conflicts[0].kind is ConflictKind.STRUCTURAL_TREND
    assert conflicts[0].participants == ("context · 1w", "setup · 1d")


def test_neutral_and_indeterminate_never_conflict_with_a_trend() -> None:
    """Absence is not disagreement — the rule AI established, applied here."""
    for quiet in (StructuralTrendType.NEUTRAL, StructuralTrendType.INDETERMINATE):
        assert (
            detect_conflicts(
                trends=[
                    (TimeframeRole.CONTEXT, "1w", StructuralTrendType.SUSTAINED_HIGHER),
                    (TimeframeRole.SETUP, "1d", quiet),
                ],
                regimes=[],
            )
            == ()
        )


def test_agreeing_trends_produce_no_conflict() -> None:
    assert (
        detect_conflicts(
            trends=[
                (TimeframeRole.CONTEXT, "1w", StructuralTrendType.SUSTAINED_LOWER),
                (TimeframeRole.SETUP, "1d", StructuralTrendType.SUSTAINED_LOWER),
            ],
            regimes=[],
        )
        == ()
    )


def test_regime_structure_disagreement_is_reported() -> None:
    trending = regime_of(StructuralTrendType.SUSTAINED_HIGHER)
    ranging = regime_of(
        StructuralTrendType.NEUTRAL, close=97.0, ema_fast=100.0, ema_slow=95.0
    )
    conflicts = detect_conflicts(
        trends=[],
        regimes=[
            (TimeframeRole.CONTEXT, "1w", trending),
            (TimeframeRole.SETUP, "1d", ranging),
        ],
    )
    kinds = {c.kind for c in conflicts}
    assert ConflictKind.REGIME_STRUCTURE in kinds


def test_transitioning_and_insufficient_are_not_opposites() -> None:
    """Only trending against ranging is a decisive disagreement."""
    transitioning = regime_of(
        StructuralTrendType.SUSTAINED_HIGHER, closed_count=101, latest_change_index=99
    )
    insufficient = regime_of(StructuralTrendType.INDETERMINATE)
    conflicts = detect_conflicts(
        trends=[],
        regimes=[
            (TimeframeRole.CONTEXT, "1w", transitioning),
            (TimeframeRole.SETUP, "1d", insufficient),
        ],
    )
    assert all(c.kind is not ConflictKind.REGIME_STRUCTURE for c in conflicts)


def test_an_indeterminate_regime_is_itself_a_conflict() -> None:
    indeterminate = regime_of(
        StructuralTrendType.SUSTAINED_HIGHER, close=97.0, ema_fast=100.0, ema_slow=95.0
    )
    assert (
        indeterminate.by_dimension[RegimeDimensionName.STRUCTURE].state
        is StructureState.INDETERMINATE
    )
    conflicts = detect_conflicts(
        trends=[], regimes=[(TimeframeRole.SETUP, "1d", indeterminate)]
    )
    assert [c.kind for c in conflicts] == [ConflictKind.REGIME_INDETERMINATE]
    assert "moving averages" in conflicts[0].participants


def test_an_insufficient_regime_is_not_reported_as_a_conflict() -> None:
    """Evidence absent belongs under missing evidence, not disagreement."""
    conflicts = detect_conflicts(
        trends=[],
        regimes=[
            (TimeframeRole.SETUP, "1d", regime_of(StructuralTrendType.INDETERMINATE))
        ],
    )
    assert conflicts == ()


def test_evidence_conflicts_are_surfaced_not_recomputed() -> None:
    report = build_evidence_report(snapshot_from_sheet(facts(seed=3)))
    conflicts = detect_conflicts(
        trends=[], regimes=[], evidence=("setup · 1d", report)
    )
    if report.groups.conflicting:
        assert any(c.kind is ConflictKind.EVIDENCE_DISAGREEMENT for c in conflicts)
    else:
        assert all(c.kind is not ConflictKind.EVIDENCE_DISAGREEMENT for c in conflicts)


def test_conflict_output_is_ordered_and_input_order_independent() -> None:
    trends = [
        (TimeframeRole.CONTEXT, "1w", StructuralTrendType.SUSTAINED_HIGHER),
        (TimeframeRole.SETUP, "1d", StructuralTrendType.SUSTAINED_LOWER),
        (TimeframeRole.EXECUTION, "4h", StructuralTrendType.SUSTAINED_HIGHER),
    ]
    first = detect_conflicts(trends=trends, regimes=[])
    second = detect_conflicts(trends=list(reversed(trends)), regimes=[])
    assert {c.statement for c in first} == {c.statement for c in second}
    assert [c.kind for c in first] == sorted(
        [c.kind for c in first], key=lambda k: list(ConflictKind).index(k)
    )


def test_conflicts_never_resolve_rank_or_recommend() -> None:
    """The module may not contain the vocabulary of a decision."""
    source = (SRC / "workspace" / "conflicts.py").read_text()
    tree = ast.parse(source)
    docstrings = {
        d
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and (d := ast.get_docstring(node, clean=False)) is not None
    }
    tokens: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                tokens.update(node.value.lower().replace("_", " ").split())
        elif isinstance(node, ast.Name):
            tokens.update(node.id.lower().split("_"))
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            tokens.update(node.name.lower().split("_"))
    # `dominant` is deliberately absent from this list: it names
    # `EvidenceGroups.dominant_alignment`, a field ADR-0008 defined and this
    # module reads. Forbidding a module from mentioning the contract it consumes
    # would push the explanation out of the code rather than out the behaviour.
    for banned in ("resolve", "resolved", "winner", "wins", "outranks", "score",
                   "severity", "priority", "recommend", "prefer", "override"):
        assert banned not in tokens, banned


def test_a_conflict_validates_itself() -> None:
    with pytest.raises(TypeError):
        Conflict(kind="structural_trend", statement="s", participants=("a",))
    with pytest.raises(ValueError):
        Conflict(kind=ConflictKind.STRUCTURAL_TREND, statement=" ", participants=("a",))
    with pytest.raises(ValueError):
        Conflict(kind=ConflictKind.STRUCTURAL_TREND, statement="s", participants=())
    with pytest.raises(ValueError):
        Conflict(kind=ConflictKind.STRUCTURAL_TREND, statement="s", participants=(" ",))


def test_detect_conflicts_rejects_a_string_sequence() -> None:
    for kwargs in (dict(trends="x", regimes=[]), dict(trends=[], regimes="x")):
        with pytest.raises(TypeError):
            detect_conflicts(**kwargs)  # type: ignore[arg-type]


def test_no_conflict_kind_names_a_severity_or_a_winner() -> None:
    for member in ConflictKind:
        for banned in ("major", "minor", "critical", "dominant", "override", "wins"):
            assert banned not in member.value


# ============ 2. the evidence join ==========================================


def test_the_snapshot_adapter_copies_and_never_fetches() -> None:
    sheet = facts()
    snapshot = snapshot_from_sheet(sheet)
    assert snapshot.symbol == sheet.symbol
    assert snapshot.interval == sheet.interval
    assert snapshot.as_of == sheet.as_of
    assert snapshot.window is sheet.window
    assert snapshot.features is sheet.features


def test_the_adapter_rejects_anything_that_is_not_a_sheet() -> None:
    with pytest.raises(TypeError):
        snapshot_from_sheet("not a sheet")  # type: ignore[arg-type]


def test_the_evidence_report_is_built_from_the_same_fetch() -> None:
    """Calling analyze_symbol instead would fetch twice and could disagree."""
    sheet = facts()
    report = build_evidence_report(snapshot_from_sheet(sheet))
    assert report.context.as_of == sheet.as_of
    assert report.context.symbol == sheet.symbol


def test_every_observation_key_resolves_to_a_catalogued_family() -> None:
    """The workspace places observations by lookup, never by guessing the name."""
    from fmis.evidence import find

    report = build_evidence_report(snapshot_from_sheet(facts()))
    groups = report.groups
    for observation in groups.supporting + groups.conflicting + groups.unavailable:
        assert find(observation.key) is not None, observation.key


def test_only_two_families_are_catalogued_today() -> None:
    """Pins the coverage the evidence section reports, so a change is visible."""
    catalogued = {f for f in EvidenceFamily if descriptors_for(f)}
    assert catalogued == {EvidenceFamily.TREND, EvidenceFamily.MOMENTUM}


# ============ 3. the builder ================================================


def test_the_builder_produces_a_complete_page() -> None:
    workspace = build_workspace(multi())
    assert isinstance(workspace, Workspace)
    assert len(workspace.sections) == 12
    assert {s.id for s in workspace.sections} == set(SectionId)


def test_the_unbuilt_sections_are_unavailable_and_name_their_owner() -> None:
    workspace = build_workspace(multi())
    expected = {
        SectionId.RISK: "EP-04",
        SectionId.PORTFOLIO: "EP-04",
        SectionId.TRADE_PLAN: "EP-13",
        SectionId.INTERPRETATION: "EP-20",
    }
    for section_id, owner in expected.items():
        section = workspace.by_id[section_id]
        assert isinstance(section, Unavailable)
        assert owner in section.owner
        assert section.prohibition


def test_the_built_sections_all_answered() -> None:
    workspace = build_workspace(multi())
    for section_id in (
        SectionId.INSTRUMENT,
        SectionId.REGIME,
        SectionId.STRUCTURE,
        SectionId.LEVELS,
        SectionId.EVIDENCE,
        SectionId.CONFLICTS,
        SectionId.LIMITATIONS,
    ):
        section = workspace.by_id[section_id]
        assert section.status in (SectionStatus.AVAILABLE, SectionStatus.PARTIAL)
        assert section.provenance is not None


def test_the_builder_is_a_pure_function_of_its_sheet() -> None:
    sheet = multi()
    assert build_workspace(sheet) == build_workspace(sheet)


def test_one_policy_classifies_every_view() -> None:
    """Three regimes are only comparable if one policy produced them."""
    policy = RegimePolicy(policy_id="swept", volatility_band=0.35)
    workspace = build_workspace(multi(), policy=policy)
    provenance = workspace.by_id[SectionId.REGIME].provenance
    assert provenance is not None and provenance.policy_id == "swept"


def test_the_primary_role_selects_levels_and_evidence() -> None:
    workspace = build_workspace(multi(), primary_role=TimeframeRole.EXECUTION)
    assert "execution" in workspace.by_id[SectionId.LEVELS].summary[0]
    assert workspace.metadata["primary_role"] == "execution"


def test_an_unknown_primary_role_is_rejected() -> None:
    sheet = build_multi_timeframe_facts(
        {TimeframeRole.SETUP: facts()},
        intervals={TimeframeRole.SETUP: "1d"},
        source="fixture",
    )
    with pytest.raises(ValueError) as excinfo:
        build_workspace(sheet, primary_role=TimeframeRole.CONTEXT)
    assert "not among the sheet's views" in str(excinfo.value)


def test_builder_type_validation() -> None:
    with pytest.raises(TypeError):
        build_workspace("not a sheet")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_workspace(multi(), objective="swing")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_workspace(multi(), primary_role="setup")  # type: ignore[arg-type]


def test_the_objective_is_recorded_never_inferred() -> None:
    workspace = build_workspace(multi(), objective=TradingObjective.DAY_TRADE)
    assert workspace.objective == "day_trade"


def test_the_workspace_inherits_every_limitation_layer() -> None:
    workspace = build_workspace(multi())
    text = " ".join(
        row.label for block in workspace.by_id[SectionId.LIMITATIONS].body
        for row in block.rows
    )
    assert "ADR-0019 D2" in text
    assert "AG-1" in text
    assert "AI-1" in text
    for limitation in WORKSPACE_LIMITATIONS:
        assert limitation.code in text


def test_a_short_window_reports_evidence_as_failed_not_missing() -> None:
    """A page whose evidence could not be built is still true everywhere else."""
    import dataclasses

    sheet = multi()
    view = sheet.by_role[TimeframeRole.SETUP]
    broken_window = dataclasses.replace(view.sheet.window, last_close=None)
    broken_sheet = dataclasses.replace(view.sheet, window=broken_window)
    replaced = build_multi_timeframe_facts(
        {
            TimeframeRole.CONTEXT: sheet.by_role[TimeframeRole.CONTEXT].sheet,
            TimeframeRole.SETUP: broken_sheet,
            TimeframeRole.EXECUTION: sheet.by_role[TimeframeRole.EXECUTION].sheet,
        },
        intervals={
            TimeframeRole.CONTEXT: "1w",
            TimeframeRole.SETUP: "1d",
            TimeframeRole.EXECUTION: "4h",
        },
        source="fixture",
    )
    workspace = build_workspace(replaced)
    evidence = workspace.by_id[SectionId.EVIDENCE]
    assert evidence.status is SectionStatus.FAILED
    assert evidence.reason
    assert workspace.by_id[SectionId.STRUCTURE].status is SectionStatus.AVAILABLE


# ============ 4. the registry is the extension surface ======================


def test_the_registry_covers_every_section_exactly_once_and_in_order() -> None:
    from fmis.workspace.models import SECTION_ORDER

    assert tuple(sid for sid, _ in SECTION_PROVIDERS) == SECTION_ORDER


def test_a_provider_returning_the_wrong_section_is_rejected() -> None:
    from fmis.workspace import sections as sections_module

    original = sections_module.SECTION_PROVIDERS
    wrong = ((SectionId.INSTRUMENT, sections_module.risk_section),) + original[1:]
    try:
        sections_module.SECTION_PROVIDERS = wrong  # type: ignore[misc]
        with pytest.raises(TypeError) as excinfo:
            build_workspace(multi())
        assert "returned section" in str(excinfo.value)
    finally:
        sections_module.SECTION_PROVIDERS = original  # type: ignore[misc]


def test_no_provider_computes_a_market_quantity() -> None:
    """Providers copy; engines compute. Asserted over the whole module."""
    tree = ast.parse((SRC / "workspace" / "sections.py").read_text())
    offenders = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(node.op, (ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Pow,
                                 ast.Mod))
    ]
    assert offenders == [], [ast.unparse(o) for o in offenders]


def test_the_builder_calls_no_engine_directly() -> None:
    """It composes roots; it does not reach past them into an engine."""
    tree = ast.parse((SRC / "workspace" / "builder.py").read_text())
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for banned in ("detect_swings", "structural_levels", "derive_structure_breaks",
                   "derive_level_crossings", "classify_regime"):
        assert banned not in called, banned


# ============ 5. the branches a fixture does not naturally reach =============


def test_a_warming_up_view_reports_partial_and_names_the_feature() -> None:
    """A 40-candle view cannot compute ema_200, and the page must say so."""
    short = build_multi_timeframe_facts(
        {
            TimeframeRole.CONTEXT: facts(seed=1, count=40),
            TimeframeRole.SETUP: facts(seed=5),
            TimeframeRole.EXECUTION: facts(seed=9),
        },
        intervals={
            TimeframeRole.CONTEXT: "1w",
            TimeframeRole.SETUP: "1d",
            TimeframeRole.EXECUTION: "4h",
        },
        source="fixture",
    )
    section = build_workspace(short).by_id[SectionId.INSTRUMENT]
    assert section.status is SectionStatus.PARTIAL
    notes = [b for b in section.body if hasattr(b, "notes")]
    assert notes and "Warming up" in notes[0].notes[0]
    assert "not zero and not neutral" in notes[0].notes[1]


def test_a_view_with_no_levels_reports_both_sides_as_absent() -> None:
    """A short window yields no labelled swing, so no nearest level exists."""
    tiny = build_multi_timeframe_facts(
        {TimeframeRole.SETUP: facts(seed=5, count=12)},
        intervals={TimeframeRole.SETUP: "1d"},
        source="fixture",
    )
    section = build_workspace(tiny).by_id[SectionId.LEVELS]
    rows = [row for block in section.body for row in getattr(block, "rows", ())]
    absent = [r for r in rows if r.note == "none in this window"]
    assert len(absent) == 2


def test_a_regime_dimension_reason_is_carried_onto_the_page() -> None:
    """The 'why' line exists exactly when a dimension declined to classify."""
    workspace = build_workspace(multi(seeds=(1, 2, 9)))
    section = workspace.by_id[SectionId.REGIME]
    rows = [row for block in section.body for row in getattr(block, "rows", ())]
    labels = [r.label.strip() for r in rows]
    states = {
        r.label.strip(): r.value
        for r in rows
        if r.label.strip() in {"structure", "volatility", "participation"}
    }
    if any(v in {"indeterminate", "insufficient"} for v in states.values()):
        assert "why" in labels
    else:
        assert "why" not in labels


def test_an_uncatalogued_observation_is_counted_in_no_family() -> None:
    """A descriptor the catalogue does not know must not be silently binned."""
    import dataclasses

    from fmis.decision_support import Observation
    from fmis.workspace.sections import WorkspaceInputs, evidence_section

    sheet = multi()
    report = build_evidence_report(snapshot_from_sheet(facts()))
    stranger = dataclasses.replace(report.groups.supporting[0], key="not_catalogued")
    groups = dataclasses.replace(
        report.groups, supporting=(stranger,) + report.groups.supporting[1:]
    )
    patched = dataclasses.replace(report, groups=groups)

    section = evidence_section(
        WorkspaceInputs(
            symbol="BTCUSDT",
            objective="swing_trade",
            source="fixture",
            sheet=sheet,
            regimes={v.role: regime_for_sheet(v.sheet) for v in sheet.views},
            primary_role=TimeframeRole.SETUP,
            conflicts=(),
            evidence=patched,
            context=None,
            limitations=(),
        )
    )
    notes = [b for b in section.body if hasattr(b, "notes")][0]
    assert any("not in the evidence catalogue" in n for n in notes.notes)


def test_unavailable_observations_are_placed_in_their_family() -> None:
    """A warming-up feature produces an UNAVAILABLE observation, not an omission."""
    report = build_evidence_report(snapshot_from_sheet(facts(count=25)))
    assert report.groups.unavailable
    tiny = build_multi_timeframe_facts(
        {TimeframeRole.SETUP: facts(count=25)},
        intervals={TimeframeRole.SETUP: "1d"},
        source="fixture",
    )
    section = build_workspace(tiny).by_id[SectionId.EVIDENCE]
    table = [b for b in section.body if hasattr(b, "records")][0]
    unavailable_total = sum(int(record[3]) for record in table.records)
    assert unavailable_total == len(report.groups.unavailable)


def test_a_non_numeric_value_renders_as_the_absence_marker() -> None:
    from fmis.workspace.sections import _number

    assert _number(None) == "—"
    assert _number(True) == "—"
    assert _number("100") == "—"
    assert _number(1234.5) == "1,234.50"


def test_an_evidence_tie_is_reported_as_a_conflict() -> None:
    """ADR-0008 §5: a tie yields no dominant alignment, and the tie is the finding."""
    import dataclasses

    report = build_evidence_report(snapshot_from_sheet(facts()))
    tied = dataclasses.replace(
        report.groups, dominant_alignment=Alignment.NEUTRAL
    )
    conflicts = detect_conflicts(
        trends=[], regimes=[], evidence=("setup · 1d", dataclasses.replace(report, groups=tied))
    )
    assert any(c.kind is ConflictKind.EVIDENCE_TIE for c in conflicts)


def test_agreeing_regime_states_produce_no_regime_conflict() -> None:
    """Exercises the loop's skip branch: identical decisive states are not a conflict."""
    trending = regime_of(StructuralTrendType.SUSTAINED_HIGHER)
    conflicts = detect_conflicts(
        trends=[],
        regimes=[
            (TimeframeRole.CONTEXT, "1w", trending),
            (TimeframeRole.SETUP, "1d", trending),
        ],
    )
    assert all(c.kind is not ConflictKind.REGIME_STRUCTURE for c in conflicts)


# ============ 6. gaps the mutation gate found ===============================


def test_a_duplicate_section_in_canonical_order_is_still_rejected() -> None:
    """Survivor 3: the earlier test's duplicate also broke the *order* check.

    Appending a repeat put the ids out of canonical order, so the order guard
    fired and the duplicate guard was never exercised. This repeats a section
    *in place*, where only the duplicate check can catch it.
    """
    from fmis.workspace.models import SECTION_ORDER, Workspace

    sections = list(build_workspace(multi()).sections)
    doubled = tuple([sections[0]] + sections)
    assert [s.id for s in doubled] == sorted(
        [s.id for s in doubled], key=lambda sid: SECTION_ORDER.index(sid)
    )
    with pytest.raises(Exception) as excinfo:
        Workspace(
            symbol="BTCUSDT", objective="swing_trade",
            as_of=sections[0].provenance.as_of, source="fixture", sections=doubled,
        )
    assert "repeat a section" in str(excinfo.value)


def test_trending_against_insufficient_is_not_a_regime_conflict() -> None:
    """Survivor 17: `INSUFFICIENT` is missing evidence, not the opposite of trending."""
    conflicts = detect_conflicts(
        trends=[],
        regimes=[
            (TimeframeRole.CONTEXT, "1w", regime_of(StructuralTrendType.SUSTAINED_HIGHER)),
            (TimeframeRole.SETUP, "1d", regime_of(StructuralTrendType.INDETERMINATE)),
        ],
    )
    assert all(c.kind is not ConflictKind.REGIME_STRUCTURE for c in conflicts)


def test_regime_conflicts_are_also_order_independent() -> None:
    """Survivor 20: order independence was asserted for trends only."""
    trending = regime_of(StructuralTrendType.SUSTAINED_HIGHER)
    ranging = regime_of(
        StructuralTrendType.NEUTRAL, close=97.0, ema_fast=100.0, ema_slow=95.0
    )
    pairs = [
        (TimeframeRole.CONTEXT, "1w", trending),
        (TimeframeRole.EXECUTION, "4h", ranging),
    ]
    forward = detect_conflicts(trends=[], regimes=pairs)
    backward = detect_conflicts(trends=[], regimes=list(reversed(pairs)))
    assert [c.statement for c in forward] == [c.statement for c in backward]


def test_conflicts_are_ordered_by_kind_then_statement() -> None:
    """Survivor 21: with mixed kinds, the kind rank must decide the order.

    Chosen so the two orderings genuinely disagree: the structural-trend
    statement begins "setup", the regime statement begins "context". Sorting by
    statement alone would put the regime conflict first, so only the kind rank
    can produce the asserted order.
    """
    indeterminate = regime_of(
        StructuralTrendType.SUSTAINED_HIGHER, close=97.0, ema_fast=100.0, ema_slow=95.0
    )
    conflicts = detect_conflicts(
        trends=[
            (TimeframeRole.SETUP, "1d", StructuralTrendType.SUSTAINED_HIGHER),
            (TimeframeRole.EXECUTION, "4h", StructuralTrendType.SUSTAINED_LOWER),
        ],
        regimes=[(TimeframeRole.CONTEXT, "1w", indeterminate)],
    )
    kinds = [c.kind for c in conflicts]
    assert kinds == [
        ConflictKind.STRUCTURAL_TREND,
        ConflictKind.REGIME_INDETERMINATE,
    ]
    statements = [c.statement for c in conflicts]
    assert statements != sorted(statements), (
        "the fixture must distinguish kind order from statement order"
    )


def _report_with_conflicting_evidence():
    """An evidence report that definitely carries a conflicting observation."""
    import dataclasses

    report = build_evidence_report(snapshot_from_sheet(facts()))
    groups = report.groups
    pool = groups.supporting + groups.conflicting
    assert len(pool) >= 2
    moved = dataclasses.replace(
        groups, supporting=pool[:1], conflicting=pool[1:]
    )
    return dataclasses.replace(report, groups=moved)


def test_evidence_disagreement_is_reported_when_it_exists() -> None:
    """Survivor 22: the earlier assertion was conditional and passed vacuously."""
    report = _report_with_conflicting_evidence()
    conflicts = detect_conflicts(
        trends=[], regimes=[], evidence=("setup · 1d", report)
    )
    disagreements = [
        c for c in conflicts if c.kind is ConflictKind.EVIDENCE_DISAGREEMENT
    ]
    assert len(disagreements) == 1
    assert str(len(report.groups.conflicting)) in disagreements[0].statement


def test_a_dimension_reason_reaches_the_page_when_one_exists() -> None:
    """Survivor 28: asserted conditionally before, so dropping it went unnoticed."""
    from fmis.workspace.sections import WorkspaceInputs, regime_section

    indeterminate = regime_of(
        StructuralTrendType.SUSTAINED_HIGHER, close=97.0, ema_fast=100.0, ema_slow=95.0
    )
    sheet = multi()
    section = regime_section(
        WorkspaceInputs(
            symbol="BTCUSDT", objective="swing_trade", source="fixture", sheet=sheet,
            regimes={view.role: indeterminate for view in sheet.views},
            primary_role=TimeframeRole.SETUP, conflicts=(), evidence=None,
            context=None, limitations=(),
        )
    )
    rows = [row for block in section.body for row in getattr(block, "rows", ())]
    reasons = [r for r in rows if r.label.strip() == "why"]
    assert len(reasons) == 1
    assert "disagree" in reasons[0].value


def test_the_structure_table_carries_each_view_s_actual_trend() -> None:
    """Survivor 29: nothing asserted the trend value itself, only its presence."""
    sheet = multi()
    section = build_workspace(sheet).by_id[SectionId.STRUCTURE]
    table = [b for b in section.body if hasattr(b, "records")][0]
    expected = {
        f"{v.role.value} · {v.interval}": v.sheet.structure.trend.value
        for v in sheet.views
    }
    assert {record[0]: record[1] for record in table.records} == expected


def test_the_levels_section_reads_the_primary_view_s_numbers() -> None:
    """Survivor 30: the label came from the primary role, the numbers from a view.

    A mutation reading `views[0]` left the heading saying "execution" while the
    prices came from the context view — a mislabelled section that every earlier
    assertion accepted, because they only checked the label.
    """
    sheet = multi()
    workspace = build_workspace(sheet, primary_role=TimeframeRole.EXECUTION)
    section = workspace.by_id[SectionId.LEVELS]
    expected = sheet.by_role[TimeframeRole.EXECUTION].sheet
    rows = {r.label: r.value for block in section.body for r in getattr(block, "rows", ())}
    assert rows["Levels in window"] == str(len(expected.structure.levels))
    assert str(len(expected.structure.levels)) in section.summary[0]
    assert rows["Timeframe"] == "execution · 4h"


def test_the_family_table_counts_match_the_evidence_groups() -> None:
    """Survivor 32: nothing tied the consistent column to the supporting group."""
    sheet = multi()
    report = build_evidence_report(
        snapshot_from_sheet(sheet.by_role[TimeframeRole.SETUP].sheet)
    )
    section = build_workspace(sheet).by_id[SectionId.EVIDENCE]
    table = [b for b in section.body if hasattr(b, "records")][0]
    totals = [sum(int(r[i]) for r in table.records) for i in (1, 2, 3)]
    assert totals[0] == len(report.groups.supporting)
    assert totals[1] == len(report.groups.conflicting)
    assert totals[2] == len(report.groups.unavailable)


def test_uncatalogued_families_are_named_and_the_section_reports_partial() -> None:
    """Survivors 35 and 36: coverage was described but never asserted."""
    section = build_workspace(multi()).by_id[SectionId.EVIDENCE]
    assert section.status is SectionStatus.PARTIAL

    expected = sorted(f.value for f in EvidenceFamily if not descriptors_for(f))
    notes = [b for b in section.body if hasattr(b, "notes")][0]
    coverage = next(n for n in notes.notes if "no descriptor" in n)
    assert f"{len(expected)} of {len(list(EvidenceFamily))} families" in coverage
    for family in expected:
        assert family in coverage


def test_the_conflicts_section_lists_statements_when_conflicts_exist() -> None:
    """Survivor 37: both branches carry the same caveat, so only the body differs."""
    from fmis.workspace.sections import WorkspaceInputs, conflicts_section

    sheet = multi()
    conflict = Conflict(
        kind=ConflictKind.STRUCTURAL_TREND,
        statement="context · 1w reports x while setup · 1d reports y",
        participants=("context · 1w", "setup · 1d"),
    )
    base = dict(
        symbol="BTCUSDT", objective="swing_trade", source="fixture", sheet=sheet,
        regimes={v.role: regime_for_sheet(v.sheet) for v in sheet.views},
        primary_role=TimeframeRole.SETUP, evidence=None, context=None,
        limitations=(),
    )
    with_conflict = conflicts_section(WorkspaceInputs(conflicts=(conflict,), **base))
    without = conflicts_section(WorkspaceInputs(conflicts=(), **base))

    rows = [r for block in with_conflict.body for r in getattr(block, "rows", ())]
    assert any(conflict.statement == r.value for r in rows)
    assert "1 disagreement" in with_conflict.summary[0]

    assert without.body and not any(
        getattr(b, "rows", ()) for b in without.body
    )
    assert "No disagreement observed" in without.summary[0]


# ============ 7. the decision context section (Milestone AL) =================


def test_the_page_gained_a_gate_between_conflicts_and_the_planning_sections() -> None:
    """A gate belongs after everything it judges and before everything it guards."""
    from fmis.workspace.models import SECTION_ORDER

    order = list(SECTION_ORDER)
    assert order.index(SectionId.CONFLICTS) < order.index(SectionId.CONTEXT)
    assert order.index(SectionId.CONTEXT) < order.index(SectionId.RISK)
    assert len(order) == 12


def test_the_context_section_discriminates_thin_data_from_full_data() -> None:
    """The measured gap: before AL these three pages looked alike."""
    from fmis.decision_context import ContextState

    seen = {}
    for count in (12, 40, 260):
        sheet = build_multi_timeframe_facts(
            {TimeframeRole.SETUP: facts(seed=5, count=count)},
            intervals={TimeframeRole.SETUP: "1d"}, source="fixture")
        section = build_workspace(sheet).by_id[SectionId.CONTEXT]
        seen[count] = section.summary[0]
    assert seen[12] == ContextState.INSUFFICIENT.value
    assert seen[40] == ContextState.LIMITED.value
    assert seen[260] == ContextState.SUFFICIENT.value


def test_the_context_section_lists_every_requirement_and_its_owner() -> None:
    from fmis.decision_context import Requirement, SOURCES

    section = build_workspace(multi()).by_id[SectionId.CONTEXT]
    rows = [r for block in section.body for r in getattr(block, "rows", ())]
    assert {r.label for r in rows} == {r.value for r in Requirement}
    notes = [n for block in section.body for n in getattr(block, "notes", ())]
    for requirement, source in SOURCES.items():
        assert any(requirement.value in n and source in n for n in notes)


def test_the_adapter_reads_each_view_s_own_detection_requirement() -> None:
    """Depth is judged against what that analysis needed, not against a literal."""
    from fmis.market_structure import required_candles
    from fmis.workspace.builder import context_input_from_facts

    sheet = build_multi_timeframe_facts(
        {TimeframeRole.SETUP: facts(seed=5, count=260,
                                    detection=DetectionSettings(4, 6))},
        intervals={TimeframeRole.SETUP: "1d"}, source="fixture")
    regimes = {v.role: regime_for_sheet(v.sheet) for v in sheet.views}
    subject = context_input_from_facts(
        sheet, regimes, None, primary_role=TimeframeRole.SETUP, conflict_count=0)
    assert subject.primary.required_candles == required_candles(4, 6)
    assert subject.primary.closed_candles == sheet.views[0].sheet.window.closed_count


def test_a_missing_evidence_report_is_itself_insufficiency() -> None:
    from fmis.workspace.builder import context_input_from_facts

    sheet = multi()
    regimes = {v.role: regime_for_sheet(v.sheet) for v in sheet.views}
    subject = context_input_from_facts(
        sheet, regimes, None, primary_role=TimeframeRole.SETUP, conflict_count=0)
    assert subject.evidence_is_insufficient is True


def test_the_context_section_never_states_a_direction() -> None:
    import re

    banned = {"long", "short", "buy", "sell", "bullish", "bearish", "entry",
              "target", "stop", "recommend", "score"}
    section = build_workspace(multi()).by_id[SectionId.CONTEXT]
    text = " ".join(
        list(section.summary)
        + [f"{r.label} {r.value} {r.note}" for b in section.body for r in getattr(b, "rows", ())]
        + [n for b in section.body for n in getattr(b, "notes", ())]
        + list(section.caveats)
    )
    assert not (set(re.findall(r"[a-z]+", text.lower())) & banned)


def test_the_strict_policy_reaches_the_page() -> None:
    from fmis.decision_context import ContextPolicy, ContextState

    sheet = build_multi_timeframe_facts(
        {TimeframeRole.SETUP: facts(seed=5, count=40)},
        intervals={TimeframeRole.SETUP: "1d"}, source="fixture")
    lenient = build_workspace(sheet).by_id[SectionId.CONTEXT]
    strict = build_workspace(
        sheet, context_policy=ContextPolicy(strict=True)
    ).by_id[SectionId.CONTEXT]
    assert lenient.summary[0] == ContextState.LIMITED.value
    assert strict.summary[0] == ContextState.INSUFFICIENT.value


def test_an_unevaluated_context_reports_failed_with_a_reason() -> None:
    from fmis.workspace.sections import WorkspaceInputs, context_section

    sheet = multi()
    section = context_section(
        WorkspaceInputs(
            symbol="BTCUSDT", objective="swing_trade", source="fixture", sheet=sheet,
            regimes={v.role: regime_for_sheet(v.sheet) for v in sheet.views},
            primary_role=TimeframeRole.SETUP, conflicts=(), evidence=None,
            context=None, limitations=(),
        )
    )
    assert section.status is SectionStatus.FAILED
    assert section.reason


def test_the_adapter_copies_every_view_count_from_the_sheet() -> None:
    """Survivors 37–39, 41: the adapter's fields were never checked one by one."""
    from fmis.workspace.builder import context_input_from_facts

    sheet = build_multi_timeframe_facts(
        {TimeframeRole.CONTEXT: facts(seed=1, count=40),
         TimeframeRole.SETUP: facts(seed=5, count=260),
         TimeframeRole.EXECUTION: facts(seed=9, count=260)},
        intervals={TimeframeRole.CONTEXT: "1w", TimeframeRole.SETUP: "1d",
                   TimeframeRole.EXECUTION: "4h"}, source="fixture")
    regimes = {v.role: regime_for_sheet(v.sheet) for v in sheet.views}
    subject = context_input_from_facts(
        sheet, regimes, None, primary_role=TimeframeRole.EXECUTION, conflict_count=0)

    assert subject.primary_role == "execution"
    assert subject.primary.role == "execution"
    by_role = {v.role: v for v in subject.views}
    for view in sheet.views:
        adequacy = by_role[view.role.value]
        assert adequacy.warming_up == len(view.sheet.warming_up)
        assert adequacy.level_count == len(view.sheet.structure.levels)
        insufficient = sum(
            1 for d in regimes[view.role].dimensions
            if d.state.value == "insufficient"
        )
        assert adequacy.dimensions_insufficient == insufficient
    # The thin 1w view must actually carry non-trivial counts, or the assertions
    # above would hold on a fixture where every value happened to be zero.
    assert by_role["context"].warming_up > 0
    assert by_role["context"].dimensions_insufficient > 0


def test_the_context_section_status_follows_the_state() -> None:
    """Survivor 42: available only when sufficient, partial otherwise."""
    from fmis.decision_context import ContextState

    for count, expected in ((260, SectionStatus.AVAILABLE), (40, SectionStatus.PARTIAL),
                            (12, SectionStatus.PARTIAL)):
        sheet = build_multi_timeframe_facts(
            {TimeframeRole.SETUP: facts(seed=5, count=count)},
            intervals={TimeframeRole.SETUP: "1d"}, source="fixture")
        section = build_workspace(sheet).by_id[SectionId.CONTEXT]
        assert section.status is expected, (count, section.summary[0])
        assert (section.summary[0] == ContextState.SUFFICIENT.value) is (
            expected is SectionStatus.AVAILABLE
        )
