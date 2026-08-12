"""The journal: the owner's own words, typed, tagged and linked.

`JournalEntry` is the record; `TradeJournal` is the read-time view over every
entry linked to one subject — the brief's name, modelled as a projection so it
never becomes a second place an entry can live.
"""

from __future__ import annotations

from fmis.journal.models import (
    COUNTED_TAG_ORIGINS,
    JOURNAL_ENTRY_KIND,
    JOURNAL_ENTRY_SCHEMA_VERSION,
    JOURNAL_ENTRY_TYPE_SLUG,
    SUPPORTED_JOURNAL_ENTRY_VERSIONS,
    JournalEntry,
    JournalError,
    JournalKind,
    JournalLink,
    JournalTag,
    LinkKind,
    ReviewStatus,
    TagOrigin,
    TradeJournal,
)

__all__ = [
    "JournalError",
    "JournalKind",
    "TagOrigin",
    "COUNTED_TAG_ORIGINS",
    "JournalTag",
    "LinkKind",
    "JournalLink",
    "ReviewStatus",
    "JournalEntry",
    "TradeJournal",
    "JOURNAL_ENTRY_SCHEMA_VERSION",
    "SUPPORTED_JOURNAL_ENTRY_VERSIONS",
    "JOURNAL_ENTRY_TYPE_SLUG",
    "JOURNAL_ENTRY_KIND",
]
