"""Milestone BJ — the boundary `fmis.today` occupies, asserted rather than stated.

`fmis.today` is the first package in this repository that reads both halves of
FMITS. That is a real architectural claim and it needs guarding in both
directions:

* **Nothing below imports it.** No engine, no domain package, no store module,
  and no `fmis.pipeline` module except `cli.py` — the outermost edge, which is
  the same exception `fmis.archive` already holds.
* **The two halves still cannot see each other.** Widening the crossing to one
  new package must not widen it anywhere else, so the existing rule — no
  market-half package imports `fmis.persistence` — is re-asserted here against
  `fmis.today`'s own arrival.
* **This package holds no directional vocabulary of its own.** ADR-0028's
  boundary applies to it unchanged: it renders the side an engine or a record
  already decided, and names none.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pathlib
import pkgutil
import subprocess
import sys

import fmis
import fmis.today

SRC = pathlib.Path(fmis.__file__).parent
TODAY = "fmis.today"

#: Every package that reads a candle. Copied deliberately rather than imported
#: from the persistence guard, so adding a package to either list is a visible
#: edit in both places.
MARKET_HALF = (
    "fmis.data", "fmis.ingest", "fmis.providers", "fmis.features",
    "fmis.alignment", "fmis.relative_value", "fmis.series_context",
    "fmis.market_structure", "fmis.structural_trend", "fmis.structure_break",
    "fmis.change_of_character", "fmis.level_crossing", "fmis.market_regime",
    "fmis.evidence", "fmis.decision_support", "fmis.decision_context",
    "fmis.swing_setup", "fmis.workspace", "fmis.daily", "fmis.archive",
    "fmis.trading_context",
)

#: Every package the trading domain is made of.
DOMAIN = (
    "fmis.records", "fmis.provenance", "fmis.money", "fmis.versioning",
    "fmis.accounts", "fmis.analysis_record", "fmis.snapshotting",
    "fmis.proposal", "fmis.ledger", "fmis.positions", "fmis.portfolio",
    "fmis.risk", "fmis.journal",
)


def _modules_of(package_name: str) -> list[str]:
    package = importlib.import_module(package_name)
    return [package_name] + [
        module.name
        for module in pkgutil.iter_modules(package.__path__, prefix=f"{package_name}.")
    ]


def _imports_of(module_name: str) -> set[str]:
    module = importlib.import_module(module_name)
    source = pathlib.Path(inspect.getfile(module)).read_text(encoding="utf-8")
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _reaches(module_name: str, target: str) -> set[str]:
    return {
        name
        for name in _imports_of(module_name)
        if name == target or name.startswith(f"{target}.")
    }


# --------------------------------------------------------------------------
# Nothing below imports this package
# --------------------------------------------------------------------------


def test_no_engine_or_domain_package_imports_the_workspace() -> None:
    """*Or an engine's answer becomes a function of the owner's position.*"""
    offenders: dict[str, set[str]] = {}
    for package_name in MARKET_HALF + DOMAIN + ("fmis.persistence",):
        for module_name in _modules_of(package_name):
            reached = _reaches(module_name, TODAY)
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_only_the_cli_imports_the_workspace_from_the_pipeline() -> None:
    """The same exception `fmis.archive` already holds, for the same reason:
    `cli.py` is the outermost edge and composes, it does not compute."""
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of("fmis.pipeline"):
        if module_name == "fmis.pipeline.cli":
            continue
        reached = _reaches(module_name, TODAY)
        if reached:
            offenders[module_name] = reached
    assert offenders == {}
    assert _reaches("fmis.pipeline.cli", TODAY)


def test_the_cli_does_not_import_the_store_directly() -> None:
    """`fmis.pipeline` is a market-half package and may not reach the store.

    Every store failure the CLI reports arrives as a `StoreUnreadableError`
    raised by this package, which is why that exception exists at all.
    """
    assert _reaches("fmis.pipeline.cli", "fmis.persistence") == set()


def test_importing_the_pipeline_does_not_pull_in_the_workspace_layer() -> None:
    """A cold `import fmis.pipeline` must not load the store, the domain or this
    package. Asserted in a subprocess, because this test session has already
    imported all three."""
    probe = (
        "import fmis.pipeline, sys;"
        "print(int(any(n.startswith('fmis.today') for n in sys.modules)))"
    )
    finished = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert finished.stdout.strip() == "0"


# --------------------------------------------------------------------------
# The crossing is exactly one package wide
# --------------------------------------------------------------------------


def test_no_market_half_package_imports_the_store() -> None:
    """Re-asserted here so this milestone's own widening cannot be mistaken for
    permission to widen it again elsewhere."""
    offenders: dict[str, set[str]] = {}
    for package_name in MARKET_HALF + ("fmis.pipeline",):
        for module_name in _modules_of(package_name):
            reached = _reaches(module_name, "fmis.persistence")
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_this_package_reaches_both_halves_and_that_is_the_point() -> None:
    reached: set[str] = set()
    for module_name in _modules_of(TODAY):
        reached |= _imports_of(module_name)
    assert any(name.startswith("fmis.persistence") for name in reached)
    assert any(name.startswith("fmis.swing_setup") for name in reached)


def test_this_package_writes_nothing() -> None:
    """A read-only surface, enforced rather than promised.

    None of the store's write verbs appears anywhere in this package. A page
    that could write would be a page that changes what it is reporting on.
    """
    forbidden = {
        "publish", "append_event", "append_lines", "atomic_write",
        "revise", "admit", "rebuild_index",
    }
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(TODAY):
        source = pathlib.Path(
            inspect.getfile(importlib.import_module(module_name))
        ).read_text(encoding="utf-8")
        called = {
            node.func.attr
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        } | {
            node.func.id
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        found = called & forbidden
        if found:
            offenders[module_name] = found
    assert offenders == {}


def test_the_only_create_call_is_absent_too() -> None:
    """`create` is the store's write verb on every one of the nine repositories."""
    for module_name in _modules_of(TODAY):
        source = pathlib.Path(
            inspect.getfile(importlib.import_module(module_name))
        ).read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"create", "update", "replace"}
            ):
                raise AssertionError(f"{module_name} calls {node.func.attr}")


# --------------------------------------------------------------------------
# No clock, no cycles, no state
# --------------------------------------------------------------------------


def test_nothing_in_this_package_reads_a_clock() -> None:
    """Every instant is supplied by the outer boundary, so two runs over the
    same inputs are identical — the property that makes the page reproducible."""
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(TODAY):
        source = pathlib.Path(
            inspect.getfile(importlib.import_module(module_name))
        ).read_text(encoding="utf-8")
        found = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Attribute) and node.attr in {
                "now", "utcnow", "today", "time", "monotonic"
            }:
                found.add(node.attr)
        if found:
            offenders[module_name] = found
    assert offenders == {}


def test_the_package_holds_no_module_level_mutable_state() -> None:
    """`__all__` is exempt: it is a list by the language's own convention, and
    every package in this repository declares one."""
    for module_name in _modules_of(TODAY):
        source = pathlib.Path(
            inspect.getfile(importlib.import_module(module_name))
        ).read_text(encoding="utf-8")
        for node in ast.parse(source).body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {t.id for t in targets if isinstance(t, ast.Name)}
            if names == {"__all__"}:
                continue
            if isinstance(node.value, (ast.List, ast.Dict, ast.Set)):
                raise AssertionError(
                    f"{module_name} holds mutable module state: {sorted(names)}"
                )


def test_no_module_in_this_package_participates_in_an_import_cycle() -> None:
    """Pins the layering order so an intra-package import must point backwards."""
    order = [
        "fmis.today.evidence",
        "fmis.today.models",
        "fmis.today.warnings",
        "fmis.today.attention",
        "fmis.today.sections",
        "fmis.today.render",
        "fmis.today.builder",
    ]
    position = {name: index for index, name in enumerate(order)}
    assert set(order) | {TODAY} == set(_modules_of(TODAY))
    for module_name, index in position.items():
        for imported in _imports_of(module_name):
            if imported in position:
                assert position[imported] < index, (module_name, imported)


def test_the_package_adds_no_runtime_dependency() -> None:
    permitted = {
        "__future__", "ast", "collections.abc", "dataclasses", "datetime",
        "enum", "pathlib", "textwrap", "types", "typing",
    }
    for module_name in _modules_of(TODAY):
        for imported in _imports_of(module_name):
            if imported.startswith("fmis"):
                continue
            assert imported in permitted, (module_name, imported)


# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------


def test_this_package_holds_no_directional_vocabulary_of_its_own() -> None:
    """ADR-0028's boundary, applied unchanged.

    The page prints a side by reading `Direction.value` or
    `PositionDirection.value` at runtime. Naming a member, or writing the word
    as a literal, would make this package a second place the vocabulary lives.
    """
    banned = {"long", "short", "buy", "sell", "bullish", "bearish"}
    offenders: list[tuple[str, str]] = []
    for module_name in _modules_of(TODAY):
        source = pathlib.Path(
            inspect.getfile(importlib.import_module(module_name))
        ).read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            token = None
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                token = node.name
            elif isinstance(node, ast.Name):
                token = node.id
            elif isinstance(node, ast.Attribute):
                token = node.attr
            elif isinstance(node, ast.arg):
                token = node.arg
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                token = node.value
            if token is not None and token.lower() in banned:
                offenders.append((module_name, token))
    assert offenders == []


def test_the_repository_wide_directional_guard_already_covers_this_package() -> None:
    """`fmis.today` is not on any exemption list, so the existing guard applies
    to it with no edit. Asserted so a future exemption is a deliberate act."""
    from tests import test_directional_vocabulary_boundary as guard

    exempt = {path.name for path in guard._TRADE_DOMAIN_PERMITTED_DIRS}
    assert "today" not in exempt
    assert guard._PERMITTED_DIR.name != "today"
    covered = {path.parent.name for path in guard._covered_files()}
    assert "today" in covered


def test_every_public_name_is_importable_from_the_package_root() -> None:
    for name in fmis.today.__all__:
        assert hasattr(fmis.today, name), name


def test_the_package_introduces_no_export_collision() -> None:
    """Checked against every other package's `__all__`, repository-wide."""
    ours = set(fmis.today.__all__)
    for package_name in MARKET_HALF + DOMAIN + ("fmis.persistence",):
        other = getattr(importlib.import_module(package_name), "__all__", ())
        shared = ours & set(other)
        assert shared == set(), (package_name, sorted(shared))
