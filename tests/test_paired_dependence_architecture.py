"""Structural guards: Milestone CD cannot become a second trading system.

Every guard asserts an **absence**, and each absence is one way a research
package quietly stops being research:

* a production module that imports it, which would make a dependence estimate a
  trading rule;
* a credential, an order verb or a private endpoint;
* a changed production constant — the thing CD is most able to break by accident,
  because it replays Milestone CA which replays the production admission path;
* a measurement module that reaches a network, so an "offline reproduction"
  claim stops being checkable;
* a renderer that owns a threshold;
* a verdict that could be read as an endorsement.

The production-safety class is the one that matters most. CD reaches Milestone
CA's paired records by adding an observer to CA's own study loop, so a careless
edit anywhere in this milestone could move a live constant or a sealed digest.
These tests pin every one of them.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "fmis"
_PACKAGE = _SOURCE_ROOT / "paired_dependence"

_MODULES = (
    "__init__.py",
    "artifact.py",
    "capture.py",
    "controls.py",
    "estimator.py",
    "integration.py",
    "models.py",
    "observations.py",
    "preregistration.py",
    "render.py",
    "study.py",
    "synthetic.py",
    "uncertainty.py",
    "verdict.py",
)

#: The only module permitted to reach a network. Everything else is arithmetic,
#: and that is what makes `--from-study` a real reproduction rather than a claim.
_NETWORK_MODULES = ("capture.py",)

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
    module = (
        f"fmis.paired_dependence.{name[:-3]}"
        if name != "__init__.py"
        else "fmis.paired_dependence"
    )
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
        """A dependence estimate reachable from a trading engine would be a rule."""
        offenders: set[str] = set()
        for path in sorted(_SOURCE_ROOT.rglob("*.py")):
            if "paired_dependence" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                if any(item.startswith("fmis.paired_dependence") for item in names):
                    offenders.add(str(path.relative_to(_SOURCE_ROOT)).replace("\\", "/"))
        assert offenders <= {"pipeline/cli.py"}, sorted(offenders)

    def test_the_dashboard_depends_on_nothing_here(self) -> None:
        dashboard = _SOURCE_ROOT / "operator_dashboard"
        for path in sorted(dashboard.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith(
                        "fmis.paired_dependence"
                    ), path.name
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith(
                            "fmis.paired_dependence"
                        ), path.name

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
            # name a fetcher is by re-exporting one.
            if item not in _NETWORK_MODULES and item != "__init__.py"
        ],
    )
    def test_a_measurement_module_reaches_no_network(self, name: str) -> None:
        text = _source(name).lower()
        for token in ("urllib", "requests", "socket", "http", "fetch_"):
            assert token not in text, f"{name} names {token}"

    def test_the_package_facade_defines_nothing_and_only_re_exports(self) -> None:
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
            if item not in ("capture.py", "artifact.py", "__init__.py")
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
        """A measurement that changed between runs would not be reproducible."""
        text = _source(name)
        for token in ("random.random()", "random.seed", "randint("):
            assert token not in text, f"{name} draws from an unseeded generator"

    @pytest.mark.parametrize("name", _MODULES)
    def test_every_shuffle_and_choice_runs_on_a_seeded_generator(self, name: str) -> None:
        """`Random(seed).shuffle` is fine; the module-level `shuffle` is not."""
        for node in ast.walk(_tree(name)):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in ("shuffle", "choice", "sample", "gauss"):
                continue
            owner = node.func.value
            assert not (
                isinstance(owner, ast.Name) and owner.id == "random"
            ), f"{name} calls the module-level random.{node.func.attr}"

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
            "fmis.paired_dependence.estimator",
            "fmis.paired_dependence.uncertainty",
            "fmis.paired_dependence.verdict",
            "fmis.paired_dependence.integration",
            "fmis.research_design",
        ):
            assert module not in imported, f"{name} imports {module}"

    @pytest.mark.parametrize("name", _RENDER_MODULES)
    def test_it_recommends_no_trade(self, name: str) -> None:
        for emitted in _runtime_strings(name):
            lowered = emitted.lower()
            for phrase in ("buy", "sell", "long the", "short the", "recommend"):
                assert phrase not in lowered, f"{name} emits {phrase!r}"

    @pytest.mark.parametrize("name", _RENDER_MODULES)
    def test_it_compares_nothing_against_a_threshold(self, name: str) -> None:
        for node in ast.walk(_tree(name)):
            if isinstance(node, ast.Compare):
                for operand in [node.left, *node.comparators]:
                    assert not (
                        isinstance(operand, ast.Constant)
                        and isinstance(operand.value, (int, float))
                        and not isinstance(operand.value, bool)
                    ), f"{name} compares against a literal number"


class TestThePackageDeclaresWhatItExports:
    def test_every_exported_name_exists(self) -> None:
        package = importlib.import_module("fmis.paired_dependence")
        assert package.__all__
        for name in package.__all__:
            assert hasattr(package, name), name

    def test_every_module_declares_its_own_exports(self) -> None:
        for name in _MODULES:
            if name == "__init__.py":
                continue
            module = importlib.import_module(f"fmis.paired_dependence.{name[:-3]}")
            assert getattr(module, "__all__", None), name

    def test_the_package_exports_no_composite_score(self) -> None:
        package = importlib.import_module("fmis.paired_dependence")
        exported = " ".join(package.__all__).lower()
        for forbidden in ("score", "grade", "rating", "health", "rank"):
            assert forbidden not in exported


class TestNoVerdictEndorses:
    def test_both_vocabularies_refuse_across_every_member(self) -> None:
        from fmis.paired_dependence.models import DependenceVerdict, RequirementOutcome

        for enum in (DependenceVerdict, RequirementOutcome):
            for member in enum:
                assert member.is_approved_for_trading is False, member
                assert member.earns_forward_test is False, member
                assert member.says_nothing_about_the_hypothesis is True, member

    def test_no_member_name_reads_as_an_endorsement(self) -> None:
        from fmis.paired_dependence.models import DependenceVerdict, RequirementOutcome

        for enum in (DependenceVerdict, RequirementOutcome):
            for member in enum:
                lowered = member.value.lower()
                for word in ("approve", "promote", "trade", "candidate", "go"):
                    assert word not in lowered, member


class TestProductionSafety:
    """**The constants Milestone CD replays and must not have moved.**"""

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

    def test_the_derived_warmup_is_still_1750_days(self) -> None:
        from fmis.universe.eligibility import warmup_prefix

        assert warmup_prefix().days == 1750

    def test_the_CA_seal_is_byte_identical(self) -> None:
        from fmis.swing_lab.admission_preregistration import (
            CA_PREREGISTRATION_DIGEST,
            ca_preregistration_digest,
        )

        assert ca_preregistration_digest() == CA_PREREGISTRATION_DIGEST
        assert CA_PREREGISTRATION_DIGEST == (
            "910cad28001ee18d9630f685e454bfd6bf24fb7d78b907e89172371b83f25e8a"
        )

    def test_the_BZ_seal_is_byte_identical(self) -> None:
        from fmis.swing_lab.persistence_preregistration import (
            BZ_PREREGISTRATION_DIGEST,
        )

        assert BZ_PREREGISTRATION_DIGEST == (
            "4d089ff43ec11e24e7e43e0a0f7ca377da996ee5a6391bb8f9c70d6922a3a175"
        )

    def test_the_BY_seal_is_byte_identical(self) -> None:
        from fmis.swing_lab.preregistration import (
            PREREGISTRATION_DIGEST,
            preregistration_digest,
        )

        assert preregistration_digest() == PREREGISTRATION_DIGEST

    def test_the_CC_seal_is_byte_identical(self) -> None:
        from fmis.universe.preregistration import (
            CC_PREREGISTRATION_DIGEST,
            cc_preregistration_digest,
        )

        assert cc_preregistration_digest() == CC_PREREGISTRATION_DIGEST
        assert CC_PREREGISTRATION_DIGEST == (
            "ef6f39508a3d183c88618c727ba65fd8c6ffdcada4452660aaa4ad74a0021bac"
        )

    def test_milestone_CB_results_still_reproduce(self) -> None:
        from fmis.paired_dependence.integration import cb_required_clusters

        clusters, admissions, _per_cluster = cb_required_clusters()
        assert clusters == 467
        assert admissions == 4823

    def test_milestone_CA_s_own_verdict_vocabulary_is_untouched(self) -> None:
        from fmis.swing_lab.admission_preregistration import CaVerdict

        assert [item.value for item in CaVerdict] == [
            "no_edge", "inconclusive", "mechanism_evidence", "admission_edge_candidate"
        ]

    def test_milestone_CC_s_verdict_vocabulary_is_untouched(self) -> None:
        from fmis.universe.models import FeasibilityVerdict

        assert [item.value for item in FeasibilityVerdict] == [
            "feasible", "feasible_with_limitations", "infeasible", "indeterminate"
        ]


class TestTheObserverHookIsAdditive:
    def test_it_defaults_to_absent_so_ca_is_unchanged_by_default(self) -> None:
        import inspect

        from fmis.swing_lab.admission_study import study_from_capture

        parameter = inspect.signature(study_from_capture).parameters["record_observer"]
        assert parameter.default is None
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY

    def test_it_is_called_only_where_the_primary_seed_s_records_are_collected(self) -> None:
        source = (_SOURCE_ROOT / "swing_lab" / "admission_study.py").read_text(
            encoding="utf-8"
        )
        # Once as the guarded call; the definition of the read-only projection is
        # a separate name and is not a second call site.
        assert source.count("record_observer(\n") == 1
        index = source.index("record_observer(\n")
        preceding = source[:index]
        assert "if record_observer is not None:" in preceding[-900:]
        # And it sits after the primary-seed collection, never inside the
        # alternate-seed loop, which exists only to answer whether a sign is a
        # property of the data or of one draw.
        assert "collected[family.family_id].extend(records)" in preceding[-1200:]

    def test_the_observer_receives_read_only_records(self) -> None:
        """Inertness must be a property of the HOOK, not of CD's own observer.

        `PairedRecord` is frozen but its horizon maps were plain dicts behind a
        `Mapping` annotation, so an observer could write into one and move
        Milestone CA's published effect. Found by independent review.
        """
        source = (_SOURCE_ROOT / "swing_lab" / "admission_study.py").read_text(
            encoding="utf-8"
        )
        assert "_read_only_record(item) for item in records" in source
        assert "MappingProxyType" in source
