# Report 0023 — Statistics & Performance Engine (Milestone BP) — Implementation Record

| Field | Value |
|---|---|
| **Report number** | 0023 |
| **Title** | Statistics & Performance Engine (Milestone BP) — Implementation Record |
| **Date** | 2026-08-18 |
| **Report type** | Implementation |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `e1cfad0` — the production code and tests of this milestone, committed on top of `3a2bd3a`. This record and the product documents are committed directly on top of it |
| **Status** | Final |

---

## 1. What shipped, in one sentence

FMITS can now answer *"does this system actually have an edge"* from recorded
history alone — counts, performance, risk, excursion quality, an equity curve, a
drawdown curve and twelve breakdowns — with **every rate refused below a stated
sample floor**, every figure carrying the number of trades it rests on, and
nothing estimated, inferred, predicted or calibrated.

**One new package, five new commands and a ninth `fmits today` section.**

```
fmis.statistics   15 modules   a pure projection: no record kind, no repository,
                               no write path, nothing stored anywhere
```

---

## 2. The design in five decisions

### 2.1 It stores nothing, and that is architectural rather than a simplification

`AP` §25.2 classifies **"Cohort statistics, bias metrics"** as `Aggregate` —
*recomputable, disposable*. So this milestone adds **no `RecordKind`, no
repository and no write path at all**. Delete every figure it produces, run it
again over the same store, and the answers are identical; there is no second
copy of anything to drift from the records it summarizes.

A guard asserts it: no store write verb — `create`, `update`, `replace`,
`publish`, `append_event`, `append_lines`, `atomic_write`, `revise`, `admit`,
`rebuild_index` — appears anywhere in the package, and a live run over a real
store leaves it byte-identical.

### 2.2 The sample floor is a boundary, not a caveat

`AP` §20.7 rule 2 requires the guard *"at the boundary, so no surface can route
around it"*. `fmis.statistics.sampling` **is** that boundary: nothing else in the
package divides, averages, takes a median or picks an extremum. A statistic
cannot be computed without passing through a function that has already decided
what to do about a missing value and a small sample.

**The floor governs rates, and not counts.** Two different things, and
conflating them is the trap:

* A **count** is a fact at any `n`. *"You closed three trades and lost on all
  three"* is true, and refusing to say it would be a different dishonesty from
  overstating it. `Tally` carries its denominator and no floor.
* A **rate** is a claim about a process. Win rate, loss rate, profit factor,
  payoff ratio. These consult `SamplePolicy` first, and below it return
  `InsufficientSample(n)` — `Absent` with its `sample_size` populated, which is
  the shape `fmis.provenance` already designed for exactly this face.

The default floor is **30**, and `SAMPLE_FLOOR_BASIS` is printed beside every
refusal: *"A floor, never a sufficiency claim. `AP` §20.1 puts genuine
conditional analysis at 5,000 resolved episodes and calls 100 'almost nothing
statistically'. Passing it establishes nothing."*

### 2.3 Two sources of trade, one vocabulary, and the difference is never hidden

A **simulated** trade (`fmis.paper`) carries an R multiple, an excursion in both
directions and a bar count — frozen at close by `AP` §25.3, because kline history
is not permanent. A trade the owner **recorded** by hand (`fmis.trade_capture`)
carries none of them, because nothing froze them.

A corpus mixing the two is the normal case, and an average MAE computed over it
without saying so would let the simulated trades' excursions stand for every
trade the owner ever took. So:

* a **total** with a missing contributor is `Absent` —
  `fmis.portfolio_risk.sum_or_absent`, called rather than restated;
* a **distribution** is computed over the members that have the value and
  **reports that `n`**, naming what was excluded and why.

`ST-2` carries this to every page, and `QualityStatistics` over a corpus of
hand-recorded trades says `n = 0` rather than producing a number.

**A recorded trade's R multiple is computed, and a running trade's is not.** The
denominator already exists — `TradeView.capital_at_risk`, which is
`fmis.plan.capital_at_risk` over the plan's stop and the position's largest
exposure — so dividing the realized profit and loss into it is one division and
makes hand-recorded trades comparable with simulated ones on the one scale that
crosses markets. A trade still running has no final R: averaging a live figure
beside finished ones would mix *"what this trade did"* with *"what it has done
so far"*.

### 2.4 The equity curve refuses to interpolate, and the drawdown curve refuses to finish a decline that has not recovered

One step per closed trade and nothing between them. A curve drawn daily between
two closes would be inventing the account's value on days no measurement was
taken, and drawing it truthfully would need a mark for every open position on
every one of those days — which `ST-3` records this system does not keep. Open
trades are tracked separately and never fold in: their contribution needs a
mark, is unrealized, and reverses, so including it would make yesterday's curve
change today.

The owner's opening capital is recorded nowhere, so without `--starting-equity`
this is a **cumulative realized profit-and-loss curve**: every shape statement
holds and every percentage is `Absent` with the reason.

On the drawdown side, a decline that has not recovered is reported as
**ongoing** rather than as a finished episode — the single most flattering error
available here, since it turns *"I am still down and have been for four months"*
into a completed episode with a duration. The percentage denominator is the
equity **at the peak**, not the starting equity: a 500-unit decline from a
doubled account is a smaller drawdown than the same decline from the opening
balance, and dividing both by the opening balance would report them as equal.

### 2.5 The multiplicity hazard is a mechanism, not a paragraph

`TRADER_WORKSPACE` §3.4.12 is explicit that with roughly twenty-five
segmentations and no correction, *"a new set of striking-looking cells will
appear, and the defence is a document, not a mechanism."*

The mechanism is `BreakdownSet.cells_examined` — the count of every cell produced
across every dimension, carried on the object and printed beside the
breakdowns. This engine applies **no** multiplicity correction, has no basis to
choose one, and states the number instead of implying there was nothing to
correct. Every cell also carries its own `n` and its own floor, so the cells that
survive slicing are the ones with enough trades behind them and the rest say so.

---

## 3. Six refusals, and why each earns its place

| # | The refusal | What it prevents |
|---|---|---|
| 1 | **No candle is ever fetched.** A finished trade contributes its *frozen* outcome | A past statistic silently depending on what the venue still serves — `AP` §25.3's whole reason for freezing MAE and MFE |
| 2 | **Figures are never summed across quote assets.** A store settled in two produces two sets | One wrong number in place of two right ones; this system ingests no rate that would cross them |
| 3 | **A closed trade with no stateable result is excluded from the curve and named**, never stepped by zero | A flat segment where the truth is unmeasured, and a drawdown computed over a curve that does not exist |
| 4 | **A zero denominator is undefined, not large.** Profit factor with no losing trade; capture efficiency with no favourable excursion; an R multiple over a capital-at-risk of zero | The usual way each of those three figures lies |
| 5 | **A rate below the floor is refused outright**, not printed with a caveat | A caveat beside a number is read as a number |
| 6 | **A page refuses to emit a line wider than the page it claims**, and every unbounded value wraps before it gets there | §5.9 — a 145-column store path, and two tables that budgeted their columns before any value was substituted |

---

## 4. What the owner can do that was impossible before

```
fmits statistics              every family, every curve, every cut
fmits performance             what the trades made, and how they behaved
fmits expectancy              the one question, with the sample in front of it
fmits equity                  the curve, the drawdowns, and the last steps
fmits trades summary          the counts, and the last trades one per line
fmits statistics --as-of …    the figures as they stood at a past instant
fmits today                   a ninth section: is this working, and on what n
```

Every one is read-only, deterministic and offline.

---

## 5. Findings — every one recorded rather than quietly fixed

Two were found by the tests as they were written, three by mutation probes
against a suite that was already green, one by a coverage gap, one by an
architecture guard, and one by the independent release gate — after all of
those had passed (§5.9), and one more by a coverage test written for that
fix (§5.10). Three are recorded and not fixed (§5.11).

### 5.1 P1 — the default regime dimension named a dimension nothing emits *(fixed)*

`DEFAULT_REGIME_DIMENSION` was `"trend"`. `fmis.market_regime` emits
**`structure`**, **`volatility`** and **`participation`** — and has never emitted
`trend`. So the per-regime breakdown placed **every trade in `UNCLASSIFIED`**,
silently, and the cut the brief asked for was dead on arrival.

It survived every test that existed because no fixture carried a real frozen
snapshot; the first one that did failed with `KeyError: 'trend'`. This is the
same class as `BO`'s `PT-W6` — a default that could never match — and it is why
the fix is not merely the corrected string: the value is copied rather than
imported (this package may not reach the market half), and
`test_statistics_architecture` now asserts the copy still matches
`RegimeDimensionName`. The copy-and-guard the boundary tests already use for the
market-half list itself.

### 5.2 P1 — a corrupt store raised past this layer *(fixed)*

`collect_trades` wrapped the two listing calls in a `try` that re-raises as
`CorpusUnreadableError`, and read the market snapshots **before** it. A store
whose index was corrupt therefore raised the store's own `StoreIntegrityError`
straight past the boundary, so a caller catching this package's errors saw an
unhandled traceback for the one condition the class exists to name. Every store
read now sits inside the block.

### 5.3 P2 — two public names collided with existing exports *(fixed)*

`breakdown_by` against `fmis.portfolio_risk.breakdown_by`, and
`StoreUnreadableError` against `fmis.today.StoreUnreadableError`. The repository
holds zero public-name collisions as a measured invariant, and the zero-collision
guard caught both — the third time it has done so, after `BL`'s `stop_distance`
and `read_exposure_lines`. Renamed to **`cut_by`** and
**`CorpusUnreadableError`**, each with the reason recorded at the definition.

### 5.4 P2 — `CollectedTrades` validated nothing *(fixed)*

A corpus holding one wrong value failed several layers down, inside a reduction,
as an `AttributeError` about a field the caller never mentioned. Found by a
fixture typo. It now checks its four fields at construction and names both the
collection and what was wrong with it.

### 5.5 P2 — the day's page printed the floor's justification four times *(fixed)*

The sample floor's basis is five sentences. Rendered against each refused figure
it made the workspace section unreadable — which makes the guard **easier** to
ignore, not harder. The basis is now stated once per section in
`PerformanceSummary.floor_note`, and each refusal carries only its own two
numbers, derived from `n` and the floor rather than paraphrased from the
sentence.

The first attempt at that shortening sniffed `Absent.sample_size` to decide
whether a refusal was the guard's. That was wrong: `sample_size` is also
populated for an empty population and for a zero denominator, so a mean over no
trades was labelled *"below the floor"*. The rule is now explicit — only the two
figures the guard actually governs are passed `floored=(resolved, floor)` — and
a population of zero says *"no resolved trade to state this from"* rather than
*"below the floor"*, because both are true and only one says what to do.

### 5.6 Three test gaps found by mutation probes against a green suite *(fixed)*

* **The largest loss** was asserted against a fixture whose two losers were both
  −50, so swapping the extremum for its opposite changed nothing. A fixture with
  unequal losses now distinguishes them.
* **The absence that decides `UNRESOLVED`** is net's, not gross's — and the
  fixture made gross default to net, so the two were indistinguishable. The
  builder gained an `ABSENT` sentinel so a genuinely unstateable gross can be
  expressed.
* **The excursion block's all-or-nothing collapse** was only exercised by a
  corpus in which every figure happened to be stateable, so turning the `all`
  into an `any` survived. A partly-stateable corpus now proves the collapse
  cannot swallow figures that exist.

### 5.7 A coverage gap that was a real hole, not a formality *(fixed)*

Nothing drove a **finished paper trade** through `collect_trades`: every
collection test wrote hand-recorded trades. So the entire `stat_from_paper`
mapping — the half of this engine that reads frozen outcomes — was exercised only
by a type refusal. Seven tests now activate a plan, replay it over hand-built
bars through the product's own simulator, and collect it.

### 5.8 Two mutation survivors, proven equivalent rather than absorbed

* **An open trade contributing a step to the curve.** Removing the phase check
  changes no reachable outcome, because the next guard drops any trade whose
  `closed_at` is `Absent` — which every open trade's is.
* **A frozen excursion read from the monitor instead of the outcome.** `collect`
  calls `list_paper_trades` with **no bars**, so the monitor's excursion *is* the
  frozen one; the two expressions read the same value by construction. The
  property that makes it equivalent is the one this milestone asserts
  architecturally, and it is separately guarded.

Two further probes were run and are recorded as equivalent for the same class of
reason: a negative drawdown depth (`_depth`'s peak is the running maximum by
construction) and an R multiple over a capital-at-risk of zero
(`stop_distance` refuses a non-positive distance, over a positive quantity).

**Two unreachable branches were removed rather than marked.** The histogram's
bin search had a fall-through case that could not happen, and the snapshot sweep
hand-rolled a type filter the repository already owns. Both were rewritten so
the totality is structural — the bin index is *counted* (`sum(1 for edge in
edges if value >= edge)`) rather than searched, and `SnapshotRepository.snapshots()`
does its own filtering. An unreachable branch is one nobody can test and everybody
has to reason about.

### 5.9 P2 — the pages ran to 145 columns, and nothing checked *(fixed)*

Found by the release gate. Every module docstring in this package claims *"78
columns, ASCII, no colour — the geometry `fmits today` already uses"*, and
`fmis.today.render` has enforced that with `_require_fits` since `BJ`. These
pages claimed the same geometry and enforced nothing, so:

* the **store path** was printed on one line — 145 characters against a real
  temporary directory;
* the **trades-summary table** budgeted 79 columns before any value was
  substituted, and a thirty-digit R multiple took one row to 101;
* a long **breakdown cell key** — a setup term or an account id, both the
  owner's own words — pushed its row over.

Three fixes and a guard. Unbounded tokens now wrap, **including mid-token**,
which is `fmis.paper.render`'s own rule: a truncated path is one the owner
copies and cannot open, and a truncated id is one they cannot look up. The two
tables changed shape rather than gaining a truncation — a shortened number is a
different number, so each row became a wrapped pair. And `_fitted` now refuses
to emit a page containing a line wider than the page claims, which is
`fmis.today.render`'s choice made for its reason: every unbounded value is
wrapped before it arrives, so an over-wide line is a defect in that module
rather than an unusual input.

**The gate's own first measurement was wrong and is worth recording.** It
counted bytes: an em-dash is three bytes and one column, so every line of prose
read as over-wide. The corrected measurement — characters — found the two real
offenders among eleven reported. The guard measures characters, and says so.

### 5.10 P3 — the day's page could render a dataclass repr *(fixed)*

Found by a coverage test written for §5.9's fix. `PerformanceSummary.quote_asset`
is a `str | NotAvailable`, and the workspace block interpolated it straight into
an f-string — so a summary with trades and no settlement asset produced 185
characters of `NotAvailable(reason=..., owned_by=..., forbidden_inference=...)`
on a page that raises above 78.

`performance_summary` never produces that pairing: it sets the asset whenever
trades exist and returns early when they do not. But `PerformanceSummary` is
**exported** from `fmis.today`, so a consumer can build one, and the failure
mode is `fmits today` raising rather than rendering. The block now goes through
`_value_text`, which is the helper that exists for exactly this, and wraps.

### 5.11 Not fixed, and recorded

**`ST-10` — a non-terminating quotient prints in full.** `2 ÷ 3` renders to the
full precision of the arithmetic. Shortening it would be a rounding policy this
system does not set — `BN`'s and `BO`'s own finding, inherited. Two consequences
were handled rather than absorbed: breakdown tables show the division as a
**pair of counts**, which is exact at any width, and the day's page **wraps**
rather than truncating, because that page raises on any line over 78 columns and
a shortened number is a different number.

**`ST-11` — average capture efficiency is a mean of ratios** and is dominated by
trades whose favourable excursion was small: one that showed 0.1 R and lost 1 R
contributes −10. The median is the more readable summary; both are shown and the
basis says so.

**Risk utilization covers this corpus, not the portfolio.** `fmis.portfolio_risk`
owns *"is this portfolio within its limits"* and `fmits approve` asks it. What is
read here is the single ceiling the owner configured, divided into the open risk
of the trades on the page — a narrower figure, labelled as such wherever it
appears, because two figures measuring different populations must not share a
name.

---

## 6. Verification

| Check | Result |
|---|---|
| Focused BP suite | **570 tests** across 11 files |
| Full suite | 7,805 → **8,378 tests** (+573), passing identically under `-W error` |
| Coverage | **100 % statement and 100 % branch** of all 15 new modules — 1,860 statements, 614 branches, **0 missed** |
| Coverage, modified `fmis.today` | **100 % statement and branch** of `builder`, `models`, `render` and `sections` |
| Mutation | **60 probes, 60 detected, 0 survivors**; four further probes were run, proven equivalent and are recorded as such rather than left in the run (§5.8); byte-identical restoration verified by SHA-256 with the bytecode cache cleared on both sides of every probe |
| Record kinds | **0 added** (15, unchanged) — `AP` §25.2 |
| Public exports | 1,045 → **1,147**, **0 collisions** |
| Import cycles | **0**, across 257 modules |
| Runtime dependencies | **0 new** — standard library and `fmis` only; `pyproject.toml` and `uv.lock` byte-identical to `HEAD` |
| Cold import | `import fmis.pipeline` does not load `fmis.statistics` |
| Store integrity | byte-identical after all five commands run over a real store |
| Directional vocabulary | **no ADR-0028 exemption taken** — group keys come from the enum at runtime |
| Live | a store built entirely through `fmits trade record` / `close`; every figure hand-verified |

**The live demonstration was rebuilt twice**, and both harness defects are
recorded because a demonstration its own harness can mis-build proves nothing:
the first paired exit prices to plans by position in `store.plans.all()`, which
is index order and not creation order, so a short was closed at a long's target;
the second interleaved recording and closing, which the append-only write journal
correctly refused.

**Hand-verified against the live store** — entry 62000, stop 60000, size 0.5,
exit 66000, one unit of fee each side: net 1998, initial risk 1000, R 1.998.
Gross profit 3994, gross loss 1904, net 2090, profit factor 2.0977, expectancy
418 USDT, average R 0.5973, maximum drawdown 1506 over 26 days, recovered. Every
one matches the page.

---

## 7. What this milestone does not do

No machine learning, no AI analysis, no trade-review engine, no news, macro,
on-chain or funding data, no execution, no broker, no Telegram, no visualization
library and no web dashboard — the brief's forbidden list, asserted as
source-level absence over the whole package.

`calibrated_probability` (`AP` §20.6) remains **`ABSENT` until earned**, and this
milestone does not earn it. `AP` §20.5's behavioural and bias metrics are **not**
built: they need the `DecisionEpisode` corpus that `C10` owns, and stale-proposal
rate, invalid-entry rate and rejection quality are computable only from the whole
proposal lifecycle. The `n` guard those metrics will need exists now and is
load-bearing before they arrive, which is the roadmap's own instruction.

---

## 8. Files

**New production** — 15 modules, 5,280 lines: `src/fmis/statistics/`.

**New tests** — 12 files, 5,218 lines, 570 tests.

**Modified production** — 6 files, all additively: `pipeline/cli.py` (five
commands and one subcommand), `today/{__init__,builder,models,render,sections}.py`
(a ninth section, `TODAY_SCHEMA_VERSION` 3 → 4).

**Modified tests** — 12 files, every change a guard **widened by name with its
justification recorded**, never relaxed: the command registry (three separate
guards), the workspace section list and numbering, the schema version, the
`fmis.pipeline.cli` import allow-list, and the day-page magic-number guard.

Two of those deserve naming, because in both cases the guard was right and the
**code** moved rather than the rule:

* `fmis.today.sections` may not type `86400`. The duration formatter moved to
  `fmis.statistics.duration_text`, which is now the one place a duration becomes
  text in this product.
* `fmis.pipeline.cli` may not reach a domain package. The first draft imported
  `fmis.provenance` to build an `Absent`; the three absences moved into
  `fmis.statistics.inputs`, where every other conversion already lives.
