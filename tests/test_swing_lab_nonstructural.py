"""The distance-only control, and the label it can never lose.

This module invents prices, which every other geometry module is forbidden to
do. The tests below are therefore mostly about **containment**: the invented
levels must be unmistakable in every artifact, the policy must be permanently
ineligible for promotion, and the arithmetic must be exact enough that a
difference between the control and the structural rule is a real difference
rather than a rounding artefact.
"""

from __future__ import annotations

import pytest

from fmis.swing_lab.geometry import (
    GeometryPlan,
    GeometrySkip,
    PlansGeometry,
    SkipReason,
    VolatilitySource,
)
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.nonstructural import (
    ATR_STOP_ORIGIN,
    NON_STRUCTURAL_FAMILY,
    R_TARGET_ORIGIN,
    SYNTHETIC_INTERVAL,
    SyntheticGeometryPolicy,
    synthetic_policy,
)
from fmis.swing_setup.models import Direction

from tests.swing_lab_helpers import candidate

TWIN = synthetic_policy(0.5, 2.0)


# ------------------------------------------------------------ arithmetic ---


def test_a_long_places_the_stop_below_and_the_target_above() -> None:
    """entry 100, execution ATR 1.0 → risk 0.5, reward 1.0."""
    plan = TWIN.plan(candidate())
    assert isinstance(plan, GeometryPlan)
    assert plan.entry == 100.0
    assert plan.stop.price == pytest.approx(99.5)
    assert plan.target.price == pytest.approx(101.0)
    assert plan.risk == pytest.approx(0.5)
    assert plan.reward == pytest.approx(1.0)
    assert plan.planned_rr == 2.0


def test_a_short_mirrors_the_long() -> None:
    plan = TWIN.plan(candidate(direction=Direction.SHORT))
    assert plan.stop.price == pytest.approx(100.5)
    assert plan.target.price == pytest.approx(99.0)
    assert plan.risk == pytest.approx(0.5)
    assert plan.planned_rr == 2.0


def test_the_planned_rr_is_the_declared_multiple_by_construction() -> None:
    """A synthetic target is exactly its multiple; nothing rounds it toward a level."""
    for target_r in (1.5, 2.0, 2.5):
        plan = synthetic_policy(0.5, target_r).plan(candidate())
        assert plan.planned_rr == target_r


def test_the_atr_multiples_are_the_declared_ones() -> None:
    plan = TWIN.plan(candidate())
    assert plan.stop_atr_multiple == 0.5
    assert plan.target_atr_multiple == 1.0


def test_it_reads_the_setup_atr_when_told_to() -> None:
    policy = SyntheticGeometryPolicy(
        policy_id="p", title="t", hypothesis="h", stop_atr=0.5, target_r=2.0,
        volatility_source=VolatilitySource.SETUP_ATR,
    )
    plan = policy.plan(candidate())          # setup ATR is 4.0 in the fixture
    assert plan.risk == pytest.approx(2.0)


# ------------------------------------------------------------- labelling ---


def test_every_invented_level_is_labelled_synthetic_in_its_provenance() -> None:
    """The label travels into every artifact, table and page as a string."""
    plan = TWIN.plan(candidate())
    assert plan.stop.interval == SYNTHETIC_INTERVAL
    assert plan.target.interval == SYNTHETIC_INTERVAL
    assert plan.stop_source == f"synthetic:{ATR_STOP_ORIGIN}@?"
    assert plan.target_source == f"synthetic:{R_TARGET_ORIGIN}@?"


def test_the_provenance_can_never_be_read_as_a_timeframe() -> None:
    """"4h" or "" would let a reader mistake an invented price for a market level."""
    plan = TWIN.plan(candidate())
    for source in (plan.stop_source, plan.target_source):
        assert not source.startswith(("4h", "1d", "1w"))
        assert SYNTHETIC_INTERVAL in source


def test_the_family_is_outside_the_structural_families() -> None:
    from fmis.swing_lab.geometry_variants import POST_HOC_FAMILY, PRE_DECLARED_GEOMETRIES

    assert TWIN.family == NON_STRUCTURAL_FAMILY
    assert TWIN.family != POST_HOC_FAMILY
    assert TWIN.family not in {item.family for item in PRE_DECLARED_GEOMETRIES}


def test_it_is_permanently_non_structural_and_never_the_production_geometry() -> None:
    assert TWIN.is_structural is False
    assert TWIN.is_production_geometry is False


def test_the_id_says_what_it_is() -> None:
    assert TWIN.policy_id == "nonstruct_stop_0_5atr_target_2r"
    assert "NON-STRUCTURAL" in TWIN.title
    assert "CONTROL" in TWIN.hypothesis


# -------------------------------------------------------------- refusals ---


def test_no_volatility_is_a_named_skip_and_never_a_default_distance() -> None:
    """Substituting a basis-point figure would invent a second fact to cover the first."""
    skip = TWIN.plan(candidate(execution_atr=None))
    assert isinstance(skip, GeometrySkip)
    assert skip.reason is SkipReason.NO_VOLATILITY_MEASURE


def test_a_stop_below_zero_is_refused_rather_than_clamped() -> None:
    """Clamping would shrink the risk and flatter every R multiple after it."""
    wide = synthetic_policy(2.0, 2.0)
    skip = wide.plan(candidate(reference_price=1.0, execution_atr=1.0))
    assert isinstance(skip, GeometrySkip)
    assert skip.reason is SkipReason.NO_STOP_LEVEL


def test_both_multiples_are_required_and_must_be_positive() -> None:
    for kwargs in ({"stop_atr": 0}, {"target_r": 0}, {"stop_atr": -1}):
        base = {"stop_atr": 0.5, "target_r": 2.0, **kwargs}
        with pytest.raises(SwingLabError, match="must be positive"):
            SyntheticGeometryPolicy(policy_id="p", title="t", hypothesis="h", **base)


def test_it_refuses_a_non_candidate() -> None:
    with pytest.raises(TypeError, match="must be a GeometryCandidate"):
        TWIN.plan(object())


# ---------------------------------------------------------- integration ---


def test_it_satisfies_the_replay_protocol_so_the_control_shares_the_machinery() -> None:
    """A control measured by different machinery is not a control."""
    assert isinstance(TWIN, PlansGeometry)
    assert hasattr(TWIN, "policy_id") and hasattr(TWIN, "family")


def test_the_structural_geometry_modules_do_not_import_this_one() -> None:
    """The containment boundary, checked by parsing imports rather than by promise.

    Textual absence is the wrong test — `fmis.swing_lab.geometry` names this
    module in a docstring, deliberately, so a reader learns where the invented
    prices live. What must not exist is a **dependency**: the direction of the
    arrow is what keeps "this module never constructs a level" a property of
    `geometry.py` rather than of everyone's good intentions.
    """
    import ast
    import pathlib

    for name in ("geometry", "geometry_variants"):
        tree = ast.parse(
            pathlib.Path(f"src/fmis/swing_lab/{name}.py").read_text(encoding="utf-8")
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "nonstructural" not in (node.module or ""), name
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "nonstructural" not in alias.name, name
