"""The read models' own invariants — the contract everything else relies on.

The rules asserted here are the ones that keep a page honest: a failed section
must say why, a failed section must not also carry data, timestamps must be
timezone-aware, and absence must be distinguishable from zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fmis.operator_dashboard import (
    DASHBOARD_SCHEMA_VERSION,
    DashboardError,
    DataHealthView,
    OperatorDashboardSnapshot,
    OverviewCounts,
    DashboardSection,
    DashboardSectionStatus,
    SetupRow,
    SourceHealth,
    SourceState,
    SwingView,
)

AT = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def _ok(name: str = "swing") -> DashboardSection:
    return DashboardSection(name=name, status=DashboardSectionStatus.EMPTY, as_of=AT, source="fixture")


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------


def test_an_unavailable_section_must_state_a_reason() -> None:
    """An unexplained failure renders as an empty section, and an empty section
    reads as a calm one. The type refuses to be constructed that way."""
    with pytest.raises(DashboardError, match="must say why"):
        DashboardSection(name="macro", status=DashboardSectionStatus.UNAVAILABLE)


def test_an_unavailable_section_cannot_also_carry_data() -> None:
    """Half-failed is not a state. Whichever the UI checked first would win."""
    with pytest.raises(DashboardError, match="carries data"):
        DashboardSection(
            name="macro",
            status=DashboardSectionStatus.UNAVAILABLE,
            unavailable_reason="FRED did not answer",
            data=SwingView(reference_time=AT),
        )


def test_a_healthy_section_cannot_carry_an_unavailable_reason() -> None:
    with pytest.raises(DashboardError, match="not unavailable"):
        DashboardSection(
            name="macro",
            status=DashboardSectionStatus.AVAILABLE,
            unavailable_reason="but it worked",
        )


def test_a_section_must_be_named() -> None:
    with pytest.raises(DashboardError, match="must be named"):
        DashboardSection(name="   ", status=DashboardSectionStatus.EMPTY)


def test_a_naive_section_timestamp_is_refused() -> None:
    """A naive instant compared against a UTC one is a silently wrong age, and
    every age on this page is stated to the owner as a fact."""
    with pytest.raises(DashboardError, match="timezone-aware"):
        DashboardSection(
            name="pulse",
            status=DashboardSectionStatus.AVAILABLE,
            as_of=datetime(2026, 8, 24, 12, 0),
        )


def test_empty_and_unavailable_are_different_states() -> None:
    """The distinction the whole surface depends on: nothing recorded is not an
    outage, and an outage is not an empty store."""
    empty = DashboardSection(name="paper", status=DashboardSectionStatus.EMPTY)
    failed = DashboardSection(
        name="paper", status=DashboardSectionStatus.UNAVAILABLE, unavailable_reason="disk gone"
    )
    assert empty.failed is False
    assert failed.failed is True
    assert empty.is_available is False and failed.is_available is False


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def _snapshot(**overrides) -> OperatorDashboardSnapshot:
    values = dict(
        refreshed_at=AT,
        reference_time=AT,
        counts=OverviewCounts(),
        pulse=_ok("pulse"),
        macro=_ok("macro"),
        swing=_ok("swing"),
        portfolio=_ok("portfolio"),
        paper=_ok("paper"),
        performance=_ok("performance"),
        health=_ok("health"),
    )
    values.update(overrides)
    return OperatorDashboardSnapshot(**values)


@pytest.mark.parametrize("field", ["refreshed_at", "reference_time"])
def test_a_naive_snapshot_instant_is_refused(field: str) -> None:
    with pytest.raises(DashboardError, match="timezone-aware"):
        _snapshot(**{field: datetime(2026, 8, 24, 12, 0)})


def test_the_snapshot_lists_every_section_in_navigation_order() -> None:
    snapshot = _snapshot()
    assert [section.name for section in snapshot.sections] == [
        "pulse",
        "macro",
        "swing",
        "portfolio",
        "paper",
        "performance",
        "health",
    ]


def test_failed_sections_lists_only_the_failures() -> None:
    snapshot = _snapshot(
        macro=DashboardSection(
            name="macro",
            status=DashboardSectionStatus.UNAVAILABLE,
            unavailable_reason="FRED did not answer",
        )
    )
    assert [section.name for section in snapshot.failed_sections] == ["macro"]


def test_two_snapshots_over_identical_inputs_are_equal() -> None:
    """Determinism. The only clock reading is injected, so nothing else can
    vary between two composes of the same inputs."""
    assert _snapshot() == _snapshot()


def test_the_schema_version_travels_on_the_snapshot() -> None:
    assert _snapshot().schema_version == DASHBOARD_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Absence versus zero
# ---------------------------------------------------------------------------


def test_zero_and_absent_are_distinguishable_on_a_setup_row() -> None:
    """A risk/reward of zero is a measurement. A risk/reward of `None` is not.
    A model that could not tell them apart would let the page print one as the
    other, which is the single most dangerous thing this surface could do."""
    measured = SetupRow(symbol="X", state="CONFIRMED", sufficiency="ok", position=0, risk_reward=0.0)
    absent = SetupRow(symbol="X", state="CONFIRMED", sufficiency="ok", position=0)
    assert measured.risk_reward == 0.0
    assert absent.risk_reward is None
    assert measured != absent


def test_a_data_health_view_filters_by_state_without_scoring() -> None:
    """Counts per state, and deliberately no aggregate: one number over sources
    with different publication schedules would be an invented judgement."""
    view = DataHealthView(
        sources=(
            SourceHealth(source_id="a", label="A", state=SourceState.AVAILABLE),
            SourceHealth(source_id="b", label="B", state=SourceState.UNSUPPORTED),
            SourceHealth(source_id="c", label="C", state=SourceState.AVAILABLE),
        )
    )
    assert len(view.with_state(SourceState.AVAILABLE)) == 2
    assert len(view.with_state(SourceState.UNSUPPORTED)) == 1
    assert len(view.with_state(SourceState.UNAVAILABLE)) == 0
    assert not hasattr(view, "score")
    assert not hasattr(view, "health")


def test_the_source_states_are_exactly_the_engines_vocabulary() -> None:
    """No `STALE`. `fmis.market_pulse` refuses the word because staleness is a
    judgement about usability; `BEHIND_SCHEDULE` is what can be stated."""
    names = {state.value for state in SourceState}
    assert "stale" not in names
    assert "behind_schedule" in names
    assert names == {
        "available",
        "behind_schedule",
        "schedule_unknown",
        "unsupported",
        "unavailable",
        "absent",
    }


def test_a_swing_view_finds_a_row_by_symbol_across_both_groups() -> None:
    view = SwingView(
        reference_time=AT,
        opportunities=(SetupRow(symbol="BTCUSDT", state="CONFIRMED", sufficiency="ok", position=0),),
        wait_list=(SetupRow(symbol="ETHUSDT", state="WAIT", sufficiency="ok", position=1),),
    )
    assert view.row_for("BTCUSDT").state == "CONFIRMED"
    assert view.row_for("ETHUSDT").state == "WAIT"
    assert view.row_for("NOPEUSDT") is None
