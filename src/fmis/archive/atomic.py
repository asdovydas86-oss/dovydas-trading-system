"""The one atomic-publish primitive every write in this package goes through.

ADR-0027 §6: build bytes fully in memory, write them to a temp file in the
*same* directory as the final path (so the final step is a same-filesystem
rename), flush, fsync, then `os.replace` — atomic on every platform this
project runs on. A reader either sees no file or the complete file, never a
partial one.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fmis.archive.errors import ArchiveIOError

__all__ = ["atomic_write"]


def atomic_write(path: Path, data: bytes) -> None:
    directory = path.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ArchiveIOError(f"could not create directory {directory}: {error}") from error

    try:
        fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=f".{path.name}.", suffix=".tmp")
    except OSError as error:
        raise ArchiveIOError(f"could not create a temporary file in {directory}: {error}") from error

    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except OSError as error:
        tmp_path.unlink(missing_ok=True)
        raise ArchiveIOError(f"could not publish {path}: {error}") from error
