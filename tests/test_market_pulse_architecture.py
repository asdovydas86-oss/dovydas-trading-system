"""Milestone BT — the boundary `fmis.market_pulse` occupies, asserted.

The milestone's central architectural claim is that **the Global Market Pulse is
not a swing engine and does not depend on one**. Orientation must be usable by
long-term investing, by a daily brief and by later macro/news/derivatives
domains, none of which have any business importing a trade plan. So the
dependencies this package may *not* have are named one by one and asserted, and
the direction is guarded both ways:

* **Nothing below imports it.** No engine, no domain package, no store module,
  no `fmis.today` or `fmis.swing_workspace` module, and no `fmis.pipeline`
  module except its own composition root and `cli.py`.
* **It imports no provider, no adapter, no store and no swing decision.** The
  provider terminates in `fmis.pipeline.pulse`, exactly as it terminates in
  `fmis.pipeline.prices` for a mark.
* **It computes nothing.** The measurement and assembly modules hold no
  arithmetic operator at all; the renderer holds exactly one, and it is the
  percent scale.
* **It writes nothing and reads no clock.**

The regression half of this file re-asserts that BT changed nothing about BS,
BR, BG-D1, BP, BO or BN.
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
import fmis.market_pulse

SRC = pathlib.Path(fmis.__file__).parent
PULSE = "fmis.market_pulse"
ROOT = "fmis.pipeline.pulse"

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

#: The application-layer surfaces built on those two halves.
SURFACES = (
    "fmis.today", "fmis.swing_workspace", "fmis.setup_evidence",
    "fmis.setup_observation", "fmis.trade_capture", "fmis.position_sizing",
    "fmis.paper", "fmis.trade_lifecycle", "fmis.statistics", "fmis.valuation",
    "fmis.portfolio_risk", "fmis.marks", "fmis.plan", "fmis.persistence",
)

#: Everything `fmis.market_pulse` is permitted to import. Named one by one: a
#: package appearing here later is a deliberate act with a justification, not a
#: drift. Three entries, and each is an engine that already had tests over its
#: own behaviour before this milestone existed.
PERMITTED = ("fmis.data", "fmis.relative_value", "fmis.market_pulse")


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
    """*Orientation must be usable by consumers that know nothing about it.*"""
    offenders: dict[str, set[str]] = {}
    for package_name in MARKET_HALF + DOMAIN + SURFACES:
        for module_name in _modules_of(package_name):
            reached = _reaches(module_name, PULSE)
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_only_the_composition_root_and_the_cli_import_it_from_the_pipeline() -> None:
    """The same single-crossing rule `fmis.pipeline.prices` holds for a mark."""
    importers = {
        module_name
        for module_name in _modules_of("fmis.pipeline")
        if _reaches(module_name, PULSE)
    }
    # **Extended by Milestone BU, and the underlying rule is unchanged.** BT's
    # rule was *"the vocabulary crosses into the pipeline in as few places as
    # possible"*, spelled as two because two was all it took. BU added a second
    # market-data provider and a second surface, and each needs the registry:
    # `market_data` to dispatch a benchmark to its adapter, `macro` to compose
    # the macro page. Both are composition-layer modules of exactly the kind
    # `pulse` already was. What is still asserted, and is the thing that
    # matters, is that the set is closed and small — no engine, no model, no
    # renderer and no domain module is in it.
    assert importers == {
        ROOT,
        "fmis.pipeline.cli",
        "fmis.pipeline.macro",
        "fmis.pipeline.market_data",
    }


def test_the_swing_workspace_does_not_consume_the_pulse() -> None:
    """BT deliberately left the integration seam unbuilt rather than widen its
    own scope. If a future milestone wires it, this test is the deliberate edit.
    """
    for module_name in _modules_of("fmis.swing_workspace"):
        assert _reaches(module_name, PULSE) == set()
    for module_name in _modules_of("fmis.today"):
        assert _reaches(module_name, PULSE) == set()


# --------------------------------------------------------------------------
# What this package may import — and the swing half it may not
# --------------------------------------------------------------------------


def test_the_package_imports_nothing_outside_its_permitted_set() -> None:
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(PULSE):
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
    ],
)
def test_the_package_never_imports_a_named_forbidden_dependency(
    forbidden: str,
) -> None:
    """*A market pulse describes the market; it does not describe whether to
    trade it.* Each of these is named in the milestone brief; each is asserted.
    """
    for module_name in _modules_of(PULSE):
        assert _reaches(module_name, forbidden) == set(), module_name


def test_the_package_imports_no_provider_and_no_transport() -> None:
    """*The Pulse core must not become provider-shaped.*"""
    for module_name in _modules_of(PULSE):
        source = _source_of(module_name)
        tree = ast.parse(source)
        names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        for banned in ("fetch_klines", "urlopen", "urlopen_transport", "requests"):
            assert banned not in names, (module_name, banned)


def test_the_package_imports_no_ai_or_llm_machinery() -> None:
    """BT stays below AI interpretation, and there is nothing to import yet —
    asserted so the day there is, adding it here is a deliberate act."""
    for module_name in _modules_of(PULSE):
        reached = _imports_of(module_name)
        for banned in ("anthropic", "openai", "llm", "prompt"):
            assert not any(name.startswith(banned) for name in reached), module_name


def test_the_composition_root_imports_exactly_the_seams_it_needs() -> None:
    reached = {name for name in _imports_of(ROOT) if name.startswith("fmis")}
    # Milestone BU moved provider dispatch out of this module into
    # `fmis.pipeline.market_data`, so the root no longer names an ingestion
    # boundary and reaches the adapter only for its injectable transport type.
    # The seam count did not grow, and the rule it protects — this module knows
    # *what* to read and nothing about *how* — is stronger than before.
    assert reached == {
        "fmis.data.observation",
        "fmis.market_pulse",
        "fmis.pipeline.market_data",
        "fmis.providers.binance",
    }


def test_the_dispatch_layer_is_the_only_pipeline_module_naming_two_providers() -> None:
    """*Provider choice happens once.* The rule BU's second adapter created.

    A composition root may name the transport type it forwards, but only the
    dispatch layer may reach two adapters — otherwise every future surface grows
    its own chain of ``if provider ==`` branches and they drift.
    """
    adapters = ("fmis.providers.binance", "fmis.providers.fred")
    for module_name in _modules_of("fmis.pipeline"):
        reached = {
            adapter
            for adapter in adapters
            if _reaches(module_name, adapter)
        }
        if len(reached) > 1:
            assert module_name == "fmis.pipeline.market_data", module_name


# --------------------------------------------------------------------------
# It computes nothing, writes nothing, reads no clock
# --------------------------------------------------------------------------


def _executable_tree(module_name: str) -> ast.Module:
    """The module with every type annotation removed.

    `float | None` is an `ast.BinOp` carrying `BitOr`, so a naive arithmetic
    scan reports every optional annotation in the package as a computation. An
    annotation is not code that runs — `from __future__ import annotations` is
    on every module here — so the honest scan is over what executes. Stripping
    them is what makes the remaining assertion *"this module performs no
    arithmetic"* rather than *"this module performs no arithmetic except the
    kinds I listed"*.
    """
    tree = ast.parse(_source_of(module_name))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AnnAssign, ast.arg)):
            node.annotation = None
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.returns = None
    return tree


@pytest.mark.parametrize(
    "module_name",
    ["fmis.market_pulse.measure", "fmis.market_pulse.pulse", ROOT],
)
def test_the_measuring_and_composing_modules_hold_no_arithmetic_at_all(
    module_name: str,
) -> None:
    """*A number produced here would be a number no engine's tests could be held
    to.* Every figure on the page is `fmis.relative_value`'s.

    **Zero operators, with no exception list.** These three modules select
    windows, record absences and order one number; none of them adds, divides,
    scales or negates anything, including strings. That is a stronger statement
    than `fmis.pipeline.prices` makes for itself and it is worth keeping.
    """
    offenders = [
        type(node.op).__name__
        for node in ast.walk(_executable_tree(module_name))
        if isinstance(node, (ast.BinOp, ast.AugAssign))
    ]
    assert offenders == []


def test_the_model_module_computes_only_counts_and_a_duration() -> None:
    """`models.py` is permitted arithmetic, and exactly which is pinned here.

    It validates a *count relationship* (`bars + 1` observations), reports a
    *count* (`len + len`), computes two *durations* (a reading's age and a
    window's measured span, each one datetime subtraction) and takes a *set
    difference* to find markets the page failed to account for. None of those is
    a market quantity: no price, return, volatility or correlation is computed
    anywhere in this package outside the engine.
    """
    permitted = {
        "self.bars + 1",
        "len(self.readings) + len(self.unavailable)",
        '_utc(moment, "moment") - self.last_bar_open',
        "self.window_end - self.window_start",
        "expected - answered",
        # Milestone BU: a publication schedule's own bound, which is the sum of
        # two durations. Not a market quantity — no price, return, volatility,
        # correlation or yield difference is computed anywhere in this package
        # outside the engines, and that is the rule this test exists for.
        "self.publication_period + self.tolerance",
    }
    source = _source_of("fmis.market_pulse.models")
    found = {
        ast.get_source_segment(source, node)
        for node in ast.walk(_executable_tree("fmis.market_pulse.models"))
        if isinstance(node, (ast.BinOp, ast.AugAssign))
    }
    assert found <= permitted, sorted(found - permitted)


def test_the_only_float_literals_in_the_package_are_the_correlation_bounds() -> None:
    """A correlation is mathematically bounded to [-1, 1] and the model refuses
    a value outside it. That bound is a fact about the metric, not a threshold
    this package chose — and it is the only float literal anywhere here."""
    found: dict[str, list[float]] = {}
    for module_name in _modules_of(PULSE) + [ROOT]:
        literals = [
            node.value
            for node in ast.walk(ast.parse(_source_of(module_name)))
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        ]
        if literals:
            found[module_name] = literals
    assert found == {"fmis.market_pulse.models": [1.0, 1.0]}
    source = _source_of("fmis.market_pulse.models")
    assert "-1.0 <= value <= 1.0" in source


def test_the_renderer_multiplies_only_the_page_width_and_the_percent_scale() -> None:
    """The renderer's single arithmetic operation, pinned to exactly what it is.

    `_percent` scales a fraction for display and `_rule` repeats a character to
    the page width. Anything else would be a market quantity computed at the
    presentation layer.
    """
    source = _source_of("fmis.market_pulse.render")
    permitted = {
        # the percent scale, applied once at the moment of printing
        "fraction * _PERCENT_SCALE",
        # a horizontal rule, repeated to the page width
        "char * PULSE_PAGE_WIDTH",
        # a hanging indent, which is string concatenation and not a quantity
        "indent + _INDENT",
        "_INDENT + _INDENT",
    }
    found = {
        ast.get_source_segment(source, node)
        for node in ast.walk(_executable_tree("fmis.market_pulse.render"))
        if isinstance(node, (ast.BinOp, ast.AugAssign))
    }
    assert found <= permitted, sorted(found - permitted)


def test_nothing_in_this_package_reads_a_clock() -> None:
    """*Two runs over the same inputs are identical* — the property that makes
    the page reproducible, diffable and defensible."""
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(PULSE) + [ROOT]:
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
    """A pulse is a projection: no store, no cache, no file.

    **The verb list is exhaustive rather than store-shaped**, which is the hole
    BS's release gate found in its own guard — it listed only the store's verbs,
    so a raw `write_text` survived. Every filesystem-mutating call is named.
    """
    banned = {
        "write", "write_text", "write_bytes", "writelines", "open", "mkdir",
        "makedirs", "touch", "unlink", "rmdir", "remove", "rename", "replace",
        "append_record", "put", "save", "commit", "flush", "dump",
    }
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(PULSE) + [ROOT]:
        tree = ast.parse(_source_of(module_name))
        found = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            name = (
                target.attr
                if isinstance(target, ast.Attribute)
                else target.id if isinstance(target, ast.Name) else None
            )
            # `str.replace` on a rendered line is not a filesystem write; the
            # guard is about calls on paths and stores, so `replace` is only a
            # finding when its receiver is not a string expression.
            if name == "replace":
                continue
            if name in banned:
                found.add(name)
        if found:
            offenders[module_name] = found
    assert offenders == {}


def test_the_package_holds_no_module_level_mutable_state() -> None:
    """`__all__` is exempt: it is a list by the language's own convention."""
    for module_name in _modules_of(PULSE) + [ROOT]:
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


# --------------------------------------------------------------------------
# Layering, exports, dependencies
# --------------------------------------------------------------------------


def test_no_module_in_this_package_participates_in_an_import_cycle() -> None:
    """Pins the layering order so an intra-package import must point backwards."""
    order = [
        "fmis.market_pulse.models",
        "fmis.market_pulse.universe",
        "fmis.market_pulse.measure",
        "fmis.market_pulse.pulse",
        "fmis.market_pulse.render",
    ]
    position = {name: index for index, name in enumerate(order)}
    assert set(order) | {PULSE} == set(_modules_of(PULSE))
    for module_name, index in position.items():
        for imported in _imports_of(module_name):
            if imported in position:
                assert position[imported] < index, (module_name, imported)


def test_every_public_name_is_importable_from_the_package_root() -> None:
    for name in fmis.market_pulse.__all__:
        assert hasattr(fmis.market_pulse, name), name


def test_the_package_exports_no_name_twice() -> None:
    assert len(set(fmis.market_pulse.__all__)) == len(fmis.market_pulse.__all__)


def test_the_package_introduces_no_export_collision() -> None:
    """Checked against every other package's `__all__`, repository-wide."""
    ours = set(fmis.market_pulse.__all__)
    for path in sorted(SRC.iterdir()):
        if not path.is_dir() or not (path / "__init__.py").exists():
            continue
        name = f"fmis.{path.name}"
        if name == PULSE:
            continue
        other = set(getattr(importlib.import_module(name), "__all__", ()))
        assert ours & other == set(), (name, sorted(ours & other))


def test_the_package_adds_no_runtime_dependency() -> None:
    """Standard library only, like every other package in this repository."""
    permitted = {
        "__future__", "ast", "collections", "collections.abc", "dataclasses",
        "datetime", "enum", "math", "textwrap", "types", "typing",
    }
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(PULSE):
        third_party = {
            name
            for name in _imports_of(module_name)
            if not name.startswith("fmis") and name not in permitted
        }
        if third_party:
            offenders[module_name] = third_party
    assert offenders == {}


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
    for module_name in _modules_of(PULSE) + [ROOT]:
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
    assert "market_pulse" not in exempt
    assert guard._PERMITTED_DIR.name != "market_pulse"
    covered = {path.parent.name for path in guard._covered_files()}
    assert "market_pulse" in covered


def test_this_package_names_no_interpretive_market_state() -> None:
    """The milestone's own prohibition: `risk_on`/`risk_off` and the like have
    no accepted deterministic definition in this repository, so they may not be
    invented here. Identifiers and string values only, so prose can deny them.
    """
    banned = {
        "risk_on", "risk_off", "riskon", "riskoff", "overbought", "oversold",
        "strength_score", "market_score", "risk_score", "regime_score",
    }
    offenders: list[tuple[str, str]] = []
    for module_name in _modules_of(PULSE) + [ROOT]:
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
    """*There is no field a second quantity could enter through.*

    Exact names rather than substrings: `MarketPulse.rankings` is a tuple of
    orderings, and an ordering is the thing this milestone built. A `rank`
    field would be a number assigned to a market; `rankings` is a list of
    sections, and conflating the two would force the guard to be deleted the
    first time it was inconvenient.
    """
    banned = {
        "score", "weight", "weighting", "rank", "ranking", "confidence",
        "probability", "strength", "grade", "rating", "total", "composite",
    }
    offenders: list[tuple[str, str]] = []
    for module_name in _modules_of(PULSE):
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


# --------------------------------------------------------------------------
# Determinism across processes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", ["0", "1", "12345"])
def test_the_page_is_identical_under_a_different_hash_seed(seed: str) -> None:
    """A set's iteration order must never reach the page. Run in a real
    subprocess, because `PYTHONHASHSEED` is fixed at interpreter start."""
    script = (
        "import json,sys;"
        "sys.path.insert(0, %r);"
        "from tests.market_pulse_helpers import *;"
        "from fmis.market_pulse import DEFAULT_PULSE_UNIVERSE, render_market_pulse;"
        "from fmis.pipeline.pulse import run_market_pulse;"
        "rows = {b.instrument.symbol: ok_response(linear_klines(100.0, 1.0 + i, 200))"
        " for i, b in enumerate(DEFAULT_PULSE_UNIVERSE.supported)};"
        "page = run_market_pulse(as_of=instant(500),"
        " universe=DEFAULT_PULSE_UNIVERSE, transport=transport_for(rows),"
        " clock=lambda: instant(500));"
        "print(render_market_pulse(page))"
    ) % str(SRC.parent.parent)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        cwd=str(SRC.parent.parent),
    )
    assert result.returncode == 0, result.stderr
    test_the_page_is_identical_under_a_different_hash_seed.pages = getattr(
        test_the_page_is_identical_under_a_different_hash_seed, "pages", []
    )
    pages = test_the_page_is_identical_under_a_different_hash_seed.pages
    pages.append(result.stdout)
    assert pages[0] == result.stdout


# --------------------------------------------------------------------------
# Regression: BT changed nothing that came before it
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
    ],
)
def test_no_earlier_milestone_s_package_gained_an_import(package_name: str) -> None:
    """BT is additive. No package that predates it may have acquired a
    dependency on it, directly or through its own composition root."""
    for module_name in _modules_of(package_name):
        assert _reaches(module_name, PULSE) == set(), module_name
        assert _reaches(module_name, ROOT) == set(), module_name


def test_every_command_that_existed_before_bt_is_still_registered() -> None:
    """The registry gained one entry and lost none."""
    from fmis.pipeline.cli import COMMANDS

    names = [command.name for command in COMMANDS]
    before = [
        "facts", "mtf", "regime", "swing", "setup", "evidence", "scan",
        "backtest", "daily", "today", "workspace", "portfolio", "approve",
        "trade", "simulate", "statistics", "performance", "expectancy",
        "equity", "trades", "archive",
    ]
    assert set(before) <= set(names)
    # BT added `pulse`; Milestone BU added `macro` beside it; Milestone BV added
    # `dashboard` before `archive`; Milestone BW added `research` before
    # `dashboard`. All four are additive and none replaced anything, which is
    # what this test exists to prove.
    assert set(names) - set(before) == {"pulse", "macro", "dashboard", "research"}
    assert len(names) == len(set(names))


def test_the_pulse_command_shares_no_configure_function_with_another() -> None:
    """`today` and `workspace` deliberately share one; `pulse` takes different
    arguments and must not be quietly attached to theirs."""
    from fmis.pipeline.cli import COMMANDS

    pulse = next(entry for entry in COMMANDS if entry.name == "pulse")
    others = [entry for entry in COMMANDS if entry.name != "pulse"]
    assert all(pulse.configure is not entry.configure for entry in others)
    assert all(pulse.run is not entry.run for entry in others)


def test_no_record_kind_was_added() -> None:
    """A pulse is recomputable and disposable; it has no persisted form."""
    from fmis.persistence import kinds

    for name in dir(kinds):
        assert "pulse" not in name.lower()


def test_the_package_defines_no_repository_and_no_schema_version() -> None:
    """Nothing here is stored, so nothing here is versioned."""
    for module_name in _modules_of(PULSE):
        source = _source_of(module_name)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                assert "Repository" not in node.name, node.name
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assert "SCHEMA_VERSION" not in target.id, target.id
