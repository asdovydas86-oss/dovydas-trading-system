"""The boundaries around `fmis.price_zones`, asserted rather than intended.

A zone is a **description of the market**. The failure this file exists to make
impossible is the one report 0050 names in §9 and §10: a description becoming a
permission. Zone evidence independence is `NOT ESTABLISHED` — zones derive from
the same confirmed pivots as structural trend, so they share upstream information
with it — and until research question **R15** measures that, a zone may reach an
operator's eyes and nothing else.

Every test here walks real source or real objects. None asserts on a comment.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from architecture_tiers import PRODUCTION_PACKAGES, source_root

from fmis.price_zones import (
    PRICE_ZONE_LIMITATIONS,
    derive_price_zones,
    engine,
    models,
)
from fmis.price_zones.models import PriceZone, PriceZoneSet, ZoneWidthPolicy

from tests.price_zone_helpers import atr_series_of, levels_of, seeded_series

PACKAGE = source_root() / "price_zones"

#: Packages `fmis.price_zones` may import. Everything it needs to describe an
#: area and nothing that could turn one into a decision.
PERMITTED_IMPORTS = {"data", "features", "level_crossing", "price_zones"}

#: Packages that must never appear in an import inside `fmis.price_zones`. Each
#: one is a place where a zone would stop being a description.
FORBIDDEN_IMPORTS = {
    "swing_setup",
    "swing_workspace",
    "setup_evidence",
    "evidence",
    "decision_support",
    "decision_context",
    "market_regime",
    "risk",
    "risk_policy",
    "position_sizing",
    "portfolio_risk",
    "scan_memory",
    "pipeline",
    "operator_dashboard",
    "daily",
    "today",
    "swing_lab",
}


#: ``zone`` as a whole word. ``timezone`` and ``display_timezone`` are not zones,
#: and a substring guard that called them one would be widened until it guarded
#: nothing.
_WORD_ZONE = re.compile(r"(?<![A-Za-z_])[Zz]ones?(?![A-Za-z_])")


def _whole_word(word: str) -> re.Pattern[str]:
    """``word`` as a whole word, where ``_`` counts as a **boundary**.

    ``support_zone`` must be caught and ``supports_series`` — the production
    predicate ADR-0031 published — must not. A plain ``\\b`` gets both of those
    backwards, because ``_`` is a word character to ``re`` and ``s`` is not a
    boundary.
    """
    return re.compile(rf"(?<![A-Za-z]){word}(?![A-Za-z])", re.IGNORECASE)


def _modules_under(package: Path) -> list[Path]:
    return sorted(path for path in package.rglob("*.py"))


def _imported_fmis_packages(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if parts[0] == "fmis" and len(parts) > 1:
                found.add(parts[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "fmis" and len(parts) > 1:
                    found.add(parts[1])
    return found


class TestTheImportBoundary:
    def test_the_package_is_classified_production(self) -> None:
        assert "price_zones" in PRODUCTION_PACKAGES

    def test_it_imports_only_what_it_needs_to_describe_an_area(self) -> None:
        for path in _modules_under(PACKAGE):
            extra = _imported_fmis_packages(path) - PERMITTED_IMPORTS
            assert not extra, f"{path.name} imports {sorted(extra)}"

    @pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_IMPORTS))
    def test_no_module_reaches_a_package_that_would_make_a_zone_a_decision(
        self, forbidden: str
    ) -> None:
        for path in _modules_under(PACKAGE):
            assert forbidden not in _imported_fmis_packages(path), (
                f"{path.name} imports fmis.{forbidden}; a zone that can see a "
                "policy is one line from being read by it"
            )

    def test_nothing_in_production_imports_the_research_harness(self) -> None:
        """`research/zone_semantics` demonstrated the semantics; it never ships.

        Checked on the **import graph**, not on the text: `research_design` is a
        production package whose prose mentions research constantly, and a
        substring guard would either fail on it or be widened until it guarded
        nothing.
        """
        root = source_root()
        offenders = []
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                roots: set[str] = set()
                if isinstance(node, ast.ImportFrom) and node.module:
                    roots.add(node.module.split(".")[0])
                elif isinstance(node, ast.Import):
                    roots.update(alias.name.split(".")[0] for alias in node.names)
                if "research" in roots:
                    offenders.append(path.relative_to(root).as_posix())
        assert offenders == []

    def test_no_engine_below_the_zones_imports_them_back(self) -> None:
        """`level_crossing`, `market_structure` and `features` stay unaware."""
        root = source_root()
        for package in ("level_crossing", "market_structure", "features", "data"):
            for path in (root / package).rglob("*.py"):
                assert "price_zones" not in _imported_fmis_packages(path), (
                    f"{package} imports fmis.price_zones — a cycle, and an "
                    "inversion of the layering"
                )


class TestItDelegatesRatherThanReimplements:
    def test_it_defines_no_swing_level_crossing_or_indicator_function(self) -> None:
        """The chain has one implementation each, and none of them is here."""
        forbidden_names = {
            "detect_swings",
            "compare_swing_sequence",
            "label_swing_sequence",
            "structural_levels",
            "derive_level_crossings",
            "crossing_kind",
            "true_ranges",
            "atr_from_ranges",
            "derive_structure_breaks",
        }
        for path in _modules_under(PACKAGE):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            defined = {
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            assert not defined & forbidden_names, sorted(defined & forbidden_names)

    def test_it_never_touches_an_individual_candle(self) -> None:
        """A zone is built from levels and a feature history, never from bars.

        `CandleSeries` is permitted in one place — `zone_width_series` hands it
        straight to the feature that owns the arithmetic — but `Candle` itself is
        not imported anywhere, so no OHLC field can be read here at all.
        """
        for path in _modules_under(PACKAGE):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                for alias in node.names
            }
            assert "Candle" not in imported, (
                f"{path.name} imports Candle; the levels already carry "
                "everything this layer is entitled to"
            )
            names = {
                node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
            }
            assert "volume" not in names and "candles" not in names, path.name

    def test_the_only_multiplication_of_k_is_the_policy_s_own(self) -> None:
        """A second `k * atr` anywhere would make the stamp stop being a recipe."""
        source = Path(inspect.getfile(engine)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        multiplications = [
            ast.unparse(node)
            for node in ast.walk(tree)
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult)
        ]
        assert multiplications == []
        model_source = Path(inspect.getfile(models)).read_text(encoding="utf-8")
        model_tree = ast.parse(model_source)
        in_policy = [
            ast.unparse(node)
            for node in ast.walk(model_tree)
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult)
        ]
        assert in_policy == ["self.multiple * feature_value"]

    def test_it_reads_no_clock_and_no_environment(self) -> None:
        """Checked on identifiers, not on text — the docstrings say these words."""
        forbidden = {
            "now",
            "utcnow",
            "today",
            "monotonic",
            "getenv",
            "random",
            "environ",
            "time",
        }
        for path in _modules_under(PACKAGE):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            used = {
                node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
            } | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
            assert not used & forbidden, f"{path.name} uses {sorted(used & forbidden)}"

    def test_it_holds_no_module_level_mutable_state(self) -> None:
        for path in _modules_under(PACKAGE):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = (
                    [node.target] if isinstance(node, ast.AnnAssign) else node.targets
                )
                if any(
                    isinstance(target, ast.Name)
                    and target.id.startswith("__")
                    and target.id.endswith("__")
                    for target in targets
                ):
                    continue  # `__all__` is the published API, not state
                value = node.value
                if isinstance(value, (ast.List, ast.Dict, ast.Set)):
                    raise AssertionError(
                        f"{path.name} holds a mutable module-level binding: "
                        f"{ast.unparse(node)}"
                    )


class TestNoZoneReachesADecision:
    """The R15 boundary, asserted on live objects rather than on intention."""

    def test_the_policy_input_gained_no_zone_field(self) -> None:
        from fmis.swing_setup.models import SetupInputs

        for field in SetupInputs.__dataclass_fields__:
            assert "zone" not in field.lower()

    def test_the_assessment_carries_no_zone(self) -> None:
        from fmis.swing_setup.models import SetupAssessment

        for field in SetupAssessment.__dataclass_fields__:
            assert "zone" not in field.lower()

    def test_no_evidence_type_can_hold_a_zone(self) -> None:
        from fmis.setup_evidence.models import EvidenceItem

        for field in EvidenceItem.__dataclass_fields__:
            assert "zone" not in field.lower()

    def test_the_policy_module_never_mentions_zones(self) -> None:
        for module in ("policy", "models", "decision_summary"):
            path = source_root() / "swing_setup" / f"{module}.py"
            assert "price_zone" not in path.read_text(encoding="utf-8").lower()

    def test_scan_memory_never_mentions_zones(self) -> None:
        """Whole word: `timezone` is not a zone, and a substring guard would say it is."""
        for path in (source_root() / "scan_memory").rglob("*.py"):
            assert not _WORD_ZONE.search(path.read_text(encoding="utf-8")), path.name

    def test_risk_and_sizing_never_mention_zones(self) -> None:
        for package in ("risk", "risk_policy", "position_sizing", "portfolio_risk"):
            for path in (source_root() / package).rglob("*.py"):
                assert not _WORD_ZONE.search(path.read_text(encoding="utf-8")), path


class TestTheRenderingLayerOwnsNoComputation:
    def test_the_dashboard_never_builds_a_zone_itself(self) -> None:
        for path in (source_root() / "operator_dashboard").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "derive_price_zones" not in source
            assert "ZoneWidthPolicy(" not in source

    def test_the_renderer_computes_no_distance_or_position_of_its_own(self) -> None:
        """Both come from the engine's methods; the page prints what it is given."""
        source = (source_root() / "operator_dashboard" / "render.py").read_text(
            encoding="utf-8"
        )
        assert "price_position(" not in source
        assert "distance_from(" not in source

    def test_the_section_builder_calls_the_engine_rather_than_reimplementing_it(
        self,
    ) -> None:
        source = (source_root() / "operator_dashboard" / "sections.py").read_text(
            encoding="utf-8"
        )
        assert "zone.price_position(close)" in source
        assert "zone.distance_from(close)" in source

    def test_the_selection_and_its_order_belong_to_the_engine(self) -> None:
        """The dashboard chooses **how many**, never which or in what order.

        A first attempt did sort here, and the repository's own guard —
        *"`sum`, `min`, `max` and `sorted` are how a presentation layer becomes an
        engine"* — caught it. The ordering moved onto `PriceZoneSet`, beside the
        set it orders.
        """
        path = source_root() / "operator_dashboard" / "sections.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "sorted" not in called
        methods = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert {"near", "nearest_above", "nearest_below", "zones_containing"} <= methods


class TestTheTypesRefuseAReading:
    @pytest.mark.parametrize(
        "forbidden",
        [
            "support",
            "resistance",
            "breakout",
            "retest",
            "reclaim",
            "acceptance",
            "false_breakout",
            "strength",
            "quality",
            "confidence",
            "score",
            "rank",
            "bullish",
            "bearish",
            "watch_long",
            "watch_short",
        ],
    )
    def test_no_such_word_appears_in_any_field_name_or_enum_value(
        self, forbidden: str
    ) -> None:
        for kind in (PriceZone, PriceZoneSet, ZoneWidthPolicy):
            for field in kind.__dataclass_fields__:
                assert forbidden not in field.lower()

    @pytest.mark.parametrize("forbidden", ["support", "resistance"])
    def test_neither_word_names_anything_the_package_defines(
        self, forbidden: str
    ) -> None:
        """`PRICE_ZONE_ENGINE_V1.md` §9: never *in any value or field name*.

        Asserted over every identifier the package binds — every class, function,
        argument, attribute, dataclass field and enum member — and over every
        string the package can ever hand to a caller: enum values, constants and
        the text of its own error messages.

        **Docstrings, comments and the package's own stated limitations are
        deliberately exempt**, and that is the point rather than a loophole: the
        only reason these two words appear in this package at all is to say that
        a zone is not either of them, and a guard that forbade the denial would
        delete the explanation and keep the risk. Each carve-out is pinned by a
        test of its own below, so it cannot quietly become something else — the
        pattern TA Slice 5A established for the rendered page.
        """
        exempt = {text for _code, text in PRICE_ZONE_LIMITATIONS}
        pattern = _whole_word(forbidden)
        for path in _modules_under(PACKAGE):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = {
                id(node.body[0].value)
                for node in ast.walk(tree)
                if isinstance(
                    node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                )
                and node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            }
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    assert not pattern.search(node.id), f"{path.name}: {node.id}"
                elif isinstance(node, ast.Attribute):
                    assert not pattern.search(node.attr), f"{path.name}: {node.attr}"
                elif isinstance(node, ast.arg):
                    assert not pattern.search(node.arg), f"{path.name}: {node.arg}"
                elif isinstance(
                    node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    assert not pattern.search(node.name), f"{path.name}: {node.name}"
                elif (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and id(node) not in docstrings
                    and node.value not in exempt
                ):
                    assert not pattern.search(node.value), (
                        f"{path.name} can hand a caller the string "
                        f"{node.value!r}"
                    )

    def test_the_package_states_the_prohibition_in_its_own_documentation(self) -> None:
        """The denial is load-bearing; removing it must fail, not pass quietly."""
        text = (PACKAGE / "__init__.py").read_text(encoding="utf-8").lower()
        assert "support and resistance appear in no field, value or message" in text

    def test_the_one_exempt_limitation_is_a_denial_and_stays_one(self) -> None:
        """The carve-out, pinned. `PZ-2` may say the words only to refuse them."""
        stated = dict(PRICE_ZONE_LIMITATIONS)
        using = [
            code
            for code, text in PRICE_ZONE_LIMITATIONS
            if "support" in text.lower() or "resistance" in text.lower()
        ]
        assert using == ["PZ-2"]
        assert "is not support" in stated["PZ-2"]
        assert "is not resistance" in stated["PZ-2"]

    def test_a_real_zone_set_exposes_no_attribute_naming_a_reading(self) -> None:
        series = seeded_series(400, seed=7, drift=0.004)
        zone_set = derive_price_zones(levels_of(series), atr_series_of(series))
        names = set(dir(zone_set)) | set(dir(zone_set.zones[0]))
        for forbidden in ("role", "strength", "score", "rank", "confidence"):
            assert not any(
                forbidden in name for name in names if not name.startswith("_")
            ), forbidden
