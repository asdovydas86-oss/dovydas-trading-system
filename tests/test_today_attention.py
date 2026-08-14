"""Milestone BJ — the priority queue, and the guarantee that it is not a ranking.

The load-bearing test in this file is
`test_the_queue_does_not_reorder_a_high_risk_reward_candidate_forwards`. It
plants exactly the input `SWING_TRADING_READINESS_AUDIT_V1.md` §6.1 names as the
cheapest attack on this product — *"let the owner rank by risk/reward... This
attack requires no adversary; it happens by default"* — and asserts the queue's
order is unchanged. `fmis.swing_setup.scan` carries the same test for its own
`TOP OPPORTUNITIES` section; this is that guarantee, held one layer up.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from fmis.today import ORDERING_RULE, WarningSeverity, build_queue
from fmis.today import attention as attention_module
from today_helpers import line


def test_confirmed_setups_come_before_candidates() -> None:
    """The engine's own readiness state — the grouping `scan_report` applies."""
    queue = build_queue(
        (line(symbol="AAAUSDT", state="confirmed"),),
        (line(symbol="BBBUSDT", state="candidate"),),
    )
    assert [e.opportunity.symbol for e in queue.needs_attention] == [
        "AAAUSDT",
        "BBBUSDT",
    ]


def test_scan_order_is_preserved_within_a_group() -> None:
    queue = build_queue(
        (
            line(symbol="CCCUSDT"),
            line(symbol="AAAUSDT"),
            line(symbol="BBBUSDT"),
        ),
        (),
    )
    assert [e.opportunity.symbol for e in queue.needs_attention] == [
        "CCCUSDT",
        "AAAUSDT",
        "BBBUSDT",
    ]


def test_the_queue_does_not_reorder_a_high_risk_reward_candidate_forwards() -> None:
    """The whole point of this module, asserted directly.

    A `CANDIDATE` with an R:R of 49 — the value a live run actually printed —
    placed against a `CONFIRMED` setup with an R:R of 0.4. If any sort key
    involving risk/reward existed anywhere, the candidate would move.
    """
    queue = build_queue(
        (line(symbol="MODESTUSDT", state="confirmed", risk_reward=0.4),),
        (line(symbol="SPECTACULAR", state="candidate", risk_reward=49.0),),
    )
    assert [e.opportunity.symbol for e in queue.needs_attention] == [
        "MODESTUSDT",
        "SPECTACULAR",
    ]


def test_the_queue_does_not_reorder_by_warning_count_either() -> None:
    """A clean entry does not float above a flagged one; both keep their place."""
    queue = build_queue(
        (
            line(symbol="FLAGGED", risk_reward=49.0),
            line(symbol="CLEAN", risk_reward=1.0),
        ),
        (),
    )
    assert [e.opportunity.symbol for e in queue.needs_attention] == [
        "FLAGGED",
        "CLEAN",
    ]
    assert queue.needs_attention[0].warnings
    assert not queue.needs_attention[1].warnings


def test_a_refused_entry_leaves_the_queue_rather_than_sinking_in_it() -> None:
    """Refusal is not low rank. It is a different list, with the reason named."""
    queue = build_queue(
        (
            line(symbol="OKUSDT"),
            line(symbol="NOSTOPUSDT", stop=None),
        ),
        (),
    )
    assert [e.opportunity.symbol for e in queue.needs_attention] == ["OKUSDT"]
    assert [e.opportunity.symbol for e in queue.blocked] == ["NOSTOPUSDT"]
    assert queue.blocked[0].blocked_by[0].code == "B-NO-STOP"


def test_refused_entries_keep_their_own_relative_order_too() -> None:
    queue = build_queue(
        (
            line(symbol="ZZZUSDT", stop=None),
            line(symbol="AAAUSDT", stop=None),
        ),
        (),
    )
    assert [e.opportunity.symbol for e in queue.blocked] == ["ZZZUSDT", "AAAUSDT"]


def test_an_entry_carries_its_warnings_and_its_refusals_apart() -> None:
    queue = build_queue(
        (line(symbol="BOTHUSDT", stop=None, risk_reward=None, sufficiency="insufficient"),),
        (),
    )
    entry = queue.blocked[0]
    assert {w.code for w in entry.blocked_by} == {"B-CONTEXT", "B-NO-STOP"}
    assert all(w.severity is WarningSeverity.BLOCK for w in entry.blocked_by)
    assert entry.warnings == ()


def test_an_empty_queue_is_empty_rather_than_absent() -> None:
    queue = build_queue((), ())
    assert queue.is_empty
    assert queue.ordering == ORDERING_RULE


def test_the_ordering_rule_travels_on_the_object() -> None:
    """A future JSON or Telegram consumer inherits the contract without the
    renderer's help."""
    queue = build_queue((line(),), ())
    assert "never desirability" in queue.ordering
    assert "risk/reward" in queue.ordering


def test_the_queue_rejects_a_non_sequence() -> None:
    with pytest.raises(TypeError):
        build_queue("BTCUSDT", ())
    with pytest.raises(TypeError):
        build_queue((), "BTCUSDT")


def test_the_queue_rejects_a_member_that_is_not_an_opportunity() -> None:
    with pytest.raises(TypeError, match="confirmed\\[0\\]"):
        build_queue(("BTCUSDT",), ())
    with pytest.raises(TypeError, match="candidates\\[0\\]"):
        build_queue((), ("BTCUSDT",))


def test_this_module_contains_no_sort_and_no_comparison_of_two_setups() -> None:
    """Structural, not behavioural: a sort key cannot be added here by accident.

    Scans the module's own source for `sorted`, `.sort`, `min`, `max` and
    `key=`. The behavioural tests above prove today's order; this one proves the
    mechanism that could change it does not exist.
    """
    tree = ast.parse(inspect.getsource(attention_module))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
    assert not ({"sorted", "sort", "min", "max", "key", "reverse"} & names)
