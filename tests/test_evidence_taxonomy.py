"""Tests for the evidence taxonomy (fmis.evidence).

The package has no behaviour, so these tests are about the contract: which
families exist, what a descriptor may and may not carry, that the catalog is
deterministic and duplicate-free, and — most importantly — that every catalogued
concept is genuinely interpreted by the system today rather than aspirational.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
import re
import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from types import ModuleType

import pytest

import fmis.evidence as ev
from fmis.evidence import (
    EvidenceDescriptor,
    EvidenceFamily,
    descriptors,
    descriptors_for,
    find,
)

PACKAGE_DIR = Path(ev.__file__).parent
SRC = PACKAGE_DIR.parent  # src/fmis


def descriptor(**overrides: object) -> EvidenceDescriptor:
    """A valid descriptor; override one field to exercise a failure case."""
    kwargs: dict[str, object] = {
        "family": EvidenceFamily.TREND,
        "name": "example_concept",
        "description": "An example.",
    }
    kwargs.update(overrides)
    return EvidenceDescriptor(**kwargs)  # type: ignore[arg-type]


# ============================ EvidenceFamily =================================


def test_family_membership_is_exact() -> None:
    assert {f.name for f in EvidenceFamily} == {
        "TREND", "MOMENTUM", "VOLUME", "VOLATILITY", "MARKET_STRUCTURE",
        "RELATIVE_STRENGTH", "LIQUIDITY", "MACRO", "NEWS", "SENTIMENT",
    }


def test_family_has_no_trading_action_members() -> None:
    names = {f.name for f in EvidenceFamily}
    values = {f.value for f in EvidenceFamily}
    for forbidden in ("BUY", "SELL", "LONG", "SHORT", "SIGNAL"):
        assert forbidden not in names
        assert forbidden.lower() not in values


def test_family_values_are_stable_lowercase_tokens() -> None:
    for family in EvidenceFamily:
        assert family.value == family.name.lower()
        assert not any(c.isspace() for c in family.value)


def test_family_is_a_str_enum_matching_repository_convention() -> None:
    assert isinstance(EvidenceFamily.TREND, str)


def test_family_members_cannot_be_reassigned() -> None:
    with pytest.raises(AttributeError):
        EvidenceFamily.TREND = "other"  # type: ignore[misc]


def test_family_is_not_a_rename_of_feature_category() -> None:
    """Different axes: one classifies calculations, the other evidence concepts.

    Five names overlap, but neither set contains the other, so one cannot stand
    in for the other. FeatureCategory's own docstring forbids the non-technical
    members this enum requires.
    """
    from fmis.features import FeatureCategory

    feature_names = {c.name for c in FeatureCategory}
    family_names = {f.name for f in EvidenceFamily}
    assert not family_names <= feature_names
    assert not feature_names <= family_names
    assert {"MACRO", "NEWS", "SENTIMENT"} <= family_names - feature_names
    calculation_only = {"INDICATOR", "PATTERN", "SUPPORT_RESISTANCE"}
    assert calculation_only <= feature_names - family_names


# ============================ EvidenceDescriptor =============================


def test_descriptor_fields_are_exactly_three() -> None:
    assert [f.name for f in fields(EvidenceDescriptor)] == [
        "family", "name", "description",
    ]


def test_descriptor_has_no_value_score_weight_or_state_fields() -> None:
    names = {f.name for f in fields(EvidenceDescriptor)}
    tokens: set[str] = set()
    for name in names:
        tokens |= set(name.split("_")) | {name}
    for forbidden in (
        "value", "score", "weight", "confidence", "direction", "supporting",
        "conflicting", "neutral", "unavailable", "availability", "state",
        "insufficient", "reading", "observation", "alignment", "rank",
    ):
        assert forbidden not in tokens, forbidden


def test_descriptor_is_frozen() -> None:
    d = descriptor()
    with pytest.raises(FrozenInstanceError):
        d.name = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        d.family = EvidenceFamily.MACRO  # type: ignore[misc]


def test_descriptor_uses_slots_and_rejects_new_attributes() -> None:
    """Slots are real: fixed layout, no instance dict, no new attributes.

    The exception type for an *undeclared* attribute is `TypeError`, not
    `AttributeError` or `FrozenInstanceError`. That is a CPython quirk of
    `@dataclass(frozen=True, slots=True)` — `slots=True` rebuilds the class, but
    the generated `__setattr__` keeps a zero-argument `super()` bound to the
    original one — and it applies to every frozen slotted dataclass in this
    repository, not just this type. What matters is that the assignment is
    refused; the type is asserted loosely so this test documents the quirk rather
    than pinning a CPython implementation detail.
    """
    assert EvidenceDescriptor.__slots__ == ("family", "name", "description")
    d = descriptor()
    assert not hasattr(d, "__dict__")
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        d.score = 1.0  # type: ignore[attr-defined]
    assert not hasattr(d, "score")


def test_descriptor_equality_and_hashability() -> None:
    assert descriptor() == descriptor()
    assert descriptor() != descriptor(name="other_concept")
    assert len({descriptor(), descriptor()}) == 1  # frozen -> hashable


def test_descriptor_construction_is_deterministic() -> None:
    assert descriptor() == descriptor()


# ============================ descriptor validation ==========================


def test_family_must_be_an_evidence_family() -> None:
    with pytest.raises(TypeError, match="family must be an EvidenceFamily"):
        descriptor(family="trend")


@pytest.mark.parametrize("bad", ["", "   ", "\t"])
def test_empty_name_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="name cannot be empty"):
        descriptor(name=bad)


def test_non_str_name_rejected() -> None:
    with pytest.raises(TypeError, match="name must be a str"):
        descriptor(name=7)


@pytest.mark.parametrize("bad", [" leading", "trailing ", " both "])
def test_untrimmed_name_rejected_not_trimmed(bad: str) -> None:
    # Rejected, never silently normalized: two names that differ only by
    # whitespace would otherwise collapse and defeat the duplicate check.
    with pytest.raises(ValueError, match="whitespace"):
        descriptor(name=bad)


def test_internal_whitespace_rejected() -> None:
    with pytest.raises(ValueError, match="must not contain whitespace"):
        descriptor(name="two words")


@pytest.mark.parametrize("bad", ["Trend", "PRICE_VS_EMA", "mixedCase"])
def test_non_lowercase_name_rejected_not_lowered(bad: str) -> None:
    with pytest.raises(ValueError, match="must be lower-case"):
        descriptor(name=bad)


def test_normalized_names_accepted() -> None:
    for good in ("trend", "price_vs_ema_fast", "macd_histogram", "rsi_zone"):
        assert descriptor(name=good).name == good


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_description_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="description cannot be empty"):
        descriptor(description=bad)


def test_non_str_description_rejected() -> None:
    with pytest.raises(TypeError, match="description must be a str"):
        descriptor(description=None)


# ============================ catalog ========================================


def test_catalog_contents_are_exactly_the_audited_six() -> None:
    assert {(d.family.name, d.name) for d in descriptors()} == {
        ("TREND", "price_vs_ema_fast"),
        ("TREND", "price_vs_ema_slow"),
        ("TREND", "ema_fast_vs_ema_slow"),
        ("MOMENTUM", "rsi_zone"),
        ("MOMENTUM", "macd_vs_signal"),
        ("MOMENTUM", "macd_histogram"),
    }


def test_catalog_ordering_is_deterministic_and_canonical() -> None:
    first = descriptors()
    assert first == descriptors()  # stable across calls
    family_order = {f: i for i, f in enumerate(EvidenceFamily)}
    keys = [(family_order[d.family], d.name) for d in first]
    assert keys == sorted(keys)


def test_catalog_is_an_immutable_tuple() -> None:
    result = descriptors()
    assert isinstance(result, tuple)
    with pytest.raises(TypeError):
        result[0] = None  # type: ignore[index]


def test_catalog_cannot_be_mutated_through_a_returned_reference() -> None:
    before = descriptors()
    _ = list(before)  # copying is fine; the catalog itself is unchanged
    assert descriptors() == before


def test_descriptors_for_returns_only_that_family() -> None:
    trend = descriptors_for(EvidenceFamily.TREND)
    assert len(trend) == 3
    assert all(d.family is EvidenceFamily.TREND for d in trend)
    assert isinstance(trend, tuple)


def test_descriptors_for_empty_family_is_empty_not_an_error() -> None:
    for family in (EvidenceFamily.VOLUME, EvidenceFamily.VOLATILITY,
                   EvidenceFamily.RELATIVE_STRENGTH, EvidenceFamily.MACRO,
                   EvidenceFamily.NEWS, EvidenceFamily.SENTIMENT,
                   EvidenceFamily.LIQUIDITY, EvidenceFamily.MARKET_STRUCTURE):
        assert descriptors_for(family) == ()


def test_descriptors_for_rejects_a_non_family() -> None:
    with pytest.raises(TypeError, match="family must be an EvidenceFamily"):
        descriptors_for("trend")


def test_find_returns_the_descriptor_or_none() -> None:
    assert find("rsi_zone").family is EvidenceFamily.MOMENTUM
    assert find("price_vs_ema_fast").family is EvidenceFamily.TREND
    assert find("not_catalogued") is None


def test_find_matches_exactly() -> None:
    assert find("RSI_ZONE") is None
    assert find(" rsi_zone") is None


def test_find_rejects_a_non_str() -> None:
    with pytest.raises(TypeError, match="name must be a str"):
        find(7)


def test_every_catalogued_name_is_unique() -> None:
    names = [d.name for d in descriptors()]
    assert len(names) == len(set(names))


def test_every_catalogued_family_name_pair_is_unique() -> None:
    pairs = [(d.family, d.name) for d in descriptors()]
    assert len(pairs) == len(set(pairs))


# ============================ duplicate rejection ============================


def _validated():
    from fmis.evidence.catalog import _validated as v

    return v


def test_duplicate_name_in_the_same_family_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate descriptor name 'dup'"):
        _validated()((
            EvidenceDescriptor(EvidenceFamily.TREND, "dup", "One."),
            EvidenceDescriptor(EvidenceFamily.TREND, "dup", "Two."),
        ))


def test_duplicate_name_across_families_is_also_rejected() -> None:
    # Global uniqueness: the same name in two families is ambiguous to `find`.
    with pytest.raises(ValueError, match="duplicate descriptor name 'dup'"):
        _validated()((
            EvidenceDescriptor(EvidenceFamily.TREND, "dup", "One."),
            EvidenceDescriptor(EvidenceFamily.MACRO, "dup", "Two."),
        ))


def test_distinct_names_are_accepted_and_sorted() -> None:
    result = _validated()((
        EvidenceDescriptor(EvidenceFamily.MOMENTUM, "b_concept", "B."),
        EvidenceDescriptor(EvidenceFamily.TREND, "z_concept", "Z."),
        EvidenceDescriptor(EvidenceFamily.TREND, "a_concept", "A."),
    ))
    assert [d.name for d in result] == ["a_concept", "z_concept", "b_concept"]


def test_no_mutable_global_registry_exists() -> None:
    import fmis.evidence.catalog as catalog

    for name in dir(catalog):
        obj = getattr(catalog, name)
        if name.isupper() or name.startswith("_CATALOG"):
            assert not isinstance(obj, (list, dict, set)), name
    assert isinstance(catalog._CATALOG, tuple)
    # No registration entry point of any kind.
    for forbidden in ("register", "add_descriptor", "unregister", "clear"):
        assert not hasattr(catalog, forbidden), forbidden


# ============================ catalogued == genuinely interpreted =============


def test_every_descriptor_matches_an_observation_the_system_emits() -> None:
    """The catalog must describe reality, not intent.

    This test imports `decision_support` — the package under test deliberately
    does not. It builds a real report and asserts every catalogued name is an
    observation key that is actually produced and actually classified.
    """
    import json
    from datetime import datetime, timezone

    from fmis.decision_support import build_evidence_report
    from fmis.pipeline import analyze_symbol
    from fmis.providers.binance import HttpResponse

    open_ms, step = 1_704_067_200_000, 4 * 3600 * 1000

    def kline(i: int, close: float) -> list[object]:
        start = open_ms + i * step
        return [
            start, f"{close:.2f}", f"{close * 1.01:.2f}", f"{close * 0.99:.2f}",
            f"{close:.2f}", "1000.0", start + step - 1,
            "1.0", 1, "1.0", "1.0", "0",
        ]

    payload = [kline(i, 100.0 * (1.02 ** i)) for i in range(60)]
    snapshot = analyze_symbol(
        "BTCUSDT", "4h",
        transport=lambda url: HttpResponse(200, json.dumps(payload).encode()),
        clock=lambda: datetime(2024, 6, 1, tzinfo=timezone.utc),
    )
    report = build_evidence_report(snapshot)

    emitted = {
        o.key: o for o in report.trend.observations + report.momentum.observations
    }
    for d in descriptors():
        assert d.name in emitted, f"{d.name} is catalogued but never emitted"
        assert emitted[d.name].classification, f"{d.name} emits no classification"


def test_uninterpreted_measurements_are_not_catalogued() -> None:
    """A calculated value that nothing classifies must not appear as evidence."""
    for uninterpreted in (
        # computed, classification deferred by ADR-0010
        "relative_volume_20", "average_volume_20",
        # reported as raw values only, never classified
        "atr_14", "atr_percent_of_close",
        # restated from the RVE unchanged, never classified
        "relative_return", "volatility_ratio", "pearson_correlation", "period_return",
        # raw indicator outputs
        "ema_20", "ema_50", "rsi_close_14",
    ):
        assert find(uninterpreted) is None, uninterpreted


def test_families_without_interpretation_stay_empty() -> None:
    # Volume is computed today; ADR-0010 deferred classifying it, so no descriptor.
    assert descriptors_for(EvidenceFamily.VOLUME) == ()
    # The RVE metrics are restated unchanged, never classified.
    assert descriptors_for(EvidenceFamily.RELATIVE_STRENGTH) == ()
    # ATR and ATR% are raw values on VolatilityEvidence, with no Observation.
    assert descriptors_for(EvidenceFamily.VOLATILITY) == ()


# ============================ no duplication of owned concepts ===============


def test_no_evidence_type_enum_exists() -> None:
    """SUPPORTING/CONFLICTING/NEUTRAL/UNAVAILABLE are owned elsewhere.

    They are two different dimensions — relationship to a hypothesis, and data
    availability — and `decision_support` already models both.
    """
    from enum import Enum

    for name in dir(ev):
        obj = getattr(ev, name)
        if isinstance(obj, type) and issubclass(obj, Enum):
            members = {m.name for m in obj}
            for owned in ("SUPPORTING", "CONFLICTING", "UNAVAILABLE",
                          "INSUFFICIENT_DATA", "NEUTRAL"):
                assert owned not in members, f"{name} redefines {owned}"
    assert not hasattr(ev, "EvidenceType")


def test_package_defines_exactly_one_enum() -> None:
    from enum import Enum
    import fmis.evidence.families as families

    enums = [
        n for n in dir(families)
        if isinstance(getattr(families, n), type)
        and issubclass(getattr(families, n), Enum)
        and getattr(families, n) is not Enum
    ]
    assert enums == ["EvidenceFamily"]


# ============================ public API / boundaries ========================


def _package_sources() -> list[Path]:
    return sorted(PACKAGE_DIR.glob("*.py"))


def _internal_imports() -> set[str]:
    found: set[str] = set()
    for py in _package_sources():
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("fmis"):
                    found.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("fmis"):
                        found.add(alias.name)
    return found


def test_public_api_exports() -> None:
    assert set(ev.__all__) == {
        "EvidenceFamily", "EvidenceDescriptor",
        "descriptors", "descriptors_for", "find",
    }
    for name in ev.__all__:
        assert hasattr(ev, name)


def test_all_is_exact_and_ordered_as_declared() -> None:
    assert ev.__all__ == [
        "EvidenceFamily", "EvidenceDescriptor",
        "descriptors", "descriptors_for", "find",
    ]


def test_star_import_exposes_exactly_the_public_api() -> None:
    namespace: dict[str, object] = {}
    exec("from fmis.evidence import *", namespace)  # noqa: S102
    exposed = {k for k in namespace if not k.startswith("__")}
    assert exposed == set(ev.__all__)


# ============================ module namespace hygiene =======================
#
# The module holding `EvidenceDescriptor` is `descriptor` (singular) precisely so
# it cannot collide with the public `descriptors()` function. When both were
# named `descriptors`, the package attribute resolved to the function even after
# `import fmis.evidence.descriptors`, so `fmis.evidence.descriptors.EvidenceDescriptor`
# raised AttributeError while `from fmis.evidence.descriptors import ...` worked.


def test_descriptors_attribute_is_the_public_function() -> None:
    assert callable(ev.descriptors)
    assert not isinstance(ev.descriptors, ModuleType)
    assert ev.descriptors() == descriptors()


def test_descriptor_attribute_is_the_submodule_after_explicit_import() -> None:
    import fmis.evidence.descriptor  # noqa: PLC0415

    assert isinstance(fmis.evidence.descriptor, ModuleType)
    assert fmis.evidence.descriptor.__name__ == "fmis.evidence.descriptor"
    assert fmis.evidence.descriptor.EvidenceDescriptor is EvidenceDescriptor


def test_evidence_descriptor_identity_is_stable_across_imports() -> None:
    from fmis.evidence import EvidenceDescriptor as from_package
    from fmis.evidence.descriptor import EvidenceDescriptor as from_submodule
    import fmis.evidence.descriptor as module  # noqa: PLC0415

    assert from_package is from_submodule is module.EvidenceDescriptor


def test_no_submodule_shares_a_name_with_a_public_object() -> None:
    submodules = {m.name for m in pkgutil.iter_modules(ev.__path__)}
    assert submodules == {"catalog", "descriptor", "families"}
    assert submodules & set(ev.__all__) == set()


def test_no_package_in_the_repository_has_such_a_collision() -> None:
    """Regression guard for the whole tree, not just this package.

    A submodule sharing a name with an exported object is shadowed at the package
    attribute, silently and only for attribute access. Cheap to check everywhere.
    """
    collisions: dict[str, list[str]] = {}
    for name in (
        "fmis.data", "fmis.ingest", "fmis.providers", "fmis.features",
        "fmis.features.indicators", "fmis.features.volume", "fmis.alignment",
        "fmis.relative_value", "fmis.pipeline", "fmis.decision_support",
        "fmis.trading_context", "fmis.evidence",
    ):
        module = importlib.import_module(name)
        if not hasattr(module, "__path__"):
            continue
        submodules = {m.name for m in pkgutil.iter_modules(module.__path__)}
        clash = sorted(submodules & set(getattr(module, "__all__", [])))
        if clash:
            collisions[name] = clash
    assert collisions == {}


def test_old_plural_module_path_is_gone_without_an_alias() -> None:
    # The package has no released external API and nothing imported the module
    # path, so no compatibility shim was added.
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fmis.evidence.descriptors")


def test_imports_nothing_outside_its_own_package() -> None:
    assert _internal_imports() <= {
        "fmis.evidence.catalog",
        "fmis.evidence.descriptor",
        "fmis.evidence.families",
    }


@pytest.mark.parametrize(
    "forbidden",
    ["fmis.decision_support", "fmis.pipeline", "fmis.providers", "fmis.ingest",
     "fmis.features", "fmis.alignment", "fmis.relative_value",
     "fmis.trading_context", "fmis.data"],
)
def test_does_not_depend_on_any_other_layer(forbidden: str) -> None:
    assert not any(i.startswith(forbidden) for i in _internal_imports()), forbidden


def test_decision_support_was_not_made_to_depend_on_this_package() -> None:
    for py in (SRC / "decision_support").rglob("*.py"):
        assert "fmis.evidence" not in py.read_text(), str(py)


def test_no_existing_package_imports_the_taxonomy() -> None:
    offenders: list[str] = []
    for package in ("data", "ingest", "providers", "features", "alignment",
                    "relative_value", "pipeline", "decision_support",
                    "trading_context"):
        for py in (SRC / package).rglob("*.py"):
            if "fmis.evidence" in py.read_text():
                offenders.append(str(py))
    assert offenders == []


def test_scanned_packages_actually_exist() -> None:
    # Guards the scan above from silently passing if a package is renamed.
    for package in ("data", "ingest", "providers", "features", "alignment",
                    "relative_value", "pipeline", "decision_support",
                    "trading_context"):
        assert (SRC / package / "__init__.py").is_file(), package


def test_importing_the_taxonomy_loads_nothing_else(fresh_fmis_imports: None) -> None:
    import fmis.evidence  # noqa: F401

    loaded = {m for m in sys.modules if m.startswith("fmis.")}
    assert loaded <= {
        "fmis.evidence", "fmis.evidence.catalog",
        "fmis.evidence.descriptor", "fmis.evidence.families",
    }


def test_uses_only_stdlib() -> None:
    roots: set[str] = set()
    for py in _package_sources():
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
    assert roots <= set(sys.stdlib_module_names) | {"fmis"}
    for forbidden in ("urllib", "http", "socket", "openai", "anthropic", "sqlite3"):
        assert forbidden not in roots, forbidden


# ============================ no behaviour / no scoring ======================


def _code_tokens(path: Path) -> set[str]:
    """Identifiers and non-docstring string values in one module.

    Docstrings are excluded: this package's documentation must name the concepts
    it refuses to define (scores, confidence, supporting/conflicting), and a raw
    text scan would read that prose as the violation it warns against.
    """
    tree = ast.parse(path.read_text())
    docstrings = {
        d for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and (d := ast.get_docstring(node, clean=False)) is not None
    }
    tokens: set[str] = set()

    def add(text: str) -> None:
        lowered = text.lower()
        tokens.add(lowered)
        tokens.update(re.split(r"[^a-z0-9]+", lowered))

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                add(node.value)
        elif isinstance(node, ast.Name):
            add(node.id)
        elif isinstance(node, ast.Attribute):
            add(node.attr)
        elif isinstance(node, ast.arg):
            add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            add(node.name)
    return tokens


def test_no_trading_action_vocabulary_in_code() -> None:
    """No action words in code.

    "signal" is deliberately absent from this list. It occurs in
    ``macd_vs_signal`` and its description, where it names MACD's *signal line* —
    a component of the indicator and the exact observation key
    `decision_support` emits. Renaming it to avoid a word would break the
    correspondence the catalog exists to maintain. The requirement that matters
    is that SIGNAL is not an `EvidenceFamily` member, which
    `test_family_has_no_trading_action_members` asserts directly.
    """
    for py in _package_sources():
        tokens = _code_tokens(py)
        for word in ("buy", "sell", "bullish", "bearish", "entry", "stop",
                     "target", "position", "leverage", "execute", "trade"):
            assert word not in tokens, f"{py.name}: {word}"


def test_no_scoring_weighting_or_confidence_in_code() -> None:
    for py in _package_sources():
        tokens = _code_tokens(py)
        for word in ("score", "weight", "weighted", "confidence", "rank",
                     "ranking", "probability", "threshold"):
            assert word not in tokens, f"{py.name}: {word}"


def test_package_performs_no_arithmetic() -> None:
    for py in _package_sources():
        operators = [
            node for node in ast.walk(ast.parse(py.read_text()))
            if isinstance(node, ast.BinOp)
            and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div,
                                     ast.FloorDiv, ast.Pow, ast.Mod))
        ]
        assert operators == [], py.name


def test_descriptions_state_relationships_not_conclusions() -> None:
    for d in descriptors():
        lowered = d.description.lower()
        for word in ("bullish", "bearish", "strong", "weak", "confirm",
                     "buy", "sell", "should", "suggests", "indicates"):
            assert word not in lowered, f"{d.name}: {word}"
