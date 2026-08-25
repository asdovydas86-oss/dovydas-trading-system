"""Milestone BC — the research override may never reach production behaviour.

Milestone BC adds one parameter to `fmis.swing_setup.policy.evaluate_setup`.
That parameter is the whole risk of this milestone: a research knob that leaks
into the live product is a second, undeclared trading policy, and it would leak
silently because nothing about a slightly different confirmation rule looks
wrong on a page.

These tests are the containment. They assert, from four independent directions,
that the override is unreachable unless a caller asks for it by name:

1. **Default identity** — omitting it produces exactly what omitting it produced
   before it existed, field for field.
2. **Signature containment** — none of the live entry points accepts or forwards
   it, checked against the real signatures rather than by reading the source.
3. **Call-site containment** — no module outside the research layer passes it,
   checked by scanning `src/`.
4. **Self-identification** — anything produced under the override carries a
   `policy_id` no production result can carry, so a research artifact filed as
   a production one is detectable after the fact.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import replace
from pathlib import Path

import pytest

from fmis.decision_context import ContextState
from fmis.level_crossing import LevelOrigin, LevelSide, PriceLevel
from fmis.market_regime import ParticipationState, StructureState, VolatilityState
from fmis.market_structure import StructuralSwingLabel
from fmis.structural_trend import StructuralTrendType
from fmis.swing_setup import compose, scan
from fmis.swing_setup.models import (
    Direction,
    ExecutionBreakEvent,
    SetupInputs,
    SetupState,
)
from fmis.swing_setup.policy import (
    CONFIRMATION_LOOKBACK_BARS,
    RESEARCH_POLICY_ID_PREFIX,
    SETUP_POLICY_ID,
    evaluate_setup,
    research_policy_id,
)

from datetime import datetime, timedelta, timezone

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "fmis"

#: The only modules allowed to name the research override: `policy` defines it,
#: `compose` forwards it, and `swing_setup/research_*.py` is the layer it exists
#: for. Anything else naming it is a production module reaching for a research
#: knob, which is the failure this file exists to catch.
_ALLOWED_OVERRIDE_MODULES = {"swing_setup/policy.py", "swing_setup/compose.py"}
#: Widened for Milestone BW. `fmis.swing_lab` is the Swing Strategy Laboratory
#: and is research code by construction — its own architecture guard asserts
#: that no production module imports it, which is the same containment this
#: prefix expresses for `swing_setup/research_*`. The override is still
#: unreachable from any live surface.
_ALLOWED_OVERRIDE_PREFIXES = ("swing_setup/research_", "swing_lab/")
_ALLOWED_OVERRIDE_PREFIX = _ALLOWED_OVERRIDE_PREFIXES[0]


def _origin(index: int, label: StructuralSwingLabel) -> LevelOrigin:
    return LevelOrigin(
        index=index,
        timestamp=_BASE + timedelta(hours=4 * index),
        label=label,
        confirmation_bars=2,
    )


def _long_inputs(*, break_index: int, closed_count: int = 60) -> SetupInputs:
    """A `SetupInputs` that reaches CONFIRMED under a lenient bound, by hand.

    Two structural families lean LONG and the evidence family abstains, which is
    exactly `MINIMUM_AGREEING_FAMILIES` with none opposing; the context regime is
    TRENDING; and one upper-side execution break exists at ``break_index``, so
    the only thing left to decide the state is how old that break is.
    """
    upper = PriceLevel(price=110.0, side=LevelSide.UPPER, origin=_origin(5, StructuralSwingLabel.HIGHER_HIGH))
    lower = PriceLevel(price=90.0, side=LevelSide.LOWER, origin=_origin(3, StructuralSwingLabel.HIGHER_LOW))
    target = PriceLevel(price=130.0, side=LevelSide.UPPER, origin=_origin(9, StructuralSwingLabel.HIGHER_HIGH))
    return SetupInputs(
        symbol="BTCUSDT",
        as_of=_BASE,
        source="test",
        context_interval="1w",
        setup_interval="1d",
        execution_interval="4h",
        context_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        setup_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        execution_structural_trend=StructuralTrendType.INDETERMINATE,
        context_regime_structure=StructureState.TRENDING,
        context_regime_volatility=VolatilityState.STEADY,
        context_regime_participation=ParticipationState.TYPICAL,
        evidence_state=None,
        evidence_dominant_alignment=None,
        decision_context_state=ContextState.SUFFICIENT,
        decision_context_statements=(),
        execution_close=100.0,
        execution_closed_count=closed_count,
        execution_levels=(upper, lower),
        execution_breaks=(ExecutionBreakEvent(level=upper, index=break_index),),
        setup_levels=(target,),
        inherited_limitations=(),
    )


# =========================== 1. default identity ===========================


class TestOmittingTheOverrideChangesNothing:
    @pytest.mark.parametrize("break_index", [59, 55, 49, 40, 10])
    def test_none_is_exactly_the_production_constant(self, break_index: int) -> None:
        inputs = _long_inputs(break_index=break_index)
        assert evaluate_setup(inputs) == evaluate_setup(
            inputs, research_confirmation_max_age=None
        )

    @pytest.mark.parametrize("break_index", [59, 55, 49, 40, 10])
    def test_the_production_bound_reproduces_production_in_every_field_but_provenance(
        self, break_index: int
    ) -> None:
        inputs = _long_inputs(break_index=break_index)
        production = evaluate_setup(inputs)
        replayed = evaluate_setup(
            inputs, research_confirmation_max_age=CONFIRMATION_LOOKBACK_BARS
        )
        assert replayed.state == production.state
        assert replayed.direction == production.direction
        assert replayed.trigger == production.trigger
        assert replayed.confirmation == production.confirmation
        assert replayed.reference_price == production.reference_price
        assert replayed.stop == production.stop
        assert replayed.targets == production.targets
        assert replayed.risk_reward == production.risk_reward
        assert replayed.thesis == production.thesis
        # Only provenance differs: the policy id and one limitation line saying
        # out loud that this was a research replay.
        assert replayed.policy_id != production.policy_id
        assert len(replayed.limitations) == len(production.limitations) + 1

    def test_the_bound_actually_decides_the_state(self) -> None:
        fresh = _long_inputs(break_index=59)      # age 0
        stale = _long_inputs(break_index=49)      # age 10, exactly at the bound
        beyond = _long_inputs(break_index=48)     # age 11, one past it
        assert evaluate_setup(fresh).state is SetupState.CONFIRMED
        assert evaluate_setup(stale).state is SetupState.CONFIRMED
        assert evaluate_setup(beyond).state is SetupState.CANDIDATE
        # The same three inputs under a research bound of 2.
        assert evaluate_setup(fresh, research_confirmation_max_age=2).state is SetupState.CONFIRMED
        assert evaluate_setup(stale, research_confirmation_max_age=2).state is SetupState.CANDIDATE

    def test_the_comparison_is_inclusive_at_the_bound(self) -> None:
        """``age <= bound`` confirms and ``age == bound + 1`` does not — both directions."""
        for bound in (0, 1, 2, 3, 5, 10):
            at_bound = _long_inputs(break_index=59 - bound)
            past_bound = _long_inputs(break_index=59 - bound - 1)
            assert (
                evaluate_setup(at_bound, research_confirmation_max_age=bound).state
                is SetupState.CONFIRMED
            ), bound
            assert (
                evaluate_setup(past_bound, research_confirmation_max_age=bound).state
                is SetupState.CANDIDATE
            ), bound

    def test_a_stale_candidate_keeps_watching_rather_than_disappearing(self) -> None:
        """The property that makes a post-filter wrong: a deferred setup survives."""
        stale = _long_inputs(break_index=49)
        assessment = evaluate_setup(stale, research_confirmation_max_age=2)
        assert assessment.state is SetupState.CANDIDATE
        assert assessment.direction is Direction.LONG
        assert assessment.trigger is not None
        assert assessment.trigger.level is not None
        assert "beyond the 2-bar confirmation window" in assessment.confirmation[0]

    def test_a_wait_result_still_reports_the_research_policy_that_produced_it(self) -> None:
        inputs = replace(_long_inputs(break_index=59), context_regime_structure=StructureState.RANGING)
        assessment = evaluate_setup(inputs, research_confirmation_max_age=2)
        assert assessment.state is SetupState.WAIT
        assert assessment.policy_id == research_policy_id(2)

    @pytest.mark.parametrize("bad", [-1, "2", 2.0, True])
    def test_an_invalid_override_is_refused(self, bad) -> None:
        with pytest.raises((TypeError, ValueError)):
            evaluate_setup(_long_inputs(break_index=59), research_confirmation_max_age=bad)


# ========================= 2. signature containment =========================


class TestLiveEntryPointsDoNotAcceptTheOverride:
    @pytest.mark.parametrize(
        "function",
        [
            compose.setup_assessment_for_sheet,
            compose.setup_for_symbol,
            compose.run_setup_for_symbols,
            scan.run_market_scan,
        ],
    )
    def test_no_live_entry_point_exposes_a_research_parameter(self, function) -> None:
        parameters = inspect.signature(function).parameters
        assert not any("research" in name for name in parameters), function.__name__
        assert not any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        ), (
            f"{function.__name__} takes **kwargs, which would let a research "
            "override through without appearing in its signature"
        )

    def test_the_one_seam_that_does_expose_it_defaults_to_production(self) -> None:
        parameter = inspect.signature(
            compose.setup_inputs_and_assessment_for_sheet
        ).parameters["research_confirmation_max_age"]
        assert parameter.default is None
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY

    def test_evaluate_setup_takes_it_keyword_only(self) -> None:
        parameter = inspect.signature(evaluate_setup).parameters[
            "research_confirmation_max_age"
        ]
        assert parameter.default is None
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


# ========================= 3. call-site containment =========================


class TestNoProductionModuleSuppliesTheOverride:
    def _sources(self) -> list[tuple[str, str]]:
        return [
            (str(path.relative_to(_SOURCE_ROOT)), path.read_text(encoding="utf-8"))
            for path in sorted(_SOURCE_ROOT.rglob("*.py"))
        ]

    def test_only_the_declared_modules_name_the_override(self) -> None:
        offenders = [
            name
            for name, text in self._sources()
            if "research_confirmation_max_age" in text
            and name.replace("\\", "/") not in _ALLOWED_OVERRIDE_MODULES
            and not name.replace("\\", "/").startswith(_ALLOWED_OVERRIDE_PREFIXES)
        ]
        assert offenders == [], (
            "the research override escaped its declared modules; a production "
            "module naming it is a second trading policy in waiting"
        )

    def test_the_live_composition_call_passes_no_override(self) -> None:
        text = (_SOURCE_ROOT / "swing_setup" / "compose.py").read_text(encoding="utf-8")
        wrapper = re.search(
            r"def setup_assessment_for_sheet\(.*?\n    return assessment", text, re.S
        )
        assert wrapper is not None
        assert "research_confirmation_max_age" not in wrapper.group(0)

    def test_the_cli_refuses_the_flag_outside_research_mode(self) -> None:
        from fmis.pipeline.cli import main

        assert main(["backtest", "--max-confirmation-age", "2", "BTCUSDT"]) != 0


# ========================= 4. self-identification =========================


class TestResearchResultsAreSelfIdentifying:
    def test_a_production_assessment_never_carries_the_research_marker(self) -> None:
        assessment = evaluate_setup(_long_inputs(break_index=59))
        assert assessment.policy_id == SETUP_POLICY_ID
        assert RESEARCH_POLICY_ID_PREFIX not in assessment.policy_id.replace(
            SETUP_POLICY_ID, ""
        )
        assert not any("RESEARCH OVERRIDE" in line for line in assessment.limitations)

    def test_every_research_assessment_says_so_twice(self) -> None:
        assessment = evaluate_setup(_long_inputs(break_index=59), research_confirmation_max_age=2)
        assert assessment.policy_id.startswith(RESEARCH_POLICY_ID_PREFIX)
        assert any("RESEARCH OVERRIDE ACTIVE" in line for line in assessment.limitations)

    def test_the_marker_is_a_strict_extension_of_the_production_id(self) -> None:
        assert RESEARCH_POLICY_ID_PREFIX.startswith(SETUP_POLICY_ID)
        assert research_policy_id(0) != research_policy_id(10)
