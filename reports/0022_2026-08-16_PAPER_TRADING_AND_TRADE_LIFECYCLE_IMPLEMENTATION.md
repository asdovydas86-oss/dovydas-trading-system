# Report 0022 — Paper Trading & Trade Lifecycle Engine (Milestone BO) — Implementation Record

| Field | Value |
|---|---|
| **Report number** | 0022 |
| **Title** | Paper Trading & Trade Lifecycle Engine (Milestone BO) — Implementation Record |
| **Date** | 2026-08-16 |
| **Report type** | Implementation |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `e4195fc` — the production code and tests of this milestone, committed on top of `51814b1`. This record and the product documents are committed directly on top of it |
| **Status** | Final |

---

## 1. What shipped, in one sentence

FMITS can now simulate the complete deterministic life of a swing trade — activate a commitment,
watch a stop-entry trigger on a closed candle, trail the stop, take a partial exit at the first
target, close on the second, and freeze what happened — with no broker, no order, no exchange, no
model and no guess.

**Two new packages, four new record types, one new command and six new `fmits trade` subcommands.**

```
fmis.trade_lifecycle   5 modules   the domain: what is stored, and the two folds
fmis.paper            12 modules   the engine: the one candle crossing, the simulator, the surfaces
```

Plus `fmis.pipeline.candles` (the one place a venue is named for a replay), one new repository,
and a twelfth top-level command, **`fmits simulate`**.

---

## 2. The design in five decisions

### 2.1 The lifecycle is a fold, and no state is stored

`TradeLifecycleEvent` is append-only; `fold_trade_lifecycle` is the only place a state exists. The
**mechanism** is `ProposalLifecycleEvent`'s, reused; the **vocabulary** is not. `AP` §7 is explicit
that Proposal, Plan, Order, Trade and Position are five objects because each occurs without the
next, and collapsing two of their lifecycles into one enum would lose exactly the behaviours that
table names.

Ten states. `TRIGGERED` and `OPEN` are two, because *the condition was met* and *the fill happened*
are different facts a bar apart under a market entry. `PARTIALLY_EXITED` **is** a state here and
deliberately is not one on `Position`: a position is a fold over fills where a partial exit changes
the numbers without changing what the position *is*; an activation is an instruction, and *"two of
the three rungs have filled"* decides which rungs the next bar may still fill.

`PROPOSED` is **absent**, and its absence is the design: it already exists as `ProposalState`, and
`fmis.paper.compose` joins the two streams (§2.5) rather than duplicating one.

**Illegal transitions raise** — the brief's requirement, in one table, with no silent no-op.

### 2.2 A simulated fill is a real ledger `Trade` under `Book.PAPER`

`AP` §5.5 already says what the book means. So the position fold, the exposure engine, the
constraint engine, the valuation and `fmits today` all work on a paper trade with **no new code** —
the brief's *"reuse the existing architecture"* satisfied by construction rather than by a parallel
implementation. A test asserts that a paper fill reaches no real-money aggregate
(`DEFAULT_EXCLUDED_BOOKS`), and a live `fmits portfolio` run over a store holding an open paper
position reported *"no open position in the covered books."*

`LedgerSource` gained a fourth member, `PAPER_SIMULATION`. A fill the owner did not type is not
their assertion, and a surface that could not tell the two apart would be rendering a lie of
omission.

### 2.3 The stop moves by appended event, and the plan is never touched

`AP` §9.3, built for the first time. `fmis.plan` shipped with `PlanAmendment` deliberately unbuilt
and said so; this is that debt's second half, narrowed to the **stop** because that is the field
with a behavioural metric attached. `TradePlan.initial_invalidation` never changes — not a rule, an
absence of any code path — and what moves is `fold_stop_history`'s answer.

Three properties are enforced rather than documented: the chain is **validated** (an amendment whose
`previous_stop` does not match what the last one left is a refusal, not a repair); a `POLICY_DERIVED`
amendment **may only tighten**, refused at read time as well as at write time so a store containing
one is rejected rather than quietly measured; and a **tightened** stop still honours the commitment,
because counting it as a departure would make the metric read as indiscipline every time the owner
did the right thing.

### 2.4 What `TradeOutcome` deliberately does not store

`AP` §25.2 splits a finished trade's figures in two, and this record is the line. MAE, MFE, the bar
count, the exit reason and the stop in force at the exit are **frozen** — *"kline history is not
permanent and instruments get delisted."* Realized P&L, average entry, average exit, R-multiple and
P&L percentage are **absent from the record**, because §25.2 classes them as projections over a
ledger that is permanent, and storing them would be the fourth place one fact lives and the first to
disagree with a `Correction`.

The excursions are stored as **prices**, not as money and not as R. Money needs a quantity that
changed with every partial exit; R needs an entry the ledger owns. Freezing either would freeze a
quotient, which `AP` §5.3 says is never a stored field.

### 2.5 The proposal's own lifecycle is carried forward — to `TRIGGERED`, and no further

When an activation names a proposal, the entry trigger is appended to **that proposal's own stream**,
so `PROPOSED → PENDING → TRIGGERED → OPEN` is one readable history across two objects.

`EXECUTED` is **not** appended, and that is a decision rather than an omission: §8.4 defines it as
*"a Trade referencing this proposal landed"*, and a paper fill is not that. Recording one as an
execution would put simulated activity into the acceptance rate, the invalid-entry rate and every
other §20.5 behavioural metric computed over the proposal corpus.

And only when the proposal's own fold makes it legal. `ENTRY_TRIGGERED` requires `DECIDED`, so a
proposal the owner never decided on is left untouched and the skip is **reported on the page**.
Forcing it would mean loosening another package's transition table for a simulator's convenience.

---

## 3. Six refusals, and why each one earns its place

| # | The refusal | What it prevents |
|---|---|---|
| 1 | No intrabar path is invented. The engine asks *"was this level touched"*, never *"in what order were two levels touched"* | ADR-0021's guess, at the level that costs money |
| 2 | **The bar's open resolves what it genuinely can.** A bar that opened past the stop reached it at the first price of the bar, and nothing inside can have preceded it | Most false ambiguity, without inferring a path |
| 3 | **Everything still ambiguous halts.** A bar that opens between the stop and a target and reaches both records what could not be ordered and stops | A coin flip, a candle-colour guess, or a resolution to the flattering side |
| 4 | **An entry that filled inside its bar and a bar that also reached an exit level halts** | §5.2 — the flattering asymmetry the first draft introduced |
| 5 | **A run's candle window is bounded at both ends** | §5.1 — a report about the fetch rather than about the trade, and a past-dated run reading candles from its own future |
| 6 | **Costs are a named, versioned policy at zero** | A zero that reads as an omission rather than as a choice |

`AMBIGUOUS` is a **halt, not a terminal state**. The owner resolves it through the path that already
exists — recording the exit they judge they would have taken — and that exit is `ASSERTED` beside
`MEASURED` fills, which is exactly the distinction `ValueOrigin` exists to carry.

---

## 4. The gap rule, written once

A level fills **at the level**, unless the bar's **open** was already past it, in which case it fills
**at the open**. Two lines, applied identically to a favourable gap (a limit that filled better) and
an unfavourable one (a breakout that filled worse). Rounding that asymmetry towards the owner is the
single commonest way a paper record flatters itself, and writing the rule once is what makes it
impossible here. A mutation probe that removes the gap branch is detected; so is one that inverts
which side each entry type waits on.

---

## 5. Findings — every one recorded rather than quietly fixed

Five were found by an adversarial review of the shipped code, one by the live run, three by mutation
probes against a suite that was already green, and **one by the release gate itself** — after the
review, the probes and the live demonstration had all passed (§5.9).

### 5.1 P1 — the entry-bar deferral was systematically favourable *(fixed)*

The first draft deferred every exit test to the next bar whenever an entry filled at its level
rather than at the bar's open, and called the deferral symmetric because it withheld a stop and a
target alike. **It is not symmetric in effect.** A breakout entry fills near the top of its bar, so
the level the remainder of that bar is most likely to reach is the **stop**. Skipping it silently
made every stopped-out breakout survive one bar longer than it did — the exact flattering asymmetry
the engine is written against, introduced by the rule meant to prevent it.

What ships: a quiet bar defers; a bar that reached the stop **or** a target halts. One code path,
both levels, no side favoured. Design record §7.3.

### 5.2 P1 — the outcome transition wrote no journal entry *(fixed)*

The brief's §11 is *"every lifecycle transition must generate journal events. No silent state
changes."* Twelve of the thirteen did. `OUTCOME_RECORDED` — the one event that says a trade is over —
was written to the lifecycle stream and not to the owner's own history. A test now asserts the
journal's tag set is a superset of the stream's kinds, so a future kind cannot be added silently.

### 5.3 P1 — `fmits trade status` and `fmits trade lifecycle` could not show the monitoring block *(fixed)*

Found by the live run. Both commands read the store offline, so MFE, MAE, bars in trade, the mark and
both distances came back `Absent` on every open trade — honest and useless, against a brief that
lists all six as position-monitoring outputs. Both now fetch closed candles for the markets they
show, degrade to the store-only reading when the provider cannot answer, and take `--offline` for a
run with no network.

### 5.4 P2 — a run's candle window was bounded at one end only *(fixed)*

Found by the live run: a two-day-old activation reported **999 bars advanced**, because a provider
page reaches back forty-one days. Worse in the other direction: `--reference-time` in the past reads
live candles that closed after it, and the events that would be written carry an `occurred_at` later
than their own `recorded_at` — a refusal the domain raises correctly and cryptically, two layers
down. `bars_for_run` now bounds both ends, and the read path uses the same window so a monitoring
reading cannot report an excursion over bars the trade was never exposed to.

### 5.5 P2 — the proposal bridge could write an event the fold would refuse *(fixed)*

The bridge read the proposal's state, found `DECIDED`, and appended `ENTRY_TRIGGERED` — but when the
decision and the entry bar share an instant, the proposal's own fold cannot order them, and the
*combined* stream is illegal. **A read that succeeded before the write is not a promise the write is
legal.** The bridge now folds the stream *with* the new event before publishing and reports the skip.
The same discipline was applied to `amend_stop` and `cancel_activation`, where it turned a
cancellation of an open position from a write that only failed on the next read into a refusal.

### 5.6 P2 — a publish of an already-stored event was a byte-level conflict *(fixed)*

`recorded_at` is excluded from every record's digest and kept in its stored payload, both for stated
reasons. The consequence is that re-publishing an event the store already holds is neither an
idempotent success nor a correction — it is a `FrozenRecordError`. Since the whole resume design is
*"replay from the beginning every time"*, that made a second run over a still-live trade fail.
`_publish_once` asks first; the first run's `recorded_at` stands, which is correct, because that is
when this system actually learned of it. The green test that hid this asserted idempotence over a
**finished** trade, which is not live and therefore never replays.

### 5.7 P3 — a warning that could never fire *(fixed)*

`PT-W6` asked whether a trade's journal was empty. It never was: activating writes a note, so the
cheapest discipline metric in the system would have read *"the owner wrote something"* about every
trade in the store from the moment it existed. It now counts only entries the engine did not author.

### 5.8 Three test gaps found by mutation probes against a green suite *(fixed)*

* A closed trade read **offline** had no stateable total R — the known-zero branch had no test.
* A trade that had never filled reported a **partial total** rather than an absence.
* The **same bar advanced twice** was refused by the code and by no test, so an excursion inflated by
  a re-run would have gone unnoticed.

And one more the probes found on the second pass: **no test asserted that an R multiple rests on the
initial stop**, so measuring against the effective one — which collapses every R to an absence the
moment break-even fires — survived.

### 5.9 P1 — every **finished** paper trade was invisible on `fmits today` *(fixed)*

Found by the independent release gate, after the suite was green, coverage was 100 % and the live
demonstration had passed. `paper_trading()` bucketed views into a dict with **six hard-coded keys**
and read **five** of them. The engine freezes an outcome the instant a trade closes, so a finished
trade folds to `RESOLVED` — not `CLOSED` — and `setdefault("resolved", …)` quietly created a bucket
nothing read. The day's page therefore showed a trade through every state **except the one the owner
most wants**, and `PaperTrading.is_empty` reported *"none has finished"* about a store full of
finished trades.

Every earlier test and the live run used **unfinished** trades, which is why 442 tests, 100 %
branch coverage and 45 mutation probes all missed it: no probe can flip a branch that no test
reaches with the state that exposes it, and the missing key was not a branch at all.

What ships: the buckets are **derived from `TradeLifecycleState`**, so a state added later cannot be
dropped silently; `_FINISHED_STATES` names the five states the owner reads as *over*; and a guard
asserts the union of the section's five lists **equals** the enum as a set. This is the same class
as `5.7` — a surface that could not express a fact the domain could — and the second time in this
milestone that a mismatch between the fold's vocabulary and a surface's assumption produced silence
rather than an error.

### 5.10 Not fixed, and recorded

**`PT-9` — a non-terminating R multiple prints a long tail.** `0.4488...` renders exactly;
`-0.19321911152668536750820453` does not stop. This is `BN`'s own finding, inherited unchanged:
shortening it would be a rounding policy this system does not set. The fix that would close it —
carrying the pair and showing the division, as `AverageCost` and `RiskRewardReading` already do —
is recorded here as the recommendation rather than applied, because it changes a public type's shape.

**`PT-8` — a paper fill carries a placeholder FX rate of `1`.** `Trade` requires one because it is
unrecoverable later; a paper fill has no tax consequence, `Book.PAPER` is in
`DEFAULT_EXCLUDED_BOOKS`, and no tax engine exists. The rate is `1` and the **source** says so in
words, which is the only version of this a future tax engine cannot mistake for a real rate.

---

## 6. Verification

| Check | Result |
|---|---|
| Full suite | 7,359 → **7,805 tests** (+446, in 15 new files), passing identically under `-W error` |
| Coverage | **100 % statement and 100 % branch** of all 19 new and 7 modified modules — 4,193 statements, 1,220 branches, 0 missed |
| Mutation | **45 probes, 45 detected, 0 survivors**, byte-identical restoration verified by SHA-256 with the bytecode cache cleared before every run |
| Public exports | 905 → **1,045**, **0 collisions** |
| Import cycles | **0**, across the whole repository |
| Runtime dependencies | **0 new** — standard library and `fmis` only |
| Cold import | `import fmis.pipeline` loads neither new package |
| Store verification | `store.verify()` reports `ok` after a full simulation: chain, payloads, index, orphans, lineage |
| Live | Real Binance data, 2026-08-16 |

**Three probes were badly written and are recorded as such** — two were no-ops dressed as mutations
(`fraction * Decimal(1)`; an `if False else` that changed nothing) and one matched twice. All three
were rewritten to be genuine before the run that reports zero survivors, because a probe that cannot
fail is a probe that proves nothing.

### 6.1 Guards

`tests/test_paper_architecture.py` asserts, as executable checks over the source tree:

* `fmis.paper.bars` is **the only module in either package that imports `fmis.data`** — asserted as a
  set, because the domain half is imported by `fmis.persistence` and a market-half import there
  would make the store transitively depend on a candle decoder;
* the domain half's whole dependency surface, as a set, and that it never imports the store;
* no module in either package imports a venue provider, names an exchange in its executable text,
  reads a clock, reaches for a random number, holds a path, opens a file, names an execution verb
  (`place_order`, `submit_order`, `cancel_order`, `execute_trade`, `api_key`, `websocket`,
  `telegram`) or names a model, a prediction or a probability;
* the computing modules invent no threshold — every numeric literal is `0` or `1`, with **one named
  exemption**: `CAUSAL_RANK`'s integers are positions in a sequence, not numbers any measurement is
  compared against, and the exemption is written where a reader will find it;
* no float literal anywhere in either package;
* the read path names no write verb; four record kinds are registered and the engine half stores
  nothing of its own; every projection has `to_payload` and no `from_payload`;
* the layering runs one way from models outwards, and there are no cycles inside either package;
* three consumers reach the two packages and all three are named: `fmis.persistence.kinds`,
  `fmis.persistence.lifecycle_repositories`, `fmis.pipeline.cli`, `fmis.today.builder`;
* `fmis.pipeline.candles` contains no arithmetic operator of its own.

**ADR-0028's directional boundary was not widened and no exemption was taken.** Both packages branch
on which way a trade points — a simulator must, to decide whether a stop is above or below — and
neither names a side. `TradeDirection.sign` was added to `fmis.snapshotting`, where the enum already
lives and where the exemption already exists, and every comparison in 7,684 lines of new code is
arithmetic over that number. A test asserts both packages are absent from both exemption lists and
present in the covered set.

Two existing guards were widened inside their own stated extension points, each with its
justification recorded in the test: `fmis.paper` joins the four application-layer packages the CLI
may import, and `lifecycle_repositories` joins the store's layering order.

### 6.2 Live verification, 2026-08-16, real Binance data

A store built entirely through the product's own commands:

```
fmits trade plan BTCUSDT --direction long --book paper --stop 62200
    --target 63300 --target 64200 --confidence moderate --setup range_reclaim
fmits trade activate <PLAN> --size 0.4 --entry-type limit --entry 62800
    --share 0.5 --share 0.5 --break-even-r 1 --trail-r 2
fmits simulate --all
```

79 real closed 1h bars advanced. The limit filled at **exactly 62800** on the 2026-08-14T08:00 bar
that came back to it; 47 bars in trade; MFE 63247.05 (0.745 R) and MAE 62535.24 (−0.441 R) measured
from real candles; unrealized 0.44885 R against an initial risk of 240 USDT; break-even correctly
**not** fired, because 0.745 R had not reached the 1 R the owner stated. `fmits trade status`,
`fmits trade history`, `fmits trade lifecycle` and `fmits today` all rendered, exit code 0.

**Idempotence was verified at the byte level on a live store**: a second `fmits simulate` over the
same candles reported *"0 new of 8"* and left a `shasum` over every file in the store unchanged.

**Paper/live isolation was verified live**: `fmits portfolio` over a store holding an open 0.25 BTC
paper position reported *"no open position in the covered books."*

---

## 7. What this does not do

Everything in `PAPER_LIMITATIONS`, printed at the foot of every page in the package: no exchange is
reached and a paper fill is not a trade; costs are modelled at zero under a named policy; a level is
filled on touch and real liquidity at that price is not modelled; an ambiguous bar halts; funding,
borrow, liquidation and spread are not modelled; excursions are measured on the simulation
interval's closed bars only, so a wick on a finer interval is invisible; paper is excluded from every
real-money aggregate; a paper fill's FX rate is a placeholder; and a non-terminating R multiple
prints a long tail.

Beyond those: no `PlanAmendment` for targets, size or expiry; no venue `Order`; no walk-forward
harness, no shadow mode and no execution validation — the engine is written as `(state, bar) →
events` precisely so those are the same function driven by a different sequence, and none of them is
built here.

---

## 8. Files

**New production** — 17 modules, 7,684 lines: `src/fmis/trade_lifecycle/` (5), `src/fmis/paper/`
(12), plus `src/fmis/pipeline/candles.py` (141) and
`src/fmis/persistence/lifecycle_repositories.py` (339).

**New tests** — 15 files, 8,168 lines, 446 tests.

**Modified production** — 15 files, all additively: `ledger/models.py` (a fourth `LedgerSource`),
`snapshotting/readings.py` (`TradeDirection.sign`), `persistence/{__init__,base,composition,kinds}.py`
(four record kinds, an eleventh repository), `pipeline/cli.py` (a twelfth command and six
subcommands), `today/{__init__,builder,models,render,sections}.py` (an eighth section,
`TODAY_SCHEMA_VERSION` 2 → 3), `trade_capture/{__init__,capture,inputs}.py` (`record_plan`,
`entry_side`, `exit_side`).

**`TODAY_SCHEMA_VERSION` moved 2 → 3.** A consumer reading a version-2 page against a store full of
live paper trades would render none of them, which is a different claim from *"this page did not
check"*.
