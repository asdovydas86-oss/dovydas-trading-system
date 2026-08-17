"""Boundary guards for `fmis.trade_lifecycle` and `fmis.paper`.

These do not exercise behaviour. They assert the rules the milestone rests on, in
the only form that survives a refactor: an executable check over the source tree.

**The crossing is exactly one module wide.** `fmis.paper.bars` is the only place
in either package that imports `fmis.data`, and it is asserted as a set — a
design document claiming the simulator is candle-agnostic below that line is a
claim; a test that fails the moment a second module imports a candle is the
guarantee.

**The domain half must stay importable by the store.** `fmis.persistence.kinds`
imports `fmis.trade_lifecycle`, so a market-half import there would make the
store transitively depend on a candle decoder. That is the rule this file's
strictest test protects.

**The package is in tiers and the tests say which module is in which.** Tier
membership is pinned, so a new module is a deliberate edit here rather than an
unguarded one.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest

import fmis

DOMAIN = "fmis.trade_lifecycle"
ENGINE = "fmis.paper"
SOURCE_ROOT = Path(fmis.__file__).parent

#: Every package that reads a candle, reaches a venue or renders a chart. Copied
#: deliberately rather than imported, so adding one is a visible edit in each
#: guard that cares — the convention `tests/test_position_sizing_architecture.py`
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

VENUE_SPECIFIC = frozenset({"fmis.providers", "fmis.providers.binance"})

#: The domain half: four record types, two folds, and nothing else.
DOMAIN_MODULES = [
    f"{DOMAIN}.models",
    f"{DOMAIN}.events",
    f"{DOMAIN}.stops",
    f"{DOMAIN}.outcome",
]

#: The engine's pure tier — exact arithmetic, no candle, no store, no clock.
PURE_ENGINE_MODULES = [
    f"{ENGINE}.models",
    f"{ENGINE}.fills",
    f"{ENGINE}.stopping",
    f"{ENGINE}.engine",
    f"{ENGINE}.replay",
    f"{ENGINE}.monitor",
]

#: The one module that turns a `Candle` into exact values.
BAR_MODULE = f"{ENGINE}.bars"

#: The surfaces: the read path, the write path, the text boundary, the page.
SURFACE_MODULES = [
    f"{ENGINE}.views",
    f"{ENGINE}.compose",
    f"{ENGINE}.inputs",
    f"{ENGINE}.render",
]


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
    tree = ast.parse(_source_of(module_name))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _code_only(module_name: str) -> str:
    """The module's *executable* text: no docstrings, no comments.

    A docstring saying *"this module names no venue"* is the guarantee being
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


def _names_used(module_name: str) -> set[str]:
    tree = ast.parse(_source_of(module_name))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
    return found


# --------------------------------------------------------------------------
# The tiers themselves.
# --------------------------------------------------------------------------


def test_the_packages_hold_exactly_the_modules_these_guards_cover() -> None:
    assert set(_modules_of(DOMAIN)) == {DOMAIN, *DOMAIN_MODULES}
    assert set(_modules_of(ENGINE)) == {
        ENGINE,
        *PURE_ENGINE_MODULES,
        BAR_MODULE,
        *SURFACE_MODULES,
    }


# --------------------------------------------------------------------------
# The one candle crossing.
# --------------------------------------------------------------------------


def test_exactly_one_module_in_either_package_imports_a_candle() -> None:
    reaching = {
        module_name
        for package in (DOMAIN, ENGINE)
        for module_name in _modules_of(package)
        if "fmis.data" in _imports_of(module_name)
    }
    assert reaching == {BAR_MODULE}


def test_the_domain_half_reaches_no_market_half_package_at_all() -> None:
    """`fmis.persistence.kinds` imports this package. A market-half import here
    would make the store transitively depend on a candle decoder."""
    for module_name in _modules_of(DOMAIN):
        assert _imports_of(module_name) & MARKET_HALF == set(), module_name


def test_the_domain_half_reaches_only_the_kernel_and_the_owner_domain() -> None:
    """The whole dependency surface, asserted as a set rather than described."""
    permitted = {
        "fmis.accounts",
        "fmis.archive.json_safe",
        "fmis.money",
        "fmis.provenance",
        "fmis.records",
        "fmis.snapshotting",
        "fmis.versioning",
    }
    reached: set[str] = set()
    for module_name in _modules_of(DOMAIN):
        reached |= {
            name
            for name in _imports_of(module_name)
            if name.startswith("fmis.") and not name.startswith(DOMAIN)
        }
    assert reached <= permitted, f"unexpected: {sorted(reached - permitted)}"


def test_the_domain_half_never_imports_the_store() -> None:
    """The direction is one-way: the store imports the domain, never the reverse."""
    for module_name in _modules_of(DOMAIN):
        assert not [
            name
            for name in _imports_of(module_name)
            if name.startswith("fmis.persistence")
        ], module_name


def test_the_pure_engine_tier_imports_no_candle_and_no_store() -> None:
    for module_name in PURE_ENGINE_MODULES:
        reached = _imports_of(module_name)
        assert "fmis.data" not in reached, module_name
        assert not [
            name for name in reached if name.startswith("fmis.persistence")
        ], module_name


def test_no_module_in_either_package_imports_a_venue_provider() -> None:
    """Binance is not special, and the day it becomes special this fails."""
    for package in (DOMAIN, ENGINE):
        for module_name in _modules_of(package):
            reached = {
                name
                for name in _imports_of(module_name)
                if name in VENUE_SPECIFIC or name.startswith("fmis.providers")
            }
            assert reached == set(), f"{module_name} imports {sorted(reached)}"


def test_no_module_in_either_package_names_a_venue_in_its_code() -> None:
    forbidden = ("binance", "evedex", "bybit", "tradingview", "coinbase", "kraken")
    offenders: dict[str, list[str]] = {}
    for package in (DOMAIN, ENGINE):
        for module_name in _modules_of(package):
            source = _code_only(module_name).lower()
            hits = [needle for needle in forbidden if needle in source]
            if hits:
                offenders[module_name] = hits
    assert offenders == {}


# --------------------------------------------------------------------------
# No clock, no path, no randomness, no execution.
# --------------------------------------------------------------------------


def test_no_module_in_either_package_reads_a_clock_or_a_random_number() -> None:
    """`fmis.pipeline.cli` is the only place in this repository that takes the
    time. A simulator that stamped itself could not be replayed, and one that
    reached for a random number would not be deterministic."""
    forbidden = ("datetime.now(", "datetime.utcnow(", "time.time(", "random.")
    offenders: dict[str, list[str]] = {}
    for package in (DOMAIN, ENGINE):
        for module_name in _modules_of(package):
            hits = [needle for needle in forbidden if needle in _source_of(module_name)]
            if hits:
                offenders[module_name] = hits
    assert offenders == {}


def test_the_domain_and_the_pure_engine_hold_no_path_and_open_no_file() -> None:
    forbidden = ("open(", "Path(", "write_text", "write_bytes", "mkdir")
    for module_name in DOMAIN_MODULES + PURE_ENGINE_MODULES:
        source = _source_of(module_name)
        assert [needle for needle in forbidden if needle in source] == [], module_name


def test_only_three_modules_reach_persistence() -> None:
    reaching = {
        module_name
        for module_name in _modules_of(ENGINE)
        if any(
            name.startswith("fmis.persistence") for name in _imports_of(module_name)
        )
    }
    assert reaching == {
        f"{ENGINE}.views",
        f"{ENGINE}.compose",
        f"{ENGINE}.inputs",
    }


def test_the_read_path_writes_nothing() -> None:
    """A `trade status` that repaired something would make the store's contents
    depend on who looked at them."""
    forbidden = {
        "publish",
        "revise",
        "replace",
        "update",
        "append_event",
        "append_amendment",
        "append_lines",
        "rebuild_index",
        "atomic_write",
        "write_text",
        "write_bytes",
        "mkdir",
    }
    for module_name in (f"{ENGINE}.views", f"{ENGINE}.render", f"{ENGINE}.monitor"):
        assert _names_used(module_name) & forbidden == set(), module_name


def test_neither_package_names_an_execution_verb_anywhere() -> None:
    """Paper only: no order is placed and no venue is reached."""
    forbidden = (
        "place_order",
        "submit_order",
        "cancel_order",
        "execute_trade",
        "api_key",
        "websocket",
        "telegram",
    )
    offenders: dict[str, list[str]] = {}
    for package in (DOMAIN, ENGINE):
        for module_name in _modules_of(package):
            source = _code_only(module_name).lower()
            hits = [needle for needle in forbidden if needle in source]
            if hits:
                offenders[module_name] = hits
    assert offenders == {}


def test_neither_package_consults_a_model_or_predicts_anything() -> None:
    forbidden = ("predict", "probability", "forecast", "model_id", "llm", "prompt")
    offenders: dict[str, list[str]] = {}
    for package in (DOMAIN, ENGINE):
        for module_name in _modules_of(package):
            source = _code_only(module_name).lower()
            hits = [needle for needle in forbidden if needle in source]
            if hits:
                offenders[module_name] = hits
    assert offenders == {}


# --------------------------------------------------------------------------
# No invented thresholds, no scores.
# --------------------------------------------------------------------------


def test_the_computing_modules_invent_no_threshold() -> None:
    """Every number compared against is the owner's. The precedent is
    `fmis.risk`, `fmis.portfolio_risk` and `fmis.position_sizing`, which pass
    the identical test.

    `fmis.paper.monitor` and `fmis.paper.views` are outside this list for one
    constant apiece: the number of seconds in a day, which turns a `timedelta`
    into days and is a property of the calendar rather than a policy anybody
    chose.
    """
    #: `events.py` is exempt for one table: `CAUSAL_RANK`'s integers are
    #: *positions in a sequence* — the order two events on one candle are applied
    #: in — and not numbers any measurement is compared against. The distinction
    #: is the whole of what this guard protects, so the exemption is named here
    #: rather than the guard weakened for every module.
    for module_name in [
        name for name in DOMAIN_MODULES if not name.endswith(".events")
    ] + [
        f"{ENGINE}.fills",
        f"{ENGINE}.stopping",
        f"{ENGINE}.engine",
        f"{ENGINE}.replay",
    ]:
        literals = {
            node.value
            for node in ast.walk(ast.parse(_source_of(module_name)))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        }
        assert literals <= {0, 1}, (module_name, sorted(literals - {0, 1}))


def test_neither_package_holds_a_float_literal_anywhere() -> None:
    """One float in a price path is a fifty-five-digit digest away from a bug."""
    for package in (DOMAIN, ENGINE):
        for module_name in _modules_of(package):
            floats = {
                node.value
                for node in ast.walk(ast.parse(_source_of(module_name)))
                if isinstance(node, ast.Constant) and isinstance(node.value, float)
            }
            assert floats == set(), module_name


def test_neither_package_exports_a_composite_score() -> None:
    """`AP` §15.2: a single number would collapse strata into one value whose
    meaning no one could recover.

    Matched on whole `_`-separated words rather than as substrings.
    `CAUSAL_RANK` is the order two events on one candle are applied in — a
    position in a sequence, not a desirability — and a substring match would
    make the guard unable to tell the two apart.
    """
    exported = {
        word
        for package in (DOMAIN, ENGINE)
        for name in importlib.import_module(package).__all__
        for word in name.lower().split("_")
    }
    for forbidden in ("score", "grade", "rating", "health", "ranking"):
        assert forbidden not in exported, forbidden
    assert "causal_rank" in {
        name.lower()
        for package in (DOMAIN, ENGINE)
        for name in importlib.import_module(package).__all__
    }


def test_no_type_here_can_hold_a_trading_verdict() -> None:
    """*Take* and *skip* are the owner's conclusion, and there is no field they
    could be written into."""
    import dataclasses

    forbidden = {"verdict", "advice", "should", "signal"}
    offenders: dict[str, list[str]] = {}
    for package_name in (DOMAIN, ENGINE):
        package = importlib.import_module(package_name)
        for name in package.__all__:
            value = getattr(package, name)
            if not dataclasses.is_dataclass(value):
                continue
            hits = [
                field
                for field in value.__dataclass_fields__
                if forbidden & set(field.lower().split("_"))
            ]
            if hits:
                offenders[name] = hits
    assert offenders == {}


# --------------------------------------------------------------------------
# Projections stay projections.
# --------------------------------------------------------------------------


def test_exactly_four_new_record_kinds_were_added_and_they_are_the_domains() -> None:
    from fmis.persistence import SPECS, RecordKind

    from fmis import paper, trade_lifecycle

    persisted = {spec.record_type for spec in SPECS.values()}
    stored_here = {
        getattr(trade_lifecycle, name)
        for name in trade_lifecycle.__all__
        if isinstance(getattr(trade_lifecycle, name), type)
        and getattr(trade_lifecycle, name) in persisted
    }
    assert {kind.__name__ for kind in stored_here} == {
        "TradeActivation",
        "TradeLifecycleEvent",
        "StopAmendment",
        "TradeOutcome",
    }
    assert len(RecordKind) == 15
    # The engine half stores nothing of its own.
    for name in paper.__all__:
        value = getattr(paper, name)
        if isinstance(value, type):
            assert value not in persisted, name


def test_no_projection_in_the_engine_has_a_decoder() -> None:
    """`to_payload` without `from_payload`: exportable, and impossible to read
    back into the store as truth."""
    from fmis.paper import TradeMonitor
    from fmis.trade_lifecycle import StopHistory, TradeLifecycleView

    for projection in (TradeMonitor, StopHistory, TradeLifecycleView):
        assert hasattr(projection, "to_payload"), projection
        assert not hasattr(projection, "from_payload"), projection


def test_every_stored_record_round_trips_and_every_projection_does_not() -> None:
    from fmis.trade_lifecycle import (
        StopAmendment,
        TradeActivation,
        TradeLifecycleEvent,
        TradeOutcome,
    )

    for record in (TradeActivation, TradeLifecycleEvent, StopAmendment, TradeOutcome):
        assert hasattr(record, "from_payload"), record
        assert hasattr(record, "to_payload"), record


# --------------------------------------------------------------------------
# Vocabulary.
# --------------------------------------------------------------------------


def test_neither_package_holds_directional_vocabulary_of_its_own() -> None:
    """ADR-0028's boundary, applied unchanged and **without an exemption**.

    Both packages branch on which way a trade points — a simulator must, to
    decide whether a stop is above or below. Neither names a side: the sign rule
    is `TradeDirection.sign`, added to `fmis.snapshotting` where the enum already
    lives, and every comparison here is arithmetic over that number. Rewording is
    cheaper than widening a boundary — `BM`'s own precedent, followed again.
    """
    banned = {"long", "short", "buy", "sell", "bullish", "bearish"}
    offenders: list[tuple[str, str]] = []
    for package in (DOMAIN, ENGINE):
        for module_name in _modules_of(package):
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


def test_the_repository_wide_directional_guard_already_covers_both_packages() -> None:
    """No exemption list was widened for this milestone. Asserted so a future
    exemption is a deliberate act rather than a quiet one."""
    from tests import test_directional_vocabulary_boundary as guard

    exempt = {path.name for path in guard._TRADE_DOMAIN_PERMITTED_DIRS}
    surfaces = {path.name for path in guard._OWNER_SURFACE_DIRS}
    covered = {path.parent.name for path in guard._covered_files()}
    for package in ("trade_lifecycle", "paper"):
        assert package not in exempt
        assert package not in surfaces
        assert package in covered


# --------------------------------------------------------------------------
# Repository-wide invariants, re-asserted after a new package.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("package", [DOMAIN, ENGINE])
def test_the_package_declares_what_it_exports(package: str) -> None:
    module = importlib.import_module(package)
    assert getattr(module, "__all__", None)
    for name in module.__all__:
        assert hasattr(module, name), name


@pytest.mark.parametrize("package", [DOMAIN, ENGINE])
def test_every_module_has_a_docstring(package: str) -> None:
    for module_name in _modules_of(package):
        assert importlib.import_module(module_name).__doc__, module_name


def test_no_public_name_is_exported_by_two_packages() -> None:
    """The repository's zero-collision invariant, re-asserted after BO."""
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


@pytest.mark.parametrize("package", [DOMAIN, ENGINE])
def test_the_package_introduces_no_runtime_dependency(package: str) -> None:
    allowed_roots = {
        "__future__",
        "collections",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "hashlib",
        "pathlib",
        "textwrap",
        "types",
        "typing",
        "fmis",
    }
    for module_name in _modules_of(package):
        for name in _imports_of(module_name):
            assert name.split(".")[0] in allowed_roots, f"{module_name}: {name}"


@pytest.mark.parametrize("package", [DOMAIN, ENGINE])
def test_there_are_no_import_cycles_inside_the_package(package: str) -> None:
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


def test_the_layering_runs_one_way_from_models_outwards() -> None:
    position = {
        f"{DOMAIN}.models": 0,
        f"{DOMAIN}.events": 1,
        f"{DOMAIN}.stops": 1,
        f"{DOMAIN}.outcome": 1,
        f"{ENGINE}.models": 2,
        f"{ENGINE}.fills": 3,
        f"{ENGINE}.stopping": 3,
        f"{ENGINE}.bars": 3,
        f"{ENGINE}.engine": 4,
        f"{ENGINE}.replay": 5,
        f"{ENGINE}.monitor": 5,
        f"{ENGINE}.views": 6,
        f"{ENGINE}.compose": 7,
        f"{ENGINE}.render": 8,
        f"{ENGINE}.inputs": 8,
    }
    for module_name, index in position.items():
        for imported in _imports_of(module_name):
            if imported in position:
                assert position[imported] < index, (module_name, imported)


# --------------------------------------------------------------------------
# The one-way boundary, in both directions.
# --------------------------------------------------------------------------


def test_no_engine_or_domain_package_imports_the_simulator() -> None:
    """The direction is one-way. The day it reverses, an engine's analysis could
    become a function of a position the simulator opened."""
    offenders: dict[str, set[str]] = {}
    for package_name in sorted(MARKET_HALF - {"fmis.today", "fmis.pipeline"}) + [
        "fmis.portfolio_risk",
        "fmis.valuation",
        "fmis.trade_capture",
        "fmis.position_sizing",
        "fmis.plan",
        "fmis.risk",
        "fmis.ledger",
        "fmis.positions",
    ]:
        for module_name in _modules_of(package_name):
            reached = {
                name for name in _imports_of(module_name) if name.startswith(ENGINE)
            }
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_only_named_consumers_reach_the_engine_and_the_domain() -> None:
    """Every consumer of each package, named — and the two lists are **not** the
    same, which is the point.

    The **engine** is reached by exactly two modules: the CLI, which is the
    surface, and the workspace builder, which assembles the day's page from views
    the engine's own read path produced. Nothing else may run a simulation.

    The **domain** is reached by three others and by neither of those: the two
    store modules that persist the four record types, and `fmis.today.sections`,
    which needs the *state vocabulary*
    to give every lifecycle state a bucket on the page. That last one is a
    deliberate widening: the first draft of the section hard-coded six bucket
    keys and read five of them, so a finished trade — which folds to `RESOLVED`
    — landed in a key nothing read and was invisible on every page. Reading the
    enum is what makes the coverage assertable, and reading an *enum* is a
    weaker crossing than reaching the engine: `fmis.today` already imports
    `fmis.money`, `fmis.provenance` and `fmis.positions` for exactly this.
    """
    def reaching(prefix: str) -> set[str]:
        return {
            module_name
            for package_name in ("fmis.persistence", "fmis.pipeline", "fmis.today")
            for module_name in _modules_of(package_name)
            if any(name.startswith(prefix) for name in _imports_of(module_name))
        }

    assert reaching(ENGINE) == {
        "fmis.pipeline.cli",
        "fmis.today.builder",
    }
    assert reaching(DOMAIN) == {
        "fmis.persistence.kinds",
        "fmis.persistence.lifecycle_repositories",
        "fmis.today.sections",
    }


def test_the_workspace_section_reaches_the_vocabulary_and_not_the_engine() -> None:
    """The widening above is bounded: `fmis.today.sections` may name a state and
    may not run a simulation, open a store or read a candle."""
    reached = _imports_of("fmis.today.sections")
    assert not [name for name in reached if name.startswith(ENGINE)]
    assert {name for name in reached if name.startswith(DOMAIN)} == {DOMAIN}
    used = _names_used("fmis.today.sections")
    for forbidden in ("advance", "replay_bars", "run_simulation", "TradingStore", "Candle"):
        assert forbidden not in used, forbidden


def test_the_cli_still_opens_no_store_of_its_own() -> None:
    """`fmits simulate` parses no price and constructs no `AccountId`: every
    conversion lives in `paper.inputs`, where it can be tested without a parser."""
    used = _names_used("fmis.pipeline.cli")
    assert "TradingStore" not in used
    assert "AccountId" not in used
    assert "TradeActivation" not in used


def test_the_candle_fetcher_computes_nothing() -> None:
    """`fmis.pipeline.candles` chooses what to fetch and isolates failure. A
    number produced at the composition layer is a number no engine can be held
    to — the identical guard `fmis.pipeline.prices` already passes."""
    arithmetic = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
    tree = ast.parse(_source_of("fmis.pipeline.candles"))
    operators = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.AugAssign)
        or (isinstance(node, ast.BinOp) and isinstance(node.op, arithmetic))
    ]
    assert operators == []
