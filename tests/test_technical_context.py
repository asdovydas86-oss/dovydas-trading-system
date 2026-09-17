"""TA Slice 5A — the recovered technical context, and what it refuses to become.

`fmis.pipeline.technical_context` carries facts that already existed past a seam
that used to drop them (ADR-0032). Its failure modes are therefore not *wrong
numbers* — every number belongs to an engine below — but:

* **losing identity**, so a carried level is equal to but not the level the sheet
  holds, and a later engine reasons about a copy;
* **blending roles**, so the weekly picture and the four-hour one merge;
* **recomputing**, so two derivations of one fact can disagree;
* **interpreting**, so a close beyond a level acquires a meaning nothing in this
  repository has defined.

Every one is asserted directly. Offline, clock-free and network-free.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from fmis.level_crossing import CrossingKind
from fmis.pipeline import technical_context as module
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.pipeline.regime import regime_for_sheet
from fmis.pipeline.technical_context import (
    TECHNICAL_CONTEXT_LIMITATIONS,
    CrossingHistory,
    MarketTechnicalContext,
    TechnicalContextView,
    technical_context_for_sheet,
)

from tests.archive_helpers import multi

ROLES = ("context", "setup", "execution")


def context_of(seeds=(1, 5, 9), symbol: str = "BTCUSDT"):
    """One sheet, its regimes, and the context recovered from both."""
    sheet = multi(seeds=seeds, symbol=symbol)
    regimes = {view.role: regime_for_sheet(view.sheet) for view in sheet.views}
    return sheet, regimes, technical_context_for_sheet(sheet, regimes)


# ---------------------------------------------------------------------------
# Shape: three roles, in the sheet's own order, never blended
# ---------------------------------------------------------------------------


def test_all_three_roles_are_carried_in_the_sheets_own_order() -> None:
    _sheet, _regimes, technical = context_of()

    assert tuple(view.role for view in technical.views) == ROLES
    assert tuple(technical.by_role) == ROLES


def test_each_role_keeps_its_own_interval_and_instant() -> None:
    """The three views are not synchronised and must never be averaged."""
    sheet, _regimes, technical = context_of()

    for view, source in zip(technical.views, sheet.views):
        assert view.interval == source.interval
        assert view.as_of == source.sheet.as_of
        assert view.closed_count == source.sheet.window.closed_count


def test_the_three_roles_carry_genuinely_different_facts() -> None:
    """Guards the guard: a projection that read one view three times would pass
    every field-for-field assertion below while being completely wrong."""
    _sheet, _regimes, technical = context_of()
    levels = {view.role: view.levels for view in technical.views}

    assert levels["context"] != levels["setup"]
    assert levels["setup"] != levels["execution"]


def test_a_role_that_is_absent_from_the_sheet_is_absent_here() -> None:
    _sheet, _regimes, technical = context_of()

    assert technical.view_for("nonexistent") is None
    assert technical.view_for("context") is technical.views[0]


def test_two_views_for_one_role_cannot_be_constructed() -> None:
    _sheet, _regimes, technical = context_of()
    with pytest.raises(ValueError, match="role may appear once"):
        MarketTechnicalContext(
            symbol=technical.symbol,
            source=technical.source,
            newest_as_of=technical.newest_as_of,
            views=(technical.views[0], technical.views[0]),
        )


def test_views_of_two_symbols_cannot_be_one_context() -> None:
    _s1, _r1, one = context_of(symbol="BTCUSDT")
    _s2, _r2, other = context_of(symbol="ETHUSDT")
    with pytest.raises(ValueError, match="must describe"):
        MarketTechnicalContext(
            symbol="BTCUSDT",
            source=one.source,
            newest_as_of=one.newest_as_of,
            views=(one.views[0], other.views[1]),
        )


# ---------------------------------------------------------------------------
# Identity: the objects carried ARE the sheet's objects
# ---------------------------------------------------------------------------


def test_every_carried_collection_is_the_sheets_own_object() -> None:
    """**Identity, not equality.** A copy is somewhere for a fact to drift, and
    a later engine reasoning about a copy is reasoning about a second truth."""
    sheet, _regimes, technical = context_of()

    for view, source in zip(technical.views, sheet.views):
        facts = source.sheet.structure
        assert view.levels is facts.levels, view.role
        assert view.crossings.events is not None
        assert tuple(view.crossings.events) == tuple(facts.crossings)
        assert view.breaks is facts.breaks, view.role
        assert view.changes is facts.changes, view.role
        assert view.features is source.sheet.features, view.role
        assert view.warming_up is source.sheet.warming_up, view.role


def test_every_carried_event_is_the_same_object_the_engine_produced() -> None:
    """Element-level identity, not just tuple equality — the strong form."""
    sheet, _regimes, technical = context_of()

    for view, source in zip(technical.views, sheet.views):
        produced = source.sheet.structure.crossings
        assert len(view.crossings.events) == len(produced)
        for carried, original in zip(view.crossings.events, produced):
            assert carried is original, view.role


def test_the_nearest_levels_are_the_sheets_own_pair() -> None:
    sheet, _regimes, technical = context_of()

    for view, source in zip(technical.views, sheet.views):
        assert view.nearest_above is source.sheet.nearest_levels.above
        assert view.nearest_below is source.sheet.nearest_levels.below
        assert view.upper_level_count == source.sheet.nearest_levels.upper_count
        assert view.lower_level_count == source.sheet.nearest_levels.lower_count


def test_the_regime_carried_is_the_regime_that_was_evaluated() -> None:
    """All three, including the setup and execution ones the seam reduced to a
    single integer before this milestone."""
    _sheet, regimes, technical = context_of()

    for view in technical.views:
        assert view.regime is regimes[TimeframeRole(view.role)]


def test_a_role_with_no_regime_is_refused_rather_than_defaulted() -> None:
    """A silently empty regime reads as *the market has no regime*, which is a
    different statement from *the caller did not evaluate one*."""
    sheet = multi()
    partial = {
        view.role: regime_for_sheet(view.sheet)
        for view in sheet.views
        if view.role is not TimeframeRole.EXECUTION
    }
    with pytest.raises(KeyError):
        technical_context_for_sheet(sheet, partial)


@pytest.mark.parametrize("bad", [None, "sheet", 42])
def test_the_builder_refuses_anything_but_a_multi_timeframe_sheet(bad) -> None:
    with pytest.raises(TypeError):
        technical_context_for_sheet(bad, {})


# ---------------------------------------------------------------------------
# The context-role levels and setup-role breaks — the two that reached nothing
# ---------------------------------------------------------------------------


def test_the_context_role_levels_now_exist_above_the_seam() -> None:
    """Report 0047 §7: context-role levels survived as **nothing**."""
    sheet, _regimes, technical = context_of()
    view = technical.view_for("context")

    assert view.levels is sheet.by_role[TimeframeRole.CONTEXT].sheet.structure.levels
    assert len(view.levels) > 0


def test_the_setup_role_breaks_now_exist_above_the_seam() -> None:
    """Report 0047 §7: only execution breaks were passed."""
    sheet, _regimes, technical = context_of()
    view = technical.view_for("setup")

    assert view.breaks is sheet.by_role[TimeframeRole.SETUP].sheet.structure.breaks


def test_changes_of_character_now_exist_for_every_role() -> None:
    """CHoCH reached the product only as a `TRANSITIONING` regime state."""
    _sheet, _regimes, technical = context_of()

    for view in technical.views:
        assert isinstance(view.changes, tuple)
    assert any(view.changes for view in technical.views), (
        "the fixture should contain at least one change of character; without "
        "one this assertion would pass vacuously"
    )


def test_feature_sets_now_exist_for_every_role() -> None:
    """All three reached no operator surface at all before this milestone.

    The feature set's timeframe is compared against the **sheet's own** interval
    rather than the view's. `TimeframeView.interval` records what the caller
    *requested*, deliberately kept beside what the sheet reports so a provider
    normalising ``"4h"`` to ``"4H"`` would be visible rather than silent; the
    carriage inherits that distinction instead of collapsing it.
    """
    sheet, _regimes, technical = context_of()

    for view, source in zip(technical.views, sheet.views):
        assert view.features.features, view.role
        assert view.features.symbol == view.symbol
        assert view.features.timeframe == source.sheet.interval
        assert view.interval == source.interval


# ---------------------------------------------------------------------------
# The bounded summaries — selections, never derivations
# ---------------------------------------------------------------------------


def test_the_latest_crossing_is_the_last_event_in_the_engines_own_order() -> None:
    _sheet, _regimes, technical = context_of()

    for view in technical.views:
        history = view.crossings
        if not history.events:
            assert history.latest is None
            continue
        assert history.latest is history.events[-1]


def test_the_latest_close_breach_is_the_last_event_of_that_kind() -> None:
    """A filter over a classification the engine already assigned."""
    _sheet, _regimes, technical = context_of()

    for view in technical.views:
        history = view.crossings
        breaches = [
            event
            for event in history.events
            if event.kind is CrossingKind.CLOSE_BREACH
        ]
        if not breaches:
            assert history.latest_close_breach is None
            continue
        assert history.latest_close_breach is breaches[-1]


def test_the_count_is_a_projection_over_the_events_it_counts() -> None:
    _sheet, _regimes, technical = context_of()

    for view in technical.views:
        assert view.crossings.count == len(view.crossings.events)
    assert "count" not in CrossingHistory.__dataclass_fields__


def test_a_summary_naming_an_event_the_history_lacks_is_refused() -> None:
    """A second source of truth, made unrepresentable rather than discouraged."""
    _sheet, _regimes, technical = context_of()
    events = technical.views[0].crossings.events
    with pytest.raises(ValueError, match="not one of the carried events"):
        CrossingHistory(events=events[:2], latest=events[-1])


def test_a_merely_equal_event_is_not_accepted_as_a_summary() -> None:
    """Identity, not equality: two derivations of one event are two objects."""
    _sheet, _regimes, technical = context_of()
    events = technical.views[0].crossings.events
    twin = type(events[-1])(
        level=events[-1].level,
        candle=events[-1].candle,
        index=events[-1].index,
        kind=events[-1].kind,
        mechanism=events[-1].mechanism,
    )
    assert twin == events[-1]
    assert twin is not events[-1]
    with pytest.raises(ValueError):
        CrossingHistory(events=events, latest=twin)


def test_the_latest_break_and_change_are_the_sheets_own_projections() -> None:
    sheet, _regimes, technical = context_of()

    for view, source in zip(technical.views, sheet.views):
        assert view.latest_break is source.sheet.structure.latest_break
        assert view.latest_change is source.sheet.structure.latest_change


# ---------------------------------------------------------------------------
# Purity and the composition-root discipline
# ---------------------------------------------------------------------------


def test_the_module_contains_no_arithmetic_at_all() -> None:
    """The guard `structural_facts` and `multi_timeframe` hold, held here too.

    A projection that started computing would be a second engine hiding inside a
    composition root, which is the one thing ADR-0007 §2 exists to prevent.
    """
    tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
    operators = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(
            node.op,
            (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Pow, ast.Mod),
        )
    ]
    assert operators == [], [ast.unparse(node) for node in operators]


def test_the_module_reads_no_clock() -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    for verb in ("now(", "utcnow(", "today(", "monotonic("):
        assert verb not in source, verb


def test_two_builds_over_one_sheet_are_equal() -> None:
    sheet = multi()
    regimes = {view.role: regime_for_sheet(view.sheet) for view in sheet.views}

    assert technical_context_for_sheet(
        sheet, regimes
    ) == technical_context_for_sheet(sheet, regimes)


def test_the_context_imports_no_layer_above_the_pipeline() -> None:
    """No strategy, no workspace, no dashboard — the DAG points one way."""
    tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    for forbidden in (
        "fmis.swing_setup",
        "fmis.swing_workspace",
        "fmis.operator_dashboard",
        "fmis.today",
        "fmis.setup_evidence",
        "fmis.scan_memory",
        "fmis.risk_policy",
    ):
        assert not any(name.startswith(forbidden) for name in imported), forbidden


# ---------------------------------------------------------------------------
# Carriage is not interpretation
# ---------------------------------------------------------------------------


_FORBIDDEN_VOCABULARY = (
    "support",
    "resistance",
    "breakout",
    "retest",
    "reclaim",
    "rejection",
    "acceptance",
    "fakeout",
    "bullish",
    "bearish",
    "score",
    "confidence",
    "probability",
    "recommend",
    "opportunity",
    "watch_long",
    "watch_short",
)


@pytest.mark.parametrize("word", _FORBIDDEN_VOCABULARY)
def test_no_identifier_in_the_module_names_an_undefined_concept(word: str) -> None:
    """Prose may *deny* these; an identifier or a field would **assert** one.

    The module's own docstring explains what it refuses to become, so the scan
    is over identifiers and emitted string values rather than over raw text.
    """
    tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
    }
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assert word not in node.name.lower(), node.name
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assert word not in node.target.id.lower(), node.target.id
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value not in docstrings
        ):
            # The limitation register names these words to deny them, exactly as
            # `fmis.pipeline.render`'s disclaimer does. Denials are asserted
            # separately below, so deleting one fails a test.
            text = node.value.lower()
            for denial in _DENIALS:
                text = text.replace(denial.lower(), "")
            assert not re.search(rf"\b{word}\w*\b", text), node.value


#: The sentences that use a refused word precisely to refuse it.
_DENIALS = (
    "Neither is support or resistance",
    "None of them is a breakout, a reversal, a signal or a reason to trade",
)


def test_the_denials_the_scan_exempts_actually_exist() -> None:
    """Or the exemption above is a hole rather than a carve-out."""
    text = " ".join(item[1] for item in TECHNICAL_CONTEXT_LIMITATIONS)
    for denial in _DENIALS:
        assert denial in text, denial


def test_the_limitations_are_carried_on_every_context() -> None:
    _sheet, _regimes, technical = context_of()

    assert technical.limitations == TECHNICAL_CONTEXT_LIMITATIONS
    assert len(TECHNICAL_CONTEXT_LIMITATIONS) >= 5


def test_the_view_holds_no_field_that_could_carry_a_verdict() -> None:
    """No direction, no side, no lean, no state beyond what an engine named."""
    fields = set(TechnicalContextView.__dataclass_fields__)
    for forbidden in (
        "direction",
        "lean",
        "bias",
        "score",
        "rank",
        "opportunity",
        "confidence",
        "signal",
    ):
        assert forbidden not in fields, forbidden


# ---------------------------------------------------------------------------
# Symmetry
# ---------------------------------------------------------------------------


def test_the_upper_and_lower_sides_are_treated_identically() -> None:
    """No field, count or selection favours one side of the market.

    Asserted structurally: every field naming one side has an exact mirror
    naming the other, so an asymmetry would have to be introduced by adding a
    field with no partner.
    """
    fields = set(TechnicalContextView.__dataclass_fields__)
    mirrors = (
        ("nearest_above", "nearest_below"),
        ("upper_level_count", "lower_level_count"),
    )
    for one, other in mirrors:
        assert one in fields and other in fields, (one, other)

    unpaired = {
        name
        for name in fields
        if any(word in name for word in ("above", "below", "upper", "lower"))
    }
    assert unpaired == {name for pair in mirrors for name in pair}


def test_a_mirrored_market_produces_a_mirrored_shape() -> None:
    """Two different markets give two different contexts with the same shape.

    The engines below are already tested for directional symmetry; what is
    asserted here is that the carriage adds none — every role, every collection
    and every summary is present for both, and neither is richer than the other.
    """
    _s1, _r1, one = context_of(seeds=(1, 5, 9))
    _s2, _r2, other = context_of(seeds=(3, 4, 7))

    assert one != other
    assert [view.role for view in one.views] == [view.role for view in other.views]

    for left, right in zip(one.views, other.views):
        # The same facts are present for both markets. Neither run gets a field
        # the other does not, and no collection is populated for one side of the
        # market and left empty for the other by the carriage.
        assert (left.levels == ()) == (right.levels == ()), left.role
        assert (left.crossings.events == ()) == (right.crossings.events == ())
        assert (left.nearest_above is None) == (right.nearest_above is None)
        assert (left.nearest_below is None) == (right.nearest_below is None)
        # Both sides of every mirrored count are populated, for both markets.
        for view in (left, right):
            assert view.upper_level_count > 0, view.role
            assert view.lower_level_count > 0, view.role
