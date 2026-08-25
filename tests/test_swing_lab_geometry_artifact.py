"""The geometry artifact, and the whole surface path from study to rendered page.

Milestone BX. One synthetic study is written, read back, digest-verified, adapted
into the dashboard's read model and rendered — so a break anywhere along that
chain fails here rather than on the owner's screen.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.operator_dashboard.compose import DASHBOARD_LIMITATIONS
from fmis.operator_dashboard.models import GeometryView
from fmis.operator_dashboard.render import render_page
from fmis.operator_dashboard.sections import geometry_view
from fmis.paper.models import PriceBar
from fmis.swing_lab.geometry_artifact import (
    GeometryArtifact,
    encode_geometry_study,
    read_geometry_artifact,
    verify_geometry_digest,
    write_geometry_study,
)
from fmis.swing_lab.geometry_replay import GeometryCapture
from fmis.swing_lab.geometry_study import run_geometry_study
from fmis.swing_lab.geometry_variants import PRE_DECLARED_GEOMETRIES
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.trades import FRICTIONLESS_COSTS

from tests.swing_lab_helpers import candidate

_UTC = timezone.utc
_T0 = datetime(2026, 1, 1, tzinfo=_UTC)
_WINDOW = 20


def _bars(symbol: str, count: int = 60) -> tuple[PriceBar, ...]:
    return tuple(
        PriceBar(
            symbol=symbol, interval="4h",
            open_time=_T0 + timedelta(hours=4 * index),
            open=Decimal(f"{100 + index * 0.5:.4f}"),
            high=Decimal(f"{101 + index * 0.5:.4f}"),
            low=Decimal(f"{99.5 + index * 0.5:.4f}"),
            close=Decimal(f"{100.4 + index * 0.5:.4f}"),
        )
        for index in range(count)
    )


def _many(count: int, symbol: str):
    return [
        candidate(
            symbol=symbol, setup_id=f"{symbol}|long|from=seq{index}", signal_index=index
        )
        for index in range(count)
    ]


@pytest.fixture(scope="module")
def study():
    capture = GeometryCapture(
        admission_variant_id="swing_current",
        admission_policy_id="swing-setup-v1",
        candidates=tuple(_many(25, "BTCUSDT") + _many(25, "ETHUSDT")),
        bars_by_symbol={"BTCUSDT": _bars("BTCUSDT"), "ETHUSDT": _bars("ETHUSDT")},
        metadata={"measured_instants": 1000},
    )
    return run_geometry_study(
        capture,
        development_symbols=("BTCUSDT",),
        holdout_symbols=("ETHUSDT",),
        experiment_id="probe",
        run_at=_T0,
        measurement_start=_T0,
        measurement_end=_T0 + timedelta(days=30),
        warmup_start=_T0 - timedelta(days=1000),
        costs=FRICTIONLESS_COSTS,
        evaluation_window_bars=_WINDOW,
        candle_limit=250,
        policies=PRE_DECLARED_GEOMETRIES,
        with_sensitivity=True,
    )


@pytest.fixture(scope="module")
def artifact(study, tmp_path_factory):
    path = tmp_path_factory.mktemp("geometry") / "probe.geometry.json"
    write_geometry_study(study, path)
    return read_geometry_artifact(path)


class TestTheArtifactRoundTrips:
    def test_every_policy_survives_the_round_trip(self, study, artifact) -> None:
        assert artifact.policy_ids == tuple(
            result.policy.policy_id for result in study.results
        )

    def test_the_digest_verifies(self, artifact) -> None:
        assert verify_geometry_digest(artifact)

    def test_an_edited_trade_fails_the_digest(self, artifact) -> None:
        """The property that makes an artifact checkable rather than merely
        readable: a hand-edited figure cannot be quoted as evidence."""
        payload = json.loads(json.dumps(artifact.payload))
        for policy in payload["policies"]:
            if policy["development"]["trades"]:
                policy["development"]["trades"][0]["net_r"] = "99"
                break
        assert not verify_geometry_digest(GeometryArtifact(payload))

    def test_metrics_recompute_from_the_stored_trades(self, study, artifact) -> None:
        for result in study.results:
            for sample in ("development", "holdout"):
                stored = artifact.metrics(result.policy.policy_id, sample)
                live = getattr(result, sample).metrics
                assert stored.measurable_trades == live.measurable_trades
                assert stored.total_r == live.total_r

    def test_every_criterion_is_stored_not_only_its_conclusion(self, artifact) -> None:
        """A reader must be able to check a verdict against the measurements
        that produced it rather than take a report's word for it."""
        for policy_id in artifact.policy_ids:
            criteria = artifact.policy(policy_id)["criteria"]
            assert len(criteria) == 9
            for item in criteria:
                assert item["requirement"] and item["observed"]

    def test_the_limitations_travel_inside_the_artifact(self, artifact) -> None:
        limitations = artifact.manifest["limitations"]
        assert any(item.startswith("BX-2") for item in limitations)
        assert any(item.startswith("BX-3") for item in limitations)
        assert any(item.startswith("BW-4") for item in limitations)

    def test_an_artifact_never_approves_trading(self, artifact) -> None:
        assert artifact.is_approved_for_trading is False


class TestTheArtifactRefusesTheWrongThing:
    def test_writing_over_an_existing_artifact_is_refused(self, study, tmp_path) -> None:
        path = tmp_path / "probe.geometry.json"
        write_geometry_study(study, path)
        with pytest.raises(SwingLabError, match="never overwritten"):
            write_geometry_study(study, path)

    def test_a_different_schema_version_is_refused_never_upgraded(self, artifact) -> None:
        payload = dict(artifact.payload)
        payload["schema_version"] = 999
        with pytest.raises(SwingLabError, match="schema version"):
            GeometryArtifact(payload)

    def test_a_missing_file_is_refused_by_name(self, tmp_path) -> None:
        with pytest.raises(SwingLabError, match="cannot read"):
            read_geometry_artifact(tmp_path / "absent.json")

    def test_a_file_that_is_not_json_is_refused(self, tmp_path) -> None:
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(SwingLabError, match="not valid JSON"):
            read_geometry_artifact(path)

    def test_a_json_scalar_is_refused(self, tmp_path) -> None:
        path = tmp_path / "scalar.json"
        path.write_text("42", encoding="utf-8")
        with pytest.raises(SwingLabError, match="does not hold"):
            read_geometry_artifact(path)

    def test_an_unknown_policy_is_refused_by_name(self, artifact) -> None:
        with pytest.raises(SwingLabError, match="holds no geometry"):
            artifact.policy("nope")

    def test_an_unknown_sample_is_refused_by_name(self, artifact) -> None:
        with pytest.raises(SwingLabError, match="development' or 'holdout"):
            artifact.trades(artifact.policy_ids[0], "training")

    def test_encoding_a_non_study_is_refused(self) -> None:
        with pytest.raises(TypeError, match="must be a GeometryStudy"):
            encode_geometry_study(object())


class TestTheDashboardSurface:
    def test_the_view_carries_both_samples_for_every_policy(self, artifact) -> None:
        view = geometry_view(artifact, digest_verified=True)
        assert len(view.policies) == len(PRE_DECLARED_GEOMETRIES)
        for policy in view.policies:
            assert policy.development.sample == "development"
            assert policy.holdout.sample == "holdout"

    def test_the_view_keeps_refusals_beside_trade_counts(self, artifact) -> None:
        """A rule trading six times because it refused ninety candidates is a
        different finding from one trading six times because six setups formed."""
        view = geometry_view(artifact, digest_verified=True)
        assert any(policy.development.refused for policy in view.policies)

    def test_the_view_states_no_rate_the_engine_refused(self, artifact) -> None:
        view = geometry_view(artifact, digest_verified=True)
        for share in view.baseline_shares:
            if share.denominator < 20:
                assert share.fraction is None

    def test_the_view_orders_policies_as_they_were_pre_declared(self, artifact) -> None:
        """Not by result. A table sorted by expectancy has chosen a winner."""
        view = geometry_view(artifact, digest_verified=True)
        assert [item.policy_id for item in view.policies] == [
            policy.policy_id for policy in PRE_DECLARED_GEOMETRIES
        ]

    def test_the_view_never_approves_trading(self, artifact) -> None:
        assert geometry_view(artifact, digest_verified=True).is_approved_for_trading is False

    def test_the_page_renders_with_an_experiment_loaded(self, artifact) -> None:
        view = geometry_view(artifact, digest_verified=True)
        html = render_page(_snapshot(view), "/geometry")
        assert "Trade Geometry" in html
        assert "Does any geometry deserve forward testing?" in html
        assert "geom_production" in html
        assert "This page promotes nothing" in html

    def test_the_page_says_so_plainly_with_nothing_loaded(self) -> None:
        """An empty table on this page would read as 'no geometry works' rather
        than 'nothing was measured'."""
        html = render_page(_snapshot(None), "/geometry")
        assert "No geometry experiment is loaded" in html

    def test_the_page_names_every_blocking_criterion(self, artifact) -> None:
        view = geometry_view(artifact, digest_verified=True)
        html = render_page(_snapshot(view), "/geometry")
        for policy in view.policies:
            for name in policy.blocking_criteria:
                assert name in html

    def test_the_page_escapes_a_hostile_experiment_id(self, artifact) -> None:
        payload = json.loads(json.dumps(artifact.payload))
        payload["manifest"]["experiment_id"] = "<script>alert(1)</script>"
        view = geometry_view(GeometryArtifact(payload), digest_verified=False)
        html = render_page(_snapshot(view), "/geometry")
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_the_page_reports_an_unverified_digest_as_unverified(self, artifact) -> None:
        view = geometry_view(artifact, digest_verified=False)
        assert "NOT VERIFIED" in render_page(_snapshot(view), "/geometry")

    def test_the_geometry_route_is_in_the_navigation(self, artifact) -> None:
        view = geometry_view(artifact, digest_verified=True)
        assert '/geometry' in render_page(_snapshot(view), "/")


def _snapshot(view: GeometryView | None):
    """A minimal snapshot carrying only what the geometry page reads."""
    from fmis.operator_dashboard.compose import _section
    from fmis.operator_dashboard.models import (
        DashboardSection,
        DashboardSectionStatus,
        OperatorDashboardSnapshot,
        OverviewCounts,
    )

    def absent(name: str) -> DashboardSection:
        return DashboardSection(
            name=name,
            status=DashboardSectionStatus.UNAVAILABLE,
            unavailable_reason="not built for this test",
        )

    section = (
        None
        if view is None
        else _section(
            "geometry", view, as_of=None,
            source=f"saved geometry artifact · {view.experiment_id}",
            empty=not view.policies,
        )
    )
    return OperatorDashboardSnapshot(
        refreshed_at=_T0,
        reference_time=_T0,
        counts=OverviewCounts(),
        pulse=absent("pulse"),
        macro=absent("macro"),
        swing=absent("swing"),
        portfolio=absent("portfolio"),
        paper=absent("paper"),
        performance=absent("performance"),
        health=absent("health"),
        geometry=section,
        warnings=(),
        limitations=DASHBOARD_LIMITATIONS,
    )
