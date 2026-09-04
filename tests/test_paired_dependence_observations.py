"""The observation dataset: what a row is, what it refuses, and what it counts.

The most consequential assertion here is the last class. Milestone CD's whole
argument rests on rows, admissions and economic assets being **three different
numbers**, and on the row count never standing in for the sample size. Those are
asserted directly rather than left to the report's prose.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.paired_dependence.models import PairedDependenceError
from fmis.paired_dependence.observations import (
    BASE_ASSET_RULE,
    CD_QUOTE_ASSETS,
    ObservationRow,
    base_asset_of,
    dependence_concentration_of,
    dependence_coverage_of,
    dependence_overlap_of,
    rows_from_records,
)
from fmis.swing_lab.admission_preregistration import PRIMARY_HORIZON
from paired_dependence_helpers import DIGEST, panel, record, row

UNIVERSE = {"development": "primary", "validation": "primary", "holdout": "holdout"}


class TestBaseAsset:
    def test_a_usdt_pair_gives_its_base(self):
        assert base_asset_of("BTCUSDT") == "BTC"

    def test_a_numeric_prefix_survives(self):
        assert base_asset_of("1000CATUSDT") == "1000CAT"

    def test_a_cross_is_refused_rather_than_guessed(self):
        with pytest.raises(PairedDependenceError, match="ends in none of"):
            base_asset_of("ETHBTC")

    def test_a_bare_quote_is_refused(self):
        with pytest.raises(PairedDependenceError):
            base_asset_of("USDT")

    def test_an_empty_symbol_is_refused(self):
        with pytest.raises(PairedDependenceError):
            base_asset_of("")

    def test_the_rule_is_written_down_and_names_the_failure_it_prevents(self):
        assert "REFUSED" in BASE_ASSET_RULE
        assert "USDT" in CD_QUOTE_ASSETS


class TestObservationRow:
    def test_a_row_whose_difference_is_not_its_own_arithmetic_is_refused(self):
        with pytest.raises(PairedDependenceError, match="has been edited"):
            ObservationRow(
                observation_id="x", family_id="f", sample="development",
                universe="primary", symbol="BTCUSDT", base_asset="BTC",
                economic_asset="BTC", bar_index=1,
                as_of=datetime(2024, 1, 1, tzinfo=timezone.utc), direction="long",
                horizon=24, segment=None, volatility="steady", pool_size=10,
                radius_tier=0, control_draws=200, admission_forward=1.0,
                control_forward=0.0, difference=99.0,
                capture_content_digest=DIGEST, capture_captured_at=None,
            )

    def test_a_naive_timestamp_is_refused(self):
        with pytest.raises(PairedDependenceError, match="timezone-aware"):
            row(difference=1.0).__class__(
                **{**row(difference=1.0).payload(), "as_of": datetime(2024, 1, 1)}
            )

    def test_a_row_round_trips_through_its_payload(self):
        original = row(difference=0.25, symbol="ETHUSDT", bar_index=7)
        assert ObservationRow.from_payload(original.payload()) == original

    def test_the_payload_carries_every_provenance_field(self):
        payload = row(difference=1.0).payload()
        for field in (
            "observation_id", "family_id", "sample", "universe", "symbol",
            "base_asset", "economic_asset", "bar_index", "as_of", "direction",
            "horizon", "pool_size", "radius_tier", "control_draws",
            "admission_forward", "control_forward", "difference",
            "capture_content_digest",
        ):
            assert field in payload

    def test_the_block_helper_uses_the_shared_block_rule(self):
        assert row(difference=1.0, bar_index=125).block(60) == 2


class TestRowsFromRecords:
    def test_the_difference_is_ca_s_and_is_not_recomputed(self):
        rows = rows_from_records(
            [record(difference=0.4, control=1.5)],
            horizon=PRIMARY_HORIZON,
            universe_for_sample=UNIVERSE,
            capture_content_digest=DIGEST,
            capture_captured_at=None,
        )
        assert rows[0].difference == pytest.approx(0.4)
        assert rows[0].admission_forward == pytest.approx(1.9)
        assert rows[0].control_forward == pytest.approx(1.5)

    def test_the_economic_identity_is_milestone_cc_s_rule(self):
        rows = rows_from_records(
            [record(difference=0.1, symbol="BTCUSDT")],
            horizon=PRIMARY_HORIZON,
            universe_for_sample=UNIVERSE,
            capture_content_digest=DIGEST,
            capture_captured_at=None,
        )
        assert rows[0].economic_asset == "BTC"

    def test_a_sample_the_mapping_does_not_cover_is_refused(self):
        with pytest.raises(PairedDependenceError, match="no captured universe"):
            rows_from_records(
                [record(difference=0.1, sample="nowhere")],
                horizon=PRIMARY_HORIZON,
                universe_for_sample=UNIVERSE,
                capture_content_digest=DIGEST,
                capture_captured_at=None,
            )

    def test_a_missing_horizon_is_refused(self):
        with pytest.raises(PairedDependenceError, match="holds no horizon"):
            rows_from_records(
                [record(difference=0.1)],
                horizon=999,
                universe_for_sample=UNIVERSE,
                capture_content_digest=DIGEST,
                capture_captured_at=None,
            )

    def test_a_duplicated_observation_is_refused(self):
        duplicate = record(difference=0.1, symbol="BTCUSDT", bar_index=3)
        with pytest.raises(PairedDependenceError, match="appears twice"):
            rows_from_records(
                [duplicate, duplicate],
                horizon=PRIMARY_HORIZON,
                universe_for_sample=UNIVERSE,
                capture_content_digest=DIGEST,
                capture_captured_at=None,
            )

    def test_rows_come_back_in_a_stable_order(self):
        records = [
            record(difference=0.1, symbol="ETHUSDT", bar_index=5),
            record(difference=0.2, symbol="BTCUSDT", bar_index=3),
        ]
        first = rows_from_records(
            records, horizon=PRIMARY_HORIZON, universe_for_sample=UNIVERSE,
            capture_content_digest=DIGEST, capture_captured_at=None,
        )
        second = rows_from_records(
            list(reversed(records)), horizon=PRIMARY_HORIZON,
            universe_for_sample=UNIVERSE, capture_content_digest=DIGEST,
            capture_captured_at=None,
        )
        assert [item.observation_id for item in first] == [
            item.observation_id for item in second
        ]


class TestTheFiveCountsAreFive:
    def test_rows_admissions_and_assets_are_different_numbers(self):
        rows = []
        for family in ("f1", "f2", "f3"):
            for asset in range(4):
                for bar in range(3):
                    rows.append(
                        row(
                            difference=0.1,
                            symbol=f"A{asset}USDT",
                            bar_index=bar * 60,
                            family_id=family,
                        )
                    )
        coverage = dependence_coverage_of(rows, block_bars=60)
        assert coverage["rows"] == 36
        assert coverage["admissions"] == 12
        assert coverage["economic_assets"] == 4
        assert coverage["families"] == 3

    def test_a_wrapped_symbol_does_not_add_an_economic_asset(self):
        rows = [
            row(difference=0.1, symbol="BTCUSDT", bar_index=0),
            row(
                difference=0.2,
                symbol="WBTCUSDT",
                bar_index=60,
                economic_asset="BTC",
            ),
        ]
        coverage = dependence_coverage_of(rows, block_bars=60)
        assert coverage["provider_symbols"] == 2
        assert coverage["economic_assets"] == 1
        assert coverage["symbols_per_economic_asset"] == 2.0

    def test_informative_blocks_count_only_those_with_two_or_more_assets(self):
        rows = [
            row(difference=0.1, symbol="AAAUSDT", bar_index=0),
            row(difference=0.2, symbol="BBBUSDT", bar_index=1),
            row(difference=0.3, symbol="AAAUSDT", bar_index=60),
        ]
        coverage = dependence_coverage_of(rows, block_bars=60)
        assert coverage["blocks"] == 2
        assert coverage["blocks_with_two_or_more_assets"] == 1

    def test_possible_pairs_is_over_economic_assets_not_symbols(self):
        rows = [
            row(difference=0.1, symbol="BTCUSDT", bar_index=0),
            row(difference=0.1, symbol="WBTCUSDT", bar_index=1, economic_asset="BTC"),
            row(difference=0.1, symbol="ETHUSDT", bar_index=2),
        ]
        assert dependence_coverage_of(rows, block_bars=60)["possible_asset_pairs"] == 1

    def test_an_empty_panel_reports_absences_not_zeros(self):
        coverage = dependence_coverage_of([], block_bars=60)
        assert coverage["observations_per_asset_mean"] is None
        assert coverage["symbols_per_economic_asset"] is None


class TestConcentration:
    def test_the_largest_share_is_over_absolute_contributions(self):
        rows = [
            row(difference=3.0, symbol="AAAUSDT", bar_index=0),
            row(difference=-1.0, symbol="BBBUSDT", bar_index=1),
        ]
        assert dependence_concentration_of(rows)["largest_share"] == pytest.approx(0.75)

    def test_a_panel_of_zeros_has_no_share_rather_than_a_zero_one(self):
        rows = [
            row(difference=0.0, symbol="AAAUSDT", bar_index=0),
            row(difference=0.0, symbol="BBBUSDT", bar_index=1),
        ]
        assert dependence_concentration_of(rows)["largest_share"] is None

    def test_shares_are_ranked_and_carry_their_observation_counts(self):
        rows = panel(assets=3, blocks=4, level=1.0)
        shares = dependence_concentration_of(rows)["shares"]
        values = [item["share"] for item in shares]
        assert values == sorted(values, reverse=True)
        assert sum(item["observations"] for item in shares) == len(rows)


class TestOverlap:
    def test_admissions_inside_the_window_are_counted(self):
        rows = [
            row(difference=0.1, symbol="AAAUSDT", bar_index=0),
            row(difference=0.1, symbol="AAAUSDT", bar_index=10),
            row(difference=0.1, symbol="AAAUSDT", bar_index=500),
        ]
        result = dependence_overlap_of(rows, evaluation_window_bars=60)["by_family_sample"][0]
        assert result["observations"] == 3
        assert result["within_window_of_another"] == 2

    def test_admissions_on_different_assets_never_overlap_each_other(self):
        rows = [
            row(difference=0.1, symbol="AAAUSDT", bar_index=0),
            row(difference=0.1, symbol="BBBUSDT", bar_index=1),
        ]
        result = dependence_overlap_of(rows, evaluation_window_bars=60)["by_family_sample"][0]
        assert result["within_window_of_another"] == 0

    def test_it_is_counted_per_family_and_never_pooled(self):
        rows = [
            row(difference=0.1, symbol="AAAUSDT", bar_index=0, family_id="f1"),
            row(difference=0.1, symbol="AAAUSDT", bar_index=10, family_id="f1"),
            row(difference=0.1, symbol="AAAUSDT", bar_index=0, family_id="f2"),
        ]
        rows_out = dependence_overlap_of(rows, evaluation_window_bars=60)["by_family_sample"]
        assert len(rows_out) == 2
        assert {item["family_id"] for item in rows_out} == {"f1", "f2"}

    def test_a_zero_window_is_refused(self):
        with pytest.raises(PairedDependenceError):
            dependence_overlap_of([], evaluation_window_bars=0)


class TestMutationSurvivorRegressions:
    """Regressions added after a rule-level mutation probe survived."""

    def test_a_wrapped_symbol_collapses_onto_the_exposure_it_represents(self):
        """Kills: `skip the economic identity collapse`.

        The earlier identity test used `BTCUSDT`, whose base asset and economic
        identity are the same string — so it could not tell `economic_asset_id`
        from a no-op. `WBTC` and `VEN` are the cases where they differ, and they
        are exactly the cases that decide whether a cluster count is inflated.
        """
        rows = rows_from_records(
            [
                record(difference=0.1, symbol="WBTCUSDT", bar_index=1),
                record(difference=0.2, symbol="VENUSDT", bar_index=2),
                record(difference=0.3, symbol="BTCUSDT", bar_index=3),
            ],
            horizon=PRIMARY_HORIZON,
            universe_for_sample=UNIVERSE,
            capture_content_digest=DIGEST,
            capture_captured_at=None,
        )
        by_symbol = {item.symbol: item for item in rows}
        assert by_symbol["WBTCUSDT"].base_asset == "WBTC"
        assert by_symbol["WBTCUSDT"].economic_asset == "BTC"
        assert by_symbol["VENUSDT"].base_asset == "VEN"
        assert by_symbol["VENUSDT"].economic_asset == "VET"
        # Three provider symbols; two economic exposures. A universe keyed on the
        # symbol would report three independent clusters where there are two.
        assert len({item.symbol for item in rows}) == 3
        assert len({item.economic_asset for item in rows}) == 2

    def test_and_the_collapse_reaches_the_coverage_count(self):
        rows = rows_from_records(
            [
                record(difference=0.1, symbol="WBTCUSDT", bar_index=1),
                record(difference=0.3, symbol="BTCUSDT", bar_index=100),
            ],
            horizon=PRIMARY_HORIZON,
            universe_for_sample=UNIVERSE,
            capture_content_digest=DIGEST,
            capture_captured_at=None,
        )
        coverage = dependence_coverage_of(rows, block_bars=60)
        assert coverage["provider_symbols"] == 2
        assert coverage["economic_assets"] == 1
        assert coverage["possible_asset_pairs"] == 0
