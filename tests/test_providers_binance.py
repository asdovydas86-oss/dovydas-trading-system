"""Tests for the Binance provider adapter (fmis.providers.binance).

Every test is deterministic and network-free: the HTTP transport and the clock
are injected, so nothing here depends on a live endpoint or on wall-clock time.

Anchors used throughout (BTCUSDT 4h):

    open time  1704067200000 ms = 2024-01-01T00:00:00Z
    close time 1704081599999 ms = open + 4h - 1ms
"""

from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import fmis.providers.binance as binance
from fmis.data import CandleSeries
from fmis.ingest import CANDLE_FIELDS, IngestError, RecordDecodeError
from fmis.providers.binance import (
    BINANCE_API_BASE,
    KLINE_INTERVALS,
    MAX_LIMIT,
    BinanceAPIError,
    BinanceError,
    BinanceRequestError,
    BinanceResponseError,
    BinanceTransportError,
    HttpResponse,
    build_klines_url,
    fetch_klines,
    map_kline,
)

_OPEN_MS = 1_704_067_200_000  # 2024-01-01T00:00:00Z
_FOUR_HOURS_MS = 4 * 60 * 60 * 1000
_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)

# A clock long after the fixture window: every fixture candle is closed.
LATER = datetime(2024, 6, 1, tzinfo=timezone.utc)


def kline(i: int = 0, **overrides: object) -> list[object]:
    """One realistic Binance kline array (12 positional fields)."""
    open_ms = _OPEN_MS + i * _FOUR_HOURS_MS
    row: list[object] = [
        open_ms,                 # 0 open time
        "42000.10000000",        # 1 open
        "42500.00000000",        # 2 high
        "41900.00000000",        # 3 low
        "42250.50000000",        # 4 close
        "1234.56780000",         # 5 volume
        open_ms + _FOUR_HOURS_MS - 1,  # 6 close time
        "52000000.00000000",     # 7 quote asset volume
        45678,                   # 8 number of trades
        "600.00000000",          # 9 taker buy base volume
        "25000000.00000000",     # 10 taker buy quote volume
        "0",                     # 11 unused
    ]
    for key, value in overrides.items():
        row[int(key.removeprefix("f"))] = value
    return row


def transport_returning(payload: object, *, status: int = 200) -> object:
    """A Transport that answers every URL with one canned JSON payload."""
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def _transport(url: str) -> HttpResponse:
        _transport.calls.append(url)  # type: ignore[attr-defined]
        return HttpResponse(status=status, body=body)

    _transport.calls = []  # type: ignore[attr-defined]
    return _transport


def fixed_clock(moment: datetime = LATER):
    return lambda: moment


# ============================ successful mapping =============================


def test_fetch_returns_canonical_series() -> None:
    series = fetch_klines(
        "BTCUSDT", "4h",
        transport=transport_returning([kline(0), kline(1)]),
        clock=fixed_clock(),
    )
    assert isinstance(series, CandleSeries)
    assert (series.symbol, series.timeframe) == ("BTCUSDT", "4h")
    assert len(series.candles) == 2


def test_string_prices_are_parsed_to_floats() -> None:
    series = fetch_klines(
        "BTCUSDT", "4h", transport=transport_returning([kline()]), clock=fixed_clock()
    )
    candle = series.candles[0]
    assert candle.open == pytest.approx(42000.10)
    assert candle.high == pytest.approx(42500.00)
    assert candle.low == pytest.approx(41900.00)
    assert candle.close == pytest.approx(42250.50)
    assert candle.volume == pytest.approx(1234.5678)
    for field in ("open", "high", "low", "close", "volume"):
        assert isinstance(getattr(candle, field), float)


def test_map_kline_produces_exactly_the_canonical_record_shape() -> None:
    record = map_kline(kline(), symbol="BTCUSDT", interval="4h", now_ms=0)
    assert set(record) == set(CANDLE_FIELDS)


def test_interval_is_used_verbatim_as_timeframe() -> None:
    # The provider-native label is not rewritten into another casing.
    series = fetch_klines(
        "BTCUSDT", "1d", transport=transport_returning([kline()]), clock=fixed_clock()
    )
    assert series.timeframe == "1d"


def test_symbol_comes_from_the_request_not_the_payload() -> None:
    # Binance klines do not echo the symbol; it must come from the request.
    series = fetch_klines(
        "ETHUSDT", "4h", transport=transport_returning([kline()]), clock=fixed_clock()
    )
    assert series.symbol == "ETHUSDT"
    assert all(c.symbol == "ETHUSDT" for c in series.candles)


def test_extra_trailing_fields_are_tolerated() -> None:
    row = kline() + ["a future additive field"]
    record = map_kline(row, symbol="BTCUSDT", interval="4h", now_ms=0)
    assert record["close"] == pytest.approx(42250.50)


# ============================ timestamps =====================================


def test_open_time_becomes_exact_utc_instant() -> None:
    series = fetch_klines(
        "BTCUSDT", "4h", transport=transport_returning([kline()]), clock=fixed_clock()
    )
    assert series.candles[0].timestamp == _BASE


def test_timestamps_are_canonical_utc() -> None:
    ts = fetch_klines(
        "BTCUSDT", "4h", transport=transport_returning([kline()]), clock=fixed_clock()
    ).candles[0].timestamp
    assert ts.tzinfo is timezone.utc
    assert ts.utcoffset() == timedelta(0)


def test_millisecond_precision_is_preserved_exactly() -> None:
    row = kline(**{"f0": _OPEN_MS + 123, "f6": _OPEN_MS + _FOUR_HOURS_MS})
    record = map_kline(row, symbol="BTCUSDT", interval="4h", now_ms=0)
    assert record["timestamp"] == _BASE + timedelta(milliseconds=123)


def test_series_timestamps_are_strictly_increasing() -> None:
    series = fetch_klines(
        "BTCUSDT", "4h",
        transport=transport_returning([kline(i) for i in range(5)]),
        clock=fixed_clock(),
    )
    stamps = [c.timestamp for c in series.candles]
    assert stamps == sorted(stamps) and len(set(stamps)) == 5


def test_out_of_order_klines_are_rejected_not_sorted() -> None:
    with pytest.raises(IngestError, match="strictly increasing"):
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning([kline(2), kline(1), kline(0)]),
            clock=fixed_clock(),
        )


# ============================ forming-candle handling ========================


def test_closed_candle_when_close_time_has_passed() -> None:
    series = fetch_klines(
        "BTCUSDT", "4h", transport=transport_returning([kline()]), clock=fixed_clock()
    )
    assert series.candles[0].is_closed is True


def test_forming_candle_when_close_time_is_in_the_future() -> None:
    # Clock sits one hour into the 4h bar: it has not closed yet.
    mid_bar = _BASE + timedelta(hours=1)
    series = fetch_klines(
        "BTCUSDT", "4h",
        transport=transport_returning([kline()]),
        clock=fixed_clock(mid_bar),
    )
    assert series.candles[0].is_closed is False


def test_only_the_trailing_candle_is_forming() -> None:
    mid_last = _BASE + timedelta(hours=4, minutes=30)
    series = fetch_klines(
        "BTCUSDT", "4h",
        transport=transport_returning([kline(0), kline(1)]),
        clock=fixed_clock(mid_last),
    )
    assert [c.is_closed for c in series.candles] == [True, False]
    assert len(series.closed().candles) == 1  # dropping it stays the caller's choice


def test_forming_candle_is_not_dropped_by_the_adapter() -> None:
    series = fetch_klines(
        "BTCUSDT", "4h",
        transport=transport_returning([kline(0), kline(1)]),
        clock=fixed_clock(_BASE + timedelta(hours=5)),
    )
    assert len(series.candles) == 2


def test_close_time_boundary_is_exclusive() -> None:
    # now == close_time: the final millisecond has not elapsed, so still forming.
    close_ms = _OPEN_MS + _FOUR_HOURS_MS - 1
    at_close = datetime.fromtimestamp(close_ms / 1000, tz=timezone.utc)
    record = map_kline(
        kline(), symbol="BTCUSDT", interval="4h",
        now_ms=round(at_close.timestamp() * 1000),
    )
    assert record["is_closed"] is False

    record_after = map_kline(
        kline(), symbol="BTCUSDT", interval="4h", now_ms=close_ms + 1
    )
    assert record_after["is_closed"] is True


# ============================ symbol / interval validation ===================


@pytest.mark.parametrize("symbol", ["btcusdt", "BtcUsdt", "BTC-USDT", "BTC/USDT", ""])
def test_invalid_symbol_rejected(symbol: str) -> None:
    with pytest.raises(BinanceRequestError):
        build_klines_url(symbol=symbol, interval="4h")


def test_symbol_is_not_silently_uppercased() -> None:
    with pytest.raises(BinanceRequestError, match="upper-case"):
        build_klines_url(symbol="btcusdt", interval="4h")


def test_non_str_symbol_rejected() -> None:
    with pytest.raises(BinanceRequestError, match="must be a str"):
        build_klines_url(symbol=123, interval="4h")  # type: ignore[arg-type]


@pytest.mark.parametrize("interval", ["4H", "4hours", "7m", "", "1y"])
def test_invalid_interval_rejected(interval: str) -> None:
    with pytest.raises(BinanceRequestError, match="unsupported interval"):
        build_klines_url(symbol="BTCUSDT", interval=interval)


@pytest.mark.parametrize("interval", sorted(KLINE_INTERVALS))
def test_every_documented_interval_is_accepted(interval: str) -> None:
    assert f"interval={interval}" in build_klines_url(
        symbol="BTCUSDT", interval=interval
    )


def test_validation_happens_before_any_transport_call() -> None:
    sent = transport_returning([])
    with pytest.raises(BinanceRequestError):
        fetch_klines("btcusdt", "4h", transport=sent, clock=fixed_clock())
    assert sent.calls == []  # type: ignore[attr-defined]


# ============================ URL construction / limits ======================


def test_url_minimal() -> None:
    assert build_klines_url(symbol="BTCUSDT", interval="4h") == (
        f"{BINANCE_API_BASE}/api/v3/klines?symbol=BTCUSDT&interval=4h"
    )


def test_url_includes_all_parameters_in_fixed_order() -> None:
    url = build_klines_url(
        symbol="BTCUSDT",
        interval="4h",
        start_time=_BASE,
        end_time=_BASE + timedelta(days=1),
        limit=500,
    )
    assert url == (
        f"{BINANCE_API_BASE}/api/v3/klines?symbol=BTCUSDT&interval=4h"
        f"&startTime={_OPEN_MS}&endTime={_OPEN_MS + 86_400_000}&limit=500"
    )


def test_omitted_parameters_are_absent_not_empty() -> None:
    url = build_klines_url(symbol="BTCUSDT", interval="4h")
    for absent in ("startTime", "endTime", "limit"):
        assert absent not in url


@pytest.mark.parametrize("limit", [0, -1, MAX_LIMIT + 1, 5000])
def test_limit_outside_bounds_rejected(limit: int) -> None:
    with pytest.raises(BinanceRequestError, match="limit must be between"):
        build_klines_url(symbol="BTCUSDT", interval="4h", limit=limit)


@pytest.mark.parametrize("limit", [1, 500, MAX_LIMIT])
def test_limit_boundaries_accepted(limit: int) -> None:
    assert f"limit={limit}" in build_klines_url(
        symbol="BTCUSDT", interval="4h", limit=limit
    )


def test_limit_must_be_int_not_bool() -> None:
    with pytest.raises(BinanceRequestError, match="must be an int"):
        build_klines_url(symbol="BTCUSDT", interval="4h", limit=True)


def test_naive_start_time_rejected() -> None:
    with pytest.raises(BinanceRequestError, match="timezone-aware"):
        build_klines_url(
            symbol="BTCUSDT", interval="4h", start_time=datetime(2024, 1, 1)
        )


def test_non_utc_aware_start_time_converts_exactly() -> None:
    # Any aware zone denotes an unambiguous instant; +02:00 at 02:00 is 00:00Z.
    aware = datetime(2024, 1, 1, 2, tzinfo=timezone(timedelta(hours=2)))
    assert f"startTime={_OPEN_MS}" in build_klines_url(
        symbol="BTCUSDT", interval="4h", start_time=aware
    )


def test_start_after_end_rejected() -> None:
    with pytest.raises(BinanceRequestError, match="must not be after"):
        build_klines_url(
            symbol="BTCUSDT",
            interval="4h",
            start_time=_BASE + timedelta(days=1),
            end_time=_BASE,
        )


def test_base_url_override_is_honoured() -> None:
    url = build_klines_url(
        symbol="BTCUSDT", interval="4h", base_url="https://testnet.example/"
    )
    assert url.startswith("https://testnet.example/api/v3/klines?")


def test_no_pagination_is_attempted() -> None:
    sent = transport_returning([kline(i) for i in range(3)])
    fetch_klines("BTCUSDT", "4h", limit=3, transport=sent, clock=fixed_clock())
    assert len(sent.calls) == 1  # type: ignore[attr-defined]


# ============================ empty responses ================================


def test_empty_payload_yields_identified_empty_series() -> None:
    series = fetch_klines(
        "BTCUSDT", "4h", transport=transport_returning([]), clock=fixed_clock()
    )
    assert series.candles == ()
    assert (series.symbol, series.timeframe) == ("BTCUSDT", "4h")


# ============================ HTTP + provider errors =========================


def test_provider_error_payload_raises_with_code_and_message() -> None:
    payload = {"code": -1121, "msg": "Invalid symbol."}
    with pytest.raises(BinanceAPIError) as ei:
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning(payload, status=400),
            clock=fixed_clock(),
        )
    assert ei.value.status == 400
    assert ei.value.code == -1121
    assert ei.value.message == "Invalid symbol."


def test_error_payload_with_200_status_still_raises() -> None:
    # A provider error must never be mistaken for data because the status was 200.
    with pytest.raises(BinanceAPIError):
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning({"code": -1003, "msg": "Too many requests."}),
            clock=fixed_clock(),
        )


@pytest.mark.parametrize("status", [400, 401, 418, 429, 500, 503])
def test_non_2xx_without_error_payload_raises(status: int) -> None:
    with pytest.raises(BinanceAPIError) as ei:
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning([], status=status),
            clock=fixed_clock(),
        )
    assert ei.value.status == status


def test_http_error_is_not_coerced_into_empty_series() -> None:
    with pytest.raises(BinanceAPIError):
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning([], status=429),
            clock=fixed_clock(),
        )


def test_transport_failure_propagates() -> None:
    def failing(url: str) -> HttpResponse:
        raise BinanceTransportError("connection refused")

    with pytest.raises(BinanceTransportError):
        fetch_klines("BTCUSDT", "4h", transport=failing, clock=fixed_clock())


def test_non_json_body_on_success_status_raises_response_error() -> None:
    with pytest.raises(BinanceResponseError, match="not valid JSON"):
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning(b"<html>maintenance</html>"),
            clock=fixed_clock(),
        )


def test_non_json_body_on_error_status_raises_api_error() -> None:
    with pytest.raises(BinanceAPIError, match="non-JSON body"):
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning(b"<html>bad gateway</html>", status=502),
            clock=fixed_clock(),
        )


def test_non_array_payload_rejected() -> None:
    with pytest.raises(BinanceResponseError, match="expected a JSON array"):
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning({"unexpected": "object"}),
            clock=fixed_clock(),
        )


def test_transport_returning_wrong_type_rejected() -> None:
    with pytest.raises(BinanceResponseError, match="must return an HttpResponse"):
        fetch_klines(
            "BTCUSDT", "4h", transport=lambda url: b"[]", clock=fixed_clock()
        )


def test_clock_must_return_aware_datetime() -> None:
    with pytest.raises(BinanceRequestError, match="timezone-aware"):
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning([kline()]),
            clock=lambda: datetime(2024, 6, 1),
        )


# ============================ malformed provider records =====================


def test_short_kline_array_rejected() -> None:
    with pytest.raises(BinanceResponseError, match="at least 12 fields"):
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning([kline()[:6]]),
            clock=fixed_clock(),
        )


def test_non_array_kline_rejected() -> None:
    with pytest.raises(BinanceResponseError, match="expected an array"):
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning([{"open": 1}]),
            clock=fixed_clock(),
        )


def test_string_kline_rejected() -> None:
    with pytest.raises(BinanceResponseError, match="expected an array"):
        map_kline("not-a-kline", symbol="BTCUSDT", interval="4h", now_ms=0)


def test_unparseable_price_rejected() -> None:
    with pytest.raises(BinanceResponseError, match="not a valid number"):
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning([kline(**{"f4": "not-a-number"})]),
            clock=fixed_clock(),
        )


def test_null_price_rejected() -> None:
    with pytest.raises(BinanceResponseError, match="must be a string or number"):
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning([kline(**{"f2": None})]),
            clock=fixed_clock(),
        )


def test_non_integer_open_time_rejected() -> None:
    with pytest.raises(BinanceResponseError, match="integer millisecond epoch"):
        fetch_klines(
            "BTCUSDT", "4h",
            transport=transport_returning([kline(**{"f0": "1704067200000"})]),
            clock=fixed_clock(),
        )


def test_close_time_before_open_time_rejected() -> None:
    with pytest.raises(BinanceResponseError, match="precedes"):
        map_kline(
            kline(**{"f6": _OPEN_MS - 1}), symbol="BTCUSDT", interval="4h", now_ms=0
        )


def test_malformed_record_reports_its_index() -> None:
    payload = [kline(0), kline(1), kline(2, **{"f4": "oops"})]
    with pytest.raises(BinanceResponseError, match="kline 2"):
        fetch_klines(
            "BTCUSDT", "4h", transport=transport_returning(payload), clock=fixed_clock()
        )


def test_canonical_invariant_violation_surfaces_as_ingest_error() -> None:
    # high below close is a domain-rule violation, owned by Candle, not the adapter.
    payload = [kline(**{"f2": "100.0"})]
    with pytest.raises(RecordDecodeError, match="high must be"):
        fetch_klines(
            "BTCUSDT", "4h", transport=transport_returning(payload), clock=fixed_clock()
        )


def test_negative_price_surfaces_as_ingest_error() -> None:
    payload = [kline(**{"f3": "-1.0", "f5": "-5.0"})]
    with pytest.raises(IngestError):
        fetch_klines(
            "BTCUSDT", "4h", transport=transport_returning(payload), clock=fixed_clock()
        )


# ============================ purity / non-mutation ==========================


def test_provider_payload_is_not_mutated() -> None:
    payload = [kline(0), kline(1)]
    before = json.dumps(payload)
    fetch_klines(
        "BTCUSDT", "4h", transport=transport_returning(payload), clock=fixed_clock()
    )
    assert json.dumps(payload) == before


def test_map_kline_does_not_mutate_its_input() -> None:
    row = kline()
    before = list(row)
    map_kline(row, symbol="BTCUSDT", interval="4h", now_ms=0)
    assert row == before


def test_repeated_fetches_are_deterministic() -> None:
    payload = [kline(0), kline(1)]
    first = fetch_klines(
        "BTCUSDT", "4h", transport=transport_returning(payload), clock=fixed_clock()
    )
    second = fetch_klines(
        "BTCUSDT", "4h", transport=transport_returning(payload), clock=fixed_clock()
    )
    assert first == second


# ============================ error hierarchy ================================


def test_error_hierarchy() -> None:
    for error in (
        BinanceRequestError, BinanceTransportError,
        BinanceAPIError, BinanceResponseError,
    ):
        assert issubclass(error, BinanceError)
    assert issubclass(BinanceRequestError, ValueError)
    assert issubclass(BinanceResponseError, ValueError)


# ============================ public API / boundaries ========================


def test_public_api_exports() -> None:
    for name in (
        "fetch_klines", "map_kline", "build_klines_url", "urlopen_transport",
        "HttpResponse", "Transport", "BINANCE_API_BASE", "KLINE_INTERVALS",
        "MAX_LIMIT", "BinanceError", "BinanceRequestError", "BinanceTransportError",
        "BinanceAPIError", "BinanceResponseError",
    ):
        assert name in binance.__all__
        assert hasattr(binance, name)


def _internal_imports(pkg_dir: Path) -> set[str]:
    found: set[str] = set()
    for py in pkg_dir.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("fmis"):
                    found.add(node.module)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("fmis"):
                        found.add(a.name)
    return found


def test_import_boundary_source_level() -> None:
    imports = _internal_imports(Path(binance.__file__).parent)
    assert any(i.startswith("fmis.ingest") for i in imports)
    for module in imports:
        for forbidden in ("fmis.features", "fmis.alignment", "fmis.relative_value"):
            assert not module.startswith(forbidden), module
        assert "_timeutils" not in module


def test_import_does_not_load_analytical_packages(fresh_fmis_imports: None) -> None:
    import fmis.providers.binance  # noqa: F401

    for forbidden in ("fmis.features", "fmis.alignment", "fmis.relative_value"):
        assert not any(m.startswith(forbidden) for m in sys.modules)


def test_adapter_does_not_construct_canonical_models_directly() -> None:
    # Candle must be reached through fmis.ingest so validation cannot be bypassed.
    source = Path(binance.__file__).read_text()
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "fmis.data":
            imported |= {a.name for a in node.names}
    assert "Candle" not in imported


def test_no_third_party_imports() -> None:
    # The project is at zero runtime dependencies; the adapter must not change that.
    tree = ast.parse(Path(binance.__file__).read_text())
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
    assert roots <= set(sys.stdlib_module_names) | {"fmis"}


def _code_strings_and_names(path: Path) -> set[str]:
    """Every string literal and identifier in the module's *code*.

    Docstrings and comments are excluded deliberately: prose may legitimately
    mention what the adapter does not do (e.g. explaining that only the websocket
    stream carries a closed flag) without that being an actual reference.
    """
    tree = ast.parse(path.read_text())
    docstrings = {
        doc
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and (doc := ast.get_docstring(node, clean=False)) is not None
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                found.add(node.value.lower())
        elif isinstance(node, ast.Name):
            found.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            found.add(node.attr.lower())
    return found


def test_no_private_or_authenticated_endpoints() -> None:
    # Public market data only: nothing signs a request, reads a credential, or
    # touches an account/order endpoint or a websocket stream.
    code = _code_strings_and_names(Path(binance.__file__))
    for forbidden in ("api_key", "apikey", "secret", "signature", "hmac", "/order",
                      "wss://", "websocket", "/api/v3/account", "listenkey"):
        assert not any(forbidden in item for item in code), forbidden


def test_only_the_public_klines_endpoint_is_referenced() -> None:
    code = _code_strings_and_names(Path(binance.__file__))
    paths = {item for item in code if item.startswith("/api/")}
    assert paths == {"/api/v3/klines"}
