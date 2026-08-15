# Position Sizing & Trade Approval Engine (Milestone BN) — Implementation Record

| Field | Value |
|---|---|
| **Report number** | 0021 |
| **Title** | Position Sizing & Trade Approval Engine (Milestone BN) — Implementation Record |
| **Date** | 2026-08-15 |
| **Report type** | Implementation |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `b66a88f` (production code + tests), on top of `4519d0a` |
| **Status** | Final |

---

## 1. What this milestone answers

Every milestone before this one answered *"is there a setup here"* or *"what do I
hold"*. Neither answers the question that actually stands between an idea and an
order:

> **How large may this position be, and do my own limits permit it?**

`fmis.position_sizing` answers exactly that and refuses everything adjacent to
it. It is **not** a judgement about the setup: the setup engine (`AR`) already
produced one, and nothing in this package reads it. It is arithmetic over the
owner's equity, the owner's chosen fraction, the owner's own ceilings and the
positions the owner has already recorded.

`ApprovalResult` is a **deterministic fact**. No model is consulted anywhere in
the package, no probability is attached to anything, and there is no field on any
type that could hold *"take this trade"* or *"skip this trade"* — a guard test
asserts the package names neither. `AP` §15.5, unchanged: *"`EXCEEDED` on the
open-risk budget is a fact; 'don't take this trade' is the owner's conclusion."*

---

## 2. What shipped

### 2.1 One package, nine modules, three tiers

`fmis.position_sizing` — 3,737 lines, **44 new public exports, 0 collisions**
(896 total repository-wide), **0 new runtime dependencies**, **0 import cycles**.

| Tier | Modules | May reach |
|---|---|---|
| **Computing** | `models` · `policy` · `sizing` · `approval` | the trading domain only. No venue, no engine, no clock, no path, no numeric literal beyond `0` and `1` |
| **Store** | `reading` | `fmis.persistence`, read-only |
| **Surface** | `inputs` · `compose` · `render` | plus `fmis.valuation`, `fmis.trade_capture` and `fmis.pipeline.prices` |

Every row of that table is an executable guard in
`tests/test_position_sizing_architecture.py`, and the tier membership itself is
pinned so a tenth module is a deliberate edit there.

### 2.2 The chain

```
PositionProposal      what the owner is considering — no size yet
  → PositionSizer            the fraction, the ceilings, one division
  → PositionRecommendation   a quantity, and every figure derived from it
  → ApprovalEngine           the sized candidate against every limit
  → ApprovalResult           APPROVED | BLOCKED | INDETERMINATE, with reasons
```

All seven types the brief names are built, plus three the arithmetic needed:
`ApprovalStatus`, `ReasonScope`/`ReasonClass`, `SizingOutcome` and
`FractionChoice`.

### 2.3 Two commands

**`fmits approve`** — a twelfth command, registered between `portfolio` and
`trade`, because a candidate is sized against the portfolio the command before it
values and is evaluated before the command that records it.

**`fmits today`** gained five fields on every actionable candidate — approval
status, recommended size, open risk after the trade, blocking reasons and
warnings — plus a section-level note saying whether an approval was computed at
all. `TODAY_SCHEMA_VERSION` moved `1 → 2`.

---

## 3. The decisions this milestone made

### 3.1 It duplicates no arithmetic, and the one thing it adds is named

The sign rule, the risk distance, the capital at risk, the maximum quantity for a
risk allowance, the exposure fold, the before/after impact and every limit
comparison are all `fmis.portfolio_risk`'s, **called rather than
re-implemented**. `fmis.portfolio_risk.geometry.maximum_quantity_for_risk`
describes itself as *"a primitive, not a position-sizing product… what it
deliberately does not do is decide what `allowed_risk` should be."* This package
is that missing half and nothing more.

`PositionProposal.reward_distance` is worth naming: it is
`stop_distance(side, entry=target, stop=entry)` — the *same* subtraction with the
entry and the target exchanged, so the sign rule stays written once and a target
on the stop's side of the entry is refused for the identical reason a stop on the
target's side is.

### 3.2 The fraction is resolved, never defaulted — and the ceiling is not a target

Three places, in order:

1. the fraction the owner stated for this trade;
2. **`RiskLimit.default_below_ceiling`** — the field the domain already carries
   for exactly this;
3. **nothing.** `Absent(reason)`, an `INDETERMINATE` approval naming the missing
   input, and **no size**.

`SPEC` §8.1 calls 2 % *"a hard ceiling, not a default target"*. A system that
sized at the ceiling when nothing else was stated would have converted the
specification's ceiling into the specification's target with nobody deciding to.
Mutation probe **P02** plants exactly that and is caught.

### 3.3 Severity is the owner's, at every point it is read

`RiskLimit.severity` decides the class of every portfolio reason, and it decides
one more thing that took a failing test to discover: **an `ADVISORY`
total-open-risk limit does not bound the size.** The first draft passed the
headroom to the sizer unconditionally, so an advisory limit the owner had
explicitly marked *tell me, don't stop me* produced a `BLOCKED` result. The read
now happens in `_binding_capacity`, in the layer that reads policy, and
`PositionSizer` stays a pure function of what it is handed.

| Measured | `HARD_BLOCK` | `ADVISORY` |
|---|---|---|
| `EXCEEDED` | **blocking** | warning |
| `AT_LIMIT` | warning | warning |
| unmeasurable | **indeterminate** | warning |

**`AT_LIMIT` warns rather than blocks.** A ceiling stated as *at most 2 %* is not
breached by a measurement that equals it, so a candidate landing exactly on the
line is approved with the headroom named and the *next* one is blocked. Refusing
a trade the owner's own policy permits is the direction of error that teaches an
owner to stop reading the page.

### 3.4 The status is derived from the reasons, and the object refuses to disagree

Blocking outranks indeterminate outranks approved. The rule is written twice on
purpose: once in `_status_of`, where the answer is produced, and once in
`ApprovalResult.__post_init__`, where it is constructed — so a future second
producer of results cannot skip the check. A result cannot be `APPROVED` while
holding a single blocking or indeterminate reason, and probes **P12**, **P13** and
**P34** all plant that and are caught.

### 3.5 The severity of an unknown age tracks whether anything was checking it

`SWING_TRADING_MVP_BLUEPRINT_V1` §7.2 H-4 blocks on a balance older than *the
owner's configured staleness bound*. With **no** bound configured there is no
bound to be past, so:

* bound set, age known, age > bound → **blocking**;
* bound set, age unknown → **indeterminate** (the owner's own check could not run);
* no bound, age known → **warning**, the age reported and not judged;
* no bound, age unknown → **warning**.

The first draft reported an unknown age as indeterminate unconditionally, which
demoted *every* page for a rule the owner never asked for. An `INDETERMINATE`
that fires on every page is an `INDETERMINATE` nobody reads.

### 3.6 It reports the axes the owner did not constrain

A constraint check structurally cannot report this: it evaluates the limits that
exist, and a page showing every one of them `WITHIN` reads as a portfolio checked
on every axis. It was checked on the axes the owner wrote down. So the engine
adds one thing the constraint engine cannot know — whether a limit exists at all
for this candidate's instrument, its base asset, its account, its groups and the
total open-risk budget — and each gap is a warning naming the key that would
cover it. *An unchecked axis is not an axis that was found acceptable.*

The group gap has **two** sentences, because *"you have written no taxonomy"* and
*"you wrote a taxonomy and no cluster limits"* have two different remedies.

### 3.7 Exactly one, or none — never the first

`budget_in_effect` and `sole_account` both follow the rule `fmis.today.builder`
already applies to budgets and snapshots. Applied to an account it is sharper:
an approval scoped to the wrong account measures the wrong capacity pool and
reports a clean answer about a portfolio the owner does not have.

### 3.8 No ADR was widened and no exemption was taken

**ADR-0028's directional-vocabulary guard covers `fmis.position_sizing` with no
edit.** Six trading-domain packages are exempt because they *hold* a side; this
one does not. It passes `TradeDirection` through opaquely and lets
`fmis.portfolio_risk.stop_distance` own the sign rule, so no exemption was needed
and none was taken. `BM`'s own precedent: *rewording is cheaper than widening a
boundary*. A test asserts the package is absent from both exemption lists and
present in the covered set, so a future exemption is a deliberate act.

**Two existing guards were widened, each inside its own stated extension point.**
`test_trade_capture_architecture.test_the_cli_reaches_neither_the_domain_nor_the_store`
admits `fmis.position_sizing` on the identical footing it already admits
`fmis.today` and `fmis.valuation` — and the rule it actually protects, that
`fmis.pipeline` never reaches `fmis.persistence`, is unaffected and separately
asserted. Four registry tests were extended by one command name.

### 3.9 A stale claim in the standing documentation, corrected

`CURRENT_STATE.md` and `FMITS_PRODUCT_BACKLOG.md` §4 both stated that Milestones
`BJ`, `BK`, `BL` and `BM` were *"not committed, not pushed"*. They are all in
`origin/main` at `4519d0a` — verified with `git cat-file -e` against
`today/builder.py`, `trade_capture/capture.py`, `portfolio_risk/impact.py` and
`valuation/compose.py`. The notes were true when written and were never revised.
Both documents now carry a standing correction; the per-milestone entries are
left unrevised, per this board's point-in-time convention.

### 3.10 Nothing is stored and nothing is executed

No `RecordKind` was added, no repository was touched, no write verb appears
anywhere in the package, and a CLI test observes the store's bytes before and
after a run and asserts they are identical. An approval is a projection over the
ledger and the owner's limits: recompute it and it is equal; store it and it
drifts the first time either moves. `to_payload` exists on all four projections
and there is deliberately no decoder.

---

## 4. Findings — defects and design errors found before release

### F1 · An advisory total-open-risk limit blocked a trade the owner had said not to block

Found by `test_an_exceeded_advisory_limit_only_warns_because_the_owner_said_so`.
The sizer was handed `remaining_risk_capacity` unconditionally, so a spent
*advisory* budget produced `REFUSED` → `BLOCKED`. Fixed by `_binding_capacity`
(§3.3). This is the most consequential finding of the milestone: it applied a
severity the owner did not choose.

### F2 · `INDETERMINATE` fired unconditionally on an undated equity

Found by `test_a_candidate_within_every_limit_is_approved_with_a_size`, which
could not reach `APPROVED` at all. Fixed by making the severity of an unknown age
track whether a bound exists (§3.5).

### F3 · The impact invariant was too strict in one direction

`ApprovalResult` asserted *"an impact exists exactly when a size does"*. Found by
`test_a_candidate_in_an_uncovered_book_is_blocked_because_books_never_share`,
which produces a perfectly good size and no impact — books never share capacity,
so a `DAY` candidate cannot be evaluated against a `SWING`-only reading. The
invariant is now one-directional: an impact needs a size; a size does not
guarantee an impact.

### F4 · Two tests asserted premises the engine corrected

`test_a_limit_the_trade_itself_moves_over_says_the_trade_did_it` was written
against a total-open-risk limit and could not fail: **the sizer respects a hard
budget, so the after-state lands *on* the limit rather than past it.** That is the
engine working. The test was rewritten around a concentration limit — one the
sizer does not bound against — and the original behaviour was given its own test
(`test_a_hard_open_risk_budget_bounds_the_size_rather_than_breaching_it`).

### F5 · A dead `Absent` branch in `_amount_text`

Coverage found one unreachable line: `ConstraintResult` refuses a present status
beside an absent value, and `_limit_reason` reaches `_amount_text` only after
branching on a present status. The branch was removed rather than covered — an
`except` clause no input can reach reads as a case that was handled rather than
one that cannot occur.

### F6 · An unused property on `Opportunities`

`actionable` was added and never used. Removed rather than tested: unexercised
code is worse than absent code.

### F7 · Two duplicated paragraphs on the live page

Found by the **live run**, not by any test, because both lines fitted:
the cap sentence repeated the fraction basis verbatim, and the staleness warning
appended a consequence the flag's own reason already carried. Both reworded; the
cap now says *what reduced the size* and the basis says *where the fraction came
from*.

### F8 · Two mutation probes were no-ops, and one exposed a real test gap

`P06` and `P39` were first written as `X if False else Y` ternaries, which mutate
nothing. Repaired. The repaired **P06** — reporting the *allowance* as
`money_at_risk` instead of the risk of the size that was produced — then survived,
because with a risk distance of 1 600 the two are exactly equal. It is only
observable when the division does not terminate:
`test_the_risk_is_recomputed_even_when_the_division_does_not_terminate` uses a
distance of 3, where the size's own risk is `999.9999…` and the allowance says
`1 000`. That test closed the survivor.

### F9 · Exact quotients carry long expansions onto the page (**not fixed, recorded**)

The live run printed `open risk after 1325.00000000000000000000000002 USDT`. The
arithmetic is correct — an exact division that does not terminate carries a
28-significant-digit tail, and every figure derived from it inherits one. Rounding
it would be a rounding policy, and this package sets none: a venue's step size is
reference data this domain does not hold. Recorded in limitation `AP-3` on every
page rather than silently truncated.

---

## 5. Verification

### 5.1 Tests

| Measure | Value |
|---|---|
| Suite | 6,964 → **7,359** (+395) |
| Under `-W error` | identical, 0 warnings |
| New test files | 11 (9 package, 1 CLI, 1 workspace integration) + 1 helper module |
| New test lines | 4,590 |

Per file: models 78 · approval 58 · architecture 55 · inputs 44 · sizing 31 ·
policy 28 · today-approval 27 · render 22 · compose 21 · CLI 16 · reading 15.

### 5.2 Coverage

**100 % statement and 100 % branch** across all thirteen new and modified modules
— 1,933 statements, 662 branches, measured with `coverage` run through
`uv run --with coverage` and never installed into `.venv` or added to
`pyproject.toml`.

```
src/fmis/position_sizing/*.py    952 stmts   328 br   100% / 100%
src/fmis/today/builder.py        120 stmts    28 br   100% / 100%
src/fmis/today/models.py         399 stmts   142 br   100% / 100%
src/fmis/today/render.py         295 stmts   114 br   100% / 100%
src/fmis/today/sections.py       167 stmts    50 br   100% / 100%
```

`src/fmis/pipeline/cli.py` carries **exactly the 29 statements and 2 partial
branches it carried before this milestone** — measured on a clean pre-BN tree and
again after — so `fmits approve` added no uncovered CLI code. The residual gaps
are the pre-existing `backtest` paths and one defensive `trade` branch.

### 5.3 Mutation

**44 probes, 44 detected, 0 survivors, 0 invalid.** Byte-identical source
restoration verified by SHA-256 after every probe, **and every `__pycache__`
under `src/` cleared before every run** — report 0020 §6 records why that second
half is not optional.

Coverage of the probes: the sign rule (1) · fraction resolution (4) · sizing
arithmetic (6) · status derivation (2) · limit classification (5) · trade-scope
checks (10) · coverage gaps (3) · store readers (2) · model invariants (4) · text
boundary (3) · workspace integration (4).

### 5.4 Architecture, boundary and venue guards

288 guard tests pass. Specifically:

* **Venue independence** — the computing tier reaches
  `accounts · money · persistence · plan · portfolio_risk · positions ·
  provenance · records · risk · snapshotting` and nothing else; no provider
  import anywhere in the package; exactly one module (`inputs`) may name an
  exchange, and that is pinned.
* **Import guards** — a cold `import fmis.pipeline` in a subprocess loads neither
  `fmis.position_sizing` nor `fmis.persistence`. No engine, domain package or
  store module imports this package; exactly two modules import it from above
  (`pipeline/cli.py` and `today/builder.py`), asserted as a set.
* **The CLI opens no store and constructs no domain value** — asserted by name.
* 0 export collisions (896 total) · 0 import cycles repository-wide · 0 new
  runtime dependencies · `pyproject.toml` and `uv.lock` unchanged.

### 5.5 Live verification against real Binance data — 2026-08-15

A scratch store built entirely through the product's own commands
(`fmits trade record BTCUSDT`, then a risk budget and a portfolio snapshot):

* **`fmits approve ETHUSDT --direction long --entry 3400 --stop 3200 --target 3900`**
  → `APPROVED`, 4.625 ETH, 925 USDT at risk, planned R multiple 2.5, open risk
  400 → 1,325 USDT, priced from a real closed 1h candle 1 h 57 m old. Exit 0.
* **`--risk-fraction 0.10`** → reduced to **0.02** by the owner's own ceiling,
  9.25 ETH, with the reduction named. Exit 0.
* **A transposed stop** (`--stop 3600` on a long) → `BLOCKED`, `[TR-STOP]`, the
  geometry printed, **exit 0** — the evaluation succeeded and its answer was no.
* **`fmits today`** over the full 20-symbol watchlist → 2 confirmed, 2 candidates,
  16 wait, 0 error; every actionable row carried an approval status, a size, the
  resulting open risk and its warnings — `LINKUSDT LONG` and `DOTUSDT SHORT` both
  `APPROVED` with real sizes. Exit 0.

---

## 6. What it still does not do

1. **Nothing is stored.** An approval is recomputed, never recorded, so *"what
   did the engine say when I took this"* is unanswerable. `AP` §15.5 classes a
   frozen check as a captured artifact belonging to a proposal; nothing here
   creates a proposal, so freezing one would persist a record with no owner.
2. **Correlation is never measured.** `TR-DUP` reports *duplication* — the same
   instrument or the same base asset held elsewhere — which is a fact. Whether
   two markets move together is an inference this system has no data for.
   `S-1`'s *"≥3 same-direction majors"* is not implemented.
3. **Liquidity is absent entirely**, so no size is bounded by what the book could
   absorb.
4. **No `PERIOD_LOSS` and no `DRAWDOWN` limit can be measured** — both need a
   closed-trip series and an equity series respectively, and neither exists. Both
   are reported as indeterminate with the blocker named, never as within.
5. **Candidates are evaluated independently.** Two that each fit the budget alone
   do not both fit it together, and neither the page nor the engine claims they
   do. Sequencing them would be a rebalancing engine, which `AP` §15.4 places out
   of scope.
6. **The quantity is exact and unrounded** — see F9.
7. **One book and one account per run.** `fmits approve` and `fmits today` scope
   every candidate to one of each.
8. **No override log.** `SWING_TRADING_MVP_BLUEPRINT_V1` §7.1 makes *constraint
   override rate* the datum that makes a soft block meaningful; recording an
   override needs a write path this milestone deliberately does not have.
9. **`fmits today` prices only markets the store already holds**, so a candidate's
   own market is valued at the owner's stated entry rather than at a mark.
10. **No ADR and no design document was written.** The milestone creates no new
    contract: `AP` §15.4–15.6 specifies the boundary, `SWING_TRADING_MVP_BLUEPRINT_V1`
    §7 and §9.4 specify the refusals and the sizer's inputs and outputs by name,
    and `BH`/`BI`/`BK`/`BL`/`BM` built every type this assembles.

---

## 7. Files

**New** — `src/fmis/position_sizing/` (`__init__`, `models`, `policy`, `sizing`,
`approval`, `reading`, `inputs`, `compose`, `render`), 3,737 lines.

**New tests** — `tests/position_sizing_helpers.py`,
`tests/test_position_sizing_{models,policy,sizing,approval,inputs,reading,compose,render,architecture}.py`,
`tests/test_pipeline_cli_approve.py`, `tests/test_today_approval.py`.

**Modified, all additively** — `src/fmis/pipeline/cli.py` (the twelfth command,
plus seven flags on `today`), `src/fmis/today/{__init__,builder,models,render,sections}.py`.

**Modified tests** — six registry/boundary expectations widened by one name each,
plus `test_today_models.py`'s pinned schema version.
