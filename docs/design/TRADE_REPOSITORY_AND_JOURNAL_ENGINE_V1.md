# Trade Repository & Journal Engine v1 — Design

**Milestone:** BI
**Status:** **Implemented.** This document records the architecture that was built, not a proposal.
The implementation record is
[`reports/0015`](../../reports/0015_2026-08-12_TRADE_REPOSITORY_AND_JOURNAL_ENGINE_IMPLEMENTATION.md).
**Builds on:** [`TRADING_DOMAIN_ARCHITECTURE_V1.md`](TRADING_DOMAIN_ARCHITECTURE_V1.md) §24
(storage architecture), §25 (freezing policy) ·
[`TRADING_DOMAIN_DATA_MODEL_V1.md`](TRADING_DOMAIN_DATA_MODEL_V1.md) (the objects) ·
[ADR-0027](../adr/ADR-0027-memory-and-decision-archive-persistence-schema.md) (canonical encoding,
content digests, atomic publication, no silent repair) ·
[ADR-0001](../adr/ADR-0001-canonical-utc-timestamps.md) (UTC is canonical for storage) ·
[ADR-0005](../adr/ADR-0005-ingestion-boundary-strictness.md) (reject, never repair) ·
[ADR-0007](../adr/ADR-0007-application-layer-boundary.md) (import direction) ·
Milestone BH ([`reports/0014`](../../reports/0014_2026-08-12_TRADE_DOMAIN_FOUNDATION_IMPLEMENTATION.md))

---

## 1. What this layer is

`fmis.persistence` is the **only write path into the trading domain**, and the only way to read what
it wrote. One package, sixteen modules, nine repositories, one composition root.

Everything below it — the thirteen domain packages Milestone BH built — stays pure: no path, no file,
no clock. Nothing in the domain imports this package, and a guard test asserts it in both directions.
The day that reverses is the day a `Trade` cannot be constructed without a store to put it in, and
that failure would arrive as a convenience rather than as a decision.

---

## 2. The five structural decisions

### 2.1 There is exactly one write path

Every repository is a typed face over `RecordStore.publish`. There is no second way to reach disk, so
the write journal is a **complete** account of the store rather than a mostly complete one: a record
that reached disk without a journal event would have to have been written by code that does not
exist. A guard test asserts that no repository module names `atomic_write` or `append_lines`.

### 2.2 `update` never succeeds, anywhere

Not on a captured artifact, not on a source of truth, not on anything. The method exists so callers
find a message naming the legal path rather than an `AttributeError` they have to guess past.

Only two things change what a record means:

| Mechanism | Where it exists | What it is |
|---|---|---|
| **Supersession** | `Trade` (via `Correction`), `JournalEntry`, `ProposalLifecycleEvent` | A new record naming the one it replaces. Both stay readable forever |
| **The next observation** | `PortfolioSnapshot`, `MarketSnapshot`, `RiskBudget` | Not a change to anything |

`replace` also raises **by default**. A subclass that can supersede overrides it, so a kind acquires
an update path only by someone writing one — never by inheriting one. That is the opposite of the
usual default, and it is the point: the failure this guards against is a captured artifact quietly
gaining an edit path three milestones after it was declared frozen.

### 2.3 The supersession link lives on the record, not in the index

`Correction.supersedes`, `JournalEntry.supersedes`, `ProposalLifecycleEvent.supersedes` are domain
fields. The store *reads* them; it never assigns one. Two consequences:

1. **The store cannot decide what a supersession is.** A record naming something it replaces **is** a
   supersession whatever the caller called it — `publish` upgrades a `CREATE` request to `SUPERSEDE`
   from the record itself. A caller who claims `SUPERSEDE` about a record naming nothing is refused
   rather than silently downgraded.
2. **The chain survives the store.** Export the records, throw the index away, and the history is
   still derivable.

**A chain never crosses kinds, and only the store can enforce that.** `supersedes` holds a domain
record id, and the id pattern cannot tell a journal entry's from a trade's — both are well-formed. A
hostile-review probe found that an entry naming a fill was accepted, after which `load_latest` on the
*trade* returned the owner's *prose about it*. Each kind now declares which kinds it may supersede
(`RecordSpec.supersedes_kinds`), checked in `publish`: a correction may supersede a trade or the
correction before it, every other kind may supersede only its own, and a captured artifact may
supersede nothing. A *dangling* supersession is still accepted at write time — importing a correction
before the fill it corrects is ordinary backfill — and is reported by `verify()` and refused at read
time by `LedgerResolver`, which is where it matters.

### 2.4 The index is the only thing here that is not truth

`index.jsonl` is a rebuildable projection over the payloads and the write journal.
`RecordStore.rebuild_index()` reconstructs it row for row, and a test deletes it, rebuilds, and
asserts the result is identical. An index that could not be thrown away would be a second place a
record's metadata lives, and the two eventually disagree.

### 2.5 Nothing reads a clock

Every instant — a record's own, and the moment it was filed — is supplied by the caller. This is the
same rule the domain follows and for the same reason: a store that stamps itself cannot be replayed,
and a test that has to freeze a clock becomes flaky rather than wrong. A guard test scans the package
for `datetime.now(`, `time.time(` and `random.`.

---

## 3. On-disk layout

Architecture §24.1's two shapes, on the `type/YYYY/MM` axis the archive already uses:

```
<root>/
  index.jsonl                                  the metadata index — rebuildable
  journal/<YYYY>.jsonl                         the write journal, hash-chained
  records/<kind>/<YYYY>/<MM>/<record_id>.json  one captured artifact or entry
  ledger/<kind>/<YYYY>.jsonl                   one calendar year of events
  .writer.lock                                 held for the whole of one publish
```

| Kind | Shape | Durability class |
|---|---|---|
| `trade`, `correction`, `lifecycle_event` | event log | source of truth |
| `journal_entry`, `risk_budget` | record file | source of truth |
| `opportunity_proposal`, `market_snapshot`, `decision_window`, `portfolio_snapshot`, `analysis_record` | record file | captured artifact |
| *positions, holdings, portfolio valuation* | **none** | rebuildable projection |

Both shapes use ADR-0027's machinery unchanged: `canonical_dumps` for record files, content digests
from `content_digest_over`, `atomic_write` for publication, explicit schema versions, no silent
repair. The archive's encoder and digest helper are **imported, never reimplemented** — a second
definition of "the bytes" is Law 1's failure at the level of a function.

### 3.1 Append is a real `O_APPEND` write, not a read-modify-rewrite

`fmis.archive.manifest` publishes its manifest by reading the whole file, appending in memory and
replacing it atomically. This store makes the other choice for the three line files, and the reason is
integrity rather than cost: **a whole-file rewrite is a code path that can produce a shorter file.**
If the read ever comes back truncated, the rewrite publishes the truncation and the history is gone
with no evidence it was there. `os.open(..., O_APPEND)` cannot do that.

A truncated trailing line — a write that did not finish — is **reported, never repaired**. Dropping it
would be a silent repair; completing it is impossible.

---

## 4. The journal engine

**Not `fmis.journal`.** That package holds `JournalEntry`, the owner's own words. This one holds
`JournalEvent`, one line per write the store performed. They share a word and nothing else.

Every event carries the six fields the milestone requires — **timestamp, source, author, reason,
version, provenance** — plus the four the store needs to make them useful: `operation`, `record_kind`,
`record_id`, `content_digest`.

| Field | Type | Why it is required |
|---|---|---|
| `occurred_at` | UTC instant | When FMITS filed it — not when the thing happened |
| `source` | `WriteSource` | Owner, statement import, exchange API, policy engine, model, rebuild, migration |
| `author` | non-empty text | An unattributable record |
| `reason` | `VersionedTerm` | *"An untagged correction cannot be counted"*, one layer up |
| `version_set` | `VersionSet` | All ten version axes, content-addressed |
| `provenance` | `tuple[ConsumedSource, …]` | Law 8: id **and** digest of everything read |

### 4.1 The chain is what makes "nothing is rewritten" checkable

Each event's digest covers its predecessor's id. Remove an event, alter a field, or reorder two lines,
and every event after the change fails verification with the first broken link named. An append-only
file that is merely *opened* in append mode is honest about the writer; a hash chain is honest about
the file.

### 4.2 Filing time is monotonic, and that is enforced

A **record** may be backfilled — a trade that happened in 2024 is filed with `occurred_at` in 2024 —
but the *journal event* recording that filing happens now. An event claiming to precede the current
head is refused, because an audit trail that can be inserted into in the middle is not one.

### 4.3 An idempotent write appends no event

Nothing changed, so nothing is recorded. Re-entering a fill after a crash, re-running a scan that
produces the same snapshot, or importing the same statement twice all resolve to `created=False`. An
audit trail that records non-events dilutes the ones that matter.

---

## 5. The version engine

There is no `UPDATE` in this store, so *version* means something exact: **a version is a whole
record.** Every past version stays byte-identical and loadable forever; only the chain moves.

| Question | Method | Decided by |
|---|---|---|
| Every version, oldest first | `history(id)` | the supersession chain |
| What does it say now | `head(id)` | the chain's last link |
| What did it say **then** | `at(id, moment)` | **`written_at`** — what the store *knew* |
| Every record about one subject | `series(kind, key)` | `occurred_at` — what was *true* |

**A chain and a series are not the same thing**, and merging them would be a real loss. Three
snapshots of one portfolio are three observations, none superseding another. Three generations of one
risk budget are three versions of one policy, only the latest in force. Both are answered, and neither
is called a version of the other.

### 5.1 `at()` is what makes a past report reproducible

A correction filed today does not change what April's report was entitled to say. Re-deriving April's
answer means filtering on `written_at`, not `occurred_at` — `LedgerRepository.resolved_as_known_at()`
and `PositionRepository.as_known_at()` are that, applied to the two folds that matter.

`at()` returns `None` before the record was known, rather than the first version: *"the store held no
such record"* and *"the store held the first version"* are different answers, and a caller who cannot
tell them apart will report a position the owner did not have.

### 5.2 A chain extends; it never branches

Two records superseding one is a rejected state rather than a merge. A branch gives *"what actually
happened"* two answers, and a store that picks one is quietly deciding which of the owner's
corrections counted. That is `fmis.ledger.LedgerResolver`'s rule, applied to every kind.

---

## 6. The nine repositories

| Repository | Owns | Write verbs that succeed |
|---|---|---|
| `TradeRepository` | `Trade` | `create`, `replace` → appends a `Correction` |
| `LedgerRepository` | the whole event stream | none — read-only, resolves supersession |
| `PositionRepository` | **nothing** | none — every write raises |
| `PortfolioRepository` | `PortfolioSnapshot` | `create` |
| `JournalRepository` | `JournalEntry` | `create`, `replace` → appends a superseding entry |
| `RiskRepository` | `RiskBudget` | `create`, `revise` → appends the next generation |
| `SnapshotRepository` | `MarketSnapshot`, `DecisionWindow` | `create` |
| `AnalysisRecordRepository` | `AnalysisRecord` | `create` |
| `OpportunityRepository` | `OpportunityProposal`, `ProposalLifecycleEvent` | `create`, `append_event`, `replace` (events only), `admit` |

Every one supports the same read surface: `load`, `load_latest`, `history`, `lineage`, `at`, `search`,
`entries`, `load_by_owner`, `exists`, `count`, `all`.

### 6.1 What "by owner" means in a single-owner system

FMITS has exactly one owner, so `load_by_owner` cannot mean a user id — that column would hold the
same value on every row forever. What the owner actually partitions their own activity by is the
triple the domain already refuses to infer: **book** (capacity pools never share), **account** (where
the assets are), **market** (what was traded). Each is optional, because a journal entry about the
owner's own state belongs to no market and inventing one would make a filter silently exclude it.

### 6.2 `PositionRepository` is the §24.3 classification, enforced

`create`, `update`, `replace` and `load` all raise `ProjectionError`. The message names where the
write belongs. `is_reproducible()` folds twice and compares — the CI test the durability
classification rests on, available as a method.

### 6.3 `OpportunityRepository.admit` is where creation rule 4 becomes real

*One live proposal per anchor.* The domain's `admit` needs the live set; only a store knows it. Left
to each caller to remember, the rule would hold until the first caller forgot — and *"one idea
becoming forty proposals"* is the failure it exists to prevent. Whichever the domain decides is
published before it is returned: an admission that was computed and not stored is a deduplication that
did not happen.

---

## 7. Crash safety, and what each gap leaves behind

The publish sequence is **payload → journal → index**, and the order is deliberate: the journal is
truth and the index is a projection of it. The reverse order would produce an indexed record with no
audit trail, which nothing can repair.

| Crash between | What is on disk | Detected by | Repaired by |
|---|---|---|---|
| nothing written | nothing | — | — |
| payload and journal | a complete record nobody indexed | `verify().orphan_payloads` | republishing — idempotent by content |
| journal and index | record + audit trail, no lookup row | `verify().unindexed_writes` | `rebuild_index()`, or a republish that appends **no** second event |
| after index | nothing lost | — | — |

A republish over a lost index restores the row and **nothing else**: `created` is false, no second
event is appended, and the filing date stays the one the record was actually filed on rather than
moving to the retry. `rebuild_index()` will not index a payload with no journal event — inventing a
sequence number would forge the audit trail to complete a lookup table.

---

## 8. Concurrency, and exactly how much is claimed

Architecture §24.4 lists concurrency controls as **not built**, with the measured trigger *"more than
one writer process exists — today there is exactly one."*

What is built is less than that and is stated as such: a `flock`-based exclusive lock held for the
whole of one publish, so the one writer's own two threads cannot interleave a read-modify-write of the
index and the journal. Two writer *processes* remain an unsupported configuration; they no longer
silently truncate each other's index. `expected_existing` on every append turns "someone appended
while I was deciding what to write" from an undetectable interleaving into a refusal.

`fcntl` is POSIX. On a platform without it the lock degrades to no lock, and the store behaves exactly
as it would have without the method — stated here rather than discovered later.

---

## 9. Known limitations

1. **Pruning a `DecisionWindow` is refused.** A window's id and digest cover its *reference* fields, so
   a pruned window is different bytes under the same identity. The store refuses to publish it: its
   first rule is that nothing already published is rewritten, and §24.4 states no measured trigger for
   reclaiming that space. `FrozenRecordError` names the case explicitly. Adding the capability means
   deciding a trigger first.
2. **No export or full dump.** Architecture §5.7 item 4 requires a full-dump export *before the first
   real record is written*. This layer does not provide one. It is the single most important thing
   that must follow.
3. **No CLI surface.** Nothing in `fmits` reads or writes the store yet. The owner can do nothing new
   today; §10 explains why that means no changelog entry.
4. **No composition root fills a `MarketSnapshot`.** The shape is persistable; producing one from the
   engines remains the next slice's work.
5. **The index is read in full on every lookup.** `find` is O(rows). Proportionate at this owner's
   volumes and on the same cost curve ADR-0027 accepted for `manifest.jsonl`; §24.4's manifest trigger
   (5 MB, or a listing over 200 ms) applies here unchanged.
6. **`RiskRepository.evaluate` computes no measurement.** It evaluates values it is given. Deriving
   open risk, drawdown and cluster exposure needs positions, marks and a portfolio snapshot wired
   together — a later slice.
7. **Two writer processes are not supported.** §8.
8. **No schema migration has been exercised.** Every payload version in the repository is 1, so the
   forward-only reader contract is implemented and unproven. A golden-file corpus with one frozen
   sample per version per record type (§5.7 item 2) does not exist yet.

---

## 10. Why there is no changelog entry

`CLAUDE.md`: *"`FMITS_PRODUCT_CHANGELOG.md` — user-visible capability only."*

This milestone adds no user-visible capability. There is no new command and no new output; what it
adds is the ability for the *next* milestone to have one. Recording it as a release would be the exact
failure that rule exists to prevent.
