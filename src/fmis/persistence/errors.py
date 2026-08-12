"""Every way a write or a read of the durable store can fail, named.

One base class so a caller can catch the persistence layer as a group, and one
subclass per *remedy* rather than per raising site. The distinction matters: two
failures that a caller would handle identically are one error, and two that need
different handling are never merged. `RecordConflictError` and
`FrozenRecordError` both mean "this write did not happen", and the first is fixed
by looking at what is already stored while the second is fixed by appending a
different record entirely.

`PersistenceError` derives from `fmis.records.TradeDomainError`, so the trading
domain and the store that holds it are one catchable family. A surface that has
to distinguish "the record is malformed" from "the file is missing" already can;
one that only needs "this did not work" should not have to know the difference.
"""

from __future__ import annotations

from fmis.records import TradeDomainError

__all__ = [
    "PersistenceError",
    "RecordMissingError",
    "RecordConflictError",
    "FrozenRecordError",
    "ProjectionError",
    "UnknownRecordKindError",
    "StoreIntegrityError",
    "AppendOnlyViolationError",
    "LineageError",
    "StorePathError",
    "StoreIOError",
]


class PersistenceError(TradeDomainError):
    """Base class for every durable-store failure."""


class RecordMissingError(PersistenceError):
    """No record with this id is in the store.

    Deliberately not named `RecordNotFoundError`: `fmis.archive` already exports
    that name for the *analysis* archive, and the repository's zero-export-
    collision invariant is worth more than the marginally more familiar word.
    """


class RecordConflictError(PersistenceError):
    """This id is already stored, holding different content.

    Under content-derived identity this is a digest-prefix collision and nothing
    else — two records with the same economic content produce the same id *and*
    the same bytes, which is an idempotent success rather than a conflict. Handled
    explicitly rather than assumed unreachable, following ADR-0027's precedent.
    """


class FrozenRecordError(PersistenceError):
    """An edit was attempted on a record that has no edit path.

    Raised by `update` and `replace` on every captured artifact. The alternative —
    accepting the call and writing a second record — is how "frozen" becomes a
    comment three milestones after it was a rule.
    """


class ProjectionError(PersistenceError):
    """A rebuildable projection was asked to persist, or to rebuild without inputs.

    A position is a fold over the ledger. Storing one creates a second answer to
    *what do I hold*, and the two drift the first time the fold's policy version
    moves.
    """


class UnknownRecordKindError(PersistenceError):
    """A type this store has no spec for, or a kind string a newer build wrote."""


class StoreIntegrityError(PersistenceError):
    """Stored bytes disagree with what they claim to be.

    Covers a payload whose recomputed digest differs from the stored one, an id
    that does not match the content it names, an index entry pointing at a file
    that is not there, and a journal chain whose links do not verify.
    """


class AppendOnlyViolationError(StoreIntegrityError):
    """An append-only file lost or altered content that was already published.

    Its own class because the remedy is unlike every other integrity failure:
    nothing can be recomputed, and the only honest response is to stop writing and
    restore. Detected by comparing the bytes about to be published against the
    bytes already on disk — a rewrite is never merely improbable here, it is
    refused.
    """


class LineageError(PersistenceError):
    """A supersession chain that branches, loops, or names a record not in the store.

    A branch is the important one: two records superseding the same id gives
    *"what does this say now"* two answers, and a store that picks one is a store
    that quietly decides which of the owner's corrections counted.
    """


class StorePathError(PersistenceError):
    """A path would resolve outside the store root, or is not relative to it."""


class StoreIOError(PersistenceError):
    """The filesystem refused a read or a write."""
