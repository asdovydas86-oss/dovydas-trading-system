"""Where every byte goes, and the containment rule that keeps it there.

Architecture §24.1's two shapes, laid out on the `type/YYYY/MM` axis the archive
already uses:

```
<root>/
  index.jsonl                                  the metadata index
  journal/<YYYY>.jsonl                         the write journal, hash-chained
  records/<kind>/<YYYY>/<MM>/<record_id>.json  one captured artifact or entry
  ledger/<kind>/<YYYY>.jsonl                   one calendar year of events
  .writer.lock                                 held for the whole of one publish
```

**Every path this module builds is asserted to resolve inside the root**, even
though every component that reaches it has already been validated against a
traversal-free pattern. The two guards are not redundant: the pattern says *"this
id cannot contain a separator"*, and the containment check says *"and if that ever
stops being true, nothing is written outside the store."* `fmis.archive.storage`
made the same choice for the same reason, and its docstring records the concrete
trap — `Path("/root") / "/etc/passwd"` silently discards the left operand — which
is why an absolute candidate is rejected first and separately.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePath
from typing import Iterator

from fmis.persistence.errors import StoreIOError, StorePathError
from fmis.persistence.kinds import RecordKind, StorageShape

__all__ = [
    "INDEX_FILENAME",
    "JOURNAL_DIRECTORY",
    "RECORDS_DIRECTORY",
    "LEDGER_DIRECTORY",
    "LOCK_FILENAME",
    "DEFAULT_STORE_ROOT",
    "default_store_root",
    "StoreLayout",
]

INDEX_FILENAME = "index.jsonl"
JOURNAL_DIRECTORY = "journal"
RECORDS_DIRECTORY = "records"
LEDGER_DIRECTORY = "ledger"
LOCK_FILENAME = ".writer.lock"

#: The owner-level default, computed with the standard library only and
#: deliberately outside the git checkout — the same placement, and the same
#: reason, as `fmis.archive`'s `DEFAULT_ARCHIVE_ROOT`. **No test may write here**,
#: and nothing in this package falls back to it: a root is always passed in.
DEFAULT_STORE_ROOT = Path.home() / ".fmits" / "store"


def default_store_root() -> Path:
    return DEFAULT_STORE_ROOT


@dataclass(frozen=True, slots=True)
class StoreLayout:
    """One store root, and every path derived from it.

    `root` is always explicit. This class never falls back to
    `default_store_root()` on its own, so a test or a CLI invocation can never
    reach the owner's real store by omission.
    """

    root: Path

    def __post_init__(self) -> None:
        if not isinstance(self.root, (str, Path)):
            raise TypeError(f"root must be a path, got {type(self.root).__name__}")
        object.__setattr__(self, "root", Path(self.root))

    # -- containment ---------------------------------------------------------

    def resolve_within_root(self, relative_path: str) -> Path:
        """The absolute path of `relative_path`, or a refusal.

        An absolute `relative_path` is rejected explicitly and first, because
        `Path`'s `/` operator would otherwise discard the root entirely and the
        containment check below would be the only thing standing between a
        hand-edited index line and an arbitrary read.
        """
        if not isinstance(relative_path, str) or not relative_path:
            raise StorePathError("a relative path must be a non-empty str")
        if PurePath(relative_path).is_absolute():
            raise StorePathError(
                f"path {relative_path!r} must be relative to the store root"
            )
        if ".." in PurePath(relative_path).parts:
            raise StorePathError(
                f"path {relative_path!r} contains a parent-directory component"
            )
        resolved_root = self.root.resolve()
        candidate = (self.root / relative_path).resolve()
        if candidate != resolved_root and resolved_root not in candidate.parents:
            raise StorePathError(f"path {relative_path!r} escapes the store root")
        return self.root / relative_path

    # -- the four shapes -----------------------------------------------------

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_FILENAME

    @property
    def lock_path(self) -> Path:
        return self.root / LOCK_FILENAME

    def journal_relative_path(self, moment: datetime) -> str:
        return f"{JOURNAL_DIRECTORY}/{_year_of(moment)}.jsonl"

    def journal_path(self, moment: datetime) -> Path:
        return self.resolve_within_root(self.journal_relative_path(moment))

    def journal_years(self) -> tuple[int, ...]:
        return _years_in(self.root / JOURNAL_DIRECTORY)

    def record_relative_path(
        self, kind: RecordKind, record_id: str, moment: datetime
    ) -> str:
        utc = _utc(moment)
        return (
            f"{RECORDS_DIRECTORY}/{kind.value}/{utc.year:04d}/{utc.month:02d}/"
            f"{record_id}.json"
        )

    def log_relative_path(self, kind: RecordKind, moment: datetime) -> str:
        return f"{LEDGER_DIRECTORY}/{kind.value}/{_year_of(moment)}.jsonl"

    def relative_path_for(
        self, *, kind: RecordKind, shape: StorageShape, record_id: str, moment: datetime
    ) -> str:
        """The one derivation both the writer and the reader use.

        One function so write time and read time — which recomputes the path to
        detect an index line that has been pointed somewhere else — can never
        drift apart on this arithmetic.
        """
        if shape is StorageShape.RECORD_FILE:
            return self.record_relative_path(kind, record_id, moment)
        return self.log_relative_path(kind, moment)

    def log_years(self, kind: RecordKind) -> tuple[int, ...]:
        return _years_in(self.root / LEDGER_DIRECTORY / kind.value)

    def record_files(self, kind: RecordKind) -> tuple[Path, ...]:
        base = self.root / RECORDS_DIRECTORY / kind.value
        if not base.is_dir():
            return ()
        return tuple(sorted(base.rglob("*.json")))

    def all_stored_files(self) -> tuple[Path, ...]:
        """Every file the store considers its own — for orphan detection."""
        found: list[Path] = []
        for directory, pattern in (
            (RECORDS_DIRECTORY, "*.json"),
            (LEDGER_DIRECTORY, "*.jsonl"),
        ):
            base = self.root / directory
            if base.is_dir():
                found.extend(base.rglob(pattern))
        return tuple(sorted(found))

    # -- the writer lock -----------------------------------------------------

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        """Hold the store's single writer lock for the whole of one publish.

        Architecture §24.4 lists concurrency controls as *not built*, with the
        trigger *"more than one writer process exists — today there is exactly
        one."* This is deliberately less than that: it is not a concurrency
        *control*, it is the guard that stops the one writer's own read-modify-
        write of `index.jsonl` and the journal from interleaving with a second
        thread or a second invocation started by mistake. Two writers still are
        not a supported configuration; two writers no longer silently truncate
        each other's index.

        `fcntl.flock` is POSIX. On a platform without it the lock degrades to no
        lock and the store behaves exactly as it would have without this method —
        stated here rather than discovered later.
        """
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise StoreIOError(
                f"could not create the store root {self.root}: {error}"
            ) from error
        try:
            import fcntl
        except ImportError:  # pragma: no cover - POSIX only in this project
            yield
            return
        try:
            handle = open(self.lock_path, "a+b")
        except OSError as error:
            raise StoreIOError(
                f"could not open the writer lock {self.lock_path}: {error}"
            ) from error
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _utc(moment: datetime) -> datetime:
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise TypeError("a filing moment must be a timezone-aware datetime")
    return moment.astimezone(timezone.utc)


def _year_of(moment: datetime) -> str:
    return f"{_utc(moment).year:04d}"


def _years_in(directory: Path) -> tuple[int, ...]:
    if not directory.is_dir():
        return ()
    years: list[int] = []
    try:
        names = os.listdir(directory)
    except OSError as error:  # pragma: no cover - unreadable directory
        raise StoreIOError(f"could not list {directory}: {error}") from error
    for name in names:
        stem = name[: -len(".jsonl")] if name.endswith(".jsonl") else name
        if stem.isdigit():
            years.append(int(stem))
    return tuple(sorted(years))
