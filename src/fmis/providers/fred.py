"""FRED public series downloads → canonical `ObservationSeries`.

Uses the Federal Reserve Bank of St. Louis's own CSV download endpoint —
``GET https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES_ID>`` — which is
the link the FRED website itself serves behind *"Download CSV"*. It needs **no
API key** and no authentication. Nothing in this module signs a request, reads a
credential, or touches a private endpoint.

    from fmis.providers.fred import fetch_observations
    series = fetch_observations("DGS10", unit="percent per annum", frequency="daily")

**This adapter produces observations, not candles**, and that is the reason it
exists rather than being a second candle source. A macroeconomic series has one
number per observation date: there is no open, high, low or volume to invent, and
`fmis.data.ObservationSeries` is the canonical model for exactly that shape. An
adapter that manufactured OHLC from a single print would be fabricating three
values out of one.

Payload shape — a two-column CSV whose header names the series:

    observation_date,DGS10
    1962-01-02,4.06
    ...
    2026-01-01,
    2026-01-02,4.19

Three provider conventions are translated here, and deliberately nowhere else:

  * **A missing observation is an empty field**, and in older exports a single
    ``.``. Both mean *the series has no value for this date* — a market holiday,
    or a date the source has not published yet. Such a row is **dropped**, never
    carried forward and never read as zero. A gap in a macro series is an absence,
    and `ObservationSeries` permits gaps precisely so one need not be filled.
  * **An observation is dated, not timestamped.** FRED states the observation
    *date*; it does not state the instant within that date at which the value was
    determined. The date is therefore mapped to **00:00:00 UTC of that date** —
    the *start* of the period the observation describes.
  * **Values arrive as decimal strings.** Parsing them is the adapter's job,
    because only the adapter knows they are plain decimal and never
    locale-formatted.

**Why the period start, and what it costs.** This follows
`fmis.marks.PriceReading` and `fmis.market_pulse.MarketReading.last_bar_open`
exactly, and for the identical reason: the latest instant this repository can
*honestly* name for a period is the instant that period began. The consequence is
stated rather than hidden — a reading's age is **overstated** by up to one
observation period and never understated, which is the safe direction for a
freshness figure.

The cost is stated too: for a daily series, an ``as_of`` filter that keeps an
observation dated *today* keeps a value that was not actually published until
later that day. That is a real limitation for historical replay and is documented
as such; it is harmless for the live orientation this build uses the adapter for,
where ``as_of`` is the wall clock. See ``OBSERVATION_DATING_LIMITATION``.

Timestamps are built as exact UTC instants, so the canonical time contract
(ADR-0001) holds by construction and is enforced again by `ObservationSeries`.
"""

from __future__ import annotations

import csv
import io
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Final, NamedTuple

from fmis.data.observation import ObservationSeries

__all__ = [
    "fetch_observations",
    "parse_observations_csv",
    "build_series_url",
    "urlopen_transport",
    "HttpResponse",
    "Transport",
    "FRED_BASE",
    "MISSING_MARKERS",
    "OBSERVATION_DATING_LIMITATION",
    "FredError",
    "FredRequestError",
    "FredTransportError",
    "FredAPIError",
    "FredResponseError",
]

FRED_BASE: Final[str] = "https://fred.stlouisfed.org"
_SERIES_PATH: Final[str] = "/graph/fredgraph.csv"

#: Field values that mean *no observation for this date*. The empty string is
#: what the current export emits; ``.`` is the long-standing FRED convention and
#: still appears in older exports and in the documented API. Both are dropped.
#:
#: **Neither is ever read as a number.** A holiday is not a print of zero, and a
#: date the source has not reached is not a market that did not move.
MISSING_MARKERS: Final[frozenset[str]] = frozenset({"", "."})

#: The limitation the period-start dating convention carries, stated once so a
#: consumer that replays history reads it rather than discovers it.
OBSERVATION_DATING_LIMITATION = (
    "A FRED observation carries a date, not an instant. It is timestamped at "
    "00:00:00 UTC of its observation date — the start of the period it "
    "describes — because that is the latest instant this repository can name "
    "for it honestly. A reading's age is therefore overstated by up to one "
    "observation period and never understated. The cost is that filtering by an "
    "as-of instant inside the observation's own date keeps a value that was not "
    "published until later that date; this build uses the adapter with an as-of "
    "of now, where that cannot mislead, and historical replay must account for "
    "it explicitly."
)

_EXPECTED_COLUMNS: Final[int] = 2
_DATE_COLUMN: Final[int] = 0
_VALUE_COLUMN: Final[int] = 1


# ------------------------------------------------------------------- errors ---


class FredError(Exception):
    """Base class for every failure originating in the FRED adapter."""


class FredRequestError(FredError, ValueError):
    """Arguments are invalid; raised before any network call is made."""


class FredTransportError(FredError):
    """The request could not be completed (DNS, connection, timeout, TLS)."""


class FredAPIError(FredError):
    """FRED answered with an error status.

    ``status`` is the HTTP status. FRED answers an unknown series id with an HTML
    404 page rather than a structured error body, so ``preview`` carries the
    first bytes of whatever arrived — enough for a reader to tell an unknown
    series from an outage without this module guessing which it was.
    """

    def __init__(self, message: str, *, status: int, preview: str | None = None) -> None:
        self.status = status
        self.preview = preview
        super().__init__(message)


class FredResponseError(FredError, ValueError):
    """The response was accepted by HTTP but is malformed, partial, or ambiguous."""


# ---------------------------------------------------------------- transport ---


class HttpResponse(NamedTuple):
    """A raw HTTP result: the status code and the undecoded body."""

    status: int
    body: bytes


#: A callable taking a URL and returning an `HttpResponse`.
#:
#: It must **not** raise for a non-2xx status — the adapter interprets the status
#: together with the body. It should raise `FredTransportError` when the request
#: could not be completed at all. Injecting one is how the test suite avoids the
#: network. Structurally identical to `fmis.providers.binance.Transport`, and
#: deliberately a separate type: two adapters sharing one transport alias would
#: make either one's error contract the other's problem.
Transport = Callable[[str], HttpResponse]


def urlopen_transport(url: str, *, timeout: float = 20.0) -> HttpResponse:
    """Default `Transport`, built on `urllib.request` — no third-party dependency.

    Returns the status and body for any HTTP response, including 4xx/5xx. Raises
    `FredTransportError` only when the request could not be completed at all.

    The timeout is longer than the Binance adapter's because a FRED series
    download is a whole history rather than a bounded page — ``DGS10`` is some
    sixteen thousand rows — and a truncated read is worse than a slow one.
    """
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResponse(status=response.status, body=response.read())
    except urllib.error.HTTPError as exc:  # a response, not a transport failure
        return HttpResponse(status=exc.code, body=exc.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FredTransportError(f"request to {url} failed: {exc}") from exc


# ------------------------------------------------------------------ request ---


def _require_series_id(series_id: object) -> str:
    """A FRED series id, validated exactly and never normalized.

    Upper-case alphanumeric, as every series this build reads is (``DGS10``,
    ``SP500``, ``VIXCLS``, ``DTWEXBGS``). Not upper-cased for the caller, for the
    reason `fmis.providers.binance` states for a symbol and
    `fmis.market_pulse.ProviderInstrument` restates: an identifier is not a
    search term, and quietly rewriting one hides a configuration typo until it
    becomes a wrong number.
    """
    if not isinstance(series_id, str):
        raise FredRequestError(
            f"series_id must be a str, got {type(series_id).__name__}"
        )
    if not series_id:
        raise FredRequestError("series_id cannot be empty")
    if not series_id.isalnum() or not series_id.isupper():
        raise FredRequestError(
            f"series_id {series_id!r} must be upper-case alphanumeric, e.g. "
            "'DGS10' (it is not upper-cased for you: a series id is an exact "
            "identifier)"
        )
    return series_id


def build_series_url(*, series_id: str, base_url: str = FRED_BASE) -> str:
    """Build the CSV download URL, validating the series id first.

    One parameter, emitted in a fixed order, so the URL is deterministic and
    directly comparable in a test.
    """
    series_id = _require_series_id(series_id)
    query = urllib.parse.urlencode([("id", series_id)])
    return f"{base_url.rstrip('/')}{_SERIES_PATH}?{query}"


# ------------------------------------------------------------------ parsing ---


def _parse_date(raw: str, *, row: int) -> datetime:
    """One ``YYYY-MM-DD`` observation date as UTC midnight — the period's start."""
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise FredResponseError(
            f"row {row}: observation date {raw!r} is not an ISO calendar date"
        ) from exc
    return parsed.replace(tzinfo=timezone.utc)


def _parse_value(raw: str, *, row: int) -> float:
    try:
        return float(raw)
    except ValueError as exc:
        raise FredResponseError(
            f"row {row}: value {raw!r} is neither a number nor a documented "
            f"missing marker ({', '.join(sorted(repr(m) for m in MISSING_MARKERS))})"
        ) from exc


def parse_observations_csv(
    body: bytes,
    *,
    series_id: str,
    unit: str,
    frequency: str,
) -> ObservationSeries:
    """Decode a FRED CSV body into a canonical `ObservationSeries`.

    Split out from `fetch_observations` so the whole parse is testable without a
    transport, and so the one place that interprets FRED's conventions is one
    function rather than a branch inside a fetch.

    Args:
        body: the raw CSV bytes exactly as the endpoint returned them.
        series_id: the id that was requested. The header's second column **must**
            match it — a body for a different series than the one asked for is
            refused rather than relabelled, because a value printed under the
            wrong name is the one error no downstream check can catch.
        unit: the canonical unit carried onto the series. Supplied by the caller
            rather than inferred: FRED's own units string is prose
            (*"Percent, Not Seasonally Adjusted"*) and parsing it would make this
            adapter the place unit semantics are decided, which is the benchmark
            registry's job.
        frequency: the canonical frequency label, supplied for the same reason.

    Raises:
        FredResponseError: the body is not decodable UTF-8, has no header, names
            a different series, has the wrong column count, or holds a row this
            module cannot read as either a number or a documented absence.
    """
    if not isinstance(body, (bytes, bytearray)):
        raise FredResponseError(
            f"body must be bytes, got {type(body).__name__}"
        )
    try:
        text = bytes(body).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FredResponseError(
            f"response body is not valid UTF-8: {exc}"
        ) from exc

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise FredResponseError(
            f"{series_id}: response body is empty; an empty download is a "
            "failed request, not a series with no observations"
        )

    header = rows[0]
    if len(header) != _EXPECTED_COLUMNS:
        raise FredResponseError(
            f"{series_id}: header names {len(header)} column(s) "
            f"({header!r}); this endpoint returns exactly "
            f"{_EXPECTED_COLUMNS} — a date and one series"
        )
    declared = header[_VALUE_COLUMN].strip()
    if declared != series_id:
        raise FredResponseError(
            f"asked for {series_id!r} and the body declares {declared!r}; a "
            "series is never relabelled to match the request, because a value "
            "printed under the wrong name is an error nothing downstream can catch"
        )

    timestamps: list[datetime] = []
    values: list[float] = []
    for index, row in enumerate(rows[1:], start=2):
        if not row:
            continue  # a trailing blank line is formatting, not an observation
        if len(row) != _EXPECTED_COLUMNS:
            raise FredResponseError(
                f"{series_id} row {index}: expected {_EXPECTED_COLUMNS} fields, "
                f"got {len(row)} ({row!r})"
            )
        raw_value = row[_VALUE_COLUMN].strip()
        if raw_value in MISSING_MARKERS:
            # A holiday, or a date the source has not published. Dropped, never
            # carried forward and never read as zero.
            continue
        timestamps.append(_parse_date(row[_DATE_COLUMN].strip(), row=index))
        values.append(_parse_value(raw_value, row=index))

    # The canonical model owns every invariant that matters — UTC, strictly
    # increasing, finite. A body whose dates repeat or run backwards is refused
    # there rather than sorted here, exactly as the candle path refuses one.
    return ObservationSeries(
        series_id=series_id,
        unit=unit,
        frequency=frequency,
        timestamps=tuple(timestamps),
        values=tuple(values),
    )


# ------------------------------------------------------------------- fetch ----


def fetch_observations(
    series_id: str,
    *,
    unit: str,
    frequency: str,
    transport: Transport | None = None,
    base_url: str = FRED_BASE,
) -> ObservationSeries:
    """Fetch one public FRED series and return a canonical `ObservationSeries`.

    ``series_id`` is an exact FRED id (``"DGS10"``). ``unit`` and ``frequency``
    are the canonical labels carried onto the result; see `parse_observations_csv`
    for why they are supplied rather than inferred.

    ``transport`` is the injection point: `urlopen_transport` is the default, and
    supplying one makes a call fully deterministic and network-free — the same
    argument `fmis.providers.binance.fetch_klines` takes, for the same reason.

    **The whole available history is returned.** This endpoint takes no range
    parameter and no row limit; windowing is the consumer's job, and every
    consumer in this repository already selects a window from the end. Returning
    a truncated series here would put window selection in two places.

    Raises `FredRequestError` (bad arguments, before any I/O), `FredTransportError`
    (request could not be completed), `FredAPIError` (a non-2xx status),
    `FredResponseError` (malformed or mislabelled body), or `ValueError` from
    `ObservationSeries` when the decoded observations violate a canonical
    invariant. A provider failure is never turned into an empty series; an empty
    series means FRED genuinely returned no observations.
    """
    url = build_series_url(series_id=series_id, base_url=base_url)

    send = urlopen_transport if transport is None else transport
    response = send(url)
    if not isinstance(response, HttpResponse):
        raise FredResponseError(
            f"transport must return an HttpResponse, got {type(response).__name__}"
        )

    if not 200 <= response.status < 300:
        # FRED answers an unknown series with an HTML 404 page. The preview is
        # carried verbatim rather than paraphrased, so the reason a reader sees
        # is the reason the provider gave.
        preview = response.body[:200].decode("utf-8", errors="replace")
        raise FredAPIError(
            f"HTTP {response.status} from FRED for {series_id}: {preview!r}",
            status=response.status,
            preview=preview,
        )

    return parse_observations_csv(
        response.body, series_id=series_id, unit=unit, frequency=frequency
    )
