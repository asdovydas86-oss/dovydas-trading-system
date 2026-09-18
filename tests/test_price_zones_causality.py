"""Price zones — the properties the research result is only worth anything for.

Report 0050 measured **0 illegal prefix events** for the anchored construction,
against 34,192 for growable bands, 120,441 for a diameter-bounded clustering and
983,916 for width read from the latest ATR. That measurement was made on a
research harness. This file asserts the same properties of the **production**
engine, over production `structural_levels` and the production `AverageTrueRange`,
because a property proved of a harness and not of the code that ships is a
property the product does not have.

Each test states the alternative whose refutation it re-earns.

Offline, clock-free and network-free.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from fmis.price_zones import (
    ZONE_WIDTH_POLICY_V1,
    ZoneWidthPolicy,
    ZoneWidthReference,
    ZoneWidthScale,
    derive_price_zones,
)

from tests.price_zone_helpers import (
    atr_series_of,
    level,
    levels_of,
    flat_width_series,
    reflected,
    scaled,
    seeded_series,
    zone_map,
)

#: Four seeds and two shapes — a flat random walk and a trending one. The flat
#: shape piles levels into a few wide bands; the trending shape spreads them out.
#: Both are real behaviours and the invariants must hold over each.
SERIES_CASES = [
    (seed, drift)
    for seed in (3, 7, 11, 19)
    for drift in (0.0, 0.004)
]


def _zones_for(series):
    return derive_price_zones(levels_of(series), atr_series_of(series))


def _identity(zone) -> tuple:
    """A zone's identity for prefix comparison: its band and its anchor.

    Deliberately **not** its membership: a later prefix may legitimately add a
    member, and a test that forbade that would forbid the one thing the design
    does allow.
    """
    return (
        zone.low,
        zone.high,
        zone.width,
        zone.established_index,
        zone.anchor.level.origin.index,
        zone.anchor.level.price,
    )


class TestPrefixStability:
    """A published zone cannot move, shrink, split, merge or vanish. (A)"""

    @pytest.mark.parametrize("seed, drift", SERIES_CASES)
    def test_every_zone_of_a_shorter_prefix_survives_into_a_longer_one(
        self, seed: int, drift: float
    ) -> None:
        full = seeded_series(400, seed=seed, drift=drift)
        for cut in (200, 260, 320, 400):
            shorter = seeded_series(cut, seed=seed, drift=drift)
            # Same seed, so the shorter series is a genuine prefix of the longer.
            assert shorter.candles == full.candles[:cut]
            earlier = _zones_for(shorter)
            later = _zones_for(full)
            established = {zone.established_index for zone in earlier.zones}
            if not established:
                continue
            # ATR's Wilder seed is shared because both runs start at bar 0, so
            # the bands are comparable exactly rather than approximately.
            survivors = {
                _identity(zone)
                for zone in later.zones
                if zone.established_index <= max(established)
            }
            for zone in earlier.zones:
                assert _identity(zone) in survivors, (
                    f"a zone established at bar {zone.established_index} on a "
                    f"{cut}-bar prefix is not present unchanged at 400 bars"
                )

    @pytest.mark.parametrize("seed, drift", SERIES_CASES)
    def test_a_longer_prefix_only_appends_and_never_inserts(
        self, seed: int, drift: float
    ) -> None:
        """Creation order is what makes the published tuple itself prefix-stable."""
        earlier = _zones_for(seeded_series(300, seed=seed, drift=drift))
        later = _zones_for(seeded_series(400, seed=seed, drift=drift))
        count = earlier.zone_count
        assert [_identity(zone) for zone in later.zones[:count]] == [
            _identity(zone) for zone in earlier.zones
        ]

    @pytest.mark.parametrize("seed, drift", SERIES_CASES)
    def test_membership_already_written_is_never_rewritten(
        self, seed: int, drift: float
    ) -> None:
        """A zone may gain a member. It may not lose one or reorder them."""
        earlier = _zones_for(seeded_series(300, seed=seed, drift=drift))
        later = _zones_for(seeded_series(400, seed=seed, drift=drift))
        for before, after in zip(earlier.zones, later.zones):
            assert _identity(before) == _identity(after)
            keys_before = [
                (member.level.origin.index, member.joined_index, member.level.price)
                for member in before.members
            ]
            keys_after = [
                (member.level.origin.index, member.joined_index, member.level.price)
                for member in after.members
            ]
            assert keys_after[: len(keys_before)] == keys_before

    def test_a_level_arriving_later_joins_without_disturbing_what_was_written(
        self,
    ) -> None:
        """The one legitimate change: a new member, and nothing else."""
        widths = flat_width_series(4.0)
        before = derive_price_zones([level(100.0, index=20)], widths)
        after = derive_price_zones(
            [level(100.0, index=20), level(100.4, index=60)], widths
        )
        assert _identity(before.zones[0]) == _identity(after.zones[0])
        assert before.zones[0].member_count == 1
        assert after.zones[0].member_count == 2


class TestNoLookahead:
    """Today's volatility cannot reach yesterday's band. (B)"""

    @pytest.mark.parametrize("seed, drift", SERIES_CASES)
    def test_extending_the_series_leaves_every_existing_band_the_same_size(
        self, seed: int, drift: float
    ) -> None:
        """983,916 illegal prefix events were measured for width from latest ATR."""
        earlier = _zones_for(seeded_series(300, seed=seed, drift=drift))
        later = _zones_for(seeded_series(400, seed=seed, drift=drift))
        for before, after in zip(earlier.zones, later.zones):
            assert before.width == after.width
            assert (before.low, before.high) == (after.low, after.high)

    def test_a_width_from_a_later_bar_is_never_read(self) -> None:
        """Stated directly: doubling volatility after a band was written does nothing."""
        from tests.price_zone_helpers import width_series_from

        calm = {index: 4.0 for index in range(15, 40)}
        storm = dict(calm)
        storm.update({index: 400.0 for index in range(40, 80)})
        levels = [level(100.0, index=20)]
        quiet = derive_price_zones(levels, width_series_from(calm, bars=80))
        loud = derive_price_zones(levels, width_series_from(storm, bars=80))
        assert _identity(quiet.zones[0]) == _identity(loud.zones[0])

    @pytest.mark.parametrize("seed, drift", SERIES_CASES)
    def test_no_zone_is_established_after_the_last_bar_it_could_be_known_at(
        self, seed: int, drift: float
    ) -> None:
        series = seeded_series(400, seed=seed, drift=drift)
        closed = len(series.closed().candles)
        for zone in _zones_for(series).zones:
            assert zone.established_index < closed
            assert zone.latest_member_index < closed
            assert zone.established_index <= zone.latest_member_index


class TestDeterminism:
    """Same input, same zones — across calls, orders, processes and hash seeds. (J)"""

    @pytest.mark.parametrize("seed, drift", SERIES_CASES)
    def test_two_calls_over_one_series_agree_exactly(
        self, seed: int, drift: float
    ) -> None:
        series = seeded_series(400, seed=seed, drift=drift)
        assert repr(_zones_for(series)) == repr(_zones_for(series))

    @pytest.mark.parametrize("seed, drift", SERIES_CASES)
    def test_permuting_the_level_input_changes_nothing(
        self, seed: int, drift: float
    ) -> None:
        """Establishment order is read off the levels, never off the sequence."""
        series = seeded_series(400, seed=seed, drift=drift)
        levels = levels_of(series)
        widths = atr_series_of(series)
        straight = derive_price_zones(levels, widths)
        # Reversed rather than randomly shuffled: within one bar the input order
        # is the tie-break, so a permutation that keeps bars intact is the
        # honest test, and reversing is the strongest such permutation.
        by_bar: dict[int, list] = {}
        for item in levels:
            by_bar.setdefault(item.origin.knowable_from, []).append(item)
        rearranged = [
            item for bar in sorted(by_bar, reverse=True) for item in by_bar[bar]
        ]
        shuffled = derive_price_zones(rearranged, widths)
        assert zone_map(straight) == zone_map(shuffled)

    def test_the_output_is_identical_under_a_different_hash_seed(self) -> None:
        """No dict or set iteration order reaches the result."""
        program = (
            "import sys; sys.path[:0]=['tests','.']\n"
            "from tests.price_zone_helpers import seeded_series, levels_of, "
            "atr_series_of\n"
            "from fmis.price_zones import derive_price_zones\n"
            "s = seeded_series(400, seed=7, drift=0.004)\n"
            "print(repr(derive_price_zones(levels_of(s), atr_series_of(s))))\n"
        )
        outputs = set()
        for hash_seed in ("0", "1", "12345"):
            result = subprocess.run(
                [sys.executable, "-c", program],
                capture_output=True,
                text=True,
                check=True,
                cwd=Path(__file__).resolve().parents[1],
                env={
                    "PYTHONHASHSEED": hash_seed,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PATH": "/usr/bin:/bin",
                },
            )
            outputs.add(result.stdout)
        assert len(outputs) == 1


class TestInvariance:
    """Unit invariance and long/short symmetry, over the production chain. (K)"""

    @pytest.mark.parametrize("seed, drift", SERIES_CASES)
    @pytest.mark.parametrize("factor", [2.0, 1024.0, 0.125])
    def test_rescaling_every_price_leaves_the_grouping_unchanged(
        self, seed: int, drift: float, factor: float
    ) -> None:
        """Dyadic factors rescale a float exactly, so this is an equality.

        `W-PCT` fails the companion property; this is the one the winning scale
        family passes.
        """
        series = seeded_series(400, seed=seed, drift=drift)
        assert zone_map(_zones_for(series)) == zone_map(
            _zones_for(scaled(series, factor))
        )

    @pytest.mark.parametrize("seed, drift", SERIES_CASES)
    def test_reflecting_the_series_mirrors_the_zone_map_exactly(
        self, seed: int, drift: float
    ) -> None:
        """A long market and its mirrored short must group identically at k <= 1.00.

        This is the property that fixes the admissible region's ceiling: report
        0050 measured the first failures at ``k = 1.25``, and `ZoneWidthPolicy`
        refuses a multiple above ``1.00`` for exactly this reason.
        """
        series = seeded_series(400, seed=seed, drift=drift)
        mirrored = reflected(series, about=1000.0)
        assert zone_map(_zones_for(series)) == zone_map(_zones_for(mirrored))

    @pytest.mark.parametrize("multiple", [0.10, 0.25, 0.50, 0.75, 1.00])
    def test_symmetry_holds_across_the_whole_admissible_region(
        self, multiple: float
    ) -> None:
        policy = ZoneWidthPolicy(
            policy_id=f"atr14-anchor-{multiple}",
            scale=ZoneWidthScale.ATR_MULTIPLE,
            feature_name="atr_14",
            multiple=multiple,
            temporal_reference=ZoneWidthReference.AT_ANCHOR_ESTABLISHMENT,
        )
        series = seeded_series(400, seed=7, drift=0.004)
        mirrored = reflected(series, about=1000.0)
        straight = derive_price_zones(
            levels_of(series), atr_series_of(series), policy=policy
        )
        flipped = derive_price_zones(
            levels_of(mirrored), atr_series_of(mirrored), policy=policy
        )
        assert zone_map(straight) == zone_map(flipped)

    @pytest.mark.parametrize("seed, drift", SERIES_CASES)
    def test_every_level_is_either_a_member_exactly_once_or_unassigned(
        self, seed: int, drift: float
    ) -> None:
        """A partition. Nothing is duplicated and nothing is silently dropped."""
        series = seeded_series(400, seed=seed, drift=drift)
        levels = levels_of(series)
        zone_set = derive_price_zones(levels, atr_series_of(series))
        placed = [
            member.level for zone in zone_set.zones for member in zone.members
        ]
        seen = [id(item) for item in placed] + [
            id(item) for item in zone_set.unassigned
        ]
        assert len(seen) == len(set(seen)) == len(levels)
        assert set(seen) == {id(item) for item in levels}

    @pytest.mark.parametrize("seed, drift", SERIES_CASES)
    def test_a_larger_multiple_never_produces_more_zones(
        self, seed: int, drift: float
    ) -> None:
        """`k` is a resolution control, and monotone — report 0050's central finding."""
        series = seeded_series(400, seed=seed, drift=drift)
        levels = levels_of(series)
        widths = atr_series_of(series)
        counts = []
        for multiple in (0.10, 0.25, 0.50, 0.75, 1.00):
            policy = ZoneWidthPolicy(
                policy_id=f"atr14-anchor-{multiple}",
                scale=ZoneWidthScale.ATR_MULTIPLE,
                feature_name="atr_14",
                multiple=multiple,
                temporal_reference=ZoneWidthReference.AT_ANCHOR_ESTABLISHMENT,
            )
            counts.append(
                derive_price_zones(levels, widths, policy=policy).zone_count
            )
        assert counts == sorted(counts, reverse=True)
        assert ZONE_WIDTH_POLICY_V1.multiple == 0.50
