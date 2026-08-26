"""**NON-STRUCTURAL geometry. Prices this module invents, and says so.**

Read this paragraph before reading a number produced here. Every other geometry
in this package selects a `PriceLevel` the structural engines already produced;
this one **computes a price** — a stop at a multiple of ATR from the entry, a
target at a multiple of the risk. §3 and §4 of the Milestone BY brief forbid
exactly that *unless* it is pre-declared as a separate, clearly labelled research
variant, which is what this module is.

**Why it exists at all.** Milestone BX's post-hoc finding was that a stop beyond
the volatility floor *and* a target that pays the risk turned the sign positive.
That result has two possible mechanisms and BX could not separate them:

1. the **structure** is doing the work — a real 4H level beyond the noise floor
   is a genuinely better invalidation than the nearest one, and a real 1D level
   that pays 2R is a genuinely reachable objective; or
2. only the **distance** is doing the work — any stop that far out and any target
   that far out would perform identically, and the structural engines are
   decoration.

A milestone that proposes a structural rule without testing (2) is proposing a
rule it has not understood. So this module builds the *distance-only twin* of the
primary hypothesis and runs it on the same candidates. **If the twin matches the
structural rule, the structural claim is unsupported and must be withdrawn** —
and that is a result this milestone is prepared to report.

**Three things that make the label impossible to lose.**

* Every synthetic level carries `interval=SYNTHETIC_INTERVAL` and an
  `origin_label` naming the formula, so its `provenance` reads
  ``synthetic:atr_multiple_from_entry@?`` in every artifact, table and page. No
  reader can mistake it for a 4H swing low.
* Every policy here carries `NON_STRUCTURAL_FAMILY`, which is not one of the
  pre-declared structural families.
* `is_structural` is `False` and the verdict layer refuses to promote a
  non-structural policy to a forward-test candidate **whatever its expectancy**.
  It is a control, permanently. A control that wins is a finding about the
  hypothesis, never a replacement for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fmis.level_crossing import LevelSide
from fmis.swing_lab.geometry import (
    BASIS_POINT,
    GeometryCandidate,
    GeometryPlan,
    GeometrySkip,
    LevelRef,
    SkipReason,
    VolatilitySource,
)
from fmis.swing_lab.models import SwingLabError
from fmis.swing_setup.models import Direction

__all__ = [
    "SYNTHETIC_INTERVAL",
    "NON_STRUCTURAL_FAMILY",
    "ATR_STOP_ORIGIN",
    "R_TARGET_ORIGIN",
    "SyntheticGeometryPolicy",
    "synthetic_policy",
]

#: The interval every invented level carries. Not "4h", not "1d", not the empty
#: string: a value that is obviously not a timeframe, so a provenance string
#: containing it cannot be read as a market fact by a page, a table or a person.
SYNTHETIC_INTERVAL: Final[str] = "synthetic"

#: The family every policy here carries. Deliberately outside the A–F structural
#: families and outside `POST_HOC_FAMILY`, because it is neither.
NON_STRUCTURAL_FAMILY: Final[str] = "N_non_structural_control"

ATR_STOP_ORIGIN: Final[str] = "atr_multiple_from_entry"
R_TARGET_ORIGIN: Final[str] = "r_multiple_from_entry"


@dataclass(frozen=True, slots=True)
class SyntheticGeometryPolicy:
    """A stop at ``stop_atr`` × ATR and a target at ``target_r`` × the risk.

    Satisfies `fmis.swing_lab.geometry.PlansGeometry`, so the same replay,
    the same simulator, the same metrics and the same cost model measure it —
    which is the point. A control measured by different machinery is not a
    control.

    Both multiples are required. A "synthetic" policy with one of them absent
    would silently be a structural policy wearing this module's label, and the
    whole value of the comparison is that exactly one thing differs.
    """

    policy_id: str
    title: str
    hypothesis: str
    stop_atr: float
    target_r: float
    volatility_source: VolatilitySource = VolatilitySource.EXECUTION_ATR

    def __post_init__(self) -> None:
        for name in ("policy_id", "title", "hypothesis"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SwingLabError(f"{name} must be a non-empty str")
        for name in ("stop_atr", "target_r"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if value <= 0:
                raise SwingLabError(f"{name} must be positive, got {value}")
        if not isinstance(self.volatility_source, VolatilitySource):
            raise TypeError("volatility_source must be a VolatilitySource")

    @property
    def family(self) -> str:
        return NON_STRUCTURAL_FAMILY

    @property
    def is_structural(self) -> bool:
        """Always `False`. A property rather than a constant so it survives a copy."""
        return False

    @property
    def is_production_geometry(self) -> bool:
        return False

    def volatility_of(self, candidate: GeometryCandidate) -> float | None:
        if self.volatility_source is VolatilitySource.EXECUTION_ATR:
            return candidate.execution_atr
        return candidate.setup_atr

    def plan(self, candidate: GeometryCandidate) -> GeometryPlan | GeometrySkip:
        """Compute a stop and a target. **The only place in this package that does.**

        Pure and total: the same candidate always yields the same result, and the
        result is always a plan or a named skip. The one refusal it can produce is
        `NO_VOLATILITY_MEASURE` — without an ATR there is no distance to compute,
        and defaulting to a basis-point figure would invent a second market fact
        to cover for the first one being missing.
        """
        if not isinstance(candidate, GeometryCandidate):
            raise TypeError(
                f"candidate must be a GeometryCandidate, got {type(candidate).__name__}"
            )
        atr = self.volatility_of(candidate)
        if atr is None:
            return GeometrySkip(
                candidate=candidate,
                policy_id=self.policy_id,
                reason=SkipReason.NO_VOLATILITY_MEASURE,
            )

        entry = candidate.reference_price
        risk = self.stop_atr * atr
        reward = self.target_r * risk
        sign = 1 if candidate.direction is Direction.LONG else -1
        stop_price = entry - sign * risk
        target_price = entry + sign * reward
        if stop_price <= 0:
            # A stop below zero is not a price. It happens only when the ATR is
            # a large fraction of the instrument's own price, which is a real
            # market state and is refused rather than clamped: clamping would
            # silently shrink the risk and flatter every R multiple that follows.
            return GeometrySkip(
                candidate=candidate,
                policy_id=self.policy_id,
                reason=SkipReason.NO_STOP_LEVEL,
            )

        stop_side = candidate.stop_side
        target_side = candidate.target_side
        return GeometryPlan(
            candidate=candidate,
            policy_id=self.policy_id,
            entry=entry,
            stop=_synthetic(stop_price, stop_side, ATR_STOP_ORIGIN),
            target=_synthetic(target_price, target_side, R_TARGET_ORIGIN),
            risk=risk,
            reward=reward,
            planned_rr=self.target_r,
            stop_bps=(risk / entry) / BASIS_POINT,
            target_bps=(reward / entry) / BASIS_POINT,
            stop_atr_multiple=self.stop_atr,
            target_atr_multiple=self.stop_atr * self.target_r,
        )


def _synthetic(price: float, side: LevelSide, origin: str) -> LevelRef:
    """One invented level, labelled so it cannot be read as a market fact."""
    return LevelRef(
        price=price,
        side=side,
        interval=SYNTHETIC_INTERVAL,
        origin_index=None,
        origin_label=origin,
    )


def synthetic_policy(stop_atr: float, target_r: float) -> SyntheticGeometryPolicy:
    """The distance-only twin of one structural hypothesis, at the same numbers."""
    return SyntheticGeometryPolicy(
        policy_id=f"nonstruct_stop_{_slug(stop_atr)}atr_target_{_slug(target_r)}r",
        title=(
            f"NON-STRUCTURAL control: stop {stop_atr:g}× ATR(14), "
            f"target {target_r:g}R"
        ),
        hypothesis=(
            f"The distance-only twin of the structural hypothesis at the same "
            f"numbers: the stop is placed {stop_atr:g}× ATR(14) from the entry "
            f"and the target {target_r:g}× that risk, with NO reference to any "
            "structural level. If this matches the structural rule, the "
            "structural claim is unsupported and the finding is about distance "
            "rather than about market structure. It is a CONTROL and can never "
            "become a forward-test candidate, whatever it earns."
        ),
        stop_atr=stop_atr,
        target_r=target_r,
    )


def _slug(value: float) -> str:
    """``0.5`` → ``0_5``. Matches `geometry_variants._slug` so ids read alike."""
    return f"{value:g}".replace(".", "_").replace("-", "neg")
