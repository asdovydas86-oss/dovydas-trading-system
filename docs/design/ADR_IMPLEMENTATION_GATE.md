# ADR Implementation Gate — is architecture finished?

**Milestone:** AQ (gate decision)
**Status:** **Assessment. Not architecture, not an ADR, not a roadmap, not an investigation.** It
decides nothing; it states what blocks code, what does not, and recommends exactly one next action.
**Date:** 2026-08-07
**Repository state:** `75a4f40`, working tree clean apart from the four untracked AQ documents under
review. Every code claim below was executed against this tree, not quoted from a prior document.
**Reads (all re-read from source, no summaries):**
[`TRADING_DOMAIN_ARCHITECTURE_V1.md`](TRADING_DOMAIN_ARCHITECTURE_V1.md) v1.2 ·
[`AP_D1_D2_INVESTIGATION.md`](AP_D1_D2_INVESTIGATION.md) ·
[`../reviews/AP_D1_D2_INVESTIGATION_REVIEW.md`](../reviews/AP_D1_D2_INVESTIGATION_REVIEW.md) ·
[`AP_ADR_DISCOVERY.md`](AP_ADR_DISCOVERY.md) · [`IMPLEMENTATION_ROADMAP_V1.md`](IMPLEMENTATION_ROADMAP_V1.md) ·
[`../../FMITS_PRODUCT_BACKLOG.md`](../../FMITS_PRODUCT_BACKLOG.md) ·
[ADR-0027](../adr/ADR-0027-memory-and-decision-archive-persistence-schema.md) ·
[`../adr/README.md`](../adr/README.md) · `FMITS_WORKING_PROTOCOL_2026-08-06` (read from Drive, in
Lithuanian; translated inline in Part 7)

---

## 0. The verdict, stated first

**We are ready to write code today, and the code we are ready to write is not the code any of these
documents sequences next.**

Three findings carry the whole assessment. Each is verified against the repository, not argued from
the documents.

**Finding I — the owner's stated first priority requires no ADR at all.** The
`FMITS_WORKING_PROTOCOL`'s *"first practical stage"* is a system that scans the top 10–20 liquid
cryptocurrencies and returns swing ideas with **R/R, stop loss, take profit and arguments**. The scan
already exists (`fmits daily`). The setup half does not — and it stores no money, writes no
irreplaceable record and creates no identity, so **none of AP-D1 … AP-D6 gates it.**

**Finding II — that capability is the one thing no document in this repository has designed.**
Measured: `grep -rn "stop_loss\|take_profit\|risk_reward" src/fmis` returns **0 occurrences across
108 source files**. `src/fmis/workspace/sections.py:742-755` renders TRADE PLAN as `Unavailable`,
reason *"Entry, invalidation, stop, target and risk/reward are not computed by this system"*, owner
**EP-13**. `FMITS_PRODUCT_BACKLOG.md` §7 shows **EP-02 (Swing Trading Product — trade plan,
confirmation/invalidation, stop and target logic)** as `LATER · High`, gated by **`AJ`** — and `AJ` has
been DONE since Milestone AK. **The epic that delivers the owner's first priority has been unblocked
and unscheduled the entire time.** `IMPLEMENTATION_ROADMAP_V1` §C8 claims this work is *"no new
analysis logic, only a composition-root step"* and rates it Low-Medium complexity. That claim is false,
and Part 4 shows why.

**Finding III — the real week-one blocker is a guard-test wall nobody has named.** Twenty-three test
files enforce a directional-vocabulary ban. `tests/test_workspace_render.py:141-165` scans the **entire
rendered `fmits swing` page** for `entry`, `target`, `buy`, `sell`, `recommend`, `confidence`, `score`,
`verdict`, exempting exactly four denial sentences — one of which is the TRADE PLAN unavailability
notice itself, asserted separately so deleting it fails a different test. `tests/test_daily_models.py:317`
bans `entry`, `exit`, `target`. `tests/test_workspace_build.py:929` bans `long`, `short`, `stop`.
Emitting a setup through today's surfaces fails these tests **by design**. That is a real architectural
decision — *where directional vocabulary is permitted to live* — and it appears in **none** of AP-D1…D6,
none of the discovery pass's 13 new items, and none of the roadmap's 15 slices.

**So the honest answer to "is architecture finished?" is: yes for the thing it was written about, and
it was written about the wrong thing first.** The trading-domain architecture is thorough, internally
consistent and correct about the *ledger*. The owner's first priority is the *setup engine*, and the
architecture treats it as an input it will consume (`AP` §8.2 lists `stop_loss`, `entry_conditions`,
`take_profit_structure` as fields of a Proposal) rather than as a capability that must be built.

---

# Part 1 — Every AP decision

"First implementation" is ambiguous in every prior document, and the ambiguity is load-bearing. Two
candidate first slices exist, and the blocking answer differs between them:

- **Path L (ledger-first)** — `AP` §32 step 1 and `IMPLEMENTATION_ROADMAP_V1`'s C1. Records the
  owner's fills.
- **Path S (setup-first)** — the working protocol's *"first practical stage"*. Produces the swing idea.

Each decision below is classified for both. The classification test is one question, applied
mechanically:

> **If we implement without deciding this, does a later decision force rewriting code or data that
> already exists?**

Only two kinds of "yes" exist in this system: **byte-level irreversibility** (a change alters stored
bytes → the content digest → `record_id`/`event_id` → every cross-reference) and **capture
irreversibility** (a fact that existed only at one instant and was not recorded). Everything else is
recoverable — projections re-fold, fields are additive, and `AP` §24.3 already classifies which is
which.

| ID | Path L | Path S | Verdict |
|---|---|---|---|
| **AP-D1** money/quantity types | **Blocks first** (3 of 8 clauses) | **May move after** | Split |
| **AP-D2** capture contract + migration | **Blocks first** (field list only) | **May move after** | Split |
| **AP-D3** ledger taxonomy + identity scope | **Blocks first** (Trade only) | **May move after** | Split |
| **AP-D4** decision chain | Blocks later | Blocks later | Postpone |
| **AP-D5** provenance vocabulary | Optional before first release | Optional | Postpone (or write in an hour) |
| **AP-D6** counterfactual policy | May safely move after | May safely move after | Postpone — everyone already agrees |

## AP-D1 — money, quantity, currency types

**Path L: blocks — but only three of its eight sub-decisions do.**

Traced to architecture: `AP` §11.5 derives `event_id` from the canonical digest of a Trade's
authoritative fields; §11.2 puts `quantity`, `price` and `fee_amount` in that set; ADR-0027 §4 makes
`record_id` a function of the digest. The investigation measured (§1.3.9, A.4) that `Decimal("0.10")`
and `Decimal("0.1")` are equal as values and produce **different canonical bytes and different SHA-256
digests** against this repository's own `canonical_dumps`. Therefore the textual form of an amount is a
byte-level irreversibility. Blocking clauses:

| Clause | Why it blocks |
|---|---|
| **Q1 representation** | Determines the bytes |
| **Q2 canonical textual form** | Two domain-equal amounts must produce one digest, or re-entry is not idempotent |
| **Q3 the `float`→exact crossing rule** | A stop price originates in `fmis.level_crossing` as a `float` (§1.3.2) and becomes a stored exact value. The conversion must be fixed before any value is stored, or two records hold two spellings of one price |

**Non-blocking:** Q4 (validate-vs-record — already answered `record` by both the investigation and the
review, and it changes no stored byte); Q6 (rounding ownership — a code convention, testable at any
time); Q7 (adapter original-text capture — no adapter participates in manual entry; it becomes
unrecoverable only for *imported* data, and import arrives at `AP` §32 step 4); Q8 (dust source — dust
governs Position identity, and Position is a rebuildable projection that re-folds).

**Path S: may move after.** A setup engine reads `float` prices from the market half and renders
arithmetic. `AP` §5.3 and AP-D1's own recommendation keep the market half on `float`. Nothing is
stored. No decision is consumed.

## AP-D2 — capture contract and migration guarantee

**This is the decision most mis-ranked by every prior document, and the hostile review already said so
(S3) without anyone acting on it.** §5.7 bundles four rules and calls their conjunction "the migration
guarantee." They are not one decision, and only one of them is irreversible.

| §5.7 item | Blocks Path L? | Why |
|---|---|---|
| **The capture field list** (§22.2 items 1–12) | **Yes** | Capture irreversibility. §22.2 item 10 — the SEK rate at execution — is unrecoverable. It must be on the first Trade or that trade is permanently untaxable |
| **Rule 1: fields additive, never removed/re-typed** | No | This is a *constraint on future edits*, not a thing to build. It binds by being stated, at any time |
| **Rule 2: the migration mechanism** (upcast / generations / rewrite) | **No** | Nothing has two versions. **The default-by-inaction is Option A (never rewrite), which is exactly the recommended answer.** A decision whose do-nothing outcome equals its recommendation cannot block |
| **Rule 4: full dump before the first record** | **No** | A full dump is a read-only walk over the archive. It applies retroactively — the records do not change. §5.7 and §24.5 assert *"before the first real record is written"*; §4 Finding 1 item 3 says *"from the first release"*. The stronger claim is never derived, only asserted |

**Also non-blocking, contrary to the investigation's ranking:** Q8 (freeze the canonical encoder) —
`canonical_dumps` is *already* frozen in shipped, released code at `src/fmis/archive/json_safe.py:50`
and already load-bearing for AO's records. What is needed is a **test**, not an ADR. Q11 (golden
corpus) — one version exists; a matrix of one is a fixture. Q3 (version namespaces) — the archive
already runs with two and works.

**AP-D2 therefore shrinks from eleven sub-decisions to one that blocks: the field list — and §22.2
already enumerates it in full.** There is nothing left to investigate; there is a sentence left to
ratify.

## AP-D3 — ledger event taxonomy and balanced effects

**Path L: blocks, narrowly.** Two things bite on the first record:

1. **Event identity scope** (the review's C1, elevated by discovery as AP-D7). Verified by digest in
   the review: including `recorded_at`, `source` and `capture_schema_version` in the digest makes the
   same fill re-entered twenty minutes after a crash a **second position-moving event**. Idempotency is
   exercised on day one, not in year three. This is byte-level irreversible and the fix is already
   known — ADR-0027 §3 excludes `archived_at` from `content_digest` for precisely this reason and the
   precedent simply was not carried across.
2. **`balance_effects()` for a Trade** — three signed movements, derived not stored (§11.4).

**Non-blocking:** the other five event kinds (Transfer, Reward, Standalone fee, Adjustment,
Correction-as-taxonomy), AP-D3a (rebase fold continuity), AP-D3b (fee uniformity), AP-D3c (whether
`fmis.tax` re-interprets an event). Each is additive and each belongs to the slice that first builds it.
`AP` §11.7 already names all six kinds; enumerating them is not the same as needing them.

**Path S: may move after.** No ledger, no events, no identity.

## AP-D4 — the decision-chain boundary

**Blocks later, both paths.** Its content — five objects, optional links, lifecycle as an append-only
fold rather than stored state — is **already decided in substance** by `AP` §7 and §8.3–§8.4, was
attacked by the hostile review and survived, and has no live alternative on the table. Writing it is
ratification, not deliberation.

Its genuinely open sub-parts are all later: AP-D4a (lifecycle scan cadence) binds when lifecycle events
are computed; AP-D4b (ordering proof) binds when the stream is long enough to lose one; AP-D8 (position
identity under a dust-policy bump) binds when a **frozen** artifact references a position boundary —
which requires Decision Episodes, nine slices away; AP-D10 (proposal identity on re-run) binds when
proposals are stored.

## AP-D5 — provenance vocabulary ownership

**Optional before first release, both paths.** `ValueOrigin` is a five-member enum. Nobody in three
documents proposed an alternative; the review checked it for ADR compliance and found it clean. It is
uncontested, and *"fields may be added, never removed"* (§5.7 rule 1) means a record type can acquire
it later without breaking a reader. It should be written because it costs an hour and prevents three
subsystems reinventing "absent, with a reason" — **not** because anything is waiting on the answer.

## AP-D6 — counterfactual evaluation policy

**May safely move after implementation, both paths, and every document already agrees** — `AP` §31.1
("Step 5, not step 1"), §34.5 ("no new blocking decision"), and `IMPLEMENTATION_ROADMAP_V1` §2 ("not on
this list"). The only forward-compatibility obligation is stamping `counterfactual_assumption_version`
as an opaque string at proposal creation (§8.2), which is one field and is already specified.

---

# Part 2 — Destroy unnecessary ADR work

For every decision: *what breaks if we postpone this until after the first implementation?*

| Decision | What breaks if postponed | Recommendation |
|---|---|---|
| AP-D1 Q1/Q2/Q3 | Ledger identity is undefined; two spellings of one amount become two events | **Keep — on Path L only** |
| AP-D1 Q4, Q6, Q7, Q8 | **Nothing.** Q4 is answered; Q6 is a convention; Q7 needs an adapter that does not exist; Q8 governs a re-foldable projection | **Postpone to the slice that needs each** |
| AP-D2 field list | A trade recorded without its SEK rate is permanently untaxable | **Keep — on Path L only** |
| AP-D2 migration mechanism | **Nothing.** Doing nothing *is* Option A, the recommended answer | **Postpone until version 2 is proposed** |
| AP-D2 full dump | **Nothing.** It applies retroactively to bytes that never change | **Postpone** |
| AP-D2 canonical-encoder freeze | Nothing today — the encoder is already frozen in released code | **Replace the ADR with a pinning test** |
| AP-D3 identity scope | Exchange sync double-counts every typed fill; crash re-entry doubles a position | **Keep — on Path L only** |
| AP-D3a/b/c, other event kinds | **Nothing.** None of those event kinds exists | **Postpone to their slices** |
| AP-D4 (whole) | Nothing before a Proposal or Plan is stored | **Postpone** |
| AP-D5 | Nothing; additive | **Write when convenient — one hour, not a milestone** |
| AP-D6 | Nothing before hypothetical scoring | **Postpone** |
| **AP-D11 durability/freezing ownership** | **Nothing.** Discovery rates this Critical because *other ADRs cite §24.3/§25 as settled*. That is a consistency problem inside the ADR corpus, not a product problem. In the first slice exactly one durability rule matters — **nothing published is ever rewritten** — and that is one sentence, already the behaviour of shipped code (ADR-0027 §6) | **Postpone to the slice that first freezes an artifact (Episode)** |
| **AP-D9 correction propagation** | **Nothing.** There are no frozen downstream artifacts in slice 1. A Correction propagates to exactly one consumer — the Position fold — which recomputes | **Postpone to Episode** |
| **AP-D8 position identity stability** | **Nothing** until a frozen artifact holds a `position_ref` | **Postpone to Episode** |
| AP-D12/AP-D13 shared primitives | Nothing; a one-file refactor at any future date | **Postpone** |
| AP-D14/AP-D15 mark selection | Nothing until a portfolio is valued | **Postpone to the portfolio slice** |
| AP-D16–AP-D19 | Nothing; all four documents already agree | **Postpone** |

**The pattern worth naming.** Eleven of the discovery pass's thirteen "new" decisions describe an
*interaction between two objects*, and in every case at least one of the two objects does not exist.
A decision about how X affects Y cannot block building X when Y is nine slices away and X is
append-only. Severity was assigned by how bad the failure would be, never by when it could first occur —
which is exactly the ranking error the prompt asks Part 8 to correct.

**Net effect: 32 named decisions reduce to 5 blocking clauses, all on Path L, and Path S needs none of
them.**

---

# Part 3 — The real coding gate

> **What is the smallest complete set of accepted ADRs that allows implementation to begin without
> knowingly creating technical debt that forces rewriting the first implementation?**

**Path S (setup engine): the empty set — plus one ADR that no document has named.**

Proof, clause by clause:

| Requirement | Satisfied by |
|---|---|
| Stores no money | Renders `float` arithmetic like `fmits regime` and `fmits facts` do today. `AP` §5.3 keeps the market half on `float` under every AP-D1 option |
| Writes no irreplaceable record | Terminal output. If archived later, it becomes a new record type under ADR-0027's existing, shipped machinery |
| Creates no identity | No digest, no `event_id`, no cross-reference |
| Creates no rewrite debt | The setup **policy** is a function; the Proposal is a **record** that freezes its output. The conversion happens once, at the record boundary, under AP-D1 Q3 — decided later, applied at one call site |

**The one genuinely required decision is not on any list: where directional vocabulary is permitted to
live, and what deterministic policy produces entry / invalidation / stop / target.** ADR-0025 refuses
direction for regime; ADR-0008 refuses it for evidence; ADR-0023 rejected `TrendAgreement` because
classifying a combination belongs elsewhere; 23 test files enforce the ban at the render surface.
Crossing that line is a real architectural boundary and it needs an ADR — written **inside** the
milestone that crosses it, which is this repository's own unbroken precedent (Part 6).

**Path L (ledger): three clauses, not six ADRs.**

1. **AP-D1 Q1 + Q2 + Q3** — representation, canonical textual form, the one named `float`→exact
   crossing rule.
2. **AP-D3's identity-scope clause** — `event_id` covers economic fields only; `recorded_at`, `source`,
   `asserted_by` and `capture_schema_version` are excluded, following ADR-0027 §3's own precedent.
3. **AP-D2's capture field list** — §22.2 items 1–12, already fully enumerated.

**Proof that no fourth clause is needed.** Every remaining candidate fails the irreversibility test:
migration mechanism (default-by-inaction is the recommendation) · full dump (retroactive) · encoder
freeze (already frozen; needs a test) · durability taxonomy (one rule applies, and it is already
shipped behaviour) · correction propagation (no frozen consumers) · position stability (no frozen
references) · every other event kind (additive) · AP-D4/D5/D6 (additive or later).

**This is one to two ADRs and roughly one day of writing, not five acceptance events.** The
investigation and its review together have already produced the text: the investigation's §4.1 and §4.2
give the clauses, and the review's four repairs give the corrections. **What is missing is a decision,
not more analysis.**

---

# Part 4 — Attack `IMPLEMENTATION_ROADMAP_V1`

Fifteen slices, tested against: can it move earlier · later · merge · split · disappear?

| Slice | Verdict |
|---|---|
| **F1 provenance kernel** | **Merge into F2.** Two tiny dependency-free kernels reviewed and merged separately is process overhead the roadmap's own §F1 note half-admits. Value 1/10 |
| **F2 money kernel** | **Keep, and it is the only foundation slice that genuinely must precede C1** — byte-level irreversibility. Its own row rates review complexity High, correctly |
| **F3 archive generalization** | **Move later, or disappear.** It refactors *shipped, production* code with stated Medium regression risk and zero product value, to avoid writing `archive_trade` twice. Two bespoke methods are cheaper than a generic refactor with a characterization-test harness. Generalize when the fourth type arrives, not before the first |
| **F4 full-dump export** | **Move later.** Part 2 shows its "must precede the first record" justification is asserted, not derived. It walks bytes that never change |
| **F5 accounts kernel** | **Merge into C1.** The roadmap keeps it separate because C3 and C6 also need it — but they need it *after* C1, so C1 can own it |
| **C1 Trade + identity + resolver + Correction** | **Keep whole.** The roadmap's rejection of both proposed splits is correct and well argued |
| **C2 Transfer** | **Move later.** Its own row says its value is "mainly a correctness safeguard for what C6 needs later." It gates nothing |
| **C3 Position fold** | **Keep.** Hard dependency on C1, real value |
| **C4 Trade Plan** | **Can move earlier — before C1.** A Plan needs money and accounts, not a Trade. `AP` §9.1 says an unproposed, unexecuted plan is fully valid. Planning discipline (`initial_invalidation`, amendment reasons) has standalone value the day it ships, and it is the object closest to the setup engine's output |
| **C5 history view** | **Keep, or merge into C3.** A read-side composition with no new machinery; a `--plan` flag on `fmits positions` is the roadmap's own alternative and is smaller |
| **C6 Portfolio + metric snapshot** | **Keep** |
| **C7 Proposal, owner-authored** | **Challenge hard.** The owner manually types a setup they already know, and the system tracks its lifecycle. That is a logging feature, not an assistant. Its stated purpose — de-risking storage before C8 wires the generator — is a *developer* benefit paid for with a *user-facing* slice |
| **C8 proposal generation** | **Move to first, and reject its own scoping.** Row 1 claims *"no new analysis logic, only a composition-root step."* Verified false: zero occurrences of `stop_loss`/`take_profit`/`risk_reward` in 108 files, and `workspace/sections.py:742` states the computation does not exist and assigns it to EP-13. Row 9 rates it Low-Medium complexity. **This slice hides the single largest piece of undone work in the plan behind the word "composition."** |
| **C9 capture-completeness report** | **Move later.** Priority #6 work sitting ahead of priority #5 |
| **C10 Decision Episode** | **Keep last.** Correctly placed |

**The structural criticism.** `AP` §32 opens with *"Step 1 is the owner's swing assistant, **not a
foundation for it**."* The roadmap derived from it places five foundation slices and seven capability
slices **before** the swing assistant appears, then rates the assistant itself as trivial composition.
Each slice is locally well-argued; the sequence inverts the design document's own first sentence, and
no local argument could have caught it.

---

# Part 5 — Product value analysis

Score = distance to *"my first working AI-assisted crypto swing trading system"* (10 = it *is* the goal).
Owner priority in brackets.

| Slice | Score | Reasoning |
|---|---|---|
| **C8** proposal generation *(with the setup policy it actually needs)* | **10** [1] | This is the goal. After it, `fmits swing BTCUSDT` produces an actionable setup |
| **C1** Trade ledger | **7** [2] | Manual recording, plus every tax field from day one |
| **C3** Position fold | **6** [3] | "What am I holding and how has it done" |
| **C5** history view | **6** [4] | Planned vs actual, as one view |
| **C6** Portfolio | **6** [3] | First time both halves of the product appear together |
| **C10** Decision Episode | **5** [5] | Learning engine, realized-R only |
| **C4** Trade Plan | **5** [2/4] | Discipline capture; scores higher if moved before C1 |
| **C7** Proposal, owner-authored | **4** [1] | Wears priority 1's label, delivers logging |
| **C9** completeness report | **3** [6] | Reassurance, not capability |
| **C2** Transfer | **3** [2] | Correctness safeguard for a later slice |
| **F2** money kernel | **2** [—] | No value; genuinely irreversible if wrong |
| **F1** provenance · **F3** archive · **F4** full dump · **F5** accounts | **1** [—] | No value each |

**Eight of fifteen slices score under 5.** Justifications, per the prompt's requirement:

- **F2 (2)** — justified. Byte-level irreversibility; nothing that stores an amount may precede it.
- **F1 (1), F5 (1)** — justified only as *hours*, not as milestones. Merge them (Part 4).
- **F3 (1)** — **not justified before C1.** It buys developer convenience at the price of regression
  risk on shipped commands.
- **F4 (1)** — **not justified before C1.** Retroactive by construction.
- **C2 (3), C9 (3)** — justified as small, but neither should precede C10 or C8.
- **C7 (4)** — **not justified before C8.** It occupies the owner's #1 priority slot with a manual
  logging tool while the generator waits behind it.

**The aggregate finding.** Ordering the fifteen slices by score gives almost the reverse of the
roadmap's stated implementation order. The plan front-loads everything scoring 1–2 and back-loads the
only 10.

---

# Part 6 — Challenge AP itself

**Architecture paralysis, measured rather than asserted.** Between 2026-08-06 and 2026-08-07 this
project produced `TRADING_DOMAIN_ARCHITECTURE_V1` (2,152 lines), `AP_D1_D2_INVESTIGATION` (904),
`AP_D1_D2_INVESTIGATION_REVIEW` (495), `AP_ADR_DISCOVERY` (694) and `IMPLEMENTATION_ROADMAP_V1` (652) —
**4,897 lines in two days, zero lines of code, zero ADRs accepted.** More damning than the volume is
the direction of travel:

| Document | Open decisions after it |
|---|---|
| `AP` §31.1 | 6 |
| The investigation | 19 (AP-D1 and AP-D2 alone) |
| The hostile review | 19 + 4 mandatory repairs + 10 findings |
| The discovery pass | **32** |

**Every document produced so far has increased the number of open decisions. None has closed one.**
That is not thoroughness converging on an answer; it is a process with no termination condition. The
discovery pass's own §9 concedes it cannot judge which of its findings are load-bearing, and proposes a
further dedicated investigation into AP-D11.

**The precedent this milestone broke.** All 27 accepted ADRs in `docs/adr/` were written **for a
milestone that then shipped** — ADR-0025 with Milestone AI, ADR-0026 with AL, ADR-0027 with AO. Two
milestones (AK, AN) shipped with **no ADR at all**, because the implementation proved no new boundary.
`AP` is the first design-only milestone in the project's history, and AQ is the first attempt to write
ADRs in a phase separated from the code they govern. **The separation is what produced the paralysis:
an ADR with no implementation pressure has no stopping rule, so every reading finds more.**

**Unnecessary abstraction and future-proofing with no measurable value.**

| Item | Charge |
|---|---|
| **§10 Order** | Fully modelled, then explicitly not tracked in v1 — "recorded only as already-terminal facts supplied by the owner," which is a Trade with extra typing. The five-object argument (§7) is sound in principle and buys nothing until live order state exists |
| **§15 Portfolio Intelligence** | Defended in §34.5 as "a boundary, zero cost." It was not free: it generated AP-D16 and half of AP-D14 in the discovery pass. **Designing a boundary creates decisions about the boundary** |
| **§21 Personal AI Memory** | Same charge. One record type, one promotion rule, and one new open decision (AP-D18: nothing bounds how many provisional insights a model upgrade can generate) for a subsystem at step 8 |
| **§18 AI Context Package** | Correct as a rule ("no model call with input it did not produce") and premature as a record contract, since L8 does not exist |

**Architecture protecting architecture rather than the product.** The clearest instance is **AP-D11**.
Its entire justification is that other ADRs cite §24.3/§25 as settled law that no ADR owns. That is
internal consistency of the ADR corpus. Nothing the owner can do changes based on it. AP-D12 and AP-D13
are the same class — real engineering hygiene, zero product consequence, and both are one-file refactors
at any future date.

**Where AP is genuinely right, and should not be re-litigated.** The append-only ledger with derived
balance effects; refusing fictional P&L by making `HypotheticalOutcome` moneyless; `InsufficientSample`
as a return value; keeping rejected proposals; freezing decision context; the three-input friction
budget; the tax capture/engine split. These are the parts that would be expensive to discover later and
they are already done. **The document's failure is not its content — it is that its §32 named the right
first step and every derived document then buried it.**

---

# Part 7 — Comparison against `FMITS_WORKING_PROTOCOL_2026-08-06`

Read from Drive (`13CkiAihZ8kwQs3ELasuYtt9HBJwgEK_5`), Lithuanian, translated inline.

| Protocol statement | Repository / roadmap reality | Match |
|---|---|---|
| *"Priorities for the coming months: **1. Crypto Swing Trading. 2. AI automation.** Everything else only insofar as it serves these"* | The swing assistant lands at roadmap slice **14 of 15**. AI appears in **zero** of the 15 slices — C8 is explicitly deterministic and the roadmap states model-authored proposals are "far beyond this roadmap" | **Severe mismatch.** Both stated priorities are last or absent |
| *"First practical stage: the system analyses the top 10–20 most liquid cryptocurrencies, gives Swing ideas, **Risk/Reward, Stop Loss, Take Profit and arguments**. The user makes the final decision"* | The scan exists (`fmits daily`). The setup half is **0 lines of code**, unowned by any AP-D decision, and attributed to EP-13 in `workspace/sections.py:742` while `FMITS_PRODUCT_BACKLOG.md` §7 assigns it to EP-02, unblocked since `AJ` and never sequenced | **Severest mismatch.** The named first stage is undesigned, unscheduled and mis-attributed between two epics |
| *"From the first real trade, Swing, **Long-term and Day Trading** trades are recorded"* | C1 delivers Swing and Long-term (`Book` = SWING / INVESTING). Day trading is explicitly excluded — `AP` §28.2 and §33 state intraday risk concepts are "absent from this document" | **Partial mismatch**, correctly disclosed by the architecture rather than hidden |
| *"Data is stored in the system; **Excel is used for export**"* | The export suite is deferred past C10 (`AP` §32 step 10). F4's full dump is a byte-faithful archive, explicitly **not** an Excel projection (investigation Q9) | **Mismatch, minor.** No Excel path exists in the 15-slice plan |
| *"Designed to be ready for Swedish tax accounting and to accumulate the required data automatically"* | C1 captures §22.2 in full from day one; C9 verifies completeness | **Aligned.** The strongest alignment in the whole plan |
| *"AI analyses history, finds mistakes and best strategies, helps continuously improve results"* | C10 delivers realized-R episodes only; cohorts, bias metrics and any AI are past the horizon | **Aligned in kind, deferred in degree** — acceptable, since this is priority 5 |
| *"Opus for complex architecture; Sonnet for long programming work"* | Two days of Opus-grade effort produced 4,897 lines of architecture documents and no code — a correct model choice applied to work Part 6 argues should not have continued | **Process mismatch** |

**The one-line summary.** The plan is well aligned with the protocol's *tax* and *recording*
paragraphs and badly misaligned with the paragraph the protocol itself calls **the first practical
stage**.

---

# Part 8 — If implementation started tomorrow, what stops us in one week?

Ranked by **probability of actually halting work**, not by theoretical severity. Every item verified
against the tree at `75a4f40`.

| # | Blocker | P | Path | Evidence |
|---|---|---|---|---|
| **1** | **The `NOW` slot is empty and the board forbids starting without it.** `FMITS_PRODUCT_BACKLOG.md` §5: *"the next NOW item must be named before the next implementation task on this board begins"* | **Certain** | Both | Backlog §5, §11 rule 5 |
| **2** | **The setup policy is undesigned.** No document states what constitutes a setup, where the stop goes, how targets are chosen, or what R:R qualifies | **Near-certain** | S | 0 occurrences of `stop_loss`/`take_profit`/`risk_reward` in `src/fmis`; no design file; EP-02 unsequenced |
| **3** | **23 guard-test files ban directional vocabulary at the render surface.** `tests/test_workspace_render.py:141` scans the whole page for `entry`, `target`, `buy`, `sell`, `recommend`, `score`; `tests/test_daily_models.py:317`; `tests/test_workspace_build.py:929` bans `stop`, `long`, `short` | **High** | S | Executed against the tree |
| **4** | **AP-D1's canonical amount form is undecided**, so no Trade can be written without choosing `event_id`'s bytes by accident | **High** | L | Investigation §1.3.9, measured |
| **5** | **The event-identity digest scope is undecided and the design as written is wrong.** §11.2's field set breaks idempotency three ways | **High** | L | Review C1, demonstrated by digest |
| **6** | **`WORKSPACE_SCHEMA_VERSION` is 1 and ADR-0027 §8 has no migration.** Adding a section to `Workspace` makes every already-archived workspace unreadable — rejected cleanly, not recoverable | **Medium-High** | S | `workspace/models.py:55`; `archive/envelope.py:37` `frozenset({1})`. **Named by no document.** Avoided by rendering without archiving, or by a new record type |
| **7** | **`RecordType` is a closed two-member enum and `ArchiveStore` has two bespoke methods.** Any new archived type needs a code change first | **Certain, but small** | Both | `archive/envelope.py:45-47`; `archive/storage.py:152,171` |
| **8** | **The test and mutation bar.** 4,194 tests passing under `-W error`, with near-100 % mutation kill on every prior milestone. Any slice will take longer than its estimate | **High — slows, does not stop** | Both | Backlog §4, §8 |
| **9** | `Decimal` is AST-banned in three packages | **Low** | L | Only bites if `Decimal` goes below L7; nothing proposes that |

**Reading of the ranking.** Items 1, 2, 3 and 6 are the realistic week-one wall, and **not one of them
is an AP-D decision.** Items 4 and 5 — the two things every prior document treats as *the* gate — sit
below them and apply only to the ledger path.

---

# Part 9 — One recommendation

## **C — Start implementation.**

**Name as the next `NOW` milestone the deterministic swing setup engine: both directions assessed,
entry conditions, invalidation, stop, targets, R:R, and the evidence for and against — designed, ADR'd,
built, tested and reviewed inside one milestone, exactly as every previous milestone in this repository
was.**

Not option A: further ADR writing does not bring the owner's first priority one day closer, and Part 6
shows the ADR phase has no stopping rule. Not option B alone: skipping ADRs is a consequence of this
recommendation, not the recommendation. Not D: rewriting the roadmap is another document, and Parts 4
and 5 already say what is wrong with it. Not E.

**Defence.**

1. **It is the owner's first priority and the working protocol's *"first practical stage"*, stated in
   both documents in almost the same words.**
2. **It requires none of AP-D1 … AP-D6.** Proven in Part 3: it stores no money, writes no irreplaceable
   record and creates no identity. The only decision it needs — where directional vocabulary may live —
   is not on any current list and is written with the milestone, per this repository's own precedent for
   all 27 ADRs.
3. **It is the design document's own instruction.** `AP` §32: *"Step 1 is the owner's swing assistant,
   not a foundation for it."* This is that sentence followed literally.
4. **The architecture's own reasoning says proposals must exist from the beginning, and nobody applied
   it.** §4 Finding 5 calls the proposal corpus *"the highest-value data in the system"*, and §8.6 makes
   *"did the AI improve my decisions?"* answerable only by comparing owner-authored against
   system-authored proposals over the same markets and periods. **That comparison is unrecoverable in
   exactly the way a missing SEK rate is** — you cannot retroactively learn what the system would have
   proposed on a day it was not running. Every ledger-first month is a month of trades with nothing to
   compare them against. The architecture supplies this argument and every document derived from it
   sequenced against it.
5. **It creates no rewrite debt.** The setup **policy** is a function; the `OpportunityProposal` is a
   record that freezes its output with provenance. The same function serves both. The `float`→exact
   conversion happens once, at the record boundary, under AP-D1 Q3 — decided later, applied at one call
   site. This is the same foundation-then-capability shape the roadmap uses everywhere else.
6. **The ledger's ADRs then get written when they gate something real**, narrowed to the three clauses
   Part 3 proves — roughly one day, from text the investigation and its review have already produced.

**What this recommendation costs, stated plainly.** Tax capture starts later than a ledger-first plan,
and §22.2 items 9–10 are unrecoverable for any trade made in the interval. That cost is bounded (no
trades are being captured today under either plan) and mitigable — the working protocol already names
Excel, and a spreadsheet of date, pair, quantity, price, fee and SEK rate is a complete §22.2 capture
that C1 can import later through the statement adapter §23.3 already specifies. **If the owner judges
that cost unacceptable, the correct alternative is Path L with the three clauses from Part 3 — not more
ADR analysis.** Either way, the answer to the question this document exists to settle is the same.

---

## Are we ready to write code?

**Yes.**

For the owner's first priority, today, with no accepted ADR. For the ledger, after one day of writing
that binds three clauses whose text already exists in the investigation and its review.

**Architecture is finished. What is missing is a decision and a milestone, and neither of those is a
document.**

---

*No ADR was written. No option was bound. No backlog, README or architecture file was edited. Nothing
was committed. Every code, test and file claim above was executed against the repository at `75a4f40`.*
