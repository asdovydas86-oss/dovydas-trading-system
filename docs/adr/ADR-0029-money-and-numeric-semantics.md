# ADR-0029: Money and numeric semantics — where `Decimal` is required and where `float` stays

**Status:** Accepted
**Date:** 2026-09-06
**Milestone:** Slice 4 — Risk & Trade-Planning Foundation

## Context

Slice 4 wires the risk domain to the product for the first time, which means arithmetic over the
owner's capital reaches a page they read before deciding what to trade. The prior architecture
recorded an explicit warning about doing that without settling the numeric contract first:

> **Do not discover float-vs-Decimal mid-risk implementation.** And: never use `float` for money.

An audit of the repository at `03dd4e0` found that the semantics are **already implemented,
already tested and already shipped** — `fmis.money` has held exact, asset-tagged `Money` and
`Quantity` since Milestone BI, sixty-odd modules depend on it, and the durable store persists its
canonical text. What did not exist was an ADR. `docs/adr/` runs ADR-0001 to ADR-0028 and none of
them is about money; the rule lived in `TRADING_DOMAIN_ARCHITECTURE_V1.md` §5.3 (`AP`), a design
record, and in module docstrings.

That is the gap this ADR closes. **It ratifies an implemented boundary; it does not design a new
one, and no production behaviour changes because of it.** The decision needed a place where a
future reader can find it and a guard that fails when it is crossed, because the next milestone to
touch money should not have to re-derive the rule from `fmis.money`'s docstring.

## Decision

**Money and market measurement are different kinds of number, and the boundary between them is one
named function.**

### 1. Every asserted monetary and quantity value is exact

A value the owner asserts, or that the system stores, is `Decimal` — never `float`. It is carried
as `Money(amount: Decimal, asset: AssetCode)` or `Quantity(amount: Decimal, asset: AssetCode)`.

**There is no bare number.** A monetary field without an asset is a modelling error. Arithmetic
between two amounts in different assets raises `AssetMismatchError` rather than converting: a
conversion needs a dated rate with its own provenance, which is a decision and not an implicit cast.

The reason is not stylistic. Binary floating point cannot represent `0.1`; three buys closed by
three sells leave roughly `1e-17` of residue, and under *"flat means zero"* that position never
closes, never becomes an episode, and quietly biases every aggregate that reads it.

### 2. The market half keeps `float`, deliberately

The OHLCV contract, every indicator, every level price, every ATR and every ratio in the
market-measurement half stays `float`. A candle close is a **measurement**, not an assertion of
value; it carries the precision of the venue that published it, it is never summed into a balance,
and converting the whole feature engine to `Decimal` would cost a large refactor of code that has no
money in it.

**Market-measurement semantics and money semantics are not the same thing**, and this ADR declines
to unify them.

### 3. Exactly one crossing, and it is named

`fmis.money.exact_from_market_price(price: float, name: str) -> Decimal` is the **only** place a
`float` becomes an exact value in the repository. It converts through `repr`, which for a Python
float is the shortest string that round-trips — so `0.1` becomes `Decimal("0.1")` and not
`Decimal(0.1)`'s fifty-five-digit expansion. Every other exact value is typed by the owner or read
from a venue as text and never passes through a float at all.

### 4. Canonical text is part of identity

`canonical_decimal_text` is the single spelling of an amount: `0.10` → `0.1`, `1E+3` → `1000`,
`-0` → `0`, plain notation always. `Decimal("0.10")` and `Decimal("0.1")` are equal as values and
produce different SHA-256 digests under `canonical_dumps`; since `event_id` derives from that digest,
two spellings of one amount would be two events. Canonicalizing at construction is what makes
re-entering a fill after a crash an idempotent success.

Every decimal operation in `fmis.money` runs in a pinned `Context(prec=34, traps=[InvalidOperation])`
rather than the ambient one, because `getcontext()` is thread-local and mutable and a caller who had
set `prec=6` for their own reasons would otherwise change what the domain considers the canonical
spelling of an amount — and therefore change a content digest.

### 5. `NaN` and `Infinity` are not amounts

Non-finite values are rejected at construction, so no such value can reach a stored record, a digest,
a comparison against a limit, or a page.

### 6. Rates, fractions and ceilings follow money, not measurement

A risk fraction, a percentage-of-equity limit and the specification's per-trade ceiling are
`Decimal`. This is the case this milestone forced and it is worth stating plainly: `0.02` as a
binary float is `0.0200000000000000004163…`. A ceiling comparison against that decides a
capital-preservation limit by representation error — `2.0000000001 %` could pass and
`1.9999999999 %` could fail, depending on nothing anyone wrote down. Every comparison against a risk
limit is exact decimal arithmetic, and a `float` fraction is refused with a `TypeError` rather than
converted.

JSON numbers are binary floating point, so a fraction or an amount arriving from the owner's
configuration file as a JSON number is **refused by name** and must be quoted as text.

## Consequences

- The boundary is now findable. A future milestone touching money reads this rather than inferring
  the rule from a docstring.
- No production code changed to adopt this ADR. It describes `fmis.money` as built.
- `Money` arithmetic raises rather than converting across assets, so a caller holding two currencies
  must obtain a dated rate. There is no FX conversion in this build, and a declared capital figure in
  one asset cannot size a market quoted in another — it reports the mismatch instead.
- The market half is untouched, so ADR-0013's exact-`float` price comparison and every feature
  engine remain as they are.
- The cost is that two numeric worlds coexist and a developer must know which side of the boundary
  they are on. `exact_from_market_price` is the one named door between them, which is what makes the
  question answerable rather than a matter of care.

## Alternatives rejected

**Convert the market half to `Decimal` too.** Uniform, and wrong: it would impose exactness on
measurements that do not have it, cost a repository-wide refactor of code holding no money, and slow
every indicator for no correctness gain. Precision a measurement does not possess is not precision.

**Use integer minor units (cents, satoshis).** Standard in payments and a poor fit here: crypto
quantity precision varies per asset and per venue, the correct scale is not knowable at the type
level, and a wrong scale is a silent factor-of-1000 error rather than a rejection.

**Allow `float` for "display only" money.** Rejected because the display path is where a wrong
number is acted on, and a value that is exact everywhere except on the page is exact nowhere that
matters.
