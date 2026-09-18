"""Building price zones: anchored, online, and frozen at the anchor.

    zone_width_series(registry, series, policy)  ──►  FeatureSeries | None
    derive_price_zones(levels, width_series, ...) ──►  PriceZoneSet

**Construction is anchored, never clustering.** Levels are processed in the order
the market made them knowable. Each either falls inside the band of a zone that
already exists — and joins it — or opens a new zone anchored at its own price.
Zones are never merged, split, resized or deleted.

This is chosen on measurement, not taste. A clustering algorithm answers *given
all these levels, how do they group*, a question with a different answer every
time a level is added, which makes every published zone provisional. Report 0050
measured what the three natural readings of report 0047 §15.2's *"clustered"*
actually do: single-linkage chained **247 of 339 levels into one zone** on BTC
1D, with zones up to 94x the policy's own tolerance; a diameter-bounded greedy is
not reflection-symmetric and rewrote history on 120,441 prefix events. The
anchored rule produced **0** illegal prefix events across 1,836 policy-series
cells, because prefix stability is a property of the construction rather than a
claim checked afterwards.

**Nothing here is reimplemented.** Swing detection, labelling, level projection,
crossing classification and ATR each keep their single implementation in
`fmis.market_structure`, `fmis.level_crossing` and `fmis.features`. This module
reads a level's price and its origin's own ``knowable_from``, reads a feature
history it was handed, and performs exactly one arithmetic operation of its
own — the half-width — which `ZoneWidthPolicy.width_from` supplies the multiple
for.

**Pure.** No clock, no network, no randomness, no global state, no cache. Two
calls over equal inputs return equal zone sets, across processes and hash seeds.
"""

from __future__ import annotations

from collections.abc import Sequence

from fmis.data import CandleSeries
from fmis.features.registry import FeatureRegistry
from fmis.features.series import FeatureSeries, supports_series
from fmis.features.types import FeatureContext
from fmis.level_crossing import PriceLevel
from fmis.price_zones.models import (
    PRICE_ZONE_LIMITATIONS,
    ZONE_WIDTH_POLICY_V1,
    PriceZone,
    PriceZoneSet,
    SeriesWindowMismatchError,
    ZoneMember,
    ZoneWidthPolicy,
    ZoneWidthPolicyMismatchError,
)

__all__ = ["zone_width_series", "derive_price_zones"]


def zone_width_series(
    registry: FeatureRegistry,
    series: CandleSeries,
    *,
    policy: ZoneWidthPolicy = ZONE_WIDTH_POLICY_V1,
) -> FeatureSeries | None:
    """The policy's own named feature, computed over ``series`` by its owner.

    Args:
        registry: the feature registry the caller already built. The policy names
            its feature by string and this is where that name is resolved, so the
            width and the sheet's own reading of that indicator come from **one**
            feature instance rather than two that agree.
        series: the closed candle series. Closing is idempotent and the feature
            closes again for itself.
        policy: the width policy whose feature is wanted.

    Returns:
        The named feature's whole aligned history, or `None` when the feature is
        not registered or cannot produce a history. `None` means *no zones can be
        built for this series*, which the caller states rather than papers over —
        it never means *use some other width*.

    Raises:
        TypeError: ``registry`` or ``series`` is of the wrong type.
    """
    if not isinstance(registry, FeatureRegistry):
        raise TypeError(
            f"registry must be a FeatureRegistry, got {type(registry).__name__}"
        )
    if not isinstance(series, CandleSeries):
        raise TypeError(f"series must be a CandleSeries, got {type(series).__name__}")
    if not isinstance(policy, ZoneWidthPolicy):
        raise TypeError(
            f"policy must be a ZoneWidthPolicy, got {type(policy).__name__}"
        )
    if not registry.has(policy.feature_name):
        return None
    feature = registry.get(policy.feature_name)
    if not supports_series(feature):
        return None
    return feature.compute_series(FeatureContext(primary=series))


def _width_table(width_series: FeatureSeries) -> dict[int, float]:
    """``{closed-candle index: width feature value}`` over the defined points.

    A point carrying an ``undefined_reason`` contributes nothing: *warmed up and
    still undefined* is an absence, and an absence is never interpolated.
    A non-numeric value — a structured reading such as MACD's mapping — is
    likewise skipped rather than coerced, because there is no defensible way to
    turn three components into one width.
    """
    table: dict[int, float] = {}
    for point in width_series.points:
        value = point.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        table[point.index] = float(value)
    return table


def _width_value_at(table: dict[int, float], index: int) -> float | None:
    """The feature's value at ``index``, or the nearest **earlier** one; never later.

    Falling forward would be lookahead dressed as a lookup: a zone established at
    bar 20 would be sized by volatility that had not been measured yet. Returning
    `None` before warm-up is the honest answer, and the caller treats a level it
    cannot size as unassigned rather than guessing a width for it.

    For ATR the table is dense from warm-up onward, so the fallback is
    unreachable in the live path; it exists because `FeatureSeries` permits a
    gap in general and a silent `KeyError` at that point would be a defect
    discovered in production.
    """
    found = table.get(index)
    if found is not None:
        return found
    earlier = [known for known in table if known < index]
    if not earlier:
        return None
    return table[max(earlier)]


def derive_price_zones(
    levels: Sequence[PriceLevel],
    width_series: FeatureSeries,
    *,
    policy: ZoneWidthPolicy = ZONE_WIDTH_POLICY_V1,
) -> PriceZoneSet:
    """Group confirmed structural levels into frozen bands, causally.

    Args:
        levels: confirmed `PriceLevel`s from `structural_levels`. Every one must
            carry a `LevelOrigin`; a level without one has no establishment bar
            and therefore no place in a causal order.
        width_series: the whole aligned history of the feature ``policy`` names,
            typically from `zone_width_series`. Its `SeriesIdentity` becomes the
            zone set's, by reference (ADR-0018).
        policy: the versioned width policy, stamped by value onto every zone it
            produces so a stored zone stays reproducible after the default moves.

    Returns:
        A `PriceZoneSet` whose zones are in **creation order**, plus every level
        that could not be sized, carried as ``unassigned``.

    Raises:
        TypeError: a wrong argument type, or a level that is not a `PriceLevel`.
        ValueError: a level without a `LevelOrigin`.
        ZoneWidthPolicyMismatchError: ``width_series`` is not the feature
            ``policy`` names.
        SeriesWindowMismatchError: a level became knowable at a bar the width
            history never saw, so the two inputs are not a pair.

    **The rules, each one a decision report 0050 measured:**

    1. **Establishment order.** Levels are ordered by ``origin.knowable_from``,
       the bar the market made them knowable — never by price, and never by the
       pivot's own bar, which would let a zone exist before its level did.
    2. **The band is frozen at the anchor.** ``w = k x feature`` read at the
       anchor's own establishment bar; ``low = price - w/2``, ``high = price +
       w/2``. Never recomputed from the latest reading (983,916 illegal prefix
       events), never widened by a joining member (34,192).
    3. **Membership is inclusive at both edges and by price alone.** An `UPPER`
       and a `LOWER` level may share a band: an area is an area, and the side is
       a fact about the swing that made the level, which travels on the level.
    4. **Ties go to the oldest band, not the nearest centre.** Nearest centre
       compares the difference of two nearly equal floats and flipped on 35 % of
       series under a rescale; comparing a price against a boundary is stable
       under any perturbation smaller than the distance to it, and it says
       something defensible — the area that was already there keeps the level.
    5. **One bar is one instant.** Every level established at bar *i* is tested
       against the bands that existed **before** *i*, and the bands opened at *i*
       are opened together, so a band opened at *i* cannot claim another level
       from *i*. One candle can be both a swing high and a swing low, so two
       levels can share an establishment bar; any order between them would have
       to come from their side or their price, and both invert under reflection.
    6. **No width, no zone.** A level whose establishment bar precedes the
       feature's warm-up is carried as ``unassigned``. It is never given a
       default width — a default here would be the invented threshold this
       design exists to avoid, placed where nobody would look for it.
    """
    if isinstance(levels, (str, bytes)) or not isinstance(levels, Sequence):
        raise TypeError(
            f"levels must be a non-string sequence, got {type(levels).__name__}"
        )
    if not isinstance(width_series, FeatureSeries):
        raise TypeError(
            f"width_series must be a FeatureSeries, got {type(width_series).__name__}"
        )
    if not isinstance(policy, ZoneWidthPolicy):
        raise TypeError(
            f"policy must be a ZoneWidthPolicy, got {type(policy).__name__}"
        )
    if width_series.name != policy.feature_name:
        raise ZoneWidthPolicyMismatchError(
            f"policy {policy.policy_id!r} sizes bands from "
            f"{policy.feature_name!r} and the supplied history is "
            f"{width_series.name!r}; a zone stamped with a policy it was not "
            "built under is not reproducible from its own record"
        )

    members = tuple(ZoneMember(level) for level in levels)
    # The one mis-pairing this engine could otherwise absorb silently: a level
    # whose establishment bar the width history never saw would fall back to the
    # nearest earlier reading and be sized from the wrong volatility.
    for member in members:
        if member.joined_index >= width_series.closed_candles:
            raise SeriesWindowMismatchError(
                f"a level became knowable at bar {member.joined_index}, but "
                f"{width_series.name!r} was computed over "
                f"{width_series.closed_candles} closed candles; the levels and "
                "the width history do not describe the same series"
            )
    table = _width_table(width_series)
    identity = width_series.identity

    # Stable sort on the establishment bar alone. Within one bar the input order
    # is preserved untouched, which is `structural_levels`' own canonical order:
    # ordering inside a bar on any property of the level would break the tie on
    # side or price, and both invert under reflection.
    ordered = sorted(members, key=lambda member: member.joined_index)

    bands: list[list] = []  # [low, high, width, [members...]]
    unassigned: list[PriceLevel] = []
    position = 0
    while position < len(ordered):
        end = position
        bar = ordered[position].joined_index
        while end < len(ordered) and ordered[end].joined_index == bar:
            end += 1
        # The bands that existed *before* this bar. Frozen for the whole epoch,
        # so nothing opened within it can claim a sibling.
        existing = len(bands)
        opened: list[list] = []
        for member in ordered[position:end]:
            claimed = False
            for slot in range(existing):
                band = bands[slot]
                if band[0] <= member.price <= band[1]:
                    band[3].append(member)
                    claimed = True
                    break
            if claimed:
                continue
            value = _width_value_at(table, member.joined_index)
            if value is None:
                unassigned.append(member.level)
                continue
            width = policy.width_from(value)
            if width <= 0:
                # A non-positive reading cannot produce a band, and a zero-width
                # band would admit only exactly-equal prices — a different policy,
                # arrived at by accident. Carried as unsized, like a missing one.
                unassigned.append(member.level)
                continue
            half = width / 2.0
            opened.append([member.price - half, member.price + half, width, [member]])
        bands.extend(opened)
        position = end

    zones = tuple(
        PriceZone(
            low=low,
            high=high,
            anchor=band_members[0],
            members=tuple(band_members),
            width=width,
            width_policy=policy,
            identity=identity,
        )
        for low, high, width, band_members in bands
    )
    return PriceZoneSet(
        identity=identity,
        width_policy=policy,
        zones=zones,
        unassigned=tuple(unassigned),
        limitations=PRICE_ZONE_LIMITATIONS,
    )
