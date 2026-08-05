# Memory & Decision Archive v1 — Design

**Milestone:** AO
**Contracts:** [ADR-0027](../adr/ADR-0027-memory-and-decision-archive-persistence-schema.md) (resolves
D-01 — read it first; this document covers architecture and test strategy, not the persistence schema
itself, which the ADR already states in full)
**Status:** Implemented

---

## 1. The problem, measured

Every capability the product has shipped through Milestone AN computes an analysis and prints it. Nothing
records it. `Workspace` (AK) and `DailyRun` (AN) are both frozen, schema-versioned, first-class objects —
not print statements — specifically so a future consumer could read them without re-deriving anything.
`AO` is the first consumer to actually exist.

`FMITS_PRODUCT_BACKLOG.md` names the product question directly: *"what did I think about this in October,
and was I right?"* Before this milestone that question has no answer — a terminal that closed took the
only copy of the analysis with it.

## 2. Scope

**In scope.** Archiving a `Workspace` or a `DailyRun` to a durable, versioned, integrity-checked record;
listing archived records without reading full payloads; loading and rendering one record by its stable
ID with no network access; detecting corruption and unsupported schema versions; a CLI surface
(`archive` subcommands, `--archive` on `swing`/`daily`).

**Out of scope**, and deliberately absent from every model and every CLI flag this milestone adds:
discretionary notes, thesis text, trade entry/exit/stop/target/size, P&L, outcomes, tags, AI summaries,
strategy scoring, scheduling, delivery transports, cloud sync, encryption, automatic retention/deletion,
opportunity ranking, and any form of historical replay (ADR-0027 §2 states exactly what reproduction
guarantee AO does and does not make). None of these is a persistence question; each is its own future
milestone with its own acceptance criteria, and folding any of them in here would make this milestone's
review unable to tell a persistence defect from a product-scope disagreement.

## 3. Architecture

### 3.1 Where `fmis.archive` sits

```
fmis.workspace, fmis.daily  →  fmis.archive
```

One-way, in the same shape ADR-0007 §1 already established for `fmis.pipeline` over the engines: §3.5
below adds the identical import-direction guard, generalized to name `fmis.archive` instead of
`fmis.pipeline` and to add `workspace`/`daily` to the forbidden-importer set. `fmis.archive` consumes the
finished, validated `Workspace`/`DailyRun` objects `fmis.workspace`/`fmis.daily` already produce; it
computes nothing about the market and adds no calculation — its only job is turning an already-valid
object into durable bytes and back into an equal object.

**One necessary exception, stated precisely rather than papered over.** `pipeline/cli.py` already
imports `fmis.workspace` and `fmis.daily` directly — the CLI is the outermost edge, and it is where
`archive`'s CLI surface (§3.6) has to live, per the milestone brief's instruction to integrate into the
*existing* CLI registry rather than build a second one. So `cli.py` — and only `cli.py` — is permitted to
import `fmis.archive`; every *other* module in `fmis.pipeline` (`market_analysis.py`,
`structural_facts.py`, `multi_timeframe.py`, `regime.py`, `render.py`) is scanned exactly like every
other forbidden importer below. The guard test therefore excludes one named file from the package it
scans, rather than exempting the whole package — precise enough that a second pipeline module reaching
for `fmis.archive` still fails the guard.

### 3.2 Package layout

```
src/fmis/archive/
  __init__.py     public exports
  errors.py       the ArchiveError hierarchy (ADR-0027 §7)
  json_safe.py    the JSON-safe primitive/datetime/metadata codec shared by every model codec
  identity.py     record_id construction + validation, content digest
  codec.py        encode_workspace/decode_workspace, encode_daily_run/decode_daily_run,
                  and one function per nested type (Section, Unavailable, Row*, Provenance, ...)
  envelope.py     ArchiveEnvelope, ARCHIVE_SCHEMA_VERSION, envelope encode/decode
  manifest.py     ManifestEntry, atomic manifest read/append/rewrite
  storage.py      ArchiveStore — archive_workspace/archive_daily_run/load/list/verify, atomic write
```

Splitting the codec from the storage layer follows the same reasoning `workspace/render.py` follows for
keeping rendering out of `builder.py`: a codec has no filesystem opinions and a test exercising
`decode(encode(x)) == x` needs none. `storage.py` is the only module that touches `pathlib`/`tempfile`/
`os.replace`.

### 3.3 What actually gets encoded

`Workspace` and `DailyRun` are **presentation-shaped**: every richer domain object
(`EvidenceReport`, `MarketRegime`, `DecisionContext`, …) is already flattened into
`Row`/`RowBlock`/`TableBlock`/`NoteBlock` strings before it reaches either root (confirmed by reading
`workspace/sections.py`, which is where that flattening happens — nothing downstream of it holds a typed
reference to any of those richer objects). The transitive closure a codec must handle is therefore:

```
Workspace
├── sections: tuple[Section | Unavailable, ...]
│   ├── Section: id, title, status, summary, body, caveats, provenance, reason
│   │   └── body: tuple[RowBlock | TableBlock | NoteBlock, ...]
│   │       ├── RowBlock: heading, rows: tuple[Row, ...]
│   │       │   └── Row: label, value, note, tier
│   │       ├── TableBlock: heading, columns, records
│   │       └── NoteBlock: notes
│   └── Unavailable: id, title, owner, reason, prohibition
├── Provenance: engine, policy_id, as_of
└── metadata: Mapping[str, JSON-safe]

DailyRun
├── results: tuple[SymbolResult, ...]
│   └── SymbolResult: requested_symbol, category, resolved_symbol, workspace (→ Workspace | None),
│       failure (→ SymbolFailure | None), regime_summary, duration_seconds
│       (context is NOT encoded — see 3.4)
└── metadata: Mapping[str, JSON-safe]
```

`Block = RowBlock | TableBlock | NoteBlock` and `WorkspaceSection = Section | Unavailable` are closed
unions with no stored discriminant field on the domain model, so the codec adds its own `"kind"` tag on
encode and dispatches on it on decode — the model itself is untouched.

### 3.4 `SymbolResult.context` is derived, never stored twice

At runtime `SymbolResult.context` is literally `workspace.by_id[SectionId.CONTEXT]` — the same object
already reachable through `SymbolResult.workspace.sections`, confirmed by reading `daily/runner.py`.
Encoding it a second time would be the exact duplicated-value pattern ADR-0016 §4 rejected for a stored
count. `decode_symbol_result` reconstructs it as `workspace.by_id[SectionId.CONTEXT]` after decoding
`workspace`, so `decode(encode(x)) == x` still holds by structural equality (frozen dataclasses compare by
field value, not identity) while nothing is written twice.

### 3.5 Import-direction guard

`tests/test_archive_boundary.py` mirrors `test_pipeline_market_analysis.py`'s
`test_no_engine_imports_the_application_layer` exactly: a literal-substring scan of every package that
must never depend on `fmis.archive` — the existing `ENGINE_PACKAGES`, plus every engine `fmis.workspace`/
`fmis.daily` themselves sit above (`decision_context`, `market_regime`, `decision_support`, `evidence`,
`structural_trend`, `level_crossing`, `structure_break`, `change_of_character`, `market_structure`,
`trading_context`, `series_context`, `relative_value`), plus `workspace` and `daily` themselves, plus
`pipeline` (the archive composition happens *beside* `fmis.pipeline.cli`, consuming its outputs, never the
reverse). A companion guard asserts every scanned package directory still exists, so a rename cannot
silently make the scan vacuous — the same second-order guard `test_engine_packages_scanned_actually_exist`
already established the pattern for.

### 3.6 CLI integration

Following `pipeline/cli.py`'s existing `Command` registry exactly (`name`, `help`, `description`,
`configure`, `run`), three new commands are appended to `COMMANDS`:

```
fmits archive list  [--archive-root PATH]
fmits archive show    RECORD_ID [--archive-root PATH]
fmits archive verify  RECORD_ID [--archive-root PATH]   # or no ID: verify the whole archive
```

and `--archive [--archive-root PATH]` is added to `_configure_swing`/`_configure_daily`, read inside
`_run_swing`/`_run_daily_command` to call `ArchiveStore(...).archive_workspace(...)`/
`archive_daily_run(...)` **after** the existing render call succeeds — an archive failure is reported
distinctly from an analysis failure (a symbol that analysed correctly but could not be *written* is not
the same fact as a symbol whose analysis failed, and the exit code and message name which one happened).
No persistence logic lives inside a CLI handler body beyond this one call into `fmis.archive`'s public
API, matching the brief's "avoid persistence logic inside individual CLI handlers" requirement.

`archive show` calls `ArchiveStore.load(...)` and the **existing** `render_workspace`/`render_daily_run`
— no new renderer, no provider call, asserted by a test that patches every network-capable name in
`fmis.providers.binance` to raise if touched during `archive show`.

## 4. Invariants, each test-enforced

1. `decode_workspace(encode_workspace(w)) == w` for every fixture, including a workspace whose sections
   are all `Unavailable`, all `Section`, and a mix.
2. `decode_daily_run(encode_daily_run(r)) == r`, including a run with only failures, only successes, and
   a mix, and including `Unicode` in every free-text field.
3. A successful `archive_workspace`/`archive_daily_run` call is atomic: no partial `RECORD_ID.json` is
   ever observable, tested by killing the write mid-flight (mocking `os.replace` to raise after the temp
   file is fully written) and asserting the final path still does not exist.
4. `content_digest` changes if and only if the envelope's content changes; recomputing it over a byte-flip
   anywhere in the file is detected by `archive verify`.
5. Two `archive_workspace` calls with byte-identical input are idempotent: same `record_id`, one file, no
   second write (asserted via a write-count spy).
6. `record_id` accepted by `archive show`/`archive verify` is validated against the exact pattern before
   any path is constructed; every character outside `[A-Za-z0-9._-]`, and every `..` segment, is rejected
   before the filesystem is touched.
7. `archive list` never opens a record's `payload` — asserted by making every record file's `payload` key
   an unparsable sentinel the manifest never reads and confirming `archive list` still succeeds.
8. `fmis.archive` is never imported by any of `ENGINE_PACKAGES ∪ {workspace, daily, pipeline, ...}` (§3.5).
9. No new runtime dependency: `fmis.archive` imports only the standard library and `fmis.workspace`/
   `fmis.daily`'s own public names.
10. `archive show` performs no network call, asserted by patching `fmis.providers.binance`'s transport.
11. A schema version outside `{ARCHIVE_SCHEMA_VERSION}` (envelope) or outside the supported payload set is
    rejected with `UnsupportedSchemaVersionError` naming both the version found and what is supported —
    never silently accepted, never silently coerced.
12. `fmits swing SYMBOL --archive` followed by `fmits archive show RECORD_ID` reproduces byte-identical
    rendered text to the original `fmits swing SYMBOL` run, live-tested against one real Binance fetch.

## 5. Test strategy

Standard for this repository: **100 % line coverage plus mutation testing with zero unexplained
survivors**, byte-identical source restoration verified by SHA-256 before/after each mutation probe,
bytecode purged before every probe run (the defect Milestone AG's review found in the harness itself).
Test files, one per concern rather than one giant file, mirroring the existing per-package convention:

- `tests/test_archive_errors.py` — the error hierarchy is exhaustive and each subclass is distinct
- `tests/test_archive_json_safe.py` — the metadata codec: every accepted primitive, every rejected shape
  (`list`, `bytes`, `NaN`, a live object), nested tuples and mappings
- `tests/test_archive_identity.py` — `record_id` construction, validation regex, digest determinism,
  path-traversal rejection, filesystem-safety of every generated ID
- `tests/test_archive_codec.py` — round-trip for every nested type, schema/type/enum rejection, Unicode,
  naive-timestamp rejection, duplicate-JSON-key rejection, unknown-field rejection
- `tests/test_archive_storage.py` — atomicity, duplicate/conflict handling, verify's failure taxonomy,
  manifest behavior, archive-root creation
- `tests/test_archive_boundary.py` — the import-direction guard (§3.5)
- `tests/test_pipeline_cli.py` — new file; CLI commands, exit codes, `--archive-root`, no-network
  assertion for `archive show`

## 6. What it does not claim

No historical replay (ADR-0027 §2). No schema migration (ADR-0027 §8) — a version bump before a migration
path exists makes old records cleanly unreadable, not silently misread. No concurrent-writer safety beyond
what atomic single-process writes provide; a second `fmits` process archiving at the same instant is not
this version's concern, documented as a limitation rather than guarded against. No retention or deletion
policy — nothing in this milestone ever removes a record, by design (`CLAUDE.md`'s prohibition on adding
scope beyond what a milestone's task requires).

## 7. Open decisions

None remaining for v1. A schema-migration design and a concurrent-writer story are both plausible next
steps once the archive has real records in it and a real second consumer (journaling, comparisons) that
needs either.
