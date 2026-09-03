"""The whole study, run against the committed capture. **No network, ever.**

This is the integration test behind report 0039. It reproduces the milestone's
headline numbers offline from `reports/artifacts/0039_cc_series_capture.json.gz`
with a discovery response replayed from the artifact and a candle transport that
raises on every call — so a figure quoted in the report that this test does not
reproduce is a figure that changed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fmis.providers.binance import HttpResponse
from fmis.universe.artifact import read_universe_artifact
from fmis.universe.capture import SeriesCache, network_is_fatal
from fmis.universe.models import ExclusionReason, FeasibilityVerdict, SurvivorshipClass
from fmis.universe.render import render_funnel, render_growth, render_universe_study
from fmis.universe.study import run_universe_study

_ARTIFACTS = Path(__file__).resolve().parents[1] / "reports" / "artifacts"
_CAPTURE = _ARTIFACTS / "0039_cc_series_capture.json.gz"
_STUDY = _ARTIFACTS / "0039_cc_universe_feasibility.json.gz"

pytestmark = pytest.mark.skipif(
    not (_CAPTURE.exists() and _STUDY.exists()),
    reason="the Milestone CC artifacts are not present",
)


@pytest.fixture(scope="module")
def persisted() -> dict:
    return read_universe_artifact(_STUDY).study


@pytest.fixture(scope="module")
def discovery_transport(persisted):
    """Replay the discovery response from the persisted assessments.

    Discovery is a provider call, so an offline run needs the listing it saw. Every
    instrument the study assessed is rebuilt from the artifact's own record of it,
    which makes this a replay rather than a fixture somebody wrote.
    """
    symbols = []
    for item in persisted["assessments"]:
        for pair in item["asset"]["pairs"]:
            symbols.append(
                {
                    "symbol": pair["symbol"],
                    "baseAsset": pair["base_asset"],
                    "quoteAsset": pair["quote_asset"],
                    "status": "TRADING" if pair["status"] == "trading" else "BREAK",
                    "isSpotTradingAllowed": True,
                }
            )
    # Everything the funnel removed before the identity stage, so the discovered
    # count and the survivorship tally reconcile against the persisted study.
    seen = {item["symbol"] for item in symbols}
    for exclusion in persisted["exclusions"]:
        if exclusion["symbol"] in seen:
            continue
        seen.add(exclusion["symbol"])
        symbols.append(
            {
                "symbol": exclusion["symbol"],
                "baseAsset": exclusion["symbol"].replace("USDT", "") or "X",
                "quoteAsset": "BTC" if exclusion["reason"] == (
                    ExclusionReason.QUOTE_CURRENCY_NOT_ELIGIBLE.value
                ) else "USDT",
                "status": "TRADING",
                "isSpotTradingAllowed": True,
            }
        )
    body = json.dumps({"serverTime": 1, "symbols": symbols}).encode()

    def send(url: str) -> HttpResponse:
        if "exchangeInfo" not in url:
            raise AssertionError(f"an offline run reached {url}")
        return HttpResponse(status=200, body=body)

    return send


@pytest.fixture(scope="module")
def study(discovery_transport):
    cache = SeriesCache.read(_CAPTURE)
    return run_universe_study(
        cache=cache,
        transport=discovery_transport,
        allow_fetch=False,
        discovered_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )


class TestTheHeadlineNumbersReproduce:
    def test_the_seal_is_the_pinned_one(self, study) -> None:
        from fmis.universe.preregistration import CC_PREREGISTRATION_DIGEST

        assert study.preregistration_digest == CC_PREREGISTRATION_DIGEST

    def test_the_eligible_universe_is_thirty_eight_economic_assets(self, study) -> None:
        assert study.eligible_assets == 38

    def test_the_derived_warmup_is_seventeen_fifty_days(self, study) -> None:
        assert study.warmup_days == 1750

    def test_the_funnel_reconciles(self, study) -> None:
        assert study.funnel.reconciles
        assert study.funnel.discovered - study.funnel.removed == study.eligible_assets

    def test_every_exclusion_carries_a_reason_and_a_detail(self, study) -> None:
        assert study.exclusions
        for item in study.exclusions:
            assert item.reason in ExclusionReason
            assert item.detail.strip()

    def test_the_dominant_exclusion_is_history_not_quality(self, study) -> None:
        """The finding: what removes instruments is the weekly warm-up."""
        counts: dict[str, int] = {}
        for item in study.exclusions:
            counts[item.reason.value] = counts.get(item.reason.value, 0) + 1
        assert counts[ExclusionReason.INSUFFICIENT_HISTORY_FOR_WARMUP.value] > 400
        assert counts.get(ExclusionReason.EXCESSIVE_MISSING_BARS.value, 0) == 0
        # Nothing was removed for data quality or liquidity: the constraint that
        # empties this universe is FMITS's own warm-up, not the provider's data.
        assert study.funnel.by_stage["data_quality"] == 0
        assert study.funnel.by_stage["liquidity"] == 0

    def test_the_market_factor_dominates_raw_co_movement(self, study) -> None:
        assert study.dependence.raw_mean_correlation == pytest.approx(0.604, abs=0.02)
        assert study.dependence.market_factor_share == pytest.approx(0.625, abs=0.02)

    def test_the_residual_correlation_is_indistinguishable_from_zero(self, study) -> None:
        """Measured against the demeaning artefact, never against zero."""
        excess = study.dependence.residual_excess_over_artefact
        assert excess is not None
        assert abs(excess) < 0.02
        assert study.dependence.correlation_for("residual") == 0.0

    def test_the_density_is_CA_s_pooled_rate(self, study) -> None:
        assert study.density.pooled_per_asset_year == pytest.approx(5.1616, abs=1e-3)

    def test_CB_s_requirement_is_reproduced(self, study) -> None:
        assert study.cb_required_observations == 4823
        assert study.cb_required_clusters == 467

    def test_the_universe_is_partially_survivorship_aware(self, study) -> None:
        assert (
            study.survivorship.classification
            is SurvivorshipClass.PARTIALLY_SURVIVORSHIP_AWARE
        )
        assert study.survivorship.halted_instruments > 0
        assert not study.survivorship.classification.is_unbiased

    def test_the_verdict_is_INFEASIBLE_on_cluster_count(self, study) -> None:
        assert study.assessment.verdict is FeasibilityVerdict.INFEASIBLE
        assert study.assessment.binding_constraint == "cluster_count"
        assert study.assessment.required_assets_independent == 468

    def test_the_verdict_approves_nothing(self, study) -> None:
        assert study.assessment.is_approved_for_trading is False
        assert study.assessment.earns_forward_test is False

    def test_the_post_hoc_ceiling_does_not_reach_the_requirement(self, study) -> None:
        """Even every year the provider has ever produced falls short."""
        ceiling = study.horizon
        assert ceiling is not None
        assert ceiling.qualifying_assets == 106
        assert ceiling.projected_admissions < ceiling.required_admissions
        assert ceiling.reaches_requirement is False
        assert ceiling.is_post_hoc is True

    def test_the_measured_universe_could_test_a_much_larger_effect(self, study) -> None:
        """What the feasible universe CAN honestly ask, kept separate from CA's."""
        by_effect = {
            (item.effect, item.dependence_scenario): item
            for item in study.effect_requirements
        }
        assert by_effect[("0.50", "independent")].required_assets < study.eligible_assets
        assert by_effect[("0.10", "independent")].required_assets > study.eligible_assets


class TestTheRunIsOfflineAndDeterministic:
    def test_no_candle_was_refetched(self, discovery_transport) -> None:
        """The candle transport raises; only discovery is served."""
        cache = SeriesCache.read(_CAPTURE)

        def candles_are_fatal(url: str) -> HttpResponse:
            if "exchangeInfo" in url:
                return discovery_transport(url)
            return network_is_fatal()(url)

        result = run_universe_study(
            cache=cache, transport=candles_are_fatal, allow_fetch=False,
            discovered_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
        )
        assert result.eligible_assets == 38

    def test_two_runs_produce_identical_payloads(self, discovery_transport) -> None:
        payloads = []
        for _ in range(2):
            cache = SeriesCache.read(_CAPTURE)
            payloads.append(
                json.dumps(
                    run_universe_study(
                        cache=cache, transport=discovery_transport,
                        allow_fetch=False,
                        discovered_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
                    ).payload(),
                    sort_keys=True,
                )
            )
        assert payloads[0] == payloads[1]

    def test_it_agrees_with_the_persisted_artifact(self, study, persisted) -> None:
        for field in (
            "eligible_assets", "discovered_instruments", "economic_assets",
            "warmup_days", "cb_required_observations", "cb_required_clusters",
        ):
            assert study.payload()[field] == persisted[field], field
        assert study.assessment.verdict.value == persisted["assessment"]["verdict"]


class TestTheRenderer:
    def test_it_renders_without_deciding_anything(self, study) -> None:
        text = render_universe_study(study)
        assert "INFEASIBLE" in text
        assert "NO VERDICT IN THIS STUDY IS PERMISSION TO TRADE" in text

    def test_projected_rows_are_marked_differently_from_observed_ones(self, study) -> None:
        text = render_growth(study)
        assert " obs " in text
        assert " proj " in text

    def test_the_funnel_prints_every_reason_it_used(self, study) -> None:
        text = render_funnel(study)
        for item in study.exclusions:
            assert item.reason.value in text

    def test_it_prints_the_post_review_limitations_beside_the_sealed_ones(self, study) -> None:
        """A CLI reader must not see the sealed set without also seeing CC-7..CC-9."""
        text = render_universe_study(study)
        assert "SEALED WITH THE PRE-REGISTRATION" in text
        assert "ESTABLISHED BY REVIEW, AFTER SEALING" in text
        for code in ("CC-7", "CC-8", "CC-9"):
            assert code in text, code

    def test_the_concentration_number_carries_its_caveat(self, study) -> None:
        """Review finding B-7: the figure is per-sample, not per-asset."""
        text = render_universe_study(study)
        head, _, tail = text.partition("largest single share of admissions")
        assert tail, "the concentration figure is not printed at all"
        assert "NOT MEASURED" in tail[:400]
        assert "CC-2" in tail[:400]

    def test_an_unmeasured_value_prints_as_a_dash_not_a_zero(self, study) -> None:
        text = render_universe_study(study)
        assert "0.0000" not in text.split("EFFECT-SIZE GRID")[1].split("\n")[3]
