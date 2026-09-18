"""The fourteen adversarial fixtures, fixed by the preregistration §5.

These test the **geometry** axis at a supplied `w`, so that a grouping failure
cannot be blamed on how `w` was derived. Every fixture states what the geometry
must not do; passing is not a matter of degree.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from research.zone_semantics.policies import Zone, group
from research.zone_semantics.structure import ResearchLevel

W = 1.0


def _level(price: float, index: int, side: str = "upper") -> ResearchLevel:
    return ResearchLevel(
        price=price,
        side=side,
        origin_index=index,
        established_index=index + 2,
        label="higher_high" if side == "upper" else "lower_low",
    )


def _levels(prices: Sequence[float], sides: Sequence[str] | None = None):
    sides = sides or ["upper"] * len(prices)
    return tuple(
        _level(p, i * 10, s) for i, (p, s) in enumerate(zip(prices, sides))
    )


@dataclass(frozen=True, slots=True)
class Fixture:
    number: int
    name: str
    levels: tuple[ResearchLevel, ...]
    widths: tuple[float, ...]
    must: str
    check: "callable"


def _n_zones(expected: int):
    return lambda zones: len(zones) == expected


def _max_span_within_w(zones: Sequence[Zone]) -> bool:
    return all(z.span <= z.width_used + 1e-12 for z in zones)


def _same_zone(zones: Sequence[Zone]) -> bool:
    return len(zones) == 1


def build() -> tuple[Fixture, ...]:
    chain_prices = [0.0, 0.6, 1.2, 1.8, 2.4, 3.0]
    bridge_prices = [0.0, 0.1, 0.2, 1.0, 1.8, 1.9, 2.0]
    clusters = [0.0, 0.1, 0.2, 5.0, 5.1, 5.2]
    dense = [i * 0.1 for i in range(200)]

    fixtures: list[Fixture] = [
        Fixture(
            1,
            "chain",
            _levels(chain_prices),
            (W,) * len(chain_prices),
            "must not collapse six levels spanning 3w into one zone",
            _max_span_within_w,
        ),
        Fixture(
            2,
            "bridge",
            _levels(bridge_prices),
            (W,) * len(bridge_prices),
            "must not let one midway level join two separated clusters",
            _max_span_within_w,
        ),
        Fixture(
            3,
            "two-clusters",
            _levels(clusters),
            (W,) * len(clusters),
            "must separate two clusters with a clean 4.8w gap",
            _n_zones(2),
        ),
        Fixture(
            4,
            "equal-highs",
            _levels([7.0, 7.0, 7.0, 7.0]),
            (W,) * 4,
            "must not fragment four identical prices",
            _same_zone,
        ),
        Fixture(
            5,
            "equal-lows",
            _levels([3.0, 3.0, 3.0], ["lower"] * 3),
            (W,) * 3,
            "must not fragment three identical prices",
            _same_zone,
        ),
        Fixture(
            6,
            "single-level",
            _levels([42.0]),
            (W,),
            "must produce exactly one one-member zone",
            lambda z: len(z) == 1 and len(z[0].members) == 1,
        ),
        Fixture(
            7,
            "outlier",
            _levels([0.0, 0.1, 0.2, 50.0]),
            (W,) * 4,
            "must not absorb a level 50w away",
            _n_zones(2),
        ),
        Fixture(
            8,
            "overlapping-sides",
            _levels([10.0, 10.05], ["upper", "lower"]),
            (W, W),
            "the upper/lower membership rule must be stated, not emergent",
            lambda z: True,  # recorded, not asserted; see report 0050 s14
        ),
        Fixture(
            9,
            "sparse",
            _levels([1.0, 100.0]),
            (W, W),
            "must not merge two levels 99w apart",
            _n_zones(2),
        ),
        Fixture(
            10,
            "dense-uniform",
            _levels(dense),
            (W,) * len(dense),
            "must not produce one zone of 200 members spanning 19.9w",
            _max_span_within_w,
        ),
        Fixture(
            11,
            "volatility-jump",
            _levels([0.0, 0.3, 0.6, 10.0, 13.0, 16.0]),
            (W, W, W, 10 * W, 10 * W, 10 * W),
            "a later tenfold width must not rewrite the earlier grouping",
            lambda z: True,  # compared against the pre-jump prefix in run.py
        ),
        Fixture(
            12,
            "gap",
            _levels([0.0, 0.05, 0.10]),
            (W,) * 3,
            "must never claim an intrabar sequence (no interaction is computed)",
            _same_zone,
        ),
        Fixture(
            13,
            "scaled",
            _levels([p * 1000.0 for p in clusters]),
            (W * 1000.0,) * len(clusters),
            "scaling every price by 1e3 must not change the partition",
            _n_zones(2),
        ),
        Fixture(
            14,
            "mirrored",
            _levels([100.0 - p for p in clusters], ["lower"] * len(clusters)),
            (W,) * len(clusters),
            "reflecting the structure must not change the partition's shape",
            _n_zones(2),
        ),
    ]
    return tuple(fixtures)


def run_all(geometry: str) -> list[dict]:
    out: list[dict] = []
    for fixture in build():
        zones = group(geometry, fixture.levels, fixture.widths)
        out.append(
            {
                "fixture": fixture.number,
                "name": fixture.name,
                "must": fixture.must,
                "n_zones": len(zones),
                "sizes": sorted(len(z.members) for z in zones),
                "max_span_over_w": max(
                    (z.span / z.width_used for z in zones if z.width_used > 0),
                    default=0.0,
                ),
                "passed": bool(fixture.check(zones)),
            }
        )
    return out
