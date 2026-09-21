# AP-D1 / AP-D2 — Architecture Investigation

**Milestone:** AQ (ADR Phase 1)
**Status:** **Investigation. Nothing here is decided, and nothing here is an ADR.** Every option below
is presented to be chosen between by the owner. Part 4 states a recommendation and labels it as one.
**Date:** 2026-08-06
**Subjects:**
[AP-D1](TRADING_DOMAIN_ARCHITECTURE_V1.md#311-new-decisions-requiring-an-adr-before-implementation) —
money, quantity and currency types ·
[AP-D2](TRADING_DOMAIN_ARCHITECTURE_V1.md#311-new-decisions-requiring-an-adr-before-implementation) —
capture contract and migration guarantee
**Reads:** [`TRADING_DOMAIN_ARCHITECTURE_V1.md`](TRADING_DOMAIN_ARCHITECTURE_V1.md) v1.2 ·
[ADR-0027](../adr/ADR-0027-memory-and-decision-archive-persistence-schema.md) ·
[ADR-0013](../adr/ADR-0013-swing-relationship-foundation.md) §4 ·
[ADR-0005](../adr/ADR-0005-ingestion-boundary-strictness.md) ·
[ADR-0019](../adr/ADR-0019-level-crossing-foundation-v1.md) ·
[ADR-0026](../adr/ADR-0026-decision-context-boundary.md) ·
[`FMITS_PRODUCT_BACKLOG.md`](../../FMITS_PRODUCT_BACKLOG.md) §6, §10 ·
[`reports/0003`](../../reports/0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md) §3, §12 ·
[`reports/0004`](../../reports/0004_2026-08-01_FMITS_BUSINESS_AND_CAPABILITY_ARCHITECTURE_V1.md)
§4.13–§4.19 · the repository at `75a4f40`

---

## Table of contents

- [0. What this document is](#0-what-this-document-is)
- [PART 1 — AP-D1: money, decimal and quantity](#part-1--ap-d1-money-decimal-and-quantity)
  - [1.1 What is actually undecided](#11-what-is-actually-undecided)
  - [1.2 What the repository says today, measured](#12-what-the-repository-says-today-measured)
  - [1.3 The consequence surface](#13-the-consequence-surface)
  - [1.4 The eight sub-decisions AP-D1 must bind](#14-the-eight-sub-decisions-ap-d1-must-bind)
  - [1.5 The alternatives, described](#15-the-alternatives-described)
- [PART 2 — AP-D2: migration for irreplaceable records](#part-2--ap-d2-migration-for-irreplaceable-records)
  - [2.1 What is actually undecided](#21-what-is-actually-undecided)
  - [2.2 What the archive does today, measured](#22-what-the-archive-does-today-measured)
  - [2.3 The consequence surface](#23-the-consequence-surface)
  - [2.4 The eleven sub-decisions AP-D2 must bind](#24-the-eleven-sub-decisions-ap-d2-must-bind)
  - [2.5 The alternatives, described](#25-the-alternatives-described)
- [PART 3 — Decision matrices](#part-3--decision-matrices)
- [PART 4 — Recommendation (not a decision)](#part-4--recommendation-not-a-decision)
- [PART 5 — Risk register discovered by this investigation](#part-5--risk-register-discovered-by-this-investigation)
- [Appendix A — Measurements and how to reproduce them](#appendix-a--measurements-and-how-to-reproduce-them)
- [Appendix B — Questions this investigation could not answer](#appendix-b--questions-this-investigation-could-not-answer)

---

## 0. What this document is

An architecture investigation, produced before the two ADRs the backlog sequences as the next item
(`FMITS_PRODUCT_BACKLOG.md` §6 item 1). Its purpose is to establish **what is genuinely undecided**,
because both decisions arrive with a stated recommendation attached, and a recommendation that is
never tested against alternatives becomes an accepted decision by default rather than by argument.

**In scope.** The consequence surface of each decision, the sub-decisions each one actually contains,
the alternatives with their trade-offs, and a stated recommendation.

**Out of scope, deliberately.** No Python. No ADRs. No backlog or changelog edits. No implementation,
no TODO, no milestone change, no commit. Where this document uses a code-shaped fragment it is
describing the *shape of a contract*, never proposing a file.

**The one thing this document adds that the design did not have.** `AP` §31.1 states each decision as
a single line with a recommendation. Both lines turn out to contain **multiple independent
sub-decisions** — eight for AP-D1, eleven for AP-D2 — several of which the design does not mention and
at least four of which are load-bearing enough to change the shape of the first vertical slice. Naming
them is most of this document's value; the option comparison is the rest.

**Measurements.** Every numeric claim in Part 1 was measured on this machine against this repository
at commit `75a4f40`, in a throwaway interpreter session that created no files. Appendix A states each
one and how to reproduce it. Estimates are labelled as estimates.

---

# PART 1 — AP-D1: money, decimal and quantity

## 1.1 What is actually undecided

`AP` §5.3 and §31.1 decide the headline: *"every monetary amount is an exact decimal paired with its
asset; quantities are exact decimals; no arithmetic between two amounts in different assets without an
explicit conversion carrying a dated rate and its provenance; the market half keeps `float`."*

That is a good decision and this investigation does not argue with it. But it is **not sufficient to
write code against**, and it is not what will hurt in five years. Four things it does not say:

1. **What "exact" means for a quotient.** Average entry, R-multiple, FX conversion, portfolio weight
   and headroom are all divisions. Decimal division is *not* exact — it is rounded to a context
   precision. §5.3's guarantee is unachievable for any derived price, and the design does not notice.
2. **Where exactly the boundary sits, and who crosses it.** "The market half keeps `float`" is a
   statement about packages. But a proposal's `stop_loss` (§8.2) originates in `fmis.level_crossing` as
   a `float` and becomes an input to a risk amount, which is money. **Something converts a float price
   into an exact price**, and nothing in the design says what rule that conversion follows.
3. **What an exact decimal looks like on disk.** JSON has no decimal type. The chosen wire form
   determines the content digest, and the content digest determines `event_id` (§11.5), which is the
   ledger's identity. This makes AP-D1 a *prerequisite of* AP-D2 rather than a peer of it.
4. **Whether `float` is the problem the design thinks it is.** §5.3's stated failure — three buys and
   three sells leaving `~1e-17` residue so a position never closes — is real (measured: `5.55e-17`,
   Appendix A.2). But §5.3 *also* requires a per-asset dust threshold, which closes that failure
   independently of the numeric type. Both mechanisms address it; only one of them is needed for it.
   The stronger arguments for exactness are elsewhere (§1.3), and the ADR should rest on those, because
   an argument that a cheaper mechanism already answers will not survive review.

## 1.2 What the repository says today, measured

| # | Fact | Evidence |
|---|---|---|
| 1 | The `float` choice is **already scoped to market data in code**, with money named as the deferred case | `src/fmis/data/models.py:7-12` — *"`Decimal` is deliberately deferred and will be reconsidered later for money, accounting, order sizing, and execution"* |
| 2 | `float` appears **128 times across 36 of 108 source files**, in 13 packages | `grep -rn float src/fmis --include='*.py'` |
| 3 | Three packages **ban the identifier `Decimal` by AST assertion** | `tests/test_level_crossing.py:2024-2034`, `tests/test_structure_break.py:1799-1806`, `tests/test_change_of_character.py:~1714` — each walks the package AST and asserts `Decimal`, `round`, `quantize`, `isclose`, `epsilon`, `atol`, `rtol`, `approx` appear in no `Name`/`Attribute` node |
| 4 | Those bans exist to forbid **tolerance**, not to prefer `float` | `src/fmis/level_crossing/models.py:116`, `crossing.py:21`, `__init__.py:57`, `market_structure/models.py:206` — all four inherit ADR-0013 §4: comparison is exact, and `Decimal` is listed beside `epsilon` and `round` as a *fuzzing* mechanism |
| 5 | Binance delivers **exact decimal strings** and the adapter destroys the exactness at parse time | `src/fmis/providers/binance.py:274-291` — *"a Binance numeric field, which arrives as a plain decimal string"* → `float(value)` |
| 6 | The ingestion boundary **rejects strings for numeric fields** | `src/fmis/ingest/candles.py:116-128` — `int`/`float` only, `bool` rejected, strings rejected (ADR-0005) |
| 7 | The archive's metadata codec accepts **six JSON-safe types, none of them `Decimal`** | `src/fmis/archive/json_safe.py:108-137` — `str`, `bool`, `int`, finite `float`, `None`, `tuple`, `Mapping` |
| 8 | `json.dumps` raises on a `Decimal` | Measured (Appendix A.1) — `TypeError: Object of type Decimal is not JSON serializable` |
| 9 | The project has **zero runtime dependencies** and ADR-0027 §1 keeps it that way | `pyproject.toml`; ADR-0027 §1 |

**Reading of fact 3, which matters more than it looks.** A "Decimal everywhere" option is not a
docstring edit. It requires **deleting or narrowing three architectural guard tests** that encode
ADR-0013 §4, ADR-0019, ADR-0020 and ADR-0021. Those guards are not wrong — an exact `Decimal`
comparison would satisfy their *intent* perfectly well — but they are written against the
**identifier**, and weakening a guard to admit a type is how a guard stops guarding. Any option that
puts `Decimal` below L7 must state what replaces them.

## 1.3 The consequence surface

Every item the brief names, plus the ones the investigation found.

### 1.3.1 Decimal everywhere?

**No, and not for the reason usually given.** Two hard blockers below L7, independent of taste:

- **The indicator layer is not decimal arithmetic.** EMA smoothing is `alpha = 2/(n+1)` — a
  non-terminating quotient. ATR, RSI, MACD and every volatility ratio compound it. Under `Decimal`
  these are rounded at the context precision at every step, so the "exactness" gained is notional: the
  values are exactly reproducible (which `float` already is, deterministically, on one platform) but
  not exactly correct.
- **`fmis.data` is the kernel every layer's signatures speak** (`reports/0003` §3 L0). Changing
  `Candle.close` to `Decimal` is a change to 13 packages and to a type that `reports/0003` names as
  *"the only layer that must never change carelessly."*

**Performance is not a blocker, and the folklore is wrong here.** Measured on this machine, CPython
3.12: one million `Decimal` additions cost **41 ms** against **28 ms** for `float` — a **1.5×** ratio,
not the 50–100× that the received wisdom assumes (CPython ships the C `_decimal` implementation).
At `AP` §28.1's ten-year volumes (~28,000 ledger events, ~20,000 episodes) the fold cost difference is
**single-digit milliseconds**. Performance should not appear in the ADR as an argument in either
direction; it is noise at this scale. (Appendix A.5.)

### 1.3.2 float anywhere?

Unavoidable, and the honest question is *where the conversion happens and who owns it*. Four candidate
boundaries, only the first of which the design considers:

| Boundary | Rule | Problem |
|---|---|---|
| **By package** (§5.3's implied rule) | `fmis.money` and everything importing it is exact; L0–L7 is `float` | Silent on the crossing itself — §8.2's `stop_loss` starts as `float` and ends as an input to a money amount |
| **By durability class** | Anything that is a *source of truth* or a *captured artifact* (§24.3) is exact; anything *rebuildable* or *disposable* may be `float` | Cuts across packages — a Position (rebuildable) holds an average entry that a tax figure will never read but a P&L figure will |
| **By provenance** (§5.2's own vocabulary) | `ASSERTED` values are exact; `MEASURED` values are `float`; `POLICY_DERIVED` follows its policy | Elegant and already-owned vocabulary. But a `MEASURED` position quantity is a fold of `ASSERTED` quantities and must stay exact, so the rule needs an exception on its first use |
| **By role** | *Anything that will ever be summed, compared for equality with zero, or reported to a tax authority* is exact; anything that is only ever compared for order or rendered is `float` | The most defensible rule found. Also the hardest to state as a type constraint, because it is a statement about *use*, not about the value |

**The unowned conversion.** A stop-loss price is the sharpest instance. `fmis.level_crossing` produces
a price level as a `float` derived from a candle. The proposal freezes it. The plan inherits it. Risk
is `(entry − stop) × quantity`, which is money. So a `float` must become an exact decimal, and there
are three ways to do it, with materially different results (measured, Appendix A.6):

| Conversion | `59020.13` becomes | Property |
|---|---|---|
| `Decimal(float)` | `59020.129999999997380655…` | Exact image of the binary value. Faithful, unreadable, and carries 20 digits of noise into every downstream sum and every archived record |
| `Decimal(str(float))` | `59020.13` | The shortest round-tripping representation. Readable, and **not** the value the engine computed — it is a rounding, silently applied |
| `quantize(float, venue_tick_size)` | `59020.13` (tick `0.01`) | The only conversion with a *stated* rule, and the only one that produces a price the venue would accept |

The third is correct and **requires per-market tick-size and step-size reference data**. `AP` §27
explicitly rules that out: *"`Market` and `Account` are identifiers with attributes, not a registry
with lifecycle management."* That is a real, unresolved tension between §27 and §5.3, and AP-D1 has to
break it in one direction: either accept a minimal instrument-precision table as reference data, or
accept `Decimal(str(...))` as a **named, versioned rounding policy** with its own provenance stamp.

### 1.3.3 Quantity precision and quote precision

Two different precisions that a single "exact decimal" type does not distinguish:

- **Quantity step** (`LOT_SIZE`) — BTC 8 decimals on Binance spot, other assets 1 to 18.
- **Price tick** (`PRICE_FILTER`) — quote-side, per market, unrelated to the quantity step.
- **Fee precision** — a third, often finer, and sometimes in a third asset entirely (§11.7).

An "exact decimal" faithfully stores whatever it is handed; it does not *validate* that `0.123456789`
BTC is unrepresentable at the venue. The choice is whether AP-D1 makes precision a **validation**
(reject a quantity finer than the step — ADR-0005's reject-never-repair applied to money) or merely a
**record** (store what the owner typed, correct later by supersession, §5.1). Validation needs the
registry §27 excludes. Recording needs nothing and catches nothing.

Note that the design already leans one way without saying so: §11.3 says the owner types three values
and §5.1 says corrections never edit. A validation that rejects a mistyped quantity at the point of a
one-confirmation happy path is friction on exactly the path R2 identifies as the critical adoption
risk. **The design's own friction budget argues for record-and-correct, not validate.**

### 1.3.4 Fees

The hardest single field in §11.2, for three reasons that stack:

1. `fee_asset` may be base, quote or a **third asset** (BNB, and the design says so in §11.2).
2. §11.4 folds the fee into the balance effects when denominated in base or quote — which means the
   fee participates in the *same* arithmetic as quantity, so it must share quantity's exactness.
3. A fee in a third asset **is itself a disposal** under §22.2 item 5, so it needs its own FX rate and
   its own acquisition value. That is a second money amount in a second asset attached to one Trade.

Consequence for the type: `Money` cannot be a scalar with an implicit currency. It must be
`(amount, asset)` and a Trade carries **at least three** such pairs on the happy path (base, quote,
fee) and possibly a fourth (fee FX to SEK). §5.3 says this; the point here is that it is not an
edge case to be handled later — it is on the first record the system ever writes.

### 1.3.5 P&L

Realized P&L is a fold (§12.3, path-dependent). If every input is exact and every operation is
addition, subtraction and multiplication, the fold is exact. **It stops being exact the moment
`average_entry` enters it**, because average entry is a quotient (§1.3.6).

There is a clean escape, and it is already the repository's own idiom: **do not store the quotient**.
Hold `(total_cost, total_quantity)` as the authoritative pair and derive the average at read time.
This is precisely ADR-0016 §4's rejection of a stored derived count, and §11.4's *"if two fields could
ever disagree about the same fact, one of them is not a field."* It costs nothing, it makes the fold
exact, and it makes the rounded display value a presentation concern that no arithmetic reads.

Whether AP-D1 mandates that shape is a genuine sub-decision (Q5 below), and this investigation
believes it is the single highest-value line the ADR could contain.

### 1.3.6 Percentages, ratios and R-multiples

**Measured (Appendix A.3):** `Decimal(1)/Decimal(3)` returns 28 significant digits under the default
context, and for `cost = 10000.00`, `qty = 3`, `avg = cost/qty`, the identity `avg × qty == cost` is
**False** — it evaluates to `9999.999999999999999999999999`.

So "exact decimals everywhere" is **factually unachievable** for any value in this class:

| Value | Why it is a quotient |
|---|---|
| `average_entry` (§12.3) | cost ÷ quantity |
| `risk_reward` (§8.2) | reward ÷ risk |
| R-multiple (§17.3) | P&L ÷ initial risk |
| `fx_rate_to_tax_currency` (§11.2) | quote ÷ SEK, supplied to a fixed number of digits by its source |
| Portfolio weights, headroom, drawdown, leverage (§14.2) | all ÷ total |
| Expectancy, win rate, profit factor (§20.3) | all ÷ n |

AP-D1 must therefore say **where rounding is legitimate and who owns each rounding rule** — the same
discipline §12.4 already applies to fee allocation (*"exactly one owner per question"*). The candidate
statement, offered as a shape and not a decision:

> Money and quantity are exact. **A ratio is not money**, and no ratio is ever a source of truth: it
> is derived at read time from exact inputs, its rounding is a stated presentation or policy rule, and
> the exact inputs it came from are always recoverable from the record.

This also disposes of a hazard the design does not name: an R-multiple stored as a rounded `Decimal`
on an episode (§17.3) is a *stored quotient*, and two episodes rounded under two different context
precisions would be silently incomparable in a cohort statistic.

### 1.3.7 Indicators

Untouched by any option here, and should be stated as such in the ADR to stop the question being
reopened every milestone. `fmis.features` consumes `Candle` floats and produces `FeatureValue` floats.
The trading domain reads *facts* from the market half — level prices, ATR, regime — and any of those
that becomes a money-adjacent value crosses the boundary of §1.3.2 explicitly.

The one live interaction: **`AP` §8.5's counterfactual path classification consumes
`fmis.level_crossing`**, which compares a `float` candle price against a `float` level with strict
`>`/`<` (ADR-0019: exact equality is a `TOUCH`). If the proposal's stop and target were stored as
exact decimals and the evaluator compares them against `float` candles, **the comparison type is
mixed**, and Python's mixed `Decimal`/`float` comparison is exact-but-surprising (it compares the true
values, so `Decimal("59020.13") > 59020.13` is `True`). That is a correctness trap on the boundary of
the one engine the counterfactual evaluator is designed to reuse, and it belongs in the ADR as a rule:
**convert once, at a named point, and never compare across the boundary.**

### 1.3.8 Performance

Non-binding, measured, stated in §1.3.1. The only place it could matter is a future backtest over
millions of bars — which is market-half arithmetic and stays `float` under every option here.

### 1.3.9 Serialization — where AP-D1 becomes AP-D2's prerequisite

`json.dumps` raises on a `Decimal` (measured, A.1). So an exact decimal reaches disk as one of:

| Wire form | Round-trips exactly? | Consequence |
|---|---|---|
| JSON number (`0.1`) | **No** — becomes a `float` on decode | Defeats the entire decision |
| JSON string (`"0.1"`) | Yes | Requires a canonical textual form (below) |
| Scaled integer (`{"units": 10, "exp": -2}`) | Yes | Two fields per amount; verbose; needs an exponent convention |
| Integer minor units (`10` with an asset-level exponent) | Yes | Requires the per-asset exponent registry §27 excludes |

**And here is the finding that most needs to reach the ADR.** Measured (A.4): `Decimal("0.10") ==
Decimal("0.1")` is **`True`**, but `str()` gives `"0.10"` and `"0.1"` — two different strings. Under
`canonical_dumps` those produce **different bytes and different SHA-256 digests**
(`022462ef4896468a` versus `ce8c420f63a142f0`, measured against the repository's own
`src/fmis/archive/json_safe.py:50`). Since ADR-0027 §4 derives `record_id` from the digest and `AP`
§11.5 derives `event_id` the same way, this means:

> **Two Trades that are equal in every domain sense would receive two different identities, and
> ADR-0027 §6's idempotent-duplicate handling would not recognise them as the same event.**

The owner re-typing a fill as `0.10` after having typed `0.1` would create a **second position-moving
event**, not an idempotent no-op. That is a silent data-corruption path on the first record type the
system writes, and it is created by AP-D1's choice of type interacting with AP-D2's identity scheme.

The obvious fix — `Decimal.normalize()` — is **not** safe as written: measured, `Decimal("100")
.normalize()` returns `"1E+2"`, which is a correct decimal, an unreadable ledger entry, and a
different string again. A canonical form has to be specified deliberately (fixed-point, no exponent,
no leading `+`, minus sign only for negatives, trailing zeros either always stripped or always padded
to a stated scale). **This is a required clause of AP-D1, and neither §5.3 nor §31.1 mentions it.**

### 1.3.10 Archive

Consequences beyond the wire form:

- `encode_metadata` (`json_safe.py:108-137`) admits six types, none of them exact-decimal-shaped. The
  trading domain's codecs are new and hand-written (ADR-0027 §1) so they are not bound by it — but a
  money amount landing in a `metadata` mapping would be silently rejected at encode time. Fine
  behaviour; worth stating so nobody works around it.
- `allow_nan=False` is already correct and becomes *more* correct: an exact type has no NaN, so a
  whole class of on-disk poison is unrepresentable rather than merely rejected.
- ADR-0027's `content_digest` covers `payload`, so the canonical textual form of every amount is
  inside the integrity guarantee. Good — provided the form is fixed once (§1.3.9).

### 1.3.11 API adapters — Binance, TradingView, future venues

| Source | What arrives | What survives today |
|---|---|---|
| **Binance REST klines** | Decimal **strings** (`"59020.13000000"`) | `float(value)` at `binance.py:286` — exactness discarded at L1 |
| **Binance trade/order endpoints** (not yet integrated; `AP` §32 step 4) | Decimal strings for `price`, `qty`, `commission` | n/a — this is the path that will carry **fills**, i.e. money |
| **TradingView MCP** | JSON **numbers** (already IEEE-754 by the time they arrive) | Exactness is already gone upstream; it cannot be recovered |
| **Statement CSV import** (§23.3) | Text, venue-formatted, possibly locale-formatted | Parsing rule is per-venue and is itself a policy |

Two rules suggest themselves, and both are AP-D1 clauses rather than adapter details:

1. **A venue's original textual representation of anything that becomes a money or quantity fact is
   captured verbatim**, alongside the parsed exact value. It costs a string per field and it makes a
   later parsing-rule change *auditable* instead of *retroactive* — the same reasoning §22.2 items 9
   and 10 use for the FX rate.
2. **TradingView is not a source of economic fact.** It is a chart. Anything from it that reaches a
   ledger event should be `ASSERTED` by the owner, never `MEASURED` from the feed — otherwise a
   float-shaped price acquires an exactness it never had.

### 1.3.12 Excel / CSV export (§23)

Excel stores numbers as IEEE-754 doubles and coerces on open. An exported exact quantity of 18
decimals (an ERC-20 amount) **silently loses precision in the spreadsheet**, and the round trip §23.1
already forbids is exactly what makes that harmless — Excel is a projection. The consequence for
AP-D1 is narrow but real:

- Money and quantity columns in every export are **text columns**, explicitly, in the column contract.
- The **full dump** (§23.2) is the one export where lossy is not acceptable, which is a Part 2 concern
  (§2.4 Q9) — and another place the two decisions touch.

### 1.3.13 Tax (§22)

- Reporting in SEK at transaction-time rates (§22.4) means every event carries a rate that is itself a
  quotient with a source-defined precision. Storing the **rate as given by the source**, verbatim, is
  the only defensible option — re-deriving or re-rounding it changes a completed report.
- **Rounding for reporting belongs to the jurisdiction rule set, never to the money kernel.** This is
  §12.4's one-owner-per-question rule applied again, and it is the clause that keeps a 2029 change to
  Swedish rounding from touching `fmis.money`.
- Average-cost basis across all holdings of an asset (§22.4) is a running quotient over the whole
  ledger — the largest accumulation of rounding in the system. It argues, again, for the
  don't-store-the-quotient shape of §1.3.5.

### 1.3.14 Dust (§5.3)

Worth separating two things the design merges:

| Kind of dust | Cause | Fixed by exactness? |
|---|---|---|
| **Representation dust** — `5.55e-17` after three round trips | Binary floating point | **Yes, entirely.** Measured: the same sequence in `Decimal` gives exactly `0` (A.2) |
| **Real dust** — 0.00000004 BTC left after a partial fill, a fee taken in base, or a venue rounding a withdrawal | The market | **No.** Exists regardless of type |

Under `float`, one threshold policy handles both. Under exact decimals, representation dust vanishes
and the threshold becomes purely about real dust — which means **the threshold's correct source
changes**: it is no longer an epsilon chosen by the architecture, it is the venue's own minimum
tradeable step. Same registry tension as §1.3.2 and §1.3.3, arriving from a third direction. Three
independent needs for the same small table is itself an argument.

## 1.4 The eight sub-decisions AP-D1 must bind

| # | Sub-decision | Load-bearing? | Named in `AP`? |
|---|---|---|---|
| **Q1** | The representation: `Decimal`, scaled integer, or captured text with a computation type | Yes | Partly — "exact decimal" |
| **Q2** | **The canonical textual form on disk**, and therefore the content digest and `event_id` | **Yes — silent-corruption class** | **No** |
| **Q3** | Where the `float`→exact boundary sits, and the **named rule for crossing it** (tick quantize vs `str()` vs raw image) | **Yes** | No |
| **Q4** | Whether venue precision (tick, step) is **validated** or merely **recorded** — and therefore whether a minimal instrument-precision table exists | Yes — contradicts §27 either way | No |
| **Q5** | Whether quotients may be **stored at all**, or are always derived from an exact pair | Yes | No |
| **Q6** | Rounding ownership: the decimal context, its precision, and which layer sets it per question | Yes | No |
| **Q7** | Whether adapters capture the **venue's original text** beside the parsed value | Medium — cheap now, unrecoverable later | No |
| **Q8** | The dust policy's source (architecture-chosen epsilon vs venue step) and its version | Medium | Partly — "a named, versioned policy" |

**Q2, Q3 and Q5 are the ones that cost real money if got wrong**, and none of the three appears in
`AP` §31.1's one-line statement of AP-D1.

## 1.5 The alternatives, described

### Option A — Decimal domain kernel, boundary drawn by package

`fmis.money` defines `Asset`, `Money(amount: Decimal, asset: Asset)`, `Quantity(amount: Decimal,
asset: Asset)`, `FxRate` and the dust policy, importing nothing. Everything at or above `fmis.ledger`
is exact; L0–L7 is untouched `float`. A stated module-level decimal context governs division. This is
`AP` §31.1's own recommendation, made concrete.

Requires answering Q2 (canonical form), Q3 (crossing rule) and Q6 (context) explicitly; Q5 remains
optional.

### Option B — Integer minor units

`Money` and `Quantity` hold an `int` count of the asset's smallest unit plus a per-asset exponent
(satoshi, wei, öre). Arithmetic is integer arithmetic: exact, fast, and with **no context, no
rounding mode and no canonical-form ambiguity** — an integer has exactly one textual form, so Q2
dissolves. Division is impossible without an explicit, deliberate rounding call, which turns §1.3.6's
silent problem into a compile-time-visible one.

The cost is that the per-asset exponent registry becomes **mandatory rather than optional**, and a
wrong exponent is a silent factor-of-10^n error — the worst failure mode in the whole comparison.

### Option C — Exactness by durability class

The boundary is drawn by §24.3's four durability classes rather than by package:

- **Source of truth and captured artifact** — every authoritative field (§11.2) is stored as canonical
  decimal **text** and validated on decode. Text is the storage type; it is the thing that must never
  change.
- **Rebuildable projection and disposable aggregate** — computed in whatever type suits the question:
  `Decimal` for sums of money, `float` for ratios and statistics. Nothing here is ever stored, so
  nothing here can be wrong for longer than one process.
- **No quotient is ever a stored field** (Q5 answered in the affirmative by construction).

This makes the guarantee *"what was asserted is preserved exactly, forever"* rather than *"all
arithmetic is exact"* — which is the guarantee the product actually needs (§4 Finding 1), and the only
one of the three that is fully achievable.

### Option D — `float` with a quantization discipline (described for completeness)

Keep `float` everywhere; quantize to a stated precision at every boundary; rely on the dust threshold
for the flat test. Cheapest by far, changes nothing, breaks no guard test. Rejected in advance by
`AP` §30 item 37 — but stating why it fails is worth one line in the ADR, because the *stated* reason
(§5.3's `1e-17` residue) is the weakest available and is independently closed by the dust threshold.
The strong reasons are: a tax figure derived from binary floating point is not defensible to a third
party; and an amount typed by the owner is `ASSERTED` (§5.2) and must round-trip to the character.

---

# PART 2 — AP-D2: migration for irreplaceable records

## 2.1 What is actually undecided

`AP` §5.7 states four rules and calls their conjunction "the migration guarantee":

1. Fields may be added; never removed, never re-typed, never re-meaninged.
2. Every version bump ships a reader for all prior versions — forward-only migration, verified by a
   golden-file corpus with one frozen sample per version per record type.
3. ADR-0005's strictness is preserved *within* a version.
4. A full-dump export exists before the first real record is written.

These are good rules and this investigation does not argue with them either. But **rules 1 and 2
describe a policy, not a mechanism**, and three mechanisms satisfy them with radically different
long-term properties (§2.5). More importantly, the four rules **do not cover** at least seven things
that will occur within the first two years of a live ledger (§2.4). Two of those are unrecoverable if
got wrong.

## 2.2 What the archive does today, measured

| # | Fact | Evidence |
|---|---|---|
| 1 | Supported versions are an **exact-match frozenset**; anything else raises | `src/fmis/archive/envelope.py:37,180-184` — `SUPPORTED_SCHEMA_VERSIONS = frozenset({1})` |
| 2 | There are already **two** version namespaces, with two owners | ADR-0027 §3 — envelope `ARCHIVE_SCHEMA_VERSION` vs payload `WORKSPACE_SCHEMA_VERSION` (`workspace/models.py:55`) / `DAILY_SCHEMA_VERSION` (`daily/models.py:45`) |
| 3 | `AP` §5.7 introduces a **third**, `CAPTURE_SCHEMA_VERSION`, with no stated precedence against the other two | `AP` §5.7, §11.2 |
| 4 | `record_id` is **derived from the content digest** | ADR-0027 §4 |
| 5 | The manifest carries `schema_version` per entry and is **rewritten whole on every append** | `src/fmis/archive/manifest.py:36,125` |
| 6 | Publication is `mkstemp` → `fsync` → `os.replace`, record first, manifest second; a failure between them leaves a reported **orphan**, never a repair | ADR-0027 §6 |
| 7 | The canonical encoding is fixed in one function and is **not itself versioned** | `src/fmis/archive/json_safe.py:50-69` — `sort_keys`, `ensure_ascii=False`, `allow_nan=False`, `separators=(",", ": ")`, `indent=2` |
| 8 | ADR-0027 §8 states plainly that no migration exists and that an unsupported version is **rejected and not recoverable** | ADR-0027 §8, Consequences |

**Fact 7 is the one nobody has written down.** Every stored `content_digest` — and therefore every
`record_id`, and therefore every cross-reference between a proposal, a plan, a trade and an episode —
is computed over bytes produced by that exact function. If `indent`, `separators` or `ensure_ascii`
ever changes, **every historical digest becomes unverifiable and `archive verify` fails against
correct data**. The canonical encoder is a load-bearing, unversioned dependency of the entire
integrity story, and AP-D2 is the decision that should freeze it or version it.

## 2.3 The consequence surface

### 2.3.1 Immutable archives

The archive's guarantees are already strong and correct for this purpose: atomic publication, content
digests, no silent repair, typed errors. What changes with a ledger is **what immutability is for**.
For AO it protected against corruption. For a ledger it also protects against *the owner's own future
self*, and against a migration tool. Every option in §2.5 is really an answer to: *does anything, ever,
rewrite a byte that was published?*

### 2.3.2 Migration

The three mechanisms differ on one axis — **when the upgrade happens** — and everything else follows:

| Mechanism | Upgrade happens | On-disk bytes |
|---|---|---|
| Read-time upcasting | Every read, in memory | Never change |
| Batch rewrite | Once, at a migration event | Replaced |
| Frozen generations | Never; new writes go to a new generation | Never change |

### 2.3.3 Versioning

Three namespaces (fact 3 above) with no precedence rule is a defect waiting to happen. The plausible
resolutions:

- **Collapse to two.** `CAPTURE_SCHEMA_VERSION` *is* the payload version for the new record types.
  Nothing new is introduced; the envelope keeps its own knob as ADR-0027 §3 designed.
- **Keep three, with a stated containment rule.** The capture contract is a cross-record *profile*
  (which fields the tax capture obligation requires) that is orthogonal to any single record's shape.
  Defensible, and more machinery.
- **One version per record type, no global.** Maximum independence, maximum bookkeeping — 12+ counters
  by the time the domain is built out.

This is a small decision with a large blast radius, because a version number written onto twenty
thousand irreplaceable records cannot be reinterpreted later.

### 2.3.4 Snapshots

Portfolio snapshots (§14) are captured artifacts holding frozen marks. They are the record type most
likely to grow fields (new limits, new classifications, new liquidity sources) and the one where
"never removed" bites hardest: a `limits` block that grew four fields over three years produces
snapshots whose comparability across time depends entirely on absence being *stated* rather than
*implied*. This is where §2.4 Q4's ABSENT-semantics decision earns its keep.

### 2.3.5 Audit trail

Today the audit trail is: content digests + a manifest + atomic publication. Notably **absent**:

- Any **ordering proof.** Ledger files are appended per year (§24.1) but nothing binds event N to
  event N−1, so a reordering or a silent deletion of a middle event is undetectable by digest alone
  (each surviving record still verifies).
- Any **completeness proof.** The manifest lists what was filed; nothing attests that the manifest is
  complete. `archive verify` reports orphans (a record with no entry) but a *removed* pair — record and
  entry both gone — leaves no trace.

Whether this matters is a genuine judgement call for a single-user personal system, and this
investigation flags it rather than assuming it. §2.4 Q10 states the options.

### 2.3.6 Backwards compatibility — and the distinction the design does not draw

Two different guarantees, and §5.7 promises only one:

| Direction | Meaning | Promised by §5.7? | Needed? |
|---|---|---|---|
| **Backward** | A **new** reader reads an **old** record | Yes (rule 2) | **Always.** This is the whole point |
| **Forward** | An **old** reader reads a **new** record | **No** | Only if a build is ever downgraded, or if a frozen-generation reader (Option C) meets a newer file |

The forward case is not hypothetical under a single-writer assumption; it arrives the moment the owner
restores a machine from a backup taken before an upgrade, or runs an older checkout to reproduce
something. Under ADR-0005 strictness, an old reader meeting an unknown field **rejects**. The ADR
should say whether that is the intended behaviour (it probably is — reject beats misread) and
therefore whether **downgrading a build after a version bump is an unsupported operation**, stated
plainly rather than discovered.

### 2.3.7 The enum problem — additive fields are not the only additive change

§5.7 rule 1 governs *fields*. But `AP` §8.4 explicitly anticipates **new lifecycle event kinds**
(`UNTRADEABLE_ASSESSED` is written into the table as a future member), §16.2 anticipates new journal
subtypes, and §20.2 anticipates new tags. §26.2 states that *"a new event kind adds a node without
migrating anything."*

**That statement is true of the fold and false of the reader.** A v1 reader meeting
`kind: "UNTRADEABLE_ASSESSED"` has three possible behaviours, and they are not equivalent:

| Behaviour | Consequence |
|---|---|
| Reject the record (ADR-0005 strictness, literally applied) | Correct and severe: one new event kind makes older builds unable to read the ledger at all |
| Accept and preserve the unknown value opaquely | Requires a deliberate "unknown member" representation — which is *precisely* the kind of leniency ADR-0005 exists to forbid, and which §5.2's `ValueOrigin`/`ABSENT` vocabulary is already shaped to express honestly |
| Accept and coerce to a default | Silent misreading. Forbidden by every existing ADR |

**Adding an enum member is a version bump under any honest reading of §5.7 rule 1**, and the design's
own §26.2 claim that it costs no migration is only true because a *newer* reader is doing the reading.
Worth stating explicitly, because the alternative is discovering it when the first new event kind
ships.

### 2.3.8 Reproducibility and replay (Finding 7's three capabilities)

| Capability | What preserves it across a schema change |
|---|---|
| **1 · Exact reproduction** | Only an option where the original bytes survive (A or C). Under a rewrite (B), the strongest achievable claim is *"reproduces the migrated form"* |
| **2 · Reinterpretation** | The **input** records (§18 context packages) must be protected at least as strongly as the outputs. AP-D2's rules must therefore cover context packages explicitly — they are the only reason capability 2 is possible at all (§8.7) |
| **3 · True replay** | Not planned. But a **`code_version` stamp** (git describe / commit) on every captured artifact costs one string and is the *only* thing that makes a future capability-3 decision possible. Not capturing it now forecloses it forever — exactly the §8.5 rule 3 pattern of stamping an opaque version at creation so the policy can be decided later |

The `code_version` stamp is, per byte, the highest-value line item this investigation found.

### 2.3.9 Legal and financial-record integrity

**Not legal advice, and no obligation is asserted here.** What the architecture must be *able* to
express, if an obligation is later confirmed:

1. **Produce, for a stated period, the exact set of events a report consumed** — which requires the
   issued report to name the `event_id`s **and their digests**, not just the period. `AP` §22.5 says
   the engine produces a completeness report; it does not say the report names its consumed set. This
   is a one-field addition now and an unanswerable question later.
2. **Show that those events have not been altered since** — digests do this per record; §2.3.5's
   ordering and completeness gaps are what they do not do.
3. **Reproduce a previously issued report years later** — the design archives the report (§25.2) and
   versions the rule set (§22.3), which is the correct shape. Under a rewriting migration (Option B)
   the reproduction claim weakens to the migrated form.
4. **Deletion.** §31.3 records this as undecided, and it is genuinely in tension with append-only
   immutability. AP-D2 does not have to decide it, but it should state which option it forecloses:
   under A and C, deletion means *destroying the store*; under B, a rewrite mechanism already exists
   and could be pointed at redaction. That is an argument *for* B that nothing else in this
   investigation produces, and it is worth stating honestly.

### 2.3.10 Archive verification

Today: recompute the digest, compare; recompute `record_id`, compare; report orphans and stale
entries. For a ledger, three additions become available and each is a genuine choice:

| Addition | Buys | Costs |
|---|---|---|
| **Fold check** — the resolver runs over the whole ledger and reports events that supersede nothing, cycles, or a Correction whose target is absent | Referential integrity of the correction chain | A verify pass proportional to the ledger, not the manifest |
| **Per-year file digest** | Detects a whole-file replacement or a middle-record deletion | One more digest per year to maintain |
| **Hash chain** — each event carries the digest of the previous | Ordering and completeness proof; tamper-evidence | Makes the ledger genuinely append-only-or-nothing: any repair, re-order or backfill of a historically missed trade invalidates every subsequent link. Probably wrong for a personal system where backfilling forgotten trades is normal |

### 2.3.11 Rebuildability

Worth stating precisely because it is the property that makes everything else survivable: **positions,
holdings, portfolio valuations, cohort statistics and every bias metric are pure folds** (§24.3) and
are therefore *immune* to the migration decision. They are rebuilt from the sources at every process
start, and §24.3's CI test already enforces that they can be.

The migration decision therefore governs a **smaller surface than it first appears**: source-of-truth
records and captured artifacts only. That is roughly seven record types in the first vertical slice
(proposal, lifecycle event, plan + amendment, order, trade, context package, and — from step 3 —
snapshot), not the whole domain. This is the strongest available argument that AP-D2 is genuinely a
decision of days.

## 2.4 The eleven sub-decisions AP-D2 must bind

| # | Sub-decision | Load-bearing? | Named in `AP` §5.7? |
|---|---|---|---|
| **Q1** | The mechanism: read-time upcast, batch rewrite, or frozen generations | Yes | Implied ("forward-only readers") |
| **Q2** | **Whether any published byte is ever rewritten** — the same question stated as a guarantee | **Yes** | No |
| **Q3** | Version namespaces: two, three, or per-record-type, and their precedence | Yes | No |
| **Q4** | Added fields are optional-with-stated-absence; what "absent because it predates vN" reads as | Yes | Partly |
| **Q5** | **Enum extension is a version bump** (§2.3.7); and what an unknown member does | **Yes** | **No** |
| **Q6** | Whether writers may stop emitting a field while readers must still accept it | Medium | No — "never removed" is ambiguous between the two |
| **Q7** | Forward compatibility is **not** promised; downgrading a build after a bump is unsupported | Medium | No |
| **Q8** | **The canonical encoder is frozen or versioned** (§2.2 fact 7) | **Yes — invalidates every digest if got wrong** | **No** |
| **Q9** | What the full dump *is*: a lossless byte-faithful escape hatch, or a flattened projection (§2.3.9, §1.3.12) | **Yes** | Partly — §23 and §4 Finding 1 describe two different things |
| **Q10** | Verification depth: digest-only, + fold check, + per-year digest, + hash chain | Medium | No |
| **Q11** | Golden corpus mechanics: where it lives, what it asserts (byte-identical re-encode vs structural equality), one sample or a matrix | Yes | Partly — "one frozen sample per version per record type" |

**On Q9, which is a real contradiction in the design, not a gap.** §4 Finding 1 item 3 calls the full
export *"Finding 1's escape hatch"* — meaning: if the archive becomes unreadable, this is what
survives. §23.1 and §24.3 classify every export as a **disposable projection** and §23.2 rules that an
export contains *"no value that is not derivable from the ledger."* An escape hatch must be
**lossless**; a projection need not be, and a *disposable* one by definition is not the thing you keep.

The resolution this investigation suggests — offered as a shape, not a decision — is that these are two
different artifacts and should have two names:

- **Full dump** = a byte-faithful concatenation of the stored records with their digests and the
  manifest. An archive *of* the archive. Lossless, verifiable, and not a projection at all.
- **Export suite** = §23.2's flat, human-and-Excel-shaped projections. Lossy where Excel forces it
  (§1.3.12), disposable, and never an escape hatch.

Calling both "export" is what let one document assign them contradictory durability classes.

**On Q11.** A golden test that asserts *decode → re-encode → byte-identical* is much stronger and
cheaper than one asserting structural equality — and it **forbids ever changing the canonical
encoder**, which is Q8 restated. Choosing byte-identical goldens is the cheapest possible way to make
Q8's hazard impossible: the test fails the moment anyone touches `canonical_dumps`.

## 2.5 The alternatives, described

### Option A — Forward-only read-time upcasting; published bytes are immutable forever

Records stay on disk exactly as written, at the version they were written. The current build ships a
reader per version and upcasts `1 → 2 → … → N` **in memory** at decode. `archive verify` continues to
verify original digests forever. No tool ever rewrites a record.

This is the plain reading of §5.7 rule 2, made explicit about the thing rule 2 does not say: **nothing
is rewritten**.

### Option B — Batch rewrite migration to the current version

A migration tool reads every record at version N−1, writes it at version N, and retains the
pre-migration generation as a backup. Exactly one reader exists in the live code at any time.

**This option has a structural collision with the archive's identity scheme that must be stated
before it is weighed.** ADR-0027 §4 derives `record_id` from the content digest, and `AP` §11.5
derives `event_id` the same way. Rewriting a record at a new version **changes its content, therefore
its digest, therefore its ID** — and every cross-reference in the domain (`proposal_id` on a plan,
`plan_id` on a trade, `episode` → `position`, `context_package_id` on a review) is by ID. A rewriting
migration therefore either:

- rewrites every reference too, in one atomic operation over the entire store — a single point of
  catastrophic failure over irreplaceable data; or
- **decouples identity from content**, which is a reversal of ADR-0027 §4 and gives up the property
  that "same identity, different content" is structurally near-impossible.

Neither is fatal, and the second is a legitimate design (a UUID or a monotone sequence as identity,
with the digest kept purely as an integrity check). But it is a decision of the same magnitude as
AP-D2 itself, and it must be made *with* Option B rather than discovered inside it.

### Option C — Frozen generations

Each schema generation is a closed, read-only store with its own vendored, frozen reader module. When
the shape changes materially, a new generation directory opens and new writes go there. Cross-
generation reads go through a thin merge layer; old bytes are never touched and old readers are never
modified again.

A middle path: it bounds the "readers grow without bound" problem by *freezing* rather than
*maintaining* them, and preserves original bytes like Option A.

### Option D — Self-describing, schemaless capture (described for completeness)

Every record carries its own field descriptors; readers carry no schema and never reject an unknown
field. Migration becomes structurally impossible because there is nothing to migrate.

Rejected in advance by the repository's ethic — it is ADR-0005's reject-never-repair inverted, it
makes `RecordValidationError` unreachable, and it makes the domain model untyped at exactly the layer
where §5.1 requires a resolved type consumers *cannot construct*. Included because the option is real,
some systems choose it deliberately, and stating why it loses is cheaper than re-litigating it.

---

# PART 3 — Decision matrices

## 3.1 AP-D1 — money, quantity and currency types

| | **Option A** — Decimal kernel, boundary by package | **Option B** — Integer minor units | **Option C** — Exactness by durability class |
|---|---|---|---|
| **In one line** | `Money(Decimal, Asset)` above `fmis.money`; `float` below | `Money(int_units, exponent, Asset)`; integers only | Canonical decimal **text** is the stored type; computation type chosen per question; no stored quotient |
| **Advantages** | Familiar; reads naturally; stdlib-only; the whole domain speaks one type; matches `AP` §5.3 verbatim so the design needs no revision | Exact by construction with **no context, no rounding mode, no canonical-form ambiguity** — Q2 and Q6 both dissolve; fastest; division is impossible without an explicit deliberate call, so §1.3.6's silent rounding becomes visible | The only option whose guarantee is fully **achievable** — *what was asserted is preserved exactly, forever* — which is the guarantee §4 Finding 1 actually asks for; storage type and computation type are separately chosen, so no quotient can be silently frozen; smallest blast radius on existing code |
| **Disadvantages** | Division is context-rounded, so "exact everywhere" is untrue on first contact (measured: `avg × qty ≠ cost`); needs an explicit canonical form (Q2), an explicit context policy (Q6), an explicit crossing rule (Q3); a stray `float` mixing in is easy and silent | Requires a **mandatory per-asset exponent registry**, contradicting §27 outright; a wrong exponent is a silent factor-of-10ⁿ error; unreadable on disk without the exponent beside it; alien to the way the owner types a fill | Two representations to reason about (stored text, computed value) and a discipline about which is which; the "no stored quotient" rule must be enforced by test or it decays; less familiar as a pattern |
| **Long-term risks** | Rounding drift accumulating in stored quotients (average entry → realized P&L → cohort expectancy) with nothing detecting it; digest divergence from an unstated canonical form (§1.3.9) | One bad exponent in reference data corrupts every amount in that asset, retroactively and invisibly; adding a new asset becomes a data-entry operation with a silent-corruption failure mode | The discipline erodes: a future milestone stores an R-multiple "just for speed" and the guarantee quietly weakens |
| **Complexity** | Medium. One kernel package, one context policy, one crossing rule | Medium-high. One kernel package **plus** reference data with lifecycle | Low-medium. One kernel package, one storage rule, one prohibition |
| **Future maintenance** | Every new derived value re-raises "which type, rounded how" | Every new asset re-raises "what is its exponent, who verified it" | Every new stored field re-raises "is this a quotient" — a cheaper and more mechanical question, and testable |
| **Vision compatibility** | High — it is the design's own text | Medium — collides with §27's "no registry" and with §11.3's three-input friction budget | High — it is §11.4 ("if two fields could disagree, one is not a field"), ADR-0016 §4 and §24.3's durability classes applied to numbers rather than to records |

**A note on combining them.** A and C are not exclusive; C is most naturally *implemented* with A's
`Decimal` as the computation type. The real choice is whether the ADR's guarantee is stated as
*"all arithmetic is exact"* (A, and unachievable) or *"every asserted value is preserved exactly and
no derived value is ever frozen"* (C, and achievable).

## 3.2 AP-D2 — capture contract and migration guarantee

| | **Option A** — Forward-only read-time upcasting | **Option B** — Batch rewrite migration | **Option C** — Frozen generations |
|---|---|---|---|
| **In one line** | Bytes on disk never change; the current build upcasts old versions in memory | A tool rewrites every record to the current version; the old generation is retained as backup | Each generation is a closed store with a frozen reader; new writes open a new generation |
| **Advantages** | Original bytes are the record, forever — capability 1 preserved unconditionally; digests and `record_id`s stay valid for the life of the archive; **no migration event exists**, so no migration event can fail; simplest possible operational story (there is no operation) | Exactly one reader in the live code; the domain model never accretes historical shapes; a rewrite mechanism is the only thing that could ever implement redaction/deletion (§2.3.9 item 4) | Bounds reader growth by **freezing** old readers rather than maintaining them; original bytes preserved like A; a generation boundary is a natural place to make a genuinely breaking change |
| **Disadvantages** | Reader code grows with versions × record types; the in-memory model accretes optional fields that must stay forever; a *semantic* change (not just a field add) is hard to express as an upcast | **Collides with content-derived identity** (§2.5): every rewritten record changes its ID, so either every cross-reference is rewritten in one atomic pass over irreplaceable data, or ADR-0027 §4 is reversed; "what was actually recorded" can no longer be answered byte-exactly | Cross-generation queries need a merge layer; IDs referencing across a boundary need a resolution rule; a frozen reader is still code that must import and still be tested |
| **Long-term risks** | Reader sprawl becomes a maintenance tax at ~5+ versions per type; the temptation to "just drop v1 support" arrives eventually and must be refused | A failed or half-applied migration over a ledger is the **single worst outcome available in this whole document**; requires a verified backup and a verified restore, both of which are then product requirements rather than good practice | Generations proliferate if the trigger is loosely defined; the merge layer becomes the thing nobody wants to touch |
| **Complexity** | Low to start, linear growth | High at the migration event, low between them | Medium and stable |
| **Future maintenance** | One new reader per bump, forever; the golden corpus grows as a matrix (versions × types) | One migration script per bump, plus backup/restore verification, plus reference rewriting | One frozen reader per generation, never revisited; one merge layer, revisited rarely |
| **Vision compatibility** | **Highest.** It is ADR-0027's ethic extended: reject rather than repair, never rewrite, verify rather than fix; and it is the only option under which §4 Finding 1's *"the on-disk shape must be the most boring, most self-describing thing in the repository"* stays true | Lowest. Rewriting published bytes is the operation ADR-0027 §6 was built to make impossible | High, and it is the natural escalation from A when a genuinely breaking change is unavoidable |

**These three are a sequence, not a fork.** A is the default; C is what A escalates to when a change
cannot be expressed as an upcast; B is what neither should ever need. A defensible ADR could adopt A
now and name C as the stated escalation with its trigger — the same "measured trigger" pattern §24.4
already uses for every deferred piece of machinery.

---

# PART 4 — Recommendation (not a decision)

**Status of this part: a recommendation from the investigation. The owner has not decided, no ADR
exists, and nothing below is authorization to implement.**

## 4.1 AP-D1 — recommended: Option C, implemented with Option A's `Decimal`

State the guarantee as what is achievable and what the product needs:

> **Every asserted money and quantity value is stored as canonical decimal text and is preserved
> exactly, forever. Money sums are computed in `Decimal`. No quotient is ever a stored field.**

Because:

1. **It is the only guarantee that survives contact with division.** Measured: `avg × qty ≠ cost`
   under any decimal context. An ADR that promises exactness everywhere is promising something the
   language cannot deliver, and the first person to notice will be right.
2. **It matches the product's actual asymmetry.** §4 Finding 1 is about *irreplaceable* values. An
   asserted fill price is irreplaceable; an average entry is a fold away at any time.
3. **It is the repository's existing idiom**, not a new one — §11.4's balance effects, ADR-0016 §4's
   rejected stored count, and §24.3's durability classes are the same argument applied to records.
4. **It has the smallest blast radius.** No guard test is weakened, `fmis.data` is untouched, and
   nothing below L7 changes.

With these clauses, which the current one-line AP-D1 does not contain:

| Clause | Why |
|---|---|
| **A canonical textual form**, fixed-point, no exponent, stated trailing-zero rule | §1.3.9 — otherwise `0.10` and `0.1` are two different `event_id`s and re-entry is not idempotent |
| **One named crossing rule** for `float` → exact, with the tick-quantize-vs-`str()` choice made and stamped as a policy version | §1.3.2 — otherwise the conversion is invented per call site |
| **No stored quotient**, enforced by a test | §1.3.5, §1.3.6 |
| **Rounding ownership**: presentation rounds for display, the tax rule set rounds for reporting, the money kernel never rounds | §12.4's one-owner-per-question, applied again |
| **Adapters capture the venue's original text** beside the parsed value | §1.3.11 — costs a string, unrecoverable later |
| **Dust is the venue's minimum step, not an architecture-chosen epsilon**, versioned | §1.3.14 |

**On Q4 (validate vs record venue precision), the recommendation is `record`, not `validate`** — §11.3's
three-input happy path and R2's adoption risk outrank a validation that §5.1's correction mechanism
already covers. That decision also defers the instrument registry, keeping §27 intact.

## 4.2 AP-D2 — recommended: Option A, with Option C named as the stated escalation

> **No published byte is ever rewritten. Every version bump ships readers for all prior versions,
> which upcast in memory at decode. When a change cannot be expressed as an upcast, a new generation
> opens rather than the old one being rewritten.**

Because:

1. **It is the only option that does not fight the archive's own identity scheme.** Content-derived
   `record_id` (ADR-0027 §4) and `event_id` (§11.5) make rewriting structurally hostile; Option B
   requires reversing one of the two best decisions AO made.
2. **The worst outcome in this document is a half-applied migration over a ledger**, and Option A does
   not have that outcome available.
3. **The surface is smaller than it looks** (§2.3.11): rebuildable projections and disposable
   aggregates are immune, so the guarantee covers roughly seven record types in the first slice.
4. **It is ADR-0027's ethic extended rather than amended** — reject, never repair; verify, never fix.

With these clauses, which the current §5.7 does not contain:

| Clause | Why |
|---|---|
| **Freeze the canonical encoder**, and pin it with byte-identical golden tests | §2.2 fact 7 — every stored digest depends on it, and nothing currently protects it |
| **An enum member addition is a version bump**, and an unknown member is a clean rejection | §2.3.7 — §26.2's "no migration needed" is true of the fold and false of the reader |
| **Every added field is optional with a stated absence semantic** (`ABSENT(reason)` already exists in the vocabulary) | §2.3.4 — otherwise cross-period comparability degrades silently |
| **Forward compatibility is not promised**; downgrading a build after a bump is unsupported, stated | §2.3.6 |
| **Two names, two artifacts**: a lossless byte-faithful **full dump** (the escape hatch) and the lossy **export suite** (the projection) | §2.4 Q9 — the design currently assigns one artifact two contradictory durability classes |
| **Version namespaces collapse to two** — envelope and payload, as ADR-0027 §3 already designed; `CAPTURE_SCHEMA_VERSION` *is* the payload version for the new record types | §2.3.3 |
| **A `code_version` stamp on every captured artifact** | §2.3.8 — one string; the only thing that keeps a future capability-3 decision possible |
| **A tax report names the `event_id`s and digests it consumed** | §2.3.9 item 1 — one field now, unanswerable later |
| **Verification depth: digest + fold check.** No hash chain | §2.3.10 — a chain forbids backfilling a forgotten trade, which is normal behaviour for this owner |
| **Backup and verified restore are product requirements**, with a stated cadence | §4 Finding 1 item 4, which currently states the requirement without an owner |

**Deliberately not recommended:** a hash chain, a per-record-type version counter, deletion/redaction
support, and any change to `fmis.data`. Each is a real capability with a real cost, and none is needed
before the first record is written.

## 4.3 Sequencing note

**AP-D1 must be decided before AP-D2, not beside it.** AP-D1 Q2 (the canonical textual form of an
amount) determines the bytes, which determine the digest, which determine `event_id`, which is AP-D2's
identity contract. The backlog sequences them as one item ("ADRs for AP-D1 and AP-D2"), which is fine
— but within that item the order is forced.

---

# PART 5 — Risk register discovered by this investigation

Ordered by severity. Every one is a consequence of a decision **not yet made**, and none is a defect in
committed code.

| # | Risk | Severity | Where |
|---|---|---|---|
| **N1** | **Two domain-equal amounts (`0.10`, `0.1`) produce different digests, different `event_id`s, and therefore a duplicate ledger event instead of an idempotent no-op** — measured against the repository's own `canonical_dumps` | **Critical** | §1.3.9 |
| **N2** | **A rewriting migration is structurally incompatible with content-derived record identity** — Option B silently requires reversing ADR-0027 §4 | **Critical** | §2.5 Option B |
| **N3** | **The canonical encoder is an unversioned, unprotected dependency of every stored digest** — a change to `indent`/`separators` invalidates the integrity of the whole archive against correct data | **Critical** | §2.2 fact 7 |
| **N4** | **"Exact decimals everywhere" is unachievable** — every quotient (average entry, R, FX, weights, expectancy) is context-rounded; measured `avg × qty ≠ cost` | **High** | §1.3.6 |
| **N5** | **Adding an enum member breaks older readers**, and §26.2 states the opposite for the fold — the first new lifecycle kind will surface this | **High** | §2.3.7 |
| **N6** | **The `float` → exact crossing rule is unowned**, and the only principled version needs tick-size reference data that §27 excludes | **High** | §1.3.2 |
| **N7** | **The full dump is both "the escape hatch" (§4) and "a disposable projection" (§23/§24.3)** — one artifact, two contradictory durability classes | **High** | §2.4 Q9 |
| **N8** | **Adapters discard exactness at parse time** (`binance.py:286`), and the exchange-sync path in §32 step 4 is the one that will carry fills | **Medium** | §1.3.11 |
| **N9** | **Three version namespaces with no precedence rule**, written onto irreplaceable records | **Medium** | §2.3.3 |
| **N10** | **No ordering or completeness proof over the ledger** — a deleted middle event leaves every surviving digest valid | **Medium** | §2.3.5 |
| **N11** | **`Decimal` is AST-banned in three packages**; any option placing it below L7 must state what replaces those guards | **Medium** | §1.2 fact 3 |
| **N12** | **Excel silently coerces exact amounts to doubles**; export column contracts must be text | **Low** | §1.3.12 |
| **N13** | **`code_version` is not captured**, foreclosing any future capability-3 decision at a cost of one string | **Low, unrecoverable** | §2.3.8 |
| **N14** | **A tax report does not name its consumed event set** — one field now, unanswerable later | **Low, unrecoverable** | §2.3.9 |

**N13 and N14 share a property worth naming.** Both are trivial today and impossible retroactively —
the same class as §22.2 items 9 and 10, the two capture requirements the design already calls urgent
for exactly this reason. Any decision that defers them defers them permanently.

---

# Appendix A — Measurements and how to reproduce them

All measured on this machine, CPython 3.12, repository at `75a4f40`, in a throwaway interpreter
session. **No files were created and no repository code was modified.** Each can be reproduced with a
few lines at a Python prompt.

| # | Measurement | Result |
|---|---|---|
| **A.1** | `json.dumps({"q": Decimal("0.1")})` | `TypeError: Object of type Decimal is not JSON serializable` |
| **A.2** | `0.1` added three times, minus `0.3` — `float` vs `Decimal` | `float`: `5.551115123125783e-17` · `Decimal`: `0.0` (exactly) |
| **A.3** | `Decimal("10000.00") / Decimal("3") * Decimal("3") == Decimal("10000.00")` | **`False`** — evaluates to `9999.999999999999999999999999`; default context precision 28 |
| **A.4** | `Decimal("0.10") == Decimal("0.1")` versus their `str()` and `canonical_dumps` digests | Values **equal**; strings `"0.10"` / `"0.1"`; SHA-256 of the canonical bytes `022462ef4896468a` vs `ce8c420f63a142f0`. Also: `Decimal("100").normalize()` → `"1E+2"` |
| **A.5** | 10⁶ additions, `float` vs `Decimal` | 28 ms vs 41 ms — **1.5×**, not the 50–100× commonly assumed |
| **A.6** | `59020.13` converted three ways | `Decimal(x)` → `59020.1299999999973806552588939666748046…` · `Decimal(str(x))` → `59020.13` · `quantize` to a `0.01` tick → `59020.13` |
| **A.7** | `float` usage in the repository | 128 occurrences across 36 of 108 source files, in 13 packages |
| **A.8** | Guard tests banning the identifier `Decimal` | `tests/test_level_crossing.py`, `tests/test_structure_break.py`, `tests/test_change_of_character.py` — AST `Name`/`Attribute` scans, alongside `round`, `quantize`, `isclose`, `epsilon`, `atol`, `rtol`, `approx` |

---

# Appendix B — Questions this investigation could not answer

Stated so they are not mistaken for having been considered and dismissed.

| Question | Why it is open |
|---|---|
| **Whether any Swedish record-keeping obligation applies to this archive, and for how long** | A legal question. `AP` §22 defers every legal question to a qualified adviser and this document does the same. It changes AP-D2 only if the answer requires an evidentiary standard higher than digest-per-record — which would promote §2.3.10's ordering proof from optional to required |
| **The owner's actual asset set and its precision requirements** | Determines whether the per-asset exponent registry (Option B) is 5 rows or 200, which is most of that option's cost |
| **Whether the owner ever intends to downgrade a build or run an older checkout** | Determines whether §2.3.6's forward-compatibility gap is theoretical or operational |
| **Whether deletion/redaction of personal financial records will ever be required** | §31.3 records it as open. It is the only argument this investigation found *in favour of* a rewrite mechanism (Option B), and it should be answered before A is bound rather than after |
| **The real cadence and retention policy for archived analyses** | §28.1 measures them at 77 % of total bytes and §31.3 defers the policy. It does not affect either decision here, but it dominates the backup requirement that §4 Finding 1 item 4 makes a product requirement |

---

**End of investigation. No decision has been made. Two ADRs remain to be written, and the owner has
not chosen between the options above.**
