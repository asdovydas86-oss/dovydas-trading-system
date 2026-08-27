"""Milestone CA's null construction: matching, seeding, and what it refuses.

The matching rule IS the null. A control drawn from the wrong volatility band,
the wrong period or the wrong symbol would let the admission engine beat
something it was never compared against, and an unseeded draw would make the
whole study irreproducible. Every constraint the pre-registration sealed is
asserted here, and each is additionally shown to be LOAD-BEARING — a test that
passes because the fixture happens to satisfy the constraint anyway proves
nothing, so each constraint is also shown to exclude something.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fmis.swing_lab.admission import AdmissionStage, DecisionInstant
from fmis.swing_lab.admission_matching import (
    OPPOSITE_DIRECTION,
    build_pool_index,
    derive_seed,
    eligible_pool,
    match_admission,
)
from fmis.swing_lab.admission_preregistration import (
    CA_NULL_FAMILIES,
    CA_PRE_REGISTRATION,
    CaControlSource,
    CaDirectionRule,
    CaNullFamily,
)
from fmis.swing_lab.models import SwingLabError
from fmis.swing_setup.models import Direction

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
MATCHING = CA_PRE_REGISTRATION.matching
RANDOMISATION = CA_PRE_REGISTRATION.randomisation
FAMILY = {item.family_id: item for item in CA_NULL_FAMILIES}


def instant(
    bar_index: int,
    *,
    stage: AdmissionStage = AdmissionStage.UNCONFIRMED,
    atr: float = 1.0,
    symbol: str = "BTCUSDT",
    direction: Direction | None = Direction.LONG,
    sample: str = "development",
) -> DecisionInstant:
    return DecisionInstant(
        symbol=symbol,
        sample=sample,
        as_of=T0 + timedelta(hours=4 * bar_index),
        bar_index=bar_index,
        stage=stage,
        direction=direction if stage.has_direction else None,
        close=100.0,
        atr=atr,
        context_regime_structure="trending",
        context_regime_volatility="steady",
        context_structural_trend="sustained_higher",
        setup_structural_trend="sustained_higher",
        evidence_state="proceed",
    )


def _pool(*instants: DecisionInstant):
    return build_pool_index(
        instants,
        stages=frozenset(
            item for item in AdmissionStage if item is not AdmissionStage.ADMITTED
        ),
    )


class TestTheSeedIsDerivedFromIdentity:
    def test_the_same_identity_gives_the_same_seed(self) -> None:
        args = dict(
            master=1, family_id="f", sample="development", symbol="BTCUSDT",
            bar_index=100, replicate=7,
        )
        assert derive_seed(**args) == derive_seed(**args)

    @pytest.mark.parametrize(
        "field,value",
        [
            ("master", 2),
            ("family_id", "other"),
            ("sample", "holdout"),
            ("symbol", "ETHUSDT"),
            ("bar_index", 101),
            ("replicate", 8),
        ],
    )
    def test_every_component_of_the_identity_moves_the_seed(
        self, field: str, value
    ) -> None:
        """If a component did not move it, two different draws would collide."""
        args = dict(
            master=1, family_id="f", sample="development", symbol="BTCUSDT",
            bar_index=100, replicate=7,
        )
        assert derive_seed(**args) != derive_seed(**{**args, field: value})

    def test_the_seed_survives_a_different_hash_seed(self) -> None:
        """Python's salted `hash` would not. This is why SHA-256 is used."""
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        seen = set()
        for hash_seed in ("0", "1", "12345"):
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from fmis.swing_lab.admission_matching import derive_seed;"
                    "print(derive_seed(master=1, family_id='f', sample='s',"
                    "symbol='BTCUSDT', bar_index=100, replicate=7))",
                ],
                capture_output=True, text=True, cwd=root,
                env={"PYTHONHASHSEED": hash_seed, "PATH": ""},
            )
            assert result.returncode == 0, result.stderr
            seen.add(result.stdout.strip())
        assert len(seen) == 1

    def test_a_negative_replicate_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="non-negative"):
            derive_seed(
                master=1, family_id="f", sample="s", symbol="B", bar_index=1,
                replicate=-1,
            )

    def test_a_boolean_master_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="must be an int"):
            derive_seed(
                master=True, family_id="f", sample="s", symbol="B", bar_index=1,
                replicate=0,
            )


class TestTheMatchingConstraintsAreLoadBearing:
    def test_a_control_nearer_than_the_evaluation_window_is_excluded(self) -> None:
        """The single most important constraint: a nearer control would share
        forward bars with its own admission."""
        admission = instant(1000, stage=AdmissionStage.ADMITTED)
        near = instant(1000 + MATCHING.minimum_separation_bars - 1)
        far = instant(1000 + MATCHING.minimum_separation_bars)
        pool = eligible_pool(admission, _pool(near, far), matching=MATCHING, radius=540)
        assert [item.bar_index for item in pool] == [far.bar_index]

    def test_a_control_beyond_the_radius_is_excluded(self) -> None:
        admission = instant(3000, stage=AdmissionStage.ADMITTED)
        inside = instant(3000 - 540)
        outside = instant(3000 - 541)
        pool = eligible_pool(
            admission, _pool(inside, outside), matching=MATCHING, radius=540
        )
        assert [item.bar_index for item in pool] == [inside.bar_index]

    def test_a_control_outside_the_volatility_band_is_excluded(self) -> None:
        import math

        admission = instant(1000, stage=AdmissionStage.ADMITTED, atr=1.0)
        inside = instant(1200, atr=math.exp(MATCHING.atr_log_tolerance) * 0.999)
        outside = instant(1300, atr=math.exp(MATCHING.atr_log_tolerance) * 1.001)
        pool = eligible_pool(
            admission, _pool(inside, outside), matching=MATCHING, radius=540
        )
        assert [item.bar_index for item in pool] == [inside.bar_index]

    def test_the_band_is_symmetric_in_log_space(self) -> None:
        import math

        admission = instant(1000, stage=AdmissionStage.ADMITTED, atr=1.0)
        low = instant(1200, atr=math.exp(-MATCHING.atr_log_tolerance) * 1.001)
        high = instant(1300, atr=math.exp(MATCHING.atr_log_tolerance) * 0.999)
        pool = eligible_pool(
            admission, _pool(low, high), matching=MATCHING, radius=540
        )
        assert len(pool) == 2

    def test_another_symbol_is_never_in_the_pool(self) -> None:
        admission = instant(1000, stage=AdmissionStage.ADMITTED)
        other = instant(1200, symbol="ETHUSDT")
        pool = eligible_pool(admission, _pool(other), matching=MATCHING, radius=540)
        assert pool == ()

    def test_an_admitted_instant_is_never_a_control(self) -> None:
        """A null containing FMITS admissions is partly FMITS against itself."""
        admission = instant(1000, stage=AdmissionStage.ADMITTED)
        another = instant(1200, stage=AdmissionStage.ADMITTED)
        ordinary = instant(1300)
        index = build_pool_index(
            (admission, another, ordinary),
            stages=frozenset(item for item in AdmissionStage),
        )
        pool = eligible_pool(admission, index, matching=MATCHING, radius=540)
        assert [item.bar_index for item in pool] == [1300]

    def test_confirmed_repeats_are_deliberately_kept_in_the_broad_pool(self) -> None:
        """They are moments the engine did NOT admit. Removing them would make
        the null easier by discarding its most signal-like members."""
        admission = instant(1000, stage=AdmissionStage.ADMITTED)
        repeat = instant(1200, stage=AdmissionStage.CONFIRMED_REPEAT)
        pool = eligible_pool(admission, _pool(repeat), matching=MATCHING, radius=540)
        assert [item.bar_index for item in pool] == [1200]

    def test_the_unconfirmed_pool_holds_only_unconfirmed_instants(self) -> None:
        index = build_pool_index(
            (
                instant(1200, stage=AdmissionStage.UNCONFIRMED),
                instant(1300, stage=AdmissionStage.CONFIRMED_REPEAT),
                instant(1400, stage=AdmissionStage.REGIME_BLOCKED),
            ),
            stages=frozenset({AdmissionStage.UNCONFIRMED}),
        )
        admission = instant(1000, stage=AdmissionStage.ADMITTED)
        pool = eligible_pool(admission, index, matching=MATCHING, radius=2160)
        assert [item.bar_index for item in pool] == [1200]

    def test_a_bad_radius_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="positive int"):
            eligible_pool(
                instant(1000, stage=AdmissionStage.ADMITTED), _pool(),
                matching=MATCHING, radius=0,
            )

    def test_it_refuses_a_foreign_admission_type(self) -> None:
        with pytest.raises(TypeError):
            eligible_pool(object(), _pool(), matching=MATCHING, radius=540)  # type: ignore[arg-type]


class TestDrawing:
    def _admission(self):
        return instant(2000, stage=AdmissionStage.ADMITTED)

    def _wide_pool(self, count: int = 40):
        return _pool(*[instant(2000 + 60 + i * 5) for i in range(count)])

    def test_a_matched_admission_draws_the_sealed_number_of_controls(self) -> None:
        matched = match_admission(
            self._admission(), self._wide_pool(),
            family=FAMILY["ca_null_matched_timing"],
            matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
        )
        assert matched.is_matched
        assert len(matched.draws) == RANDOMISATION.draws_per_admission

    def test_every_drawn_control_satisfies_every_constraint(self) -> None:
        admission = self._admission()
        index = self._wide_pool()
        allowed = {
            item.bar_index
            for item in eligible_pool(admission, index, matching=MATCHING, radius=540)
        }
        matched = match_admission(
            admission, index, family=FAMILY["ca_null_matched_timing"],
            matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
        )
        for draw in matched.draws:
            assert draw.instant is not None
            assert draw.instant.bar_index in allowed

    def test_a_thin_pool_is_unmatched_rather_than_matched_against_nothing(self) -> None:
        thin = _pool(*[instant(2000 + 60 + i * 5) for i in range(MATCHING.minimum_pool - 1)])
        matched = match_admission(
            self._admission(), thin, family=FAMILY["ca_null_matched_timing"],
            matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
        )
        assert not matched.is_matched
        assert matched.draws == ()
        assert "below the sealed minimum" in (matched.unmatched_reason or "")

    def test_the_radius_escalates_only_when_the_tight_tier_is_thin(self) -> None:
        """Tier 0 when it can populate; a wider tier only when it cannot."""
        tight = self._wide_pool()
        assert (
            match_admission(
                self._admission(), tight, family=FAMILY["ca_null_matched_timing"],
                matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
            ).radius_tier
            == 0
        )
        distant = _pool(*[instant(2000 + 600 + i * 5) for i in range(40)])
        assert (
            match_admission(
                self._admission(), distant, family=FAMILY["ca_null_matched_timing"],
                matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
            ).radius_tier
            == 1
        )

    def test_two_runs_with_the_same_seed_draw_the_same_controls(self) -> None:
        def draw(seed: int):
            return [
                (item.replicate, item.instant.bar_index, item.direction)
                for item in match_admission(
                    self._admission(), self._wide_pool(),
                    family=FAMILY["ca_null_matched_timing"],
                    matching=MATCHING, randomisation=RANDOMISATION, master_seed=seed,
                ).draws
            ]

        assert draw(1) == draw(1)

    def test_a_different_master_seed_draws_different_controls(self) -> None:
        """Otherwise the seed-stability criterion would be vacuous."""
        def draw(seed: int):
            return [
                item.instant.bar_index
                for item in match_admission(
                    self._admission(), self._wide_pool(),
                    family=FAMILY["ca_null_matched_timing"],
                    matching=MATCHING, randomisation=RANDOMISATION, master_seed=seed,
                ).draws
            ]

        assert draw(1) != draw(2)

    def test_a_same_bar_family_draws_no_instant_and_is_always_matched(self) -> None:
        matched = match_admission(
            self._admission(), _pool(),
            family=FAMILY["ca_null_opposite_direction"],
            matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
        )
        assert matched.is_matched
        assert all(item.instant is None for item in matched.draws)

    def test_the_opposite_family_always_reverses_the_side(self) -> None:
        matched = match_admission(
            self._admission(), _pool(),
            family=FAMILY["ca_null_opposite_direction"],
            matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
        )
        assert {item.direction for item in matched.draws} == {Direction.SHORT}

    def test_the_fmits_family_always_keeps_the_side(self) -> None:
        matched = match_admission(
            self._admission(), self._wide_pool(),
            family=FAMILY["ca_null_matched_timing"],
            matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
        )
        assert {item.direction for item in matched.draws} == {Direction.LONG}

    def test_the_random_family_flips_a_fair_coin(self) -> None:
        matched = match_admission(
            self._admission(), _pool(),
            family=FAMILY["ca_null_random_direction_same_bar"],
            matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
        )
        longs = sum(1 for item in matched.draws if item.direction is Direction.LONG)
        # 200 fair flips landing outside [60, 140] would be a broken coin.
        assert 60 < longs < 140

    def test_the_gate_family_uses_each_controls_own_direction(self) -> None:
        index = build_pool_index(
            tuple(
                instant(
                    2000 + 60 + i * 5,
                    direction=Direction.SHORT if i % 2 else Direction.LONG,
                )
                for i in range(40)
            ),
            stages=frozenset({AdmissionStage.UNCONFIRMED}),
        )
        matched = match_admission(
            self._admission(), index,
            family=FAMILY["ca_null_eligible_but_rejected"],
            matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
        )
        for draw in matched.draws:
            assert draw.instant is not None
            assert draw.direction is draw.instant.direction

    def test_matching_anything_but_an_admission_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="compare two nulls"):
            match_admission(
                instant(2000, stage=AdmissionStage.UNCONFIRMED), self._wide_pool(),
                family=FAMILY["ca_null_matched_timing"],
                matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
            )

    def test_a_foreign_family_type_is_refused(self) -> None:
        with pytest.raises(TypeError):
            match_admission(
                self._admission(), self._wide_pool(), family=object(),  # type: ignore[arg-type]
                matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
            )

    def test_a_control_own_direction_family_refuses_a_directionless_control(
        self,
    ) -> None:
        """A rung below the family tally has no production direction to read.

        Probed against `_direction_for` directly, because after defect CA-D3 was
        fixed this case is **unreachable through `match_admission`**: the pool
        guard rejects a non-`UNCONFIRMED` index first, and `DecisionInstant`
        refuses a directional stage carrying no direction. The refusal is kept
        as defence in depth and is tested where it can still be reached.
        """
        from random import Random

        from fmis.swing_lab.admission_matching import _direction_for

        with pytest.raises(SwingLabError, match="no production direction"):
            _direction_for(
                FAMILY["ca_null_eligible_but_rejected"],
                instant(2000, stage=AdmissionStage.ADMITTED),
                None,
                Random(1),
            )

    def test_the_pool_guard_fires_before_the_direction_refusal(self) -> None:
        """Defect CA-D3: a family measured against a pool its seal does not name
        is refused by name, and refused EARLY."""
        index = build_pool_index(
            tuple(
                instant(2000 + 60 + i * 5, stage=AdmissionStage.REGIME_BLOCKED)
                for i in range(40)
            ),
            stages=frozenset({AdmissionStage.REGIME_BLOCKED}),
        )
        with pytest.raises(SwingLabError, match="does not name"):
            match_admission(
                instant(2000, stage=AdmissionStage.ADMITTED), index,
                family=FAMILY["ca_null_eligible_but_rejected"],
                matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
            )


def test_the_opposite_map_is_total_and_involutive() -> None:
    for direction in Direction:
        assert OPPOSITE_DIRECTION[OPPOSITE_DIRECTION[direction]] is direction


class TestNoLookahead:
    """A control's identity may depend only on information at or before its own
    matched decision point. These prove it, each with a non-vacuity control."""

    def test_a_control_is_chosen_without_any_bar_ever_being_supplied(self) -> None:
        """The structural half of the proof: `eligible_pool` and
        `match_admission` are never handed a bar, so they cannot read one."""
        import inspect

        for function in (eligible_pool, match_admission):
            parameters = set(inspect.signature(function).parameters)
            assert "bars" not in parameters
            assert "outcome" not in parameters

    def test_the_matching_module_imports_neither_a_bar_nor_an_outcome(self) -> None:
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "src" / "fmis" / "swing_lab" / "admission_matching.py"
        ).read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.update(f"{node.module}.{a.name}" for a in node.names)
        assert not any("PriceBar" in name for name in imported)
        assert not any("ForwardOutcome" in name for name in imported)

    def test_a_decision_instant_carries_no_bar_and_no_outcome(self) -> None:
        fields = set(DecisionInstant.__dataclass_fields__)
        for forbidden in ("bars", "forward", "outcome", "mfe", "mae", "future"):
            assert forbidden not in fields

    def test_the_pool_is_unchanged_by_anything_after_the_admission(self) -> None:
        """Non-vacuity: an instant BEFORE the admission does change the pool."""
        admission = instant(2000, stage=AdmissionStage.ADMITTED)
        base = [instant(2000 + 60 + i * 5) for i in range(40)]
        before = instant(2000 - 100)
        without = eligible_pool(
            admission, _pool(*base), matching=MATCHING, radius=540
        )
        with_earlier = eligible_pool(
            admission, _pool(*base, before), matching=MATCHING, radius=540
        )
        assert len(with_earlier) == len(without) + 1
