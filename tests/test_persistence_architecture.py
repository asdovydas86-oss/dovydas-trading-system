"""Boundary guards for the durable store.

These tests exercise no behaviour. They assert the *rules* the architecture states,
in the only form that survives a refactor: an executable check over the source
tree. Each corresponds to a sentence a later reader would otherwise have to take on
trust.

The direction of the layering is the one worth stating twice. The trading domain is
pure: it holds no path, opens no file and reads no clock, and **nothing in it
imports this package**. The day that reverses is the day a `Trade` cannot be
constructed without a store to put it in — and the failure would arrive as a
convenience, not as a decision.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from datetime import datetime
from pathlib import Path

import pytest

import fmis
from fmis.persistence import (
    SPECS,
    DurabilityClass,
    JOURNAL_EVENT_TYPE_SLUG,
    PersistenceError,
    RecordKind,
    Repository,
    StorageShape,
    TradingStore,
)
from fmis.records import TradeDomainError

PERSISTENCE = "fmis.persistence"

#: Every package the trading domain is made of — the layer *below* this one.
#: Copied deliberately rather than imported from the domain's own guard file, so
#: that adding a package to either list is a visible edit in both places.
DOMAIN_PACKAGES = (
    "fmis.records",
    "fmis.provenance",
    "fmis.money",
    "fmis.versioning",
    "fmis.accounts",
    "fmis.analysis_record",
    "fmis.snapshotting",
    "fmis.proposal",
    "fmis.plan",
    "fmis.ledger",
    "fmis.positions",
    "fmis.portfolio",
    "fmis.risk",
    "fmis.journal",
)

MARKET_HALF_PACKAGES = frozenset(
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
        "fmis.pipeline",
        "fmis.trading_context",
    }
)

SOURCE_ROOT = Path(fmis.__file__).parent


def _modules_of(package_name: str) -> list[str]:
    package = importlib.import_module(package_name)
    return [package_name] + [
        module.name
        for module in pkgutil.iter_modules(package.__path__, prefix=f"{package_name}.")
    ]


def _imports_of(module_name: str) -> set[str]:
    module = importlib.import_module(module_name)
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _source_of(module_name: str) -> str:
    return Path(inspect.getfile(importlib.import_module(module_name))).read_text(
        encoding="utf-8"
    )


# --------------------------------------------------------------------------
# Layering: infrastructure reads the domain and is never read by it.
# --------------------------------------------------------------------------


def test_no_domain_package_imports_the_store() -> None:
    """*Or a `Trade` stops being constructible without somewhere to put it.*"""
    offenders: dict[str, set[str]] = {}
    for package_name in DOMAIN_PACKAGES:
        for module_name in _modules_of(package_name):
            reached = {
                imported
                for imported in _imports_of(module_name)
                if imported == PERSISTENCE or imported.startswith(f"{PERSISTENCE}.")
            }
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_no_market_half_package_imports_the_store() -> None:
    offenders: dict[str, set[str]] = {}
    for package_name in sorted(MARKET_HALF_PACKAGES):
        for module_name in _modules_of(package_name):
            reached = {
                imported
                for imported in _imports_of(module_name)
                if imported == PERSISTENCE or imported.startswith(f"{PERSISTENCE}.")
            }
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_the_store_imports_no_engine() -> None:
    """It persists the owner half. What the market half computes reaches it only
    as a frozen reading already inside a domain record."""
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(PERSISTENCE):
        reached = _imports_of(module_name) & MARKET_HALF_PACKAGES
        if reached:
            offenders[module_name] = reached
    assert offenders == {}


def test_the_store_reaches_the_archive_only_for_frozen_machinery() -> None:
    """ADR-0027's encoder, digest, atomic publish and error base — reused, never
    reimplemented. A second definition of "the bytes" is Law 1's failure at the
    level of a function."""
    permitted = {
        "fmis.archive.json_safe",
        "fmis.archive.identity",
        "fmis.archive.atomic",
        "fmis.archive.errors",
    }
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(PERSISTENCE):
        reached = {
            imported
            for imported in _imports_of(module_name)
            if imported.startswith("fmis.archive")
        }
        if reached - permitted:
            offenders[module_name] = reached - permitted
    assert offenders == {}


def test_the_store_never_reaches_the_archives_own_storage() -> None:
    """Two stores under one root would be two answers to what is filed where."""
    for module_name in _modules_of(PERSISTENCE):
        assert "fmis.archive.storage" not in _imports_of(module_name), module_name
        assert "fmis.archive.manifest" not in _imports_of(module_name), module_name


def test_no_module_in_the_store_participates_in_an_import_cycle() -> None:
    """Every intra-package import points at a module earlier in the layering."""
    order = [
        "errors",
        "kinds",
        "layout",
        "appendonly",
        "envelope",
        "index",
        "journal_engine",
        "criteria",
        "store",
        "lineage",
        "base",
        "ledger_repositories",
        "decision_repositories",
        "capital_repositories",
        "composition",
    ]
    rank = {name: position for position, name in enumerate(order)}
    modules = {
        name.split(".")[-1] for name in _modules_of(PERSISTENCE) if name != PERSISTENCE
    }
    assert modules == set(order), modules.symmetric_difference(order)
    for name in order:
        for imported in _imports_of(f"{PERSISTENCE}.{name}"):
            if not imported.startswith(f"{PERSISTENCE}."):
                continue
            target = imported.split(".")[-1]
            assert rank[target] < rank[name], f"{name} imports {target}"


# --------------------------------------------------------------------------
# Determinism: no clock, no randomness, no module-level mutable state.
# --------------------------------------------------------------------------


def test_no_module_in_the_store_reads_a_clock_or_a_random_source() -> None:
    """Every instant is the caller's. A store that stamps itself cannot be replayed."""
    forbidden = ("datetime.now(", "datetime.utcnow(", "time.time(", "random.")
    offenders: dict[str, list[str]] = {}
    for module_name in _modules_of(PERSISTENCE):
        source = _source_of(module_name)
        hits = [needle for needle in forbidden if needle in source]
        if hits:
            offenders[module_name] = hits
    assert offenders == {}


def test_no_module_in_the_store_holds_module_level_mutable_state() -> None:
    for module_name in _modules_of(PERSISTENCE):
        module = importlib.import_module(module_name)
        for name, value in vars(module).items():
            if name.startswith("__") or inspect.isclass(value):
                continue
            assert not isinstance(value, (list, set)), f"{module_name}.{name}"
            if isinstance(value, dict):
                assert name.startswith("_") or name.isupper(), f"{module_name}.{name}"


def test_the_spec_table_cannot_be_extended_at_runtime() -> None:
    """A layout that depends on import order is a layout nobody can reason about."""
    with pytest.raises(TypeError):
        SPECS[RecordKind.TRADE] = None  # type: ignore[index]


def test_the_store_defaults_to_no_root() -> None:
    """`RecordStore` never falls back to the owner's real store by omission."""
    source = _source_of(f"{PERSISTENCE}.store")
    assert "default_store_root()" not in source
    assert "DEFAULT_STORE_ROOT" not in source


# --------------------------------------------------------------------------
# Writing: one path in, and only append-only primitives underneath.
# --------------------------------------------------------------------------

#: The only modules permitted to touch the filesystem for writing. Everything
#: else must go through `RecordStore.publish`, which is what makes the write
#: journal a complete account of the store rather than a mostly complete one.
_WRITERS = {
    f"{PERSISTENCE}.appendonly",
    f"{PERSISTENCE}.store",
    f"{PERSISTENCE}.index",
    f"{PERSISTENCE}.journal_engine",
    f"{PERSISTENCE}.layout",
}


def test_only_the_named_modules_write_to_disk() -> None:
    writing = ("atomic_write(", "append_lines(", "os.open(", ".write_text(", ".write_bytes(")
    for module_name in _modules_of(PERSISTENCE):
        if module_name in _WRITERS:
            continue
        source = _source_of(module_name)
        hits = [needle for needle in writing if needle in source]
        assert hits == [], f"{module_name} writes: {hits}"


def test_no_repository_writes_a_payload_itself() -> None:
    """Every repository reaches disk through `publish`, or not at all."""
    for name in (
        "ledger_repositories",
        "decision_repositories",
        "capital_repositories",
        "base",
        "composition",
    ):
        source = _source_of(f"{PERSISTENCE}.{name}")
        assert "atomic_write" not in source
        assert "append_lines" not in source


def test_no_line_file_is_ever_opened_for_truncation() -> None:
    """`O_APPEND` cannot shorten a file; a `"w"` mode can. Only the rebuild may,
    and it does so through one named method that recomputes from truth."""
    source = _source_of(f"{PERSISTENCE}.appendonly")
    assert "O_APPEND" in source
    assert "O_TRUNC" not in source
    assert '"w"' not in source and "'w'" not in source


def test_the_only_shrinking_write_is_the_index_rebuild() -> None:
    index_source = _source_of(f"{PERSISTENCE}.index")
    store_source = _source_of(f"{PERSISTENCE}.store")
    assert "unlink" in index_source  # write_all clears before republishing
    assert index_source.count("def write_all") == 1
    assert store_source.count("write_all(") == 1
    assert "rebuild_index" in store_source


# --------------------------------------------------------------------------
# The spec table.
# --------------------------------------------------------------------------


def test_every_domain_type_slug_is_persisted() -> None:
    """A record type the domain gave an id scheme, with nowhere to keep it, is a
    record type that will be persisted badly by whoever first needs it."""
    domain_slugs = set()
    for package_name in DOMAIN_PACKAGES:
        package = importlib.import_module(package_name)
        for name in getattr(package, "__all__", []):
            if name.endswith("_TYPE_SLUG"):
                domain_slugs.add(getattr(package, name))
    stored_slugs = {spec.type_slug for spec in SPECS.values()}
    assert domain_slugs <= stored_slugs, domain_slugs - stored_slugs


def test_the_journal_event_slug_collides_with_no_record_slug() -> None:
    """Or a journal event id would parse as a record id, and the reverse."""
    assert JOURNAL_EVENT_TYPE_SLUG not in {spec.type_slug for spec in SPECS.values()}


def test_every_kind_is_owned_by_exactly_one_writing_repository(
    tmp_path: Path,
) -> None:
    """Every kind has a home, and only one repository creates it."""
    from persistence_helpers import new_store

    store = new_store(tmp_path)
    owners: dict[RecordKind, list[str]] = {}
    for repository in store.repositories():
        for kind in repository.kinds:
            owners.setdefault(kind, []).append(type(repository).__name__)
    assert set(owners) == set(RecordKind)
    assert owners[RecordKind.JOURNAL_ENTRY] == ["JournalRepository"]
    assert owners[RecordKind.RISK_BUDGET] == ["RiskRepository"]


def test_every_spec_derives_its_identity_from_the_record(tmp_path: Path, sample_records) -> None:
    """Calling `identity` twice on one record gives one answer, forever."""
    for record in sample_records:
        from fmis.persistence import spec_for_record

        spec = spec_for_record(record)
        assert spec.identity(record) == spec.identity(record)
        assert spec.digest(record) == spec.digest(record)
        assert isinstance(spec.moment(record), datetime)
        assert spec.moment(record).tzinfo is not None


def test_a_frozen_spec_is_exactly_a_captured_artifact() -> None:
    for spec in SPECS.values():
        assert spec.is_frozen is (
            spec.durability is DurabilityClass.CAPTURED_ARTIFACT
        )


def test_only_one_kind_may_take_effect_in_the_future() -> None:
    """A record describing the past that could be filed before it happened would
    make the ordering guarantee meaningless."""
    future = {spec.kind for spec in SPECS.values() if spec.moment_may_be_future}
    assert future == {RecordKind.RISK_BUDGET}


def test_every_event_log_kind_is_a_source_of_truth() -> None:
    for spec in SPECS.values():
        if spec.shape is StorageShape.EVENT_LOG:
            assert spec.durability is DurabilityClass.SOURCE_OF_TRUTH


def test_only_a_source_of_truth_may_supersede_anything() -> None:
    """A captured artifact is frozen with its inputs; it replaces nothing."""
    for spec in SPECS.values():
        if spec.durability is not DurabilityClass.SOURCE_OF_TRUTH:
            assert spec.supersedes_kinds == frozenset(), spec.kind


def test_every_supersession_target_is_a_kind_this_store_holds() -> None:
    """A chain that could name a kind with no spec would be a chain nothing reads."""
    for spec in SPECS.values():
        for target in spec.supersedes_kinds:
            assert target in SPECS, (spec.kind, target)


def test_a_kind_that_can_supersede_includes_itself_as_a_target() -> None:
    """Or a correction of a correction — an ordinary chain — would be refused."""
    for spec in SPECS.values():
        if spec.supersedes_kinds:
            assert spec.kind in spec.supersedes_kinds, spec.kind


# --------------------------------------------------------------------------
# The package surface.
# --------------------------------------------------------------------------


def test_the_package_declares_what_it_exports() -> None:
    package = importlib.import_module(PERSISTENCE)
    assert package.__all__
    for name in package.__all__:
        assert hasattr(package, name), name


def test_no_submodule_shares_a_name_with_a_public_object() -> None:
    package = importlib.import_module(PERSISTENCE)
    submodules = {module.name for module in pkgutil.iter_modules(package.__path__)}
    assert not submodules & set(package.__all__)


def test_every_module_has_a_docstring() -> None:
    for module_name in _modules_of(PERSISTENCE):
        module = importlib.import_module(module_name)
        assert module.__doc__, module_name


def test_every_store_error_derives_from_one_catchable_base() -> None:
    package = importlib.import_module(PERSISTENCE)
    errors = [
        getattr(package, name)
        for name in package.__all__
        if isinstance(getattr(package, name), type)
        and issubclass(getattr(package, name), BaseException)
    ]
    assert len(errors) == 11
    for error in errors:
        assert issubclass(error, PersistenceError), error.__name__
        assert issubclass(error, TradeDomainError), error.__name__


def test_the_store_exports_no_composite_score() -> None:
    package = importlib.import_module(PERSISTENCE)
    exported = " ".join(package.__all__).lower()
    for forbidden in ("score", "grade", "rating", "health"):
        assert forbidden not in exported


def test_the_store_invents_no_threshold() -> None:
    """Every policy value — a dust threshold, a risk limit — is the owner's."""
    for module_name in _modules_of(PERSISTENCE):
        literals = {
            node.value
            for node in ast.walk(ast.parse(_source_of(module_name)))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, float)
            and not isinstance(node.value, bool)
        }
        assert literals == set(), f"{module_name}: {sorted(literals)}"


def test_every_repository_subclasses_the_one_base(tmp_path: Path) -> None:
    from persistence_helpers import new_store

    for repository in new_store(tmp_path).repositories():
        assert isinstance(repository, Repository)
        assert repository.kinds


def test_the_composition_root_computes_nothing() -> None:
    """It constructs; it does not decide. A convenience method here would become
    the tenth place a question is answered."""
    source = _source_of(f"{PERSISTENCE}.composition")
    tree = ast.parse(source)
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    assert [node.name for node in classes] == ["TradingStore"]
    for node in classes[0].body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            calls = [
                child
                for child in ast.walk(node)
                if isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr not in ("verify",)
            ]
            assert calls == [], f"TradingStore.{node.name} computes something"


def test_a_store_holds_no_state_between_calls(tmp_path: Path) -> None:
    """Two stores over one root give the same answers — nothing is cached."""
    from persistence_helpers import new_store, write_request
    from trade_domain_helpers import trade

    first = new_store(tmp_path)
    first.trades.create(trade(), request=write_request())
    second = new_store(tmp_path)
    assert second.trades.all() == first.trades.all()
    assert second.positions.rebuild() == first.positions.rebuild()
    assert second.verify().ok
