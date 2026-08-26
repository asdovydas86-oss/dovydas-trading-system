"""No-lookahead for everything Milestone BY added. **Change the future; require blindness.**

Milestone BX proved its planning layer could not read forward *structurally*: a
`GeometryCandidate` holds no bar, so a policy handed nothing else cannot see one.
BY adds three surfaces that bar-blindness does not cover, and each gets its own
proof here:

1. **entry rules read bars.** `resolve_entry` walks a real series, so it could in
   principle consult a bar before the decision existed. Every rule is therefore
   shown to be invariant to arbitrary mutation of every bar *before*
   ``signal_close_at``, and to be sensitive to the bars after it — the control
   that stops the first assertion passing vacuously.
2. **the ladder is a second series.** 1H and 15m candles enter the package for the
   first time. They are shown to change an OUTCOME and never a PLAN, and to be
   unreachable by import from the two modules that decide a stop or a target.
3. **the pre-registration is rules, not data.** It is shown to import no bar
   type, no trade type and no capture, so a threshold cannot be derived from a
   result even by accident.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.entry import (
    PRE_DECLARED_ENTRY_POLICIES,
    EntryFill,
    PathRole,
    entry_policy_by_id,
    resolve_entry,
)
from fmis.swing_lab.exits import exit_policy_by_id, simulate_managed_trade
from fmis.swing_lab.geometry import GeometryPlan
from fmis.swing_lab.intrabar import BarLadder
from fmis.swing_lab.nonstructural import synthetic_policy
from fmis.swing_lab.preregistration import PRE_REGISTERED_HYPOTHESES
from fmis.swing_lab.trades import FRICTIONLESS_COSTS
from fmis.swing_setup.models import Direction

from tests.swing_lab_helpers import candidate

_UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=_UTC)
FOUR_HOURS = timedelta(hours=4)
_PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "src" / "fmis" / "swing_lab"

FULL = exit_policy_by_id("exit_full_target")


def _bar(index: int, o: str, h: str, low: str, c: str, *, interval: str = "4h") -> PriceBar:
    step = FOUR_HOURS if interval == "4h" else timedelta(hours=1)
    return PriceBar(
        symbol="BTCUSDT", interval=interval, open_time=T0 + step * index,
        open=Decimal(o), high=Decimal(h), low=Decimal(low), close=Decimal(c),
    )


def _scaled(bar: PriceBar, factor: str) -> PriceBar:
    multiple = Decimal(factor)
    return PriceBar(
        symbol=bar.symbol, interval=bar.interval, open_time=bar.open_time,
        open=bar.open * multiple, high=bar.high * multiple,
        low=bar.low * multiple, close=bar.close * multiple,
    )


def _path(interval: str = "4h", count: int = 12) -> tuple[PriceBar, ...]:
    return tuple(
        _bar(index, "100", "105", "95", "101", interval=interval)
        for index in range(count)
    )


# ------------------------------------------------------- 1. entry rules ---


@pytest.mark.parametrize(
    "policy", PRE_DECLARED_ENTRY_POLICIES, ids=lambda p: p.policy_id
)
def test_no_entry_rule_can_see_a_bar_before_the_decision_existed(policy) -> None:
    """Mutate the whole past ×1000. **Every fill must be byte-identical.**"""
    interval = "4h" if policy.path is PathRole.EXECUTION else "1h"
    original = _path(interval)
    signal_index = 4
    signal_bar = original[signal_index]
    step = FOUR_HOURS if interval == "4h" else timedelta(hours=1)

    mutated = tuple(
        _scaled(bar, "1000") if index < signal_index + 1 else bar
        for index, bar in enumerate(original)
    )

    def resolve(path):
        return resolve_entry(
            policy, path=path,
            signal_at=signal_bar.open_time,
            signal_close_at=signal_bar.open_time + step,
            reference_price=Decimal("101"),
            direction=Direction.LONG,
        )

    assert resolve(original) == resolve(mutated)


@pytest.mark.parametrize(
    "policy", PRE_DECLARED_ENTRY_POLICIES, ids=lambda p: p.policy_id
)
def test_every_entry_rule_IS_sensitive_to_the_bars_after_the_decision(policy) -> None:
    """The control. Without it the test above passes for a rule that reads nothing."""
    interval = "4h" if policy.path is PathRole.EXECUTION else "1h"
    original = _path(interval)
    signal_index = 4
    signal_bar = original[signal_index]
    step = FOUR_HOURS if interval == "4h" else timedelta(hours=1)

    mutated = tuple(
        _scaled(bar, "1.5") if index > signal_index else bar
        for index, bar in enumerate(original)
    )

    def resolve(path):
        return resolve_entry(
            policy, path=path,
            signal_at=signal_bar.open_time,
            signal_close_at=signal_bar.open_time + step,
            reference_price=Decimal("101"),
            direction=Direction.LONG,
        )

    before, after = resolve(original), resolve(mutated)
    assert before != after, (
        f"{policy.policy_id} produced the same fill from a different future; it "
        "is reading nothing, so the blindness test above is vacuous for it"
    )


def test_the_entry_boundary_is_the_signal_CLOSE_and_not_its_open() -> None:
    """A fill at the signal bar's own open would be a four-hour lookahead."""
    path = _path()
    signal_bar = path[4]
    fill = resolve_entry(
        entry_policy_by_id("entry_immediate"), path=path,
        signal_at=signal_bar.open_time,
        signal_close_at=signal_bar.open_time + FOUR_HOURS,
        reference_price=Decimal("101"), direction=Direction.LONG,
    )
    assert isinstance(fill, EntryFill)
    assert fill.at == signal_bar.open_time + FOUR_HOURS
    assert fill.at > signal_bar.open_time
    assert fill.index == 5


def test_the_pullback_limit_cannot_be_filled_by_a_bar_outside_its_validity() -> None:
    """An expiry that leaked would let a rule pick its own best fill from the future."""
    policy = entry_policy_by_id("entry_pullback_limit")
    quiet = tuple(_bar(index, "200", "205", "195", "201") for index in range(1, 20))
    path = (_bar(0, "100", "105", "95", "101"), *quiet)
    signal_bar = path[0]

    def resolve(bars):
        return resolve_entry(
            policy, path=bars, signal_at=signal_bar.open_time,
            signal_close_at=signal_bar.open_time + FOUR_HOURS,
            reference_price=Decimal("101"), direction=Direction.LONG,
        )

    # A deep retrace far beyond the validity window must change nothing.
    late = list(path)
    late[15] = _bar(15, "200", "205", "50", "60")
    assert resolve(path) == resolve(tuple(late))


# ---------------------------------------------------------- 2. the ladder ---


def test_the_ladder_changes_an_outcome_and_never_a_plan() -> None:
    """The milestone's central separation, asserted on the same candidate.

    The plan is produced from a `GeometryCandidate`, which holds no bar of any
    resolution. Two runs whose 1H series differ arbitrarily therefore produce the
    identical plan — and different trades, which is the whole point of having
    the finer data at all.
    """
    subject = candidate()
    policy = synthetic_policy(0.5, 2.0)
    plan = policy.plan(subject)
    assert isinstance(plan, GeometryPlan)

    coarse = (
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "100.4", "99.6", "100"),   # reaches neither level
        _bar(2, "100", "101.1", "99.4", "100"),   # reaches BOTH — the ambiguity
    )
    stop, target = Decimal("99.5"), Decimal("101")

    def walk(fine):
        ladder = BarLadder("BTCUSDT", (("4h", coarse), ("1h", fine)))
        return simulate_managed_trade(
            coarse, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, entry_index=1, entry_price=coarse[1].open,
            entry_at=coarse[1].open_time, signal_at=coarse[0].open_time,
            reference_price=Decimal("100"), stop_price=stop, target_price=target,
            planned_risk_reward=2.0, window_bars=5, costs=FRICTIONLESS_COSTS,
            policy=FULL, ladder=ladder,
        )

    target_first = tuple(
        _bar(index, *values, interval="1h")
        for index, values in enumerate(
            [
                ("100", "101.1", "99.9", "101"),
                ("101", "101.1", "99.4", "99.5"),
                ("99.5", "100", "99.4", "100"),
                ("100", "100.1", "99.9", "100"),
            ],
            start=8,
        )
    )
    stop_first = tuple(
        _bar(index, *values, interval="1h")
        for index, values in enumerate(
            [
                ("100", "100.1", "99.4", "99.5"),
                ("99.5", "101.1", "99.4", "101"),
                ("101", "101.1", "99.9", "100"),
                ("100", "100.1", "99.9", "100"),
            ],
            start=8,
        )
    )

    # The PLAN is untouched by either series — it never saw one.
    assert policy.plan(subject) == plan
    # The OUTCOME differs, which is the evidence the ladder exists to supply.
    assert walk(target_first).trade.exit_reason.value == "target"
    assert walk(stop_first).trade.exit_reason.value == "stop"


def test_mutating_the_ladder_after_the_exit_changes_nothing() -> None:
    """A resolved trade must not be reopened by later candles."""
    coarse = (
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "121", "103", "120"),
        _bar(3, "120", "125", "119", "124"),
    )

    def walk(bars):
        return simulate_managed_trade(
            bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, entry_index=1, entry_price=bars[1].open,
            entry_at=bars[1].open_time, signal_at=bars[0].open_time,
            reference_price=Decimal("100"), stop_price=Decimal("90"),
            target_price=Decimal("120"), planned_risk_reward=3.0,
            window_bars=10, costs=FRICTIONLESS_COSTS, policy=FULL,
        ).trade

    mutated = (*coarse[:3], _scaled(coarse[3], "1000"))
    original, later = walk(coarse), walk(mutated)
    for field in ("exit_at", "exit_price", "exit_reason", "net_r", "mfe_r", "mae_r"):
        assert getattr(original, field) == getattr(later, field), field


def test_the_policy_modules_cannot_reach_the_lower_timeframe_layer() -> None:
    """**The architectural half of the proof.** An import is a capability."""
    for name in ("geometry.py", "geometry_variants.py", "nonstructural.py"):
        tree = ast.parse((_PACKAGE / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            for module in modules:
                for forbidden in ("intrabar", "exits", "entry", "validation_"):
                    assert forbidden not in module, f"{name} imports {module}"


def test_the_policy_modules_name_no_bar_and_no_outcome() -> None:
    """The tokens a lookahead would have to pass through, absent by inspection."""
    for name in ("geometry.py", "geometry_variants.py", "nonstructural.py"):
        text = (_PACKAGE / name).read_text(encoding="utf-8")
        body = text.split('"""', 2)[-1]      # past the module docstring
        for token in ("PriceBar", "simulate_trade", "fill_at_level", "BarLadder",
                      "mfe_r", "mae_r", "net_r"):
            assert token not in body, f"{name} names {token}"


# ------------------------------------------------- 3. the pre-registration ---


def test_the_pre_registration_imports_no_market_data_type() -> None:
    """Rules, never results. A threshold cannot be derived from a measurement here."""
    tree = ast.parse((_PACKAGE / "preregistration.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    for forbidden in (
        "PriceBar", "LabTrade", "GeometryCapture", "VariantMetrics",
        "simulate_trade", "trades_for_policy", "compute_lab_metrics",
    ):
        assert forbidden not in imported, f"the pre-registration imports {forbidden}"


def test_no_sealed_hypothesis_reads_an_outcome() -> None:
    """A policy is a pure function of a frozen candidate. Asserted per hypothesis."""
    subject = candidate()
    for item in PRE_REGISTERED_HYPOTHESES:
        first = item.policy.plan(subject)
        second = item.policy.plan(subject)
        assert first == second, item.policy_id
