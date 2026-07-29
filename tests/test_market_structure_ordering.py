"""Tests for the single shared sequence-ordering rule (fmis.market_structure).

Milestone Z0 replaced two independent implementations of one ordering contract —
one over `SwingPoint` runs in `relationships.py`, one over `SwingComparison` runs
in `models.py` — with a single core, `models._validate_key_order`, plus two thin
adapters that differ only in the nouns they put into error messages.

This module exists to make that unification *enforced* rather than assumed. It
pins every message byte-for-byte, proves the two adapters reach identical
verdicts for identical reasons, and asserts that the rule has exactly one
implementation in the package.

The messages are treated as a shipped contract. Assertions here use ``==``, not
`pytest.raises(match=...)`: a substring match is what let a reworded message
through in the structural-label milestone, and the whole point of an extraction
is that it must not reword anything.
"""

from __future__ import annotations

import ast
import itertools
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import fmis.market_structure as ms
from fmis.market_structure import (
    SwingPoint,
    SwingType,
    compare_swing_sequence,
    compare_swings,
    label_swing,
    label_swing_sequence,
)
from fmis.market_structure import models

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
PACKAGE_DIR = Path(ms.__file__).parent

POINT_NOUNS = dict(
    subject="points",
    index_noun="index",
    timestamp_noun="timestamp",
    element_noun="point",
)
COMPARISON_NOUNS = dict(
    subject="comparisons",
    index_noun="current index",
    timestamp_noun="current timestamp",
    element_noun="comparison",
)


def sp(index: int, price: float, type: SwingType = SwingType.HIGH, offset: int = 0) -> SwingPoint:
    return SwingPoint(index, _BASE + timedelta(hours=4 * index + offset), price, type)


def key(point: SwingPoint) -> tuple[int, datetime, SwingType]:
    return (point.index, point.timestamp, point.type)


def keys(points: list[SwingPoint]) -> list[tuple[int, datetime, SwingType]]:
    return [key(p) for p in points]


def verdict(call) -> tuple[str, str]:
    """``("ok", "")`` or ``(exception name, exact message)``."""
    try:
        call()
    except Exception as error:  # noqa: BLE001 - the type is part of the verdict
        return (type(error).__name__, str(error))
    return ("ok", "")


def reason(message: str) -> str:
    """Which of the five checks fired, independent of the nouns used.

    Deliberately derived from the stable fragments of each message rather than
    from the production code, so a message that changed shape would fall through
    to ``unclassified`` instead of being silently reclassified.
    """
    if "must be ordered by" in message and "timestamp" in message.split(";")[0]:
        return "non-decreasing-timestamp"
    if "must be ordered by" in message:
        return "non-decreasing-index"
    if "shares" in message:
        return "shared-index-different-timestamp"
    if "repeats or precedes" in message and "timestamp" in message:
        return "per-type-timestamp"
    if "repeats or precedes" in message:
        return "per-type-index"
    return "unclassified"


def to_point_nouns(message: str) -> str:
    """Rewrite a comparison-adapter message into point-adapter vocabulary."""
    return (
        message.replace("current index", "index")
        .replace("current timestamp", "timestamp")
        .replace("comparisons", "points")
        .replace("comparison", "point")
    )


# ============================ exact messages =================================
# Five families x two adapters. Byte-for-byte, against the wording that shipped
# before the extraction.

_TS_A = _BASE + timedelta(hours=99)
_TS_B = _BASE


@pytest.mark.parametrize(
    "run, expected",
    [
        (
            [sp(4, 1.0, SwingType.HIGH), sp(0, 1.0, SwingType.LOW)],
            "points must be ordered by index; points[1] has index 0 after 4",
        ),
        (
            [
                SwingPoint(0, _TS_A, 1.0, SwingType.HIGH),
                SwingPoint(1, _TS_B, 1.0, SwingType.LOW),
            ],
            "points must be ordered by timestamp; points[1] has "
            "2024-01-01T00:00:00+00:00 after 2024-01-05T03:00:00+00:00",
        ),
        (
            [
                sp(0, 1.0, SwingType.HIGH),
                SwingPoint(0, _BASE + timedelta(hours=9), 1.0, SwingType.LOW),
            ],
            "points[1] shares index 0 with the previous point but carries "
            "a different timestamp",
        ),
        (
            [sp(0, 1.0, SwingType.HIGH), sp(0, 2.0, SwingType.HIGH)],
            "points[1] repeats or precedes index 0 for swing type 'high'",
        ),
        (
            [
                sp(0, 1.0, SwingType.HIGH),
                SwingPoint(1, _BASE, 2.0, SwingType.HIGH),
            ],
            "points[1] repeats or precedes timestamp 2024-01-01T00:00:00+00:00 "
            "for swing type 'high'",
        ),
    ],
)
def test_point_adapter_messages_are_exact(run: list[SwingPoint], expected: str) -> None:
    with pytest.raises(ValueError) as caught:
        compare_swing_sequence(run)
    assert str(caught.value) == expected


@pytest.mark.parametrize(
    "run, expected",
    [
        (
            [sp(4, 1.0, SwingType.HIGH), sp(0, 1.0, SwingType.LOW)],
            "comparisons must be ordered by current index; comparisons[1] has "
            "index 0 after 4",
        ),
        (
            [
                SwingPoint(0, _TS_A, 1.0, SwingType.HIGH),
                SwingPoint(1, _TS_B, 1.0, SwingType.LOW),
            ],
            "comparisons must be ordered by current timestamp; comparisons[1] "
            "has 2024-01-01T00:00:00+00:00 after 2024-01-05T03:00:00+00:00",
        ),
        (
            [
                sp(0, 1.0, SwingType.HIGH),
                SwingPoint(0, _BASE + timedelta(hours=9), 1.0, SwingType.LOW),
            ],
            "comparisons[1] shares current index 0 with the previous comparison "
            "but carries a different timestamp",
        ),
        (
            [sp(0, 1.0, SwingType.HIGH), sp(0, 2.0, SwingType.HIGH)],
            "comparisons[1] repeats or precedes current index 0 for swing type "
            "'high'",
        ),
        (
            [
                sp(0, 1.0, SwingType.HIGH),
                SwingPoint(1, _BASE, 2.0, SwingType.HIGH),
            ],
            "comparisons[1] repeats or precedes current timestamp "
            "2024-01-01T00:00:00+00:00 for swing type 'high'",
        ),
    ],
)
def test_comparison_adapter_messages_are_exact(
    run: list[SwingPoint], expected: str
) -> None:
    with pytest.raises(ValueError) as caught:
        models._validate_key_order(keys(run), **COMPARISON_NOUNS)
    assert str(caught.value) == expected


# ============================ adapter equivalence ============================


def _both(run_keys) -> tuple[tuple[str, str], tuple[str, str]]:
    return (
        verdict(lambda: models._validate_key_order(run_keys, **POINT_NOUNS)),
        verdict(lambda: models._validate_key_order(run_keys, **COMPARISON_NOUNS)),
    )


def _systematic_runs() -> list[list[SwingPoint]]:
    """Every run of length 0-3 over a small key domain, plus seeded longer runs."""
    domain = [
        (index, offset, type)
        for index in (0, 1, 2)
        for offset in (0, 1)
        for type in (SwingType.HIGH, SwingType.LOW)
    ]
    runs: list[list[SwingPoint]] = []
    for length in (0, 1, 2, 3):
        for combo in itertools.product(domain, repeat=length):
            runs.append(
                [
                    sp(index, float(1 + position), type, offset)
                    for position, (index, offset, type) in enumerate(combo)
                ]
            )
    rng = random.Random(4242)
    for _ in range(600):
        runs.append(
            [
                sp(
                    rng.randint(0, 4),
                    float(rng.randint(1, 5)),
                    rng.choice((SwingType.HIGH, SwingType.LOW)),
                    rng.choice((0, 1)),
                )
                for _ in range(rng.randint(0, 6))
            ]
        )
    runs.extend(_adversarial_runs())
    return runs


def _adversarial_runs() -> list[list[SwingPoint]]:
    """Runs the generated domain cannot express.

    In generated runs a timestamp is a function of the index, so index and
    timestamp can never disagree — which makes the **per-type timestamp** check
    unreachable there. It is unreachable from real detector output too, because
    timestamps come from candles. It is a defensive check, and these hand-built
    runs are the only way to exercise it.
    """
    flat = _BASE + timedelta(hours=10)
    later = _BASE + timedelta(hours=20)
    return [
        # index rises per type, timestamp does not — an intervening LOW keeps the
        # global timestamp check from firing first.
        [
            SwingPoint(0, flat, 5.0, SwingType.HIGH),
            SwingPoint(1, flat, 1.0, SwingType.LOW),
            SwingPoint(2, flat, 6.0, SwingType.HIGH),
        ],
        [
            SwingPoint(0, flat, 1.0, SwingType.LOW),
            SwingPoint(1, flat, 5.0, SwingType.HIGH),
            SwingPoint(2, flat, 0.5, SwingType.LOW),
        ],
        # same shape, timestamps rising globally but repeating within the type
        [
            SwingPoint(0, flat, 5.0, SwingType.HIGH),
            SwingPoint(1, later, 1.0, SwingType.LOW),
            SwingPoint(2, flat, 6.0, SwingType.HIGH),
        ],
    ]


SYSTEMATIC_RUNS = _systematic_runs()


def test_the_systematic_matrix_is_large_enough_to_be_meaningful() -> None:
    """Guards the matrix itself: a generator bug must not silently shrink it."""
    assert len(SYSTEMATIC_RUNS) > 700
    outcomes = {_both(keys(run))[0][0] for run in SYSTEMATIC_RUNS}
    assert outcomes == {"ok", "ValueError"}


def test_both_adapters_reach_the_same_verdict_on_every_run() -> None:
    disagreements = [
        run for run in SYSTEMATIC_RUNS if _both(keys(run))[0][0] != _both(keys(run))[1][0]
    ]
    assert disagreements == []


def test_both_adapters_fail_for_the_same_reason_on_every_run() -> None:
    """Verdict parity alone would pass even if the two rejected for different checks."""
    mismatches = []
    for run in SYSTEMATIC_RUNS:
        point_result, comparison_result = _both(keys(run))
        if point_result[0] == "ok":
            continue
        if reason(point_result[1]) != reason(comparison_result[1]):
            mismatches.append(run)
    assert mismatches == []


def test_no_rejection_is_unclassified() -> None:
    """Every failure maps to one of the five known checks."""
    for run in SYSTEMATIC_RUNS:
        point_result, _ = _both(keys(run))
        if point_result[0] == "ValueError":
            assert reason(point_result[1]) != "unclassified", point_result[1]


def test_noun_substitution_is_the_only_textual_difference() -> None:
    for run in SYSTEMATIC_RUNS:
        point_result, comparison_result = _both(keys(run))
        if point_result[0] == "ok":
            assert comparison_result[0] == "ok"
            continue
        assert to_point_nouns(comparison_result[1]) == point_result[1]


def test_all_five_reasons_are_exercised_by_the_matrix() -> None:
    seen = set()
    for run in SYSTEMATIC_RUNS:
        point_result, _ = _both(keys(run))
        if point_result[0] == "ValueError":
            seen.add(reason(point_result[1]))
    assert seen == {
        "non-decreasing-index",
        "non-decreasing-timestamp",
        "shared-index-different-timestamp",
        "per-type-index",
        "per-type-timestamp",
    }


# ============================ real-pipeline equivalence ======================


def test_the_two_adapters_agree_on_real_detector_shaped_runs() -> None:
    """Point runs and the comparison runs derived from them accept together."""
    rng = random.Random(77)
    for _ in range(300):
        points: list[SwingPoint] = []
        index = 0
        for _ in range(rng.randint(0, 8)):
            index += rng.randint(0, 2)
            points.append(
                sp(index, float(rng.randint(1, 6)), rng.choice((SwingType.HIGH, SwingType.LOW)))
            )
        point_ok = verdict(lambda: compare_swing_sequence(points))[0] == "ok"
        if not point_ok:
            continue
        comparisons = compare_swing_sequence(points)
        assert verdict(lambda: label_swing_sequence(comparisons))[0] == "ok"


# ============================ behaviour preserved ============================


def test_valid_ordered_runs_remain_valid() -> None:
    points = [
        sp(0, 5.0, SwingType.HIGH),
        sp(1, 1.0, SwingType.LOW),
        sp(2, 7.0, SwingType.HIGH),
        sp(3, 0.5, SwingType.LOW),
    ]
    assert len(compare_swing_sequence(points)) == 2


def test_outside_bar_equal_index_pair_is_accepted_high_first() -> None:
    points = [
        sp(0, 5.0, SwingType.HIGH),
        sp(0, 1.0, SwingType.LOW),
        sp(2, 7.0, SwingType.HIGH),
        sp(2, 0.5, SwingType.LOW),
    ]
    assert len(compare_swing_sequence(points)) == 2


def test_outside_bar_equal_index_pair_is_accepted_low_first() -> None:
    points = [
        sp(0, 1.0, SwingType.LOW),
        sp(0, 5.0, SwingType.HIGH),
        sp(2, 0.5, SwingType.LOW),
        sp(2, 7.0, SwingType.HIGH),
    ]
    assert len(compare_swing_sequence(points)) == 2


def test_outside_bar_order_is_preserved_not_imposed() -> None:
    """Input order survives; the rule imposes no HIGH-before-LOW convention."""
    low_first = [
        sp(0, 1.0, SwingType.LOW),
        sp(0, 5.0, SwingType.HIGH),
        sp(2, 0.5, SwingType.LOW),
        sp(2, 7.0, SwingType.HIGH),
    ]
    comparisons = compare_swing_sequence(low_first)
    assert [c.current.type for c in comparisons] == [SwingType.LOW, SwingType.HIGH]


def test_equal_index_with_equal_timestamp_is_accepted() -> None:
    models._validate_key_order(
        [
            (3, _BASE + timedelta(hours=12), SwingType.HIGH),
            (3, _BASE + timedelta(hours=12), SwingType.LOW),
        ],
        **POINT_NOUNS,
    )


def test_equal_index_with_different_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError):
        models._validate_key_order(
            [
                (3, _BASE + timedelta(hours=12), SwingType.HIGH),
                (3, _BASE + timedelta(hours=13), SwingType.LOW),
            ],
            **POINT_NOUNS,
        )


def test_empty_and_single_runs_are_accepted() -> None:
    models._validate_key_order([], **POINT_NOUNS)
    models._validate_key_order([(0, _BASE, SwingType.HIGH)], **POINT_NOUNS)


def test_unordered_input_is_rejected_rather_than_sorted() -> None:
    points = [sp(2, 7.0, SwingType.HIGH), sp(0, 5.0, SwingType.HIGH)]
    with pytest.raises(ValueError):
        compare_swing_sequence(points)


def test_input_is_not_mutated() -> None:
    points = [sp(0, 5.0, SwingType.HIGH), sp(1, 1.0, SwingType.LOW)]
    snapshot = list(points)
    compare_swing_sequence(points)
    assert points == snapshot
    assert all(a is b for a, b in zip(points, snapshot))


def test_an_unordered_run_yields_no_partial_result() -> None:
    """Validation completes before any comparison is built."""
    points = [
        sp(0, 5.0, SwingType.HIGH),
        sp(2, 7.0, SwingType.HIGH),
        sp(1, 6.0, SwingType.HIGH),
    ]
    with pytest.raises(ValueError):
        compare_swing_sequence(points)


# ============================ one implementation =============================


def _message_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for fragment in (
                "must be ordered by",
                "repeats or precedes",
                "with the previous",
            ):
                if fragment in node.value:
                    found.add(fragment)
        if isinstance(node, ast.JoinedStr):
            text = "".join(
                part.value
                for part in node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            for fragment in (
                "must be ordered by",
                "repeats or precedes",
                "with the previous",
            ):
                if fragment in text:
                    found.add(fragment)
    return found


def test_the_ordering_rule_has_exactly_one_implementation() -> None:
    """Only `models.py` may contain the ordering message text."""
    owners = {
        path.name: _message_literals(path)
        for path in sorted(PACKAGE_DIR.glob("*.py"))
        if _message_literals(path)
    }
    assert set(owners) == {"models.py"}
    assert owners["models.py"] == {
        "must be ordered by",
        "repeats or precedes",
        "with the previous",
    }


def test_the_core_is_defined_once() -> None:
    tree = ast.parse((PACKAGE_DIR / "models.py").read_text())
    cores = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_validate_key_order"
    ]
    assert len(cores) == 1


def test_both_adapters_delegate_to_the_core() -> None:
    for module in ("models.py", "relationships.py"):
        tree = ast.parse((PACKAGE_DIR / module).read_text())
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "_validate_key_order" in called, module


def test_no_third_implementation_can_hide_in_a_loop() -> None:
    """Neither adapter compares indices or timestamps itself any more."""
    tree = ast.parse((PACKAGE_DIR / "relationships.py").read_text())
    target = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "compare_swing_sequence"
    )
    for node in ast.walk(target):
        if isinstance(node, ast.Compare):
            for op in node.ops:
                assert isinstance(
                    op, (ast.Is, ast.IsNot, ast.In, ast.NotIn, ast.Eq, ast.NotEq)
                ), ast.dump(node)


def test_the_core_stays_private() -> None:
    assert "_validate_key_order" not in ms.__all__
    assert not hasattr(ms, "_validate_key_order")
    assert "_validate_key_order" not in models.__all__


def test_the_public_api_is_unchanged_by_this_milestone() -> None:
    assert set(ms.__all__) == {
        "SwingType", "SwingPoint", "SwingRelation", "SwingComparison",
        "StructuralSwingLabel", "StructuralSwing",
        "StructuralSequenceStateType", "StructuralSequenceState",
        "detect_swings", "compare_swings", "compare_swing_sequence",
        "label_swing", "label_swing_sequence", "derive_structural_sequence_state",
        "required_candles", "DEFAULT_LEFT_BARS", "DEFAULT_RIGHT_BARS",
    }
