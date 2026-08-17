"""Trade capture — the owner records what they decided and what they did.

The first milestone in which FMITS **writes** to the durable store. Everything
before it read: `fmits today` assembles a page from records nothing could
produce, and Milestone BI built nine repositories with no command reaching any of
them. This package is the composition root that closes that gap for the one
workflow that matters first — the owner entering a swing trade.

**A swing trade is three records, and this package is the only thing that knows
that.** A `TradePlan` holds the commitment: the stop, the targets, the stated
confidence, the setup it came from. A `Trade` holds each fill. A `JournalEntry`
holds the owner's own words. They stay three because they are three different
kinds of fact with three different truth conditions — intent, money, and opinion
— and a single "swing trade" row would make *"did I honour my stop?"*
unanswerable the first time a stop moved.

**Nothing here executes anything.** No order is placed, no exchange is reached,
no venue is confirmed against. FMITS becomes the system of record for what the
owner did; the owner remains the trader.

**Nothing bypasses `TradingStore`.** Every write is a repository call, so the
store's hash-chained write journal stays a complete account of the store rather
than a mostly complete one.
"""

from __future__ import annotations

from fmis.trade_capture.capture import (
    CAPTURE_DUST_POLICY,
    CLOSE_REASON,
    DEFAULT_QUOTE_ASSET,
    DEFAULT_VENUE,
    EXIT_REASON_VOCABULARY,
    NOTE_REASON,
    RECORD_REASON,
    SETUP_TYPE_VOCABULARY,
    TAXONOMY_VERSION,
    WRITE_REASON_VOCABULARY,
    CloseRequest,
    NoteRequest,
    RecordRequest,
    append_note,
    capture_version_set,
    close_trade,
    entry_side,
    exit_side,
    market_from_symbol,
    PlanRequest,
    record_plan,
    record_trade,
)
from fmis.trade_capture.inputs import (
    BOOK_CHOICES,
    CAPTURE_ERRORS,
    DEFAULT_MARKET_MODE,
    DIRECTION_CHOICES,
    MARKET_MODE_CHOICES,
    STATUS_CHOICES,
    capture_store_root,
    close_request_from_text,
    filters_from_text,
    note_request_from_text,
    open_store,
    plan_request_from_text,
    record_request_from_text,
)
from fmis.trade_capture.models import (
    CaptureOutcome,
    CaptureRefusedError,
    CaptureStatus,
    CaptureWarning,
    FillLine,
    TradeCaptureError,
    TradeFilters,
    TradeListing,
    TradeNotFoundError,
    TradeRow,
    TradeView,
    WrittenRecord,
)
from fmis.trade_capture.render import render_listing, render_outcome, render_trade
from fmis.trade_capture.views import (
    CAPTURE_LIMITATIONS,
    PLAN_SUBJECT_KIND,
    TRADE_SUBJECT_KIND,
    fills_for_plan,
    list_trades,
    load_plan,
    load_trade,
)

__all__ = [
    # errors
    "TradeCaptureError",
    "CaptureRefusedError",
    "TradeNotFoundError",
    # the model
    "CaptureStatus",
    "CaptureWarning",
    "WrittenRecord",
    "FillLine",
    "TradeView",
    "TradeRow",
    "TradeFilters",
    "TradeListing",
    "CaptureOutcome",
    # writing
    "CAPTURE_DUST_POLICY",
    "TAXONOMY_VERSION",
    "WRITE_REASON_VOCABULARY",
    "SETUP_TYPE_VOCABULARY",
    "EXIT_REASON_VOCABULARY",
    "RECORD_REASON",
    "CLOSE_REASON",
    "NOTE_REASON",
    "DEFAULT_VENUE",
    "DEFAULT_QUOTE_ASSET",
    "entry_side",
    "exit_side",
    "market_from_symbol",
    "capture_version_set",
    "RecordRequest",
    "CloseRequest",
    "NoteRequest",
    "PlanRequest",
    "record_plan",
    "record_trade",
    "close_trade",
    "append_note",
    # the text boundary — what the CLI hands over, and what it may catch
    "CAPTURE_ERRORS",
    "BOOK_CHOICES",
    "DIRECTION_CHOICES",
    "MARKET_MODE_CHOICES",
    "STATUS_CHOICES",
    "DEFAULT_MARKET_MODE",
    "capture_store_root",
    "open_store",
    "plan_request_from_text",
    "record_request_from_text",
    "close_request_from_text",
    "note_request_from_text",
    "filters_from_text",
    # reading
    "PLAN_SUBJECT_KIND",
    "TRADE_SUBJECT_KIND",
    "CAPTURE_LIMITATIONS",
    "fills_for_plan",
    "load_plan",
    "load_trade",
    "list_trades",
    # rendering
    "render_trade",
    "render_listing",
    "render_outcome",
]
