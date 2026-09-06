"""Milestone BS — the boundary `fmis.swing_workspace` occupies, asserted.

`fmis.swing_workspace` is the **second** package in this repository that reads
both halves of FMITS, and the first one that reads them *through* another such
package rather than directly. That is a real architectural claim and it needs
guarding in every direction the first one is guarded in:

* **Nothing below imports it.** No engine, no domain package, no store module,
  no `fmis.today` module, and no `fmis.pipeline` module except `cli.py` — the
  outermost edge, the same exception `fmis.archive` and `fmis.today` hold.
* **It reaches the store only through `fmis.today`.** Widening the crossing to a
  second package must not widen it anywhere else, so the existing rule — no
  market-half package imports `fmis.persistence` — is re-asserted here, and this
  package is asserted to hold no store import of its own.
* **It writes nothing**, computes no market quantity and reads no clock.
* **It holds no directional vocabulary of its own.** ADR-0028's boundary applies
  unchanged: it renders the side an engine already decided, and names none.
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
import fmis.swing_workspace

SRC = pathlib.Path(fmis.__file__).parent
WORKSPACE = "fmis.swing_workspace"
TODAY = "fmis.today"

#: Every package that reads a candle. Copied deliberately rather than imported
#: from `test_today_architecture`, so adding a package to either list is a
#: visible edit in both places — the discipline that file's own comment records.
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

#: The application-layer packages this one is permitted to compose. Named one by
#: one: a package appearing here later is a deliberate act with a justification,
#: not a drift.
PERMITTED = (
    "fmis.today",
    "fmis.setup_evidence",
    "fmis.setup_observation",
    "fmis.trade_capture",
    "fmis.position_sizing",
    # The owner's declared risk policy, and the only producer of a `RiskBudget`
    # in `src/`. Added deliberately: this page attaches a `TradePlan` to every
    # symbol decision, and the alternative was for this package to build the
    # budget and the sizing policy itself — which would put the specification's
    # per-trade ceiling in a surface, and put sizing arithmetic in a projection.
    "fmis.risk_policy",
    "fmis.swing_setup",
    "fmis.money",
    "fmis.provenance",
)


def _modules_of(package_name: str) -> list[str]:
    package = importlib.import_module(package_name)
    return [package_name] + [
        module.name
        for module in pkgutil.iter_modules(package.__path__, prefix=f"{package_name}.")
    ]


def _source_of(module_name: str) -> str:
    module = importlib.import_module(module_name)
    return pathlib.Path(inspect.getfile(module)).read_text(encoding="utf-8")


def _imports_of(module_name: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(_source_of(module_name))):
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


def test_no_engine_or_domain_package_imports_this_one() -> None:
    """*Or an engine's answer becomes a function of the owner's position.*"""
    offenders: dict[str, set[str]] = {}
    for package_name in MARKET_HALF + DOMAIN + ("fmis.persistence", TODAY):
        for module_name in _modules_of(package_name):
            reached = _reaches(module_name, WORKSPACE)
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_the_day_page_does_not_import_the_workspace_that_is_built_from_it() -> None:
    """The dependency runs one way. A cycle here would make the seam useless."""
    for module_name in _modules_of(TODAY):
        assert _reaches(module_name, WORKSPACE) == set()


def test_only_the_cli_imports_this_package_from_the_pipeline() -> None:
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of("fmis.pipeline"):
        if module_name == "fmis.pipeline.cli":
            continue
        reached = _reaches(module_name, WORKSPACE)
        if reached:
            offenders[module_name] = reached
    assert offenders == {}
    assert _reaches("fmis.pipeline.cli", WORKSPACE)


def test_importing_the_pipeline_does_not_pull_in_this_layer() -> None:
    """A cold `import fmis.pipeline` must not load the store, the domain or this
    package. Asserted in a subprocess, because this session has imported all."""
    probe = (
        "import fmis.pipeline, sys;"
        "print(int(any(n.startswith('fmis.swing_workspace') for n in sys.modules)))"
    )
    finished = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert finished.stdout.strip() == "0"


# --------------------------------------------------------------------------
# The crossing is not widened
# --------------------------------------------------------------------------


def test_this_package_opens_no_store_of_its_own() -> None:
    """It reads both halves **through `fmis.today`**, which is the whole point of
    building on that package rather than beside it."""
    for module_name in _modules_of(WORKSPACE):
        assert _reaches(module_name, "fmis.persistence") == set()
        assert _reaches(module_name, "fmis.archive") == set()


def test_no_market_half_package_imports_the_store() -> None:
    """Re-asserted here so this milestone's own arrival cannot be mistaken for
    permission to widen the crossing again elsewhere."""
    offenders: dict[str, set[str]] = {}
    for package_name in MARKET_HALF + ("fmis.pipeline",):
        for module_name in _modules_of(package_name):
            reached = _reaches(module_name, "fmis.persistence")
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_every_package_this_one_imports_is_on_the_permitted_list() -> None:
    reached: set[str] = set()
    for module_name in _modules_of(WORKSPACE):
        reached |= {
            name
            for name in _imports_of(module_name)
            if name.startswith("fmis") and not name.startswith(WORKSPACE)
        }
    unexpected = {
        name for name in reached if not name.startswith(PERMITTED) and name != "fmis"
    }
    assert unexpected == set()


def test_this_package_writes_nothing() -> None:
    """A read-only surface, enforced rather than promised.

    **The store's write verbs are not the whole of it.** A release-gate mutation
    injected a plain `pathlib.Path(...).write_text(...)` into the composition
    root and survived, because a guard listing only repository verbs cannot see
    a raw filesystem write. *Writes nothing* means the filesystem, so the
    ordinary write verbs are listed here too.
    """
    forbidden = {
        "publish", "append_event", "append_lines", "atomic_write",
        "revise", "admit", "rebuild_index", "create", "update", "replace",
        "write_text", "write_bytes", "writelines", "mkdir", "makedirs",
        "unlink", "rmtree", "remove", "rename", "touch", "open",
    }
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(WORKSPACE):
        tree = ast.parse(_source_of(module_name))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        } | {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        found = called & forbidden
        if found:
            offenders[module_name] = found
    assert offenders == {}


def test_a_live_run_leaves_the_store_byte_identical(tmp_path) -> None:
    """The read-only claim, measured rather than asserted from the source."""
    import hashlib

    from tests.swing_workspace_helpers import assessment, result, workspace_of

    root = tmp_path / "store"
    root.mkdir()
    (root / "marker.jsonl").write_text("{}\n", encoding="utf-8")

    def digest() -> str:
        sha = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            sha.update(path.name.encode())
            if path.is_file():
                sha.update(path.read_bytes())
        return sha.hexdigest()

    before = digest()
    workspace_of(result(assessment()))
    assert digest() == before


# --------------------------------------------------------------------------
# No clock, no cycles, no state, no arithmetic on money
# --------------------------------------------------------------------------


def test_nothing_in_this_package_reads_a_clock() -> None:
    """Every instant is supplied by the outer boundary, so two runs over the
    same inputs are identical — the property that makes the page reproducible."""
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(WORKSPACE):
        found = {
            node.attr
            for node in ast.walk(ast.parse(_source_of(module_name)))
            if isinstance(node, ast.Attribute)
            and node.attr in {"now", "utcnow", "today", "monotonic"}
        }
        if found:
            offenders[module_name] = found
    assert offenders == {}


def test_no_module_in_this_package_participates_in_an_import_cycle() -> None:
    """Pins the layering order so an intra-package import must point backwards."""
    order = [
        "fmis.swing_workspace.models",
        "fmis.swing_workspace.ranking",
        "fmis.swing_workspace.sections",
        "fmis.swing_workspace.render",
        "fmis.swing_workspace.builder",
    ]
    position = {name: index for index, name in enumerate(order)}
    assert set(order) | {WORKSPACE} == set(_modules_of(WORKSPACE))
    for module_name, index in position.items():
        for imported in _imports_of(module_name):
            if imported in position:
                assert position[imported] < index, (module_name, imported)


def test_the_package_holds_no_module_level_mutable_state() -> None:
    """`__all__` is exempt: it is a list by the language's own convention."""
    for module_name in _modules_of(WORKSPACE):
        for node in ast.parse(_source_of(module_name)).body:
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


def test_the_package_adds_no_runtime_dependency() -> None:
    permitted = {
        "__future__", "ast", "collections.abc", "dataclasses", "datetime",
        "enum", "pathlib", "textwrap", "types", "typing",
    }
    for module_name in _modules_of(WORKSPACE):
        for imported in _imports_of(module_name):
            if imported.startswith("fmis"):
                continue
            assert imported in permitted, (module_name, imported)


def test_no_module_divides_subtracts_or_scales_anything() -> None:
    """*Compose, never compute.* A ratio computed here would be a second answer
    to a question an engine below already answered.

    Three operators are permitted and none is arithmetic on a quantity. `|` is
    the type union in an annotation — `str | NotAvailable`; `&` is the set
    intersection that finds a symbol placed in two sections; `+` concatenates
    strings, tuples and the one index this package derives (a 1-based position
    from a 0-based one). `*` is permitted **in the renderer only**, where it
    repeats a character to draw a rule and pads an indent; anywhere else it would
    be a scale factor, which is the thing this guard exists to forbid.
    """
    offenders: list[tuple[str, str]] = []
    for module_name in _modules_of(WORKSPACE):
        allowed: tuple[type, ...] = (ast.Add, ast.BitOr, ast.BitAnd)
        if module_name.endswith(".render"):
            allowed = (ast.Add, ast.BitOr, ast.BitAnd, ast.Mult)
        for node in ast.walk(ast.parse(_source_of(module_name))):
            if isinstance(node, (ast.BinOp, ast.AugAssign)) and not isinstance(
                node.op, allowed
            ):
                offenders.append((module_name, type(node.op).__name__))
    assert offenders == []


def test_the_renderer_only_multiplies_strings() -> None:
    """The one permitted `*` above, pinned to what it actually does."""
    source = _source_of("fmis.swing_workspace.render")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            left = node.left
            assert isinstance(left, (ast.Name, ast.Constant)), ast.dump(node)
            if isinstance(left, ast.Constant):
                assert isinstance(left.value, str), left.value


def test_no_module_holds_a_floating_point_literal() -> None:
    """Every number this page shows was formatted from a value it was handed."""
    for module_name in _modules_of(WORKSPACE):
        for node in ast.walk(ast.parse(_source_of(module_name))):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                raise AssertionError(f"{module_name} holds the literal {node.value}")


# --------------------------------------------------------------------------
# Vocabulary and exports
# --------------------------------------------------------------------------


def test_this_package_holds_no_directional_vocabulary_of_its_own() -> None:
    """ADR-0028's boundary, applied unchanged. The page prints a side by reading
    `Direction.value` at runtime; naming a member, or writing the word as a
    literal, would make this package a second place the vocabulary lives."""
    banned = {"long", "short", "buy", "sell", "bullish", "bearish"}
    offenders: list[tuple[str, str]] = []
    for module_name in _modules_of(WORKSPACE):
        for node in ast.walk(ast.parse(_source_of(module_name))):
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
    """This package is on no exemption list, so the existing guard applies to it
    with no edit. Asserted so a future exemption is a deliberate act."""
    from tests import test_directional_vocabulary_boundary as guard

    exempt = {path.name for path in guard._TRADE_DOMAIN_PERMITTED_DIRS}
    assert "swing_workspace" not in exempt
    assert guard._PERMITTED_DIR.name != "swing_workspace"
    covered = {path.parent.name for path in guard._covered_files()}
    assert "swing_workspace" in covered


def test_every_public_name_is_importable_from_the_package_root() -> None:
    for name in fmis.swing_workspace.__all__:
        assert hasattr(fmis.swing_workspace, name), name


def test_the_package_introduces_no_export_collision() -> None:
    """Checked against every other package's `__all__`, repository-wide."""
    ours = set(fmis.swing_workspace.__all__)
    root = pathlib.Path(fmis.__file__).parent
    for path in sorted(root.iterdir()):
        if not path.is_dir() or not (path / "__init__.py").exists():
            continue
        name = f"fmis.{path.name}"
        if name == WORKSPACE:
            continue
        other = set(getattr(importlib.import_module(name), "__all__", ()))
        assert ours & other == set(), (name, sorted(ours & other))


def test_the_command_is_registered_with_a_runner() -> None:
    from fmis.pipeline.cli import COMMANDS

    command = next(entry for entry in COMMANDS if entry.name == "workspace")
    assert callable(command.run) and callable(command.configure)
