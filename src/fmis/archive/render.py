"""Plain-text rendering for `archive list`/`archive verify`.

`archive show` renders through the **existing** `render_workspace`/
`render_daily_run` — this module only covers the two views those renderers
were never written for: a compact multi-record index, and a verification
report. No persistence logic lives here; this module only formats values
`fmis.archive.storage` already computed.
"""

from __future__ import annotations

from fmis.archive.manifest import ManifestEntry
from fmis.archive.storage import ArchiveVerification, RecordVerification

__all__ = ["render_manifest", "render_record_verification", "render_archive_verification"]


def render_manifest(entries: tuple[ManifestEntry, ...]) -> str:
    if not entries:
        return "No archived records."
    lines = [f"{len(entries)} archived record(s):", ""]
    for entry in entries:
        subject = ",".join(entry.subject)
        if entry.record_type.value == "workspace":
            state = entry.context_state or "-"
            detail = f"context={state}"
        else:
            detail = (
                f"completed={entry.completed_count}/{entry.requested_count} "
                f"failed={entry.failed_count}"
            )
        lines.append(
            f"{entry.record_id}  {entry.record_type.value:<10} "
            f"as_of={entry.analysis_as_of.isoformat()}  subject={subject}  {detail}"
        )
    return "\n".join(lines)


def render_record_verification(result: RecordVerification) -> str:
    if result.ok:
        return f"{result.record_id}: OK"
    problems = "; ".join(result.problems)
    return f"{result.record_id}: FAILED — {problems}"


def render_archive_verification(result: ArchiveVerification) -> str:
    if result.ok:
        return "Archive OK: no missing files, no orphans, no duplicate entries, no digest mismatches."
    lines = ["Archive verification found problems:"]
    if result.missing_files:
        lines.append(f"  missing files ({len(result.missing_files)}): {', '.join(result.missing_files)}")
    if result.orphan_files:
        lines.append(f"  orphan files ({len(result.orphan_files)}): {', '.join(result.orphan_files)}")
    if result.duplicate_manifest_entries:
        lines.append(
            f"  duplicate manifest entries ({len(result.duplicate_manifest_entries)}): "
            f"{', '.join(result.duplicate_manifest_entries)}"
        )
    if result.digest_mismatches:
        lines.append(
            f"  digest mismatches ({len(result.digest_mismatches)}): {', '.join(result.digest_mismatches)}"
        )
    if result.manifest_mismatches:
        lines.append(
            f"  manifest/record disagreements ({len(result.manifest_mismatches)}): "
            f"{', '.join(result.manifest_mismatches)}"
        )
    return "\n".join(lines)
