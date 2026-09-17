"""TA Slice 5A — the seam matrix: does a recovered fact actually survive?

`fmis.pipeline.technical_context` builds the context correctly; that is
`test_technical_context.py`'s subject. This file asks the only question that
matters to the product: **does what it built reach the operator intact**, across
four layers that each rebuild their own view of a symbol?

    run_setup_for_symbols  ──►  SetupRunResult.technical
                           ──►  SymbolDecision.technical
                           ──►  SymbolDecisionRow.technical
                           ──►  the rendered page

**A count is not a proof.** `len(crossings) == 412` on both sides of a seam is
satisfied by a layer that carried the wrong four hundred and twelve events. So
every assertion here compares **event identity, classification, timing and the
level referenced**, and the collections are compared element by element rather
than by size.

Offline, clock-free and network-free: the sheet is a fixture and the scan is
never run against a provider.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.operator_dashboard.models import (
    CrossingEventRow,
    FeatureReadingRow,
    StructuralLevelRow,
    StructureEventRow,
)
from fmis.operator_dashboard.sections import symbol_decision_rows
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.pipeline.regime import regime_for_sheet
from fmis.pipeline.technical_context import technical_context_for_sheet
from fmis.swing_setup.compose import (
    SetupRunResult,
    setup_analysis_for_symbol,
    setup_composition_for_sheet,
    setup_readings_for,
)
from fmis.swing_workspace.sections import symbol_decisions

from tests.archive_helpers import multi

ROLES = ("context", "setup", "execution")
REFERENCE = datetime(2026, 2, 14, tzinfo=timezone.utc)


def _result(seeds=(1, 5, 9), symbol: str = "BTCUSDT") -> tuple:
    """One symbol carried the whole way, exactly as the live path carries it."""
    sheet = multi(seeds=seeds, symbol=symbol)
    inputs, technical, assessment = setup_composition_for_sheet(sheet)
    result = SetupRunResult(
        requested_symbol=symbol,
        assessment=assessment,
        readings=setup_readings_for(sheet, inputs),
        technical=technical,
    )
    return sheet, result


def _decision(seeds=(1, 5, 9), symbol: str = "BTCUSDT"):
    sheet, result = _result(seeds, symbol)
    return sheet, symbol_decisions([result], reference_time=REFERENCE)[0]


def _row(seeds=(1, 5, 9), symbol: str = "BTCUSDT"):
    sheet, decision = _decision(seeds, symbol)
    return sheet, symbol_decision_rows([decision])[0]


# ---------------------------------------------------------------------------
# The composition produces it at all
# ---------------------------------------------------------------------------


def test_the_composition_returns_the_context_beside_the_assessment() -> None:
    sheet = multi()
    inputs, technical, assessment = setup_composition_for_sheet(sheet)

    assert technical.symbol == assessment.symbol == sheet.symbol
    assert tuple(view.role for view in technical.views) == ROLES
    assert inputs.symbol == sheet.symbol


def test_the_wrapper_entry_points_keep_their_exact_results() -> None:
    """Additive means additive: the three older signatures are unchanged."""
    from fmis.swing_setup.compose import (
        setup_assessment_for_sheet,
        setup_inputs_and_assessment_for_sheet,
    )

    sheet = multi()
    inputs, technical, assessment = setup_composition_for_sheet(sheet)
    wrapped_inputs, wrapped_assessment = setup_inputs_and_assessment_for_sheet(sheet)

    assert wrapped_inputs == inputs
    assert wrapped_assessment == assessment
    assert setup_assessment_for_sheet(sheet) == assessment
    assert technical is not None


def test_the_context_is_composed_from_the_regimes_the_policy_already_used() -> None:
    """One regime evaluation per role, not two — no second derivation exists."""
    sheet = multi()
    _inputs, technical, _assessment = setup_composition_for_sheet(sheet)
    independently = {view.role: regime_for_sheet(view.sheet) for view in sheet.views}

    for view in technical.views:
        assert view.regime == independently[TimeframeRole(view.role)]


# ---------------------------------------------------------------------------
# SetupRunResult
# ---------------------------------------------------------------------------


def test_a_failed_symbol_carries_no_context_and_cannot_be_given_one() -> None:
    """An unreadable symbol composed nothing; a context for it would be invented."""
    failed = SetupRunResult(requested_symbol="ZZZUSDT", failure="BinanceError: down")
    assert failed.technical is None

    _sheet, result = _result()
    with pytest.raises(ValueError, match="without an assessment"):
        SetupRunResult(
            requested_symbol="ZZZUSDT",
            failure="BinanceError: down",
            technical=result.technical,
        )


def test_a_result_cannot_describe_two_markets() -> None:
    _sheet, one = _result(symbol="BTCUSDT")
    _sheet2, other = _result(symbol="ETHUSDT")
    with pytest.raises(ValueError, match="cannot be about two markets"):
        SetupRunResult(
            requested_symbol="BTCUSDT",
            assessment=one.assessment,
            technical=other.technical,
        )


def test_a_result_built_without_a_context_is_still_valid() -> None:
    """Every hand-built result predating this field stays constructible."""
    _sheet, result = _result()
    older = SetupRunResult(
        requested_symbol=result.requested_symbol, assessment=result.assessment
    )
    assert older.technical is None


@pytest.mark.parametrize("bad", ["context", 7, object()])
def test_a_result_refuses_a_context_that_is_not_one(bad) -> None:
    _sheet, result = _result()
    with pytest.raises(TypeError, match="MarketTechnicalContext"):
        SetupRunResult(
            requested_symbol=result.requested_symbol,
            assessment=result.assessment,
            technical=bad,
        )


# ---------------------------------------------------------------------------
# SymbolDecision — the workspace seam
# ---------------------------------------------------------------------------


def test_the_decision_carries_the_very_object_the_composition_produced() -> None:
    """By reference. A copy here would be a second source of truth per symbol."""
    _sheet, result = _result()
    decision = symbol_decisions([result], reference_time=REFERENCE)[0]

    assert decision.technical is result.technical


def test_a_decision_from_a_result_without_a_context_states_the_absence() -> None:
    _sheet, result = _result()
    older = SetupRunResult(
        requested_symbol=result.requested_symbol, assessment=result.assessment
    )
    decision = symbol_decisions([older], reference_time=REFERENCE)[0]

    assert decision.technical is None


# ---------------------------------------------------------------------------
# SymbolDecisionRow — the dashboard seam, fact by fact
# ---------------------------------------------------------------------------


def test_all_three_roles_reach_the_dashboard_row() -> None:
    _sheet, row = _row()

    assert tuple(item.role for item in row.technical) == ROLES


def test_the_roles_cannot_be_swapped_on_the_way() -> None:
    """Each row's facts belong to its own role, checked against the sheet.

    The roles are built from different seeds in this fixture, so a transposition
    would change every value rather than none of them.
    """
    sheet, row = _row()

    for item, source in zip(row.technical, sheet.views):
        assert item.role == source.role.value
        assert item.interval == source.interval
        assert item.as_of == source.sheet.as_of
        assert item.structural_trend == source.sheet.structure.trend.value
        assert item.closed_count == source.sheet.window.closed_count
        assert item.last_close == source.sheet.window.last_close


def test_each_roles_regime_reaches_the_row_in_all_three_dimensions() -> None:
    """Setup and execution regimes survived as one integer before this milestone."""
    sheet, row = _row()
    regimes = {
        view.role.value: regime_for_sheet(view.sheet) for view in sheet.views
    }

    for item in row.technical:
        regime = regimes[item.role]
        states = {
            dimension.name.value: dimension.state.value
            for dimension in regime.dimensions
        }
        assert item.regime_structure == states["structure"]
        assert item.regime_volatility == states["volatility"]
        assert item.regime_participation == states["participation"]


def test_the_level_counts_reach_the_row_for_every_role() -> None:
    sheet, row = _row()

    for item, source in zip(row.technical, sheet.views):
        assert item.level_count == len(source.sheet.structure.levels)
        assert item.upper_level_count == source.sheet.nearest_levels.upper_count
        assert item.lower_level_count == source.sheet.nearest_levels.lower_count


def test_the_nearest_levels_reach_the_row_without_changing_identity() -> None:
    """Price, side and the swing the level came from — not just a number."""
    sheet, row = _row()

    for item, source in zip(row.technical, sheet.views):
        for carried, original in (
            (item.nearest_above, source.sheet.nearest_levels.above),
            (item.nearest_below, source.sheet.nearest_levels.below),
        ):
            if original is None:
                assert carried is None, item.role
                continue
            assert carried.price == original.price
            assert carried.side == original.side.value
            assert carried.origin_label == original.origin.label.value
            assert carried.origin_timestamp == original.origin.timestamp
            assert carried.origin_index == original.origin.index


def test_the_crossing_classification_reaches_the_row_intact() -> None:
    """**Not a count.** The kind, the mechanism, the bar, the instant and the
    level the event references, for both selections, on every role."""
    sheet, row = _row()

    for item, source in zip(row.technical, sheet.views):
        produced = source.sheet.structure.crossings
        assert item.crossing_count == len(produced)
        assert produced, item.role

        latest = produced[-1]
        assert item.latest_crossing.kind == latest.kind.value
        assert item.latest_crossing.mechanism == latest.mechanism.value
        assert item.latest_crossing.side == latest.level.side.value
        assert item.latest_crossing.level_price == latest.level.price
        assert item.latest_crossing.as_of == latest.timestamp
        assert item.latest_crossing.index == latest.index

        breaches = [
            event for event in produced if event.kind.value == "close_breach"
        ]
        if not breaches:
            assert item.latest_close_breach is None
            continue
        assert item.latest_close_breach.as_of == breaches[-1].timestamp
        assert item.latest_close_breach.index == breaches[-1].index
        assert item.latest_close_breach.level_price == breaches[-1].level.price


def test_the_breaks_reach_the_row_for_every_role_including_setup() -> None:
    """Only execution breaks crossed the seam before this milestone."""
    sheet, row = _row()

    for item, source in zip(row.technical, sheet.views):
        produced = source.sheet.structure.breaks
        assert item.break_count == len(produced)
        if not produced:
            assert item.latest_break is None
            continue
        assert item.latest_break.index == produced[-1].index
        assert item.latest_break.as_of == produced[-1].timestamp
        assert item.latest_break.side == produced[-1].side.value
        assert item.latest_break.level_price == produced[-1].level.price
        assert item.latest_break.origin_label == produced[-1].label.value


def test_a_change_of_character_reaches_the_row_with_the_break_it_changed_from() -> None:
    """CHoCH reached the product as a regime state and nothing else before 5A."""
    sheet, row = _row()
    seen = 0

    for item, source in zip(row.technical, sheet.views):
        produced = source.sheet.structure.changes
        assert item.character_change_count == len(produced)
        if not produced:
            assert item.latest_character_change is None
            continue
        seen += 1
        change = produced[-1]
        carried = item.latest_character_change
        assert carried.index == change.subject.index
        assert carried.as_of == change.subject.timestamp
        assert carried.side == change.subject.side.value
        assert carried.level_price == change.subject.level.price
        assert carried.previous_side == change.previous.side.value
        assert carried.previous_as_of == change.previous.timestamp
        assert carried.previous_side != carried.side

    assert seen, "the fixture must contain a change of character somewhere"


def test_every_feature_reading_reaches_the_row_for_every_role() -> None:
    """All three feature sets reached **no** operator surface before this milestone."""
    sheet, row = _row()

    for item, source in zip(row.technical, sheet.views):
        produced = source.sheet.features.features
        assert [reading.name for reading in item.features] == list(produced)
        for reading in item.features:
            result = produced[reading.name]
            if result.value is None:
                assert not reading.available, reading.name
                continue
            assert reading.available, reading.name
            if reading.components:
                assert dict(reading.components) == dict(result.value)
            else:
                assert reading.value == result.value


def test_a_structured_reading_keeps_all_of_its_components() -> None:
    _sheet, row = _row()
    structured = [
        reading
        for item in row.technical
        for reading in item.features
        if reading.components
    ]

    assert structured, "the default feature set includes a structured reading"
    for reading in structured:
        assert len(reading.components) == 3
        assert reading.value is None


def test_the_warm_up_list_reaches_the_row_and_stays_explicit() -> None:
    """Unavailable must stay unavailable, never be replaced with a default."""
    sheet, row = _row()

    for item, source in zip(row.technical, sheet.views):
        assert item.warming_up == source.sheet.warming_up
        for name in item.warming_up:
            reading = next(item_ for item_ in item.features if item_.name == name)
            assert not reading.available
            assert reading.value is None
            assert reading.unavailable_reason is not None


def test_a_warming_up_reading_is_carried_as_an_absence_with_its_reason() -> None:
    """Built from a deliberately short view so the warm-up case is real."""
    from tests.archive_helpers import facts
    from fmis.pipeline.multi_timeframe import build_multi_timeframe_facts

    sheet = build_multi_timeframe_facts(
        {
            TimeframeRole.CONTEXT: facts(seed=1, count=60),
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
    inputs, technical, assessment = setup_composition_for_sheet(sheet)
    result = SetupRunResult(
        requested_symbol=sheet.symbol,
        assessment=assessment,
        readings=setup_readings_for(sheet, inputs),
        technical=technical,
    )
    row = symbol_decision_rows(
        symbol_decisions([result], reference_time=REFERENCE)
    )[0]
    short = row.technical[0]

    assert short.warming_up, "a 60-bar view cannot have warmed up EMA(200)"
    unavailable = [
        reading for reading in short.features if not reading.available
    ]
    assert unavailable
    for reading in unavailable:
        assert reading.value is None
        assert reading.components == ()
        assert reading.unavailable_reason == "insufficient_data"


def test_a_row_from_a_decision_without_a_context_is_empty_not_invented() -> None:
    _sheet, result = _result()
    older = SetupRunResult(
        requested_symbol=result.requested_symbol, assessment=result.assessment
    )
    row = symbol_decision_rows(
        symbol_decisions([older], reference_time=REFERENCE)
    )[0]

    assert row.technical == ()


# ---------------------------------------------------------------------------
# No recomputation anywhere above the projection
# ---------------------------------------------------------------------------


def test_the_renderer_needs_no_recomputation_to_show_any_of_it() -> None:
    """Every field the page prints is already on the row, as a primitive.

    Stated as an assertion rather than a claim: if a renderer had to reach back
    into an engine object to display something, that object would be on the row,
    and this scan would find it.
    """
    _sheet, row = _row()
    primitive = (str, int, float, bool, datetime)
    nested = (StructuralLevelRow, CrossingEventRow, StructureEventRow)

    def check(record: object, label: str) -> None:
        for name in type(record).__dataclass_fields__:
            value = getattr(record, name)
            if value is None or isinstance(value, primitive):
                continue
            if isinstance(value, nested):
                check(value, f"{label}.{name}")
                continue
            if isinstance(value, tuple):
                for position, element in enumerate(value):
                    if isinstance(element, (FeatureReadingRow, *nested)):
                        check(element, f"{label}.{name}[{position}]")
                    elif not isinstance(element, (*primitive, tuple)):
                        raise AssertionError(
                            f"{label}.{name}[{position}] is an engine object: "
                            f"{type(element).__name__}"
                        )
                continue
            raise AssertionError(
                f"{label}.{name} is an engine object: {type(value).__name__}"
            )

    for item in row.technical:
        check(item, item.role)


def test_the_dashboard_layer_makes_no_selection_of_its_own() -> None:
    """The bounded summaries came from `fmis.pipeline`, not from the translator.

    Checked by comparing the row's selections against the projection's, which is
    the only way a second selection rule would be visible.
    """
    sheet, result = _result()
    regimes = {view.role: regime_for_sheet(view.sheet) for view in sheet.views}
    projected = technical_context_for_sheet(sheet, regimes)
    row = symbol_decision_rows(
        symbol_decisions([result], reference_time=REFERENCE)
    )[0]

    for item, view in zip(row.technical, projected.views):
        assert item.latest_crossing.index == view.crossings.latest.index
        if view.crossings.latest_close_breach is None:
            assert item.latest_close_breach is None
        else:
            assert (
                item.latest_close_breach.index
                == view.crossings.latest_close_breach.index
            )


# ---------------------------------------------------------------------------
# The live entry point
# ---------------------------------------------------------------------------


def test_the_symbol_entry_point_returns_all_four_artifacts(monkeypatch) -> None:
    """`setup_analysis_for_symbol` is what the scan runs through.

    The fetch is replaced with the fixture sheet, so this exercises the
    composition and the carriage without a provider.
    """
    sheet = multi()
    monkeypatch.setattr(
        "fmis.swing_setup.compose.multi_timeframe_facts_for_symbol",
        lambda *args, **kwargs: sheet,
    )

    returned, readings, technical, assessment = setup_analysis_for_symbol("BTCUSDT")

    assert returned is sheet
    assert technical.symbol == assessment.symbol
    assert tuple(view.role for view in technical.views) == ROLES
    assert len(readings.timeframes) == 3


def test_the_scan_attaches_a_context_to_every_readable_symbol(monkeypatch) -> None:
    from fmis.swing_setup.compose import run_setup_for_symbols

    sheets = {"BTCUSDT": multi(symbol="BTCUSDT"), "ETHUSDT": multi(symbol="ETHUSDT")}
    monkeypatch.setattr(
        "fmis.swing_setup.compose.multi_timeframe_facts_for_symbol",
        lambda symbol, **kwargs: sheets[symbol],
    )

    results = run_setup_for_symbols(["BTCUSDT", "ETHUSDT"])

    assert len(results) == 2
    for result in results:
        assert result.technical is not None
        assert result.technical.symbol == result.requested_symbol
