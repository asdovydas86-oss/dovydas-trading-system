"""Shared fixtures for Milestone BU — the macro & cross-asset context.

Every helper here builds data **in the shape the real source returns it**, so a
test exercises the real adapter, the real decoder and the real canonical
boundary rather than a mock of them. A fake that returned an
`ObservationSeries` directly would prove the engines work and prove nothing
about the parsing that stands between them and a CSV.

Mirrors `tests.market_pulse_helpers`, which does the same job for candles.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fmis.market_pulse import (
    Benchmark,
    FreshnessPolicy,
    MarketCategory,
    ProviderInstrument,
    QuantityKind,
    TradingSchedule,
)
from fmis.providers.fred import HttpResponse

#: The epoch every helper counts observation dates from. A Monday, so a run of
#: consecutive business days starts at the beginning of a week.
EPOCH = datetime(2026, 1, 5, tzinfo=timezone.utc)

DAILY_FRESHNESS = FreshnessPolicy(
    publication_period=timedelta(days=1),
    tolerance=timedelta(days=4),
    basis="a test policy standing in for a business-day series",
)


def day(offset: int) -> datetime:
    """The observation instant ``offset`` calendar days after the epoch."""
    return EPOCH + timedelta(days=offset)


def business_days(count: int, *, start: int = 0) -> list[datetime]:
    """``count`` consecutive weekday instants, skipping Saturdays and Sundays.

    Weekends are skipped rather than ignored because the gap they leave is the
    whole reason macro alignment is interesting: a market trading seven days a
    week and one trading five do not observe the same dates, and a fixture with
    no weekends would never exercise that.
    """
    found: list[datetime] = []
    offset = start
    while len(found) < count:
        moment = day(offset)
        if moment.weekday() < 5:
            found.append(moment)
        offset += 1
    return found


def fred_csv(
    series_id: str, rows: list[tuple[datetime, float | None]]
) -> bytes:
    """A FRED CSV body. ``None`` becomes an empty field — the source's own
    spelling of *no observation for this date*."""
    lines = [f"observation_date,{series_id}"]
    for moment, value in rows:
        rendered = "" if value is None else f"{value}"
        lines.append(f"{moment.date().isoformat()},{rendered}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def linear_series(
    series_id: str,
    *,
    base: float = 100.0,
    step: float = 1.0,
    count: int = 40,
    start: int = 0,
    weekdays_only: bool = True,
) -> bytes:
    """A CSV whose value rises by ``step`` each observation. Exactly reconstructable."""
    moments = (
        business_days(count, start=start)
        if weekdays_only
        else [day(start + index) for index in range(count)]
    )
    return fred_csv(
        series_id,
        [(moment, base + step * index) for index, moment in enumerate(moments)],
    )


def business_days_ending(count: int, end: datetime) -> list[datetime]:
    """``count`` weekday instants ending on or before ``end``, oldest first.

    Anchored to a supplied instant rather than to `EPOCH`, so a fixture can put
    its observations next to whatever ``as_of`` the test describes. A macro
    series whose newest observation is seven months before the instant under
    test is legitimately behind schedule, and a test meaning to exercise
    something else would be measuring that instead.
    """
    found: list[datetime] = []
    moment = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
    while len(found) < count:
        if moment.weekday() < 5:
            found.append(moment)
        moment -= timedelta(days=1)
    return list(reversed(found))


def series_ending(
    series_id: str,
    end: datetime,
    *,
    base: float = 100.0,
    step: float = 1.0,
    count: int = 60,
) -> bytes:
    """A rising CSV whose newest observation lands on or before ``end``."""
    return fred_csv(
        series_id,
        [
            (moment, base + step * index)
            for index, moment in enumerate(business_days_ending(count, end))
        ],
    )


def ok_csv(body: bytes) -> HttpResponse:
    return HttpResponse(status=200, body=body)


def not_found() -> HttpResponse:
    """FRED's own answer to an unknown series: an HTML 404, not a JSON error."""
    return HttpResponse(
        status=404,
        body=b"<!DOCTYPE html><html><body>Page not found</body></html>",
    )


def fred_transport_for(bodies: dict[str, bytes | HttpResponse]):
    """A `Transport` answering by series id, recording every id requested.

    Raises `KeyError` for an id it was not given, which is deliberate: a test
    that fetched a series it did not declare should fail loudly rather than
    receive an empty answer that looks like a market with no history.
    """

    def send(url: str) -> HttpResponse:
        series_id = url.split("id=")[1].split("&")[0]
        send.calls.append(series_id)
        answer = bodies[series_id]
        return answer if isinstance(answer, HttpResponse) else ok_csv(answer)

    send.calls = []
    return send


def macro_benchmark(
    benchmark_id: str = "SPX",
    *,
    series_id: str = "SP500",
    display_name: str | None = None,
    category: MarketCategory = MarketCategory.EQUITY_INDEX,
    quote_unit: str = "index points",
    quantity_kind: QuantityKind = QuantityKind.PRICE_LIKE,
    interval: str = "1d",
    freshness: FreshnessPolicy | None = DAILY_FRESHNESS,
) -> Benchmark:
    """One session-bound daily macro benchmark on the macro provider."""
    return Benchmark(
        benchmark_id=benchmark_id,
        display_name=display_name or f"{benchmark_id} market",
        category=category,
        schedule=TradingSchedule.SESSION_BOUND,
        quote_unit=quote_unit,
        instrument=ProviderInstrument(
            provider="fred", symbol=series_id, interval=interval
        ),
        quantity_kind=quantity_kind,
        freshness_policy=freshness,
    )


def yield_benchmark(
    benchmark_id: str = "US10Y", *, series_id: str = "DGS10"
) -> Benchmark:
    """One Treasury yield — rate-like, quoted in percent per annum."""
    return macro_benchmark(
        benchmark_id,
        series_id=series_id,
        category=MarketCategory.RATES,
        quote_unit="percent per annum",
        quantity_kind=QuantityKind.RATE_LIKE,
    )
