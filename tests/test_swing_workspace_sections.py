"""Milestone BS — the adapters, one at a time.

Each section is a projection of an object another package built. These tests
assert three things about every one of them: the value shown is the value that
package produced, an absence is stated rather than blanked, and no arithmetic
happened on the way.

The paper tests build a **real store** through the product's own commands and
read a **real** `TradeMonitor`, because the whole claim of that section is that
its figures are the simulator's own.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fmis.accounts import AccountId, Book
from fmis.money import AssetCode, Quantity
from fmis.paper import (
    PAPER_DUST_POLICY,
    ActivateRequest,
    activate_trade,
    load_paper_trade,
    run_simulation,
)
from fmis.persistence import TradingStore
from fmis.setup_evidence import SetupEvidenceError
from fmis.snapshotting import TradeDirection
from fmis.swing_setup import SetupState
from fmis.swing_workspace import (
    PAPER_LIVE_STATES,
    BookExposure,
    EvidenceDigest,
    NoTradeGroup,
    SwingWorkspaceError,
    UnanalysedSymbol,
    aggregated_warnings,
    books_from,
    evidence_digest_for,
    global_summary,
    identity_ref_for,
    no_trade_groups,
    paper_positions,
    paper_status_for,
    require_actionable_split,
    risk_state_of,
    unanalysed_from,
)
from fmis.today import (
    NotAvailable,
    WarningClass,
    WarningSeverity,
    WorkspaceWarning,
    build_today,
    read_store,
)
from fmis.trade_capture import PlanRequest, record_plan
from fmis.trade_lifecycle import EntryType

from paper_helpers import MARKET, START, at, bar
from tests.swing_workspace_helpers import (
    assessment,
    failed_result,
    reading,
    result,
    run_of,
    workspace_of,
)


# ---------------------------------------------------------------------------
# Evidence digest — the projection is called, never re-implemented
# ---------------------------------------------------------------------------


def test_the_digest_counts_the_projections_own_groups() -> None:
    subject = assessment("BTCUSDT", state=SetupState.CONFIRMED)
    from fmis.setup_evidence import project_setup_evidence

    report = project_setup_evidence(subject)
    digest = evidence_digest_for(subject)

    assert digest.supporting == len(report.supporting)
    assert digest.conflicting == len(report.conflicting)
    assert digest.missing == len(report.missing)
    assert digest.unavailable == len(report.unavailable)
    assert digest.decision_ready is report.decision_ready
    assert digest.decision_ready_reason == report.decision_ready_reason


def test_a_confirmed_setup_awaits_nothing_and_a_candidate_does() -> None:
    confirmed = evidence_digest_for(assessment(state=SetupState.CONFIRMED))
    candidate = evidence_digest_for(assessment(state=SetupState.CANDIDATE))

    assert confirmed.missing == 0
    assert candidate.missing >= 1


def test_the_digest_carries_the_correlation_caveats_when_independence_fails() -> None:
    digest = evidence_digest_for(assessment())

    assert digest.independence_established is False
    assert digest.caveats


def test_a_digest_cannot_claim_independence_and_caveats_at_once() -> None:
    with pytest.raises(SwingWorkspaceError, match="two different things"):
        EvidenceDigest(
            supporting=1,
            conflicting=0,
            missing=0,
            unavailable=0,
            agreeing_families=(),
            conflicting_families=(),
            independence_established=True,
            decision_ready=True,
            decision_ready_reason="stated",
            caveats=("but not really",),
        )


def test_an_established_independence_carries_no_caveats_onto_the_row(
    monkeypatch,
) -> None:
    """The caveats *are* the reasons independence does not hold. A digest that
    reported both would say two different things, and `EvidenceDigest` refuses
    it — so the digest drops them rather than letting the page fail to build."""
    from dataclasses import dataclass

    import fmis.swing_workspace.sections as module

    @dataclass(frozen=True)
    class _Family:
        value: str

    @dataclass(frozen=True)
    class _Confluence:
        agreeing_families: tuple
        conflicting_families: tuple
        independence_established: bool
        caveats: tuple

    @dataclass(frozen=True)
    class _Report:
        supporting: tuple
        conflicting: tuple
        missing: tuple
        unavailable: tuple
        confluence: _Confluence
        decision_ready: bool
        decision_ready_reason: str

    report = _Report(
        supporting=(1, 2),
        conflicting=(),
        missing=(),
        unavailable=(),
        confluence=_Confluence(
            agreeing_families=(_Family("trend"), _Family("volume")),
            conflicting_families=(),
            independence_established=True,
            caveats=("a correlation that no longer applies",),
        ),
        decision_ready=True,
        decision_ready_reason="stated",
    )
    monkeypatch.setattr(module, "project_setup_evidence", lambda *a, **k: report)
    digest = module.evidence_digest_for(assessment())

    assert digest.independence_established is True
    assert digest.caveats == ()
    assert digest.agreeing_families == ("trend", "volume")


def test_a_projection_refusal_is_isolated_to_its_own_row(monkeypatch) -> None:
    """One symbol's unprojectable evidence must not remove every other symbol's."""
    import fmis.swing_workspace.sections as module

    def _refuse(*_args, **_kwargs):
        raise SetupEvidenceError("two items shared one key")

    monkeypatch.setattr(module, "project_setup_evidence", _refuse)
    digest = module.evidence_digest_for(assessment())

    assert isinstance(digest, NotAvailable)
    assert "refused this setup" in digest.reason
    assert "no evidence behind it" in digest.forbidden_inference


def test_a_programmer_error_in_the_projection_still_propagates(monkeypatch) -> None:
    """A surface that swallows a `TypeError` renders a clean page over broken code."""
    import fmis.swing_workspace.sections as module

    def _broken(*_args, **_kwargs):
        raise TypeError("a defect, not a refusal")

    monkeypatch.setattr(module, "project_setup_evidence", _broken)
    with pytest.raises(TypeError, match="a defect"):
        module.evidence_digest_for(assessment())


# ---------------------------------------------------------------------------
# Identity — the same call `fmits setup` and `fmits evidence` already make
# ---------------------------------------------------------------------------


def test_the_identity_is_the_one_the_setup_page_already_prints() -> None:
    import fmis
    from fmis.setup_observation import observe_setup_series
    from fmis.trade_capture import market_from_symbol

    subject = assessment("BTCUSDT")
    expected = observe_setup_series(
        [subject],
        market=market_from_symbol("BTCUSDT"),
        code_version=fmis.__version__,
        occurrence_gap_bars=0,
    ).occurrences[-1].identity

    reference, text = identity_ref_for(subject)

    assert text == expected
    assert reference.setup_id == expected


def test_two_readings_of_one_idea_carry_one_identity() -> None:
    _, first = identity_ref_for(assessment("BTCUSDT", bar=0))
    _, second = identity_ref_for(assessment("BTCUSDT", bar=4))

    assert first == second


def test_a_window_relative_index_never_changes_the_identity() -> None:
    """`BG-D1`'s whole point: identity may not move when the window moves."""
    _, first = identity_ref_for(assessment("BTCUSDT", swing_index=5))
    _, second = identity_ref_for(assessment("BTCUSDT", swing_index=417))

    assert first == second


def test_the_identity_call_passes_the_named_gap_constant_not_a_literal() -> None:
    """`ONE_READING_GAP_BARS` is zero and cannot matter for a single reading, so
    a mutant changing the value at the call site is equivalent *today*. It stops
    being equivalent the moment a surface passes a series, which is exactly what
    the constant's own docstring warns about — so the call site is pinned to the
    name rather than to the value."""
    import ast
    import inspect
    import pathlib

    import fmis.swing_workspace.sections as module

    source = pathlib.Path(inspect.getfile(module)).read_text(encoding="utf-8")
    passed = [
        kw.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "occurrence_gap_bars"
    ]

    assert len(passed) == 1
    assert isinstance(passed[0], ast.Name), ast.dump(passed[0])
    assert passed[0].id == "ONE_READING_GAP_BARS"
    from fmis.swing_workspace import ONE_READING_GAP_BARS

    assert ONE_READING_GAP_BARS == 0


def test_a_symbol_that_names_no_market_states_why_it_has_no_identity() -> None:
    reference, text = identity_ref_for(assessment("BTCEUR"))

    assert reference is None
    assert isinstance(text, NotAvailable)
    assert "could not be resolved to a market" in text.reason


def test_a_wait_reading_has_no_occurrence_to_name() -> None:
    reference, text = identity_ref_for(assessment("BTCUSDT", direction=None))

    assert reference is None
    assert isinstance(text, NotAvailable)
    assert "no occurrence" in text.reason


# ---------------------------------------------------------------------------
# Paper status on a setup row
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> TradingStore:
    return TradingStore(tmp_path / "store", dust=PAPER_DUST_POLICY)


def _open_paper_trade(store: TradingStore):
    plan = record_plan(
        store,
        PlanRequest(
            market=MARKET,
            book=Book.PAPER,
            direction=TradeDirection.LONG,
            stop=Decimal("95"),
            targets=(Decimal("110"), Decimal("120")),
            committed_at=START,
            written_at=START,
            author="owner",
            confidence="medium",
            code_version="test",
        ),
    ).view.plan
    subject = activate_trade(
        store,
        ActivateRequest(
            plan_id=plan.plan_id,
            account=AccountId("paper"),
            quantity=Quantity(Decimal("1"), AssetCode("BTC")),
            entry_type=EntryType.STOP_ENTRY,
            entry_price=Decimal("100"),
            interval="1h",
            activated_at=START,
            written_at=START,
            code_version="test",
            fractions=(Decimal("0.5"), Decimal("0.5")),
        ),
    ).activation
    run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={
            "BTCUSDT": (
                bar(0, "99", "101", "98", "100"),
                bar(1, "100", "112", "99", "111"),
            )
        },
    )
    return subject


def _views(store: TradingStore, subject) -> tuple:
    return (
        load_paper_trade(
            store, subject.activation_id, dust=PAPER_DUST_POLICY, at=at(8)
        ),
    )


def test_a_live_paper_trade_is_named_on_the_setup_row(store) -> None:
    subject = _open_paper_trade(store)
    positions, _ = paper_positions(_views(store, subject), read=True)

    status = paper_status_for("BTCUSDT", positions, read=True)

    assert subject.activation_id in status
    assert positions[0].state in status


def test_a_paper_trade_on_another_market_never_reaches_this_row() -> None:
    """The match is on the market, not merely on the trade being live."""
    from fmis.swing_workspace import PaperPosition

    elsewhere = PaperPosition(
        activation_id="ACT-9",
        market="ETHUSDT",
        state="open",
        open_size="1 ETH",
        bars_in_trade=1,
        stop_widenings=0,
        entry="100",
        initial_risk="10 USDT",
        total_r="0.1",
        max_favourable_r="0.2",
        max_adverse_r="-0.1",
        stop="95",
        initial_stop="95",
    )

    assert paper_status_for("BTCUSDT", (elsewhere,), read=True) == (
        "none in the paper book"
    )
    assert "ACT-9" in paper_status_for("ETHUSDT", (elsewhere,), read=True)


def test_a_market_with_no_paper_trade_names_the_book_it_checked() -> None:
    """*"none"* alone, beside a real open position, is the wrong half of the
    truth — so the row says which book it looked in."""
    assert paper_status_for("BTCUSDT", (), read=True) == "none in the paper book"


def test_an_unread_store_states_that_it_did_not_look() -> None:
    """*"There is no paper trade"* and *"this page did not look"* differ."""
    status = paper_status_for("BTCUSDT", (), read=False)

    assert isinstance(status, NotAvailable)
    assert "did not look" in status.forbidden_inference


def test_the_paper_row_carries_the_simulators_own_figures(store) -> None:
    subject = _open_paper_trade(store)
    view = _views(store, subject)[0]
    positions, note = paper_positions((view,), read=True)
    row = positions[0]

    assert row.activation_id == subject.activation_id
    assert row.market == "BTCUSDT"
    assert row.bars_in_trade == view.monitor.bars_in_trade
    assert row.stop_widenings == view.monitor.stop_widenings
    assert row.entry == str(view.monitor.entry_price)
    assert isinstance(note, str)


def test_an_absent_excursion_is_stated_rather_than_printed_as_zero(store) -> None:
    subject = _open_paper_trade(store)
    positions, _ = paper_positions(_views(store, subject), read=True)
    excursion = positions[0].max_favourable_r

    if isinstance(excursion, NotAvailable):
        assert "zero" in excursion.forbidden_inference
    else:  # pragma: no cover - depends on the simulator having observed bars
        assert excursion.strip()


def test_an_unread_store_produces_no_rows_and_says_why() -> None:
    positions, note = paper_positions((), read=False)

    assert positions == ()
    assert isinstance(note, NotAvailable)
    assert "did not look" in note.forbidden_inference


def test_the_live_state_set_is_a_subset_of_the_lifecycles_own_states() -> None:
    from fmis.trade_lifecycle import TradeLifecycleState

    assert PAPER_LIVE_STATES <= {state.value for state in TradeLifecycleState}


def test_the_summary_counts_only_the_trades_that_are_still_running(store) -> None:
    subject = _open_paper_trade(store)
    positions, _ = paper_positions(_views(store, subject), read=True)
    workspace = workspace_of(
        result(assessment()), store=reading(paper_trades=positions and ())
    )

    assert workspace.summary.paper_positions == 0
    assert all(position.state for position in positions)


# ---------------------------------------------------------------------------
# Books, risk state, exposure
# ---------------------------------------------------------------------------


def test_a_store_with_no_position_has_no_book_rows() -> None:
    workspace = workspace_of(result(assessment()))

    assert workspace.books == ()


def test_books_are_counted_from_the_positions_the_page_already_lists() -> None:
    from fmis.today import PortfolioOverview, PositionLine
    from datetime import datetime, timezone

    def _position(book: str) -> PositionLine:
        return PositionLine(
            market="BTCUSDT",
            book=book,
            direction="up",
            quantity="1 BTC",
            average_entry="100",
            opened_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            trade_count=1,
            event_ids=("e1",),
        )

    absent = NotAvailable(
        reason="nothing was measured", owned_by="a later slice", forbidden_inference="none"
    )
    portfolio = PortfolioOverview(
        store_root="/tmp/store",
        store_present=True,
        open_positions=(_position("paper"), _position("swing"), _position("paper")),
        limits=(),
        budget_note=absent,
        committed_risk=absent,
        available_risk=absent,
        cash=absent,
        exposure=absent,
    )
    books = books_from(portfolio, None)

    assert {book.label: book.open_positions for book in books} == {
        "paper": 2,
        "swing": 1,
    }
    assert all(isinstance(book.market_value, NotAvailable) for book in books)


def test_books_from_refuses_anything_but_a_portfolio_overview() -> None:
    with pytest.raises(TypeError, match="PortfolioOverview"):
        books_from(object(), None)


def test_a_book_row_with_no_position_is_not_representable() -> None:
    with pytest.raises(SwingWorkspaceError, match="cannot be negative"):
        BookExposure(label="paper", open_positions=-1, market_value="1 USDT")


def test_the_risk_state_states_the_two_counts_when_a_budget_exists() -> None:
    from fmis.today import LimitLine, PortfolioOverview

    absent = NotAvailable(
        reason="nothing was measured", owned_by="a later slice", forbidden_inference="none"
    )
    portfolio = PortfolioOverview(
        store_root="/tmp/store",
        store_present=True,
        open_positions=(),
        limits=(
            LimitLine(
                limit_id="L1",
                scope="portfolio",
                stated_limit="2 percent",
                severity="hard",
                current=absent,
                status=absent,
            ),
        ),
        budget_note="budget B1 · policy version 1",
        committed_risk=absent,
        available_risk=absent,
        cash=absent,
        exposure=absent,
    )

    assert risk_state_of(portfolio) == (
        "budget B1 · policy version 1 · 1 limit(s) recorded · 0 measured "
        "against this page"
    )


def test_the_risk_state_carries_the_budget_absence_through_unchanged() -> None:
    workspace = workspace_of(result(assessment()))

    assert isinstance(workspace.summary.risk_state, NotAvailable)


# ---------------------------------------------------------------------------
# Warnings: aggregated, never invented, never duplicated
# ---------------------------------------------------------------------------


def _warning(code: str, subjects: tuple[str, ...] = ()) -> WorkspaceWarning:
    return WorkspaceWarning(
        code=code,
        kind=WarningClass.RISK,
        severity=WarningSeverity.WARNING,
        statement="a stated observation",
        evidence="a stated source",
        subjects=subjects,
    )


def test_the_days_warnings_arrive_unchanged_and_in_their_own_order() -> None:
    """Identity, not equality: a warning that needs no merge must be passed
    through rather than rebuilt, or the page is showing a copy of the day's
    finding rather than the finding."""
    first, second = _warning("A"), _warning("B")
    merged = aggregated_warnings((first, second), ())

    assert merged[0] is first
    assert merged[1] is second


def test_one_rule_firing_twice_is_one_warning_with_two_subjects() -> None:
    merged = aggregated_warnings(
        (_warning("A", ("BTCUSDT",)), _warning("A", ("ETHUSDT",))), ()
    )

    assert len(merged) == 1
    assert merged[0].subjects == ("BTCUSDT", "ETHUSDT")


def test_a_repeated_subject_is_not_listed_twice() -> None:
    """And the surviving warning is the **first** object, not a rebuild of it:
    a merge that adds nothing must leave the day's own finding in place."""
    first = _warning("A", ("BTCUSDT",))
    merged = aggregated_warnings((first, _warning("A", ("BTCUSDT",))), ())

    assert merged[0].subjects == ("BTCUSDT",)
    assert merged[0] is first


def test_the_simulators_own_warnings_reach_the_page(store) -> None:
    """`fmits today` never surfaced them; a halted trade waits for the owner."""
    subject = _open_paper_trade(store)
    views = _views(store, subject)
    raised = aggregated_warnings((), views)

    codes = {warning.code for warning in raised}
    assert codes == {warning.code for view in views for warning in view.warnings}
    for warning in raised:
        assert subject.activation_id in " ".join(warning.subjects)


def test_a_non_warning_in_the_input_is_refused() -> None:
    with pytest.raises(TypeError, match="WorkspaceWarning"):
        aggregated_warnings(("not a warning",), ())


# ---------------------------------------------------------------------------
# The split guard, and the two small converters
# ---------------------------------------------------------------------------


def test_a_symbol_in_both_actionable_groups_is_refused() -> None:
    from tests.test_swing_workspace_ranking import line

    with pytest.raises(SwingWorkspaceError, match="both actionable states"):
        require_actionable_split((line("BTCUSDT"),), (line("BTCUSDT"),))


def test_a_clean_split_passes_silently() -> None:
    from tests.test_swing_workspace_ranking import line

    assert require_actionable_split((line("BTCUSDT"),), (line("ETHUSDT"),)) is None


def test_the_failed_symbols_keep_their_reason() -> None:
    workspace = workspace_of(failed_result("DOGEUSDT", "BinanceError: 451"))
    converted = unanalysed_from(workspace.unanalysed)

    assert converted == (UnanalysedSymbol(symbol="DOGEUSDT", detail="BinanceError: 451"),)


def test_a_no_trade_group_with_no_symbols_is_not_representable() -> None:
    with pytest.raises(SwingWorkspaceError, match="not a group"):
        NoTradeGroup(reason="a reason", classification="read and declined", symbols=())


def test_no_trade_groups_ignore_failed_and_actionable_results() -> None:
    groups = no_trade_groups(
        (
            result(assessment("BTCUSDT", state=SetupState.CONFIRMED)),
            failed_result("ETHUSDT"),
            result(assessment("SOLUSDT", direction=None, thesis=("quiet",))),
        )
    )

    assert len(groups) == 1
    assert groups[0].symbols == ("SOLUSDT",)


def test_the_global_summary_refuses_anything_but_a_market_overview() -> None:
    workspace = workspace_of(result(assessment()))
    with pytest.raises(TypeError, match="MarketOverview"):
        global_summary(
            market=object(),
            confirmed=0,
            candidates=0,
            waiting=0,
            unanalysed=0,
            portfolio=workspace.portfolio,
            paper=(),
            store_read=True,
        )


def test_an_unread_store_states_that_the_exposure_was_never_looked_at() -> None:
    workspace = workspace_of(result(assessment()), store=reading(present=False))

    assert isinstance(workspace.summary.open_exposure, NotAvailable)
    assert "was not read" in workspace.summary.open_exposure.reason


# ---------------------------------------------------------------------------
# The branches a plain fixture does not reach
# ---------------------------------------------------------------------------


def test_a_row_with_no_assessment_still_ranks_and_states_both_absences() -> None:
    """The ordering reads only the line, so a row missing its assessment keeps
    its place rather than vanishing — and says what could not be attached."""
    from fmis.swing_workspace import ranked_setups
    from tests.test_swing_workspace_ranking import line

    rows = ranked_setups(
        [line("BTCUSDT")],
        watchlist=("BTCUSDT",),
        assessments={},
        paper=(),
        store_read=True,
    )

    assert len(rows) == 1
    assert isinstance(rows[0].identity, NotAvailable)
    assert isinstance(rows[0].evidence, NotAvailable)
    assert "no assessment was supplied" in rows[0].identity.reason


def test_the_book_axis_is_the_exposure_engines_own_dimension() -> None:
    """Compared as a string; pinned here to the enum it must equal."""
    from fmis.portfolio_risk import ExposureDimension
    from fmis.swing_workspace import BOOK_AXIS

    assert BOOK_AXIS == ExposureDimension.BOOK.value


def test_a_priced_book_carries_the_exposure_engines_own_figure() -> None:
    """The `BOOK` breakdown `build_state` already folded — never a second sum."""
    from dataclasses import dataclass
    from datetime import datetime, timezone
    from decimal import Decimal

    from fmis.money import AssetCode, Money
    from fmis.portfolio_risk import ExposureDimension
    from fmis.today import PortfolioOverview, PositionLine

    @dataclass(frozen=True)
    class _Entry:
        key: str
        gross: object

    @dataclass(frozen=True)
    class _Breakdown:
        dimension: object
        entries: tuple

    @dataclass(frozen=True)
    class _State:
        breakdowns: tuple

    @dataclass(frozen=True)
    class _Valuation:
        state: _State

    gross = Money(Decimal("1234.50"), AssetCode("USDT"))
    # The ACCOUNT axis is listed **after** the BOOK axis and shares its key: an
    # owner whose account is named "paper" is ordinary, and a read that did not
    # filter on the axis would take the account's figure for the book's. The
    # mutation harness found this: the filter survived every earlier fixture
    # because no two axes had ever shared a key in one.
    other = Money(Decimal("999999.99"), AssetCode("USDT"))
    valuation = _Valuation(
        state=_State(
            breakdowns=(
                _Breakdown(
                    dimension=ExposureDimension.BOOK, entries=(_Entry("paper", gross),)
                ),
                _Breakdown(
                    dimension=ExposureDimension.ACCOUNT,
                    entries=(_Entry("paper", other),),
                ),
            )
        )
    )
    absent = NotAvailable(
        reason="nothing was measured", owned_by="a later slice", forbidden_inference="n"
    )
    portfolio = PortfolioOverview(
        store_root="/tmp/store",
        store_present=True,
        open_positions=(
            PositionLine(
                market="BTCUSDT",
                book="paper",
                direction="up",
                quantity="1 BTC",
                average_entry="100",
                opened_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                trade_count=1,
                event_ids=("e1",),
            ),
        ),
        limits=(),
        budget_note=absent,
        committed_risk=absent,
        available_risk=absent,
        cash=absent,
        exposure=absent,
    )
    books = books_from(portfolio, valuation)

    assert len(books) == 1
    assert books[0].market_value == f"{gross.text} {gross.asset}"


def test_a_book_the_exposure_engine_did_not_price_states_the_absence() -> None:
    from dataclasses import dataclass
    from datetime import datetime, timezone

    from fmis.today import PortfolioOverview, PositionLine

    @dataclass(frozen=True)
    class _State:
        breakdowns: tuple

    @dataclass(frozen=True)
    class _Valuation:
        state: _State

    absent = NotAvailable(
        reason="nothing was measured", owned_by="a later slice", forbidden_inference="n"
    )
    portfolio = PortfolioOverview(
        store_root="/tmp/store",
        store_present=True,
        open_positions=(
            PositionLine(
                market="BTCUSDT",
                book="swing",
                direction="up",
                quantity="1 BTC",
                average_entry="100",
                opened_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                trade_count=1,
                event_ids=("e1",),
            ),
        ),
        limits=(),
        budget_note=absent,
        committed_risk=absent,
        available_risk=absent,
        cash=absent,
        exposure=absent,
    )
    books = books_from(portfolio, _Valuation(state=_State(breakdowns=())))

    assert isinstance(books[0].market_value, NotAvailable)
    assert "no price source" in books[0].market_value.reason


def test_a_trade_with_no_fill_states_its_absent_risk_rather_than_zero() -> None:
    """A monetary absence is carried through with the simulator's own reason."""
    from dataclasses import dataclass

    from fmis.provenance import Absent

    @dataclass(frozen=True)
    class _State:
        value: str

    @dataclass(frozen=True)
    class _Market:
        pair_symbol: str

    @dataclass(frozen=True)
    class _Activation:
        market: _Market

    @dataclass(frozen=True)
    class _Monitor:
        remaining: str
        initial_stop: object
        effective_stop: object
        entry_price: object
        initial_risk: object
        total_r: object
        max_favourable_r: object
        max_adverse_r: object
        bars_in_trade: int
        stop_widenings: int

    @dataclass(frozen=True)
    class _View:
        activation_id: str
        activation: _Activation
        state: _State
        monitor: _Monitor

    from decimal import Decimal

    view = _View(
        activation_id="ACT-1",
        activation=_Activation(market=_Market(pair_symbol="BTCUSDT")),
        state=_State(value="pending"),
        monitor=_Monitor(
            remaining="1 BTC",
            initial_stop=Decimal("95"),
            effective_stop=Decimal("95"),
            entry_price=Absent("no fill has opened this trade"),
            initial_risk=Absent("no entry to measure risk from"),
            total_r=Absent("neither half of the R multiple is stateable"),
            max_favourable_r=Absent("no excursion has been observed"),
            max_adverse_r=Absent("no excursion has been observed"),
            bars_in_trade=0,
            stop_widenings=0,
        ),
    )
    positions, _ = paper_positions((view,), read=True)
    row = positions[0]

    assert isinstance(row.initial_risk, NotAvailable)
    assert row.initial_risk.reason == "no entry to measure risk from"
    assert "is zero" in row.initial_risk.forbidden_inference
    assert isinstance(row.entry, NotAvailable)


# ---------------------------------------------------------------------------
# The paper/live mismatch: a row must not answer half the question
# ---------------------------------------------------------------------------


def _position_line(book: str = "swing", market: str = "BTCUSDT"):
    from datetime import datetime, timezone

    from fmis.today import PositionLine

    return PositionLine(
        market=market,
        book=book,
        direction="up",
        quantity="0.5 BTC",
        average_entry="61000",
        opened_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        trade_count=1,
        event_ids=("e1",),
    )


def test_a_row_names_the_recorded_position_the_owner_already_holds() -> None:
    from fmis.swing_workspace import holding_for

    text = holding_for("BTCUSDT", (_position_line(),), read=True)

    assert "swing" in text and "0.5 BTC" in text and "61000" in text


def test_a_market_the_owner_holds_nothing_in_says_so_across_every_book() -> None:
    from fmis.swing_workspace import holding_for

    assert holding_for("ETHUSDT", (_position_line(),), read=True) == (
        "none recorded, in any book"
    )


def test_an_unread_store_never_claims_the_owner_holds_nothing() -> None:
    from fmis.swing_workspace import holding_for

    held = holding_for("BTCUSDT", (), read=False)

    assert isinstance(held, NotAvailable)
    assert "did not look" in held.forbidden_inference


def test_two_books_on_one_market_are_named_separately_never_totalled() -> None:
    """`AP` §5.5: the book is the economic classification, and adding a
    simulated position to a real one would put play money into a statement
    about the owner's capital."""
    from fmis.swing_workspace import holding_for

    text = holding_for(
        "BTCUSDT",
        (_position_line("swing"), _position_line("paper")),
        read=True,
    )

    assert text.count("0.5 BTC") == 2
    assert "swing:" in text and "paper:" in text


def test_the_holding_reaches_the_ranked_row_from_the_pages_own_positions() -> None:
    from fmis.swing_workspace import ranked_setups
    from tests.test_swing_workspace_ranking import line

    rows = ranked_setups(
        [line("BTCUSDT")],
        watchlist=("BTCUSDT",),
        assessments={},
        paper=(),
        positions=(_position_line(),),
        store_read=True,
    )

    assert "swing" in rows[0].held
    assert rows[0].paper_status == "none in the paper book"
