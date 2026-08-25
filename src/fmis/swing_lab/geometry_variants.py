"""The pre-declared geometry policies. **Written before any history was replayed.**

This module is Milestone BX's anti-overfitting device and only works if it is
read as one. Every policy below — its id, its family, its stated hypothesis and
its numeric threshold — was fixed before a single result came back. A policy
added after a number is seen is a *new experiment*, must carry
`POST_HOC_FAMILY`, and can never be described as independently validated.

**The families, and what each one is asking.** They follow §3 of the milestone
brief exactly, and they are deliberately *isolated* before they are combined:

===  =========================  ====================================================
 A   `FAMILY_BASELINE`          What does the product do today? A control.
 B   `FAMILY_MIN_RR`            Is a minimum planned reward-to-risk the answer?
 C   `FAMILY_VOLATILITY_STOP`   Is a structurally valid stop still too tight to use?
 D   `FAMILY_STRUCTURAL_STOP`   Is the nearest 4H level the true invalidation?
 E   `FAMILY_TARGET_SELECTION`  Is the nearest 1D level the right objective?
 F   `FAMILY_COMBINED`          Do the surviving ideas compose?
===  =========================  ====================================================

**What is deliberately absent.**

* No policy places a target at a computed R multiple. `fmis.swing_lab.geometry`
  cannot express one, and family B skips a trade rather than moving its target.
* No combinatorial sweep. Family F holds **two** logically motivated
  combinations, not the cross-product of A–E.
* No threshold is presented as a production default. Every number here is an
  experiment value, and the sensitivity grids exist precisely to show whether a
  result is a plateau or a spike.

**The sensitivity grids are not candidates.** `MIN_RR_SENSITIVITY_GRID` and
`MIN_STOP_ATR_SENSITIVITY_GRID` exist to answer §9 — *does the result collapse
when the number moves?* — and are reported as a sensitivity curve, never as a
menu to pick a winner from. That distinction is recorded in the artifact so a
reader cannot mistake the best point on a grid for a pre-declared hypothesis.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Final

from fmis.swing_lab.geometry import (
    GeometryPolicy,
    StopRule,
    TargetRule,
    VolatilitySource,
)
from fmis.swing_lab.models import SwingLabError

__all__ = [
    "FAMILY_BASELINE",
    "FAMILY_MIN_RR",
    "FAMILY_VOLATILITY_STOP",
    "FAMILY_STRUCTURAL_STOP",
    "FAMILY_TARGET_SELECTION",
    "FAMILY_COMBINED",
    "POST_HOC_FAMILY",
    "PRODUCTION_GEOMETRY",
    "PRE_DECLARED_GEOMETRIES",
    "MIN_RR_SENSITIVITY_GRID",
    "MIN_STOP_ATR_SENSITIVITY_GRID",
    "geometry_by_id",
    "min_rr_policy",
    "min_stop_atr_policy",
    "sensitivity_series",
]

FAMILY_BASELINE: Final[str] = "A_baseline"
FAMILY_MIN_RR: Final[str] = "B_minimum_planned_rr"
FAMILY_VOLATILITY_STOP: Final[str] = "C_volatility_aware_stop"
FAMILY_STRUCTURAL_STOP: Final[str] = "D_structural_invalidation_stop"
FAMILY_TARGET_SELECTION: Final[str] = "E_target_selection"
FAMILY_COMBINED: Final[str] = "F_combined"

#: Any policy constructed after a result was observed carries this family. It is
#: separated from A–F so no summary table can present a post-hoc idea beside a
#: pre-declared hypothesis without the difference being visible.
POST_HOC_FAMILY: Final[str] = "Z_post_hoc"


def _slug(value: float) -> str:
    """``1.25`` → ``1_25``. A stable id fragment with no locale-dependent decimal point."""
    return f"{value:g}".replace(".", "_").replace("-", "neg")


PRODUCTION_GEOMETRY: Final[GeometryPolicy] = GeometryPolicy(
    policy_id="geom_production",
    title="Production geometry (control)",
    family=FAMILY_BASELINE,
    hypothesis=(
        "The live rule, unchanged: the stop is the nearest execution-timeframe "
        "(4H) structural level on the protective side, the target is the "
        "nearest setup-timeframe (1D) structural level on the objective side, "
        "and no admission rule applies. This is a CONTROL, not a candidate. It "
        "must reproduce Milestone BW's baseline trade-for-trade; if it does "
        "not, the geometry layer is unfaithful and every comparison below is "
        "worthless."
    ),
    stop_rule=StopRule.NEAREST_EXECUTION,
    target_rule=TargetRule.NEAREST_SETUP,
)


def min_rr_policy(threshold: float, *, family: str = FAMILY_MIN_RR) -> GeometryPolicy:
    """Family B at one threshold: production geometry, refused below ``threshold``.

    The target is **production's own** — the nearest 1D level. Nothing is moved.
    A setup whose real structural target cannot pay ``threshold`` times its risk
    is not traded, which is the only honest way to express "require 1.5R".
    """
    return GeometryPolicy(
        policy_id=f"geom_min_rr_{_slug(threshold)}",
        title=f"Minimum planned R:R ≥ {threshold:g}",
        family=family,
        hypothesis=(
            f"Production geometry, but a setup is skipped unless its real "
            f"structural target pays at least {threshold:g}× its risk. BW found "
            "48% of baseline setups planned a reward smaller than their risk; "
            "this asks whether refusing those is enough on its own. The target "
            "is never moved to reach the threshold — the trade is refused."
        ),
        stop_rule=StopRule.NEAREST_EXECUTION,
        target_rule=TargetRule.NEAREST_SETUP,
        min_planned_rr=threshold,
    )


def min_stop_atr_policy(
    threshold: float, *, family: str = FAMILY_VOLATILITY_STOP
) -> GeometryPolicy:
    """Family C at one threshold: production geometry, refused inside ordinary noise.

    Normalised by the Wilder ATR(14) the execution view **already computes**
    (`fmis.pipeline.regime.regime_features`). No volatility engine is added.
    """
    return GeometryPolicy(
        policy_id=f"geom_min_stop_{_slug(threshold)}atr",
        title=f"Minimum stop distance ≥ {threshold:g}× ATR(14)",
        family=family,
        hypothesis=(
            f"Production geometry, but a setup is skipped unless its stop sits "
            f"at least {threshold:g}× the execution timeframe's ATR(14) from "
            "the entry. BW found stops as tight as 1.29 basis points: "
            "structurally real, economically unusable, and guaranteed to be "
            "taken out by an ordinary bar. This asks whether a stop can be "
            "meaningful and still be too close to trade."
        ),
        stop_rule=StopRule.NEAREST_EXECUTION,
        target_rule=TargetRule.NEAREST_SETUP,
        min_stop_atr=threshold,
        volatility_source=VolatilitySource.EXECUTION_ATR,
    )


SETUP_TIMEFRAME_STOP: Final[GeometryPolicy] = GeometryPolicy(
    policy_id="geom_setup_stop",
    title="Stop at the setup-timeframe (1D) invalidation",
    family=FAMILY_STRUCTURAL_STOP,
    hypothesis=(
        "The thesis is formed on the SETUP timeframe, so its invalidation "
        "arguably lives there too. This replaces the nearest 4H protective "
        "level with the nearest 1D one and leaves the target alone. If the "
        "current stop is merely the closest level rather than the level that "
        "would disprove the trade, this should raise the average winner while "
        "widening the risk denominator — and the two effects must be read "
        "together, because a wider stop mechanically shrinks every R multiple."
    ),
    stop_rule=StopRule.NEAREST_SETUP,
    target_rule=TargetRule.NEAREST_SETUP,
)

SECOND_TARGET: Final[GeometryPolicy] = GeometryPolicy(
    policy_id="geom_second_target",
    title="Target at the second setup-timeframe (1D) level",
    family=FAMILY_TARGET_SELECTION,
    hypothesis=(
        "The nearest 1D level is often only a few basis points away. This takes "
        "the SECOND nearest — a real level the same engine already identified — "
        "and skips the setup entirely when only one exists rather than falling "
        "back to the first. If targets are structurally valid but economically "
        "too close, this should raise the average winner at the cost of a lower "
        "hit rate."
    ),
    stop_rule=StopRule.NEAREST_EXECUTION,
    target_rule=TargetRule.SECOND_SETUP,
)

CONTEXT_TARGET: Final[GeometryPolicy] = GeometryPolicy(
    policy_id="geom_context_target",
    title="Target at the context-timeframe (1W) objective",
    family=FAMILY_TARGET_SELECTION,
    hypothesis=(
        "A structurally larger objective, already computed by the same engine "
        "on the context view. This tests the far end of the target-distance "
        "question: if the problem is that objectives are too near, the weekly "
        "objective is the furthest real level the system knows about. It is "
        "expected to trade rarely and to hold for a long time; both are "
        "measured rather than assumed."
    ),
    stop_rule=StopRule.NEAREST_EXECUTION,
    target_rule=TargetRule.NEAREST_CONTEXT,
)

#: Family F, combination 1. The economically coherent story: the stop is where
#: the *setup* thesis dies, it must clear ordinary noise, and the objective must
#: be a real level far enough away to pay for the risk.
COMBINED_STRUCTURAL: Final[GeometryPolicy] = GeometryPolicy(
    policy_id="geom_combined_structural",
    title="1D invalidation stop + 1.0 ATR floor + first 1D target paying 1.5R",
    family=FAMILY_COMBINED,
    hypothesis=(
        "The three isolated ideas composed, and the only combination with a "
        "single coherent story: the stop is the level that would disprove the "
        "SETUP-timeframe thesis, it must clear one ATR of ordinary execution-"
        "timeframe range, and the objective must be a REAL 1D level far enough "
        "away to pay 1.5× the risk. Each component is measured alone in "
        "families C, D and E, so any joint effect can be attributed rather than "
        "assumed. No level is created: when no real 1D level pays 1.5R, the "
        "trade is skipped."
    ),
    stop_rule=StopRule.NEAREST_SETUP,
    target_rule=TargetRule.FIRST_SETUP_SUPPORTING_RR,
    min_planned_rr=1.5,
    min_stop_atr=1.0,
    volatility_source=VolatilitySource.EXECUTION_ATR,
)

#: Family F, combination 2. The same idea with the *execution* timeframe kept as
#: the stop's source, so the pair isolates "which timeframe owns invalidation"
#: while holding the volatility floor and the target rule fixed.
COMBINED_EXECUTION: Final[GeometryPolicy] = GeometryPolicy(
    policy_id="geom_combined_execution",
    title="4H stop beyond 1.0 ATR + first 1D target paying 1.5R",
    family=FAMILY_COMBINED,
    hypothesis=(
        "The same composition as geom_combined_structural, except the stop is "
        "the nearest EXECUTION-timeframe level that already clears one ATR "
        "rather than the setup-timeframe level. Run as a pair with it, this "
        "isolates 'which timeframe owns invalidation' while the volatility "
        "floor and the target rule are held fixed."
    ),
    stop_rule=StopRule.EXECUTION_BEYOND_VOLATILITY,
    target_rule=TargetRule.FIRST_SETUP_SUPPORTING_RR,
    min_planned_rr=1.5,
    min_stop_atr=1.0,
    volatility_source=VolatilitySource.EXECUTION_ATR,
)


#: The full pre-declared set, in presentation order: control, then each isolated
#: family, then the combinations. Thirteen policies, every one written down
#: before a result was seen.
PRE_DECLARED_GEOMETRIES: Final[tuple[GeometryPolicy, ...]] = (
    PRODUCTION_GEOMETRY,
    min_rr_policy(1.0),
    min_rr_policy(1.25),
    min_rr_policy(1.5),
    min_rr_policy(2.0),
    min_stop_atr_policy(0.5),
    min_stop_atr_policy(1.0),
    min_stop_atr_policy(1.5),
    SETUP_TIMEFRAME_STOP,
    SECOND_TARGET,
    CONTEXT_TARGET,
    COMBINED_STRUCTURAL,
    COMBINED_EXECUTION,
)

#: §9's plateau test for family B. **Not a menu of candidates.** Reported as a
#: curve so a reader sees whether performance changes smoothly with the
#: threshold or spikes at one hand-picked value.
MIN_RR_SENSITIVITY_GRID: Final[tuple[float, ...]] = (
    1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0,
)

#: §9's plateau test for family C. Same discipline.
MIN_STOP_ATR_SENSITIVITY_GRID: Final[tuple[float, ...]] = (
    0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0,
)


def sensitivity_series(
    kind: str,
) -> tuple[GeometryPolicy, ...]:
    """Every policy on one sensitivity grid, in ascending threshold order.

    ``kind`` is ``"min_rr"`` or ``"min_stop_atr"``. The returned policies keep
    their own family, so a caller cannot accidentally file a grid point as a
    pre-declared hypothesis.

    Raises:
        SwingLabError: ``kind`` names no grid.
    """
    if kind == "min_rr":
        return tuple(min_rr_policy(value) for value in MIN_RR_SENSITIVITY_GRID)
    if kind == "min_stop_atr":
        return tuple(min_stop_atr_policy(value) for value in MIN_STOP_ATR_SENSITIVITY_GRID)
    raise SwingLabError(
        f"no sensitivity grid named {kind!r}; this module defines "
        "'min_rr' and 'min_stop_atr'"
    )


def _grid_neighbours(value: float, grid: Sequence[float]) -> tuple[float, ...]:
    """The grid values immediately below and above ``value``. Never ``value`` itself.

    A threshold that is not on its own grid still has neighbours — the nearest
    grid point each side — so a policy can be plateau-tested without its exact
    value having to be a grid point.
    """
    below = [item for item in grid if item < value]
    above = [item for item in grid if item > value]
    return tuple(
        [max(below)] if below else []
    ) + tuple([min(above)] if above else [])


def with_thresholds(
    policy: GeometryPolicy,
    *,
    min_planned_rr: float | None = None,
    min_stop_atr: float | None = None,
) -> GeometryPolicy:
    """The same policy with one or both thresholds moved, and a **new id**.

    The id is regenerated from the thresholds rather than reused, because two
    policies that differ in a number are two policies, and a shared id would let
    their trades be summed. ``family`` is preserved, so a neighbour generated for
    a plateau test never masquerades as a pre-declared hypothesis of its own.
    """
    if not isinstance(policy, GeometryPolicy):
        raise TypeError("policy must be a GeometryPolicy")
    rr = policy.min_planned_rr if min_planned_rr is None else min_planned_rr
    atr = policy.min_stop_atr if min_stop_atr is None else min_stop_atr
    parts = [policy.policy_id.split("@", 1)[0]]
    if rr is not None:
        parts.append(f"rr{_slug(rr)}")
    if atr is not None:
        parts.append(f"atr{_slug(atr)}")
    return replace(
        policy,
        policy_id="@".join(parts[:1]) + ("@" + "+".join(parts[1:]) if parts[1:] else ""),
        min_planned_rr=rr,
        min_stop_atr=atr,
    )


def neighbours_of(policy: GeometryPolicy) -> tuple[GeometryPolicy, ...]:
    """Every one-step threshold neighbour of ``policy``, for the §9 plateau test.

    Each numeric threshold is moved one grid step **down and up, one at a time**,
    holding the other fixed. That is deliberately not a grid search over the
    pair: the question is *does this result survive a small change*, and moving
    two numbers at once answers a different question while multiplying the
    number of tests.

    A policy with no numeric threshold has no neighbours and returns ``()`` —
    which the verdict layer reports as *not applicable*, never as a pass.
    """
    if not isinstance(policy, GeometryPolicy):
        raise TypeError("policy must be a GeometryPolicy")
    generated: list[GeometryPolicy] = []
    if policy.min_planned_rr is not None:
        for value in _grid_neighbours(policy.min_planned_rr, MIN_RR_SENSITIVITY_GRID):
            generated.append(with_thresholds(policy, min_planned_rr=value))
    if policy.min_stop_atr is not None:
        for value in _grid_neighbours(policy.min_stop_atr, MIN_STOP_ATR_SENSITIVITY_GRID):
            generated.append(with_thresholds(policy, min_stop_atr=value))
    # De-duplicate by id while preserving order: a policy sitting between two
    # grid points can generate the same neighbour twice.
    seen: set[str] = set()
    unique: list[GeometryPolicy] = []
    for item in generated:
        if item.policy_id in seen:
            continue
        seen.add(item.policy_id)
        unique.append(item)
    return tuple(unique)


_BY_ID: Final[dict[str, GeometryPolicy]] = {
    policy.policy_id: policy for policy in PRE_DECLARED_GEOMETRIES
}

if len(_BY_ID) != len(PRE_DECLARED_GEOMETRIES):  # pragma: no cover - import-time guard
    raise SwingLabError("two pre-declared geometry policies share a policy_id")


def geometry_by_id(policy_id: str) -> GeometryPolicy:
    """Look one pre-declared geometry up by id.

    Raises:
        SwingLabError: no pre-declared policy carries that id. Names the
            available ids, because a caller who mistyped needs the alternatives.
    """
    try:
        return _BY_ID[policy_id]
    except KeyError:
        raise SwingLabError(
            f"no pre-declared geometry {policy_id!r}; this study defines "
            f"{', '.join(sorted(_BY_ID))}"
        ) from None
