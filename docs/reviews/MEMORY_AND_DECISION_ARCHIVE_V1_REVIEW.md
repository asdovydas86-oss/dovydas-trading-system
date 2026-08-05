# Memory & Decision Archive v1 — Independent Review

**Milestone:** AO
**Audited commit:** uncommitted at the time of writing (working tree at review time)
**Contracts:** [ADR-0027](../adr/ADR-0027-memory-and-decision-archive-persistence-schema.md); design in
[MEMORY_AND_DECISION_ARCHIVE_V1.md](../design/MEMORY_AND_DECISION_ARCHIVE_V1.md)
**Method:** an independent pass (a fresh general-purpose review, told to re-derive every claim from the
live source and tests rather than trust the implementation's own documentation), followed by fixes for
every P1/P2 it found, re-verified against the fixed code.

---

## 1. Method

The review was adversarial by construction: told what the milestone claims (from the ADR and design
doc), then instructed to verify each claim against the live source directly — reading every file under
`src/fmis/archive/`, the full `git diff` to `src/fmis/pipeline/cli.py`, and the test bodies (not just
names) under `tests/test_archive_*.py` and `tests/test_pipeline_cli.py` — and to reproduce, not assume,
every finding. It ran the full suite itself and spot-checked six test bodies against their names before
trusting any of them.

## 2. Findings

Twenty categories were checked (the milestone's own review checklist: unsafe deserialization, atomicity,
digest stability, record-ID collision resistance, path traversal, arbitrary file reads, symlink
surprises, manifest/record disagreement, schema coercion, model-validation bypass, rendered-text-as-storage,
persistence leaking into the renderer/CLI, secrets/absolute paths in records, hidden archival failure,
analysis/archive failure confusion, `list` reading full payloads, dishonest replay claims, future-proofing,
the one-way import boundary, and the test suite itself). Seventeen were clean on first inspection. Three
real defects were found, all in the one place this milestone's whole point rests on — `archive verify`,
the tool whose job is catching corruption, missed three categories of corruption it should have caught.

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | **P1** | `payload.schema_version` (the domain model's own version, distinct from the envelope's) was checked for type but never compared against a supported set — an unsupported *payload* version decoded and loaded silently. Contradicted ADR-0027 §8 directly. | **Fixed** |
| 2 | **P1** | `archive verify`/`load` never recomputed `record_id` from content, only compared it to itself; a `record_id` field forged to a different, validly-shaped value (with digest/payload left untouched) went undetected. | **Fixed** |
| 3 | **P1** | `verify_archive` cross-checked only `content_digest`; every other manifest field (`subject`, `context_state`, daily counts, `analysis_as_of`) could drift from the actual record and `archive list` would report the fabricated value as genuine, with `verify_archive` reporting `ok=True`. | **Fixed** |
| 4 | P2 | Path-traversal defense in `_resolve_within_root` relied on `resolve()`-based containment rather than an explicit rejection of absolute paths — not currently exploitable (verified: `/etc/passwd`, `//etc/passwd` and relative traversal were all already rejected), but incidental to how the check happened to be written. | **Fixed** (explicit `PurePath.is_absolute()` guard added, defense-in-depth) |
| 5 | P3 | `manifest.jsonl` line parsing used plain `json.loads`, without the duplicate-JSON-key rejection record files already had. | **Fixed** (shared `reject_duplicate_json_keys` hook) |
| 6 | P3 | TOCTOU between the containment check and the later file open in `_resolve_within_root`. | Documented limitation, not fixed — matches the design doc's own stated "no concurrent-writer safety" scope (§6) |

### Finding 1 in detail

`fmis/archive/codec.py`'s `decode_workspace`/`decode_daily_run` validated `schema_version` was a non-bool
`int` but never checked it against `WORKSPACE_SCHEMA_VERSION`/`DAILY_SCHEMA_VERSION`. `UnsupportedSchemaVersionError`
existed and was correctly wired for the *envelope's* version in `envelope.py`, but was dead code with
respect to the payload. **Fix:** `SUPPORTED_WORKSPACE_SCHEMA_VERSIONS`/`SUPPORTED_DAILY_SCHEMA_VERSIONS`
(each `frozenset({current_version})`, mirroring `envelope.py`'s pattern) are now checked explicitly in
both decode functions, closing the same gap the milestone's own "unsupported schema version rejected
clearly" requirement named. Regression tests: `test_decode_workspace_rejects_an_unsupported_payload_schema_version`,
`test_decode_daily_run_rejects_an_unsupported_payload_schema_version`,
`test_decode_daily_run_rejects_an_unsupported_nested_workspace_schema_version`,
`test_supported_payload_schema_versions_are_exactly_the_current_ones`.

### Finding 2 in detail

The load path checked `envelope.record_id != record_id` (a self-referential check: does the file agree
with what it was looked up by?) and separately verified `content_digest`, but never asked "does this
`record_id` actually follow from this content?" A `record_id` swapped for a different, validly-shaped one
— with `content_digest`/`payload` left completely untouched, and the manifest updated to match — passed
every existing check. **Fix:** `_load_envelope` now recomputes `record_id` from the loaded content
(`build_record_id` over the envelope's own `record_type`/subject/`analysis_as_of`/`content_digest`) and
raises `IntegrityError` if it disagrees with the id being loaded. Both checks are kept, deliberately, not
merged — they catch different corruptions (`test_load_detects_a_record_id_forged_to_match_a_correct_digest`
isolates the case only the new check catches; `test_load_detects_a_corrupted_self_declared_record_id_even_when_content_is_genuine`
isolates the case only the *original* check catches, proving neither is redundant).

### Finding 3 in detail

`ArchiveVerification` gained a fourth problem category, `manifest_mismatches`, and `verify_archive` now
decodes each digest-clean record and compares the manifest entry's own fields — `record_type`,
`schema_version`, `analysis_as_of`, `subject`, and (record-type-specific) `context_state` or the daily
counts — against values derived from the actual record. A manifest line hand-edited to claim a different
subject, decision-context state, or failure count, while the record file itself stays byte-for-byte
correct, is now reported rather than silently trusted. Regression tests:
`test_verify_archive_detects_a_manifest_field_drifted_from_the_record`,
`test_verify_archive_detects_a_drifted_manifest_subject`,
`test_verify_archive_detects_a_drifted_daily_run_manifest_summary`. `render_archive_verification` and the
CLI output were updated to surface the new category.

## 3. Mutation results

29 initial probes across every AO module plus the `cli.py` additions found the three defects above (all
three survived their first mutation-adjacent test — `env-01`, hunting for a digest-stability gap, is what
led to writing the golden-digest test that then made the schema-version and record-id gaps visible under
manual review, not mutation directly; the P1s were found by the independent agent review, not the
mutation pass). After the fixes, 35 probes (6 added specifically to exercise the new code) ran:

**34/35 detected, 0 no-ops, 1 proven-equivalent survivor.**

The survivor: `identity.py`'s explicit `"\\\\" in record_id` check inside `validate_record_id` is
provably redundant with `RECORD_ID_PATTERN`, whose character classes (`[A-Za-z0-9_]` for the subject slug,
fixed digit/hex shapes elsewhere) already exclude a backslash from matching at all — confirmed by
construction, not by absence of a test: no string containing `\` can ever satisfy
`RECORD_ID_PATTERN.fullmatch`, so removing the explicit check changes no reachable behaviour. Kept for
defense-in-depth clarity rather than removed, following the same "rounded to zero, not left unexplained"
convention Milestone AH's review established for its own one surviving probe.

Bytecode was purged (`__pycache__` removed, no `.pyc` reuse) before every probe; every mutated file was
restored from an in-memory backup and its SHA-256 verified to match the pre-mutation digest after every
probe, verified for the whole run (`git status --short` showed no drift after either mutation pass).

Every mutation probe and its full first-pass/second-pass output is reproducible from
`/private/tmp/claude-501/.../scratchpad/mutation/mutate.py` (session-scoped, not part of the repository);
the harness is a hand-written find/replace/restore driver, matching this repository's established manual
mutation-testing pattern (`docs/AI_HANDOFF/CURRENT_STATE.md` records no dedicated mutation tool exists in
this project — every milestone's mutation testing is a scripted manual process).

## 4. Coverage

100% line and 100% branch coverage on every module under `src/fmis/archive/` and on the modified
`src/fmis/pipeline/cli.py`, measured with `coverage.py --branch` (an ephemeral `uv run --with coverage`
dependency — not added to `pyproject.toml`, which keeps its zero-runtime-dependency policy unchanged):

```
src/fmis/archive/__init__.py   100%    src/fmis/archive/manifest.py   100%
src/fmis/archive/atomic.py     100%    src/fmis/archive/render.py     100%
src/fmis/archive/codec.py      100%    src/fmis/archive/storage.py    100%
src/fmis/archive/envelope.py   100%    src/fmis/pipeline/cli.py       100%
src/fmis/archive/errors.py     100%
src/fmis/archive/identity.py   100%    TOTAL: 939 statements, 276 branches — 0 missed
src/fmis/archive/json_safe.py  100%
```

## 5. Test suite

3,905 → **4,181 tests** (+276), identically green under `-W error`. New test files:
`test_archive_atomic.py`, `test_archive_boundary.py`, `test_archive_codec.py`, `test_archive_envelope.py`,
`test_archive_errors.py`, `test_archive_identity.py`, `test_archive_json_safe.py`,
`test_archive_manifest_entry.py`, `test_archive_render.py`, `test_archive_storage.py`,
`test_pipeline_cli.py`, plus `tests/archive_helpers.py` (shared offline fixture builders, not itself a
test module). Four pre-existing tests were updated to account for the sixth CLI command
(`test_daily_runner.py::test_no_engine_imports_this_package`'s importer allowlist,
`test_multi_timeframe.py`/`test_pipeline_regime.py`/`test_workspace_render.py`'s hardcoded command lists)
— each a mechanical, expected widening, not a behavioural change to what those tests actually guard.

## 6. Measured results

Encoded artifact sizes and timings (median of 10–20 runs, `time.perf_counter`, this machine):

| Measurement | Value |
|---|---|
| Encoded `Workspace` size | 22,818 bytes |
| `Workspace` encode time | 0.016 ms |
| Encoded `DailyRun` size (1 symbol) | 27,818 bytes — encode 0.019 ms |
| Encoded `DailyRun` size (10 symbols) | 274,895 bytes — encode 0.199 ms |
| Encoded `DailyRun` size (50 symbols) | 1,373,255 bytes — encode 1.089 ms |
| Atomic write (mkstemp→fsync→replace, sequential) | 1.230 ms |
| Load (decode + digest + record-id verify) | 0.630 ms |
| Single-record verify | 0.622 ms |
| Whole-archive verify (20 records) | 9.461 ms |
| `archive list` (20 records) | 0.091 ms |
| `archive list` (200 records) | 0.713 ms |

No compression, no concurrency — consistent with ADR-0027's Rejected Alternatives, and nothing measured
here suggests either is needed at this owner's expected scale (hundreds of records, not millions).

## 7. Live demonstration

Run against real Binance data (`fmits swing BTCUSDT --archive -n 260`, live network fetch):

- `archive show RECORD_ID` reproduced **byte-identical** rendered text to the original `fmits swing`
  run (diffed directly; the archived-record line was the only difference, as expected).
- `archive show` made **zero** network calls (verified both by test — `test_show_performs_no_network_call`,
  `test_swing_archive_can_then_be_shown_with_no_network` patches the fetch path to raise if touched — and
  by construction: no import in `storage.py`/`codec.py` is network-capable).
- Corruption was detected: flipping one value inside a stored record made `archive verify RECORD_ID`
  report `FAILED — content_digest mismatch ...` with exit code 1.
- An unsupported schema version was rejected cleanly: setting `schema_version: 999` on a stored envelope
  made `archive show` report `UnsupportedSchemaVersionError: envelope schema_version 999 is not
  supported; this build supports [1]` with exit code 1, no partial output.
- `fmits daily BTCUSDT ETHUSDT --archive` archived a `DailyRun`, and `archive list` displayed
  `completed=2/2 failed=0` read from the manifest alone.

## 8. Verdict

The atomic-write path, record-ID construction, one-way import boundary, and failure-reporting discipline
(archive failure vs. analysis failure, kept visibly distinct end to end) were sound on first inspection —
careful, not merely well-narrated. The three P1s were real and specific to the one guarantee this
milestone exists to make: that a "verify OK" can be trusted. None was catastrophic on this milestone's own
terms — single supported schema version today, no RCE, no exploitable traversal — but each was exactly the
kind of ordinary corruption (a stale format, a hand-edited manifest line, a tampered identifier) `archive
verify` is supposed to exist for. All three are closed, independently regression-tested, and re-verified
by a second, larger mutation pass (34/35 detected, 1 proven-equivalent, 0 no-ops) against the fixed code.
No P0 was found at any point. AO is accepted as verified-quality persistence for a personal-use system.
