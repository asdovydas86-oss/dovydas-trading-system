"""Milestone BU — the boundary `fmis.macro` occupies, asserted.

The milestone's central architectural claim is that **macro context is not a
trading feature and does not depend on one**. The same facts must serve an
equity thesis, an ETF or sector review, a country analysis and a portfolio risk
review — none of which have any business importing a trade plan. So the
dependencies this package may *not* have are named one by one, and the direction
is guarded both ways:

* **Nothing below imports it.** No engine, no domain package, no store module,
  no swing surface, and no `fmis.pipeline` module except its own composition
  root and `cli.py`.
* **It imports no provider, no store, no swing decision and no AI machinery.**
  Both providers terminate in `fmis.pipeline.market_data`.
* **It reuses rather than reimplements.** No second benchmark registry, no
  second return formula, no second correlation, no hand-rolled alignment.
* **It writes nothing and reads no clock.**

The regression half re-asserts that BU changed nothing about BT, BS, BR, BG-D1
or BP beyond the integration it deliberately made.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pathlib
import pkgutil
import subprocess
import sys

import pytest

import fmis
import fmis.macro

SRC = pathlib.Path(fmis.__file__).parent
MACRO = "fmis.macro"
ROOT = "fmis.pipeline.macro"
DISPATCH = "fmis.pipeline.market_data"

#: Every package that reads a candle. Copied deliberately rather than imported,
#: so adding a package to either list is a visible edit in both places — the
#: discipline `test_today_architecture` and `test_market_pulse_architecture`
#: both record.
MARKET_HALF = (
    "fmis.data", "fmis.ingest", "fmis.providers", "fmis.features",
    "fmis.alignment", "fmis.relative_value", "fmis.series_context",
    "fmis.market_structure", "fmis.structural_trend", "fmis.structure_break",
    "fmis.change_of_character", "fmis.level_crossing", "fmis.market_regime",
    "fmis.evidence", "fmis.decision_support", "fmis.decision_context",
    "fmis.swing_setup", "fmis.workspace", "fmis.daily", "fmis.archive",
    "fmis.trading_context", "fmis.market_pulse",
)

DOMAIN = (
    "fmis.records", "fmis.provenance", "fmis.money", "fmis.versioning",
    "fmis.accounts", "fmis.analysis_record", "fmis.snapshotting",
    "fmis.proposal", "fmis.ledger", "fmis.positions", "fmis.portfolio",
    "fmis.risk", "fmis.journal",
)

SURFACES = (
    "fmis.today", "fmis.swing_workspace", "fmis.setup_evidence",
    "fmis.setup_observation", "fmis.trade_capture", "fmis.position_sizing",
    "fmis.paper", "fmis.trade_lifecycle", "fmis.statistics", "fmis.valuation",
    "fmis.portfolio_risk", "fmis.marks", "fmis.plan", "fmis.persistence",
)

#: Everything `fmis.macro` is permitted to import. Named one by one: a package
#: appearing here later is a deliberate act with a justification, not a drift.
#: Four entries, and each is a layer that already had tests over its own
#: behaviour before this milestone existed.
PERMITTED = (
    "fmis.data",
    "fmis.alignment",
    "fmis.relative_value",
    "fmis.market_pulse",
    "fmis.macro",
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


def test_no_engine_domain_or_surface_package_imports_this_one() -> None:
    """*Macro context must be usable by consumers that know nothing about it.*"""
    offenders: dict[str, set[str]] = {}
    for package_name in MARKET_HALF + DOMAIN + SURFACES:
        for module_name in _modules_of(package_name):
            reached = _reaches(module_name, MACRO)
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_only_the_composition_root_and_the_cli_import_it_from_the_pipeline() -> None:
    importers = {
        module_name
        for module_name in _modules_of("fmis.pipeline")
        if _reaches(module_name, MACRO)
    }
    assert importers == {ROOT, "fmis.pipeline.cli"}


def test_the_swing_workspace_does_not_consume_macro_context() -> None:
    """*Do NOT allow macro data to alter CONFIRMED, CANDIDATE, WAIT, setup
    ranking, position sizing or approval in BU.*

    The seam is deliberately unbuilt. If a future milestone wires macro to a
    setup as a separate evidence domain, this test is the deliberate edit.
    """
    for package_name in ("fmis.swing_workspace", "fmis.today", "fmis.setup_evidence"):
        for module_name in _modules_of(package_name):
            assert _reaches(module_name, MACRO) == set(), module_name
            assert _reaches(module_name, ROOT) == set(), module_name


# --------------------------------------------------------------------------
# What this package may import
# --------------------------------------------------------------------------


def test_the_package_imports_nothing_outside_its_permitted_set() -> None:
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(MACRO):
        reached = {
            name
            for name in _imports_of(module_name)
            if name.startswith("fmis")
            and not any(
                name == allowed or name.startswith(f"{allowed}.")
                for allowed in PERMITTED
            )
        }
        if reached:
            offenders[module_name] = reached
    assert offenders == {}


@pytest.mark.parametrize(
    "forbidden",
    [
        "fmis.plan",
        "fmis.position_sizing",
        "fmis.paper",
        "fmis.trade_lifecycle",
        "fmis.swing_setup",
        "fmis.proposal",
        "fmis.today",
        "fmis.swing_workspace",
        "fmis.setup_evidence",
        "fmis.decision_context",
        "fmis.decision_support",
        "fmis.persistence",
        "fmis.archive",
        "fmis.providers",
        "fmis.ingest",
        "fmis.marks",
        "fmis.valuation",
        "fmis.portfolio_risk",
        "fmis.statistics",
        "fmis.market_regime",
        "fmis.journal",
        "fmis.ledger",
        "fmis.accounts",
    ],
)
def test_the_package_never_imports_a_named_forbidden_dependency(
    forbidden: str,
) -> None:
    """*A macro context describes markets; it does not describe whether to trade
    one.* Each of these is named in the milestone brief; each is asserted."""
    for module_name in _modules_of(MACRO):
        assert _reaches(module_name, forbidden) == set(), module_name


def test_the_package_imports_no_provider_and_no_transport() -> None:
    """*The macro core must not become provider-shaped.*"""
    for module_name in _modules_of(MACRO):
        tree = ast.parse(_source_of(module_name))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        for banned in (
            "fetch_klines",
            "fetch_observations",
            "urlopen",
            "urlopen_transport",
            "requests",
            "urllib",
        ):
            assert banned not in names, (module_name, banned)


def test_the_package_names_no_provider_specific_symbol_or_endpoint() -> None:
    """*Provider-specific symbols, endpoints and payloads terminate at adapters.*

    A FRED series id or a Binance pair appearing in the macro core would mean
    the core had learned a provider's vocabulary.
    """
    for module_name in _modules_of(MACRO):
        source = _source_of(module_name)
        for banned in ("DGS10", "SP500", "VIXCLS", "DTWEXBGS", "BTCUSDT", "fredgraph"):
            assert banned not in source, (module_name, banned)


def test_the_package_imports_no_ai_or_llm_machinery() -> None:
    """*BU stops before interpretation, and there is nothing here to cross that
    line with.*"""
    for module_name in _modules_of(MACRO):
        reached = _imports_of(module_name)
        for banned in ("anthropic", "openai", "llm", "prompt"):
            assert not any(name.startswith(banned) for name in reached), module_name


def test_the_composition_root_imports_exactly_the_seams_it_needs() -> None:
    reached = {name for name in _imports_of(ROOT) if name.startswith("fmis")}
    assert reached == {
        "fmis.data.observation",
        "fmis.macro",
        "fmis.market_pulse",
        DISPATCH,
    }


# --------------------------------------------------------------------------
# It reuses rather than reimplements
# --------------------------------------------------------------------------


def test_there_is_exactly_one_benchmark_registry_in_the_repository() -> None:
    """*Reuse BT's registry. Do not create a second one.*"""
    for module_name in _modules_of(MACRO):
        source = _source_of(module_name)
        assert "MarketUniverse(" not in source, module_name
        assert "ProviderInstrument(" not in source, module_name
        assert "Benchmark(" not in source, module_name


def test_the_package_writes_no_return_volatility_or_correlation_formula() -> None:
    """Every price-like number is `fmis.relative_value`'s.

    A formula here would be a number no engine's tests could be held to. The
    scan is for the shapes those formulas take rather than for their names.
    """
    for module_name in _modules_of(MACRO):
        source = _source_of(module_name)
        for banned in ("math.sqrt", "stdev", "variance", "fsum", "** 2", "**2"):
            assert banned not in source, (module_name, banned)


def test_the_package_never_intersects_two_series_by_hand() -> None:
    """*Alignment is `fmis.alignment`'s.* A hand-rolled intersection would be a
    second alignment policy with no diagnostics and no tests."""
    for module_name in _modules_of(MACRO):
        source = _source_of(module_name)
        for banned in ("set(", "&", "intersection"):
            if banned == "&" and "align" not in source:
                continue
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitAnd):
                raise AssertionError(f"{module_name} intersects by hand")


def test_only_the_rates_module_computes_a_yield_difference() -> None:
    """The one genuinely new quantity lives in one module, with its own tests."""
    scale = "BASIS_POINTS_PER_PERCENTAGE_POINT"
    holders = [
        module_name
        for module_name in _modules_of(MACRO)
        if scale in _source_of(module_name) and module_name != MACRO
    ]
    assert holders == ["fmis.macro.rates"]


def test_no_module_outside_rates_holds_a_basis_point_scale_literal() -> None:
    """Hostile review: *bp scale 10000 vs the wrong scale.* A second literal
    anywhere would be a second scale nobody reconciled."""
    for module_name in _modules_of(MACRO):
        if module_name == "fmis.macro.rates":
            continue
        source = _source_of(module_name)
        assert "10_000" not in source, module_name
        assert "10000" not in source, module_name


# --------------------------------------------------------------------------
# It computes no market quantity outside its own engine, writes nothing,
# reads no clock
# --------------------------------------------------------------------------


def _executable_tree(module_name: str) -> ast.Module:
    """The module with every type annotation removed.

    `float | None` is an `ast.BinOp` carrying `BitOr`, so a naive arithmetic
    scan reports every optional annotation as a computation. Stripping them is
    what makes the assertion *"this module performs no arithmetic"* honest.
    """
    tree = ast.parse(_source_of(module_name))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AnnAssign, ast.arg)):
            node.annotation = None
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.returns = None
    return tree


#: What each module is permitted to compute, spelled exactly. Comparability
#: decides *whether*, never *what*; the models validate; the root composes.
#: **None of these is a market quantity** — no price, return, volatility,
#: correlation or yield difference is computed in any of them, and that is the
#: rule these entries preserve rather than weaken.
_PERMITTED_ARITHMETIC: dict[str, set[str]] = {
    # Joining a refusal's reasons into one sentence. String concatenation.
    "fmis.macro.comparability": {
        '"not comparable: " + ", ".join(\n'
        "            reason.value.replace(\"_\", \" \") for reason in self.reasons\n"
        "        )"
    },
    # The set of markets the report failed to account for. A set difference.
    "fmis.macro.models": {"expected - answered"},
    ROOT: set(),
}


@pytest.mark.parametrize(
    "module_name", ["fmis.macro.comparability", "fmis.macro.models", ROOT]
)
def test_the_deciding_and_composing_modules_compute_no_market_quantity(
    module_name: str,
) -> None:
    found = {
        ast.get_source_segment(_source_of(module_name), node)
        for node in ast.walk(_executable_tree(module_name))
        if isinstance(node, (ast.BinOp, ast.AugAssign))
    }
    permitted = _PERMITTED_ARITHMETIC[module_name]
    assert found <= permitted, sorted(found - permitted)


def test_the_assembly_module_computes_only_window_selection() -> None:
    """`context.py` is permitted arithmetic, and exactly which is pinned here.

    Selecting the last N observations is index arithmetic, not a market
    quantity: no price, return, volatility, correlation or yield difference is
    computed here — each comes from an engine.
    """
    # `-count` and `-1` are **index** arithmetic — taking the last N
    # observations and the last one. Neither is a market quantity.
    permitted = {"-count", "-1"}
    source = _source_of("fmis.macro.context")
    found = {
        ast.get_source_segment(source, node)
        for node in ast.walk(_executable_tree("fmis.macro.context"))
        if isinstance(node, (ast.BinOp, ast.AugAssign, ast.UnaryOp))
        and not isinstance(getattr(node, "op", None), ast.Not)
    }
    assert found <= permitted, sorted(found - permitted)


def test_the_renderer_scales_only_the_percent_and_the_page_width() -> None:
    permitted = {
        "fraction * _PERCENT_SCALE",
        "char * MACRO_PAGE_WIDTH",
        "indent + _INDENT",
        "_INDENT + _INDENT",
    }
    source = _source_of("fmis.macro.render")
    found = {
        ast.get_source_segment(source, node)
        for node in ast.walk(_executable_tree("fmis.macro.render"))
        if isinstance(node, (ast.BinOp, ast.AugAssign))
    }
    assert found <= permitted, sorted(found - permitted)


def test_nothing_in_this_package_reads_a_clock() -> None:
    """*Two runs over the same observations produce the same report.*"""
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(MACRO) + [ROOT]:
        found = {
            node.attr
            for node in ast.walk(ast.parse(_source_of(module_name)))
            if isinstance(node, ast.Attribute)
            and node.attr in {"now", "utcnow", "today", "monotonic", "time"}
        }
        if found:
            offenders[module_name] = found
    assert offenders == {}


def test_nothing_in_this_package_writes_anything_anywhere() -> None:
    """A macro context is a projection: no store, no cache, no file."""
    banned = {
        "write", "write_text", "write_bytes", "writelines", "open", "mkdir",
        "makedirs", "touch", "unlink", "rmdir", "remove", "rename",
        "append_record", "put", "save", "commit", "flush", "dump",
    }
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(MACRO) + [ROOT]:
        found = set()
        for node in ast.walk(ast.parse(_source_of(module_name))):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            name = (
                target.attr
                if isinstance(target, ast.Attribute)
                else target.id if isinstance(target, ast.Name) else None
            )
            if name in banned:
                found.add(name)
        if found:
            offenders[module_name] = found
    assert offenders == {}


def test_the_package_holds_no_module_level_mutable_state() -> None:
    """`__all__` is exempt: it is a list by the language's own convention."""
    for module_name in _modules_of(MACRO) + [ROOT, DISPATCH]:
        for node in ast.parse(_source_of(module_name)).body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {t.id for t in targets if isinstance(t, ast.Name)}
            if names == {"__all__"}:
                continue
            if isinstance(node.value, (ast.List, ast.Set)):
                raise AssertionError(
                    f"{module_name} holds mutable module state: {sorted(names)}"
                )


def test_the_package_defines_no_repository_and_no_schema_version() -> None:
    """Nothing here is stored, so nothing here is versioned."""
    for module_name in _modules_of(MACRO):
        tree = ast.parse(_source_of(module_name))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                assert "Repository" not in node.name, node.name
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assert "SCHEMA_VERSION" not in target.id, target.id


def test_no_record_kind_was_added() -> None:
    from fmis.persistence import kinds

    for name in dir(kinds):
        assert "macro" not in name.lower()


# --------------------------------------------------------------------------
# Layering, exports, dependencies
# --------------------------------------------------------------------------


def test_no_module_in_this_package_participates_in_an_import_cycle() -> None:
    """Pins the layering order so an intra-package import must point backwards."""
    order = [
        "fmis.macro.rates",
        "fmis.macro.comparability",
        "fmis.macro.models",
        "fmis.macro.context",
        "fmis.macro.render",
    ]
    position = {name: index for index, name in enumerate(order)}
    assert set(order) | {MACRO} == set(_modules_of(MACRO))
    for module_name, index in position.items():
        for imported in _imports_of(module_name):
            if imported in position:
                assert position[imported] < index, (module_name, imported)


def test_every_public_name_is_importable_from_the_package_root() -> None:
    for name in fmis.macro.__all__:
        assert hasattr(fmis.macro, name), name


def test_the_package_exports_no_name_twice() -> None:
    assert len(set(fmis.macro.__all__)) == len(fmis.macro.__all__)


def test_the_package_introduces_no_export_collision() -> None:
    """Checked against every other package's `__all__`, repository-wide."""
    ours = set(fmis.macro.__all__)
    for path in sorted(SRC.iterdir()):
        if not path.is_dir() or not (path / "__init__.py").exists():
            continue
        name = f"fmis.{path.name}"
        if name == MACRO:
            continue
        other = set(getattr(importlib.import_module(name), "__all__", ()))
        assert ours & other == set(), (name, sorted(ours & other))


def test_the_package_adds_no_runtime_dependency() -> None:
    """Standard library only, like every other package in this repository."""
    permitted = {
        "__future__", "collections", "collections.abc", "dataclasses",
        "datetime", "enum", "math", "textwrap", "types", "typing",
    }
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(MACRO):
        third_party = {
            name
            for name in _imports_of(module_name)
            if not name.startswith("fmis") and name not in permitted
        }
        if third_party:
            offenders[module_name] = third_party
    assert offenders == {}


def test_the_new_provider_adds_no_runtime_dependency() -> None:
    """The FRED adapter is `urllib` and `csv`, both standard library."""
    permitted = {
        "__future__", "csv", "io", "urllib", "urllib.error", "urllib.parse",
        "urllib.request", "collections.abc", "dataclasses", "datetime", "typing",
    }
    third_party = {
        name
        for name in _imports_of("fmis.providers.fred")
        if not name.startswith("fmis") and name not in permitted
    }
    assert third_party == set()


def test_the_project_declares_no_new_dependency() -> None:
    text = (SRC.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert "dependencies = []" in text


# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------


def test_this_package_holds_no_directional_vocabulary_of_its_own() -> None:
    """ADR-0028's boundary, applied unchanged and with no exemption taken."""
    banned = {"long", "short", "buy", "sell", "bullish", "bearish"}
    offenders: list[tuple[str, str]] = []
    for module_name in _modules_of(MACRO) + [ROOT]:
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
            if token is not None and token.lower() in banned:
                offenders.append((module_name, token))
    assert offenders == []


def test_this_package_names_no_interpretive_market_state() -> None:
    """*No "risk-on / risk-off". No "tightening / easing".* Identifiers and
    non-docstring string values only, so prose can deny them."""
    banned = {
        "risk_on", "risk_off", "riskon", "riskoff", "tightening", "easing",
        "hawkish", "dovish", "overbought", "oversold", "macro_score",
        "regime_score", "risk_score", "safe_haven",
    }
    offenders: list[tuple[str, str]] = []
    for module_name in _modules_of(MACRO) + [ROOT]:
        tree = ast.parse(_source_of(module_name))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(
                node,
                (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef),
            )
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        for node in ast.walk(tree):
            token = None
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                token = node.name
            elif isinstance(node, ast.Name):
                token = node.id
            elif isinstance(node, ast.arg):
                token = node.arg
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
            ):
                token = node.value
            if token is not None and token.lower().replace(" ", "_") in banned:
                offenders.append((module_name, token))
    assert offenders == []


def test_no_field_anywhere_is_named_score_weight_rank_or_confidence() -> None:
    """*There is no field a second quantity could enter through.*"""
    banned = {
        "score", "weight", "weighting", "rank", "ranking", "confidence",
        "probability", "strength", "grade", "rating", "total", "composite",
        "regime", "signal", "bias",
    }
    offenders: list[tuple[str, str]] = []
    for module_name in _modules_of(MACRO):
        for node in ast.walk(ast.parse(_source_of(module_name))):
            if not isinstance(node, ast.ClassDef):
                continue
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(
                    statement.target, ast.Name
                ):
                    if statement.target.id.lower() in banned:
                        offenders.append((node.name, statement.target.id))
    assert offenders == []


def test_no_type_here_is_named_for_swing_trading() -> None:
    """*Do not name the macro model `SwingMacroContext`.* The same facts must
    serve long-term investing, sector and country analysis."""
    for module_name in _modules_of(MACRO):
        for node in ast.walk(ast.parse(_source_of(module_name))):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                lowered = node.name.lower()
                for banned in ("swing", "setup", "trade", "entry", "stop", "target"):
                    assert banned not in lowered, (module_name, node.name)


# --------------------------------------------------------------------------
# Determinism across processes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", ["0", "1", "12345"])
def test_the_page_is_identical_under_a_different_hash_seed(seed: str) -> None:
    """A set's iteration order must never reach the page. Run in a real
    subprocess, because `PYTHONHASHSEED` is fixed at interpreter start."""
    script = (
        "import sys;"
        "sys.path.insert(0, %r);"
        "from tests.macro_helpers import fred_transport_for, series_ending;"
        "from tests.market_pulse_helpers import instant, linear_klines,"
        " ok_response, transport_for;"
        "from fmis.market_pulse import DEFAULT_PULSE_UNIVERSE, MACRO_PROVIDER;"
        "from fmis.pipeline.market_data import MarketDataSources;"
        "from fmis.pipeline.macro import run_macro_context;"
        "from fmis.macro import render_macro_context;"
        "at = instant(500);"
        "macro = {b.instrument.symbol: series_ending(b.instrument.symbol, at,"
        " base=100.0+i, step=0.5+i, count=60)"
        " for i, b in enumerate(DEFAULT_PULSE_UNIVERSE.supported)"
        " if b.instrument.provider == MACRO_PROVIDER};"
        "crypto = {b.instrument.symbol: ok_response(linear_klines(100.0, 1.0+i, 200))"
        " for i, b in enumerate(DEFAULT_PULSE_UNIVERSE.supported)"
        " if b.instrument.provider != MACRO_PROVIDER};"
        "report = run_macro_context(as_of=at, sources=MarketDataSources("
        " binance_transport=transport_for(crypto),"
        " fred_transport=fred_transport_for(macro), clock=lambda: at));"
        "print(render_macro_context(report))"
    ) % str(SRC.parent.parent)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        cwd=str(SRC.parent.parent),
    )
    assert result.returncode == 0, result.stderr
    pages = getattr(test_the_page_is_identical_under_a_different_hash_seed, "pages", [])
    test_the_page_is_identical_under_a_different_hash_seed.pages = pages
    pages.append(result.stdout)
    assert pages[0] == result.stdout


# --------------------------------------------------------------------------
# Regression: BU is additive
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "package_name",
    [
        "fmis.swing_workspace",  # BS
        "fmis.setup_evidence",   # BR
        "fmis.proposal",         # BG-D1
        "fmis.statistics",       # BP
        "fmis.paper",            # BO
        "fmis.trade_lifecycle",  # BO
        "fmis.position_sizing",  # BN
        "fmis.today",            # BJ
        "fmis.market_pulse",     # BT
    ],
)
def test_no_earlier_milestone_s_package_gained_a_dependency_on_this_one(
    package_name: str,
) -> None:
    for module_name in _modules_of(package_name):
        assert _reaches(module_name, MACRO) == set(), module_name
        assert _reaches(module_name, ROOT) == set(), module_name


def test_the_pulse_package_still_imports_nothing_it_did_not_before() -> None:
    """BU extended `fmis.market_pulse` with cross-asset vocabulary; it did not
    give it a new dependency."""
    permitted = ("fmis.data", "fmis.relative_value", "fmis.market_pulse")
    for module_name in _modules_of("fmis.market_pulse"):
        reached = {
            name
            for name in _imports_of(module_name)
            if name.startswith("fmis")
            and not any(
                name == allowed or name.startswith(f"{allowed}.")
                for allowed in permitted
            )
        }
        assert reached == set(), module_name


def test_the_dispatch_layer_is_where_both_providers_terminate() -> None:
    for module_name in _modules_of(MACRO):
        assert _reaches(module_name, "fmis.providers") == set(), module_name
    reached = _reaches(DISPATCH, "fmis.providers")
    assert reached == {"fmis.providers.binance", "fmis.providers.fred"}
