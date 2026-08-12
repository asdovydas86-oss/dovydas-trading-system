"""The economic ledger: append-only, corrected by supersession, never edited.

`Trade` and `Correction` are the two record types this milestone builds; the
other four kinds `LedgerEventKind` names — transfer, reward, standalone fee,
adjustment — are additive and belong to the slices that first need them.

Read through `LedgerResolver`. Reading the raw stream and ignoring supersession is
how one consumer eventually reports a value the owner already corrected.
"""

from __future__ import annotations

from fmis.ledger.models import (
    CORRECTION_KIND,
    CORRECTION_SCHEMA_VERSION,
    CORRECTION_TYPE_SLUG,
    STORABLE_TRADE_STATUSES,
    SUPPORTED_CORRECTION_VERSIONS,
    SUPPORTED_TRADE_VERSIONS,
    TRADE_KIND,
    TRADE_SCHEMA_VERSION,
    TRADE_STATUS_TRANSITIONS,
    TRADE_TYPE_SLUG,
    BalanceEffect,
    Correction,
    IllegalTradeTransitionError,
    LedgerError,
    LedgerEventKind,
    LedgerSource,
    Trade,
    TradeSide,
    TradeStatus,
    advance_trade_status,
    balance_effects,
)
from fmis.ledger.resolver import (
    DanglingCorrectionError,
    LedgerResolver,
    ResolvedTrade,
    SupersessionError,
    resolve,
)

__all__ = [
    "LedgerError",
    "IllegalTradeTransitionError",
    "SupersessionError",
    "DanglingCorrectionError",
    "LedgerEventKind",
    "LedgerSource",
    "TradeSide",
    "TradeStatus",
    "TRADE_STATUS_TRANSITIONS",
    "STORABLE_TRADE_STATUSES",
    "advance_trade_status",
    "Trade",
    "Correction",
    "BalanceEffect",
    "balance_effects",
    "ResolvedTrade",
    "LedgerResolver",
    "resolve",
    "TRADE_SCHEMA_VERSION",
    "SUPPORTED_TRADE_VERSIONS",
    "TRADE_TYPE_SLUG",
    "TRADE_KIND",
    "CORRECTION_SCHEMA_VERSION",
    "SUPPORTED_CORRECTION_VERSIONS",
    "CORRECTION_TYPE_SLUG",
    "CORRECTION_KIND",
]
