# Directional vocabulary and the trading domain — a boundary note

**Milestone:** BH (Trade Domain Foundation)
**Status:** **Design note. It decides nothing.** It records an architectural issue the
implementation revealed, states what was done to keep the repository consistent, and names the one
decision that belongs to the owner. No ADR was written, no ADR was amended, and no accepted decision
was reopened.
**Date:** 2026-08-12
**Type:** Implementation-revealed boundary note.
**Scope:** One rule — ADR-0028 §5 — and one test file, `tests/test_directional_vocabulary_boundary.py`.

---

## 1. What happened

Implementing the Trade Domain Foundation produced four types that name a market side:

| Type | Package | What it says |
|---|---|---|
| `TradeDirection` (`LONG` · `SHORT` · `NO_TRADE`) | `fmis.snapshotting` | which side a **frozen reading** came down on |
| `TradeSide` (`BUY` · `SELL`) | `fmis.ledger` | which way the base asset **actually moved** |
| `PositionDirection` (`LONG` · `SHORT` · `FLAT`) | `fmis.positions` | which way exposure **currently points** |
| `DirectionalCase.direction` | `fmis.proposal` | which side a **suggestion** argued |

`tests/test_directional_vocabulary_boundary.py` — a repository-wide AST scan shipped with Milestone
AR — asserts that no Python identifier or string-literal value equals `long`, `short`, `buy`, `sell`,
`bullish` or `bearish` anywhere under `src/fmis` except `fmis/swing_setup/` and
`fmis/pipeline/cli.py`, the two locations ADR-0028 §5 names.

All four types fail that scan. **This was predicted.** `ADR_IMPLEMENTATION_GATE.md` Part 8 ranks it
blocker #3 — *"23 guard-test files ban directional vocabulary at the render surface"* — and Part 3
states the conclusion plainly:

> **The one genuinely required decision is not on any list: where directional vocabulary is permitted
> to live.**

That decision was needed by the setup engine (Milestone AR, which took the `swing_setup` exemption)
and is needed again here, for a different reason.

---

## 2. Why this is not the same crossing AR made

AR's exemption answers *"may an engine that reads candles emit a side?"* — and ADR-0028's answer is
**no, except for the one engine designed to**. That rule is about **interpretation of a market**.

BH's types answer a different question: *"may a record of the owner's own money say which way it
went?"* A ledger that cannot record a buy is not a ledger. A position that cannot say it is long
cannot state exposure, cannot size risk against a stop, and cannot be closed. Direction here is
**`ASSERTED` by the owner or the venue about a fact that already happened**, not `POLICY_DERIVED`
from an engine's reading of price.

The distinction is the whole of the trading-domain architecture's Law 6 — *the trading domain reads
the market half and is never read by it* — expressed in vocabulary rather than in imports.

---

## 3. What was done, and what it costs

The guard was **widened, not weakened**, and the widening is bounded and asserted:

1. Four trading-domain packages are exempt, **named one by one** rather than pattern-matched. A
   fifth appearing anywhere fails the test.
2. A new test — `test_the_market_half_still_holds_no_directional_vocabulary_at_all` — scans **every
   package that reads a candle, by name**, and asserts zero directional tokens. This is the
   assertion that actually protects ADR-0028's rule, and it did not exist before: the original test
   protected the rule by scanning *everything except one directory*, which is a weaker statement
   than scanning *the twenty directories that matter*.
3. A third new test asserts each exemption is **used**, so an exemption granted to a package that
   turns out not to need it cannot quietly become wrong.

Net effect: the market half is now guarded more explicitly than before, and the trading domain's
exemption is enumerated rather than implied.

**What it costs:** `tests/test_directional_vocabulary_boundary.py` was edited. Its original test
body is unchanged; the permitted set grew and two tests were added.

---

## 4. The decision that belongs to the owner

**ADR-0028 §5, as written, does not scope its rule to the analysis engines.** It says the vocabulary
lives in `fmis.swing_setup`. The trading domain now holds it too, and a test asserting that is not
the same thing as an ADR permitting it. The repository's own rule — *where they disagree, the ADRs
win* — means this note cannot close the gap.

**The proposed amendment, offered as a shape and not a decision:**

> ADR-0028 §5 applies to the **market half** — every module that reads candles and produces a
> reading of a market. The **owner half** records direction as an `ASSERTED` property of the owner's
> own money: a trade's side, a position's exposure, a proposal's chosen side, and the side a frozen
> reading came down on. The two halves are distinguished by `ValueOrigin`, not by vocabulary.

Two things follow if the owner accepts it, and neither was done here:

- ADR-0028 gains a scope sentence and a `Superseded-in-part-by` or `Amended` marker.
- `tests/test_directional_vocabulary_boundary.py`'s docstring cites the amended ADR rather than this
  note.

**If the owner rejects it**, the alternative is to rename the four types away from the banned words —
`TradeSide.ACQUIRE`/`DISPOSE`, `PositionDirection.POSITIVE`/`NEGATIVE`. That is representable and is
recorded here as the rejected option, because a ledger whose buy is called something else is a
ledger every future reader has to translate, and translation is where facts get lost.

---

## 5. What this note does not claim

It does not claim the amendment is correct, that ADR-0028's authors would agree, or that no other
guard in the suite will need the same treatment when the next domain package ships. It records one
crossing, what was done about it, and who owns the decision.
