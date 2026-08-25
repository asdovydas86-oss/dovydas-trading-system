"""Research artifacts: reproducible, verifiable, and never silently replaced."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.swing_lab.artifact import (
    LabArtifact,
    encode_study,
    read_artifact,
    verify_digest,
    write_study,
)
from fmis.swing_lab.gate import measure_gate_impact
from fmis.swing_lab.metrics import compute_lab_metrics
from fmis.swing_lab.models import (
    LAB_SCHEMA_VERSION,
    LabExitReason,
    LabTrade,
    SwingLabError,
)
from fmis.swing_lab.replay import VariantReplay
from fmis.swing_lab.study import (
    LAB_LIMITATIONS,
    LabManifest,
    LabStudy,
    VariantResult,
    result_digest,
)
from fmis.swing_lab.trades import FRICTIONLESS_COSTS
from fmis.swing_lab.variants import BASELINE_VARIANT, CONTEXT_ONLY_VARIANT
from fmis.swing_setup.models import Direction
from fmis.swing_setup.research_models import ResearchWindow

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def trade(variant_id: str, index: int, net_r: str | None = "1.5") -> LabTrade:
    value = None if net_r is None else Decimal(net_r)
    return LabTrade(
        variant_id=variant_id,
        symbol="BTCUSDT",
        setup_id=f"setup-{index}",
        direction=Direction.LONG,
        signal_at=T0 + timedelta(days=index),
        entry_at=T0 + timedelta(days=index, hours=4),
        entry_price=Decimal("100.5"),
        initial_stop=Decimal("90.25"),
        target=Decimal("120.75"),
        planned_reference_price=Decimal("100"),
        exit_at=T0 + timedelta(days=index, hours=8),
        exit_price=Decimal("115.125"),
        exit_reason=LabExitReason.TARGET if value is not None else LabExitReason.AMBIGUOUS_SAME_BAR,
        bars_held=3,
        gross_r=value,
        net_r=value,
        mfe_r=None if value is None else Decimal("1.75"),
        mae_r=None if value is None else Decimal("-0.25"),
        cost_policy_id=FRICTIONLESS_COSTS.policy_id,
        planned_risk_reward=2.0,
        segment="q1",
        context_regime_structure="trending",
        context_structural_trend="sustained_higher",
        setup_structural_trend="sustained_higher",
    )


def build_study() -> LabStudy:
    results = []
    for variant in (BASELINE_VARIANT, CONTEXT_ONLY_VARIANT):
        trades = tuple(
            trade(variant.variant_id, index) for index in range(3)
        ) + (trade(variant.variant_id, 99, None),)
        results.append(
            VariantResult(
                variant=variant,
                replay=VariantReplay(
                    variant=variant, observations=(), trades=trades, metadata={}
                ),
                metrics=compute_lab_metrics(trades, label=variant.variant_id),
            )
        )
    ordered = tuple(results)
    window = ResearchWindow(
        warmup_start=T0 - timedelta(days=2000),
        measurement_start=T0,
        measurement_end=T0 + timedelta(days=365),
        outcome_tail_end=T0 + timedelta(days=375),
    )
    manifest = LabManifest(
        experiment_id="test-1",
        schema_version=LAB_SCHEMA_VERSION,
        generated_at=T0,
        symbols=("BTCUSDT",),
        variant_ids=tuple(r.variant.variant_id for r in ordered),
        measurement_start=window.measurement_start,
        measurement_end=window.measurement_end,
        warmup_start=window.warmup_start,
        outcome_tail_end=window.outcome_tail_end,
        interval_groups=(("1w", "1d", "4h"),),
        candle_limit=250,
        evaluation_window_bars=180,
        identity_priming_bars=60,
        cost_policy=FRICTIONLESS_COSTS.to_payload(),
        setup_policy_id="swing-setup-v1",
        confirmation_lookback_bars=10,
        minimum_agreeing_families=2,
        data_boundaries=(),
        trade_basis="test basis",
        limitations=LAB_LIMITATIONS,
        result_digest=result_digest(ordered),
    )
    return LabStudy(
        manifest=manifest,
        window=window,
        segments=(),
        results=ordered,
        gate=measure_gate_impact((), ordered),
        costs=FRICTIONLESS_COSTS,
    )


@pytest.fixture
def study() -> LabStudy:
    return build_study()


class TestDigest:
    def test_the_same_study_digests_identically(self, study: LabStudy) -> None:
        assert result_digest(study.results) == result_digest(build_study().results)

    def test_symbol_order_does_not_change_the_digest(self, study: LabStudy) -> None:
        reversed_results = tuple(reversed(study.results))
        assert result_digest(reversed_results) == result_digest(study.results)

    def test_trade_order_within_a_variant_does_not_change_the_digest(
        self, study: LabStudy
    ) -> None:
        """The digest must be invariant to how trades were *accumulated*.

        Reversing the results list only permutes trades ACROSS variants, which
        the sort key's first component already separates. This permutes them
        WITHIN one variant, which is what actually exercises the rest of the
        key — and is the case a surviving mutation probe found untested during
        the BW release gate.
        """
        permuted = tuple(
            VariantResult(
                variant=result.variant,
                replay=VariantReplay(
                    variant=result.variant,
                    observations=(),
                    trades=tuple(reversed(result.trades)),
                    metadata={},
                ),
                metrics=result.metrics,
            )
            for result in study.results
        )
        assert result_digest(permuted) == result_digest(study.results)

    def test_the_digest_separates_two_different_studies(self, study: LabStudy) -> None:
        """Two studies over different trades must never share a digest."""
        other = VariantResult(
            variant=study.results[0].variant,
            replay=VariantReplay(
                variant=study.results[0].variant,
                observations=(),
                trades=(trade(study.results[0].variant.variant_id, 0, "7.5"),),
                metadata={},
            ),
            metrics=study.results[0].metrics,
        )
        assert result_digest((other,)) != result_digest(study.results)

    def test_a_changed_return_changes_the_digest(self, study: LabStudy) -> None:
        first = study.results[0]
        mutated = VariantResult(
            variant=first.variant,
            replay=VariantReplay(
                variant=first.variant,
                observations=(),
                trades=(trade(first.variant.variant_id, 0, "9.99"),),
                metadata={},
            ),
            metrics=first.metrics,
        )
        assert result_digest((mutated,)) != result_digest((first,))

    def test_a_changed_cost_policy_changes_the_digest(self, study: LabStudy) -> None:
        from fmis.swing_lab.trades import CONSERVATIVE_COSTS, reprice

        first = study.results[0]
        recosted = tuple(reprice(item, CONSERVATIVE_COSTS) for item in first.trades)
        mutated = VariantResult(
            variant=first.variant,
            replay=VariantReplay(
                variant=first.variant, observations=(), trades=recosted, metadata={}
            ),
            metrics=first.metrics,
        )
        assert result_digest((mutated,)) != result_digest((first,))


class TestRoundTrip:
    def test_a_written_artifact_reads_back_and_verifies(
        self, study: LabStudy, tmp_path
    ) -> None:
        path = write_study(study, tmp_path / "study.lab.json")
        artifact = read_artifact(path)
        assert artifact.experiment_id == "test-1"
        assert verify_digest(artifact)

    def test_every_trade_survives_the_round_trip_exactly(
        self, study: LabStudy, tmp_path
    ) -> None:
        artifact = read_artifact(write_study(study, tmp_path / "s.lab.json"))
        for result in study.results:
            restored = artifact.trades_by_variant[result.variant.variant_id]
            assert len(restored) == len(result.trades)
            for before, after in zip(result.trades, restored, strict=True):
                assert after.net_r == before.net_r
                assert after.entry_price == before.entry_price
                assert after.exit_reason is before.exit_reason
                assert after.mfe_r == before.mfe_r

    def test_decimals_survive_as_decimals_not_floats(
        self, study: LabStudy, tmp_path
    ) -> None:
        path = write_study(study, tmp_path / "s.lab.json")
        raw = json.loads(path.read_text(encoding="utf-8"))
        entry = raw["variants"][0]["trades"][0]["entry_price"]
        assert isinstance(entry, str)
        assert Decimal(entry) == Decimal("100.5")

    def test_metrics_recomputed_from_an_artifact_match_the_study(
        self, study: LabStudy, tmp_path
    ) -> None:
        artifact = read_artifact(write_study(study, tmp_path / "s.lab.json"))
        for result in study.results:
            restored = artifact.metrics(result.variant.variant_id)
            assert restored.total_r == result.metrics.total_r
            assert restored.measurable_trades == result.metrics.measurable_trades
            assert restored.ambiguous_trades == result.metrics.ambiguous_trades


class TestRefusals:
    def test_an_artifact_never_overwrites_another(
        self, study: LabStudy, tmp_path
    ) -> None:
        path = tmp_path / "s.lab.json"
        write_study(study, path)
        with pytest.raises(SwingLabError, match="never overwritten"):
            write_study(study, path)

    def test_an_edited_artifact_fails_verification(
        self, study: LabStudy, tmp_path
    ) -> None:
        path = write_study(study, tmp_path / "s.lab.json")
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["variants"][0]["trades"][0]["net_r"] = "99"
        path.write_text(json.dumps(raw), encoding="utf-8")
        assert not verify_digest(read_artifact(path))

    def test_a_foreign_schema_version_is_refused(
        self, study: LabStudy, tmp_path
    ) -> None:
        payload = encode_study(study)
        payload["schema_version"] = LAB_SCHEMA_VERSION + 1
        with pytest.raises(SwingLabError, match="schema version"):
            LabArtifact(payload)

    def test_unreadable_json_is_refused_with_the_path(self, tmp_path) -> None:
        path = tmp_path / "broken.lab.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(SwingLabError, match="not valid JSON"):
            read_artifact(path)

    def test_a_missing_file_is_refused(self, tmp_path) -> None:
        with pytest.raises(SwingLabError, match="cannot read"):
            read_artifact(tmp_path / "absent.lab.json")

    def test_an_unknown_variant_is_refused(self, study: LabStudy, tmp_path) -> None:
        artifact = read_artifact(write_study(study, tmp_path / "s.lab.json"))
        with pytest.raises(SwingLabError, match="no variant"):
            artifact.variant("swing_nonexistent")


class TestTheArtifactCarriesItsCaveats:
    def test_the_limitations_travel_with_the_numbers(
        self, study: LabStudy, tmp_path
    ) -> None:
        artifact = read_artifact(write_study(study, tmp_path / "s.lab.json"))
        limitations = artifact.manifest["limitations"]
        assert any(item.startswith("BW-2") for item in limitations)
        assert any(item.startswith("BW-7") for item in limitations)

    def test_the_cost_basis_travels_with_the_numbers(
        self, study: LabStudy, tmp_path
    ) -> None:
        artifact = read_artifact(write_study(study, tmp_path / "s.lab.json"))
        assert artifact.manifest["cost_policy"]["policy_id"] == FRICTIONLESS_COSTS.policy_id

    def test_the_baseline_is_identifiable_in_the_artifact(
        self, study: LabStudy, tmp_path
    ) -> None:
        artifact = read_artifact(write_study(study, tmp_path / "s.lab.json"))
        baseline = artifact.variant("swing_current")
        assert baseline["is_production_baseline"] is True
        assert baseline["policy_id"] == "swing-setup-v1"

    def test_a_research_variant_is_never_marked_as_the_baseline(
        self, study: LabStudy, tmp_path
    ) -> None:
        artifact = read_artifact(write_study(study, tmp_path / "s.lab.json"))
        research = artifact.variant("swing_1w_context")
        assert research["is_production_baseline"] is False
        assert "research" in research["policy_id"]
