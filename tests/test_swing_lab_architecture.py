"""Structural guards: the laboratory cannot become a second trading system.

Every guard here asserts an **absence**, and each absence is one way research
code historically leaks into production:

* a second swing engine, a second lifecycle or a second statistics engine —
  the brief's explicit warning, checked by requiring the reuse to be visible as
  an import rather than promised in a docstring;
* a second **fill rule**, which is the specific way a backtest flatters itself;
* a write path, an execution verb, an AI call or an exchange integration;
* a production module importing the laboratory, which would make a research
  policy reachable from a live decision.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "fmis"
_PACKAGE = _SOURCE_ROOT / "swing_lab"

_MODULES = (
    "__init__.py",
    "admission.py",
    "admission_artifact.py",
    "admission_matching.py",
    "admission_preregistration.py",
    "admission_render.py",
    "admission_study.py",
    "artifact.py",
    "entry.py",
    "exits.py",
    "gate.py",
    "geometry.py",
    "geometry_artifact.py",
    "geometry_diagnosis.py",
    "geometry_outcome.py",
    "geometry_render.py",
    "geometry_replay.py",
    "geometry_study.py",
    "geometry_variants.py",
    "geometry_verdict.py",
    "intrabar.py",
    "metrics.py",
    "models.py",
    "nonstructural.py",
    "persistence.py",
    "persistence_artifact.py",
    "persistence_preregistration.py",
    "persistence_render.py",
    "persistence_replay.py",
    "persistence_study.py",
    "preregistration.py",
    "render.py",
    "replay.py",
    "robustness.py",
    "study.py",
    "trades.py",
    "validation.py",
    "validation_artifact.py",
    "validation_mechanics.py",
    "validation_render.py",
    "validation_study.py",
    "variants.py",
)

#: The Milestone BX modules that decide a stop or a target. Guarded more tightly
#: than the rest of the package: these are the ones a lookahead or a fabricated
#: level would have to pass through.
_GEOMETRY_POLICY_MODULES = ("geometry.py", "geometry_variants.py")

#: The only modules permitted to touch a file. One per milestone that persists a
#: research record, and each is additionally guarded against writing to a store.
_ARTIFACT_MODULES = (
    "artifact.py",
    "geometry_artifact.py",
    "validation_artifact.py",
    "persistence_artifact.py",
    "admission_artifact.py",
)


def _source(name: str) -> str:
    return (_PACKAGE / name).read_text(encoding="utf-8")


def _tree(name: str) -> ast.Module:
    return ast.parse(_source(name))


def _imported_modules(name: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(_tree(name)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def test_the_package_holds_exactly_the_modules_these_guards_cover() -> None:
    """A new module must be added to `_MODULES`, so no module escapes review."""
    present = {path.name for path in _PACKAGE.glob("*.py")}
    assert present == set(_MODULES)


@pytest.mark.parametrize("name", _MODULES)
def test_every_module_imports_in_a_fresh_interpreter(name: str) -> None:
    module = f"fmis.swing_lab.{name[:-3]}" if name != "__init__.py" else "fmis.swing_lab"
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        cwd=_SOURCE_ROOT.parents[1],
    )
    assert result.returncode == 0, result.stderr


class TestNothingIsDuplicated:
    def test_the_swing_policy_is_imported_never_reimplemented(self) -> None:
        """`evaluate_setup` is called; no module defines a second one."""
        assert "evaluate_setup" in _imported_names("replay.py")
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if isinstance(node, ast.FunctionDef):
                    assert node.name != "evaluate_setup", name

    def test_the_fill_rule_is_the_paper_engines(self) -> None:
        assert "fmis.paper.fills" in _imported_modules("trades.py")
        assert "fill_at_level" in _imported_names("trades.py")

    def test_no_module_defines_its_own_gap_or_touch_rule(self) -> None:
        """A second definition of "did this bar reach the level" is the danger."""
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if isinstance(node, ast.FunctionDef):
                    assert node.name not in {
                        "fill_at_level",
                        "reached",
                        "opened_beyond",
                        "stop_reached",
                        "_hits",
                    }, f"{name} defines its own fill rule"

    def test_the_cost_policy_is_the_lifecycles(self) -> None:
        assert "fmis.trade_lifecycle" in _imported_modules("trades.py")
        assert "PaperCostPolicy" in _imported_names("trades.py")

    def test_the_replay_transport_and_warmup_are_milestone_bcs(self) -> None:
        imported = _imported_modules("replay.py") | _imported_modules("study.py")
        assert "fmis.swing_setup.backtest_replay" in imported
        assert "fmis.swing_setup.research_warmup" in imported
        assert "fmis.swing_setup.research_harness" in imported

    def test_the_setup_identity_tracker_is_reused(self) -> None:
        assert "fmis.swing_setup.research_identity" in _imported_modules("replay.py")


def _imported_names(name: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(_tree(name)):
        if isinstance(node, ast.ImportFrom):
            found.update(alias.name for alias in node.names)
    return found


class TestNoProductionSideEffects:
    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_names_an_execution_verb(self, name: str) -> None:
        text = _source(name).lower()
        for verb in ("place_order", "submit_order", "cancel_order", "execute_trade"):
            assert verb not in text, f"{name} names {verb}"

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_mentions_an_exchange_integration(self, name: str) -> None:
        assert "evedex" not in _source(name).lower(), name

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_calls_an_ai_model(self, name: str) -> None:
        text = _source(name).lower()
        for token in ("anthropic", "openai", "llm", "completion(", "prompt("):
            assert token not in text, f"{name} names {token}"

    @pytest.mark.parametrize("name", _MODULES)
    def test_only_the_artifact_module_touches_the_filesystem(self, name: str) -> None:
        """Only the artifact modules may write, and they write research records.

        Milestone BY adds `validation_artifact.py` to the exempt set on exactly
        the same footing as BW's and BX's: it is the ONE module of its milestone
        that touches a file, it writes a JSON research record, and
        `test_the_artifact_modules_write_no_store_record` below covers it too. No
        other BY module is exempt, and the renderer, the study, the mechanics and
        the pre-registration all fail this guard if they ever open a path.
        """
        text = _source(name)
        if name in _ARTIFACT_MODULES:
            return
        for token in ("open(", "write_text", "mkdir", "unlink", "Path("):
            assert token not in text, f"{name} touches the filesystem via {token}"

    @pytest.mark.parametrize("name", _ARTIFACT_MODULES)
    def test_the_artifact_modules_write_no_store_record(self, name: str) -> None:
        text = _source(name)
        for token in ("fmis.records", "fmis.persistence", "fmis.archive", "fmis.ledger"):
            assert token not in text

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_catches_bare_exception(self, name: str) -> None:
        for node in ast.walk(_tree(name)):
            if isinstance(node, ast.ExceptHandler):
                assert node.type is not None, f"{name} catches everything"
                if isinstance(node.type, ast.Name):
                    assert node.type.id != "Exception", f"{name} catches Exception"


class TestTheLaboratoryIsUnreachableFromProduction:
    def _production_sources(self) -> list[tuple[str, str]]:
        return [
            (str(path.relative_to(_SOURCE_ROOT)).replace("\\", "/"),
             path.read_text(encoding="utf-8"))
            for path in sorted(_SOURCE_ROOT.rglob("*.py"))
            if "swing_lab" not in path.parts
        ]

    def test_only_the_cli_imports_the_laboratory(self) -> None:
        """The CLI is a research *surface*; no engine may reach the lab.

        Checked as an **import**, parsed, rather than as the substring
        ``swing_lab`` anywhere in a file. A docstring that names the package is
        documentation and is welcome; an `import` is a dependency and is not.
        The dashboard is the case that proves the distinction matters: its
        `/lab` page describes lab figures in prose and receives them already
        decoded, so it depends on nothing here — which is exactly why it can
        keep its own guarantee of opening no file.
        """
        offenders = []
        for name, text in self._production_sources():
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                if any(item.startswith("fmis.swing_lab") for item in names):
                    offenders.append(name)
        assert set(offenders) <= {"pipeline/cli.py"}, (
            f"{sorted(set(offenders))} import the laboratory; a research policy "
            "reachable from an engine is a second trading policy in waiting"
        )

    def test_the_dashboard_depends_on_nothing_in_the_laboratory(self) -> None:
        """The `/lab` page renders lab figures without importing the lab.

        It receives an already-decoded view from the CLI. That is what lets the
        dashboard keep its own guarantee — no module in it opens a file — while
        still showing research on a page.
        """
        dashboard = _SOURCE_ROOT / "operator_dashboard"
        for path in sorted(dashboard.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith("fmis.swing_lab"), path.name
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith("fmis.swing_lab"), path.name

    def test_no_production_module_names_the_context_role_override(self) -> None:
        allowed = {"swing_setup/policy.py", "swing_setup/compose.py", "swing_setup/__init__.py"}
        offenders = [
            name
            for name, text in self._production_sources()
            if "research_context_role" in text and name not in allowed
        ]
        assert offenders == []

    def test_the_live_setup_entry_points_do_not_accept_the_override(self) -> None:
        from fmis.swing_setup import compose

        import inspect

        for function in (
            compose.setup_assessment_for_sheet,
            compose.setup_for_symbol,
            compose.run_setup_for_symbols,
        ):
            parameters = inspect.signature(function).parameters
            assert "research_context_role" not in parameters, function.__name__
            assert "research_confirmation_max_age" not in parameters, function.__name__


class TestNoPromotionVocabulary:
    """The package may describe a candidate; it may not promote one."""

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_claims_a_strategy_is_adopted(self, name: str) -> None:
        text = _source(name).lower()
        for phrase in (
            "new production strategy",
            "promote to production",
            "use this strategy",
            "adopt this variant",
        ):
            assert phrase not in text, f"{name} promotes a strategy"


class TestGeometryIsResearchOnly:
    """Milestone BX's own absences. Each is a way a geometry rule could go wrong."""

    @pytest.mark.parametrize("name", _GEOMETRY_POLICY_MODULES)
    def test_no_policy_module_constructs_a_price_level(self, name: str) -> None:
        """**A level is never invented.** Every stop and target must be one the
        structural engines already produced, so a policy module may not build a
        `PriceLevel` — 'place the target at 2R' has no spelling here."""
        for node in ast.walk(_tree(name)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "PriceLevel", f"{name} constructs a level"

    @pytest.mark.parametrize("name", _GEOMETRY_POLICY_MODULES)
    def test_no_policy_module_reads_a_bar_or_an_outcome(self, name: str) -> None:
        """A geometry policy decides before the outcome exists. If it could name
        an MFE, an MAE or a realized R, a future value could reach an admission
        rule — which is exactly what §11 of the brief forbids."""
        text = _source(name)
        for token in (
            "mfe", "mae", "net_r", "gross_r", "PriceBar", "exit_price",
            "simulate_trade", "fill_at_level", "reached(",
        ):
            assert token not in text, f"{name} reads {token}"

    @pytest.mark.parametrize("name", _GEOMETRY_POLICY_MODULES)
    def test_no_policy_module_imports_the_outcome_layer(self, name: str) -> None:
        """The isolation is one-directional and asserted in both directions."""
        imported = _imported_modules(name)
        for forbidden in (
            "fmis.swing_lab.geometry_outcome",
            "fmis.swing_lab.geometry_diagnosis",
            "fmis.swing_lab.trades",
            "fmis.paper.fills",
            "fmis.paper.models",
        ):
            assert forbidden not in imported, f"{name} imports {forbidden}"

    def test_the_outcome_layer_imports_no_policy(self) -> None:
        """The other direction: an outcome statistic can never become a rule."""
        imported = _imported_modules("geometry_outcome.py")
        assert "fmis.swing_lab.geometry_variants" not in imported

    @pytest.mark.parametrize(
        "name", (*_GEOMETRY_POLICY_MODULES, "nonstructural.py")
    )
    def test_no_policy_module_imports_the_persistence_layer(self, name: str) -> None:
        """Milestone BZ's twin of the guard above.

        A post-entry measurement — a give-back, a peak excursion, a thesis state
        — must never become an admission criterion. `persistence.py` is the
        post-entry twin of `geometry_outcome.py`, and the isolation is asserted
        in both directions rather than described in a docstring.
        """
        imported = _imported_modules(name)
        for forbidden in (
            "fmis.swing_lab.persistence",
            "fmis.swing_lab.persistence_replay",
            "fmis.swing_lab.persistence_study",
            "fmis.swing_lab.exits",
        ):
            assert forbidden not in imported, f"{name} imports {forbidden}"

    @pytest.mark.parametrize("name", _GEOMETRY_POLICY_MODULES)
    def test_no_policy_module_names_a_persistence_measurement(
        self, name: str
    ) -> None:
        text = _source(name)
        for token in (
            "peak_r", "giveback", "ThesisState", "PersistenceTrack",
            "PostEntryCheckpoint", "thesis_state",
        ):
            assert token not in text, f"{name} names {token}"

    def test_the_persistence_layer_imports_no_geometry_policy(self) -> None:
        """The other direction. A path measurement cannot reach a policy."""
        imported = _imported_modules("persistence.py")
        assert "fmis.swing_lab.geometry_variants" not in imported
        assert "fmis.swing_lab.nonstructural" not in imported

    def test_the_bz_preregistration_reads_no_measurement(self) -> None:
        """A BZ threshold cannot be derived from a result, even by accident."""
        imported = _imported_modules("persistence_preregistration.py")
        for forbidden in (
            "fmis.paper.models",
            "fmis.swing_lab.trades",
            "fmis.swing_lab.geometry_replay",
            "fmis.swing_lab.persistence_study",
        ):
            assert forbidden not in imported, (
                f"the BZ pre-registration imports {forbidden}"
            )

    def test_the_bz_seal_is_pinned_beside_its_content(self) -> None:
        """The seal and the content must live in one file, or neither guards."""
        text = _source("persistence_preregistration.py")
        assert "BZ_PREREGISTRATION_DIGEST: Final[str] = (" in text
        assert "def bz_preregistration_digest(" in text

    def test_bys_sealed_exit_policies_are_untouched_by_bz(self) -> None:
        """BZ added mechanics to a module BY sealed. BY's four must not move."""
        from fmis.swing_lab.exits import PRE_DECLARED_EXIT_POLICIES

        assert tuple(item.policy_id for item in PRE_DECLARED_EXIT_POLICIES) == (
            "exit_full_target",
            "exit_partial_1r",
            "exit_break_even_1r",
            "exit_trail_prior_bar",
        )

    def test_bys_pinned_digest_survives_every_bz_change(self) -> None:
        from fmis.swing_lab.preregistration import (
            PREREGISTRATION_DIGEST,
            preregistration_digest,
        )

        assert preregistration_digest() == PREREGISTRATION_DIGEST

    def test_the_level_ordering_rule_is_productions_own(self) -> None:
        """`ordered_levels` is called, never restated. A research copy of the
        ordering is exactly the copy that could drift from production's."""
        assert "ordered_levels" in _imported_modules_names("geometry.py")
        for name in _MODULES:
            tree = _tree(name)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    assert node.name != "ordered_levels", f"{name} defines its own"

    def test_no_geometry_module_assigns_a_production_constant(self) -> None:
        """Threshold shopping, made structurally impossible for the constants a
        researcher would most want to move.

        `SAMPLE_FLOOR` is exempt in `metrics.py` alone, because that module
        **owns** it. Every other module — including all nine BX ones — may read
        it and may not rebind it, which is the property that matters: a variant
        cannot lower the floor to make its own thin cohort reportable.
        """
        owners = {"SAMPLE_FLOOR": "metrics.py"}
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if not isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                    continue
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                for target in targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if owners.get(target.id) == name:
                        continue
                    assert target.id not in (
                        "MINIMUM_AGREEING_FAMILIES",
                        "CONFIRMATION_LOOKBACK_BARS",
                        "DEFAULT_TIMEFRAMES",
                        "SAMPLE_FLOOR",
                    ), f"{name} assigns {target.id}"

    def test_the_trade_simulator_is_milestone_bws(self) -> None:
        """No second simulator: the geometry replay calls `simulate_trade`."""
        assert "fmis.swing_lab.trades" in _imported_modules("geometry_replay.py")
        for name in _MODULES:
            if name == "trades.py":
                continue
            for node in ast.walk(_tree(name)):
                if isinstance(node, ast.FunctionDef):
                    assert node.name != "simulate_trade", f"{name} defines its own"

    def test_the_volatility_measure_is_an_existing_feature(self) -> None:
        """No volatility engine was added: the ATR is the production feature,
        named from the production constant rather than retyped."""
        imported = _imported_modules("geometry_replay.py")
        assert "fmis.features.indicators.atr" in imported
        assert "fmis.pipeline.regime" in imported
        for name in _MODULES:
            text = _source(name)
            assert "true_range" not in text, f"{name} computes a true range"

    def test_no_geometry_module_defines_a_second_metrics_engine(self) -> None:
        for name in _MODULES:
            if name == "metrics.py":
                continue
            for node in ast.walk(_tree(name)):
                if isinstance(node, ast.FunctionDef):
                    assert node.name not in (
                        "compute_lab_metrics", "classify", "lab_breakdown_by"
                    ), f"{name} redefines {node.name}"

    def test_the_verdict_layer_can_never_approve_trading(self) -> None:
        text = _source("geometry_verdict.py")
        assert "approved_for_live" not in text.lower()
        assert "APPROVED" not in text or "is_approved_for_trading" in text

    def test_no_geometry_module_names_a_position_size_or_leverage(self) -> None:
        """§7: BX must not improve a result by risking more. Position sizing is
        a separate layer and this package cannot reach it."""
        for name in _MODULES:
            text = _source(name).lower()
            for token in ("leverage", "position_size", "notional_size", "margin"):
                assert token not in text, f"{name} names {token}"


def _imported_modules_names(name: str) -> set[str]:
    """Every bare name imported by ``name`` (as opposed to every module)."""
    found: set[str] = set()
    for node in ast.walk(_tree(name)):
        if isinstance(node, ast.ImportFrom):
            found.update(alias.asname or alias.name for alias in node.names)
    return found
