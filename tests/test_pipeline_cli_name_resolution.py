"""Every name the CLI reads at runtime must actually resolve. **A NameError guard.**

Milestone BX's audit found `fmits research swing` crashing on *every* invocation:
`cli.py` referenced `DEFAULT_BACKTEST_LIMIT` without importing it, so the command
raised `NameError` the moment it reached the call. It shipped because no test
executed that line — and a command's argument-construction line is exactly the
kind of code an offline suite never reaches.

Two guards, deliberately at different levels:

* `TestEveryGlobalNameResolves` is **static and total**. It walks every function
  in `fmis.pipeline.cli`, works out which names each one loads from module scope,
  and asserts every one exists. This catches the whole class of defect — a missed
  import, a renamed constant, a typo — in **any** CLI runner, not just the one
  that failed. A per-line test would only have covered the line already fixed.
* `TestTheResearchRunnersExecute` actually calls the runners with the expensive
  work stubbed, so the argument-construction path really runs.

Neither test asserts anything about research *results*. They assert the commands
can start.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import inspect
from pathlib import Path

import pytest

from fmis.pipeline import cli

_CLI_PATH = Path(inspect.getfile(cli))
_TREE = ast.parse(_CLI_PATH.read_text(encoding="utf-8"))


def _bound_names(node: ast.AST) -> set[str]:
    """Names a function binds locally: args, assignments, imports, targets."""
    bound: set[str] = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        args = node.args
        for group in (args.posonlyargs, args.args, args.kwonlyargs):
            bound.update(a.arg for a in group)
        if args.vararg:
            bound.add(args.vararg.arg)
        if args.kwarg:
            bound.add(args.kwarg.arg)

    body = node.body if not isinstance(node, ast.Lambda) else [node.body]
    for statement in body:
        for inner in ast.walk(statement):
            # Do not descend into a nested function's own bindings here; the
            # walker handles each scope separately and passes enclosing bindings
            # down explicitly.
            if isinstance(inner, ast.Name) and isinstance(inner.ctx, (ast.Store, ast.Del)):
                bound.add(inner.id)
            elif isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(inner.name)
            elif isinstance(inner, ast.Import):
                bound.update((a.asname or a.name).split(".")[0] for a in inner.names)
            elif isinstance(inner, ast.ImportFrom):
                bound.update(a.asname or a.name for a in inner.names)
            elif isinstance(inner, ast.ExceptHandler) and inner.name:
                bound.add(inner.name)
            elif isinstance(inner, (ast.Global, ast.Nonlocal)):
                bound.update(inner.names)
    return bound


def _functions(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _loaded_names(node: ast.AST) -> set[str]:
    """Every name loaded anywhere under ``node``, nested scopes included."""
    return {
        inner.id
        for inner in ast.walk(node)
        if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load)
    }


def _nested_scopes(func: ast.AST) -> list[ast.AST]:
    """Function and lambda scopes defined inside ``func`` (any depth)."""
    return [
        inner
        for inner in ast.walk(func)
        if inner is not func
        and isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
    ]


def _own_loads(func: ast.AST) -> set[str]:
    """Names loaded by ``func`` **itself**, excluding its nested scopes' bodies.

    Precision matters here. A looser analyser that simply walked everything under
    a function would report a nested closure's *parameter* — `announce(url, ...)`
    inside `_run_dashboard` is a real example — as an unresolved global. Widening
    the bound set to absorb such names would work, but it would also let a
    genuinely missing global slip through whenever its name happened to match
    some nested parameter. So each scope is analysed on its own loads instead.
    """
    nested = _nested_scopes(func)
    inside: set[int] = set()
    for scope in nested:
        for inner in ast.walk(scope):
            inside.add(id(inner))
    return {
        inner.id
        for inner in ast.walk(func)
        if isinstance(inner, ast.Name)
        and isinstance(inner.ctx, ast.Load)
        and id(inner) not in inside
    }


class TestEveryGlobalNameResolves:
    """The guard that would have caught the shipped defect."""

    def test_the_module_parses_and_holds_functions(self) -> None:
        """Guards the guard: an empty walk would pass everything vacuously."""
        assert len(list(_functions(_TREE))) > 20

    def test_every_name_loaded_by_every_cli_function_resolves(self) -> None:
        module_names = set(vars(cli))
        builtin_names = set(dir(builtins))
        # Names bound anywhere at module scope, including inside `if` blocks.
        for node in ast.walk(_TREE):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                module_names.add(node.id)

        unresolved: list[str] = []
        for func in _functions(_TREE):
            bound = _bound_names(func)
            # Enclosing scopes: any function whose body contains this one, so a
            # closure reading its parent's local is not reported as unresolved.
            for other in _functions(_TREE):
                if other is func:
                    continue
                if any(inner is func for inner in ast.walk(other)):
                    bound |= _bound_names(other)
            for name in _own_loads(func) - bound:
                if name not in module_names and name not in builtin_names:
                    unresolved.append(f"{func.name}: {name}")
        assert unresolved == [], (
            "these names are read at runtime but resolve to nothing — the exact "
            f"defect that shipped in `fmits research swing`: {unresolved}"
        )

    def test_the_specific_regression_that_shipped(self) -> None:
        """`DEFAULT_BACKTEST_LIMIT` is referenced by `_run_research`; it must be
        importable from the module, not merely spelled in it."""
        source = _CLI_PATH.read_text(encoding="utf-8")
        assert "DEFAULT_BACKTEST_LIMIT" in source
        assert vars(cli)["DEFAULT_BACKTEST_LIMIT"] == 250

    def test_the_guard_detects_a_reintroduced_missing_import(self) -> None:
        """A guard nobody has seen fail is a guard nobody should trust."""
        broken = ast.parse(
            "def runner(args):\n"
            "    return SOME_CONSTANT_THAT_WAS_NEVER_IMPORTED + args.x\n"
        )
        func = next(_functions(broken))
        missing = _own_loads(func) - _bound_names(func) - set(dir(builtins))
        assert "SOME_CONSTANT_THAT_WAS_NEVER_IMPORTED" in missing

    def test_the_guard_does_not_flag_a_nested_closures_parameter(self) -> None:
        """The false positive this analyser was tightened to avoid: a closure's
        own parameter belongs to the closure's scope, not the parent's."""
        source = ast.parse(
            "def outer(a):\n"
            "    def inner(url):\n"
            "        return url\n"
            "    return inner\n"
        )
        outer = next(_functions(source))
        assert "url" not in _own_loads(outer)
        assert "url" in _loaded_names(outer)


class TestTheResearchRunnersExecute:
    """The runners really run — argument construction included."""

    def _args(self, **overrides) -> argparse.Namespace:
        values = dict(
            area="swing", symbols=["BTCUSDT"], development=None, holdout=None,
            start="2024-01-01T00:00:00+00:00", end="2024-02-01T00:00:00+00:00",
            variant=None, window=180, costs="frictionless", robustness=False,
            save=None, limit=None, no_sensitivity=False,
        )
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_the_swing_runner_reaches_the_study_call(self, monkeypatch) -> None:
        seen: dict = {}

        def fake_study(symbols, **kwargs):
            seen.update(kwargs)
            seen["symbols"] = symbols
            raise cli.SwingLabError("stubbed before any network access")

        monkeypatch.setattr(cli, "run_lab_study", fake_study)
        assert cli._run_research(self._args()) == cli.EXIT_FAILURE
        # The defect was in building THESE arguments; reaching them is the proof.
        assert seen["symbols"] == ["BTCUSDT"]
        assert seen["limit"] == 250
        assert seen["evaluation_window_bars"] == 180

    def test_the_geometry_runner_reaches_the_experiment_call(self, monkeypatch) -> None:
        seen: dict = {}

        def fake_experiment(**kwargs):
            seen.update(kwargs)
            raise cli.SwingLabError("stubbed before any network access")

        monkeypatch.setattr(cli, "run_geometry_experiment", fake_experiment)
        code = cli._run_research(
            self._args(area="geometry", symbols=[],
                       development=["BTCUSDT"], holdout=["ETHUSDT"])
        )
        assert code == cli.EXIT_FAILURE
        assert seen["development_symbols"] == ["BTCUSDT"]
        assert seen["holdout_symbols"] == ["ETHUSDT"]
        assert seen["limit"] == 250

    def test_the_swing_runner_refuses_a_geometry_only_flag(self) -> None:
        assert cli._run_research(
            self._args(development=["BTCUSDT"])
        ) == cli.EXIT_FAILURE

    def test_the_swing_runner_refuses_an_empty_universe(self) -> None:
        assert cli._run_research(self._args(symbols=[])) == cli.EXIT_FAILURE

    def test_the_geometry_runner_refuses_positional_symbols(self) -> None:
        assert cli._run_research(
            self._args(area="geometry", symbols=["BTCUSDT"],
                       development=["BTCUSDT"], holdout=["ETHUSDT"])
        ) == cli.EXIT_FAILURE

    def test_the_geometry_runner_requires_both_samples(self) -> None:
        for dev, hold in ((["BTCUSDT"], None), (None, ["ETHUSDT"]), (None, None)):
            assert cli._run_research(
                self._args(area="geometry", symbols=[], development=dev, holdout=hold)
            ) == cli.EXIT_FAILURE

    def test_a_naive_start_instant_is_refused(self) -> None:
        assert cli._run_research(
            self._args(start="2024-01-01T00:00:00")
        ) == cli.EXIT_FAILURE


class TestNoBroadExceptionHidesTheNextDefect:
    """§11: a bare `except` around a runner would have swallowed this NameError."""

    def test_no_cli_function_catches_bare_exception_or_baseexception(self) -> None:
        offenders: list[str] = []
        for func in _functions(_TREE):
            for node in ast.walk(func):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                if node.type is None:
                    offenders.append(f"{func.name}: bare except")
                elif isinstance(node.type, ast.Name) and node.type.id in (
                    "Exception", "BaseException"
                ):
                    offenders.append(f"{func.name}: except {node.type.id}")
                elif isinstance(node.type, ast.Tuple):
                    for element in node.type.elts:
                        if isinstance(element, ast.Name) and element.id in (
                            "Exception", "BaseException"
                        ):
                            offenders.append(f"{func.name}: except {element.id}")
        assert offenders == [], offenders

    def test_no_cli_function_catches_name_error(self) -> None:
        """Catching `NameError` would turn this defect back into a silent exit."""
        for func in _functions(_TREE):
            for node in ast.walk(func):
                if isinstance(node, ast.ExceptHandler) and node.type is not None:
                    names = (
                        [node.type] if isinstance(node.type, ast.Name)
                        else list(getattr(node.type, "elts", []))
                    )
                    for element in names:
                        if isinstance(element, ast.Name):
                            assert element.id != "NameError", func.name
