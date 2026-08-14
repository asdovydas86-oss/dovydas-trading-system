"""Builders for the durable store's fixtures.

Extends `tests/trade_domain_helpers.py` rather than duplicating it: the domain
records are already built there, and a second set of builders would be a second
definition of "a valid trade" that drifts from the first.

Two rules this module keeps, both inherited from the domain's helpers:

* **No clock.** `NOW` is a fixed instant. Nothing in `fmis.persistence` reads a
  clock either, so a test that needed one would be testing something this system
  does not do.
* **No policy value.** Dust thresholds, risk limits and write reasons are all
  supplied by the caller. A helper that quietly chose one would make a test pass
  for the wrong reason.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from trade_domain_helpers import (
    ACCOUNT,
    AT,
    BTC,
    MARKET,
    USDT,
    dust_policy,
    money,
    quantity,
    reason_tag,
    version_set,
)

from fmis.accounts import Book
from fmis.analysis_record import AnalysisRecord
from fmis.journal import JournalEntry, JournalKind, JournalLink, LinkKind
from fmis.persistence import (
    RecordStore,
    TradingStore,
    WriteOperation,
    WriteRequest,
    WriteSource,
)
from fmis.portfolio import (
    AllocationEntry,
    CashBalance,
    ExposureSummary,
    FlowSummary,
    Holding,
    MarkQuote,
    PortfolioSnapshot,
)
from fmis.provenance import Absent
from fmis.records import RecordAudit
from fmis.risk import (
    LimitPeriod,
    LimitScope,
    LimitSeverity,
    LimitUnit,
    RiskBudget,
    RiskLimit,
)

__all__ = [
    "NOW",
    "later_than",
    "write_request",
    "new_store",
    "new_record_store",
    "journal_entry",
    "risk_limit",
    "risk_budget",
    "portfolio_snapshot",
    "analysis_record",
    "sample_records",
    "ARCHIVE_RECORD_ID",
    "ABOUT_MARKET",
]

#: The instant every write in these tests is filed at, unless one says otherwise.
#: Deliberately after `trade_domain_helpers.AT`'s day, because the store refuses to
#: file a record before the instant it describes.
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def later_than(moment: datetime, *, hours: int = 1) -> datetime:
    return moment + timedelta(hours=hours)


def write_request(**overrides: Any) -> WriteRequest:
    """A complete, valid write request. Every field is overridable."""
    values: dict[str, Any] = {
        "written_at": NOW,
        "source": WriteSource.OWNER,
        "author": "owner",
        "reason": reason_tag("manual_entry", "write_reason"),
        "version_set": version_set(),
        "operation": WriteOperation.CREATE,
    }
    values.update(overrides)
    return WriteRequest(**values)


def new_store(root: Path, **overrides: Any) -> TradingStore:
    """A `TradingStore` under `root`, with the domain helpers' dust policy."""
    dust = overrides.pop("dust", dust_policy())
    return TradingStore(root, dust=dust, **overrides)


def new_record_store(root: Path) -> RecordStore:
    return RecordStore(root)


# --------------------------------------------------------------------------
# The four records `trade_domain_helpers` does not build.
# --------------------------------------------------------------------------

#: A well-formed `fmis.archive` record id. An analysis citation is the one kind
#: whose id belongs to the archive's scheme rather than the domain's.
ARCHIVE_RECORD_ID = "workspace-BTCUSDT-20260812T090000Z-0123456789abcdef"

ABOUT_MARKET = JournalLink(LinkKind.ABOUT, "market", MARKET.value)


def journal_entry(**overrides: Any) -> JournalEntry:
    recorded = overrides.pop("recorded_at", AT(9))
    values: dict[str, Any] = {
        "kind": JournalKind.NOTE,
        "recorded_at": recorded,
        "author": "owner",
        "audit": RecordAudit.frozen_at(recorded),
        "title": "waiting on the execution role",
        "body": "no close above 62000 yet",
        "links": (ABOUT_MARKET,),
    }
    values.update(overrides)
    return JournalEntry(**values)


def risk_limit(limit_id: str = "per_trade_risk", **overrides: Any) -> RiskLimit:
    values: dict[str, Any] = {
        "limit_id": limit_id,
        "scope": LimitScope.PER_TRADE_RISK,
        "value": Decimal("0.02"),
        "unit": LimitUnit.PERCENT_OF_EQUITY,
        "period": LimitPeriod.NONE,
        "severity": LimitSeverity.HARD_BLOCK,
    }
    values.update(overrides)
    return RiskLimit(**values)


def risk_budget(**overrides: Any) -> RiskBudget:
    effective = overrides.pop("effective_from", AT(0))
    values: dict[str, Any] = {
        "budget_id": "swing_budget",
        "risk_policy_version": 1,
        "effective_from": effective,
        "limits": (risk_limit(),),
        "audit": RecordAudit.frozen_at(effective),
    }
    values.update(overrides)
    return RiskBudget(**values)


def portfolio_snapshot(**overrides: Any) -> PortfolioSnapshot:
    as_of = overrides.pop("as_of", AT(9))
    values: dict[str, Any] = {
        "portfolio_id": "main",
        "base_currency": USDT,
        "as_of": as_of,
        "books_covered": (Book.SWING,),
        "holdings": (
            Holding(
                BTC,
                ACCOUNT,
                quantity("1.5"),
                MarkQuote(Decimal("60000"), USDT, "binance", AT(8)),
            ),
        ),
        "cash": (
            CashBalance(ACCOUNT, money("2500"), Absent("already the base currency")),
        ),
        "flows": FlowSummary(money("0"), money("0"), Absent("first snapshot")),
        "exposure": ExposureSummary(
            money("90000"),
            money("90000"),
            money("90000"),
            money("92500"),
            money("90000"),
        ),
        "allocations": (
            AllocationEntry("asset", "BTC", money("90000"), money("92500"), "cls-v1"),
        ),
        "open_position_event_ids": (),
        "version_set": version_set(),
        "audit": RecordAudit.frozen_at(as_of),
    }
    values.update(overrides)
    return PortfolioSnapshot(**values)


def analysis_record(**overrides: Any) -> AnalysisRecord:
    archived = overrides.pop("archived_at", AT(9))
    values: dict[str, Any] = {
        "record_id": ARCHIVE_RECORD_ID,
        "record_type": "workspace",
        "payload_schema_version": 1,
        "analysis_as_of": AT(9),
        "subject": ("BTCUSDT",),
        "content_digest": "sha256:" + "b" * 64,
        "archived_at": archived,
        "audit": RecordAudit.frozen_at(archived),
    }
    values.update(overrides)
    return AnalysisRecord(**values)


def sample_records() -> tuple[Any, ...]:
    """One valid instance of every persisted kind, in dependency order.

    Dependency order matters: a lifecycle event names a proposal, and the store
    refuses an event whose subject it does not hold.
    """
    from trade_domain_helpers import (
        correction,
        decision_window,
        lifecycle_event,
        market_snapshot,
        proposal,
        trade,
        trade_plan,
    )

    from fmis.proposal import LifecycleKind

    original = trade()
    replacement = trade(quantity=quantity("0.6"))
    subject = proposal()
    return (
        original,
        correction(original, replacement),
        trade_plan(),
        market_snapshot(),
        decision_window(),
        subject,
        lifecycle_event(subject, LifecycleKind.REAFFIRMED, 11),
        journal_entry(),
        risk_budget(),
        portfolio_snapshot(),
        analysis_record(),
    )
