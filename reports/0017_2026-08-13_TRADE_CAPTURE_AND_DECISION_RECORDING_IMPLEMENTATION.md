# 0017 — Trade Capture & Decision Recording (Milestone BK) — implementation record

| Field | Value |
|---|---|
| **Report number** | 0017 |
| **Title** | Trade Capture & Decision Recording (Milestone BK) — implementation record |
| **Date** | 2026-08-13 |
| **Report type** | Implementation record |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | Working tree on top of `dbc4765`, which also carries Milestone BJ uncommitted. `origin/main` is at `f9ddc54` |
| **Status** | Implementation complete. **Not committed, not pushed.** Both require separate, explicit authorization (`CLAUDE.md`) |

---

## 0. What was built, in one paragraph

Two new packages and one new command. `fmis.plan` holds `TradePlan` — the data
model's entity 19, designed since Milestone AP and never built. `fmis.trade_capture`
is the composition root behind `fmits trade`, with five subcommands: `record`,
`show`, `list`, `note` and `close`. **3,279 lines of production code, 4,197 lines
of tests, 435 new tests, 100 % statement coverage of the nine new modules, 30
mutation probes with 30 detected and 0 survivors, zero new runtime dependencies,
zero export collisions, zero module-level import cycles.** The whole suite is
**6,311 tests passing, identically under `-W error`**, up from 5,876.

**This is the first milestone in which FMITS writes to the durable store.**
Milestone BI built nine repositories and no command reached any of them; BJ read
them and wrote nothing. The owner can now record what they decided and what they
did, and read it back.

---

## 1. What the owner can do after this that was impossible before

```
fmits trade record BTCUSDT --direction long --account binance_spot --book swing \
      --entry 60000 --stop 58400 --target 64000 --target 68000 --size 0.5 \
      --fee 15 --fx-rate 10.5 --fx-source riksbank --confidence moderate \
      --setup trend_continuation --thesis "weekly context up; the 4H retest held"

fmits trade show  TRADE_ID          # commitment, fills, position, journal, warnings
fmits trade list  --status open     # one row per commitment, filtered, never ranked
fmits trade note  TRADE_ID --body "…"           # append-only; nothing is edited
fmits trade close TRADE_ID --price 63800 --fee 16 --reason target_reached \
      --fx-rate 10.6 --fx-source riksbank
```

Before this milestone the owner's stop existed on a chart and in their memory.
After it, the stop is a record that **cannot be changed**, the fills that were
taken under it are linked to it, and *"did I honour my stop?"* is a question with
an answer rather than a recollection.

Concretely, five things that were impossible:

| # | Now possible | Previously |
|---|---|---|
| 1 | Record a swing trade — commitment, fill and thesis — in one command | Nothing wrote to the store at all |
| 2 | See capital at risk with the arithmetic that produced it | No stop was stored, so no risk denominator existed |
| 3 | Read a trade's realized P&L back as a fold over its own fills | The position fold existed with nothing to fold |
| 4 | Append a note to a trade, and never lose the earlier one | The journal had no writer |
| 5 | Record an exit with a reason from the owner's own vocabulary | Exits were not representable |

---

## 2. The finding that shaped the milestone

**The brief's field list is `TradePlan`'s field list, and `TradePlan` did not exist.**

The brief asks `fmits trade record` to capture symbol, direction, account, entry
price, **stop, target(s), position size, capital at risk, trade thesis,
originating setup, originating AnalysisRecord, MarketSnapshot reference,
confidence** and notes. Measured against the thirteen domain packages Milestone BH
built, six of those fourteen fields had a home and eight did not:

| Field | Home before BK |
|---|---|
| symbol · direction · account · entry price · position size · notes | `Trade` (`fmis.ledger`) |
| **stop · target(s) · confidence · setup · snapshot ref · analysis ref** | **none** |
| **capital at risk** | **none — and correctly so; see §4.2** |
| **thesis** | `JournalEntry`, by §11.6's own routing |

`TRADING_DOMAIN_ARCHITECTURE_V1` §9 and `TRADING_DOMAIN_DATA_MODEL_V1` §10.3 both
specify the missing entity in full, down to its package name (`fmis.plan`), and
§11.6 assigns *stop, target and intended size* to it **by name**.
`SWING_TRADING_MVP_BLUEPRINT_V1` §12.3 records the omission as accepted debt with
the cost stated: *"until it lands, a widened stop is invisible, and stop integrity
is the highest-value single behavioural metric."* §14 lists it as the first item
after day 30.

**Three alternatives were considered and rejected**, each for a reason the
repository already states:

1. **Put the stop on `Trade`.** Refused by §11.6 explicitly. A `Trade` records what
   happened to money; a stop that never triggered is not part of what happened,
   and a field holding "the stop" would hold whatever it was when the position
   closed rather than when it opened.
2. **Use `OpportunityProposal`.** It has a stop, targets and a stated confidence —
   and it *requires* a `market_snapshot_id` and, for a directional proposal, an
   `Anchor` carrying a `LevelOriginRef` from the level-crossing engine. The brief
   makes the snapshot optional, and an owner typing at a CLI has no level origin.
   It also has no account and no size. Worse, it is a *suggestion*: recording an
   executed trade as one would corrupt the proposal cohort that
   *"did the AI improve my decisions?"* rests on.
3. **Store the plan as prose in a `JournalEntry`.** The brief requires *"Reject
   invalid stop placement"* and *"Reject impossible risk"*. Prose cannot be
   validated, and `trade show` would have to parse it back. That is Law 1's
   failure with extra steps.

**So `fmis.plan` was built, to the card the data model already wrote.** This is an
addition the design specifies, not a redesign: no existing record type, repository
or boundary changed shape. `Trade.plan_id` — an optional field present since
Milestone BH and unconstrained precisely because `fmis.plan` did not exist — is the
link, used exactly as §10.3 relationship 6 defines it. **No domain type was
modified.**

---

## 3. What was built

### 3.1 `fmis.plan` — the commitment (736 lines)

| Module | Holds |
|---|---|
| `models.py` | `TradePlan`, `PlanError`, the schema constants |
| `adherence.py` | `check_placement`, `risk_distance`, `capital_at_risk`, `planned_risk_reward`, `nearest_planned_level`, `exit_divergence`, `ExitDivergence`, `PlanPlacementError` |

`TradePlan` is a **captured artifact**, `ASSERTED` throughout, with
`initial_invalidation` required and no code path that changes it — a test pins the
four public callables the type exposes, so adding a `with_stop` fails there rather
than three milestones after someone found it convenient.

`adherence.py` takes **plain values, never records**: a `TradePlan`, an exact price
and a `Quantity`. `fmis.plan` therefore never imports `fmis.ledger`, which keeps
§9.1's claim true — *"an unproposed, unexecuted plan is equally valid"* — and a
guard test asserts it.

### 3.2 `fmis.persistence` — the tenth repository (+101 lines across four files)

| Change | Detail |
|---|---|
| `RecordKind.TRADE_PLAN` | Eleventh kind |
| `RecordSpec` | Captured artifact · record file · keyed on `committed_at` · lineage on market · scope `(book, market)` · supersedes nothing |
| `PlanRepository` | In `decision_repositories.py`, beside the proposal it may cite |
| `TradingStore.plans` | Wired second, after `trades` |

`update` and `replace` both raise, inherited from `Repository` — and the refusal is
the feature rather than a consequence of the classification.

### 3.3 `fmis.trade_capture` — the composition root (2,543 lines)

| Module | Holds |
|---|---|
| `models.py` | `TradeView`, `TradeRow`, `TradeListing`, `TradeFilters`, `FillLine`, `CaptureOutcome`, `WrittenRecord`, `CaptureWarning`, `CaptureStatus`, three errors |
| `capture.py` | `record_trade`, `close_trade`, `append_note`, the three request records, `market_from_symbol`, `capture_version_set` |
| `views.py` | `load_trade`, `list_trades`, `fills_for_plan`, `load_plan`, the eight warnings, the five invariant limitations |
| `inputs.py` | The text boundary: strings → domain values, and `open_store` |
| `render.py` | `render_trade`, `render_listing`, `render_outcome` |

### 3.4 `fmits trade` (+574 lines in `pipeline/cli.py`, additive)

Registered between `today` and `archive`. Every other command parses and runs
exactly as before.

---

## 4. The five decisions worth recording

### 4.1 A swing trade is three records, and only this package knows that

A `TradePlan` (intent), one or more `Trade` fills (money) and `JournalEntry`
entries (opinion). They stay three because they have three different truth
conditions, and a single "swing trade" row would make *"did I honour my stop?"*
unanswerable the first time a stop moved. `TradeView` assembles them at read time
and is stored nowhere.

### 4.2 There is no `capital_at_risk` field, and its absence is the money rule

Capital at risk is `|entry − stop| × quantity` — a product over one number the plan
holds and two the fill holds. `AP` §5.3: *"no quotient is ever a stored field"*, and
the domain's two precedents are unanimous — `RiskRewardReading` stores the pair and
computes the ratio, `AverageCost` stores the pair and divides at read time. Storing
the product would be a fourth place the same fact lives, and the first one to
disagree with a `Correction`.

So the CLI takes `--size`, not `--risk`, and the page prints:

```
 capital at risk  800 USDT
                  (|60000 − 58400| × 0.5)
```

**This is a departure from §10.3's rule 7** — *"`intended_size` is expressed in risk
terms, from which quantity is derived — never the reverse"* — and the reason is
stated rather than hidden: BK records trades the owner has **already entered**. The
size is a fact they filled; the risk is arithmetic over it. Risk-first *sizing*
belongs to a plan committed **before** the fill, which is C4's other half and is
listed in §8 as a known gap.

### 4.3 A planned price is not a `LevelReading`

`LevelReading` is a frozen engine reading: `MEASURED`, carrying a `LevelOriginRef`
naming the swing and the confirmation bars that produced it, under the rule that
*"no price in this domain is fabricated."* A stop the owner types has no such
origin, and manufacturing one to reuse the type would be exactly that fabrication.
`TradePlan` therefore holds exact `Decimal` prices and the whole record is
`ASSERTED`.

### 4.4 The symbol split is stated, never guessed

`MarketId` deliberately has no parse-from-string: *"`BTCUSDT` cannot be split back
into base and quote without an asset registry this package declines to hold —
`BTCU`/`SDT` is a legal reading of the same characters."* `market_from_symbol`
does not guess it. The **owner** supplies `--quote` (defaulting to `USDT`, the
watchlist's own), which makes the split a stated fact, and a symbol that does not
end in the quote they named is refused rather than cut somewhere plausible.

### 4.5 The CLI reaches neither the domain nor the store

Milestone BJ established that `fmis.pipeline` is a market-half package and may not
import `fmis.persistence`; this milestone keeps it. The first draft of the CLI
imported `AccountId`, `Money`, `Quantity`, `TradeDirection` and `TradingStore`
directly, and the existing guard tests caught it. `inputs.py` exists because of
that: the CLI hands over strings and a filing instant, and every conversion lives
where it can be tested without a parser.

---

## 5. What the commands refuse

Each refusal names the two values that disagree, exits non-zero and writes nothing.

| Refusal | Why |
|---|---|
| Stop on the losing side of the entry, or **at** it | A stop the entry has passed is not a stop; a stop at the entry is a zero risk distance and a division by zero downstream |
| A target on the losing side of the entry | A "target" reached by the trade going wrong is a stop with the wrong label |
| A target on the stop's side, or a ladder that steps backwards | Refused at construction; the commonest typing error there is |
| `NO_TRADE` as a direction | A decision not to act belongs to a proposal's lifecycle, where it can be scored |
| A size in the quote asset | Size is a quantity of what was bought, never of what paid for it |
| A size or price that is not positive | Direction is stated separately; a signed size is the same fact twice |
| A negative fee | A rebate is a different economic fact and is its own event |
| A third-asset fee with no rate of its own | It is its own disposal, and the rate is unrecoverable later |
| A numeric confidence label | Confidence is the owner's word and is not a probability (`AP` §20.6) |
| A naive timestamp | ADR-0001: UTC is canonical, and an assumed local zone is invisible in the stored bytes |
| A record filed before it happened | FMITS cannot learn of something before it happens |
| A commitment dated **after** its own fill | A plan is what was committed to before the market moved |
| Closing more than is open, or a trade already flat | The second would open a position in the opposite direction, which is a new decision |
| Closing a commitment nothing filled against | It is closed by letting it expire, not by recording an exit that did not happen |
| An exit with no reason | *"The reason is the field that makes exits analysable"* |
| An exit across two accounts with none named | FMITS cannot tell which one it came from |

**Validation precedes publication.** All three records are constructed first, the
cross-record checks run, and only then does the first byte move. A test asserts
that a refused capture leaves the store completely empty.

---

## 6. What is derived and never stored

| Figure | Derived from | Rendered as |
|---|---|---|
| Capital at risk | `|entry − stop| × max exposure` | the answer **and** the multiplication |
| Risk/reward | `RiskRewardReading(risk, reward)` against the nearest target | the ratio **and** the division |
| Average entry | `AverageCost.per_unit` — the domain's own division | the answer **and** the division |
| Realized P&L, gross and net | the position fold | both, always, and never called a taxable gain |
| Status (`PLANNED`/`OPEN`/`CLOSED`) | the fold, under the owner's dust policy | on the page and in every row |
| Exit divergence | `exit − nearest planned level` | available; not surfaced by `close` in this build (§8) |

Every one of them is `Absent(reason)` when it cannot be computed, and the reason is
printed. A blank capital-at-risk line would read as *no risk*; the line
*"the average entry has moved to the stop's side, so no risk distance exists"*
cannot be misread that way — and that arrangement of prices happens for real, by
adding to a loser past the level the plan named.

---

## 7. The eight warnings

Fixed order, never severity-sorted: ordering by severity would make the list read
as ranked by importance, and this package ranks nothing.

| Code | Raised when |
|---|---|
| TC-W1 | The average entry has drifted to the stop's side; no risk figure exists |
| TC-W2 | The commitment's fills cross flat more than once; figures describe the latest round trip |
| TC-W3 | Fills sit in more than one account |
| TC-W4 | A fill has been corrected |
| TC-W5 | The position has been reduced; capital at risk describes the maximum held |
| TC-W6 | The commitment expired while the position was still open |
| TC-W7 | No target, so no risk/reward pair exists |
| TC-W8 | Nothing has been written about this trade — the discipline metric |

Five invariant limitations (TC-1…TC-5) print once at the foot of every page: FMITS
places no order; capital at risk assumes the stop holds; realized P&L is not a
taxable gain; the fold is this commitment's own; no position size is computed.

---

## 8. Known limitations

1. **`PlanAmendment` is not built.** §10.4's amendment stream is what makes a
   *widened* stop visible, and stop integrity is `AP` §20.5's highest-value
   behavioural metric. Nothing in this milestone amends a plan, so every field is
   immutable — stricter than §10.3, never looser. **This is the largest remaining
   piece of C4 and should follow next.**
2. **Risk-first sizing is not implemented.** §4.2 states why, and the consequence:
   FMITS records the size the owner filled and reports the risk it implies; it does
   not compute a size from a risk allowance. That needs an equity figure, which
   requires the portfolio slice.
3. **`fmits trade correct` does not exist.** `TradeRepository.replace` appends a
   `Correction` and the read path already resolves and reports one (TC-W4), but no
   command reaches it. A mistyped fill is currently corrected only through the API.
4. **The exit divergence is computed and not surfaced.** `exit_divergence` is built,
   tested and exported; `close` does not print it, because which level the owner was
   aiming at is not knowable and the "nearest level" convention deserves a surface
   decision rather than a default.
5. **`fmits today` does not read a `TradePlan`.** The daily workspace still reports
   positions folded book-wide and knows nothing about commitments. Wiring the two
   is a small, obvious follow-up and was left out of scope deliberately.
6. **The listing is O(plans × ledger).** The ledger is resolved once per listing and
   the journal once per plan. Proportionate at this owner's volumes and on the same
   cost curve ADR-0027 accepted for the archive manifest.
7. **One writer process.** Unchanged from Milestone BI §8: a `flock` guards the one
   writer's own threads; two writer processes remain unsupported.
8. **No schema migration has been exercised.** `TRADE_PLAN_SCHEMA_VERSION` is 1, like
   every other payload version in the repository.

---

## 9. Boundaries crossed, and the guard tests that record them

Two existing guard tests were widened. Both were designed to force exactly this
decision, and both are pinned so a further widening is a deliberate edit.

| Guard | Was | Now | Justification |
|---|---|---|---|
| `test_directional_vocabulary_boundary.py` — trade-domain exemption | four packages | **five**: `+ fmis.plan` | The side the owner *committed* to. Same class as `fmis.proposal`'s. Validating *"below the entry on a long"* is impossible in a package that may not name the word |
| the same file — surface exemption | `pipeline/cli.py` only | `+ fmis/trade_capture/` | Where the owner states a side and it becomes a `TradeSide`. Kept as a separate set, so "stores a direction" and "asks the owner for one" remain two justifications |

A new test, `test_the_owner_surface_imports_no_engine`, asserts that the widening
widened *who may spell a side* and not *who may read a candle* — and
`test_the_market_half_still_holds_no_directional_vocabulary_at_all` is unchanged
and still passes.

Registry and count guards updated additively: the command list (four files), the
repository count 9 → 10, and `DOMAIN_PACKAGES` in the two architecture guards.
`fmis.plan` is now covered by every sweep the other thirteen domain packages are
covered by — no clock, no float, no engine, no store, one catchable error base, a
pinned schema-version set, a unique type slug, round-trip and byte-stability.

**No ADR was written.** The repository's own precedent (`ADR_IMPLEMENTATION_GATE`
Part 6) is that all 27 accepted ADRs were written for a milestone that then
shipped, and two milestones shipped with none because the implementation proved no
new boundary. This milestone crosses no boundary an ADR does not already govern:
ADR-0027 supplies identity and publication, ADR-0001 the timestamps, ADR-0005 the
reject-never-repair rule, ADR-0028 §5 the directional-vocabulary rule this widens
inside its own stated extension point.

---

## 10. Verification

Every figure below was executed against the working tree, not quoted.

| Measurement | Value |
|---|---|
| **Tests** | **6,311 collected, 6,311 passing** — identically under `-W error` |
| Tests before this milestone | 5,876 |
| New tests | **435** across ten new files, plus two added to an existing guard |
| **Statement coverage, nine new modules** | **100 %** (962 statements, 0 missed) |
| Distinct branch edges exercised | 422 |
| **Mutation probes** | **30 applied, 30 detected, 0 survivors** |
| New runtime dependencies | **0** |
| Public exports | 764 total, **0 collisions** (`fmis.plan` 14, `fmis.trade_capture` 52) |
| Module-level import cycles | **0** (197 modules) |
| Production files modified | 5, all additively: `cli.py` and four in `fmis.persistence` |
| Domain types modified | **0** |
| Store verification after a full trade | `verify().ok is True`; the write-journal chain intact |

Coverage was measured with the standard library's `sys.monitoring`, the same
approach Milestones BC and BJ used, because no coverage package is installed and
none is a runtime dependency. Docstring lines and the `if (` of a multi-line
condition are excluded from the statement set — CPython emits no line event for
either, so counting them would report a permanent phantom miss.

The thirty mutation probes are hand-written and each attacks a **stated rule**: a
stop at the entry accepted, the identity keyed on when typing began, the exit
recorded on the entry's side, a filtered listing reading as the whole store, an
absence rendering as a dash, an exact amount passing through a float. Two probes
found real gaps during development and both were closed by adding tests rather
than by weakening the probe.

---

## 11. What this milestone deliberately did not do

Per the brief, and each verified absent from the source:

- **No expectancy, no analytics.** The only arithmetic is a product, a difference
  and the folds the domain already owned.
- **No execution.** No order, no exchange, no venue confirmation. Asserted in the
  command's own description and in TC-1.
- **No paper trading.** `Book.PAPER` is recordable like any other book, and nothing
  simulates a fill.
- **No repository redesign.** One repository added; none changed.
- **No domain redesign.** One package added, to a card the data model already wrote;
  no existing type changed.
- **Nothing bypasses `TradingStore`.** A guard test asserts this package names no
  atomic write, no append and no path write.

---

## 12. Files

**New (11):**

```
src/fmis/plan/__init__.py                     56
src/fmis/plan/models.py                      436
src/fmis/plan/adherence.py                   244
src/fmis/trade_capture/__init__.py           146
src/fmis/trade_capture/models.py             385
src/fmis/trade_capture/capture.py            798
src/fmis/trade_capture/views.py              448
src/fmis/trade_capture/inputs.py             392
src/fmis/trade_capture/render.py             374
tests/trade_capture_helpers.py               126
reports/0017_…_IMPLEMENTATION.md           (this)
```

**New tests (10 files, 435 tests):** `test_plan_models.py` (62),
`test_plan_adherence.py` (39), `test_persistence_plan_repository.py` (22),
`test_trade_capture_models.py` (40), `test_trade_capture_capture.py` (76),
`test_trade_capture_views.py` (50), `test_trade_capture_inputs.py` (45),
`test_trade_capture_render.py` (40), `test_trade_capture_architecture.py` (27),
`test_pipeline_cli_trade.py` (32).

**Modified production (5):** `pipeline/cli.py`, `persistence/kinds.py`,
`persistence/decision_repositories.py`, `persistence/composition.py`,
`persistence/__init__.py`.

**Modified tests (8):** the two architecture guards, the directional-vocabulary
guard, the four registry guards, the repository-count guard, plus
`trade_domain_helpers.py` and `persistence_helpers.py`.
