"""The timeline collector, and the one property that makes it safe to add.

Milestone BZ needed structural state at every bar, and the cheap way to get it
would have been a second replay. A second replay is the *wrong* way: two walks
over the same history can differ for provider reasons, and every BZ claim about
a state transition would then rest on comparing two datasets rather than one.

So `capture_geometry_candidates` grew an ``observer`` sink. The load-bearing
test in this file is `test_the_observer_cannot_change_the_capture`: a capture
taken with a collector attached must be **identical**, candidate for candidate
and bar for bar, to one taken without. If that ever fails, Milestones BX and BY
are no longer reproducible from this code and nothing BZ measures can be read
against them.

The fixture is `tests.swing_lab_geometry_fixture` — the same synthetic dataset
BX's own no-lookahead suite replays — reused rather than restated so a change to
the warm-up derivation moves both suites together.
"""

from __future__ import annotations

import pytest

from fmis.swing_lab.geometry_replay import capture_geometry_candidates
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.persistence import ThesisObservation, ThesisTimeline
from fmis.swing_lab.persistence_replay import TimelineCollector, observation_from
from fmis.swing_lab.replay import ReplayInstant
from fmis.swing_lab.variants import BASELINE_VARIANT

from tests.swing_lab_geometry_fixture import (
    LIMIT,
    SYMBOLS,
    all_rows,
    dataset_for,
    segments_for,
    window_for,
)


def _capture(observer=None):
    window = window_for()
    return capture_geometry_candidates(
        SYMBOLS,
        BASELINE_VARIANT,
        window=window,
        segments=segments_for(window),
        dataset=dataset_for(all_rows()),
        limit=LIMIT,
        observer=observer,
    )


@pytest.fixture(scope="module")
def plain():
    return _capture()


@pytest.fixture(scope="module")
def collected():
    collector = TimelineCollector()
    return _capture(collector), collector


class TestTheObserverIsInert:
    """**The regression that protects BX and BY.**"""

    def test_the_observer_cannot_change_the_capture(self, plain, collected) -> None:
        observed, _ = collected
        assert observed.candidates == plain.candidates
        assert observed.bars_by_symbol == plain.bars_by_symbol
        assert observed.admission_variant_id == plain.admission_variant_id
        assert observed.admission_policy_id == plain.admission_policy_id
        assert dict(observed.metadata) == dict(plain.metadata)

    def test_the_candidates_are_not_merely_equal_but_the_same_facts(
        self, plain, collected
    ) -> None:
        """Field-by-field, so an ``__eq__`` that ignored a field could not hide."""
        observed, _ = collected
        for left, right in zip(plain.candidates, observed.candidates, strict=True):
            assert left.symbol == right.symbol
            assert left.signal_at == right.signal_at
            assert left.signal_index == right.signal_index
            assert left.direction == right.direction
            assert left.reference_price == right.reference_price
            assert left.execution_atr == right.execution_atr
            assert left.setup_atr == right.setup_atr
            assert left.execution_stop_levels == right.execution_stop_levels
            assert left.setup_target_levels == right.setup_target_levels

    def test_a_capture_with_no_observer_still_works(self, plain) -> None:
        assert plain.candidates


class TestWhatTheCollectorSees:
    def test_it_observes_more_instants_than_there_are_candidates(
        self, collected
    ) -> None:
        """Every analysable bar, not only the admitted ones. **The whole point.**

        An exit rule acting at bar t needs the structure at bar t whether or not
        bar t admitted a setup, so a collector that only saw admissions would be
        blind at exactly the bars a post-entry decision is taken on.
        """
        capture, collector = collected
        assert collector.observed > len(capture.candidates)

    def test_every_candidate_bar_has_an_observation(self, collected) -> None:
        capture, collector = collected
        timelines = collector.timelines()
        for candidate in capture.candidates:
            timeline = timelines[candidate.symbol]
            assert timeline.at(candidate.signal_index) is not None

    def test_the_observation_at_a_candidate_bar_agrees_with_it(
        self, collected
    ) -> None:
        """The two sides of one instant must describe the same instant."""
        capture, collector = collected
        timelines = collector.timelines()
        for candidate in capture.candidates:
            observation = timelines[candidate.symbol].at(candidate.signal_index)
            assert observation is not None
            assert observation.setup_state == "confirmed"
            assert observation.setup_direction == candidate.direction.value
            assert (
                observation.context_structural_trend
                == candidate.context_structural_trend
            )
            assert (
                observation.setup_structural_trend == candidate.setup_structural_trend
            )
            assert (
                observation.context_regime_structure
                == candidate.context_regime_structure
            )

    def test_the_timelines_cover_every_requested_symbol(self, collected) -> None:
        _, collector = collected
        assert set(collector.timelines()) == set(SYMBOLS)

    def test_a_timeline_is_a_snapshot_not_a_live_view(self, collected) -> None:
        """Mutating the returned mapping cannot corrupt the collector."""
        _, collector = collected
        first = collector.timelines()
        first.clear()
        assert set(collector.timelines()) == set(SYMBOLS)

    def test_the_observations_carry_ordered_levels(self, collected) -> None:
        _, collector = collected
        seen_upper = seen_lower = False
        for timeline in collector.timelines().values():
            for observation in timeline.observations.values():
                assert len(observation.upper_levels) <= 5
                assert len(observation.lower_levels) <= 5
                seen_upper = seen_upper or bool(observation.upper_levels)
                seen_lower = seen_lower or bool(observation.lower_levels)
                for level in observation.upper_levels:
                    assert observation.execution_close is not None
                    assert level.price > observation.execution_close
                for level in observation.lower_levels:
                    assert observation.execution_close is not None
                    assert level.price < observation.execution_close
        assert seen_upper and seen_lower, "the fixture produced no levels either side"

    def test_the_upper_levels_are_nearest_first(self, collected) -> None:
        """Production's own ordering, so a trail and a stop agree about 'nearer'."""
        _, collector = collected
        for timeline in collector.timelines().values():
            for observation in timeline.observations.values():
                prices = [level.price for level in observation.upper_levels]
                assert prices == sorted(prices)
                lows = [level.price for level in observation.lower_levels]
                assert lows == sorted(lows, reverse=True)


class TestTheCollectorRefuses:
    def test_a_duplicated_bar_is_refused_never_overwritten(self) -> None:
        """A last-write-wins would silently halve every transition count."""
        collector = TimelineCollector()
        # Build one real observation, then feed its instant twice.
        window = window_for()
        seen: list[ReplayInstant] = []
        capture_geometry_candidates(
            SYMBOLS, BASELINE_VARIANT, window=window,
            segments=segments_for(window), dataset=dataset_for(all_rows()),
            limit=LIMIT, observer=seen.append,
        )
        assert seen
        collector(seen[0])
        with pytest.raises(SwingLabError, match="two instants for execution bar"):
            collector(seen[0])

    def test_an_instant_with_no_bar_index_is_refused(self) -> None:
        window = window_for()
        seen: list[ReplayInstant] = []
        capture_geometry_candidates(
            SYMBOLS, BASELINE_VARIANT, window=window,
            segments=segments_for(window), dataset=dataset_for(all_rows()),
            limit=LIMIT, observer=seen.append,
        )
        broken = ReplayInstant(
            symbol=seen[0].symbol, as_of=seen[0].as_of, measured=seen[0].measured,
            segment=seen[0].segment, sheet=seen[0].sheet, inputs=seen[0].inputs,
            baseline_assessment=seen[0].baseline_assessment,
            last_timestamp=seen[0].last_timestamp, signal_index=None,
        )
        with pytest.raises(SwingLabError, match="no bar index"):
            observation_from(broken)

    def test_a_non_instant_is_a_type_error(self) -> None:
        with pytest.raises(TypeError, match="ReplayInstant"):
            observation_from(object())  # type: ignore[arg-type]


class TestDeterminism:
    def test_two_collections_agree_exactly(self) -> None:
        """Same dataset, same observations — the property every digest rests on."""
        first = TimelineCollector()
        _capture(first)
        second = TimelineCollector()
        _capture(second)
        left = first.timelines()
        right = second.timelines()
        assert set(left) == set(right)
        for symbol in left:
            assert left[symbol].observations == right[symbol].observations

    def test_the_payload_is_json_safe(self, collected) -> None:
        import json

        _, collector = collected
        for timeline in collector.timelines().values():
            for observation in timeline.observations.values():
                json.dumps(observation.payload())


class TestAWarmingUpViewInventsNothing:
    """A view with no close has no ordering reference, so it reports no levels.

    `ordered_levels` needs a price to measure "nearer" against. When the
    execution view is still warming up there is no such price, and substituting
    one — the bar's own close, zero, the first level — would invent a distance
    the instant did not have.

    **Measured, not argued: the branch is unreachable through the fixture.** All
    1,120 analysable instants in `tests.swing_lab_geometry_fixture` carry a
    close, so a capture-level test could never walk this path and a mutation
    probe against it survived. It is covered directly instead, which is what a
    defensive guard deserves rather than an equivalence claim.
    """

    @staticmethod
    def _instant_with_no_close(instant: ReplayInstant) -> ReplayInstant:
        from dataclasses import replace

        return ReplayInstant(
            symbol=instant.symbol, as_of=instant.as_of, measured=instant.measured,
            segment=instant.segment, sheet=instant.sheet,
            inputs=replace(instant.inputs, execution_close=None),
            baseline_assessment=instant.baseline_assessment,
            last_timestamp=instant.last_timestamp,
            signal_index=instant.signal_index,
        )

    def test_no_close_yields_no_levels_on_either_side(self, collected) -> None:
        _, collector = collected
        window = window_for()
        seen: list[ReplayInstant] = []
        capture_geometry_candidates(
            SYMBOLS, BASELINE_VARIANT, window=window,
            segments=segments_for(window), dataset=dataset_for(all_rows()),
            limit=LIMIT, observer=seen.append,
        )
        # A real instant that DOES have levels, so the assertion is not vacuous.
        rich = next(
            item for item in seen
            if observation_from(item).upper_levels
            or observation_from(item).lower_levels
        )
        assert observation_from(rich).execution_close is not None

        blind = observation_from(self._instant_with_no_close(rich))
        assert blind.execution_close is None
        assert blind.upper_levels == ()
        assert blind.lower_levels == ()

    def test_the_rest_of_the_observation_still_reports(self, collected) -> None:
        """An absent close removes the LEVELS, never the structural reading."""
        window = window_for()
        seen: list[ReplayInstant] = []
        capture_geometry_candidates(
            SYMBOLS, BASELINE_VARIANT, window=window,
            segments=segments_for(window), dataset=dataset_for(all_rows()),
            limit=LIMIT, observer=seen.append,
        )
        original = observation_from(seen[0])
        blind = observation_from(self._instant_with_no_close(seen[0]))
        assert blind.setup_structural_trend == original.setup_structural_trend
        assert blind.context_regime_structure == original.context_regime_structure
        assert blind.bar_index == original.bar_index
