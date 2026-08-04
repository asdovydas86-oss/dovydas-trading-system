"""Milestone AN — the daily-run value types.

The promises the whole milestone rests on live in the model: every requested
symbol produces exactly one result, the order is the caller's, a failure carries
its reason, counts are derived rather than stored, and **nothing ranks**.
"""

from __future__ import annotations

import ast
import pathlib
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from fmis.daily.models import (
    DAILY_SCHEMA_VERSION,
    MAXIMUM_SYMBOLS,
    DailyRun,
    DailyRunError,
    FailureKind,
    ResultCategory,
    SymbolFailure,
    SymbolResult,
    require_symbols,
)

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
DAILY_SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "fmis" / "daily"


# ============================ fixtures =======================================


def failure(kind: FailureKind = FailureKind.PROVIDER_FAILURE) -> SymbolFailure:
    return SymbolFailure(kind=kind, detail="the request timed out", exception_type="E")


def completed(symbol: str = "BTCUSDT", **overrides) -> SymbolResult:
    fields = dict(
        requested_symbol=symbol,
        category=ResultCategory.SUFFICIENT,
        resolved_symbol=symbol,
        workspace=object(),
        context=object(),
    )
    fields.update(overrides)
    return SymbolResult(**fields)  # type: ignore[arg-type]


def failed(symbol: str = "NOPE", **overrides) -> SymbolResult:
    fields = dict(
        requested_symbol=symbol,
        category=ResultCategory.FAILED,
        failure=failure(),
    )
    fields.update(overrides)
    return SymbolResult(**fields)  # type: ignore[arg-type]


def run(**overrides) -> DailyRun:
    fields = dict(
        reference_time=_BASE,
        results=(completed(), failed()),
        objective="swing_trade",
        source="fixture",
        limitations=(("AN-0", "a fixture limitation"),),
    )
    fields.update(overrides)
    return DailyRun(**fields)  # type: ignore[arg-type]


# ============ 1. one result per requested symbol ============================


def test_a_run_carries_one_result_per_symbol_in_input_order() -> None:
    """The order is the contract: reordering by any analysis property is a ranking."""
    order = ("SOLUSDT", "BTCUSDT", "ETHUSDT")
    built = run(results=tuple(completed(s) for s in order))
    assert built.requested_symbols == order


def test_a_run_needs_at_least_one_result() -> None:
    with pytest.raises(DailyRunError, match="at least one result"):
        run(results=())


def test_a_failed_symbol_still_occupies_a_row() -> None:
    """A dropped row is indistinguishable from a symbol nobody asked about."""
    built = run(results=(completed("BTCUSDT"), failed("NOPE"), completed("ETHUSDT")))
    assert built.requested_symbols == ("BTCUSDT", "NOPE", "ETHUSDT")
    assert built.by_symbol("NOPE") is not None


def test_by_symbol_matches_what_the_caller_typed() -> None:
    built = run(results=(completed("BTCUSDT", resolved_symbol="BTC-USD"),))
    assert built.by_symbol("BTCUSDT") is built.results[0]
    assert built.by_symbol("BTC-USD") is None
    assert built.by_symbol("ETHUSDT") is None


# ============ 2. a result cannot be internally inconsistent =================


def test_a_failed_result_must_carry_its_failure() -> None:
    with pytest.raises(DailyRunError, match="must carry its failure"):
        SymbolResult(requested_symbol="X", category=ResultCategory.FAILED)


def test_a_failed_result_cannot_carry_an_analysis() -> None:
    for extra in ({"workspace": object()}, {"context": object()}):
        with pytest.raises(DailyRunError, match="cannot carry a workspace"):
            SymbolResult(
                requested_symbol="X",
                category=ResultCategory.FAILED,
                failure=failure(),
                **extra,  # type: ignore[arg-type]
            )


@pytest.mark.parametrize(
    "category",
    [ResultCategory.SUFFICIENT, ResultCategory.LIMITED, ResultCategory.INSUFFICIENT],
)
def test_a_completed_result_must_carry_both_its_analysis_parts(
    category: ResultCategory,
) -> None:
    """INSUFFICIENT means an analysis happened and rests on too little — not absent."""
    for missing in ("workspace", "context"):
        fields = {"workspace": object(), "context": object(), missing: None}
        with pytest.raises(DailyRunError, match="must carry both"):
            SymbolResult(requested_symbol="X", category=category, **fields)  # type: ignore[arg-type]


def test_a_completed_result_cannot_also_carry_a_failure() -> None:
    with pytest.raises(DailyRunError, match="cannot also carry a failure"):
        completed(failure=failure())


def test_insufficient_is_not_failed() -> None:
    """The load-bearing distinction: thin data is a market fact, an outage is not."""
    thin = completed(category=ResultCategory.INSUFFICIENT)
    assert thin.completed is True
    assert failed().completed is False


def test_result_type_validation() -> None:
    with pytest.raises(DailyRunError, match="requested_symbol"):
        completed(requested_symbol="  ")
    with pytest.raises(TypeError, match="category must be"):
        completed(category="sufficient")
    with pytest.raises(TypeError, match="failure must be"):
        SymbolResult(
            requested_symbol="X",
            category=ResultCategory.FAILED,
            failure="timed out",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="regime_summary"):
        completed(regime_summary=7)
    with pytest.raises(DailyRunError, match="resolved_symbol"):
        completed(resolved_symbol="  ")


def test_a_duration_must_be_a_non_negative_number() -> None:
    assert completed(duration_seconds=0).duration_seconds == 0
    assert completed(duration_seconds=1.5).duration_seconds == 1.5
    with pytest.raises(TypeError, match="duration_seconds"):
        completed(duration_seconds="1.5")
    with pytest.raises(TypeError, match="duration_seconds"):
        completed(duration_seconds=True)
    with pytest.raises(DailyRunError, match="negative"):
        completed(duration_seconds=-0.1)


def test_a_failure_must_say_what_and_why() -> None:
    with pytest.raises(TypeError, match="kind must be"):
        SymbolFailure(kind="provider_failure", detail="d", exception_type="E")  # type: ignore[arg-type]
    for field in ("detail", "exception_type"):
        with pytest.raises(DailyRunError, match=field):
            SymbolFailure(**{**dict(kind=FailureKind.PROVIDER_FAILURE,
                                    detail="d", exception_type="E"), field: "  "})


def test_failure_kinds_cover_the_expected_causes_and_no_defect() -> None:
    """There is deliberately no member for a programming error."""
    assert {k.value for k in FailureKind} == {
        "invalid_symbol",
        "provider_failure",
        "insufficient_data",
        "malformed_data",
    }


# ============ 3. counts are projections =====================================


def test_counts_are_derived_and_cannot_disagree_with_the_members() -> None:
    built = run(
        results=(
            completed("A"),
            completed("B", category=ResultCategory.LIMITED),
            completed("C", category=ResultCategory.INSUFFICIENT),
            failed("D"),
        )
    )
    assert built.requested_count == 4
    assert built.completed_count == 3
    assert built.failed_count == 1
    assert built.count_of(ResultCategory.SUFFICIENT) == 1
    assert built.count_of(ResultCategory.LIMITED) == 1
    assert built.count_of(ResultCategory.INSUFFICIENT) == 1
    assert built.count_of(ResultCategory.FAILED) == 1
    assert sum(built.count_of(c) for c in ResultCategory) == built.requested_count


def test_no_count_is_stored_on_the_run() -> None:
    """ADR-0016 §4 applied to an aggregate: a stored total can drift from its members."""
    fields = {f.name for f in DailyRun.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    assert not any("count" in name for name in fields)


def test_count_of_rejects_a_stranger() -> None:
    with pytest.raises(TypeError, match="category must be"):
        run().count_of("sufficient")  # type: ignore[arg-type]


# ============ 4. the run object =============================================


def test_a_run_is_immutable_and_copies_its_metadata() -> None:
    source = {"a": 1}
    built = run(metadata=source)
    source["a"] = 2
    assert built.metadata["a"] == 1
    with pytest.raises(TypeError):
        built.metadata["b"] = 3  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        built.objective = "day_trade"  # type: ignore[misc]


def test_the_schema_version_travels_with_the_artifact() -> None:
    assert run().schema_version == DAILY_SCHEMA_VERSION
    with pytest.raises(TypeError, match="schema_version"):
        run(schema_version="1")
    with pytest.raises(TypeError, match="schema_version"):
        run(schema_version=True)


def test_run_type_validation() -> None:
    with pytest.raises(TypeError, match="reference_time"):
        run(reference_time="2026-01-01")
    with pytest.raises(TypeError, match="results must be a tuple"):
        run(results=[completed()])
    with pytest.raises(TypeError, match=r"results\[1\]"):
        run(results=(completed(), "not a result"))
    for field in ("objective", "source"):
        with pytest.raises(DailyRunError, match=field):
            run(**{field: "  "})


def test_equality_is_structural() -> None:
    shared = completed()
    assert run(results=(shared,)) == run(results=(shared,))
    assert run(results=(shared,)) != run(results=(shared,), source="other")


# ============ 5. the requested universe =====================================


def test_a_universe_keeps_its_order_and_is_stripped() -> None:
    assert require_symbols([" BTCUSDT ", "ETHUSDT"]) == ("BTCUSDT", "ETHUSDT")


def test_a_repeat_is_rejected_rather_than_collapsed() -> None:
    """Collapsing would change the row count the caller expected without saying so."""
    with pytest.raises(DailyRunError, match="must not repeat: BTCUSDT"):
        require_symbols(["BTCUSDT", "ETHUSDT", "BTCUSDT"])


def test_a_repeat_after_stripping_is_still_a_repeat() -> None:
    with pytest.raises(DailyRunError, match="must not repeat"):
        require_symbols(["BTCUSDT", " BTCUSDT"])


def test_an_empty_or_blank_universe_is_a_caller_error() -> None:
    with pytest.raises(DailyRunError, match="at least one symbol"):
        require_symbols([])
    with pytest.raises(DailyRunError, match=r"symbols\[1\] is blank"):
        require_symbols(["BTCUSDT", "  "])


def test_a_string_is_not_a_universe() -> None:
    """"BTCUSDT" would otherwise become seven single-character symbols."""
    with pytest.raises(TypeError, match="non-string sequence"):
        require_symbols("BTCUSDT")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="non-string sequence"):
        require_symbols(b"BTCUSDT")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="non-string sequence"):
        require_symbols({"BTCUSDT"})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"symbols\[0\] must be a str"):
        require_symbols([7])  # type: ignore[list-item]


def test_the_maximum_is_a_stated_policy_and_is_enforced_at_its_edge() -> None:
    at_limit = [f"S{i}" for i in range(MAXIMUM_SYMBOLS)]
    assert len(require_symbols(at_limit)) == MAXIMUM_SYMBOLS
    with pytest.raises(DailyRunError, match=f"maximum of {MAXIMUM_SYMBOLS}"):
        require_symbols(at_limit + ["ONE_MORE"])


# ============ 6. nothing ranks, nothing recommends ==========================


_FORBIDDEN = (
    "rank", "ranking", "score", "scored", "best", "worst", "top", "opportunity",
    "recommend", "recommendation", "buy", "sell", "entry", "exit", "target",
    "stop", "position size", "bullish", "bearish", "signal", "setup quality",
)


def _module_sources() -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(DAILY_SRC.glob("*.py"))}


@pytest.mark.parametrize("word", _FORBIDDEN)
def test_no_public_name_in_the_package_uses_forbidden_vocabulary(word: str) -> None:
    import fmis.daily as daily

    for name in daily.__all__:
        assert word.replace(" ", "_") not in name.lower(), name


def test_no_module_sorts_or_reverses_a_result_sequence() -> None:
    """A sort by any analysis property is a ranking, whatever it is called.

    Exactly one sort exists in the package, and it orders the *names it is about
    to reject* inside an error message — never a sequence of results.
    """
    sorts: list[str] = []
    for name, source in _module_sources().items():
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            called = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if called in {"sorted", "sort", "reverse", "reversed"}:
                sorts.append(f"{name}:{ast.unparse(node)}")
    assert sorts == ["models.py:sorted({s for s in cleaned if cleaned.count(s) > 1})"]


def test_the_run_preserves_order_under_a_permutation_of_the_same_symbols() -> None:
    forward = run(results=(completed("A"), completed("B"), completed("C")))
    reverse = run(results=(completed("C"), completed("B"), completed("A")))
    assert forward.requested_symbols == ("A", "B", "C")
    assert reverse.requested_symbols == ("C", "B", "A")


def test_result_categories_mirror_the_decision_context_states_exactly() -> None:
    """AL owns the judgement; ADR-0026 forbids adding thresholds around it."""
    from fmis.decision_context import ContextState

    assert {c.value for c in ResultCategory} - {"failed"} == {
        s.value for s in ContextState
    }


def test_the_package_defines_no_threshold_of_its_own() -> None:
    """MAXIMUM_SYMBOLS is a run-size policy, not a market number."""
    for name, source in _module_sources().items():
        tree = ast.parse(source)
        numbers = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        }
        #: Run-size policy, schema version, and the renderer's column geometry.
        #: Not one of them is a market quantity.
        allowed = {0, 1, 2, 12, 13, 16, 30, 50, 78}
        assert numbers <= allowed, f"{name} introduced {numbers - allowed}"


def test_a_run_must_state_its_limitations() -> None:
    """A page of results with no caveats is the confidence SPEC §7 warns against."""
    with pytest.raises(DailyRunError, match="must state its limitations"):
        run(limitations=())
    with pytest.raises(TypeError, match="limitations must be a tuple"):
        run(limitations=[("AN-1", "text")])
