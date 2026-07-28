# ADR-0010 — Volume foundation: shared measurement, deferred interpretation

**Status:** Accepted
**Date:** 2026-07-28
**Decides:** the first deterministic volume metrics, their window convention, and why their
interpretation is deliberately not built yet (Milestone T)
**Implemented by:** `feat(volume): add deterministic volume foundation v1a`
**Relates to:** [ADR-0008](ADR-0008-decision-support-evidence-boundary.md) (evidence classification, where
volume interpretation will eventually live); [ADR-0009](ADR-0009-trading-analysis-context-boundary.md)
(shared calculations do not imply shared decision logic);
[ADR-0006](ADR-0006-provider-adapter-contract.md) (provider-native fields stay in the adapter)

---

## Context

Every indicator implemented so far reads price. `Candle.volume` has been carried, validated, and never
used. Volume is the most obviously missing deterministic input: participation is what distinguishes a
move that many participants took part in from one that few did, and no layer above can reason about that
distinction if nothing measures it.

The `fmis.features.volume` package has existed as a documented placeholder since the Feature Engine was
built, naming exactly these metrics as its intended contents. Nothing in the repository computes a
rolling mean of anything: SMA appears only *inside* EMA, ATR, and RSI as a seed, never as a reusable
kernel. So this is genuinely new arithmetic, not a duplicate.

## Decisions

### 1. Volume is a shared deterministic measurement, computed once
`AverageVolume` and `RelativeVolume` are ordinary features in the existing engine — same
`BaseFeature`/`FeatureResult`/registry conventions as EMA and RSI, category `FeatureCategory.VOLUME`. No
parallel indicator engine, no second orchestration path.

Both take their arithmetic from one kernel, `volume_math.trailing_mean`, following the `ema_math.py`
precedent: a small pure function that indicators share rather than re-implement. A test asserts the mean
is computed in exactly one module and that no other package — pipeline, decision support, providers,
ingest, data, alignment, relative value — contains volume-baseline arithmetic.

### 2. The baseline excludes the current candle
`average_volume` is the mean of the ``lookback`` candles **preceding** the latest closed one;
`relative_volume` compares the latest candle against that baseline:

```
current_volume  = closed[-1].volume
average_volume  = mean(closed[-(lookback+1) : -1].volume)     # lookback candles, current excluded
relative_volume = current_volume / average_volume
```

Including the current candle would let a value dilute its own comparison, and the dilution is worst
exactly when the measurement matters most: with lookback 20, a candle trading 20× its baseline would
report roughly 10.5× instead of 20×, because it is inflating the denominator it is being divided by. The
smaller the lookback, the worse the distortion. Warm-up is therefore ``lookback + 1`` closed candles, not
``lookback``.

Default lookback is **20**, and it is the only registered default. Multiple presets (10/20/30/50) were
rejected: there is no consumer that needs them, and a preset per taste is a strategy assumption wearing a
constant's clothing. The features are parameterized, so any lookback is available on request.

### 3. Zero baseline is undefined, never infinity and never epsilon
If every candle in the baseline window reported zero volume, `relative_volume` has no denominator. It
returns ``value=None`` with ``undefined_reason="zero_average_volume"`` and ``insufficient_data=False``.

No infinity is fabricated and no epsilon is substituted. Both would convert "we cannot say" into a number
that a later layer would treat as a measurement — and an epsilon in particular would produce an
enormous, entirely artificial ratio precisely in the illiquid conditions where a reader is most likely to
over-read it. This is not hypothetical: a trading halt, a suspended listing, or a thin session on a
smaller venue genuinely produces a zero window.

Three outcomes are therefore distinguishable from the result alone:

| Outcome | `value` | `insufficient_data` | `undefined_reason` |
|---|---|---|---|
| calculated | float | `False` | absent |
| warming up | `None` | `True` | absent |
| undefined | `None` | `False` | `"zero_average_volume"` |

Zero *current* volume against a non-zero baseline is a perfectly defined `0.0`, not an error.

### 4. Volume validity is inherited, not re-checked
`Candle` already rejects negative and non-finite volume and permits zero. The volume package re-validates
none of it; a test asserts the canonical rejections still hold and that the package contains no
validation strings of its own. Duplicating the rule would create a second source of truth for something
the canonical model owns.

### 5. Interpretation is deferred to a separate milestone
No labels. No `HIGH_VOLUME`, `LOW_VOLUME`, `STRONG`, `WEAK`, `CONFIRMED_BREAKOUT`. No thresholds — a
threshold constant is an interpretation smuggled in as data, and a test scans for one. `EvidenceReport`
is untouched: classifying relative volume as evidence is Volume Evidence v1b's job.

Keeping them apart is what makes the measurement reusable. The moment a threshold lands in the
calculation, the number stops being a fact and becomes one market's opinion, and every other market
inherits it silently.

### 6. Shared calculation does not mean identical interpretation
This is the decision that matters most for what the system is being built to do.

The arithmetic above is identical for a 24/7 crypto perpetual, an HKEX share with a lunch break and a
closing auction, a Shanghai listing with daily price limits, a thinly traded mining company, and a
mega-cap AI stock. **What the resulting number means is not.** Consider only what "reported volume" even
is across those venues:

- **Crypto** trades continuously with no session boundary, so a "20-candle baseline" spans a fixed
  duration; volume is venue-specific and the same asset trades simultaneously elsewhere, so one
  exchange's volume is a sample, not the market's.
- **HKEX** has a morning session, a lunch break, and a closing auction. A bar containing the auction is
  structurally different from a mid-session bar, and a daily baseline mixes both.
- **Shanghai/Shenzhen** have opening/closing auctions and price-limit mechanics; a limit-locked day can
  show collapsed volume for reasons that have nothing to do with participation waning.
- **Mining equities** are frequently thin, so a single institutional order can produce a relative volume
  a crypto trader would read as extraordinary.
- **Large-cap AI names** fragment across lit venues, dark pools, and off-exchange reporting, so the
  volume a single feed reports is a partial count whose completeness varies by venue and time of day.

The core computes the measurement. Market-specific reasoning — later, and per module — interprets it.
This mirrors ADR-0009 §4: the deterministic engines are shared precisely because they are free of
interpretation.

### 7. Provider-specific volume fields stay outside the core
Binance's klines carry taker buy base/quote volume and quote asset volume. None of them enter the
canonical model, and this milestone reads only `Candle.volume`. Those fields are venue-specific
conventions, not universal quantities: there is no HKEX equivalent of "taker buy base volume", and
inventing a canonical field for it would either be empty for most markets or mean different things in
each. Per ADR-0006 the adapter maps only what the canonical shape defines, and it computes no indicator
— a test asserts the Binance adapter contains no averaging or volume-ratio arithmetic.

### 8. `volume` is not added to the indicator source vocabulary
`VALID_SOURCES` remains `("open", "high", "low", "close")`. Adding `"volume"` would silently enable
`ExponentialMovingAverage(20, source="volume")` and an RSI of volume — a scope expansion with no decision
behind it, and one that would give two different "average volume" answers with different smoothing. The
volume features are explicit about their own arithmetic instead.

## Alternatives considered

- **Include the current candle in the baseline** (the common charting default). Rejected: see §2 — it
  makes a spike hide inside its own denominator, which is precisely the case the metric exists for.
- **Register a `current_volume` feature.** Rejected: it would be a second source of truth for
  `Candle.volume`, which is already authoritative. It is reported in `RelativeVolume`'s metadata instead,
  so a consumer sees the input without a competing owner.
- **Register `AverageVolume(20)` as a default too.** Rejected: `RelativeVolume`'s metadata already carries
  `average_volume`, so a second default feature would restate a number the first one reports. The class
  remains registerable on request.
- **Several default lookbacks.** Rejected: no consumer needs them (§2).
- **Return `inf` or use an epsilon denominator for a zero baseline.** Rejected: see §3.
- **Put the kernel in `features/indicators/` beside `ema_math`.** Rejected for now: the volume package is
  the documented home for these metrics, and one caller does not justify promoting a helper into the
  shared indicator layer. If a non-volume feature ever needs a trailing mean, promoting it is an
  evidence-based move at that point.
- **Classify volume as evidence in the same milestone.** Rejected: it couples calculation to
  interpretation (§5) and would need the market-specific reasoning that §6 says does not exist yet.

## Consequences

- Every analysis now carries `relative_volume_20`, computed identically across every market the system
  will ever read, with its inputs visible in metadata.
- A later Volume Evidence milestone can classify the ratio without touching the calculation — and will
  have to decide *per market* what a given ratio means, which is the hard part this ADR deliberately
  leaves open.
- Warm-up rises for a default analysis only in the volume feature itself (21 closed candles); MACD's 34
  still dominates the default set.
- Raw exchange-reported volume remains a limited instrument. It says how much traded, never who traded or
  why, and it is not comparable across venues without normalization the system does not yet perform. Any
  future interpretation layer inherits that limitation and should state it.
