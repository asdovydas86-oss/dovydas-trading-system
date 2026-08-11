"""Milestone BC — corrected research windows and counterfactual policy replay.

Fully deterministic and network-free. No test derives its expected value by
calling the production helper it is checking; every boundary expectation is
reasoned by hand from the fixture's own construction.

The synthetic dataset is deliberately built so the derived warm-up requirement
is *exactly* satisfied at ``measurement_start`` and not one bar more — which is
what makes the off-by-one tests in `TestBoundaries` mean something.
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

from fmis.features.types import BaseFeature, FeatureCategory, FeatureResult
from fmis.market_structure import required_candles
from fmis.pipeline.multi_timeframe import DEFAULT_TIMEFRAMES, TimeframeRole
from fmis.providers.binance import HttpResponse
from fmis.swing_setup.backtest_models import OutcomeStatus, SetupOutcome
from fmis.swing_setup.backtest_replay import (
    build_replay_transport,
    prepare_replay_index,
    to_epoch_ms,
)
from fmis.swing_setup.models import Direction, SetupState
from fmis.swing_setup.research_compare import (
    compare_variant,
    post_filter_comparison,
    post_filter_keep,
)
from fmis.swing_setup.research_harness import (
    DEFAULT_IDENTITY_PRIMING_BARS,
    DEFAULT_VARIANT_MAX_AGES,
    build_segments,
    fetch_research_dataset,
    run_research_study,
    run_research_variant,
)
from fmis.swing_setup.research_identity import OpportunityTracker, opportunity_key
from fmis.swing_setup.research_metrics import (
    compute_research_metrics,
    confirmation_records,
    first_confirmations,
)
from fmis.swing_setup.research_models import (
    PRODUCTION_BASELINE_VARIANT,
    AvailabilityReport,
    ConfirmationRecord,
    PostFilterComparison,
    ResearchError,
    ResearchObservation,
    ResearchPolicyVariant,
    ResearchWindow,
    SeriesAvailability,
    TemporalSegment,
    VariantComparison,
    WarmupComponent,
    RoleWarmup,
    WarmupRequirement,
    interval_duration,
)
from fmis.swing_setup.research_render import (
    render_availability_report,
    render_research_report,
)
from fmis.swing_setup.research_warmup import (
    derive_warmup,
    feature_warmup_bars,
    probe_availability,
    required_from_by_interval,
)
from tests.test_swing_setup_backtest import (
    _CLOSE_TIME_INDEX,
    _FOUR_HOURS_MS,
    _OPEN_TIME_INDEX,
    mirrored_rows,
    resampled_rows,
    zigzag_rows,
)

_UTC = timezone.utc
_BASE = datetime(2024, 1, 1, tzinfo=_UTC)
_FOUR_HOURS = timedelta(hours=4)

# ---------------------------------------------------------------- fixture geometry

#: Bars per period in the synthetic resampling — the same 6/42 the AV integration
#: fixture uses, so one 4H master path yields genuinely correlated 1d and 1w roles.
_BARS_PER_DAY = 6
_BARS_PER_WEEK = 42

#: The research limit these tests run at. 200 rather than the harness default of
#: 250 so that EMA(200) — a real production dependency — is the binding warm-up
#: component, which keeps the synthetic dataset to a size a test suite can build.
_TEST_LIMIT = 200

#: With `_TEST_LIMIT`, every role needs 200 closed candles. The weekly role binds:
#: 200 weekly candles is 200 * 42 = 8400 four-hour bars. The identity-priming
#: replay runs before that and must be equally warm, so the fixture carries the
#: priming bars on top — which makes the weekly series reach back to exactly
#: `_BASE` and not one bar further, so an off-by-one in the derivation shows up
#: as an availability failure rather than as a quietly shorter window.
_WARM_BARS = 200 * _BARS_PER_WEEK + DEFAULT_IDENTITY_PRIMING_BARS
_MEASURED_BARS = 300
_TAIL_BARS = 60
_TOTAL_BARS = _WARM_BARS + _MEASURED_BARS + _TAIL_BARS + 20

MEASUREMENT_START = _BASE + _WARM_BARS * _FOUR_HOURS
MEASUREMENT_END = MEASUREMENT_START + _MEASURED_BARS * _FOUR_HOURS
TAIL_END = MEASUREMENT_END + _TAIL_BARS * _FOUR_HOURS
RUN_AT = datetime(2030, 1, 1, tzinfo=_UTC)


#: The bar at which the synthetic path's secular drift reverses sign. Chosen so
#: the *weekly* regime completes its turn inside the measurement window rather
#: than before it: a monotonic path produces one endless directional run, one
#: opportunity, and therefore a fixture that cannot exercise a second
#: confirmation, a direction flip, or a deferred re-confirmation at all. It is a
#: property of the fixture, fixed once, and no assertion below reads a
#: profitability number from it.
_DRIFT_FLIP_BAR = 7900
_DRIFT_PER_BAR = 0.15


def _reversing_rows(count: int) -> list[list]:
    """A price path that trends up, then down, continuously in price.

    Two `zigzag_rows` paths joined at `_DRIFT_FLIP_BAR`, the second starting from
    the first's last close so the join introduces no gap candle. The reversal is
    what gives the weekly regime something to change its mind about, which is
    what gives this fixture more than one opportunity.
    """
    first = zigzag_rows(
        _DRIFT_FLIP_BAR,
        start_ms=to_epoch_ms(_BASE),
        interval_ms=_FOUR_HOURS_MS,
        base=100.0,
        linear_drift_per_bar=_DRIFT_PER_BAR,
    )
    second = zigzag_rows(
        count - _DRIFT_FLIP_BAR,
        start_ms=to_epoch_ms(_BASE) + _DRIFT_FLIP_BAR * _FOUR_HOURS_MS,
        interval_ms=_FOUR_HOURS_MS,
        base=float(first[-1][4]),
        linear_drift_per_bar=-_DRIFT_PER_BAR,
    )
    return first + second


def _three_role_rows(*, mirror: bool = False, count: int = _TOTAL_BARS) -> dict[str, list[list]]:
    rows_4h = _reversing_rows(count)
    rows_1d = resampled_rows(rows_4h, bars_per_period=_BARS_PER_DAY)
    rows_1w = resampled_rows(rows_4h, bars_per_period=_BARS_PER_WEEK)
    if mirror:
        rows_4h = mirrored_rows(rows_4h)
        rows_1d = mirrored_rows(rows_1d)
        rows_1w = mirrored_rows(rows_1w)
    return {"4h": rows_4h, "1d": rows_1d, "1w": rows_1w}


def _cache_for(symbols_rows: dict[str, dict[str, list[list]]]) -> dict[tuple[str, str], list[list]]:
    return {
        (symbol, interval): rows
        for symbol, by_interval in symbols_rows.items()
        for interval, rows in by_interval.items()
    }


def binance_like_transport(cache: dict[tuple[str, str], list[list]]):
    """A `Transport` that answers the way the real endpoint does, including "latest".

    The AV test fake honours ``startTime``/``endTime``/``limit`` but, given a
    bare ``limit``, returns the *first* rows. The real endpoint returns the most
    recent ones, and `probe_availability` asks exactly that question to find a
    series' newest candle — so a fake that gets it backwards would make the
    availability probe pass for the wrong reason.
    """

    def _transport(url: str) -> HttpResponse:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        symbol = query.get("symbol", [""])[0]
        interval = query.get("interval", [""])[0]
        rows = cache.get((symbol, interval))
        if rows is None:
            return HttpResponse(
                status=400, body=json.dumps({"code": -1121, "msg": "Invalid symbol."}).encode()
            )
        start_ms = int(query["startTime"][0]) if "startTime" in query else None
        end_ms = int(query["endTime"][0]) if "endTime" in query else None
        limit = int(query["limit"][0]) if "limit" in query else 500
        filtered = [
            row
            for row in rows
            if (start_ms is None or row[_OPEN_TIME_INDEX] >= start_ms)
            and (end_ms is None or row[_CLOSE_TIME_INDEX] <= end_ms)
        ]
        sliced = filtered[:limit] if start_ms is not None else filtered[-limit:]
        return HttpResponse(status=200, body=json.dumps(sliced).encode())

    return _transport


def _study(
    symbols=("BTCUSDT",),
    *,
    cache=None,
    variant_max_ages=(2,),
    measurement_end=MEASUREMENT_END,
    **kwargs,
):
    if cache is None:
        cache = _cache_for({symbol: _three_role_rows() for symbol in symbols})
    return run_research_study(
        list(symbols),
        measurement_start=MEASUREMENT_START,
        measurement_end=measurement_end,
        run_at=RUN_AT,
        variant_max_ages=variant_max_ages,
        limit=_TEST_LIMIT,
        evaluation_window_bars=_TAIL_BARS,
        transport=binance_like_transport(cache),
        **kwargs,
    )


@pytest.fixture(scope="module")
def single_symbol_cache() -> dict[tuple[str, str], list[list]]:
    return _cache_for({"BTCUSDT": _three_role_rows()})


@pytest.fixture(scope="module")
def baseline_study(single_symbol_cache):
    return _study(cache=single_symbol_cache, variant_max_ages=(10, 1, 0))


# ===================================== models =====================================


class TestResearchWindow:
    def _window(self, **overrides) -> ResearchWindow:
        fields = dict(
            warmup_start=_BASE,
            measurement_start=MEASUREMENT_START,
            measurement_end=MEASUREMENT_END,
            outcome_tail_end=TAIL_END,
        )
        fields.update(overrides)
        return ResearchWindow(**fields)

    def test_measurement_is_half_open_at_both_edges(self) -> None:
        window = self._window()
        assert window.is_measured(MEASUREMENT_START)
        assert window.is_measured(MEASUREMENT_END - timedelta(milliseconds=1))
        assert not window.is_measured(MEASUREMENT_END)
        assert not window.is_measured(MEASUREMENT_START - timedelta(milliseconds=1))

    def test_the_three_phases_partition_time(self) -> None:
        window = self._window()
        for instant in (
            _BASE, MEASUREMENT_START - timedelta(days=1), MEASUREMENT_START,
            MEASUREMENT_END, TAIL_END,
        ):
            phases = [window.is_warmup(instant), window.is_measured(instant), window.is_tail(instant)]
            assert sum(phases) == 1, instant

    def test_a_window_with_no_warmup_prefix_is_unrepresentable(self) -> None:
        with pytest.raises(ResearchError, match="warmup_start"):
            self._window(warmup_start=MEASUREMENT_START)

    def test_naive_datetimes_rejected(self) -> None:
        with pytest.raises(ResearchError, match="timezone-aware"):
            self._window(measurement_start=MEASUREMENT_START.replace(tzinfo=None))

    def test_tail_may_not_precede_measurement_end(self) -> None:
        with pytest.raises(ResearchError, match="outcome_tail_end"):
            self._window(outcome_tail_end=MEASUREMENT_END - timedelta(days=1))

    def test_zero_length_measurement_rejected(self) -> None:
        with pytest.raises(ResearchError, match="measurement_start"):
            self._window(measurement_end=MEASUREMENT_START)

    def test_durations_are_the_differences(self) -> None:
        window = self._window()
        assert window.warmup_duration == MEASUREMENT_START - _BASE
        assert window.measurement_duration == MEASUREMENT_END - MEASUREMENT_START
        assert window.tail_duration == TAIL_END - MEASUREMENT_END


class TestTemporalSegment:
    def test_contains_is_half_open(self) -> None:
        segment = TemporalSegment(label="s", start=_BASE, end=_BASE + timedelta(days=1))
        assert segment.contains(_BASE)
        assert not segment.contains(_BASE + timedelta(days=1))

    def test_inverted_bounds_rejected(self) -> None:
        with pytest.raises(ResearchError):
            TemporalSegment(label="s", start=_BASE + timedelta(days=1), end=_BASE)


class TestResearchPolicyVariant:
    def test_production_baseline_carries_the_production_policy_id(self) -> None:
        from fmis.swing_setup.policy import CONFIRMATION_LOOKBACK_BARS, SETUP_POLICY_ID

        assert PRODUCTION_BASELINE_VARIANT.is_production_baseline
        assert PRODUCTION_BASELINE_VARIANT.policy_id == SETUP_POLICY_ID
        assert PRODUCTION_BASELINE_VARIANT.effective_max_age == CONFIRMATION_LOOKBACK_BARS

    def test_a_counterfactual_is_self_identifying(self) -> None:
        from fmis.swing_setup.policy import RESEARCH_POLICY_ID_PREFIX

        variant = ResearchPolicyVariant.counterfactual(2)
        assert not variant.is_production_baseline
        assert variant.effective_max_age == 2
        assert variant.policy_id.startswith(RESEARCH_POLICY_ID_PREFIX)
        assert "2" in variant.policy_id

    def test_two_bounds_never_share_a_policy_id(self) -> None:
        ids = {ResearchPolicyVariant.counterfactual(age).policy_id for age in range(11)}
        assert len(ids) == 11

    def test_zero_is_allowed_and_negative_is_not(self) -> None:
        assert ResearchPolicyVariant.counterfactual(0).effective_max_age == 0
        with pytest.raises(ResearchError):
            ResearchPolicyVariant.counterfactual(-1)


class TestComparisonModels:
    def test_variant_comparison_must_reconcile_against_the_baseline(self) -> None:
        with pytest.raises(ResearchError, match="baseline_confirmations"):
            VariantComparison(
                baseline_variant_id="b", variant_id="v",
                baseline_confirmations=10, variant_confirmations=8,
                unchanged=5, shifted_later=1, shifted_earlier=0, removed=1, added=0,
            )

    def test_variant_comparison_must_reconcile_against_the_variant(self) -> None:
        with pytest.raises(ResearchError, match="variant_confirmations"):
            VariantComparison(
                baseline_variant_id="b", variant_id="v",
                baseline_confirmations=10, variant_confirmations=99,
                unchanged=5, shifted_later=1, shifted_earlier=0, removed=4, added=0,
            )

    def test_a_reconciling_comparison_is_accepted(self) -> None:
        comparison = VariantComparison(
            baseline_variant_id="b", variant_id="v",
            baseline_confirmations=10, variant_confirmations=7,
            unchanged=5, shifted_later=1, shifted_earlier=0, removed=4, added=1,
        )
        assert comparison.removed == 4

    def test_post_filter_comparison_reconciles_both_populations(self) -> None:
        with pytest.raises(ResearchError, match="post_filter_kept"):
            PostFilterComparison(
                max_confirmation_age=2, baseline_confirmations=10, post_filter_kept=5,
                replay_confirmations=6, in_both=3, only_in_post_filter=1, only_in_replay=3,
                post_filter_target_first=0, post_filter_stop_first=0,
                replay_target_first=0, replay_stop_first=0,
            )

    def test_agreement_rate_is_the_jaccard_of_the_two_populations(self) -> None:
        comparison = PostFilterComparison(
            max_confirmation_age=2, baseline_confirmations=10, post_filter_kept=4,
            replay_confirmations=6, in_both=3, only_in_post_filter=1, only_in_replay=3,
            post_filter_target_first=0, post_filter_stop_first=0,
            replay_target_first=0, replay_stop_first=0,
        )
        assert comparison.agreement_rate == pytest.approx(3 / 7)


class TestAvailabilityModels:
    def test_satisfaction_and_shortfall_may_never_disagree(self) -> None:
        with pytest.raises(ResearchError, match="satisfies_window"):
            SeriesAvailability(
                symbol="BTCUSDT", interval="1w", earliest_open=_BASE, latest_open=_BASE,
                implied_candle_count=1, required_from=_BASE, satisfies_window=True,
                shortfall=timedelta(days=3),
            )

    def test_report_summarises_the_worst_shortfall(self) -> None:
        report = AvailabilityReport(
            series=(
                SeriesAvailability(
                    symbol="A", interval="1w", earliest_open=_BASE, latest_open=_BASE,
                    implied_candle_count=1, required_from=_BASE, satisfies_window=True,
                    shortfall=timedelta(0),
                ),
                SeriesAvailability(
                    symbol="B", interval="1w", earliest_open=_BASE, latest_open=_BASE,
                    implied_candle_count=1, required_from=_BASE - timedelta(days=9),
                    satisfies_window=False, shortfall=timedelta(days=9),
                ),
            ),
            probed_at=RUN_AT,
        )
        assert not report.is_satisfiable
        assert report.worst_shortfall == timedelta(days=9)
        assert [item.symbol for item in report.unsatisfied] == ["B"]


class TestResearchObservationInvariants:
    def _historical(self, **overrides):
        from fmis.swing_setup.backtest_models import HistoricalObservation

        fields = dict(
            symbol="BTCUSDT", as_of=_BASE, status=SetupState.WAIT, direction=None,
            setup_id=None, is_new_setup=False, directional_factors=(), thesis=(),
            confirmation=(), trigger_kind=None, trigger_price=None, reference_price=None,
            stop_price=None, target_price=None, risk_reward_ratio=None,
            sufficiency="sufficient", context_regime_structure="trending",
            context_regime_volatility="stable", context_regime_participation="normal",
            execution_last_timestamp=None, policy_id="swing-setup-v1",
        )
        fields.update(overrides)
        return HistoricalObservation(**fields)

    def test_a_measured_observation_must_have_a_segment(self) -> None:
        with pytest.raises(ResearchError, match="segment"):
            ResearchObservation(
                observation=self._historical(), in_measurement=True,
                opportunity_key=None, is_new_opportunity=False,
                is_first_confirmation=False,
                confirmation_break_age_bars=None, segment=None,
            )

    def test_an_unmeasured_observation_may_not_have_one(self) -> None:
        with pytest.raises(ResearchError, match="segment"):
            ResearchObservation(
                observation=self._historical(), in_measurement=False,
                opportunity_key=None, is_new_opportunity=False,
                is_first_confirmation=False,
                confirmation_break_age_bars=None, segment="s1",
            )

    def test_opportunity_key_tracks_direction(self) -> None:
        with pytest.raises(ResearchError, match="opportunity_key"):
            ResearchObservation(
                observation=self._historical(), in_measurement=False,
                opportunity_key="k", is_new_opportunity=False,
                is_first_confirmation=False,
                confirmation_break_age_bars=None, segment=None,
            )


class TestModelValidationRefusesMalformedInput:
    """Every guard on every research model, exercised.

    These are not defensive-programming decoration: each one is the difference
    between a research artifact that is wrong and one that cannot be built. A
    `RoleWarmup` whose duration is in the wrong unit, an `AvailabilityReport`
    that disagrees with itself, a `ResearchObservation` flagged as a first
    confirmation while reporting `CANDIDATE` — every one of those would produce
    a report full of reconciling numbers about nothing.
    """

    def _component(self) -> WarmupComponent:
        return WarmupComponent(name="x", bars=5, source="test")

    def _role(self) -> RoleWarmup:
        return RoleWarmup(
            role="context", interval="1w", required_bars=5,
            duration=5 * timedelta(weeks=1), components=(self._component(),),
        )

    @pytest.mark.parametrize(
        "kwargs, error",
        [
            ({"name": ""}, ResearchError),
            ({"source": "  "}, ResearchError),
            ({"bars": "5"}, TypeError),
            ({"bars": True}, TypeError),
            ({"bars": -1}, ResearchError),
        ],
    )
    def test_warmup_component_guards(self, kwargs, error) -> None:
        fields = {"name": "x", "bars": 5, "source": "test"}
        fields.update(kwargs)
        with pytest.raises(error):
            WarmupComponent(**fields)

    @pytest.mark.parametrize(
        "kwargs, error",
        [
            ({"role": ""}, ResearchError),
            ({"interval": ""}, ResearchError),
            ({"required_bars": "5"}, TypeError),
            ({"required_bars": 0}, ResearchError),
            ({"duration": 5}, TypeError),
            ({"components": ()}, ResearchError),
            ({"components": ("x",)}, TypeError),
        ],
    )
    def test_role_warmup_guards(self, kwargs, error) -> None:
        fields = dict(
            role="context", interval="1w", required_bars=5,
            duration=5 * timedelta(weeks=1),
            components=(WarmupComponent(name="x", bars=5, source="test"),),
        )
        fields.update(kwargs)
        with pytest.raises(error):
            RoleWarmup(**fields)

    @pytest.mark.parametrize(
        "kwargs, error",
        [
            ({"by_role": ()}, ResearchError),
            ({"by_role": ("x",)}, TypeError),
            ({"prefix": 5}, TypeError),
        ],
    )
    def test_warmup_requirement_guards(self, kwargs, error) -> None:
        fields = {"by_role": (self._role(),), "prefix": 5 * timedelta(weeks=1)}
        fields.update(kwargs)
        with pytest.raises(error):
            WarmupRequirement(**fields)

    def test_for_interval_refuses_an_interval_no_role_uses(self) -> None:
        requirement = WarmupRequirement(
            by_role=(self._role(),), prefix=5 * timedelta(weeks=1)
        )
        assert requirement.for_interval("1w") == 5 * timedelta(weeks=1)
        with pytest.raises(ResearchError, match="no role uses"):
            requirement.for_interval("4h")

    def test_research_window_refuses_a_non_datetime(self) -> None:
        with pytest.raises(TypeError):
            ResearchWindow(
                warmup_start=_BASE, measurement_start="tomorrow",
                measurement_end=MEASUREMENT_END, outcome_tail_end=TAIL_END,
            )

    @pytest.mark.parametrize(
        "kwargs, error",
        [
            ({"label": " "}, ResearchError),
            ({"start": "now"}, TypeError),
            ({"end": _BASE.replace(tzinfo=None)}, ResearchError),
        ],
    )
    def test_temporal_segment_guards(self, kwargs, error) -> None:
        fields = {"label": "s", "start": _BASE, "end": _BASE + timedelta(days=1)}
        fields.update(kwargs)
        with pytest.raises(error):
            TemporalSegment(**fields)

    @pytest.mark.parametrize(
        "kwargs, error",
        [
            ({"variant_id": ""}, ResearchError),
            ({"max_confirmation_age": "2"}, TypeError),
            ({"max_confirmation_age": True}, TypeError),
            ({"max_confirmation_age": -1}, ResearchError),
        ],
    )
    def test_policy_variant_guards(self, kwargs, error) -> None:
        fields = {"variant_id": "v", "max_confirmation_age": 2}
        fields.update(kwargs)
        with pytest.raises(error):
            ResearchPolicyVariant(**fields)

    @pytest.mark.parametrize(
        "kwargs, error",
        [
            ({"symbol": ""}, ResearchError),
            ({"interval": " "}, ResearchError),
            ({"earliest_open": "yesterday"}, TypeError),
            ({"latest_open": None}, ResearchError),
            ({"required_from": 1}, TypeError),
            ({"implied_candle_count": "1"}, TypeError),
            ({"implied_candle_count": -1}, ResearchError),
            ({"satisfies_window": 1}, TypeError),
            ({"shortfall": 0}, TypeError),
        ],
    )
    def test_series_availability_guards(self, kwargs, error) -> None:
        fields = dict(
            symbol="BTCUSDT", interval="1w", earliest_open=_BASE, latest_open=_BASE,
            implied_candle_count=1, required_from=_BASE, satisfies_window=True,
            shortfall=timedelta(0),
        )
        fields.update(kwargs)
        with pytest.raises(error):
            SeriesAvailability(**fields)

    @pytest.mark.parametrize(
        "kwargs, error",
        [({"series": ["x"]}, TypeError), ({"series": ("x",)}, TypeError),
         ({"probed_at": "now"}, TypeError)],
    )
    def test_availability_report_guards(self, kwargs, error) -> None:
        fields = {"series": (), "probed_at": RUN_AT}
        fields.update(kwargs)
        with pytest.raises(error):
            AvailabilityReport(**fields)

    def test_confirmation_record_guards(self) -> None:
        with pytest.raises(ResearchError):
            _record("", "k", _BASE, 0)
        with pytest.raises(TypeError):
            ConfirmationRecord(
                symbol="BTCUSDT", opportunity_key="k", confirmed_at="now",
                direction="long", confirmation_break_age_bars=0,
                reference_price=1.0, risk_reward_ratio=1.0, segment=None,
            )

    @pytest.mark.parametrize("field", ["baseline_confirmations", "unchanged", "added"])
    def test_variant_comparison_rejects_non_integers_and_negatives(self, field) -> None:
        fields = dict(
            baseline_variant_id="b", variant_id="v", baseline_confirmations=0,
            variant_confirmations=0, unchanged=0, shifted_later=0,
            shifted_earlier=0, removed=0, added=0,
        )
        with pytest.raises(TypeError):
            VariantComparison(**{**fields, field: "0"})
        with pytest.raises(ResearchError):
            VariantComparison(**{**fields, field: -1})

    def test_variant_comparison_rejects_empty_identifiers(self) -> None:
        with pytest.raises(ResearchError):
            VariantComparison(
                baseline_variant_id="", variant_id="v", baseline_confirmations=0,
                variant_confirmations=0, unchanged=0, shifted_later=0,
                shifted_earlier=0, removed=0, added=0,
            )

    def test_post_filter_comparison_guards(self) -> None:
        fields = dict(
            max_confirmation_age=2, baseline_confirmations=0, post_filter_kept=0,
            replay_confirmations=0, in_both=0, only_in_post_filter=0, only_in_replay=0,
            post_filter_target_first=0, post_filter_stop_first=0,
            replay_target_first=0, replay_stop_first=0,
        )
        assert PostFilterComparison(**fields).agreement_rate is None
        with pytest.raises(TypeError):
            PostFilterComparison(**{**fields, "in_both": "0"})
        with pytest.raises(ResearchError):
            PostFilterComparison(**{**fields, "in_both": -1})
        with pytest.raises(ResearchError, match="only_in_replay"):
            PostFilterComparison(
                **{**fields, "replay_confirmations": 3, "in_both": 1, "only_in_replay": 1,
                   "post_filter_kept": 1}
            )

    def test_research_observation_rejects_a_non_observation(self) -> None:
        with pytest.raises(TypeError):
            ResearchObservation(
                observation="not one", in_measurement=False, opportunity_key=None,
                is_new_opportunity=False, is_first_confirmation=False,
                confirmation_break_age_bars=None, segment=None,
            )

    def test_research_backtest_run_rejects_a_bad_schema_version(self, baseline_study) -> None:
        from dataclasses import replace

        with pytest.raises(TypeError):
            replace(baseline_study.baseline, schema_version="1")


# ==================================== warm-up =====================================


class _MuteFeature(BaseFeature):
    """A feature that declares no warm-up at all — the case that must never pass silently."""

    category = FeatureCategory.INDICATOR
    dependencies: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.name = "mute"

    def compute(self, context) -> FeatureResult:
        return FeatureResult(
            name=self.name, category=self.category, value=None, metadata={"period": 3}
        )


class _LoudFeature(BaseFeature):
    """A feature declaring a warm-up far longer than any shipped one."""

    category = FeatureCategory.INDICATOR
    dependencies: tuple[str, ...] = ()

    def __init__(self, bars: int = 999) -> None:
        self.name = f"loud_{bars}"
        self._bars = bars

    def compute(self, context) -> FeatureResult:
        return FeatureResult(
            name=self.name,
            category=self.category,
            value=None,
            metadata={"warmup_candles": self._bars},
        )


class TestWarmupDerivation:
    def test_a_features_own_declaration_is_what_is_read(self) -> None:
        from fmis.features.indicators.ema import ExponentialMovingAverage

        assert feature_warmup_bars(ExponentialMovingAverage(50), "1w") == 50
        assert feature_warmup_bars(ExponentialMovingAverage(200), "1d") == 200
        assert feature_warmup_bars(_LoudFeature(777), "4h") == 777

    def test_a_feature_declaring_no_warmup_raises_rather_than_scoring_zero(self) -> None:
        with pytest.raises(ResearchError, match="declares no warm-up"):
            feature_warmup_bars(_MuteFeature(), "4h")

    def test_a_longer_feature_lengthens_the_prefix_without_editing_the_derivation(self) -> None:
        base = derive_warmup(DEFAULT_TIMEFRAMES, limit=10)
        louder = derive_warmup(DEFAULT_TIMEFRAMES, limit=10, features=(_LoudFeature(999),))
        assert louder.prefix > base.prefix
        assert louder.prefix == 999 * timedelta(weeks=1)

    def test_the_requested_analysis_window_is_a_warmup_component(self) -> None:
        small = derive_warmup(DEFAULT_TIMEFRAMES, limit=10)
        large = derive_warmup(DEFAULT_TIMEFRAMES, limit=1000)
        assert large.prefix == 1000 * timedelta(weeks=1)
        assert small.prefix < large.prefix
        names = {component.name for role in large.by_role for component in role.components}
        assert "analysis_window" in names

    def test_every_role_reports_its_own_duration_in_its_own_unit(self) -> None:
        warmup = derive_warmup(DEFAULT_TIMEFRAMES, limit=_TEST_LIMIT)
        by_interval = {role.interval: role for role in warmup.by_role}
        assert by_interval["1w"].required_bars == 200
        assert by_interval["1w"].duration == 200 * timedelta(weeks=1)
        assert by_interval["1d"].duration == 200 * timedelta(days=1)
        assert by_interval["4h"].duration == 200 * timedelta(hours=4)
        assert warmup.prefix == by_interval["1w"].duration

    def test_structural_detection_and_confirmation_windows_are_named_components(self) -> None:
        warmup = derive_warmup(DEFAULT_TIMEFRAMES, limit=10)
        by_role = {role.role: role for role in warmup.by_role}
        structural = {
            component.name: component.bars
            for component in by_role["setup"].components
        }
        assert structural["structural_detection"] == required_candles(2, 2)
        execution = {
            component.name: component.bars
            for component in by_role["execution"].components
        }
        assert execution["confirmation_staleness_window"] == 10

    def test_a_missing_role_is_rejected(self) -> None:
        with pytest.raises(ResearchError, match="missing"):
            derive_warmup({TimeframeRole.CONTEXT: "1w"}, limit=10)

    def test_per_interval_starts_use_each_intervals_own_requirement(self) -> None:
        warmup = derive_warmup(DEFAULT_TIMEFRAMES, limit=_TEST_LIMIT)
        window = ResearchWindow(
            warmup_start=MEASUREMENT_START - warmup.prefix,
            measurement_start=MEASUREMENT_START,
            measurement_end=MEASUREMENT_END,
            outcome_tail_end=TAIL_END,
        )
        starts = required_from_by_interval(window, warmup, ("1w", "1d", "4h"))
        assert starts["1w"] == MEASUREMENT_START - 200 * timedelta(weeks=1)
        assert starts["1d"] == MEASUREMENT_START - 200 * timedelta(days=1)
        assert starts["4h"] == MEASUREMENT_START - 200 * timedelta(hours=4)

    def test_role_warmup_rejects_a_duration_in_the_wrong_unit(self) -> None:
        component = WarmupComponent(name="x", bars=5, source="test")
        with pytest.raises(ResearchError, match="wrong unit"):
            RoleWarmup(
                role="context", interval="1w", required_bars=5,
                duration=timedelta(days=5), components=(component,),
            )

    def test_role_warmup_rejects_a_requirement_smaller_than_a_component(self) -> None:
        with pytest.raises(ResearchError, match="largest component"):
            RoleWarmup(
                role="context", interval="1w", required_bars=3,
                duration=3 * timedelta(weeks=1),
                components=(WarmupComponent(name="x", bars=9, source="test"),),
            )

    def test_prefix_must_be_the_longest_role(self) -> None:
        role = RoleWarmup(
            role="context", interval="1w", required_bars=2,
            duration=2 * timedelta(weeks=1),
            components=(WarmupComponent(name="x", bars=2, source="test"),),
        )
        with pytest.raises(ResearchError, match="prefix"):
            WarmupRequirement(by_role=(role,), prefix=timedelta(days=1))


class TestIntervalDuration:
    def test_calendar_months_are_refused_rather_than_approximated(self) -> None:
        with pytest.raises(ResearchError, match="no exact fixed duration"):
            interval_duration("1M")

    def test_known_intervals_are_exact(self) -> None:
        assert interval_duration("4h") == timedelta(hours=4)
        assert interval_duration("1w") == timedelta(weeks=1)


# ==================================== segments ====================================


class TestSegments:
    def _window(self, days: int) -> ResearchWindow:
        return ResearchWindow(
            warmup_start=_BASE - timedelta(days=1),
            measurement_start=_BASE,
            measurement_end=_BASE + timedelta(days=days),
            outcome_tail_end=_BASE + timedelta(days=days + 10),
        )

    def test_two_full_years_are_cut_into_years(self) -> None:
        segments = build_segments(self._window(800))
        assert len(segments) == 2
        assert all(segment.label.startswith("year_") for segment in segments)

    def test_one_year_falls_to_half_years(self) -> None:
        segments = build_segments(self._window(390))
        assert len(segments) == 2
        assert all(segment.label.startswith("half_year_") for segment in segments)

    def test_a_short_window_still_gets_two_segments(self) -> None:
        segments = build_segments(self._window(30))
        assert len(segments) == 2

    def test_segments_tile_the_window_exactly(self) -> None:
        for days in (30, 200, 390, 800, 1100):
            window = self._window(days)
            segments = build_segments(window)
            assert segments[0].start == window.measurement_start
            assert segments[-1].end == window.measurement_end
            for earlier, later in zip(segments, segments[1:]):
                assert earlier.end == later.start

    def test_every_measured_instant_belongs_to_exactly_one_segment(self) -> None:
        window = self._window(390)
        segments = build_segments(window)
        for offset in (0, 1, 100, 194, 195, 196, 389):
            instant = window.measurement_start + timedelta(days=offset)
            assert sum(1 for segment in segments if segment.contains(instant)) == 1

    def test_the_end_instant_belongs_to_no_segment(self) -> None:
        window = self._window(390)
        segments = build_segments(window)
        assert not any(segment.contains(window.measurement_end) for segment in segments)


# ==================================== identity ====================================


class TestOpportunityIdentity:
    def test_wait_has_no_key(self) -> None:
        assert opportunity_key("BTCUSDT", None, _BASE) is None

    def test_equal_arguments_give_an_equal_key(self) -> None:
        assert opportunity_key("BTCUSDT", Direction.LONG, _BASE) == opportunity_key(
            "BTCUSDT", Direction.LONG, _BASE
        )

    def test_symbol_direction_and_start_all_participate(self) -> None:
        keys = {
            opportunity_key("BTCUSDT", Direction.LONG, _BASE),
            opportunity_key("ETHUSDT", Direction.LONG, _BASE),
            opportunity_key("BTCUSDT", Direction.SHORT, _BASE),
            opportunity_key("BTCUSDT", Direction.LONG, _BASE + _FOUR_HOURS),
        }
        assert len(keys) == 4

    def test_a_run_keeps_one_key_across_every_bar(self) -> None:
        tracker = OpportunityTracker()
        keys = []
        for step in range(5):
            key, is_new, _ = tracker.observe(
                "BTCUSDT", Direction.LONG, SetupState.CANDIDATE, _BASE + step * _FOUR_HOURS
            )
            keys.append((key, is_new))
        assert len({key for key, _ in keys}) == 1
        assert [is_new for _, is_new in keys] == [True, False, False, False, False]

    def test_first_confirmation_fires_exactly_once_per_run(self) -> None:
        tracker = OpportunityTracker()
        flags = [
            tracker.observe(
                "BTCUSDT", Direction.LONG, SetupState.CONFIRMED, _BASE + step * _FOUR_HOURS
            )[2]
            for step in range(4)
        ]
        assert flags == [True, False, False, False]

    def test_wait_ends_a_run_and_a_later_return_is_new(self) -> None:
        tracker = OpportunityTracker()
        first, _, _ = tracker.observe("BTCUSDT", Direction.LONG, SetupState.CANDIDATE, _BASE)
        tracker.observe("BTCUSDT", None, SetupState.WAIT, _BASE + _FOUR_HOURS)
        second, is_new, _ = tracker.observe(
            "BTCUSDT", Direction.LONG, SetupState.CANDIDATE, _BASE + 2 * _FOUR_HOURS
        )
        assert is_new and second != first

    def test_a_direction_flip_starts_a_new_run(self) -> None:
        tracker = OpportunityTracker()
        long_key, _, _ = tracker.observe("BTCUSDT", Direction.LONG, SetupState.CANDIDATE, _BASE)
        short_key, is_new, _ = tracker.observe(
            "BTCUSDT", Direction.SHORT, SetupState.CANDIDATE, _BASE + _FOUR_HOURS
        )
        assert is_new and short_key != long_key

    def test_symbols_are_isolated(self) -> None:
        tracker = OpportunityTracker()
        tracker.observe("BTCUSDT", Direction.LONG, SetupState.CONFIRMED, _BASE)
        _, is_new, first_confirmation = tracker.observe(
            "ETHUSDT", Direction.LONG, SetupState.CONFIRMED, _BASE
        )
        assert is_new and first_confirmation


# =================================== replay index =================================


class TestReplayIndex:
    def test_an_indexed_transport_answers_byte_identically(self, single_symbol_cache) -> None:
        index = prepare_replay_index(single_symbol_cache)
        for offset in (0, 500, _WARM_BARS, _WARM_BARS + 50):
            now = _BASE + offset * _FOUR_HOURS
            plain = build_replay_transport(single_symbol_cache, now=now)
            indexed = build_replay_transport(single_symbol_cache, now=now, index=index)
            for interval in ("4h", "1d", "1w"):
                url = (
                    "https://api.binance.com/api/v3/klines?"
                    f"symbol=BTCUSDT&interval={interval}&limit={_TEST_LIMIT}"
                )
                assert plain(url).body == indexed(url).body

    def test_an_unknown_series_still_answers_with_the_provider_error(self, single_symbol_cache) -> None:
        index = prepare_replay_index(single_symbol_cache)
        transport = build_replay_transport(single_symbol_cache, now=_BASE, index=index)
        response = transport(
            "https://api.binance.com/api/v3/klines?symbol=NOPE&interval=4h&limit=5"
        )
        assert response.status == 400
        assert json.loads(response.body)["code"] == -1121

    def test_unsorted_rows_are_rejected_rather_than_binary_searched(self) -> None:
        rows = zigzag_rows(5, start_ms=to_epoch_ms(_BASE), interval_ms=_FOUR_HOURS_MS)
        with pytest.raises(Exception, match="ascending close-time order"):
            prepare_replay_index({("X", "4h"): list(reversed(rows))})


# ================================ harness integration =============================


class TestBoundaries:
    def test_warmup_observations_are_recorded_and_never_counted(self, baseline_study) -> None:
        run = baseline_study.baseline
        primed = [item for item in run.observations if not item.in_measurement]
        measured = run.measured
        assert primed, "the priming window must actually be replayed"
        assert len(primed) == DEFAULT_IDENTITY_PRIMING_BARS
        assert all(item.as_of < MEASUREMENT_START for item in primed) or all(
            item.observation.execution_last_timestamp < MEASUREMENT_START for item in primed
        )
        metrics = compute_research_metrics(run)
        assert metrics.measured_observations == len(measured)
        assert metrics.warmup_observations == len(primed)
        assert metrics.measured_observations + metrics.warmup_observations == len(
            run.observations
        )

    def test_the_measurement_window_is_exact_at_both_edges(self, baseline_study) -> None:
        run = baseline_study.baseline
        stamps = sorted(
            item.observation.execution_last_timestamp
            for item in run.measured
            if item.observation.execution_last_timestamp is not None
        )
        # An instant is the millisecond after a candle closes; the candle whose
        # close produced the first measured instant OPENS one bar earlier.
        assert stamps[0] == MEASUREMENT_START - _FOUR_HOURS
        assert stamps[-1] == MEASUREMENT_END - 2 * _FOUR_HOURS
        assert len(run.measured) == _MEASURED_BARS

    def test_no_observation_is_ever_created_from_tail_data(self, baseline_study) -> None:
        run = baseline_study.baseline
        for item in run.observations:
            assert item.observation.execution_last_timestamp < MEASUREMENT_END

    def test_a_changed_tail_candle_moves_an_outcome_but_no_observation(self) -> None:
        """The tail must be readable for resolution and invisible to decisions.

        The measurement window is deliberately closed two bars after a real
        confirmation, so that confirmation's whole resolution path lies in the
        outcome tail. Corrupting the tail must therefore change the outcome and
        leave every observation byte-identical.
        """
        rows = _three_role_rows()
        cache = _cache_for({"BTCUSDT": rows})
        survey = _study(cache=cache, variant_max_ages=())
        assert survey.baseline.outcomes, "fixture must produce an outcome"
        confirmed_at = survey.baseline.outcomes[0].confirmed_at
        short_end = confirmed_at + 2 * _FOUR_HOURS
        tail_index = round((short_end - _BASE) / _FOUR_HOURS)

        original = _study(cache=cache, variant_max_ages=(), measurement_end=short_end)
        assert original.baseline.outcomes, "the shortened window must still confirm"

        mutated_4h = [list(row) for row in rows["4h"]]
        for row in mutated_4h[tail_index:]:
            row[2] = f"{float(row[2]) * 100:.8f}"   # high
            row[3] = "0.00000001"                    # low
        mutated = _study(
            cache=_cache_for({"BTCUSDT": {**rows, "4h": mutated_4h}}),
            variant_max_ages=(),
            measurement_end=short_end,
        )

        assert [item.observation for item in original.baseline.observations] == [
            item.observation for item in mutated.baseline.observations
        ]
        assert original.baseline.outcomes != mutated.baseline.outcomes

    def test_a_changed_future_measurement_candle_cannot_alter_an_earlier_decision(self) -> None:
        rows = _three_role_rows()
        cutoff = _WARM_BARS + 60
        early_end = _BASE + cutoff * _FOUR_HOURS
        original = _study(
            cache=_cache_for({"BTCUSDT": rows}),
            variant_max_ages=(),
            measurement_end=early_end,
        )
        mutated_4h = [list(row) for row in rows["4h"]]
        for row in mutated_4h[cutoff:]:
            for price_index in (1, 2, 3, 4):
                row[price_index] = f"{float(row[price_index]) * 1000:.8f}"
        mutated = _study(
            cache=_cache_for({"BTCUSDT": {**rows, "4h": mutated_4h}}),
            variant_max_ages=(),
            measurement_end=early_end,
        )
        assert [item.observation for item in original.baseline.observations] == [
            item.observation for item in mutated.baseline.observations
        ]

    def test_a_changed_warmup_candle_may_legitimately_change_later_state(self) -> None:
        rows = _three_role_rows()
        original = _study(cache=_cache_for({"BTCUSDT": rows}), variant_max_ages=())
        mutated_4h = [list(row) for row in rows["4h"]]
        # A warm-up candle inside the analysis window every measured instant
        # still reads. Changing it SHOULD change later state — a harness where
        # it did not would be ignoring its own warm-up.
        for row in mutated_4h[_WARM_BARS - 50 : _WARM_BARS]:
            for price_index in (1, 2, 3, 4):
                row[price_index] = f"{float(row[price_index]) * 1.5:.8f}"
        mutated = _study(
            cache=_cache_for({"BTCUSDT": {**rows, "4h": mutated_4h}}), variant_max_ages=()
        )
        assert [item.observation for item in original.baseline.observations] != [
            item.observation for item in mutated.baseline.observations
        ]

    def test_no_measured_instant_was_analysed_on_a_warming_or_short_window(
        self, baseline_study
    ) -> None:
        """The warm-up claim, verified per instant rather than argued.

        The fixture reaches back exactly as far as the derivation demands and
        not one bar further, so if the derived prefix were short by anything at
        all, some measured instant would show a feature still warming up or a
        role holding fewer candles than the harness requested.
        """
        for run in baseline_study.runs:
            metadata = run.metadata
            assert metadata["measured_role_views_with_warming_features"] == 0
            assert metadata["measured_role_views_below_requested_window"] == 0
            assert metadata["insufficient_data_measured_instants"] == 0
            assert set(metadata["minimum_closed_candles_by_role"]) == {
                "context", "setup", "execution"
            }
            assert all(
                closed >= _TEST_LIMIT
                for closed in metadata["minimum_closed_candles_by_role"].values()
            )

    def test_every_measured_observation_lands_in_exactly_one_segment(self, baseline_study) -> None:
        run = baseline_study.baseline
        labels = {segment.label for segment in run.segments}
        for item in run.measured:
            assert item.segment in labels
        for item in run.observations:
            if not item.in_measurement:
                assert item.segment is None

    def test_the_recorded_segment_is_the_one_that_actually_contains_the_instant(
        self, baseline_study
    ) -> None:
        """Membership, not merely a legal label — a misclassification that put
        every observation in the first segment would satisfy the reconciliation
        checks above while making every temporal claim false."""
        run = baseline_study.baseline
        by_label = {segment.label: segment for segment in run.segments}
        for item in run.measured:
            instant = item.observation.execution_last_timestamp + _FOUR_HOURS
            assert by_label[item.segment].contains(instant), (item.segment, instant)
        assert len({item.segment for item in run.measured}) == len(run.segments), (
            "the fixture must populate every segment, or this test proves nothing"
        )


class TestDenominators:
    def test_state_counts_reconcile_to_measured_observations(self, baseline_study) -> None:
        metrics = compute_research_metrics(baseline_study.baseline)
        assert (
            metrics.wait_count + metrics.candidate_count + metrics.confirmed_count
            == metrics.measured_observations
        )

    def test_outcome_statuses_reconcile_to_evaluated_outcomes(self, baseline_study) -> None:
        metrics = compute_research_metrics(baseline_study.baseline)
        assert (
            metrics.target_first
            + metrics.stop_first
            + metrics.ambiguous_same_bar
            + metrics.unresolved
            == metrics.evaluated_outcomes
        )

    def test_segment_observation_counts_reconcile(self, baseline_study) -> None:
        metrics = compute_research_metrics(baseline_study.baseline)
        assert sum(metrics.observations_by_segment.values()) == metrics.measured_observations

    def test_segment_outcome_counts_reconcile(self, baseline_study) -> None:
        metrics = compute_research_metrics(baseline_study.baseline)
        assert sum(cohort.total for cohort in metrics.by_segment) == metrics.evaluated_outcomes

    def test_symbol_and_side_cohorts_reconcile(self, baseline_study) -> None:
        metrics = compute_research_metrics(baseline_study.baseline)
        assert sum(cohort.total for cohort in metrics.by_symbol) == metrics.evaluated_outcomes
        assert sum(cohort.total for cohort in metrics.by_side) == metrics.evaluated_outcomes

    def test_one_outcome_per_confirmed_opportunity_at_most(self, baseline_study) -> None:
        run = baseline_study.baseline
        keys = [outcome.setup_id for outcome in run.outcomes]
        assert len(keys) == len(set(keys)), "an opportunity may be evaluated once"
        assert len(run.outcomes) <= len(first_confirmations(run))


class TestVariantReplay:
    def test_the_override_at_the_production_bound_reproduces_the_baseline(
        self, baseline_study
    ) -> None:
        baseline = baseline_study.baseline
        replayed = next(
            run for run in baseline_study.variants if run.variant.max_confirmation_age == 10
        )
        assert [item.observation.status for item in baseline.observations] == [
            item.observation.status for item in replayed.observations
        ]
        assert [item.observation.direction for item in baseline.observations] == [
            item.observation.direction for item in replayed.observations
        ]
        assert [item.opportunity_key for item in baseline.observations] == [
            item.opportunity_key for item in replayed.observations
        ]
        assert baseline.outcomes == replayed.outcomes

    def test_only_the_policy_id_marks_the_replayed_baseline_as_research(
        self, baseline_study
    ) -> None:
        from fmis.swing_setup.policy import RESEARCH_POLICY_ID_PREFIX, SETUP_POLICY_ID

        baseline = baseline_study.baseline
        replayed = next(
            run for run in baseline_study.variants if run.variant.max_confirmation_age == 10
        )
        assert {item.observation.policy_id for item in baseline.observations} == {
            SETUP_POLICY_ID
        }
        assert all(
            item.observation.policy_id.startswith(RESEARCH_POLICY_ID_PREFIX)
            for item in replayed.observations
        )

    def test_opportunity_decomposition_is_invariant_across_variants(
        self, baseline_study
    ) -> None:
        keys = [
            tuple(item.opportunity_key for item in run.observations)
            for run in baseline_study.runs
        ]
        assert len(set(keys)) == 1, (
            "the confirmation-age override must not change where directional runs "
            "begin and end; if it does, cross-variant comparison is meaningless"
        )

    def test_a_stricter_bound_never_confirms_where_the_baseline_did_not(
        self, baseline_study
    ) -> None:
        strict = next(
            run for run in baseline_study.variants if run.variant.max_confirmation_age == 0
        )
        comparison = compare_variant(baseline_study.baseline, strict)
        assert comparison.added == 0

    def test_a_stricter_bound_defers_a_confirmation_onto_a_later_break(
        self, baseline_study
    ) -> None:
        """The lifecycle a post-filter cannot produce, observed in a replay.

        The baseline confirms this opportunity on a 3-bar-old break. Under a
        1-bar bound that break is stale, the candidate survives as CANDIDATE,
        and a later break confirms it at a *different* instant — same
        opportunity, moved, not deleted.
        """
        strict = next(
            run for run in baseline_study.variants if run.variant.max_confirmation_age == 1
        )
        comparison = compare_variant(baseline_study.baseline, strict)
        assert comparison.shifted_later >= 1
        assert comparison.removed == 0
        symbol, _key, before, after = comparison.shifted_examples[0]
        assert symbol == "BTCUSDT"
        assert after > before

    def test_a_stricter_bound_confirms_on_fresher_breaks(self, baseline_study) -> None:
        baseline_ages = {
            record.confirmation_break_age_bars
            for record in confirmation_records(baseline_study.baseline)
        }
        strict = next(
            run for run in baseline_study.variants if run.variant.max_confirmation_age == 1
        )
        strict_ages = {
            record.confirmation_break_age_bars
            for record in confirmation_records(strict)
        }
        assert max(baseline_ages) > 1
        assert max(strict_ages) <= 1

    def test_a_comparison_over_two_different_windows_is_refused(self, single_symbol_cache) -> None:
        other = _study(
            cache=single_symbol_cache,
            variant_max_ages=(),
            measurement_end=MEASUREMENT_END - 4 * _FOUR_HOURS,
        )
        study = _study(cache=single_symbol_cache, variant_max_ages=())
        with pytest.raises(ResearchError, match="shared measurement window"):
            compare_variant(study.baseline, other.baseline)

    def test_deterministic_rerun_is_identical(self, single_symbol_cache) -> None:
        first = _study(cache=single_symbol_cache, variant_max_ages=(2,))
        second = _study(cache=single_symbol_cache, variant_max_ages=(2,))
        assert first.baseline.observations == second.baseline.observations
        assert first.baseline.outcomes == second.baseline.outcomes
        assert first.variants[0].observations == second.variants[0].observations

    def test_symbol_isolation(self) -> None:
        both_cache = _cache_for(
            {"BTCUSDT": _three_role_rows(), "ETHUSDT": _three_role_rows(mirror=True)}
        )
        solo_cache = _cache_for({"BTCUSDT": _three_role_rows()})
        both = _study(("BTCUSDT", "ETHUSDT"), cache=both_cache, variant_max_ages=())
        solo = _study(("BTCUSDT",), cache=solo_cache, variant_max_ages=())
        btc_from_both = [
            item.observation
            for item in both.baseline.observations
            if item.symbol == "BTCUSDT"
        ]
        assert btc_from_both == [item.observation for item in solo.baseline.observations]

    def test_long_short_symmetry(self) -> None:
        up = _study(cache=_cache_for({"BTCUSDT": _three_role_rows()}), variant_max_ages=())
        down = _study(
            cache=_cache_for({"BTCUSDT": _three_role_rows(mirror=True)}), variant_max_ages=()
        )
        assert len(up.baseline.observations) == len(down.baseline.observations)
        long_up = sum(1 for i in up.baseline.measured if i.direction is Direction.LONG)
        short_up = sum(1 for i in up.baseline.measured if i.direction is Direction.SHORT)
        long_down = sum(1 for i in down.baseline.measured if i.direction is Direction.LONG)
        short_down = sum(1 for i in down.baseline.measured if i.direction is Direction.SHORT)
        # The measurement window sits in the fixture's falling leg, so the
        # upright path leans SHORT and the reflected one leans LONG. The claim
        # is that the harness follows the market it is fed rather than favouring
        # a side — which side that is, is the fixture's business, not the
        # harness's.
        assert short_up > long_up
        assert long_down > short_down
        assert short_up == long_down
        assert long_up == short_down


class TestAvailabilityProbe:
    def test_a_satisfiable_window_measures_real_boundaries(self, single_symbol_cache) -> None:
        warmup = derive_warmup(DEFAULT_TIMEFRAMES, limit=_TEST_LIMIT)
        window = ResearchWindow(
            warmup_start=MEASUREMENT_START - warmup.prefix,
            measurement_start=MEASUREMENT_START,
            measurement_end=MEASUREMENT_END,
            outcome_tail_end=TAIL_END,
        )
        report = probe_availability(
            ["BTCUSDT"],
            ("1w", "1d", "4h"),
            required_from=required_from_by_interval(window, warmup, ("1w", "1d", "4h")),
            probed_at=RUN_AT,
            transport=binance_like_transport(single_symbol_cache),
        )
        assert report.is_satisfiable
        weekly = next(item for item in report.series if item.interval == "1w")
        assert weekly.earliest_open == _BASE
        assert weekly.implied_candle_count == len(
            single_symbol_cache[("BTCUSDT", "1w")]
        )

    def test_an_unsatisfiable_window_is_refused_not_shortened(self, single_symbol_cache) -> None:
        with pytest.raises(ResearchError, match="not satisfiable"):
            run_research_study(
                ["BTCUSDT"],
                measurement_start=MEASUREMENT_START - 40 * timedelta(weeks=1),
                measurement_end=MEASUREMENT_END,
                run_at=RUN_AT,
                variant_max_ages=(),
                limit=_TEST_LIMIT,
                evaluation_window_bars=_TAIL_BARS,
                transport=binance_like_transport(single_symbol_cache),
            )

    def test_an_unsatisfiable_window_can_be_inspected_deliberately(
        self, single_symbol_cache
    ) -> None:
        study = run_research_study(
            ["BTCUSDT"],
            measurement_start=MEASUREMENT_START - 40 * timedelta(weeks=1),
            measurement_end=MEASUREMENT_END,
            run_at=RUN_AT,
            variant_max_ages=(),
            limit=_TEST_LIMIT,
            evaluation_window_bars=_TAIL_BARS,
            transport=binance_like_transport(single_symbol_cache),
            require_availability=False,
        )
        assert not study.availability.is_satisfiable
        assert study.baseline.availability.unsatisfied


# =============================== post-filter vs replay ============================


def _record(symbol: str, key: str, when: datetime, age: int | None) -> ConfirmationRecord:
    return ConfirmationRecord(
        symbol=symbol,
        opportunity_key=key,
        confirmed_at=when,
        direction="long",
        confirmation_break_age_bars=age,
        reference_price=100.0,
        risk_reward_ratio=2.0,
        segment="s1",
    )


class TestPostFilterVersusReplay:
    def test_a_post_filter_can_only_ever_return_a_subset_of_the_baseline(
        self, baseline_study
    ) -> None:
        baseline = baseline_study.baseline
        kept = post_filter_keep(baseline, 2)
        all_records = {record.identity for record in confirmation_records(baseline)}
        assert {record.identity for record in kept} <= all_records
        assert all(
            record.confirmation_break_age_bars is not None
            and record.confirmation_break_age_bars <= 2
            for record in kept
        )

    def test_a_looser_filter_keeps_at_least_as_much(self, baseline_study) -> None:
        baseline = baseline_study.baseline
        sizes = [len(post_filter_keep(baseline, bound)) for bound in (0, 1, 2, 5, 10)]
        assert sizes == sorted(sizes)

    def test_the_production_baseline_cannot_be_post_filter_compared_against_itself(
        self, baseline_study
    ) -> None:
        with pytest.raises(ResearchError, match="counterfactual"):
            post_filter_comparison(baseline_study.baseline, baseline_study.baseline)

    def test_comparison_reconciles_over_a_real_pair(self, baseline_study) -> None:
        strict = next(
            run for run in baseline_study.variants if run.variant.max_confirmation_age == 0
        )
        comparison = post_filter_comparison(baseline_study.baseline, strict)
        assert comparison.in_both + comparison.only_in_post_filter == comparison.post_filter_kept
        assert comparison.in_both + comparison.only_in_replay == comparison.replay_confirmations

    def test_the_post_filter_misses_a_confirmation_the_replay_finds(
        self, baseline_study
    ) -> None:
        """BB finding #2, measured end to end on a deterministic fixture.

        The post-filter drops the baseline's 3-bar-old confirmation and can put
        nothing in its place. The replay defers the same opportunity and
        confirms it later, so `only_in_replay` is non-zero and the two methods
        disagree about the population, not merely about a rate.
        """
        strict = next(
            run for run in baseline_study.variants if run.variant.max_confirmation_age == 1
        )
        comparison = post_filter_comparison(baseline_study.baseline, strict)
        assert comparison.only_in_replay >= 1
        assert comparison.replay_confirmations > comparison.post_filter_kept
        assert comparison.agreement_rate is not None
        assert comparison.agreement_rate < 1.0

    def test_a_deferred_confirmation_is_visible_to_replay_and_invisible_to_a_filter(
        self,
    ) -> None:
        """The exact lifecycle BB finding #2 says a post-filter cannot reproduce.

        Baseline confirms one opportunity on a 7-bar-old break. Under a bound of
        2 that same opportunity is deferred and confirms later, on a fresh break.
        A post-filter over the baseline drops the row and can produce nothing in
        its place; a replay produces the later confirmation.
        """
        baseline_records = (_record("BTCUSDT", "k1", _BASE, 7),)
        replay_records = (_record("BTCUSDT", "k1", _BASE + 5 * _FOUR_HOURS, 0),)
        kept = tuple(
            record
            for record in baseline_records
            if record.confirmation_break_age_bars is not None
            and record.confirmation_break_age_bars <= 2
        )
        assert kept == ()
        kept_ids = {record.identity for record in kept}
        replay_ids = {record.identity for record in replay_records}
        assert len(replay_ids - kept_ids) == 1
        assert baseline_records[0].confirmed_at != replay_records[0].confirmed_at


# ==================================== rendering ===================================


class TestRendering:
    def test_the_report_states_all_four_boundaries_and_stays_in_page_width(
        self, baseline_study
    ) -> None:
        comparisons = tuple(
            compare_variant(baseline_study.baseline, run) for run in baseline_study.variants
        )
        post_filters = tuple(
            post_filter_comparison(baseline_study.baseline, run)
            for run in baseline_study.variants
        )
        report = render_research_report(baseline_study.runs, comparisons, post_filters)
        for boundary in ("warm-up start", "measurement start", "measurement end", "outcome tail end"):
            assert boundary in report
        assert "SAMPLE CONCENTRATION" in report
        assert "POST-FILTER" in report
        assert "warm-up verified per instant" in report
        for line in report.splitlines():
            assert len(line) <= 78, line

    def test_the_availability_page_reports_every_series(self, baseline_study) -> None:
        page = render_availability_report(baseline_study.availability)
        assert "BTCUSDT" in page
        for line in page.splitlines():
            assert len(line) <= 78, line

    def test_an_empty_run_list_is_refused(self) -> None:
        with pytest.raises(ValueError):
            render_research_report(())

    def test_an_unsatisfiable_availability_page_states_the_shortfall(self) -> None:
        report = AvailabilityReport(
            series=(
                SeriesAvailability(
                    symbol="AAA", interval="1w", earliest_open=_BASE, latest_open=_BASE,
                    implied_candle_count=1, required_from=_BASE - timedelta(days=9),
                    satisfies_window=False, shortfall=timedelta(days=9),
                ),
                SeriesAvailability(
                    symbol="BBB", interval="1w", earliest_open=None, latest_open=None,
                    implied_candle_count=0, required_from=_BASE,
                    satisfies_window=False, shortfall=timedelta.max,
                ),
            ),
            probed_at=RUN_AT,
        )
        page = render_availability_report(report)
        # A series with no candle at all must not be rendered as a 999,999,999
        # day shortfall, which reads as a bug rather than as missing data.
        assert "999999999" not in page
        assert "short by 9 day(s)" in page
        assert "no candle at all" in page
        for line in page.splitlines():
            assert len(line) <= 78, line
