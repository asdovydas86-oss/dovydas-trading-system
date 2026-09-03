"""Structural guards: Milestone CC cannot become a second trading system.

Every guard asserts an **absence**, and each absence is one way a research package
quietly stops being research:

* a production module that imports it, which would make a feasibility gate a
  trading rule;
* a credential, an order verb or a private endpoint;
* a changed production constant — the thing CC is most able to break by accident,
  because it replays the production admission path;
* a renderer that owns a threshold;
* a verdict that could be read as an endorsement.

The production-safety class is the one that matters most. CC calls
`capture_for_window` under the production variant, so a careless edit anywhere in
this milestone could move a live constant. These tests pin the values.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "fmis"
_PACKAGE = _SOURCE_ROOT / "universe"

_MODULES = (
    "__init__.py",
    "artifact.py",
    "capture.py",
    "controls.py",
    "density.py",
    "dependence.py",
    "eligibility.py",
    "growth.py",
    "horizon.py",
    "identity.py",
    "models.py",
    "preregistration.py",
    "render.py",
    "study.py",
    "verdict.py",
)

#: The only modules permitted to reach a network. Everything else is arithmetic.
_NETWORK_MODULES = ("capture.py", "density.py", "study.py", "controls.py")

_RENDER_MODULES = ("render.py",)


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


def _docstrings(tree: ast.Module) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            found.add(id(first.value))
    return found


def _runtime_strings(name: str) -> list[str]:
    tree = _tree(name)
    docs = _docstrings(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docs
    ]


def test_the_package_holds_exactly_the_modules_these_guards_cover() -> None:
    """A new module must be added to `_MODULES`, so none escapes review."""
    assert {path.name for path in _PACKAGE.glob("*.py")} == set(_MODULES)


@pytest.mark.parametrize("name", _MODULES)
def test_every_module_imports_in_a_fresh_interpreter(name: str) -> None:
    module = f"fmis.universe.{name[:-3]}" if name != "__init__.py" else "fmis.universe"
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True, text=True, cwd=_SOURCE_ROOT.parents[1],
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", _MODULES)
def test_every_module_has_a_docstring(name: str) -> None:
    assert ast.get_docstring(_tree(name)), name


class TestTheProductionBoundary:
    def test_no_production_module_imports_this_package(self) -> None:
        """A feasibility gate reachable from a trading engine would be a rule."""
        offenders: set[str] = set()
        for path in sorted(_SOURCE_ROOT.rglob("*.py")):
            if "universe" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                if any(item.startswith("fmis.universe") for item in names):
                    offenders.add(str(path.relative_to(_SOURCE_ROOT)).replace("\\", "/"))
        assert offenders <= {"pipeline/cli.py"}, sorted(offenders)

    def test_the_dashboard_depends_on_nothing_here(self) -> None:
        dashboard = _SOURCE_ROOT / "operator_dashboard"
        for path in sorted(dashboard.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith("fmis.universe"), path.name
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith("fmis.universe"), path.name

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_names_an_execution_verb(self, name: str) -> None:
        text = _source(name).lower()
        for verb in (
            "place_order", "submit_order", "cancel_order", "execute_trade",
            "new_order", "/api/v3/order",
        ):
            assert verb not in text, f"{name} names {verb}"

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_reads_a_credential(self, name: str) -> None:
        text = _source(name).lower()
        for token in ("api_key", "apikey", "secret", "signature", "hmac", "x-mbx-apikey"):
            assert token not in text, f"{name} names {token}"

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_writes_a_trading_store_record(self, name: str) -> None:
        text = _source(name)
        for token in ("fmis.records", "fmis.ledger", "fmis.paper", "fmis.positions"):
            assert token not in text, name

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_calls_an_ai_model(self, name: str) -> None:
        text = _source(name).lower()
        for token in ("anthropic", "openai", "llm", "completion(", "prompt("):
            assert token not in text, f"{name} names {token}"


class TestOnlyTheCaptureLayerFetches:
    @pytest.mark.parametrize(
        "name",
        [
            item for item in _MODULES
            # `__init__.py` is excluded and the exclusion is NOT a loosening: the
            # test below asserts it defines nothing at all, so the only way it can
            # name `fetch_daily_bars` is by re-exporting it. A facade that names a
            # fetcher does not fetch; a facade that could define one would, which
            # is the property actually worth guarding.
            if item not in _NETWORK_MODULES and item != "__init__.py"
        ],
    )
    def test_a_measurement_module_reaches_no_network(self, name: str) -> None:
        """Arithmetic modules must be pure, so an offline re-run is a real claim."""
        text = _source(name).lower()
        for token in ("urllib", "requests", "socket", "http", "fetch_"):
            assert token not in text, f"{name} names {token}"

    def test_the_package_facade_defines_nothing_and_only_re_exports(self) -> None:
        """What makes excluding `__init__.py` above safe rather than convenient."""
        tree = _tree("__init__.py")
        for node in tree.body:
            assert isinstance(
                node, (ast.Import, ast.ImportFrom, ast.Expr, ast.Assign, ast.AnnAssign)
            ), f"the facade defines {type(node).__name__}"
            if isinstance(node, ast.Assign):
                assert [
                    target.id for target in node.targets if isinstance(target, ast.Name)
                ] == ["__all__"], "the facade assigns something other than __all__"

    @pytest.mark.parametrize(
        "name",
        [
            item for item in _MODULES
            if item not in ("capture.py", "artifact.py", "__init__.py", "study.py")
        ],
    )
    def test_a_measurement_module_touches_no_filesystem(self, name: str) -> None:
        imported = _imported_modules(name)
        for module in ("pathlib", "os", "io", "gzip", "shutil", "tempfile", "subprocess"):
            assert module not in imported, f"{name} imports {module}"

    @pytest.mark.parametrize(
        "name", [item for item in _MODULES if item not in ("capture.py", "study.py")]
    )
    def test_a_measurement_module_does_not_read_the_clock(self, name: str) -> None:
        text = _source(name)
        for token in ("datetime.now", "utcnow", "time.time", "monotonic"):
            assert token not in text, f"{name} reads the clock"

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_uses_an_unseeded_generator(self, name: str) -> None:
        """A universe that changed between runs would not be reproducible."""
        text = _source(name)
        for token in ("random.random", "random.seed", "randint(", "shuffle(", "sample("):
            assert token not in text, f"{name} draws from an unseeded generator"

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_catches_bare_exception(self, name: str) -> None:
        for node in ast.walk(_tree(name)):
            if isinstance(node, ast.ExceptHandler):
                assert node.type is not None, f"{name} catches everything"
                if isinstance(node.type, ast.Name):
                    assert node.type.id != "Exception", f"{name} catches Exception"


class TestTheRendererOwnsNoRule:
    @pytest.mark.parametrize("name", _RENDER_MODULES)
    def test_it_declares_no_float_constant(self, name: str) -> None:
        """A float in a renderer is a threshold that escaped its owner."""
        floats = {
            node.value
            for node in ast.walk(_tree(name))
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        }
        assert floats == set(), name

    @pytest.mark.parametrize("name", _RENDER_MODULES)
    def test_it_imports_no_measurement_machinery(self, name: str) -> None:
        imported = _imported_modules(name)
        for module in (
            "fmis.universe.growth", "fmis.universe.verdict",
            "fmis.universe.dependence", "fmis.universe.eligibility",
            "fmis.research_design",
        ):
            assert module not in imported, f"{name} imports {module}"

    @pytest.mark.parametrize("name", _RENDER_MODULES)
    def test_it_recommends_no_trade(self, name: str) -> None:
        for emitted in _runtime_strings(name):
            lowered = emitted.lower()
            for phrase in ("buy", "sell", "long the", "short the", "recommend"):
                assert phrase not in lowered, f"{name} emits {phrase!r}"


class TestThePackageDeclaresWhatItExports:
    def test_every_exported_name_exists(self) -> None:
        package = importlib.import_module("fmis.universe")
        assert package.__all__
        for name in package.__all__:
            assert hasattr(package, name), name

    def test_every_module_declares_its_own_exports(self) -> None:
        for name in _MODULES:
            if name == "__init__.py":
                continue
            module = importlib.import_module(f"fmis.universe.{name[:-3]}")
            assert getattr(module, "__all__", None), name

    def test_the_package_exports_no_composite_score(self) -> None:
        package = importlib.import_module("fmis.universe")
        exported = " ".join(package.__all__).lower()
        for forbidden in ("score", "grade", "rating", "health", "rank"):
            assert forbidden not in exported


class TestProductionSafety:
    """**The constants Milestone CC replays and must not have moved.**"""

    def test_the_confirmation_lookback_is_unchanged(self) -> None:
        from fmis.swing_setup.policy import CONFIRMATION_LOOKBACK_BARS

        assert CONFIRMATION_LOOKBACK_BARS == 10

    def test_the_minimum_agreeing_families_is_unchanged(self) -> None:
        from fmis.swing_setup.policy import MINIMUM_AGREEING_FAMILIES

        assert MINIMUM_AGREEING_FAMILIES == 2

    def test_the_production_timeframe_roles_are_unchanged(self) -> None:
        from fmis.pipeline.multi_timeframe import DEFAULT_TIMEFRAMES, TimeframeRole

        assert DEFAULT_TIMEFRAMES[TimeframeRole.CONTEXT] == "1w"
        assert DEFAULT_TIMEFRAMES[TimeframeRole.SETUP] == "1d"
        assert DEFAULT_TIMEFRAMES[TimeframeRole.EXECUTION] == "4h"

    def test_the_production_analysis_window_is_unchanged(self) -> None:
        from fmis.swing_setup.backtest_harness import DEFAULT_BACKTEST_LIMIT

        assert DEFAULT_BACKTEST_LIMIT == 250

    def test_the_derived_warmup_is_what_the_study_reported(self) -> None:
        """1,750 days. If this moves, every eligibility figure moves with it."""
        from fmis.universe.eligibility import warmup_prefix

        assert warmup_prefix().days == 1750

    def test_the_CA_seal_is_byte_identical(self) -> None:
        from fmis.swing_lab.admission_preregistration import (
            CA_PREREGISTRATION_DIGEST,
            ca_preregistration_digest,
        )

        assert ca_preregistration_digest() == CA_PREREGISTRATION_DIGEST

    def test_the_BY_seal_is_byte_identical(self) -> None:
        from fmis.swing_lab.preregistration import (
            PREREGISTRATION_DIGEST,
            preregistration_digest,
        )

        assert preregistration_digest() == PREREGISTRATION_DIGEST

    def test_the_admission_density_measurement_uses_the_production_variant(self) -> None:
        """A density measured under a research override would not be production's."""
        source = _source("density.py")
        assert "capture_for_window" in source
        for override in ("context_role=", "max_confirmation_age=", "LabVariant("):
            assert override not in source, f"density.py supplies {override}"

    def test_milestone_CB_results_still_reproduce(self) -> None:
        from fmis.universe.growth import cb_required_information

        requirement = cb_required_information()
        assert requirement.required_observations == 4823
        assert requirement.required_clusters == 467
