"""Market Scanner v1 — `fmis.swing_setup.scan`.

No test here re-derives the directional policy (covered in
`tests/test_swing_setup_policy.py`) or the single-symbol page (covered in
`tests/test_swing_setup_render.py`). This file covers only: the fixed
universe, `run_market_scan`'s per-symbol isolation, and `render_scan`'s
table, counts and TOP OPPORTUNITIES section.
"""

from __future__ import annotations

import pytest

from fmis.providers.binance import BinanceTransportError
from fmis.swing_setup import SCAN_UNIVERSE, SwingSetupError, render_scan, run_market_scan
from fmis.swing_setup import compose as compose_module
from fmis.swing_setup.compose import SetupRunResult
from tests.archive_helpers import multi
from tests.test_swing_setup_render import (
    candidate_short_with_watched_level,
    confirmed_long,
    waiting,
)


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        compose_module, "multi_timeframe_facts_for_symbol",
        lambda symbol, **kw: multi(symbol=symbol),
    )


def _waiting_result(symbol: str) -> SetupRunResult:
    return SetupRunResult(requested_symbol=symbol, assessment=waiting())


def _confirmed_result(symbol: str = "BTCUSDT") -> SetupRunResult:
    return SetupRunResult(requested_symbol=symbol, assessment=confirmed_long())


def _candidate_result(symbol: str = "DOTUSDT") -> SetupRunResult:
    return SetupRunResult(requested_symbol=symbol, assessment=candidate_short_with_watched_level())


def _error_result(symbol: str = "BADUSDT") -> SetupRunResult:
    return SetupRunResult(
        requested_symbol=symbol, failure="BinanceTransportError: connection refused"
    )


# ---------------------------------------------------------------------------
# SCAN_UNIVERSE
# ---------------------------------------------------------------------------


def test_scan_universe_has_twenty_major_pairs() -> None:
    assert len(SCAN_UNIVERSE) == 20


def test_scan_universe_has_no_duplicates() -> None:
    assert len(set(SCAN_UNIVERSE)) == len(SCAN_UNIVERSE)


def test_scan_universe_is_every_symbol_a_non_empty_upper_string() -> None:
    for symbol in SCAN_UNIVERSE:
        assert isinstance(symbol, str) and symbol.strip()
        assert symbol == symbol.upper()


def test_scan_universe_includes_the_named_majors() -> None:
    assert {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"} <= set(SCAN_UNIVERSE)


# ---------------------------------------------------------------------------
# run_market_scan
# ---------------------------------------------------------------------------


def test_run_market_scan_defaults_to_the_scan_universe() -> None:
    results = run_market_scan()
    assert tuple(r.requested_symbol for r in results) == SCAN_UNIVERSE


def test_run_market_scan_accepts_a_custom_symbol_list() -> None:
    results = run_market_scan(["ETHUSDT", "BTCUSDT"])
    assert tuple(r.requested_symbol for r in results) == ("ETHUSDT", "BTCUSDT")


def test_run_market_scan_rejects_an_empty_symbol_list() -> None:
    with pytest.raises(ValueError):
        run_market_scan([])


def test_run_market_scan_every_symbol_produces_exactly_one_result() -> None:
    results = run_market_scan(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    assert len(results) == 3
    assert all(isinstance(r, SetupRunResult) for r in results)


def test_run_market_scan_isolates_one_failing_symbol_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def flaky(symbol: str, **kw: object):
        if symbol == "BADUSDT":
            raise BinanceTransportError("connection refused")
        return multi(symbol=symbol)

    monkeypatch.setattr(compose_module, "multi_timeframe_facts_for_symbol", flaky)
    results = run_market_scan(["BTCUSDT", "BADUSDT", "ETHUSDT"])
    assert [r.requested_symbol for r in results] == ["BTCUSDT", "BADUSDT", "ETHUSDT"]
    assert results[0].assessment is not None
    assert results[1].assessment is None
    assert "BinanceTransportError" in results[1].failure
    assert results[2].assessment is not None


def test_run_market_scan_all_symbols_failing_still_returns_one_result_each(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def always_fails(symbol: str, **kw: object):
        raise BinanceTransportError("down")

    monkeypatch.setattr(compose_module, "multi_timeframe_facts_for_symbol", always_fails)
    results = run_market_scan(["BTCUSDT", "ETHUSDT"])
    assert len(results) == 2
    assert all(r.assessment is None for r in results)
    assert all(r.failure is not None for r in results)


def test_run_market_scan_a_defect_propagates_rather_than_becoming_a_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def buggy(symbol: str, **kw: object):
        raise KeyError("not a market failure")

    monkeypatch.setattr(compose_module, "multi_timeframe_facts_for_symbol", buggy)
    with pytest.raises(KeyError):
        run_market_scan(["BTCUSDT"])


# ---------------------------------------------------------------------------
# render_scan — type and shape guards
# ---------------------------------------------------------------------------


def test_render_scan_rejects_a_non_sequence() -> None:
    with pytest.raises(TypeError):
        render_scan(object())  # type: ignore[arg-type]


def test_render_scan_rejects_a_string() -> None:
    with pytest.raises(TypeError):
        render_scan("BTCUSDT")  # type: ignore[arg-type]


def test_render_scan_rejects_a_sequence_of_the_wrong_type() -> None:
    with pytest.raises(TypeError):
        render_scan([object()])  # type: ignore[list-item]


def test_render_scan_rejects_an_empty_sequence() -> None:
    with pytest.raises(ValueError):
        render_scan([])


# ---------------------------------------------------------------------------
# render_scan — content
# ---------------------------------------------------------------------------


def test_render_scan_all_wait() -> None:
    results = [_waiting_result(s) for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]
    text = render_scan(results)
    assert text.count("WAIT") >= 3
    assert "3 scanned · 3 WAIT · 0 CANDIDATE · 0 CONFIRMED · 0 ERROR" in text
    assert "TOP OPPORTUNITIES" not in text


def test_render_scan_all_error() -> None:
    results = [_error_result(s) for s in ("BADUSDT", "WORSEUSDT")]
    text = render_scan(results)
    assert text.count("ERROR") >= 2
    assert "2 scanned · 0 WAIT · 0 CANDIDATE · 0 CONFIRMED · 2 ERROR" in text
    assert "connection refused" in text
    assert "TOP OPPORTUNITIES" not in text


def test_render_scan_mixed_results_reports_every_symbol() -> None:
    results = [
        _waiting_result("ETHUSDT"),
        _confirmed_result("BTCUSDT"),
        _candidate_result("DOTUSDT"),
        _error_result("BADUSDT"),
    ]
    text = render_scan(results)
    for symbol in ("ETHUSDT", "BTCUSDT", "DOTUSDT", "BADUSDT"):
        assert symbol in text
    assert "4 scanned · 1 WAIT · 1 CANDIDATE · 1 CONFIRMED · 1 ERROR" in text


def test_render_scan_preserves_input_order_regardless_of_state() -> None:
    results = [
        _confirmed_result("BTCUSDT"),
        _error_result("BADUSDT"),
        _waiting_result("ETHUSDT"),
        _candidate_result("DOTUSDT"),
    ]
    text = render_scan(results)
    table = text.split("TOP OPPORTUNITIES")[0]
    positions = [table.index(r.requested_symbol) for r in results]
    assert positions == sorted(positions)


def test_render_scan_candidate_output_shows_side_and_watched_level() -> None:
    text = render_scan([_candidate_result("DOTUSDT")])
    assert "DOTUSDT" in text
    assert "CANDIDATE" in text
    assert "SHORT" in text
    assert "0.815" in text
    assert "0.825" in text


def test_render_scan_confirmed_output_shows_side_rr_stop_and_target() -> None:
    text = render_scan([_confirmed_result("BTCUSDT")])
    assert "BTCUSDT" in text
    assert "CONFIRMED" in text
    assert "LONG" in text
    assert "3.00" in text  # 30 reward / 10 risk, from the confirmed_long fixture
    assert "90" in text  # stop
    assert "130" in text  # target


def test_render_scan_wait_row_shows_no_fabricated_side_or_price() -> None:
    text = render_scan([_waiting_result("ETHUSDT")])
    lines = [line for line in text.splitlines() if line.strip().startswith("ETHUSDT")]
    assert len(lines) == 1
    row = lines[0]
    assert "WAIT" in row
    assert "LONG" not in row and "SHORT" not in row


def test_render_scan_error_row_shows_no_status_words() -> None:
    text = render_scan([_error_result("BADUSDT")])
    lines = [line for line in text.splitlines() if line.strip().startswith("BADUSDT")]
    assert len(lines) == 1
    row = lines[0]
    assert "ERROR" in row
    assert "WAIT" not in row and "CANDIDATE" not in row and "CONFIRMED" not in row


def test_render_scan_top_opportunities_lists_only_candidate_and_confirmed() -> None:
    results = [
        _waiting_result("ETHUSDT"),
        _confirmed_result("BTCUSDT"),
        _error_result("BADUSDT"),
        _candidate_result("DOTUSDT"),
    ]
    text = render_scan(results)
    opportunities = text.split("TOP OPPORTUNITIES", 1)[1]
    assert "BTCUSDT" in opportunities
    assert "DOTUSDT" in opportunities
    assert "ETHUSDT" not in opportunities
    assert "BADUSDT" not in opportunities


def test_render_scan_top_opportunities_preserves_scan_order_not_desirability() -> None:
    """CANDIDATE appears before CONFIRMED here, on purpose — the opposite of

    any plausible "readiness" sort — to prove the section is a filter, never
    a reorder.
    """
    results = [
        _waiting_result("ETHUSDT"),
        _candidate_result("DOTUSDT"),
        _confirmed_result("BTCUSDT"),
    ]
    text = render_scan(results)
    opportunities = text.split("TOP OPPORTUNITIES", 1)[1]
    assert opportunities.index("DOTUSDT") < opportunities.index("BTCUSDT")


def test_render_scan_omits_top_opportunities_section_when_none_qualify() -> None:
    results = [_waiting_result("ETHUSDT"), _error_result("BADUSDT")]
    text = render_scan(results)
    assert "TOP OPPORTUNITIES" not in text


def test_render_scan_is_deterministic() -> None:
    results = [_confirmed_result("BTCUSDT"), _waiting_result("ETHUSDT")]
    assert render_scan(results) == render_scan(results)


def test_render_scan_states_it_is_not_a_ranking() -> None:
    text = render_scan([_waiting_result("BTCUSDT")])
    assert "not a ranking" in text.lower()
    assert "wait is a" in text.lower()


def test_render_scan_never_exceeds_the_page_width() -> None:
    results = [_confirmed_result("BTCUSDT"), _candidate_result("DOTUSDT"), _error_result("BADUSDT")]
    text = render_scan(results)
    for line in text.splitlines():
        assert len(line) <= 78


def test_render_scan_clips_a_symbol_wider_than_its_column() -> None:
    """Live-observed shape: an invalid, long symbol name is clipped with an

    ellipsis rather than pushing the row's later columns out of alignment —
    verified live against Binance during development
    (`NOTAREALSYMBOLXYZ` -> `NOTAREALS…`).
    """
    text = render_scan([_error_result("NOTAREALSYMBOLXYZ")])
    lines = [line for line in text.splitlines() if line.strip().startswith("NOTAREALS")]
    assert len(lines) == 1
    assert "NOTAREALS…" in lines[0]
    assert "NOTAREALSYMBOLXYZ" not in lines[0]


def test_render_scan_handles_the_full_twenty_symbol_universe() -> None:
    results = [_waiting_result(symbol) for symbol in SCAN_UNIVERSE]
    text = render_scan(results)
    assert "20 scanned · 20 WAIT · 0 CANDIDATE · 0 CONFIRMED · 0 ERROR" in text
    for symbol in SCAN_UNIVERSE:
        assert symbol in text


def test_a_width_violation_raises_swing_setup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import fmis.swing_setup.scan as scan_module

    monkeypatch.setattr(scan_module, "_WIDTH", 5)
    with pytest.raises(SwingSetupError):
        render_scan([_waiting_result("BTCUSDT")])
