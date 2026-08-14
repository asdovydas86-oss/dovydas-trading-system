# 0019 — Portfolio Intelligence & Risk Engine (Milestone BL) — hostile review

| Field | Value |
|---|---|
| **Report number** | 0019 |
| **Title** | Portfolio Intelligence & Risk Engine (Milestone BL) — hostile review |
| **Date** | 2026-08-14 |
| **Report type** | Hostile review |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | Working tree on top of `dbc4765`; the implementation is [report 0018](0018_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_IMPLEMENTATION.md) |
| **Status** | Final. **3 findings, all fixed.** 1 further defect found by the suite during development, also fixed |

---

## 0. Method

Eleven attacks, each stated as a claim the implementation should be **unable to
satisfy**, then pressed against the running code rather than against the source
by inspection. Where an attack succeeded, the finding was fixed in this milestone
and a regression test added; where it failed, the evidence that defeated it is
named so a future reader can re-run it.

A hostile review that reports nothing is a review that was not hostile. This one
found three real defects, and the most expensive of them — H1 — was one the brief
named in advance and the implementation had nonetheless got wrong.

---

## 1. Findings

| # | Severity | Attack | Status |
|---|---|---|---|
| **H1** | **P1** | Correlated exposure is presented as diversification | **Fixed** |
| **H2** | **P2** | A stale valuation silently reinterprets every percent-of-equity limit | **Fixed** |
| **H3** | **P2** | Two surfaces report different capital at risk for one trade | **Fixed (pinned)** |
| **H4** | **P1** | One mis-stated limit takes down the whole constraint check | **Fixed** |

H4 was surfaced by a test written against the constraint engine during
development rather than by this pass, and is recorded here because it belongs to
the same class as the rest: a failure in which the *safety mechanism* is what
breaks.

---

## 2. H1 — correlated exposure presented as diversification · **P1** · fixed

### The attack

> Hold BTC against two different quote currencies. The portfolio will report two
> unrelated symbols and no duplicate, so the owner adding a third BTC position
> sees a diversified book.

### It succeeded

```
state(BTC/USDT long 0.5, BTC/USDC long 0.5)

  symbol axis    ('BTCUSDC', 'BTCUSDT')     two buckets
  detect_overlap(candidate = BTC/USDT long)
    same_instrument_elsewhere: 0            no duplicate reported
```

Both the `SYMBOL` and `INSTRUMENT` axes key on the traded pair, and duplicate
detection keyed on `pair_symbol`. `BTCUSDT` and `BTCUSDC` share neither. The
portfolio was 100 % long BTC and reported two independent 50 % concentrations
with no duplicate — which is the single most expensive thing a portfolio page can
do, and the exact attack the brief names.

### The fix

Two changes, because the attack has two halves:

1. **`ExposureDimension.ASSET`** — a breakdown keyed on the **base asset alone**,
   added to `build_state`'s axis set and to the concentration engine's addressable
   keys, so a limit may be written `asset:BTC`.
2. **`PositionOverlap.same_asset_elsewhere`** and note **`PR-N10`** — duplicate
   detection now reports the same base asset held under a *different* pair,
   separately from the same pair held elsewhere, because they are two sentences:
   the instrument is genuinely different and the bet is the same one.

`is_duplicate` now counts base-asset exposure. Answering *"no duplicate"* to a
candidate BTC long while a BTC long is open was the flattering answer, not the
true one.

### The honest limit of the fix

The `ASSET` axis differs from `SYMBOL` **exactly when the quote currencies
differ**, and in that case the money figures are `Absent` for want of a rate. So
today the axis earns its place by *identity* — grouping and duplicate detection —
and not by arithmetic. A concentration limit on `asset:BTC` over a mixed-quote
portfolio reports `INDETERMINATE` naming the missing rate, which is correct and is
**not** the same as reporting a smaller number. Both behaviours are pinned:

- `test_the_same_base_asset_under_two_quotes_is_one_asset_and_two_symbols`
- `test_a_cross_quote_holding_is_grouped_but_not_valued_without_a_rate`
- `test_the_same_asset_under_a_different_quote_is_reported_as_duplicate`
- `test_a_cross_quote_duplicate_produces_its_own_note`

---

## 3. H2 — a stale valuation reinterprets every percent-of-equity limit · **P2** · fixed

### The attack

> Take a portfolio snapshot, wait six weeks, then read the portfolio. Equity comes
> from the snapshot, every percent-of-equity limit is measured against it, and
> nothing on the resulting state says when that equity was true.

### It succeeded

`PortfolioState` carried `as_of` and `equity`, and no field related the two.
`read_equity_and_cash` returned the figures and discarded `snapshot.as_of`. A
2 % per-trade ceiling measured against a six-week-old equity is a different
ceiling, and the reading looked identical to a current one.

This is precisely the hazard `MarkQuote.as_of` exists to prevent one layer down —
*"a mark read at 22:00 and frozen into a 22:15 snapshot is fifteen minutes stale,
and a reader is entitled to see that rather than infer it"* — and the portfolio
layer had not applied its own domain's rule to itself.

### The fix

`PortfolioState.equity_as_of: datetime | Absent`, with a read-time
`equity_staleness` projection. `read_equity_and_cash` now returns three values
rather than two, and `read_portfolio` threads the snapshot's instant onto the
state. A valuation dated after the reading is refused outright — *a valuation from
the future is not a valuation*.

A caller who supplies equity directly gets
`Absent("the caller supplied equity and cash directly and stated no instant for
them")` rather than the reading's own instant borrowed on their behalf.

Pinned by `test_the_equity_figure_carries_the_instant_it_was_true`,
`test_no_snapshot_means_no_valuation_instant`,
`test_supplying_equity_directly_states_no_instant_for_it` and
`test_a_valuation_dated_after_the_reading_is_refused`.

**Not fixed, and deliberately:** no staleness *threshold* is applied. How old is
too old is the owner's policy, and this package invents no threshold. The figure
is reported; the judgement is not made.

---

## 4. H3 — two surfaces, two capital-at-risk figures · **P2** · fixed by pinning

### The attack

> Record a trade, exit part of it, then read `fmits trade show` and the portfolio.
> They will disagree about capital at risk and neither will say so.

### It succeeded, and both figures are correct

```
long 0.5 BTC, stop 1600 away, then exit 0.2

  fmits trade show   capital at risk   800 USDT   (max exposure 0.5)
  portfolio state    open risk         480 USDT   (net exposure 0.3)
```

BK measures the position's **maximum** exposure, because *"what did this
commitment put at risk"* is a question about the decision. BL measures what is
**still open**, because *"what is at risk now"* is a question about the portfolio.
Neither is wrong; a reader comparing the two pages without knowing which is which
would conclude one of them is.

### The fix

No arithmetic changed — changing either would make one of the two questions
unanswerable. The relationship is now a **pinned property**:
`test_this_engine_measures_open_exposure_and_bk_measures_maximum_exposure` asserts
both figures, asserts BK still raises its own `TC-W5` warning about the gap, and
will fail if a future change makes the two surfaces silently agree on the wrong
number. Report 0018 §13 states the divergence in prose.

---

## 5. H4 — one mis-stated limit takes down the whole check · **P1** · fixed

### The attack

> State one limit in a currency the portfolio is not denominated in. The
> constraint engine will refuse to produce *any* result.

### It succeeded

`_status_of` correctly returned `Absent(reason)` for an uncomparable limit, but
the measured `Money` value was still passed to `ConstraintResult` — whose
`__post_init__` refuses a value paired with an absent status, precisely to stop an
indeterminate result becoming a silent `WITHIN`. The two safety mechanisms
collided: `evaluate_constraints` raised `DomainValidationError` and the owner got
**no risk evaluation at all** because one limit was mis-typed.

A mis-stated limit costing the owner every *other* limit's evaluation is exactly
backwards.

### The fix

`_status_of` became `_compare`, returning the value and the status **together**
and demoting both when the comparison is impossible. One bad limit now costs that
limit and nothing else. Pinned by
`test_an_uncomparable_limit_costs_that_limit_and_no_other` and
`test_an_uncomparable_measurement_is_not_carried_beside_an_absent_status`.

---

## 6. Attacks that failed

Each is recorded with the evidence that defeated it, so the claim is checkable
rather than asserted.

### "Risk is understated"

Refuted on five paths. A position with no recorded stop yields `Absent`, not zero
(`test_a_position_with_no_stop_makes_open_risk_absent_rather_than_smaller`;
mutation M26 killed). Broken geometry yields `Absent`, not a magnitude (M25
killed). A foreign quote yields `Absent`, not a conversion. One unmeasurable
position makes the **total** absent rather than shrinking it (M24 killed). Every
figure publishes `RISK_BASIS`, which names fees, slippage, funding, liquidation
and gap risk as excluded.

### "Short math is asymmetric"

Refuted. `stop_distance` writes the two branches once; mutations M01 and M02
mutate each branch independently and both are killed, which requires the suite to
carry a short assertion with its own arithmetic answer. A short read from the
real store is exercised end to end
(`test_a_short_read_from_the_store_computes_its_own_risk_and_sign`) — a gap that
mutation N07 exposed and that this pass closed.

### "The same symbol across venues double-counts incorrectly"

Refuted, in both directions. Two venues produce two `INSTRUMENT` buckets and one
`SYMBOL` bucket; gross counts both because they *are* two positions with two
counterparties; a long at one venue and a short at another does **not** net to
flat (`test_a_long_at_one_venue_and_a_short_at_another_do_not_net_to_flat`).

### "Cash is fabricated"

Refuted. Cash comes from a `PortfolioSnapshot` or from the caller and from nowhere
else; with no snapshot both equity and cash are `Absent("...A balance this system
has not observed is not a zero balance")`. A cash balance whose currency the
snapshot froze no rate for makes the total `Absent` rather than dropping that
balance (mutation N12 killed).

### "Missing inputs become zero"

Refuted as a rule rather than case by case: `sum_or_absent` is the single place
totals are formed, and it refuses any total with an absent contributor while
naming every one. Twelve of the sixty-four mutation probes attack this directly
and all twelve are killed.

### "The risk limit is treated as a target rather than a ceiling"

Refuted. `default_below_ceiling` is never promoted to the comparison value
(`test_the_ceiling_is_never_treated_as_a_target`), and `AT_LIMIT` is a **binding**
constraint. That second property was *not* asserted before this pass — mutation
N18 removed `AT_LIMIT` from the binding set and survived. Three tests now pin it.

### "One trade can bypass total-open-risk checks"

Refuted. Every limit in the budget appears in every result; dropping unmeasurable
limits is mutation N19 and is killed. Two positions each comfortably inside the
per-trade ceiling still register the total-open-risk breach
(`test_one_trade_cannot_bypass_the_total_open_risk_check`).

### "Projection state is persisted as truth"

Refuted structurally. No exported type appears in the store's `SPECS` table, no
projection has a `from_payload`, and `reading.py` names no write verb — all three
asserted as source-level guards rather than as conventions.

### "Venue-specific assumptions leaked into the domain"

Refuted by five guards, one of which **found a real hit**: a `venue:binance`
example baked into a constraint-engine help string. The string was replaced with
the axis list rather than the guard being relaxed. The guard strips docstrings and
comments before grepping, so documenting the guarantee stays permitted and
branching on a venue does not.

### "Position sizing was added without a proper equity contract"

Refuted, and the gap is recorded rather than closed.
`maximum_quantity_for_risk` takes an `allowed_risk` **as an argument**; it reads
no equity, resolves no limit and consults no portfolio, and
`test_the_sizing_primitive_reads_no_equity_and_no_portfolio` pins its entire
signature. What it deliberately does not do — decide what `allowed_risk` should be
— is the decision gap recorded in report 0018 §12: it needs a mark source and an
owner decision about which equity figure sizing reads. Neither was smuggled in.

---

## 7. What this review did not do

- It ran no statistical correlation analysis, because none is built.
- It did not attack the persistence layer's own guarantees, which are BI's and
  were reviewed there.
- It did not attempt a performance attack. At this owner's volumes the fold is
  milliseconds, and the cost curve is `fmis.persistence`'s to change.
- It assumes `fmis.risk`, `fmis.positions`, `fmis.plan` and `fmis.money` are
  correct. BL changed none of them, and mutation probe N02's equivalence rests on
  a `Position` invariant this review took on trust and did not re-derive.

---

## 8. Conclusion

Four defects, all fixed and all regression-tested. **H1 is the finding that
mattered**: the implementation satisfied every axis the brief listed by name and
still presented one bet on BTC as two independent positions, because the brief's
word *"symbol"* and the domain's word *"symbol"* are not the same thing. The
lesson is recorded rather than generalized — an axis list is only as good as the
question each axis is actually asked.

No finding required a change to any domain package outside
`fmis.portfolio_risk`, and no arithmetic was weakened to make a test pass.
