"""The append-only line file, and why it is not an atomic whole-file rewrite.

Three of this store's four file shapes are line files: the write journal, the
ledger year files and the index. All three are appended to and never edited, and
this module is the only code in the package that writes them.

**A real `O_APPEND` write, not a read-modify-rewrite.** `fmis.archive.manifest`
publishes its manifest by reading the whole file, appending in memory and
replacing it atomically — correct, and its own docstring records the O(entries)
cost as proportionate for *"hundreds, not millions."* This store makes the other
choice, for a reason that is about integrity rather than cost: a whole-file
rewrite is a code path that *can* produce a shorter file. If the read ever comes
back truncated — a bug, a partial restore, a filesystem returning short reads —
the rewrite publishes the truncation and the history is gone with no evidence it
was ever there. `os.open(..., O_APPEND)` cannot do that. The kernel moves the
offset to end-of-file atomically on every write, so the only reachable outcome is
*more* bytes than before.

Record files keep the archive's atomic-publish path unchanged, because they are
written once and never appended to: there, `os.replace` is exactly right and
`fmis.archive.atomic.atomic_write` is reused rather than reimplemented.

**A truncated trailing line is reported, never repaired.** A line with no
terminating newline is a write that did not finish. Dropping it would be a silent
repair, and completing it is impossible; the reader raises, and a human decides.
"""

from __future__ import annotations

import os
from pathlib import Path

from fmis.persistence.errors import AppendOnlyViolationError, StoreIOError

__all__ = ["read_lines", "append_lines", "line_count"]


def read_lines(path: Path) -> tuple[str, ...]:
    """Every complete line in `path`, in order. A missing file reads as empty.

    A missing file is emptiness rather than an error because that is what it means
    here: no event of this kind has been written in this calendar year. Every other
    unreadable state — a directory, a permission failure, a truncated tail — is a
    raise.
    """
    if not path.exists():
        return ()
    if not path.is_file():
        raise StoreIOError(f"{path} exists but is not a file")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise StoreIOError(f"could not read {path}: {error}") from error
    if not data:
        return ()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AppendOnlyViolationError(
            f"{path} is not valid UTF-8: {error}"
        ) from error
    if not text.endswith("\n"):
        raise AppendOnlyViolationError(
            f"{path} ends mid-line; the last append did not complete. The "
            "incomplete line is reported rather than dropped — discarding it "
            "would be a silent repair of an append-only file"
        )
    return tuple(line for line in text.split("\n")[:-1])


def line_count(path: Path) -> int:
    return len(read_lines(path))


def append_lines(
    path: Path, lines: tuple[str, ...], *, expected_existing: int | None = None
) -> None:
    """Append complete lines to `path`, creating it if it does not exist.

    `expected_existing` is the number of lines the caller believes are already
    there. Supplying it turns "someone else wrote while I was deciding what to
    write" from an undetectable interleaving into a refusal — which matters
    because the caller decided *what* to append by reading this same file, and an
    append computed against content that has since moved is a corruption the
    hash chain would only notice afterwards.
    """
    if not isinstance(lines, tuple) or not all(isinstance(line, str) for line in lines):
        raise TypeError("lines must be a tuple of str")
    for line in lines:
        if "\n" in line:
            raise AppendOnlyViolationError(
                "a line may not contain a newline; it would split into two records"
            )
    if expected_existing is not None:
        actual = line_count(path)
        if actual != expected_existing:
            raise AppendOnlyViolationError(
                f"{path} holds {actual} line(s); this append was computed against "
                f"{expected_existing}. Another writer appended in between, and "
                "publishing anyway would file a record against a store state that "
                "no longer exists"
            )
    if not lines:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise StoreIOError(
            f"could not create directory {path.parent}: {error}"
        ) from error
    payload = ("".join(f"{line}\n" for line in lines)).encode("utf-8")
    try:
        descriptor = os.open(
            path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644
        )
    except OSError as error:
        raise StoreIOError(f"could not open {path} for append: {error}") from error
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):  # pragma: no cover - short write on a local file
            raise AppendOnlyViolationError(
                f"only {written} of {len(payload)} bytes reached {path}; the file "
                "now ends mid-line and must be repaired by hand"
            )
        os.fsync(descriptor)
    except OSError as error:
        raise StoreIOError(f"could not append to {path}: {error}") from error
    finally:
        os.close(descriptor)
