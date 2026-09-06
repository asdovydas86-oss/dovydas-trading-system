# ADR-0030: Risk policy declaration boundary — where the specification's 2 % lives, and the only producer of a `RiskBudget`

**Status:** Accepted
**Date:** 2026-09-06
**Milestone:** Slice 4 — Risk & Trade-Planning Foundation

## Context

The Slice 4 audit of `03dd4e0` found a large, correct and completely unreachable risk capability.

`fmis.risk` (761 lines) holds `RiskLimit`, `RiskBudget`, `LimitEvaluation` and `evaluate_budget`.
`fmis.portfolio_risk` (3,767 lines) holds the risk distance, the capital at risk, the exposure fold,
the before/after impact and every limit comparison. `fmis.position_sizing` (3,737 lines) holds
`PositionSizer`, `SizingPolicy`, `ApprovalEngine` and `approve_results`. All of it is tested, all of
it is architecturally guarded, and all of it satisfies the capital-preservation rules the
specification states.

**And `RiskBudget(` and `RiskLimit(` appeared nowhere in `src/`.** They were constructed only in
four test files. There was no CLI command, no configuration path and no product surface by which one
could come into existence — so `per_trade_ceiling` was never consulted with a real budget,
`SizingPolicy.fraction_for` never resolved a fraction, `ApprovalEngine` never ran against real
limits, and the owner's dashboard showed no risk figure and no explanation of why. The chain had no
first link.

There is a second, related gap. `SPEC` §8.1 states:

> A maximum of 2% portfolio risk per trade is a hard ceiling, not a default target.

That number lived in **no code at all**. It could not: `fmis.risk` and the computing modules of
`fmis.position_sizing` are guarded by AST tests to hold no numeric literal beyond `0` and `1`,
deliberately, so that *"every value a size is decided by is the owner's."* Those guards are correct
and this ADR does not weaken them. But a ceiling that exists only in a specification document is a
ceiling nothing enforces.

## Decision

**A new package, `fmis.risk_policy`, is the owner's declaration boundary: the one place the
specification's ceiling is written, and the only producer of a `RiskBudget` in the repository.**

### 1. The ceiling lives here, once

`SPECIFICATION_PER_TRADE_CEILING = Decimal("0.02")`, cited to `SPEC` §8.1, written as decimal text
exactly once and asserted by a test to appear in exactly one module. It is the only numeric literal
in the package beyond `0` and `1`.

It belongs here and not in `fmis.risk` because the guard on that package expresses a real rule — an
*engine* must invent no threshold — and the ceiling is not an invented threshold. It is the owner's
own specification. But it is still a number, and a number belongs at the boundary where the owner's
words become a domain object, not inside the engines that evaluate them.

### 2. The ceiling is structural, not validated

A `RiskPolicyDeclaration` whose `per_trade_fraction` exceeds the ceiling **cannot be constructed**.
The refusal is in `__post_init__`, so there is no object for a surface to render, no branch for a
caller to forget, and no second entry point that could skip the check. UI-level validation was
rejected outright.

`<= 2 %` is permitted and `> 2 %` is not, because the specification says *maximum* and no accepted
decision says otherwise. Both boundary values are tested exactly: `1.9999999999 %` is accepted,
`2.0000000001 %` is refused, and neither answer comes from float rounding (see ADR-0029 §6).

**Leverage does not move this ceiling.** A trade whose defined loss at invalidation exceeds the
ceiling is outside it; adding leverage magnifies the loss and does not make it acceptable. No
leverage is modelled in this slice at all, and the scope is stated on the page.

### 3. The ceiling is never a default

`budget_from(declaration)` produces a `RiskBudget` carrying one `PER_TRADE_RISK` /
`PERCENT_OF_EQUITY` limit at the ceiling, with **`default_below_ceiling` left `Absent`**. The
specification states a maximum and states no default; supplying one would invent the owner's risk
appetite at exactly the point the specification declines to.

The owner's own declared fraction travels separately, on `SizingPolicy.risk_fraction` — source 1 of
`fraction_for`, *"the owner's own choice"*, which is what it is. A declaration stating no fraction
therefore resolves to **no fraction at all**: `fraction_for` finds nothing at source 1, nothing at
source 2, and returns `Absent`, which produces a `NOT_EVALUABLE` plan naming the missing input.

A system that sized at the ceiling by default would have converted the specification's ceiling into
the specification's target with nobody deciding to. That is the single failure this arrangement
exists to prevent, and it is asserted by test.

### 4. Declared capital is asserted, and is not portfolio equity

`RiskPolicyDeclaration.equity` is a figure the owner typed, dated by `declared_at`, with
`origin == ValueOrigin.ASSERTED`. It is deliberately **not** `PortfolioState.equity`, which is folded
from recorded fills and marks and is `MEASURED`. They are different facts about the same word, they
can disagree, and the page states which one it is showing.

Declared capital exists because the alternative was worse. Sizing from `PortfolioState.equity`
requires the owner to have recorded fills, which requires them to have a book, which they do not yet
have — and inventing one would be fabricating their holdings. A planning figure computed against
capital the owner states is honest, useful the day they write it, and needs no exchange connection.

### 5. Declared, not stored

The declaration is read from `~/.fmits/risk_policy.json` — beside the durable store, outside the
repository, outside Git. It is **not** persisted as a config event in this slice.

The reason is idempotence. The dashboard re-reads on every refresh and a `GET` must change nothing;
a declaration persisted on read would make *"the owner looked at the page"* an append to the store.
`fmis.risk.RiskRepository` remains the right home for a versioned budget lineage the day the owner
records one deliberately — that is a write path, and this slice adds none.

The file's keys are validated against a **closed set**, so a file carrying an API key, a secret or an
exchange credential is refused by name rather than ignored: a loader that skipped unknown keys would
make a credential in this file invisible rather than impossible. The declaration holds financial
parameters only. Nothing in the package reads an environment variable, opens a keyring or reaches a
network.

### 6. Risk observes the decision and never participates in it

`TradePlan` is computed **from** a `SetupAssessment` and attached to the symbol's decision record at
the projection seam. Nothing flows the other way. `fmis.risk_policy` imports neither
`fmis.swing_setup` nor `fmis.setup_evidence` nor `fmis.decision_support` — it duck-types over the
assessment's `symbol`, `direction`, `reference_price`, `stop` and `targets`, which is what makes the
independence checkable rather than asserted.

A guard test scans every module for confidence vocabulary — `confidence`, `probability`, `score`,
`strength`, `evidence`, `supporting`, `conflicting`, `independence`, `readiness`, `confirmed`,
`candidate`, `win_rate`, `expectancy` — and fails if any appears as an identifier. A size that moved
with evidence count would be indistinguishable from one that did not in every feature test that
fixes the evidence; the vocabulary guard is what makes it impossible instead of merely untested.

A companion test compares every field of every decision record with and without a declared policy,
excluding only the plan, and asserts the workspace's opportunities, wait list, no-trade groups,
summary and ordering are identical. **`WAIT` remains `WAIT`; `CANDIDATE` remains `CANDIDATE`.**

### 7. No geometry is invented

The entry is the engine's `reference_price` — the execution-timeframe close its stop and targets were
measured against — and the page carries the engine's own caveat that it is *not an order price*. The
invalidation is the engine's own structural stop level. A candidate with no stop, or no reference
price, is `NOT_EVALUABLE` with the reason named; **no stop is derived from ATR, from a multiple, or
from anything else**, and no target is assumed, so a candidate with no target has no reward:risk
rather than a fabricated `2R`.

### 8. Portfolio impact is not evaluated, and says so

Sizing runs with `remaining_open_risk=None`, which `PositionSizer` documents as *"the caller is
sizing in isolation and states no portfolio"* — distinct from `Absent`, which means a portfolio was
read and its headroom could not be measured. `TradePlan.portfolio_impact` is always an `Absent` whose
reason states that total open risk, concentration and correlation are **not evaluated, which is not
the same as their being zero**, and that a plan inside the per-trade ceiling is not thereby one the
book has room for. The type refuses to hold anything else.

### 9. The contract is versioned

`RISK_POLICY_CONTRACT_VERSION` is on the declaration and on every plan, and a file declaring another
version is refused rather than guessed at. Risk limits will evolve, and a future archived decision
must be able to answer *"which policy evaluated this?"*.

## Consequences

- The owner can, for the first time, see what a trade on a scanned symbol would risk — against
  capital they declare, with no exchange connection, no recorded holdings and no fabricated figure.
- Every symbol on the watchlist now carries a planning record, including every `WAIT`, and a `WAIT`
  carries **no figures at all** rather than a zero.
- Until the owner writes `~/.fmits/risk_policy.json`, every planning section states that no policy is
  declared and prints the file to write. That is the correct product result, not a defect.
- `fmis.swing_workspace` gains one permitted import, recorded in its architecture guard with the
  justification.
- Scope is explicit and narrow: linear spot-like instruments, one trade in isolation, before costs,
  planned risk rather than worst-case risk. Inverse contracts, dated futures with a multiplier,
  options, leverage, FX conversion, lot-size rounding, fees, slippage, portfolio impact, correlation
  and event risk are all out, and each is stated on the page rather than left to be discovered.

## Alternatives rejected

**Put the ceiling in `fmis.risk` and widen its no-literal guard.** Rejected: the guard expresses the
rule that an engine invents no threshold, and weakening it to admit one number would leave nothing
stopping the next.

**Express the owner's fraction as `RiskLimit.default_below_ceiling`.** Attractive — the field exists
for exactly this shape — and rejected on two counts. `RiskLimit` requires a default to sit *strictly*
below the ceiling, so an owner declaring exactly 2 % could not be represented; and a "default" is a
property of the limit, whereas the fraction is the owner's choice for their trading, which
`fraction_for` already models as source 1.

**Derive equity from a connected exchange account.** Out of scope by instruction and by judgement:
it needs API credentials, and no part of this system should hold them to compute a planning figure
the owner can type.

**Persist the declaration as a config event on read.** Rejected: it would make rendering a page a
write, and idempotence of `GET` is the property the read-only dashboard rests on.

**Show a hypothetical size for `WAIT` symbols.** Rejected: a waiting symbol with an entry, a stop and
a quantity beside it reads as almost a trade, and it is not almost anything.
