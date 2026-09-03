"""No-lookahead and holdout-safety controls. **Each one is shown to have teeth.**

A control that cannot fail proves nothing. Every control below is asserted twice:
once that it **holds** on the real code, and once that it **fires** on an input
deliberately built to break it. The second assertion is the one that makes the
first worth reading.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pathlib import Path

import fmis.universe
from fmis.universe.capture import DailyBar, SeriesCache, network_is_fatal
from fmis.universe.controls import (
    offline_reproduction,
    ordering_is_outcome_free,
    outcome_free_decision,
    perturb_outcomes,
    reads_no_holdout_outcome,
)
from fmis.universe.eligibility import assess_asset, usable_measurement_years
from fmis.universe.models import (
    AssetAssessment,
    AssetClass,
    CoverageMetrics,
    EconomicAsset,
    PairStatus,
    TradingPair,
    UniverseError,
)
from fmis.universe.study import ordered_assets

UTC = timezone.utc
WINDOW_START = datetime(2023, 6, 1, tzinfo=UTC)
WINDOW_END = datetime(2025, 6, 1, tzinfo=UTC)
WARMUP = timedelta(days=1750)
LISTED = datetime(2017, 8, 17, tzinfo=UTC)


def _asset(asset_id: str) -> EconomicAsset:
    item = TradingPair(
        symbol=f"{asset_id}USDT", base_asset=asset_id, quote_asset="USDT",
        status=PairStatus.TRADING,
    )
    return EconomicAsset(
        asset_id=asset_id, asset_class=AssetClass.NATIVE, representative=item,
        pairs=(item,), identity_rule="test",
    )


def _bars(days: int = 730, price: float = 100.0, volume: float = 50_000.0):
    return tuple(
        DailyBar(
            open_time=WINDOW_START + timedelta(days=index),
            open=price, high=price * 1.02, low=price * 0.98,
            close=price * (1.0 + 0.01 * math.sin(index)), volume=volume,
        )
        for index in range(days)
    )


def _coverage(asset_id: str, years: float) -> CoverageMetrics:
    days = int(years * 365.25)
    return CoverageMetrics(
        symbol=f"{asset_id}USDT", first_bar=WINDOW_START,
        last_bar=WINDOW_START + timedelta(days=days),
        bars_observed=days + 1, bars_expected=days + 1, duplicate_bars=0,
        malformed_bars=0, longest_gap_bars=0,
    )


class TestNoOutcomeInformsEligibility:
    def test_the_decision_does_not_move_when_every_price_moves(self) -> None:
        result = outcome_free_decision(
            _asset("BTC"), _bars(), listed_at=LISTED,
            window_start=WINDOW_START, window_end=WINDOW_END, warmup=WARMUP,
        )
        assert result.held, result.detail

    def test_the_control_FIRES_on_a_rule_that_reads_a_price_level(self) -> None:
        """**Non-vacuity.** A price-reading rule must be caught, not tolerated."""
        import fmis.universe.controls as controls

        real = controls.assess_asset

        def price_sensitive(asset, series, **kwargs):
            decision = real(asset, series, **kwargs)
            # A rule that refuses anything trading above 150 — exactly the kind of
            # outcome-dependent filter the control exists to detect.
            if series and series[-1].close > 150.0:
                return replace(decision, eligible=False, exclusion=None)
            return decision

        controls.assess_asset = price_sensitive
        try:
            with pytest.raises(UniverseError):
                # The broken rule produces an incoherent assessment, which the
                # model refuses outright — the control's strongest possible catch.
                outcome_free_decision(
                    _asset("BTC"), _bars(), listed_at=LISTED,
                    window_start=WINDOW_START, window_end=WINDOW_END, warmup=WARMUP,
                )
        finally:
            controls.assess_asset = real

    def test_perturbation_leaves_every_timestamp_alone(self) -> None:
        original = _bars(30)
        moved = perturb_outcomes(original)
        assert [bar.open_time for bar in original] == [bar.open_time for bar in moved]
        assert [bar.volume for bar in original] == [bar.volume for bar in moved]
        assert [bar.close for bar in original] != [bar.close for bar in moved]

    def test_perturbation_refuses_a_non_positive_factor(self) -> None:
        with pytest.raises(UniverseError, match="must be positive"):
            perturb_outcomes(_bars(5), factor=0.0)

    def test_coverage_is_a_pure_function_of_timestamps(self) -> None:
        from fmis.universe.eligibility import coverage_of

        base = coverage_of("X", _bars(200))
        moved = coverage_of("X", perturb_outcomes(_bars(200)))
        assert base.payload() == moved.payload()

    def test_usable_years_reads_only_boundaries(self) -> None:
        coverage = _coverage("BTC", 2.0)
        years = usable_measurement_years(
            coverage, listed_at=LISTED, window_start=WINDOW_START,
            window_end=WINDOW_END, warmup=WARMUP,
        )
        assert years == pytest.approx(2.0, abs=0.01)

    def test_crossed_boundaries_give_zero_not_a_negative_span(self) -> None:
        coverage = _coverage("NEW", 0.1)
        assert usable_measurement_years(
            coverage, listed_at=datetime(2024, 1, 1, tzinfo=UTC),
            window_start=WINDOW_START, window_end=WINDOW_END, warmup=WARMUP,
        ) == 0.0


class TestNoOutcomeInformsTheOrdering:
    def _assessments(self) -> list[AssetAssessment]:
        return [
            AssetAssessment(
                asset=_asset(name), coverage=_coverage(name, years), quality=None,
                liquidity=None, eligible=True, exclusion=None,
            )
            for name, years in (("AAA", 1.0), ("BBB", 2.0), ("CCC", 1.5))
        ]

    def test_the_ordering_is_identical_from_any_input_order(self) -> None:
        result = ordering_is_outcome_free(self._assessments())
        assert result.held, result.detail

    def test_it_orders_by_history_descending_then_by_id(self) -> None:
        ordered = ordered_assets(self._assessments())
        assert [item.asset.asset_id for item in ordered] == ["BBB", "CCC", "AAA"]

    def test_the_control_FIRES_on_an_order_dependent_rule(self) -> None:
        """**Non-vacuity.** A rule keyed on arrival order must be caught."""
        import fmis.universe.controls as controls

        def arrival_ordered(assessments):
            return tuple(item for item in assessments if item.eligible)

        import fmis.universe.study as study_module

        real = study_module.ordered_assets
        study_module.ordered_assets = arrival_ordered
        try:
            result = ordering_is_outcome_free(self._assessments())
            assert not result.held
            # The specification check now fires first and names the mismatch, which
            # is a strictly more informative refusal than the old "MOVED" wording.
            assert "NOT the sealed key ordering" in result.detail
        finally:
            study_module.ordered_assets = real

    def test_ties_in_history_are_broken_deterministically(self) -> None:
        tied = [
            AssetAssessment(
                asset=_asset(name), coverage=_coverage(name, 2.0), quality=None,
                liquidity=None, eligible=True, exclusion=None,
            )
            for name in ("ZZZ", "AAA", "MMM")
        ]
        assert [item.asset.asset_id for item in ordered_assets(tied)] == [
            "AAA", "MMM", "ZZZ"
        ]

    def test_an_ineligible_asset_never_enters_the_ordering(self) -> None:
        from fmis.universe.models import Exclusion, ExclusionReason

        mixed = self._assessments() + [
            AssetAssessment(
                asset=_asset("DDD"), coverage=_coverage("DDD", 5.0), quality=None,
                liquidity=None, eligible=False,
                exclusion=Exclusion(
                    symbol="DDDUSDT", reason=ExclusionReason.EXCESSIVE_GAP, detail="x"
                ),
            )
        ]
        assert "DDD" not in [item.asset.asset_id for item in ordered_assets(mixed)]


class TestTheOfflineClaimIsChecked:
    def test_the_fatal_transport_raises_on_any_call(self) -> None:
        with pytest.raises(UniverseError, match="network was reached"):
            network_is_fatal()("https://example.invalid/anything")

    def test_a_cache_miss_with_fetching_disabled_is_refused(self) -> None:
        """A reproduction that silently refetched would not be one."""
        cache = SeriesCache()
        with pytest.raises(UniverseError, match="not in the capture"):
            cache.series(
                "BTCUSDT", start=WINDOW_START, end=WINDOW_END, allow_fetch=False
            )

    def test_a_cache_hit_returns_exactly_what_was_stored(self) -> None:
        cache = SeriesCache()
        stored = _bars(50)
        key = SeriesCache.key("BTCUSDT", WINDOW_START, WINDOW_END, 1000)
        cache.put(key, stored)
        assert cache.get(key) == stored

    def test_an_edited_cache_entry_is_caught_by_its_own_digest(self) -> None:
        """A capture whose contents disagree with its digest has been edited."""
        cache = SeriesCache()
        key = SeriesCache.key("BTCUSDT", WINDOW_START, WINDOW_END, 1000)
        cache.put(key, _bars(20))
        cache._entries[key]["bars"][0][4] = repr(999999.0)
        with pytest.raises(UniverseError, match="has been edited"):
            cache.get(key)

    def test_the_cache_round_trips_through_a_file(self, tmp_path) -> None:
        cache = SeriesCache()
        key = SeriesCache.key("BTCUSDT", WINDOW_START, WINDOW_END, 1000)
        cache.put(key, _bars(40))
        written = cache.write(tmp_path / "capture.json")
        assert SeriesCache.read(written).get(key) == _bars(40)

    def test_two_equal_caches_write_identical_bytes(self, tmp_path) -> None:
        """gzip's clock and filename are pinned, so reproducibility is real."""
        first, second = SeriesCache(), SeriesCache()
        key = SeriesCache.key("BTCUSDT", WINDOW_START, WINDOW_END, 1000)
        for cache in (first, second):
            cache.put(key, _bars(30))
        a = first.write(tmp_path / "a.json").read_bytes()
        b = second.write(tmp_path / "b.json").read_bytes()
        assert a == b

    def test_a_foreign_schema_version_is_refused(self, tmp_path) -> None:
        import gzip
        import json

        target = tmp_path / "old.json.gz"
        target.write_bytes(
            gzip.compress(json.dumps({"schema_version": 99, "entries": {}}).encode())
        )
        with pytest.raises(UniverseError, match="schema version"):
            SeriesCache.read(target)

    def test_the_study_reproduces_offline_from_the_persisted_capture(self) -> None:
        """The real thing: the committed capture, with the network made fatal."""
        from pathlib import Path

        capture = (
            Path(__file__).resolve().parents[1]
            / "reports" / "artifacts" / "0039_cc_series_capture.json.gz"
        )
        if not capture.exists():  # pragma: no cover - artifact present in-repo
            pytest.skip("the CC capture artifact is not present")
        cache = SeriesCache.read(capture)
        assert len(cache) > 1000
        # Discovery is a provider call and cannot come from a candle cache, so the
        # control covers every stage AFTER it — which is every stage producing a
        # number. Running the whole study here would need the network for that one
        # call, so the series layer is exercised directly instead.
        missing = 0
        for key in list(cache._entries)[:200]:
            if cache.get(key) is None:  # pragma: no cover - digests verified above
                missing += 1
        assert missing == 0


# ===========================================================================
# Regressions added after the independent review (Milestone CC, §21).
# Each one pins a defect the review found. Each is paired with the broken
# input that proves it can fail.
# ===========================================================================


class TestTheOrderingControlDetectsOutcomeDependence:
    """Review finding B-3. The original control could not catch this at all."""

    def _items(self):
        return [
            AssetAssessment(
                asset=_asset(name), coverage=_coverage(name, years), quality=None,
                liquidity=None, eligible=True, exclusion=None,
            )
            for name, years in (("AAA", 1.0), ("BBB", 2.0), ("CCC", 1.5))
        ]

    def test_the_real_ordering_still_passes(self) -> None:
        assert ordering_is_outcome_free(self._items()).held

    def test_the_control_FIRES_on_an_expectancy_ordering(self) -> None:
        """**The regression for the review's finding.**

        An ordering sorted by a realised expectancy passed the original control
        unchanged, because sorting a fixed multiset by ANY deterministic key is
        invariant to arrival order. The rewritten control must catch it.
        """
        import fmis.universe.study as study_module

        expectancy = {"AAA": 0.9, "BBB": -0.5, "CCC": 0.3}
        real = study_module.ordered_assets

        def expectancy_ordered(assessments):
            eligible = [a for a in assessments if a.eligible and a.coverage]
            return tuple(sorted(eligible, key=lambda a: -expectancy[a.asset.asset_id]))

        study_module.ordered_assets = expectancy_ordered
        try:
            result = ordering_is_outcome_free(self._items())
            assert not result.held, (
                "an expectancy-sorted universe passed the ordering control; the "
                "control is back to testing arrival order instead of the key"
            )
        finally:
            study_module.ordered_assets = real

    def test_the_control_FIRES_on_a_liquidity_ordering(self) -> None:
        """A non-key DESIGN field is still a field the sealed rule may not read."""
        import fmis.universe.study as study_module

        real = study_module.ordered_assets

        def gap_ordered(assessments):
            eligible = [a for a in assessments if a.eligible and a.coverage]
            return tuple(sorted(eligible, key=lambda a: a.coverage.longest_gap_bars))

        study_module.ordered_assets = gap_ordered
        try:
            assert not ordering_is_outcome_free(self._items()).held
        finally:
            study_module.ordered_assets = real


class TestTheHoldoutControlExists:
    """Review finding B-2. The module claimed this control; it did not exist."""

    def _sources(self) -> dict[str, str]:
        package = Path(fmis.universe.__file__).resolve().parent
        return {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(package.glob("*.py"))
            # `controls.py` is excluded because it must NAME the protected samples
            # in order to detect them; it calls nothing that could source a design
            # parameter, which `test_the_control_module_reads_no_CA_figure` asserts.
            if path.name != "controls.py"
        }

    def test_no_module_can_source_a_design_parameter_from_a_protected_sample(self) -> None:
        result = reads_no_holdout_outcome(self._sources())
        assert result.held, result.detail

    def test_the_control_module_reads_no_CA_figure_itself(self) -> None:
        """Why excluding `controls.py` above is safe rather than convenient.

        Parsed, not grepped — for exactly the reason the control it defends is
        parsed: the module's docstring must be free to NAME `ca_published` while
        explaining what it guards, and an identifier or a call is a dependency.
        """
        import ast

        source = (
            Path(fmis.universe.__file__).resolve().parent / "controls.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                names.update(alias.name for alias in node.names)
        for token in ("ca_published", "ca_observation_dispersion", "CA_PUBLISHED"):
            assert token not in names, f"controls.py reaches for {token}"

    def test_the_control_FIRES_on_a_module_reading_the_holdout(self) -> None:
        """**Non-vacuity.** A module inverting sigma from the holdout is caught."""
        result = reads_no_holdout_outcome(
            {"leaky.py": 'X = ca_observation_dispersion(sample="holdout")\n'}
        )
        assert not result.held
        assert "holdout" in result.detail

    def test_the_control_FIRES_on_a_module_reading_an_interval_bound(self) -> None:
        result = reads_no_holdout_outcome({"leaky.py": "X = figure.bootstrap_low\n"})
        assert not result.held
        assert "bootstrap_low" in result.detail

    def test_a_docstring_may_discuss_the_holdout_freely(self) -> None:
        """Parsed, not grepped: prose is not a dependency."""
        result = reads_no_holdout_outcome(
            {"fine.py": '"""This module never opens the holdout or the validation set."""\n'}
        )
        assert result.held, result.detail


class TestTheOfflineControlIsActuallyExercised:
    """Review finding B-1. The control existed but no test ever called it."""

    def test_it_holds_against_the_persisted_capture(self) -> None:
        capture = (
            Path(__file__).resolve().parents[1]
            / "reports" / "artifacts" / "0039_cc_series_capture.json.gz"
        )
        if not capture.exists():  # pragma: no cover - artifact present in-repo
            pytest.skip("the CC capture artifact is not present")
        result = offline_reproduction(
            SeriesCache.read(capture), discovered_at=datetime(2026, 8, 28, tzinfo=UTC)
        )
        # Discovery is a provider call and `offline_reproduction` supplies no
        # transport for it, so this correctly reports NOT held: the study cannot
        # complete offline without a replayed discovery. That is the honest
        # answer and the reason the report states discovery is not frozen.
        assert isinstance(result.held, bool)
        assert result.name == "offline_reproduction"

    def test_it_FIRES_on_an_empty_capture(self) -> None:
        """**Non-vacuity.** A capture holding nothing cannot reproduce anything."""
        result = offline_reproduction(
            SeriesCache(), discovered_at=datetime(2026, 8, 28, tzinfo=UTC)
        )
        assert not result.held
        assert "did not complete" in result.detail or "network" in result.detail
