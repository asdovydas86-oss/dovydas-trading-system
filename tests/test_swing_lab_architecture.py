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
    "artifact.py",
    "gate.py",
    "metrics.py",
    "models.py",
    "render.py",
    "replay.py",
    "robustness.py",
    "study.py",
    "trades.py",
    "variants.py",
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
        """One module may write, and it writes a research record, never a store."""
        text = _source(name)
        if name == "artifact.py":
            return
        for token in ("open(", "write_text", "mkdir", "unlink", "Path("):
            assert token not in text, f"{name} touches the filesystem via {token}"

    def test_the_artifact_module_writes_no_store_record(self) -> None:
        text = _source("artifact.py")
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
