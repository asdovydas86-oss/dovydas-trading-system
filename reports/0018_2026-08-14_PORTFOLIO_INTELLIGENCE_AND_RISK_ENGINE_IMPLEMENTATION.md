# 0018 — Portfolio Intelligence & Risk Engine (Milestone BL) — implementation record

| Field | Value |
|---|---|
| **Report number** | 0018 |
| **Title** | Portfolio Intelligence & Risk Engine (Milestone BL) — implementation record |
| **Date** | 2026-08-14 |
| **Report type** | Implementation record |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | Working tree on top of `dbc4765`, which also carries Milestones BJ and BK uncommitted. `origin/main` is at `f9ddc54` |
| **Status** | Implementation complete. **Not committed, not pushed.** Both require separate, explicit authorization (`CLAUDE.md`) |

---

## 0. What was built, in one paragraph

One new package, `fmis.portfolio_risk`, holding `AP` §15's Portfolio Intelligence
boundary: the deterministic step between portfolio facts and the owner's own
limits. The system stops evaluating trades one at a time and answers **what
changes in the portfolio if the owner opens this proposed trade now** — as two
portfolio states and the differences between them, never as a verdict. **3,767
production lines, 4,569 test lines, 368 new tests, 96 % statement coverage of the
eight new modules, 64 mutation probes with 62 killed and 2 proven-equivalent
survivors, zero new runtime dependencies, zero export collisions, zero import
cycles across 205 modules.** The whole suite is **6,679 tests passing, identically
under `-W error`**, up from 6,311.

**No CLI command was added, and that is deliberate.** The brief scopes BL to the
deterministic backend; Part 13 forbids turning it into a dashboard milestone.
The changelog entry is therefore **Foundational** rather than a product release
(§13).

---

## 1. Starting Git state

| Fact | Value |
|---|---|
| Branch | `main` |
| `HEAD` | `dbc4765` — *docs(product): record Trade Repository and Journal Engine* |
| `origin/main` | `f9ddc54` — local `main` is **6 commits ahead**, 0 behind |
| Stash | empty |
| Unresolved operation | none |
| Working tree at start | Milestones BJ and BK uncommitted (21 modified files, `src/fmis/plan/`, `src/fmis/today/`, `src/fmis/trade_capture/`, their tests, reports 0016 and 0017), plus 15 pre-existing untracked research documents under `docs/design/` and `docs/reviews/` |
| Baseline test run | **6,311 passed** in 170 s |

Every pre-existing untracked research document is untouched and still present.

---

## 2. Exact scope

Built:

| Part | Delivered in |
|---|---|
| 1 · Portfolio state | `models.PortfolioState`, `exposure.build_state` |
| 2 · Risk budget | `constraints.evaluate_constraints`, `remaining_risk_capacity` |
| 3 · Position risk | `geometry.stop_distance`, `capital_at_risk_of` |
| 4 · Proposed-trade impact | `impact.ProposedTrade`, `PortfolioImpact`, `evaluate_impact` |
| 5 · Constraint engine | `constraints.ConstraintResult`, `PortfolioConstraintCheck` |
| 6 · Duplicate / scale-in | `impact.PositionOverlap`, `detect_overlap`, `lines_after` |
| 7 · Classification groups | `classification.ClassificationMap`, `ExposureDimension.GROUP` |
| 8 · Venue awareness | `ExposureDimension.VENUE`; proof in `test_portfolio_risk_architecture.py` |
| 9 · Leverage readiness | `SPOT_ONLY_MODES`, the margin blockers (§11) |
| 10 · Persistence integration | `reading.py` — the only module touching the store |
| 11 · BK integration | `test_portfolio_risk_reading.py`, real records end to end |
| 12 · Sizing primitive | `geometry.maximum_quantity_for_risk` (§12) |
| 13 · `fmits today` | **unchanged**; integration point documented (§13) |
| 14 · Failure modes | every one, listed in §14 |

Not built, per the brief: exchange execution, credentials, order submission,
paper trading, Telegram, UI, AI interpretation, funding/OI ingestion, statistical
correlation, exchange adapters.

**Zero domain types were changed.** `fmis.portfolio`, `fmis.risk`,
`fmis.positions`, `fmis.plan` and `fmis.ledger` are read and not modified. The
only pre-existing file this milestone edits is
`tests/test_directional_vocabulary_boundary.py` (§10).

### Files added

```
src/fmis/portfolio_risk/__init__.py         160   package contract and exports
src/fmis/portfolio_risk/geometry.py         211   the four arithmetic facts
src/fmis/portfolio_risk/classification.py   189   the owner's read-time groupings
src/fmis/portfolio_risk/exposure.py         337   aggregation; build_state
src/fmis/portfolio_risk/reading.py          367   the composition root — reads, never writes
src/fmis/portfolio_risk/constraints.py      694   the one contract, AP §15.5
src/fmis/portfolio_risk/models.py           884   ExposureLine · Breakdown · PortfolioState
src/fmis/portfolio_risk/impact.py           925   proposed-trade impact, duplicate detection
                                          -----
                                           3,767
```

---

## 3. Portfolio-state model

`PortfolioState` is a **rebuildable projection** in the architecture's §24.3
sense: delete it, recompute it from the resolved ledger and the same supplied
marks, and the result is equal (`test_the_same_store_produces_an_equal_state_every_time`).
The frozen half of the portfolio remains `PortfolioSnapshot`, which
`PortfolioRepository` already owns and which this package reads and never writes.

The unit is `ExposureLine`, not `Position`, and the reason is structural: a
`Position` is keyed by `(market, book)` and **holds no account**, because a book
never shares capacity across accounts. A portfolio must report exposure per
account and per venue, so a line carries both and is produced by folding **one
account's fills at a time** — the operation `PositionRepository.load_by_owner`
already sanctions. The consequence is stated rather than hidden:
`PortfolioState.accounts_share_a_market` names every market where a per-account
fold and a book-wide fold answer different questions.

One shape serves held and proposed exposure, so the arithmetic runs once and a
before/after comparison cannot compare two differently-computed numbers.
`ExposureSource` keeps them distinguishable, and `ExposureLine.origin` reports
`MEASURED` for a held line and `ASSERTED` for a proposed one.

Figures on the state: `equity`, `equity_as_of`, `cash`, `gross_exposure`,
`net_exposure`, `long_exposure`, `short_exposure`, `open_risk`,
`deployed_capital`, `reserved_capital`, `available_capital` (read-time),
`leverage` (read-time), `open_position_count`, `pending`, `unmarked`,
`unstopped`, and eight breakdowns. Every money figure is `Money | Absent`.

---

## 4. Exposure calculations

| Figure | How |
|---|---|
| Gross | Σ \|quantity × mark\| |
| Net | Σ signed(quantity × mark) |
| Long / short | Σ over that side's own lines — **never recovered by subtraction** |
| Open risk | Σ capital at risk |
| Deployed capital | Σ \|quantity × entry\|, spot longs only (§11) |
| Reserved capital | zero when nothing is pending; `Absent` otherwise (§14) |
| Leverage | `gross ÷ equity`, divided at read time |

**Gross and net are computed separately and neither is derived from the other.**
A portfolio long 10 and short 10 has a gross of 20 and a net of 0, and a page
showing only one of them describes a different portfolio.

Eight axes, each a different question:

```
account · venue · book · instrument · symbol · asset · direction · group
```

`INSTRUMENT` is the full `MarketId` (counterparty risk follows it), `SYMBOL` is
the traded pair, and `ASSET` is the **base asset alone** — added by the hostile
review (report 0019, H1) because `BTCUSDT` and `BTCUSDC` are two symbols and one
bet on BTC.

Every share is a numerator and a denominator with the division at read time;
`ExposureBreakdown` carries the portfolio's own totals so a reader can check the
division rather than trust it.

---

## 5. Risk calculations

```
LONG   distance = entry − stop
SHORT  distance = stop  − entry
capital at risk = distance × quantity, in the market's quote asset
```

Written once, in `geometry.stop_distance`, so a short's risk can never be
computed by a caller who reached for the long formula. A non-positive distance is
a **refusal**, not an absolute value: `abs()` over it reports a transposed stop as
a risk figure, and a position's average entry really does drift to the stop's side
after an add.

`RISK_BASIS` is published on every line, state, check and impact:

> pre-cost and pre-funding, and assumes the stop is honoured at the stated price.
> Fees, slippage, funding and liquidation are not included, and no data this
> system ingests bounds a gap through the stop.

**Where the stop comes from.** The fills that folded into a position carry
`plan_id`; `reading._stop_for` resolves those to `TradePlan`s and uses
`initial_invalidation` when exactly one distinct stop is found. Two commitments
with two different stops produce `Absent(reason)` naming both — never the first,
the newest or an average.

---

## 6. Risk-budget semantics

Limits are `fmis.risk.RiskBudget`, unchanged and unextended. **This package
invents no threshold**, asserted by the same test `fmis.risk` passes: no numeric
literal beyond 0 and 1 appears anywhere in it.

Two comparison semantics, and conflating them is the bug the module exists to
avoid. Almost every limit is a **ceiling**; `MIN_RESERVE` is a **floor**, where
*below* is the breach. Routing a floor through a ceiling comparison reports an
account with no reserve left as comfortably within its reserve limit.
`_FLOOR_SCOPES` names the exception and the comparison branches on it once.
`headroom` is `limit − current` on a ceiling and `current − limit` on a floor, so
positive means room on both.

Every limit in the budget appears in the result. A limit that cannot be measured
is `Absent(reason)`, never omitted — and `binding_constraints` and
`indeterminate` are two separate lists so a surface cannot render the second as
the first.

| Scope | Measured as | Units accepted |
|---|---|---|
| `PER_TRADE_RISK` | the candidate's risk, or the largest held position | money · % of equity |
| `TOTAL_OPEN_RISK` | Σ capital at risk | money · % of equity |
| `CONCENTRATION` | a keyed axis's share | ratio · % of open risk · % of equity · money |
| `CLUSTER_EXPOSURE` | a group's share | ratio · % of open risk · % of equity · money |
| `LEVERAGE` | gross ÷ equity | ratio |
| `MAX_CONCURRENT_POSITIONS` | open line count | count |
| `MIN_RESERVE` | available capital — **floor** | money · % of equity |
| `PERIOD_LOSS` | `Absent`, naming the owner-local period | — |
| `DRAWDOWN` | `Absent`, naming the missing equity peak series | — |

**`PERCENT_OF_EQUITY` means a fraction, and the convention is stated because the
domain does not fix it.** `RiskLimit` validates that a percent limit is a positive
`Decimal` and says nothing about whether `2` means 2 % or 200 %.
`PERCENT_UNIT_CONVENTION` records the choice — the 2 % ceiling is `0.02` — for the
reason that every other ratio in the repository already is one
(`ExposureSummary.leverage`, `AllocationEntry.weight`, `RiskRewardReading.ratio`),
and because `tests/persistence_helpers.py` already wrote `Decimal("0.02")` against
`PERCENT_OF_EQUITY` before this milestone existed.

**The 2 % rule stays a ceiling.** `default_below_ceiling` is never promoted to the
comparison value, and `AT_LIMIT` is a **binding** constraint — excluding it would
be the quietest possible way to turn a ceiling into a target.

Constraint keys are written `{dimension}:{value}` — `venue:…`, `symbol:BTCUSDT`,
`asset:BTC` — so one limit set can constrain several axes without the engine
guessing which was meant. A key naming an axis this engine does not measure is
`Absent(reason)` listing the axes it does.

---

## 7. Proposed-trade impact

`ProposedTrade` is **not** a duplicated `TradePlan`. A plan holds the commitment
and deliberately holds no size and no account; this type is the missing half — a
size, an account and an entry price. `ProposedTrade.from_plan` supplies the rest
from a recorded commitment, and **has no `stop` parameter**: `initial_invalidation`
is the field the plan entity exists to keep immutable, and a sizing helper that
let a caller pass a different stop would be the edit path it was built to prevent.

`PortfolioImpact` carries `before`, `after`, `overlap`, `incremental_notional`,
`incremental_capital_required`, `incremental_open_risk`, `remaining_risk_budget`,
`before_check`, `after_check` and its notes, plus read-time `resulting_*`
projections and `newly_binding` / `already_binding`.

Three properties make it safe:

1. **Both states are built by `build_state` and evaluated by
   `evaluate_constraints`.** Every after-figure is comparable with its before
   counterpart by construction rather than by care.
2. **The increment is `after − before`, not the candidate's own risk.** A trade
   that reduces an opposite position has 400 USDT of standalone risk and *lowers*
   the portfolio's open risk by 400; reporting the first would file a de-risking
   trade as the book's largest addition.
3. **Both checks are carried.** *"This trade breaches your concentration cap"* and
   *"you were already over it"* are different sentences and only one is about the
   trade.

A proposed line is valued at **its own entry price**, carrying
`PROPOSED_MARK_SOURCE` so a reader can always tell it from a measured mark.

**No verdict.** A guard test walks every exported dataclass and asserts no field
name contains `verdict`, `decision`, `recommend`, `action`, `signal`, `advice` or
`should`, and a second greps the executable source (docstrings and comments
stripped) for `take_trade`, `reject_trade`, `should_trade` and `recommendation`.

Ten note codes, in a fixed order, with no severity and no rank: `PR-N1` duplicate
instrument elsewhere · `PR-N2` shared classification group · `PR-N3` newly binding
· `PR-N4` already binding · `PR-N5` indeterminate limits · `PR-N6` reversal ·
`PR-N7` unclassified candidate · `PR-N8` indeterminate effect · `PR-N9` unstopped
positions · `PR-N10` same base asset under a different quote.

---

## 8. Duplicate and scale-in detection

`PositionRelationship` answers *what is there* — `NO_EXISTING_POSITION`,
`SAME_DIRECTION`, `OPPOSITE_DIRECTION`. `IntendedEffect` answers *what the
candidate would do* — `NEW_POSITION`, `SCALE_IN`, `REDUCTION`, `CLOSE`,
`REVERSAL_CANDIDATE`. Two enums, because *"I hold a long"* and *"I am adding to a
long"* are two facts.

Matching is on `(account, market, book)`. Book is part of it because books never
share capacity: the same market held in `SWING` and proposed in `INVESTING` is a
**new position**, not a scale-in.

**Direction is netted, and the convention is stated rather than inferred.** FMITS
models one net position per `(account, market, book)`: `fold_positions` already
splits a fill that carries exposure through zero, and a hedge-mode two-sided
position is not representable anywhere in this domain. `lines_after` mirrors that
split exactly — add, reduce, remove, or remove-and-open-the-remainder.

A scale-in is kept as **two lines**, not one blended line: blending would need a
weighted-average stop the owner never stated, and the open risk of a scale-in with
its own stop is the sum of the two risks.

`IntendedEffect` is `Absent(reason)` when two open lines sit in one triple —
unreachable from a fold, reachable from caller-supplied lines, and an effect
computed against an arbitrary one of two would be a guess wearing an answer's
clothes.

Duplicate exposure is reported on two axes, kept separate because they are two
sentences: `same_instrument_elsewhere` (the same pair in another account, book or
venue — two venues do not net) and `same_asset_elsewhere` (the same base asset
under a different quote, which is the same bet).

---

## 9. Classification-group support

`ClassificationMap` is `asset → group ids` at a stated version, applied at read
time and **never written onto a holding** — `AP` §15.7's rule, implemented.
**This module names no group**: BTC-beta, Layer 1, DeFi, AI, meme and exchange
tokens are the owner's words, and every member is supplied at construction.

An asset may belong to several groups at once, and the consequence is stated
rather than smoothed away: group buckets overlap, so they sum to *more* than gross
exposure, and `overlapping_keys` names every asset responsible while the totals
stay the portfolio's real ones. An asset the map does not name is `UNCLASSIFIED` —
a named bucket, never a guess and never a silent omission.

`unclassified_map` is the honest default: it names nothing, and it is still
versioned, so the day the owner writes a taxonomy the two readings are visibly
different rather than one silently replacing the other.

---

## 10. Venue-agnostic proof

Not a claim — five executable guards in
`tests/test_portfolio_risk_architecture.py`:

1. **No module imports a venue provider** — nothing under `fmis.providers`.
2. **No module imports a market-half engine** — 22 named packages, TradingView
   and the scanner among them.
3. **No module names a venue in its executable code** — `binance`, `evedex`,
   `bybit`, `tradingview`, `coinbase`, `kraken`. Docstrings and comments are
   stripped before the grep, so documenting the guarantee is permitted and
   branching on a venue is not. *This test found and rejected one real hit* — a
   `venue:binance` example baked into a help string, replaced with the axis list.
4. **The whole dependency surface is pinned as a set** — eleven `fmis` packages,
   all domain or store.
5. **`ExposureLine` has no `venue` field** — the venue is read off `MarketId`.

The test suite carries the claim positively too: `EVEDEX_MARKET` and
`EVEDEX_PERP` are first-class fixtures, and
`test_the_same_symbol_at_two_venues_is_two_lines` records real trades on a venue
this repository has no provider for and never will inside this package.

**ADR-0028 §5 was widened, inside its own stated extension point.**
`fmis.portfolio_risk` computes long exposure, short exposure, directional net and
directional concentration, and carries the sign rule capital at risk depends on;
none of that has any expression in a package that may not name the word. The
exemption set moves from five domain packages to six, the pinning test moves with
it, and the justification is written into the guard itself. A new assertion —
`test_the_exempt_domain_packages_import_no_engine` — now holds every exempt domain
package to the rule the ban exists to protect, which previously only the owner
surface was checked against.

---

## 11. Derivative and leverage limitations

Inspected and preserved rather than extended. `MarketMode` already carries `SPOT`,
`PERPETUAL`, `MARGIN` and `FUTURES_DATED` as part of market identity, so leveraged
instruments are representable and the spot assumptions are not corrupted. No
liquidation or funding engine was built.

Where the domain genuinely cannot answer, the figure is refused with the blocker
named:

- **`deployed_capital`** is `Absent` when any open line is short or in a
  non-spot mode. What such a position ties up is *margin*, which no record in
  this domain holds, and reporting cost basis under the name "deployed capital"
  would understate what a leveraged account has at stake.
- **`incremental_capital_required`** is `Absent` for the same two cases, while
  `incremental_notional` is still reported — two figures, because they are two
  facts.

**Stated limitation:** `deployed_capital` is all-or-nothing. One perpetual makes
the figure absent for the whole portfolio, including its unleveraged spot longs.
That is the conservative direction of error and it is a real coarseness; the fix
is a per-line margin field, which needs a venue contract this milestone does not
build.

---

## 12. Persistence integration

`reading.py` is the only module that touches persistence, asserted by
`test_only_the_reading_module_reaches_persistence`. It introduces no store, adds
no repository and **writes nothing** — `test_reading_writes_nothing` compares the
file list and the write-journal length before and after a full read.

Reads go through `store.ledger` (resolved, never raw), `store.plans`,
`store.portfolios` and `store.risk`. `read_exposure_lines(at=…)` reconstructs what
the store *knew* at a past instant on the `written_at` axis, which is what makes a
past portfolio reading reproducible after a correction is filed.

Nothing rebuildable is persisted:
`test_nothing_in_this_package_is_a_persisted_record_kind` asserts no exported type
appears in the store's `SPECS` table, and `test_no_projection_here_has_a_decoder`
asserts every projection has `to_payload` and **no** `from_payload` — the shape
`Position` already uses: exportable, and impossible to read back into the store as
truth.

### The sizing primitive, and its recorded decision gap

`geometry.maximum_quantity_for_risk(direction, *, allowed_risk, entry, stop,
base_asset)` is a **primitive, not a product**. It reads no equity, resolves no
limit, consults no portfolio and recommends nothing;
`test_the_sizing_primitive_reads_no_equity_and_no_portfolio` pins its whole
signature so a portfolio argument cannot be added quietly.

**Recorded decision gap.** It deliberately does *not* decide what `allowed_risk`
should be, because that needs an equity contract this build does not have: equity
requires a mark for every holding, and no mark source exists. `AP` §15.4 places
Buying Power in the risk layer and states it is not built at the portfolio
boundary *"because placing it in Portfolio would give the portfolio object a
recommendation."* Closing the gap requires (a) a mark source and (b) an owner
decision about which equity figure sizing reads — the latest snapshot, a
reconciled balance, or a stated one. **Neither was smuggled in.**

---

## 13. BK and BJ integration

**BK.** A trade recorded by `fmits trade record` is consumable by this engine with
no manual transformation, demonstrated against real records rather than fixtures:
`test_a_trade_recorded_by_bk_is_consumable_with_no_transformation` records a trade
and reads back the account, market, book, direction, quantity, average entry, the
**stop taken from the plan BK wrote**, and an open-risk figure. Part 11's full
flow — account · plan · trade · position · state · risk · second proposal — is
`test_a_second_proposed_trade_is_evaluated_against_the_first`. No exchange API is
touched anywhere in the suite.

**One divergence, pinned rather than left latent (report 0019, H3).** After a
partial exit, `fmits trade show` reports capital at risk from the position's
**maximum** exposure and this engine reports it from what is **still open** — 800
USDT against 480 USDT on the same trade. Both are correct and they answer
different questions; BK already warns about the gap on its own page (`TC-W5`) and
`test_this_engine_measures_open_exposure_and_bk_measures_maximum_exposure` states
the relationship from the other side.

**BJ is unchanged.** `fmits today` is not modified, not read and not extended, per
Part 13. The integration point is `fmis.today.sections.portfolio_overview`, whose
`unmeasurable` `NotAvailable` currently reads *"open risk needs a mark for every
holding and a stop for every open position; no mark source exists and no plan is
recorded"* and is owned by *"the risk layer (roadmap C4/C6)"*. **Two of those three
blockers are now gone**: plans are recorded (BK) and open risk is computed (BL).
The remaining blocker is the mark source. Wiring `read_portfolio` into that
section is a one-function change and belongs to the milestone that also supplies
marks — doing it here would have produced a workspace section whose every figure
was `Absent`.

---

## 14. Failure modes

Every one the brief names, each with a stated reason and none substituting a
plausible value:

| Failure | Behaviour |
|---|---|
| Missing equity | `Absent`; leverage and every percent-of-equity limit become `Absent` |
| Missing stop | `Absent` naming the market; open risk absent, **never smaller** |
| Missing account | structurally impossible — every line carries one |
| Missing position price | `cost_basis` and `capital_at_risk` `Absent` |
| Malformed trade geometry | `RiskGeometryError`, surfaced as `Absent(reason)` |
| Multiple venues | separate `INSTRUMENT` buckets, one `SYMBOL`/`ASSET` bucket |
| Same symbol on multiple venues | duplicate-detected, noted `PR-N1`, never netted |
| Conflicting directions | gross and net both reported; neither derived from the other |
| Missing group classification | `UNCLASSIFIED` bucket, `PR-N7` note |
| Unavailable cash | `Absent`; available capital and `MIN_RESERVE` follow |
| Stale valuation | `equity_as_of` and `equity_staleness` (report 0019, H2) |
| Unknown fees | `RISK_BASIS` on every figure |
| Unsupported leveraged risk | `deployed_capital` and capital-required `Absent`, margin named |
| Two stops for one position | `Absent` naming both; no stop is chosen |
| Dangling `plan_id` | `Absent` naming the missing commitment |
| Foreign quote currency | `Absent` naming the missing rate; never converted |
| Limit in another currency | that limit `Absent`; **the other limits still evaluate** |

---

## 15. Tests

**368 new tests**: 367 in seven new files plus one helper module (4,569 lines), and one
added to the pre-existing ADR-0028 boundary guard (§10).

| File | Tests | Covers |
|---|---|---|
| `test_portfolio_risk_geometry.py` | 30 | the sign rule and every boundary of it |
| `test_portfolio_risk_models.py` | 37 | value types, refusals, read-time projections |
| `test_portfolio_risk_exposure.py` | 60 | every portfolio shape the brief names |
| `test_portfolio_risk_constraints.py` | 89 | every scope, unit, boundary and refusal |
| `test_portfolio_risk_impact.py` | 73 | detection, before/after, notes |
| `test_portfolio_risk_reading.py` | 45 | the store, the BK flow, determinism |
| `test_portfolio_risk_architecture.py` | 33 | the boundary guards |

Every shape Part 15 lists is a separate test with its own arithmetic: empty · one
long · one short · long + short · same symbol duplicate · same symbol opposing ·
multiple accounts · multiple venues · multiple quote currencies · missing equity ·
missing stop · risk one unit below the limit · exactly at it · one unit above ·
the 2 % ceiling · total open risk · account, venue, symbol, asset and
correlation-group concentration · before/after comparison · deterministic rerun ·
serialization · no provider imports · BK and BJ suites green.

---

## 16. Coverage

Measured with `coverage.py` 7.15.4 run through `uv run --no-project`, which builds
an ephemeral environment: **`pyproject.toml` and `uv.lock` are unchanged and no
package was installed into the project venv** (`.venv/bin/python -c "import
coverage"` still fails, verified).

```
src/fmis/portfolio_risk/__init__.py           9      0   100%
src/fmis/portfolio_risk/classification.py    70      5    93%
src/fmis/portfolio_risk/constraints.py      265      5    98%
src/fmis/portfolio_risk/exposure.py          71      2    97%
src/fmis/portfolio_risk/geometry.py          55      3    95%
src/fmis/portfolio_risk/impact.py           295     17    94%
src/fmis/portfolio_risk/models.py           359     15    96%
src/fmis/portfolio_risk/reading.py           94      0   100%
-------------------------------------------------------------
TOTAL                                      1218     47    96%
```

**Reported honestly: this is 96 %, not 100 %, and the 47 uncovered lines were
classified one by one rather than characterized in a sentence.**

- **43** are `raise TypeError(...)` / `raise DomainValidationError(...)` type and
  validation guards in `__post_init__` blocks and function preambles.
- **4** are defensive branches unreachable through this package's public entry
  points, all in `constraints.py`: two `state.breakdown(...)` absent-arms (lines
  380 and 414 — `build_state` always builds all eight axes, so only a hand-built
  `PortfolioState` could reach them) and the money-versus-ratio mismatch arm
  (lines 574 and 580 — `RiskLimit` refuses that construction one layer down,
  recorded in `test_a_money_limit_cannot_be_stated_with_a_ratio_unit_at_all`).

**No uncovered line is business logic.** An earlier draft of this report claimed
*"every uncovered line is a defensive type guard"*; a line-by-line audit during
final verification showed that was true of 44 of 56, not all of them. Six tests
were added to close the reachable remainder — which is what moved the figure from
95 % to 96 % — and the four that survive are described above rather than
generalized.

## 17. Mutations

**64 probes across two rounds, 62 killed, 2 survivors, both proven equivalent.**
The harness lives in the session scratchpad, applies one source mutation at a
time, runs the BL suite, and restores the file in a `finally` block.

Round 1 (36 probes) covers the categories the brief names: LONG risk sign · SHORT
risk sign · `>` vs `>=` · risk exactly at the ceiling · gross vs net · long/short
inversion · account, venue and symbol aggregation · before/after swap · duplicate
detection side · missing value becoming zero · concentration numerator/denominator
swap. Round 2 (28 probes) covers the composition root: account attribution, stop
resolution, book filtering, supersession, the pending filter, snapshot currency
checks, headroom direction, binding-set membership.

### A harness defect that invalidated a whole round

The first round-2 run reported **28/28 killed**. It was wrong. A mutation such as
`/` → `*` changes no byte count, and CPython invalidates a `.pyc` on
`(mtime, size)`; on a filesystem with one-second mtime granularity, a
write-mutate-run-restore cycle inside one second leaves stale bytecode in place,
so the suite runs code that is neither the original nor the mutant. The harness
now clears every `__pycache__` before each run and after each restore. **The
re-run with cache invalidation reported 7 survivors**, five of which were real
test gaps. This is recorded because a clean mutation score obtained from a broken
harness is worse than no mutation score at all.

### The five real gaps, and what closed them

| Probe | Gap | Test added |
|---|---|---|
| N01 | folding every account's fills together — each line would claim the *combined* size | `test_each_accounts_line_carries_only_that_accounts_fills` |
| N07 | no short position was ever read from the store, so `abs(net_quantity)` was untested | `test_a_short_position_is_read_with_a_positive_magnitude` and one more |
| N13 | `cash − reserved` was only ever exercised with reserved at zero | `test_available_capital_subtracts_reserved_rather_than_adding_it` |
| N18 | nothing asserted that an `AT_LIMIT` result is **binding** | three tests, constraints and impact |
| N28 | the zero-total share guard was never reached | `test_a_share_of_a_zero_total_is_undefined_even_when_the_bucket_exists` |

One probe (N09) was withdrawn as **invalid, not survived**: `x + ""` changes no
behaviour. It was replaced with a mutation that keys mark lookup on the pair
symbol instead of the full market — which the suite killed.

### The two survivors, classified honestly

**M05 — `current > limit` → `current >= limit`. Equivalent, proven.** The two
operators can differ only where the operands are equal, and the preceding
equality branch returns `AT_LIMIT` before that line is reached. Verified
empirically for `Decimal` and `Money` including differing canonical spellings.
The branch it shadows is *not* untested: probe M06 deletes the equality branch and
the suite kills it, so the boundary is fully pinned from the other side.

**N02 — dropping the `is_open` filter. Equivalent, by an invariant owned
elsewhere.** `Position.__post_init__` refuses a `CLOSED` position that is not
`FLAT`, so the direction guard catches every closed position even without the
state guard. Both guards are kept — the invariant lives in another package, and a
guard that depends on someone else's invariant should not be the only one.
`test_a_closed_position_is_excluded_by_two_independent_guards` records the
reasoning so this does not read as a gap later.

**Neither survivor is labelled cosmetic, and neither is functional.**

---

## 18. Hostile-review findings

Conducted as a separate pass and recorded in
[report 0019](0019_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_HOSTILE_REVIEW.md).
Three findings, all fixed in this milestone:

| # | Severity | Finding |
|---|---|---|
| **H1** | **P1** | Two longs on the same base asset under different quote currencies (`BTCUSDT`, `BTCUSDC`) read as unrelated symbols — correlated exposure presented as diversification. Fixed by the `ASSET` axis and `same_asset_elsewhere` / `PR-N10` |
| **H2** | **P2** | A snapshot's equity was indistinguishable from a current one, so every percent-of-equity limit could be measured against a months-old figure. Fixed by `equity_as_of` and `equity_staleness` |
| **H3** | **P2** | BK and BL report different capital-at-risk figures after a partial exit. Both correct; pinned as a stated property |

One further defect was found by the test suite during development and fixed: a
limit stated in a currency the portfolio is not denominated in **took the whole
constraint check down** with a `DomainValidationError`, rather than producing one
indeterminate result. One mis-typed limit costing the owner every other limit's
evaluation is precisely backwards.

---

## 19. Live domain demonstration

Real records through the real store, no exchange API:

```
fmits trade record BTCUSDT --direction long --account binance_spot --book swing
      --entry 60000 --stop 58400 --size 0.5 ...        (Milestone BK)

read_portfolio(store, portfolio_id="main", base_currency=USDT, as_of=…)

  lines                1
    binance_spot · binance:BTCUSDT:spot · long 0.5 BTC
    entry 60000 · stop 58400 (read off the plan BK wrote)
  open risk            800 USDT
  gross exposure       Absent — "no mark was supplied for binance:BTCUSDT:spot;
                       this build reaches no venue and ingests no price"
```

Then a second candidate against it:

```
evaluate_impact(proposed=2 ETH long @3000, stop 2800, before=…, budget=…)

  before open risk     800 USDT
  after  open risk     1200 USDT
  incremental          +400 USDT
  total_open (1000)    WITHIN  →  EXCEEDED
  newly binding        ('total_open',)
  remaining budget     −200 USDT
```

The engine reports the breach as a fact and names it. It does not say whether to
take the trade.

---

## 20. Files changed

**Added — production (8 files, 3,767 lines):** the `src/fmis/portfolio_risk/`
package listed in §2.

**Added — tests (8 files, 4,569 lines):** `tests/portfolio_risk_helpers.py` and
the seven `tests/test_portfolio_risk_*.py` files.

**Added — documentation (2 files):** this report and report 0019.

**Modified — 1 pre-existing test file:**
`tests/test_directional_vocabulary_boundary.py` — the ADR-0028 §5 exemption set
widened from five domain packages to six, its pinning test updated, its docstring
extended with the justification, and one new guard added holding every exempt
domain package to the no-engine rule (§10).

**Modified — product documents (4):** `FMITS_PRODUCT_BACKLOG.md`,
`FMITS_PRODUCT_CHANGELOG.md`, `docs/AI_HANDOFF/CURRENT_STATE.md`,
`reports/README.md`.

**No production file outside `src/fmis/portfolio_risk/` was modified.** No domain
type changed. No ADR written or amended. `pyproject.toml` and `uv.lock` unchanged.

---

## 21. Release validation

| Gate | Result |
|---|---|
| Focused BL suite | **367 passed** |
| BK trade-capture suite | **passed** (6 files) |
| BJ today suite | **passed** (7 files) |
| BI persistence suite | **passed** (8 files) |
| BH domain suite | **passed** (7 files) |
| Full repository suite under `-W error` | **6,679 passed** (6,311 before; +368) |
| Coverage | **96 %** of the eight new modules, reported honestly (§16) |
| Mutations | **64 probes, 62 killed, 2 proven-equivalent survivors** (§17) |
| Import cycles | **0** across 205 modules |
| Export collisions | **0** across 811 public names |
| New runtime dependencies | **0** |
| `pyproject.toml` / `uv.lock` | **unchanged** |
| `git diff --check` | clean |
| Markdown links | valid |
| Unrelated file changes | none |
| Pre-existing untracked research documents | all preserved |

---

## 22. Commit state

**Nothing has been committed. NOTHING HAS BEEN PUSHED.**

`CLAUDE.md` requires explicit owner authorization before any commit, merge,
rebase, tag or push. The milestone brief authorizes two commit messages but the
repository rule is the stricter of the two and governs, so this work stops here
and asks.

The two commits, prepared and not made:

```
feat(portfolio): add Portfolio Intelligence and Risk Engine
docs(product):   record Portfolio Intelligence and Risk Engine
```

---

## 23. Recommended next milestone

**One only: a mark source, and the workspace section it unblocks.**

Every absent figure in this engine traces to the same missing input. Open risk,
duplicate detection, the constraint engine and the whole before/after comparison
work today; **gross exposure, net exposure, leverage, concentration shares and
every percent-of-equity limit are `Absent` because no price reaches the owner
half.** The market half already fetches closed candles for every command the owner
runs, and `IMPLEMENTATION_ROADMAP_V1` C6 already names the answer — *"the last
available closed-candle close from `fmis.providers`/`fmis.data`"*.

That milestone would supply marks through an adapter at the composition root,
write the `PortfolioSnapshot` that makes equity real, and wire `read_portfolio`
into `fmis.today.sections.portfolio_overview` — the one-function change §13
identifies. It converts this milestone's engine from correct-and-mostly-absent
into the daily number the owner actually reads, and it is the last input the
sizing primitive needs before Buying Power can be built on a real equity contract.
