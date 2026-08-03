"""Milestone AH — the confirmation delay travels with the origin that earned it.

ADR-0020 deferred question **D1** said the confirmation delay was carried on no
derived fact. `derive_structure_breaks` demanded it as a keyword argument, and a
caller who supplied a value that disagreed with the ``right_bars`` used for
detection silently changed which level was the reference at every bar — and so
which breaks and which changes of character existed — **while raising no error**.

This suite pins the fix (ADR-0024): detection stamps its window onto every
`SwingPoint`, `structural_levels` copies it onto every `LevelOrigin`, and the
break layer reads it off the level. The mismatch is not detected — it is
**unrepresentable**.

The load-bearing test here is `test_the_new_derivation_equals_the_old_one_...`:
it reimplements the pre-AH algorithm and proves the two agree exactly wherever
the old caller passed a matching delay. Removing a hazard is only worth anything
if it left correct behaviour alone.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import pathlib
import pickle
import random
import subprocess
import sys
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from fmis.data import Candle, CandleSeries
from fmis.level_crossing import (
    LevelOrigin,
    LevelSide,
    PriceLevel,
    derive_level_crossings,
    structural_levels,
)
from fmis.market_structure import (
    StructuralSwingLabel,
    SwingPoint,
    SwingType,
    compare_swing_sequence,
    detect_swings,
    label_swing_sequence,
)
from fmis.pipeline.multi_timeframe import TimeframeRole, build_multi_timeframe_facts
from fmis.pipeline.structural_facts import (
    LIMITATIONS,
    DetectionSettings,
    build_structural_facts,
)
from fmis.structure_break import (
    StructureBreak,
    StructureBreakInputError,
    derive_structure_breaks,
)
from fmis.change_of_character import derive_changes_of_character

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)

#: The window the hand-built fixtures in this file are confirmed under.
CB = 2


# ============================ fixtures =======================================


def candle(index: int, o: float, h: float, low: float, c: float) -> Candle:
    return Candle(
        timestamp=_BASE + timedelta(hours=4 * index),
        symbol="BTCUSDT",
        timeframe="4h",
        open=float(o),
        high=float(h),
        low=float(low),
        close=float(c),
        volume=1.0,
        is_closed=True,
    )


def series(rows: list[tuple[float, float, float, float]]) -> CandleSeries:
    return CandleSeries(
        symbol="BTCUSDT",
        timeframe="4h",
        candles=tuple(candle(i, *row) for i, row in enumerate(rows)),
    )


def seeded_rows(count: int, seed: int) -> list[tuple[float, float, float, float]]:
    """Deterministic OHLC. Seeded in a **test** only; production has no randomness."""
    rng = random.Random(seed)
    rows: list[tuple[float, float, float, float]] = []
    for _ in range(count):
        open_ = rng.uniform(95.0, 105.0)
        close = rng.uniform(95.0, 105.0)
        rows.append(
            (
                open_,
                max(open_, close) + rng.uniform(0.0, 3.0),
                min(open_, close) - rng.uniform(0.0, 3.0),
                close,
            )
        )
    return rows


def chain(rows: list, right_bars: int = CB, left_bars: int = 2):
    """candles -> swings -> levels -> crossings, at one detection window."""
    candles = series(rows)
    swings = detect_swings(candles, left_bars=left_bars, right_bars=right_bars)
    labelled = label_swing_sequence(compare_swing_sequence(swings))
    levels = structural_levels(labelled)
    return levels, derive_level_crossings(candles, list(levels))


def origin(
    index: int,
    label: StructuralSwingLabel = StructuralSwingLabel.HIGHER_HIGH,
    confirmation_bars: int = CB,
) -> LevelOrigin:
    return LevelOrigin(
        index=index,
        timestamp=_BASE + timedelta(hours=4 * index),
        label=label,
        confirmation_bars=confirmation_bars,
    )


def level(
    price: float,
    side: LevelSide = LevelSide.UPPER,
    origin_index: int = 5,
    confirmation_bars: int = CB,
) -> PriceLevel:
    label = (
        StructuralSwingLabel.HIGHER_HIGH
        if side is LevelSide.UPPER
        else StructuralSwingLabel.LOWER_LOW
    )
    return PriceLevel(
        price=price,
        side=side,
        origin=origin(origin_index, label, confirmation_bars),
    )


# ============ 1. the origin carries the delay that earned it =================


def test_detection_stamps_its_own_window_on_every_point() -> None:
    for right_bars in (1, 2, 3, 5):
        swings = detect_swings(
            series(seeded_rows(80, 11)), left_bars=2, right_bars=right_bars
        )
        assert swings
        for point in swings:
            assert point.confirmation_bars == right_bars


def test_the_window_survives_the_whole_chain_to_the_level() -> None:
    """swing -> comparison -> label -> level, with the number copied at each step."""
    for right_bars in (1, 2, 4):
        levels, _ = chain(seeded_rows(90, 12), right_bars=right_bars)
        assert levels
        for lvl in levels:
            assert lvl.origin is not None
            assert lvl.origin.confirmation_bars == right_bars


def test_knowable_from_is_the_pivot_plus_the_window() -> None:
    for bars in (1, 2, 7):
        point = SwingPoint(
            index=9,
            timestamp=_BASE,
            price=100.0,
            type=SwingType.HIGH,
            confirmation_bars=bars,
        )
        assert point.knowable_from == 9 + bars
        assert origin(9, confirmation_bars=bars).knowable_from == 9 + bars


def test_knowable_from_is_a_projection_not_a_field() -> None:
    """ADR-0016 §4: a stored copy one attribute away is somewhere to drift."""
    assert "knowable_from" not in SwingPoint.__dataclass_fields__
    assert "knowable_from" not in LevelOrigin.__dataclass_fields__
    assert isinstance(SwingPoint.knowable_from, property)
    assert isinstance(LevelOrigin.knowable_from, property)


def test_eligibility_is_derived_from_the_origin_alone() -> None:
    lvl = level(103.0, origin_index=5, confirmation_bars=3)
    rows = [(100, 101, 99, 100)] * 8 + [(100, 110, 99, 109)]
    crossings = derive_level_crossings(series(rows), [lvl])
    got = derive_structure_breaks([lvl], list(crossings))
    assert [b.eligible_from for b in got] == [8]
    assert got[0].eligible_from == lvl.origin.knowable_from


# ============ 2. the mismatch is unrepresentable ============================


def test_the_break_layer_takes_no_confirmation_delay() -> None:
    parameters = inspect.signature(derive_structure_breaks).parameters
    assert set(parameters) == {"levels", "crossings"}
    assert "confirmation_bars" not in parameters


def test_supplying_a_delay_is_a_type_error_not_a_silent_wrong_answer() -> None:
    """The D1 hazard, expressed as the call that used to make it."""
    lvl = level(103.0)
    rows = [(100, 101, 99, 100)] * 7 + [(100, 110, 99, 109)]
    crossings = list(derive_level_crossings(series(rows), [lvl]))
    for wrong in (0, 1, 5, 50):
        with pytest.raises(TypeError):
            derive_structure_breaks(  # type: ignore[call-arg]
                [lvl], crossings, confirmation_bars=wrong
            )


def test_structural_levels_takes_no_confirmation_delay_either() -> None:
    """The rejected alternative: a `right_bars` parameter one layer up.

    It would let a caller record a window the swings were not detected under —
    the same hazard, relocated and dressed as provenance (ADR-0024 §rejected).
    """
    assert set(inspect.signature(structural_levels).parameters) == {"swings"}


def test_no_public_entry_point_accepts_a_confirmation_delay() -> None:
    from fmis.structure_break import contextual_structure_breaks

    for fn in (derive_structure_breaks, contextual_structure_breaks, structural_levels):
        assert "confirmation_bars" not in inspect.signature(fn).parameters


# ============ 3. prior behaviour is preserved where it was correct ==========


def _reference_pre_ah(levels, crossings, confirmation_bars: int):
    """The pre-AH algorithm, reimplemented from ADR-0020 §2.4 and §3.

    Deliberately naive and independent of the production code: eligibility is
    ``origin.index + confirmation_bars``, the reference is the most recent
    eligible level on the side by linear scan, only a `CLOSE_BREACH` that is not
    `ALREADY_BEYOND` qualifies, and each level breaks at most once.
    """
    from fmis.level_crossing import CrossingKind, CrossingMechanism

    ranked: dict[LevelSide, list[tuple[int, PriceLevel]]] = {
        LevelSide.UPPER: [],
        LevelSide.LOWER: [],
    }
    for lvl in levels:
        ranked[lvl.side].append((lvl.origin.index + confirmation_bars, lvl))
    for side in ranked:
        ranked[side].sort(key=lambda pair: pair[0])

    def reference(side: LevelSide, index: int):
        found = None
        for eligible_from, lvl in ranked[side]:
            if eligible_from > index:
                break
            found = lvl
        return found

    earliest: dict[int, object] = {}
    for crossing in crossings:
        lvl = crossing.level
        if crossing.kind is not CrossingKind.CLOSE_BREACH:
            continue
        if crossing.mechanism is CrossingMechanism.ALREADY_BEYOND:
            continue
        if reference(lvl.side, crossing.index) is not lvl:
            continue
        previous = earliest.get(id(lvl))
        if previous is None or crossing.index < previous.index:
            earliest[id(lvl)] = crossing
    rank = {LevelSide.UPPER: 0, LevelSide.LOWER: 1}
    found = sorted(
        earliest.values(), key=lambda c: (c.index, rank[c.level.side])
    )
    return [(c.index, c.level.side, c.level.price) for c in found]


@pytest.mark.parametrize("right_bars", [1, 2, 3, 4])
def test_the_new_derivation_equals_the_old_one_when_the_delay_matched(
    right_bars: int,
) -> None:
    """**The regression that matters.** AH removes a hazard; it must remove nothing else.

    Across 40 seeded series at four detection windows, the AH derivation is
    compared against a reimplementation of the pre-AH algorithm called with the
    delay a *correct* caller would have passed. Every break must be identical.
    """
    compared = 0
    for seed in range(40):
        rows = seeded_rows(120, seed)
        levels, crossings = chain(rows, right_bars=right_bars)
        if not levels:
            continue
        new = [(b.index, b.side, b.level.price) for b in
               derive_structure_breaks(levels, list(crossings))]
        old = _reference_pre_ah(levels, list(crossings), right_bars)
        assert new == old, (seed, right_bars)
        compared += 1
    assert compared >= 35


def test_a_wrong_delay_would_have_changed_the_answer() -> None:
    """The hazard was real: the reference implementation proves it, on the same data.

    This is what a caller could previously produce **without any error** — and
    is precisely what can no longer be expressed.
    """
    differing = 0
    total = 0
    for seed in range(40):
        levels, crossings = chain(seeded_rows(120, seed), right_bars=2)
        if not levels:
            continue
        total += 1
        correct = _reference_pre_ah(levels, list(crossings), 2)
        for wrong in (0, 1, 4, 6):
            if _reference_pre_ah(levels, list(crossings), wrong) != correct:
                differing += 1
                break
    assert total >= 35
    assert differing > total // 3, (differing, total)


# ============ 4. conflicting and duplicate provenance =======================


def test_two_levels_disagreeing_about_the_window_are_rejected() -> None:
    first = level(100.0, LevelSide.UPPER, origin_index=3, confirmation_bars=2)
    second = level(110.0, LevelSide.UPPER, origin_index=8, confirmation_bars=4)
    with pytest.raises(StructureBreakInputError) as excinfo:
        derive_structure_breaks([first, second], [])
    assert str(excinfo.value) == (
        "levels[1] was confirmed under 4 bars but levels[0] under 2; one level "
        "set cannot mix confirmation windows, because the most recent eligible "
        "level would be ambiguous"
    )


def test_the_rejection_names_the_first_disagreeing_pair_deterministically() -> None:
    levels = [
        level(100.0, LevelSide.UPPER, origin_index=1, confirmation_bars=2),
        level(101.0, LevelSide.LOWER, origin_index=2, confirmation_bars=2),
        level(102.0, LevelSide.UPPER, origin_index=3, confirmation_bars=9),
    ]
    for _ in range(5):
        with pytest.raises(StructureBreakInputError) as excinfo:
            derive_structure_breaks(levels, [])
        assert "levels[2] was confirmed under 9 bars but levels[0] under 2" in str(
            excinfo.value
        )


def test_one_window_across_the_set_is_accepted() -> None:
    levels = [
        level(100.0, LevelSide.UPPER, origin_index=1, confirmation_bars=3),
        level(90.0, LevelSide.LOWER, origin_index=4, confirmation_bars=3),
    ]
    assert derive_structure_breaks(levels, []) == ()


def test_duplicate_origin_index_on_one_side_is_still_rejected() -> None:
    a = level(100.0, LevelSide.UPPER, origin_index=5)
    b = level(110.0, LevelSide.UPPER, origin_index=5)
    with pytest.raises(StructureBreakInputError) as excinfo:
        derive_structure_breaks([a, b], [])
    assert "shares origin index 5" in str(excinfo.value)


def test_a_real_detection_run_never_mixes_windows() -> None:
    for right_bars in (1, 2, 3):
        levels, _ = chain(seeded_rows(120, 7), right_bars=right_bars)
        assert len({lvl.origin.confirmation_bars for lvl in levels}) == 1


# ============ 5. invalid and nonsensical delays =============================


@pytest.mark.parametrize("bad", [0, -1, -99])
def test_a_non_positive_window_is_rejected_on_the_swing(bad: int) -> None:
    with pytest.raises(ValueError) as excinfo:
        SwingPoint(
            index=1,
            timestamp=_BASE,
            price=100.0,
            type=SwingType.HIGH,
            confirmation_bars=bad,
        )
    assert str(excinfo.value) == f"confirmation_bars must be at least 1, got {bad}"


@pytest.mark.parametrize("bad", [0, -1, -99])
def test_a_non_positive_window_is_rejected_on_the_origin(bad: int) -> None:
    with pytest.raises(ValueError) as excinfo:
        origin(5, confirmation_bars=bad)
    assert str(excinfo.value) == f"confirmation_bars must be at least 1, got {bad}"


@pytest.mark.parametrize("bad", ["2", 2.0, None, True])
def test_a_non_int_window_is_rejected(bad: object) -> None:
    with pytest.raises(TypeError) as excinfo:
        origin(5, confirmation_bars=bad)  # type: ignore[arg-type]
    assert "confirmation_bars must be an int" in str(excinfo.value)
    with pytest.raises(TypeError):
        SwingPoint(
            index=1,
            timestamp=_BASE,
            price=100.0,
            type=SwingType.HIGH,
            confirmation_bars=bad,  # type: ignore[arg-type]
        )


def test_a_window_is_required_with_no_default() -> None:
    """A default would rebuild the hazard at the constructor."""
    with pytest.raises(TypeError):
        SwingPoint(  # type: ignore[call-arg]
            index=1, timestamp=_BASE, price=100.0, type=SwingType.HIGH
        )
    with pytest.raises(TypeError):
        LevelOrigin(  # type: ignore[call-arg]
            index=1, timestamp=_BASE, label=StructuralSwingLabel.HIGHER_HIGH
        )
    for model in (SwingPoint, LevelOrigin):
        field = model.__dataclass_fields__["confirmation_bars"]
        assert field.default is dataclasses.MISSING
        assert field.default_factory is dataclasses.MISSING


def test_two_points_from_different_windows_cannot_be_compared() -> None:
    """A comparison across detection runs is not a comparable pair."""
    a = SwingPoint(
        index=1, timestamp=_BASE, price=100.0, type=SwingType.HIGH,
        confirmation_bars=2,
    )
    b = SwingPoint(
        index=5, timestamp=_BASE + timedelta(hours=20), price=110.0,
        type=SwingType.HIGH, confirmation_bars=3,
    )
    with pytest.raises(ValueError) as excinfo:
        compare_swing_sequence([a, b])
    # The exact wording, and in particular which window is reported as which:
    # a message that swapped them would misdirect every reader debugging it.
    assert str(excinfo.value) == (
        "previous and current must share a confirmation window, got 2 and 3; "
        "two points detected under different windows are not a comparable pair"
    )


# ============ 6. equality, hashing, replay ==================================


def test_a_comparison_can_never_straddle_two_windows() -> None:
    """Why `structural_levels` reading `previous` instead of `current` is equivalent.

    A mutation swapping those two reads survives the suite, and provably must:
    `SwingComparison` rejects a pair whose windows disagree, so the two values are
    always equal and no input can distinguish the two spellings. Recorded as a
    **proven equivalent mutant**, with the invariant that makes it one asserted
    here rather than left as an argument in prose.

    `current` remains the correct spelling — the level sits at the current pivot —
    but its correctness is a matter of meaning, not of observable behaviour.
    """
    for right_bars in (1, 2, 3):
        swings = detect_swings(
            series(seeded_rows(140, 17)), left_bars=2, right_bars=right_bars
        )
        comparisons = compare_swing_sequence(swings)
        assert comparisons
        for comparison in comparisons:
            assert (
                comparison.previous.confirmation_bars
                == comparison.current.confirmation_bars
                == right_bars
            )


def test_the_window_participates_in_equality_and_hashing() -> None:
    a = origin(5, confirmation_bars=2)
    b = origin(5, confirmation_bars=2)
    c = origin(5, confirmation_bars=3)
    assert a == b and hash(a) == hash(b)
    assert a != c
    assert len({a, b, c}) == 2


def test_two_levels_differing_only_in_window_are_two_levels() -> None:
    a = level(100.0, confirmation_bars=2)
    b = level(100.0, confirmation_bars=3)
    assert a != b
    assert a.origin.knowable_from != b.origin.knowable_from


def test_provenance_survives_pickle() -> None:
    levels, crossings = chain(seeded_rows(100, 3))
    breaks = derive_structure_breaks(levels, list(crossings))
    restored = pickle.loads(pickle.dumps(breaks))
    assert restored == breaks
    for before, after in zip(breaks, restored):
        assert after.origin.confirmation_bars == before.origin.confirmation_bars
        assert after.eligible_from == before.eligible_from


def test_the_models_are_still_frozen() -> None:
    point = SwingPoint(
        index=1, timestamp=_BASE, price=1.0, type=SwingType.HIGH, confirmation_bars=2
    )
    with pytest.raises(FrozenInstanceError):
        point.confirmation_bars = 9  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        origin(5).confirmation_bars = 9  # type: ignore[misc]


def test_derivation_is_deterministic_across_processes() -> None:
    """No hash-order or environment dependence entered with the new field."""
    script = (
        "from tests.test_confirmation_provenance import chain, seeded_rows;"
        "from fmis.structure_break import derive_structure_breaks;"
        "levels, crossings = chain(seeded_rows(120, 5));"
        "print([(b.index, b.side.value, b.eligible_from) for b in "
        "derive_structure_breaks(levels, list(crossings))])"
    )
    outputs = set()
    for seed in ("0", "1", "42", "12345"):
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin",
                 "PYTHONPATH": "src:."},
            cwd=str(pathlib.Path(__file__).resolve().parent.parent),
        )
        assert proc.returncode == 0, proc.stderr
        outputs.add(proc.stdout.strip())
    assert len(outputs) == 1


# ============ 7. prefix stability and series edges ==========================


def test_prefix_stability_is_unchanged() -> None:
    """A break reported over a prefix must still be reported over the full run.

    This is the property ADR-0020 §2.4 bought with confirmation-based
    eligibility; AH changes where the delay comes from, not the rule.
    """
    violations = 0
    for seed in range(20):
        rows = seeded_rows(120, seed)
        levels, crossings = chain(rows)
        full = {
            (b.index, b.side)
            for b in derive_structure_breaks(levels, list(crossings))
        }
        for cut in range(30, len(rows), 10):
            p_levels, p_crossings = chain(rows[:cut])
            for b in derive_structure_breaks(p_levels, list(p_crossings)):
                if (b.index, b.side) not in full:
                    violations += 1
    assert violations == 0


def test_no_level_is_knowable_at_the_start_of_a_series() -> None:
    """The earliest breakable bar is 1, because the window is at least 1."""
    assert origin(0, confirmation_bars=1).knowable_from == 1
    with pytest.raises(ValueError):
        origin(0, confirmation_bars=0)


def test_a_short_series_yields_no_levels_and_no_breaks() -> None:
    levels, crossings = chain([(100, 101, 99, 100)] * 3)
    assert levels == ()
    assert derive_structure_breaks(levels, list(crossings)) == ()


def test_custom_detection_settings_reach_the_provenance() -> None:
    rows = seeded_rows(160, 21)
    for left, right in ((1, 1), (2, 2), (3, 5), (4, 3)):
        sheet = build_structural_facts(
            series(rows), detection=DetectionSettings(left, right)
        )
        assert sheet.structure.levels
        for lvl in sheet.structure.levels:
            assert lvl.origin.confirmation_bars == right
        for brk in sheet.structure.breaks:
            assert brk.eligible_from == brk.origin.index + right


# ============ 8. the layers above are unchanged =============================


def test_change_of_character_still_derives_from_the_break_run() -> None:
    for seed in (2, 8, 19):
        levels, crossings = chain(seeded_rows(150, seed))
        breaks = derive_structure_breaks(levels, list(crossings))
        changes = derive_changes_of_character(breaks)
        for change in changes:
            assert change.previous.side is not change.side
            assert change.index >= change.previous.index


def test_the_af_sheet_still_reports_the_whole_chain() -> None:
    sheet = build_structural_facts(series(seeded_rows(200, 31)))
    assert sheet.structure.swings
    assert sheet.structure.levels
    assert sheet.structure.breaks
    assert sheet.detection.right_bars == 2
    for lvl in sheet.structure.levels:
        assert lvl.origin.confirmation_bars == 2


def test_the_ag_sheet_still_composes_three_views() -> None:
    rows = seeded_rows(200, 33)
    views = {
        role: build_structural_facts(series(rows), source="fixture")
        for role in TimeframeRole
    }
    sheet = build_multi_timeframe_facts(
        views, intervals={TimeframeRole.CONTEXT: "1w",
                          TimeframeRole.SETUP: "1d",
                          TimeframeRole.EXECUTION: "4h"},
        source="fixture",
    )
    assert len(sheet.views) == 3
    for view in sheet.views:
        for lvl in view.sheet.structure.levels:
            assert lvl.origin.confirmation_bars == 2


def test_the_d1_limitation_is_no_longer_carried() -> None:
    assert all(item.code != "ADR-0020 D1" for item in LIMITATIONS)


# ============ 9. boundaries and purity ======================================


def _code_without_docstrings(path: pathlib.Path) -> str:
    """Source with docstrings blanked, so prose is not mistaken for a dependency.

    These packages document *which layer owns what* by naming the layers, so a
    raw text scan would flag an explanation as a violation. Executable code,
    comments and non-docstring literals are all still scanned, which keeps a
    dynamic ``importlib.import_module("fmis.providers")`` inside the net.
    """
    source = path.read_text()
    lines = source.splitlines(keepends=True)
    for node in ast.walk(ast.parse(source)):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body or not isinstance(body[0], ast.Expr):
            continue
        doc = body[0].value
        if isinstance(doc, ast.Constant) and isinstance(doc.value, str):
            for lineno in range(doc.lineno, doc.end_lineno + 1):
                lines[lineno - 1] = "\n"
    return "".join(lines)


def test_no_clock_and_no_provider_in_the_deterministic_layer() -> None:
    roots = ("market_structure", "level_crossing", "structure_break")
    src = pathlib.Path(__file__).resolve().parent.parent / "src" / "fmis"
    banned = ("datetime.now", "utcnow", "time.time", "time.monotonic",
              "requests", "urllib", "httpx", "fmis.providers")
    for package in roots:
        for py in (src / package).rglob("*.py"):
            code = _code_without_docstrings(py)
            for word in banned:
                assert word not in code, f"{py}: {word}"


def test_the_new_field_added_no_import_edge() -> None:
    """`fmis.level_crossing` still reaches market_structure only for the label enum."""
    src = pathlib.Path(__file__).resolve().parent.parent / "src" / "fmis"
    tree = ast.parse((src / "level_crossing" / "models.py").read_text())
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("fmis")
    }
    assert modules == {"fmis.data", "fmis.market_structure"}


def test_the_public_surface_grew_by_nothing() -> None:
    """AH adds fields and properties, not names. Nothing new is exported."""
    import fmis.level_crossing as lc
    import fmis.market_structure as ms
    import fmis.structure_break as sb

    assert len(lc.__all__) == 13
    assert len(ms.__all__) == 19
    assert len(sb.__all__) == 5
    assert "confirmation_bars" not in lc.__all__ + ms.__all__ + sb.__all__
    assert "knowable_from" not in lc.__all__ + ms.__all__ + sb.__all__


def test_no_engine_imports_the_application_layer() -> None:
    src = pathlib.Path(__file__).resolve().parent.parent / "src" / "fmis"
    for package in ("market_structure", "level_crossing", "structure_break",
                    "change_of_character"):
        for py in (src / package).rglob("*.py"):
            tree = ast.parse(py.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith("fmis.pipeline"), py


def test_the_break_model_carries_exactly_one_field() -> None:
    assert set(StructureBreak.__dataclass_fields__) == {"crossing"}
    assert isinstance(StructureBreak.eligible_from, property)
