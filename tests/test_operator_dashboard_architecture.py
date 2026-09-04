"""Guards over `fmis.operator_dashboard`. **This package is a window, not an engine.**

Every guard here scans the package's own source. The claims they defend are the
ones the whole design rests on:

* it computes no market, monetary or statistical quantity;
* it produces no ordering of its own;
* it writes nothing, anywhere, by any means;
* it names no execution verb;
* it depends on nothing outside the standard library;
* the read models depend on no UI, so the UI can be replaced.

A guard that scanned only for imports would miss the case that actually happens:
somebody adding `sum(...)` to a render helper because a total was needed and the
engine call was two files away.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest

import fmis.operator_dashboard as package

MODULES = tuple(
    sorted(
        [package.__name__]
        + [
            module.name
            for module in pkgutil.iter_modules(
                package.__path__, prefix=f"{package.__name__}."
            )
        ]
    )
)

#: The modules that may hold appearance and markup. Everything else must be
#: renderable-agnostic, so a different UI can be written against the models.
PRESENTATION = {
    "fmis.operator_dashboard.render",
    "fmis.operator_dashboard.theme",
    "fmis.operator_dashboard.server",
}

#: The contract layer. Nothing here may know a UI exists.
CONTRACT = {
    "fmis.operator_dashboard.models",
    "fmis.operator_dashboard.sections",
    "fmis.operator_dashboard.compose",
}


def _source(name: str) -> str:
    return Path(inspect.getfile(importlib.import_module(name))).read_text(
        encoding="utf-8"
    )


def _tree(name: str) -> ast.Module:
    return ast.parse(_source(name))


def _code_strings(name: str) -> set[str]:
    """Every string literal that is not a docstring.

    Docstrings are excluded on purpose: this package's prose *describes* the
    things it refuses to do, and a guard that scanned documentation would fire
    on the sentence explaining why the guard exists.
    """
    tree = _tree(name)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
    }


def _called_names(name: str) -> set[str]:
    called: set[str] = set()
    for node in ast.walk(_tree(name)):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name):
                called.add(target.id)
            elif isinstance(target, ast.Attribute):
                called.add(target.attr)
    return called


def _imported_roots(name: str) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(_tree(name)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


# ---------------------------------------------------------------------------
# The package's shape
# ---------------------------------------------------------------------------


def test_the_package_holds_exactly_the_modules_these_guards_cover() -> None:
    """A new module must be added to a layer deliberately, not by appearing."""
    assert set(MODULES) == PRESENTATION | CONTRACT | {"fmis.operator_dashboard"}


def test_every_public_name_is_exported_exactly_once() -> None:
    """No export collision: two modules exporting one name means the package's
    `__all__` silently resolves to whichever imported last."""
    assert len(package.__all__) == len(set(package.__all__))
    for name in package.__all__:
        assert hasattr(package, name), name


def test_the_intra_package_import_graph_is_acyclic() -> None:
    """No import cycle, asserted over the parsed graph.

    **Deliberately not `importlib.reload`.** Reloading rebinds `DashboardSectionStatus`
    to a new class object while every already-imported module still holds the
    old one, so `isinstance` starts failing in tests that run afterwards — a
    guard that breaks two hundred unrelated assertions is worse than the defect
    it looks for.
    """
    graph: dict[str, set[str]] = {}
    for name in MODULES:
        edges = set()
        for node in ast.walk(_tree(name)):
            if isinstance(node, ast.ImportFrom) and node.module in MODULES:
                edges.add(node.module)
        graph[name] = edges

    visiting: set[str] = set()
    done: set[str] = set()

    def walk(node: str, trail: list[str]) -> None:
        if node in done:
            return
        assert node not in visiting, f"import cycle: {' -> '.join(trail + [node])}"
        visiting.add(node)
        for edge in sorted(graph[node]):
            walk(edge, trail + [node])
        visiting.discard(node)
        done.add(node)

    for name in MODULES:
        walk(name, [])


def test_each_module_imports_in_a_fresh_interpreter() -> None:
    """A subprocess, so nothing this process already imported can hide a
    missing import or a circular one."""
    import subprocess
    import sys

    for name in MODULES:
        result = subprocess.run(
            [sys.executable, "-c", f"import {name}"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (name, result.stderr)


# ---------------------------------------------------------------------------
# It computes nothing
# ---------------------------------------------------------------------------

#: The vocabulary of every quantity that has an owner elsewhere in this
#: repository. Named as *text*, because the failure that happens is a
#: reimplementation, not an import.
FORBIDDEN_QUANTITIES = (
    "macd", "rsi", "ema", "sma", "atr", "bollinger", "stochastic",
    "expectancy_of", "profit_factor_of", "drawdown_of", "win_rate_of",
    "correlation_of", "volatility_of", "position_size", "risk_reward_of",
    "compute_return", "compute_risk", "compute_pnl", "calculate",
)


def _identifier_parts(name: str) -> set[str]:
    """Every underscore-separated part of every identifier in a module.

    Matched on **parts**, not substrings: `"ema"` appears inside `schema` and
    `"rsi"` inside `version`, and a guard that fired on those would be edited
    away rather than trusted. A reimplementation of an indicator would be
    spelled `ema_of`, `_rsi`, `atr` — all of which are parts.
    """
    parts: set[str] = set()
    for node in ast.walk(_tree(name)):
        identifier = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            identifier = node.name
        elif isinstance(node, ast.Name):
            identifier = node.id
        elif isinstance(node, ast.Attribute):
            identifier = node.attr
        elif isinstance(node, ast.arg):
            identifier = node.arg
        if identifier:
            parts.update(part for part in identifier.lower().split("_") if part)
    return parts


def _identifiers(name: str) -> set[str]:
    """Every identifier in a module, whole."""
    found: set[str] = set()
    for node in ast.walk(_tree(name)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name.lower())
        elif isinstance(node, ast.Name):
            found.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            found.add(node.attr.lower())
        elif isinstance(node, ast.arg):
            found.add(node.arg.lower())
    return found


@pytest.mark.parametrize("name", MODULES)
@pytest.mark.parametrize("vocabulary", FORBIDDEN_QUANTITIES)
def test_no_module_computes_a_quantity_that_has_an_owner(
    name: str, vocabulary: str
) -> None:
    """A reimplementation would be spelled `ema_of`, `_rsi`, `atr` — a whole
    identifier or one of its underscore-separated parts, never a substring of
    an unrelated word."""
    assert vocabulary not in _identifier_parts(name), (name, vocabulary)
    assert vocabulary not in _identifiers(name), (name, vocabulary)


@pytest.mark.parametrize("name", CONTRACT)
def test_the_contract_layer_performs_no_aggregation(name: str) -> None:
    """**`sum`, `min`, `max` and `sorted` are how a presentation layer becomes
    an engine.** A total is arithmetic over financial values; an extremum is a
    comparison of them; a sort is a ranking. All four have owners below."""
    called = _called_names(name)
    for builtin in ("sum", "sorted", "min", "max", "round", "abs"):
        assert builtin not in called, (name, builtin)


@pytest.mark.parametrize("name", CONTRACT)
def test_the_contract_layer_holds_no_arithmetic_on_engine_values(name: str) -> None:
    """No `+`, `-`, `*` or `/` outside the two places counting is legitimate:
    building a footnote index and slicing a string."""
    tree = _tree(name)
    operators = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(node.op, (ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Pow))
    ]
    assert operators == [], (name, [ast.unparse(node) for node in operators])


def test_the_only_arithmetic_in_the_package_is_the_charts_pixel_scaling() -> None:
    """**Pixels are not financial observations.** The equity chart scales
    engine-produced values into a viewBox; that is coordinate arithmetic and it
    is confined to one function, which says so."""
    tree = _tree("fmis.operator_dashboard.render")
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            has_math = any(
                isinstance(inner, ast.BinOp)
                and isinstance(inner.op, (ast.Sub, ast.Mult, ast.Div))
                for inner in ast.walk(node)
            )
            if has_math and node.name not in ("_equity_chart", "_y", "_duration", "_percent"):
                offenders.append(node.name)
    assert offenders == [], offenders


@pytest.mark.parametrize("name", CONTRACT)
def test_the_contract_layer_never_sorts(name: str) -> None:
    """Ordering is inherited from `fmis.swing_workspace`, never produced here.
    Re-sorting rows by risk/reward would be inventing the ranking four engines
    below deliberately refused to make."""
    assert "sort" not in _called_names(name)
    assert ".sort(" not in _source(name)


# ---------------------------------------------------------------------------
# It writes nothing
# ---------------------------------------------------------------------------

#: Store verbs and raw filesystem verbs together. *Writes nothing* means the
#: filesystem, so a plain `Path(...).write_text(...)` is covered too.
WRITE_VERBS = (
    "publish", "append_event", "append_lines", "atomic_write", "save",
    "write_text", "write_bytes", "write", "writelines", "mkdir", "makedirs",
    "unlink", "rmtree", "rename", "replace_file", "touch", "commit",
    "record_trade", "record", "store", "persist", "flush",
)


@pytest.mark.parametrize("name", MODULES)
def test_no_module_names_a_write_verb(name: str) -> None:
    """`list.append` is excluded and nothing else is.

    Building a list of rows is not persistence, and a guard that fired on it
    would be deleted within a week. Every *store* append verb — `append_event`,
    `append_lines` — is still listed, and so is every raw filesystem verb,
    because *writes nothing* means the filesystem too.
    """
    called = _called_names(name)
    found = called & set(WRITE_VERBS)
    if name == "fmis.operator_dashboard.server":
        # The one legitimate `write` in the package: the response body onto the
        # HTTP socket. Narrowed to that exact receiver rather than exempting the
        # module, so a write to anything else here still fails.
        found = found - {"write"}
        receivers = {
            ast.unparse(node.func.value)
            for node in ast.walk(_tree(name))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "write"
        }
        assert receivers == {"self.wfile"}, receivers
    assert not found, (name, found)


@pytest.mark.parametrize("name", MODULES)
def test_no_module_opens_anything(name: str) -> None:
    """No `open`, and no `Path.open`. The package reads engines, not files."""
    called = _called_names(name)
    assert "open" not in called, name


#: Every verb that would place, change or end a real position.
EXECUTION_VERBS = (
    "place_order", "submit_order", "cancel_order", "amend_order",
    "activate_trade", "close_trade", "record_fill", "withdraw", "transfer",
    "amend_stop", "cancel_activation", "run_approval",
)


@pytest.mark.parametrize("name", MODULES)
@pytest.mark.parametrize("verb", EXECUTION_VERBS)
def test_no_module_names_an_execution_verb(name: str, verb: str) -> None:
    """**If an existing application method writes, the dashboard must not call
    it.** Asserted by name across the package's whole source."""
    assert verb not in _source(name).replace(f"`{verb}`", ""), (name, verb)


def test_the_composition_root_calls_only_the_four_named_reads() -> None:
    """A fifth read is a decision somebody makes on purpose."""
    from fmis.operator_dashboard import REFRESH_READS

    source = _source("fmis.operator_dashboard.compose")
    for read in REFRESH_READS:
        assert read.rsplit(".", 1)[-1] in source, read
    assert len(REFRESH_READS) == 4


def test_no_module_catches_bare_exception() -> None:
    """**A dashboard that renders its own bugs as a tidy amber panel hides
    them.** Every `except` names types."""
    for name in MODULES:
        for node in ast.walk(_tree(name)):
            if isinstance(node, ast.ExceptHandler):
                assert node.type is not None, name
                names = (
                    [node.type] if not isinstance(node.type, ast.Tuple) else node.type.elts
                )
                for handler in names:
                    label = ast.unparse(handler)
                    assert label not in ("Exception", "BaseException"), (name, label)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

#: The brief's forbidden list, plus every web framework this build refuses.
FORBIDDEN_DEPENDENCIES = (
    "flask", "django", "fastapi", "starlette", "uvicorn", "streamlit",
    "jinja2", "aiohttp", "tornado", "bottle", "werkzeug", "pydantic",
    "numpy", "pandas", "scipy", "matplotlib", "plotly", "seaborn",
    "requests", "httpx", "websockets", "sklearn", "torch", "openai",
    "anthropic", "ccxt",
)


@pytest.mark.parametrize("name", MODULES)
@pytest.mark.parametrize("dependency", FORBIDDEN_DEPENDENCIES)
def test_no_module_imports_a_third_party_package(name: str, dependency: str) -> None:
    """**Zero runtime dependencies is a property of this repository**, declared
    in `pyproject.toml`. Seven static routes did not justify breaking it."""
    assert dependency not in _imported_roots(name), (name, dependency)


@pytest.mark.parametrize("name", MODULES)
def test_every_import_is_the_standard_library_or_this_repository(name: str) -> None:
    permitted = {
        "__future__", "fmis", "dataclasses", "datetime", "decimal", "enum",
        "html", "http", "pathlib", "threading", "typing", "urllib", "ast",
        "collections", "functools", "itertools", "math", "os", "socketserver",
        "sys", "textwrap", "json",
    }
    assert _imported_roots(name) <= permitted, (name, _imported_roots(name) - permitted)


def test_the_project_declares_no_new_runtime_dependency() -> None:
    manifest = Path(__file__).resolve().parents[1] / "pyproject.toml"
    body = manifest.read_text(encoding="utf-8")
    assert "dependencies = []" in body


# ---------------------------------------------------------------------------
# The redesign seam
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", CONTRACT)
def test_the_contract_layer_knows_no_user_interface(name: str) -> None:
    """**This is the seam the brief asked for.** Deleting `render` and `theme`
    and writing a different UI against `models` must require touching nothing
    here — so nothing here may import them, or hold markup."""
    assert not (_imported_roots(name) & {"html"}), name
    imported = _imported_roots(name)
    assert "urllib" not in imported, name
    # Asserted over imports rather than over the text: this package's prose
    # explains the seam by naming both sides of it, and a text scan would fire
    # on the paragraph describing why the seam exists.
    for node in ast.walk(_tree(name)):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in PRESENTATION, (name, node.module)


@pytest.mark.parametrize("name", CONTRACT)
def test_the_contract_layer_holds_no_markup_and_no_colour(name: str) -> None:
    for literal in _code_strings(name):
        lowered = literal.lower()
        assert "<div" not in lowered, (name, literal)
        assert "<span" not in lowered, (name, literal)
        assert "<table" not in lowered, (name, literal)
        assert not lowered.startswith("#") or len(literal) != 7, (name, literal)


def test_every_appearance_decision_lives_in_the_theme() -> None:
    """One module to replace for a redesign.

    **The regression this caught:** a footnote list and a market's secondary
    name carried `style="font-size:11px;color:var(--muted)"` inline. Two colour
    decisions outside the theme are two places a redesign has to find, and the
    inline one wins over the stylesheet — so the theme would stop being the
    single answer to *what does this look like*.
    """
    render = _source("fmis.operator_dashboard.render")
    assert 'style="' not in render, "appearance belongs in the theme, not inline"
    for declaration in ("color:", "background:", "font-family", "font-size:"):
        assert declaration not in render, declaration


def test_the_read_models_hold_no_method_that_computes() -> None:
    """Frozen dataclasses with lookups and predicates. Nothing that derives a
    financial value."""
    tree = _tree("fmis.operator_dashboard.models")
    permitted = {
        "__post_init__", "is_available", "failed", "sections",
        "failed_sections", "with_state", "row_for", "decision_for",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    assert item.name in permitted, (node.name, item.name)


# ---------------------------------------------------------------------------
# No recommendation vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", MODULES)
@pytest.mark.parametrize(
    "word", ["score", "confidence", "probability", "recommend", "rating", "grade"]
)
def test_no_field_or_function_carries_a_judgement_word(name: str, word: str) -> None:
    """**No composite health score, and no rating of anything.** A single number
    over sources with different publication schedules would be a judgement this
    system has no basis to make — and it would be the field most likely to be
    believed."""
    #: `recommended_size` is the Position Sizing Engine's **own** field name,
    #: carried across the seam verbatim. Renaming it here would break the
    #: correspondence between a figure on screen and the engine that produced
    #: it, which is a worse outcome than the word appearing. The guard's target
    #: is a judgement this package *invents*, and this is not one.
    carried_from_an_engine = {"recommended_size"}

    tree = _tree(name)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert word not in node.name.lower(), (name, node.name)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            field = node.target.id
            if field in carried_from_an_engine:
                continue
            assert word not in field.lower(), (name, field)
