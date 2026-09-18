"""`fmis.price_zones` — the rules, each one a decision report 0050 measured.

The engine is small; the reason each rule is the rule is not. Every test below
names the alternative that was refuted, because a rule whose alternative is
forgotten is a rule the next milestone re-litigates from intuition.

Offline, clock-free and network-free.
"""

from __future__ import annotations

import pytest

from fmis.data import SeriesIdentity
from fmis.level_crossing import LevelSide, PriceLevel
from fmis.market_structure import StructuralSwingLabel
from fmis.price_zones import (
    ADMISSIBLE_MULTIPLE,
    ZONE_WIDTH_POLICY_V1,
    PriceZone,
    PriceZoneSet,
    ZoneMember,
    ZonePricePosition,
    ZoneWidthPolicy,
    SeriesWindowMismatchError,
    ZoneWidthPolicyMismatchError,
    ZoneWidthReference,
    ZoneWidthScale,
    derive_price_zones,
)

from tests.price_zone_helpers import (
    IDENTITY,
    atr_series_of,
    flat_width_series,
    level,
    levels_of,
    seeded_series,
    width_series_from,
)


class TestTheDeclaredPolicy:
    """`k` is declared, and the type says so where a reader will meet it."""

    def test_v1_is_one_half_of_atr_14_read_at_the_anchor(self) -> None:
        assert ZONE_WIDTH_POLICY_V1.multiple == 0.50
        assert ZONE_WIDTH_POLICY_V1.feature_name == "atr_14"
        assert ZONE_WIDTH_POLICY_V1.scale is ZoneWidthScale.ATR_MULTIPLE
        assert (
            ZONE_WIDTH_POLICY_V1.temporal_reference
            is ZoneWidthReference.AT_ANCHOR_ESTABLISHMENT
        )

    def test_the_policy_id_names_the_parameters_it_was_built_from(self) -> None:
        """A stored zone must be reproducible from its own stamp, not from a default."""
        assert ZONE_WIDTH_POLICY_V1.policy_id == "atr14-anchor-0_50"

    def test_one_policy_serves_every_timeframe_role(self) -> None:
        """No per-role constant exists, hidden or otherwise (owner decision C).

        Asserted on the **output**, over a real three-role sheet at three
        different intervals, rather than on the source text: a per-role branch
        anywhere in the chain would show up here as two policies.
        """
        from tests.archive_helpers import multi

        sheet = multi(seeds=(1, 5, 9), symbol="BTCUSDT")
        stamped = set()
        intervals = set()
        for view in sheet.views:
            intervals.add(view.interval)
            zone_set = view.sheet.structure.zones
            assert zone_set is not None
            stamped.add(zone_set.width_policy)
            for zone in zone_set.zones:
                stamped.add(zone.width_policy)
        assert intervals == {"1w", "1d", "4h"}
        assert stamped == {ZONE_WIDTH_POLICY_V1}

    def test_the_multiple_is_the_only_place_k_is_multiplied(self) -> None:
        assert ZONE_WIDTH_POLICY_V1.width_from(10.0) == 5.0

    @pytest.mark.parametrize("bad", [0.0, 0.05, 1.25, 2.0, -0.5])
    def test_a_multiple_outside_the_measured_region_is_rejected(
        self, bad: float
    ) -> None:
        """The one thing about `k` that **was** measured is the region it lies in."""
        with pytest.raises(ValueError, match="admissible region"):
            ZoneWidthPolicy(
                policy_id="bad",
                scale=ZoneWidthScale.ATR_MULTIPLE,
                feature_name="atr_14",
                multiple=bad,
                temporal_reference=ZoneWidthReference.AT_ANCHOR_ESTABLISHMENT,
            )

    @pytest.mark.parametrize("edge", list(ADMISSIBLE_MULTIPLE))
    def test_both_edges_of_the_region_are_admitted(self, edge: float) -> None:
        assert ZoneWidthPolicy(
            policy_id=f"edge-{edge}",
            scale=ZoneWidthScale.ATR_MULTIPLE,
            feature_name="atr_14",
            multiple=edge,
            temporal_reference=ZoneWidthReference.AT_ANCHOR_ESTABLISHMENT,
        ).multiple == edge

    def test_a_history_of_the_wrong_feature_is_refused(self) -> None:
        """A zone stamped with a policy it was not built under is unreproducible."""
        with pytest.raises(ZoneWidthPolicyMismatchError, match="atr_14"):
            derive_price_zones(
                [level(100.0, index=20)],
                flat_width_series(4.0, name="atr_28"),
            )

    def test_a_width_history_from_a_different_window_is_refused(self) -> None:
        """The one mis-pairing the engine could otherwise absorb silently.

        A level that became knowable at bar 47 needs a width read at bar 47. Hand
        it a history computed over 30 candles and the nearest-earlier fallback
        would size the band from bar 29's volatility and say nothing. `PriceLevel`
        carries no `SeriesIdentity`, so the bar index is the only thing that can
        catch this — and it catches it exactly.
        """
        with pytest.raises(SeriesWindowMismatchError, match="do not describe the same"):
            derive_price_zones(
                [level(100.0, index=45)], flat_width_series(4.0, bars=30)
            )

    def test_a_longer_width_history_than_the_levels_need_is_fine(self) -> None:
        """Only a *shorter* window is a mismatch. A longer one saw every bar."""
        zone_set = derive_price_zones(
            [level(100.0, index=45)], flat_width_series(4.0, bars=900)
        )
        assert zone_set.zone_count == 1


class TestTheBand:
    """Frozen at the anchor, and the two rejected alternatives cannot be selected."""

    def test_the_band_is_the_anchor_price_plus_and_minus_half_the_width(self) -> None:
        zones = derive_price_zones(
            [level(100.0, index=20)], flat_width_series(4.0)
        ).zones
        assert len(zones) == 1
        assert zones[0].low == pytest.approx(99.0)
        assert zones[0].high == pytest.approx(101.0)
        assert zones[0].width == pytest.approx(2.0)  # k = 0.50 x ATR 4.0

    def test_the_width_is_read_at_the_anchors_own_establishment_bar(self) -> None:
        """Not the latest value: that moved every historical band on every bar.

        Two anchors, two different volatilities at their two bars. If the width
        were read at the end of the series both bands would be the same size.
        """
        widths = {index: 4.0 for index in range(15, 60)}
        for index in range(40, 60):
            widths[index] = 20.0
        zones = derive_price_zones(
            [level(100.0, index=20), level(200.0, index=45)],
            width_series_from(widths, bars=60),
        ).zones
        assert [zone.width for zone in zones] == [
            pytest.approx(2.0),
            pytest.approx(10.0),
        ]

    def test_a_joining_member_does_not_widen_the_band(self) -> None:
        """34,192 illegal prefix events were measured for the growing variant.

        The second level joins from inside the band while its own bar's width is
        five times larger. The band must not notice.
        """
        widths = {index: 4.0 for index in range(15, 60)}
        for index in range(40, 60):
            widths[index] = 20.0
        zone_set = derive_price_zones(
            [level(100.0, index=20), level(100.5, index=45)],
            width_series_from(widths, bars=60),
        )
        assert zone_set.zone_count == 1
        zone = zone_set.zones[0]
        assert zone.member_count == 2
        assert (zone.low, zone.high) == (pytest.approx(99.0), pytest.approx(101.0))
        assert zone.width == pytest.approx(2.0)

    def test_the_bands_edges_do_not_move_when_a_later_level_joins(self) -> None:
        """The prefix form of the same rule, stated as an equality on the tuple."""
        widths = flat_width_series(4.0)
        first = derive_price_zones([level(100.0, index=20)], widths)
        second = derive_price_zones(
            [level(100.0, index=20), level(100.4, index=45)], widths
        )
        assert (first.zones[0].low, first.zones[0].high) == (
            second.zones[0].low,
            second.zones[0].high,
        )
        assert first.zones[0].established_index == second.zones[0].established_index
        assert second.zones[0].latest_member_index == 47
        assert first.zones[0].latest_member_index == 22


class TestMembership:
    """By price alone, inclusive at both edges, and never twice."""

    @pytest.mark.parametrize("price", [99.0, 100.0, 101.0])
    def test_the_edges_are_inclusive(self, price: float) -> None:
        zone_set = derive_price_zones(
            [level(100.0, index=20), level(price, index=45)], flat_width_series(4.0)
        )
        assert zone_set.zone_count == 1
        assert zone_set.zones[0].member_count == 2

    @pytest.mark.parametrize("price", [98.9999, 101.0001])
    def test_a_price_outside_the_band_opens_its_own(self, price: float) -> None:
        zone_set = derive_price_zones(
            [level(100.0, index=20), level(price, index=45)], flat_width_series(4.0)
        )
        assert zone_set.zone_count == 2

    def test_an_upper_and_a_lower_level_may_share_one_area(self) -> None:
        """An area is an area. The side travels on the level and is never lost."""
        zone_set = derive_price_zones(
            [
                level(100.0, index=20, side=LevelSide.UPPER),
                level(100.3, index=45, side=LevelSide.LOWER),
            ],
            flat_width_series(4.0),
        )
        assert zone_set.zone_count == 1
        sides = [member.level.side for member in zone_set.zones[0].members]
        assert sides == [LevelSide.UPPER, LevelSide.LOWER]

    def test_a_level_belongs_to_exactly_one_zone(self) -> None:
        """Bands overlap; membership does not."""
        zone_set = derive_price_zones(
            [
                level(100.0, index=20),
                level(101.5, index=25),
                level(100.8, index=40),
            ],
            flat_width_series(4.0),
        )
        seen = [
            member.level
            for zone in zone_set.zones
            for member in zone.members
        ]
        assert len(seen) == 3 == zone_set.member_count
        assert len({id(item) for item in seen}) == 3

    def test_equal_prices_with_different_origins_stay_two_distinct_members(
        self,
    ) -> None:
        """Requirement G. Collapsing them destroys exactly what a later layer wants."""
        first = level(100.0, index=20, label=StructuralSwingLabel.HIGHER_HIGH)
        second = level(100.0, index=44, label=StructuralSwingLabel.LOWER_HIGH)
        zone_set = derive_price_zones([first, second], flat_width_series(4.0))
        assert zone_set.zone_count == 1
        members = zone_set.zones[0].members
        assert len(members) == 2
        assert first != second
        assert members[0].level is first
        assert members[1].level is second
        assert members[0].level.origin.label is StructuralSwingLabel.HIGHER_HIGH
        assert members[1].level.origin.label is StructuralSwingLabel.LOWER_HIGH

    def test_every_member_is_the_caller_s_own_level_object(self) -> None:
        """Requirement F. Carried by reference; the zone reinterprets nothing."""
        levels = [level(100.0, index=20), level(100.3, index=45)]
        zone = derive_price_zones(levels, flat_width_series(4.0)).zones[0]
        assert [member.level for member in zone.members] == levels
        assert all(
            member.level is original
            for member, original in zip(zone.members, levels)
        )

    def test_a_level_without_an_origin_is_refused_rather_than_guessed_at(self) -> None:
        with pytest.raises(ValueError, match="LevelOrigin"):
            derive_price_zones(
                [PriceLevel(price=100.0, side=LevelSide.UPPER)],
                flat_width_series(4.0),
            )


class TestTies:
    """The oldest band, never the nearest centre."""

    def test_a_level_inside_two_bands_joins_the_one_created_first(self) -> None:
        """Nearest centre flipped on 35 % of series under a rescale.

        The third level sits nearer the **second** band's centre and inside both.
        Under the refuted rule it would join the second; under this one the
        band that was already there keeps it.
        """
        zone_set = derive_price_zones(
            [
                level(100.0, index=20),
                level(101.5, index=30),
                level(100.9, index=50),
            ],
            flat_width_series(4.0),
        )
        assert zone_set.zone_count == 2
        first, second = zone_set.zones
        # Inside both bands, and nearer the second band's centre.
        assert first.contains(100.9) and second.contains(100.9)
        assert abs(100.9 - 101.5) < abs(100.9 - 100.0)
        assert first.member_count == 2 and second.member_count == 1
        assert first.members[1].price == pytest.approx(100.9)

    def test_the_outcome_does_not_depend_on_the_order_the_levels_arrive_in(
        self,
    ) -> None:
        """Establishment order is read off the levels, never off the sequence."""
        levels = [
            level(100.0, index=20),
            level(101.5, index=30),
            level(100.9, index=50),
        ]
        expected = derive_price_zones(levels, flat_width_series(4.0))
        shuffled = derive_price_zones(
            [levels[2], levels[0], levels[1]], flat_width_series(4.0)
        )
        assert [(z.low, z.high, z.member_count) for z in expected.zones] == [
            (z.low, z.high, z.member_count) for z in shuffled.zones
        ]


class TestOneBarIsOneInstant:
    """A band opened at bar *i* cannot claim another level from bar *i*."""

    def test_two_levels_on_one_bar_open_two_bands_even_when_each_contains_the_other(
        self,
    ) -> None:
        """One candle can be both a swing high and a swing low.

        Any order between two levels of one bar would have to break the tie on
        side or price, and both invert under reflection — which moved the zone
        map on 2 % of series before this rule existed.
        """
        zone_set = derive_price_zones(
            [
                level(100.0, index=20, side=LevelSide.UPPER),
                level(100.2, index=20, side=LevelSide.LOWER),
            ],
            flat_width_series(4.0),
        )
        assert zone_set.zone_count == 2
        assert [zone.member_count for zone in zone_set.zones] == [1, 1]
        assert zone_set.zones[0].contains(100.2)  # each band does contain the other
        assert zone_set.zones[1].contains(100.0)

    def test_a_level_from_the_next_bar_may_join_a_band_opened_on_the_previous_one(
        self,
    ) -> None:
        """The rule is about one instant, not about a quarantine period."""
        zone_set = derive_price_zones(
            [
                level(100.0, index=20, confirmation_bars=2),
                level(100.2, index=21, confirmation_bars=2),
            ],
            flat_width_series(4.0),
        )
        assert zone_set.zone_count == 1
        assert zone_set.zones[0].member_count == 2

    def test_the_establishment_bar_is_the_pivot_plus_its_confirmation_window(
        self,
    ) -> None:
        """Reading the pivot's own bar would let a zone exist before its level did."""
        zone = derive_price_zones(
            [level(100.0, index=20, confirmation_bars=3)], flat_width_series(4.0)
        ).zones[0]
        assert zone.established_index == 23
        assert zone.anchor.level.origin.index == 20


class TestMissingWidth:
    """No width, no zone — and never a default."""

    def test_a_level_established_before_warm_up_forms_no_zone(self) -> None:
        zone_set = derive_price_zones(
            [level(100.0, index=2, confirmation_bars=2), level(200.0, index=30)],
            flat_width_series(4.0, first_index=15),
        )
        assert zone_set.zone_count == 1
        assert zone_set.unassigned_count == 1
        assert zone_set.unassigned[0].price == pytest.approx(100.0)

    def test_the_unassigned_level_is_carried_by_reference_not_summarised_away(
        self,
    ) -> None:
        early = level(100.0, index=2, confirmation_bars=2)
        zone_set = derive_price_zones([early], flat_width_series(4.0))
        assert zone_set.zones == ()
        assert zone_set.unassigned == (early,)
        assert zone_set.unassigned[0] is early

    def test_no_band_anywhere_borrows_a_later_width(self) -> None:
        """Falling forward would be lookahead dressed as a lookup."""
        zone_set = derive_price_zones(
            [level(100.0, index=5, confirmation_bars=1)],
            width_series_from({20: 4.0}, bars=60),
        )
        assert zone_set.zone_count == 0
        assert zone_set.unassigned_count == 1

    def test_an_earlier_width_is_used_when_the_exact_bar_has_no_point(self) -> None:
        """A gap in a feature history is a real possibility; a KeyError is not a policy."""
        zone_set = derive_price_zones(
            [level(100.0, index=28, confirmation_bars=2)],
            width_series_from({20: 4.0}, bars=60),
        )
        assert zone_set.zone_count == 1
        assert zone_set.zones[0].width == pytest.approx(2.0)

    def test_a_non_positive_reading_forms_no_band_rather_than_a_point(self) -> None:
        """A zero-width band would admit only exactly-equal prices — another policy."""
        zone_set = derive_price_zones(
            [level(100.0, index=20)], width_series_from({22: 0.0}, bars=60)
        )
        assert zone_set.zone_count == 0
        assert zone_set.unassigned_count == 1


class TestOverlap:
    """Bands overlap, are reported, and are never merged."""

    def test_two_overlapping_bands_stay_two_zones(self) -> None:
        zone_set = derive_price_zones(
            [level(100.0, index=20), level(101.5, index=40)], flat_width_series(4.0)
        )
        assert zone_set.zone_count == 2
        assert zone_set.overlapping == ((0, 1),)
        assert zone_set.zones[0].high > zone_set.zones[1].low

    def test_one_price_may_sit_inside_several_zones_at_once(self) -> None:
        zone_set = derive_price_zones(
            [level(100.0, index=20), level(101.5, index=40)], flat_width_series(4.0)
        )
        assert len(zone_set.zones_containing(101.0)) == 2

    def test_a_real_series_produces_overlapping_bands_and_they_are_not_merged(
        self,
    ) -> None:
        series = seeded_series(400, seed=7, drift=0.004)
        zone_set = derive_price_zones(levels_of(series), atr_series_of(series))
        assert zone_set.overlapping
        for first, second in zone_set.overlapping:
            assert zone_set.zones[first] is not zone_set.zones[second]


class TestPositionIsGeometryAndNeverARole:
    """The rule owner decision D and the 0047 disposition §E both turn on."""

    @pytest.mark.parametrize(
        "price, expected",
        [
            (101.5, ZonePricePosition.PRICE_ABOVE),
            (101.0, ZonePricePosition.PRICE_INSIDE),
            (100.0, ZonePricePosition.PRICE_INSIDE),
            (99.0, ZonePricePosition.PRICE_INSIDE),
            (98.5, ZonePricePosition.PRICE_BELOW),
        ],
    )
    def test_position_reads_as_a_sentence_about_the_price(
        self, price: float, expected: ZonePricePosition
    ) -> None:
        zone = derive_price_zones(
            [level(100.0, index=20)], flat_width_series(4.0)
        ).zones[0]
        assert zone.price_position(price) is expected

    def test_the_vocabulary_holds_three_members_and_no_role_among_them(self) -> None:
        assert {member.value for member in ZonePricePosition} == {
            "price_above",
            "price_below",
            "price_inside",
        }

    @pytest.mark.parametrize(
        "forbidden",
        [
            "support",
            "resistance",
            "held",
            "broken",
            "reclaim",
            "retest",
            "breakout",
            "flip",
            "untested",
            "strong",
            "weak",
            "strength",
            "quality",
            "score",
            "rank",
            "confidence",
            "bullish",
            "bearish",
        ],
    )
    def test_no_zone_type_carries_a_field_that_states_a_reading(
        self, forbidden: str
    ) -> None:
        """A field that could hold a role is a field something will fill with one."""
        for kind in (PriceZone, PriceZoneSet, ZoneMember, ZoneWidthPolicy):
            for field in kind.__dataclass_fields__:
                assert forbidden not in field.lower(), (
                    f"{kind.__name__}.{field} names a reading this layer has no "
                    "engine for"
                )
            for attribute in dir(kind):
                if attribute.startswith("_"):
                    continue
                assert forbidden not in attribute.lower(), (
                    f"{kind.__name__}.{attribute} names a reading this layer has "
                    "no engine for"
                )

    def test_asking_where_price_stands_leaves_the_zone_completely_unchanged(
        self,
    ) -> None:
        """A zone has no memory of having been asked, so no role can accumulate.

        The measured case against the forbidden derivation: 39 % (1W) and 50 %
        (1D) of zones have had price close on **both** sides since they were
        established. If position ever became a stored role, the same unchanged
        area would read as two different things on two different days — and the
        only structural defence is that there is nowhere to store it.
        """
        zone = derive_price_zones(
            [level(100.0, index=20)], flat_width_series(4.0)
        ).zones[0]
        before = repr(zone)
        for price in (50.0, 99.5, 100.0, 100.5, 5000.0):
            zone.price_position(price)
            zone.distance_from(price)
        assert repr(zone) == before

    def test_two_zones_on_opposite_sides_of_price_are_records_of_the_same_shape(
        self,
    ) -> None:
        """One below price and one above it differ in their numbers and nothing else.

        Every field either belongs to the band's own geometry or to its
        provenance; there is no field whose *meaning* depends on which side of it
        price happens to be, which is what a role would be.
        """
        zone_set = derive_price_zones(
            [level(100.0, index=20), level(120.0, index=40)], flat_width_series(4.0)
        )
        below, above = zone_set.zones
        assert below.price_position(110.0) is ZonePricePosition.PRICE_ABOVE
        assert above.price_position(110.0) is ZonePricePosition.PRICE_BELOW
        assert below.member_count == above.member_count == 1
        assert below.width == above.width
        # The two records differ only where the band itself differs.
        differing = {
            name
            for name in PriceZone.__dataclass_fields__
            if getattr(below, name) != getattr(above, name)
        }
        assert differing == {"low", "high", "anchor", "members"}


class TestDistanceIsPresentationGeometry:
    def test_distance_is_zero_inside_the_band(self) -> None:
        zone = derive_price_zones(
            [level(100.0, index=20)], flat_width_series(4.0)
        ).zones[0]
        assert zone.distance_from(100.0) == 0.0
        assert zone.distance_from(99.0) == 0.0
        assert zone.distance_from(101.0) == 0.0

    def test_distance_is_the_gap_to_the_nearest_edge(self) -> None:
        zone = derive_price_zones(
            [level(100.0, index=20)], flat_width_series(4.0)
        ).zones[0]
        assert zone.distance_from(103.0) == pytest.approx(2.0)
        assert zone.distance_from(97.0) == pytest.approx(2.0)

    def test_distance_is_never_negative(self) -> None:
        zone = derive_price_zones(
            [level(100.0, index=20)], flat_width_series(4.0)
        ).zones[0]
        for price in (0.5, 50.0, 99.5, 100.0, 150.0, 1e6):
            assert zone.distance_from(price) >= 0.0


class TestTheZoneSet:
    def test_zones_are_held_in_creation_order(self) -> None:
        zone_set = derive_price_zones(
            [level(200.0, index=20), level(100.0, index=40)], flat_width_series(4.0)
        )
        assert [zone.established_index for zone in zone_set.zones] == [22, 42]
        assert zone_set.zones[0].low > zone_set.zones[1].high  # not price-sorted

    def test_the_identity_is_the_width_series_own_object(self) -> None:
        widths = flat_width_series(4.0)
        zone_set = derive_price_zones([level(100.0, index=20)], widths)
        assert zone_set.identity is widths.identity
        assert zone_set.zones[0].identity is widths.identity

    def test_the_policy_is_stamped_on_every_zone_by_value(self) -> None:
        zone_set = derive_price_zones(
            [level(100.0, index=20), level(200.0, index=40)], flat_width_series(4.0)
        )
        for zone in zone_set.zones:
            assert zone.width_policy == ZONE_WIDTH_POLICY_V1

    def test_a_set_whose_zones_disagree_about_their_policy_is_unrepresentable(
        self,
    ) -> None:
        other = ZoneWidthPolicy(
            policy_id="other",
            scale=ZoneWidthScale.ATR_MULTIPLE,
            feature_name="atr_14",
            multiple=0.25,
            temporal_reference=ZoneWidthReference.AT_ANCHOR_ESTABLISHMENT,
        )
        zone = derive_price_zones(
            [level(100.0, index=20)], flat_width_series(4.0)
        ).zones[0]
        with pytest.raises(ValueError, match="width policy"):
            PriceZoneSet(identity=IDENTITY, width_policy=other, zones=(zone,))

    def test_a_set_cannot_hold_two_series(self) -> None:
        zone = derive_price_zones(
            [level(100.0, index=20)], flat_width_series(4.0)
        ).zones[0]
        with pytest.raises(ValueError, match="cannot be about two series"):
            PriceZoneSet(
                identity=SeriesIdentity(symbol="OTHER", timeframe="4h"),
                width_policy=ZONE_WIDTH_POLICY_V1,
                zones=(zone,),
            )

    def test_the_set_states_its_own_limitations(self) -> None:
        zone_set = derive_price_zones(
            [level(100.0, index=20)], flat_width_series(4.0)
        )
        codes = [code for code, _text in zone_set.limitations]
        assert codes == ["PZ-1", "PZ-2", "PZ-3", "PZ-4", "PZ-5", "PZ-6", "PZ-7"]
        declared = dict(zone_set.limitations)["PZ-1"]
        assert "declared, not measured" in declared


class TestTheSelectionTheEngineOffersAPage:
    """A page must select from 20-250 bands. The engine owns which, and in what order."""

    def _set(self):
        return derive_price_zones(
            [
                level(100.0, index=20),
                level(120.0, index=30),
                level(140.0, index=40),
                level(80.0, index=50),
                level(60.0, index=60),
            ],
            flat_width_series(4.0),
        )

    def test_above_below_and_containing_partition_the_set(self) -> None:
        zone_set = self._set()
        for price in (50.0, 60.0, 99.0, 100.0, 110.0, 141.0, 500.0):
            counted = (
                len(zone_set.zones_above(price))
                + len(zone_set.zones_below(price))
                + len(zone_set.zones_containing(price))
            )
            assert counted == zone_set.zone_count, price

    def test_nearest_above_and_below_are_the_nearest(self) -> None:
        zone_set = self._set()
        assert zone_set.nearest_above(110.0).low == pytest.approx(119.0)
        assert zone_set.nearest_below(110.0).high == pytest.approx(101.0)

    def test_nearest_returns_an_absence_rather_than_the_far_end_of_the_set(
        self,
    ) -> None:
        zone_set = self._set()
        assert zone_set.nearest_above(500.0) is None
        assert zone_set.nearest_below(1.0) is None

    def test_near_is_bounded_per_side_and_ordered_high_to_low(self) -> None:
        zone_set = self._set()
        selected = zone_set.near(110.0, per_side=2)
        assert len(selected) == 4
        highs = [zone.high for zone in selected]
        assert highs == sorted(highs, reverse=True)
        assert [zone.price_position(110.0).value for zone in selected] == [
            "price_below",
            "price_below",
            "price_above",
            "price_above",
        ]

    def test_near_includes_the_band_the_price_is_inside(self) -> None:
        zone_set = self._set()
        selected = zone_set.near(100.5, per_side=1)
        assert any(zone.contains(100.5) for zone in selected)

    def test_near_is_deterministic_and_order_independent(self) -> None:
        zone_set = self._set()
        assert zone_set.near(110.0, per_side=3) == zone_set.near(110.0, per_side=3)

    def test_a_negative_bound_is_refused(self) -> None:
        with pytest.raises(ValueError, match="per_side"):
            self._set().near(110.0, per_side=-1)


class TestTheZoneModelRejectsAnImpossibleZone:
    """Validate, never repair — the repository's rule, applied to the band."""

    def test_a_member_outside_the_band_is_refused(self) -> None:
        anchor = ZoneMember(level(100.0, index=20))
        stray = ZoneMember(level(500.0, index=40))
        with pytest.raises(ValueError, match="outside the band"):
            PriceZone(
                low=99.0,
                high=101.0,
                anchor=anchor,
                members=(anchor, stray),
                width=2.0,
                width_policy=ZONE_WIDTH_POLICY_V1,
                identity=IDENTITY,
            )

    def test_an_anchor_that_is_not_the_first_member_is_refused(self) -> None:
        anchor = ZoneMember(level(100.0, index=20))
        other = ZoneMember(level(100.2, index=40))
        with pytest.raises(ValueError, match="anchor must be the first member"):
            PriceZone(
                low=99.0,
                high=101.0,
                anchor=anchor,
                members=(other, anchor),
                width=2.0,
                width_policy=ZONE_WIDTH_POLICY_V1,
                identity=IDENTITY,
            )

    def test_members_out_of_join_order_are_refused(self) -> None:
        anchor = ZoneMember(level(100.0, index=40))
        earlier = ZoneMember(level(100.2, index=20))
        with pytest.raises(ValueError, match="join order"):
            PriceZone(
                low=99.0,
                high=101.0,
                anchor=anchor,
                members=(anchor, earlier),
                width=2.0,
                width_policy=ZONE_WIDTH_POLICY_V1,
                identity=IDENTITY,
            )
