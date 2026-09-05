"""Guards over `fmis.scan_memory`. **This package remembers; it never decides.**

Every guard here scans the package's own source, or the source of everything
around it. The claims they defend are the ones Slice 3 rests on:

* history is never an input to a trading decision;
* a change is a difference between structured states, never between sentences;
* nothing here is scored, ranked, weighted or called important;
* nothing here reads a clock, a provider or the network;
* nothing here notifies anybody, and nothing here asks a model anything.

A guard that only checked imports would miss the case that actually happens:
somebody comparing `blocker.statement` because the sentence was right there.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest

import fmis.scan_memory as package

MODULES = tuple(
    sorted(
        [package.__name__]
        + [
            module.name
            for module in pkgutil.iter_modules(package.__path__, prefix=f"{package.__name__}.")
        ]
    )
)

SOURCE_ROOT = Path(package.__file__).resolve().parent.parent


def _source(name: str) -> str:
    return Path(inspect.getfile(importlib.import_module(name))).read_text(encoding="utf-8")


def _tree(name: str) -> ast.AST:
    return ast.parse(_source(name))


def _called_names(name: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(_tree(name)):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                found.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                found.add(node.func.attr)
    return found


def _field_names(name: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(_tree(name)):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.add(node.target.id)
    return found


def test_the_module_list_is_not_empty() -> None:
    """Non-vacuity: every guard below is parametrized over this."""
    assert len(MODULES) >= 6, MODULES


# ---------------------------------------------------------------------------
# History cannot influence a decision
# ---------------------------------------------------------------------------

#: Everything that computes, gates or admits a trading conclusion. If any of
#: these could import scan memory, a remembered state could reach current trade
#: admission — which is the one thing §6 forbids absolutely.
DECIDING_PACKAGES = (
    "swing_setup", "swing_workspace", "setup_evidence", "decision_context",
    "market_regime", "structural_trend", "market_structure", "series_context",
    "level_crossing", "structure_break", "change_of_character", "evidence",
    "decision_support", "trading_context", "features", "alignment",
    "relative_value", "position_sizing", "portfolio_risk", "risk", "today",
    "workspace", "daily", "paper", "plan", "proposal",
)


def test_the_deciding_packages_scanned_actually_exist() -> None:
    """Guards the test below from silently passing if a package is renamed."""
    for name in DECIDING_PACKAGES:
        assert (SOURCE_ROOT / name / "__init__.py").is_file(), name


@pytest.mark.parametrize("name", DECIDING_PACKAGES)
def test_nothing_that_decides_can_reach_scan_memory(name: str) -> None:
    """**The central invariant of Slice 3, asserted as an import direction.**

    `SetupAssessment`, candidate admission, the regime gates and the evidence
    tally cannot see history, because the packages that compute them cannot
    import the package that holds it.
    """
    offenders = [
        str(path)
        for path in (SOURCE_ROOT / name).rglob("*.py")
        if "fmis.scan_memory" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], offenders
    assert not any(_imports_scan_memory(path) for path in (SOURCE_ROOT / name).rglob("*.py"))


def _imports_scan_memory(path: Path) -> bool:
    """Whether a file really imports the package, rather than mentioning it.

    Parsed, not grepped: three dashboard modules name `fmis.scan_memory` in a
    docstring to say what they do *not* do, and a substring search would report
    the documentation of the boundary as a breach of it.
    """
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("fmis.scan_memory"):
            return True
        if isinstance(node, ast.Import):
            if any(alias.name.startswith("fmis.scan_memory") for alias in node.names):
                return True
    return False


def test_exactly_one_module_outside_the_package_wires_scan_memory() -> None:
    """**Precision, not an allowlist.** The one importer is named, so a second
    one appearing anywhere is a decision somebody makes on purpose."""
    importers = sorted(
        str(path.relative_to(SOURCE_ROOT))
        for path in SOURCE_ROOT.rglob("*.py")
        if path.parent.name != "scan_memory" and _imports_scan_memory(path)
    )
    assert importers == ["pipeline/scan_memory.py"], importers


def test_the_dashboard_documents_the_boundary_without_crossing_it() -> None:
    """Non-vacuity for the parse above: the modules that *mention* the package
    are the ones that must never import it, and they do not."""
    mentions = sorted(
        str(path.relative_to(SOURCE_ROOT))
        for path in (SOURCE_ROOT / "operator_dashboard").rglob("*.py")
        if "fmis.scan_memory" in path.read_text(encoding="utf-8")
    )
    assert mentions, "the boundary is documented where it is enforced"
    for name in mentions:
        assert not _imports_scan_memory(SOURCE_ROOT / name), name


@pytest.mark.parametrize("name", MODULES)
def test_scan_memory_imports_no_engine_and_no_policy(name: str) -> None:
    """The arrow points **into** this package. It reads finished projections
    handed to it and reaches no engine at all — the only `fmis` import outside
    itself is the shared atomic-publish primitive."""
    permitted = {"fmis.scan_memory", "fmis.archive.atomic", "fmis.archive.errors"}
    for node in ast.walk(_tree(name)):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("fmis"):
            assert any(node.module.startswith(root) for root in permitted), (name, node.module)


# ---------------------------------------------------------------------------
# Structured state, never prose
# ---------------------------------------------------------------------------

#: Field names that hold a sentence somewhere in this repository. Comparing one
#: would report a reworded message as a changed market.
PROSE_FIELDS = (
    "statement", "requirement", "thesis", "regime_context", "confirmation",
    "invalidation", "detail", "note", "caveats",
    "open_questions", "decision_ready_reason", "evidence_reason",
)


@pytest.mark.parametrize("field", PROSE_FIELDS)
def test_no_prose_field_is_read_by_the_comparator(field: str) -> None:
    """**§11.** Asserted over the two modules that could compare anything."""
    for name in ("fmis.scan_memory.comparison", "fmis.scan_memory.projection"):
        assert f".{field}" not in _source(name), (name, field)


def test_the_comparator_reads_only_declared_dimensions() -> None:
    """**§12's guarantee, asserted structurally.** The comparator's whole field
    list is `CHANGE_DIMENSIONS`, and no instant, age or bar count is on it."""
    from fmis.scan_memory import CHANGE_DIMENSIONS, ChangeDimension, dimension_values

    from tests.scan_memory_helpers import state

    assert set(dimension_values(state())) | {ChangeDimension.PRESENCE} == set(
        CHANGE_DIMENSIONS
    )
    for forbidden in ("age", "closed_count", "as_of", "recorded_at", "reference_time"):
        assert forbidden not in {member.value for member in CHANGE_DIMENSIONS}


def test_the_comparator_never_reads_a_stored_instant() -> None:
    source = _source("fmis.scan_memory.comparison")
    for forbidden in (".as_of", ".recorded_at", ".blocker_observed"):
        assert forbidden not in source, forbidden


# ---------------------------------------------------------------------------
# No ranking, no score, no importance
# ---------------------------------------------------------------------------

RANKING_VOCABULARY = (
    "score", "rank", "weight", "importance", "urgency", "severity",
    "priority", "significance", "opportunity", "confidence", "probability",
    "closeness", "strength", "quality", "grade", "tier",
)


@pytest.mark.parametrize("name", MODULES)
@pytest.mark.parametrize("word", RANKING_VOCABULARY)
def test_no_field_name_matches_a_ranking_vocabulary(name: str, word: str) -> None:
    """§13. A change is a named transition, never a 95/100."""
    for field in _field_names(name):
        assert word not in field.lower(), (name, field)


def test_the_comparator_orders_nothing() -> None:
    """**§13 and §14.** Changed symbols arrive in the scan's own universe order
    and leave in it; nothing in the comparator reorders a market.

    The guard is on the comparator alone because the other two sorts in the
    package order *nothing that is a market*: the store sorts filenames to find
    the newest record, and the projection sorts timeframe roles so an identity
    is canonical. Both are named below rather than exempted by silence.
    """
    calls = _called_names("fmis.scan_memory.comparison")
    assert "sorted" not in calls
    assert "sort" not in calls


def test_every_sort_in_the_package_orders_something_that_is_not_a_market() -> None:
    """Precision for the guard above. Four modules sort, and each is named:

    * `store` — filenames, to find the newest record;
    * `projection` — timeframe roles, so an identity is canonical;
    * `models` and `codec` — a set, so a refusal message is deterministic.

    Not one of them orders symbols, and the comparator does not sort at all.
    """
    sorting = {
        name
        for name in MODULES
        if "sorted" in _called_names(name) and name != "fmis.scan_memory"
    }
    assert sorting == {
        "fmis.scan_memory.store",
        "fmis.scan_memory.projection",
        "fmis.scan_memory.models",
        "fmis.scan_memory.codec",
    }


#: Every arithmetic operator in the package, written out — ADR-0007 §2's
#: discipline applied here. Four path joins and one set difference; not one of
#: them touches a market value, and adding a sixth is a visible decision.
PERMITTED_ARITHMETIC = {
    "Path.home() / '.fmits'",
    "Path.home() / '.fmits' / 'scan_memory'",
    "self._root / SCANS_DIRECTORY",
    "self.scans_directory / f'{stamp}-{record.scan_id[:12]}.json'",
    "{state.symbol for state in symbols} - requested",
}


def test_the_package_contains_no_arithmetic_but_the_five_named_expressions() -> None:
    """**Nothing here computes a magnitude.** Counting a tuple's length is not a
    market calculation; scaling, weighting or accumulating one would be."""
    found: set[str] = set()
    for name in MODULES:
        for node in ast.walk(_tree(name)):
            if isinstance(node, ast.BinOp) and isinstance(
                node.op, (ast.Mult, ast.Div, ast.Pow, ast.FloorDiv, ast.Sub, ast.Add)
            ):
                found.add(ast.unparse(node))
    assert found == PERMITTED_ARITHMETIC, found ^ PERMITTED_ARITHMETIC


@pytest.mark.parametrize("name", MODULES)
def test_no_module_imports_a_maths_library(name: str) -> None:
    for node in ast.walk(_tree(name)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in ("math", "statistics", "decimal", "fractions"), name
        if isinstance(node, ast.ImportFrom):
            assert node.module not in ("math", "statistics", "decimal", "fractions"), name


# ---------------------------------------------------------------------------
# No side is named, nothing is predicted, nobody is notified
# ---------------------------------------------------------------------------


def test_no_module_declares_a_directional_constant() -> None:
    """ADR-0028. Sides are carried at runtime as values, never spelled here.

    The repository-wide identifier-and-literal scan in
    `tests/test_directional_vocabulary_boundary.py` already covers this package
    the moment it exists; this adds the field-name half, which that scan does
    not look at.
    """
    for name in MODULES:
        for field in _field_names(name):
            assert "long" not in field.lower(), (name, field)
            assert "short" not in field.lower(), (name, field)


@pytest.mark.parametrize("name", MODULES)
def test_no_module_names_a_notification_channel(name: str) -> None:
    """§36. Slice 3 builds the substrate an alert could later use. Not the alert."""
    source = _source(name).lower()
    for word in ("telegram", "discord", "webhook", "smtp", "notify(", "alert("):
        assert word not in source, (name, word)


@pytest.mark.parametrize("name", MODULES)
def test_no_module_asks_a_model_anything(name: str) -> None:
    """§37. Change detection is deterministic, end to end."""
    source = _source(name).lower()
    for word in ("openai", "anthropic", "llm", "gpt", "claude", "prompt", "completion"):
        assert word not in source, (name, word)


@pytest.mark.parametrize("name", MODULES)
def test_no_module_reads_a_clock_or_the_network(name: str) -> None:
    """Every instant is supplied. Two runs over the same inputs are equal."""
    calls = _called_names(name)
    for forbidden in ("now", "utcnow", "today", "monotonic", "urlopen", "urlretrieve", "urlopen"):
        assert forbidden not in calls, (name, forbidden)


@pytest.mark.parametrize("name", MODULES)
def test_no_module_catches_bare_exception(name: str) -> None:
    """A corrupt history is a named condition, never a swallowed one."""
    for node in ast.walk(_tree(name)):
        if isinstance(node, ast.ExceptHandler):
            assert node.type is not None, name
            handlers = (
                [node.type] if not isinstance(node.type, ast.Tuple) else node.type.elts
            )
            for handler in handlers:
                assert ast.unparse(handler) not in ("Exception", "BaseException"), name


# ---------------------------------------------------------------------------
# Only the store writes
# ---------------------------------------------------------------------------

WRITE_VERBS = ("atomic_write", "write_text", "write_bytes", "unlink", "mkdir", "open")


@pytest.mark.parametrize("name", MODULES)
def test_only_the_store_module_touches_the_filesystem(name: str) -> None:
    """**One writer.** The model, the projection, the comparator and the codec
    are pure; a test can exercise all four with no directory at all."""
    if name in ("fmis.scan_memory.store", "fmis.scan_memory"):
        return
    calls = _called_names(name)
    for verb in WRITE_VERBS:
        assert verb not in calls, (name, verb)
    assert "read_bytes" not in calls, name


def test_the_store_module_really_does_write() -> None:
    """Proves the exclusion above is precise rather than vacuous."""
    calls = _called_names("fmis.scan_memory.store")
    assert "atomic_write" in calls
    assert "unlink" in calls


def test_the_research_boundary_is_stated_in_the_package_itself() -> None:
    """§38. The four accepted conclusions are named where somebody adding to this
    package will read them, rather than only in a report they will not."""
    text = " ".join(_source("fmis.scan_memory").split())
    for conclusion in ("NO_EDGE", "UNDERPOWERED", "INFEASIBLE"):
        assert conclusion in text, conclusion
    assert "not a signal" in text and "not a validated edge" in text


def test_no_model_field_could_hold_a_verdict_about_the_market() -> None:
    """Nothing here can be given a place to put an edge, a probability or a
    return, because no field name in the package admits one."""
    for name in MODULES:
        for field in _field_names(name):
            for word in ("edge", "return", "profit", "pnl", "expectancy", "calibration"):
                assert word not in field.lower(), (name, field)
