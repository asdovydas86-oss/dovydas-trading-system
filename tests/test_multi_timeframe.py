"""Tests for the Multi-Timeframe Fact Sheet composition root (Milestone AG).

Three things are tested that no other suite can test:

  1. **Composition delegates wholly** — every view equals calling
     `structural_facts_for_symbol` directly, so no logic was duplicated.
  2. **Nothing is derived from the combination** — no agreement, alignment,
     conflict or consensus field exists, and none appears in rendered output.
     This is the milestone's load-bearing constraint.
  3. **The ADR-0020 D1 containment extends across views** — one
     `DetectionSettings` reaches every timeframe.

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
from fmis.features.indicators.ema import ExponentialMovingAverage
from fmis.market_structure import DEFAULT_LEFT_BARS, DEFAULT_RIGHT_BARS
from fmis.pipeline import cli as cli_module
from fmis.pipeline import multi_timeframe as mtf_module
from fmis.pipeline import render as render_module
from fmis.pipeline.market_analysis import default_features
from fmis.pipeline.multi_timeframe import (
    DEFAULT_TIMEFRAMES,
    MULTI_TIMEFRAME_LIMITATIONS,
    MultiTimeframeFactSheet,
    TimeframeRole,
    TimeframeView,
    build_multi_timeframe_facts,
    multi_timeframe_facts_for_symbol,
    swing_features,
)
from fmis.pipeline.structural_facts import (
    LIMITATIONS,
    DetectionSettings,
    InsufficientDataError,
    build_structural_facts,
    structural_facts_for_symbol,
)
from fmis.providers.binance import HttpResponse

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
_OPEN_MS = 1_704_067_200_000
_FOUR_HOURS_MS = 4 * 60 * 60 * 1000
LATER = datetime(2024, 6, 1, tzinfo=timezone.utc)
ROLES = (TimeframeRole.CONTEXT, TimeframeRole.SETUP, TimeframeRole.EXECUTION)


# =============================== helpers ====================================


def series(timeframe: str, n: int = 60, offset_hours: int = 0,
           symbol: str = "BTCUSDT") -> CandleSeries:
    """A zig-zag series that reliably produces swings, breaks and levels."""
    candles = []
    for i in range(n):
        high = 100.0 + (10.0 if i % 4 in (1, 2) else 0.0) + i * 0.7
        low = high - 5.0
        mid = (high + low) / 2
        candles.append(
            Candle(
                timestamp=_BASE + timedelta(hours=4 * i + offset_hours),
                symbol=symbol,
                timeframe=timeframe,
                open=mid, high=high, low=low, close=mid,
                volume=100.0, is_closed=True,
            )
        )
    return CandleSeries(symbol=symbol, timeframe=timeframe, candles=tuple(candles))


def sheets(counts=(60, 90, 120), offsets=(0, 24, 48), symbol="BTCUSDT"):
    """One StructuralFactSheet per role, with deliberately differing as_of."""
    return {
        role: build_structural_facts(
            series(DEFAULT_TIMEFRAMES[role], n, off, symbol), source="fixture"
        )
        for role, n, off in zip(ROLES, counts, offsets)
    }


def sheet(**kwargs) -> MultiTimeframeFactSheet:
    return build_multi_timeframe_facts(
        sheets(), intervals=DEFAULT_TIMEFRAMES, source="fixture", **kwargs
    )


def kline(i: int, close: float, *, closed: bool = True) -> list[object]:
    open_ms = _OPEN_MS + i * _FOUR_HOURS_MS
    close_ms = open_ms + _FOUR_HOURS_MS - 1
    if not closed:
        close_ms = int(datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    return [open_ms, f"{close:.8f}", f"{close * 1.01:.8f}", f"{close * 0.99:.8f}",
            f"{close:.8f}", "1000.00000000", close_ms, "1000.0", 100,
            "500.0", "500.0", "0"]


def klines(closes: list[float]) -> list[list[object]]:
    return [kline(i, c) for i, c in enumerate(closes)]


def wave(n: int) -> list[float]:
    return [100.0 + (10.0 if i % 4 in (1, 2) else 0.0) + i for i in range(n)]


def interval_transport(by_interval: dict[str, int]):
    """Transport answering per interval, so each view gets a distinct length."""
    def _transport(url: str) -> HttpResponse:
        _transport.calls.append(url)  # type: ignore[attr-defined]
        for interval, n in by_interval.items():
            if f"interval={interval}&" in url or url.endswith(f"interval={interval}"):
                return HttpResponse(status=200, body=json.dumps(klines(wave(n))).encode())
        raise AssertionError(f"unexpected interval in {url}")
    _transport.calls = []  # type: ignore[attr-defined]
    return _transport


DEFAULT_LENGTHS = {"1w": 60, "1d": 90, "4h": 120}


# ========================== composition & delegation ========================


def test_builds_a_three_view_sheet() -> None:
    s = sheet()
    assert isinstance(s, MultiTimeframeFactSheet)
    assert s.symbol == "BTCUSDT"
    assert s.source == "fixture"
    assert len(s.views) == 3


def test_views_are_in_canonical_role_order() -> None:
    assert [v.role for v in sheet().views] == list(ROLES)


def test_role_order_is_independent_of_input_order() -> None:
    forward = build_multi_timeframe_facts(sheets(), intervals=DEFAULT_TIMEFRAMES)
    reversed_input = dict(reversed(list(sheets().items())))
    backward = build_multi_timeframe_facts(reversed_input, intervals=DEFAULT_TIMEFRAMES)
    assert [v.role for v in forward.views] == [v.role for v in backward.views]
    assert forward.views == backward.views


def test_each_view_carries_its_requested_interval() -> None:
    assert sheet().intervals == ("1w", "1d", "4h")
    for view in sheet().views:
        assert view.interval == DEFAULT_TIMEFRAMES[view.role]


def test_view_interval_matches_its_sheet_interval_today() -> None:
    """Two fields, deliberately. A divergence must be visible, not silent."""
    for view in sheet().views:
        assert view.interval == view.sheet.interval


def test_delegation_equals_calling_structural_facts_directly() -> None:
    """Reuse proven, not assumed: no structural logic may be duplicated here."""
    direct = sheets()
    composed = build_multi_timeframe_facts(direct, intervals=DEFAULT_TIMEFRAMES)
    for view in composed.views:
        assert view.sheet is direct[view.role]


def test_by_role_returns_each_view() -> None:
    s = sheet()
    assert set(s.by_role) == set(ROLES)
    for role, view in s.by_role.items():
        assert view.role is role


def test_by_role_is_immutable() -> None:
    with pytest.raises(TypeError):
        sheet().by_role[TimeframeRole.CONTEXT] = None  # type: ignore[index]


def test_a_single_view_sheet_is_valid() -> None:
    only = {TimeframeRole.SETUP: sheets()[TimeframeRole.SETUP]}
    s = build_multi_timeframe_facts(only)
    assert len(s.views) == 1
    assert s.views[0].role is TimeframeRole.SETUP


def test_two_view_sheet_keeps_role_order() -> None:
    src = sheets()
    partial = {TimeframeRole.EXECUTION: src[TimeframeRole.EXECUTION],
               TimeframeRole.CONTEXT: src[TimeframeRole.CONTEXT]}
    assert [v.role for v in build_multi_timeframe_facts(partial).views] == [
        TimeframeRole.CONTEXT, TimeframeRole.EXECUTION]


# ================================ roles =====================================


def test_roles_are_never_inferred_from_the_interval() -> None:
    """A caller may map any interval to any role, and it is honoured verbatim."""
    src = sheets()
    swapped = {TimeframeRole.CONTEXT: src[TimeframeRole.EXECUTION],
               TimeframeRole.EXECUTION: src[TimeframeRole.CONTEXT]}
    s = build_multi_timeframe_facts(swapped)
    assert s.by_role[TimeframeRole.CONTEXT].sheet is src[TimeframeRole.EXECUTION]
    assert s.by_role[TimeframeRole.EXECUTION].sheet is src[TimeframeRole.CONTEXT]


def test_explicit_intervals_override_the_sheet_interval() -> None:
    src = {TimeframeRole.SETUP: sheets()[TimeframeRole.SETUP]}
    s = build_multi_timeframe_facts(src, intervals={TimeframeRole.SETUP: "240m"})
    assert s.views[0].interval == "240m"


def test_role_values_are_stable_strings() -> None:
    assert [r.value for r in ROLES] == ["context", "setup", "execution"]


def test_default_timeframes_are_the_spec_mapping() -> None:
    assert dict(DEFAULT_TIMEFRAMES) == {
        TimeframeRole.CONTEXT: "1w",
        TimeframeRole.SETUP: "1d",
        TimeframeRole.EXECUTION: "4h",
    }


def test_default_timeframes_mapping_is_immutable() -> None:
    with pytest.raises(TypeError):
        DEFAULT_TIMEFRAMES[TimeframeRole.CONTEXT] = "1M"  # type: ignore[index]


def test_role_order_is_explicit_not_definition_order() -> None:
    assert mtf_module._ROLE_ORDER == {
        TimeframeRole.CONTEXT: 0, TimeframeRole.SETUP: 1, TimeframeRole.EXECUTION: 2}


def test_rejects_a_non_role_key() -> None:
    with pytest.raises(TypeError, match="TimeframeRole"):
        build_multi_timeframe_facts({"context": sheets()[TimeframeRole.SETUP]})  # type: ignore[dict-item]


def test_rejects_a_non_sheet_value() -> None:
    with pytest.raises(TypeError, match="StructuralFactSheet"):
        build_multi_timeframe_facts({TimeframeRole.SETUP: object()})  # type: ignore[dict-item]


def test_rejects_an_empty_view_mapping() -> None:
    with pytest.raises(ValueError, match="at least one view"):
        build_multi_timeframe_facts({})


def test_rejects_views_of_different_symbols() -> None:
    src = sheets()
    src[TimeframeRole.SETUP] = build_structural_facts(series("1d", 90, 0, "ETHUSDT"))
    with pytest.raises(ValueError, match="one symbol"):
        build_multi_timeframe_facts(src)


# ===================== ADR-0020 D1 containment across views =================


def test_one_detection_settings_reaches_every_view() -> None:
    """Parsed, because the hazard is that a mismatch produces plausible output."""
    tree = ast.parse(Path(mtf_module.__file__).read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef)
              and n.name == "multi_timeframe_facts_for_symbol")
    body = "\n".join(ast.unparse(n) for n in fn.body
                     if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)))
    assert body.count("DetectionSettings()") == 1
    assert "settings = DetectionSettings() if detection is None else detection" in body
    assert "detection=settings" in body
    # ...and the loop passes that one object, never rebuilding per view.
    assert body.count("detection=") == 1


def test_the_same_settings_object_is_used_for_every_view() -> None:
    seen: list[object] = []
    original = mtf_module.structural_facts_for_symbol

    def spy(symbol, interval, **kwargs):
        seen.append(kwargs["detection"])
        return original(symbol, interval, **kwargs)

    mtf_module.structural_facts_for_symbol = spy  # type: ignore[assignment]
    try:
        settings = DetectionSettings(left_bars=3, right_bars=3)
        multi_timeframe_facts_for_symbol(
            "BTCUSDT", detection=settings,
            transport=interval_transport(DEFAULT_LENGTHS), clock=lambda: LATER)
    finally:
        mtf_module.structural_facts_for_symbol = original  # type: ignore[assignment]
    assert len(seen) == 3
    assert all(s is settings for s in seen), "views received different settings"


def test_module_defines_no_confirmation_bars_of_its_own() -> None:
    source = Path(mtf_module.__file__).read_text()
    assert "confirmation_bars" not in source.split('"""', 2)[-1]


# ======================= determinism and purity =============================


def test_two_builds_over_the_same_views_are_equal() -> None:
    src = sheets()
    a = build_multi_timeframe_facts(src, intervals=DEFAULT_TIMEFRAMES, source="fixture")
    b = build_multi_timeframe_facts(src, intervals=DEFAULT_TIMEFRAMES, source="fixture")
    assert a == b


def test_module_reads_no_clock() -> None:
    source = Path(mtf_module.__file__).read_text()
    for forbidden in ("datetime.now", "utcnow", "time.time", "time.monotonic"):
        assert forbidden not in source, forbidden


def test_module_contains_no_arithmetic_at_all() -> None:
    tree = ast.parse(Path(mtf_module.__file__).read_text())
    operators = [n for n in ast.walk(tree) if isinstance(n, ast.BinOp)
                 and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div,
                                       ast.FloorDiv, ast.Pow, ast.Mod))]
    assert operators == [], [ast.unparse(o) for o in operators]


def test_module_imports_no_maths_library() -> None:
    tree = ast.parse(Path(mtf_module.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not imported & {"math", "statistics", "decimal", "fractions", "random"}


def test_no_alignment_is_applied() -> None:
    """`fmis.alignment` serves arithmetic; nothing here computes across views.

    Asserted against *imports*, not raw text: the module docstring names
    `fmis.alignment` deliberately, to record why it is not used. A text scan
    would read that explanation as the dependency it rules out.
    """
    tree = ast.parse(Path(mtf_module.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("fmis.alignment"), node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("fmis.alignment"), alias.name


# ============================== staleness ===================================


def test_each_view_keeps_its_own_as_of() -> None:
    src = sheets()
    s = build_multi_timeframe_facts(src, intervals=DEFAULT_TIMEFRAMES)
    for view in s.views:
        assert view.sheet.as_of == src[view.role].as_of


def test_views_have_genuinely_different_as_of() -> None:
    stamps = [v.sheet.as_of for v in sheet().views]
    assert len(set(stamps)) == 3, "fixture no longer exercises differing staleness"


def test_newest_as_of_is_the_maximum_across_views() -> None:
    s = sheet()
    assert s.newest_as_of == max(v.sheet.as_of for v in s.views)


def test_newest_as_of_is_not_the_first_or_last_view_by_position() -> None:
    """Guards against reading position instead of comparing timestamps."""
    src = sheets(counts=(120, 90, 60), offsets=(48, 24, 0))
    s = build_multi_timeframe_facts(src, intervals=DEFAULT_TIMEFRAMES)
    assert s.newest_as_of == max(v.sheet.as_of for v in s.views)
    assert s.newest_as_of == s.views[0].sheet.as_of  # context happens to be newest here


# ============= no cross-timeframe synthesis (the key constraint) ============

_SYNTHESIS_TERMS = ("aligned", "alignment", "agreement", "agree", "conflict",
                    "consensus", "confluence", "divergen", "majority", "matches")


def test_the_sheet_has_no_synthesis_field() -> None:
    fields = set(MultiTimeframeFactSheet.__dataclass_fields__)
    assert fields == {"symbol", "source", "views", "newest_as_of",
                      "limitations", "metadata"}
    for term in _SYNTHESIS_TERMS:
        assert not any(term in f.lower() for f in fields), term


def test_the_sheet_exposes_no_synthesis_property() -> None:
    public = {n for n in dir(MultiTimeframeFactSheet) if not n.startswith("_")}
    for term in _SYNTHESIS_TERMS:
        assert not any(term in n.lower() for n in public), (term, public)


def test_rendered_output_contains_no_synthesis_vocabulary() -> None:
    """No synthesis word may appear where facts are reported.

    The limitations block is excluded on purpose: it is the one place that
    *describes what the sheet does not do* ("not aligned", "reconciling
    disagreement is a later layer's decision"), and those sentences are the
    guarantee, not a violation of it. `test_limitations_still_disclaim_synthesis`
    asserts they remain present, so the exclusion cannot hide their removal.
    """
    text = render_module.render_multi_timeframe_sheet(sheet())
    facts_only = text.split("LIMITATIONS OF THESE FACTS")[0].lower()
    found = {t for t in _SYNTHESIS_TERMS if t in facts_only}
    assert found == set(), found


def test_limitations_still_disclaim_synthesis() -> None:
    """Guards the exclusion above: the disclaimers must actually be rendered."""
    text = render_module.render_multi_timeframe_sheet(sheet())
    # Whitespace-normalised: the limitations block is wrapped to the page width,
    # so a phrase can straddle two lines.
    block = re.sub(r"\s+", " ", text.split("LIMITATIONS OF THESE FACTS")[1].lower())
    assert "not aligned" in block
    assert "no cross-timeframe synthesis is performed" in block
    assert "reconciling disagreement" in block


def test_rendered_output_states_nothing_is_derived() -> None:
    text = render_module.render_multi_timeframe_sheet(sheet())
    assert "Nothing is derived from the combination." in text


def test_disagreeing_trends_are_reported_without_a_verdict() -> None:
    """The SPEC §5 case: three different trends, three plain statements."""
    src = sheets()
    trends = {v: src[v].structure.trend.value for v in src}
    text = render_module.render_multi_timeframe_sheet(
        build_multi_timeframe_facts(src, intervals=DEFAULT_TIMEFRAMES))
    block = text.split("STRUCTURAL TREND BY ROLE")[1]
    for role, trend in trends.items():
        assert trend in block
    for term in ("verdict", "overall", "net ", "score"):
        assert term not in block.lower(), term


# ============================== features ====================================


def test_swing_features_adds_ema_200() -> None:
    names = [f.name for f in swing_features()]
    assert "ema_200" in names
    assert names[:-1] == [f.name for f in default_features()]


def test_default_features_is_unchanged_by_this_milestone() -> None:
    """Regression: AG must not alter what `analyze_symbol` computes."""
    assert [f.name for f in default_features()] == [
        "ema_20", "ema_50", "rsi_close_14", "atr_14",
        "macd_close_12_26_9", "relative_volume_20"]
    assert "ema_200" not in {f.name for f in default_features()}


def test_swing_features_returns_fresh_instances() -> None:
    first, second = swing_features(), swing_features()
    assert [f.name for f in first] == [f.name for f in second]
    assert all(a is not b for a, b in zip(first, second))


def test_swing_features_is_the_default_for_the_network_edge() -> None:
    s = multi_timeframe_facts_for_symbol(
        "BTCUSDT", transport=interval_transport({"1w": 260, "1d": 260, "4h": 260}),
        clock=lambda: LATER)
    for view in s.views:
        assert "ema_200" in view.sheet.features.features


def test_explicit_features_override_the_default() -> None:
    s = multi_timeframe_facts_for_symbol(
        "BTCUSDT", features=[ExponentialMovingAverage(5)],
        transport=interval_transport(DEFAULT_LENGTHS), clock=lambda: LATER)
    for view in s.views:
        assert set(view.sheet.features.features) == {"ema_5"}


# ============================ network edge ==================================


def test_fetches_one_view_per_role() -> None:
    transport = interval_transport(DEFAULT_LENGTHS)
    s = multi_timeframe_facts_for_symbol("BTCUSDT", transport=transport,
                                         clock=lambda: LATER)
    assert len(s.views) == 3
    assert len(transport.calls) == 3
    for interval in ("1w", "1d", "4h"):
        assert any(f"interval={interval}" in c for c in transport.calls)


def test_source_is_recorded_as_the_provider() -> None:
    s = multi_timeframe_facts_for_symbol(
        "BTCUSDT", transport=interval_transport(DEFAULT_LENGTHS), clock=lambda: LATER)
    assert s.source == "binance-spot"
    for view in s.views:
        assert view.sheet.source == "binance-spot"


def test_request_provenance_is_recorded() -> None:
    s = multi_timeframe_facts_for_symbol(
        "BTCUSDT", limit=120, transport=interval_transport(DEFAULT_LENGTHS),
        clock=lambda: LATER)
    assert s.metadata["requested_limit"] == 120
    assert s.metadata["requested_timeframes"] == (
        ("context", "1w"), ("setup", "1d"), ("execution", "4h"))


def test_custom_timeframes_are_honoured() -> None:
    transport = interval_transport({"1d": 90, "4h": 120, "1h": 150})
    s = multi_timeframe_facts_for_symbol(
        "BTCUSDT",
        timeframes={TimeframeRole.CONTEXT: "1d", TimeframeRole.SETUP: "4h",
                    TimeframeRole.EXECUTION: "1h"},
        transport=transport, clock=lambda: LATER)
    assert s.intervals == ("1d", "4h", "1h")


def test_a_short_timeframe_raises_and_returns_nothing() -> None:
    """Nothing partial: one failing view fails the whole sheet."""
    transport = interval_transport({"1w": 60, "1d": 3, "4h": 120})
    with pytest.raises(InsufficientDataError):
        multi_timeframe_facts_for_symbol("BTCUSDT", transport=transport,
                                         clock=lambda: LATER)


def test_no_partial_sheet_escapes_on_failure() -> None:
    transport = interval_transport({"1w": 60, "1d": 3, "4h": 120})
    result = None
    try:
        result = multi_timeframe_facts_for_symbol(
            "BTCUSDT", transport=transport, clock=lambda: LATER)
    except InsufficientDataError:
        pass
    assert result is None


def test_rejects_an_empty_timeframe_mapping() -> None:
    with pytest.raises(ValueError, match="at least one"):
        multi_timeframe_facts_for_symbol("BTCUSDT", timeframes={})


def test_rejects_a_non_role_timeframe_key() -> None:
    with pytest.raises(TypeError, match="TimeframeRole"):
        multi_timeframe_facts_for_symbol("BTCUSDT", timeframes={"1d": "1d"})  # type: ignore[dict-item]


def test_views_equal_individually_fetched_sheets() -> None:
    """The composed view must equal the single-timeframe call, field for field."""
    transport = interval_transport(DEFAULT_LENGTHS)
    settings = DetectionSettings()
    composed = multi_timeframe_facts_for_symbol(
        "BTCUSDT", detection=settings, transport=transport, clock=lambda: LATER)
    direct = structural_facts_for_symbol(
        "BTCUSDT", "1d", features=swing_features(), detection=settings,
        transport=interval_transport(DEFAULT_LENGTHS), clock=lambda: LATER)
    setup = composed.by_role[TimeframeRole.SETUP].sheet
    assert setup.structure.swings == direct.structure.swings
    assert setup.structure.breaks == direct.structure.breaks
    assert setup.window == direct.window


# ============================ immutability ==================================


def test_sheet_is_frozen() -> None:
    with pytest.raises(Exception):
        sheet().symbol = "OTHER"  # type: ignore[misc]


def test_view_is_frozen() -> None:
    with pytest.raises(Exception):
        sheet().views[0].role = TimeframeRole.SETUP  # type: ignore[misc]


def test_metadata_is_immutable_and_copied() -> None:
    supplied = {"a": 1}
    s = build_multi_timeframe_facts(sheets(), metadata=supplied)
    supplied["a"] = 999
    assert s.metadata["a"] == 1
    with pytest.raises(TypeError):
        s.metadata["b"] = 2  # type: ignore[index]


def test_views_is_a_tuple() -> None:
    assert isinstance(sheet().views, tuple)


def test_view_rejects_bad_types() -> None:
    good = sheets()[TimeframeRole.SETUP]
    with pytest.raises(TypeError, match="role"):
        TimeframeView(role="context", interval="1d", sheet=good)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="interval"):
        TimeframeView(role=TimeframeRole.SETUP, interval="", sheet=good)
    with pytest.raises(TypeError, match="sheet"):
        TimeframeView(role=TimeframeRole.SETUP, interval="1d", sheet=None)  # type: ignore[arg-type]


def test_sheet_rejects_duplicate_roles_and_bad_order() -> None:
    src = sheets()
    views = tuple(TimeframeView(TimeframeRole.SETUP, "1d", s) for s in src.values())
    with pytest.raises(ValueError, match="once"):
        MultiTimeframeFactSheet(symbol="BTCUSDT", source="x", views=views,
                                newest_as_of=_BASE, limitations=())
    ordered = sheet().views
    with pytest.raises(ValueError, match="ordered"):
        MultiTimeframeFactSheet(symbol="BTCUSDT", source="x",
                                views=tuple(reversed(ordered)),
                                newest_as_of=_BASE, limitations=())


def test_sheet_rejects_empty_views_when_constructed_directly() -> None:
    """The model is public, so its own guard must hold independently.

    `build_multi_timeframe_facts` rejects an empty mapping first, which made the
    dataclass guard unreachable through the public path — a mutation probe that
    deleted it survived on exactly that. A caller holding the model can bypass
    the factory, so the guard is real and is tested where it lives.
    """
    with pytest.raises(ValueError, match="at least one view"):
        MultiTimeframeFactSheet(
            symbol="BTCUSDT", source="x", views=(),
            newest_as_of=_BASE, limitations=())


def test_sheet_rejects_a_symbol_mismatch() -> None:
    with pytest.raises(ValueError, match="every view must be for"):
        MultiTimeframeFactSheet(symbol="ETHUSDT", source="x", views=sheet().views,
                                newest_as_of=_BASE, limitations=())


# ============================= limitations ==================================


def test_limitations_are_inherited_plus_three() -> None:
    s = sheet()
    assert s.limitations == (*LIMITATIONS, *MULTI_TIMEFRAME_LIMITATIONS)
    assert len(s.limitations) == len(LIMITATIONS) + 3


def test_the_three_new_limitation_codes_are_present() -> None:
    codes = {l.code for l in sheet().limitations}
    assert {"AG-1", "AG-2", "AG-3"} <= codes
    assert "ADR-0019 D2" in codes
    # Inherited from AF, which dropped ADR-0020 D1 in Milestone AH.
    assert "ADR-0020 D1" not in codes


def test_ag2_states_no_synthesis_is_performed() -> None:
    text = next(l.text for l in MULTI_TIMEFRAME_LIMITATIONS if l.code == "AG-2")
    assert "No cross-timeframe synthesis is performed" in text


def test_ag1_states_views_are_not_aligned() -> None:
    text = next(l.text for l in MULTI_TIMEFRAME_LIMITATIONS if l.code == "AG-1")
    assert "not aligned" in text and "own as-of" in text


def test_limitation_texts_end_in_a_full_stop() -> None:
    for limitation in MULTI_TIMEFRAME_LIMITATIONS:
        assert limitation.text.endswith(".")


# ============================== renderer ====================================


def test_render_is_deterministic() -> None:
    s = sheet()
    assert (render_module.render_multi_timeframe_sheet(s)
            == render_module.render_multi_timeframe_sheet(s))


def test_render_includes_a_block_per_role() -> None:
    text = render_module.render_multi_timeframe_sheet(sheet())
    for role, interval in DEFAULT_TIMEFRAMES.items():
        assert f"{role.value.upper()} · {interval}" in text
    # Each header must be its own rule line, so a generic header cannot pass.
    headers = [l for l in text.splitlines() if l.startswith("── ") and "·" in l]
    assert len(headers) == 3, headers


def test_render_shows_each_views_own_as_of() -> None:
    s = sheet()
    text = render_module.render_multi_timeframe_sheet(s)
    for view in s.views:
        assert view.sheet.as_of.isoformat() in text


def test_render_shows_per_view_age_against_a_reference() -> None:
    s = sheet()
    text = render_module.render_multi_timeframe_sheet(
        s, reference_time=s.newest_as_of + timedelta(hours=2))
    assert text.count("age ") >= 3


def test_render_states_newest_data_is_not_a_shared_instant() -> None:
    text = render_module.render_multi_timeframe_sheet(sheet())
    assert "not a shared instant" in text
    assert sheet().newest_as_of.isoformat() in text


def test_render_shows_each_views_trend_value() -> None:
    s = sheet()
    block = render_module.render_multi_timeframe_sheet(s).split(
        "STRUCTURAL TREND BY ROLE")[1]
    for view in s.views:
        assert view.sheet.structure.trend.value in block
        assert f"{view.role.value} · {view.interval}" in block


def test_render_shows_each_views_last_close() -> None:
    s = sheet()
    text = render_module.render_multi_timeframe_sheet(s)
    for view in s.views:
        assert f"{view.sheet.window.last_close:,.2f}" in text


def test_render_shows_ema_200_when_present() -> None:
    src = {r: build_structural_facts(series(DEFAULT_TIMEFRAMES[r], 260, o),
                                     features=swing_features())
           for r, o in zip(ROLES, (0, 24, 48))}
    text = render_module.render_multi_timeframe_sheet(
        build_multi_timeframe_facts(src, intervals=DEFAULT_TIMEFRAMES))
    assert "ema_200" in text


def test_render_marks_warming_up_features() -> None:
    src = {r: build_structural_facts(series(DEFAULT_TIMEFRAMES[r], 30, 0),
                                     features=swing_features())
           for r in ROLES}
    text = render_module.render_multi_timeframe_sheet(
        build_multi_timeframe_facts(src, intervals=DEFAULT_TIMEFRAMES))
    line = next(l for l in text.splitlines() if l.strip().startswith("ema_200"))
    assert "warming up" in line and "—" in line


def test_render_shows_a_change_of_character_when_one_exists() -> None:
    """The MTF change branch was reached by no fixture until the review.

    `choch_series` is imported from the AF suite rather than duplicated: it is a
    committed walk found by search, and the zig-zag used elsewhere in this file
    produces zero changes of character. Copying ninety float literals into a
    second file would be two fixtures to keep true instead of one.
    """
    from test_structural_facts import choch_series

    src = {role: build_structural_facts(choch_series()) for role in ROLES}
    s = build_multi_timeframe_facts(src)
    latest = s.views[0].sheet.structure.latest_change
    assert latest is not None, "fixture no longer exercises the CHoCH path"
    line = next(
        l for l in render_module.render_multi_timeframe_sheet(s).splitlines()
        if l.strip().startswith("Change of character")
    )
    assert f"{latest.side.value} @ bar {latest.index}" in line
    assert latest.timestamp.isoformat() in line
    assert "none in this window" not in line


def test_render_shows_absent_structure_on_a_flat_view() -> None:
    """A view with no labelled swing and no break renders both as absent."""
    flat = CandleSeries(
        symbol="BTCUSDT", timeframe="1d",
        candles=tuple(
            Candle(timestamp=_BASE + timedelta(hours=4 * i), symbol="BTCUSDT",
                   timeframe="1d", open=100.0 + i, high=100.0 + i, low=95.0 + i,
                   close=100.0 + i, volume=100.0, is_closed=True)
            for i in range(12)
        ),
    )
    view = build_structural_facts(flat)
    assert view.structure.labelled == ()
    assert view.structure.latest_break is None
    text = render_module.render_multi_timeframe_sheet(
        build_multi_timeframe_facts({TimeframeRole.SETUP: view}))
    label_line = next(l for l in text.splitlines()
                      if l.strip().startswith("Latest label"))
    break_line = next(l for l in text.splitlines()
                      if l.strip().startswith("Break of structure"))
    assert "no labelled swing yet" in label_line and "—" in label_line
    assert "none in this window" in break_line and "—" in break_line


def test_render_includes_all_limitations() -> None:
    text = render_module.render_multi_timeframe_sheet(sheet())
    for code in ("ADR-0019 D2", "AG-1", "AG-2", "AG-3"):
        assert f"[{code}]" in text
    assert "[ADR-0020 D1]" not in text


def test_render_carries_the_disclaimer() -> None:
    text = render_module.render_multi_timeframe_sheet(sheet())
    assert "measurements, not conclusions" in text
    assert "recommendation is expressed or implied" in text


# ====================== fact-only vocabulary ================================

_FORBIDDEN = ("buy", "sell", "long", "short", "bullish", "bearish", "support",
              "resistance", "signal", "recommend", "entry", "target",
              "confidence", "score")
_ALLOWED = ("signal_line",)
_DISCLAIMER = "recommendation is expressed or implied"


def _forbidden_words(text: str) -> set[str]:
    lowered = text.lower()
    for allowed in _ALLOWED:
        lowered = lowered.replace(allowed, "")
    lowered = lowered.replace(_DISCLAIMER, "")
    return {w for w in _FORBIDDEN if re.search(rf"\b{w}\w*\b", lowered)}


def test_rendered_sheet_contains_no_interpretation_vocabulary() -> None:
    assert _forbidden_words(
        render_module.render_multi_timeframe_sheet(sheet())) == set()


def test_new_limitation_texts_are_fact_only() -> None:
    for limitation in MULTI_TIMEFRAME_LIMITATIONS:
        assert _forbidden_words(limitation.text) == set(), limitation.code


# ================================ CLI =======================================


def test_registry_names_are_unique() -> None:
    # Widened for Milestone AV to admit "backtest".
    names = [c.name for c in cli_module.COMMANDS]
    assert len(names) == len(set(names))
    assert set(names) == {
        "facts", "mtf", "regime", "swing", "setup", "scan", "backtest", "daily", "archive",
    }


def test_every_registered_command_is_reachable_from_the_parser() -> None:
    parser = cli_module.build_parser()
    action = next(a for a in parser._actions if a.dest == "command")
    assert set(action.choices) == {c.name for c in cli_module.COMMANDS}


def test_every_registered_command_has_a_runner() -> None:
    for command in cli_module.COMMANDS:
        assert callable(command.run)
        assert callable(command.configure)


def test_mtf_parser_defaults() -> None:
    args = cli_module.build_parser().parse_args(["mtf", "BTCUSDT"])
    assert args.command == "mtf"
    assert (args.context, args.setup, args.execution) == ("1w", "1d", "4h")
    assert args.left_bars == DEFAULT_LEFT_BARS
    assert args.right_bars == DEFAULT_RIGHT_BARS


def test_mtf_parser_accepts_role_overrides() -> None:
    args = cli_module.build_parser().parse_args(
        ["mtf", "ETHUSDT", "--context", "1M", "--setup", "1w", "--execution", "1d"])
    assert (args.context, args.setup, args.execution) == ("1M", "1w", "1d")


def test_facts_parser_still_works() -> None:
    args = cli_module.build_parser().parse_args(["facts", "BTCUSDT", "-i", "1d"])
    assert args.command == "facts" and args.interval == "1d"


def test_main_runs_mtf_and_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    s = sheet()
    monkeypatch.setattr(cli_module, "multi_timeframe_facts_for_symbol",
                        lambda *a, **k: s)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli_module.main(["mtf", "BTCUSDT", "--no-age"])
    assert code == cli_module.EXIT_OK
    out = buffer.getvalue()
    assert "MULTI-TIMEFRAME FACT SHEET" in out
    assert "CONTEXT · 1w" in out and "EXECUTION · 4h" in out


def test_main_forwards_role_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake(symbol, **kwargs):
        seen.update(kwargs, symbol=symbol)
        return sheet()

    monkeypatch.setattr(cli_module, "multi_timeframe_facts_for_symbol", fake)
    with redirect_stdout(io.StringIO()):
        cli_module.main(["mtf", "ETHUSDT", "--context", "1M", "--right-bars", "3"])
    assert seen["symbol"] == "ETHUSDT"
    assert seen["timeframes"][TimeframeRole.CONTEXT] == "1M"
    assert seen["detection"] == DetectionSettings(left_bars=2, right_bars=3)


def test_main_mtf_returns_failure_on_insufficient_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raiser(*a, **k):
        raise InsufficientDataError(subject="BTCUSDT 1w", required=5,
                                    fetched=2, closed=2)

    monkeypatch.setattr(cli_module, "multi_timeframe_facts_for_symbol", raiser)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli_module.main(["mtf", "BTCUSDT", "--no-age"])
    assert code == cli_module.EXIT_FAILURE
    assert "InsufficientDataError" in buffer.getvalue()


def test_main_mtf_omits_age_with_no_age(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "multi_timeframe_facts_for_symbol",
                        lambda *a, **k: sheet())
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli_module.main(["mtf", "BTCUSDT", "--no-age"])
    assert "age " not in buffer.getvalue()


def test_main_mtf_shows_age_with_a_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    s = sheet()
    monkeypatch.setattr(cli_module, "multi_timeframe_facts_for_symbol",
                        lambda *a, **k: s)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli_module.main(["mtf", "BTCUSDT", "--reference-time",
                         s.newest_as_of.isoformat()])
    assert "age " in buffer.getvalue()


def test_cli_defines_no_market_arithmetic() -> None:
    tree = ast.parse(Path(cli_module.__file__).read_text())
    ops = [n for n in ast.walk(tree) if isinstance(n, ast.BinOp)
           and isinstance(n.op, (ast.Mult, ast.Div, ast.FloorDiv, ast.Pow, ast.Mod))]
    assert ops == [], [ast.unparse(o) for o in ops]


# =========================== architectural guards ===========================


def test_no_engine_imports_the_multi_timeframe_root() -> None:
    """No **engine** imports the application layer. The workspace is not one.

    Widened for Milestone AK for the same reason as the fact-sheet root:
    `fmis.workspace` is above `fmis.pipeline`, and composing this root is what
    it exists to do.
    Widened again for Milestone AN: `fmis.daily` is a second application-layer
    root, above the workspace, and running the same analysis across a universe is
    what it exists to do. The guard's direction is unchanged — an engine still
    may not reach upward — and every engine remains covered.

    Widened again for Milestone AR: `fmis.swing_setup` is a third
    application-layer root, at the same tier as the workspace (ADR-0028),
    fetching the same multi-timeframe sheet through the identical composition
    root. The direction is still unchanged.
    """
    root = Path(mtf_module.__file__).parent.parent
    above = {"pipeline", "workspace", "daily", "swing_setup"}
    for path in root.rglob("*.py"):
        if above & set(path.parts) or "__pycache__" in path.parts:
            continue
        assert "multi_timeframe" not in path.read_text(), path


def test_importing_an_engine_does_not_load_it(fresh_fmis_imports: None) -> None:
    import fmis.market_structure  # noqa: F401

    assert not any(m.startswith("fmis.pipeline") for m in sys.modules)


def test_it_reaches_no_engine_directly() -> None:
    """AG composes `structural_facts`; it must not call an engine itself."""
    tree = ast.parse(Path(mtf_module.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)
    engines = {m for m in imported if m.startswith("fmis.")
               and not m.startswith("fmis.pipeline")}
    assert engines <= {"fmis.features.indicators.ema", "fmis.features.types",
                       "fmis.providers.binance"}, engines


def test_it_reaches_no_foreign_private_module() -> None:
    tree = ast.parse(Path(mtf_module.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "._" not in node.module, node.module


def test_public_surface_is_exported() -> None:
    for name in ("build_multi_timeframe_facts", "multi_timeframe_facts_for_symbol",
                 "render_multi_timeframe_sheet", "MultiTimeframeFactSheet",
                 "TimeframeRole", "TimeframeView", "swing_features",
                 "DEFAULT_TIMEFRAMES"):
        assert name in pipeline.__all__
        assert hasattr(pipeline, name)


def test_structural_facts_was_not_modified_by_this_milestone() -> None:
    """AG consumes AF; it must not have edited it."""
    source = Path(mtf_module.__file__).parent.joinpath("structural_facts.py").read_text()
    assert "multi_timeframe" not in source
    assert "TimeframeRole" not in source
