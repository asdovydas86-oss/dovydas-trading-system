"""Boundary guards for `fmis.position_sizing`.

These do not exercise behaviour. They assert the rules the milestone rests on, in
the only form that survives a refactor: an executable check over the source tree.

**The venue-agnostic proof is here.** A design document claiming FMITS is not
Binance-centric is a claim; a test that fails the moment a provider import
appears in sizing arithmetic is the guarantee. The same test covers TradingView,
every market-half engine and every future execution adapter, because the check is
*"which packages does this reach"* rather than a list of names somebody has to
remember to extend.

**The package is in three tiers and the tests say which module is in which.**
`policy`/`models`/`sizing`/`approval` compute and reach nothing; `reading` reads
the store and writes nothing; `inputs`, `compose` and `render` are surfaces. Every
rule below is applied to the tier it belongs to, and the tier membership itself is
pinned so a new module is a deliberate edit here.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest

import fmis

PACKAGE = "fmis.position_sizing"
SOURCE_ROOT = Path(fmis.__file__).parent

#: Every package that reads a candle, reaches a venue or renders a chart. Copied
#: deliberately rather than imported, so adding one is a visible edit in each
#: guard that cares — the convention `tests/test_portfolio_risk_architecture.py`
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

#: The modules that compute. Nothing here opens a file, reaches a venue, reads a
#: clock, names an exchange or holds a threshold.
PURE_MODULES = [
    f"{PACKAGE}.models",
    f"{PACKAGE}.policy",
    f"{PACKAGE}.sizing",
    f"{PACKAGE}.approval",
]

#: The one module that touches persistence, and it only reads.
STORE_MODULE = f"{PACKAGE}.reading"

#: The surfaces: where the owner's text becomes a domain value, where the outer
#: edge opens a store and fetches prices, and where a result becomes a page.
SURFACE_MODULES = [f"{PACKAGE}.inputs", f"{PACKAGE}.compose", f"{PACKAGE}.render"]


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
    code branches on. Grepping raw source cannot tell them apart, so the tree is
    stripped of docstrings and re-unparsed.
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


def test_the_package_holds_exactly_the_modules_these_guards_cover() -> None:
    """A new module is a deliberate edit here rather than an unguarded one."""
    assert set(_modules_of(PACKAGE)) == {
        PACKAGE,
        *PURE_MODULES,
        STORE_MODULE,
        *SURFACE_MODULES,
    }


# --------------------------------------------------------------------------
# The venue-agnostic guarantee.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", PURE_MODULES + [STORE_MODULE])
def test_no_computing_module_imports_a_venue_provider(module_name: str) -> None:
    """Binance is not special, and the day it becomes special this fails."""
    reached = {
        name
        for name in _imports_of(module_name)
        if name in VENUE_SPECIFIC or name.startswith("fmis.providers")
    }
    assert reached == set(), f"{module_name} imports {sorted(reached)}"


@pytest.mark.parametrize("module_name", PURE_MODULES + [STORE_MODULE])
def test_no_computing_module_imports_a_market_half_engine(module_name: str) -> None:
    """A size must not be a function of the analysis. The scanner, the regime
    engine and the workspace are all on the far side of this line."""
    reached = _imports_of(module_name) & MARKET_HALF
    assert reached == set(), f"{module_name} imports {sorted(reached)}"


@pytest.mark.parametrize("module_name", PURE_MODULES + [STORE_MODULE])
def test_no_computing_module_names_a_venue_in_its_code(module_name: str) -> None:
    """Not even as a default, a fallback or a special case.

    `fmis.position_sizing.inputs` legitimately names one, because it is a
    *surface* pre-filling a field the owner can change — the identical footing
    `fmis.trade_capture` holds. Sizing arithmetic has no such excuse: a venue
    named here would be a branch some venues take and others do not.
    """
    forbidden = ("binance", "evedex", "bybit", "tradingview", "coinbase", "kraken")
    source = _code_only(module_name).lower()
    assert [needle for needle in forbidden if needle in source] == []


def test_the_venue_naming_surface_is_exactly_one_module() -> None:
    """Pinned, so a second module naming an exchange has to justify itself."""
    forbidden = ("binance", "evedex", "bybit", "tradingview", "coinbase", "kraken")
    naming = {
        module_name
        for module_name in _modules_of(PACKAGE)
        if any(needle in _code_only(module_name).lower() for needle in forbidden)
    }
    assert naming <= {f"{PACKAGE}.inputs"}


def test_the_computing_tier_reaches_only_the_domain() -> None:
    """The whole dependency surface, asserted as a set rather than described."""
    permitted = {
        "fmis.accounts",
        "fmis.money",
        "fmis.plan",
        "fmis.portfolio_risk",
        "fmis.positions",
        "fmis.provenance",
        "fmis.records",
        "fmis.risk",
        "fmis.snapshotting",
        "fmis.persistence",
    }
    reached: set[str] = set()
    for module_name in PURE_MODULES + [STORE_MODULE]:
        reached |= {
            name
            for name in _imports_of(module_name)
            if name.startswith("fmis.") and not name.startswith(PACKAGE)
        }
    assert reached <= permitted, f"unexpected: {sorted(reached - permitted)}"


def test_the_whole_package_reaches_only_the_domain_and_the_two_bridges() -> None:
    """`fmis.valuation` and `fmis.trade_capture` are reached from surfaces only.

    Both are application-layer packages at the same tier as this one, and each is
    imported for exactly one thing: `valuation` produces the `PortfolioState` an
    approval is measured against, and `trade_capture` owns the one symbol→market
    split in the repository. `fmis.pipeline.prices` is the mark interval's own
    home and is where every provider call in this repository already lives.
    """
    permitted = {
        "fmis.accounts",
        "fmis.money",
        "fmis.persistence",
        "fmis.pipeline.prices",
        "fmis.plan",
        "fmis.portfolio_risk",
        "fmis.positions",
        "fmis.provenance",
        "fmis.records",
        "fmis.risk",
        "fmis.snapshotting",
        "fmis.trade_capture",
        "fmis.valuation",
    }
    reached: set[str] = set()
    for module_name in _modules_of(PACKAGE):
        reached |= {
            name
            for name in _imports_of(module_name)
            if name.startswith("fmis.") and not name.startswith(PACKAGE)
        }
    assert reached <= permitted, f"unexpected: {sorted(reached - permitted)}"


# --------------------------------------------------------------------------
# Purity: only two modules touch disk, and one of them only reads.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", PURE_MODULES)
def test_the_pure_modules_never_import_the_store(module_name: str) -> None:
    reached = {
        name for name in _imports_of(module_name) if name.startswith("fmis.persistence")
    }
    assert reached == set(), f"{module_name} imports {sorted(reached)}"


@pytest.mark.parametrize("module_name", PURE_MODULES)
def test_the_pure_modules_hold_no_path_no_file_and_no_clock(module_name: str) -> None:
    """A size that stamped itself could not be pinned in a test."""
    forbidden = (
        "datetime.now(",
        "datetime.utcnow(",
        "time.time(",
        "random.",
        "open(",
        "Path(",
    )
    source = _source_of(module_name)
    assert [needle for needle in forbidden if needle in source] == []


def test_no_module_in_the_package_reads_a_clock() -> None:
    """`fmis.pipeline.cli` is the only place in this repository that takes the
    time; every instant here is an argument."""
    forbidden = ("datetime.now(", "datetime.utcnow(", "time.time(", "random.")
    offenders: dict[str, list[str]] = {}
    for module_name in _modules_of(PACKAGE):
        hits = [needle for needle in forbidden if needle in _source_of(module_name)]
        if hits:
            offenders[module_name] = hits
    assert offenders == {}


def test_only_two_modules_reach_persistence() -> None:
    reaching = {
        module_name
        for module_name in _modules_of(PACKAGE)
        if any(
            name.startswith("fmis.persistence") for name in _imports_of(module_name)
        )
    }
    assert reaching == {STORE_MODULE, f"{PACKAGE}.compose"}


@pytest.mark.parametrize("module_name", [STORE_MODULE, f"{PACKAGE}.compose"])
def test_nothing_in_this_package_writes_to_the_store(module_name: str) -> None:
    """A read path that repaired something would make the store's contents
    depend on who looked at it. This engine evaluates; it records nothing."""
    forbidden = {
        "publish",
        "create",
        "revise",
        "replace",
        "update",
        "admit",
        "append_event",
        "append_lines",
        "rebuild_index",
        "atomic_write",
        "write_text",
        "write_bytes",
        "mkdir",
    }
    assert _names_used(module_name) & forbidden == set()


def test_the_package_names_no_execution_verb_anywhere() -> None:
    """This engine never executes: no order is placed and no venue is reached."""
    forbidden = ("place_order", "submit_order", "cancel_order", "execute_trade")
    offenders: dict[str, list[str]] = {}
    for module_name in _modules_of(PACKAGE):
        source = _code_only(module_name).lower()
        hits = [needle for needle in forbidden if needle in source]
        if hits:
            offenders[module_name] = hits
    assert offenders == {}


# --------------------------------------------------------------------------
# No thresholds, no scores, no verdicts.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", PURE_MODULES)
def test_the_computing_modules_invent_no_threshold(module_name: str) -> None:
    """Every number compared against is the owner's. The precedent is
    `fmis.risk` and `fmis.portfolio_risk`, which pass the identical test."""
    literals = {
        node.value
        for node in ast.walk(ast.parse(_source_of(module_name)))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    assert literals <= {0, 1}, sorted(literals - {0, 1})


def test_the_package_holds_no_float_literal_anywhere() -> None:
    """One float in a price path is a fifty-five-digit digest away from a bug."""
    for module_name in _modules_of(PACKAGE):
        floats = {
            node.value
            for node in ast.walk(ast.parse(_source_of(module_name)))
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        }
        assert floats == set(), module_name


def test_the_package_exports_no_composite_score() -> None:
    """`AP` §15.2: a single number would collapse three strata into one value
    whose meaning no one could recover."""
    exported = " ".join(importlib.import_module(PACKAGE).__all__).lower()
    for forbidden in ("score", "grade", "rating", "health", "rank", "index"):
        assert forbidden not in exported, forbidden


def test_no_type_here_can_hold_a_trading_verdict() -> None:
    """*Take* and *skip* are the owner's conclusion, and there is no field they
    could be written into. `recommendation` is deliberately not on this list: a
    recommended **size** is what this package produces, and it is a different
    word from a recommended **action**."""
    import dataclasses

    from fmis import position_sizing

    # Matched on whole words rather than as substrings: `risk_fraction` contains
    # "action" and is a fraction of equity, not an action anybody takes.
    forbidden = {"verdict", "decision", "action", "signal", "advice", "should"}
    offenders: dict[str, list[str]] = {}
    for name in position_sizing.__all__:
        value = getattr(position_sizing, name)
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


def test_no_module_names_a_trading_verdict() -> None:
    """A grep-level guard over the source, so a verdict cannot arrive as a string
    constant, an enum member or a docstring promise."""
    forbidden = (
        "take_trade",
        "reject_trade",
        "should_trade",
        "skip_trade",
        "take this trade\"",
    )
    offenders: dict[str, list[str]] = {}
    for module_name in _modules_of(PACKAGE):
        source = _code_only(module_name).lower()
        hits = [needle for needle in forbidden if needle in source]
        if hits:
            offenders[module_name] = hits
    assert offenders == {}


def test_the_status_vocabulary_is_this_packages_own_and_the_limit_status_is_not() -> None:
    """`WITHIN`/`AT_LIMIT`/`EXCEEDED` stay `fmis.risk`'s; an approval is a
    different question with a different three-valued answer."""
    from fmis.risk import LimitStatus

    from fmis.position_sizing import ApprovalStatus

    assert "LimitStatus" not in importlib.import_module(PACKAGE).__all__
    assert {member.value for member in ApprovalStatus} & {
        member.value for member in LimitStatus
    } == set()


def test_the_sizing_arithmetic_never_reads_setup_quality() -> None:
    """*'Never size from setup quality or confidence.'* Confidence is
    `NOT_CALIBRATED`, and sizing off an uncalibrated number is sizing off
    nothing."""
    used = _names_used(f"{PACKAGE}.sizing")
    for forbidden in (
        "confidence",
        "probability",
        "stated_confidence",
        "sufficiency",
        "state",
        "thesis",
    ):
        assert forbidden not in used, forbidden


# --------------------------------------------------------------------------
# Projections stay projections.
# --------------------------------------------------------------------------


def test_nothing_in_this_package_is_a_persisted_record_kind() -> None:
    """A derived approval must not become authoritative truth. The day one does,
    it needs a `RecordKind`, a spec row and a durability class chosen
    deliberately — not a `to_payload` that happened to be written."""
    from fmis.persistence import SPECS

    from fmis import position_sizing

    persisted = {spec.record_type for spec in SPECS.values()}
    for name in position_sizing.__all__:
        value = getattr(position_sizing, name)
        if not isinstance(value, type):
            continue
        assert value not in persisted, name


def test_no_projection_here_has_a_decoder() -> None:
    """`to_payload` without `from_payload`: exportable, and impossible to read
    back into the store as truth."""
    from fmis.position_sizing import (
        ApprovalReason,
        ApprovalResult,
        PositionProposal,
        PositionRecommendation,
    )

    for projection in (
        PositionProposal,
        PositionRecommendation,
        ApprovalReason,
        ApprovalResult,
    ):
        assert hasattr(projection, "to_payload"), projection
        assert not hasattr(projection, "from_payload"), projection


# --------------------------------------------------------------------------
# Vocabulary.
# --------------------------------------------------------------------------


def test_this_package_holds_no_directional_vocabulary_of_its_own() -> None:
    """ADR-0028's boundary, applied unchanged and **without an exemption**.

    Six trading-domain packages are exempt from the repository-wide guard because
    they *hold* a side. This one does not: it passes `TradeDirection` through
    opaquely and lets `fmis.portfolio_risk.stop_distance` own the sign rule, so
    no exemption was needed and none was taken. Rewording is cheaper than
    widening a boundary — `BM`'s own precedent.
    """
    banned = {"long", "short", "buy", "sell", "bullish", "bearish"}
    offenders: list[tuple[str, str]] = []
    for module_name in _modules_of(PACKAGE):
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
    """No exemption list was widened for this milestone. Asserted so a future
    exemption is a deliberate act rather than a quiet one."""
    from tests import test_directional_vocabulary_boundary as guard

    exempt = {path.name for path in guard._TRADE_DOMAIN_PERMITTED_DIRS}
    surfaces = {path.name for path in guard._OWNER_SURFACE_DIRS}
    assert "position_sizing" not in exempt
    assert "position_sizing" not in surfaces
    covered = {path.parent.name for path in guard._covered_files()}
    assert "position_sizing" in covered


# --------------------------------------------------------------------------
# Repository-wide invariants, re-asserted after a new package.
# --------------------------------------------------------------------------


def test_the_package_declares_what_it_exports() -> None:
    package = importlib.import_module(PACKAGE)
    assert getattr(package, "__all__", None)
    for name in package.__all__:
        assert hasattr(package, name), name


def test_every_module_has_a_docstring() -> None:
    for module_name in _modules_of(PACKAGE):
        assert importlib.import_module(module_name).__doc__, module_name


def test_no_public_name_is_exported_by_two_packages() -> None:
    """The repository's zero-collision invariant, re-asserted after BN."""
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


def test_the_package_introduces_no_runtime_dependency() -> None:
    """Standard library and `fmis` only."""
    allowed_roots = {
        "__future__",
        "ast",
        "collections",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "pathlib",
        "textwrap",
        "typing",
        "fmis",
    }
    for module_name in _modules_of(PACKAGE):
        for name in _imports_of(module_name):
            assert name.split(".")[0] in allowed_roots, f"{module_name}: {name}"


def test_there_are_no_import_cycles_inside_the_package() -> None:
    edges = {
        module_name: {
            name
            for name in _imports_of(module_name)
            if name.startswith(f"{PACKAGE}.")
        }
        for module_name in _modules_of(PACKAGE)
        if module_name != PACKAGE
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
    """A later tier may import an earlier one and never the reverse."""
    position = {
        f"{PACKAGE}.models": 0,
        f"{PACKAGE}.policy": 1,
        f"{PACKAGE}.sizing": 2,
        f"{PACKAGE}.approval": 3,
        f"{PACKAGE}.reading": 4,
        f"{PACKAGE}.render": 4,
        f"{PACKAGE}.inputs": 5,
        f"{PACKAGE}.compose": 6,
    }
    for module_name, index in position.items():
        for imported in _imports_of(module_name):
            if imported in position:
                assert position[imported] < index, (module_name, imported)


# --------------------------------------------------------------------------
# The one-way boundary, in both directions.
# --------------------------------------------------------------------------


def test_no_engine_or_domain_package_imports_the_sizing_layer() -> None:
    """The direction is one-way. The day it reverses, an engine's analysis could
    become a function of how large a position the owner may take."""
    offenders: dict[str, set[str]] = {}
    for package_name in sorted(MARKET_HALF - {"fmis.today", "fmis.pipeline"}) + [
        "fmis.portfolio_risk",
        "fmis.valuation",
        "fmis.trade_capture",
        "fmis.persistence",
        "fmis.plan",
        "fmis.risk",
    ]:
        for module_name in _modules_of(package_name):
            reached = {
                name for name in _imports_of(module_name) if name.startswith(PACKAGE)
            }
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_only_the_cli_and_the_workspace_builder_import_it_from_above() -> None:
    """Two consumers, both named. `fmits approve` is the surface and `fmits
    today` is the page that shows an approval per candidate."""
    reaching = {
        module_name
        for package_name in ("fmis.pipeline", "fmis.today")
        for module_name in _modules_of(package_name)
        if any(name.startswith(PACKAGE) for name in _imports_of(module_name))
    }
    assert reaching == {"fmis.pipeline.cli", "fmis.today.builder"}


def test_the_cli_still_opens_no_store_of_its_own() -> None:
    """`fmits approve` parses no price and constructs no `AccountId`: every
    conversion lives in `position_sizing.inputs`, where it can be tested without
    a parser."""
    used = _names_used("fmis.pipeline.cli")
    assert "TradingStore" not in used
    assert "AccountId" not in used
    assert "PositionProposal" not in used
