# Paper Trading & Trade Lifecycle Engine v1 — Design

**Milestone:** BO
**Status:** Implemented. This document records the design the implementation was written to, and
every deviation it forced. **Revision v1.1** — §7.3 and §7.5 revised after the hostile review found
that the first draft's entry-bar deferral was systematically favourable, and that a run's candle
window was bounded at one end only. §13 records the disposition of every finding.
**Builds on:** [`TRADING_DOMAIN_ARCHITECTURE_V1.md`](TRADING_DOMAIN_ARCHITECTURE_V1.md) §5.5 (books,
and `PAPER` as one of them) · §9.3 (amendments are events, never edits) · §10 (Order, and why v1
deferred it) · §12 (Position as the fold) · §25.2 (what is frozen, and the MAE/MFE rule) ·
[`TRADING_DOMAIN_DATA_MODEL_V1.md`](TRADING_DOMAIN_DATA_MODEL_V1.md) §10.3–§10.4 ·
[ADR-0021](../adr/ADR-0021-change-of-character-foundation-v1.md) (intrabar order is unknowable
without sub-bar data) · [ADR-0019](../adr/ADR-0019-level-crossing-foundation-v1.md) (a crossing is a
fact) · [ADR-0028](../adr/ADR-0028-directional-interpretation-boundary.md) ·
[`SWING_SETUP_BACKTEST_V1.md`](SWING_SETUP_BACKTEST_V1.md) (the replay transport this milestone
reuses unchanged) · reports 0014–0021.

---

## 1. The capability that was missing

Before `BO`, FMITS could detect a setup, size it, approve it, record a fill the owner had already
taken, fold it into a position, value the portfolio and print the day's page. What it could **not**
do is *simulate the complete life of a swing trade*: activate a commitment, watch a stop-entry
trigger on a closed candle, hold the position while the stop trails, take a partial exit at the
first target, close on the second, and record what happened — deterministically, with no broker and
no guess.

That is one sentence, and it is the whole milestone.

**This is paper trading only.** No exchange execution, no broker adapter, no API credential, no
websocket, no order routing, no automated trading. Everything below is a pure function of closed
candles the system already fetches.

---

## 2. What is *not* built, and why that is the design

| Not built | Why |
|---|---|
| A venue `Order` (§10) | §10.3 defers it with a stated trigger — exchange read-only sync — and nothing here places anything at a venue. A `TradeActivation` is an *instruction to the simulator*, and calling it an order would make a future real order the second thing with that name. |
| A general `PlanAmendment` (§9.3) | Only the **stop** moves in this milestone, and the stop is the field with a behavioural metric attached (§20.5, *"stop integrity … the highest-value single behavioural metric"*). A record type that could move targets, size and expiry, with nothing writing three of those four, is weight without value. `StopAmendment` is §9.3 narrowed to what is used, and widening it later is additive. |
| A `PROPOSED` state of its own | It already exists, as `ProposalState.LIVE`/`DECIDED` in `fmis.proposal`. §6.4 below **joins** the two streams rather than duplicating one. |
| Fees, slippage, funding, spread, depth, partial-fill-by-liquidity | This system ingests no data that bounds any of them. §7.4 states what is modelled instead, as a named policy at zero, rather than as an omission. |
| A resolution of an ambiguous bar | §7.3. ADR-0021's refusal, applied. |

---

## 3. Two packages, and where the line runs

```
fmis.trade_lifecycle    the domain      exact values only · no candle · no store · no clock
fmis.paper              the engine      the one candle crossing, the simulator, the surfaces
```

The split is the same one `fmis.plan` / `fmis.trade_capture` and `fmis.portfolio_risk` /
`fmis.valuation` already draw, and it exists for a hard reason: `fmis.trade_lifecycle` owns four
**persisted record types**, so `fmis.persistence.kinds` imports it — and a domain package that
`fmis.persistence` imports must not reach the market half, or the store transitively depends on a
candle decoder.

`fmis.paper.bars` is **the only module in either package that imports `fmis.data`**, and a guard
asserts it as a set. It is where a `float` OHLC bar becomes an exact `PriceBar`, through
`fmis.money.exact_from_market_price` — the repository's one `float`→exact crossing, reused rather
than reinvented.

### 3.1 Module layout

```
fmis/trade_lifecycle/
  models.py     EntryType · ExitLeg · ExitLadder · BreakEvenRule · TrailingRule
                StopManagement · TradeActivation · PriceBar
  events.py     TradeLifecycleKind · TradeLifecycleState · TRANSITIONS · CAUSAL_RANK
                TradeLifecycleEvent · TradeLifecycleView · fold_trade_lifecycle
  stops.py      StopAmendment · STOP_REASONS · StopHistory · fold_stop_history
  monitor.py    Excursion · TradeMonitor · monitor_trade
  outcome.py    ExitReason · TradeOutcome · OutcomeReading · read_outcome

fmis/paper/
  models.py     PaperError · PaperCostPolicy · FillKind · Fill · StepResult · SimulationResult
  fills.py      the fill arithmetic — pure, exact, no candle
  bars.py       bar_from_candle · bars_from_series          ← the only fmis.data import
  engine.py     advance() — one closed candle at a time
  replay.py     replay_bars() · replay_series()
  views.py      the read path over the store
  compose.py    the write path and the composition root
  inputs.py     text → domain, for the CLI
  render.py     the pages
```

---

## 4. The lifecycle is a fold, not a stored status

`TradeLifecycleEvent` is append-only and immutable; the state is **never stored**. This is the
mechanism `ProposalLifecycleEvent` already established, and reusing the *mechanism* rather than the
*type* is deliberate: a proposal's states describe a suggestion, and these describe a commitment
that has money behind it.

### 4.1 States

| State | Meaning |
|---|---|
| `PENDING` | Activated. The entry condition has not been met. |
| `TRIGGERED` | The entry condition was met on a closed candle. No fill yet. |
| `OPEN` | An entry fill exists. |
| `PARTIALLY_EXITED` | At least one exit fill, and exposure remains. |
| `CLOSED` | Exposure is flat. |
| `CANCELLED` | The owner withdrew it before any fill. |
| `EXPIRED` | `expires_at` passed with no entry. |
| `SUPERSEDED` | Replaced by a later activation for the same commitment. |
| `AMBIGUOUS` | **Halted.** One candle contained two events whose order decides the answer. §7.3. |
| `RESOLVED` | Terminal. An outcome was computed and frozen. |

`TRIGGERED` and `OPEN` are two states and not one, and the split is the same one §8.4 draws between
`ENTRY_TRIGGERED` and `EXECUTED`: *the condition was met* and *the fill happened* are different
facts, they can be separated by a bar under a `MARKET` entry, and merging them makes the delay
between them unmeasurable.

`PARTIALLY_EXITED` **is** a state here, where `PositionState` deliberately has no such member. The
two are not in conflict and the difference is the subject: a `Position` is a fold over fills, where
a partial exit changes the numbers without changing what the position *is*; an activation is an
*instruction*, and *"two of the three legs have filled"* is genuinely its state — it decides which
legs the next bar may still fill.

### 4.2 Illegal transitions raise

`TRANSITIONS` is the whole legal machine in one table. An event whose kind is absent from the
current state's row is an `IllegalLifecycleTransitionError` — never a silent no-op and never a
best guess.

### 4.3 Same-bar events

Two events caused by one closed candle are ordered by `CAUSAL_RANK`, a fixed table derived from the
state machine's own shape (`ACTIVATED` < `EXPIRED` < `TRIGGERED` < `ENTRY_FILLED` < `STOP_AMENDED` <
`PARTIAL_EXIT_FILLED` < `EXIT_FILLED` < `AMBIGUOUS_BAR` < `OUTCOME_RECORDED`).

**This is not the ordering ADR-0021 forbids.** The ranks order events whose sequence is a *logical
consequence of the machine* — a fill cannot precede the trigger that caused it — and never events
whose sequence is an *observation about price*. The one case that is genuinely an observation about
price is the one the engine refuses outright (§7.3), so the fold never has to arbitrate it. Two
events sharing a bar **and** a rank is a rejection, not a coin flip.

---

## 5. Records

Four new `RecordKind`s. Eleven → fifteen; ten repositories → eleven.

| Record | Durability | Shape | Why |
|---|---|---|---|
| `TradeActivation` | Captured artifact | Record file | What was activated, at what size, with which entry type, ladder and stop management. Frozen: changing it after the market moved is the failure `TradePlan` exists to prevent, one layer out. |
| `TradeLifecycleEvent` | Source of truth | Event log | Append-only; a wrong event is superseded by a later one carrying `supersedes`, the identical mechanism the ledger uses for a `Correction`. |
| `StopAmendment` | Source of truth | Event log | §9.3. Append-only. `initial_invalidation` is never touched. |
| `TradeOutcome` | Captured artifact | Record file | §25.2: MAE/MFE are frozen at close *"because candle history may become unfetchable"*. |

### 5.1 What `TradeOutcome` deliberately does **not** store

Realized P&L, R-multiple, PnL %, average entry and average exit are all absent from the record.
§25.2 classes them as **projections** — *"pure fold, recomputable: yes"* — and the ledger they fold
over is permanent. Storing them here would be the fourth place the same fact lives and the first to
disagree with a `Correction`.

What the record holds is exactly what cannot be recomputed once candle history is gone: the
excursions, the bar count, the exit reason, the effective stop at exit, the interval the excursions
were measured on, and the policy versions in force. `OutcomeReading` folds the record together with
the ledger at read time and produces every figure the brief's §6 asks for — including the two
quotients, computed and never stored, exactly as `AverageCost` and `RiskRewardReading` already do.

### 5.2 A paper trade's fills are real ledger `Trade` records

`Book.PAPER` already exists and §5.5 already says what it means: *"Paper events live in the same
ledger under `PAPER`, are excluded from every real-money aggregate by default, and use identical
sizing, fee and risk logic."* So the simulator writes **`Trade` records**, and the position fold,
the portfolio, the exposure engine, the constraint engine, the valuation and `fmits today` all work
on a paper trade with **zero new code**. That is the brief's §12 and §13 satisfied by construction
rather than by a parallel implementation.

Every simulated fill carries `source=LedgerSource.MANUAL`? **No** — a fourth `LedgerSource` member,
`PAPER_SIMULATION`, is added, because a simulated fill the owner did not type is not a manual
assertion and a surface that cannot tell them apart is rendering a lie of omission. This is an enum
extension and therefore a capture-schema concern; `SUPPORTED_TRADE_VERSIONS` is unchanged because
the *payload shape* is unchanged, and a build that does not know the member rejects it cleanly,
which is the existing contract.

`asserted_by` is the simulator's own policy id, not a person.

### 5.3 The activation does not carry the stop

The stop is `TradePlan.initial_invalidation` and lives in exactly one place. The activation names
`plan_id`; the *effective* stop at any instant is `fold_stop_history(plan, amendments, at)`. Two
fields that could disagree about the same fact would be one field too many.

---

## 6. The engine

### 6.1 One closed candle at a time

```
advance(state, bar) -> StepResult(events, fills, amendments)
```

Pure. No clock, no store, no network, no randomness, no model, no prediction. `state` carries the
activation, the plan, the effective stop, the folded lifecycle state, the remaining quantity, the
legs already filled and the excursion accumulator. `bar` is an exact `PriceBar`.

Determinism is not a hope: the same bars in the same order produce byte-identical events, and a
test replays a series twice and compares digests.

### 6.2 No lookahead

Three independent mechanisms, any one of which alone would be sufficient:

1. Only **closed** candles ever reach the engine — `CandleSeries.closed()`, the existing rule.
2. `bars_from_series` refuses a bar whose `is_closed` is false, rather than filtering it silently.
3. The engine reads exactly one bar per call and holds no forward index.

Replay over history reuses `fmis.swing_setup.backtest_replay`'s existing raw-kline cache and replay
transport unchanged — the mechanism `AV` already proved, not a second one.

### 6.3 Entry simulation

Deterministic, stated as a named policy (`PAPER_FILL_POLICY_ID`, version 1) recorded on every fill.

| Entry type | Trigger, on a closed bar | Fill price |
|---|---|---|
| `MARKET` | the first bar after activation | that bar's **open** |
| `LIMIT` | long: `low ≤ limit` · short: `high ≥ limit` | the **open** when the bar gapped through it, otherwise the limit |
| `STOP_ENTRY` | long: `high ≥ trigger` · short: `low ≤ trigger` | the **open** when the bar gapped through it, otherwise the trigger |

`MARKET` fills at the *next* bar's open and never at the close of the bar the owner was looking at:
that close had already happened when the decision was made, and filling at it would be a lookahead
of exactly one bar dressed as realism.

The gap rule is symmetric and is applied identically to a favourable gap (a limit filled better) and
an unfavourable one (a stop-entry filled worse). Rounding the asymmetry toward the owner's benefit
is the single commonest way a paper record flatters itself, and the rule is written once so it
cannot be applied twice.

### 6.4 Exits, and the ladder

The remaining quantity runs to the effective stop. Each `ExitLeg` names a target price and a
fraction of the **activated** quantity; the fractions sum to at most 1, and any remainder runs to
the stop. When the owner names no ladder, the CLI builds a single leg at the plan's first target for
the whole size and **prints that it did** — a default the record states explicitly rather than a
default the code applies silently.

Same touch rules as the entry, same gap rule, same policy id.

### 6.5 Joining the proposal's lifecycle

When an activation names a `proposal_id`, the composition root appends `ENTRY_TRIGGERED` and then
`EXECUTED` to **that proposal's own stream**, so the brief's `PROPOSED → PENDING → TRIGGERED → OPEN`
is one continuous chain across two objects rather than two disconnected ones.

It appends them **only when the proposal's folded state makes them legal** — `ENTRY_TRIGGERED`
requires `DECIDED`, so a proposal the owner never decided on is left untouched and the skip is
reported on the page. Forcing the event would either raise mid-simulation or, worse, require
loosening `fmis.proposal`'s transition table for the convenience of a simulator.

---

## 7. Six refusals

### 7.1 No intrabar path is invented

A bar is four numbers. The engine reads `open`, `high`, `low`, `close` and asks *"was this level
touched"* — never *"in what order were two levels touched"*, except where the **open** answers it.

### 7.2 The open resolves what it can

If a long position's bar **opens at or below the effective stop**, the stop was reached at the first
price of the bar and no target inside the bar can have preceded it. That is not a guess; it is the
one piece of intrabar ordering four numbers actually contain, and using it removes most false
ambiguity. The mirror holds for a bar opening at or beyond a target.

### 7.3 An entry that filled inside its bar cannot be reasoned past

**Revised in v1.1 after the hostile review.** The first draft deferred every exit
test to the next bar whenever the entry filled at its level rather than at the bar's open,
and called the deferral symmetric because it withheld a stop and a target alike. It is not
symmetric in effect: a breakout entry fills near the top of its bar, so the level the
remainder of that bar is most likely to reach is the **stop**. Skipping it made every
stopped-out breakout survive one bar longer than it did — the flattering asymmetry
this whole engine is written against, introduced by the rule meant to prevent it.

What ships:

* the bar reached **no** exit level — the exit tests are deferred by one bar, which
  delays an answer and invents nothing;
* the bar reached the stop **or** a target — the trade **halts** as `AMBIGUOUS_BAR`.
  One code path, both levels, no side favoured.

### 7.4 Everything else that is ambiguous **halts**

When a bar opens *between* the stop and a target and touches both, the order is unknowable without
sub-bar data this repository does not ingest. The engine emits `AMBIGUOUS_BAR`, records the two
levels and the bar, and **stops advancing that trade**. No fill is invented, no price is fabricated,
and the position stays open in the ledger.

`AMBIGUOUS` is a halt, not a terminal state. The owner resolves it through the path that already
exists — `fmits trade close`, recording the exit they judge they would have taken — and that exit is
an `ASSERTED` fill beside `MEASURED` ones, which is exactly the distinction `ValueOrigin` exists to
carry. Resolving it to the flattering side, to the conservative side, or by candle colour were all
considered and all rejected: ADR-0021 refused the identical guess for a two-sided break bar, and
`AV`'s shipped `AMBIGUOUS_SAME_BAR` refused it again.

### 7.5 A run's candle window is bounded at both ends

**Revised in v1.1 after the hostile review.** A provider page reaches back further
than any activation and forward to the live edge, and the first draft bounded
neither end.

* **Before the activation** — those bars cannot affect an instruction that did not
  exist, and counting them made *"bars advanced"* a figure about the fetch rather
  than about the trade. A live run reported 999 bars advanced on a two-day-old
  activation.
* **After the run's own instant** — `--reference-time` is a replay clock, not a
  label. Without the bound, a past-dated run reads live candles that closed after
  it, and the events it writes carry an `occurred_at` later than their own
  `recorded_at`: a refusal the domain raises correctly and cryptically, two layers
  down.

`bars_for_run` is the one function that applies both, and the read path uses the
same window so a monitoring reading cannot report an excursion over bars the trade
was never exposed to.

### 7.6 Costs are zero, and the zero is a stated policy

`PaperCostPolicy(policy_id="fmits-paper-zero-cost", version=1, fee_rate=0, slippage=0)` is recorded
on every activation and every outcome. A zero that is a **named, versioned policy** is a different
object from a zero that is an omission: the day a real fee model arrives it is version 2, every
outcome already recorded still says which basis produced it, and no figure silently changes meaning.
Every surface prints the basis beside the number.

---

## 8. Monitoring

`monitor_trade` is a pure projection over (plan, activation, fills, amendments, latest bar). It
produces, per the brief's §3: remaining quantity · current RR · realized RR · unrealized RR ·
maximum favourable excursion · maximum adverse excursion · holding time · bars in trade · days in
trade · distance to stop · distance to target.

Every one of them is `Absent(reason)` rather than zero when it cannot be stated — an unmarked
position has no unrealized RR, and a zero there makes a page look complete.

**No arithmetic is duplicated.** The risk distance, the capital at risk and the sign rule are
`fmis.portfolio_risk.geometry`'s, called; the average entry is `AverageCost.per_unit`; the position
fold is `fmis.positions.fold_positions`; the planned risk/reward is `fmis.plan.adherence`. An R
multiple is `realized ÷ initial risk` — one quotient, computed at read time, stored nowhere.

---

## 9. Surfaces

| Command | What it does |
|---|---|
| `fmits trade activate PLAN_ID` | Creates a `TradeActivation` — entry type, size, ladder, expiry, stop management. Writes one record. |
| `fmits trade stop PLAN_ID --to PRICE --reason TERM` | Appends a `StopAmendment`. Append-only; the plan is untouched. |
| `fmits simulate [SYMBOL ...]` / `--all` | Runs the engine over closed candles for the named markets, or every market with a live activation. |
| `fmits trade status` | Pending, triggered, open and partially exited paper trades, with the full monitoring block. |
| `fmits trade history` | Closed paper trades with their frozen outcomes. |
| `fmits trade lifecycle ID` | One trade's complete event stream, stop history and outcome. |
| `fmits today` | Gains a **paper trading** section: pending · triggered · open · partial exits · recently closed · holding duration · current RR · lifecycle status · warnings. |

`TODAY_SCHEMA_VERSION` moves `2 → 3`. A consumer reading a version-2 page would render a store full
of live paper trades as a page with none, which is a different claim from *"this page did not
check"*.

---

## 10. Journal integration

**Every lifecycle transition writes a `JournalEntry`.** No silent state change: activation, trigger,
entry, every stop amendment, every partial exit, the close, the cancellation, the expiry, the
ambiguity halt and the outcome each append one entry linked to the plan and to the fill.

The entries are `JournalKind.NOTE` authored by the simulator, tagged from the existing exit-reason
and a new `lifecycle_event` vocabulary, and they are **never** `IDEA` — an idea is the owner's, and
a simulator that could author one would pollute the discipline metric that counts whether the owner
wrote anything at all.

---

## 11. Limitations, printed on every page

| # | Limitation |
|---|---|
| `PT-1` | Nothing here reaches an exchange. A paper fill is what this system computes would have happened; it is not a trade. |
| `PT-2` | Fills are modelled at zero fee and zero slippage under a named policy. A real fill costs more. |
| `PT-3` | A level is filled on **touch**, at the level or at the bar's open when it gapped through. Real liquidity at that price is not modelled. |
| `PT-4` | A bar that opens between the stop and a target and touches both **halts** the trade. No intrabar order is inferred. |
| `PT-5` | Perpetual funding, borrow cost, liquidation and spread are not modelled, and no data this system ingests bounds any of them. |
| `PT-6` | Excursions are measured on the simulation interval's closed bars only. A wick on a finer interval is invisible. |
| `PT-7` | Paper is excluded from every real-money aggregate by default (`DEFAULT_EXCLUDED_BOOKS`), and a figure that includes it says so. |
| `PT-8` | A paper fill carries a **placeholder** FX rate of `1` and a source that says so in words. `Book.PAPER` has no tax consequence and no tax engine exists; when one arrives it must exclude the book, and that rate must never be read as a real one. |
| `PT-9` | Every R multiple is an exact quotient and a non-terminating one prints a 28-digit tail. Shortening it would be a rounding policy this system does not set — the finding `BN` recorded and left unfixed, inherited unchanged. |

---

## 12. What this makes possible next

The engine is written as `(state, bar) → events` precisely so that the bar source is replaceable.
Walk-forward testing, shadow mode over live closed candles, and future execution validation are all
the same function driven by a different sequence — none of them is built here, and none of them
needs the engine to change.
