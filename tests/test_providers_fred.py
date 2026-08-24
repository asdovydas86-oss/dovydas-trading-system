"""Milestone BU — the FRED adapter, and every convention that stops here.

An adapter's job is to make one source's conventions somebody else's non-problem.
The ones that matter here, each tested below:

  * a missing observation is an **empty field** (and historically a ``.``), and
    it is dropped — never carried forward, never read as zero;
  * an observation carries a **date**, not an instant, and is timestamped at the
    start of the period it describes;
  * the body must **declare the series that was asked for**, because a value
    printed under the wrong name is the one error nothing downstream can catch;
  * a non-2xx answer is an error carrying the source's own words, never an empty
    series.

Nothing here touches the network: every test injects a transport.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.data.observation import ObservationSeries
from fmis.providers.fred import (
    FRED_BASE,
    MISSING_MARKERS,
    OBSERVATION_DATING_LIMITATION,
    FredAPIError,
    FredRequestError,
    FredResponseError,
    FredTransportError,
    HttpResponse,
    build_series_url,
    fetch_observations,
    parse_observations_csv,
    urlopen_transport,
)

UNIT = "percent per annum"
FREQ = "1d"


def parse(body: bytes, series_id: str = "DGS10") -> ObservationSeries:
    return parse_observations_csv(body, series_id=series_id, unit=UNIT, frequency=FREQ)


def csv(*rows: str, series_id: str = "DGS10") -> bytes:
    return ("\n".join([f"observation_date,{series_id}", *rows]) + "\n").encode()


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# The request
# --------------------------------------------------------------------------


def test_the_url_is_the_documented_csv_download() -> None:
    url = build_series_url(series_id="DGS10")
    assert url == f"{FRED_BASE}/graph/fredgraph.csv?id=DGS10"


def test_the_url_is_deterministic() -> None:
    assert build_series_url(series_id="SP500") == build_series_url(series_id="SP500")


def test_a_base_url_override_is_honoured_and_its_trailing_slash_ignored() -> None:
    assert build_series_url(series_id="DGS10", base_url="http://x/").startswith(
        "http://x/graph"
    )


@pytest.mark.parametrize("bad", ["dgs10", "DGS 10", "DGS-10", "", "Dgs10"])
def test_a_series_id_is_exact_and_is_never_normalised(bad: str) -> None:
    """*An identifier is not a search term.* Rewriting one hides a typo until it
    becomes a wrong number on a page."""
    with pytest.raises(FredRequestError):
        build_series_url(series_id=bad)


@pytest.mark.parametrize("bad", [None, 7, b"DGS10", ["DGS10"]])
def test_a_series_id_that_is_not_text_is_refused_before_any_request(bad: object) -> None:
    with pytest.raises(FredRequestError, match="must be a str"):
        build_series_url(series_id=bad)


def test_no_credential_or_key_appears_in_the_url() -> None:
    """This endpoint needs no authentication and this adapter sends none."""
    url = build_series_url(series_id="DGS10")
    lowered = url.lower()
    for banned in ("api_key", "apikey", "token", "secret", "password", "auth"):
        assert banned not in lowered


# --------------------------------------------------------------------------
# Parsing — the ordinary case
# --------------------------------------------------------------------------


def test_a_well_formed_body_becomes_a_canonical_series() -> None:
    series = parse(csv("2026-08-19,4.65", "2026-08-20,4.69"))
    assert isinstance(series, ObservationSeries)
    assert series.series_id == "DGS10"
    assert series.unit == UNIT
    assert series.frequency == FREQ
    assert series.values == (4.65, 4.69)
    assert series.timestamps == (utc("2026-08-19"), utc("2026-08-20"))


def test_an_observation_is_timestamped_at_the_start_of_its_own_date() -> None:
    """*The latest instant this repository can name for a period is the instant
    that period began.* An age is therefore overstated, never understated."""
    series = parse(csv("2026-08-20,4.69"))
    moment = series.timestamps[0]
    assert (moment.hour, moment.minute, moment.second) == (0, 0, 0)
    assert moment.tzinfo is not None and moment.utcoffset().total_seconds() == 0


def test_the_dating_limitation_is_stated_rather_than_left_to_be_discovered() -> None:
    assert "overstated" in OBSERVATION_DATING_LIMITATION
    assert "never understated" in OBSERVATION_DATING_LIMITATION
    assert "replay" in OBSERVATION_DATING_LIMITATION


def test_a_series_with_no_observations_is_empty_rather_than_an_error() -> None:
    """An empty *body* is a failed request; a header with no rows is a series
    that genuinely has no observations. The two are different facts."""
    series = parse(csv())
    assert series.values == ()
    assert series.timestamps == ()


def test_a_trailing_blank_line_is_formatting_and_not_an_observation() -> None:
    body = b"observation_date,DGS10\n2026-08-20,4.69\n\n"
    assert parse(body).values == (4.69,)


def test_a_negative_value_is_accepted_because_a_yield_can_be_negative() -> None:
    assert parse(csv("2026-08-20,-0.43")).values == (-0.43,)


def test_a_value_in_scientific_notation_is_parsed() -> None:
    assert parse(csv("2026-08-20,1e2")).values == (100.0,)


# --------------------------------------------------------------------------
# Missing observations
# --------------------------------------------------------------------------


def test_the_documented_missing_markers_are_the_empty_field_and_a_dot() -> None:
    assert MISSING_MARKERS == frozenset({"", "."})


@pytest.mark.parametrize("marker", ["", "."])
def test_a_missing_observation_is_dropped_and_never_read_as_zero(marker: str) -> None:
    """A market holiday is not a print of zero. This is the single most
    consequential line in the adapter."""
    series = parse(csv("2026-08-19,4.65", f"2026-08-20,{marker}", "2026-08-21,4.71"))
    assert series.values == (4.65, 4.71)
    assert 0.0 not in series.values
    assert utc("2026-08-20") not in series.timestamps


def test_a_missing_observation_is_never_carried_forward() -> None:
    series = parse(csv("2026-08-19,4.65", "2026-08-20,", "2026-08-21,4.71"))
    assert len(series.values) == 2
    assert series.values.count(4.65) == 1


def test_a_whitespace_only_value_is_treated_as_missing() -> None:
    assert parse(csv("2026-08-19,4.65", "2026-08-20,   ")).values == (4.65,)


def test_a_series_that_is_entirely_missing_is_empty_and_not_zeros() -> None:
    series = parse(csv("2026-08-19,", "2026-08-20,."))
    assert series.values == ()


# --------------------------------------------------------------------------
# Bodies that must be refused
# --------------------------------------------------------------------------


def test_a_body_declaring_another_series_is_refused_rather_than_relabelled() -> None:
    """*A value printed under the wrong name is an error nothing downstream can
    catch.* The most dangerous malformed body there is."""
    with pytest.raises(FredResponseError, match="never relabelled"):
        parse(csv("2026-08-20,4.69", series_id="SP500"), series_id="DGS10")


def test_an_empty_body_is_a_failed_request_and_not_an_empty_series() -> None:
    with pytest.raises(FredResponseError, match="empty download is a"):
        parse(b"")


def test_a_header_with_the_wrong_column_count_is_refused() -> None:
    with pytest.raises(FredResponseError, match="returns exactly"):
        parse(b"observation_date,DGS10,extra\n2026-08-20,4.69,1\n")


def test_a_row_with_the_wrong_field_count_is_refused() -> None:
    with pytest.raises(FredResponseError, match="expected 2 fields"):
        parse(b"observation_date,DGS10\n2026-08-20,4.69,7\n")


def test_a_value_that_is_neither_a_number_nor_a_missing_marker_is_refused() -> None:
    with pytest.raises(FredResponseError, match="neither a number nor"):
        parse(csv("2026-08-20,n/a"))


def test_a_date_that_is_not_a_calendar_date_is_refused() -> None:
    with pytest.raises(FredResponseError, match="not an ISO calendar date"):
        parse(csv("20-08-2026,4.69"))


def test_a_body_that_is_not_utf8_is_refused() -> None:
    with pytest.raises(FredResponseError, match="not valid UTF-8"):
        parse(b"observation_date,DGS10\n2026-08-20,\xff\xfe\n")


def test_a_body_that_is_not_bytes_is_refused() -> None:
    with pytest.raises(FredResponseError, match="must be bytes"):
        parse_observations_csv(
            "observation_date,DGS10\n", series_id="DGS10", unit=UNIT, frequency=FREQ
        )


def test_dates_that_run_backwards_are_refused_by_the_canonical_boundary() -> None:
    """*The canonical model owns every invariant that matters.* The adapter does
    not sort, because a source returning unordered dates is a source whose
    output nobody should be silently repairing."""
    with pytest.raises(ValueError, match="strictly increasing"):
        parse(csv("2026-08-21,4.71", "2026-08-20,4.69"))


def test_a_duplicated_date_is_refused_rather_than_deduplicated() -> None:
    """Hostile review: *the exact same timestamp with conflicting values.*"""
    with pytest.raises(ValueError, match="strictly increasing"):
        parse(csv("2026-08-20,4.69", "2026-08-20,4.71"))


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------


def transport_for(response: HttpResponse):
    def send(url: str) -> HttpResponse:
        send.urls.append(url)
        return response

    send.urls = []
    return send


def test_a_successful_fetch_returns_the_parsed_series() -> None:
    send = transport_for(HttpResponse(200, csv("2026-08-20,4.69")))
    series = fetch_observations("DGS10", unit=UNIT, frequency=FREQ, transport=send)
    assert series.values == (4.69,)
    assert send.urls == [build_series_url(series_id="DGS10")]


@pytest.mark.parametrize("status", [400, 403, 404, 500, 503])
def test_a_non_2xx_answer_is_an_error_carrying_the_source_s_own_words(
    status: int,
) -> None:
    """FRED answers an unknown series with an HTML 404 rather than a structured
    error, so the preview is carried verbatim instead of paraphrased."""
    body = b"<!DOCTYPE html><html><body>Page not found</body></html>"
    send = transport_for(HttpResponse(status, body))
    with pytest.raises(FredAPIError) as caught:
        fetch_observations("NOPE", unit=UNIT, frequency=FREQ, transport=send)
    assert caught.value.status == status
    assert "Page not found" in caught.value.preview


def test_a_provider_failure_is_never_turned_into_an_empty_series() -> None:
    send = transport_for(HttpResponse(500, b"down"))
    with pytest.raises(FredAPIError):
        fetch_observations("DGS10", unit=UNIT, frequency=FREQ, transport=send)


def test_a_transport_returning_the_wrong_type_is_refused() -> None:
    with pytest.raises(FredResponseError, match="must return an HttpResponse"):
        fetch_observations(
            "DGS10", unit=UNIT, frequency=FREQ, transport=lambda url: b"raw"
        )


def test_a_bad_series_id_fails_before_any_request_is_made() -> None:
    send = transport_for(HttpResponse(200, csv("2026-08-20,4.69")))
    with pytest.raises(FredRequestError):
        fetch_observations("bad", unit=UNIT, frequency=FREQ, transport=send)
    assert send.urls == []


def test_the_whole_available_history_is_returned_without_truncation() -> None:
    """*Windowing is the consumer's job.* Truncating here would put window
    selection in two places."""
    rows = [f"2026-01-{day:02d},{day}.0" for day in range(1, 29)]
    send = transport_for(HttpResponse(200, csv(*rows)))
    series = fetch_observations("DGS10", unit=UNIT, frequency=FREQ, transport=send)
    assert len(series.values) == 28


def test_a_programmer_defect_inside_the_transport_propagates() -> None:
    """*Anything not a source condition propagates.* A `KeyError` rendered as a
    market that could not be read teaches the owner to ignore both."""

    def broken(url: str) -> HttpResponse:
        raise KeyError("a defect inside FMITS")

    with pytest.raises(KeyError):
        fetch_observations("DGS10", unit=UNIT, frequency=FREQ, transport=broken)


def test_the_default_transport_raises_a_transport_error_for_an_unreachable_host() -> None:
    """The one network-shaped test, pointed at a host that cannot resolve."""
    with pytest.raises(FredTransportError):
        urlopen_transport(
            "http://localhost:1/graph/fredgraph.csv?id=DGS10", timeout=0.05
        )


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_two_parses_of_one_body_produce_one_series() -> None:
    body = csv("2026-08-19,4.65", "2026-08-20,", "2026-08-21,4.71")
    assert parse(body) == parse(body)


def test_the_unit_and_frequency_are_the_caller_s_and_are_never_inferred() -> None:
    """*FRED's own units string is prose, and parsing it would make this adapter
    the place unit semantics are decided.*"""
    series = parse_observations_csv(
        csv("2026-08-20,4.69"),
        series_id="DGS10",
        unit="index points",
        frequency="weekly",
    )
    assert series.unit == "index points"
    assert series.frequency == "weekly"
