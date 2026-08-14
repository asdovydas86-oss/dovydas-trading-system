"""Milestone BM — the boundaries `fmis.marks` and `fmis.valuation` occupy.

These do not exercise behaviour. They assert the milestone's own architectural
claims in the only form that survives a refactor: an executable check over the
source tree.

Four claims, and each has a test below.

1. **Nothing may depend directly on an exchange.** `fmis.marks` names no
   provider and imports none; `fmis.valuation` names none either. The provider is
   reached through `fmis.pipeline.prices`, where every other provider call in
   this repository already lives.
2. **No adapter lives in the owner domain.** `fmis.portfolio_risk`'s dependency
   surface is unchanged and its venue-agnostic guard still passes: it receives a
   `Mapping[str, MarkQuote]` and knows nothing about where one came from.
3. **The conversion is one module wide.** `fmis.valuation.marking` is the only
   place in the repository that turns a price into a `MarkQuote`, asserted by
   checking who may *construct* one rather than who may import what.
4. **Nothing below imports the bridge.** No engine, no domain package and no
   store module reaches `fmis.valuation`, in either direction.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import subprocess
import sys
from pathlib import Path

import fmis

MARKS = "fmis.marks"
VALUATION = "fmis.valuation"

#: Every package that reads a candle, reaches a venue or renders a chart. Copied
#: deliberately rather than imported, so adding one is a visible edit in each
#: guard that cares — the convention `tests/test_portfolio_risk_architecture.py`
#: established and this file follows. `fmis.marks` is on it: it reads candles.
MARKET_HALF = frozenset({
    "fmis.data", "fmis.ingest", "fmis.providers", "fmis.features",
    "fmis.alignment", "fmis.relative_value", "fmis.series_context",
    "fmis.market_structure", "fmis.structural_trend", "fmis.structure_break",
    "fmis.change_of_character", "fmis.level_crossing", "fmis.market_regime",
    "fmis.evidence", "fmis.decision_support", "fmis.decision_context",
    "fmis.swing_setup", "fmis.workspace", "fmis.daily", "fmis.trading_context",
    "fmis.pipeline", "fmis.marks",
})

#: Every package the trading domain is made of.
DOMAIN = frozenset({
    "fmis.records", "fmis.provenance", "fmis.money", "fmis.versioning",
    "fmis.accounts", "fmis.analysis_record", "fmis.snapshotting",
    "fmis.proposal", "fmis.ledger", "fmis.positions", "fmis.portfolio",
    "fmis.risk", "fmis.journal", "fmis.plan", "fmis.portfolio_risk",
})

VENUE_WORDS = ("binance", "evedex", "bybit", "tradingview", "coinbase", "kraken")


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


def _code_only(module_name: str) -> str:
    """The module's *executable* text: no docstrings, no comments.

    A docstring that says *"this package names no venue"* is the guarantee being
    documented; a string constant `"binance"` inside a function is a venue the
    code branches on. Grepping raw source cannot tell them apart.
    """
    tree = ast.parse(_source_of(module_name))
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


# --------------------------------------------------------------------------
# 1. Nothing depends directly on an exchange
# --------------------------------------------------------------------------


def test_the_price_package_imports_only_the_canonical_data_layer() -> None:
    """`fmis.marks` holds no `Money`, no `MarkQuote`, no account and no position.

    The moment a price package knows what a portfolio is, the portfolio's
    valuation becomes a function of the price package's opinion of it.
    """
    reached: set[str] = set()
    for module_name in _modules_of(MARKS):
        reached |= {
            name
            for name in _imports_of(module_name)
            if name.startswith("fmis.") and not name.startswith(MARKS)
        }
    assert reached == {"fmis.data"}


def test_the_price_package_names_no_venue_in_its_code() -> None:
    offenders = {
        module_name: [word for word in VENUE_WORDS if word in _code_only(module_name).lower()]
        for module_name in _modules_of(MARKS)
        if any(word in _code_only(module_name).lower() for word in VENUE_WORDS)
    }
    assert offenders == {}


def test_the_bridge_names_no_venue_in_its_code() -> None:
    """It branches on `MarketMode`, a domain enum, and on nothing else."""
    offenders = {
        module_name: [word for word in VENUE_WORDS if word in _code_only(module_name).lower()]
        for module_name in _modules_of(VALUATION)
        if any(word in _code_only(module_name).lower() for word in VENUE_WORDS)
    }
    assert offenders == {}


def test_no_module_in_either_package_imports_a_provider() -> None:
    """The provider is reached through `fmis.pipeline.prices` and nowhere else."""
    for package in (MARKS, VALUATION):
        for module_name in _modules_of(package):
            reached = {
                name
                for name in _imports_of(module_name)
                if name.startswith("fmis.providers")
            }
            assert reached == set(), (module_name, sorted(reached))


def test_exactly_one_module_in_the_repository_binds_the_provider_to_a_mark() -> None:
    """So the day a second price source arrives, there is one file to change."""
    binding = {
        module_name
        for package in ("fmis.pipeline", MARKS, VALUATION)
        for module_name in _modules_of(package)
        if "fmis.marks" in _imports_of(module_name)
        and any(n.startswith("fmis.providers") for n in _imports_of(module_name))
    }
    assert binding == {"fmis.pipeline.prices"}


# --------------------------------------------------------------------------
# 2. No adapter lives in the owner domain
# --------------------------------------------------------------------------


def test_the_risk_engines_dependency_surface_is_unchanged() -> None:
    """`fmis.portfolio_risk` receives a mapping of marks and knows nothing about
    where one came from. Re-asserted here so this milestone's own bridge cannot
    be mistaken for permission to widen it."""
    permitted = {
        "fmis.accounts", "fmis.ledger", "fmis.money", "fmis.persistence",
        "fmis.plan", "fmis.portfolio", "fmis.positions", "fmis.provenance",
        "fmis.records", "fmis.risk", "fmis.snapshotting",
    }
    reached: set[str] = set()
    for module_name in _modules_of("fmis.portfolio_risk"):
        reached |= {
            name
            for name in _imports_of(module_name)
            if name.startswith("fmis.") and not name.startswith("fmis.portfolio_risk")
        }
    assert reached <= permitted, sorted(reached - permitted)


def test_no_domain_package_imports_either_new_package() -> None:
    """Or a position's value would become a function of a price package."""
    offenders: dict[str, set[str]] = {}
    for package_name in DOMAIN | {"fmis.persistence"}:
        for module_name in _modules_of(package_name):
            reached = {
                name
                for name in _imports_of(module_name)
                if name.startswith(MARKS) or name.startswith(VALUATION)
            }
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_no_market_half_engine_imports_the_bridge() -> None:
    """The crossing points one way. An engine that could read a valuation is an
    engine whose answer depends on the owner's position."""
    offenders: dict[str, set[str]] = {}
    for package_name in MARKET_HALF - {"fmis.pipeline"}:
        for module_name in _modules_of(package_name):
            reached = {
                name for name in _imports_of(module_name) if name.startswith(VALUATION)
            }
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_only_the_cli_imports_the_bridge_from_the_pipeline() -> None:
    """The same exception `fmis.archive` and `fmis.today` already hold: `cli.py`
    is the outermost edge and composes, it does not compute."""
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of("fmis.pipeline"):
        if module_name == "fmis.pipeline.cli":
            continue
        reached = {
            name for name in _imports_of(module_name) if name.startswith(VALUATION)
        }
        if reached:
            offenders[module_name] = reached
    assert offenders == {}
    assert _imports_of("fmis.pipeline.cli") & {VALUATION}


def test_the_price_package_never_reaches_the_store() -> None:
    """`fmis.marks` is a market-half package, and the market half may not reach
    `fmis.persistence`. Re-asserted for the package this milestone added."""
    for module_name in _modules_of(MARKS):
        assert not any(
            name.startswith("fmis.persistence") for name in _imports_of(module_name)
        ), module_name


def test_importing_the_pipeline_still_does_not_load_the_store_layer() -> None:
    """A cold `import fmis.pipeline` must not pull in the store, the domain or
    the bridge. Asserted in a subprocess, because this session imported all
    three long ago."""
    probe = (
        "import fmis.pipeline, sys;"
        "print(int(any(n.startswith('fmis.valuation') "
        "or n.startswith('fmis.persistence') for n in sys.modules)))"
    )
    finished = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert finished.stdout.strip() == "0"


def test_importing_the_price_package_loads_nothing_from_the_owner_half() -> None:
    probe = (
        "import fmis.marks, sys;"
        "print(int(any(n.startswith('fmis.portfolio') "
        "or n.startswith('fmis.persistence') for n in sys.modules)))"
    )
    finished = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert finished.stdout.strip() == "0"


# --------------------------------------------------------------------------
# 3. The crossing is one module wide
# --------------------------------------------------------------------------


def test_only_four_modules_in_the_bridge_touch_the_price_package() -> None:
    """The surface is pinned as a set, so widening it is a visible edit.

    Three of the four only *carry* a `PriceSnapshot` — as a field, as an
    argument, as a fetch result — and never open one. The conversion itself is
    the next test's subject and lives in exactly one of them.
    """
    reaching = {
        module_name
        for module_name in _modules_of(VALUATION)
        if any(name.startswith(MARKS) for name in _imports_of(module_name))
    }
    assert reaching == {
        f"{VALUATION}.marking",    # the conversion itself
        f"{VALUATION}.models",     # carries a PriceSnapshot as a field
        f"{VALUATION}.reading",    # takes one as an argument
        f"{VALUATION}.compose",    # fetches one
    }


def test_only_one_module_converts_a_price_into_a_mark() -> None:
    """A guard on the *conversion*, not the import: the type that crosses is
    `MarkQuote`, and exactly one module may construct one."""
    constructing = {
        module_name
        for module_name in _modules_of(VALUATION)
        if "MarkQuote(" in _code_only(module_name)
    }
    assert constructing == {f"{VALUATION}.marking"}


def test_the_float_to_exact_conversion_is_the_money_kernels_and_not_a_copy() -> None:
    """Two answers to *what is this price, exactly* is how two surfaces come to
    disagree about a total."""
    users = {
        module_name
        for package in (VALUATION, MARKS)
        for module_name in _modules_of(package)
        if "exact_from_market_price" in _code_only(module_name)
    }
    assert users == {f"{VALUATION}.marking"}
    for module_name in _modules_of(VALUATION):
        assert "Decimal(repr(" not in _code_only(module_name), module_name
        assert "Decimal(str(" not in _code_only(module_name), module_name


def test_only_the_reading_and_compose_modules_reach_persistence() -> None:
    reaching = {
        module_name
        for module_name in _modules_of(VALUATION)
        if any(
            name.startswith("fmis.persistence") for name in _imports_of(module_name)
        )
    }
    assert reaching == {f"{VALUATION}.reading", f"{VALUATION}.compose"}


def test_the_store_facing_modules_write_nothing() -> None:
    """A read path that repaired something would make the store's contents
    depend on who looked at them."""
    forbidden = {
        "publish", "create", "revise", "replace", "update", "admit",
        "append_event", "append_lines", "rebuild_index", "atomic_write",
        "write_text", "write_bytes", "mkdir",
    }
    for module_name in (f"{VALUATION}.reading", f"{VALUATION}.compose"):
        called = {
            node.func.attr
            for node in ast.walk(ast.parse(_source_of(module_name)))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert called & forbidden == set(), module_name


# --------------------------------------------------------------------------
# Purity, determinism and no invented policy
# --------------------------------------------------------------------------


def test_no_module_in_either_package_reads_a_clock() -> None:
    """Every instant is an argument, which is what makes a valuation replayable
    and a test of one non-flaky."""
    forbidden = ("datetime.now(", "datetime.utcnow(", "time.time(", "random.")
    offenders: dict[str, list[str]] = {}
    for package in (MARKS, VALUATION):
        for module_name in _modules_of(package):
            source = _source_of(module_name)
            hits = [needle for needle in forbidden if needle in source]
            if hits:
                offenders[module_name] = hits
    assert offenders == {}


def test_the_pure_modules_open_no_file() -> None:
    pure = [
        f"{MARKS}.models", f"{MARKS}.service",
        f"{VALUATION}.marking", f"{VALUATION}.models", f"{VALUATION}.render",
    ]
    for module_name in pure:
        source = _source_of(module_name)
        for needle in ("open(", "Path("):
            assert needle not in source, (module_name, needle)


def test_neither_package_exports_a_composite_score() -> None:
    """`AP` §15.2: a single number would collapse strata into one value whose
    meaning no one could recover."""
    for package in (MARKS, VALUATION):
        exported = " ".join(importlib.import_module(package).__all__).lower()
        for forbidden in ("score", "grade", "rating", "health", "rank"):
            assert forbidden not in exported, (package, forbidden)


def test_no_type_in_the_bridge_can_hold_a_verdict() -> None:
    import dataclasses

    from fmis import valuation

    forbidden = ("verdict", "decision", "recommend", "action", "signal", "advice")
    offenders: dict[str, list[str]] = {}
    for name in valuation.__all__:
        value = getattr(valuation, name)
        if not dataclasses.is_dataclass(value):
            continue
        hits = [
            field
            for field in value.__dataclass_fields__
            if any(word in field.lower() for word in forbidden)
        ]
        if hits:
            offenders[name] = hits
    assert offenders == {}


def test_the_bridge_holds_no_float_literal_anywhere() -> None:
    """One float in a price path is a digest away from a bug. `fmis.marks`
    legitimately holds floats — it reads candles, which are floats by ADR-0005 —
    and the bridge is where that stops."""
    for module_name in _modules_of(VALUATION):
        floats = {
            node.value
            for node in ast.walk(ast.parse(_source_of(module_name)))
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        }
        assert floats == set(), module_name


def test_neither_package_holds_module_level_mutable_state() -> None:
    for package in (MARKS, VALUATION):
        for module_name in _modules_of(package):
            for node in ast.parse(_source_of(module_name)).body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                names = {t.id for t in targets if isinstance(t, ast.Name)}
                if names == {"__all__"}:
                    continue
                assert not isinstance(node.value, (ast.List, ast.Dict, ast.Set)), (
                    module_name, sorted(names)
                )


# --------------------------------------------------------------------------
# Repository-wide invariants, re-asserted
# --------------------------------------------------------------------------


def test_both_packages_declare_what_they_export() -> None:
    for package_name in (MARKS, VALUATION):
        package = importlib.import_module(package_name)
        assert getattr(package, "__all__", None)
        for name in package.__all__:
            assert hasattr(package, name), (package_name, name)


def test_every_new_module_has_a_docstring() -> None:
    for package in (MARKS, VALUATION, "fmis.pipeline"):
        for module_name in _modules_of(package):
            assert importlib.import_module(module_name).__doc__, module_name


def test_no_public_name_is_exported_by_two_packages() -> None:
    """The repository's zero-collision invariant, re-asserted after BM."""
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


def test_neither_package_introduces_a_runtime_dependency() -> None:
    """Standard library and `fmis` only."""
    allowed_roots = {
        "__future__", "collections", "dataclasses", "datetime", "decimal",
        "enum", "math", "pathlib", "textwrap", "typing", "fmis",
    }
    for package in (MARKS, VALUATION):
        for module_name in _modules_of(package):
            for name in _imports_of(module_name):
                assert name.split(".")[0] in allowed_roots, (module_name, name)


def test_the_new_pipeline_module_introduces_no_runtime_dependency() -> None:
    allowed_roots = {"__future__", "collections", "datetime", "typing", "fmis"}
    for name in _imports_of("fmis.pipeline.prices"):
        assert name.split(".")[0] in allowed_roots, name


def test_there_are_no_import_cycles_inside_either_package() -> None:
    for package in (MARKS, VALUATION):
        edges = {
            module_name: {
                name
                for name in _imports_of(module_name)
                if name.startswith(f"{package}.")
            }
            for module_name in _modules_of(package)
            if module_name != package
        }
        visiting: set[str] = set()
        done: set[str] = set()

        def walk(node: str, path: tuple[str, ...]) -> None:
            if node in done:
                return
            assert node not in visiting, f"cycle: {' -> '.join(path + (node,))}"
            visiting.add(node)
            for neighbour in edges.get(node, set()):
                walk(neighbour, path + (node,))
            visiting.discard(node)
            done.add(node)

        for module_name in edges:
            walk(module_name, ())


def test_the_directional_guard_covers_both_new_packages_with_no_exemption() -> None:
    """Neither package is on any exemption list, so ADR-0028's repository-wide
    guard applies to both with no edit. Asserted so a future exemption is a
    deliberate act."""
    from tests import test_directional_vocabulary_boundary as guard

    exempt = {path.name for path in guard._TRADE_DOMAIN_PERMITTED_DIRS}
    assert "marks" not in exempt
    assert "valuation" not in exempt
    covered = {path.parent.name for path in guard._covered_files()}
    assert {"marks", "valuation"} <= covered
