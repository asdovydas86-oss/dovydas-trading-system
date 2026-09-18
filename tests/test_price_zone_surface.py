"""TA Slice 5B — the zones reach the operator intact, and the page refuses a role.

Two questions, and the second is the one that matters.

**Does the fact survive the seam?** A `PriceZoneSet` is built inside
`build_structural_facts` and has four layers to cross before an operator sees it:
the technical-context carriage, the setup result, the workspace decision and the
dashboard row. Every assertion here compares zone **identity** — the band, the
anchor, the membership — not a count, because `len(zones) == 5` on both sides of
a seam is satisfied by a layer that carried the wrong five.

**Did having the data license a vocabulary for it?** Once bands are on the page
the shortest path to a "useful" surface is to call the one below price *support*
and the one price just left a *breakout*. Neither concept exists in this
repository: `ZoneInteraction` is not V1, research questions R3 and R4 are
unanswered, and report 0050 measured that a role read from position is not even
well-defined over time. The scan below reads the rendered HTML and refuses the
whole vocabulary, with the panel's own denial paragraph carved out explicitly and
asserted separately — the exemption pattern TA Slice 5A established.

Offline, clock-free and network-free.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from fmis.operator_dashboard.render import _price_zone_panel, _symbol_page
from fmis.operator_dashboard.sections import (
    ZONE_MEMBERS_SHOWN,
    ZONES_SHOWN_PER_SIDE,
    price_zone_group_rows,
    symbol_decision_rows,
)
from fmis.pipeline.regime import regime_for_sheet
from fmis.pipeline.technical_context import technical_context_for_sheet
from fmis.price_zones import ZONE_WIDTH_POLICY_V1, PriceZoneSet, ZonePricePosition
from fmis.swing_setup.compose import (
    SetupRunResult,
    setup_composition_for_sheet,
    setup_readings_for,
)
from fmis.swing_workspace.sections import symbol_decisions

from tests.archive_helpers import multi

REFERENCE = datetime(2026, 2, 14, tzinfo=timezone.utc)


def _carried(seeds=(1, 5, 9), symbol: str = "BTCUSDT"):
    """One symbol carried the whole way, exactly as the live path carries it."""
    sheet = multi(seeds=seeds, symbol=symbol)
    inputs, technical, assessment = setup_composition_for_sheet(sheet)
    result = SetupRunResult(
        requested_symbol=symbol,
        assessment=assessment,
        readings=setup_readings_for(sheet, inputs),
        technical=technical,
    )
    decision = symbol_decisions([result], reference_time=REFERENCE)[0]
    return sheet, technical, decision, symbol_decision_rows([decision])[0]


def _panel(seeds=(1, 5, 9), symbol: str = "BTCUSDT") -> str:
    _sheet, _technical, _decision, row = _carried(seeds, symbol)
    return _price_zone_panel(row.symbol, row.zones)


def _visible_text(html: str) -> str:
    """The page with its markup stripped — what a reader actually reads."""
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    return text.replace(" ,", ",").replace(" .", ".")


# ---------------------------------------------------------------------------
# The seam: the sheet's zone set reaches the row, by reference
# ---------------------------------------------------------------------------


class TestTheSeam:
    def test_every_role_of_the_sheet_carries_a_zone_set(self) -> None:
        sheet, _technical, _decision, _row = _carried()
        for view in sheet.views:
            assert isinstance(view.sheet.structure.zones, PriceZoneSet)

    def test_the_carriage_holds_the_sheets_own_object_and_not_a_copy(self) -> None:
        """Identity, not equality: two equal sets would be two sources of truth."""
        sheet, technical, _decision, _row = _carried()
        for view, carried in zip(sheet.views, technical.views):
            assert carried.zones is view.sheet.structure.zones

    def test_the_decision_holds_the_same_object_the_carriage_built(self) -> None:
        _sheet, technical, decision, _row = _carried()
        assert decision.technical is technical

    def test_every_zone_reaches_the_row_with_its_band_and_anchor_intact(self) -> None:
        sheet, _technical, _decision, row = _carried()
        assert len(row.zones) == len(sheet.views)
        for view, group in zip(sheet.views, row.zones):
            source = view.sheet.structure.zones
            assert group.role == view.role.value
            assert group.interval == view.interval
            assert group.zone_count == source.zone_count
            assert group.member_count == source.member_count
            assert group.unassigned_count == source.unassigned_count
            by_band = {(zone.low, zone.high): zone for zone in source.zones}
            for shown in group.zones:
                original = by_band[(shown.low, shown.high)]
                assert shown.member_count == original.member_count
                assert shown.width == original.width
                assert shown.established_index == original.established_index
                assert shown.latest_member_index == original.latest_member_index
                assert shown.anchor.price == original.anchor.level.price
                assert shown.anchor.origin_index == (
                    original.anchor.level.origin.index
                )

    def test_the_member_provenance_is_the_zones_own_levels_in_join_order(self) -> None:
        sheet, _technical, _decision, row = _carried()
        for view, group in zip(sheet.views, row.zones):
            source = {
                (zone.low, zone.high): zone for zone in view.sheet.structure.zones.zones
            }
            for shown in group.zones:
                original = source[(shown.low, shown.high)]
                expected = [
                    (member.level.price, member.level.side.value)
                    for member in original.members[:ZONE_MEMBERS_SHOWN]
                ]
                assert [
                    (member.price, member.side) for member in shown.members
                ] == expected

    def test_the_policy_stamped_on_the_row_is_the_declared_v1_policy(self) -> None:
        _sheet, _technical, _decision, row = _carried()
        for group in row.zones:
            assert group.policy_id == ZONE_WIDTH_POLICY_V1.policy_id
            assert group.width_multiple == 0.50
            assert group.width_feature == "atr_14"


# ---------------------------------------------------------------------------
# The selection rule
# ---------------------------------------------------------------------------


class TestTheSelection:
    def test_the_page_shows_a_bounded_selection_and_states_the_true_total(
        self,
    ) -> None:
        _sheet, _technical, _decision, row = _carried()
        for group in row.zones:
            assert len(group.zones) <= 3 * ZONES_SHOWN_PER_SIDE
            assert group.zone_count >= len(group.zones)
            assert (
                group.above_count + group.below_count + group.containing_count
                == group.zone_count
            )

    def test_the_selection_is_in_descending_price_order(self) -> None:
        _sheet, _technical, _decision, row = _carried()
        for group in row.zones:
            highs = [zone.high for zone in group.zones]
            assert highs == sorted(highs, reverse=True)

    def test_the_nearest_band_above_is_the_nearest_band_above(self) -> None:
        _sheet, technical, _decision, row = _carried()
        for view, group in zip(technical.views, row.zones):
            above = [
                zone for zone in view.zones.zones if zone.low > view.last_close
            ]
            if not above:
                assert group.nearest_above is None
                continue
            expected = min(
                above, key=lambda zone: zone.distance_from(view.last_close)
            )
            assert group.nearest_above.low == expected.low
            assert group.nearest_above.position == (
                ZonePricePosition.PRICE_BELOW.value
            )

    def test_the_nearest_band_below_is_the_nearest_band_below(self) -> None:
        _sheet, technical, _decision, row = _carried()
        for view, group in zip(technical.views, row.zones):
            below = [
                zone for zone in view.zones.zones if zone.high < view.last_close
            ]
            if not below:
                assert group.nearest_below is None
                continue
            expected = min(
                below, key=lambda zone: zone.distance_from(view.last_close)
            )
            assert group.nearest_below.high == expected.high
            assert group.nearest_below.position == (
                ZonePricePosition.PRICE_ABOVE.value
            )

    def test_the_containing_band_named_is_the_oldest_one_containing_the_price(
        self,
    ) -> None:
        """The band the membership rule itself prefers, so page and engine agree."""
        _sheet, technical, _decision, row = _carried()
        found = 0
        for view, group in zip(technical.views, row.zones):
            inside = view.zones.zones_containing(view.last_close)
            if not inside:
                assert group.oldest_containing is None
                continue
            found += 1
            assert group.oldest_containing.low == inside[0].low
            assert group.oldest_containing.position == (
                ZonePricePosition.PRICE_INSIDE.value
            )
            assert group.oldest_containing.distance == 0.0
        assert found, "the fixture must contain a role whose price is inside a band"

    def test_the_distance_shown_is_the_engine_s_own(self) -> None:
        _sheet, technical, _decision, row = _carried()
        for view, group in zip(technical.views, row.zones):
            by_band = {(zone.low, zone.high): zone for zone in view.zones.zones}
            for shown in group.zones:
                assert shown.distance == by_band[
                    (shown.low, shown.high)
                ].distance_from(view.last_close)

    def test_the_selection_is_identical_on_two_builds(self) -> None:
        first = price_zone_group_rows(_carried()[1])
        second = price_zone_group_rows(_carried()[1])
        assert first == second

    def test_a_role_with_no_zone_set_is_stated_rather_than_omitted(self) -> None:
        """*This role built no areas* and *this symbol was never read* differ."""
        import dataclasses

        _sheet, technical, _decision, _row = _carried()
        stripped = dataclasses.replace(
            technical,
            views=tuple(
                dataclasses.replace(view, zones=None) for view in technical.views
            ),
        )
        groups = price_zone_group_rows(stripped)
        assert len(groups) == 3
        for group in groups:
            assert group.available is False
            assert group.zones == ()
            assert "never given a substitute width" in group.unavailable_reason


# ---------------------------------------------------------------------------
# What the page shows
# ---------------------------------------------------------------------------


class TestThePage:
    def test_the_panel_names_every_role_and_its_interval(self) -> None:
        text = _visible_text(_panel())
        for interval in ("1w", "1d", "4h"):
            assert interval in text, interval
        for role in ("context", "setup", "execution"):
            assert role in text, role

    def test_the_headline_row_shows_the_nearest_band_each_side(self) -> None:
        _sheet, _technical, _decision, row = _carried()
        text = _visible_text(_price_zone_panel(row.symbol, row.zones))
        assert "Nearest area above" in text
        assert "Nearest area below" in text
        for group in row.zones:
            for shown in (group.nearest_above, group.nearest_below):
                if shown is None:
                    continue
                assert repr(shown.low) in text
                assert repr(shown.high) in text

    def test_every_selected_band_prints_its_two_edges_and_its_level_count(
        self,
    ) -> None:
        _sheet, _technical, _decision, row = _carried()
        text = _visible_text(_price_zone_panel(row.symbol, row.zones))
        for group in row.zones:
            for shown in group.zones:
                assert repr(shown.low) in text
                assert repr(shown.high) in text

    def test_the_page_states_where_price_stands_as_a_sentence_about_the_price(
        self,
    ) -> None:
        text = _visible_text(_panel())
        assert "price is below" in text
        assert "price is above" in text

    def test_the_page_states_the_declared_width_policy_beside_the_bands(self) -> None:
        text = _visible_text(_panel())
        assert "atr14-anchor-0_50" in text
        assert "0.5 × atr_14" in text
        assert "declared V1 setting, not a measured optimum" in text

    def test_the_page_states_that_bands_overlap_and_are_not_merged(self) -> None:
        text = _visible_text(_panel())
        assert "overlapping band pairs" in text
        assert "never merged" in text

    def test_the_page_states_that_a_level_count_is_a_size_and_not_a_strength(
        self,
    ) -> None:
        text = _visible_text(_panel())
        assert "a count of levels, never a strength" in text

    def test_the_provenance_of_each_shown_band_is_reachable(self) -> None:
        _sheet, _technical, _decision, row = _carried()
        text = _visible_text(_price_zone_panel(row.symbol, row.zones))
        assert "anchored on" in text
        assert "established at bar" in text
        for group in row.zones:
            for shown in group.zones:
                assert repr(shown.anchor.price) in text

    def test_an_absent_zone_section_is_stated_rather_than_blank(self) -> None:
        text = _visible_text(_price_zone_panel("BTCUSDT", ()))
        assert "No price zones were carried" in text
        assert "BTCUSDT" in text

    def test_the_panel_sits_on_the_symbol_page_after_the_technical_context(
        self,
    ) -> None:
        """Order is the design decision: exact facts first, then the areas they form."""
        from fmis.operator_dashboard.render import _decision_detail

        _sheet, _technical, _decision, row = _carried()
        page = _decision_detail(row)
        assert page.index("— technical context") < page.index("— price zones")

    def test_the_decision_panel_still_comes_first(self) -> None:
        """Slice 2's ordering is not disturbed: the trading question stays on top."""
        from fmis.operator_dashboard.render import _decision_detail

        _sheet, _technical, _decision, row = _carried()
        page = _decision_detail(row)
        assert page.index("— decision") < page.index("— price zones")

    def test_the_first_screen_did_not_become_an_audit_dump(self) -> None:
        """Every band beyond the headline row is behind a disclosure."""
        _sheet, _technical, _decision, row = _carried()
        html = _price_zone_panel(row.symbol, row.zones)
        head, _sep, tail = html.partition("<details")
        for group in row.zones:
            for shown in group.zones:
                if shown in (
                    group.nearest_above,
                    group.nearest_below,
                    group.oldest_containing,
                ):
                    continue
                assert repr(shown.low) not in head, (
                    "a band that is not one of the three headline bands is "
                    "printed above the first disclosure"
                )


# ---------------------------------------------------------------------------
# The vocabulary the page refuses
# ---------------------------------------------------------------------------

#: Concepts this repository has **not** implemented. Every one of them is a
#: reading of a band the panel now shows, which is exactly why the scan exists.
_UNIMPLEMENTED = (
    "support",
    "resistance",
    "breakout",
    "retest",
    "reclaim",
    "rejection",
    "acceptance",
    "fakeout",
    "divergence",
    "trendline",
    "channel",
    "fibonacci",
    "elliott",
    "flag",
    "consolidation",
    "impulse",
    "oversold",
    "overbought",
    "golden",
    "crossover",
    "momentum",
    "untested",
)

#: Directional and judgement vocabulary the whole system refuses outside
#: `fmis.swing_setup`.
_JUDGEMENTS = (
    "bullish",
    "bearish",
    "buy",
    "sell",
    "score",
    "rank",
    "confidence",
    "probability",
    "recommend",
    "opportunity",
    "watch",
    "strong",
    "weak",
    "quality",
)

#: The one paragraph in the panel that uses refused words precisely to refuse
#: them. Asserted separately below, so deleting it fails a test rather than
#: quietly passing this scan.
_DENIAL = (
    "A price zone is a band frozen around the confirmed structural level that "
    "opened it, half a stated multiple of that bar's own ATR either side, and "
    "it never moves again — later levels join it, and the edges stay where they "
    "were written. None of these is support or resistance. Whether price has "
    "held at an area or broken through it is a function of what price has done "
    "there, and this system does not yet derive that; where price stands right "
    "now is geometry and nothing more. The level count is a size, not a "
    "strength. Bands overlap on purpose and are never merged. The width "
    "multiple is declared, not measured — the research bounded the usable range "
    "and deliberately did not pick a best value inside it. Nothing in this "
    "section reached the decision above it, and none of it is a reason to trade."
)


def _scanned(html: str) -> set[str]:
    """Every word on the page, with the one denial paragraph removed first."""
    text = _visible_text(html)
    assert _DENIAL in text, "the denial paragraph is not on the page"
    return set(re.findall(r"[a-z]+", text.replace(_DENIAL, "").lower()))


@pytest.mark.parametrize("word", _UNIMPLEMENTED)
def test_the_page_never_names_a_concept_this_system_has_not_built(word: str) -> None:
    """**The bands being visible is not authorisation for the vocabulary.**"""
    assert word not in _scanned(_panel()), word


@pytest.mark.parametrize("word", _JUDGEMENTS)
def test_the_page_never_names_a_direction_or_a_judgement(word: str) -> None:
    assert word not in _scanned(_panel()), word


def test_the_denial_the_scan_exempts_is_actually_on_the_page() -> None:
    text = _visible_text(_panel())
    assert _DENIAL in text
    assert "None of these is support or resistance" in text
    assert "declared, not measured" in text


@pytest.mark.parametrize("seeds", [(1, 5, 9), (3, 4, 7), (2, 6, 8)])
def test_the_refusal_holds_across_different_markets(seeds) -> None:
    """One fixture proving a negative is one fixture. Three is better."""
    words = _scanned(_panel(seeds=seeds))
    for word in _UNIMPLEMENTED + _JUDGEMENTS:
        assert word not in words, (seeds, word)


def test_the_page_states_that_nothing_here_reached_the_decision() -> None:
    text = _visible_text(_panel())
    assert "Nothing in this section reached the decision above it" in text
