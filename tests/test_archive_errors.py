"""The `fmis.archive` error hierarchy: exhaustive and catchable as a group."""

from __future__ import annotations

import pytest

from fmis.archive import errors

_SUBCLASSES = [
    errors.RecordNotFoundError,
    errors.InvalidRecordIdError,
    errors.CorruptRecordError,
    errors.IntegrityError,
    errors.UnsupportedRecordTypeError,
    errors.UnsupportedSchemaVersionError,
    errors.RecordValidationError,
    errors.DuplicateRecordConflictError,
    errors.ManifestError,
    errors.ArchiveIOError,
]


@pytest.mark.parametrize("subclass", _SUBCLASSES)
def test_every_subclass_is_an_archive_error(subclass: type[Exception]) -> None:
    assert issubclass(subclass, errors.ArchiveError)


def test_every_subclass_is_distinct() -> None:
    assert len(set(_SUBCLASSES)) == len(_SUBCLASSES)


def test_archive_error_itself_is_an_exception() -> None:
    assert issubclass(errors.ArchiveError, Exception)


@pytest.mark.parametrize("subclass", _SUBCLASSES)
def test_a_subclass_is_catchable_as_the_group(subclass: type[Exception]) -> None:
    with pytest.raises(errors.ArchiveError):
        raise subclass("boom")


def test_module_exports_exactly_the_hierarchy() -> None:
    assert set(errors.__all__) == {"ArchiveError", *[c.__name__ for c in _SUBCLASSES]}
