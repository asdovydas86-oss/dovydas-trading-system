"""TA Slice 5A — the recovered technical context reaches Scan Memory **not at all**.

Slice 3's comparison dimensions are deliberately few, and the reason is stated on
`ChangeDimension` itself: a dimension that advances because time advanced turns
*what changed* into noise, and noise on that surface is worse than silence.

The technical context is the largest thing that has ever been carried onto a
`SymbolDecision`, and almost every value on it moves on **every refresh** — an
EMA value, a crossing count, a nearest level, a last close. If any of it leaked
into the comparison, the owner's *what changed since the previous scan* panel
would report twenty symbols changed, every time, forever, and the one symbol that
genuinely moved would be invisible in it.

So this file asserts the leak is absent in three independent ways: the projected
state is byte-identical with and without a context; the record's digest is
unchanged; and existing scan history stays readable.

Offline, clock-free and filesystem-free. **`~/.fmits/scan_memory` is never
touched** — every store used here is a `tmp_path`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.scan_memory import CHANGE_DIMENSIONS, symbol_state_of
from fmis.scan_memory.comparison import dimension_values, transitions_between
from fmis.swing_setup.compose import (
    SetupRunResult,
    setup_composition_for_sheet,
    setup_readings_for,
)
from fmis.swing_workspace.sections import symbol_decisions

from tests.archive_helpers import multi

REFERENCE = datetime(2026, 2, 14, tzinfo=timezone.utc)


def _decisions(seeds=(1, 5, 9), symbol: str = "BTCUSDT"):
    """One decision with the recovered context, and the same one without it."""
    sheet = multi(seeds=seeds, symbol=symbol)
    inputs, technical, assessment = setup_composition_for_sheet(sheet)
    readings = setup_readings_for(sheet, inputs)
    with_context = SetupRunResult(
        requested_symbol=symbol,
        assessment=assessment,
        readings=readings,
        technical=technical,
    )
    without = SetupRunResult(
        requested_symbol=symbol, assessment=assessment, readings=readings
    )
    return (
        symbol_decisions([with_context], reference_time=REFERENCE)[0],
        symbol_decisions([without], reference_time=REFERENCE)[0],
    )


def test_the_projected_state_is_identical_with_and_without_a_context() -> None:
    """**The assertion that matters.** Equal states, field for field."""
    carried, bare = _decisions()

    assert carried.technical is not None
    assert bare.technical is None
    assert symbol_state_of(carried) == symbol_state_of(bare)


def test_the_compared_dimensions_are_identical_with_and_without_a_context() -> None:
    carried, bare = _decisions()

    assert dimension_values(symbol_state_of(carried)) == dimension_values(
        symbol_state_of(bare)
    )


def test_two_scans_differing_only_in_the_context_report_no_change() -> None:
    """The failure this file exists to prevent, stated as the operator sees it."""
    carried, bare = _decisions()

    assert transitions_between(symbol_state_of(bare), symbol_state_of(carried)) == ()
    assert transitions_between(symbol_state_of(carried), symbol_state_of(bare)) == ()


def test_the_comparison_surface_did_not_grow() -> None:
    """Twelve dimensions, and the recovered context added none of them."""
    names = {dimension.value for dimension in CHANGE_DIMENSIONS}

    assert names == {
        "presence",
        "decision",
        "policy_direction",
        "decision_context",
        "developing_evidence",
        "blocker",
        "context_structure",
        "setup_structure",
        "execution_structure",
        "evidence_independence",
        "evidence_availability",
        "evidence_composition",
    }
    for forbidden in (
        "levels",
        "crossings",
        "features",
        "regime",
        "character",
        "technical",
        "nearest",
    ):
        assert not any(forbidden in name for name in names), forbidden


def test_the_persisted_state_holds_no_field_from_the_recovered_context() -> None:
    """A field is how a dimension arrives; the record has none to arrive in."""
    from fmis.scan_memory.models import SymbolState

    fields = set(SymbolState.__dataclass_fields__)
    for forbidden in (
        "technical",
        "levels",
        "crossings",
        "features",
        "regime",
        "nearest_above",
        "nearest_below",
        "character",
    ):
        assert forbidden not in fields, forbidden


def test_the_projection_never_reads_the_context_at_all() -> None:
    """Source-level, so a future edit has to be deliberate rather than accidental."""
    import ast
    import inspect
    from pathlib import Path

    from fmis.scan_memory import projection

    source = Path(inspect.getfile(projection)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert "technical" not in attributes


def test_a_record_written_before_this_milestone_is_still_readable(tmp_path) -> None:
    """Existing history must survive the model change, not merely be ignored.

    An isolated store under ``tmp_path`` — the owner's `~/.fmits/scan_memory` is
    never opened, written or reset by this suite.
    """
    from fmis.scan_memory import scan_record_from

    from tests.scan_memory_helpers import store_at
    from fmis.pipeline.multi_timeframe import DEFAULT_TIMEFRAMES

    from tests.swing_workspace_helpers import assessment, result, workspace_of

    # A workspace whose results predate the field entirely: hand-built
    # `SetupRunResult`s with no `technical`, exactly as every record written
    # before this milestone was projected from.
    legacy = workspace_of(result(assessment()))
    record = scan_record_from(
        legacy,
        recorded_at=REFERENCE,
        universe=("BTCUSDT",),
        timeframes=DEFAULT_TIMEFRAMES,
    )

    store = store_at(tmp_path)
    store.append(record)
    read_back = store.records()

    assert len(read_back) == 1
    assert read_back[0].record == record
    assert read_back[0].record.symbols[0].symbol == "BTCUSDT"


def test_a_record_written_now_is_readable_by_the_same_codec(tmp_path) -> None:
    """Forward compatibility of the same schema, on a context-bearing workspace."""
    from fmis.scan_memory import scan_record_from

    from tests.scan_memory_helpers import store_at
    from fmis.pipeline.multi_timeframe import DEFAULT_TIMEFRAMES
    from tests.swing_workspace_helpers import reading, run_of
    from fmis.swing_workspace import build_swing_workspace

    sheet = multi()
    inputs, technical, assessment_now = setup_composition_for_sheet(sheet)
    carried = SetupRunResult(
        requested_symbol=sheet.symbol,
        assessment=assessment_now,
        readings=setup_readings_for(sheet, inputs),
        technical=technical,
    )
    workspace = build_swing_workspace(run_of(carried, store=reading()))
    record = scan_record_from(
        workspace,
        recorded_at=REFERENCE,
        universe=(sheet.symbol,),
        timeframes=DEFAULT_TIMEFRAMES,
    )

    store = store_at(tmp_path)
    store.append(record)

    assert store.records()[0].record == record


def test_the_record_digest_does_not_move_because_a_context_exists(tmp_path) -> None:
    """The strongest form: the persisted bytes are the same either way."""
    from fmis.pipeline.multi_timeframe import DEFAULT_TIMEFRAMES
    from fmis.scan_memory import scan_record_from
    from fmis.swing_workspace import build_swing_workspace
    from tests.swing_workspace_helpers import reading, run_of

    sheet = multi()
    inputs, technical, assessment_now = setup_composition_for_sheet(sheet)
    readings = setup_readings_for(sheet, inputs)
    store_reading = reading()

    def record_for(result: SetupRunResult):
        return scan_record_from(
            build_swing_workspace(run_of(result, store=store_reading)),
            recorded_at=REFERENCE,
            universe=(sheet.symbol,),
            timeframes=DEFAULT_TIMEFRAMES,
        )

    carried = record_for(
        SetupRunResult(
            requested_symbol=sheet.symbol,
            assessment=assessment_now,
            readings=readings,
            technical=technical,
        )
    )
    bare = record_for(
        SetupRunResult(
            requested_symbol=sheet.symbol,
            assessment=assessment_now,
            readings=readings,
        )
    )

    assert carried == bare


# ---------------------------------------------------------------------------
# TA Slice 5B — the price zones ride inside the context and reach no further
# ---------------------------------------------------------------------------


def test_a_decision_carrying_zones_projects_the_same_state_as_one_without_them() -> None:
    """The zones are the largest thing the context has ever carried.

    `PriceZoneSet` holds every band a role produced and every level inside each
    one, and almost all of it moves on every refresh — a new level joins, a new
    band opens, the last close moves relative to all of them. If any of it
    reached a comparison dimension, *what changed since the previous scan* would
    report every symbol changed, every time, forever.

    The whole-context tests above already cover this, because the zones ride
    inside the context. This one names the zones specifically, so a future
    milestone that carried them by some other route fails here rather than
    silently.
    """
    import dataclasses

    sheet = multi()
    inputs, technical, assessment = setup_composition_for_sheet(sheet)
    readings = setup_readings_for(sheet, inputs)

    assert all(view.zones is not None for view in technical.views)
    assert any(view.zones.zone_count > 0 for view in technical.views)

    without_zones = dataclasses.replace(
        technical,
        views=tuple(
            dataclasses.replace(view, zones=None) for view in technical.views
        ),
    )

    def decision_for(context):
        return symbol_decisions(
            [
                SetupRunResult(
                    requested_symbol=sheet.symbol,
                    assessment=assessment,
                    readings=readings,
                    technical=context,
                )
            ],
            reference_time=REFERENCE,
        )[0]

    with_zones = symbol_state_of(decision_for(technical))
    no_zones = symbol_state_of(decision_for(without_zones))

    assert with_zones == no_zones
    assert dimension_values(with_zones) == dimension_values(no_zones)


def test_no_comparison_dimension_names_a_zone() -> None:
    """Asserted on the vocabulary itself, not on one fixture's values."""
    for dimension in CHANGE_DIMENSIONS:
        assert "zone" not in dimension.value.lower()
        assert "zone" not in dimension.name.lower()
