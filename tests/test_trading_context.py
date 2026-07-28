"""Tests for the trading analysis context (fmis.trading_context).

The type has no behaviour, so these tests are about the contract: which
objectives exist, what is rejected, what is stored exactly as given, and which
dependencies the package is not allowed to acquire.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

import fmis.trading_context as tc
from fmis.trading_context import TradingAnalysisContext, TradingObjective

PACKAGE_DIR = Path(tc.__file__).parent


def context(**overrides: object) -> TradingAnalysisContext:
    """A valid context; override one field to exercise a failure case."""
    kwargs: dict[str, object] = {
        "objective": TradingObjective.SWING_TRADE,
        "primary_timeframe": "4h",
    }
    kwargs.update(overrides)
    return TradingAnalysisContext(**kwargs)  # type: ignore[arg-type]


# ============================ TradingObjective ===============================


def test_objective_members_are_exactly_swing_and_day() -> None:
    assert {o.name for o in TradingObjective} == {"SWING_TRADE", "DAY_TRADE"}


def test_long_term_investment_is_absent() -> None:
    # Long-term investing is a separate module, not a trading objective.
    assert not hasattr(TradingObjective, "LONG_TERM_INVESTMENT")
    names = {o.name for o in TradingObjective}
    values = {o.value for o in TradingObjective}
    for forbidden in ("LONG_TERM_INVESTMENT", "INVESTMENT", "LONG_TERM", "HODL"):
        assert forbidden not in names
    for token in ("invest", "long_term", "portfolio"):
        assert not any(token in v for v in values)


def test_objective_values_are_stable_strings() -> None:
    assert TradingObjective.SWING_TRADE.value == "swing_trade"
    assert TradingObjective.DAY_TRADE.value == "day_trade"


def test_objective_is_a_str_enum_matching_repository_convention() -> None:
    assert isinstance(TradingObjective.SWING_TRADE, str)


def test_objective_members_cannot_be_reassigned() -> None:
    with pytest.raises(AttributeError):
        TradingObjective.SWING_TRADE = "something else"  # type: ignore[misc]


# ============================ construction / defaults ========================


def test_minimal_construction_and_defaults() -> None:
    ctx = context()
    assert ctx.objective is TradingObjective.SWING_TRADE
    assert ctx.primary_timeframe == "4h"
    assert ctx.supporting_timeframes == ()
    assert ctx.benchmark_symbol is None
    assert ctx.notes is None


def test_full_construction() -> None:
    ctx = context(
        objective=TradingObjective.DAY_TRADE,
        primary_timeframe="15m",
        supporting_timeframes=("1h", "4h"),
        benchmark_symbol="ETHUSDT",
        notes="range session",
    )
    assert ctx.objective is TradingObjective.DAY_TRADE
    assert ctx.supporting_timeframes == ("1h", "4h")
    assert ctx.benchmark_symbol == "ETHUSDT"
    assert ctx.notes == "range session"


def test_construction_is_deterministic() -> None:
    assert context(supporting_timeframes=["1d", "1w"]) == context(
        supporting_timeframes=["1d", "1w"]
    )


def test_equality_is_by_value() -> None:
    assert context() == context()
    assert context() != context(primary_timeframe="1h")
    assert context() != context(objective=TradingObjective.DAY_TRADE)
    assert context() != context(benchmark_symbol="ETHUSDT")


def test_timeframes_accessor_puts_primary_first() -> None:
    ctx = context(supporting_timeframes=("1d", "1w"))
    assert ctx.timeframes == ("4h", "1d", "1w")


# ============================ immutability ===================================


def test_context_is_frozen() -> None:
    ctx = context()
    with pytest.raises(FrozenInstanceError):
        ctx.primary_timeframe = "1h"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        ctx.objective = TradingObjective.DAY_TRADE  # type: ignore[misc]


def test_supporting_timeframes_stored_as_tuple() -> None:
    ctx = context(supporting_timeframes=["1d", "1w"])
    assert isinstance(ctx.supporting_timeframes, tuple)
    assert ctx.supporting_timeframes == ("1d", "1w")


def test_mutating_the_input_collection_cannot_mutate_the_context() -> None:
    supplied = ["1d", "1w"]
    ctx = context(supporting_timeframes=supplied)
    supplied.append("1M")
    supplied[0] = "changed"
    assert ctx.supporting_timeframes == ("1d", "1w")


def test_supporting_timeframes_accepts_any_iterable() -> None:
    assert context(supporting_timeframes=iter(["1d"])).supporting_timeframes == ("1d",)
    assert context(supporting_timeframes=("1d",)).supporting_timeframes == ("1d",)


def test_order_is_preserved_not_sorted() -> None:
    # Deliberately not alphabetical: the caller's order is their stated priority.
    given = ["1w", "1d", "1h"]
    assert context(supporting_timeframes=given).supporting_timeframes == (
        "1w", "1d", "1h",
    )


# ============================ validation =====================================


@pytest.mark.parametrize("bad", ["", "   ", "\t"])
def test_empty_primary_timeframe_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="primary_timeframe cannot be empty"):
        context(primary_timeframe=bad)


def test_non_str_primary_timeframe_rejected() -> None:
    with pytest.raises(TypeError, match="primary_timeframe must be a str"):
        context(primary_timeframe=4)


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_supporting_timeframe_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match=r"supporting_timeframes\[1\] cannot be empty"):
        context(supporting_timeframes=["1d", bad])


def test_non_str_supporting_timeframe_rejected() -> None:
    with pytest.raises(TypeError, match=r"supporting_timeframes\[0\] must be a str"):
        context(supporting_timeframes=[15])


def test_duplicate_supporting_timeframes_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate supporting timeframe '1d'"):
        context(supporting_timeframes=["1d", "1w", "1d"])


def test_primary_timeframe_cannot_also_be_supporting() -> None:
    with pytest.raises(ValueError, match="must not also appear"):
        context(primary_timeframe="4h", supporting_timeframes=["1d", "4h"])


def test_case_differences_are_distinct_labels() -> None:
    # No normalization is applied, so '4h' and '4H' are two different labels.
    ctx = context(primary_timeframe="4h", supporting_timeframes=["4H"])
    assert ctx.supporting_timeframes == ("4H",)


def test_a_bare_string_is_not_accepted_as_supporting_timeframes() -> None:
    # tuple("1d") would silently become ('1', 'd'); that must never happen.
    with pytest.raises(TypeError, match="not a single string"):
        context(supporting_timeframes="1d")


def test_non_iterable_supporting_timeframes_rejected() -> None:
    with pytest.raises(TypeError, match="must be an iterable"):
        context(supporting_timeframes=42)


def test_invalid_objective_rejected() -> None:
    with pytest.raises(TypeError, match="objective must be a TradingObjective"):
        context(objective="swing_trade")


@pytest.mark.parametrize("field", ["benchmark_symbol", "notes"])
def test_optional_fields_reject_blank_but_accept_absent(field: str) -> None:
    assert getattr(context(**{field: None}), field) is None
    with pytest.raises(ValueError, match=f"{field} cannot be empty"):
        context(**{field: "   "})


def test_timeframe_syntax_is_not_validated() -> None:
    # No canonical timeframe vocabulary exists, so no syntax rule is invented.
    for label in ("4h", "4H", "H4", "240", "quarterly", "P1D"):
        assert context(primary_timeframe=label).primary_timeframe == label


# ============================ no decision content ============================


def test_no_trading_action_vocabulary_in_field_names() -> None:
    banned = (
        "buy", "sell", "long", "short", "direction", "entry", "exit", "stop",
        "target", "size", "sizing", "leverage", "risk", "confidence", "score",
        "strategy", "allocation", "position", "holding", "quantity",
    )
    names = {f.name for f in fields(TradingAnalysisContext)}
    tokens: set[str] = set()
    for name in names:
        tokens |= set(name.split("_")) | {name}
    for word in banned:
        assert word not in tokens, word


def test_no_speculative_fields_present() -> None:
    assert {f.name for f in fields(TradingAnalysisContext)} == {
        "objective", "primary_timeframe", "supporting_timeframes",
        "benchmark_symbol", "notes",
    }


def _package_sources() -> list[Path]:
    return sorted(PACKAGE_DIR.glob("*.py"))


def test_no_objective_dependent_branching_anywhere() -> None:
    """No member is referenced outside its own definition.

    Branching on *which* objective it is would be per-objective behaviour, which
    belongs to a layer that has behaviour. Type validation against the enum
    itself is fine; naming a member is not.
    """
    offenders: list[str] = []
    for py in _package_sources():
        for node in ast.walk(ast.parse(py.read_text())):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "TradingObjective"
            ):
                offenders.append(f"{py.name}:{node.lineno} -> .{node.attr}")
    assert offenders == []


def _code_tokens(py: Path) -> set[str]:
    """Identifiers and non-docstring string values in one module.

    Docstrings and comments are excluded deliberately: prose may state what the
    package does not do (e.g. "no timeframe presets") without that being a
    preset. Only code can embody a rule.
    """
    tree = ast.parse(py.read_text())
    docstrings = {
        d for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and (d := ast.get_docstring(node, clean=False)) is not None
    }
    tokens: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                tokens |= set(re.findall(r"[a-z_]+", node.value.lower()))
        elif isinstance(node, ast.Name):
            tokens.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            tokens.add(node.attr.lower())
        elif isinstance(node, ast.arg):
            tokens.add(node.arg.lower())
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            tokens.add(node.name.lower())
    expanded: set[str] = set()
    for token in tokens:
        expanded |= set(token.split("_")) | {token}
    return expanded


def test_package_defines_no_timeframe_presets() -> None:
    # A preset or default timeframe would be the module choosing for the caller.
    for py in _package_sources():
        tokens = _code_tokens(py)
        for token in ("preset", "presets", "recommended"):
            assert token not in tokens, f"{py.name}: {token}"


def test_package_contains_no_arithmetic() -> None:
    for py in _package_sources():
        operators = [
            node for node in ast.walk(ast.parse(py.read_text()))
            if isinstance(node, ast.BinOp)
            and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div,
                                     ast.FloorDiv, ast.Pow, ast.Mod))
        ]
        assert operators == [], py.name


# ============================ public API / boundaries ========================


def test_public_api_exports() -> None:
    assert set(tc.__all__) == {"TradingObjective", "TradingAnalysisContext"}
    for name in tc.__all__:
        assert hasattr(tc, name)


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


def test_imports_nothing_outside_its_own_package() -> None:
    assert _internal_imports() <= {"fmis.trading_context.context"}


@pytest.mark.parametrize(
    "forbidden",
    ["fmis.pipeline", "fmis.decision_support", "fmis.providers", "fmis.ingest",
     "fmis.features", "fmis.alignment", "fmis.relative_value", "fmis.data"],
)
def test_does_not_depend_on_other_layers(forbidden: str) -> None:
    assert not any(i.startswith(forbidden) for i in _internal_imports()), forbidden


def test_uses_no_third_party_or_io_modules() -> None:
    roots: set[str] = set()
    for py in _package_sources():
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
    assert roots <= set(sys.stdlib_module_names) | {"fmis"}
    for forbidden in ("urllib", "http", "socket", "json", "sqlite3", "pickle",
                      "os", "pathlib", "subprocess"):
        assert forbidden not in roots, forbidden


def test_no_lower_or_sibling_layer_imports_trading_context() -> None:
    src = PACKAGE_DIR.parent  # src/fmis
    offenders: list[str] = []
    for package in ("data", "ingest", "providers", "features", "alignment",
                    "relative_value", "pipeline", "decision_support"):
        for py in (src / package).rglob("*.py"):
            if "trading_context" in py.read_text():
                offenders.append(str(py))
    assert offenders == []


def test_scanned_packages_actually_exist() -> None:
    # Guards the test above from silently passing if a package is renamed.
    src = PACKAGE_DIR.parent
    for package in ("data", "ingest", "providers", "features", "alignment",
                    "relative_value", "pipeline", "decision_support"):
        assert (src / package / "__init__.py").is_file(), package


def test_importing_trading_context_loads_nothing_else(
    fresh_fmis_imports: None,
) -> None:
    import fmis.trading_context  # noqa: F401

    loaded = {m for m in sys.modules if m.startswith("fmis.")}
    assert loaded <= {"fmis.trading_context", "fmis.trading_context.context"}


def test_no_investment_vocabulary_in_the_package() -> None:
    """Investment analysis is a separate future module, not this one.

    Prose may explain the exclusion; identifiers and values may not embody it.
    """
    for py in _package_sources():
        tokens = _code_tokens(py)
        for word in ("thesis", "fundamentals", "valuation", "catalyst",
                     "dividend", "earnings", "portfolio"):
            assert word not in tokens, f"{py.name}: {word}"
