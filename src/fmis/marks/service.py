"""Candles in, a price snapshot out. Pure, and the whole of the policy.

Two functions and one sentence of policy. `read_price` turns one `CandleSeries`
into one `PriceReading`; `build_price_snapshot` turns many into one frozen
bundle, folding every symbol that could not be read into `unavailable` with its
reason attached.

**The forming candle is excluded unconditionally, not by default.** There is no
flag that includes it. `fmis.pipeline.market_analysis` states the reason for the
identical rule one layer over: *"a snapshot computed over a forming bar is not
reproducible"*. A mark is the input to a money figure, so the consequence there
is a portfolio whose value changes when nothing traded.

**A series with no closed candle is a reason, never a raise, at the snapshot
level.** `read_price` raises — one market, one caller, a precise failure — and
`build_price_snapshot` catches exactly that and files it, because one unreadable
market must never cost a portfolio every other price it already had.

**A price from after the instant being described is refused the same way.**
Asking what the portfolio was worth last Tuesday fetches candles that closed
since; a mark from the future of the moment it is marking is not a mark for that
moment, and this build stores no price history to read the right one from. That
market is reported unpriced with the dates in the reason, and every other market
in the snapshot is unaffected. `PriceSnapshot` rejects the same condition at
construction, which is defence in depth rather than duplication: the type refuses
to *exist* in that state, and this function is what stops one market putting it
there.

**Nothing here fetches.** The caller supplies series and supplies the reasons for
the ones it could not fetch, which is what keeps every provider name, every
transport error type and every retry policy on the far side of this package.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime

from fmis.data import CandleSeries

from fmis.marks.models import (
    PriceBasis,
    PriceReading,
    PriceSnapshot,
    PriceUnavailable,
    PriceUnreadableError,
)
# The canonical-time check, reused rather than re-stated. A sibling module's
# private helper is a smaller coupling than two spellings of one time contract
# inside one package.
from fmis.marks.models import _utc as _require_instant

__all__ = [
    "MARK_BASIS_NOTE",
    "read_price",
    "build_price_snapshot",
    "empty_price_snapshot",
]

#: The sentence every surface prints beside a marked figure. Written once so a
#: page cannot show a valuation under a shorter description that omits how the
#: price was chosen or how old it can be.
MARK_BASIS_NOTE = (
    "Every price is the close of the last closed candle on the stated interval. "
    "A forming bar is never read, so the same history always yields the same "
    "price. A price is timestamped with the instant its bar opened, because the "
    "canonical candle carries no close time — so a mark's age is overstated by "
    "up to one interval and is never understated."
)


def read_price(
    series: CandleSeries, *, source: str, basis: PriceBasis | None = None
) -> PriceReading:
    """The last closed candle's close, as a reading with its provenance.

    Args:
        series: candles for one symbol on one timeframe, forming bar included —
            it is dropped here rather than by the caller, so the exclusion has
            one implementation.
        source: an opaque label for where the candles came from. Carried onto
            the reading and never interpreted.
        basis: the selection rule. Only `LAST_CLOSED_CANDLE_CLOSE` exists, and
            it is the default; the parameter is here so that adding a second
            member later is an addition rather than a change of meaning.

    Raises:
        TypeError: ``series`` is not a `CandleSeries`.
        PriceUnreadableError: the series holds no closed candle. A window of
            forming bars only, or an empty response, is not a price of zero.
    """
    if not isinstance(series, CandleSeries):
        raise TypeError(
            f"series must be a CandleSeries, got {type(series).__name__}"
        )
    chosen = PriceBasis.LAST_CLOSED_CANDLE_CLOSE if basis is None else basis
    if not isinstance(chosen, PriceBasis):
        raise TypeError(f"basis must be a PriceBasis, got {type(chosen).__name__}")
    closed = series.closed()
    if not closed.candles:
        raise PriceUnreadableError(
            f"{series.symbol} {series.timeframe}: no closed candle in a window of "
            f"{len(series.candles)} candle(s); a forming bar is never read, and "
            "an unread market has no price rather than a price of zero"
        )
    last = closed.candles[-1]
    return PriceReading(
        symbol=last.symbol,
        interval=last.timeframe,
        price=last.close,
        observed_at=last.timestamp,
        basis=chosen,
        source=source,
        closed_count=len(closed.candles),
    )


def build_price_snapshot(
    series: Sequence[CandleSeries] | Iterable[CandleSeries],
    *,
    taken_at: datetime,
    source: str,
    unreadable: Mapping[str, str] | None = None,
    basis: PriceBasis | None = None,
) -> PriceSnapshot:
    """One frozen snapshot from many series, with every failure named.

    Args:
        series: one `CandleSeries` per market that was fetched. A series whose
            window holds no closed candle becomes an `unavailable` entry with
            that reason rather than being dropped.
        taken_at: the instant the snapshot describes. An argument, because a
            package that read a clock could not be replayed.
        source: the label carried onto every reading and onto the snapshot.
        unreadable: symbols that could not be fetched at all, mapped to the
            reason. The caller owns this because only the caller knows what its
            provider's failures mean.
        basis: the selection rule, forwarded to `read_price`.

    Raises:
        TypeError, ValueError: an argument is of the wrong type or shape, or two
            sources disagree about one symbol.
    """
    moment = _require_instant(taken_at, "taken_at")
    chosen = PriceBasis.LAST_CLOSED_CANDLE_CLOSE if basis is None else basis
    readings: list[PriceReading] = []
    failures: list[PriceUnavailable] = []
    for one in series:
        try:
            reading = read_price(one, source=source, basis=chosen)
        except PriceUnreadableError as error:
            failures.append(PriceUnavailable(symbol=one.symbol, reason=str(error)))
            continue
        if reading.observed_at > moment:
            # A price from after the instant being described is not a price for
            # that instant. This happens for real whenever a past `as_of` is
            # supplied — *"what was my portfolio worth on Tuesday"* fetches
            # today's candles — and it must be a reason on one market rather
            # than a failure of the whole reading, which is what refusing it in
            # `PriceSnapshot.__post_init__` alone would produce.
            failures.append(
                PriceUnavailable(
                    symbol=reading.symbol,
                    reason=(
                        f"{reading.symbol}: the latest closed "
                        f"{reading.interval} bar opened "
                        f"{reading.observed_at.isoformat()}, after the instant "
                        f"this snapshot describes ({moment.isoformat()}); a "
                        "price from after a moment is not that moment's price, "
                        "and this build stores no historical prices to read one "
                        "from"
                    ),
                )
            )
            continue
        readings.append(reading)
    stated = {} if unreadable is None else dict(unreadable)
    if not isinstance(stated, dict):  # pragma: no cover - dict() already raised
        raise TypeError("unreadable must be a mapping of symbol to reason")
    for symbol, reason in stated.items():
        failures.append(PriceUnavailable(symbol=symbol, reason=reason))
    return PriceSnapshot(
        taken_at=moment,
        source=source,
        basis=chosen,
        readings=tuple(readings),
        unavailable=tuple(failures),
    )


def empty_price_snapshot(*, taken_at: datetime, source: str) -> PriceSnapshot:
    """A snapshot that priced nothing, whose `source` says why it did not try.

    Distinct from a snapshot whose every fetch failed: this one asked for
    nothing, and `unavailable` is empty rather than full. A page that could not
    tell the two apart would report *"no prices available"* both when the
    network was down and when the owner passed `--no-marks`, and only one of
    those is a problem. ``source`` is therefore a sentence — *"no price source
    was consulted"* — rather than a provider name.
    """
    return PriceSnapshot(
        taken_at=taken_at,
        source=source,
        basis=PriceBasis.LAST_CLOSED_CANDLE_CLOSE,
        readings=(),
        unavailable=(),
    )
