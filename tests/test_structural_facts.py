"""Tests for the Structural Fact Sheet composition root (Milestone AF).

Three things are tested that no other suite can test, because no other layer
composes the whole stack:

  1. **The chain runs end to end** — measurement *and* structure, from one call.
  2. **The ADR-0020 D1 containment holds** — `right_bars` reaches detection and
     break derivation from one source, so they cannot disagree through this root.
  3. **The root stays a root** — no arithmetic, no clock, no interpretation, and
     nothing below it imports it.

Expected values are hand-derived or read from the committed fixture, never
produced by calling the code under test.
"""

from __future__ import annotations

import ast
import io
import json
import re
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import fmis.pipeline as pipeline
from fmis.data import Candle, CandleSeries
from fmis.features import FeatureSet
from fmis.features.indicators.ema import ExponentialMovingAverage
from fmis.level_crossing import LevelOrigin, LevelSide, PriceLevel
from fmis.market_structure import (
    DEFAULT_LEFT_BARS,
    DEFAULT_RIGHT_BARS,
    StructuralSwingLabel,
)
from fmis.pipeline import cli as cli_module
from fmis.pipeline import render as render_module
from fmis.pipeline import structural_facts as sf_module
from fmis.pipeline.structural_facts import (
    LIMITATIONS,
    DetectionSettings,
    InsufficientDataError,
    Limitation,
    NearestLevels,
    StructuralFactSheet,
    StructureFacts,
    build_structural_facts,
    structural_facts_for_symbol,
)
from fmis.providers.binance import HttpResponse

#: The confirmation window every hand-built fixture point is confirmed under.
#: Required since Milestone AH: a swing that does not state its window cannot
#: say when it became knowable, and nothing downstream may assume one.
CB = 2

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
_OPEN_MS = 1_704_067_200_000
_FOUR_HOURS_MS = 4 * 60 * 60 * 1000
LATER = datetime(2024, 6, 1, tzinfo=timezone.utc)


# =============================== helpers ====================================


def fixture_series(symbol: str = "BTCUSDT") -> CandleSeries:
    """The committed 20-candle 4H fixture, as a canonical series."""
    rows = json.loads(
        (Path(__file__).parent / "fixtures" / "btcusdt_4h.json").read_text()
    )
    return CandleSeries(
        symbol=symbol,
        timeframe="4h",
        candles=tuple(
            Candle(
                timestamp=datetime.fromisoformat(
                    row["timestamp"].replace("Z", "+00:00")
                ),
                symbol=symbol,
                timeframe="4h",
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                is_closed=row["is_closed"],
            )
            for row in rows
        ),
    )


def synthetic(
    highs_lows: list[tuple[float, float]], *, closed_tail: bool = True
) -> CandleSeries:
    """A series with hand-chosen highs and lows, for structure-shaping tests."""
    candles = []
    for i, (high, low) in enumerate(highs_lows):
        mid = (high + low) / 2
        candles.append(
            Candle(
                timestamp=_BASE + timedelta(hours=4 * i),
                symbol="TEST",
                timeframe="4h",
                open=mid,
                high=high,
                low=low,
                close=mid,
                volume=100.0,
                is_closed=closed_tail or i < len(highs_lows) - 1,
            )
        )
    return CandleSeries(symbol="TEST", timeframe="4h", candles=tuple(candles))


def kline(i: int, close: float, *, closed: bool = True) -> list[object]:
    open_ms = _OPEN_MS + i * _FOUR_HOURS_MS
    close_ms = open_ms + _FOUR_HOURS_MS - 1
    if not closed:
        close_ms = int(datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    return [
        open_ms,
        f"{close:.8f}",
        f"{close * 1.01:.8f}",
        f"{close * 0.99:.8f}",
        f"{close:.8f}",
        "1000.00000000",
        close_ms,
        "1000.0",
        100,
        "500.0",
        "500.0",
        "0",
    ]


def klines(closes: list[float], *, forming_tail: bool = False) -> list[list[object]]:
    rows = [kline(i, c) for i, c in enumerate(closes)]
    if forming_tail and rows:
        rows[-1] = kline(len(closes) - 1, closes[-1], closed=False)
    return rows


def wave(n: int) -> list[float]:
    """A zig-zag that reliably produces swings on both sides."""
    return [100.0 + (10.0 if i % 4 in (1, 2) else 0.0) + i for i in range(n)]


def _irregular_highs(n: int) -> list[float]:
    """A fixed, committed irregular walk — no randomness at test time.

    Generated once from a seeded walk and inlined as literals, because a test
    that called `random` would be reproducible only by accident and the
    repository forbids nondeterministic inputs.
    """
    steps = (
        2.31, -4.87, 5.42, -1.09, -5.63, 3.18, 5.94, -2.76, -0.41, 4.55,
        -5.12, 1.87, 3.29, -4.03, 5.71, -3.44, 0.62, -5.88, 2.94, 4.16,
        -1.53, -4.29, 5.07, 3.62, -5.41, 1.24, -2.85, 4.93, -0.77, -3.96,
        5.38, 2.11, -4.64, 0.95, 3.87, -5.29, 1.46, 4.72, -2.38, -1.84,
        5.63, -3.71, 2.05, -4.98, 3.44, 1.19, -5.52, 4.27, -0.63, -3.15,
        5.86, -1.97, 2.68, 4.41, -5.74, 0.38, -2.52, 3.96, 5.13, -4.45,
        1.72, -3.28, 4.89, -5.06, 2.47, 0.84, -4.71, 3.53, -1.28, 5.95,
        -2.19, 4.06, -5.83, 1.61, 3.34, -0.49, -4.12, 5.27, -3.58, 2.83,
    )
    prices: list[float] = []
    price = 100.0
    for step in steps[:n]:
        price += step
        prices.append(round(price, 4))
    return prices


def _choch_highs() -> list[float]:
    """A committed walk that produces changes of character, not just breaks.

    Found by search and inlined as literals. Needed because the regular `wave`
    zig-zag and the `_irregular_highs` walk both yield **zero** changes of
    character, which left the renderer's change-of-character branch unexecuted
    by any test — a gap the independent review found through coverage.
    """
    steps = (
        -5.12, 4.86, 3.69, -3.43, -0.06, -0.71, 2.12, 4.04, -5.69, -6.6,
        4.7, -0.94, 3.67, -6.97, -0.76, 3.1, -3.8, 6.23, 5.62, -6.57,
        -6.64, 0.58, 6.15, -1.66, -3.97, -1.09, -6.59, -3.9, -0.87, -0.06,
        -3.74, -3.77, -3.94, -0.57, -2.94, -6.7, 4.73, 0.79, 1.99, -4.4,
        6.9, 5.04, -5.31, -2.34, 3.1, 2.96, 6.11, -1.09, 4.62, 2.38,
        -2.75, 1.23, 5.35, 4.85, 0.07, 1.25, -6.52, -3.6, 4.16, -1.2,
        -4.58, 0.68, 2.84, 2.44, -1.75, -0.85, 0.12, 3.9, 0.29, -1.49,
        -0.14, -6.59, -6.39, 2.85, 6.76, 1.3, -1.49, -4.62, 0.03, 6.75,
        3.79, 0.55, 5.04, -3.75, 0.19, 6.33, 1.09, -0.57, -3.23, 0.67,
    )
    prices: list[float] = []
    price = 100.0
    for step in steps:
        price += step
        prices.append(round(price, 4))
    return prices


def choch_series() -> CandleSeries:
    """A series whose fact sheet contains at least one change of character."""
    return synthetic([(h + 3.0, h - 3.0) for h in _choch_highs()])


def transport_for(payload: object, *, status: int = 200):
    def _transport(url: str) -> HttpResponse:
        _transport.calls.append(url)  # type: ignore[attr-defined]
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return HttpResponse(status=status, body=body)

    _transport.calls = []  # type: ignore[attr-defined]
    return _transport


def level(price: float, side: LevelSide, index: int, label: StructuralSwingLabel):
    return PriceLevel(
        price=price,
        side=side,
        origin=LevelOrigin(
            index=index, timestamp=_BASE + timedelta(hours=4 * index), label=label, confirmation_bars=CB
        ),
    )


# ========================= end-to-end composition ===========================


def test_builds_a_sheet_from_the_committed_fixture() -> None:
    sheet = build_structural_facts(fixture_series(), source="fixture")
    assert isinstance(sheet, StructuralFactSheet)
    assert sheet.symbol == "BTCUSDT"
    assert sheet.interval == "4h"
    assert sheet.source == "fixture"


def test_reaches_every_deterministic_layer() -> None:
    """The point of the milestone: one call touches measurement AND structure."""
    sheet = build_structural_facts(fixture_series())
    assert isinstance(sheet.features, FeatureSet)
    assert isinstance(sheet.structure, StructureFacts)
    assert sheet.structure.swings, "swing detection produced nothing"
    assert sheet.structure.labelled, "labelling produced nothing"
    assert sheet.structure.state_history, "state history produced nothing"
    assert sheet.structure.trend is not None
    assert sheet.structure.levels, "level derivation produced nothing"
    assert sheet.structure.crossings, "crossing derivation produced nothing"


def test_fixture_counts_are_stable() -> None:
    """Known-answer regression on the committed fixture."""
    sheet = build_structural_facts(fixture_series())
    assert len(sheet.structure.swings) == 5
    assert len(sheet.structure.labelled) == 3
    assert len(sheet.structure.levels) == 3
    assert len(sheet.structure.breaks) == 1
    assert len(sheet.structure.changes) == 0


def test_as_of_is_the_last_closed_candle_not_the_clock() -> None:
    sheet = build_structural_facts(fixture_series())
    assert sheet.as_of == fixture_series().candles[-1].timestamp
    assert sheet.as_of == sheet.window.last_timestamp


def test_window_reports_last_close() -> None:
    series = fixture_series()
    sheet = build_structural_facts(series)
    assert sheet.window.last_close == series.candles[-1].close


def test_structure_matches_calling_the_engines_directly() -> None:
    """Reuse is proven, not assumed: the root must not re-derive anything."""
    from fmis.level_crossing import derive_level_crossings, structural_levels
    from fmis.market_structure import (
        compare_swing_sequence,
        detect_swings,
        label_swing_sequence,
    )

    series = fixture_series()
    sheet = build_structural_facts(series)
    swings = detect_swings(
        series.closed(), left_bars=DEFAULT_LEFT_BARS, right_bars=DEFAULT_RIGHT_BARS
    )
    labelled = label_swing_sequence(compare_swing_sequence(swings))
    assert sheet.structure.swings == swings
    assert sheet.structure.labelled == labelled
    assert sheet.structure.levels == structural_levels(labelled)
    assert sheet.structure.crossings == derive_level_crossings(
        series.closed(), structural_levels(labelled)
    )


# ============================ closed-candle policy ==========================


def test_forming_candle_is_excluded_unconditionally() -> None:
    series = synthetic([(h, h - 5) for h in wave(30)], closed_tail=False)
    sheet = build_structural_facts(series)
    assert sheet.window.excluded_forming_count == 1
    assert sheet.window.closed_count == 29
    assert sheet.as_of == series.candles[-2].timestamp


def test_no_forming_candle_excludes_nothing() -> None:
    sheet = build_structural_facts(fixture_series())
    assert sheet.window.excluded_forming_count == 0


# ======================= determinism and purity =============================


def test_two_builds_over_the_same_candles_are_equal() -> None:
    a = build_structural_facts(fixture_series(), source="fixture")
    b = build_structural_facts(fixture_series(), source="fixture")
    assert a == b


def test_repeated_builds_produce_identical_structure_runs() -> None:
    a = build_structural_facts(fixture_series()).structure
    b = build_structural_facts(fixture_series()).structure
    assert a.swings == b.swings
    assert a.breaks == b.breaks
    assert a.changes == b.changes
    assert a.levels == b.levels


def test_module_reads_no_clock() -> None:
    """A sheet must be a pure function of its candles."""
    source = Path(sf_module.__file__).read_text()
    for forbidden in ("datetime.now", "utcnow", "time.time", "time.monotonic"):
        assert forbidden not in source, forbidden


def test_module_contains_no_arithmetic_at_all() -> None:
    """Stricter than ADR-0007 §2: the one bookkeeping subtraction is reused."""
    tree = ast.parse(Path(sf_module.__file__).read_text())
    operators = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(
            node.op,
            (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Pow, ast.Mod),
        )
    ]
    assert operators == [], [ast.unparse(o) for o in operators]


def test_module_imports_no_maths_library() -> None:
    tree = ast.parse(Path(sf_module.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not imported & {"math", "statistics", "decimal", "fractions", "random"}


# =================== ADR-0020 D1 containment (the key test) =================


def test_this_root_no_longer_carries_a_duplicated_delay(
) -> None:
    """AH: the delay reaches exactly one callee, so there is nothing to keep in step.

    This replaces the AF-era containment guard, which asserted that
    ``detection.right_bars`` was read **once** and handed to **two** consumers.
    That guard was correct while `derive_structure_breaks` demanded the number as
    an argument; it is meaningless now that the argument is gone, and keeping it
    would pin a workaround in place after its cause was removed.

    What is asserted instead is stronger: this root reads ``right_bars`` once, it
    reaches `detect_swings` only, and no ``confirmation_bars`` argument is passed
    anywhere in the module.
    """
    tree = ast.parse(Path(sf_module.__file__).read_text())
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_structure_of"
    )
    # The docstring explains the rule and names the attribute; the assertion is
    # about executable code, so prose must not count towards it.
    statements = [
        node
        for node in fn.body
        if not (
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        )
    ]
    body = "\n".join(ast.unparse(node) for node in statements)
    assert body.count("detection.right_bars") == 1, body
    assert "right_bars=detection.right_bars" in body
    assert "derive_structure_breaks(levels, crossings)" in body

    # And nowhere in the whole module does a confirmation delay get passed.
    module_body = "\n".join(
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    )
    assert "confirmation_bars=" not in module_body


def test_changing_right_bars_changes_both_detection_and_breaks() -> None:
    """Behavioural counterpart: one knob moves the whole chain coherently."""
    series = synthetic([(h, h - 5) for h in wave(60)])
    tight = build_structural_facts(series, detection=DetectionSettings(2, 2))
    loose = build_structural_facts(series, detection=DetectionSettings(4, 4))
    assert tight.detection.right_bars == 2
    assert loose.detection.right_bars == 4
    assert tight.structure.swings != loose.structure.swings


def test_breaks_agree_with_a_hand_matched_direct_call() -> None:
    """The root's result equals the engine called with the matching delay."""
    from fmis.level_crossing import derive_level_crossings, structural_levels
    from fmis.market_structure import (
        compare_swing_sequence,
        detect_swings,
        label_swing_sequence,
    )
    from fmis.structure_break import derive_structure_breaks

    series = synthetic([(h, h - 5) for h in wave(60)])
    right = 3
    sheet = build_structural_facts(series, detection=DetectionSettings(3, right))
    swings = detect_swings(series.closed(), left_bars=3, right_bars=right)
    levels = structural_levels(label_swing_sequence(compare_swing_sequence(swings)))
    expected = derive_structure_breaks(
        levels, derive_level_crossings(series.closed(), levels)
    )
    assert sheet.structure.breaks == expected


def test_detection_settings_delegates_validation() -> None:
    with pytest.raises(ValueError):
        DetectionSettings(left_bars=-1, right_bars=2)
    with pytest.raises(TypeError):
        DetectionSettings(left_bars="2", right_bars=2)  # type: ignore[arg-type]


def test_detection_settings_is_frozen() -> None:
    settings = DetectionSettings()
    with pytest.raises(Exception):
        settings.right_bars = 9  # type: ignore[misc]


def test_detection_settings_required_candles_delegates() -> None:
    from fmis.market_structure import required_candles

    assert DetectionSettings(3, 4).required_candles == required_candles(3, 4)


def test_rejects_a_non_detection_settings_object() -> None:
    with pytest.raises(TypeError, match="DetectionSettings"):
        build_structural_facts(fixture_series(), detection=(2, 2))  # type: ignore[arg-type]


# ============================ nearest levels ================================


def test_nearest_levels_pick_the_closest_each_side() -> None:
    levels = (
        level(110.0, LevelSide.UPPER, 1, StructuralSwingLabel.HIGHER_HIGH),
        level(105.0, LevelSide.UPPER, 2, StructuralSwingLabel.LOWER_HIGH),
        level(95.0, LevelSide.LOWER, 3, StructuralSwingLabel.HIGHER_LOW),
        level(90.0, LevelSide.LOWER, 4, StructuralSwingLabel.LOWER_LOW),
    )
    near = sf_module._nearest_levels(levels, 100.0)
    assert near.above is not None and near.above.price == 105.0
    assert near.below is not None and near.below.price == 95.0
    assert near.upper_count == 2
    assert near.lower_count == 2


def test_nearest_levels_are_absent_when_price_is_beyond_every_level() -> None:
    levels = (level(90.0, LevelSide.LOWER, 1, StructuralSwingLabel.LOWER_LOW),)
    near = sf_module._nearest_levels(levels, 100.0)
    assert near.above is None
    assert near.below is not None and near.below.price == 90.0


def test_nearest_levels_absent_without_a_close() -> None:
    near = sf_module._nearest_levels((), None)
    assert near == NearestLevels(above=None, below=None, upper_count=0, lower_count=0)


def test_nearest_level_tie_break_is_deterministic() -> None:
    """Two levels at one price must resolve identically in any input order.

    Both carry the **same label** deliberately: with different labels the label
    field alone would decide, and a tie-break that ignored the origin index
    would still pass. A mutation probe that blanked the index survived exactly
    that way, so the fixture now makes the index the deciding field.
    """
    a = level(105.0, LevelSide.UPPER, 2, StructuralSwingLabel.HIGHER_HIGH)
    b = level(105.0, LevelSide.UPPER, 7, StructuralSwingLabel.HIGHER_HIGH)
    forward = sf_module._nearest_levels((a, b), 100.0)
    reverse = sf_module._nearest_levels((b, a), 100.0)
    assert forward.above == reverse.above
    assert forward.above is a  # lower origin index wins
    assert forward.above.origin is not None
    assert forward.above.origin.index == 2


def test_level_at_exactly_the_close_is_neither_above_nor_below() -> None:
    exact = level(100.0, LevelSide.UPPER, 1, StructuralSwingLabel.HIGHER_HIGH)
    near = sf_module._nearest_levels((exact,), 100.0)
    assert near.above is None
    assert near.below is None


def test_a_level_may_be_upper_and_below_the_close() -> None:
    """Price above a former swing high: the fact the naming rule protects."""
    sheet = build_structural_facts(fixture_series())
    below = sheet.nearest_levels.below
    assert below is not None
    assert below.side is LevelSide.UPPER
    assert below.price < sheet.window.last_close


# ============================== warm-up =====================================


def test_warming_up_names_features_without_enough_history() -> None:
    sheet = build_structural_facts(fixture_series())
    assert "ema_50" in sheet.warming_up
    for name in sheet.warming_up:
        assert sheet.features.features[name].value is None


def test_ready_features_are_not_listed_as_warming_up() -> None:
    sheet = build_structural_facts(fixture_series())
    assert "ema_20" not in sheet.warming_up
    assert sheet.features.features["ema_20"].value is not None


def test_no_feature_warms_up_given_enough_history() -> None:
    series = synthetic([(h, h - 5) for h in wave(120)])
    sheet = build_structural_facts(series)
    assert sheet.warming_up == ()


def test_custom_features_are_honoured() -> None:
    sheet = build_structural_facts(
        fixture_series(), features=[ExponentialMovingAverage(5)]
    )
    assert set(sheet.features.features) == {"ema_5"}


# =========================== insufficient data ==============================


def test_too_few_candles_for_detection_raises() -> None:
    series = synthetic([(101.0, 99.0), (102.0, 98.0)])
    with pytest.raises(InsufficientDataError) as excinfo:
        build_structural_facts(series)
    assert excinfo.value.required == DetectionSettings().required_candles
    assert excinfo.value.closed == 2


def test_insufficient_data_names_the_subject() -> None:
    with pytest.raises(InsufficientDataError, match="TEST 4h"):
        build_structural_facts(synthetic([(101.0, 99.0)]))


def test_exactly_enough_candles_succeeds() -> None:
    needed = DetectionSettings().required_candles
    series = synthetic([(100.0 + i, 95.0 + i) for i in range(needed)])
    sheet = build_structural_facts(series)
    assert sheet.window.closed_count == needed


# ============================ immutability ==================================


def test_sheet_is_frozen() -> None:
    sheet = build_structural_facts(fixture_series())
    with pytest.raises(Exception):
        sheet.symbol = "OTHER"  # type: ignore[misc]


def test_metadata_is_an_immutable_mapping() -> None:
    sheet = build_structural_facts(fixture_series(), metadata={"a": 1})
    with pytest.raises(TypeError):
        sheet.metadata["b"] = 2  # type: ignore[index]


def test_metadata_is_defensively_copied() -> None:
    supplied = {"a": 1}
    sheet = build_structural_facts(fixture_series(), metadata=supplied)
    supplied["a"] = 999
    assert sheet.metadata["a"] == 1


def test_structure_runs_are_tuples() -> None:
    structure = build_structural_facts(fixture_series()).structure
    for run in (
        structure.swings,
        structure.labelled,
        structure.levels,
        structure.crossings,
        structure.breaks,
        structure.changes,
    ):
        assert isinstance(run, tuple)


# ============================= limitations ==================================


def test_limitations_are_present_and_sourced() -> None:
    sheet = build_structural_facts(fixture_series())
    assert sheet.limitations == LIMITATIONS
    codes = {limitation.code for limitation in sheet.limitations}
    assert "ADR-0019 D2" in codes
    # ADR-0020 D1 was removed in Milestone AH: the delay is now carried on every
    # LevelOrigin, so the limitation it described is no longer true.
    assert "ADR-0020 D1" not in codes
    for limitation in sheet.limitations:
        assert isinstance(limitation, Limitation)
        assert limitation.code.startswith("ADR-")
        assert limitation.text.endswith(".")


def test_the_d1_limitation_is_gone_because_it_was_fixed() -> None:
    """AH: a limitation kept past its fix teaches a reader to discount the list."""
    assert all(x.code != "ADR-0020 D1" for x in LIMITATIONS)
    assert not any("confirmation delay is carried on no derived fact" in x.text
                   for x in LIMITATIONS)

    # The fact it used to disclaim now holds on every level the sheet reports.
    sheet = build_structural_facts(fixture_series())
    assert sheet.structure.levels
    for level in sheet.structure.levels:
        assert level.origin is not None
        assert level.origin.confirmation_bars == sheet.detection.right_bars


# ====================== latest projections ==================================


def test_latest_break_and_change_are_the_last_elements() -> None:
    structure = build_structural_facts(fixture_series()).structure
    assert structure.latest_break is structure.breaks[-1]
    assert structure.latest_change is None  # fixture has no change of character


def test_latest_projections_are_none_on_empty_runs() -> None:
    empty = StructureFacts(
        swings=(), labelled=(), state_history=(),
        trend=build_structural_facts(fixture_series()).structure.trend,
        levels=(), crossings=(), breaks=(), changes=(),
    )
    assert empty.latest_break is None
    assert empty.latest_change is None


# ============================ network edge ==================================


def test_fetches_and_builds_from_a_provider() -> None:
    sheet = structural_facts_for_symbol(
        "BTCUSDT",
        "4h",
        transport=transport_for(klines(wave(60))),
        clock=lambda: LATER,
    )
    assert sheet.symbol == "BTCUSDT"
    assert sheet.source == sf_module.BINANCE_SPOT
    assert sheet.structure.swings


def test_provider_metadata_is_recorded() -> None:
    sheet = structural_facts_for_symbol(
        "BTCUSDT", "4h", limit=60,
        transport=transport_for(klines(wave(60))), clock=lambda: LATER,
    )
    assert sheet.metadata["requested_limit"] == 60
    assert sheet.metadata["fetched_count"] == 60


def test_forming_candle_from_the_provider_is_dropped() -> None:
    sheet = structural_facts_for_symbol(
        "BTCUSDT", "4h",
        transport=transport_for(klines(wave(60), forming_tail=True)),
        clock=lambda: LATER,
    )
    assert sheet.window.excluded_forming_count == 1
    assert sheet.window.closed_count == 59


def test_provider_shortfall_raises_insufficient_data() -> None:
    with pytest.raises(InsufficientDataError):
        structural_facts_for_symbol(
            "BTCUSDT", "4h",
            transport=transport_for(klines(wave(3))), clock=lambda: LATER,
        )


# =========================== architectural guards ===========================


def test_no_engine_imports_the_fact_sheet_root() -> None:
    """No **engine** imports the application layer. The workspace is not one.

    Widened for Milestone AK: `fmis.workspace` sits *above* `fmis.pipeline` and
    consumes this root, which is the direction ADR-0007 permits. What the guard
    still forbids is an engine — anything below the application layer — reaching
    upward, and every such package remains covered.
    Widened again for Milestone AN: `fmis.daily` is a second application-layer
    root, above the workspace, and running the same analysis across a universe is
    what it exists to do. The guard's direction is unchanged — an engine still
    may not reach upward — and every engine remains covered.

    Widened again for Milestone AR: `fmis.swing_setup` is a third
    application-layer root, at the same tier as the workspace (ADR-0028). The
    direction is still unchanged.
    """
    root = Path(sf_module.__file__).parent.parent
    above = {"pipeline", "workspace", "daily", "swing_setup"}
    for path in root.rglob("*.py"):
        if above & set(path.parts) or "__pycache__" in path.parts:
            continue
        assert "structural_facts" not in path.read_text(), path


def test_importing_an_engine_does_not_load_the_fact_sheet(
    fresh_fmis_imports: None,
) -> None:
    import fmis.market_structure  # noqa: F401

    assert not any(m.startswith("fmis.pipeline") for m in sys.modules)


def test_importing_pipeline_loads_the_whole_stack(fresh_fmis_imports: None) -> None:
    import fmis.pipeline  # noqa: F401

    for expected in (
        "fmis.data",
        "fmis.features",
        "fmis.market_structure",
        "fmis.level_crossing",
        "fmis.structure_break",
        "fmis.change_of_character",
        "fmis.structural_trend",
    ):
        assert expected in sys.modules, expected


def test_root_reaches_no_private_module_of_another_package() -> None:
    tree = ast.parse(Path(sf_module.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)
    foreign_private = {
        m for m in imported
        if m.startswith("fmis.") and not m.startswith("fmis.pipeline")
        and ("._" in m or m.rsplit(".", 1)[-1].startswith("_"))
    }
    assert foreign_private == set(), foreign_private


def test_public_surface_is_exported() -> None:
    for name in (
        "build_structural_facts",
        "structural_facts_for_symbol",
        "render_fact_sheet",
        "StructuralFactSheet",
        "DetectionSettings",
    ):
        assert name in pipeline.__all__
        assert hasattr(pipeline, name)


# ====================== fact-only vocabulary ================================

_FORBIDDEN = (
    "buy", "sell", "long", "short", "bullish", "bearish",
    "support", "resistance", "signal", "recommend", "entry",
    "target", "confidence", "score",
)

#: Two exemptions, each justified rather than convenient.
#:
#: ``signal_line`` is MACD's own component name — the standard term for one of
#: the three numbers `MovingAverageConvergenceDivergence` returns. It names a
#: computed quantity, not a trading signal, and renaming it would invent a second
#: vocabulary for a value `fmis.features` already named.
#:
#: The closing disclaimer contains "recommendation" precisely to deny making one.
#: It is asserted separately, so removing it would fail a test rather than pass
#: this one.
_ALLOWED_CONTEXTS = ("signal_line",)
_DISCLAIMER = "recommendation is expressed or implied"


def _forbidden_words(text: str) -> set[str]:
    lowered = text.lower()
    for allowed in _ALLOWED_CONTEXTS:
        lowered = lowered.replace(allowed, "")
    lowered = lowered.replace(_DISCLAIMER, "")
    return {w for w in _FORBIDDEN if re.search(rf"\b{w}\w*\b", lowered)}


def test_the_disclaimer_is_present_and_denies_a_recommendation() -> None:
    """The one exempted phrase must actually exist, or the exemption is a hole."""
    text = render_module.render_fact_sheet(build_structural_facts(fixture_series()))
    assert _DISCLAIMER in text
    assert "measurements, not conclusions" in text


def test_rendered_sheet_contains_no_interpretation_vocabulary() -> None:
    sheet = build_structural_facts(fixture_series())
    found = _forbidden_words(render_module.render_fact_sheet(sheet))
    assert found == set(), found


def test_rendered_sheet_with_a_change_of_character_stays_fact_only() -> None:
    series = synthetic([(h, h - 5) for h in wave(90)])
    sheet = build_structural_facts(series)
    found = _forbidden_words(render_module.render_fact_sheet(sheet))
    assert found == set(), found


def test_limitation_texts_are_fact_only() -> None:
    for limitation in LIMITATIONS:
        assert _forbidden_words(limitation.text) == set(), limitation.code


# ============================== renderer ====================================


def test_render_is_deterministic() -> None:
    sheet = build_structural_facts(fixture_series())
    assert render_module.render_fact_sheet(sheet) == render_module.render_fact_sheet(
        sheet
    )


def test_render_includes_the_headline_facts() -> None:
    sheet = build_structural_facts(fixture_series(), source="fixture")
    text = render_module.render_fact_sheet(sheet)
    for expected in (
        "BTCUSDT",
        "fixture",
        "4h",
        sheet.as_of.isoformat(),
        "confirmation_bars=2 (carried on each level)",
        "Structural trend",
        "Break of structure",
        "Change of character",
        "Nearest above close",
        "Nearest below close",
        "LIMITATIONS",
    ):
        assert expected in text, expected


def test_render_reports_the_right_bars_window_not_the_left_one() -> None:
    """The detection row names the **confirmation** window, which is `right_bars`.

    Asserted with asymmetric settings on purpose: the default is L2 R2, so a
    renderer that printed `left_bars` would be indistinguishable from a correct
    one on every symmetric fixture. A mutation doing exactly that survived the
    suite until this test existed.
    """
    sheet = build_structural_facts(
        fixture_series(), detection=DetectionSettings(3, 5), source="fixture"
    )
    text = render_module.render_fact_sheet(sheet)
    line = next(ln for ln in text.splitlines() if "Detection" in ln)
    assert "L3 R5" in line
    assert "confirmation_bars=5 (carried on each level)" in line
    assert "confirmation_bars=3" not in line


def test_render_marks_warming_up_features_with_a_dash_not_a_zero() -> None:
    text = render_module.render_fact_sheet(build_structural_facts(fixture_series()))
    assert "warming up" in text
    assert "ema_50" in text
    line = next(ln for ln in text.splitlines() if ln.strip().startswith("ema_50"))
    assert "—" in line and "0.00" not in line
    # The note must be on the row itself. The WARM-UP section header also
    # contains "warming up", so asserting only its presence in the whole text
    # let a probe that removed the per-row note survive.
    assert "warming up" in line


def test_asymmetric_detection_bars_are_not_interchangeable() -> None:
    """`left_bars` and `right_bars` must reach `detect_swings` in the right slots.

    Every earlier test used the symmetric default (L2 R2) or another equal pair,
    which made swapping the two arguments invisible. A mutation probe that passed
    the confirmation delay as ``left_bars`` survived on exactly that. An
    asymmetric pair is the only fixture that can catch it.
    """
    from fmis.market_structure import detect_swings

    # An *irregular* series is required. The regular `wave` zig-zag yields the
    # same pivots under L3R5 and L5R3, which would make the second assertion
    # vacuous; this walk does not.
    series = synthetic([(h, h - 6.0) for h in _irregular_highs(80)])
    settings = DetectionSettings(left_bars=3, right_bars=5)
    sheet = build_structural_facts(series, detection=settings)
    assert sheet.structure.swings == detect_swings(
        series.closed(), left_bars=3, right_bars=5
    )
    # ...and is genuinely different from the swapped pair, or the test is empty.
    assert sheet.structure.swings != detect_swings(
        series.closed(), left_bars=5, right_bars=3
    )


def test_render_shows_the_actual_break_when_one_exists() -> None:
    """Presence of the label is not enough; the fact itself must be printed."""
    sheet = build_structural_facts(fixture_series())
    latest = sheet.structure.latest_break
    assert latest is not None
    line = next(
        ln
        for ln in render_module.render_fact_sheet(sheet).splitlines()
        if ln.strip().startswith("Break of structure")
    )
    assert f"{latest.side.value} @ bar {latest.index}" in line
    assert "none in this window" not in line


def test_render_emits_structure_rows_in_a_fixed_order() -> None:
    """Row order is part of the contract, not an accident of the code layout.

    Found by the Milestone AG review: extracting `_structure_rows` made the three
    rows swappable as a unit, and a probe that reordered them survived the **full**
    3,403-test suite. Nothing asserted order while the code was inline, so the gap
    existed before the refactor — it was simply unreachable by mutation.
    """
    text = render_module.render_fact_sheet(build_structural_facts(fixture_series()))
    labels = [
        line.strip().split("  ")[0]
        for line in text.splitlines()
        if line.startswith(" ") and line.strip()
    ]
    order = [l for l in labels if l in {
        "Structural trend", "Latest label", "Break of structure",
        "Breaks in window", "Change of character", "Changes in window"}]
    assert order == [
        "Structural trend", "Latest label", "Break of structure",
        "Breaks in window", "Change of character", "Changes in window"], order


def test_render_shows_none_when_no_break_exists() -> None:
    series = synthetic([(100.0 + i, 95.0 + i) for i in range(12)])
    sheet = build_structural_facts(series)
    assert sheet.structure.latest_break is None
    line = next(
        ln
        for ln in render_module.render_fact_sheet(sheet).splitlines()
        if ln.strip().startswith("Break of structure")
    )
    assert "none in this window" in line


def test_render_puts_each_nearest_level_on_its_own_line() -> None:
    """Above and below must not be swapped, which needs both to exist and differ."""
    sheet = build_structural_facts(synthetic([(h, h - 5) for h in wave(120)]))
    above, below = sheet.nearest_levels.above, sheet.nearest_levels.below
    assert above is not None and below is not None and above.price != below.price
    lines = render_module.render_fact_sheet(sheet).splitlines()
    above_line = next(ln for ln in lines if "Nearest above close" in ln)
    below_line = next(ln for ln in lines if "Nearest below close" in ln)
    assert f"{above.price:,.2f}" in above_line
    assert f"{below.price:,.2f}" in below_line
    assert f"{below.price:,.2f}" not in above_line


def test_the_choch_fixture_actually_produces_changes() -> None:
    """Guards the fixture itself: if it stops producing changes, say so loudly."""
    structure = build_structural_facts(choch_series()).structure
    assert structure.changes, "fixture no longer exercises the CHoCH path"
    assert structure.latest_change is not None


def test_render_shows_the_actual_change_of_character() -> None:
    """The renderer's change branch was executed by no test until the review."""
    sheet = build_structural_facts(choch_series())
    latest = sheet.structure.latest_change
    assert latest is not None
    line = next(
        ln
        for ln in render_module.render_fact_sheet(sheet).splitlines()
        if ln.strip().startswith("Change of character")
    )
    assert f"{latest.side.value} @ bar {latest.index}" in line
    assert latest.timestamp.isoformat() in line
    assert "none in this window" not in line


def test_render_counts_changes_in_window() -> None:
    sheet = build_structural_facts(choch_series())
    line = next(
        ln
        for ln in render_module.render_fact_sheet(sheet).splitlines()
        if ln.strip().startswith("Changes in window")
    )
    assert str(len(sheet.structure.changes)) in line


def test_render_handles_a_level_without_an_origin() -> None:
    """`PriceLevel.origin` is optional; the renderer must not assume it."""
    bare = PriceLevel(price=101.0, side=LevelSide.UPPER, origin=None)
    value, note = render_module._level(bare)
    assert value == "101.00"
    assert note == "upper · no origin"


def test_render_formats_non_numeric_and_boolean_values() -> None:
    assert render_module._number(True) == "True"
    assert render_module._number("n/a") == "n/a"
    assert render_module._number(None) == "—"
    assert render_module._number(1234.5) == "1,234.50"


def test_render_omits_age_without_a_reference_time() -> None:
    text = render_module.render_fact_sheet(build_structural_facts(fixture_series()))
    assert "Data freshness" not in text


def test_render_reports_age_against_an_injected_reference() -> None:
    sheet = build_structural_facts(fixture_series())
    text = render_module.render_fact_sheet(
        sheet, reference_time=sheet.as_of + timedelta(hours=5, minutes=30)
    )
    assert "age 5h 30m" in text


def test_render_reports_minutes_only_under_an_hour() -> None:
    sheet = build_structural_facts(fixture_series())
    text = render_module.render_fact_sheet(
        sheet, reference_time=sheet.as_of + timedelta(minutes=12)
    )
    assert "age 12m" in text


def test_render_flags_a_reference_before_the_data() -> None:
    sheet = build_structural_facts(fixture_series())
    text = render_module.render_fact_sheet(
        sheet, reference_time=sheet.as_of - timedelta(hours=1)
    )
    assert "reference precedes the data" in text


def test_render_expands_a_structured_feature_value() -> None:
    series = synthetic([(h, h - 5) for h in wave(120)])
    text = render_module.render_fact_sheet(build_structural_facts(series))
    assert "macd_close_12_26_9.macd_line" in text
    assert "macd_close_12_26_9.histogram" in text


def test_renderer_reaches_no_engine() -> None:
    tree = ast.parse(Path(render_module.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)
    engine_imports = {
        m for m in imported
        if m.startswith("fmis.")
        and not m.startswith("fmis.pipeline")
        and m != "fmis.level_crossing"  # PriceLevel, for a type annotation only
        # `fmis.market_regime` supplies type annotations and one vocabulary
        # constant (`EvidenceStatus`, for the explicit display order). The
        # renderer calls nothing from it, which the assertion below proves
        # separately — this exemption is about *names*, not about behaviour.
        and m != "fmis.market_regime"
    }
    assert engine_imports == set(), engine_imports

    # The exemptions above are type-only, and that is asserted rather than
    # trusted: the renderer must call no function from either package.
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "classify_regime" not in called
    assert "derive_level_crossings" not in called
    assert "structural_levels" not in called


# ================================ CLI =======================================


def test_parser_defaults() -> None:
    args = cli_module.build_parser().parse_args(["facts", "BTCUSDT"])
    assert args.command == "facts"
    assert args.symbol == "BTCUSDT"
    assert args.interval == "4h"
    assert args.limit is None
    assert args.left_bars == DEFAULT_LEFT_BARS
    assert args.right_bars == DEFAULT_RIGHT_BARS


def test_parser_accepts_overrides() -> None:
    args = cli_module.build_parser().parse_args(
        ["facts", "ETHUSDT", "-i", "1d", "-n", "300", "--right-bars", "4"]
    )
    assert (args.symbol, args.interval, args.limit, args.right_bars) == (
        "ETHUSDT",
        "1d",
        300,
        4,
    )


def test_parser_requires_a_subcommand() -> None:
    with pytest.raises(SystemExit):
        cli_module.build_parser().parse_args([])


def test_main_prints_a_sheet_and_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    sheet = build_structural_facts(fixture_series(), source="fixture")
    monkeypatch.setattr(
        cli_module, "structural_facts_for_symbol", lambda *a, **k: sheet
    )
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli_module.main(["facts", "BTCUSDT", "--no-age"])
    assert code == cli_module.EXIT_OK
    assert "FMITS STRUCTURAL FACT SHEET" in buffer.getvalue()
    assert "BTCUSDT" in buffer.getvalue()
    # --no-age must actually suppress the line. Without this the flag could be
    # ignored entirely and every other assertion would still pass.
    assert "Data freshness" not in buffer.getvalue()


def test_main_shows_age_when_no_age_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    sheet = build_structural_facts(fixture_series())
    monkeypatch.setattr(
        cli_module, "structural_facts_for_symbol", lambda *a, **k: sheet
    )
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli_module.main(
            ["facts", "BTCUSDT", "--reference-time", sheet.as_of.isoformat()]
        )
    assert code == cli_module.EXIT_OK
    assert "Data freshness" in buffer.getvalue()


def test_main_forwards_detection_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake(symbol, interval, **kwargs):
        seen.update(kwargs, symbol=symbol, interval=interval)
        return build_structural_facts(fixture_series())

    monkeypatch.setattr(cli_module, "structural_facts_for_symbol", fake)
    with redirect_stdout(io.StringIO()):
        cli_module.main(["facts", "ETHUSDT", "-i", "1d", "--right-bars", "3"])
    assert seen["symbol"] == "ETHUSDT"
    assert seen["interval"] == "1d"
    assert seen["detection"] == DetectionSettings(left_bars=2, right_bars=3)


def test_main_returns_failure_on_insufficient_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raiser(*args, **kwargs):
        raise InsufficientDataError(
            subject="BTCUSDT 4h", required=5, fetched=2, closed=2
        )

    monkeypatch.setattr(cli_module, "structural_facts_for_symbol", raiser)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli_module.main(["facts", "BTCUSDT", "--no-age"])
    assert code == cli_module.EXIT_FAILURE
    assert "InsufficientDataError" in buffer.getvalue()


def test_main_returns_failure_on_a_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fmis.providers.binance import BinanceTransportError

    def raiser(*args, **kwargs):
        raise BinanceTransportError("network down")

    monkeypatch.setattr(cli_module, "structural_facts_for_symbol", raiser)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli_module.main(["facts", "BTCUSDT", "--no-age"])
    assert code == cli_module.EXIT_FAILURE
    assert "network down" in buffer.getvalue()


def test_main_rejects_a_naive_reference_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_module,
        "structural_facts_for_symbol",
        lambda *a, **k: build_structural_facts(fixture_series()),
    )
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli_module.main(
            ["facts", "BTCUSDT", "--reference-time", "2026-08-01T09:00:00"]
        )
    assert code == cli_module.EXIT_FAILURE
    assert "timezone-aware" in buffer.getvalue()


def test_main_uses_an_explicit_reference_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sheet = build_structural_facts(fixture_series())
    monkeypatch.setattr(
        cli_module, "structural_facts_for_symbol", lambda *a, **k: sheet
    )
    reference = (sheet.as_of + timedelta(hours=2)).isoformat()
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli_module.main(["facts", "BTCUSDT", "--reference-time", reference])
    assert code == cli_module.EXIT_OK
    assert "age 2h 00m" in buffer.getvalue()


def test_cli_defines_no_arithmetic_over_market_data() -> None:
    """The CLI parses, calls, renders. It must not compute."""
    tree = ast.parse(Path(cli_module.__file__).read_text())
    operators = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(node.op, (ast.Mult, ast.Div, ast.FloorDiv, ast.Pow, ast.Mod))
    ]
    assert operators == [], [ast.unparse(o) for o in operators]


def test_module_entry_point_forwards_to_main() -> None:
    source = Path(sf_module.__file__).parent.joinpath("__main__.py").read_text()
    assert "from fmis.pipeline.cli import main" in source
    assert "SystemExit(main())" in source
