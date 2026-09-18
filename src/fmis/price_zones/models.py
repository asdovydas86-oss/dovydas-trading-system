"""Value types for deterministic price zones.

A `PriceZone` is a **bounded price band, written once**, at the moment one
confirmed structural level had no existing band to join — and thereafter
collecting the confirmed levels that fall inside it. It is not support, not
resistance, not strong, not weak, not a breakout and not a reason to trade.

Three distinctions this module exists to keep apart, each recorded in
ADR-0033 and `docs/design/PRICE_ZONE_ENGINE_V1.md`:

**A zone is not a cluster.** Clustering is a function of a whole set and has a
different answer every time a level is added. A zone is a record written at an
instant, which is why it can be published before the market is finished.

**A zone is not a level.** `PriceLevel` equality stays exact, everywhere,
unchanged. Two levels in one zone are still two different levels —
``PriceLevel(A) != PriceLevel(B)`` while ``zone.members == (A, B)`` — and that is
not a contradiction but the whole point. The tolerance this package introduces is
scoped to **one** thing: deciding which confirmed levels a band contains. It
reaches `classify_comparison`, `CrossingKind` and `LevelSide` nowhere.

**A zone has no role.** `ZonePricePosition` is **geometry** and nothing else. The
role vocabulary ADR-0033 §8 approves — ``UNTESTED``, ``HELD_FROM_ABOVE``,
``HELD_FROM_BELOW``, ``BROKEN_UPWARD``, ``BROKEN_DOWNWARD``, ``ROLE_FLIPPED``,
``INDETERMINATE`` — requires an interaction engine that does not exist, and is
deliberately **not declared here**: a vocabulary present in the code is a
vocabulary something will populate. Deriving a role from where price stands is
forbidden, and report 0050 measured what it would cost — 22 % of zones above the
1W close have no interaction history at all, and 39 % (1W) / 50 % (1D) have had
price close on **both** sides since they were established, so the position rule
is not merely sometimes wrong, it is not well-defined over time.

Deliberately absent from every type here: strength, quality, score, rank,
confidence, direction, target, invalidation, and the words support and
resistance in any field, value or message.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from fmis.data import SeriesIdentity
from fmis.level_crossing import PriceLevel

__all__ = [
    "PriceZoneError",
    "ZoneWidthPolicyMismatchError",
    "SeriesWindowMismatchError",
    "ZoneWidthScale",
    "ZoneWidthReference",
    "ZoneWidthPolicy",
    "ZONE_WIDTH_POLICY_V1",
    "ADMISSIBLE_MULTIPLE",
    "ZonePricePosition",
    "ZoneMember",
    "PriceZone",
    "PriceZoneSet",
    "PRICE_ZONE_LIMITATIONS",
]


class PriceZoneError(Exception):
    """Base class for every price-zone failure.

    Follows the established package-error convention — `IngestError`,
    `LevelCrossingError`, `SeriesContextError` — so a caller can catch this
    layer's failures as a group.
    """


class ZoneWidthPolicyMismatchError(PriceZoneError, ValueError):
    """The supplied width series is not the one the policy names.

    Also a `ValueError`, matching `DuplicateLevelError(LevelCrossingError,
    ValueError)`, so an existing caller catching `ValueError` at a boundary keeps
    working.

    Raised rather than tolerated. A `ZoneWidthPolicy` stamped on a zone is a
    claim about how that zone's band was produced; letting a caller size bands
    with ``atr_28`` while stamping ``atr_14`` would make every stored zone
    unreproducible from its own record, which is the one guarantee §4.3 of the
    design exists to give.
    """


class SeriesWindowMismatchError(PriceZoneError, ValueError):
    """The levels and the width history do not describe the same closed series.

    A level established at bar *i* needs a width read at bar *i*. If the width
    history never saw bar *i*, the two inputs are not a pair — a shorter feature
    window, a different symbol, or a level run from another timeframe — and the
    engine would otherwise fall back to the nearest **earlier** reading and size
    every affected band from the wrong volatility, silently.

    `PriceLevel` carries no `SeriesIdentity`, so identity cannot be compared
    here. The bar index can, and the check is exact: a level cannot become
    knowable at a bar its own series never closed. Raised rather than repaired,
    on the repository's validate-never-repair rule, and it makes the one
    mis-pairing this engine cannot otherwise detect **loud instead of plausible**.
    """


class ZoneWidthScale(str, Enum):
    """In what units a band's width is expressed.

    One member in V1, and the single member is the point: report 0050 tested four
    scale families over 55,728 policy cells and exactly one survived.

    Deliberately absent, each rejected on stated evidence (ADR-0033 §7):

      * **percentage of price** — not long/short symmetric, passing 6 % of cells.
        A width proportional to price cannot mirror, because zero is an absolute
        floor and there is no corresponding ceiling.
      * **absolute / tick distance** — not expressible. `fmis.data.Candle`
        carries no instrument metadata and no tick size exists anywhere under
        ``src/``. Revisitable the day an ingestion tick model exists.
      * **structural spacing** — the naive form reads the whole level set, a
        quantity that did not exist when the zone was established (696,588
        illegal prefix events). A causal form was implemented, given the same
        symmetry repairs the winning geometry received, and still failed unit
        invariance.
    """

    ATR_MULTIPLE = "atr_multiple"


class ZoneWidthReference(str, Enum):
    """**When** a volatility-derived width is read. The temporal decision, named.

    One member, and it is the one measurement selected. The two alternatives were
    both implemented and both refuted:

      * reading the **latest** value and re-sizing historical bands produced
        983,916 illegal prefix events — every historical zone in the sample moved
        its own boundaries every time a new bar arrived;
      * letting a **joining member** widen the band produced 34,192 — a level
        outside the zone yesterday is inside it today with no new information
        about that level.

    Neither member for either alternative exists here, so neither is selectable.
    """

    AT_ANCHOR_ESTABLISHMENT = "at_anchor_establishment"


#: The admissible region for `ZoneWidthPolicy.multiple`, inclusive, as report
#: 0050 bounded it — and **enforced**, not advised.
#:
#: Above ``1.00`` long/short symmetry is lost (first failures at ``1.25``); below
#: ``0.10`` the representation degenerates toward one-level-one-zone (``k = 0``
#: leaves 96 % singletons); at ``k >= 2.00`` distinct areas are destroyed
#: outright (99.4 % of levels merged, largest zone 44 members).
#:
#: A bound that is documented but not enforced is a bound a later caller steps
#: over without noticing. This is the one thing about `k` that **was** measured,
#: so it is the one thing the type system is allowed to insist on.
ADMISSIBLE_MULTIPLE: tuple[float, float] = (0.10, 1.00)


@dataclass(frozen=True, slots=True)
class ZoneWidthPolicy:
    """How a band's width is produced — named, versioned, and stamped on every zone.

    The shape `RegimePolicy` already uses, for the same reason: a zone recorded a
    year ago must stay reproducible from its own record after the default
    changes. The policy is **stamped by value onto each zone**, never referenced
    by name from a mutable global.

    ``feature_name`` names the **production feature**, by name. This package
    reimplements no ATR, no swing detection, no level projection and no crossing
    classification; it is handed the named feature's own history and rejects any
    other (`ZoneWidthPolicyMismatchError`).

    ``multiple`` is `k`. **It is declared, not measured**, and the distinction is
    load-bearing enough to belong in the type's own documentation rather than
    only in an ADR. Report 0050 found every descriptive metric **monotone** in
    `k` over the admissible region: there is no plateau, no interior optimum and
    no knife-edge, because `k` is a **resolution control** and a study that
    deliberately excludes outcome data cannot derive a preferred value from
    representation alone. What the evidence fixes is the admissible region, which
    `ADMISSIBLE_MULTIPLE` enforces. `k` is therefore **not** a calibrated trading
    threshold, a prediction threshold, an edge claim or a confidence value, and
    no code or rendered string may present it as one.

    Frozen, slotted and hashable, so a stamped policy cannot drift and two zones
    built under one policy share one object rather than two copies.
    """

    policy_id: str
    scale: ZoneWidthScale
    feature_name: str
    multiple: float
    temporal_reference: ZoneWidthReference

    def __post_init__(self) -> None:
        for name in ("policy_id", "feature_name"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise TypeError(f"{name} must be a non-empty str")
        if not isinstance(self.scale, ZoneWidthScale):
            raise TypeError(
                f"scale must be a ZoneWidthScale, got {type(self.scale).__name__}"
            )
        if not isinstance(self.temporal_reference, ZoneWidthReference):
            raise TypeError(
                "temporal_reference must be a ZoneWidthReference, got "
                f"{type(self.temporal_reference).__name__}"
            )
        # bool is an int subclass; a multiple of True is a programming error.
        if isinstance(self.multiple, bool) or not isinstance(
            self.multiple, (int, float)
        ):
            raise TypeError(
                f"multiple must be a number, got {type(self.multiple).__name__}"
            )
        if not math.isfinite(self.multiple):
            raise ValueError("multiple must be a finite number")
        low, high = ADMISSIBLE_MULTIPLE
        if not low <= self.multiple <= high:
            raise ValueError(
                f"multiple must lie in the admissible region [{low}, {high}] "
                f"report 0050 measured, got {self.multiple}. Above the upper "
                "bound long/short symmetry is lost; below the lower bound the "
                "representation degenerates toward one level per zone"
            )

    def width_from(self, feature_value: float) -> float:
        """The band width this policy produces from one reading of its feature.

        The **one** place ``k * atr`` is written. A caller that multiplied for
        itself would be a second implementation of the policy, and the stamp on
        the zone would stop being a reproduction recipe.
        """
        return self.multiple * feature_value


#: The declared V1 width policy — **one policy, shared by every timeframe role**.
#:
#: ``k = 0.50`` is a **declared V1 product/representation parameter**, accepted
#: by the owner on 2026-09-18 in knowledge of ADR-0033 §6. It is not an
#: empirically discovered optimum: report 0050 bounded the admissible region and
#: deliberately refused to identify a value inside it.
#:
#: **One `k` for 1W, 1D and 4H.** No per-role constant exists, hidden or
#: otherwise. If evidence later shows one shared `k` produces materially bad
#: product behaviour, that is a new explicit research and product decision, not a
#: quiet second default.
ZONE_WIDTH_POLICY_V1 = ZoneWidthPolicy(
    policy_id="atr14-anchor-0_50",
    scale=ZoneWidthScale.ATR_MULTIPLE,
    feature_name="atr_14",
    multiple=0.50,
    temporal_reference=ZoneWidthReference.AT_ANCHOR_ESTABLISHMENT,
)


class ZonePricePosition(str, Enum):
    """Where a reference price stands relative to one band. **Geometry only.**

    Read the members as sentences about the **price**, which is why every one of
    them starts with the word: ``PRICE_ABOVE`` means *the price is above this
    band*, not *this band is above something*.

    **This is not a role and can never become one.** A band the price sits above
    is not support; one it sits below is not resistance; one it sits inside is
    not a retest; and leaving one is not a breakout. Role comes from interaction
    history — ADR-0033 §8, the report 0047 review disposition §E — and no
    interaction engine exists. Report 0050 measured the forbidden derivation:
    39 % of 1W zones and 50 % of 1D zones have had price close on both sides
    since they were established, so the position rule would have called one
    unchanged zone *support* on some days and *resistance* on others.

    Deliberately absent: SUPPORT, RESISTANCE, HELD, BROKEN, RECLAIMED, RETESTED,
    UNTESTED, FLIPPED, and every other member that would state a reading.
    """

    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    PRICE_INSIDE = "price_inside"


@dataclass(frozen=True, slots=True)
class ZoneMember:
    """One confirmed `PriceLevel`, held **by reference**, plus the bar it became knowable.

    The zone adds nothing to the level and reinterprets nothing: the level keeps
    its own price, its own side and its own `LevelOrigin` unchanged, and two
    members at an identical price with different origins stay two members.

    ``joined_index`` is a **projection, never a stored field** — it is the
    origin's own ``knowable_from``, which is ``index + confirmation_bars``. A
    ``confirmation_bars`` parameter here would be the ADR-0020 D1 hazard
    relocated one layer up and dressed as provenance: the approach ADR-0024
    records as explicitly rejected, and the same reason `structural_levels`
    refuses one.

    An origin is **required**, unlike on `PriceLevel` itself, where it is
    optional on purpose. Every member comes from `structural_levels`, which
    always sets one, and a member without an origin has no establishment bar —
    so it has no place in a causal ordering and could not be sized.
    """

    level: PriceLevel

    def __post_init__(self) -> None:
        if not isinstance(self.level, PriceLevel):
            raise TypeError(
                f"level must be a PriceLevel, got {type(self.level).__name__}"
            )
        if self.level.origin is None:
            raise ValueError(
                "a zone member must carry a LevelOrigin: without one there is no "
                "establishment bar, so the level has no place in the causal "
                "order zones are built in and no bar at which to read a width"
            )

    @property
    def joined_index(self) -> int:
        """The closed-candle index at which this level became knowable."""
        origin = self.level.origin
        assert origin is not None  # guaranteed by __post_init__
        return origin.knowable_from

    @property
    def price(self) -> float:
        """The member's price. A projection over the level, never a second copy."""
        return self.level.price


@dataclass(frozen=True, slots=True)
class PriceZone:
    """A frozen band, its anchor, and every confirmed level that has fallen inside it.

    ``low`` and ``high`` are **immutable after construction** and are a function
    of the anchor's price and the stamped width policy alone:

        low  = anchor.price - width / 2
        high = anchor.price + width / 2

    They are never recomputed from the latest volatility, never widened by a
    joining member, and never adjusted when the market moves. A zone is a record
    of where an area was, not a redrawing of the past.

    ``established_index`` is the **anchor's** bar — ⚠ deliberately not the last
    member's, which report 0047 §15.2 proposed. A zone whose identity depends on
    its last member has no identity until it stops growing.
    ``latest_member_index`` carries the last member's bar separately; it grows and
    never affects identity.

    **No `role`. No `strength`. No score, rank, quality or confidence.** A zone
    with twelve members and a zone with one are two facts, not a strong one and a
    weak one, and `member_count` is a size rather than a strength.

    Frozen and slotted, so a published zone cannot drift downstream.
    """

    low: float
    high: float
    anchor: ZoneMember
    members: tuple[ZoneMember, ...]
    width: float
    width_policy: ZoneWidthPolicy
    identity: SeriesIdentity

    def __post_init__(self) -> None:
        for name in ("low", "high", "width"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number, got {type(value).__name__}")
            if not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if self.width <= 0:
            raise ValueError(
                f"width must be positive, got {self.width}; a band of zero width "
                "would admit only exactly-equal prices and is not a policy this "
                "engine may produce silently"
            )
        if self.low > self.high:
            raise ValueError(f"low {self.low} cannot exceed high {self.high}")
        if not isinstance(self.anchor, ZoneMember):
            raise TypeError(
                f"anchor must be a ZoneMember, got {type(self.anchor).__name__}"
            )
        if not isinstance(self.width_policy, ZoneWidthPolicy):
            raise TypeError(
                "width_policy must be a ZoneWidthPolicy, got "
                f"{type(self.width_policy).__name__}"
            )
        if not isinstance(self.identity, SeriesIdentity):
            raise TypeError(
                f"identity must be a SeriesIdentity, got {type(self.identity).__name__}"
            )
        if not isinstance(self.members, tuple) or not self.members:
            raise TypeError("members must be a non-empty tuple of ZoneMember")
        for position, member in enumerate(self.members):
            if not isinstance(member, ZoneMember):
                raise TypeError(
                    f"members[{position}] must be a ZoneMember, got "
                    f"{type(member).__name__}"
                )
            if not self.low <= member.price <= self.high:
                raise ValueError(
                    f"members[{position}] sits at {member.price}, outside the "
                    f"band [{self.low}, {self.high}]. A band never moves to "
                    "admit a member"
                )
        # Identity, not equality: the anchor **is** the first member, not an
        # object that looks like it. Two equal members would satisfy `==` and
        # would still be a second source of truth for the band's origin.
        if self.members[0] is not self.anchor:
            raise ValueError(
                "the anchor must be the first member, by identity: the level "
                "that opened the band is the one the band is centred on"
            )
        previous = self.members[0].joined_index
        for position, member in enumerate(self.members[1:], start=1):
            if member.joined_index < previous:
                raise ValueError(
                    f"members[{position}] became knowable at bar "
                    f"{member.joined_index}, before members[{position - 1}] at "
                    f"{previous}; members are held in join order, which is the "
                    "order the market made them knowable"
                )
            previous = member.joined_index

    @property
    def established_index(self) -> int:
        """The bar this zone became knowable — the **anchor's**, never the last member's."""
        return self.anchor.joined_index

    @property
    def latest_member_index(self) -> int:
        """The most recent member's bar. Grows; never part of the zone's identity."""
        return self.members[-1].joined_index

    @property
    def member_count(self) -> int:
        """How many confirmed levels fall inside this band.

        **A size, never a strength.** A level touched many times is not thereby a
        strong level, and six levels in one band is not a stronger area than two;
        that reading needs interaction semantics this repository does not have.
        """
        return len(self.members)

    @property
    def levels(self) -> tuple[PriceLevel, ...]:
        """The member levels themselves, by reference, in join order."""
        return tuple(member.level for member in self.members)

    def contains(self, price: float) -> bool:
        """Does this band contain ``price``? **Inclusive at both edges.**"""
        return self.low <= price <= self.high

    def price_position(self, reference_price: float) -> ZonePricePosition:
        """Where ``reference_price`` stands relative to this band. **Geometry only.**

        Named `price_position` and returning `ZonePricePosition` so that a caller
        reaching for a role finds no method that could be mistaken for one. See
        `ZonePricePosition` for what this may never be read as.
        """
        if self.contains(reference_price):
            return ZonePricePosition.PRICE_INSIDE
        if reference_price > self.high:
            return ZonePricePosition.PRICE_ABOVE
        return ZonePricePosition.PRICE_BELOW

    def distance_from(self, reference_price: float) -> float:
        """The gap between ``reference_price`` and the nearest edge of this band.

        Exactly and only:

            price inside the band   -> 0.0
            price above the band    -> price - high
            price below the band    -> low - price

        Non-negative by construction, and **transparent on purpose**: it is a
        presentation quantity, used to put the nearest areas first on a page, and
        a reader must be able to reproduce it from the two numbers printed beside
        it.

        **It is not a score, a rank, a strength or a relevance.** Nearer is not
        more important; it is only nearer. Nothing in this repository has
        measured that proximity to a structural area predicts anything.
        """
        if self.contains(reference_price):
            return 0.0
        if reference_price > self.high:
            return reference_price - self.high
        return self.low - reference_price


@dataclass(frozen=True, slots=True)
class PriceZoneSet:
    """Every zone one series produced, plus the levels that could not be sized.

    ``zones`` are in **creation order** — the order the market opened them. That
    is the order in which prefix stability is a property rather than a claim: a
    longer prefix appends, and never inserts, so a consumer holding position *n*
    still holds the same zone after more candles arrive. A surface that wants
    them by price or by distance sorts them itself, and says that it did.

    ``unassigned`` holds confirmed levels that produced **no zone at all**,
    because the width policy's feature had no value at their establishment bar.
    They are carried, with a count, rather than dropped or given a default width:
    a default here would be the invented threshold this whole design exists to
    avoid, placed at the one point where nobody would look for it.

    ``overlapping`` is a projection rather than a repair. Bands overlap — at
    ``k = 0.50``, 70 % of adjacent pairs — so a price may sit inside several
    zones at once. **Zones are never merged because their bands intersect.**
    Membership is unique; physical overlap is a genuine property of the
    representation and is exposed rather than smoothed away.
    """

    identity: SeriesIdentity
    width_policy: ZoneWidthPolicy
    zones: tuple[PriceZone, ...] = ()
    unassigned: tuple[PriceLevel, ...] = ()
    limitations: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identity, SeriesIdentity):
            raise TypeError(
                f"identity must be a SeriesIdentity, got {type(self.identity).__name__}"
            )
        if not isinstance(self.width_policy, ZoneWidthPolicy):
            raise TypeError(
                "width_policy must be a ZoneWidthPolicy, got "
                f"{type(self.width_policy).__name__}"
            )
        if not isinstance(self.zones, tuple):
            raise TypeError("zones must be a tuple of PriceZone")
        previous = -1
        for position, zone in enumerate(self.zones):
            if not isinstance(zone, PriceZone):
                raise TypeError(
                    f"zones[{position}] must be a PriceZone, got "
                    f"{type(zone).__name__}"
                )
            if zone.identity != self.identity:
                raise ValueError(
                    f"zones[{position}] describes {zone.identity.symbol} "
                    f"{zone.identity.timeframe} and the set describes "
                    f"{self.identity.symbol} {self.identity.timeframe}; one set "
                    "cannot be about two series"
                )
            if zone.width_policy != self.width_policy:
                raise ValueError(
                    f"zones[{position}] was sized by a different policy than the "
                    "set declares; a set whose zones disagree about their own "
                    "width policy is not reproducible from its own record"
                )
            if zone.established_index < previous:
                raise ValueError(
                    f"zones[{position}] was established at bar "
                    f"{zone.established_index}, before zones[{position - 1}] at "
                    f"{previous}; zones are held in creation order, which is "
                    "what makes a longer prefix append rather than insert"
                )
            previous = zone.established_index
        if not isinstance(self.unassigned, tuple):
            raise TypeError("unassigned must be a tuple of PriceLevel")
        for position, level in enumerate(self.unassigned):
            if not isinstance(level, PriceLevel):
                raise TypeError(
                    f"unassigned[{position}] must be a PriceLevel, got "
                    f"{type(level).__name__}"
                )

    @property
    def zone_count(self) -> int:
        """How many zones this series produced. A projection over ``zones``."""
        return len(self.zones)

    @property
    def member_count(self) -> int:
        """How many confirmed levels fell inside a band. A size, never a strength."""
        return sum(zone.member_count for zone in self.zones)

    @property
    def unassigned_count(self) -> int:
        """How many confirmed levels produced no zone for want of a width."""
        return len(self.unassigned)

    @property
    def overlapping(self) -> tuple[tuple[int, int], ...]:
        """Index pairs whose bands intersect, in creation order. **Never merged.**

        Reported so a consumer can see that overlap is normal rather than
        discover it as a surprise. Inclusive at the edges, matching membership.
        """
        pairs: list[tuple[int, int]] = []
        for first in range(len(self.zones)):
            for second in range(first + 1, len(self.zones)):
                a, b = self.zones[first], self.zones[second]
                if a.low <= b.high and b.low <= a.high:
                    pairs.append((first, second))
        return tuple(pairs)

    def zones_containing(self, price: float) -> tuple[PriceZone, ...]:
        """Every zone whose band contains ``price``, in creation order.

        Plural on purpose. Bands overlap heavily, so a price inside three zones
        is normal and a method that returned one would be choosing. Creation
        order means element ``0`` is the **oldest** band containing the price —
        the one the membership rule itself prefers when several contain a level
        (§4 of ADR-0033) — so a surface naming one band and the engine assigning
        a level agree about which area a price is in.
        """
        return tuple(zone for zone in self.zones if zone.contains(price))

    def zones_above(self, price: float) -> tuple[PriceZone, ...]:
        """Every zone lying **wholly above** ``price``, in creation order.

        Wholly above, so this and `zones_below` and `zones_containing` partition
        the set: a band that contains the price is in neither.
        """
        return tuple(zone for zone in self.zones if zone.low > price)

    def zones_below(self, price: float) -> tuple[PriceZone, ...]:
        """Every zone lying **wholly below** ``price``, in creation order."""
        return tuple(zone for zone in self.zones if zone.high < price)

    def nearest_above(self, price: float) -> PriceZone | None:
        """The closest band wholly above ``price``, or `None` if none is.

        Closest by `PriceZone.distance_from`, broken by the band's own edges and
        then its establishment bar — a **total** order over properties of the
        zone itself, so two equidistant bands resolve identically on every run.

        **Not a ranking.** Nearer is nearer; nothing here has measured that it is
        more likely to matter. This exists so a surface can print *the nearest
        area above* without sorting a set it does not own.
        """
        return min(self.zones_above(price), key=_proximity_key(price), default=None)

    def nearest_below(self, price: float) -> PriceZone | None:
        """The closest band wholly below ``price``, or `None` if none is."""
        return min(self.zones_below(price), key=_proximity_key(price), default=None)

    def near(self, price: float, *, per_side: int = 3) -> tuple[PriceZone, ...]:
        """A bounded selection of the bands around ``price``, **high to low**.

        The ``per_side`` nearest bands above, up to ``per_side`` of the bands
        containing it (oldest first, §4's own preference) and the ``per_side``
        nearest below — returned in **descending price order**, so a page built
        from this reads top-down the way a chart does.

        A real symbol produces twenty to two hundred and fifty bands per role, so
        a consumer must select; this is the one place that selection is defined,
        beside the set it selects from, rather than in a renderer. The totals stay
        available on the set, so a surface can always say it is showing a part.

        Raises:
            ValueError: ``per_side`` is negative.
        """
        if isinstance(per_side, bool) or not isinstance(per_side, int):
            raise TypeError(f"per_side must be an int, got {type(per_side).__name__}")
        if per_side < 0:
            raise ValueError(f"per_side cannot be negative, got {per_side}")
        key = _proximity_key(price)
        chosen = (
            sorted(self.zones_above(price), key=key)[:per_side]
            + list(self.zones_containing(price))[:per_side]
            + sorted(self.zones_below(price), key=key)[:per_side]
        )
        # Total over the band's own edges and its establishment bar, so the order
        # cannot depend on how the three groups above were concatenated.
        return tuple(
            sorted(chosen, key=lambda zone: (-zone.high, -zone.low, zone.established_index))
        )


def _proximity_key(price: float):
    """A **total** order over zones by distance from ``price``.

    Total rather than merely by distance, so two bands equidistant from a price
    resolve identically on every run and in every input order. Ties break on the
    band's own edges and then on the bar it was established at — all properties
    of the zone itself, never its position in a list.

    Distance is `PriceZone.distance_from`'s own value; this function computes
    nothing of its own, and it orders nothing but presentation.
    """

    def key(zone: PriceZone) -> tuple[float, float, float, int]:
        return (
            zone.distance_from(price),
            zone.low,
            zone.high,
            zone.established_index,
        )

    return key


#: Limitations of the zone representation itself, stated **on the object** rather
#: than left in an ADR — a fact sheet that omits what it cannot say reads as more
#: complete than it is. The same convention `StructuralFactSheet.LIMITATIONS` and
#: `TECHNICAL_CONTEXT_LIMITATIONS` already hold.
PRICE_ZONE_LIMITATIONS: tuple[tuple[str, str], ...] = (
    (
        "PZ-1",
        "The width multiple k is declared, not measured. Report 0050 bounded "
        "the admissible region and found every descriptive metric monotone "
        "within it, so no optimum exists to discover from representation alone. "
        "k is a resolution control, never a calibrated threshold or an edge.",
    ),
    (
        "PZ-2",
        "A zone has no role. Whether price has held at an area or broken "
        "through it is a function of interaction history, which this repository "
        "does not yet derive. Position is geometry: a zone below price is not "
        "support and a zone above it is not resistance.",
    ),
    (
        "PZ-3",
        "Bands overlap heavily — at k = 0.50, 70 percent of adjacent pairs — so "
        "one price may sit inside several zones at once. Zones are never merged "
        "because their bands intersect.",
    ),
    (
        "PZ-4",
        "A band's edges are window-sensitive at the margin: ATR's Wilder seed "
        "moves with the first bar loaded, so a longer history shifts a band "
        "slightly. Measured pairwise agreement 0.995 at k = 0.50.",
    ),
    (
        "PZ-5",
        "ADR-0019 D2 is inherited: the first swing high and first swing low "
        "produce no level, so the earliest zone on each side is missing.",
    ),
    (
        "PZ-6",
        "A confirmed level whose establishment bar precedes the width feature's "
        "warm-up produces no zone and is carried as unassigned. It is never "
        "given a default width.",
    ),
    (
        "PZ-7",
        "Two bands opened by sibling levels on one bar can overlap, and a later "
        "level inside both is claimed by whichever the level run produced "
        "first. Report 0050 measured long/short symmetry holding at k <= 1.00 "
        "and failing from k = 1.25; the admissible region is enforced, and this "
        "residual is the mechanism behind that ceiling.",
    ),
)
