"""Builders for Milestone BO's tests — one place a valid object is assembled.

Every test below the surface needs a `TradePlan`, a `TradeActivation` and a
handful of bars, and hand-rolling them per test produces fixtures that drift:
one test's activation ends up with a ladder another's does not, and a guard that
should have failed passes because the two are not comparable. These build the
same object every time and take overrides.

Nothing here reaches a network and nothing reads a clock. Every instant is
derived from `START`, so a rendered page and a record id are both pinnable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fmis.accounts import AccountId, Book, MarketId, MarketMode, VenueId
from fmis.money import AssetCode, Quantity
from fmis.plan import TradePlan
from fmis.proposal import StatedConfidence
from fmis.provenance import Absent
from fmis.records import RecordAudit
from fmis.snapshotting import TradeDirection
from fmis.trade_lifecycle import (
    BreakEvenRule,
    EntryType,
    ExitLadder,
    ExitLeg,
    StopManagement,
    TradeActivation,
    TradeLifecycleEvent,
    TradeLifecycleKind,
    TrailingRule,
)
from fmis.paper import (
    PAPER_FILL_POLICY_ID,
    PAPER_FILL_POLICY_VERSION,
    PAPER_ZERO_COST_POLICY,
    PriceBar,
)
from fmis.versioning import VersionAxis, VersionSet

START = datetime(2026, 8, 1, tzinfo=timezone.utc)
INTERVAL = "1h"
SYMBOL = "BTCUSDT"

MARKET = MarketId(
    venue=VenueId("binance"),
    base_asset=AssetCode("BTC"),
    quote_asset=AssetCode("USDT"),
    mode=MarketMode.SPOT,
)

VERSIONS = VersionSet.of(
    {VersionAxis.CODE_VERSION: "test"}, absent_reason="a test fixture"
)


def at(hours: int) -> datetime:
    """`START` plus whole hours — the only clock these tests have."""
    return START + timedelta(hours=hours)


def plan(**overrides: Any) -> TradePlan:
    """A committed long: stop 95, targets 110 and 120."""
    fields: dict[str, Any] = {
        "created_at": START,
        "committed_at": START,
        "market": MARKET,
        "book": Book.PAPER,
        "direction": TradeDirection.LONG,
        "initial_invalidation": Decimal("95"),
        "targets": (Decimal("110"), Decimal("120")),
        "stated_confidence": StatedConfidence("medium"),
        "version_set": VERSIONS,
        "audit": RecordAudit.frozen_at(START),
    }
    fields.update(overrides)
    if "audit" not in overrides and "created_at" in overrides:
        fields["audit"] = RecordAudit.frozen_at(fields["created_at"])
    return TradePlan(**fields)


def short_plan(**overrides: Any) -> TradePlan:
    """The mirror of `plan`: stop 105, targets 90 and 80."""
    fields: dict[str, Any] = {
        "direction": TradeDirection.SHORT,
        "initial_invalidation": Decimal("105"),
        "targets": (Decimal("90"), Decimal("80")),
    }
    fields.update(overrides)
    return plan(**fields)


def ladder(*shares: str) -> ExitLadder:
    """A ladder over `plan`'s two targets, with the shares given."""
    targets = (Decimal("110"), Decimal("120"))
    return ExitLadder(
        legs=tuple(
            ExitLeg(target=targets[index], fraction=Decimal(share))
            for index, share in enumerate(shares)
        )
    )


def activation(committed: TradePlan | None = None, **overrides: Any) -> TradeActivation:
    """A stop-entry at 100 for one unit, exiting half at each target."""
    subject = committed or plan()
    fields: dict[str, Any] = {
        "activated_at": START,
        "plan_id": subject.plan_id,
        "market": subject.market,
        "book": Book.PAPER,
        "account": AccountId("paper"),
        "direction": subject.direction,
        "entry_type": EntryType.STOP_ENTRY,
        "quantity": Quantity(Decimal("1"), subject.market.base_asset),
        "ladder": ExitLadder(
            legs=tuple(
                ExitLeg(target=target, fraction=Decimal("0.5"))
                for target in subject.targets
            )
        ),
        "stop_management": StopManagement(),
        "cost_policy": PAPER_ZERO_COST_POLICY,
        "fill_policy_id": PAPER_FILL_POLICY_ID,
        "fill_policy_version": PAPER_FILL_POLICY_VERSION,
        "interval": INTERVAL,
        "version_set": VERSIONS,
        "audit": RecordAudit.frozen_at(START),
        "entry_price": Decimal("100"),
    }
    fields.update(overrides)
    moment = fields["activated_at"]
    if "audit" not in overrides:
        fields["audit"] = RecordAudit.frozen_at(moment)
    return TradeActivation(**fields)


def market_activation(committed: TradePlan | None = None, **overrides: Any) -> TradeActivation:
    """The same activation with a market entry, which names no level."""
    fields: dict[str, Any] = {
        "entry_type": EntryType.MARKET,
        "entry_price": Absent("a market entry names no level"),
    }
    fields.update(overrides)
    return activation(committed, **fields)


def break_even(trigger: str = "1", offset: str = "0") -> StopManagement:
    return StopManagement(
        break_even=BreakEvenRule(
            trigger_r=Decimal(trigger), offset_r=Decimal(offset)
        )
    )


def trailing(distance: str = "1", start: str | None = None) -> StopManagement:
    return StopManagement(
        trailing=TrailingRule(
            distance_r=Decimal(distance),
            activate_at_r=(
                Absent("the trail runs from the first bar")
                if start is None
                else Decimal(start)
            ),
        )
    )


def bar(
    hours: int,
    open_price: str,
    high: str,
    low: str,
    close: str,
    *,
    symbol: str = SYMBOL,
    interval: str = INTERVAL,
) -> PriceBar:
    """One exact bar, opening `hours` after `START`."""
    return PriceBar(
        symbol=symbol,
        interval=interval,
        open_time=at(hours),
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
    )


def event(
    subject: TradeActivation,
    kind: TradeLifecycleKind,
    *,
    hours: int = 0,
    **overrides: Any,
) -> TradeLifecycleEvent:
    """One lifecycle event against an activation, with the kind's own rules met."""
    moment = at(hours)
    fields: dict[str, Any] = {
        "activation_id": subject.activation_id,
        "kind": kind,
        "occurred_at": moment,
        "recorded_at": moment,
        "audit": RecordAudit.frozen_at(moment),
    }
    from fmis.trade_lifecycle import MEASURED_LIFECYCLE_KINDS

    if kind in MEASURED_LIFECYCLE_KINDS:
        fields["causing_close_time"] = moment
    if kind is TradeLifecycleKind.AMBIGUOUS_BAR:
        fields["note"] = "the bar reached both levels"
    if kind is TradeLifecycleKind.SUPERSEDED:
        fields["reference"] = subject.activation_id
    if kind is TradeLifecycleKind.CANCELLED:
        from fmis.provenance import VersionedTerm

        fields["reason"] = VersionedTerm(
            vocabulary_id="stop_amendment_reason",
            term_id="thesis_invalidated",
            taxonomy_version=1,
        )
    fields.update(overrides)
    return TradeLifecycleEvent(**fields)
