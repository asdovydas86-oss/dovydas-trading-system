"""Where completed scans are remembered. **A bounded rolling buffer, not an archive.**

**Why this is not `fmis.archive` and not `fmis.persistence`.** Both already
exist, both write atomically, and neither is this. `fmis.archive` (ADR-0027) is
the permanent, content-addressed record of what the system decided — nothing in
it is ever pruned, and pruning is exactly what this store must do. `fmis.
persistence` is the trade domain's journalled record store, whose write journal
is a legal-grade audit trail of money movements; a market observation that will
be discarded in eight refreshes does not belong in it. Scan memory has different
semantics on every axis that matters — bounded retention, tolerated corruption,
comparability rather than lineage — so it is its own small store, and it reuses
the one primitive that *is* shared: `fmis.archive.atomic.atomic_write`, exactly
as `fmis.persistence.store` reuses it.

**The layout, and why the filename carries the instant.**

```
<root>/
  scans/<recorded_at compact UTC>-<scan_id first 12>.json
```

One file per scan, named so that lexicographic order **is** chronological order.
Finding the previous scan is therefore a directory listing and one decode, not a
walk of every record — which is what keeps `/swing` rendering cheap however long
the product has been running.

**Atomicity.** Every file is published through `atomic_write`: bytes built fully
in memory, written to a temporary file in the same directory, flushed, fsynced,
then `os.replace`d. An interrupted write leaves a dot-prefixed `.tmp` that the
`*.json` glob never sees. A reader gets no file or a complete file; there is no
third outcome, and no partial record can ever be mistaken for a baseline.

**Concurrency.** Names are unique per scan identity, so two writers cannot
collide on one file and a half-written record cannot exist. Within a process the
dashboard's `SnapshotHolder` already serialises refreshes under a lock, so the
ordinary case is one writer. Two dashboards on one machine would each record
their own scans and each compare against whichever completed most recently — a
true statement about a store two processes are writing, and stated here rather
than defended against, because this is a single-operator local product.

**Corruption is reported, never routed around.** `latest_complete` stops at the
first record it cannot read and says so. Skipping it to reach an older one would
silently redefine *the previous scan* as *some earlier scan*, and the operator
would be shown a delta over a gap they were never told about.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from pathlib import Path

from fmis.archive.atomic import atomic_write
from fmis.archive.errors import ArchiveIOError
from fmis.scan_memory.codec import decode_scan, encode_scan
from fmis.scan_memory.models import (
    ScanHistoryFormatError,
    ScanHistoryIOError,
    ScanMemoryError,
    ScanRecord,
)

__all__ = [
    "DEFAULT_SCAN_MEMORY_ROOT",
    "DEFAULT_RETAINED_SCANS",
    "SCANS_DIRECTORY",
    "default_scan_memory_root",
    "StoredScan",
    "ScanHistoryStore",
    "HISTORY_ERRORS",
]

#: What a caller must catch around a store call. One name, one place, rather
#: than reaching into the models module for the two exceptions separately.
HISTORY_ERRORS = (ScanHistoryFormatError, ScanHistoryIOError)

#: The owner-level default, computed with the standard library only and
#: deliberately **outside the git checkout** — the same placement, and the same
#: reason, as `fmis.archive`'s `DEFAULT_ARCHIVE_ROOT` and `fmis.persistence`'s
#: `DEFAULT_STORE_ROOT`. Runtime scan history is not source, is never committed,
#: and needs no ignore rule because it is not inside the repository at all.
DEFAULT_SCAN_MEMORY_ROOT = Path.home() / ".fmits" / "scan_memory"

#: How many scans are kept. The product needs **current and previous**; the
#: extra six are slack so that a run of incomplete scans — a provider having a
#: bad hour — cannot push the last complete baseline out of the window before
#: the next complete one arrives. It is not an analytics history and nothing in
#: this repository reads further back than the first complete record.
DEFAULT_RETAINED_SCANS = 8

SCANS_DIRECTORY = "scans"

_STAMP_FORMAT = "%Y%m%dT%H%M%S%f"


def default_scan_memory_root() -> Path:
    return DEFAULT_SCAN_MEMORY_ROOT


@dataclass(frozen=True, slots=True)
class StoredScan:
    """One record and the path it was published to."""

    path: Path
    record: ScanRecord


class ScanHistoryStore:
    """The only thing that writes scan history, and the only way to read it back.

    ``root`` is always explicit. This class never falls back to
    `default_scan_memory_root()` on its own, so a test can never reach the
    owner's real history by omission — the rule `fmis.persistence.StoreLayout`
    already states for the same reason.
    """

    def __init__(self, root: Path | str, *, retain: int = DEFAULT_RETAINED_SCANS) -> None:
        if not isinstance(root, (str, Path)):
            raise ScanMemoryError(f"root must be a path, got {type(root).__name__}")
        if not isinstance(retain, int) or isinstance(retain, bool) or retain < 2:
            raise ScanMemoryError(
                "retain must be at least 2; the product compares a scan with the "
                "one before it, and a store that keeps one record can never do that"
            )
        self._root = Path(root)
        self._retain = retain

    @property
    def root(self) -> Path:
        return self._root

    @property
    def retain(self) -> int:
        return self._retain

    @property
    def scans_directory(self) -> Path:
        return self._root / SCANS_DIRECTORY

    # -- naming ---------------------------------------------------------------

    def path_for(self, record: ScanRecord) -> Path:
        """Where this record lives. **A pure function of its identity.**

        Recording the same completed scan twice therefore targets the same path
        rather than appending a second row, which is what makes a duplicated
        observation an idempotent no-op instead of a fake `A → A` transition.
        """
        stamp = record.recorded_at.astimezone(timezone.utc).strftime(_STAMP_FORMAT)
        return self.scans_directory / f"{stamp}-{record.scan_id[:12]}.json"

    def _files(self) -> list[Path]:
        """Every published record, newest first. Never a temporary file."""
        directory = self.scans_directory
        if not directory.is_dir():
            return []
        try:
            return sorted(
                (path for path in directory.glob("*.json") if not path.name.startswith(".")),
                reverse=True,
            )
        except OSError as error:
            raise ScanHistoryIOError(f"could not list {directory}: {error}") from error

    # -- reading --------------------------------------------------------------

    def read(self, path: Path) -> ScanRecord:
        try:
            data = path.read_bytes()
        except OSError as error:
            raise ScanHistoryIOError(f"could not read {path}: {error}") from error
        return decode_scan(data)

    def records(self) -> tuple[StoredScan, ...]:
        """Every readable record, newest first. **Stops at the first unreadable one.**"""
        out: list[StoredScan] = []
        for path in self._files():
            out.append(StoredScan(path=path, record=self.read(path)))
        return tuple(out)

    def latest_complete(self, *, exclude: str | None = None) -> ScanRecord | None:
        """The newest complete record, or `None` when there is none yet.

        ``exclude`` drops one scan id from consideration, which is how a scan
        being recorded avoids comparing itself with the copy of itself a
        previous run of the same completed scan already published.

        Raises:
            ScanHistoryFormatError: a record newer than the answer could not be
                read. Deliberately *not* skipped — see the module docstring.
        """
        for path in self._files():
            record = self.read(path)
            if exclude is not None and record.scan_id == exclude:
                continue
            if record.complete:
                return record
        return None

    # -- writing --------------------------------------------------------------

    def append(self, record: ScanRecord) -> StoredScan:
        """Publish one record atomically, then prune. **Idempotent per scan identity.**

        Raises:
            ScanHistoryIOError: the filesystem refused. The caller's contract is
                that the current market analysis is still true and still shown;
                only the remembering failed.
        """
        if not isinstance(record, ScanRecord):
            raise ScanMemoryError(f"record must be a ScanRecord, got {type(record).__name__}")
        path = self.path_for(record)
        try:
            atomic_write(path, encode_scan(record))
        except ArchiveIOError as error:
            raise ScanHistoryIOError(f"could not record the scan: {error}") from error
        self.prune()
        return StoredScan(path=path, record=record)

    def prune(self) -> tuple[Path, ...]:
        """Delete everything past the retention bound, oldest first.

        Deterministic: the newest ``retain`` files by name are kept and the rest
        are removed. A file that cannot be removed is reported rather than
        swallowed, but it never stops the newer records from being kept.
        """
        files = self._files()
        removed: list[Path] = []
        for path in files[self._retain :]:
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError as error:
                raise ScanHistoryIOError(f"could not prune {path}: {error}") from error
            removed.append(path)
        return tuple(removed)
