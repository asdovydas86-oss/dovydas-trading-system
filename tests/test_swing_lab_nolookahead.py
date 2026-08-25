"""No-lookahead, proved over a synthetic path where the future is known and mutable.

A backtest cannot prove the absence of lookahead by inspection: the leak is
always an ordinary-looking read of a series that happens to extend past the
instant being decided. So this file proves it the only way that survives a
refactor — **by changing the future and requiring the past not to notice.**

Three mutations, each targeting a different way a leak could enter:

* candles **after** the measurement window — a leak here would let the outcome
  tail influence the decisions it is supposed to judge;
* candles **inside** the measurement window but after a cutoff — a leak here
  would let a later measured bar alter an earlier one's assessment;
* candles in the **warm-up prefix** — where a change *must* propagate, because a
  harness that ignored its own warm-up would be analysing a shorter window than
  production does. This is the control that stops the first two tests from
  passing vacuously on a harness that reads nothing at all.

The fixture is Milestone BC's own synthetic 4H path, resampled into genuinely
correlated 1D and 1W roles, reused rather than rebuilt.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fmis.swing_lab.replay import replay_variant_group
from fmis.swing_lab.trades import FRICTIONLESS_COSTS
from fmis.swing_lab.variants import (
    BASELINE_VARIANT,
    CONTEXT_ONLY_VARIANT,
    CORE_1D4H_VARIANT,
    HARD_GATE_CONTROL_VARIANT,
)
from fmis.swing_setup.backtest_replay import prepare_replay_index
from fmis.swing_setup.research_harness import (
    DEFAULT_IDENTITY_PRIMING_BARS,
    ResearchDataset,
    build_segments,
)
from fmis.swing_setup.research_models import ResearchWindow
from fmis.swing_setup.research_warmup import derive_warmup
from fmis.swing_lab.variants import PRODUCTION_INTERVALS

from tests.test_swing_setup_backtest import (
    _FOUR_HOURS_MS,
    resampled_rows,
    zigzag_rows,
)

_UTC = timezone.utc
_BASE = datetime(2024, 1, 1, tzinfo=_UTC)
_FOUR_HOURS = timedelta(hours=4)
_BARS_PER_DAY = 6
_BARS_PER_WEEK = 42

#: 200 rather than the harness default of 250. Lowering it further would not
#: shorten the fixture: `derive_warmup` takes the MAXIMUM over the production
#: dependencies, and EMA(200) — a real one — binds at 200 bars however small the
#: requested analysis window is. A first draft of this fixture used 60 and was
#: silently under-warmed; `run_lab_study`'s availability probe refused it, which
#: is the derivation doing exactly the job Milestone BC built it for.
_TEST_LIMIT = 200
_WARM_BARS = _TEST_LIMIT * _BARS_PER_WEEK + DEFAULT_IDENTITY_PRIMING_BARS
_MEASURED_BARS = 120
_TAIL_BARS = 40
_TOTAL_BARS = _WARM_BARS + _MEASURED_BARS + _TAIL_BARS + 20

MEASUREMENT_START = _BASE + _WARM_BARS * _FOUR_HOURS
MEASUREMENT_END = MEASUREMENT_START + _MEASURED_BARS * _FOUR_HOURS
RUN_AT = datetime(2030, 1, 1, tzinfo=_UTC)

VARIANTS = (
    BASELINE_VARIANT,
    HARD_GATE_CONTROL_VARIANT,
    CONTEXT_ONLY_VARIANT,
    CORE_1D4H_VARIANT,
)


def _rows(count: int = _TOTAL_BARS) -> dict[str, list[list]]:
    """One 4H path, resampled up — so the three roles are genuinely correlated."""
    rows_4h = zigzag_rows(
        count,
        start_ms=int(_BASE.timestamp() * 1000),
        interval_ms=_FOUR_HOURS_MS,
        base=100.0,
        linear_drift_per_bar=0.15,
    )
    return {
        "4h": rows_4h,
        "1d": resampled_rows(rows_4h, bars_per_period=_BARS_PER_DAY),
        "1w": resampled_rows(rows_4h, bars_per_period=_BARS_PER_WEEK),
    }


def _dataset(rows: dict[str, list[list]]) -> ResearchDataset:
    cache = {("BTCUSDT", interval): data for interval, data in rows.items()}
    return ResearchDataset(
        cache=cache,
        index=prepare_replay_index(cache),
        boundaries=(),
        fetch_starts={},
        fetched_at=RUN_AT,
    )


def _replay(rows: dict[str, list[list]], *, measurement_end: datetime = MEASUREMENT_END):
    warmup = derive_warmup(PRODUCTION_INTERVALS, limit=_TEST_LIMIT)
    window = ResearchWindow(
        warmup_start=_BASE,
        measurement_start=MEASUREMENT_START,
        measurement_end=measurement_end,
        outcome_tail_end=measurement_end + _TAIL_BARS * _FOUR_HOURS,
    )
    return replay_variant_group(
        ["BTCUSDT"],
        VARIANTS,
        window=window,
        warmup=warmup,
        segments=build_segments(window),
        dataset=_dataset(rows),
        costs=FRICTIONLESS_COSTS,
        evaluation_window_bars=_TAIL_BARS,
        limit=_TEST_LIMIT,
        gate_counterfactual_id=CONTEXT_ONLY_VARIANT.variant_id,
    )


def _scale(rows: list[list], start: int, factor: float) -> list[list]:
    """Every price from ``start`` onward, multiplied. Open/high/low/close alike."""
    mutated = [list(row) for row in rows]
    for row in mutated[start:]:
        for price_index in (1, 2, 3, 4):
            row[price_index] = f"{float(row[price_index]) * factor:.8f}"
    return mutated


def _states(replays) -> list[tuple]:
    return [
        (
            replay.variant.variant_id,
            item.symbol,
            item.as_of,
            item.state,
            item.direction,
            item.setup_id,
        )
        for replay in replays
        for item in replay.observations
    ]


@pytest.fixture(scope="module")
def baseline_run():
    return _replay(_rows())


class TestTheFixtureIsCapableOfFailing:
    """If the fixture produced no setups, every test below would pass vacuously."""

    def test_the_replay_produces_measured_observations(self, baseline_run) -> None:
        replays, _ = baseline_run
        for replay in replays:
            assert replay.measured_observations, replay.variant.variant_id

    def test_at_least_one_variant_reaches_a_directional_state(self, baseline_run) -> None:
        replays, _ = baseline_run
        assert any(
            item.direction is not None
            for replay in replays
            for item in replay.measured_observations
        ), "a fixture with no direction cannot detect a directional leak"

    def test_the_gate_was_actually_exercised(self, baseline_run) -> None:
        _, gates = baseline_run
        assert gates, "no gate observation means the attribution was never run"


class TestNoLookahead:
    def test_mutating_the_outcome_tail_cannot_change_any_observation(
        self, baseline_run
    ) -> None:
        """Candles after the measurement window may not reach a decision."""
        rows = _rows()
        cutoff = _WARM_BARS + _MEASURED_BARS
        mutated = {**rows, "4h": _scale(rows["4h"], cutoff, 1000.0)}
        replays, _ = baseline_run
        mutated_replays, _ = _replay(mutated)
        assert _states(mutated_replays) == _states(replays)

    def test_mutating_later_measured_candles_cannot_change_earlier_ones(self) -> None:
        """A measured bar may not be influenced by a measured bar after it."""
        rows = _rows()
        cutoff = _WARM_BARS + 60
        early_end = _BASE + cutoff * _FOUR_HOURS
        original, _ = _replay(rows, measurement_end=early_end)
        mutated = {**rows, "4h": _scale(rows["4h"], cutoff, 1000.0)}
        changed, _ = _replay(mutated, measurement_end=early_end)
        assert _states(changed) == _states(original)

    def test_the_gate_attribution_is_also_free_of_lookahead(self, baseline_run) -> None:
        rows = _rows()
        cutoff = _WARM_BARS + _MEASURED_BARS
        mutated = {**rows, "4h": _scale(rows["4h"], cutoff, 1000.0)}
        _, gates = baseline_run
        _, mutated_gates = _replay(mutated)
        assert mutated_gates == gates

    def test_a_warmup_mutation_DOES_propagate(self) -> None:
        """The control. A harness that ignored its warm-up would fail this.

        Without it, a replay that read no candles at all would pass every test
        above — the two mutations would change nothing precisely because
        nothing was ever read.
        """
        rows = _rows()
        mutated = {**rows, "4h": _scale(rows["4h"], _WARM_BARS - 200, 1.5)}
        # The 1d/1w roles are resampled from 4h, so a 4H warm-up change must
        # reach every role — which is what makes this a real control.
        mutated["1d"] = resampled_rows(mutated["4h"], bars_per_period=_BARS_PER_DAY)
        mutated["1w"] = resampled_rows(mutated["4h"], bars_per_period=_BARS_PER_WEEK)
        original, _ = _replay(rows)
        changed, _ = _replay(mutated)
        assert _states(changed) != _states(original)


class TestFactsAreSharedAndPoliciesAreNot:
    def test_the_control_variant_matches_the_baseline_observation_for_observation(
        self, baseline_run
    ) -> None:
        replays, _ = baseline_run
        by_id = {replay.variant.variant_id: replay for replay in replays}
        baseline = by_id["swing_current"].observations
        control = by_id["swing_1w_hard_gate"].observations
        assert len(baseline) == len(control)
        for left, right in zip(baseline, control, strict=True):
            assert (left.state, left.direction, left.as_of) == (
                right.state,
                right.direction,
                right.as_of,
            )

    def test_the_control_produces_identical_trades(self, baseline_run) -> None:
        replays, _ = baseline_run
        by_id = {replay.variant.variant_id: replay for replay in replays}
        baseline = by_id["swing_current"].trades
        control = by_id["swing_1w_hard_gate"].trades
        assert len(baseline) == len(control)
        for left, right in zip(baseline, control, strict=True):
            assert (left.signal_at, left.net_r, left.exit_reason) == (
                right.signal_at,
                right.net_r,
                right.exit_reason,
            )

    def test_every_variant_saw_the_same_instants(self, baseline_run) -> None:
        """Facts are shared, so no variant may skip or invent an instant."""
        replays, _ = baseline_run
        instants = {
            replay.variant.variant_id: [item.as_of for item in replay.observations]
            for replay in replays
        }
        reference = instants["swing_current"]
        for variant_id, seen in instants.items():
            assert seen == reference, variant_id

    def test_removing_the_gate_never_reduces_the_directional_count(
        self, baseline_run
    ) -> None:
        """A strictly weaker refusal cannot produce strictly fewer directions."""
        replays, _ = baseline_run
        by_id = {replay.variant.variant_id: replay for replay in replays}
        directional = {
            key: sum(
                1
                for item in replay.measured_observations
                if item.direction is not None
            )
            for key, replay in by_id.items()
        }
        assert directional["swing_1w_context"] >= directional["swing_current"]

    def test_each_variant_stamps_its_own_policy_id_on_every_observation(
        self, baseline_run
    ) -> None:
        replays, _ = baseline_run
        for replay in replays:
            stamped = {item.policy_id for item in replay.observations}
            assert stamped == {replay.variant.policy_id}, replay.variant.variant_id


class TestDeterminism:
    def test_two_identical_replays_agree_exactly(self) -> None:
        rows = _rows()
        assert _states(_replay(rows)[0]) == _states(_replay(rows)[0])


# ---------------------------------------------------------------------------
# End to end, offline
# ---------------------------------------------------------------------------


class TestTheWholeStudyRunsOffline:
    """`run_lab_study` end to end against a fake transport.

    Exercises the parts `replay_variant_group` alone cannot: per-group warm-up
    derivation, the availability probe and its refusal, the fetch, the manifest
    and the digest. No network, so it is deterministic and fast.
    """

    @staticmethod
    def _study(**overrides):
        from fmis.swing_lab.study import run_lab_study
        from tests.test_swing_setup_research import binance_like_transport

        rows = _rows()
        cache = {("BTCUSDT", interval): data for interval, data in rows.items()}
        kwargs = dict(
            symbols=["BTCUSDT"],
            measurement_start=MEASUREMENT_START,
            measurement_end=MEASUREMENT_END,
            run_at=RUN_AT,
            experiment_id="offline-1",
            variants=(BASELINE_VARIANT, CONTEXT_ONLY_VARIANT),
            limit=_TEST_LIMIT,
            evaluation_window_bars=_TAIL_BARS,
            transport=binance_like_transport(cache),
        )
        kwargs.update(overrides)
        return run_lab_study(**kwargs)

    def test_a_whole_study_completes_and_carries_a_manifest(self) -> None:
        study = self._study()
        manifest = study.manifest
        assert manifest.experiment_id == "offline-1"
        assert manifest.symbols == ("BTCUSDT",)
        assert manifest.interval_groups == (("1w", "1d", "4h"),)
        assert manifest.result_digest
        assert manifest.warmup_start < manifest.measurement_start
        assert manifest.outcome_tail_end > manifest.measurement_end
        assert any(item.startswith("BW-2") for item in manifest.limitations)

    def test_rerunning_the_same_study_reproduces_the_digest(self) -> None:
        assert self._study().manifest.result_digest == self._study().manifest.result_digest

    def test_the_manifest_records_the_constants_that_shaped_the_run(self) -> None:
        manifest = self._study().manifest
        assert manifest.candle_limit == _TEST_LIMIT
        assert manifest.minimum_agreeing_families == 2
        assert manifest.confirmation_lookback_bars == 10
        assert manifest.cost_policy["policy_id"] == "swing-lab-frictionless"

    def test_the_gate_impact_is_measured_over_the_measured_window_only(self) -> None:
        study = self._study()
        assert study.gate.instants > 0
        assert study.gate.counterfactual_variant_id == CONTEXT_ONLY_VARIANT.variant_id
        assert study.gate.baseline_variant_id == BASELINE_VARIANT.variant_id

    def test_an_unsatisfiable_window_is_refused_with_the_shortfall(self) -> None:
        from fmis.swing_lab.models import SwingLabError

        with pytest.raises(SwingLabError, match="not satisfiable"):
            self._study(measurement_start=_BASE + timedelta(hours=4))

    def test_an_unsatisfiable_window_can_be_inspected_deliberately(self) -> None:
        study = self._study(
            measurement_start=MEASUREMENT_START - 400 * _FOUR_HOURS,
            require_availability=False,
        )
        assert study.manifest.result_digest

    def test_a_study_can_be_written_and_read_back(self, tmp_path) -> None:
        from fmis.swing_lab.artifact import read_artifact, verify_digest, write_study

        study = self._study()
        artifact = read_artifact(write_study(study, tmp_path / "offline.lab.json"))
        assert verify_digest(artifact)
        assert set(artifact.variant_ids) == {
            BASELINE_VARIANT.variant_id,
            CONTEXT_ONLY_VARIANT.variant_id,
        }
