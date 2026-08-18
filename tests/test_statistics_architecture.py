"""Boundary guards for `fmis.statistics`.

These do not exercise behaviour. They assert the rules the milestone rests on,
in the only form that survives a refactor: an executable check over the source
tree.

**The package writes nothing, and that is architectural.** `AP` §25.2 classes
cohort statistics as `Aggregate` — *recomputable, disposable*. So the strictest
test here is that no store write verb appears anywhere in the package, and that
it registers no `RecordKind` and no repository. A statistics engine that could
write would be a second, drifting copy of the records it summarizes.

**It fetches no candle, ever.** A statistic is computed from recorded history;
re-deriving an excursion from today's kline history would make a past figure
depend on what the venue still serves — the exact failure `AP` §25.3 froze
MAE/MFE to prevent. Asserted as a set, so a second module reaching for a candle
fails here.

**One module opens the store.** `fmis.statistics.collect` and nothing else, so
the folds above it are pure and can be exercised with no filesystem at all.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest

import fmis

PACKAGE = "fmis.statistics"
SOURCE_ROOT = Path(fmis.__file__).parent

#: Every package that reads a candle, reaches a venue or renders a chart.
#: Copied deliberately rather than imported, so adding one is a visible edit in
#: each guard that cares — the convention `tests/test_paper_architecture.py`
#: established and this file follows.
MARKET_HALF = frozenset(
    {
        "fmis.data",
        "fmis.ingest",
        "fmis.providers",
        "fmis.features",
        "fmis.alignment",
        "fmis.relative_value",
        "fmis.series_context",
        "fmis.market_structure",
        "fmis.structural_trend",
        "fmis.structure_break",
        "fmis.change_of_character",
        "fmis.level_crossing",
        "fmis.market_regime",
        "fmis.evidence",
        "fmis.decision_support",
        "fmis.decision_context",
        "fmis.swing_setup",
        "fmis.workspace",
        "fmis.daily",
        "fmis.trading_context",
        "fmis.pipeline",
        "fmis.today",
        "fmis.marks",
    }
)

#: The pure tier: exact arithmetic over values, no store, no clock, no candle.
PURE_MODULES = [
    f"{PACKAGE}.models",
    f"{PACKAGE}.sampling",
    f"{PACKAGE}.general",
    f"{PACKAGE}.performance",
    f"{PACKAGE}.risk",
    f"{PACKAGE}.quality",
    f"{PACKAGE}.distribution",
    f"{PACKAGE}.equity",
    f"{PACKAGE}.drawdown",
    f"{PACKAGE}.breakdown",
]

#: The one module that opens a store.
STORE_MODULE = f"{PACKAGE}.collect"

#: The surfaces: composition, the text boundary, the page.
SURFACE_MODULES = [f"{PACKAGE}.report", f"{PACKAGE}.inputs", f"{PACKAGE}.render"]


def _modules_of(package_name: str) -> list[str]:
    package = importlib.import_module(package_name)
    return [package_name] + [
        module.name
        for module in pkgutil.iter_modules(package.__path__, prefix=f"{package_name}.")
    ]


def _source_of(module_name: str) -> str:
    return Path(inspect.getfile(importlib.import_module(module_name))).read_text(
        encoding="utf-8"
    )


def _imports_of(module_name: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(_source_of(module_name))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _calls_in(module_name: str) -> set[str]:
    called: set[str] = set()
    for node in ast.walk(ast.parse(_source_of(module_name))):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
            elif isinstance(node.func, ast.Name):
                called.add(node.func.id)
    return called


def _names_used(module_name: str) -> set[str]:
    used: set[str] = set()
    for node in ast.walk(ast.parse(_source_of(module_name))):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
    return used


# --------------------------------------------------------------------------
# The tiers are pinned
# --------------------------------------------------------------------------


def test_the_package_holds_exactly_the_modules_the_tiers_name() -> None:
    """A new module is a deliberate edit here rather than an unguarded one."""
    declared = set(PURE_MODULES + [STORE_MODULE] + SURFACE_MODULES) | {PACKAGE}
    assert set(_modules_of(PACKAGE)) == declared


def test_every_module_has_a_docstring() -> None:
    for module_name in _modules_of(PACKAGE):
        assert importlib.import_module(module_name).__doc__, module_name


# --------------------------------------------------------------------------
# It writes nothing — `AP` §25.2
# --------------------------------------------------------------------------


def test_no_module_in_this_package_calls_a_store_write_verb() -> None:
    """The whole architectural claim of the milestone, as one check.

    `replace` is in the list and is why `fmis.today.sections` builds a day
    boundary explicitly rather than calling `datetime.replace`: a guard that had
    to know which object a name was called on would be a guard with an
    exception in it.
    """
    forbidden = {
        "create", "update", "replace", "publish", "append_event", "append_lines",
        "append_amendment", "atomic_write", "revise", "admit", "rebuild_index",
        "record_trade", "close_trade", "append_note", "record_plan",
    }
    offenders = {
        module_name: found
        for module_name in _modules_of(PACKAGE)
        if (found := _calls_in(module_name) & forbidden)
    }
    assert offenders == {}


def test_this_package_registers_no_record_kind_and_no_repository() -> None:
    """`AP` §25.2 classes these as disposable aggregates. A repository here
    would be the second answer to *"what did my trading do"*."""
    from fmis.persistence import SPECS, TradingStore

    for spec in SPECS.values():
        assert "statistics" not in str(spec.kind.value).lower()
    store = TradingStore.__init__
    assert "statistics" not in inspect.getsource(store)


def test_no_module_defines_a_payload_decoder() -> None:
    """`to_payload` without `from_payload` is the shape of an export. The pair
    is the shape of a stored record."""
    for module_name in _modules_of(PACKAGE):
        assert "def from_payload" not in _source_of(module_name), module_name


# --------------------------------------------------------------------------
# It fetches no candle and reaches no venue
# --------------------------------------------------------------------------


def test_no_module_in_this_package_imports_a_market_half_package() -> None:
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(PACKAGE):
        reached = {
            name
            for name in _imports_of(module_name)
            if any(name == half or name.startswith(f"{half}.") for half in MARKET_HALF)
        }
        if reached:
            offenders[module_name] = reached
    assert offenders == {}


def test_no_module_names_a_candle_a_bar_or_a_provider() -> None:
    """Stronger than the import check: it catches a candle arriving as a
    parameter from a caller that had one."""
    forbidden = {"Candle", "CandleSeries", "PriceBar", "BinanceClient", "fetch_candles"}
    for module_name in _modules_of(PACKAGE):
        assert not (_names_used(module_name) & forbidden), module_name


def test_the_package_reaches_no_venue_specific_module() -> None:
    for module_name in _modules_of(PACKAGE):
        for name in _imports_of(module_name):
            assert not name.startswith("fmis.providers"), module_name


# --------------------------------------------------------------------------
# One module opens the store
# --------------------------------------------------------------------------


def test_exactly_one_module_imports_the_store() -> None:
    """So every fold above it is pure and needs no filesystem to exercise."""
    reaching = {
        module_name
        for module_name in _modules_of(PACKAGE)
        if any(
            name == "fmis.persistence" or name.startswith("fmis.persistence.")
            for name in _imports_of(module_name)
        )
    }
    assert reaching == {STORE_MODULE, f"{PACKAGE}.report", f"{PACKAGE}.inputs"}


@pytest.mark.parametrize("module_name", PURE_MODULES)
def test_no_pure_module_touches_a_store_a_clock_or_a_path(module_name: str) -> None:
    reached = _imports_of(module_name)
    assert not any(name.startswith("fmis.persistence") for name in reached), module_name
    assert "pathlib" not in reached, module_name
    used = _names_used(module_name)
    for forbidden in ("TradingStore", "now", "utcnow", "today"):
        assert forbidden not in used, f"{module_name}: {forbidden}"


def test_nothing_in_this_package_reads_a_clock() -> None:
    """Every instant arrives as a parameter from `fmis.pipeline.cli`, the one
    place in the repository that takes the time."""
    for module_name in _modules_of(PACKAGE):
        used = _names_used(module_name)
        assert "now" not in used, module_name
        assert "utcnow" not in used, module_name


# --------------------------------------------------------------------------
# The dependency surface
# --------------------------------------------------------------------------


def test_the_package_introduces_no_runtime_dependency() -> None:
    allowed_roots = {
        "__future__", "collections", "dataclasses", "datetime", "decimal",
        "enum", "pathlib", "textwrap", "types", "typing", "fmis",
    }
    for module_name in _modules_of(PACKAGE):
        for name in _imports_of(module_name):
            assert name.split(".")[0] in allowed_roots, f"{module_name}: {name}"


def test_the_owner_half_packages_it_reads_are_named_as_a_set() -> None:
    """Pinned so that reaching for a new subsystem is a visible edit."""
    reached: set[str] = set()
    for module_name in _modules_of(PACKAGE):
        reached |= {
            name for name in _imports_of(module_name) if name.startswith("fmis.")
        }
    outside = {name for name in reached if not name.startswith(f"{PACKAGE}.")}
    assert outside == {
        "fmis.accounts",
        "fmis.money",
        "fmis.paper",
        "fmis.persistence",
        "fmis.plan",
        "fmis.portfolio_risk",
        "fmis.provenance",
        "fmis.records",
        "fmis.risk",
        "fmis.snapshotting",
        "fmis.trade_capture",
    }


def test_there_are_no_import_cycles_inside_the_package() -> None:
    edges = {
        module_name: {
            name for name in _imports_of(module_name) if name.startswith(f"{PACKAGE}.")
        }
        for module_name in _modules_of(PACKAGE)
    }
    seen: set[str] = set()
    stack: set[str] = set()

    def walk(node: str) -> None:
        if node in stack:
            raise AssertionError(f"import cycle through {node}")
        if node in seen:
            return
        stack.add(node)
        for edge in edges.get(node, set()):
            walk(edge)
        stack.discard(node)
        seen.add(node)

    for module_name in edges:
        walk(module_name)


def test_no_owner_half_package_imports_the_statistics_engine() -> None:
    """The engine reads them; none of them may read it, or a fold would depend
    on a summary of itself."""
    consumers = (
        "fmis.accounts", "fmis.money", "fmis.records", "fmis.provenance",
        "fmis.ledger", "fmis.positions", "fmis.plan", "fmis.portfolio",
        "fmis.portfolio_risk", "fmis.journal", "fmis.risk", "fmis.snapshotting",
        "fmis.persistence", "fmis.trade_capture", "fmis.paper",
        "fmis.trade_lifecycle", "fmis.valuation", "fmis.position_sizing",
    )
    offenders: dict[str, set[str]] = {}
    for package_name in consumers:
        for module_name in _modules_of(package_name):
            reached = {
                name for name in _imports_of(module_name) if name.startswith(PACKAGE)
            }
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_only_the_named_consumers_reach_the_statistics_engine() -> None:
    """Two: the CLI, which is the surface, and the workspace, which puts one
    section of it on the day's page."""
    reaching = {
        module_name
        for package_name in ("fmis.pipeline", "fmis.today")
        for module_name in _modules_of(package_name)
        if any(name.startswith(PACKAGE) for name in _imports_of(module_name))
    }
    assert reaching == {
        "fmis.pipeline.cli",
        "fmis.today.builder",
        "fmis.today.sections",
    }


def test_a_cold_import_of_the_pipeline_does_not_load_this_package() -> None:
    """`fmits facts` must not pay for a subsystem it never uses."""
    import subprocess
    import sys

    code = (
        "import fmis.pipeline, sys; "
        f"print(any(name.startswith({PACKAGE!r}) for name in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False"


# --------------------------------------------------------------------------
# Vocabulary and exports
# --------------------------------------------------------------------------


def test_this_package_holds_no_directional_vocabulary_of_its_own() -> None:
    """BP takes **no** ADR-0028 exemption. The per-direction breakdown groups on
    `TradeDirection.value` at runtime, so no side is ever spelled in the source.
    """
    banned = {"long", "short", "buy", "sell", "bullish", "bearish"}
    for module_name in _modules_of(PACKAGE):
        tree = ast.parse(_source_of(module_name))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                assert node.name.lower() not in banned, module_name
            elif isinstance(node, ast.Name):
                assert node.id.lower() not in banned, module_name
            elif isinstance(node, ast.Attribute):
                assert node.attr.lower() not in banned, module_name
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value.lower() not in banned, module_name


def test_the_repository_wide_directional_guard_already_covers_this_package() -> None:
    """Belt and braces: the repository-wide scan must not have an exemption for
    this directory."""
    guard = (Path(__file__).parent / "test_directional_vocabulary_boundary.py").read_text(
        encoding="utf-8"
    )
    assert '"statistics"' not in guard
    assert 'SRC / "statistics"' not in guard


def test_the_default_regime_dimension_is_one_the_regime_engine_emits() -> None:
    """The copy-and-guard this package uses everywhere it may not import.

    `fmis.statistics` must not reach the market half, so the default dimension
    name is a literal — and a literal naming a dimension nothing produces makes
    the whole per-regime breakdown `UNCLASSIFIED` without failing anything. The
    first draft said `"trend"`, which that engine has never emitted. This test
    is the mechanism that keeps the copy honest; the test may import both sides
    because `tests/` is outside the boundary it is checking.
    """
    from fmis.market_regime import RegimeDimensionName
    from fmis.statistics import DEFAULT_REGIME_DIMENSION

    emitted = {dimension.value for dimension in RegimeDimensionName}
    assert DEFAULT_REGIME_DIMENSION in emitted, sorted(emitted)


def test_every_public_name_is_importable_from_the_package_root() -> None:
    package = importlib.import_module(PACKAGE)
    for name in package.__all__:
        assert hasattr(package, name), name


def test_no_submodule_shares_a_name_with_an_exported_object() -> None:
    package = importlib.import_module(PACKAGE)
    submodules = {module.name for module in pkgutil.iter_modules(package.__path__)}
    assert submodules & set(package.__all__) == set()


def test_this_package_introduces_no_export_collision() -> None:
    """The repository's zero-collision invariant, re-asserted after BP."""
    seen: dict[str, str] = {}
    collisions: dict[str, list[str]] = {}
    for module in pkgutil.walk_packages(fmis.__path__, "fmis."):
        if not module.ispkg:
            continue
        package = importlib.import_module(module.name)
        for name in getattr(package, "__all__", []):
            if name in seen and seen[name] != module.name:
                collisions.setdefault(name, [seen[name]]).append(module.name)
            else:
                seen[name] = module.name
    assert collisions == {}


def test_the_renderer_computes_nothing_it_was_not_given() -> None:
    """A renderer that computed one number would become the second place that
    number is defined."""
    used = _names_used(f"{PACKAGE}.render")
    for forbidden in (
        "build_report", "collect_trades", "equity_curve", "drawdown_curve",
        "performance_statistics", "general_statistics", "quality_statistics",
        "risk_statistics", "breakdown_set", "histogram_of", "TradingStore",
    ):
        assert forbidden not in used, forbidden
