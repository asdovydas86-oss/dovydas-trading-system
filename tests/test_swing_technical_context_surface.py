"""TA Slice 5A — what the operator actually sees, and what the page refuses to say.

The milestone's product test. `test_technical_context_carriage.py` proves the
facts reach the row; this proves they reach the **page**, that the page stays
scannable, and — the part that matters most — that recovering the data did not
quietly license a vocabulary for it.

**The vocabulary scan is the load-bearing test here.** Once levels, crossings and
changes of character are visible, the shortest path to a "useful" page is to call
the level below price *support* and the close beyond it a *breakout*. Neither
concept exists in this repository. The scan reads the rendered HTML and refuses
both, with the page's own denial sentences carved out explicitly and asserted
separately — the exemption pattern `fmis.pipeline.render` established for its
disclaimer, so deleting a denial fails a test rather than widening a hole.

Offline, clock-free and network-free.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from fmis.operator_dashboard.render import (
    _decision_detail,
    _technical_context_panel,
)
from fmis.operator_dashboard.sections import symbol_decision_rows
from fmis.swing_setup.compose import (
    SetupRunResult,
    setup_composition_for_sheet,
    setup_readings_for,
)
from fmis.swing_workspace.sections import symbol_decisions

from tests.archive_helpers import multi

REFERENCE = datetime(2026, 2, 14, tzinfo=timezone.utc)


def _row(seeds=(1, 5, 9), symbol: str = "BTCUSDT"):
    sheet = multi(seeds=seeds, symbol=symbol)
    inputs, technical, assessment = setup_composition_for_sheet(sheet)
    result = SetupRunResult(
        requested_symbol=symbol,
        assessment=assessment,
        readings=setup_readings_for(sheet, inputs),
        technical=technical,
    )
    decisions = symbol_decisions([result], reference_time=REFERENCE)
    return sheet, symbol_decision_rows(decisions)[0]


def _panel(seeds=(1, 5, 9), symbol: str = "BTCUSDT") -> str:
    _sheet, row = _row(seeds, symbol)
    return _technical_context_panel(row.symbol, row.technical)


def _visible_text(html: str) -> str:
    """The page with its markup stripped — what a reader actually reads.

    Tags become a space rather than nothing, so two adjacent cells never run
    into one word and hide a term from the scan below. The punctuation fix-up
    undoes the one artefact that creates: an inline tag closing before a comma
    leaves ``word ,``, which would make the page's own denial sentence
    unquotable and would silently weaken the carve-out it earns.
    """
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    return text.replace(" ,", ",").replace(" .", ".")


# ---------------------------------------------------------------------------
# The section exists, and shows all three roles
# ---------------------------------------------------------------------------


def test_the_panel_names_every_timeframe_role_and_its_interval() -> None:
    _sheet, row = _row()
    text = _visible_text(_technical_context_panel(row.symbol, row.technical))

    for interval in ("1w", "1d", "4h"):
        assert interval in text, interval
    for role in ("context", "setup", "execution"):
        assert role in text, role


def test_the_panel_shows_the_structural_trend_and_regime_for_every_role() -> None:
    _sheet, row = _row()
    text = _visible_text(_technical_context_panel(row.symbol, row.technical))

    for item in row.technical:
        assert item.structural_trend in text, item.role
        assert item.regime_structure in text, item.role
        assert item.regime_volatility in text, item.role
        assert item.regime_participation in text, item.role


def test_the_panel_shows_the_nearest_level_each_side_for_every_role() -> None:
    _sheet, row = _row()
    text = _visible_text(_technical_context_panel(row.symbol, row.technical))

    assert "Nearest level above" in text
    assert "Nearest level below" in text
    for item in row.technical:
        for level in (item.nearest_above, item.nearest_below):
            if level is None:
                continue
            assert repr(level.price) in text, (item.role, level.price)


def test_the_panel_shows_a_change_of_character_when_one_occurred() -> None:
    """The acceptance case the milestone brief names, on a fixture that has one."""
    _sheet, row = _row()
    text = _visible_text(_technical_context_panel(row.symbol, row.technical))
    with_change = [
        item for item in row.technical if item.latest_character_change is not None
    ]

    assert with_change, "the fixture must contain a change of character"
    assert "latest change of character" in text
    for item in with_change:
        change = item.latest_character_change
        assert repr(change.level_price) in text
        assert "changed from a" in text


def test_the_panel_shows_the_indicator_readings_under_the_engines_own_names() -> None:
    _sheet, row = _row()
    text = _visible_text(_technical_context_panel(row.symbol, row.technical))

    for item in row.technical:
        for reading in item.features:
            assert reading.name in text, reading.name


def test_the_panel_shows_a_structured_readings_three_components() -> None:
    _sheet, row = _row()
    text = _visible_text(_technical_context_panel(row.symbol, row.technical))
    structured = [
        reading
        for item in row.technical
        for reading in item.features
        if reading.components
    ]

    assert structured
    for part, _number in structured[0].components:
        assert part in text, part


def test_an_absent_context_is_stated_rather_than_blank() -> None:
    panel = _technical_context_panel("BTCUSDT", ())
    text = _visible_text(panel)

    assert "No per-role technical context was carried" in text
    assert "BTCUSDT" in text


def test_a_warming_up_reading_is_shown_as_an_absence_with_its_reason() -> None:
    from fmis.pipeline.multi_timeframe import build_multi_timeframe_facts
    from fmis.pipeline.multi_timeframe import TimeframeRole
    from tests.archive_helpers import facts

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
    text = _visible_text(_technical_context_panel(row.symbol, row.technical))

    assert "not enough closed history yet" in text
    assert "still warming up" in text


# ---------------------------------------------------------------------------
# The vocabulary the page refuses
# ---------------------------------------------------------------------------

#: Concepts this repository has **not** implemented. Every one of them is a
#: reading of a fact the panel now shows, which is exactly why the scan exists:
#: the data arriving is not authorisation for the word.
_UNIMPLEMENTED = (
    "support",
    "resistance",
    "breakout",
    "retest",
    "reclaim",
    "rejection",
    "acceptance",
    "fakeout",
    "divergence",
    "trendline",
    "channel",
    "fibonacci",
    "elliott",
    "flag",
    "consolidation",
    "impulse",
    "oversold",
    "overbought",
    "golden",
    "crossover",
    "momentum",
)

#: Directional and judgement vocabulary the whole system refuses outside
#: `fmis.swing_setup`.
_JUDGEMENTS = (
    "bullish",
    "bearish",
    "buy",
    "sell",
    "score",
    "confidence",
    "probability",
    "recommend",
    "opportunity",
    "watch",
)

#: The one sentence in the panel that uses refused words precisely to refuse
#: them. Asserted separately below, so deleting it fails a test rather than
#: quietly passing this scan — the exemption pattern report 0047 §10.4 describes
#: and `fmis.pipeline.render` already uses for its own disclaimer.
_DENIAL = (
    "A level is where a confirmed swing sat — it is not called support or "
    "resistance, because a role would have to come from what price has done at "
    "it and this system does not yet derive that. A close beyond a level is a "
    "close beyond a level, not a breakout. A change of character is two breaks "
    "on opposite sides, not a reversal. The readings are values, not leans: no "
    "slope, rate of change or divergence is computed anywhere here."
)


def _scanned(html: str) -> set[str]:
    """Every word on the page, with the one denial sentence removed first."""
    text = " ".join(_visible_text(html).split())
    return set(re.findall(r"[a-z]+", text.replace(_DENIAL, "").lower()))


@pytest.mark.parametrize("word", _UNIMPLEMENTED)
def test_the_page_never_names_a_concept_this_system_has_not_built(word: str) -> None:
    """**The data being visible is not authorisation for the vocabulary.**"""
    assert word not in _scanned(_panel()), word


@pytest.mark.parametrize("word", _JUDGEMENTS)
def test_the_page_never_names_a_direction_or_a_judgement(word: str) -> None:
    assert word not in _scanned(_panel()), word


def test_the_denial_the_scan_exempts_is_actually_on_the_page() -> None:
    """Or the carve-out above is a hole rather than a stated refusal."""
    text = " ".join(_visible_text(_panel()).split())

    assert _DENIAL in text
    assert "it is not called support or resistance" in text
    assert "not a breakout" in text


@pytest.mark.parametrize("seeds", [(1, 5, 9), (3, 4, 7), (2, 6, 8)])
def test_the_refusal_holds_across_different_markets(seeds) -> None:
    """One fixture proving a negative is one fixture. Three is better."""
    words = _scanned(_panel(seeds=seeds))
    for word in _UNIMPLEMENTED + _JUDGEMENTS:
        assert word not in words, (seeds, word)


def test_the_page_states_that_nothing_here_reached_the_decision() -> None:
    text = " ".join(_visible_text(_panel()).split())

    assert "Nothing in this section reached the decision above it" in text
    assert "none of it is a reason to trade" in text


# ---------------------------------------------------------------------------
# Where it sits, and how much of it there is
# ---------------------------------------------------------------------------


def test_the_decision_layer_still_comes_first_on_the_symbol_page() -> None:
    """The operator question above the audit question, and now above this one.

    A page that opened with a technical dump would be the audit page Slice 2
    deliberately reordered away from.
    """
    _sheet, row = _row()
    page = _decision_detail(row)

    decision_at = page.index(f"{row.symbol} — decision")
    technical_at = page.index(f"{row.symbol} — technical context")
    evidence_at = page.index(f"{row.symbol} — evidence")

    assert decision_at < technical_at < evidence_at


def test_the_decision_panel_still_answers_the_operator_questions_first() -> None:
    """Nothing Slice 1 or Slice 2 put on the page was displaced to make room."""
    _sheet, row = _row()
    text = _visible_text(_decision_detail(row))

    for heading in (
        "decision",
        "developing evidence",
        "what is holding it",
        "HTF context",
        "setup state",
        "data age",
    ):
        assert heading in text, heading


def test_the_raw_crossing_history_is_never_rendered() -> None:
    """Hundreds of events per role exist; the page shows two of them.

    A truthful count and two bounded selections, which is what a page can
    honestly say. The full run stays on the model for the engines that will need
    event identity and timing.
    """
    _sheet, row = _row()
    panel = _technical_context_panel(row.symbol, row.technical)

    total = sum(item.crossing_count for item in row.technical)
    assert total > 100, total

    # One table row per role, plus the header. A rendered event flood would show
    # up here as hundreds.
    assert panel.count("<tr>") < 60, panel.count("<tr>")


def test_the_panel_stays_a_section_rather_than_a_page() -> None:
    """A size bound, so a later milestone cannot turn this into an audit dump."""
    _sheet, row = _row()
    panel = _technical_context_panel(row.symbol, row.technical)

    assert len(panel) < 40_000, len(panel)


def test_the_detail_is_behind_a_disclosure_per_role() -> None:
    """Progressive disclosure: the table is open, the depth is folded away."""
    _sheet, row = _row()
    panel = _technical_context_panel(row.symbol, row.technical)

    assert panel.count("<details") == len(row.technical)
    assert "open" not in panel.split("<details")[1].split(">")[0]
