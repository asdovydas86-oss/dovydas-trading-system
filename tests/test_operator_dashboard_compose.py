"""The composition root: four reads, each isolated, and no fifth.

The two properties asserted here are the ones a dashboard normally gets wrong —
fetching the world once per widget, and letting one source's outage blank the
whole page.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import swing_workspace_helpers as W
from operator_dashboard_helpers import (
    AT,
    Boom,
    benchmark,
    dark,
    macro_of,
    pulse_of,
    reading_for,
)

from fmis.macro import MacroError
from fmis.market_pulse import MarketPulseError
from fmis.operator_dashboard import (
    REFRESH_READS,
    DashboardSectionStatus,
    SourceState,
    build_snapshot,
    refresh,
)
from fmis.swing_workspace import SwingWorkspaceError


class _Recorder:
    """Counts calls and returns a canned value, or raises a canned failure."""

    def __init__(self, value=None, error: BaseException | None = None) -> None:
        self.value = value
        self.error = error
        self.calls: list[dict] = []

    def __call__(self, *args, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.value


def _runners(**overrides):
    workspace = W.workspace_of(W.result(W.assessment("BTCUSDT")))
    runners = {
        "workspace_runner": _Recorder(workspace),
        "pulse_runner": _Recorder(pulse_of([reading_for(benchmark("BTC"))])),
        "macro_runner": _Recorder(macro_of([reading_for(benchmark("SPX"))])),
        "statistics_runner": _Recorder(_statistics()),
    }
    runners.update(overrides)
    return runners


def _statistics():
    """A real, empty `StatisticsReport` — an owner who has never traded."""
    from fmis.statistics import DEFAULT_SAMPLE_POLICY
    from fmis.statistics.report import StatisticsReport
    from fmis.provenance import Absent

    return StatisticsReport(
        reference_time=AT,
        store_root="/tmp/none",
        present=False,
        policy=DEFAULT_SAMPLE_POLICY,
        assets=(),
        refused=(),
        as_of=Absent("no point-in-time cut was requested"),
    )


# ---------------------------------------------------------------------------
# One refresh, four reads
# ---------------------------------------------------------------------------


def test_one_refresh_performs_exactly_four_reads_one_each() -> None:
    """**The failure mode this asserts against:** a pulse card fetching the
    market, a macro card fetching it again, a swing table re-scanning, a
    portfolio panel re-reading the store — four copies of the world and four
    different instants behind one header."""
    runners = _runners()
    refresh(refreshed_at=AT, **runners)
    assert [len(runner.calls) for runner in runners.values()] == [1, 1, 1, 1]


def test_the_named_reads_are_the_reads_that_happen() -> None:
    """`REFRESH_READS` is a contract, not a comment: a fifth read is a decision
    somebody makes on purpose rather than one that happens because fetching was
    easy."""
    assert len(REFRESH_READS) == 4
    runners = _runners()
    refresh(refreshed_at=AT, **runners)
    assert sum(len(runner.calls) for runner in runners.values()) == len(REFRESH_READS)


def test_three_sections_share_the_single_workspace_read() -> None:
    """Swing, portfolio and paper come from one call — one scan, one store
    read, one valuation. A second store read would put two instants on one
    page."""
    runners = _runners()
    snapshot = refresh(refreshed_at=AT, **runners)
    assert len(runners["workspace_runner"].calls) == 1
    for section in (snapshot.swing, snapshot.portfolio, snapshot.paper):
        assert not section.failed


def test_every_read_is_given_the_same_instant() -> None:
    """One page, one reference time. Otherwise the sections describe different
    moments under one header."""
    runners = _runners()
    refresh(refreshed_at=AT, **runners)
    assert runners["pulse_runner"].calls[0]["as_of"] == AT
    assert runners["macro_runner"].calls[0]["as_of"] == AT
    assert runners["workspace_runner"].calls[0]["reference_time"] == AT
    assert runners["statistics_runner"].calls[0]["at"] == AT


def test_a_past_reference_time_is_honoured_while_the_refresh_instant_is_not() -> None:
    """A replayed page states a past market instant and still reports honestly
    when it was built."""
    past = AT - timedelta(days=2)
    runners = _runners()
    snapshot = refresh(refreshed_at=AT, reference_time=past, **runners)
    assert snapshot.refreshed_at == AT
    assert snapshot.reference_time == past
    assert runners["pulse_runner"].calls[0]["as_of"] == past


# ---------------------------------------------------------------------------
# Section isolation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "runner,error,failed,survivors",
    [
        (
            "macro_runner",
            MacroError("FRED did not answer"),
            ["macro"],
            ["pulse", "swing", "portfolio", "paper", "performance"],
        ),
        (
            "pulse_runner",
            MarketPulseError("the venue returned 503"),
            ["pulse"],
            ["macro", "swing", "portfolio", "paper", "performance"],
        ),
        (
            "workspace_runner",
            SwingWorkspaceError("the store could not be read"),
            ["swing", "portfolio", "paper"],
            ["pulse", "macro", "performance"],
        ),
    ],
)
def test_one_sources_outage_never_costs_the_other_sections(
    runner, error, failed, survivors
) -> None:
    """Pulse works, macro fails, swing works, portfolio works — and the page
    still renders every one of them."""
    runners = _runners(**{runner: _Recorder(error=error)})
    snapshot = refresh(refreshed_at=AT, **runners)
    assert sorted(section.name for section in snapshot.failed_sections) == sorted(failed)
    for name in survivors:
        assert not getattr(snapshot, name).failed


def test_a_failed_section_states_the_error_type_and_its_message() -> None:
    """*"HTTPError: 503"* tells the owner the provider answered and refused;
    *"503"* alone could be anything."""
    runners = _runners(macro_runner=_Recorder(error=MacroError("FRED said no")))
    snapshot = refresh(refreshed_at=AT, **runners)
    assert snapshot.macro.unavailable_reason == "MacroError: FRED said no"


def test_a_programming_defect_propagates_and_is_not_dressed_as_a_data_failure() -> None:
    """**A dashboard that renders its own bugs as a tidy amber panel is a
    dashboard that hides them.** The `except` clauses name exception families;
    not one of them is `except Exception`."""
    runners = _runners(macro_runner=_Recorder(error=KeyError("a defect")))
    with pytest.raises(KeyError):
        refresh(refreshed_at=AT, **runners)


def test_every_domain_failing_still_produces_a_renderable_snapshot() -> None:
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        workspace_error=Boom("no store"),
        pulse_error=Boom("no venue"),
        macro_error=Boom("no FRED"),
        statistics_error=Boom("no corpus"),
    )
    assert len(snapshot.failed_sections) == 6
    assert not snapshot.health.failed
    assert snapshot.counts.scanned == 0


def test_a_domain_supplied_both_an_output_and_a_failure_is_refused() -> None:
    """Which one the page showed would depend on the order it checked them."""
    with pytest.raises(ValueError, match="both an output and a failure"):
        build_snapshot(
            refreshed_at=AT,
            reference_time=AT,
            pulse=pulse_of([reading_for(benchmark("BTC"))]),
            pulse_error=Boom("and also this"),
        )


# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------


def test_an_empty_corpus_is_empty_and_not_unavailable() -> None:
    """An owner who has never traded has not suffered an outage."""
    snapshot = refresh(refreshed_at=AT, **_runners())
    assert snapshot.performance.status is DashboardSectionStatus.EMPTY
    assert snapshot.performance.unavailable_reason is None


def test_an_absent_store_makes_the_portfolio_section_empty_not_available() -> None:
    """**The three portfolio statuses are three different facts.** A store that
    is not there yet is `EMPTY`; a store that was read is `AVAILABLE`; a store
    that could not be read is `UNAVAILABLE`. The System page prints the status
    per section, so collapsing the first into the second would report *"the
    portfolio was read"* about a machine that has never had a store.
    """
    absent = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        workspace=W.workspace_of(
            W.result(W.assessment("BTCUSDT")), store=W.reading(present=False)
        ),
    )
    assert absent.portfolio.status is DashboardSectionStatus.EMPTY
    assert absent.portfolio.unavailable_reason is None

    present = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        workspace=W.workspace_of(
            W.result(W.assessment("BTCUSDT")), store=W.reading(present=True)
        ),
    )
    assert present.portfolio.status is DashboardSectionStatus.AVAILABLE

    failed = build_snapshot(
        refreshed_at=AT, reference_time=AT, workspace_error=Boom("the store is gone")
    )
    assert failed.portfolio.status is DashboardSectionStatus.UNAVAILABLE


def test_the_system_page_prints_each_sections_status() -> None:
    """So the three are distinguishable without reading code."""
    from fmis.operator_dashboard import render_page

    html = render_page(
        build_snapshot(
            refreshed_at=AT,
            reference_time=AT,
            workspace=W.workspace_of(
                W.result(W.assessment("BTCUSDT")), store=W.reading(present=False)
            ),
        ),
        "/system",
    )
    assert "Sections read this refresh" in html
    assert "empty" in html


def test_each_section_carries_its_own_data_instant_not_the_refresh_instant() -> None:
    """A daily macro series and an hourly crypto series read in one refresh
    describe two different moments."""
    old = AT - timedelta(days=3)
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        # The reading's bar must not post-date the pulse it belongs to — the
        # engine refuses a reading from the future as a clock problem.
        pulse=pulse_of(
            [reading_for(benchmark("BTC"), bar_open=old - timedelta(hours=1))],
            as_of=old,
        ),
        macro=macro_of([reading_for(benchmark("SPX"))], as_of=AT),
    )
    assert snapshot.pulse.as_of == old
    assert snapshot.macro.as_of == AT
    assert snapshot.refreshed_at == AT


def test_the_health_section_survives_every_other_section_failing() -> None:
    """Data health is the section that must never go dark: it is the one that
    says *why* the others did."""
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        workspace_error=Boom("no store"),
        pulse_error=Boom("no venue"),
        macro_error=Boom("no FRED"),
        statistics_error=Boom("no corpus"),
    )
    states = {source.source_id for source in snapshot.health.data.sources}
    assert {"pulse", "macro", "store"} <= states


def test_an_unsupported_market_reaches_data_health() -> None:
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        pulse=pulse_of([reading_for(benchmark("BTC"))], unsupported=[dark("DXY")]),
    )
    states = {
        source.source_id: source.state for source in snapshot.health.data.sources
    }
    assert states["pulse:DXY"] is SourceState.UNSUPPORTED


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_two_composes_over_identical_inputs_are_equal() -> None:
    """No clock is read below the caller, so nothing else can vary."""
    workspace = W.workspace_of(W.result(W.assessment("BTCUSDT")))
    pulse = pulse_of([reading_for(benchmark("BTC"))])
    kwargs = dict(
        refreshed_at=AT, reference_time=AT, workspace=workspace, pulse=pulse
    )
    assert build_snapshot(**kwargs) == build_snapshot(**kwargs)


def test_the_snapshot_holds_no_method_that_writes() -> None:
    """Every field is a frozen dataclass or a tuple of them. There is nothing
    here to call that could reach a store."""
    snapshot = build_snapshot(refreshed_at=AT, reference_time=AT)
    forbidden = {
        "save", "write", "publish", "commit", "record", "append", "delete",
        "update", "activate", "close", "amend", "cancel", "submit", "place",
    }
    for name in dir(snapshot):
        assert name.lower() not in forbidden, name
    with pytest.raises((AttributeError, TypeError)):
        snapshot.refreshed_at = AT  # type: ignore[misc]


# ------------------------------------------------- artifact sections wiring ---
#
# `refresh()` grew `geometry` and `validation` parameters and forwarded neither,
# so `fmits dashboard --geometry-artifact ... --validation-artifact ...` decoded
# both artifacts, handed them to the refresher, and both pages still reported
# that nothing was loaded. A parameter accepted and dropped is worse than one
# that does not exist, because the caller has no way to tell.


def test_refresh_forwards_every_artifact_section_it_accepts() -> None:
    """Static: every artifact parameter must reach `build_snapshot`.

    Asserted over the parameter list rather than by naming two fields, so a
    third artifact section added later cannot be dropped the same way.
    """
    import inspect

    from fmis.operator_dashboard.compose import refresh

    source = inspect.getsource(refresh)
    call = source[source.index("return build_snapshot("):]
    for name in ("lab", "geometry", "validation"):
        assert name in inspect.signature(refresh).parameters, name
        assert f"{name}={name}" in call, f"refresh() drops {name} on the floor"


def test_a_forwarded_validation_artifact_reaches_the_snapshot() -> None:
    """Functional: the section is present, not merely the keyword."""
    from fmis.operator_dashboard.models import ValidationView

    view = ValidationView(experiment_id="probe", policies=())
    snapshot = refresh(refreshed_at=AT, validation=view, **_runners())
    assert snapshot.validation is not None
    assert snapshot.validation.data is view


def test_a_forwarded_geometry_artifact_reaches_the_snapshot() -> None:
    """The same defect existed for `--geometry-artifact` and is fixed with it."""
    from fmis.operator_dashboard.models import GeometryView

    view = GeometryView(experiment_id="probe", policies=())
    snapshot = refresh(refreshed_at=AT, geometry=view, **_runners())
    assert snapshot.geometry is not None
    assert snapshot.geometry.data is view
