"""Hostile probes: every way Milestone CC could be made to lie, tried on purpose.

Each test below constructs the input that would produce a **flattering** answer
and asserts the code refuses it or reports it honestly. A feasibility study is
easier to fake than an effect study — a determined analyst reaches 467 clusters by
counting `BTCUSDT`, `BTCUSDC` and `WBTCUSDT` as three, or by loosening a history
floor until the number arrives — so these are the tests that carry the milestone's
credibility.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.universe.capture import DailyBar
from fmis.universe.dependence import (
    DependenceSummary,
    correlated_groups,
    effective_clusters,
    measure_dependence,
    pearson,
)
from fmis.universe.eligibility import assess_asset, funnel_counts, screen_pair
from fmis.universe.growth import growth_row, requirement_for_effect
from fmis.universe.horizon import HorizonCeiling, asset_horizon, horizon_ceiling
from fmis.universe.identity import (
    classify_asset,
    economic_asset_id,
    group_by_economic_asset,
)
from fmis.universe.models import (
    AssetAssessment,
    AssetClass,
    CoverageMetrics,
    EconomicAsset,
    Exclusion,
    ExclusionReason,
    FeasibilityVerdict,
    LiquidityEvidence,
    PairStatus,
    SurvivorshipClass,
    TradingPair,
    UniverseError,
)
from fmis.universe.preregistration import representative_of
from fmis.universe.verdict import (
    SurvivorshipReading,
    classify_survivorship,
    decide_feasibility,
)

UTC = timezone.utc
WINDOW_START = datetime(2023, 6, 1, tzinfo=UTC)
WINDOW_END = datetime(2025, 6, 1, tzinfo=UTC)
WARMUP = timedelta(days=1750)


def pair(symbol: str, base: str, quote: str = "USDT", *, halted: bool = False):
    return TradingPair(
        symbol=symbol, base_asset=base, quote_asset=quote,
        status=PairStatus.HALTED if halted else PairStatus.TRADING,
    )


def bars(
    *, start: datetime, days: int, price: float = 100.0, volume: float = 10_000.0,
    step: int = 1, drift: float = 0.0,
) -> tuple[DailyBar, ...]:
    out = []
    for index in range(days):
        value = price * math.exp(drift * index)
        out.append(
            DailyBar(
                open_time=start + timedelta(days=index * step),
                open=value, high=value * 1.01, low=value * 0.99,
                close=value, volume=volume,
            )
        )
    return tuple(out)


def asset(asset_id: str, symbol: str, *, halted: bool = False) -> EconomicAsset:
    item = pair(symbol, asset_id, halted=halted)
    return EconomicAsset(
        asset_id=asset_id, asset_class=AssetClass.NATIVE, representative=item,
        pairs=(item,), identity_rule="test",
    )


# --------------------------------------------------------------- inflation ---


class TestTheClusterCountCannotBeInflated:
    def test_duplicate_trading_pairs_collapse_to_one_economic_asset(self) -> None:
        """BTCUSDT and BTCFDUSD are two markets and one experimental cluster."""
        assets = group_by_economic_asset(
            [pair("BTCUSDT", "BTC"), pair("BTCFDUSD", "BTC", "FDUSD")],
            representative_of=representative_of,
        )
        assert len(assets) == 1
        assert assets[0].asset_id == "BTC"
        assert len(assets[0].duplicate_pairs) == 1

    def test_a_wrapped_representation_collapses_onto_its_underlying(self) -> None:
        assets = group_by_economic_asset(
            [pair("BTCUSDT", "BTC"), pair("WBTCUSDT", "WBTC")],
            representative_of=representative_of,
        )
        assert [item.asset_id for item in assets] == ["BTC"]

    def test_a_leveraged_token_collapses_onto_its_underlying(self) -> None:
        assets = group_by_economic_asset(
            [pair("ETHUSDT", "ETH"), pair("ETHBULLUSDT", "ETHBULL")],
            representative_of=representative_of,
        )
        assert [item.asset_id for item in assets] == ["ETH"]

    def test_a_redenominated_ticker_collapses_onto_its_successor(self) -> None:
        assets = group_by_economic_asset(
            [pair("VETUSDT", "VET"), pair("VENUSDT", "VEN")],
            representative_of=representative_of,
        )
        assert [item.asset_id for item in assets] == ["VET"]

    def test_stablecoins_never_reach_the_identity_stage(self) -> None:
        for base in ("USDC", "FDUSD", "DAI", "TUSD", "EUR"):
            excluded = screen_pair(pair(f"{base}USDT", base))
            assert excluded is not None
            assert excluded.reason is ExclusionReason.BASE_IS_STABLECOIN

    def test_the_identity_maps_refuse_a_cycle(self) -> None:
        """A ticker that is its own underlying has no economic identity."""
        import fmis.universe.identity as identity

        original = identity.WRAPPED_REPRESENTATIONS
        try:
            identity.WRAPPED_REPRESENTATIONS = {"AAA": "BBB", "BBB": "AAA"}
            with pytest.raises(UniverseError, match="cycle"):
                economic_asset_id("AAA")
        finally:
            identity.WRAPPED_REPRESENTATIONS = original

    def test_a_suffix_rule_would_have_removed_real_assets(self) -> None:
        """The reason sealed lists are used instead of patterns. **JUP is a token.**"""
        for base in ("JUP", "SYRUP", "W"):
            assert classify_asset(base) is AssetClass.NATIVE

    def test_one_pair_listed_twice_is_refused_outright(self) -> None:
        with pytest.raises(UniverseError, match="appears twice"):
            group_by_economic_asset(
                [pair("BTCUSDT", "BTC"), pair("BTCUSDT", "BTC")],
                representative_of=representative_of,
            )


class TestCorrelationCannotBeIgnored:
    def test_five_hundred_cloned_series_are_NOT_five_hundred_clusters(self) -> None:
        """**The headline hostile test.** Perfect co-movement supplies one cluster."""
        assert effective_clusters(500, 1.0) == pytest.approx(1.0)

    def test_the_effective_count_saturates_at_one_over_r(self) -> None:
        for correlation in (0.1, 0.25, 0.5):
            ceiling = 1.0 / correlation
            assert effective_clusters(10**6, correlation) < ceiling
            assert effective_clusters(10**6, correlation) > ceiling * 0.99

    def test_identical_clones_measure_a_correlation_of_one(self) -> None:
        stamps = [WINDOW_START + timedelta(days=i) for i in range(120)]
        closes = [100.0 * math.exp(0.01 * math.sin(i)) for i in range(120)]
        summary = measure_dependence(
            {"A": closes, "B": list(closes), "C": list(closes)},
            instants={"A": stamps, "B": stamps, "C": stamps},
            window_days=120,
        )
        assert summary.raw_mean_correlation == pytest.approx(1.0, abs=1e-9)

    def test_a_negative_correlation_cannot_create_clusters(self) -> None:
        with pytest.raises(UniverseError, match=r"\[0, 1\]"):
            effective_clusters(10, -0.5)

    def test_zero_correlation_returns_every_asset_as_a_cluster(self) -> None:
        assert effective_clusters(38, 0.0) == pytest.approx(38.0)

    def test_a_constant_series_has_no_correlation_rather_than_zero(self) -> None:
        assert pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None

    def test_a_missing_scenario_measurement_is_never_read_as_zero(self) -> None:
        summary = DependenceSummary(
            assets=2, pairs_measured=0, pairs_skipped=1,
            raw_mean_correlation=None, raw_median_correlation=None,
            residual_mean_correlation=None, residual_median_correlation=None,
            demeaning_artefact=None, market_factor_share=None,
            highest_decile_correlation=None, window_days=10, method="none",
        )
        with pytest.raises(UniverseError, match="most favourable"):
            summary.correlation_for("residual")

    def test_an_unknown_scenario_is_refused_by_name(self) -> None:
        summary = DependenceSummary(
            assets=2, pairs_measured=1, pairs_skipped=0,
            raw_mean_correlation=0.5, raw_median_correlation=0.5,
            residual_mean_correlation=0.1, residual_median_correlation=0.1,
            demeaning_artefact=-1.0, market_factor_share=0.5,
            highest_decile_correlation=0.5, window_days=10, method="x",
        )
        with pytest.raises(UniverseError, match="unknown dependence scenario"):
            summary.correlation_for("whatever_is_convenient")

    def test_perfectly_correlated_symbols_form_one_measured_group(self) -> None:
        stamps = [WINDOW_START + timedelta(days=i) for i in range(120)]
        series = {
            name: {stamp: math.sin(index) for index, stamp in enumerate(stamps)}
            for name in ("A", "B", "C")
        }
        groups = correlated_groups(series, threshold=0.8)
        assert groups == (("A", "B", "C"),)


# ------------------------------------------------------------- eligibility ---


class TestEveryExclusionIsAttributable:
    def test_an_exclusion_with_an_empty_reason_is_refused(self) -> None:
        with pytest.raises(UniverseError, match="non-empty"):
            Exclusion(
                symbol="BTCUSDT",
                reason=ExclusionReason.EXCESSIVE_GAP,
                detail="",
            )

    def test_an_excluded_asset_must_carry_a_reason(self) -> None:
        with pytest.raises(UniverseError, match="excluded with no reason"):
            AssetAssessment(
                asset=asset("BTC", "BTCUSDT"), coverage=None, quality=None,
                liquidity=None, eligible=False, exclusion=None,
            )

    def test_an_eligible_asset_may_not_carry_one(self) -> None:
        with pytest.raises(UniverseError, match="eligible asset carries an exclusion"):
            AssetAssessment(
                asset=asset("BTC", "BTCUSDT"), coverage=None, quality=None,
                liquidity=None, eligible=True,
                exclusion=Exclusion(
                    symbol="BTCUSDT", reason=ExclusionReason.EXCESSIVE_GAP,
                    detail="x",
                ),
            )

    def test_the_funnel_refuses_to_balance_falsely(self) -> None:
        """An instrument that left without a reason must break the tally."""
        with pytest.raises(UniverseError, match="does not balance"):
            funnel_counts(discovered=100, exclusions=(), eligible=5)

    def test_every_reason_has_exactly_one_owning_stage(self) -> None:
        for reason in ExclusionReason:
            assert reason.stage is not None


class TestHistoryRulesCannotBeEvaded:
    def test_a_young_asset_cannot_pass_the_warmup_requirement(self) -> None:
        """Listed inside the window: the weekly context role can never be warm."""
        young = datetime(2024, 1, 1, tzinfo=UTC)
        result = assess_asset(
            asset("NEW", "NEWUSDT"),
            bars(start=young, days=400),
            listed_at=young, window_start=WINDOW_START, window_end=WINDOW_END,
            warmup=WARMUP,
        )
        assert not result.eligible
        assert result.exclusion.reason is ExclusionReason.INSUFFICIENT_HISTORY_FOR_WARMUP

    def test_an_instrument_delisted_before_the_window_has_no_forward_room(self) -> None:
        listed = datetime(2017, 8, 1, tzinfo=UTC)
        result = assess_asset(
            asset("OLD", "OLDUSDT"),
            bars(start=datetime(2022, 1, 1, tzinfo=UTC), days=60),
            listed_at=listed, window_start=WINDOW_START, window_end=WINDOW_END,
            warmup=WARMUP,
        )
        assert not result.eligible
        assert result.exclusion.reason is ExclusionReason.INSUFFICIENT_FORWARD_WINDOW

    def test_a_seven_day_hole_is_caught_by_the_gap_rule_alone(self) -> None:
        """One long hole is ~1 % missing and passes the FRACTION rule. Both exist."""
        listed = datetime(2015, 1, 1, tzinfo=UTC)
        head = bars(start=WINDOW_START, days=300)
        tail = bars(start=WINDOW_START + timedelta(days=320), days=400)
        result = assess_asset(
            asset("GAP", "GAPUSDT"), head + tail,
            listed_at=listed, window_start=WINDOW_START, window_end=WINDOW_END,
            warmup=WARMUP,
        )
        assert not result.eligible
        assert result.exclusion.reason in (
            ExclusionReason.EXCESSIVE_GAP, ExclusionReason.EXCESSIVE_MISSING_BARS,
        )

    def test_a_duplicated_bar_is_refused_rather_than_counted(self) -> None:
        listed = datetime(2015, 1, 1, tzinfo=UTC)
        series = bars(start=WINDOW_START, days=700)
        result = assess_asset(
            asset("DUP", "DUPUSDT"), series + (series[10],),
            listed_at=listed, window_start=WINDOW_START, window_end=WINDOW_END,
            warmup=WARMUP,
        )
        assert not result.eligible
        assert result.exclusion.reason is ExclusionReason.DUPLICATE_BARS

    def test_a_malformed_bar_is_refused(self) -> None:
        listed = datetime(2015, 1, 1, tzinfo=UTC)
        series = list(bars(start=WINDOW_START, days=700))
        series[5] = DailyBar(
            open_time=series[5].open_time, open=100.0, high=1.0, low=200.0,
            close=100.0, volume=1.0,
        )
        result = assess_asset(
            asset("BAD", "BADUSDT"), tuple(series),
            listed_at=listed, window_start=WINDOW_START, window_end=WINDOW_END,
            warmup=WARMUP,
        )
        assert not result.eligible
        assert result.exclusion.reason is ExclusionReason.MALFORMED_BARS

    def test_window_bars_without_a_listing_date_are_refused(self) -> None:
        """Defaulting the listing date would credit history the asset lacks."""
        with pytest.raises(UniverseError, match="no listing date"):
            assess_asset(
                asset("X", "XUSDT"), bars(start=WINDOW_START, days=100),
                listed_at=None, window_start=WINDOW_START, window_end=WINDOW_END,
                warmup=WARMUP,
            )

    def test_an_illiquid_market_is_excluded_with_its_measured_number(self) -> None:
        listed = datetime(2015, 1, 1, tzinfo=UTC)
        result = assess_asset(
            asset("THIN", "THINUSDT"),
            bars(start=WINDOW_START, days=730, price=1.0, volume=1.0),
            listed_at=listed, window_start=WINDOW_START, window_end=WINDOW_END,
            warmup=WARMUP,
        )
        assert not result.eligible
        assert result.exclusion.reason is ExclusionReason.INSUFFICIENT_LIQUIDITY
        assert "1" in result.exclusion.detail


class TestLiquidityEvidenceCannotBeImpossible:
    def test_a_median_over_zero_observed_days_is_refused(self) -> None:
        with pytest.raises(UniverseError, match="zero observed days"):
            LiquidityEvidence(
                symbol="X", median_quote_volume=1_000_000.0, observed_days=0,
                window_start=WINDOW_START, window_end=WINDOW_END, source="x",
            )

    def test_observed_days_with_no_median_is_refused(self) -> None:
        with pytest.raises(UniverseError, match="computation that was skipped"):
            LiquidityEvidence(
                symbol="X", median_quote_volume=None, observed_days=50,
                window_start=WINDOW_START, window_end=WINDOW_END, source="x",
            )

    def test_a_negative_notional_is_refused(self) -> None:
        with pytest.raises(UniverseError, match="negative"):
            LiquidityEvidence(
                symbol="X", median_quote_volume=-1.0, observed_days=5,
                window_start=WINDOW_START, window_end=WINDOW_END, source="x",
            )

    def test_no_evidence_and_measured_illiquidity_are_different_reasons(self) -> None:
        assert (
            ExclusionReason.NO_LIQUIDITY_EVIDENCE
            is not ExclusionReason.INSUFFICIENT_LIQUIDITY
        )


class TestCoverageCannotOverstateCompleteness:
    def test_the_missing_fraction_never_goes_negative(self) -> None:
        coverage = CoverageMetrics(
            symbol="X", first_bar=WINDOW_START,
            last_bar=WINDOW_START + timedelta(days=9),
            bars_observed=50, bars_expected=10, duplicate_bars=40,
            malformed_bars=0, longest_gap_bars=0,
        )
        assert coverage.missing_fraction == 0.0

    def test_a_last_bar_before_the_first_is_refused(self) -> None:
        with pytest.raises(UniverseError, match="precedes"):
            CoverageMetrics(
                symbol="X", first_bar=WINDOW_END, last_bar=WINDOW_START,
                bars_observed=1, bars_expected=1, duplicate_bars=0,
                malformed_bars=0, longest_gap_bars=0,
            )


# ------------------------------------------------------------ survivorship ---


class TestSurvivorshipIsNeverFlattered:
    def test_a_current_only_universe_cannot_be_called_aware(self) -> None:
        reading = classify_survivorship(
            total_instruments=500, halted_instruments=0, eligible_halted=0,
            unrecoverable_gap_demonstrated=False,
        )
        assert reading.classification is SurvivorshipClass.CURRENT_SURVIVOR_ONLY
        assert not reading.classification.is_unbiased

    def test_a_demonstrated_gap_forbids_the_unbiased_label(self) -> None:
        with pytest.raises(UniverseError, match="cannot be classified SURVIVORSHIP_AWARE"):
            SurvivorshipReading(
                classification=SurvivorshipClass.SURVIVORSHIP_AWARE,
                total_instruments=100, halted_instruments=10, eligible_halted=1,
                unrecoverable_gap_demonstrated=True, evidence="x",
            )

    def test_understating_coverage_is_refused_too(self) -> None:
        with pytest.raises(UniverseError, match="not current-survivor-only"):
            SurvivorshipReading(
                classification=SurvivorshipClass.CURRENT_SURVIVOR_ONLY,
                total_instruments=100, halted_instruments=10, eligible_halted=1,
                unrecoverable_gap_demonstrated=True, evidence="x",
            )

    def test_more_halted_than_total_is_refused(self) -> None:
        with pytest.raises(UniverseError, match="two different universes"):
            classify_survivorship(
                total_instruments=10, halted_instruments=20, eligible_halted=0,
                unrecoverable_gap_demonstrated=True,
            )


# ----------------------------------------------------------------- verdict ---


def _dependence(residual: float = 0.0, raw: float = 0.5) -> DependenceSummary:
    return DependenceSummary(
        assets=38, pairs_measured=703, pairs_skipped=0,
        raw_mean_correlation=raw, raw_median_correlation=raw,
        residual_mean_correlation=residual, residual_median_correlation=residual,
        demeaning_artefact=-1 / 37, market_factor_share=0.6,
        highest_decile_correlation=raw, window_days=731, method="test",
    )


class TestNoVerdictApprovesAnything:
    @pytest.mark.parametrize("verdict", list(FeasibilityVerdict))
    def test_no_member_approves_trading_or_a_forward_test(self, verdict) -> None:
        assert verdict.is_approved_for_trading is False
        assert verdict.earns_forward_test is False
        assert verdict.says_nothing_about_the_hypothesis is True

    def test_the_assessment_itself_approves_nothing(self) -> None:
        requirement = requirement_for_effect(
            magnitude=Decimal("0.10"), scenario="independent",
            dependence=_dependence(), years_per_asset=2.0,
            admissions_per_asset_year=5.16,
        )
        assessment = decide_feasibility(
            requirements={"independent": requirement, "residual": requirement},
            eligible_assets=100_000, dependence=_dependence(),
            survivorship=classify_survivorship(
                total_instruments=100, halted_instruments=10, eligible_halted=1,
                unrecoverable_gap_demonstrated=True,
            ),
            limitations=("one",),
        )
        assert assessment.is_approved_for_trading is False
        assert assessment.earns_forward_test is False

    def test_a_missing_dependence_measurement_is_INDETERMINATE_not_INFEASIBLE(self) -> None:
        """A failed download must never read as a scientific finding."""
        blank = DependenceSummary(
            assets=0, pairs_measured=0, pairs_skipped=0,
            raw_mean_correlation=None, raw_median_correlation=None,
            residual_mean_correlation=None, residual_median_correlation=None,
            demeaning_artefact=None, market_factor_share=None,
            highest_decile_correlation=None, window_days=1, method="none",
        )
        assessment = decide_feasibility(
            requirements={}, eligible_assets=38, dependence=blank,
            survivorship=classify_survivorship(
                total_instruments=100, halted_instruments=10, eligible_halted=1,
                unrecoverable_gap_demonstrated=True,
            ),
            limitations=("one",),
        )
        assert assessment.verdict is FeasibilityVerdict.INDETERMINATE

    def test_an_assessment_with_no_limitation_is_refused(self) -> None:
        with pytest.raises(UniverseError, match="at least one limitation"):
            decide_feasibility(
                requirements={}, eligible_assets=1, dependence=_dependence(),
                survivorship=classify_survivorship(
                    total_instruments=1, halted_instruments=0, eligible_halted=0,
                    unrecoverable_gap_demonstrated=False,
                ),
                limitations=(),
            )

    def test_falling_short_of_the_INDEPENDENT_case_is_INFEASIBLE(self) -> None:
        requirement = requirement_for_effect(
            magnitude=Decimal("0.10"), scenario="independent",
            dependence=_dependence(), years_per_asset=2.0,
            admissions_per_asset_year=5.16,
        )
        assessment = decide_feasibility(
            requirements={"independent": requirement, "residual": requirement},
            eligible_assets=38, dependence=_dependence(),
            survivorship=classify_survivorship(
                total_instruments=100, halted_instruments=10, eligible_halted=1,
                unrecoverable_gap_demonstrated=True,
            ),
            limitations=("one",),
        )
        assert assessment.verdict is FeasibilityVerdict.INFEASIBLE
        assert assessment.binding_constraint == "cluster_count"


# ------------------------------------------------------- growth projections ---


class TestProjectionsAreNeverPresentedAsMeasurements:
    def test_a_row_beyond_the_measured_universe_is_marked_projected(self) -> None:
        row = growth_row(
            assets=500, observed=False, scenario="independent", correlation=0.0,
            years_per_asset=2.0, admissions_per_asset_year=5.16,
            effect=__import__(
                "fmis.universe.growth", fromlist=["effect_for"]
            ).effect_for(Decimal("0.10")),
        )
        assert row.observed is False
        assert "proj" in _rendered_marker(row)

    def test_a_row_whose_verdict_disagrees_with_its_arithmetic_is_refused(self) -> None:
        from fmis.universe.growth import GrowthRow

        with pytest.raises(UniverseError, match="not its arithmetic"):
            GrowthRow(
                assets=10, observed=True, dependence_scenario="independent",
                between_asset_correlation=0.0, effective_clusters=10.0,
                years_per_asset=2.0, admissions_per_asset_year=5.0,
                projected_admissions=100, admissions_per_effective_cluster=10.0,
                half_width=0.5, required_half_width=0.1, resolves=True,
            )

    def test_more_effective_clusters_than_assets_is_refused(self) -> None:
        from fmis.universe.growth import GrowthRow

        with pytest.raises(UniverseError, match="cannot create independent clusters"):
            GrowthRow(
                assets=10, observed=True, dependence_scenario="independent",
                between_asset_correlation=0.0, effective_clusters=50.0,
                years_per_asset=2.0, admissions_per_asset_year=5.0,
                projected_admissions=100, admissions_per_effective_cluster=2.0,
                half_width=0.5, required_half_width=0.1, resolves=False,
            )

    def test_a_saturating_correlation_makes_the_effect_unreachable_at_any_size(self) -> None:
        """**No quantity of this data suffices** is a finding, not a timeout."""
        requirement = requirement_for_effect(
            magnitude=Decimal("0.10"), scenario="raw",
            dependence=_dependence(raw=0.60), years_per_asset=2.0,
            admissions_per_asset_year=5.16,
        )
        assert requirement.reachable is False
        assert requirement.required_assets is None
        assert "saturates" in requirement.note

    def test_a_zero_rate_is_refused_rather_than_treated_as_infinite(self) -> None:
        from fmis.universe.growth import effect_for

        with pytest.raises(UniverseError, match="must both be positive"):
            growth_row(
                assets=10, observed=True, scenario="independent", correlation=0.0,
                years_per_asset=0.0, admissions_per_asset_year=5.0,
                effect=effect_for(Decimal("0.10")),
            )


def _rendered_marker(row) -> str:
    return "obs" if row.observed else "proj"


class TestThePostHocCeilingCannotMasqueradeAsPreRegistered:
    def test_it_cannot_be_constructed_as_pre_registered(self) -> None:
        with pytest.raises(UniverseError, match="may not be presented as pre-registered"):
            HorizonCeiling(
                candidate_assets=10, qualifying_assets=5, total_asset_years=10.0,
                admissions_per_asset_year=5.0, projected_admissions=50,
                required_admissions=4823, required_clusters=467,
                is_post_hoc=False, note="x",
            )

    def test_its_note_labels_itself_post_hoc(self) -> None:
        spans = [
            asset_horizon(
                asset_id=f"A{index}", listed_at=datetime(2017, 8, 1, tzinfo=UTC),
                last_bar=datetime(2026, 8, 1, tzinfo=UTC), warmup=WARMUP,
            )
            for index in range(5)
        ]
        ceiling = horizon_ceiling(
            spans, admissions_per_asset_year=5.16,
            required_admissions=4823, required_clusters=467,
        )
        assert ceiling.is_post_hoc
        assert "POST-HOC" in ceiling.note
        assert ceiling.qualifying_assets == 5

    def test_an_asset_whose_warmup_never_completes_contributes_nothing(self) -> None:
        span = asset_horizon(
            asset_id="YOUNG", listed_at=datetime(2025, 1, 1, tzinfo=UTC),
            last_bar=datetime(2026, 1, 1, tzinfo=UTC), warmup=WARMUP,
        )
        assert span.usable_years == 0.0
        assert not span.qualifies
