"""`ArchiveStore` — the one entry point that writes, reads and verifies records.

ADR-0027 §5–§6. This is the only module that touches `pathlib`/`tempfile`/
`os.replace` directly (through `fmis.archive.atomic`); everything upstream of
it (codec, envelope, identity, manifest) is pure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePath

from fmis.archive.atomic import atomic_write
from fmis.archive.codec import decode_daily_run, decode_workspace, encode_daily_run, encode_workspace
from fmis.archive.envelope import (
    ArchiveEnvelope,
    ARCHIVE_SCHEMA_VERSION,
    RecordType,
    compute_content_digest,
    decode_envelope,
    encode_envelope,
    envelope_content_digest,
)
from fmis.archive.errors import (
    ArchiveError,
    DuplicateRecordConflictError,
    IntegrityError,
    InvalidRecordIdError,
    ManifestError,
    RecordNotFoundError,
)
from fmis.archive.identity import build_record_id, parse_record_id
from fmis.archive.json_safe import canonical_loads
from fmis.archive.manifest import ManifestEntry, append_manifest_entry, read_manifest
from fmis.daily.models import DailyRun
from fmis.workspace.models import Workspace

__all__ = [
    "DEFAULT_ARCHIVE_ROOT",
    "ArchivedRecord",
    "RecordVerification",
    "ArchiveVerification",
    "ArchiveStore",
    "default_archive_root",
]

#: The user-level default, computed with the standard library only and
#: deliberately outside the git repository (ADR-0027 §5). Every test and every
#: CLI invocation may override it with an explicit root; no test may write here.
DEFAULT_ARCHIVE_ROOT = Path.home() / ".fmits" / "archive"


def default_archive_root() -> Path:
    return DEFAULT_ARCHIVE_ROOT


_TYPE_DIR = {RecordType.WORKSPACE: "workspace", RecordType.DAILY_RUN: "daily"}
_TYPE_SLUG = {RecordType.WORKSPACE: "workspace", RecordType.DAILY_RUN: "daily"}


def _id_subject(record_type: RecordType, subject: tuple[str, ...]) -> str:
    """The `subject` argument `build_record_id` slugifies into the id.

    One function so write time (`_archive`) and read time (`_load_envelope`,
    which recomputes the id to detect a tampered `record_id` field) can never
    drift apart on this derivation.
    """
    return subject[0] if record_type is RecordType.WORKSPACE else f"{len(subject)}sym"


@dataclass(frozen=True, slots=True)
class ArchivedRecord:
    """What a successful `archive_workspace`/`archive_daily_run` call returns."""

    record_id: str
    relative_path: str
    content_digest: str
    created: bool  # False when an identical duplicate already existed


@dataclass(frozen=True, slots=True)
class RecordVerification:
    """The result of verifying one record."""

    record_id: str
    ok: bool
    problems: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ArchiveVerification:
    """The result of sweeping the whole archive (§ ADR-0027 §6, §10)."""

    ok: bool
    missing_files: tuple[str, ...] = ()
    orphan_files: tuple[str, ...] = ()
    duplicate_manifest_entries: tuple[str, ...] = ()
    digest_mismatches: tuple[str, ...] = ()
    #: A manifest entry whose *non-digest* metadata (subject, analysis_as_of,
    #: context_state, requested/completed/failed counts, ...) disagrees with
    #: the record it describes. `content_digest` matching proves the record
    #: file is intact; it does not prove the manifest's own summary of that
    #: file is still accurate — a manifest line can be hand-edited without
    #: touching the record at all. Checked independently.
    manifest_mismatches: tuple[str, ...] = ()


def _relative_path(record_type: RecordType, record_id: str, analysis_as_of: datetime) -> str:
    utc = analysis_as_of.astimezone(timezone.utc)
    return f"{_TYPE_DIR[record_type]}/{utc.year:04d}/{utc.month:02d}/{record_id}.json"


class ArchiveStore:
    """One archive rooted at `root`. `root` is always explicit — callers pass
    it, this class never falls back to `default_archive_root()` on its own,
    so a test or a CLI invocation can never accidentally reach the owner's
    real archive by omission."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def _resolve_within_root(self, relative_path: str) -> Path:
        """Defense in depth: `record_id` is already validated against a
        traversal-free pattern (ADR-0027 §4), but every path this class
        constructs is still asserted to resolve inside `root` before use.

        An absolute `relative_path` is rejected explicitly and first: `Path`'s
        own `/` operator silently discards the left operand when the right is
        absolute (``Path("/root") / "/etc/passwd" == Path("/etc/passwd")``),
        so the containment check below would otherwise be the only thing
        standing between an absolute manifest entry and an arbitrary read —
        correct today, but incidental to how it happens to be written rather
        than an explicit guard.
        """
        if PurePath(relative_path).is_absolute():
            raise InvalidRecordIdError(f"path {relative_path!r} must be relative to the archive root")
        root = self._root.resolve()
        candidate = (self._root / relative_path).resolve()
        if candidate != root and root not in candidate.parents:
            raise InvalidRecordIdError(f"path {relative_path!r} escapes the archive root")
        return self._root / relative_path

    # ------------------------------------------------------------------ #
    # Writing
    # ------------------------------------------------------------------ #

    def archive_workspace(self, workspace: Workspace, *, archived_at: datetime | None = None) -> ArchivedRecord:
        payload = encode_workspace(workspace)
        # `fmis.daily.runner` already reads the decision-context state back out
        # of `workspace.metadata["context_state"]` rather than parsing the
        # context section's rendered prose; the manifest follows the same path.
        context_state_raw = workspace.metadata.get("context_state")
        context_state = context_state_raw if isinstance(context_state_raw, str) else None
        return self._archive(
            record_type=RecordType.WORKSPACE,
            payload=payload,
            subject=(workspace.symbol,),
            analysis_as_of=workspace.as_of,
            archived_at=archived_at,
            context_state=context_state,
            requested_count=None,
            completed_count=None,
            failed_count=None,
        )

    def archive_daily_run(self, daily_run: DailyRun, *, archived_at: datetime | None = None) -> ArchivedRecord:
        payload = encode_daily_run(daily_run)
        return self._archive(
            record_type=RecordType.DAILY_RUN,
            payload=payload,
            subject=daily_run.requested_symbols,
            analysis_as_of=daily_run.reference_time,
            archived_at=archived_at,
            context_state=None,
            requested_count=daily_run.requested_count,
            completed_count=daily_run.completed_count,
            failed_count=daily_run.failed_count,
        )

    def _archive(
        self,
        *,
        record_type: RecordType,
        payload: dict,
        subject: tuple[str, ...],
        analysis_as_of: datetime,
        archived_at: datetime | None,
        context_state: str | None,
        requested_count: int | None,
        completed_count: int | None,
        failed_count: int | None,
    ) -> ArchivedRecord:
        digest = compute_content_digest(
            record_type=record_type,
            schema_version=ARCHIVE_SCHEMA_VERSION,
            analysis_as_of=analysis_as_of,
            subject=subject,
            payload=payload,
        )
        record_id = build_record_id(
            type_slug=_TYPE_SLUG[record_type],
            subject=_id_subject(record_type, subject),
            analysis_as_of=analysis_as_of,
            digest=digest,
        )
        relative_path = _relative_path(record_type, record_id, analysis_as_of)
        final_path = self._resolve_within_root(relative_path)

        if final_path.is_file():
            existing_digest = self._existing_digest(final_path)
            if existing_digest == digest:
                self._ensure_manifest_entry(
                    record_id=record_id,
                    record_type=record_type,
                    analysis_as_of=analysis_as_of,
                    archived_at=archived_at or datetime.now(timezone.utc),
                    subject=subject,
                    relative_path=relative_path,
                    digest=digest,
                    context_state=context_state,
                    requested_count=requested_count,
                    completed_count=completed_count,
                    failed_count=failed_count,
                )
                return ArchivedRecord(
                    record_id=record_id, relative_path=relative_path, content_digest=digest, created=False
                )
            raise DuplicateRecordConflictError(
                f"record_id {record_id!r} already exists with a different content_digest "
                f"({existing_digest} != {digest}) — an 8-hex-character digest-prefix collision"
            )

        envelope = ArchiveEnvelope(
            record_type=record_type,
            schema_version=ARCHIVE_SCHEMA_VERSION,
            record_id=record_id,
            archived_at=archived_at or datetime.now(timezone.utc),
            analysis_as_of=analysis_as_of,
            subject=subject,
            payload=payload,
            content_digest=digest,
        )
        atomic_write(final_path, encode_envelope(envelope))
        append_manifest_entry(
            self._root,
            ManifestEntry(
                record_id=record_id,
                record_type=record_type,
                schema_version=ARCHIVE_SCHEMA_VERSION,
                archived_at=envelope.archived_at,
                analysis_as_of=analysis_as_of,
                subject=subject,
                relative_path=relative_path,
                content_digest=digest,
                context_state=context_state,
                requested_count=requested_count,
                completed_count=completed_count,
                failed_count=failed_count,
            ),
        )
        return ArchivedRecord(record_id=record_id, relative_path=relative_path, content_digest=digest, created=True)

    def _existing_digest(self, path: Path) -> str | None:
        try:
            envelope = decode_envelope(canonical_loads(path.read_bytes()))
        except Exception:  # noqa: BLE001 — any decode failure means "not a clean duplicate"
            return None
        return envelope.content_digest

    def _ensure_manifest_entry(
        self,
        *,
        record_id: str,
        record_type: RecordType,
        analysis_as_of: datetime,
        archived_at: datetime,
        subject: tuple[str, ...],
        relative_path: str,
        digest: str,
        context_state: str | None,
        requested_count: int | None,
        completed_count: int | None,
        failed_count: int | None,
    ) -> None:
        existing = read_manifest(self._root)
        if any(entry.record_id == record_id for entry in existing):
            return
        append_manifest_entry(
            self._root,
            ManifestEntry(
                record_id=record_id,
                record_type=record_type,
                schema_version=ARCHIVE_SCHEMA_VERSION,
                archived_at=archived_at,
                analysis_as_of=analysis_as_of,
                subject=subject,
                relative_path=relative_path,
                content_digest=digest,
                context_state=context_state,
                requested_count=requested_count,
                completed_count=completed_count,
                failed_count=failed_count,
            ),
        )

    # ------------------------------------------------------------------ #
    # Reading
    # ------------------------------------------------------------------ #

    def _path_for(self, record_id: str) -> Path:
        # Validated first — a record ID typed at the CLI is exactly as
        # untrusted as one read from a corrupted manifest line (ADR-0027 §4).
        parse_record_id(record_id)
        # The path always comes from the manifest, never a filesystem glob —
        # a glob would defeat the point of the manifest existing at all, and
        # would let an unindexed (orphan) file be loaded as if it were archived.
        for entry in read_manifest(self._root):
            if entry.record_id == record_id:
                return self._resolve_within_root(entry.relative_path)
        raise RecordNotFoundError(f"no manifest entry for {record_id!r}") from None

    def _load_envelope(self, record_id: str) -> ArchiveEnvelope:
        path = self._path_for(record_id)
        if not path.is_file():
            raise RecordNotFoundError(f"record file for {record_id!r} does not exist at {path}")
        envelope = decode_envelope(canonical_loads(path.read_bytes()))
        if envelope.record_id != record_id:
            raise IntegrityError(
                f"record file for {record_id!r} contains a different record_id {envelope.record_id!r}"
            )
        recomputed_digest = envelope_content_digest(envelope)
        if recomputed_digest != envelope.content_digest:
            raise IntegrityError(
                f"content_digest mismatch for {record_id!r}: stored {envelope.content_digest}, "
                f"recomputed {recomputed_digest}"
            )
        # The digest check alone does not prove `record_id` itself was never
        # tampered with in a way that still passes RECORD_ID_PATTERN — e.g. a
        # different (but validly-shaped) digest prefix substituted in place
        # of the real one. Recomputing the id from the now digest-verified
        # content closes that gap.
        recomputed_id = build_record_id(
            type_slug=_TYPE_SLUG[envelope.record_type],
            subject=_id_subject(envelope.record_type, envelope.subject),
            analysis_as_of=envelope.analysis_as_of,
            digest=envelope.content_digest,
        )
        if recomputed_id != record_id:
            raise IntegrityError(
                f"record_id {record_id!r} does not match the id its own content implies "
                f"({recomputed_id!r}) — record_id itself has been tampered with"
            )
        return envelope

    def load(self, record_id: str) -> Workspace | DailyRun:
        """Load and reconstruct one record. No network access is ever made."""
        envelope = self._load_envelope(record_id)
        if envelope.record_type is RecordType.WORKSPACE:
            return decode_workspace(envelope.payload)
        return decode_daily_run(envelope.payload)

    def list(self) -> tuple[ManifestEntry, ...]:
        """Every manifest entry, metadata-only — no payload is ever read here."""
        return read_manifest(self._root)

    # ------------------------------------------------------------------ #
    # Verification
    # ------------------------------------------------------------------ #

    def verify_record(self, record_id: str) -> RecordVerification:
        """Report every defined problem category as a result, never a raise.

        Covers not-found, corrupt JSON, integrity mismatch, unsupported
        type/version, model-validation failure and an invalid ID — every
        `ArchiveError` this package defines names a *known* problem here.
        """
        try:
            self.load(record_id)
        except ArchiveError as error:
            return RecordVerification(
                record_id=record_id, ok=False, problems=(f"{type(error).__name__}: {error}",)
            )
        return RecordVerification(record_id=record_id, ok=True)

    def verify_archive(self) -> ArchiveVerification:
        try:
            entries = read_manifest(self._root)
        except ManifestError as error:
            return ArchiveVerification(ok=False, missing_files=(str(error),))

        missing: list[str] = []
        digest_mismatches: list[str] = []
        manifest_mismatches: list[str] = []
        seen_ids: set[str] = set()
        duplicates: list[str] = []
        known_paths: set[Path] = set()

        for entry in entries:
            if entry.record_id in seen_ids:
                duplicates.append(entry.record_id)
            seen_ids.add(entry.record_id)
            try:
                path = self._resolve_within_root(entry.relative_path)
            except InvalidRecordIdError:
                # A manifest entry naming a path outside the archive root is
                # never followed — treated as a missing record, not read.
                missing.append(entry.record_id)
                continue
            if not path.is_file():
                missing.append(entry.record_id)
                continue
            known_paths.add(path.resolve())
            try:
                envelope = decode_envelope(canonical_loads(path.read_bytes()))
                recomputed = envelope_content_digest(envelope)
                if recomputed != envelope.content_digest or envelope.content_digest != entry.content_digest:
                    digest_mismatches.append(entry.record_id)
                    continue
                if not self._manifest_entry_agrees_with_record(entry, envelope):
                    manifest_mismatches.append(entry.record_id)
            except Exception:  # noqa: BLE001 — any decode failure is a digest-class problem
                digest_mismatches.append(entry.record_id)

        orphans: list[str] = []
        for type_dir in _TYPE_DIR.values():
            base = self._root / type_dir
            if not base.is_dir():
                continue
            for candidate in base.rglob("*.json"):
                if candidate.resolve() not in known_paths:
                    orphans.append(str(candidate.relative_to(self._root)))

        ok = not (missing or orphans or duplicates or digest_mismatches or manifest_mismatches)
        return ArchiveVerification(
            ok=ok,
            missing_files=tuple(missing),
            orphan_files=tuple(sorted(orphans)),
            duplicate_manifest_entries=tuple(duplicates),
            digest_mismatches=tuple(digest_mismatches),
            manifest_mismatches=tuple(manifest_mismatches),
        )

    def _manifest_entry_agrees_with_record(self, entry: ManifestEntry, envelope: ArchiveEnvelope) -> bool:
        """Whether a manifest entry's own fields still describe this record.

        A matching `content_digest` proves the *record file* is intact; it
        says nothing about whether the manifest's separately-stored summary
        of that file (subject, timestamps, decision-context state, daily
        counts) was ever hand-edited or has drifted. Checked independently
        because `archive list` trusts exactly these fields without opening
        the record (design doc §3, "list never reads a payload").
        """
        if (
            entry.record_type is not envelope.record_type
            or entry.schema_version != envelope.schema_version
            or entry.analysis_as_of != envelope.analysis_as_of
            or entry.subject != envelope.subject
        ):
            return False
        if envelope.record_type is RecordType.WORKSPACE:
            workspace = decode_workspace(envelope.payload)
            context_state_raw = workspace.metadata.get("context_state")
            expected_context_state = context_state_raw if isinstance(context_state_raw, str) else None
            return entry.context_state == expected_context_state
        daily_run = decode_daily_run(envelope.payload)
        return (
            entry.requested_count == daily_run.requested_count
            and entry.completed_count == daily_run.completed_count
            and entry.failed_count == daily_run.failed_count
        )
