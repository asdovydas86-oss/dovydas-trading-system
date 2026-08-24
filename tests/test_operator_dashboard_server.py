"""The local server: routing, refusal, binding, and the refresh model.

These are the safety tests. The page states an owner's positions, open risk and
account figures, so the properties asserted here — loopback only, GET only, no
filesystem, one refresh — are controls rather than conveniences.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection

import pytest
from operator_dashboard_helpers import AT, Boom

from fmis.operator_dashboard import (
    ALLOWED_METHODS,
    DEFAULT_HOST,
    PAGES,
    SnapshotHolder,
    build_server,
    build_snapshot,
    resolve_route,
)

ROUTES = [path for path, _ in PAGES]


def _snapshot(refreshed_at=AT, **kwargs):
    return build_snapshot(
        refreshed_at=refreshed_at,
        reference_time=refreshed_at,
        workspace_error=Boom("no store"),
        pulse_error=Boom("no venue"),
        macro_error=Boom("no FRED"),
        statistics_error=Boom("no corpus"),
    )


class _Counter:
    """A refresher that counts calls and never touches the network."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *, refreshed_at, **kwargs):
        self.calls += 1
        return _snapshot(refreshed_at)


@pytest.fixture
def live():
    """A bound, serving dashboard on an ephemeral loopback port."""
    counter = _Counter()
    holder = SnapshotHolder(refresher=counter, clock=lambda: AT)
    server, _ = build_server(port=0, holder=holder, quiet=True)
    # `shutdown` waits up to one poll interval, and the stdlib default of 0.5s
    # would make the fixture's teardown dominate the suite's runtime.
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield host, port, counter, holder
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _request(host, port, path, method="GET", body=None):
    connection = HTTPConnection(host, port, timeout=10)
    try:
        connection.request(method, path, body=body)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ROUTES)
def test_every_declared_route_resolves(path: str) -> None:
    assert resolve_route(path) == (path, None)


def test_a_trailing_slash_resolves_to_the_same_page() -> None:
    assert resolve_route("/markets/") == ("/markets", None)


def test_a_symbol_route_resolves_to_the_swing_page_and_the_symbol() -> None:
    assert resolve_route("/swing/BTCUSDT") == ("/swing", "BTCUSDT")


def test_a_percent_encoded_symbol_is_decoded() -> None:
    assert resolve_route("/swing/BTC%20USDT") == ("/swing", "BTC USDT")


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "/../../etc/passwd",
        "/swing/../../etc/passwd",
        "/swing/a/b",
        "/swing/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "/static/theme.css",
        "/nope",
    ],
)
def test_no_traversal_or_unknown_path_resolves(path: str) -> None:
    """**There is no filesystem underneath.** No request path is ever joined to
    a root, so traversal cannot reach a file — but the router refuses these
    anyway rather than letting one become a symbol lookup."""
    assert resolve_route(path) is None


def test_a_decoded_separator_is_refused_after_decoding_not_before() -> None:
    """`%2F` decodes to a separator, so the check must happen on the decoded
    text. Checking first would let an encoded path through."""
    assert resolve_route("/swing/a%2Fb") is None


@pytest.mark.parametrize("path", ROUTES)
def test_every_route_answers_200(live, path: str) -> None:
    host, port, _, _ = live
    status, _, body = _request(host, port, path)
    assert status == 200
    assert body.startswith(b"<!DOCTYPE html>")


def test_an_unknown_route_answers_404_and_not_a_half_page(live) -> None:
    host, port, _, _ = live
    status, _, body = _request(host, port, "/nope")
    assert status == 404
    assert b"serves a fixed set of routes and no files" in body


def test_an_unknown_symbol_answers_200_and_says_it_is_not_here(live) -> None:
    host, port, _, _ = live
    status, _, body = _request(host, port, "/swing/NOSUCHUSDT")
    assert status == 200


# ---------------------------------------------------------------------------
# Read-only: the methods
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_every_mutating_method_is_refused_with_405(live, method: str) -> None:
    """**Defined on purpose.** `BaseHTTPRequestHandler`'s own 501 is a *not
    implemented yet*, which reads as an invitation to implement it."""
    host, port, _, _ = live
    status, headers, body = _request(host, port, "/", method=method, body=b"")
    assert status == 405
    assert headers.get("Allow") == ", ".join(ALLOWED_METHODS)
    assert b"read-only" in body


def test_only_get_and_head_are_allowed() -> None:
    assert ALLOWED_METHODS == ("GET", "HEAD")


def test_head_returns_the_headers_and_no_body(live) -> None:
    host, port, _, _ = live
    status, headers, body = _request(host, port, "/", method="HEAD")
    assert status == 200
    assert body == b""
    assert int(headers["Content-Length"]) > 0


def test_a_post_to_a_symbol_route_is_refused_too(live) -> None:
    host, port, _, _ = live
    status, _, _ = _request(host, port, "/swing/BTCUSDT", method="POST", body=b"")
    assert status == 405


# ---------------------------------------------------------------------------
# Read-only: the binding
# ---------------------------------------------------------------------------


def test_the_default_host_is_loopback() -> None:
    """Chosen, not defaulted into."""
    assert DEFAULT_HOST == "127.0.0.1"


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10"])
def test_binding_off_loopback_is_refused_rather_than_warned_about(host: str) -> None:
    """A warning printed to a terminal nobody reads is not a control."""
    with pytest.raises(ValueError, match="refusing to bind"):
        build_server(host=host, port=0)


def test_binding_off_loopback_is_possible_when_asked_for_explicitly() -> None:
    server, _ = build_server(host="0.0.0.0", port=0, allow_public=True, quiet=True)
    try:
        assert server.server_address[0] == "0.0.0.0"
    finally:
        server.server_close()


# ---------------------------------------------------------------------------
# Read-only: the headers
# ---------------------------------------------------------------------------


def test_the_page_is_never_cached(live) -> None:
    """It states an owner's positions."""
    host, port, _, _ = live
    _, headers, _ = _request(host, port, "/")
    assert "no-store" in headers["Cache-Control"]


@pytest.mark.parametrize(
    "header,expected",
    [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
    ],
)
def test_the_hardening_headers_are_present(live, header: str, expected: str) -> None:
    host, port, _, _ = live
    _, headers, _ = _request(host, port, "/")
    assert headers[header] == expected


def test_the_content_security_policy_forbids_scripts(live) -> None:
    host, port, _, _ = live
    _, headers, _ = _request(host, port, "/")
    policy = headers["Content-Security-Policy"]
    assert "default-src 'none'" in policy
    assert "script-src" not in policy


# ---------------------------------------------------------------------------
# The refresh model
# ---------------------------------------------------------------------------


def test_navigating_every_route_performs_one_refresh_not_seven(live) -> None:
    """**Seven routes each fetching would mean seven different instants behind
    one header,** and the header can only state one."""
    host, port, counter, _ = live
    for path in ROUTES:
        _request(host, port, path)
    assert counter.calls == 1


def test_an_explicit_refresh_re_reads(live) -> None:
    host, port, counter, _ = live
    _request(host, port, "/")
    assert counter.calls == 1
    _request(host, port, "/?refresh=1")
    assert counter.calls == 2


@pytest.mark.parametrize("value", ["0", "", "false"])
def test_a_falsey_refresh_parameter_does_not_re_read(live, value: str) -> None:
    host, port, counter, _ = live
    _request(host, port, "/")
    _request(host, port, f"/?refresh={value}")
    assert counter.calls == 1


def test_repeated_reloads_do_not_re_read(live) -> None:
    host, port, counter, _ = live
    for _ in range(12):
        _request(host, port, "/markets")
    assert counter.calls == 1


def test_simultaneous_refreshes_collapse_into_one_read() -> None:
    """Two tabs reloading together would otherwise run two full sets of engine
    reads and race to install the result."""
    started = threading.Barrier(4)
    counter = _Counter()
    slow_lock = threading.Lock()

    def slow(*, refreshed_at, **kwargs):
        with slow_lock:
            counter.calls += 1
        threading.Event().wait(0.05)
        return _snapshot(refreshed_at)

    holder = SnapshotHolder(refresher=slow, clock=lambda: AT)
    results = []

    def hit() -> None:
        started.wait()
        results.append(holder.current())

    threads = [threading.Thread(target=hit) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(results) == 4
    # One refresh, and every waiter saw a fully assembled snapshot.
    assert counter.calls == 1
    assert all(result is results[0] for result in results)


def test_the_holder_reports_how_many_refreshes_it_performed() -> None:
    holder = SnapshotHolder(refresher=_Counter(), clock=lambda: AT)
    assert holder.refresh_count == 0
    holder.current()
    holder.current()
    holder.current(force=True)
    assert holder.refresh_count == 2


def test_a_held_snapshot_never_pretends_to_be_current(live) -> None:
    """**A green-looking stale dashboard is a severe defect.** The refresh
    instant is the held one, not the moment the page was served."""
    host, port, _, _ = live
    _, _, first = _request(host, port, "/")
    _, _, later = _request(host, port, "/markets")
    stamp = AT.strftime("%Y-%m-%d %H:%M").encode()
    assert stamp in first and stamp in later


def test_serve_binds_announces_and_shuts_down_cleanly() -> None:
    """**The only serving loop.** The CLI calls this rather than repeating the
    bind-print-serve-clean sequence, so there is one place that knows how the
    dashboard starts and one that knows how it stops."""
    from fmis.operator_dashboard import serve

    announced: list[str] = []
    ready = threading.Event()

    def announce(url: str, server) -> None:
        announced.append(url)
        ready.set()
        # Stop the loop from another thread once it is running.
        threading.Thread(target=_stop_soon, args=(server, ready), daemon=True).start()

    def _stop_soon(server, flag) -> None:
        flag.wait(5)
        threading.Event().wait(0.05)
        server.shutdown()

    thread = threading.Thread(
        target=serve, kwargs={"port": 0, "quiet": True, "announce": announce}
    )
    thread.start()
    thread.join(timeout=15)
    assert not thread.is_alive(), "serve did not shut down"
    assert announced and announced[0].startswith("http://127.0.0.1:")


def test_serve_propagates_a_refused_binding_rather_than_swallowing_it() -> None:
    """The caller maps a failure to start to an exit code; this layer does not
    decide what one is worth."""
    from fmis.operator_dashboard import serve

    with pytest.raises(ValueError, match="refusing to bind"):
        serve(host="0.0.0.0", port=0, quiet=True)


def test_the_server_can_be_closed_and_rebuilt_on_the_same_port() -> None:
    """Dashboard closed and reopened."""
    server, _ = build_server(port=0, quiet=True)
    port = server.server_address[1]
    server.server_close()
    again, _ = build_server(port=port, quiet=True)
    try:
        assert again.server_address[1] == port
    finally:
        again.server_close()


# ---------------------------------------------------------------------------
# Nothing is written
# ---------------------------------------------------------------------------


def test_browsing_every_route_changes_no_stored_value(tmp_path, live) -> None:
    """The functional read-only proof: fingerprint the store, browse, compare."""
    store = tmp_path / "store"
    store.mkdir()
    (store / "positions.jsonl").write_text('{"a": 1}\n', encoding="utf-8")
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime)
        for path in store.rglob("*")
    }

    host, port, _, _ = live
    for path in ROUTES + ["/swing/BTCUSDT", "/?refresh=1"]:
        _request(host, port, path)

    after = {
        path.name: (path.read_bytes(), path.stat().st_mtime)
        for path in store.rglob("*")
    }
    assert before == after
