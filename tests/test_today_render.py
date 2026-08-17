"""Milestone BJ — rendering the Daily Trading Workspace.

The renderer is the surface a human actually reads, so the tests here are about
what the page can and cannot say. Three groups:

* **Width and structure** — 78 columns, asserted; ASCII structure; a word for
  every state, so nothing depends on colour.
* **Honesty** — every absence prints its forbidden inference, every measured
  figure prints its `n` and caveat, and the page never uses a word of ranking.
* **Purity** — the module reads the model and nothing else.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from fmis.today import (
    TODAY_LIMITATIONS,
    TodayError,
    render_today,
)
from fmis.today import render as render_module
from today_helpers import REFERENCE, failed_result, line, reading, result, workspace

from tests.test_swing_setup_render import (
    candidate_short_with_watched_level,
    confirmed_long,
    waiting,
)

_WIDTH = 78


def _scan():
    return (
        result(confirmed_long()),
        result(candidate_short_with_watched_level()),
        result(waiting()),
        failed_result("BADUSDT"),
    )


def _page(results=None, store=None) -> str:
    return render_today(workspace(results or _scan(), store))


def _flat(page: str) -> str:
    """The page as one line of collapsed whitespace.

    Prose is wrapped at 78 columns, so a sentence the page certainly contains is
    split across lines. Searching the wrapped text for it would fail for a
    reason that has nothing to do with whether the page says it.
    """
    return " ".join(page.split())


# --------------------------------------------------------------------------
# Width and structure
# --------------------------------------------------------------------------


def test_no_line_exceeds_the_page_width() -> None:
    for rendered in _page().splitlines():
        assert len(rendered) <= _WIDTH, rendered


def test_a_very_long_symbol_and_reason_still_fit() -> None:
    """A terminal that wraps mid-value produces something a reader parses as a
    different value, so long content is wrapped here rather than at the edge."""
    long_line = line(
        symbol="A" * 40,
        thesis=("word " * 60,),
        confirmation=("another " * 40,),
        invalidation=("yet " * 40,),
    )
    from fmis.today import Opportunities, build_queue
    from fmis.today.models import TodayWorkspace

    space = workspace(_scan())
    grouped = Opportunities(
        confirmed=(long_line,), candidates=(), waiting=(), failed=()
    )
    wide = TodayWorkspace(
        reference_time=space.reference_time,
        objective=space.objective,
        source="s" * 200,
        market=space.market,
        portfolio=space.portfolio,
        opportunities=grouped,
        queue=build_queue(grouped.confirmed, ()),
        paper=space.paper,
        journal=space.journal,
        analysis=space.analysis,
        warnings=space.warnings,
        limitations=space.limitations,
    )
    for rendered in render_today(wide).splitlines():
        assert len(rendered) <= _WIDTH, rendered


def test_all_eight_sections_are_present_and_numbered() -> None:
    page = _page()
    for heading in (
        "1. MARKET OVERVIEW",
        "2. PORTFOLIO OVERVIEW",
        "3. TODAY'S OPPORTUNITIES",
        "4. PRIORITY QUEUE",
        "5. PAPER TRADING",
        "6. TRADE JOURNAL",
        "7. RECENT ANALYSIS",
        "8. WORKSPACE WARNINGS",
    ):
        assert heading in page, heading


def test_the_sections_appear_in_the_designed_order() -> None:
    """Capital and existing exposure before opportunity. A dashboard that opens
    with opportunities is a dashboard that produces trades."""
    page = _page()
    order = [
        page.index("ATTENTION"),
        page.index("1. MARKET OVERVIEW"),
        page.index("2. PORTFOLIO OVERVIEW"),
        page.index("3. TODAY'S OPPORTUNITIES"),
        page.index("4. PRIORITY QUEUE"),
        page.index("5. PAPER TRADING"),
        page.index("6. TRADE JOURNAL"),
        page.index("7. RECENT ANALYSIS"),
        page.index("8. WORKSPACE WARNINGS"),
    ]
    assert order == sorted(order)


def test_the_three_attention_lines_come_before_every_section() -> None:
    page = _page()
    assert page.index("ATTENTION") < page.index("1. MARKET OVERVIEW")
    assert page.index("CAPITAL") < page.index("1. MARKET OVERVIEW")
    assert page.index("SIGNALS") < page.index("1. MARKET OVERVIEW")


def test_every_severity_carries_a_word_so_nothing_depends_on_colour() -> None:
    page = _page(
        (result(confirmed_long()), result(waiting())),
    )
    assert "WARNING" in page or "NOTE" in page
    assert "\x1b[" not in page


def test_the_structure_this_module_writes_is_ascii_only() -> None:
    """Rules, labels and separators must read identically in a terminal, a log
    file and a chat client. Engine prose is exempt — it is printed verbatim."""
    source = inspect.getsource(render_module)
    for token in ("─", "═", "…", "•"):
        assert token not in source, token


def test_the_limitations_print_once_at_the_foot_and_not_beside_a_value() -> None:
    """Two registers, never mixed: repetition of invariant text is the fastest
    way to teach a reader to skip a region."""
    page = _page()
    for code, _ in TODAY_LIMITATIONS:
        assert page.count(f"[{code}]") == 1, code
    assert page.index("LIMITATIONS") > page.index("8. WORKSPACE WARNINGS")


# --------------------------------------------------------------------------
# Honesty
# --------------------------------------------------------------------------


def test_an_absence_prints_its_reason_and_the_inference_it_forbids() -> None:
    page = _page()
    assert "not available" in page
    assert "Do not read this as risk being within budget." in _flat(page)
    assert "owned by:" in page


def test_an_empty_capital_section_never_renders_as_a_zero() -> None:
    page = _page()
    assert "Risk committed" in page
    assert "Risk committed          0" not in page


def test_the_measured_figures_print_with_their_sample_and_caveat() -> None:
    page = _page((result(confirmed_long()),) + (
        result(candidate_short_with_watched_level()),
    ))
    spectacular = workspace(
        (result(confirmed_long()),),
    )
    from fmis.today import Opportunities, build_queue
    from fmis.today.models import TodayWorkspace
    from fmis.today.warnings import workspace_warnings

    flagged = line(symbol="BIGRRUSDT", risk_reward=49.0)
    grouped = Opportunities(confirmed=(flagged,), candidates=(), waiting=(), failed=())
    space = TodayWorkspace(
        reference_time=spectacular.reference_time,
        objective=spectacular.objective,
        source=spectacular.source,
        market=spectacular.market,
        portfolio=spectacular.portfolio,
        opportunities=grouped,
        queue=build_queue((flagged,), ()),
        paper=spectacular.paper,
        journal=spectacular.journal,
        analysis=spectacular.analysis,
        warnings=workspace_warnings(
            actionable=(flagged,), failed=(), unreadable=(),
            readable_declined=(), portfolio=spectacular.portfolio,
        ),
        limitations=spectacular.limitations,
    )
    rendered = render_today(space)
    flat = _flat(rendered)
    assert "n = 146" in flat
    assert "superseded" in flat.lower()
    assert "7.7%" in flat
    assert page  # the ordinary page renders too


def test_the_page_makes_no_claim_of_desirability() -> None:
    """`fmis.daily` asserts the same discipline over its own vocabulary.

    The page's two *denial* sentences are removed first. Every renderer in this
    repository states what it refuses to produce, and a substring scan that
    flagged those denials would be flagging the mechanism rather than the
    hazard — the identical reason the repository-wide directional guard parses
    identifiers instead of prose.
    """
    page = _flat(_page()).lower()
    denials = (
        "nothing here is ranked by desirability, scored or recommended.",
        "attention order, never desirability",
        "nothing here is ranked by desirability. the priority queue orders by",
    )
    for denial in denials:
        page = page.replace(denial, " ")
    for word in (
        "best", "top pick", "strongest", "recommend", "score", "rating",
        "ranked", "rank by", "highest quality", "buy this", "worth taking",
    ):
        assert word not in page, word


def test_the_page_states_that_nothing_is_ranked() -> None:
    page = _flat(_page())
    assert "Nothing here is ranked by desirability" in page
    assert "never desirability" in page


def test_the_page_states_that_no_size_is_computed() -> None:
    assert "No position size is computed" in _flat(_page())


def test_wait_is_named_a_successful_result() -> None:
    assert "successful result" in _flat(_page())


def test_a_refused_entry_is_printed_in_its_own_group_with_the_refusal_named() -> None:
    from fmis.today import Opportunities, build_queue
    from fmis.today.models import TodayWorkspace

    base = workspace(_scan())
    stopless = line(symbol="NOSTOPUSDT", stop=None)
    grouped = Opportunities(
        confirmed=(stopless,), candidates=(), waiting=(), failed=()
    )
    space = TodayWorkspace(
        reference_time=base.reference_time,
        objective=base.objective,
        source=base.source,
        market=base.market,
        portfolio=base.portfolio,
        opportunities=grouped,
        queue=build_queue((stopless,), ()),
        paper=base.paper,
        journal=base.journal,
        analysis=base.analysis,
        warnings=base.warnings,
        limitations=base.limitations,
    )
    page = render_today(space)
    assert "IGNORE FOR NOW" in page
    assert "[B-NO-STOP]" in page
    assert "REFUSED" in page
    assert "cannot stop you trading anyway" in _flat(page)


def test_an_empty_queue_says_so_rather_than_printing_nothing() -> None:
    page = _page((result(waiting()),))
    assert "nothing is actionable today" in page


def test_the_page_names_the_next_command_for_every_depth() -> None:
    page = _page()
    assert "fmits setup SYMBOL" in page
    assert "fmits scan" in page


def test_the_wait_reasons_are_printed_verbatim() -> None:
    assessment = waiting()
    page = _flat(_page((result(assessment),)))
    assert " ".join(assessment.thesis[0].split()) in page


def test_a_failed_symbol_is_printed_under_error_and_never_under_wait() -> None:
    page = _page()
    assert "ERROR — no analysis happened for these" in page
    assert "BADUSDT" in page


def test_an_empty_journal_and_analysis_print_their_forbidden_inference() -> None:
    page = _page()
    assert "quiet month" in _flat(page)
    assert "nothing having changed" in _flat(page)


def test_a_populated_journal_and_analysis_print_their_records() -> None:
    from persistence_helpers import analysis_record, journal_entry

    entry = journal_entry()
    citation = analysis_record()
    page = render_today(
        workspace(
            _scan(),
            reading(journal_entries=(entry,), citations=(citation,)),
        )
    )
    assert entry.kind.value in page
    assert citation.record_id in page


def test_a_recollection_is_marked_on_the_page() -> None:
    from persistence_helpers import journal_entry
    from trade_domain_helpers import AT

    hindsight = journal_entry(decision_resolved_at=AT(8))
    page = render_today(
        workspace(_scan(), reading(journal_entries=(hindsight,)))
    )
    assert "(recollection)" in page


def test_a_configured_limit_prints_indeterminate_rather_than_within() -> None:
    from persistence_helpers import risk_budget

    page = render_today(workspace(_scan(), reading(budget=risk_budget())))
    assert "indeterminate — nothing measured against it" in _flat(page)
    assert "status: within" not in page


def test_an_open_position_prints_its_recorded_values() -> None:
    from fmis.ledger import LedgerResolver
    from fmis.positions import fold_positions
    from fmis.today import DUST_POLICY
    from trade_domain_helpers import trade

    folded = fold_positions(
        LedgerResolver(trades=(trade(),), corrections=()).resolved(),
        dust=DUST_POLICY,
    )
    page = render_today(workspace(_scan(), reading(positions=folded)))
    assert folded[0].market.value in page
    assert "no store on this machine" not in page


def test_a_populated_market_snapshot_prints_under_recent_analysis() -> None:
    from trade_domain_helpers import market_snapshot

    snapshot = market_snapshot()
    page = render_today(workspace(_scan(), reading(market_snapshots=(snapshot,))))
    assert snapshot.snapshot_id in page
    assert "market_snapshot" in page


# --------------------------------------------------------------------------
# Purity and failure
# --------------------------------------------------------------------------


def test_the_renderer_rejects_anything_that_is_not_a_workspace() -> None:
    with pytest.raises(TypeError):
        render_today({"market": "everything is fine"})


def test_an_over_wide_line_is_raised_rather_than_printed() -> None:
    """A defect in this module, surfaced rather than silently truncated."""
    original = render_module._WIDTH
    try:
        render_module._WIDTH = 10
        with pytest.raises(TodayError, match="exceeds"):
            render_today(workspace(_scan()))
    finally:
        render_module._WIDTH = original


def test_the_renderer_imports_only_the_model() -> None:
    tree = ast.parse(inspect.getsource(render_module))
    reached = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            reached.add(node.module)
        elif isinstance(node, ast.Import):
            reached.update(alias.name for alias in node.names)
    fmis_imports = {name for name in reached if name.startswith("fmis")}
    assert fmis_imports == {"fmis.today.models"}


def test_the_renderer_calls_no_builder_section_or_engine() -> None:
    tree = ast.parse(inspect.getsource(render_module))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    forbidden = {
        "build_today", "run_today", "read_store", "build_queue",
        "workspace_warnings", "warnings_for_opportunity",
        "opportunities_from_results", "market_overview_from_results",
        "portfolio_overview", "journal_summary", "analysis_summary",
        "run_market_scan",
    }
    assert not (called & forbidden)


def test_rendering_is_deterministic() -> None:
    results = _scan()
    store = reading()
    assert render_today(workspace(results, store)) == render_today(
        workspace(results, store)
    )


def test_the_reference_time_is_printed_in_full() -> None:
    assert REFERENCE.isoformat() in _page()


# --------------------------------------------------------------------------
# The remaining rendered branches
# --------------------------------------------------------------------------


def _with(space, **changes):
    from fmis.today.models import TodayWorkspace

    fields = {
        "reference_time": space.reference_time,
        "objective": space.objective,
        "source": space.source,
        "market": space.market,
        "portfolio": space.portfolio,
        "opportunities": space.opportunities,
        "queue": space.queue,
        "paper": space.paper,
        "journal": space.journal,
        "analysis": space.analysis,
        "warnings": space.warnings,
        "limitations": space.limitations,
    }
    fields.update(changes)
    return TodayWorkspace(**fields)


def test_a_short_value_prints_beside_its_label() -> None:
    """The other half of the branch a long budget note exercises."""
    page = render_today(
        workspace(_scan(), reading(present=True))
    )
    assert any(
        stripped.startswith("Cash") or stripped.startswith("Exposure")
        for stripped in (row.strip() for row in page.splitlines())
    )
    from persistence_helpers import portfolio_snapshot

    with_snapshot = render_today(
        workspace(_scan(), reading(snapshot=portfolio_snapshot()))
    )
    assert "Snapshot as of" in with_snapshot
    assert "Cash " in with_snapshot


def test_unclassifiable_symbols_are_listed_by_name() -> None:
    from tests.test_today_sections import unclassifiable

    page = _page((result(unclassifiable()),))
    assert "could not classify" in _flat(page)
    assert unclassifiable().symbol in page


def test_live_proposals_and_closed_positions_reach_the_journal_block() -> None:
    from datetime import timedelta
    from decimal import Decimal

    from fmis.ledger import LedgerResolver, TradeSide
    from fmis.positions import fold_positions
    from fmis.today import DUST_POLICY
    from trade_domain_helpers import trade

    opening = trade()
    closing = trade(
        side=TradeSide.SELL,
        quantity=opening.quantity,
        price=Decimal("40000"),
        occurred_at=opening.occurred_at + timedelta(hours=2),
    )
    folded = fold_positions(
        LedgerResolver(trades=(opening, closing), corrections=()).resolved(),
        dust=DUST_POLICY,
    )
    page = render_today(
        workspace(
            _scan(),
            reading(
                closed_positions=tuple(p for p in folded if not p.is_open),
                decisions=("P-1 · live · valid until 2026-08-15T00:00:00+00:00",),
            ),
        )
    )
    assert "live proposals (1)" in page
    assert "recently closed" in page
    assert "closed 2026" in page


def test_a_workspace_with_no_warnings_says_none_were_raised() -> None:
    """Unreachable from a real run — every run raises the two standing
    limitations — and rendered correctly anyway, because a model this renderer
    accepts must not produce a section that silently disappears."""
    page = render_today(_with(workspace(_scan()), warnings=()))
    assert "none raised" in page
    assert "8. WORKSPACE WARNINGS" in page


def test_an_opportunity_with_no_risk_reward_prints_no_ratio() -> None:
    """The negative branch of the R:R header, in both places it appears."""
    from fmis.today import Opportunities, build_queue

    bare = line(symbol="NORRUSDT", risk_reward=None, target=None, thesis=())
    grouped = Opportunities(confirmed=(bare,), candidates=(), waiting=(), failed=())
    page = render_today(
        _with(
            workspace(_scan()),
            opportunities=grouped,
            queue=build_queue((bare,), ()),
        )
    )
    assert "NORRUSDT" in page
    assert "R:R" not in page


def test_a_queue_entry_with_no_thesis_still_renders() -> None:
    from fmis.today import Opportunities, build_queue

    bare = line(symbol="NOTHESIS", thesis=())
    grouped = Opportunities(confirmed=(bare,), candidates=(), waiting=(), failed=())
    page = render_today(
        _with(
            workspace(_scan()),
            opportunities=grouped,
            queue=build_queue((bare,), ()),
        )
    )
    assert "NOTHESIS" in page


def test_the_width_guard_fires_at_exactly_one_column_over() -> None:
    """Pins the comparison itself. A guard that only fires far past the edge
    would let a 79-column line through, and 79 is the failure that actually
    happens — a value that fits in the author's terminal and not the reader's.
    """
    render_module._require_fits(["x" * _WIDTH])
    with pytest.raises(TodayError, match=f"of {_WIDTH + 1} exceeds"):
        render_module._require_fits(["x" * (_WIDTH + 1)])
