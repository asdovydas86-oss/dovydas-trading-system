"""Panels whose true dependence is known. **The estimator is tested before it is trusted.**

Milestone CC's residual estimator was believed for a whole milestone and then
shown by simulation to be structurally incapable of answering its own question.
The lesson is not "simulate afterwards". It is that an estimator must recover a
dependence it was *given* before it is allowed to report one it *found*.

This module generates paired-difference panels with a stated generative structure
and no market data of any kind. Every panel is a pure function of its seed —
`fmis.research_design.numeric.derive_seed`, so nothing here moves across
processes — and every scenario in `CALIBRATION_SCENARIOS` names the qualitative
ordering the estimator must reproduce.

**The generative model, written down once.**

    D[asset a, block b, observation k]
        = market * f[b]                     shared across every asset in block b
        + asset  * g[a]                     one asset's own level, across blocks
        + noise  * e[a, b, k]               idiosyncratic

Under that model the two quantities CD estimates are, for large panels,

    r_b   ≈ market^2 / (market^2 + asset^2 + noise^2)     between assets, same block
    rho_w ≈ asset^2  / (market^2 + asset^2 + noise^2)     within one asset

so a scenario can *state* what the estimator ought to find and the calibration
compares against a number nobody read off a result. The approximations are exact
in the balanced, one-observation-per-cell limit and drift with imbalance, which is
why the calibration asserts an **ordering and a tolerance**, never an equality.

**The market-factor-removed scenario is the important one.** It generates a large
common factor and then subtracts each block's cross-sectional mean — Milestone
CC's exact operation. A correct estimator must report a *low* between-asset
correlation on the differenced panel and CC's residual estimator must report
``-1/(K-1)`` on it whatever the true value was. That pair is what separates
"measured" from "structurally uninformative", and both halves are asserted.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from random import Random
from typing import Any, Final

from fmis.paired_dependence.models import (
    PairedDependenceError,
    require_count,
)

__all__ = [
    "SyntheticRow",
    "SyntheticScenario",
    "CALIBRATION_SCENARIOS",
    "generate_panel",
    "scenario_by_id",
]


@dataclass(frozen=True, slots=True)
class SyntheticRow:
    """The minimum an estimator reads. **No provenance, deliberately.**

    A synthetic row carries exactly the three attributes
    `fmis.paired_dependence.estimator` touches. Giving it a fabricated symbol, a
    fabricated digest and a fabricated timestamp would let a test pass that only
    works because a real row happens to carry them.
    """

    economic_asset: str
    bar_index: int
    difference: float


@dataclass(frozen=True, slots=True)
class SyntheticScenario:
    """One generative structure, with the ordering it must produce."""

    scenario_id: str
    description: str
    assets: int
    blocks: int
    observations_per_cell: int
    market: float
    asset: float
    noise: float
    remove_market_factor: bool = False
    unequal_assets: bool = False
    missing_block_fraction: float = 0.0
    duplicate_assets: int = 0
    block_structure: bool = False

    def __post_init__(self) -> None:
        require_count(self.assets, "assets", minimum=2)
        require_count(self.blocks, "blocks", minimum=2)
        require_count(self.observations_per_cell, "observations_per_cell", minimum=1)
        require_count(self.duplicate_assets, "duplicate_assets", minimum=0)
        for field in ("market", "asset", "noise"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PairedDependenceError(f"{field} must be a real number")
            if value < 0.0:
                raise PairedDependenceError(
                    f"{field} is a standard deviation and cannot be negative"
                )
        if self.noise <= 0.0 and self.market <= 0.0 and self.asset <= 0.0:
            raise PairedDependenceError(
                "a panel with no variance at all has no correlation to recover"
            )
        if not 0.0 <= self.missing_block_fraction < 1.0:
            raise PairedDependenceError(
                "missing_block_fraction must lie in [0, 1)"
            )

    @property
    def total_variance(self) -> float:
        return self.market**2 + self.asset**2 + self.noise**2

    @property
    def has_point_expectation(self) -> bool:
        """Whether a single number is the right thing to expect from this panel.

        Two scenarios deliberately have none. ``unequal_assets`` gives every
        asset a different cell size, so the cell-mean noise term differs per
        asset and no one ``r_b`` describes the panel; ``block_structure`` puts the
        common factor in half the timeline and not the other half, so the panel is
        **not exchangeable over blocks** and asking for its single exchangeable
        correlation is the wrong question. Both are kept because the estimator
        must still behave sensibly on them, and both are asserted by ordering
        alone rather than against a fabricated target.
        """
        return not (self.unequal_assets or self.block_structure)

    @property
    def expected_between_asset(self) -> float | None:
        """``r_b`` implied by the generative parameters, under `CELL_MEAN`.

        A cell holding ``c`` observations is averaged before the block axis sees
        it, so its idiosyncratic term has variance ``noise^2 / c`` while the
        shared block factor and the asset level are untouched:

            r_b = market^2 / (market^2 + asset^2 + noise^2 / c)

        With the market factor differenced out the expectation is **not zero**. It
        is ``-1 / (K - 1)``, and stating it that way is the whole point of the
        scenario: cross-sectional demeaning removes an exchangeable common
        component exactly and leaves residuals whose pairwise correlation is
        pinned at that value for *every* true correlation. That is Milestone CC's
        failure, written as an expectation this estimator must reproduce — if it
        returned zero here it would be hiding the artefact rather than exposing
        it.
        """
        if not self.has_point_expectation:
            return None
        if self.remove_market_factor:
            return -1.0 / (self.assets - 1)
        total = (
            self.market**2
            + self.asset**2
            + self.noise**2 / self.observations_per_cell
        )
        return (self.market**2 / total) if total else 0.0

    @property
    def expected_within_asset(self) -> float | None:
        """``rho_w`` implied by the generative parameters, over raw observations.

        Two observations on one asset always share its level; they share the
        block factor only when they fall in the same block, which happens with
        probability ``p`` under this generator. So

            rho_w = (asset^2 + p * market^2) / (market^2 + asset^2 + noise^2)

        and after the market factor is differenced out both the factor and its
        share of the total are gone, leaving ``asset^2 / (asset^2 + noise^2)``.
        """
        if not self.has_point_expectation:
            return None
        if self.remove_market_factor:
            denominator = self.asset**2 + self.noise**2
            return (self.asset**2 / denominator) if denominator else 0.0
        total = self.total_variance
        if not total:
            return 0.0
        per_asset = self.blocks * self.observations_per_cell
        if per_asset < 2:
            same_block = 0.0
        else:
            within = self.blocks * (
                self.observations_per_cell * (self.observations_per_cell - 1) / 2
            )
            same_block = within / (per_asset * (per_asset - 1) / 2)
        return (self.asset**2 + same_block * self.market**2) / total

    def payload(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "description": self.description,
            "assets": self.assets,
            "blocks": self.blocks,
            "observations_per_cell": self.observations_per_cell,
            "market": self.market,
            "asset": self.asset,
            "noise": self.noise,
            "remove_market_factor": self.remove_market_factor,
            "unequal_assets": self.unequal_assets,
            "missing_block_fraction": self.missing_block_fraction,
            "duplicate_assets": self.duplicate_assets,
            "block_structure": self.block_structure,
            "expected_between_asset": self.expected_between_asset,
            "expected_within_asset": self.expected_within_asset,
        }


#: The calibration grid. **Every case the milestone brief names, plus the two CC
#: taught this project to add** — a dominant market factor, and the same panel
#: with that factor differenced out.
CALIBRATION_SCENARIOS: Final[tuple[SyntheticScenario, ...]] = (
    SyntheticScenario(
        scenario_id="independent",
        description="No shared component of any kind. Both correlations are zero.",
        assets=15, blocks=60, observations_per_cell=1,
        market=0.0, asset=0.0, noise=1.0,
    ),
    SyntheticScenario(
        scenario_id="weak_between",
        description="A small common block factor. r_b about 0.05.",
        assets=15, blocks=60, observations_per_cell=1,
        market=0.2294, asset=0.0, noise=1.0,
    ),
    SyntheticScenario(
        scenario_id="moderate_between",
        description="A material common block factor. r_b about 0.20.",
        assets=15, blocks=60, observations_per_cell=1,
        market=0.5, asset=0.0, noise=1.0,
    ),
    SyntheticScenario(
        scenario_id="strong_between",
        description="A dominant common block factor. r_b about 0.50.",
        assets=15, blocks=60, observations_per_cell=1,
        market=1.0, asset=0.0, noise=1.0,
    ),
    SyntheticScenario(
        scenario_id="within_asset_only",
        description="Assets differ in level, blocks share nothing. rho_w about 0.50.",
        assets=15, blocks=60, observations_per_cell=3,
        market=0.0, asset=1.0, noise=1.0,
    ),
    SyntheticScenario(
        scenario_id="both_components",
        description="A common block factor AND per-asset levels, together.",
        assets=15, blocks=60, observations_per_cell=3,
        market=0.7071, asset=0.7071, noise=1.0,
    ),
    SyntheticScenario(
        scenario_id="unequal_observations",
        description="Strong dependence on a panel where assets differ tenfold in size.",
        assets=15, blocks=60, observations_per_cell=3,
        market=1.0, asset=0.0, noise=1.0, unequal_assets=True,
    ),
    SyntheticScenario(
        scenario_id="missing_overlap",
        description="Strong dependence where half of every asset's blocks are absent.",
        assets=15, blocks=60, observations_per_cell=1,
        market=1.0, asset=0.0, noise=1.0, missing_block_fraction=0.5,
    ),
    SyntheticScenario(
        scenario_id="repeated_within_asset",
        description="Many observations per asset per block, so cells reduce.",
        assets=15, blocks=60, observations_per_cell=6,
        market=0.5, asset=0.5, noise=1.0,
    ),
    SyntheticScenario(
        scenario_id="duplicated_identity",
        description=(
            "Five assets are duplicated under a second label. A symbol-keyed "
            "count would report twenty clusters where there are fifteen."
        ),
        assets=15, blocks=60, observations_per_cell=1,
        market=0.5, asset=0.0, noise=1.0, duplicate_assets=5,
    ),
    SyntheticScenario(
        scenario_id="dominant_market_factor",
        description="Crypto-like: the common factor is most of the variance.",
        assets=15, blocks=60, observations_per_cell=1,
        market=1.4142, asset=0.3, noise=0.7,
    ),
    SyntheticScenario(
        scenario_id="market_factor_removed",
        description=(
            "The dominant-factor panel with each block's cross-sectional mean "
            "subtracted — Milestone CC's operation, applied to a known panel."
        ),
        assets=15, blocks=60, observations_per_cell=1,
        market=1.4142, asset=0.3, noise=0.7, remove_market_factor=True,
    ),
    SyntheticScenario(
        scenario_id="non_exchangeable_blocks",
        description=(
            "The common factor is present in the first half of the timeline and "
            "absent in the second, so no single exchangeable r_b is correct."
        ),
        assets=15, blocks=60, observations_per_cell=1,
        market=1.0, asset=0.0, noise=1.0, block_structure=True,
    ),
    SyntheticScenario(
        scenario_id="ca_shaped",
        description=(
            "The shape Milestone CA actually produced: fifteen assets, roughly "
            "ten observations each, spread thinly over the timeline."
        ),
        assets=15, blocks=73, observations_per_cell=1,
        market=0.5, asset=0.0, noise=1.0, missing_block_fraction=0.86,
    ),
)


def scenario_by_id(scenario_id: str) -> SyntheticScenario:
    """One scenario by name.

    Raises:
        PairedDependenceError: no scenario carries that id.
    """
    for scenario in CALIBRATION_SCENARIOS:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise PairedDependenceError(
        f"no calibration scenario {scenario_id!r}; there are "
        f"{', '.join(item.scenario_id for item in CALIBRATION_SCENARIOS)}"
    )


def generate_panel(
    scenario: SyntheticScenario, *, block_bars: int, master_seed: int, replicate: int = 0
) -> tuple[SyntheticRow, ...]:
    """One realisation of ``scenario``. **A pure function of its identity.**

    ``block_bars`` is honoured so a generated panel lands in the blocks the
    estimator will cut: an observation for block ``b`` is given a bar index inside
    ``[b * block_bars, (b + 1) * block_bars)``, which is what makes
    `fmis.paired_dependence.estimator.block_index` recover the intended block.

    Raises:
        PairedDependenceError: ``block_bars`` cannot hold the requested
            observations per cell, so two observations would collide on one bar.
    """
    from fmis.research_design.numeric import derive_seed

    require_count(block_bars, "block_bars", minimum=1)
    if not isinstance(scenario, SyntheticScenario):
        raise PairedDependenceError("scenario must be a SyntheticScenario")
    if scenario.observations_per_cell > block_bars:
        raise PairedDependenceError(
            f"scenario {scenario.scenario_id!r} wants "
            f"{scenario.observations_per_cell} observations in a block of "
            f"{block_bars} bar(s); two of them would share a bar index"
        )

    generator = Random(
        derive_seed(
            master=master_seed,
            parts=[scenario.scenario_id, block_bars, replicate],
        )
    )
    names = [f"A{index:03d}" for index in range(scenario.assets)]
    factors = {}
    for block in range(scenario.blocks):
        active = (
            block < scenario.blocks // 2 if scenario.block_structure else True
        )
        factors[block] = generator.gauss(0.0, scenario.market) if active else 0.0
    levels = {name: generator.gauss(0.0, scenario.asset) for name in names}

    rows: list[SyntheticRow] = []
    for asset_position, name in enumerate(names):
        per_cell = scenario.observations_per_cell
        if scenario.unequal_assets:
            # A tenfold spread across the panel, deterministic in position.
            per_cell = 1 + (asset_position % 10) * scenario.observations_per_cell
            per_cell = min(per_cell, block_bars)
        for block in range(scenario.blocks):
            if scenario.missing_block_fraction and (
                generator.random() < scenario.missing_block_fraction
            ):
                continue
            for slot in range(per_cell):
                rows.append(
                    SyntheticRow(
                        economic_asset=name,
                        bar_index=block * block_bars + slot,
                        difference=(
                            factors[block]
                            + levels[name]
                            + generator.gauss(0.0, scenario.noise)
                        ),
                    )
                )

    if scenario.duplicate_assets:
        # The SAME economic exposure listed under a second provider symbol. Its
        # rows are the original's, so an identity rule that collapses them must
        # recover the original panel exactly and one that does not must inflate
        # the cluster count — which is what the hostile control asserts.
        duplicated: list[SyntheticRow] = []
        for name in names[: scenario.duplicate_assets]:
            for row in rows:
                if row.economic_asset == name:
                    duplicated.append(
                        SyntheticRow(
                            economic_asset=f"{name}-WRAPPED",
                            bar_index=row.bar_index,
                            difference=row.difference,
                        )
                    )
        rows.extend(duplicated)

    if scenario.remove_market_factor:
        rows = _remove_block_mean(rows, block_bars=block_bars)

    return tuple(sorted(rows, key=lambda item: (item.economic_asset, item.bar_index)))


def _remove_block_mean(
    rows: Sequence[SyntheticRow], *, block_bars: int
) -> list[SyntheticRow]:
    """Milestone CC's operation: subtract each block's cross-sectional mean.

    Blocks holding fewer than two assets produce no factor and are dropped — a
    "market" of one asset is that asset, and subtracting it would zero the row by
    construction. This is `fmis.universe.dependence.market_residuals`' own rule,
    restated here over blocks rather than days because the synthetic panel has no
    calendar.
    """
    by_block: dict[int, list[SyntheticRow]] = {}
    for row in rows:
        by_block.setdefault(row.bar_index // block_bars, []).append(row)
    kept: list[SyntheticRow] = []
    for _block, members in sorted(by_block.items()):
        if len({item.economic_asset for item in members}) < 2:
            continue
        centre = statistics.fmean(item.difference for item in members)
        kept.extend(
            SyntheticRow(
                economic_asset=item.economic_asset,
                bar_index=item.bar_index,
                difference=item.difference - centre,
            )
            for item in members
        )
    return kept
