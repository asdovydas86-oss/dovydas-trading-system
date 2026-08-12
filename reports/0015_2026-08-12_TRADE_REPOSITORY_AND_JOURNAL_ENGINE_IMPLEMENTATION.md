# 0015 — Trade Repository & Journal Engine (Milestone BI) — implementation record

| Field | Value |
|---|---|
| **Report number** | 0015 |
| **Title** | Trade Repository & Journal Engine (Milestone BI) — implementation record |
| **Date** | 2026-08-12 |
| **Report type** | Implementation record |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | Working tree on top of `c96c3e4`. `origin/main` is at `f9ddc54`, four commits behind |
| **Status** | Implementation complete. **Not committed, not pushed.** Both require separate, explicit authorization (`CLAUDE.md`) |

---

## 0. What was built, in one paragraph

One new package, `fmis.persistence`: sixteen modules implementing the **durable store** for the owner
half of FMITS — nine repositories, an append-only hash-chained write journal, a version engine, a
rebuildable metadata index, and one composition root. **4,700 lines of production code, 5,178 lines of
tests, 366 new tests, 100 % statement and 100 % branch coverage of the new package, an 81.6 % mutation
score over four sweeps with every survivor classified, zero new runtime dependencies, zero export
collisions, zero existing source files modified.** The trading domain Milestone BH built is now
persistable, correctable by supersession, reconstructable at any past instant, and auditable line by
line.

---

## 1. The brief's nine repositories, and what each one turned out to be

| Brief asked for | Built as | Write verbs that succeed | Note |
|---|---|---|---|
| **TradeRepository** | `TradeRepository` | `create`, `replace` → appends a `Correction` | — |
| **PositionRepository** | `PositionRepository` | **none** | §3 — it stores nothing, by classification |
| **PortfolioRepository** | `PortfolioRepository` | `create` | Frozen observations |
| **JournalRepository** | `JournalRepository` | `create`, `replace` → appends a superseding entry | The owner's words, not the store's |
| **SnapshotRepository** | `SnapshotRepository` | `create` | `MarketSnapshot` **and** `DecisionWindow` |
| **AnalysisRecordRepository** | `AnalysisRecordRepository` | `create` | The one kind whose id belongs to `fmis.archive` |
| **OpportunityRepository** | `OpportunityRepository` | `create`, `append_event`, `replace` (events only), `admit` | Owns the proposal *and* its lifecycle stream |
| **RiskRepository** | `RiskRepository` | `create`, `revise` → appends the next generation | Generations, not supersession |
| **LedgerRepository** | `LedgerRepository` | **none** | Read-only; the enforced supersession-applying read path |

**Nothing the brief asked for was dropped.** Two of the nine turned out to have no successful write
verb at all, and both for stated reasons: a position is a fold, and the ledger is read through a
resolver whose writes belong to `TradeRepository` where the event being superseded can be checked.

### 1.1 Every capability the brief named, and where it lives

| Required | Where |
|---|---|
| create | `Repository.create` — idempotent by content on all nine |
| update | **Raises on all nine**, naming the legal path. §2.1 |
| replace *when appropriate* | Three kinds have a supersession mechanism; the other six refuse |
| load by id | `Repository.load` — four independent integrity checks |
| load by owner | `Repository.load_by_owner(book=, market=, account=)`. §4.2 |
| history | `Repository.history` — every version, oldest first |
| search | `Repository.search(SearchCriteria)` — two time axes kept apart |
| immutable historical reconstruction | `Repository.at(id, moment)`, `LedgerRepository.resolved_as_known_at`, `PositionRepository.as_known_at` |
| version-aware loading | `VersionEngine` — `lineage`, `head`, `history`, `at`, `series`, `series_at` |

---

## 2. The three findings that changed a design decision

### 2.1 `update` cannot succeed anywhere, and that is the honest implementation

The brief asks for `create` / `update` / `replace when appropriate`. Implementing `update` as a
successful operation on **any** kind would contradict the same brief's *"nothing is rewritten."*

There are exactly two ways a record's meaning changes in this system, and neither is an update:

* **supersession** — a new record naming the one it replaces (`Correction`, a superseding
  `JournalEntry`, a superseding `ProposalLifecycleEvent`);
* **the next observation** — a later `PortfolioSnapshot`, a later `MarketSnapshot`, the next
  `RiskBudget` generation. Not a change to anything.

So `update` exists on all nine repositories and raises on all nine, with a message naming the legal
path for that kind. The alternative — omitting the method — leaves a caller with an `AttributeError`
and no direction.

**`replace` also raises by default**, and a subclass that can supersede overrides it. That is the
opposite of the usual inheritance default and it is deliberate: a kind acquires an update path only
by someone writing one. The failure being guarded against is a captured artifact quietly gaining an
edit path three milestones after it was declared frozen.

### 2.2 The store cannot be allowed to decide what a supersession is — the record decides

The first draft took `WriteOperation` from the caller's `WriteRequest`. That is wrong, and the reason
is concrete: a `Correction` filed as a plain `CREATE` is **invisible to every later reader of the
chain**, and nobody would notice until a report showed a value the owner had already corrected.

`publish` now reads `supersedes` off the record through its spec and upgrades the operation itself. A
caller who claims `SUPERSEDE` about a record naming nothing is **refused** rather than silently
downgraded — the reverse direction is a misunderstanding worth surfacing.

The corollary is that the link lives on the *record*, not in the index: export the records, throw the
index away, and the history is still derivable.

### 2.3 A record file's bytes are not a pure function of the record

Found while testing crash recovery. An envelope carries `written_at`, so two filings of the identical
record produce different bytes — and the first implementation compared bytes, which reported a
`RecordConflictError` on every crash-recovery retry.

ADR-0027 §3 already draws this line for `archived_at`: **what a record *is* excludes when it was
filed.** Sameness is now judged on `(kind, record_id, content_digest, payload)`, and a retry over a
lost index leaves the original filing date in place rather than moving it to the retry.

That produced a second correction. Consulting only the index missed a case: if the journal *already*
holds an event for the record, a retry must not append a second one — the index row is what was
missing, and the index row is what the retry restores. `created` is false, and the audit trail does
not gain a write that never happened.

---

## 3. `PositionRepository` stores nothing, and that is the deliverable

Architecture §24.3 classes a position as a **rebuildable projection**: *"delete every rebuildable
projection, recompute, and assert identical results."*

`create`, `update`, `replace` and `load` all raise `ProjectionError`. `load` raises with its own
reason: positions have no ids in this store, because a derived key can move when a dust policy
changes and nothing frozen may reference one (AP-D8).

Everything the repository offers is a fold over `LedgerRepository.resolved()`: `rebuild`,
`open_positions`, `as_known_at`, `load_by_owner`, `total_fees_in`, and `is_reproducible()` — which
folds twice and compares, making §24.3's CI test available as a method.

A repository that refuses to write is a stranger deliverable than one that writes, and it is the more
valuable of the two: it is the difference between a classification written in a document and one the
code will not let anybody violate.

---

## 4. What the implementation enforces rather than documents

| Rule | Where it is enforced | What it would cost to lose |
|---|---|---|
| There is exactly one write path | Guard test: no repository module names `atomic_write` or `append_lines` | The write journal becomes *mostly* complete, which is worth nothing |
| Every write appends exactly one journal event | `RecordStore.publish`, the only writer | A record with no audit trail, and no way to tell which |
| An idempotent write appends **no** event | `_resolve_duplicate` returns `created=False` | Every crash-recovery re-entry counted as a new fill |
| A removed, altered or reordered event is detectable | The journal's hash chain, verified on every read | "Append-only" becomes a claim about the writer, not about the file |
| Filing time never moves backwards | `JournalEngine.append` | An audit trail that can be inserted into in the middle |
| A published line file can never shorten | `O_APPEND` only; a guard test forbids `"w"` and `O_TRUNC` | One short read publishes a truncation, and the history is gone with no evidence |
| A truncated trailing line is reported, never dropped | `read_lines` | A silent repair of an append-only file |
| A chain extends; it never branches | `RecordStore.successors`, `VersionEngine.lineage` | *"What actually happened"* gets two answers |
| A correction naming an event this store lacks is refused | `TradeRepository.replace` | A detected gap becomes a silent one |
| A lifecycle event about an unknown proposal is refused | `OpportunityRepository.create` | A fold input that will never resolve |
| A superseding record must name what it replaces | Every `replace` | The link survives only in the index, and not in an export |
| A record may not be filed before it happened | `publish`, with one declared exception | A store of things that have not happened |
| Exactly one kind may be dated in the future | `RecordSpec.moment_may_be_future`, asserted by test | *"Raise my per-trade risk from Monday"* becomes unrepresentable, or the rule becomes meaningless |
| A back-dated budget generation is refused | `RiskRepository.revise` | Which limits an already-frozen check ran against silently changes |
| A draft trade is never in the ledger | `TradeRepository.create` | A value nobody asserted enters an append-only economic record |
| Pruning a captured window is refused | `_resolve_duplicate`, `FrozenRecordError` | Captured rows deleted under a name that does not say "delete" |
| The index is rebuildable, and proven so | `rebuild_index()`, asserted row-for-row by test | A second place a record's metadata lives |
| A rebuild will not index a record with no journal event | `rebuild_index` | The audit trail forged to complete a lookup table |
| Nothing reads a clock | AST/text scan over every module | A store that stamps itself cannot be replayed |
| Nothing in the domain imports the store | AST scan, both directions | A `Trade` that cannot be built without somewhere to put it |
| The archive's encoder is reused, never reimplemented | Import guard limited to four modules | A second definition of "the bytes" |
| No threshold is invented | AST scan: no float literal anywhere in the package | The owner's policy becomes the store's judgement |

---

## 5. Architecture

**No existing source file was modified.** All thirteen domain packages, `fmis.archive` and every
L0–L7 engine are byte-identical.

**Four `fmis.archive` modules are imported, read-only**: `json_safe` (the frozen canonical encoder and
the timestamp codec), `identity` (SHA-256 and the archive's own id validator), `atomic` (ADR-0027 §6's
publish sequence) and `errors` (the base class, so a corrupt file can be relabelled rather than
escape). A guard test asserts the store never reaches `fmis.archive.storage` or
`fmis.archive.manifest` — two stores under one root would be two answers to what is filed where.

**The store imports no engine.** Asserted across all 21 market-half packages.

**No module in the package participates in an import cycle.** Asserted by a test that pins the
fifteen-module layering order and checks every intra-package import points backwards along it.

**The layering is asserted in both directions**: no domain package and no market-half package imports
`fmis.persistence`.

### 5.1 The one existing file changed

`tests/conftest.py`, +21 lines: two fixtures (`sample_records`, `budget`) shared by four persistence
test modules. No existing fixture was touched. No production file was modified.

---

## 6. Test and coverage evidence

Every figure below was executed against this working tree, not quoted.

| Measure | Value |
|---|---|
| **New tests** | **366**, in 8 files plus one shared builder module |
| **Test suite** | 5,263 → **5,629**, all passing. Verified on the final tree with `pytest -q -W error` — 5,629 passed, 171 s, zero warnings |
| **New-package statement coverage** | **100 %** — 1,623 statements, 0 missed |
| **New-package branch coverage** | **100 %** — 416 branches, 0 partial |
| **Production lines added** | 4,700 across 16 modules |
| **Test lines added** | 5,178 |
| **New public exports** | 60; repository total 586 → **646** |
| **Export collisions** | **0**, verified repository-wide |
| **New runtime dependencies** | **0** |
| **Existing source files modified** | **0** |
| **Existing test files modified** | **1** (`tests/conftest.py` — §5.1) |

`coverage` and `mutmut` were run through `uv run --with …` against the project interpreter; neither is
installed into `.venv` and neither is added to `pyproject.toml`.

### 6.1 What the tests cover

| Area | Where |
|---|---|
| Repository round-trip | Every kind, twice: equal value **and** byte-stable re-encoding |
| Version reconstruction | Chains of one, two and three versions; reachable from any member |
| Historical replay | `at()`, `resolved_as_known_at()`, `as_known_at()` — a correction filed later does not move a past answer |
| Append-only verification | Prior bytes byte-identical after every append, on all three line files |
| Identity stability | Content-derivation, idempotency, filing time excluded from the digest |
| Snapshot immutability | Frozen kinds refuse `update` and `replace`; a pruned window is refused |
| Journal ordering | Sequence contiguity, chain links, monotonic filing time, cross-year spans |
| Concurrency safety | Eight threads publishing eight records, and four publishing one |
| Serialization | Every envelope, index row and journal event round-trips; unknown fields, versions and enum members all rejected |
| Repository determinism | Two stores over one root give identical answers; nothing is cached |
| Corruption detection | Tampered record file, tampered log line, re-pointed index row, forged digest, altered journal field, removed event, reordered events, truncated tail, duplicate index line |
| Crash recovery | Every gap in the publish sequence, and what a retry does about each |
| I/O failure | Unreadable file, unwritable root, undecodable payload, failed `write`, failed `fsync`, failed atomic publish |
| Architecture | 30 boundary guards: layering both ways, cycles, clocks, mutable state, write paths, thresholds, exports |

---

## 7. Mutation testing

`mutmut` 3.7.0 against `fmis.persistence`, with the seven behavioural persistence test modules as the
test selection. `tests/test_persistence_architecture.py` is excluded from the runner: it asserts
properties of the *source text*, so it would kill mutants for reasons unrelated to behaviour and
inflate the score.

| Measure | Value |
|---|---|
| **Mutants generated** | **1,987** |
| **Killed** | **1,622** |
| **Survived** | 363 |
| **Timed out** | 2 |
| **Mutation score** | **81.6 %** |

### 7.1 The first classification of the survivors was wrong, and how that was found

Four sweeps were run; survivors fell **490 → 407 → 373 → 363**. After the third, this report claimed
that *"no surviving mutant changes an outcome any test could observe."* **That claim was false**, and
it was false because of how the triage worked rather than because of anything in the code.

The triage binned every `f(x)` → `f(None)` mutation as *diagnostic*, on the assumption that the
argument being replaced was always the entity name a validator quotes in an error message. It usually
was. It was not always. A verification pass re-audited the residue item by item and found **eighteen
survivors that were genuinely behavioural**, each wearing that harmless shape:

| What the mutation did | Why it survived |
|---|---|
| `astimezone(timezone.utc)` → `astimezone(None)` in the layout's UTC helper | Converts to the *machine's local zone*. An event at 23:30 UTC on 31 December files under the wrong year east of UTC — ADR-0001's storage contract, broken silently on somebody else's laptop |
| `rebuild(criteria)` → `rebuild(None)` in `open_positions`, `total_fees_in`, `is_reproducible` | The fold quietly widened to the whole ledger |
| `proposals(criteria)` → `proposals(None)` in `live_proposals` | Same, for proposals |
| `search(base)` → `search(None)` in `PortfolioRepository.snapshots` | Same, for snapshots |
| `kind=…` dropped in `snapshots`, `windows`, `latest_for_market`, `RecordStore.records` | Both snapshot kinds carry the same market, so a listing would return the other one |
| `lineage_key=…` dropped in `snapshots`, `latest`, `for_subject` | Every test had exactly *one* portfolio and *one* analysis subject, so no filter could fail |
| `WriteReceipt(record_id=…)`, `RecordCheck(record_id=…, ok=…)` → `None` | The results' own fields were barely asserted; `assert not result.ok` cannot tell `False` from `None` |
| `unjournalled_records` and the early-return journal fields dropped from `verify` | Every existing test left those empty, so deleting them changed nothing |

**Each of the eighteen was closed by a test, and each test was then verified against its own mutant**:
the mutation applied to the real source, the bytecode cache cleared, the suite confirmed to fail, and
the source restored under a hash check. That procedure caught two further mistakes — one test that did
not kill the mutant it named, and a mutation pattern that matched the wrong call site and so exposed a
third gap nobody was looking for.

**A stale `.pyc` invalidated an entire earlier verification round.** Restoring a file with `cp` leaves
bytecode compiled from the mutated source in place; results from that round were discarded and the
round re-run with the cache cleared between every step. It is recorded here because a verification
procedure that can silently lie is worth more attention than the thing it was verifying.

### 7.2 What the 363 remaining survivors are

| Class | Count | Why it is not chased |
|---|---|---|
| **Error-message prose** | 259 | The mutation rewrites the *text* of a failure, not whether it fails. Killing these means asserting exact wording everywhere, so every rewording becomes a test failure |
| **String argument → `None`** | 55 | The *name* a value is reported under when validation rejects it. Same failure, different sentence |
| **Line number in a message** | ~18 | `enumerate(…, start=1)` → `start=2`, and `line_number=…` → `None`. Only the number quoted in a decode error moves |
| **Redundant keyword** | ~9 | An argument deleted where it equalled the callee's default — `expected_existing=len(lines)` versus the same value recomputed inside |
| **Remaining, audited individually** | ~22 | Two file-mode arguments to `os.open` (`0o644` dropped, and `0o644` → `0o645`). These are **not** the same mode as each other — `0o755`, `0o645`, `0o644` after this machine's `0o022` umask — and what they share is that none sets a group- or other-write bit, which is the property `test_a_stored_file_is_not_writable_by_anybody_else` asserts and the only one this store depends on. The rest are kind filters whose alternative kinds cannot collide (no non-lifecycle lineage key can take the shape of a proposal id), dict values read only inside a message, and `ensure_ascii=False` → `None`, which is the same falsy value |

**The honest summary is narrower than the one this report first gave.** Every survivor was looked at;
each is in a class above; and the classes are described so a later reader can disagree with the
judgement rather than take it on trust. What is *not* claimed is that no observable survivor exists —
that claim was made once, and was wrong.

## 8. Hostile review

Ten attack classes, each probed against a running store rather than reasoned about.
**One found a real defect**, and it is recorded here rather than quietly fixed.

| Attack | Result |
|---|---|
| **Repository corruption** — hand-edit a record file, a log line, an index row, a journal line | Refused. Four independent checks on every load: index path re-derived, envelope id, decoded id, decoded digest |
| **Lost history** — delete a journal event, truncate a year file, shorten the index | Detected. The chain names the first broken link; a truncated tail is reported, not dropped; `O_APPEND` makes shortening unreachable from inside the package |
| **Rewritten history** — alter a field inside a published event or record | Detected. Every id is a digest of its own content and is re-derived on read |
| **Identity drift** — publish the same record twice, from two sources, at two filing times | One record. Filing time is excluded from the digest, and sameness is judged on content |
| **Version mismatch** — an unsupported `schema_version`, an unknown kind, an unknown enum member, an unknown field | Clean rejection at every layer: envelope, index row, journal event, domain payload |
| **Serialization bugs** — non-ASCII, non-finite numbers, duplicate JSON keys, key reordering, a newline inside a line | All refused or normalized; `encode_line` is a pure function of content |
| **Ordering bugs** — a write filed before the journal head, two events on one candle, a cross-year sequence | Refused, reported as ambiguous by the domain's fold, and verified contiguous across years |
| **Race conditions** — eight threads publishing eight records; four publishing one | Eight records, one intact chain; and one record with one event |
| **Partial writes** — a short `os.write`, a failed `fsync`, a failed atomic publish | Each raises `StoreIOError`; a short write is refused explicitly rather than assumed impossible |
| **Hidden coupling** — two stores over one root, a cached resolver, module-level state | None found. Two stores give identical answers; the resolver is rebuilt per call; a guard test forbids module-level mutable state |

### 8.1 The defect the review found: a supersession chain could cross record kinds

`supersedes` holds a **domain record id**, and the id pattern cannot tell a journal entry's from a
trade's — both are well-formed. A `JournalEntry` naming a `Trade`'s `event_id` was accepted, and
`load_latest` on that fill then returned **the owner's prose about it**. The note became the current
version of the trade.

Neither the domain nor the id validator can catch this: the shape is identical, and only a store knows
what a given id turned out to be. Fixed by declaring, per kind, which kinds it may supersede
(`RecordSpec.supersedes_kinds`) and checking it in `publish` — the single write path, so no repository
can route around it. A correction may supersede a trade *or* another correction, because a chain of
corrections is legal; every other kind may supersede only its own kind, and captured artifacts may
supersede nothing at all. Three guard tests now assert the table's shape, and one test reproduces the
original attack.

**A dangling supersession is deliberately still accepted at write time.** A correction imported before
the fill it corrects is ordinary backfill. The gap is reported by `verify()` and refused at read time
by `LedgerResolver`, which is where a dangling reference actually matters.

---

## 9. Known limitations, stated rather than implied

1. **The store has no surface.** Nothing in `fmits` reads or writes it. The owner can do nothing new
   today; §11 explains why that means no changelog entry.
2. **No full-dump export exists.** Architecture §5.7 item 4 requires one *before the first real record
   is written*. **This is the single most important thing that must follow**, and it is not built.
3. **No golden-file corpus exists.** Every payload version in the repository is 1, so the forward-only
   reader contract (§5.7 item 2) is implemented and unproven.
4. **Pruning a `DecisionWindow` is refused rather than supported.** §4. Adding the capability means
   deciding a measured trigger first; §24.4 states none.
5. **The index is read in full on every lookup.** `find` is O(rows), on the same cost curve ADR-0027
   accepted for `manifest.jsonl`. §24.4's manifest trigger applies here unchanged.
6. **Two writer processes are not supported.** The lock stops one writer's threads from interleaving;
   it is not the concurrency control §24.4 defers, and does not claim to be.
7. **`fcntl` is POSIX.** On a platform without it the lock degrades to no lock. Stated in the source.
8. **`RiskRepository.evaluate` computes no measurement.** It evaluates values it is given, exactly as
   the domain's `RiskBudgetState` does.
9. **No composition root fills a `MarketSnapshot`.** The shape is persistable; producing one from the
   engines is still the next slice's work.
10. **The backlog's exactly-one-NOW rule remains unsatisfied.** This was an explicitly scoped,
    owner-directed implementation task, like BH, AT, AU and AV before it — not a NOW selection.

---

## 10. What a reviewer should attack first

1. **`_operation_for` upgrading a caller's `CREATE` to `SUPERSEDE`.** The store reading intent off the
   record is the right call, but it *is* the store overriding an explicit argument. If a caller ever
   has a legitimate reason to file a superseding record as a plain create, this is wrong.
2. **`written_at` taken from the stored envelope on a retry.** §2.3. It makes the filing date stable
   across crash recovery, and it means the journal event's timestamp and the index row's `written_at`
   can differ. Both are correct — one is when the record was filed, the other when this call recorded
   the filing — but they are two timestamps that look like one.
3. **The journal scan in `_existing_journal_event`.** O(all events), reached only when a payload is
   already on disk. If that path ever becomes common, it is the first thing that will hurt.
4. **`DecisionWindow`'s digest over `identity_basis`.** It follows the domain's own id derivation, and
   it means the store's integrity check for that one kind does not cover the captured rows. The rows
   are covered by `series_digest`, which the domain validates at construction — but the chain of
   reasoning is one link longer than for every other kind.
5. **`RecordSpec.moment_may_be_future`.** One boolean, one kind. If a second kind ever needs it, the
   flag stops carrying its stated reason and becomes a switch.
6. **The nine repositories' `search` all reading the whole index.** Correct and deterministic;
   proportionate today; the first thing a listing at year ten will notice.

---

## 11. Why there is no changelog entry

`CLAUDE.md`: *"`FMITS_PRODUCT_CHANGELOG.md` — user-visible capability only. Never record documentation
or refactors as a product release."*

This milestone adds **no user-visible capability**. There is no new command, no new output, and
nothing the owner can do after it that was impossible before. What it adds is the ability for the next
milestone to have one. Recording it as a release would be the exact failure that rule exists to
prevent. The backlog records it under §8 with the value it *does* deliver; the changelog stays silent
until a command reads or writes a record.

---

*No ADR was written. No accepted ADR was amended. `fmis.archive`, all thirteen domain packages and
every engine are unmodified. The only existing file changed is `tests/conftest.py`, for the reason
recorded in §5.1.*
