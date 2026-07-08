# Analysis Notes — Swing Trading Analyzer v2 → v3

**Date:** 2026-07-08
**Problem reported:** The v2 prompt almost always produced LONG suggestions and rarely SHORT, even on clearly bearish charts.

## Root cause: structural bias in the v2 entry rules

The v2 LONG and SHORT checklists *looked* symmetric (9 mirrored items each, 3 required),
but interacted asymmetrically with market reality and with how LLMs process prompts.

### 1. Trend gate double-counted in LONG's favor (biggest issue)

Both checklists started with "Weekly trend bullish/bearish" + "Daily trend bullish/bearish"
as two separate confirmations. In crypto, price sits above the weekly EMA 200 with a golden
cross most of the time, so a LONG usually started with **2 free confirmations** and needed
only 1 real signal to reach the 3-confirmation threshold. "Weekly trend bearish" required
price below weekly EMA 200 **and** a weekly death cross — a deep-bear-market condition —
so a SHORT nearly always had to find 3 genuine signals.

### 2. Short setup contradicted the prompt's own EMA rules

The Weekly EMA section said EMA 200 is "too low — breaking here means the trend already
reversed" (i.e., too late), and that weekly **EMA 50 rejection** is the good short signal.
Yet the Short Setup required price below weekly EMA 200 — defining shorts by the exact
condition the prompt called "too late." The actually-useful weekly EMA 50 rejection was
never part of the entry checklist.

### 3. Bullish-only tool definitions

- RSI divergence was defined only in the bullish direction ("price lower low, RSI higher
  low"). No bearish mirror existed, so RSI divergence could only ever support LONGs.
- The "STRONGEST SIGNAL" S/R flip listed only "old resistance becomes support" — the
  bearish mirror ("old support becomes resistance") was missing.
- Chart patterns listed Head and Shoulders but not Inverse Head and Shoulders (this one
  actually favored shorts — inconsistency, not direction, was the pattern).

### 4. RSI regime gate locked shorts behind a rare condition

"Only sell overbought on Daily when Weekly trend is bearish" — with "weekly bearish"
defined as in #1, this rule almost never activated.

### 5. No NO-TRADE option + spot framing

The output format demanded a full trade plan on every analysis, and the opening question
("How much USDC do you have?") framed everything as spot buying. On ambiguous charts the
model had to pick something, inferred shorting might not be executable, and defaulted
to LONG.

### 6. Order anchoring

The Long Setup was always listed and evaluated first; SHORT read as the fallback branch.
LLMs anchor on the first framework they evaluate.

## Changes in v3

1. **Regime classification first** — 1W/1D/4H each classified BULLISH / BEARISH / RANGE
   with mirrored criteria (EMA 200 position + market structure) before any trade idea.
2. **Both directions scored on every analysis** — mandatory 0–9 score for LONG *and*
   SHORT, both reported in the output. Kills order anchoring and makes bias visible.
3. **Trend alignment collapsed to 1 point** — weekly+daily alignment is a single
   confirmation, removing the 2-free-points head start for LONGs.
4. **Short trigger fixed** — weekly EMA 50 rejection (in a bearish/range regime) is now
   the short-side trigger, mirrored by weekly EMA 50 bounce for longs. Weekly EMA 200
   demoted to "too late" status in both directions, consistently.
5. **All tools defined in both directions** — bearish RSI divergence, support→resistance
   flip, inverse H&S added; RSI overbought/oversold gates now also active in RANGE regime.
6. **Explicit NO TRADE outcome** — required when neither direction scores ≥ 3 or scores
   tie; framed as a successful, capital-protecting result.
7. **Shorting declared always available** — prompt states shorts execute via perps/margin
   so the USDC spot framing can't bias direction.
8. **Counter-trend trades defined** — allowed only at major S/R with reversal confirmation,
   labeled COUNTER-TREND, confidence capped at Medium.

## Expected outcome

Direction now follows the higher of two symmetric scores computed on every chart, so
LONG/SHORT frequency should track actual market conditions — and neutral charts produce
NO TRADE instead of a default LONG.
