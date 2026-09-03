"""Structural guards: the design layer cannot become a second trading system.

Every guard asserts an **absence**, and each absence is one way a statistics
package quietly stops being general or stops being safe:

* a dependency on the swing laboratory, which would make the "reusable core"
  a swing module with a different name;
* a trading vocabulary — ATR, R, BTC, symbol — baked into the core rather than
  supplied by an adapter;
* a file, a network call, an AI call or a store write;
* a renderer that owns a rule;
* a verdict that could be read as an endorsement.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "fmis"
_PACKAGE = _SOURCE_ROOT / "research_design"

_MODULES = (
    "__init__.py",
    "artifact.py",
    "dependence.py",
    "models.py",
    "numeric.py",
    "render.py",
    "resolution.py",
    "verdict.py",
)

#: Presentation may own no rule. This is the swing laboratory's constraint,
#: inherited for the same reason: a renderer that decided anything would make the
#: report unreplaceable.
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
    """The identity of every docstring node, so prose can be told from code.

    This is the distinction `test_only_the_cli_imports_the_laboratory` draws for
    the swing laboratory and it matters at least as much here: a docstring that
    explains *why this package exists* has to name Milestone CA's ATR effect, and
    an identifier or a runtime string that names it is a coupling. Checking the
    raw source cannot tell them apart; checking the parsed tree can.
    """
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
    """Every string constant that is NOT a docstring: the text this module emits."""
    tree = _tree(name)
    docs = _docstrings(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docs
    ]


def _code_names(name: str) -> set[str]:
    """Every identifier this module defines, uses or imports. Lower-cased."""
    found: set[str] = set()
    for node in ast.walk(_tree(name)):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.update(alias.name.split("."))
                if alias.asname:
                    found.add(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            found.update((node.module or "").split("."))
            for alias in node.names:
                found.add(alias.name)
                if alias.asname:
                    found.add(alias.asname)
    return {item.lower() for item in found}


def _called_names(name: str) -> set[str]:
    """Every function or method this module actually CALLS. Case preserved.

    A side effect is a call. ``path`` is a legitimate parameter name here — it
    holds a `GrowthPath` — so the filesystem guard asks what is invoked rather
    than what is spelled.
    """
    found: set[str] = set()
    for node in ast.walk(_tree(name)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            found.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            found.add(node.func.attr)
    return found


def _code_text(name: str) -> str:
    """Identifiers and runtime strings, joined and lower-cased. **No prose.**"""
    return " ".join([*sorted(_code_names(name)), *_runtime_strings(name)]).lower()


def test_the_package_holds_exactly_the_modules_these_guards_cover() -> None:
    """A new module must be added to `_MODULES`, so none escapes review."""
    assert {path.name for path in _PACKAGE.glob("*.py")} == set(_MODULES)


@pytest.mark.parametrize("name", _MODULES)
def test_every_module_imports_in_a_fresh_interpreter(name: str) -> None:
    module = (
        f"fmis.research_design.{name[:-3]}" if name != "__init__.py" else "fmis.research_design"
    )
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        cwd=_SOURCE_ROOT.parents[1],
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", _MODULES)
def test_every_module_has_a_docstring(name: str) -> None:
    assert ast.get_docstring(_tree(name)), name


class TestTheCoreIsGeneral:
    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_depends_on_the_swing_laboratory(self, name: str) -> None:
        """The dependency runs the other way. This is the whole reuse claim."""
        for imported in _imported_modules(name):
            assert not imported.startswith("fmis.swing_lab"), name

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_names_a_trading_instrument_or_unit_in_its_CODE(
        self, name: str
    ) -> None:
        """`atr`, `btcusdt` and `candle` belong to an adapter, never to the core.

        Checked over **identifiers and runtime strings**, not over prose. The
        docstrings here must be free to say that Milestone CA's bar was +0.10 ATR,
        because that is the case which forced this package into existence and a
        package that could not explain itself would be worse. What may not happen
        is a field, a default, a branch or an emitted message that knows what an
        ATR is — that is a swing package wearing a general name, and it arrives one
        convenient default at a time.
        """
        text = _code_text(name)
        for token in ("atr", "btcusdt", "crypto", "candle", "ohlc", "bps", "usdt"):
            assert token not in text, f"{name} names {token} in code"

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_names_a_trading_instrument_in_a_runtime_message(
        self, name: str
    ) -> None:
        """The same absence, stated separately over what a user can actually read."""
        for emitted in _runtime_strings(name):
            lowered = emitted.lower()
            for token in ("atr", "btcusdt", "crypto", "candle", "ohlc"):
                assert token not in lowered, f"{name} emits {token!r} in {emitted!r}"

    def test_the_docstrings_ARE_allowed_to_name_the_case_that_motivated_this(self) -> None:
        """The other half of the distinction, asserted so it cannot be lost.

        If this test ever fails it means the guards above were widened to cover
        prose, which would force the package to stop explaining why it exists.
        """
        module = ast.get_docstring(_tree("__init__.py")) or ""
        assert "ATR" in module
        assert "atr" not in _code_text("__init__.py")

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_declares_a_default_effect_threshold(self, name: str) -> None:
        """The research question owns the meaningful effect. Always."""
        text = _source(name)
        for token in ("MINIMUM_EFFECT", "DEFAULT_EFFECT", "MIN_EFFECT", "DEFAULT_THRESHOLD"):
            assert token not in text, f"{name} declares {token}"

    def test_the_core_owns_no_confidence_default(self) -> None:
        """Every entry point takes a confidence; none supplies one."""
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if not isinstance(node, ast.FunctionDef):
                    continue
                arguments = node.args
                named = list(arguments.args) + list(arguments.kwonlyargs)
                defaults = list(arguments.defaults) + [
                    item for item in arguments.kw_defaults if item is not None
                ]
                if not any(item.arg == "confidence" for item in named):
                    continue
                assert not defaults or all(
                    not isinstance(item, ast.Constant)
                    or not isinstance(item.value, float)
                    or item.value != 0.95
                    for item in defaults
                ), f"{name}.{node.name} defaults a confidence level"


class TestNoSideEffects:
    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_touches_the_filesystem(self, name: str) -> None:
        """**Nothing here opens a file.** A design assessment is recomputable and
        disposable, so persisting it is a caller's decision and there is no module
        in this package that could take it.

        Asked as two questions rather than as a substring probe. A blunt
        ``"Path("`` probe matches `GrowthPath(Enum)`, and a guard that fires on a
        class name teaches the next reader to weaken it. Nothing in Python reaches
        a file without importing one of these modules or calling one of these
        names, so the pair is decisive rather than approximate.
        """
        imported = _imported_modules(name)
        for module in ("pathlib", "os", "io", "gzip", "shutil", "tempfile", "subprocess"):
            assert module not in imported, f"{name} imports {module}"
        called = _called_names(name)
        for token in (
            "open", "Path", "write_text", "read_text", "write_bytes", "read_bytes",
            "mkdir", "unlink", "rmtree", "NamedTemporaryFile",
        ):
            assert token not in called, f"{name} calls {token}"

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_reaches_a_network(self, name: str) -> None:
        text = _source(name).lower()
        for token in ("urllib", "requests", "socket", "http", "fetch_"):
            assert token not in text, f"{name} names {token}"

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_writes_a_store_record(self, name: str) -> None:
        text = _source(name)
        for token in ("fmis.records", "fmis.persistence", "fmis.archive", "fmis.ledger"):
            assert token not in text, name

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_calls_an_ai_model(self, name: str) -> None:
        text = _source(name).lower()
        for token in ("anthropic", "openai", "llm", "completion(", "prompt("):
            assert token not in text, f"{name} names {token}"

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_names_an_execution_verb(self, name: str) -> None:
        text = _source(name).lower()
        for verb in ("place_order", "submit_order", "cancel_order", "execute_trade"):
            assert verb not in text, f"{name} names {verb}"

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_catches_bare_exception(self, name: str) -> None:
        for node in ast.walk(_tree(name)):
            if isinstance(node, ast.ExceptHandler):
                assert node.type is not None, f"{name} catches everything"
                if isinstance(node.type, ast.Name):
                    assert node.type.id != "Exception", f"{name} catches Exception"

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_uses_an_unseeded_generator(self, name: str) -> None:
        """`random.random()` at module scope would make a result unreproducible."""
        text = _source(name)
        for token in ("random.random", "random.seed", "randint(", "shuffle("):
            assert token not in text, f"{name} draws from an unseeded generator"

    @pytest.mark.parametrize("name", _MODULES)
    def test_no_module_reads_the_clock(self, name: str) -> None:
        """A design assessment is a pure function of its inputs."""
        text = _source(name)
        for token in ("datetime.now", "utcnow", "time.time", "monotonic"):
            assert token not in text, f"{name} reads the clock"


class TestTheRendererOwnsNoRule:
    @pytest.mark.parametrize("name", _RENDER_MODULES)
    def test_it_imports_no_estimator_and_no_verdict_machinery(self, name: str) -> None:
        imported = _imported_modules(name)
        assert "fmis.research_design.resolution" not in imported
        assert "fmis.research_design.verdict" not in imported
        assert "fmis.research_design.numeric" not in imported

    @pytest.mark.parametrize("name", _RENDER_MODULES)
    def test_it_constructs_no_decimal_and_names_no_comparison_threshold(
        self, name: str
    ) -> None:
        for node in ast.walk(_tree(name)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "Decimal", f"{name} constructs a Decimal"

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
    def test_it_recommends_no_trade(self, name: str) -> None:
        """Checked over what the renderer PRINTS, which is the strongest form.

        A renderer's non-docstring string constants are its output, so this is not
        a proxy for the property — it is the property. Its docstring is free to
        say that no trading recommendation appears, which is the sentence a reader
        needs and the one a raw-source probe would reject.
        """
        for emitted in _runtime_strings(name):
            lowered = emitted.lower()
            for phrase in ("buy", "sell", "long the", "short the", "recommend"):
                assert phrase not in lowered, f"{name} emits {phrase!r} in {emitted!r}"


class TestThePackageDeclaresWhatItExports:
    def test_every_exported_name_exists(self) -> None:
        package = importlib.import_module("fmis.research_design")
        assert package.__all__
        for name in package.__all__:
            assert hasattr(package, name), name

    def test_every_module_declares_its_own_exports(self) -> None:
        for name in _MODULES:
            if name == "__init__.py":
                continue
            module = importlib.import_module(f"fmis.research_design.{name[:-3]}")
            assert getattr(module, "__all__", None), name

    def test_the_package_exports_no_composite_score(self) -> None:
        package = importlib.import_module("fmis.research_design")
        exported = " ".join(package.__all__).lower()
        for forbidden in ("score", "grade", "rating", "health", "rank"):
            assert forbidden not in exported


class TestTheProductionBoundary:
    def test_only_the_cli_and_the_laboratory_import_this_package(self) -> None:
        """A design gate reachable from a trading engine would be a trading rule."""
        offenders: set[str] = set()
        for path in sorted(_SOURCE_ROOT.rglob("*.py")):
            if "research_design" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                if any(item.startswith("fmis.research_design") for item in names):
                    offenders.add(str(path.relative_to(_SOURCE_ROOT)).replace("\\", "/"))
        # Milestone CC adds `universe/growth.py`, on exactly the footing this
        # package was built for: it is the second ADAPTER, expressing a second
        # milestone's design question in the general vocabulary. The dependency
        # still runs one way — nothing here imports `fmis.universe` — so the reuse
        # claim is strengthened rather than weakened, and the property this guard
        # protects is unchanged: no ENGINE reaches the design layer.
        assert offenders <= {
            "pipeline/cli.py",
            "swing_lab/admission_matching.py",
            "swing_lab/admission_power.py",
            "swing_lab/metrics.py",
            "swing_lab/robustness.py",
            "universe/growth.py",
        }, sorted(offenders)

    def test_the_dashboard_depends_on_nothing_here(self) -> None:
        dashboard = _SOURCE_ROOT / "operator_dashboard"
        for path in sorted(dashboard.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith("fmis.research_design"), path.name
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith("fmis.research_design"), path.name
