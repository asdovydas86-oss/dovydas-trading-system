# ADR-0027 — Memory & Decision Archive persistence schema (closes D-01)

**Status:** Accepted
**Date:** 2026-08-05
**Decides:** what AO persists, in what format, under what identity, with what atomicity and
compatibility guarantees (Milestone AO)
**Implemented by:** *(uncommitted at the time of writing)*
**Relates to:** [ADR-0001](ADR-0001-canonical-utc-timestamps.md) (timestamp canonicalization — this
decision extends it to a new artifact rather than reopening it); [ADR-0007](ADR-0007-application-layer-boundary.md)
(the one-way import-direction rule this package must respect); `reports/0006` §6 (where D-01 was first
raised, as `ARCH` §13.8's open serialization question); `docs/AI_HANDOFF/CURRENT_STATE.md` (the three
prior milestones — AK, AN, and implicitly AI/AL — that each independently hit the same wall: `Workspace`,
`DailyRun`, `MarketRegime` and `StructuralFactSheet` all carry `MappingProxyType` metadata and are
therefore unpicklable with the standard library's own `pickle`)

---

## Context

`Workspace` (AK) and `DailyRun` (AN) are the two composed, schema-versioned, first-class objects the
product already produces on every run — and both are discarded the moment the terminal closes. Both
carry a `metadata: Mapping[str, Any]` field that `__post_init__` wraps in `MappingProxyType`, which has
no `__reduce__` and is not picklable by the standard library without custom support. That property is
what every reviewer who reached this point flagged as D-01, and `FMITS_PRODUCT_BACKLOG.md` records it as
the single decision blocking `AO`.

Four of the project's nine top-level success criteria depend on durable memory (`FMITS_PRODUCT_BACKLOG.md`
§5). `AO`'s product question is *"what did I think about this in October, and was I right?"* — which
requires reading an old record back with full fidelity, not merely writing one.

**What actually needs to round-trip.** `Workspace` and `DailyRun` are **presentation-shaped**, not
domain-shaped (ADR-0026's own finding, re-confirmed here by reading `workspace/sections.py`): every
richer domain object (`EvidenceReport`, `MarketRegime`, `DecisionContext`, …) is flattened into
`Row`/`RowBlock`/`TableBlock`/`NoteBlock` strings during construction and never stored as a typed field.
The actual transitive closure a codec must handle is small: `Workspace → Section|Unavailable →
RowBlock|TableBlock|NoteBlock → Row`, plus `Provenance`, `SectionId`, `SectionStatus`, `Tier`, and a
JSON-safe `metadata` mapping; and `DailyRun → SymbolResult → (Workspace | SymbolFailure)`, plus
`FailureKind`, `ResultCategory`. `SymbolResult.context` is never independently stored — at runtime it is
always `workspace.by_id[SectionId.CONTEXT]`, the identical object already reachable through
`SymbolResult.workspace`, so persisting it a second time would be exactly the duplicated-value pattern
ADR-0016 §4 already rejected for a stored count. It is **re-derived at decode time**, not encoded.

---

## Decision

### 1. Format: explicit UTF-8 JSON record files, hand-written codecs, no reflection

Evaluated against `pickle`, JSON Lines, SQLite, a custom binary format, and Markdown-plus-sidecar (see
Rejected alternatives). **Standalone JSON files**, one per record, win on every criterion that matters
here: human-inspectable without tooling, diffable in `git` if ever vendored, trivially forward-portable
off Python, and requiring no new dependency (the project has **zero runtime dependencies** and stays
that way — `json`, `hashlib`, `tempfile`, `os`, `pathlib`, `datetime` are all this milestone touches).

Every codec is **hand-written and explicit** — `encode_workspace`/`decode_workspace`,
`encode_daily_run`/`decode_daily_run`, and one function per nested type. No `dataclasses.asdict`, no
`__dict__` reflection, no `eval`, no `pickle`. A generic reflective serializer would silently include a
field added to a domain model next milestone before anyone decided whether Memory should carry it; an
explicit codec makes that omission a `TypeError` at the call site instead.

**Canonical encoding.** `json.dumps(obj, sort_keys=True, ensure_ascii=False, allow_nan=False,
separators=(",", ": "), indent=2) + "\n"`, UTF-8. `sort_keys=True` makes the byte output a pure function
of content — the same envelope always serializes identically regardless of the order Python happened to
build the dict in — which is what makes a content digest meaningful and what keeps a `git diff` of a
vendored record readable. `allow_nan=False` makes a `NaN`/`Infinity` value a hard write-time error rather
than an on-disk token later readers must special-case; decode additionally rejects those tokens via
`parse_constant`, so a hand-edited or foreign file cannot smuggle one in either. `indent=2` is a
readability choice with no cost: sorted keys keep it just as deterministic as a compact encoding, and an
owner asking "what did I think in October" is a person who benefits from a file they can open directly.

**Duplicate JSON object keys are rejected on decode**, via `object_pairs_hook`, which the stdlib parser
does not do by default (`json.loads('{"a":1,"a":2}')` silently keeps the last value otherwise) — the
codebase's own "reject rather than repair" ethic (ADR-0005, ADR-0018) applied to the wire format itself.

### 2. Three reproduction guarantees, and AO ships exactly one

| Guarantee | What it means | AO v1 |
|---|---|---|
| **Snapshot reproduction** | `decode(read(path)) == the value that was archived`, structurally, by the model's own `__eq__` | **Guaranteed.** This is the whole of AO v1. |
| **Re-computation** | current code re-fetches live data and recomputes | Not attempted; `archive show` makes zero provider calls, by test |
| **Historical replay** | *historical* code/policy recomputes the same result from archived *raw inputs* | **Not supported, and not claimed.** No candle history is archived — only the already-composed `Workspace`/`DailyRun`. Replay would need every candle each view read, at every timeframe, which nothing measures the cost of yet; claiming it without archiving the inputs it needs would be a promise this milestone cannot keep. |

A record's `payload` is therefore the composed model exactly as built — nothing rendered, nothing
recomputed, nothing summarized further. `Workspace.render_workspace(...)` applied to a decoded record
produces the same text `render_workspace` would have produced at archive time, because rendering is a
pure function of the model and the model round-trips exactly.

### 3. The envelope

One dict, one JSON file, these seven keys and no others:

```json
{
  "record_type": "workspace",
  "schema_version": 1,
  "record_id": "workspace-BTCUSDT-20260805T091500Z-a1b2c3d4",
  "archived_at": "2026-08-05T09:20:03.512481+00:00",
  "analysis_as_of": "2026-08-05T09:15:00+00:00",
  "subject": ["BTCUSDT"],
  "payload": { "...": "the encoded Workspace or DailyRun" },
  "content_digest": "sha256:3f9a…"
}
```

`schema_version` here is the **envelope's own** schema version (`ARCHIVE_SCHEMA_VERSION = 1`), owned by
`fmis.archive` — distinct from `payload.schema_version`, which is `WORKSPACE_SCHEMA_VERSION` /
`DAILY_SCHEMA_VERSION`, owned by `fmis.workspace`/`fmis.daily` and carried through unchanged. Two knobs,
two owners: the envelope can grow a field (say, a compression flag) without either domain package
noticing, and a domain package can change its own payload shape without the archive format itself
changing. `subject` is always a JSON array of the requested symbol(s) — a workspace's is a one-element
array, a daily run's lists every requested symbol in request order — so both record types share one
field rather than the reader needing to know which scalar-vs-list shape today's record type prefers.

`content_digest` is `"sha256:" + hexdigest`, computed over the canonical bytes of exactly
`{record_type, schema_version, analysis_as_of, subject, payload}` — **not** the full envelope. Two fields
are deliberately excluded, for two different reasons: `record_id` is excluded because it is *derived
from* the digest (§4) and including it would make the digest depend on itself; `archived_at` is excluded
because it is a filing timestamp that must not affect whether two archive calls of the *same analysis*
are recognised as duplicates (§6) — a re-archive of unchanged data one day later must produce the
identical digest, not a new one. `content_digest` is therefore a checksum over **what the record says**,
not over the file bytes as a whole; on-disk integrity is checked by recomputing it from the loaded
envelope's own fields (excluding the same two) and comparing, which still detects a flipped byte anywhere
in `payload` or in any of the five covered envelope fields — only a corruption confined to `record_id` or
`archived_at` themselves would need a second, narrower check, which `archive verify` performs separately
(§10) by recomputing `record_id` from the loaded content and comparing it to the stored one.

### 4. Record identity

```
record_id = f"{type_slug}-{subject_slug}-{YYYYMMDDTHHMMSSZ}-{digest[:8]}"
```

`type_slug` is `workspace` or `daily`. `subject_slug` is the symbol with every character outside
`[A-Za-z0-9]` replaced by `_` (`daily` uses `{count}sym`, e.g. `3sym`, since a fifty-symbol universe would
otherwise make the filename itself the bottleneck). The timestamp is `analysis_as_of` converted to UTC
and formatted compactly — the one place this milestone converts a timestamp rather than merely validating
it, done for **display in a filename**, never stored back as the canonical value (the envelope's own
`analysis_as_of` field keeps the original offset). `digest[:8]` is the first 8 hex characters of the full
content digest.

This makes the ID **content-derived**: two archive calls that produce byte-identical envelopes produce
the identical ID, and any change to the content — including one that keeps the same symbol and the same
`analysis_as_of` — changes the ID. The scenario the design brief asks to be defined, *"same identity but
different content"*, is therefore structurally near-impossible rather than merely disallowed: it can only
arise from an 8-hex-character digest-prefix collision (1-in-2^32) between two envelopes that differ
somewhere the prefix didn't cover. §6 below defines what happens in that case rather than assuming it
cannot.

`record_id` is validated on every use — not just at write time — against a strict pattern
(`^(workspace|daily)-[A-Za-z0-9_]{1,24}-\d{8}T\d{6}Z-[0-9a-f]{8}$`) before it is ever joined onto a
filesystem path, and every derived path is asserted to resolve inside the archive root after joining. A
`record_id` typed by a human at the CLI is exactly as untrusted as one read from a corrupted manifest
line, and both go through the identical check.

### 5. Layout, and why `YYYY/MM` is keyed by `analysis_as_of`

```
archive-root/
  manifest.jsonl
  workspace/YYYY/MM/RECORD_ID.json
  daily/YYYY/MM/RECORD_ID.json
```

`YYYY/MM` is taken from `analysis_as_of` (UTC), not `archived_at` — the same instant the record's own ID
already encodes, so a reader who has the ID can compute the path without opening the manifest, and a
directory never disagrees with the filename inside it. Two directories per record type, never one flat
directory, because an owner using this daily is expected to accumulate hundreds of records within a
year and a single directory of thousands of files is a real `ls`/backup/sync cost this design has no
reason to accept for free.

**Default root.** `Path.home() / ".fmits" / "archive"` — computed with the standard library only, no
third-party `platformdirs` dependency, deliberately **outside the git repository** so a checkout can be
deleted without touching stored history. Every test and every CLI invocation may override it with an
explicit `--archive-root` / `root=` parameter; **no test may write to the real default root** — enforced
by a fixture that points every archive test at `tmp_path` and a guard test asserting the string
`Path.home()` appears in exactly one production file.

### 6. Atomicity, duplicates, and conflicts

A record becomes visible to readers in one indivisible step, built in this order:

1. Build and validate the envelope in memory (this already runs every `__post_init__` in the domain
   models, since `decode_workspace`/`decode_daily_run` construct real `Workspace`/`DailyRun` instances).
2. Encode canonical bytes; compute `content_digest` over them.
3. `tempfile.mkstemp(dir=<same directory as the final path>)` — same directory so the final `os.replace`
   is same-filesystem and therefore atomic on every platform this project runs on.
4. Write, `flush()`, `os.fsync(fd)`, close.
5. `os.replace(tmp_path, final_path)` — atomic; a reader either sees no file or the complete file, never a
   partial one, and a crash between steps 3–5 leaves at most an orphaned temp file, never a corrupt
   `RECORD_ID.json`.
6. **Only after step 5 succeeds**, the manifest gains an entry: the current `manifest.jsonl` is read in
   full, the new line appended in memory, and the result is written through the identical
   temp-file-then-`os.replace` sequence — so the manifest, too, either fully reflects the new record or
   is untouched, never half-written. If this step raises, the record file already exists on disk
   correctly but is not yet indexed — an **orphan**, reported by `archive verify`, never silently
   repaired.

**Identical duplicate** (re-archiving byte-identical content): the target path already exists: its digest
is recomputed and compared. Equal → treated as success without rewriting the record file (no unnecessary
fsync), and the manifest gains an entry only if one is missing. This makes `fmits swing BTCUSDT --archive`
run twice in a row against unchanged data idempotent rather than an error.

**Conflicting duplicate** (the near-impossible digest-prefix collision from §4): digest differs while the
`record_id` matches → `DuplicateRecordConflictError`. Never overwritten, never silently suffixed — a
collision this rare is worth surfacing loudly rather than working around invisibly.

**Every other failure category named in the brief** (permission failure, disk failure, interrupted temp
file, malformed JSON, checksum mismatch, unsupported version, missing record, orphan record, stale
manifest entry, duplicate manifest entry, manifest update failure) maps to one of the typed errors in §7,
never a bare `ArchiveError`, and none is auto-repaired — `archive verify` reports, and repair is a human
decision this milestone does not make for them.

### 7. Typed errors

```
ArchiveError                              (base — catch as a group)
├── RecordNotFoundError
├── InvalidRecordIdError                  (malformed id, path-traversal attempt)
├── CorruptRecordError                    (malformed/truncated/duplicate-keyed JSON)
├── IntegrityError                        (content_digest mismatch)
├── UnsupportedRecordTypeError
├── UnsupportedSchemaVersionError
├── RecordValidationError                 (payload decodes but the domain model rejects it)
├── DuplicateRecordConflictError
├── ManifestError                         (inconsistency or update failure)
└── ArchiveIOError                        (filesystem/permission failure; wraps OSError)
```

### 8. Compatibility policy: exact match, no migration, in v1

`schema_version` (envelope) and `payload.schema_version` (domain) are each checked against an explicit
supported set (`{1}` today). Anything else — newer or older — is `UnsupportedSchemaVersionError` naming
both the version found and the versions supported. **No migration path exists yet.** This is a stated
limitation, not an oversight: a version bump before this milestone ships a reader for it would be
speculative code with nothing to test it against, and CLAUDE.md's "deterministic first" principle argues
against guessing at a future shape now.

### 9. Metadata is JSON-safe and tuple-normalized, never arbitrary

`Workspace.metadata` / `DailyRun.metadata` are typed `Mapping[str, Any]`. The codec accepts exactly:
`str`, `bool`, non-`bool` `int`, finite `float`, `None`, a `tuple` of the same (recursively), and a
`Mapping[str, ...]` of the same — and **rejects `list`**, because every metadata sequence value observed
in the repository today (`Workspace.metadata["intervals"]`, `DailyRun.metadata["intervals"]`) is already
a `tuple`, matching the "tuples, never lists" convention `frozen=True, slots=True` types use everywhere
else in `fmis`. JSON has no tuple/list distinction, so decode reconstructs every JSON array as a `tuple`;
accepting a `list` on encode would make `decode(encode(x)) == x` false for that value's type, silently.
Anything else — a live callable, a domain object, a byte string — raises `RecordValidationError` at
encode time, before a single byte is written.

### 10. Manifest is metadata-only

Every manifest line carries the seven envelope fields the reader needs *without opening the record*:
`record_id`, `record_type`, `schema_version`, `archived_at`, `analysis_as_of`, `subject`,
`relative_path`, `content_digest`, plus one record-type-specific summary field — `context_state` for a
workspace, `completed_count`/`failed_count`/`requested_count` for a daily run — never the payload.
`archive list` parses only this file; it is never proportional to the size of what has been archived, only
to the count.

---

## Rejected alternatives

| Alternative | Why rejected |
|---|---|
| **`pickle`** | The exact hazard D-01 exists to close: opaque, Python-version-coupled, and — the sharper reason — `pickle.loads` on an untrusted file is arbitrary code execution; a personal archive one might eventually sync or back up off-machine is not a place to plant that |
| **SQLite** | A real, safe, stdlib-available option — rejected on proportionality, not safety: v1 has no query need beyond "list metadata" and "load by id", both served by a flat file and a JSONL index; a database schema migration is a second migration problem layered on top of the envelope's own, for no capability AO v1 uses |
| **JSON Lines as the *record* store** (one giant file, one record per line) | Makes "load record by id" a linear scan instead of a filesystem lookup, and makes "delete/replace a record" (needed the moment retention or correction is ever discussed) a full-file rewrite instead of one file — the per-record-file design keeps both operations local |
| **Custom binary format** | No inspectability, no diffability, and buys nothing over JSON at this owner's data volume (single-digit KB per record, hundreds of records) |
| **Markdown + structured JSON sidecar** | Two files per record double the atomicity surface (now both must appear together) for a human-readability gain JSON-with-`indent=2` already delivers |
| **A single mutable manifest.json object, rewritten wholesale** | Same atomicity story as the chosen line-file, more code for no benefit — kept the JSONL *shape* for readability (`grep`/`jq -s` friendly) while still writing it via a whole-file atomic replace, not a raw unguarded append |
| **Compression (`gzip`) by default** | No measurement yet shows it is needed (§ Performance measurements, filed with the implementation); adding it later is compatible, removing it after owners depend on it is not |
| **Historical-replay guarantee in v1** | Requires archiving every candle every view read; unmeasured cost, unbuilt capability — claiming it dishonestly is worse than not having it |
| **Reflective serialization (`dataclasses.asdict` + generic reconstruction)** | Silently includes a field the next milestone adds before anyone decided Memory should carry it; explicit codecs make that decision visible as a `TypeError` |

---

## Consequences

**AO can now be implemented.** Every metadata-carrying model the repository has shipped so far
(`Workspace`, `DailyRun`) has an explicit path to durable storage; `MarketRegime` and
`StructuralFactSheet` are not persisted by AO directly (they are not reachable as typed fields from either
root — see Context) but the same JSON-envelope pattern applies unchanged whenever a future milestone
decides to archive them directly.

**No migration exists yet**, and any schema change to `Workspace`, `DailyRun`, or the envelope itself
before a migration path is designed makes every record archived under the old version unreadable by name
— rejected cleanly, with a clear error, never silently misread, but not recoverable without a future
milestone.

**No historical replay.** An owner can prove *what the system said*, exactly, forever. They cannot yet
ask *what the system would say now, given what it knew then* — that needs raw inputs this version does
not store, and is explicitly out of scope rather than quietly implied.
