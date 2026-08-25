"""No-lookahead for the geometry layer, proved by mutating the future.

Milestone BX. Milestone BW proved its *decisions* could not read forward; this
file proves the same for everything BX added on top — the frozen candidate, the
ATR reading, the stop and target selection, the volatility normalisation and
every admission threshold.

The method is BW's and is the only one that survives a refactor: **change the
future and require the past not to notice.** Three mutations, each aimed at a
different way a geometry leak could enter, plus the warm-up control that stops
the other two passing vacuously on a harness that reads nothing at all.

There is also a **structural** proof the mutation tests cannot give.
`GeometryCandidate` holds no bar and no outcome, so `plan_geometry` cannot read
forward — it has nothing to read. `test_planning_does_not_depend_on_the_bars_at_all`
demonstrates that directly by throwing the bar array away and requiring every
plan to be unchanged. The mutation tests then prove the *capture* that builds
those candidates does not smuggle a future price into one.

Captures are cached at module scope because each one replays a real production
warm-up and costs seconds. See `tests.swing_lab_geometry_fixture` for why the
fixture is what it is.
"""

from __future__ import annotations

import pytest

from fmis.swing_lab.geometry import GeometryPlan, GeometrySkip, plan_geometry
from fmis.swing_lab.geometry_outcome import measure_outcome
from fmis.swing_lab.geometry_replay import (
    capture_geometry_candidates,
    trades_for_policy,
)
from fmis.swing_lab.geometry_variants import PRE_DECLARED_GEOMETRIES, PRODUCTION_GEOMETRY
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.trades import FRICTIONLESS_COSTS
from fmis.swing_lab.variants import BASELINE_VARIANT
from fmis.swing_setup.models import Direction

from tests.swing_lab_geometry_fixture import (
    BASE,
    FOUR_HOURS,
    LIMIT,
    MEASURED_BARS,
    SYMBOLS,
    TAIL_BARS,
    WARM_BARS,
    all_rows,
    dataset_for,
    scale_all,
    segments_for,
    window_for,
)


def _capture(rows, *, measurement_end=None):
    window = window_for() if measurement_end is None else window_for(measurement_end)
    return capture_geometry_candidates(
        SYMBOLS,
        BASELINE_VARIANT,
        window=window,
        segments=segments_for(window),
        dataset=dataset_for(rows),
        limit=LIMIT,
    )


def _fingerprint(capture) -> list[tuple]:
    """Every geometry fact a policy could read, flattened for exact comparison.

    Deliberately exhaustive rather than a summary: a fingerprint over only the
    *chosen* stop and target would miss a leak that reordered the levels a
    different policy selects from.
    """
    return [
        (
            item.symbol, item.setup_id, item.signal_at, item.signal_index,
            item.direction, item.reference_price,
            item.execution_atr, item.setup_atr,
            tuple((r.price, r.side, r.interval, r.origin_index)
                  for r in item.execution_stop_levels),
            tuple((r.price, r.side, r.interval, r.origin_index)
                  for r in item.setup_stop_levels),
            tuple((r.price, r.side, r.interval, r.origin_index)
                  for r in item.setup_target_levels),
            tuple((r.price, r.side, r.interval, r.origin_index)
                  for r in item.context_target_levels),
        )
        for item in capture.candidates
    ]


def _plan_fingerprint(capture) -> list[tuple]:
    """Every policy's chosen geometry, so a leak that only moved a selection shows."""
    out: list[tuple] = []
    for policy in PRE_DECLARED_GEOMETRIES:
        for item in capture.candidates:
            outcome = plan_geometry(item, policy)
            if isinstance(outcome, GeometrySkip):
                out.append((policy.policy_id, item.setup_id, "skip", outcome.reason))
            else:
                out.append(
                    (
                        policy.policy_id, item.setup_id, "plan",
                        outcome.stop.price, outcome.target.price,
                        outcome.risk, outcome.reward, outcome.planned_rr,
                        outcome.stop_bps, outcome.stop_atr_multiple,
                    )
                )
    return out


_TAIL_CUTOFF = WARM_BARS + MEASURED_BARS
_MID_CUTOFF = WARM_BARS + 260
_EARLY_END = BASE + _MID_CUTOFF * FOUR_HOURS


@pytest.fixture(scope="module")
def baseline_capture():
    return _capture(all_rows())


@pytest.fixture(scope="module")
def tail_mutated_capture():
    """Every 4H candle AFTER the measurement window, scaled ×1000."""
    return _capture(scale_all(all_rows(), _TAIL_CUTOFF, 1000.0))


@pytest.fixture(scope="module")
def early_original_capture():
    return _capture(all_rows(), measurement_end=_EARLY_END)


@pytest.fixture(scope="module")
def early_mutated_capture():
    """Candles after a MID-window cutoff, scaled ×1000; the window ends there."""
    return _capture(
        scale_all(all_rows(), _MID_CUTOFF, 1000.0), measurement_end=_EARLY_END
    )


@pytest.fixture(scope="module")
def warmup_mutated_capture():
    """The whole warm-up prefix scaled — this one MUST change the result."""
    return _capture(scale_all(all_rows(), 0, 1.5, intervals=("4h", "1d", "1w")))


class TestTheFixtureIsCapableOfFailing:
    """Each of these would let a later test pass vacuously if it did not hold."""

    def test_the_capture_produces_candidates(self, baseline_capture) -> None:
        assert baseline_capture.candidates

    def test_both_directions_are_present(self, baseline_capture) -> None:
        """A single-direction fixture cannot detect a rule that inverted a side."""
        directions = {item.direction for item in baseline_capture.candidates}
        assert directions == {Direction.LONG, Direction.SHORT}

    def test_every_candidate_carries_a_volatility_reading(self, baseline_capture) -> None:
        assert all(item.execution_atr is not None for item in baseline_capture.candidates)

    def test_candidates_offer_a_real_choice_of_levels(self, baseline_capture) -> None:
        """With one level per side, a selection leak would be invisible."""
        assert all(
            len(item.setup_target_levels) > 1 and len(item.execution_stop_levels) > 1
            for item in baseline_capture.candidates
        )

    def test_the_policies_actually_disagree_on_this_fixture(self, baseline_capture) -> None:
        chosen = set()
        for policy in PRE_DECLARED_GEOMETRIES:
            picks = tuple(
                (outcome.stop.price, outcome.target.price)
                for item in baseline_capture.candidates
                if isinstance(outcome := plan_geometry(item, policy), GeometryPlan)
            )
            chosen.add(picks)
        assert len(chosen) > 1, (
            "if every policy chose identically here, this fixture proves nothing"
        )

    def test_the_baseline_admits_trades(self, baseline_capture) -> None:
        outcome = trades_for_policy(
            baseline_capture, PRODUCTION_GEOMETRY,
            costs=FRICTIONLESS_COSTS, evaluation_window_bars=TAIL_BARS,
        )
        assert outcome.trades


class TestNoLookahead:
    def test_mutating_the_outcome_tail_cannot_change_any_candidate(
        self, baseline_capture, tail_mutated_capture
    ) -> None:
        """Candles after the measurement window may not reach a frozen fact."""
        assert _fingerprint(tail_mutated_capture) == _fingerprint(baseline_capture)

    def test_mutating_the_outcome_tail_cannot_change_any_plan(
        self, baseline_capture, tail_mutated_capture
    ) -> None:
        """The same mutation, checked through every policy's actual selection."""
        assert _plan_fingerprint(tail_mutated_capture) == _plan_fingerprint(
            baseline_capture
        )

    def test_mutating_later_measured_candles_cannot_change_earlier_ones(
        self, early_original_capture, early_mutated_capture
    ) -> None:
        """A measured bar may not be influenced by a measured bar after it."""
        assert _fingerprint(early_mutated_capture) == _fingerprint(
            early_original_capture
        )

    def test_mutating_later_candles_cannot_change_an_earlier_plan(
        self, early_original_capture, early_mutated_capture
    ) -> None:
        assert _plan_fingerprint(early_mutated_capture) == _plan_fingerprint(
            early_original_capture
        )

    def test_the_volatility_reading_is_not_taken_from_the_future(
        self, baseline_capture, tail_mutated_capture
    ) -> None:
        """ATR is the most tempting leak here: it is a rolling average, and a
        window that ran one bar long would be nearly invisible in a result."""
        assert [item.execution_atr for item in tail_mutated_capture.candidates] == [
            item.execution_atr for item in baseline_capture.candidates
        ]
        assert [item.setup_atr for item in tail_mutated_capture.candidates] == [
            item.setup_atr for item in baseline_capture.candidates
        ]

    def test_the_admission_instant_is_not_taken_from_the_future(
        self, baseline_capture, tail_mutated_capture
    ) -> None:
        assert [
            (item.symbol, item.signal_at, item.signal_index)
            for item in tail_mutated_capture.candidates
        ] == [
            (item.symbol, item.signal_at, item.signal_index)
            for item in baseline_capture.candidates
        ]


class TestTheControl:
    """Mutating the warm-up MUST change the result, or the tests above prove nothing."""

    def test_mutating_the_warm_up_prefix_changes_the_candidates(
        self, baseline_capture, warmup_mutated_capture
    ) -> None:
        assert _fingerprint(warmup_mutated_capture) != _fingerprint(baseline_capture)

    def test_mutating_the_warm_up_prefix_changes_the_plans(
        self, baseline_capture, warmup_mutated_capture
    ) -> None:
        assert _plan_fingerprint(warmup_mutated_capture) != _plan_fingerprint(
            baseline_capture
        )


class TestOutcomesCannotFlowBackwards:
    """MFE and MAE are outcome statistics and must never become admission criteria."""

    def test_a_geometry_policy_receives_no_object_carrying_a_price_path(
        self, baseline_capture
    ) -> None:
        item = baseline_capture.candidates[0]
        for name in item.__slots__:
            value = getattr(item, name)
            for probe in ("high", "low", "open_time", "close"):
                assert not hasattr(value, probe), f"{name} exposes {probe}"

    def test_planning_does_not_depend_on_the_bars_at_all(self, baseline_capture) -> None:
        """The strongest available statement: plans are identical when the bar
        array is thrown away entirely, because no policy ever consults it."""
        before = _plan_fingerprint(baseline_capture)
        stripped = type(baseline_capture)(
            admission_variant_id=baseline_capture.admission_variant_id,
            admission_policy_id=baseline_capture.admission_policy_id,
            candidates=baseline_capture.candidates,
            bars_by_symbol={},
            metadata={},
        )
        assert _plan_fingerprint(stripped) == before

    def test_an_outcome_carries_the_window_that_bounded_it(self, baseline_capture) -> None:
        outcome = trades_for_policy(
            baseline_capture, PRODUCTION_GEOMETRY,
            costs=FRICTIONLESS_COSTS, evaluation_window_bars=TAIL_BARS,
        )
        plan, trade = outcome.plans[0], outcome.trades[0]
        bars = baseline_capture.bars_by_symbol[trade.symbol]
        measured = measure_outcome(plan, trade, bars, evaluation_window_bars=TAIL_BARS)
        assert measured.evaluation_window_bars == TAIL_BARS
        assert measured.policy_id == PRODUCTION_GEOMETRY.policy_id

    def test_measuring_an_outcome_against_the_wrong_trade_is_refused(
        self, baseline_capture
    ) -> None:
        outcome = trades_for_policy(
            baseline_capture, PRODUCTION_GEOMETRY,
            costs=FRICTIONLESS_COSTS, evaluation_window_bars=TAIL_BARS,
        )
        assert len(outcome.trades) >= 2
        bars = baseline_capture.bars_by_symbol[outcome.trades[0].symbol]
        with pytest.raises(SwingLabError, match="but the trade describes"):
            measure_outcome(
                outcome.plans[0], outcome.trades[1], bars,
                evaluation_window_bars=TAIL_BARS,
            )

    def test_reached_r_is_read_from_the_recorded_excursion_not_a_second_walk(
        self, baseline_capture
    ) -> None:
        """Two walks over the bars could disagree about a touch. The thresholds
        are therefore derived from the trade's own MFE and from nothing else."""
        outcome = trades_for_policy(
            baseline_capture, PRODUCTION_GEOMETRY,
            costs=FRICTIONLESS_COSTS, evaluation_window_bars=TAIL_BARS,
        )
        for plan, trade in zip(outcome.plans, outcome.trades, strict=True):
            bars = baseline_capture.bars_by_symbol[trade.symbol]
            measured = measure_outcome(
                plan, trade, bars, evaluation_window_bars=TAIL_BARS
            )
            if trade.mfe_r is None:
                assert measured.reached_r == ()
                continue
            assert all(threshold <= trade.mfe_r for threshold in measured.reached_r)


class TestCaptureDeterminism:
    def test_two_captures_over_the_same_rows_agree_exactly(self, baseline_capture) -> None:
        assert _fingerprint(_capture(all_rows())) == _fingerprint(baseline_capture)

    def test_a_sample_split_selects_rather_than_recomputes(self, baseline_capture) -> None:
        narrowed = baseline_capture.for_symbols(["BTCUSDT"])
        assert {item.symbol for item in narrowed.candidates} == {"BTCUSDT"}
        # Identity, not equality: the split hands back the same frozen objects,
        # so a development sample and a holdout cannot see different facts.
        originals = [c for c in baseline_capture.candidates if c.symbol == "BTCUSDT"]
        assert all(a is b for a, b in zip(narrowed.candidates, originals, strict=True))

    def test_a_split_naming_an_unknown_symbol_is_refused(self, baseline_capture) -> None:
        with pytest.raises(SwingLabError, match="holds no candidates for"):
            baseline_capture.for_symbols(["DOGEUSDT"])

    def test_capture_order_is_identity_based_not_iteration_based(
        self, baseline_capture
    ) -> None:
        keys = [
            (item.symbol, item.signal_at, item.setup_id)
            for item in baseline_capture.candidates
        ]
        assert keys == sorted(keys)

    def test_capture_order_does_not_depend_on_the_order_symbols_were_requested(
        self, baseline_capture
    ) -> None:
        """The property the sort exists for. Requesting the universe backwards
        must produce byte-identical candidates, or a study's digest would depend
        on how its command line was typed."""
        window = window_for()
        reversed_capture = capture_geometry_candidates(
            tuple(reversed(SYMBOLS)),
            BASELINE_VARIANT,
            window=window,
            segments=segments_for(window),
            dataset=dataset_for(all_rows()),
            limit=LIMIT,
        )
        assert _fingerprint(reversed_capture) == _fingerprint(baseline_capture)

    def test_the_signal_index_points_at_the_bar_that_produced_the_signal(
        self, baseline_capture
    ) -> None:
        """An ABSOLUTE check, not a comparison between two captures. An index
        shifted by one would move every entry a bar into the future and would
        cancel out of any test that compared one capture against another."""
        for item in baseline_capture.candidates:
            bars = baseline_capture.bars_by_symbol[item.symbol]
            assert bars[item.signal_index].open_time == item.signal_at

    def test_the_entry_bar_is_strictly_after_the_signal_bar(
        self, baseline_capture
    ) -> None:
        outcome = trades_for_policy(
            baseline_capture, PRODUCTION_GEOMETRY,
            costs=FRICTIONLESS_COSTS, evaluation_window_bars=TAIL_BARS,
        )
        for plan, trade in zip(outcome.plans, outcome.trades, strict=True):
            if trade.entry_at is None:
                continue
            bars = baseline_capture.bars_by_symbol[trade.symbol]
            assert trade.entry_at == bars[plan.candidate.signal_index + 1].open_time
            assert trade.entry_at > trade.signal_at
