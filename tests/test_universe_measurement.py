"""The measurement layer: discovery, identity, coverage, dependence, growth, artifact.

These are the unit tests behind the numbers Milestone CC reports. Where a figure in
report 0039 can be checked by arithmetic, it is checked here rather than quoted, so
a later change that moved it fails a test instead of quietly changing the report's
meaning.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.providers.binance import (
    BinanceRequestError,
    BinanceResponseError,
    HttpResponse,
    build_exchange_info_url,
    fetch_exchange_info,
    map_symbol_record,
)
from fmis.universe.artifact import (
    CC_ARTIFACT_KIND,
    artifact_digest,
    encode_universe_study,
    read_universe_artifact,
    verify_artifact_digest,
    write_universe_artifact,
)
from fmis.universe.capture import DailyBar, discover_pairs, series_digest
from fmis.universe.density import (
    AssetDensity,
    published_densities,
    subsample_for_density,
    summarise_density,
)
from fmis.universe.dependence import (
    aligned_returns,
    correlated_groups,
    effective_clusters,
    log_returns,
    market_residuals,
    measure_dependence,
    pearson,
)
from fmis.universe.eligibility import coverage_of, liquidity_of, quality_of
from fmis.universe.growth import (
    ca_observation_dispersion,
    requirement_for_effect,
    cb_required_information,
    effect_for,
    growth_curve,
    growth_row,
)
from fmis.universe.identity import (
    classify_asset,
    economic_asset_id,
    identity_rules_payload,
    peg_like_by_volatility,
)
from fmis.universe.models import AssetClass, UniverseError
from fmis.universe.preregistration import UNIVERSE_GROWTH_SIZES

UTC = timezone.utc
START = datetime(2023, 6, 1, tzinfo=UTC)
END = datetime(2025, 6, 1, tzinfo=UTC)


def _bars(days: int, *, price: float = 100.0, volume: float = 1000.0, step: int = 1):
    return tuple(
        DailyBar(
            open_time=START + timedelta(days=index * step),
            open=price, high=price * 1.01, low=price * 0.99, close=price,
            volume=volume,
        )
        for index in range(days)
    )


# ------------------------------------------------------------------ provider ---


class TestTheDiscoveryEndpoint:
    def test_the_url_is_read_only_and_deterministic(self) -> None:
        url = build_exchange_info_url()
        assert url == "https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT"
        assert "key" not in url and "signature" not in url

    @pytest.mark.parametrize("value", ["", "spot", "SPOT ", 5, None])
    def test_a_malformed_permission_fails_before_any_request(self, value) -> None:
        with pytest.raises(BinanceRequestError):
            build_exchange_info_url(permissions=value)

    def test_a_symbol_record_maps_the_five_fields_it_needs(self) -> None:
        record = map_symbol_record(
            {
                "symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
                "status": "TRADING", "isSpotTradingAllowed": True, "filters": [],
            }
        )
        assert record.symbol == "BTCUSDT"
        assert record.status == "TRADING"
        assert record.spot_trading_allowed is True

    @pytest.mark.parametrize(
        "payload",
        [
            {"baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING",
             "isSpotTradingAllowed": True},
            {"symbol": "BTCUSDT", "quoteAsset": "USDT", "status": "TRADING",
             "isSpotTradingAllowed": True},
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
             "isSpotTradingAllowed": True},
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
             "status": "TRADING", "isSpotTradingAllowed": "yes"},
        ],
    )
    def test_a_malformed_record_is_refused_never_skipped(self, payload) -> None:
        """A silently dropped instrument would understate the universe."""
        with pytest.raises(BinanceResponseError):
            map_symbol_record(payload)

    def _transport(self, body: dict):
        def send(url: str) -> HttpResponse:
            return HttpResponse(status=200, body=json.dumps(body).encode())

        return send

    def test_a_response_with_no_symbols_array_is_refused(self) -> None:
        with pytest.raises(BinanceResponseError, match="no 'symbols' array"):
            fetch_exchange_info(transport=self._transport({"serverTime": 1}))

    def test_a_response_with_no_server_time_is_refused(self) -> None:
        with pytest.raises(BinanceResponseError, match="serverTime"):
            fetch_exchange_info(transport=self._transport({"symbols": []}))

    def test_discovery_sorts_and_does_not_depend_on_provider_order(self) -> None:
        """**Hostile:** a shuffled provider response must give the same universe."""
        records = [
            {"symbol": s, "baseAsset": s[:-4], "quoteAsset": "USDT",
             "status": "TRADING", "isSpotTradingAllowed": True}
            for s in ("ZZZUSDT", "AAAUSDT", "MMMUSDT")
        ]
        forward = discover_pairs(
            transport=self._transport({"serverTime": 1, "symbols": records})
        )
        backward = discover_pairs(
            transport=self._transport(
                {"serverTime": 1, "symbols": list(reversed(records))}
            )
        )
        assert forward == backward
        assert [item.symbol for item in forward[1]] == [
            "AAAUSDT", "MMMUSDT", "ZZZUSDT"
        ]

    def test_a_listing_not_permitted_on_spot_is_dropped(self) -> None:
        _, pairs = discover_pairs(
            transport=self._transport(
                {
                    "serverTime": 1,
                    "symbols": [
                        {"symbol": "AUSDT", "baseAsset": "A", "quoteAsset": "USDT",
                         "status": "TRADING", "isSpotTradingAllowed": False},
                    ],
                }
            )
        )
        assert pairs == ()


# ------------------------------------------------------------------ identity ---


class TestEconomicIdentity:
    @pytest.mark.parametrize(
        "base, expected",
        [
            ("BTC", AssetClass.NATIVE),
            ("USDC", AssetClass.STABLECOIN),
            ("EUR", AssetClass.STABLECOIN),
            ("WBTC", AssetClass.WRAPPED),
            ("ETHBULL", AssetClass.LEVERAGED_TOKEN),
            ("PAXG", AssetClass.NATIVE),
        ],
    )
    def test_classification_is_by_sealed_membership(self, base, expected) -> None:
        assert classify_asset(base) is expected

    @pytest.mark.parametrize(
        "base, expected",
        [("BTC", "BTC"), ("WBTC", "BTC"), ("BTCUP", "BTC"), ("BETH", "ETH"),
         ("VEN", "VET"), ("BCC", "BCH"), ("NANO", "XNO")],
    )
    def test_identity_resolves_through_every_map(self, base, expected) -> None:
        assert economic_asset_id(base) == expected

    def test_only_NATIVE_may_stand_as_its_own_cluster(self) -> None:
        assert AssetClass.NATIVE.may_be_an_independent_cluster
        for other in (AssetClass.STABLECOIN, AssetClass.WRAPPED,
                      AssetClass.LEVERAGED_TOKEN):
            assert not other.may_be_an_independent_cluster

    def test_an_empty_base_asset_is_refused(self) -> None:
        with pytest.raises(UniverseError):
            classify_asset("")

    def test_the_volatility_backstop_flags_a_peg_the_name_list_missed(self) -> None:
        peg = [1.0 + 0.00001 * math.sin(index) for index in range(200)]
        assert peg_like_by_volatility(peg, bars_per_year=365.25) is True

    def test_the_backstop_does_not_flag_a_floating_asset(self) -> None:
        floating = [100.0 * math.exp(0.03 * math.sin(index)) for index in range(200)]
        assert peg_like_by_volatility(floating, bars_per_year=365.25) is False

    def test_the_backstop_returns_None_rather_than_guessing(self) -> None:
        assert peg_like_by_volatility([1.0, 1.0], bars_per_year=365.25) is None

    def test_the_backstop_refuses_a_non_positive_price(self) -> None:
        with pytest.raises(UniverseError, match="cannot be a traded price"):
            peg_like_by_volatility([1.0, 0.0, 1.0], bars_per_year=365.25)

    def test_the_rules_payload_is_sorted_and_complete(self) -> None:
        payload = identity_rules_payload()
        assert payload["stablecoin_assets"] == sorted(payload["stablecoin_assets"])
        for key in ("wrapped_representations", "leveraged_tokens", "redenominations"):
            assert list(payload[key]) == sorted(payload[key])


# ------------------------------------------------------------------ coverage ---


class TestCoverageAndQuality:
    def test_a_complete_series_reports_no_missing_bars(self) -> None:
        coverage = coverage_of("X", _bars(100))
        assert coverage.missing_fraction == 0.0
        assert coverage.longest_gap_bars == 0
        assert coverage.bars_observed == 100

    def test_an_empty_series_gives_None_not_a_complete_one(self) -> None:
        assert coverage_of("X", ()) is None

    def test_a_gap_is_measured_in_consecutive_missing_bars(self) -> None:
        head = _bars(10)
        tail = tuple(
            DailyBar(
                open_time=START + timedelta(days=20 + index),
                open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0,
            )
            for index in range(10)
        )
        coverage = coverage_of("X", head + tail)
        # Head covers days 0-9, tail resumes at day 20: days 10-19 are absent.
        assert coverage.longest_gap_bars == 10
        assert coverage.bars_observed == 20
        assert coverage.bars_expected == 30

    def test_duplicates_are_counted_and_not_added_to_observations(self) -> None:
        series = _bars(10)
        coverage = coverage_of("X", series + (series[3],))
        assert coverage.duplicate_bars == 1
        assert coverage.bars_observed == 10

    def test_quality_mirrors_coverage_exactly(self) -> None:
        coverage = coverage_of("X", _bars(50))
        quality = quality_of(coverage)
        assert quality.missing_fraction == coverage.missing_fraction
        assert quality.longest_gap_bars == coverage.longest_gap_bars

    def test_liquidity_ignores_bars_outside_the_window(self) -> None:
        inside = _bars(30, volume=1000.0)
        outside = tuple(
            DailyBar(
                open_time=END + timedelta(days=index), open=100.0, high=100.0,
                low=100.0, close=100.0, volume=10**9,
            )
            for index in range(30)
        )
        evidence = liquidity_of(
            "X", inside + outside, window_start=START, window_end=END
        )
        assert evidence.observed_days == 30
        assert evidence.median_quote_volume == pytest.approx(100_000.0)

    def test_a_window_with_no_volume_reports_no_evidence(self) -> None:
        evidence = liquidity_of(
            "X", _bars(30, volume=0.0), window_start=START, window_end=END
        )
        assert not evidence.is_measured
        assert evidence.observed_days == 0


# ---------------------------------------------------------------- dependence ---


class TestDependence:
    def _stamps(self, count: int):
        return [START + timedelta(days=index) for index in range(count)]

    def test_log_returns_refuse_a_non_positive_close(self) -> None:
        with pytest.raises(UniverseError, match="fabricate an adjacency"):
            log_returns([1.0, 0.0, 1.0])

    def test_returns_are_aligned_by_instant_not_by_position(self) -> None:
        """Two histories starting on different days must not be zipped."""
        instants, indexed = aligned_returns(
            {"A": {1: 0.1, 2: 0.2}, "B": {2: 0.3, 3: 0.4}}
        )
        assert instants == (1, 2, 3)
        assert indexed["A"].keys() & indexed["B"].keys() == {2}

    def test_pearson_refuses_unequal_lengths(self) -> None:
        with pytest.raises(UniverseError, match="equal length"):
            pearson([1.0, 2.0], [1.0])

    def test_the_market_factor_needs_at_least_two_assets_on_a_day(self) -> None:
        residual = market_residuals([1, 2], {"A": {1: 0.5, 2: 0.1}, "B": {2: 0.3}})
        assert 1 not in residual["A"]
        assert residual["A"][2] == pytest.approx(0.1 - 0.2)

    def test_demeaning_induces_exactly_minus_one_over_k_minus_one(self) -> None:
        """The artefact the residual correlation must be read against."""
        stamps = self._stamps(200)
        series = {
            name: [
                100.0 * math.exp(0.01 * math.sin(index * (position + 1) * 1.7))
                for index in range(200)
            ]
            for position, name in enumerate(("A", "B", "C", "D", "E"))
        }
        summary = measure_dependence(
            series, instants={name: stamps for name in series}, window_days=200
        )
        assert summary.demeaning_artefact == pytest.approx(-1.0 / 4)

    def test_a_two_point_series_is_dropped_rather_than_correlated(self) -> None:
        stamps = self._stamps(2)
        summary = measure_dependence(
            {"A": [1.0, 2.0]}, instants={"A": stamps}, window_days=2
        )
        assert summary.assets == 0
        assert not summary.is_measured

    def test_mismatched_closes_and_instants_are_refused(self) -> None:
        with pytest.raises(UniverseError, match="cannot be dated"):
            measure_dependence(
                {"A": [1.0, 2.0, 3.0]}, instants={"A": [START]}, window_days=3
            )

    def test_a_group_threshold_outside_the_range_is_refused(self) -> None:
        with pytest.raises(UniverseError, match=r"\[-1, 1\]"):
            correlated_groups({}, threshold=2.0)

    def test_effective_clusters_refuses_a_zero_cluster_count(self) -> None:
        with pytest.raises(UniverseError):
            effective_clusters(0, 0.5)


# -------------------------------------------------------------------- growth ---


class TestGrowthReusesMilestoneCB:
    def test_CB_s_published_requirement_reproduces_exactly(self) -> None:
        requirement = cb_required_information()
        assert requirement.required_observations == 4823
        assert requirement.required_clusters == 467

    def test_the_dispersion_is_inverted_from_CA_s_published_bounds(self) -> None:
        assert ca_observation_dispersion() == pytest.approx(3.5432, abs=1e-3)

    def test_the_independent_scenario_agrees_with_CB_s_own_arithmetic(self) -> None:
        """468 assets at 2 years and 5.1616/asset-year is CB's ~4,823 admissions."""
        row = growth_row(
            assets=468, observed=False, scenario="independent", correlation=0.0,
            years_per_asset=1.9976, admissions_per_asset_year=5.1616,
            effect=effect_for(Decimal("0.10")),
        )
        assert row.resolves
        assert row.projected_admissions == pytest.approx(4825, abs=10)

    def test_a_positive_correlation_creates_a_floor_no_size_clears(self) -> None:
        """The milestone's central mechanism, checked as arithmetic."""
        widths = [
            growth_row(
                assets=size, observed=False, scenario="raw", correlation=0.6,
                years_per_asset=2.0, admissions_per_asset_year=5.16,
                effect=effect_for(Decimal("0.10")),
            ).half_width
            for size in (100, 1_000, 10_000, 100_000)
        ]
        assert widths == sorted(widths, reverse=True)
        # It converges to z * sigma * sqrt(r / (years * density)), not to zero.
        floor = 1.959963985 * ca_observation_dispersion() * math.sqrt(
            0.6 / (2.0 * 5.16)
        )
        assert widths[-1] == pytest.approx(floor, rel=0.01)
        assert all(width > 0.10 for width in widths)

    def test_at_zero_correlation_the_width_falls_without_bound(self) -> None:
        widths = [
            growth_row(
                assets=size, observed=False, scenario="independent",
                correlation=0.0, years_per_asset=2.0,
                admissions_per_asset_year=5.16, effect=effect_for(Decimal("0.10")),
            ).half_width
            for size in (100, 10_000, 1_000_000)
        ]
        assert widths[-1] < widths[0] / 50

    def test_the_curve_marks_exactly_the_sizes_the_universe_reaches(self) -> None:
        from fmis.universe.dependence import DependenceSummary

        dependence = DependenceSummary(
            assets=38, pairs_measured=703, pairs_skipped=0,
            raw_mean_correlation=0.6, raw_median_correlation=0.6,
            residual_mean_correlation=0.0, residual_median_correlation=0.0,
            demeaning_artefact=-1 / 37, market_factor_share=0.62,
            highest_decile_correlation=0.75, window_days=731, method="test",
        )
        rows = growth_curve(
            sizes=UNIVERSE_GROWTH_SIZES, scenarios=("independent",),
            dependence=dependence, eligible_assets=38, years_per_asset=2.0,
            admissions_per_asset_year=5.16, effect=effect_for(Decimal("0.10")),
        )
        observed = {row.assets for row in rows if row.observed}
        assert observed == {15, 30}

    def test_a_non_decimal_effect_is_refused(self) -> None:
        with pytest.raises(UniverseError, match="must be a Decimal"):
            effect_for(0.10)  # type: ignore[arg-type]

    def test_the_primary_effect_is_marked_and_the_others_are_not(self) -> None:
        assert "sealed bar" in effect_for(Decimal("0.10")).rationale
        assert "NOT Milestone CA's question" in effect_for(Decimal("0.50")).rationale


# ------------------------------------------------------------------- density ---


class TestAdmissionDensity:
    def test_CA_s_three_samples_reproduce_from_sealed_constants(self) -> None:
        entries = published_densities()
        assert {item.asset_id for item in entries} == {
            "ca:development", "ca:validation", "ca:holdout"
        }
        rates = sorted(item.per_year for item in entries)
        # Three disjoint samples, 36 distinct symbols, agreeing to within 1 %.
        assert rates[0] == pytest.approx(5.145, abs=0.01)
        assert rates[-1] == pytest.approx(5.202, abs=0.01)

    def test_the_pooled_rate_weights_by_asset_years_not_by_sample(self) -> None:
        summary = summarise_density(published_densities())
        assert summary.pooled_per_asset_year == pytest.approx(5.1616, abs=1e-3)
        assert summary.pooled_per_asset_year != summary.mean_per_asset_year

    def test_an_empty_summary_is_refused_rather_than_reported_as_zero(self) -> None:
        with pytest.raises(UniverseError, match="absence"):
            summarise_density(())

    def test_a_density_over_zero_years_is_refused(self) -> None:
        with pytest.raises(UniverseError, match="division by zero"):
            AssetDensity(asset_id="X", admissions=5, usable_years=0.0, source="x")

    def test_the_subsample_is_seeded_and_order_independent(self) -> None:
        names = [f"ASSET{index}" for index in range(50)]
        first = subsample_for_density(names, size=12)
        second = subsample_for_density(list(reversed(names)), size=12)
        assert first == second
        assert len(first) == 12

    def test_the_subsample_changes_with_the_seed(self) -> None:
        names = [f"ASSET{index}" for index in range(50)]
        assert subsample_for_density(names, size=12) != subsample_for_density(
            names, size=12, seed="a-different-seed"
        )

    def test_an_empty_candidate_pool_is_refused(self) -> None:
        with pytest.raises(UniverseError, match="no candidate"):
            subsample_for_density([], size=3)


# ------------------------------------------------------------------ artifact ---


class _FakeStudy:
    def __init__(self, verdict: str = "infeasible") -> None:
        self._verdict = verdict

    def payload(self) -> dict:
        return {
            "preregistration_digest": "a" * 64,
            "assessment": {"verdict": self._verdict},
            "eligible_assets": 38,
        }


class TestTheArtifact:
    def test_the_digest_covers_everything_except_its_own_slot(self) -> None:
        payload = encode_universe_study(_FakeStudy(), manifest={"run": "one"})
        assert artifact_digest(payload) == payload["manifest"]["content_digest"]

    def test_editing_a_measured_number_breaks_the_digest(self) -> None:
        payload = encode_universe_study(_FakeStudy(), manifest={"run": "one"})
        payload["study"]["eligible_assets"] = 500
        assert artifact_digest(payload) != payload["manifest"]["content_digest"]

    def test_editing_the_manifest_breaks_it_too(self) -> None:
        payload = encode_universe_study(_FakeStudy(), manifest={"run": "one"})
        payload["manifest"]["run"] = "two"
        assert artifact_digest(payload) != payload["manifest"]["content_digest"]

    def test_it_refuses_to_overwrite_a_persisted_record(self, tmp_path) -> None:
        payload = encode_universe_study(_FakeStudy(), manifest={"run": "one"})
        target = write_universe_artifact(payload, tmp_path / "study.json")
        with pytest.raises(UniverseError, match="already exists"):
            write_universe_artifact(payload, target)

    def test_it_round_trips_and_verifies(self, tmp_path) -> None:
        payload = encode_universe_study(_FakeStudy(), manifest={"run": "one"})
        written = write_universe_artifact(payload, tmp_path / "study.json")
        artifact = read_universe_artifact(written)
        assert verify_artifact_digest(artifact)
        assert artifact.verdict == "infeasible"

    def test_a_capture_is_not_read_as_a_study(self, tmp_path) -> None:
        """Two different files must not be readable as each other."""
        import gzip

        target = tmp_path / "capture.json.gz"
        target.write_bytes(
            gzip.compress(
                json.dumps(
                    {"kind": "something.else", "schema_version": 1, "manifest": {},
                     "study": {}, "offline_claim": "x"}
                ).encode()
            )
        )
        with pytest.raises(UniverseError, match="kind"):
            read_universe_artifact(target)

    def test_the_persisted_CC_artifact_verifies_and_says_INFEASIBLE(self) -> None:
        """The real committed artifact, checked rather than described."""
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[1]
            / "reports" / "artifacts" / "0039_cc_universe_feasibility.json.gz"
        )
        if not path.exists():  # pragma: no cover - artifact present in-repo
            pytest.skip("the CC artifact is not present")
        artifact = read_universe_artifact(path)
        assert artifact.payload["kind"] == CC_ARTIFACT_KIND
        assert verify_artifact_digest(artifact)
        assert artifact.verdict == "infeasible"
        study = artifact.study
        assert study["eligible_assets"] == 38
        # These two counts are the ONLY figures that moved when the artifact was
        # regenerated on a later discovery (2026-08-28 -> 2026-09-03): the provider
        # listed four more instruments. They are asserted as a floor rather than an
        # equality precisely because they are the mutable ones — provider drift is
        # a documented property of this study, not a regression.
        assert study["discovered_instruments"] >= 3645
        assert study["economic_assets"] >= 656
        assert study["economic_assets"] < study["discovered_instruments"]
        assert study["warmup_days"] == 1750
        assert study["horizon"]["qualifying_assets"] == 106
        assert study["horizon"]["reaches_requirement"] is False
        assert study["assessment"]["is_approved_for_trading"] is False


class TestSeriesDigests:
    def test_two_equal_series_digest_equally(self) -> None:
        assert series_digest(_bars(20)) == series_digest(_bars(20))

    def test_one_changed_bar_changes_the_digest(self) -> None:
        original = list(_bars(20))
        changed = list(original)
        changed[5] = DailyBar(
            open_time=changed[5].open_time, open=1.0, high=1.0, low=1.0,
            close=1.0, volume=1.0,
        )
        assert series_digest(tuple(original)) != series_digest(tuple(changed))


# ===========================================================================
# Regressions added after the independent review (Milestone CC, §21).
# ===========================================================================


class TestTheHoldoutCannotSetADesignParameter:
    """Review finding, own pass. `ca_observation_dispersion` took any sample."""

    def test_the_development_sample_is_accepted(self) -> None:
        assert ca_observation_dispersion() == pytest.approx(3.5432, abs=1e-3)

    @pytest.mark.parametrize("sample", ["holdout", "validation"])
    def test_a_protected_sample_is_refused_by_name(self, sample) -> None:
        """**The regression.** Inverting sigma from the holdout would spend it."""
        with pytest.raises(UniverseError, match="may not set a design parameter"):
            ca_observation_dispersion(sample=sample)

    def test_the_refusal_names_the_only_permitted_sample(self) -> None:
        from fmis.universe.growth import DESIGN_SAMPLE

        assert DESIGN_SAMPLE == "development"
        from fmis.research_design.models import SampleRole

        assert SampleRole(DESIGN_SAMPLE).may_inform_design
        assert not SampleRole.HOLDOUT.may_inform_design


class TestTheWithinClusterCorrelationClaim:
    """Review finding, own pass. The old 'lower bound' claim was mis-stated."""

    def _required_assets(self, rho_within: float) -> int:
        from fmis.research_design.resolution import (
            half_width_for_design,
            observation_dispersion_from_half_width,
        )

        ca_half = (0.3662 - -0.7494) / 2
        sigma = observation_dispersion_from_half_width(
            half_width=ca_half, clusters=15, observations=155,
            intracluster_correlation=rho_within, confidence=0.95,
        )
        years, density = 1.9976, 5.1616
        low, high = 1, 200_000
        while low < high:
            mid = (low + high) // 2
            n = int(mid * years * density)
            width = half_width_for_design(
                observation_sd=sigma, clusters=mid,
                observations_per_cluster=n / mid,
                intracluster_correlation=rho_within, confidence=0.95,
            )
            if width < 0.10:
                high = mid
            else:
                low = mid + 1
        return low

    def test_the_requirement_is_robust_to_the_within_cluster_correlation(self) -> None:
        """**The regression.** Across rho_within in [0, 0.8] it moves by one asset.

        `sigma` is inverted from CA's interval under the SAME rho_within, so the
        two effects nearly cancel — and CA's observations-per-cluster (10.333) is
        almost exactly CC's projected admissions-per-asset (10.311), which is why
        the cancellation is near-exact. The requirement therefore does not rest on
        a parameter nobody can measure.
        """
        required = {rho: self._required_assets(rho)
                    for rho in (0.0, 0.05, 0.2, 0.5, 0.8)}
        assert max(required.values()) - min(required.values()) <= 1, required
        assert required[0.0] == 468

    def test_zero_is_NOT_the_most_favourable_value(self) -> None:
        """The discarded claim, pinned as false so it cannot be reinstated."""
        assert self._required_assets(0.0) >= self._required_assets(0.5)

    def test_CA_and_CC_observations_per_cluster_nearly_coincide(self) -> None:
        """The reason the cancellation is near-exact, stated as a number."""
        assert 155 / 15 == pytest.approx(1.9976 * 5.1616, rel=0.005)


class TestTheEigenvalueShareIsGuarded:
    """Review finding A-2. Power iteration could return a subdominant eigenvalue."""

    def test_it_agrees_with_an_exact_decomposition_on_positive_data(self) -> None:
        from fmis.universe.dependence import _leading_eigenvalue_share

        stamps = [START + timedelta(days=i) for i in range(400)]
        rho = 0.6
        import random

        rng = random.Random(11)
        # The common factor is drawn ONCE PER INSTANT and shared across assets —
        # drawing it per asset would build six independent series instead.
        series = {f"A{k}": {} for k in range(6)}
        for stamp in stamps[1:]:
            common = rng.gauss(0, 1)
            for k in range(6):
                series[f"A{k}"][stamp] = 0.02 * (
                    math.sqrt(rho) * common + math.sqrt(1 - rho) * rng.gauss(0, 1)
                )
        share = _leading_eigenvalue_share(sorted(series), series)
        assert share is not None
        # For an equicorrelated matrix the exact share is (1 + (K-1)rho)/K.
        assert share == pytest.approx((1 + 5 * rho) / 6, abs=0.05)

    def test_a_subdominant_result_is_refused_rather_than_reported(self) -> None:
        """**The regression.** A correlation matrix's top eigenvalue is always >= 1.

        The review supplied a two-block matrix whose dominant eigenvector is
        orthogonal to the uniform start, on which the old code silently returned a
        share 55x too small. The guard refuses any converged value below 1.
        """
        from fmis.universe.dependence import _leading_eigenvalue_share

        stamps = [START + timedelta(days=i) for i in range(400)]
        # Two EXACTLY anti-correlated blocks. Every row of the correlation matrix
        # sums to 3(+1) + 3(-1) = 0, so a uniform start maps to the zero vector:
        # the leading eigenvector (+1,+1,+1,-1,-1,-1) is exactly orthogonal to it
        # and power iteration cannot reach it from there.
        import random

        rng = random.Random(3)
        base = [rng.gauss(0, 1) for _ in range(399)]
        series = {}
        for k in range(6):
            sign = 1.0 if k < 3 else -1.0
            series[f"A{k}"] = dict(
                zip(stamps[1:], [0.02 * sign * base[i] for i in range(399)])
            )
        share = _leading_eigenvalue_share(sorted(series), series)
        assert share is None, (
            f"returned {share} for a matrix whose dominant eigenvector is "
            "orthogonal to the uniform start; a wrong share was reported as a "
            "measurement"
        )

    def test_any_reported_share_is_at_least_one_over_K(self) -> None:
        """The invariant the guard enforces: lambda >= 1 for a correlation matrix."""
        from fmis.universe.dependence import _leading_eigenvalue_share

        import random

        for seed, K in ((1, 4), (2, 7), (3, 10)):
            rng = random.Random(seed)
            stamps = [START + timedelta(days=i) for i in range(300)]
            series = {f"A{k}": {} for k in range(K)}
            for stamp in stamps[1:]:
                common = rng.gauss(0, 1)
                for k in range(K):
                    series[f"A{k}"][stamp] = 0.02 * (0.5 * common + rng.gauss(0, 1))
            share = _leading_eigenvalue_share(sorted(series), series)
            if share is not None:
                assert share >= 1.0 / K - 1e-12, (K, share)

    def test_every_measured_correlation_in_the_study_is_non_negative(self) -> None:
        """Why the guard never fires on the real universe (Perron-Frobenius)."""
        from pathlib import Path

        from fmis.universe.artifact import read_universe_artifact

        path = (Path(__file__).resolve().parents[1] / "reports" / "artifacts"
                / "0039_cc_universe_feasibility.json.gz")
        if not path.exists():  # pragma: no cover - artifact present in-repo
            pytest.skip("the CC artifact is not present")
        dependence = read_universe_artifact(path).study["dependence"]
        assert dependence["market_factor_share"] is not None
        assert dependence["raw_mean_correlation"] > 0


class TestTheResidualScenarioCannotMeasureResidualDependence:
    """Review finding A-1, re-derived. The sealed scenario is structurally blind."""

    def test_demeaning_pins_the_residual_at_the_artefact_for_any_dependence(self) -> None:
        """**The central post-review finding, as a regression.**

        Built as x_i = f + e_i with corr(e_i, e_j) = rho_e. Cross-sectional
        demeaning removes ANY exchangeable common component exactly, so the
        measured residual correlation is -1/(K-1) whatever rho_e is — meaning the
        sealed residual scenario carries no information about the LEVEL of
        residual dependence.
        """
        import random

        K, T = 12, 2500
        stamps = [START + timedelta(days=i) for i in range(T + 1)]
        for rho_e in (0.0, 0.3, 0.7):
            rng = random.Random(5)
            closes = {f"A{k}": [100.0] for k in range(K)}
            for _ in range(T):
                factor = rng.gauss(0, 1)
                shared = rng.gauss(0, 1)
                for k in range(K):
                    idio = (math.sqrt(rho_e) * shared
                            + math.sqrt(1 - rho_e) * rng.gauss(0, 1))
                    closes[f"A{k}"].append(
                        closes[f"A{k}"][-1] * math.exp(0.02 * (factor + idio))
                    )
            summary = measure_dependence(
                closes, instants={n: stamps for n in closes}, window_days=T
            )
            # Exact in expectation; a finite sample deviates by O(1/sqrt(T)).
            # The tolerance is still two orders of magnitude below any dependence
            # signal this study would act on.
            assert summary.residual_mean_correlation == pytest.approx(
                -1.0 / (K - 1), abs=1e-3
            ), f"rho_e={rho_e} moved the residual off the artefact"
            assert summary.residual_excess_over_artefact == pytest.approx(0.0, abs=1e-3)

    def test_correlation_for_returns_the_SEALED_quantity_not_the_excess(self) -> None:
        """The seal defines `residual` as the measured mean, and that is honoured.

        An independent review proposed substituting the artefact-corrected excess.
        That was REJECTED: changing what a sealed scenario computes after seeing
        its result is what a seal exists to prevent.
        """
        from fmis.universe.dependence import DependenceSummary

        summary = DependenceSummary(
            assets=38, pairs_measured=703, pairs_skipped=0,
            raw_mean_correlation=0.6041, raw_median_correlation=0.62,
            residual_mean_correlation=-0.024764, residual_median_correlation=-0.04,
            demeaning_artefact=-0.027027, market_factor_share=0.6254,
            highest_decile_correlation=0.75, window_days=731, method="test",
        )
        assert summary.correlation_for("residual") == 0.0
        assert summary.residual_excess_over_artefact == pytest.approx(0.002263, abs=1e-6)

    def test_a_tiny_residual_dependence_would_be_decisive(self) -> None:
        """Post-review limitation CC-8, pinned: 0.0023 makes it unreachable."""
        from fmis.universe.dependence import DependenceSummary

        summary = DependenceSummary(
            assets=38, pairs_measured=703, pairs_skipped=0,
            raw_mean_correlation=0.6041, raw_median_correlation=0.62,
            residual_mean_correlation=0.002263, residual_median_correlation=0.002,
            demeaning_artefact=-0.027027, market_factor_share=0.6254,
            highest_decile_correlation=0.75, window_days=731, method="test",
        )
        requirement = requirement_for_effect(
            magnitude=Decimal("0.10"), scenario="residual", dependence=summary,
            years_per_asset=1.9976, admissions_per_asset_year=5.1616,
        )
        assert requirement.reachable is False
        assert requirement.required_assets is None


class TestPostReviewLimitationsAreCarried:
    def test_they_are_separate_from_the_sealed_limitations(self) -> None:
        """A seal may not be retro-fitted with what was learned after sealing."""
        from fmis.universe.dependence import POST_REVIEW_LIMITATIONS
        from fmis.universe.preregistration import CC_LIMITATIONS

        assert len(POST_REVIEW_LIMITATIONS) == 3
        for item in POST_REVIEW_LIMITATIONS:
            assert item not in CC_LIMITATIONS
        assert {item[:5] for item in POST_REVIEW_LIMITATIONS} == {
            "CC-7 ", "CC-8 ", "CC-9 "
        }

    def test_adding_them_did_not_move_the_seal(self) -> None:
        from fmis.universe.preregistration import (
            CC_PREREGISTRATION_DIGEST,
            cc_preregistration_digest,
        )

        assert cc_preregistration_digest() == CC_PREREGISTRATION_DIGEST


class TestMutationSurvivorsClosedAfterReview:
    """Three mutation probes survived the post-review suite. Each is closed here.

    A surviving mutant is a rule the tests do not actually constrain. All three
    survived for the same underlying reason — the real universe never exercises
    the branch — which is exactly when a hostile test has to construct the case.
    """

    def test_a_pair_with_too_little_overlap_is_skipped_not_measured(self) -> None:
        """Survivor 1: `MIN_OVERLAP_DAYS` 60 -> 2 changed nothing.

        In the measured universe all 703 pairs share the full window, so the
        threshold never binds. Constructed here so it does.
        """
        from fmis.universe.dependence import MIN_OVERLAP_DAYS

        assert MIN_OVERLAP_DAYS == 60
        early = [START + timedelta(days=i) for i in range(200)]
        late = [START + timedelta(days=150 + i) for i in range(200)]
        values = [100.0 * math.exp(0.01 * math.sin(i)) for i in range(200)]
        summary = measure_dependence(
            {"A": values, "B": values},
            instants={"A": early, "B": late}, window_days=350,
        )
        # The two series overlap on 49 instants, below the sealed floor of 60.
        assert summary.pairs_measured == 0
        assert summary.pairs_skipped == 1
        assert summary.raw_mean_correlation is None

    def test_a_pair_with_enough_overlap_IS_measured(self) -> None:
        """The other side of the same threshold, so the test is a bound not a wall."""
        early = [START + timedelta(days=i) for i in range(200)]
        late = [START + timedelta(days=100 + i) for i in range(200)]
        values = [100.0 * math.exp(0.01 * math.sin(i)) for i in range(200)]
        summary = measure_dependence(
            {"A": values, "B": values},
            instants={"A": early, "B": late}, window_days=300,
        )
        assert summary.pairs_measured == 1
        assert summary.pairs_skipped == 0

    def test_the_eigenvalue_guard_itself_fires(self) -> None:
        """Survivor 2: replacing `if eigenvalue < 1.0` with `if False` changed nothing.

        The earlier anti-correlation test lands on the ``norm <= 0`` branch instead,
        so the guard proper was never exercised. Two ANTI-correlated series make a
        2x2 whose uniform start is exactly the eigenvector of the SMALLER eigenvalue
        ``1 + r``: for r ~ -0.9 the iteration converges to ~0.1, which is below 1
        and therefore impossible for a correlation matrix's dominant eigenvalue.
        """
        import random

        from fmis.universe.dependence import _leading_eigenvalue_share, pearson

        rng = random.Random(17)
        stamps = [START + timedelta(days=i) for i in range(400)]
        base = [rng.gauss(0, 1) for _ in range(399)]
        noise = [rng.gauss(0, 1) for _ in range(399)]
        a = {stamps[i + 1]: base[i] for i in range(399)}
        b = {stamps[i + 1]: -base[i] + 0.45 * noise[i] for i in range(399)}
        shared = sorted(a.keys() & b.keys())
        correlation = pearson([a[k] for k in shared], [b[k] for k in shared])
        assert correlation is not None and correlation < -0.85, correlation

        share = _leading_eigenvalue_share(["A", "B"], {"A": a, "B": b})
        assert share is None, (
            f"returned {share}; the uniform start converges to 1 + r ~= "
            f"{1 + correlation:.3f}, which is below 1 and cannot be the dominant "
            "eigenvalue of a correlation matrix"
        )

    def test_the_named_unrecoverable_pair_is_the_one_the_report_cites(self) -> None:
        """Survivor 3: renaming `KNOWN_UNRECOVERABLE_PAIR` changed nothing.

        The report states as fact that HSRUSDT traded on this provider and is absent
        from both `exchangeInfo` and `klines`. That specific claim is what makes the
        survivorship gap *demonstrated* rather than suspected, so it is pinned.
        """
        from fmis.universe.verdict import KNOWN_UNRECOVERABLE_PAIR, classify_survivorship

        assert KNOWN_UNRECOVERABLE_PAIR == "HSRUSDT"
        reading = classify_survivorship(
            total_instruments=3649, halted_instruments=2290, eligible_halted=4,
            unrecoverable_gap_demonstrated=True,
        )
        assert KNOWN_UNRECOVERABLE_PAIR in reading.evidence
        assert "UNMEASURABLE" in reading.evidence


class TestTheResidualSensitivityIsMarginalAndSaysSo:
    """Release-audit finding: the 0.0023 claim is conditional, not demonstrated.

    The half-width floor is `z*sigma*sqrt(r/(years*density))`. The break-even `r`
    — where the floor equals the +0.10 bar exactly — is 0.00214. The measured
    residual excess is 0.0022633, only 5.9 % above it, and that margin does not
    survive the +/-30 % scatter limitation CB-6 places on the input interval.

    These tests pin the marginality so the conditional claim cannot silently
    harden into a demonstrated one.
    """

    Z = 1.959963984540054
    YEARS = 1.9976223927374908
    DENSITY = 5.16163222045575
    EXCESS = 0.0022633357817192674

    def _floor(self, r, *, sigma=None, years=None, density=None):
        sigma = ca_observation_dispersion() if sigma is None else sigma
        years = self.YEARS if years is None else years
        density = self.DENSITY if density is None else density
        return self.Z * sigma * math.sqrt(r / (years * density))

    def _breakeven(self, **kwargs) -> float:
        low, high = 0.0, 1.0
        for _ in range(200):
            mid = (low + high) / 2
            if self._floor(mid, **kwargs) < 0.10:
                low = mid
            else:
                high = mid
        return low

    def test_the_break_even_correlation_is_where_the_report_says(self) -> None:
        assert self._breakeven() == pytest.approx(0.00214, abs=1e-5)

    def test_the_measured_excess_clears_break_even_by_under_ten_percent(self) -> None:
        """The margin is thin, and that is the point of recording it."""
        margin = self.EXCESS / self._breakeven() - 1.0
        assert 0.0 < margin < 0.10, margin
        assert margin == pytest.approx(0.059, abs=0.01)

    @pytest.mark.parametrize(
        "label, kwargs",
        [
            ("density +10%", {"density": DENSITY * 1.1}),
            ("years +10%", {"years": YEARS * 1.1}),
            ("CA half-width -30% (CB-6)", {"sigma": None}),
        ],
    )
    def test_the_claim_FLIPS_under_ordinary_variation(self, label, kwargs) -> None:
        """**The regression.** The measured excess does NOT robustly close the door."""
        if label.startswith("CA half-width"):
            kwargs = {"sigma": ca_observation_dispersion() * 0.7}
        assert self.EXCESS < self._breakeven(**kwargs), (
            f"{label}: the claim survived, so the report's marginality caveat is "
            "now wrong and must be re-derived"
        )

    def test_a_correlation_of_that_ORDER_is_decisive_regardless(self) -> None:
        """What IS robust: an order-0.002 correlation defeats any universe size."""
        for r in (0.005, 0.01, 0.05):
            assert self._floor(r) > 0.10, r

    def test_the_carried_limitation_states_the_conditional_not_the_demonstrated(self) -> None:
        from fmis.universe.dependence import POST_REVIEW_LIMITATIONS

        cc8 = next(item for item in POST_REVIEW_LIMITATIONS if item.startswith("CC-8"))
        assert "ORDER 0.002" in cc8
        assert "break-even" in cc8
        assert "is NOT a measured between-asset" in cc8
        assert "CONDITIONAL" in cc8
