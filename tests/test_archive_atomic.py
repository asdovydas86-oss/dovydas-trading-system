"""Direct tests for `fmis.archive.atomic.atomic_write`.

Durability (fsync) and same-filesystem atomicity (temp file placement) have
no observable black-box effect within a single test process on one volume —
a crash-recovery test would need OS-level fault injection, out of scope
here. Both are pinned white-box instead: the call itself, not its OS-level
consequence, following the same technique the codebase already applies to
defensive branches that are otherwise unreachable through the public API.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fmis.archive import atomic as atomic_module
from fmis.archive.atomic import atomic_write


def test_atomic_write_creates_the_file_with_the_exact_bytes(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "record.json"
    atomic_write(target, b"hello world")
    assert target.read_bytes() == b"hello world"


def test_atomic_write_calls_fsync_before_publishing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    real_fsync = atomic_module.os.fsync

    def spying_fsync(fd: int) -> None:
        calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(atomic_module.os, "fsync", spying_fsync)
    atomic_write(tmp_path / "record.json", b"data")
    assert len(calls) == 1


def test_atomic_write_creates_the_temp_file_in_the_destination_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen_dirs: list[Path] = []
    real_mkstemp = atomic_module.tempfile.mkstemp

    def spying_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
        seen_dirs.append(Path(kwargs["dir"]))  # type: ignore[arg-type]
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr(atomic_module.tempfile, "mkstemp", spying_mkstemp)
    destination = tmp_path / "workspace" / "2026" / "08"
    atomic_write(destination / "record.json", b"data")
    assert seen_dirs == [destination]
