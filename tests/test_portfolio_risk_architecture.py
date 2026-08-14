"""Boundary guards for `fmis.portfolio_risk`.

These do not exercise behaviour. They assert the rules the milestone rests on, in
the only form that survives a refactor: an executable check over the source tree.

**The venue-agnostic proof is here and nowhere else.** A design document claiming
FMITS is not Binance-centric is a claim; a test that fails the moment a provider
import appears in portfolio math is the guarantee. The same test covers
TradingView, every market-half engine and every future execution adapter, because
the check is *"which packages does this reach"* rather than a list of names
somebody has to remember to extend.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest

import fmis

PACKAGE = "fmis.portfolio_risk"
SOURCE_ROOT = Path(fmis.__file__).parent

#: Every package that reads a candle, reaches a venue or renders a chart. Copied
#: deliberately rather than imported, so adding one is a visible edit in each
#: guard that cares — the convention `tests/test_trade_capture_architecture.py`
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
    }
)

#: The module names a venue-specific integration would arrive under. Named
#: explicitly *as well as* covered by `MARKET_HALF`, so the failure message says
#: "a venue leaked into portfolio math" rather than "an engine did".
VENUE_SPECIFIC = frozenset({"fmis.providers", "fmis.providers.binance"})


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

    The distinction matters for the grep-style guards below. A docstring that
    says *"Binance is not special, and the day it becomes special this fails"* is
    the guarantee being documented; a string constant `"binance"` inside a
    function is a venue the code branches on. Grepping the raw source cannot tell
    them apart, so the tree is stripped of docstrings and re-unparsed — which
    drops comments too, and leaves every real string literal in place.
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


PURE_MODULES = [
    f"{PACKAGE}.geometry",
    f"{PACKAGE}.models",
    f"{PACKAGE}.classification",
    f"{PACKAGE}.exposure",
    f"{PACKAGE}.constraints",
    f"{PACKAGE}.impact",
]


# --------------------------------------------------------------------------
# The venue-agnostic guarantee.
# --------------------------------------------------------------------------


def test_no_module_imports_a_venue_provider() -> None:
    """Binance is not special, and the day it becomes special this fails.

    Portfolio and risk logic operates on `MarketId`, `VenueId`, `AccountId`,
    `Book` and `Money`. A provider import here would make one venue's model the
    portfolio's model, and every other venue an adapter problem forever.
    """
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(PACKAGE):
        reached = {
            name
            for name in _imports_of(module_name)
            if name in VENUE_SPECIFIC or name.startswith("fmis.providers")
        }
        if reached:
            offenders[module_name] = reached
    assert offenders == {}


def test_no_module_imports_a_market_half_engine() -> None:
    """A portfolio must not be a function of the analysis. TradingView, the
    scanner, the regime engine and the workspace are all on the far side of this
    line."""
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(PACKAGE):
        reached = _imports_of(module_name) & MARKET_HALF
        if reached:
            offenders[module_name] = reached
    assert offenders == {}


def test_no_module_names_a_venue_in_its_code() -> None:
    """Not even as a default, a fallback or a special case.

    `fmis.trade_capture` legitimately holds `DEFAULT_VENUE = "binance"` because it
    is a *surface* pre-filling a field the owner can change. Portfolio math has no
    such excuse: a venue named here would be a branch some venues take and others
    do not.
    """
    forbidden = ("binance", "evedex", "bybit", "tradingview", "coinbase", "kraken")
    offenders: dict[str, list[str]] = {}
    for module_name in _modules_of(PACKAGE):
        source = _code_only(module_name).lower()
        hits = [needle for needle in forbidden if needle in source]
        if hits:
            offenders[module_name] = hits
    assert offenders == {}


def test_the_package_reaches_only_the_domain_and_the_store() -> None:
    """The whole dependency surface, asserted as a set rather than described."""
    permitted = {
        "fmis.accounts",
        "fmis.ledger",
        "fmis.money",
        "fmis.persistence",
        "fmis.plan",
        "fmis.portfolio",
        "fmis.positions",
        "fmis.provenance",
        "fmis.records",
        "fmis.risk",
        "fmis.snapshotting",
    }
    reached: set[str] = set()
    for module_name in _modules_of(PACKAGE):
        reached |= {
            name
            for name in _imports_of(module_name)
            if name.startswith("fmis.") and not name.startswith(PACKAGE)
        }
    assert reached <= permitted, f"unexpected: {sorted(reached - permitted)}"


def test_every_exposure_axis_is_a_domain_identifier() -> None:
    """The venue is metadata on a `MarketId`, never a field this package owns."""
    from fmis.accounts import MarketId, VenueId
    from fmis.portfolio_risk import ExposureLine

    assert "venue" not in ExposureLine.__dataclass_fields__
    assert ExposureLine.__dataclass_fields__["market"].type in ("MarketId", MarketId)
    assert isinstance(_sample_line().venue, VenueId)


def _sample_line():  # type: ignore[no-untyped-def]
    from portfolio_risk_helpers import line

    return line()


# --------------------------------------------------------------------------
# Purity: only one module touches disk, and it only reads.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", PURE_MODULES)
def test_the_pure_modules_never_import_the_store(module_name: str) -> None:
    """The direction is one-way. The day it reverses, portfolio arithmetic cannot
    be computed without a store to compute it from."""
    reached = {
        name
        for name in _imports_of(module_name)
        if name.startswith("fmis.persistence")
    }
    assert reached == set(), f"{module_name} imports {sorted(reached)}"


@pytest.mark.parametrize("module_name", PURE_MODULES)
def test_the_pure_modules_hold_no_path_no_file_and_no_clock(module_name: str) -> None:
    """A figure that stamped itself could not be pinned in a test, and a portfolio
    that read a clock could not be replayed."""
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


def test_only_the_reading_module_reaches_persistence() -> None:
    reaching = {
        module_name
        for module_name in _modules_of(PACKAGE)
        if any(
            name.startswith("fmis.persistence")
            for name in _imports_of(module_name)
        )
    }
    assert reaching == {f"{PACKAGE}.reading"}


def test_the_reading_module_writes_nothing() -> None:
    """A read path that repaired something would make the store's contents depend
    on who looked at them."""
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
    assert _names_used(f"{PACKAGE}.reading") & forbidden == set()


def test_no_module_reads_a_clock() -> None:
    """`fmis.pipeline.cli` is the only place in this repository that takes the
    time; every instant here is an argument."""
    forbidden = ("datetime.now(", "datetime.utcnow(", "time.time(", "random.")
    offenders: dict[str, list[str]] = {}
    for module_name in _modules_of(PACKAGE):
        source = _source_of(module_name)
        hits = [needle for needle in forbidden if needle in source]
        if hits:
            offenders[module_name] = hits
    assert offenders == {}


# --------------------------------------------------------------------------
# No thresholds, no scores, no verdicts.
# --------------------------------------------------------------------------


def test_the_package_invents_no_threshold() -> None:
    """Every number compared against is the owner's. The precedent is
    `fmis.risk`, which passes the identical test."""
    offenders: dict[str, list[object]] = {}
    for module_name in _modules_of(PACKAGE):
        literals = {
            node.value
            for node in ast.walk(ast.parse(_source_of(module_name)))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        }
        if not literals <= {0, 1}:
            offenders[module_name] = sorted(literals - {0, 1})
    assert offenders == {}


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
    """`AP` §15.2: a single number would collapse all three strata into one value
    whose meaning no one could recover."""
    exported = " ".join(importlib.import_module(PACKAGE).__all__).lower()
    for forbidden in ("score", "grade", "rating", "health", "rank", "index"):
        assert forbidden not in exported, forbidden


def test_no_type_here_can_hold_a_verdict() -> None:
    """This object reports facts. `BUY`, `SELL`, take and reject are the owner's
    conclusion, and there is no field they could be written into."""
    import dataclasses

    from fmis import portfolio_risk

    forbidden = (
        "verdict",
        "decision",
        "recommend",
        "action",
        "signal",
        "advice",
        "should",
    )
    offenders: dict[str, list[str]] = {}
    for name in portfolio_risk.__all__:
        value = getattr(portfolio_risk, name)
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


def test_no_module_names_a_trading_verdict() -> None:
    """A grep-level guard over the source, so a verdict cannot arrive as a string
    constant, an enum member or a docstring promise."""
    forbidden = ("take_trade", "reject_trade", "should_trade", "recommendation")
    offenders: dict[str, list[str]] = {}
    for module_name in _modules_of(PACKAGE):
        source = _code_only(module_name).lower()
        hits = [needle for needle in forbidden if needle in source]
        if hits:
            offenders[module_name] = hits
    assert offenders == {}


def test_the_status_vocabulary_is_the_domains_own_and_is_not_duplicated() -> None:
    """`WITHIN` / `AT_LIMIT` / `EXCEEDED` already exist in `fmis.risk`; a second
    enum would be a second vocabulary two surfaces could disagree about."""
    from fmis.risk import LimitStatus

    from fmis.portfolio_risk import ConstraintResult

    assert "LimitStatus" not in importlib.import_module(PACKAGE).__all__
    assert {member.value for member in LimitStatus} == {
        "within",
        "at_limit",
        "exceeded",
    }
    assert ConstraintResult.__dataclass_fields__["status"] is not None


# --------------------------------------------------------------------------
# Projections stay projections.
# --------------------------------------------------------------------------


def test_nothing_in_this_package_is_a_persisted_record_kind() -> None:
    """A derived portfolio reading must not become authoritative truth. The day
    one does, it needs a `RecordKind`, a spec row and a durability class chosen
    deliberately — not a `to_payload` that happened to be written."""
    from fmis.persistence import SPECS

    from fmis import portfolio_risk

    persisted = {spec.record_type for spec in SPECS.values()}
    for name in portfolio_risk.__all__:
        assert getattr(portfolio_risk, name) not in persisted, name


def test_no_projection_here_has_a_decoder() -> None:
    """`to_payload` without `from_payload` is the shape `Position` already uses:
    exportable, and impossible to read back into the store as truth."""
    from fmis.portfolio_risk import (
        ExposureLine,
        PortfolioConstraintCheck,
        PortfolioImpact,
        PortfolioState,
    )

    for projection in (
        ExposureLine,
        PortfolioState,
        PortfolioConstraintCheck,
        PortfolioImpact,
    ):
        assert hasattr(projection, "to_payload"), projection
        assert not hasattr(projection, "from_payload"), projection


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
    """The repository's zero-collision invariant, re-asserted after BL."""
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
        "collections",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "typing",
        "fmis",
    }
    for module_name in _modules_of(PACKAGE):
        for name in _imports_of(module_name):
            assert name.split(".")[0] in allowed_roots, f"{module_name}: {name}"


def test_there_are_no_import_cycles_inside_the_package() -> None:
    """A cycle here would mean the arithmetic and the store could not be
    separated, which is the separation the whole layering rests on."""
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
