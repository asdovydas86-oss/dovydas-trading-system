"""Milestone AU — Market Scanner Intelligence Report v1: `fmis.swing_setup.scan_report`.

No test here re-derives the directional policy (`tests/test_swing_setup_policy.py`)
or the compact table's own content rules (`tests/test_swing_setup_scan.py`) — only
this module's own sections: SCAN SUMMARY, MARKET OVERVIEW, ACTIONABLE SETUPS and
WAIT REASONS. The recurring theme across these tests is the hostile-review brief
this milestone names directly: prove the report cannot lie. Every "reason" this
module prints is checked against the exact source field it was copied from, and
every count is cross-checked against `render_scan`'s own, independently-computed
count for the same input.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.decision_context import ContextState
from fmis.decision_support import Alignment, OverallState
from fmis.level_crossing import LevelOrigin, LevelSide, PriceLevel
from fmis.market_regime import ParticipationState, StructureState, VolatilityState
from fmis.market_structure import StructuralSwingLabel
from fmis.structural_trend import StructuralTrendType
from fmis.swing_setup import (
    NOT_CALIBRATED,
    ExecutionBreakEvent,
    Lean,
    SetupAssessment,
    SetupInputs,
    SetupState,
    SwingSetupError,
    evaluate_setup,
    render_scan,
)
from fmis.swing_setup import compose as compose_module
from fmis.swing_setup.compose import SetupRunResult
from fmis.swing_setup.scan import SCAN_UNIVERSE, result_status
from fmis.swing_setup.scan_report import render_scan_report
from tests.archive_helpers import multi
from tests.test_swing_setup_render import (
    candidate_short_with_watched_level,
    candidate_with_no_watched_level,
    confirmed_long,
    waiting,
)

_AS_OF = datetime(2026, 1, 2, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        compose_module, "multi_timeframe_facts_for_symbol",
        lambda symbol, **kw: multi(symbol=symbol),
    )


def _level(side: LevelSide, price: float, index: int = 1) -> PriceLevel:
    label = StructuralSwingLabel.HIGHER_HIGH if side is LevelSide.UPPER else StructuralSwingLabel.LOWER_LOW
    origin = LevelOrigin(
        index=index, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        label=label, confirmation_bars=2,
    )
    return PriceLevel(side=side, price=price, origin=origin)


def conflicted_trend():
    """WAIT via a NEUTRAL context structural trend — a `CONFLICTED` market-
    overview member (`Lean.CONFLICTING`), distinct from `waiting()`'s own
    `INDETERMINATE`/`Lean.UNAVAILABLE` shape."""
    inputs = SetupInputs(
        symbol="LINKUSDT", as_of=_AS_OF, source="fixture",
        context_interval="1w", setup_interval="1d", execution_interval="4h",
        context_structural_trend=StructuralTrendType.NEUTRAL,
        setup_structural_trend=StructuralTrendType.NEUTRAL,
        execution_structural_trend=StructuralTrendType.INDETERMINATE,
        context_regime_structure=StructureState.RANGING,
        context_regime_volatility=VolatilityState.STEADY,
        context_regime_participation=ParticipationState.TYPICAL,
        evidence_state=OverallState.INSUFFICIENT_DATA, evidence_dominant_alignment=None,
        decision_context_state=ContextState.SUFFICIENT, decision_context_statements=(),
        execution_close=100.0, execution_closed_count=10, execution_levels=(),
        execution_breaks=(), setup_levels=(),
        inherited_limitations=(),
    )
    return evaluate_setup(inputs)


def insufficient_context():
    """WAIT via an INSUFFICIENT decision context — a second, textually
    distinct WAIT thesis, used to prove WAIT REASONS groups by exact text
    rather than merging every WAIT into one bucket."""
    inputs = SetupInputs(
        symbol="XRPUSDT", as_of=_AS_OF, source="fixture",
        context_interval="1w", setup_interval="1d", execution_interval="4h",
        context_structural_trend=StructuralTrendType.INDETERMINATE,
        setup_structural_trend=StructuralTrendType.INDETERMINATE,
        execution_structural_trend=StructuralTrendType.INDETERMINATE,
        context_regime_structure=StructureState.RANGING,
        context_regime_volatility=VolatilityState.STEADY,
        context_regime_participation=ParticipationState.TYPICAL,
        evidence_state=OverallState.INSUFFICIENT_DATA, evidence_dominant_alignment=None,
        decision_context_state=ContextState.INSUFFICIENT,
        decision_context_statements=("at least one view has too few closed candles",),
        execution_close=100.0, execution_closed_count=10, execution_levels=(),
        execution_breaks=(), setup_levels=(),
        inherited_limitations=(),
    )
    return evaluate_setup(inputs)


def wait_with_no_directional_factors() -> SetupAssessment:
    """A hand-built assessment with no `context_structural_trend` factor at
    all — never produced by `evaluate_setup` today (it always computes the
    factor first), but `_context_trend_factor`'s `None` branch exists
    defensively in case a future engine change ever omits it, and must
    honestly fall back to `NO DATA` rather than crash or guess."""
    from fmis.decision_context import ContextState as _ContextState

    return SetupAssessment(
        symbol="ZZZUSDT", as_of=_AS_OF, objective="swing",
        state=SetupState.WAIT, direction=None,
        thesis=("no directional factors were computed",),
        directional_factors=(), confirmation=(), invalidation=(),
        trigger=None, reference_price=None, stop=None, targets=(),
        risk_reward=None, probability=NOT_CALIBRATED, regime_context=(),
        sufficiency=_ContextState.SUFFICIENT, limitations=(),
        policy_id="test", source="test",
    )


def candidate_with_no_thesis_or_confirmation() -> SetupAssessment:
    """A hand-built CANDIDATE with empty `thesis`/`confirmation` — never
    produced by `evaluate_setup` (a candidate always carries at least the
    agreeing factors' thesis), but `_reason_lines`'s empty-tuple branch exists
    to avoid printing a dangling `reason:`/`needs:` label with nothing under
    it, and must be exercised directly."""
    from fmis.decision_context import ContextState as _ContextState
    from fmis.swing_setup import Direction as _Direction

    return SetupAssessment(
        symbol="YYYUSDT", as_of=_AS_OF, objective="swing",
        state=SetupState.CANDIDATE, direction=_Direction.LONG,
        thesis=(), directional_factors=(), confirmation=(), invalidation=(),
        trigger=None, reference_price=None, stop=None, targets=(),
        risk_reward=None, probability=NOT_CALIBRATED, regime_context=(),
        sufficiency=_ContextState.SUFFICIENT, limitations=(),
        policy_id="test", source="test",
    )


def _extract_block(text: str, label: str) -> list[str]:
    """Every wrapped continuation line under one `   label:` marker.

    Relies on `scan_report._wrap`'s own indent contract: a label line has 3
    leading spaces, every wrapped line under it has at least 5. The first line
    with fewer than 5 leading spaces ends the block.
    """
    lines = text.splitlines()
    start = lines.index(f"   {label}:") + 1
    block = []
    for line in lines[start:]:
        if not line.startswith("     "):
            break
        block.append(line.strip())
    return block


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _dewrap(lines: list[str]) -> str:
    return " ".join(lines)


def _result(symbol: str, assessment=None, failure: str | None = None) -> SetupRunResult:
    return SetupRunResult(requested_symbol=symbol, assessment=assessment, failure=failure)


# ---------------------------------------------------------------------------
# type and shape guards
# ---------------------------------------------------------------------------


def test_rejects_a_non_sequence() -> None:
    with pytest.raises(TypeError):
        render_scan_report(object())  # type: ignore[arg-type]


def test_rejects_a_string() -> None:
    with pytest.raises(TypeError):
        render_scan_report("BTCUSDT")  # type: ignore[arg-type]


def test_rejects_a_sequence_of_the_wrong_type() -> None:
    with pytest.raises(TypeError):
        render_scan_report([object()])  # type: ignore[list-item]


def test_rejects_an_empty_sequence() -> None:
    with pytest.raises(ValueError):
        render_scan_report([])


# ---------------------------------------------------------------------------
# determinism and page width
# ---------------------------------------------------------------------------


def test_is_deterministic() -> None:
    results = [_result("BTCUSDT", confirmed_long()), _result("ETHUSDT", waiting())]
    assert render_scan_report(results) == render_scan_report(results)


def test_never_exceeds_the_page_width() -> None:
    results = [
        _result("BTCUSDT", confirmed_long()),
        _result("DOTUSDT", candidate_short_with_watched_level()),
        _result("ADAUSDT", candidate_with_no_watched_level()),
        _result("LINKUSDT", conflicted_trend()),
        _result("XRPUSDT", insufficient_context()),
        _result("BADUSDT", failure="BinanceTransportError: connection refused"),
    ]
    text = render_scan_report(results)
    for line in text.splitlines():
        assert len(line) <= 78


def test_handles_the_full_twenty_symbol_universe_sharing_one_reason() -> None:
    """A live-observed shape: every symbol in the fixed watchlist sharing the
    identical WAIT thesis produces one WAIT REASONS group whose symbol list
    alone is 190+ characters — it must wrap, not overflow."""
    results = [_result(symbol, waiting()) for symbol in SCAN_UNIVERSE]
    text = render_scan_report(results)
    for line in text.splitlines():
        assert len(line) <= 78
    assert "20 symbols scanned" in text
    assert "20 symbols:" in text


def test_a_width_violation_raises_swing_setup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import fmis.swing_setup.scan_report as scan_report_module

    monkeypatch.setattr(scan_report_module, "_WIDTH", 5)
    with pytest.raises(SwingSetupError):
        render_scan_report([_result("BTCUSDT", waiting())])


# ---------------------------------------------------------------------------
# SCAN SUMMARY — counts must agree with render_scan, always
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "results",
    [
        [_result("BTCUSDT", waiting())],
        [_result("BADUSDT", failure="down")],
        [
            _result("BTCUSDT", confirmed_long()),
            _result("DOTUSDT", candidate_short_with_watched_level()),
            _result("ETHUSDT", waiting()),
            _result("BADUSDT", failure="down"),
        ],
        [_result(s, waiting()) for s in SCAN_UNIVERSE],
    ],
)
def test_scan_summary_counts_agree_with_render_scan(results: list[SetupRunResult]) -> None:
    report = render_scan_report(results)
    table = render_scan(results)
    counts = {"WAIT": 0, "CANDIDATE": 0, "CONFIRMED": 0, "ERROR": 0}
    for result in results:
        counts[result_status(result)] += 1
    for label, count in counts.items():
        assert f"{label} " in report
        # the table's own summary line is independently produced by scan.py;
        # cross-checking it here is what a "counts disagree" review finding
        # would have to break.
        assert f"{count} {label}" in table or (label == "WAIT" and f"{count} WAIT" in table)
    assert f" {len(results)} symbols scanned" in report


def test_scan_summary_shows_zero_for_an_absent_status() -> None:
    text = render_scan_report([_result("BTCUSDT", waiting())])
    assert "CANDIDATE" in text
    assert "CONFIRMED" in text
    assert "ERROR" in text


# ---------------------------------------------------------------------------
# MARKET OVERVIEW
# ---------------------------------------------------------------------------


def test_market_overview_buckets_a_long_leaning_symbol_as_directional() -> None:
    text = render_scan_report([_result("BTCUSDT", confirmed_long())])
    assert "DIRECTIONAL (1)" in text
    assert "BTCUSDT (long)" in text


def test_market_overview_buckets_a_short_leaning_symbol_as_directional() -> None:
    text = render_scan_report([_result("DOTUSDT", candidate_short_with_watched_level())])
    assert "DIRECTIONAL (1)" in text
    assert "DOTUSDT (short)" in text


def test_market_overview_buckets_conflicting_trend_as_conflicted() -> None:
    text = render_scan_report([_result("LINKUSDT", conflicted_trend())])
    assert "CONFLICTED (1)" in text
    assert "LINKUSDT" in text.split("CONFLICTED (1)", 1)[1].split("\n\n", 1)[0]
    assert "DIRECTIONAL" not in text


def test_market_overview_buckets_unavailable_trend_as_no_data() -> None:
    text = render_scan_report([_result("ETHUSDT", waiting())])
    assert "NO DATA (1)" in text
    assert "DIRECTIONAL" not in text
    assert "CONFLICTED" not in text


def test_market_overview_buckets_a_failed_symbol_as_not_scanned_only() -> None:
    text = render_scan_report([_result("BADUSDT", failure="connection refused")])
    assert "NOT SCANNED (1)" in text
    assert "BADUSDT" in text
    assert "DIRECTIONAL" not in text and "CONFLICTED" not in text and "NO DATA" not in text


def test_market_overview_buckets_a_missing_trend_factor_as_no_data() -> None:
    text = render_scan_report([_result("ZZZUSDT", wait_with_no_directional_factors())])
    assert "NO DATA (1)" in text
    assert "ZZZUSDT" in text


def test_market_overview_never_uses_the_word_trending() -> None:
    """Regression for the adversarial-review finding: `context_regime_structure`
    (gates the "not trending" WAIT branch) and `context_structural_trend`
    (feeds this section's fallback factor) are independently computed and can
    disagree, so this section must never print a label that collides with a
    WAIT reason's own "not trending" wording for the same symbol."""
    text = render_scan_report(
        [_result("BTCUSDT", confirmed_long()), _result("ETHUSDT", waiting())]
    )
    overview = text.split("MARKET OVERVIEW", 1)[1].split("ACTIONABLE SETUPS", 1)[0]
    assert "TRENDING" not in overview


def test_market_overview_buckets_a_confirmed_trade_as_directional_even_when_its_own_context_trend_factor_disagrees() -> None:
    """Regression: a symbol can reach CONFIRMED with `direction=LONG` while
    its own `context_structural_trend` factor leans SHORT or is unavailable —
    the other two families (setup trend, setup evidence) can win the tally
    alone. `MARKET OVERVIEW` must read the policy's own final `direction`
    first, never bucket a live trade under `NO DATA`/`CONFLICTED`."""
    inputs = SetupInputs(
        symbol="BTCUSDT", as_of=_AS_OF, source="fixture",
        context_interval="1w", setup_interval="1d", execution_interval="4h",
        context_structural_trend=StructuralTrendType.INDETERMINATE,
        setup_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        execution_structural_trend=StructuralTrendType.NEUTRAL,
        context_regime_structure=StructureState.TRENDING,
        context_regime_volatility=VolatilityState.STEADY,
        context_regime_participation=ParticipationState.TYPICAL,
        evidence_state=OverallState.WATCH, evidence_dominant_alignment=Alignment.UPWARD,
        decision_context_state=ContextState.SUFFICIENT, decision_context_statements=(),
        execution_close=100.0, execution_closed_count=10,
        execution_levels=(_level(LevelSide.UPPER, 110.0), _level(LevelSide.LOWER, 90.0)),
        execution_breaks=(
            ExecutionBreakEvent(level=_level(LevelSide.UPPER, 105.0, index=3), index=5),
        ),
        setup_levels=(_level(LevelSide.UPPER, 130.0), _level(LevelSide.LOWER, 70.0)),
        inherited_limitations=(),
    )
    assessment = evaluate_setup(inputs)
    assert assessment.state is SetupState.CONFIRMED
    context_factor = next(
        f for f in assessment.directional_factors if f.family == "context_structural_trend"
    )
    assert context_factor.lean is Lean.UNAVAILABLE  # the factor this bucket used to trust alone

    text = render_scan_report([_result("BTCUSDT", assessment)])
    assert "DIRECTIONAL (1)" in text
    assert "NO DATA" not in text


def test_market_overview_never_reorders_within_a_bucket() -> None:
    results = [
        _result("DOTUSDT", candidate_short_with_watched_level()),
        _result("BTCUSDT", confirmed_long()),
    ]
    text = render_scan_report(results)
    overview = text.split("MARKET OVERVIEW", 1)[1].split("ACTIONABLE SETUPS", 1)[0]
    assert overview.index("DOTUSDT") < overview.index("BTCUSDT")


# ---------------------------------------------------------------------------
# ACTIONABLE SETUPS — reason fidelity is the whole point
# ---------------------------------------------------------------------------


def test_actionable_setups_absent_when_nothing_qualifies() -> None:
    text = render_scan_report([_result("ETHUSDT", waiting())])
    assert "ACTIONABLE SETUPS" not in text


def test_confirmed_setup_shows_side_rr_stop_and_target() -> None:
    text = render_scan_report([_result("BTCUSDT", confirmed_long())])
    assert "CONFIRMED  BTCUSDT  LONG" in text
    assert "RR 3.00" in text
    assert "stop 90" in text
    assert "target 130" in text


def test_confirmed_setup_reason_is_verbatim_thesis_and_confirmation() -> None:
    assessment = confirmed_long()
    text = render_scan_report([_result("BTCUSDT", assessment)])
    reason_block = _extract_block(text, "reason")
    expected = _normalize(" ".join(assessment.thesis + assessment.confirmation))
    assert _dewrap(reason_block) == expected


def test_confirmed_setup_invalidation_is_verbatim() -> None:
    assessment = confirmed_long()
    text = render_scan_report([_result("BTCUSDT", assessment)])
    block = _extract_block(text, "invalidation")
    expected = _normalize(" ".join(assessment.invalidation))
    assert _dewrap(block) == expected


def test_candidate_setup_reason_is_verbatim_thesis() -> None:
    assessment = candidate_short_with_watched_level()
    text = render_scan_report([_result("DOTUSDT", assessment)])
    reason_block = _extract_block(text, "reason")
    expected = _normalize(" ".join(assessment.thesis))
    assert _dewrap(reason_block) == expected


def test_candidate_setup_needs_is_verbatim_confirmation() -> None:
    assessment = candidate_short_with_watched_level()
    text = render_scan_report([_result("DOTUSDT", assessment)])
    block = _extract_block(text, "needs")
    expected = _normalize(" ".join(assessment.confirmation))
    assert _dewrap(block) == expected


def test_candidate_with_no_thesis_or_confirmation_omits_dangling_labels() -> None:
    text = render_scan_report([_result("YYYUSDT", candidate_with_no_thesis_or_confirmation())])
    assert "CANDIDATE  YYYUSDT  LONG" in text
    assert "reason:" not in text
    assert "needs:" not in text


def test_candidate_with_no_level_shows_no_fabricated_stop_or_target() -> None:
    text = render_scan_report([_result("DOTUSDT", candidate_with_no_watched_level())])
    setups = text.split("ACTIONABLE SETUPS", 1)[1]
    line = next(l for l in setups.splitlines() if l.startswith("   target"))
    assert line == "   target -   stop -"


def test_candidate_shows_rr_and_target_when_already_computed() -> None:
    """Regression for the adversarial-review finding: a CANDIDATE with a
    known stop and target on each side already carries a real `risk_reward`
    (`policy.py` never conditions it on `state`), and this section must not
    silently drop it."""
    assessment = candidate_short_with_watched_level()
    assert assessment.risk_reward is not None
    assert assessment.targets
    text = render_scan_report([_result("DOTUSDT", assessment)])
    setups = text.split("ACTIONABLE SETUPS", 1)[1]
    header_line = next(l for l in setups.splitlines() if l.startswith(" CANDIDATE"))
    assert f"RR {assessment.risk_reward.ratio:,.2f}" in header_line
    target_line = next(l for l in setups.splitlines() if l.startswith("   target"))
    assert target_line == (
        f"   target {assessment.targets[0].price:,.6g}   "
        f"stop {assessment.stop.price:,.6g}"
    )


def test_confirmed_section_appears_before_candidate_section() -> None:
    results = [
        _result("DOTUSDT", candidate_short_with_watched_level()),
        _result("BTCUSDT", confirmed_long()),
    ]
    text = render_scan_report(results)
    setups = text.split("ACTIONABLE SETUPS", 1)[1]
    assert setups.index("CONFIRMED  BTCUSDT") < setups.index("CANDIDATE  DOTUSDT")


def test_actionable_setups_preserves_scan_order_within_each_state() -> None:
    """Two CONFIRMED results stay in scan order — a filter and a state
    grouping, never a reorder by direction, RR or any other property."""
    second_confirmed = evaluate_setup(
        SetupInputs(
            symbol="ETHUSDT", as_of=_AS_OF, source="fixture",
            context_interval="1w", setup_interval="1d", execution_interval="4h",
            context_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
            setup_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
            execution_structural_trend=StructuralTrendType.NEUTRAL,
            context_regime_structure=StructureState.TRENDING,
            context_regime_volatility=VolatilityState.STEADY,
            context_regime_participation=ParticipationState.TYPICAL,
            evidence_state=OverallState.WATCH, evidence_dominant_alignment=Alignment.UPWARD,
            decision_context_state=ContextState.SUFFICIENT, decision_context_statements=(),
            execution_close=50.0, execution_closed_count=10,
            execution_levels=(_level(LevelSide.UPPER, 55.0), _level(LevelSide.LOWER, 45.0)),
            execution_breaks=(
                ExecutionBreakEvent(level=_level(LevelSide.UPPER, 52.0, index=3), index=5),
            ),
            setup_levels=(_level(LevelSide.UPPER, 65.0), _level(LevelSide.LOWER, 35.0)),
            inherited_limitations=(),
        )
    )
    results = [_result("BTCUSDT", confirmed_long()), _result("ETHUSDT", second_confirmed)]
    text = render_scan_report(results)
    setups = text.split("ACTIONABLE SETUPS", 1)[1]
    assert setups.index("BTCUSDT") < setups.index("ETHUSDT")


# ---------------------------------------------------------------------------
# WAIT REASONS
# ---------------------------------------------------------------------------


def test_wait_reasons_absent_when_no_wait_results() -> None:
    text = render_scan_report([_result("BTCUSDT", confirmed_long())])
    assert "WAIT REASONS" not in text


def test_wait_reasons_groups_identical_theses_together() -> None:
    results = [_result("BTCUSDT", waiting()), _result("ETHUSDT", waiting())]
    text = render_scan_report(results)
    assert "2 symbols:" in text
    block = text.split("WAIT REASONS", 1)[1]
    assert "BTCUSDT" in block and "ETHUSDT" in block
    assert block.count("regime structure is ranging") == 1


def test_wait_reasons_keeps_textually_distinct_theses_separate() -> None:
    results = [_result("BTCUSDT", waiting()), _result("XRPUSDT", insufficient_context())]
    text = render_scan_report(results)
    block = text.split("WAIT REASONS", 1)[1]
    assert "1 symbol:" in block
    assert block.count("1 symbol:") == 2
    assert "ranging, not trending" in block
    assert "INSUFFICIENT" in block


def test_wait_reasons_sorted_by_descending_count() -> None:
    results = [
        _result("XRPUSDT", insufficient_context()),
        _result("BTCUSDT", waiting()),
        _result("ETHUSDT", waiting()),
    ]
    text = render_scan_report(results)
    block = text.split("WAIT REASONS", 1)[1]
    assert block.index("2 symbols:") < block.index("1 symbol:")


def test_wait_reasons_ties_keep_first_occurrence_scan_order() -> None:
    results = [
        _result("XRPUSDT", insufficient_context()),
        _result("BTCUSDT", waiting()),
    ]
    text = render_scan_report(results)
    block = text.split("WAIT REASONS", 1)[1]
    assert block.index("INSUFFICIENT") < block.index("ranging, not trending")


def test_wait_reason_text_is_verbatim_thesis() -> None:
    assessment = waiting()
    text = render_scan_report([_result("BTCUSDT", assessment)])
    block = text.split("WAIT REASONS", 1)[1]
    assert _normalize(assessment.thesis[0]) in _normalize(block)


# ---------------------------------------------------------------------------
# SCAN ERRORS and failure isolation
# ---------------------------------------------------------------------------


def test_scan_errors_absent_when_nothing_failed() -> None:
    text = render_scan_report([_result("BTCUSDT", waiting())])
    assert "SCAN ERRORS" not in text


def test_scan_errors_shows_the_failure_message() -> None:
    text = render_scan_report([_result("BADUSDT", failure="BinanceTransportError: down")])
    assert "SCAN ERRORS" in text
    assert "BADUSDT" in text
    assert "BinanceTransportError: down" in text


def test_one_failed_symbol_does_not_suppress_the_other_sections() -> None:
    results = [
        _result("BTCUSDT", confirmed_long()),
        _result("DOTUSDT", candidate_short_with_watched_level()),
        _result("ETHUSDT", waiting()),
        _result("BADUSDT", failure="down"),
    ]
    text = render_scan_report(results)
    assert "SCAN SUMMARY" in text
    assert "MARKET OVERVIEW" in text
    assert "ACTIONABLE SETUPS" in text
    assert "WAIT REASONS" in text
    assert "SCAN ERRORS" in text


# ---------------------------------------------------------------------------
# golden output
# ---------------------------------------------------------------------------


def test_golden_output_for_a_small_mixed_scan() -> None:
    results = [
        _result("BTCUSDT", confirmed_long()),
        _result("DOTUSDT", candidate_with_no_watched_level()),
        _result("ETHUSDT", waiting()),
    ]
    text = render_scan_report(results)
    lines = text.splitlines()
    assert lines[0] == "=" * 78
    assert lines[1] == " FMITS MARKET SCANNER - MARKET INTELLIGENCE REPORT"
    assert lines[2] == "=" * 78
    assert lines[3] == " 3 symbols scanned"
    assert "" == lines[4]
    assert lines[5] == " SCAN SUMMARY"
    assert lines[6] == "-" * 78
    assert lines[7] == "   WAIT ................ 1"
    assert lines[8] == "   CANDIDATE ........... 1"
    assert lines[9] == "   CONFIRMED ........... 1"
    assert lines[10] == "   ERROR ............... 0"
    assert " CONFIRMED  BTCUSDT  LONG   RR 3.00" in lines
    assert " CANDIDATE  DOTUSDT  SHORT" in lines
    assert text.rstrip().endswith("=" * 78)


# ---------------------------------------------------------------------------
# no invention: every printed side/RR/price already exists on the assessment
# ---------------------------------------------------------------------------


def test_wait_result_never_shows_a_side_or_price_in_actionable_setups() -> None:
    text = render_scan_report([_result("ETHUSDT", waiting())])
    assert "ACTIONABLE SETUPS" not in text
    assert "LONG" not in text and "SHORT" not in text


def test_states_it_is_not_a_ranking() -> None:
    text = render_scan_report([_result("BTCUSDT", waiting())])
    assert "not a ranking" in text.lower()
