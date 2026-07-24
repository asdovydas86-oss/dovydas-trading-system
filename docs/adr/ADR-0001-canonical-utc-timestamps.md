# ADR-0001 — Canonical UTC timestamps

**Status:** Accepted
**Date:** 2026-07-24
**Implemented by:** `5e7e3d5` — `feat(data): enforce canonical UTC timestamps`
**Applies to:** every timestamp stored in a canonical model (`Candle`, `CandleSeries`,
`ObservationSeries`, and every canonical model added later)
**Enforced by:** `src/fmis/data/_timeutils.py::validate_utc_timestamp`, called from each model's
`__post_init__`; covered by `tests/test_data_models.py` and `tests/test_observation.py`

---

## Context

FMITS exists to compare series that come from different worlds: crypto trades 24/7, equities observe a
five-day calendar with holidays, macro series are published monthly against national calendars, and every
provider reports time in whatever convention it prefers — epoch milliseconds, exchange local time, an
ISO-8601 string with an offset, or a naive string with the timezone stated only in the API documentation.

The Relative Value Engine's central operation is deciding whether two observations describe **the same
instant**. Everything downstream inherits that judgement: alignment, correlation, look-ahead prevention,
and any backtest built on top of them. A timestamp convention is therefore not a formatting detail — it
is the correctness foundation of the whole comparison layer.

Three specific hazards forced an explicit rule rather than a convention-by-habit:

1. **Naive timestamps.** A `datetime` with no `tzinfo` has no defined instant. Python will happily
   compare, sort, and store it; it silently means "whatever the writer assumed". Two naive timestamps from
   two providers can differ by hours while comparing equal.
2. **Seasonal zero-offset zones.** `Europe/London` has a UTC offset of zero in winter and +01:00 in
   summer. A rule of the form *"accept any timestamp whose current offset is zero"* accepts a London
   timestamp in January and rejects the same series in July — an inconsistency that would appear as a
   mysterious mid-year data gap rather than as an error.
3. **DST ambiguity.** During a "fall-back" hour a DST-aware zone repeats one wall-clock hour. Python
   disambiguates with the `fold` attribute, but `fold` does **not** participate in equality or hashing for
   `zoneinfo` zones: two values representing genuinely different instants can compare and hash as equal.
   Any dictionary-based or set-based alignment would silently merge them.

The alignment service (`align_intersection`) matches instants using aware-`datetime` equality and hashing.
That is exact and correct for fixed-offset timestamps and unsafe for DST-aware ones. The choice was
therefore either to make alignment defend against timezone pathologies, or to make the pathologies
unrepresentable in the canonical layer.

## Decision

**A canonical model may only store a timestamp whose timezone is *permanently* zero-offset, and the
system validates this without ever converting.**

Permanence is proven **structurally**, not by sampling:

| Timezone kind | Rule | Rationale |
|---|---|---|
| `datetime.timezone` | Accept **iff** its fixed offset is zero | Fixed-offset by construction — it cannot transition. Covers `timezone.utc` and `timezone(timedelta(0))`. |
| `zoneinfo.ZoneInfo` | Accept **iff** its IANA `key` is in a conservative whitelist: `UTC`, `Etc/UTC`, `Etc/GMT`, `GMT` | These keys are permanently zero-offset. Permanence cannot be derived from the `tzinfo` interface, so it is asserted by identity. |
| anything else (custom `tzinfo`, DST-aware zones, non-zero offsets, naive) | Reject | Permanence cannot be established, so the conservative answer is refusal. |

Two further properties are part of the decision, not incidental:

- **Validate, never convert.** `_timeutils` contains no `astimezone` call and mutates nothing. A
  non-conforming timestamp raises; it is not repaired.
- **Two distinct failure messages.** A naive timestamp reports `must be timezone-aware`; an aware but
  non-canonical one reports `must represent UTC`. The two are different bugs — a missing timezone in an
  adapter versus a wrong one — and they are diagnosed differently.

## Alternatives considered

**A. Accept any aware timestamp; normalize with `astimezone(timezone.utc)` on construction.**
Rejected. Normalization is silent repair, and the repository's principles forbid silently repairing bad
data (architecture doc §4.2, §10 uncertainty representation). It also destroys the evidence: a provider
adapter that attaches the wrong timezone produces timestamps that are *plausible but wrong*, and
converting them makes the defect invisible forever rather than failing at the boundary where it can be
found and fixed. Conversion additionally cannot rescue a naive timestamp — there is nothing to convert
*from* — so the hardest case remains unhandled.

**B. Accept any timestamp whose UTC offset is zero at the supplied instant.**
Rejected. This is hazard (2) above: it admits `Europe/London` for half the year. It also fails to exclude
hazard (3), because a DST-aware zone can be zero-offset at the sampled instant and still carry ambiguous
equality semantics.

**C. Probe the `tzinfo` for transitions (sample offsets across a year and require them constant).**
Rejected. Sampling can disprove permanence but never prove it: a zone that is stable across the sampled
window may still transition outside it, and political timezone changes are published continuously. The
check would also be slow, non-obvious, and dependent on which instants were sampled — a poor foundation
for a rule that must be identical everywhere.

**D. Store epoch integers instead of `datetime`.**
Rejected. Epoch integers are unambiguous but discard calendar semantics that later layers genuinely need
(monthly macro frequencies, trading-day calendars, human-readable diagnostics), and they push
timezone handling out of the type system into arithmetic that no test can see.

**E. Enforce the rule at the alignment service instead of in the models.**
Rejected. It would leave every *other* consumer — features, future RVE math, future persistence — free to
receive pathological timestamps, and it would place the same validation burden on each new service. The
invariant belongs where the data is constructed, once, so that holding a canonical object is itself the
proof.

## Consequences

**Gained**

- Instant equality is exact everywhere in the system. `align_intersection` can rely on plain aware-datetime
  equality and hashing with no timezone defences of its own — the DST `fold` hazard is structurally
  unrepresentable rather than merely documented.
- Timestamp defects fail loudly at the canonical boundary, with a message that distinguishes *missing*
  timezone from *wrong* timezone.
- The rule is one function called from every model, so it cannot drift between `Candle` and
  `ObservationSeries` — or from any model added later.
- No conversion means no hidden mutation: what a caller constructed is what the model stores.

**Accepted costs**

- **The burden moves to the boundary.** Provider adapters (all `deferred` today) must convert exchange
  local time, epoch values, and offset strings to UTC *before* constructing a canonical object. This is
  deliberate: normalization is an adapter responsibility (architecture doc §4.1, §5.2), and doing it there
  keeps the domain model honest.
- **The whitelist is a maintained list.** A legitimate permanent zero-offset zone outside
  `{UTC, Etc/UTC, Etc/GMT, GMT}` is rejected until added. This is intentionally conservative; extending it
  is a one-line change with a test, and over-acceptance is the more expensive error.
- **Fixed non-zero offsets are rejected even though they are unambiguous.** `+01:00` denotes a perfectly
  well-defined instant, and alignment would in fact intersect it correctly with the equivalent UTC value.
  It is refused anyway, so that the canonical layer has exactly **one** representation of an instant and
  no reader has to reason about whether two differently-offset timestamps are "the same". Uniformity is
  worth more here than permissiveness.
- Callers that legitimately think in local time must convert explicitly, at their own layer, and record
  that they did.

## Enforcement and verification

- `validate_utc_timestamp` is the single implementation; `Candle.__post_init__` and
  `ObservationSeries.__post_init__` both call it, and any new canonical model must.
- Tests assert acceptance of `timezone.utc`, `timezone(timedelta(0))`, and the whitelisted `ZoneInfo`
  keys; rejection of naive datetimes, fixed non-zero offsets, non-UTC `ZoneInfo` zones, and — the case
  that motivates the whole rule — a regional zero-offset zone (`Europe/London`) **in both seasons**, so
  the "zero offset today" shortcut cannot be reintroduced without a test failing.
- `tests/test_alignment.py` asserts that two distinct zero-offset representations of one instant
  (`timezone.utc` and `ZoneInfo("UTC")`) intersect, and that a non-UTC series cannot be constructed at all.

## Related

- Architecture doc §7.3 (alignment requirements — timezone normalization row) and §5.2 (adapters must not
  leak provider types into canonical models).
- `docs/ARCHITECTURE_REVIEW_2026-07-24.md` — the review that formalized this decision as an ADR, which
  also notes that `_timeutils` is currently a *private* module inside `fmis.data` while being a
  system-wide contract.
