"""Builders for trade-capture fixtures.

Extends `tests/trade_domain_helpers.py` and `tests/persistence_helpers.py` rather
than duplicating either: the market, the account and the dust policy are already
defined there, and a second definition of "a valid trade" would drift from the
first.

**No clock.** Every instant is `AT(...)`, a fixed value. Nothing in
`fmis.trade_capture` reads a clock either, so a test that needed one would be
testing something this system does not do.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from trade_domain_helpers import ACCOUNT, AT, BTC, MARKET, USDT

from fmis.accounts import Book
from fmis.money import Money, Quantity
from fmis.persistence import TradingStore
from fmis.snapshotting import TradeDirection
from fmis.trade_capture import (
    CAPTURE_DUST_POLICY,
    CloseRequest,
    NoteRequest,
    RecordRequest,
    close_trade,
    record_trade,
)

__all__ = [
    "CODE_VERSION",
    "capture_store",
    "record_request",
    "close_request",
    "note_request",
    "recorded",
    "closed",
]

#: The build every fixture stamps its records with. A fixed string, because a
#: version read from the package would make a record id change on every release
#: and turn a golden-id assertion into a flake.
CODE_VERSION = "bk-test"


def capture_store(root: Path) -> TradingStore:
    """A store under `root`, folding on the capture package's own dust policy."""
    return TradingStore(root, dust=CAPTURE_DUST_POLICY)


def record_request(**overrides: Any) -> RecordRequest:
    """A complete LONG capture: 0.5 BTC at 60000, stop 58400, one target."""
    values: dict[str, Any] = {
        "market": MARKET,
        "book": Book.SWING,
        "account": ACCOUNT,
        "direction": TradeDirection.LONG,
        "entry_price": Decimal("60000"),
        "stop": Decimal("58400"),
        "targets": (Decimal("64000"),),
        "quantity": Quantity(Decimal("0.5"), BTC),
        "fee": Money(Decimal("15"), USDT),
        "fx_rate_to_tax_currency": Decimal("10.5"),
        "fx_source": "riksbank",
        "occurred_at": AT(10),
        "written_at": AT(11),
        "author": "owner",
        "confidence": "moderate",
        "code_version": CODE_VERSION,
    }
    values.update(overrides)
    return RecordRequest(**values)


def close_request(plan_id: str, **overrides: Any) -> CloseRequest:
    """A complete exit at 63800, the whole open position, reason `target_reached`."""
    values: dict[str, Any] = {
        "plan_id": plan_id,
        "exit_price": Decimal("63800"),
        "fee": Money(Decimal("16"), USDT),
        "fx_rate_to_tax_currency": Decimal("10.6"),
        "fx_source": "riksbank",
        "occurred_at": AT(9, day=14),
        "written_at": AT(10, day=14),
        "author": "owner",
        "reason": "target_reached",
        "code_version": CODE_VERSION,
    }
    values.update(overrides)
    return CloseRequest(**values)


def note_request(plan_id: str, **overrides: Any) -> NoteRequest:
    values: dict[str, Any] = {
        "plan_id": plan_id,
        "body": "still holding; the weekly close is the thing to watch",
        "recorded_at": AT(12),
        "written_at": AT(12),
        "author": "owner",
        "code_version": CODE_VERSION,
    }
    values.update(overrides)
    return NoteRequest(**values)


def recorded(store: TradingStore, **overrides: Any) -> Any:
    """Record one trade and return the outcome."""
    return record_trade(store, record_request(**overrides))


def closed(store: TradingStore, plan_id: str, **overrides: Any) -> Any:
    """Close a recorded trade and return the outcome."""
    return close_trade(store, close_request(plan_id, **overrides))


def at(hour: int, *, day: int = 12) -> datetime:
    """Re-exported so a capture test need not import two helper modules."""
    return AT(hour, day=day)


__all__.append("at")
