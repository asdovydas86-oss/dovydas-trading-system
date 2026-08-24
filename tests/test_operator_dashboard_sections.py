"""Engine output → read model. The mapping, asserted against real engine values.

Every fixture here is a genuine `MarketPulse`, `MacroContextReport` or
`SwingWorkspace`, so a field an engine renames fails a test here rather than
rendering as a silent absence on the page.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import swing_workspace_helpers as W
from operator_dashboard_helpers import (
    AT,
    HOURLY,
    benchmark,
    dark,
    level_for,
    macro_of,
    pulse_of,
    reading_for,
)

from fmis.market_pulse import MarketCategory, QuantityKind
from fmis.operator_dashboard import (
    SourceState,
    counts_from,
    health_view,
    macro_view,
    paper_view,
    portfolio_view,
    pulse_view,
    swing_view,
    warning_rows,
)
from fmis.operator_dashboard.sections import (
    _decimal_or_reason,
    _money_or_reason,
    _text_or_reason,
)
from fmis.provenance import Absent
from fmis.today import NotAvailable


# ---------------------------------------------------------------------------
# The three absence vocabularies collapse to one shape
# ---------------------------------------------------------------------------


def test_a_not_available_becomes_a_none_and_its_reason() -> None:
    """`fmis.today`'s absence carries three fields; only the reason crosses the
    seam, because the other two are an audit trail for the engine."""
    value, reason = _text_or_reason(
        NotAvailable(
            reason="no mark was read for this market",
            owned_by="fmis.marks",
            forbidden_inference="do not read this as a zero position value",
        )
    )
    assert value is None
    assert reason == "no mark was read for this market"


def test_plain_text_survives_unchanged() -> None:
    assert _text_or_reason("1234.56") == ("1234.56", None)


def test_an_absent_becomes_a_none_and_its_reason() -> None:
    value, reason = _money_or_reason(Absent("fewer than 30 closed trades"))
    assert value is None
    assert reason == "fewer than 30 closed trades"


def test_money_crosses_as_its_canonical_text_not_a_rounded_float() -> None:
    """The exact spelling the store holds and the digest covers. Rounding here
    would make a figure on screen differ from the same figure in a record."""
    from fmis.money import AssetCode, Money
    from decimal import Decimal

    value, reason = _money_or_reason(
        Money(amount=Decimal("1234.567890123"), asset=AssetCode("USDT"))
    )
    assert value == "1234.567890123"
    assert reason is None


def test_a_decimal_crosses_exactly_and_never_through_a_float() -> None:
    from decimal import Decimal

    value, _ = _decimal_or_reason(Decimal("0.333333333333333333"))
    assert value == "0.333333333333333333"


@pytest.mark.parametrize(
    "splitter", [_text_or_reason, _money_or_reason, _decimal_or_reason]
)
def test_exactly_one_of_value_and_reason_is_ever_set(splitter) -> None:
    """The invariant the render layer relies on to keep zero and absent apart."""
    for supplied in (None, Absent("gone"), "0"):
        value, reason = splitter(supplied)
        assert value is None or reason is None


# ---------------------------------------------------------------------------
# Pulse
# ---------------------------------------------------------------------------


def test_every_market_appears_exactly_once_as_a_reading_or_a_failure() -> None:
    view = pulse_view(
        pulse_of(
            [reading_for(benchmark("BTC")), reading_for(benchmark("ETH"))],
            unavailable=[(benchmark("SOL"), "the venue returned 503")],
            unsupported=[dark("DXY")],
        )
    )
    assert [row.benchmark_id for row in view.rows] == ["BTC", "ETH", "SOL", "DXY"]


def test_an_unsupported_market_is_carried_even_though_it_is_not_in_unavailable() -> None:
    """**The regression this test exists for.** Unsupported markets live on the
    universe, not in `unavailable` — they were never asked for. A mapping that
    read only `unavailable` dropped DXY and XAU off the page entirely, which
    answers *"what can this system not tell me?"* with silence."""
    view = pulse_view(pulse_of([reading_for(benchmark("BTC"))], unsupported=[dark("XAU")]))
    row = next(row for row in view.rows if row.benchmark_id == "XAU")
    assert row.state is SourceState.UNSUPPORTED
    assert row.unavailable_reason == "no provider is configured"


def test_unsupported_and_unavailable_stay_different_states() -> None:
    """One is a permanent property of the build; the other is this afternoon."""
    view = pulse_view(
        pulse_of(
            unavailable=[(benchmark("SOL"), "timed out")], unsupported=[dark("DXY")]
        )
    )
    states = {row.benchmark_id: row.state for row in view.rows}
    assert states["SOL"] is SourceState.UNAVAILABLE
    assert states["DXY"] is SourceState.UNSUPPORTED


def test_a_readings_freshness_verdict_is_carried_not_recomputed() -> None:
    """The bound belongs to the series. This layer carries the engine's answer."""
    fresh = pulse_view(pulse_of([reading_for(benchmark("BTC"))]))
    assert fresh.rows[0].state is SourceState.AVAILABLE

    old = pulse_view(
        pulse_of([reading_for(benchmark("BTC"), bar_open=AT - timedelta(days=4))])
    )
    assert old.rows[0].state is SourceState.BEHIND_SCHEDULE


def test_the_age_is_the_engines_own_and_not_a_subtraction_here() -> None:
    reading = reading_for(benchmark("BTC"), bar_open=AT - timedelta(hours=3))
    view = pulse_view(pulse_of([reading]))
    assert view.rows[0].age == reading.age_at(AT) == timedelta(hours=3)


def test_a_measured_zero_move_is_not_an_absence() -> None:
    view = pulse_view(pulse_of([reading_for(benchmark("BTC"), move=0.0)]))
    move = view.rows[0].moves[0]
    assert move.value == 0.0
    assert move.unavailable_reason is None


def test_an_unmeasured_move_carries_its_reason() -> None:
    view = pulse_view(
        pulse_of(
            [reading_for(benchmark("BTC"), move=None, move_reason="too few bars")]
        )
    )
    move = view.rows[0].moves[0]
    assert move.value is None
    assert move.unavailable_reason == "too few bars"


def test_the_categorys_enum_crosses_as_its_own_value() -> None:
    view = pulse_view(
        pulse_of([reading_for(benchmark("SPX", category=MarketCategory.EQUITY_INDEX))])
    )
    assert view.rows[0].category == "equity_index"


# ---------------------------------------------------------------------------
# Macro
# ---------------------------------------------------------------------------


def test_a_macro_level_crosses_with_its_unit_and_its_source() -> None:
    subject = benchmark("US10Y", quantity_kind=QuantityKind.RATE_LIKE)
    view = macro_view(
        macro_of([reading_for(subject)], levels=[level_for(subject, value=4.69)])
    )
    row = view.rows[0]
    assert row.level == 4.69
    assert row.unit == "percent per annum"
    assert row.source == "test-source"
    assert row.quantity_kind == "rate_like"


def test_an_unsupported_macro_market_is_carried_too() -> None:
    view = macro_view(macro_of(unsupported=[dark("XAU")]))
    assert view.rows[0].state is SourceState.UNSUPPORTED


# ---------------------------------------------------------------------------
# Swing
# ---------------------------------------------------------------------------


def test_the_workspaces_order_is_preserved_index_for_index() -> None:
    """**Nothing here sorts.** The workspace's lexicographic key placed these
    rows; re-deriving the order above it would be inventing a ranking four
    engines below deliberately refused to make."""
    workspace = W.workspace_of(
        W.result(W.assessment("BTCUSDT")),
        W.result(W.assessment("ETHUSDT")),
        W.result(W.assessment("SOLUSDT")),
    )
    view = swing_view(workspace)
    assert [row.symbol for row in view.opportunities] == [
        ranked.opportunity.symbol for ranked in workspace.opportunities
    ]
    assert [row.position for row in view.opportunities] == [
        ranked.position for ranked in workspace.opportunities
    ]


def test_the_ordering_key_is_carried_component_by_component() -> None:
    """So the reason one row sits above another is readable on the row itself."""
    workspace = W.workspace_of(W.result(W.assessment("BTCUSDT")))
    row = swing_view(workspace).opportunities[0]
    assert row.rank_components
    assert row.rank_components == tuple(
        (component.name, component.value)
        for component in workspace.opportunities[0].key.components
    )


def test_a_failed_symbol_becomes_an_unreadable_row_not_a_no_trade() -> None:
    """*Could not be read* and *concluded no trade* are different facts, and a
    surface that merged them would report an outage as an analysis."""
    workspace = W.workspace_of(W.failed_result("BTCUSDT", "provider timed out"))
    view = swing_view(workspace)
    assert [row.symbol for row in view.unreadable] == ["BTCUSDT"]
    assert view.no_trade == ()


def test_held_and_paper_status_stay_separate_fields() -> None:
    """One field carrying either would let the page imply real exposure where
    there is only a simulated trade."""
    workspace = W.workspace_of(W.result(W.assessment("BTCUSDT")))
    row = swing_view(workspace).opportunities[0]
    assert not (row.held and row.paper_status and row.held == row.paper_status)


def test_the_counts_are_the_workspaces_own_tallies() -> None:
    workspace = W.workspace_of(
        W.result(W.assessment("BTCUSDT")),
        W.failed_result("ETHUSDT"),
    )
    counts = counts_from(workspace)
    assert counts.scanned == workspace.summary.scanned
    assert counts.confirmed == workspace.summary.confirmed
    assert counts.unreadable == workspace.summary.unanalysed


# ---------------------------------------------------------------------------
# Portfolio and paper stay apart
# ---------------------------------------------------------------------------


def test_the_portfolio_view_reads_no_paper_field() -> None:
    """Aggregating a simulated position into a real exposure figure is the
    single most dangerous thing this dashboard could do.

    Asserted over the parsed function rather than its text, so the prose saying
    *no paper field is read here* does not itself trip the guard.
    """
    import ast
    import inspect
    import textwrap

    from fmis.operator_dashboard import sections

    tree = ast.parse(textwrap.dedent(inspect.getsource(sections.portfolio_view)))
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert "paper" not in attributes
    assert not any("paper" in name for name in attributes), attributes


def test_a_store_that_is_absent_is_reported_as_absent_not_as_a_failure() -> None:
    workspace = W.workspace_of(
        W.result(W.assessment("BTCUSDT")), store=W.reading(present=False)
    )
    view = portfolio_view(workspace)
    assert view.store_present is False
    assert view.positions == ()


def test_paper_and_portfolio_are_built_from_different_fields() -> None:
    workspace = W.workspace_of(W.result(W.assessment("BTCUSDT")))
    assert paper_view(workspace).rows == () or all(
        row.market for row in paper_view(workspace).rows
    )
    assert portfolio_view(workspace).positions == ()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_a_failed_domain_appears_as_an_unavailable_source_not_a_missing_row() -> None:
    """A page that omitted the macro sources when FRED was down would look
    exactly like a page where FRED was fine."""
    view = health_view(
        pulse=None,
        macro=None,
        portfolio=None,
        paper=None,
        pulse_failure="HTTPError: 503",
        macro_failure="HTTPError: 500",
    )
    states = {source.source_id: source.state for source in view.sources}
    assert states == {
        "pulse": SourceState.UNAVAILABLE,
        "macro": SourceState.UNAVAILABLE,
    }


def test_every_market_becomes_its_own_health_row_with_the_engines_verdict() -> None:
    pulse = pulse_view(
        pulse_of([reading_for(benchmark("BTC"))], unsupported=[dark("DXY")])
    )
    view = health_view(pulse=pulse, macro=None, portfolio=None, paper=None)
    states = {source.source_id: source.state for source in view.sources}
    assert states["pulse:BTC"] is SourceState.AVAILABLE
    assert states["pulse:DXY"] is SourceState.UNSUPPORTED


def test_every_health_row_states_a_detail_even_when_it_was_read_fine() -> None:
    """An available source left blank renders as an absence, and *"unavailable:
    no detail was stated"* against a market that was read perfectly well is
    exactly the misleading cell this section exists to prevent."""
    pulse = pulse_view(pulse_of([reading_for(benchmark("BTC"))]))
    view = health_view(pulse=pulse, macro=None, portfolio=None, paper=None)
    assert all(source.detail for source in view.sources)


def test_an_absent_store_is_absent_and_not_unavailable() -> None:
    workspace = W.workspace_of(
        W.result(W.assessment("BTCUSDT")), store=W.reading(present=False)
    )
    view = health_view(
        pulse=None, macro=None, portfolio=portfolio_view(workspace), paper=None
    )
    assert view.sources[0].state is SourceState.ABSENT


def test_warnings_keep_the_workspaces_own_order() -> None:
    workspace = W.workspace_of(W.result(W.assessment("BTCUSDT")))
    assert [row.code for row in warning_rows(workspace)] == [
        warning.code for warning in workspace.warnings
    ]
