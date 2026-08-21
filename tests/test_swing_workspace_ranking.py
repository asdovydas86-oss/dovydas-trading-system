"""Milestone BS — the ordering, and everything that must not be in it.

This is the suite that matters most. The workspace's one addition over
`fmits today` is that it *orders* actionable setups, and this repository has
refused every previous ordering by desirability on the grounds that a reader
reads the top row as the best idea. The price of ordering at all is that the key
is explicit, total, reconstructable and provably blind to every quantity — and
these are the tests that hold it to that.
"""

from __future__ import annotations

import pytest

from fmis.swing_workspace import (
    APPROVAL_ORDER,
    EXCLUDED_FROM_RANKING,
    RANK_KEYS,
    RANKING_RULE,
    READINESS_ORDER,
    SUFFICIENCY_ORDER,
    UNSTATED,
    RankComponent,
    RankKey,
    SwingWorkspaceError,
    rank_key_for,
    rank_setups,
)
from fmis.today import OpportunityLine

WATCHLIST = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")


def line(
    symbol: str = "BTCUSDT",
    *,
    state: str = "confirmed",
    sufficiency: str = "sufficient",
    approval: str | None = None,
    risk_reward: float | None = 2.0,
    **extra,
) -> OpportunityLine:
    return OpportunityLine(
        symbol=symbol,
        state=state,
        sufficiency=sufficiency,
        direction="up",
        risk_reward=risk_reward,
        stop=100.0,
        target=120.0,
        thesis=("a stated reason",),
        approval_status=approval,
        **extra,
    )


def order_of(*lines, watchlist=WATCHLIST) -> tuple[str, ...]:
    return tuple(item.symbol for item, _ in rank_setups(lines, watchlist=watchlist))


# ---------------------------------------------------------------------------
# The key itself
# ---------------------------------------------------------------------------


def test_the_key_has_exactly_the_four_documented_components_in_order() -> None:
    key = rank_key_for(line(), watchlist_index=0)

    assert tuple(component.name for component in key.components) == RANK_KEYS
    assert RANK_KEYS == ("readiness", "approval", "sufficiency", "watchlist")


def test_every_component_names_the_engine_that_produced_its_value() -> None:
    """A component with no stated source is a rule this package invented."""
    for component in rank_key_for(line(), watchlist_index=0).components:
        assert component.source.strip()
        assert component.value.strip()


def test_the_ordinals_are_the_only_thing_compared() -> None:
    key = rank_key_for(
        line(state="candidate", approval="approved", sufficiency="limited"),
        watchlist_index=7,
    )

    assert key.ordinals == (1, 0, 1, 7)


def test_the_key_explains_itself_without_reference_to_any_code() -> None:
    text = rank_key_for(line(), watchlist_index=2).explain()

    assert "readiness=confirmed(0)" in text
    assert "watchlist=#3(2)" in text


def test_a_key_with_no_components_is_refused() -> None:
    with pytest.raises(SwingWorkspaceError, match="no components"):
        RankKey(components=())


def test_a_key_naming_one_component_twice_is_refused() -> None:
    component = RankComponent(name="readiness", value="confirmed", rank=0, source="x")
    with pytest.raises(SwingWorkspaceError, match="same component twice"):
        RankKey(components=(component, component))


# ---------------------------------------------------------------------------
# The vocabularies are complete, and unmapped values raise
# ---------------------------------------------------------------------------


def test_the_readiness_vocabulary_covers_every_state_the_engine_has() -> None:
    from fmis.swing_setup import SetupState

    assert set(READINESS_ORDER) == {state.value for state in SetupState}


def test_the_approval_vocabulary_covers_every_status_the_engine_has() -> None:
    from fmis.position_sizing import ApprovalStatus

    assert {status.value for status in ApprovalStatus} <= set(APPROVAL_ORDER)


def test_the_sufficiency_vocabulary_covers_every_context_state() -> None:
    from fmis.decision_context import ContextState

    assert set(SUFFICIENCY_ORDER) == {state.value for state in ContextState}


def test_an_unmapped_state_raises_rather_than_sorting_by_default() -> None:
    """A default would order the page by a rule nobody wrote down."""
    with pytest.raises(SwingWorkspaceError, match="not a value the readiness"):
        rank_key_for(line(state="euphoric"), watchlist_index=0)


def test_an_unmapped_approval_raises_too() -> None:
    with pytest.raises(SwingWorkspaceError, match="not a value the approval"):
        rank_key_for(line(approval="probably fine"), watchlist_index=0)


def test_an_unmapped_sufficiency_raises_too() -> None:
    with pytest.raises(SwingWorkspaceError, match="not a value the sufficiency"):
        rank_key_for(line(sufficiency="adequate"), watchlist_index=0)


def test_a_line_with_no_approval_carries_the_unstated_value_and_sorts_last() -> None:
    key = rank_key_for(line(approval=None), watchlist_index=0)
    component = key.components[1]

    assert component.value == UNSTATED
    assert component.rank == max(APPROVAL_ORDER.values())


# ---------------------------------------------------------------------------
# What the ordering does
# ---------------------------------------------------------------------------


def test_readiness_decides_before_anything_else() -> None:
    assert order_of(
        line("ETHUSDT", state="candidate", approval="approved"),
        line("BTCUSDT", state="confirmed", approval="blocked"),
    ) == ("BTCUSDT", "ETHUSDT")


def test_approval_decides_within_one_readiness_state() -> None:
    assert order_of(
        line("SOLUSDT", approval="indeterminate"),
        line("ETHUSDT", approval="approved"),
        line("BTCUSDT", approval="blocked"),
    ) == ("ETHUSDT", "BTCUSDT", "SOLUSDT")


def test_a_measured_refusal_outranks_an_unmeasured_one() -> None:
    """*"It breaks a limit you set"* is more settled than *"we could not check"*."""
    assert APPROVAL_ORDER["blocked"] < APPROVAL_ORDER["indeterminate"]
    assert APPROVAL_ORDER["indeterminate"] < APPROVAL_ORDER[UNSTATED]


def test_sufficiency_decides_when_readiness_and_approval_agree() -> None:
    assert order_of(
        line("ETHUSDT", approval="approved", sufficiency="limited"),
        line("BTCUSDT", approval="approved", sufficiency="sufficient"),
    ) == ("BTCUSDT", "ETHUSDT")


def test_watchlist_position_is_the_final_tiebreak_and_makes_the_order_total() -> None:
    ordered = rank_setups(
        [line("XRPUSDT"), line("BTCUSDT"), line("SOLUSDT")], watchlist=WATCHLIST
    )

    assert tuple(item.symbol for item, _ in ordered) == (
        "BTCUSDT",
        "SOLUSDT",
        "XRPUSDT",
    )
    ordinals = [key.ordinals for _, key in ordered]
    assert len(set(ordinals)) == len(ordinals)


def test_two_rows_never_tie_when_the_watchlist_names_each_symbol_once() -> None:
    lines = [line(symbol) for symbol in WATCHLIST]
    keys = [key.ordinals for _, key in rank_setups(lines, watchlist=WATCHLIST)]

    assert len(set(keys)) == len(WATCHLIST)


def test_a_symbol_outside_the_watchlist_sorts_last_rather_than_raising() -> None:
    assert order_of(line("DOGEUSDT"), line("BTCUSDT")) == ("BTCUSDT", "DOGEUSDT")


def test_a_watchlist_naming_one_symbol_twice_keeps_the_first_position() -> None:
    ordered = rank_setups(
        [line("ETHUSDT"), line("BTCUSDT")],
        watchlist=("BTCUSDT", "ETHUSDT", "BTCUSDT"),
    )

    assert tuple(item.symbol for item, _ in ordered) == ("BTCUSDT", "ETHUSDT")


def test_the_order_is_reproducible_across_calls_over_the_same_input() -> None:
    lines = [line(symbol) for symbol in reversed(WATCHLIST)]

    first = order_of(*lines)
    second = order_of(*lines)

    assert first == second == WATCHLIST


# ---------------------------------------------------------------------------
# What the ordering must never do
# ---------------------------------------------------------------------------


def test_risk_reward_moves_nothing() -> None:
    """The measured association runs the other way; see `RISK_REWARD_ASSOCIATION`."""
    high_then_low = order_of(
        line("ETHUSDT", risk_reward=99.0), line("BTCUSDT", risk_reward=0.1)
    )
    low_then_high = order_of(
        line("ETHUSDT", risk_reward=0.1), line("BTCUSDT", risk_reward=99.0)
    )

    assert high_then_low == low_then_high == ("BTCUSDT", "ETHUSDT")


def test_a_high_risk_reward_candidate_never_outranks_a_confirmed_setup() -> None:
    assert order_of(
        line("ETHUSDT", state="candidate", risk_reward=50.0),
        line("BTCUSDT", state="confirmed", risk_reward=0.5),
    ) == ("BTCUSDT", "ETHUSDT")


def test_risk_reward_cannot_break_a_tie_either() -> None:
    """The one place a hidden score could still enter.

    When the fourth component ties — two symbols neither of which is in the
    watchlist — the order falls back to the stable sort, i.e. to scan order. A
    mutant that pre-sorted the input by risk/reward survived every other test in
    this file precisely because the *total* key overrides a pre-sort; it changes
    the answer only here, which is exactly where a quantity that orders nothing
    must be proven not to.
    """
    high_first = order_of(
        line("AAAUSDT", risk_reward=99.0),
        line("BBBUSDT", risk_reward=0.1),
        watchlist=("ZZZUSDT",),
    )
    low_first = order_of(
        line("AAAUSDT", risk_reward=0.1),
        line("BBBUSDT", risk_reward=99.0),
        watchlist=("ZZZUSDT",),
    )

    assert high_first == low_first == ("AAAUSDT", "BBBUSDT")


def test_risk_reward_cannot_reorder_a_duplicated_watchlist_entry() -> None:
    """The second shape that ties on the fourth component."""
    watchlist = ("BTCUSDT", "ETHUSDT", "BTCUSDT")

    assert order_of(
        line("ETHUSDT", risk_reward=99.0),
        line("BTCUSDT", risk_reward=0.1),
        watchlist=watchlist,
    ) == ("BTCUSDT", "ETHUSDT")


def test_the_recommended_size_moves_nothing() -> None:
    assert order_of(
        line(
            "ETHUSDT",
            approval="approved",
            recommended_size="900 BTC",
            open_risk_after="9 USDT",
        ),
        line(
            "BTCUSDT",
            approval="approved",
            recommended_size="0.001 BTC",
            open_risk_after="1 USDT",
        ),
    ) == ("BTCUSDT", "ETHUSDT")


def test_the_module_holds_no_arithmetic_at_all() -> None:
    """No multiplication, division, weighting or float anywhere in the ordering."""
    import ast
    import inspect
    import pathlib

    import fmis.swing_workspace.ranking as module

    source = pathlib.Path(inspect.getfile(module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp):
            assert isinstance(node.op, ast.Add), ast.dump(node.op)
        assert not isinstance(node, ast.AugAssign), ast.dump(node)
        if isinstance(node, ast.Constant):
            assert not isinstance(node.value, float), node.value


def test_the_excluded_list_names_the_quantities_a_reader_expects_to_be_used() -> None:
    joined = " ".join(EXCLUDED_FROM_RANKING)

    for expected in ("risk/reward", "size", "open risk", "evidence", "direction"):
        assert expected in joined


def test_the_rule_states_that_readiness_is_not_desirability() -> None:
    assert "not desirability" in RANKING_RULE
    assert "score" in RANKING_RULE


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def test_rank_key_for_refuses_a_non_line() -> None:
    with pytest.raises(TypeError, match="OpportunityLine"):
        rank_key_for("BTCUSDT", watchlist_index=0)


def test_rank_key_for_refuses_a_non_integer_index() -> None:
    with pytest.raises(TypeError, match="watchlist_index must be an int"):
        rank_key_for(line(), watchlist_index="0")


def test_rank_key_for_refuses_a_negative_index() -> None:
    """Matched on *this* guard's own words: `RankComponent` refuses a negative
    rank too, and a looser pattern let a mutant that removed this check pass by
    failing one layer down with a different message."""
    with pytest.raises(SwingWorkspaceError, match="watchlist_index cannot be negative"):
        rank_key_for(line(), watchlist_index=-1)


@pytest.mark.parametrize("bad", ["BTCUSDT", 3, None])
def test_rank_setups_refuses_a_non_sequence(bad) -> None:
    with pytest.raises(TypeError, match="non-string sequence"):
        rank_setups(bad, watchlist=WATCHLIST)


def test_rank_setups_refuses_a_non_sequence_watchlist() -> None:
    with pytest.raises(TypeError, match="watchlist must be a non-string sequence"):
        rank_setups([line()], watchlist="BTCUSDT")


def test_ranking_an_empty_group_produces_an_empty_result() -> None:
    assert rank_setups([], watchlist=WATCHLIST) == ()
