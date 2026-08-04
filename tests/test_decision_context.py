"""Milestone AL — the Decision Context Engine.

The engine answers one question: does this analysis contain enough trustworthy
information to continue toward a trading setup? The tests that matter most are
the ones pinning what it must **never** do — produce a direction, invent a
threshold, or let disagreement masquerade as absence.

The gap it closes was measured before the milestone began: a 40-candle page
rendered its regime section as *available* while two of three regime dimensions
underneath read `insufficient`. `test_the_measured_gap_is_closed` reproduces that
exact case.
"""

from __future__ import annotations

import ast
import pathlib
import re
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from fmis.decision_context import (
    DEFAULT_CONTEXT_POLICY,
    REQUIREMENT_ORDER,
    SEVERITY,
    SOURCES,
    ContextInput,
    ContextInputError,
    ContextPolicy,
    ContextPolicyError,
    ContextState,
    DecisionContext,
    Requirement,
    RequirementCheck,
    Severity,
    ViewAdequacy,
    evaluate_context,
)

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
PACKAGE_DIR = pathlib.Path(__file__).resolve().parent.parent / "src" / "fmis" / "decision_context"


def view(**overrides) -> ViewAdequacy:
    fields = dict(
        role="setup", interval="1d", closed_candles=259, required_candles=5,
        warming_up=0, level_count=78, dimensions_insufficient=0,
    )
    fields.update(overrides)
    return ViewAdequacy(**fields)  # type: ignore[arg-type]


def make_input(**overrides) -> ContextInput:
    fields = dict(
        symbol="BTCUSDT", as_of=_BASE, views=(view(),), primary_role="setup",
        evidence_is_insufficient=False, conflict_count=0,
    )
    fields.update(overrides)
    return ContextInput(**fields)  # type: ignore[arg-type]


def state_of(**overrides) -> ContextState:
    return evaluate_context(make_input(**overrides)).state


# ============ 1. the question is answered, and every state is reachable =====


def test_a_complete_analysis_is_sufficient() -> None:
    assert state_of() is ContextState.SUFFICIENT


def test_a_blocking_gap_makes_it_insufficient() -> None:
    assert state_of(views=(view(closed_candles=3),)) is ContextState.INSUFFICIENT
    assert state_of(views=(view(level_count=0),)) is ContextState.INSUFFICIENT
    assert state_of(evidence_is_insufficient=True) is ContextState.INSUFFICIENT


def test_a_limiting_gap_alone_makes_it_limited() -> None:
    assert state_of(views=(view(warming_up=3),)) is ContextState.LIMITED
    assert state_of(views=(view(dimensions_insufficient=2),)) is ContextState.LIMITED


def test_the_measured_gap_is_closed() -> None:
    """The 40-candle case that reported *available* before this milestone.

    Three features warming up and two regime dimensions unclassified: the page
    used to render this as a fully available analysis. It is now `LIMITED`, and
    the two gaps are named.
    """
    result = evaluate_context(
        make_input(
            views=(view(closed_candles=40, warming_up=3, dimensions_insufficient=2, level_count=10),)
        )
    )
    assert result.state is ContextState.LIMITED
    assert result.may_continue is True
    assert {c.requirement for c in result.limiting} == {
        Requirement.WARM_UP_COMPLETE,
        Requirement.REGIME_DETERMINATE,
    }
    assert "3 feature(s) still warming up" in result.limiting[0].statement


def test_every_requirement_is_reported_including_the_met_ones() -> None:
    """A reader needs to know what was checked, not only what failed."""
    result = evaluate_context(make_input())
    assert [c.requirement for c in result.checks] == list(REQUIREMENT_ORDER)
    assert all(c.met for c in result.checks)
    assert result.unmet == ()


def test_check_order_is_fixed_and_a_reordered_result_is_rejected() -> None:
    result = evaluate_context(make_input())
    with pytest.raises(ContextInputError):
        DecisionContext(
            symbol="X", as_of=_BASE, state=result.state,
            checks=tuple(reversed(result.checks)), policy=DEFAULT_CONTEXT_POLICY,
        )
    with pytest.raises(ContextInputError):
        DecisionContext(
            symbol="X", as_of=_BASE, state=result.state,
            checks=result.checks[:2], policy=DEFAULT_CONTEXT_POLICY,
        )


# ============ 2. no direction, no plan, no risk =============================

_FORBIDDEN = frozenset({
    "long", "short", "buy", "sell", "entry", "exit", "target", "stop",
    "position", "size", "risk", "bullish", "bearish", "signal", "recommend",
    "score", "confidence", "rank", "trade",
})


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def test_no_forbidden_word_in_any_public_name() -> None:
    import fmis.decision_context as dc

    for name in dc.__all__:
        assert not (_words(name) & _FORBIDDEN), name
    for enum in (ContextState, Requirement, Severity):
        for member in enum:
            assert not (_words(member.value) & _FORBIDDEN), member


def test_no_forbidden_word_in_any_produced_statement() -> None:
    """Swept across every reachable combination of gaps."""
    seen: set[str] = set()
    for candles in (3, 40, 259):
        for warm in (0, 3):
            for dims in (0, 2):
                for levels in (0, 10):
                    for insufficient in (True, False):
                        result = evaluate_context(
                            make_input(
                                views=(view(closed_candles=candles, warming_up=warm,
                                            dimensions_insufficient=dims,
                                            level_count=levels),),
                                evidence_is_insufficient=insufficient,
                            )
                        )
                        for check in result.checks:
                            seen.add(check.statement)
                            seen.add(check.source)
    assert seen
    for text in seen:
        offending = _words(text) & _FORBIDDEN
        assert not offending, (offending, text)


def test_the_result_carries_no_score_and_no_direction_field() -> None:
    for banned in ("score", "confidence", "rank", "direction", "bias", "grade"):
        assert banned not in DecisionContext.__dataclass_fields__
        assert not hasattr(evaluate_context(make_input()), banned)


def test_may_continue_is_named_for_information_not_for_action() -> None:
    """`should_trade` would be a different and forbidden claim."""
    assert hasattr(DecisionContext, "may_continue")
    for banned in ("should_trade", "is_tradeable", "go", "approved"):
        assert not hasattr(DecisionContext, banned)


# ============ 3. the engine invents no threshold ============================


def test_no_numeric_literal_decides_any_requirement() -> None:
    """Every rule delegates. A literal here would be a second definition.

    Only 0 and 1 may appear, and only as "none" and "at least one" — counts, not
    thresholds. Any other number would be a judgement this engine is not
    entitled to make.
    """
    tree = ast.parse((PACKAGE_DIR / "evaluate.py").read_text())
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    assert numbers <= {0, 1}, numbers


def test_the_policy_carries_no_thresholds() -> None:
    assert set(ContextPolicy.__dataclass_fields__) == {"policy_id", "strict"}
    for field in ContextPolicy.__dataclass_fields__:
        assert not isinstance(getattr(DEFAULT_CONTEXT_POLICY, field), (int, float)) or isinstance(
            getattr(DEFAULT_CONTEXT_POLICY, field), bool
        )


def test_every_requirement_names_the_layer_that_owns_its_rule() -> None:
    assert set(SOURCES) == set(Requirement)
    for requirement, source in SOURCES.items():
        assert source.startswith("fmis."), (requirement, source)
    result = evaluate_context(make_input())
    for check in result.checks:
        assert check.source == SOURCES[check.requirement]


def test_depth_is_compared_against_the_callers_own_requirement() -> None:
    """Not against a number chosen here: the same candle count can pass or fail."""
    assert state_of(views=(view(closed_candles=10, required_candles=5),)) is (
        ContextState.SUFFICIENT
    )
    assert state_of(views=(view(closed_candles=10, required_candles=50),)) is (
        ContextState.INSUFFICIENT
    )


# ============ 4. conflicts never move the answer ============================


def test_conflicts_change_no_state_and_no_check() -> None:
    """Sufficiency is about availability, never about agreement.

    Penalising disagreement would reward pages that look tidy by being
    one-sided, which is the failure `docs/analysis-notes.md` records.
    """
    baseline = evaluate_context(make_input(conflict_count=0))
    for count in (1, 5, 99):
        other = evaluate_context(make_input(conflict_count=count))
        assert other.state is baseline.state
        assert other.checks == baseline.checks
    assert baseline.metadata["conflict_count"] == 0


def test_the_conflict_count_is_carried_but_unread() -> None:
    result = evaluate_context(make_input(conflict_count=7))
    assert result.metadata["conflict_count"] == 7
    tree = ast.parse((PACKAGE_DIR / "evaluate.py").read_text())
    reads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "conflict_count"
    ]
    # Exactly one read: the metadata line that carries it forward.
    assert len(reads) == 1


# ============ 5. severity and strictness ====================================


def test_severity_is_fixed_per_requirement_not_configured() -> None:
    assert set(SEVERITY) == set(Requirement)
    assert SEVERITY[Requirement.PRIMARY_DATA_DEPTH] is Severity.BLOCKING
    assert SEVERITY[Requirement.STRUCTURE_PRESENT] is Severity.BLOCKING
    assert SEVERITY[Requirement.EVIDENCE_PRESENT] is Severity.BLOCKING
    assert SEVERITY[Requirement.WARM_UP_COMPLETE] is Severity.LIMITING
    assert SEVERITY[Requirement.REGIME_DETERMINATE] is Severity.LIMITING


def test_strict_promotes_every_limiting_gap_to_blocking() -> None:
    subject = make_input(views=(view(warming_up=3),))
    assert evaluate_context(subject).state is ContextState.LIMITED
    strict = evaluate_context(subject, ContextPolicy(strict=True))
    assert strict.state is ContextState.INSUFFICIENT
    assert strict.may_continue is False


def test_strict_does_not_invent_a_gap_where_none_exists() -> None:
    assert evaluate_context(make_input(), ContextPolicy(strict=True)).state is (
        ContextState.SUFFICIENT
    )


def test_there_is_no_per_requirement_severity_override() -> None:
    """One flag, not a demotable set: a per-check override lets a caller switch
    off the single gate that was about to stop them."""
    for banned in ("severities", "overrides", "ignore", "waive", "exempt"):
        assert banned not in ContextPolicy.__dataclass_fields__


def test_the_policy_travels_with_the_result() -> None:
    policy = ContextPolicy(policy_id="experiment-3", strict=True)
    assert evaluate_context(make_input(), policy).policy is policy
    assert dict(policy.describe())["policy_id"] == "experiment-3"
    assert "none" in dict(DEFAULT_CONTEXT_POLICY.describe())["thresholds"]


@pytest.mark.parametrize("bad", ["", "  ", None, 5])
def test_an_invalid_policy_id_is_rejected(bad: object) -> None:
    with pytest.raises((ContextPolicyError, TypeError)):
        ContextPolicy(policy_id=bad)  # type: ignore[arg-type]


def test_a_non_boolean_strict_is_rejected() -> None:
    with pytest.raises(TypeError):
        ContextPolicy(strict="yes")  # type: ignore[arg-type]


# ============ 6. input validation ===========================================


@pytest.mark.parametrize(
    "field", ["closed_candles", "required_candles", "warming_up", "level_count",
              "dimensions_insufficient"],
)
def test_a_negative_or_non_int_count_is_rejected(field: str) -> None:
    with pytest.raises(ContextInputError):
        view(**{field: -1})
    with pytest.raises(TypeError):
        view(**{field: 1.5})
    with pytest.raises(TypeError):
        view(**{field: True})


def test_a_view_requires_a_positive_requirement() -> None:
    with pytest.raises(ContextInputError):
        view(required_candles=0)


@pytest.mark.parametrize("field", ["role", "interval"])
def test_a_view_requires_its_identity(field: str) -> None:
    with pytest.raises(ContextInputError):
        view(**{field: "  "})


def test_an_input_requires_at_least_one_view() -> None:
    with pytest.raises(ContextInputError):
        make_input(views=())


def test_views_may_not_repeat_a_role() -> None:
    with pytest.raises(ContextInputError):
        make_input(views=(view(), view()))


def test_the_primary_role_must_be_present() -> None:
    with pytest.raises(ContextInputError) as excinfo:
        make_input(views=(view(role="context"),), primary_role="setup")
    assert "not among the views" in str(excinfo.value)


def test_input_type_validation() -> None:
    with pytest.raises(TypeError):
        make_input(as_of="2026-01-01")
    with pytest.raises(TypeError):
        make_input(views=[view()])
    with pytest.raises(TypeError):
        make_input(views=("not a view",))
    with pytest.raises(TypeError):
        make_input(evidence_is_insufficient="no")
    with pytest.raises(TypeError):
        make_input(conflict_count=1.5)
    with pytest.raises(ContextInputError):
        make_input(conflict_count=-1)
    with pytest.raises(ContextInputError):
        make_input(symbol="  ")
    with pytest.raises(TypeError):
        evaluate_context("not an input")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        evaluate_context(make_input(), "not a policy")  # type: ignore[arg-type]


def test_a_check_validates_itself() -> None:
    with pytest.raises(TypeError):
        RequirementCheck(requirement="depth", met=True, severity=Severity.BLOCKING,
                         statement="s", source="fmis.x")
    with pytest.raises(TypeError):
        RequirementCheck(requirement=Requirement.WARM_UP_COMPLETE, met="yes",
                         severity=Severity.BLOCKING, statement="s", source="fmis.x")
    with pytest.raises(TypeError):
        RequirementCheck(requirement=Requirement.WARM_UP_COMPLETE, met=True,
                         severity="blocking", statement="s", source="fmis.x")
    for field in ("statement", "source"):
        with pytest.raises(ContextInputError):
            RequirementCheck(
                **{**dict(requirement=Requirement.WARM_UP_COMPLETE, met=True,
                          severity=Severity.BLOCKING, statement="s", source="fmis.x"),
                   field: "  "}
            )


def test_a_context_validates_itself() -> None:
    result = evaluate_context(make_input())
    base = dict(symbol="X", as_of=_BASE, state=result.state, checks=result.checks,
                policy=DEFAULT_CONTEXT_POLICY)
    with pytest.raises(ContextInputError):
        DecisionContext(**{**base, "symbol": "  "})
    with pytest.raises(TypeError):
        DecisionContext(**{**base, "as_of": "2026"})
    with pytest.raises(TypeError):
        DecisionContext(**{**base, "state": "sufficient"})
    with pytest.raises(TypeError):
        DecisionContext(**{**base, "checks": list(result.checks)})
    with pytest.raises(TypeError):
        DecisionContext(**{**base, "checks": ("not a check",) * 5})
    with pytest.raises(ContextInputError):
        DecisionContext(**{**base, "checks": (result.checks[0],) * 5})


# ============ 7. determinism, immutability, boundaries ======================


def test_evaluation_is_a_pure_function_of_its_inputs() -> None:
    subject = make_input()
    assert evaluate_context(subject) == evaluate_context(subject)


def test_results_are_immutable_and_copy_their_metadata() -> None:
    source = {"a": 1}
    result = evaluate_context(make_input(metadata=source))
    source["a"] = 2
    assert result.metadata["a"] == 1
    with pytest.raises(TypeError):
        result.metadata["b"] = 3  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        result.symbol = "ETHUSDT"  # type: ignore[misc]


def test_the_engine_imports_nothing_from_the_repository() -> None:
    """Its input is integers and strings, so it needs no other layer."""
    modules: set[str] = set()
    for py in PACKAGE_DIR.rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("fmis") and not node.module.startswith(
                    "fmis.decision_context"
                ):
                    modules.add(node.module)
    assert modules == set()


def test_the_engine_reads_no_clock_and_no_network() -> None:
    for py in PACKAGE_DIR.rglob("*.py"):
        source = py.read_text()
        lines = source.splitlines(keepends=True)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                body = getattr(node, "body", None)
                if body and isinstance(body[0], ast.Expr):
                    doc = body[0].value
                    if isinstance(doc, ast.Constant) and isinstance(doc.value, str):
                        for n in range(doc.lineno, doc.end_lineno + 1):
                            lines[n - 1] = "\n"
        code = "".join(lines)
        for banned in ("datetime.now", "utcnow", "time.time", "requests", "urllib",
                       "random"):
            assert banned not in code, f"{py}: {banned}"


def test_no_engine_below_imports_this_package() -> None:
    """Only the application layer may consume this engine.

    `fmis.daily` (Milestone AN) joins `fmis.workspace` as a permitted importer:
    both are composition roots above this package, which is the direction
    ADR-0007 allows. No engine has been permitted anything.
    """
    root = PACKAGE_DIR.parent
    permitted = {root / "workspace", root / "daily", PACKAGE_DIR}
    for py in root.rglob("*.py"):
        if py.parent in permitted:
            continue
        assert "fmis.decision_context" not in py.read_text(), py


def test_the_public_surface_is_exactly_what_is_documented() -> None:
    import fmis.decision_context as dc

    assert len(dc.__all__) == 16
    assert len(set(dc.__all__)) == len(dc.__all__)
    for name in dc.__all__:
        assert hasattr(dc, name), name


def test_no_export_collides_with_another_package() -> None:
    """`DEFAULT_POLICY` already belongs to `fmis.market_regime`."""
    import fmis.decision_context as dc
    import fmis.market_regime as mr

    assert not set(dc.__all__) & set(mr.__all__)
    assert "DEFAULT_POLICY" in mr.__all__
    assert "DEFAULT_CONTEXT_POLICY" in dc.__all__


def test_may_continue_can_never_disagree_with_the_state() -> None:
    """The defect that made this a property of `state` rather than of the checks.

    Under a strict policy the state is `INSUFFICIENT` while every check keeps its
    own fixed severity, so a `may_continue` derived from the checks reported that
    an insufficient analysis could be continued.
    """
    for strict in (False, True):
        policy = ContextPolicy(strict=strict)
        for warm in (0, 3):
            for candles in (3, 259):
                result = evaluate_context(
                    make_input(views=(view(closed_candles=candles, warming_up=warm),)),
                    policy,
                )
                assert result.may_continue is (
                    result.state is not ContextState.INSUFFICIENT
                )


# ============ 8. gaps the mutation gate found ===============================


def test_a_requirement_repeated_in_place_is_rejected() -> None:
    """Survivor 20: the earlier fixture also broke completeness and order."""
    checks = evaluate_context(make_input()).checks
    doubled = (checks[0],) + checks          # in canonical order, all five present
    assert {c.requirement for c in doubled} == set(REQUIREMENT_ORDER)
    with pytest.raises(ContextInputError) as excinfo:
        DecisionContext(symbol="X", as_of=_BASE, state=ContextState.SUFFICIENT,
                        checks=doubled, policy=DEFAULT_CONTEXT_POLICY)
    assert "twice" in str(excinfo.value)


def test_the_requirement_order_is_asserted_explicitly() -> None:
    """Survivor 25: comparing against REQUIREMENT_ORDER follows it when mutated."""
    assert REQUIREMENT_ORDER == (
        Requirement.PRIMARY_DATA_DEPTH,
        Requirement.WARM_UP_COMPLETE,
        Requirement.REGIME_DETERMINATE,
        Requirement.STRUCTURE_PRESENT,
        Requirement.EVIDENCE_PRESENT,
    )
    assert [c.requirement for c in evaluate_context(make_input()).checks] == [
        Requirement.PRIMARY_DATA_DEPTH,
        Requirement.WARM_UP_COMPLETE,
        Requirement.REGIME_DETERMINATE,
        Requirement.STRUCTURE_PRESENT,
        Requirement.EVIDENCE_PRESENT,
    ]


def test_an_input_with_no_view_names_the_view_requirement() -> None:
    """Survivor 27: the primary-role check fired first and hid this one."""
    with pytest.raises(ContextInputError) as excinfo:
        ContextInput(symbol="BTCUSDT", as_of=_BASE, views=(), primary_role="setup",
                     evidence_is_insufficient=False)
    assert "at least one view" in str(excinfo.value)


def test_the_primary_view_is_selected_by_role_not_by_position() -> None:
    """Survivor 30: every earlier fixture had exactly one view."""
    subject = make_input(
        views=(view(role="context", interval="1w", level_count=1),
               view(role="setup", interval="1d", level_count=99)),
        primary_role="setup",
    )
    assert subject.primary.role == "setup"
    assert subject.primary.level_count == 99
    assert "99 structural level" in evaluate_context(subject).checks[3].statement


def test_blocking_and_limiting_are_not_interchangeable() -> None:
    """Survivor 31: no case carried one of each."""
    result = evaluate_context(
        make_input(views=(view(level_count=0, warming_up=2),))
    )
    assert {c.requirement for c in result.blocking} == {Requirement.STRUCTURE_PRESENT}
    assert {c.requirement for c in result.limiting} == {Requirement.WARM_UP_COMPLETE}
    assert len(result.unmet) == 2


def test_the_policy_describes_its_own_strictness_correctly() -> None:
    """Survivor 35: `describe()` was rendered but never read back."""
    assert "yes" in dict(ContextPolicy(strict=True).describe())["strict"]
    assert dict(ContextPolicy(strict=False).describe())["strict"] == "no"
