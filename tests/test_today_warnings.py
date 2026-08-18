"""Milestone BJ — the deterministic warning rules and the figures behind them.

Two things are checked throughout. First, that each rule fires on exactly the
condition it names and not on a neighbouring one — a warning that fires on the
wrong input is worse than none, because it trains the owner to skip the region.
Second, that every measured figure reaches the page **with its `n` and its
caveat**, which `SWING_TRADING_MVP_BLUEPRINT_V1.md` §7.6 requires by name:

    Every soft warning drawn from that chain must therefore be rendered with its
    `n` and a note that the sample is superseded — or the warning becomes the
    thing it exists to prevent: a confident number the owner acts on.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from fmis.today import (
    CLUSTER_MINIMUM,
    CODES,
    MEASURED_FIGURES,
    RISK_REWARD_ASSOCIATION,
    RISK_REWARD_DISTRIBUTION,
    RISK_REWARD_ELEVATED,
    RISK_REWARD_P90,
    MeasuredFigure,
    NotAvailable,
    WarningClass,
    WarningSeverity,
    warnings_for_opportunity,
    workspace_warnings,
)
from fmis.today import evidence as evidence_module
from fmis.today import sections as sections_module
from fmis.today import warnings as warnings_module
from today_helpers import line, portfolio

from fmis.today.models import FailedSymbol


def _codes(warnings) -> set[str]:
    return {warning.code for warning in warnings}


def _run(**overrides):
    values = {
        "actionable": (),
        "failed": (),
        "unreadable": (),
        "readable_declined": (),
        "portfolio": portfolio(),
    }
    values.update(overrides)
    return workspace_warnings(**values)


# --------------------------------------------------------------------------
# Per-setup rules
# --------------------------------------------------------------------------


def test_an_insufficient_context_refuses_the_setup() -> None:
    raised = warnings_for_opportunity(line(sufficiency="insufficient"))
    block = next(w for w in raised if w.code == "B-CONTEXT")
    assert block.severity is WarningSeverity.BLOCK
    assert block.kind is WarningClass.INCOMPLETE_ANALYSIS


def test_a_limited_context_is_not_refused() -> None:
    """`LIMITED` is the honest middle state and is not a refusal."""
    assert "B-CONTEXT" not in _codes(warnings_for_opportunity(line(sufficiency="limited")))


def test_a_missing_stop_refuses_the_setup_because_there_is_no_denominator() -> None:
    raised = warnings_for_opportunity(line(stop=None))
    block = next(w for w in raised if w.code == "B-NO-STOP")
    assert block.severity is WarningSeverity.BLOCK
    assert block.kind is WarningClass.RISK


def test_a_present_stop_raises_no_refusal() -> None:
    assert "B-NO-STOP" not in _codes(warnings_for_opportunity(line(stop=1.0)))


def test_a_risk_reward_above_the_measured_p90_is_flagged() -> None:
    raised = warnings_for_opportunity(line(risk_reward=RISK_REWARD_P90 + 1))
    assert "R-RR-DISTRIBUTION" in _codes(raised)


def test_a_risk_reward_exactly_at_the_p90_is_not_flagged_as_beyond_it() -> None:
    """The boundary is `>` and not `>=`: p90 is inside the measured range."""
    raised = warnings_for_opportunity(line(risk_reward=RISK_REWARD_P90))
    assert "R-RR-DISTRIBUTION" not in _codes(raised)


def test_a_risk_reward_at_the_elevated_edge_is_flagged() -> None:
    """The bucket is `[5, 20)`, so its lower edge is inside it."""
    raised = warnings_for_opportunity(line(risk_reward=RISK_REWARD_ELEVATED))
    assert "R-RR-ELEVATED" in _codes(raised)


def test_a_risk_reward_below_the_elevated_edge_is_not_flagged() -> None:
    raised = warnings_for_opportunity(line(risk_reward=RISK_REWARD_ELEVATED - 0.01))
    assert "R-RR-ELEVATED" not in _codes(raised)


def test_an_absent_risk_reward_raises_no_geometry_warning() -> None:
    raised = warnings_for_opportunity(line(risk_reward=None))
    assert not ({"R-RR-DISTRIBUTION", "R-RR-ELEVATED"} & _codes(raised))


def test_the_elevated_warning_states_the_direction_of_the_association_in_words() -> None:
    """A percentile alone is a quality score with extra steps."""
    raised = warnings_for_opportunity(line(risk_reward=49.0))
    elevated = next(w for w in raised if w.code == "R-RR-ELEVATED")
    assert "worse" in elevated.statement


def test_every_measured_warning_carries_its_sample_and_its_caveat() -> None:
    raised = warnings_for_opportunity(line(risk_reward=49.0))
    for code in ("R-RR-DISTRIBUTION", "R-RR-ELEVATED"):
        warning = next(w for w in raised if w.code == code)
        joined = " ".join(warning.detail)
        assert "n = " in joined, code
        assert warning.detail[-1].strip(), code


def test_the_superseded_sample_caveat_reaches_the_association_warning() -> None:
    raised = warnings_for_opportunity(line(risk_reward=49.0))
    elevated = next(w for w in raised if w.code == "R-RR-ELEVATED")
    assert "superseded" in " ".join(elevated.detail).lower()


def test_the_rules_are_evaluated_in_the_stated_order() -> None:
    """Sufficiency, then the stop, then geometry — the blueprint's own order."""
    raised = warnings_for_opportunity(
        line(sufficiency="insufficient", stop=None, risk_reward=49.0)
    )
    assert [w.code for w in raised] == [
        "B-CONTEXT",
        "B-NO-STOP",
        "R-RR-DISTRIBUTION",
        "R-RR-ELEVATED",
    ]


def test_the_per_setup_rules_reject_a_non_opportunity() -> None:
    with pytest.raises(TypeError):
        warnings_for_opportunity("BTCUSDT")


# --------------------------------------------------------------------------
# Run-wide rules
# --------------------------------------------------------------------------


def test_three_setups_on_one_side_raise_a_concentration_observation() -> None:
    actionable = tuple(
        line(symbol=f"S{index}USDT", direction="up") for index in range(CLUSTER_MINIMUM)
    )
    warning = next(w for w in _run(actionable=actionable) if w.code == "R-CLUSTER")
    assert warning.kind is WarningClass.CORRELATION
    assert len(warning.subjects) == CLUSTER_MINIMUM


def test_two_setups_on_one_side_do_not() -> None:
    actionable = tuple(
        line(symbol=f"S{index}USDT", direction="up")
        for index in range(CLUSTER_MINIMUM - 1)
    )
    assert "R-CLUSTER" not in _codes(_run(actionable=actionable))


def test_setups_split_across_two_sides_do_not_concentrate() -> None:
    actionable = (
        line(symbol="A", direction="up"),
        line(symbol="B", direction="up"),
        line(symbol="C", direction="down"),
        line(symbol="D", direction="down"),
    )
    assert "R-CLUSTER" not in _codes(_run(actionable=actionable))


def test_setups_with_no_direction_never_concentrate() -> None:
    actionable = tuple(
        line(symbol=f"S{index}", direction=None) for index in range(CLUSTER_MINIMUM + 2)
    )
    assert "R-CLUSTER" not in _codes(_run(actionable=actionable))


def test_the_concentration_observation_does_not_claim_the_markets_are_correlated() -> None:
    actionable = tuple(
        line(symbol=f"S{index}", direction="up") for index in range(CLUSTER_MINIMUM)
    )
    warning = next(w for w in _run(actionable=actionable) if w.code == "R-CLUSTER")
    assert "may be one bet" in warning.statement
    assert "nothing in this system can currently measure" in warning.statement


def test_an_absent_store_is_reported_differently_from_an_empty_one() -> None:
    """*"You have recorded nothing"* and *"this page did not look"* are not the
    same fact, and a page printing a zero for both would say neither."""
    absent = _run(portfolio=portfolio(store_present=False))
    empty = _run(portfolio=portfolio(store_present=True))
    assert "M-NO-STORE" in _codes(absent)
    assert "M-NO-POSITIONS" not in _codes(absent)
    assert "M-NO-POSITIONS" in _codes(empty)
    assert "M-NO-STORE" not in _codes(empty)


def test_a_store_with_open_positions_raises_neither() -> None:
    from fmis.today import PositionLine
    from today_helpers import REFERENCE

    held = PositionLine(
        market="binance:BTCUSDT:spot", book="swing", direction="long",
        quantity="0.5 BTC", average_entry="30000 / 0.5", opened_at=REFERENCE,
        trade_count=1, event_ids=("e",),
    )
    raised = _run(portfolio=portfolio(open_positions=(held,)))
    assert not ({"M-NO-STORE", "M-NO-POSITIONS"} & _codes(raised))


def test_no_risk_budget_in_force_is_reported() -> None:
    assert "R-NO-BUDGET" in _codes(_run())


def test_a_risk_budget_in_force_is_not_reported_as_missing() -> None:
    raised = _run(portfolio=portfolio(budget_note="budget swing-v1 in force"))
    assert "R-NO-BUDGET" not in _codes(raised)


def test_a_failed_symbol_is_reported_and_never_counted_as_a_wait() -> None:
    raised = _run(failed=(FailedSymbol(symbol="XYZ", detail="timeout"),))
    warning = next(w for w in raised if w.code == "M-FAILED-SYMBOL")
    assert warning.subjects == ("XYZ",)
    assert "not a WAIT" in warning.statement


def test_unreadable_symbols_are_reported_against_declined_ones() -> None:
    """A quiet system and a quiet market are indistinguishable as one number."""
    raised = _run(unreadable=("A", "B"), readable_declined=("C",))
    warning = next(w for w in raised if w.code == "I-UNREADABLE")
    assert warning.severity is WarningSeverity.INFORMATION
    assert "2 symbol(s) were read but could not be classified" in warning.statement
    assert "against 1" in warning.statement


def test_no_unreadable_symbols_raises_no_readability_note() -> None:
    assert "I-UNREADABLE" not in _codes(_run(readable_declined=("C",)))


def test_the_two_standing_limitations_are_always_raised() -> None:
    codes = _codes(_run())
    assert {"L-NO-FRESHNESS", "L-NO-SIZING"} <= codes


def test_the_run_rejects_a_non_portfolio() -> None:
    with pytest.raises(TypeError):
        _run(portfolio="a portfolio")


def test_per_setup_warnings_are_attributed_to_their_symbol() -> None:
    raised = _run(actionable=(line(symbol="ONLYUSDT", risk_reward=49.0),))
    for warning in raised:
        if warning.code.startswith("R-RR"):
            assert warning.subjects == ("ONLYUSDT",)


# --------------------------------------------------------------------------
# The evidence module
# --------------------------------------------------------------------------


def test_every_measured_figure_is_complete() -> None:
    for figure in MEASURED_FIGURES:
        assert figure.sample >= 1
        assert figure.source
        assert figure.caveat
        assert len(figure.rendered()) == 3


def test_a_figure_with_no_sample_is_rejected() -> None:
    with pytest.raises(ValueError):
        MeasuredFigure(
            label="l", statement="s", sample=0, source="src", caveat="c"
        )


def test_a_figure_rejects_a_blank_field_and_a_non_integer_sample() -> None:
    with pytest.raises(ValueError):
        MeasuredFigure(label="  ", statement="s", sample=1, source="src", caveat="c")
    with pytest.raises(TypeError):
        MeasuredFigure(label="l", statement="s", sample="44", source="s", caveat="c")


def test_the_published_figures_match_the_artifacts_they_cite() -> None:
    """Pins the two numbers to the reports they were read out of, so a later
    edit that changes one without changing the citation fails here."""
    assert RISK_REWARD_P90 == 10.70
    assert RISK_REWARD_ELEVATED == 5.0
    assert RISK_REWARD_DISTRIBUTION.sample == 44
    assert "0012" in RISK_REWARD_DISTRIBUTION.source
    assert RISK_REWARD_ASSOCIATION.sample == 146
    assert "7.7%" in RISK_REWARD_ASSOCIATION.statement
    assert "74.5%" in RISK_REWARD_ASSOCIATION.statement


# --------------------------------------------------------------------------
# Structural guards over the rules themselves
# --------------------------------------------------------------------------


def test_the_shipped_codes_are_exactly_the_declared_ones() -> None:
    """A code appearing in one branch nobody reads is a rule nobody reviewed."""
    tree = ast.parse(inspect.getsource(warnings_module))
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    declared = set(CODES)
    assert declared <= literals
    emitted = {token for token in literals if token[:2] in {"B-", "R-", "M-", "I-", "L-"}}
    assert emitted == declared


def test_no_rule_module_invents_a_number(  # noqa: D103 - the docstring is below
) -> None:
    """Every numeric literal in the rule modules is accounted for by name.

    `0` and `1` are structural; `CLUSTER_MINIMUM` is a count this rule's own
    docstring justifies. The two measured figures live in `evidence.py` and
    reach these modules only by import — so a threshold cannot be typed into a
    rule without failing here.

    Two list lengths are admitted **by name**: `RECENT_LIMIT`, and
    `PERFORMANCE_RECENT_LIMIT` added by Milestone BP. Both are how many rows a
    section prints, both carry a docstring saying why, and neither is a
    threshold anything is compared against — which is the distinction this
    guard exists to hold. BP's duration formatting was moved to
    `fmis.statistics.duration_text` rather than admitted here, because `86400`
    and `3600` genuinely are unit constants and belong in one place.
    """
    permitted = {0, 1, float(CLUSTER_MINIMUM)}
    named_lengths = {
        float(sections_module.RECENT_LIMIT),
        float(sections_module.PERFORMANCE_RECENT_LIMIT),
    }
    for module in (warnings_module, sections_module):
        found = {
            float(node.value)
            for node in ast.walk(ast.parse(inspect.getsource(module)))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        }
        assert found <= permitted | named_lengths, module.__name__


def test_the_measured_figures_are_defined_only_in_the_evidence_module() -> None:
    figures = {RISK_REWARD_P90, RISK_REWARD_ELEVATED}
    in_evidence = {
        float(node.value)
        for node in ast.walk(ast.parse(inspect.getsource(evidence_module)))
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    }
    assert figures <= in_evidence
    for module in (warnings_module, sections_module):
        found = {
            float(node.value)
            for node in ast.walk(ast.parse(inspect.getsource(module)))
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        }
        assert not (figures & found), module.__name__


def test_every_rule_names_a_source() -> None:
    raised = _run(
        actionable=(line(risk_reward=49.0, stop=None, sufficiency="insufficient"),),
        failed=(FailedSymbol(symbol="X", detail="d"),),
        unreadable=("Y",),
        portfolio=portfolio(store_present=False),
    )
    assert raised
    for warning in raised:
        assert warning.evidence.strip(), warning.code


def test_a_missing_budget_is_detected_by_type_not_by_a_sentinel_string() -> None:
    """`NotAvailable` is a different type from a rendered value on purpose."""
    assert isinstance(portfolio().budget_note, NotAvailable)
    assert "R-NO-BUDGET" in _codes(_run())
