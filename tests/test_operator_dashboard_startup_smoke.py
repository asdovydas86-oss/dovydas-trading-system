"""The startup smoke test: does `fmits dashboard` actually open?

**Why this file exists.** The dashboard stopped opening while 14,049 tests
passed under ``-W error``. Nothing in the suite was wrong; the suite simply had
no test that performed the operator's sequence — run the command, read the URL
off the terminal, request it, look at the page, press Ctrl-C. Every piece was
covered and the sequence was not, so a surface that started and never answered
was indistinguishable, to the suite, from a healthy one.

**What is real here and what is not.** A subprocess runs
`tests/dashboard_smoke_driver.py`, which calls `fmis.pipeline.cli.main` with the
operator's argument vector. The process, the argument parsing, the runner, the
warming refresh, `serve`, the bound socket, the HTTP handler, the composition
root, every `sections` mapping, the renderer and the interrupt are production
code and real. Only the three networked reads in `compose.REFRESH_READS` are
replaced, by fixtures, through `SnapshotHolder`'s own ``refresher`` seam — see
the driver's module docstring for why exactly those three.

**No live provider is required to render the shell, and that is asserted.** If
it ever becomes required, these tests hang against Binance and FRED rather than
passing quietly, which is the outcome worth having.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

from dashboard_smoke_driver import SLOW_REFRESH_SECONDS

from fmis.operator_dashboard import PAGES

DRIVER = Path(__file__).with_name("dashboard_smoke_driver.py")

#: Every route the product declares. Read from the production tuple rather than
#: copied, so a page added to the dashboard is smoke-tested the day it lands.
ROUTES = tuple(path for path, _ in PAGES)

#: Generous, because a machine under load starting an interpreter is not a
#: defect. Small enough that a dashboard that never answers fails the suite
#: rather than hanging it.
READY_TIMEOUT = 60.0
EXIT_TIMEOUT = 30.0

#: The line `_run_dashboard` prints once, and only once, a request to the
#: address can be answered. Its arrival *is* the readiness signal — that is the
#: whole point of the repair it is testing.
READY_PREFIX = "  open     http://"

#: Printed after the socket is bound and before the first refresh.
PREPARING_PREFIX = "  address  http://"


class _Dashboard:
    """A running `fmits dashboard` process, its output, and how to stop it."""

    def __init__(self, process: subprocess.Popen) -> None:
        self.process = process
        self.stdout: list[str] = []
        self.stderr: list[str] = []
        self._pumps = [
            self._pump(process.stdout, self.stdout),
            self._pump(process.stderr, self.stderr),
        ]

    @staticmethod
    def _pump(stream, sink: list[str]) -> threading.Thread:
        # Read on threads: the parent must not block on one pipe while the child
        # blocks writing the other, and it must be able to give up on a child
        # that never speaks at all.
        def drain() -> None:
            for line in stream:
                sink.append(line.rstrip("\n"))

        thread = threading.Thread(target=drain, daemon=True)
        thread.start()
        return thread

    def line_starting(self, prefix: str, *, timeout: float) -> str | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for line in list(self.stdout):
                if line.startswith(prefix):
                    return line
            if self.process.poll() is not None:
                # It exited. One last look, then stop waiting for a dead process.
                for line in list(self.stdout):
                    if line.startswith(prefix):
                        return line
                return None
            time.sleep(0.02)
        return None

    def url(self, *, timeout: float = READY_TIMEOUT) -> str | None:
        line = self.line_starting(READY_PREFIX, timeout=timeout)
        return None if line is None else line.split()[-1]

    def interrupt(self) -> int:
        """Ctrl-C, exactly as the banner tells the operator to stop it."""
        self.process.send_signal(signal.SIGINT)
        return self.process.wait(timeout=EXIT_TIMEOUT)

    def kill(self) -> None:
        """Stop it however it was left, and close the pipes.

        The pipes are closed explicitly rather than left to the garbage
        collector: this suite runs under ``-W error``, so the `ResourceWarning`
        an unclosed pipe raises at collection is a test failure — correctly, and
        in a file whose whole subject is cleaning up after a process.
        """
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=EXIT_TIMEOUT)
        # The pumps end at EOF, which the exit above guarantees.
        for pump in self._pumps:
            pump.join(timeout=5)
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()


def _start(store_root: Path, *, break_mode: str = "none") -> _Dashboard:
    process = subprocess.Popen(
        [
            sys.executable,
            "-W",
            "error",
            str(DRIVER),
            # Port 0: the operating system picks a free one, so a developer who
            # happens to be running their own dashboard on 8787 does not fail
            # this test, and two of these can run at once.
            "--port",
            "0",
            "--store-root",
            str(store_root),
            "--break",
            break_mode,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        # Unbuffered, so the banner reaches the pipe when it is printed rather
        # than when the process ends — and the process is not meant to end.
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    return _Dashboard(process)


@pytest.fixture
def dashboard(tmp_path):
    """A started dashboard, killed however the test leaves it."""
    started: list[_Dashboard] = []

    def start(*, break_mode: str = "none") -> _Dashboard:
        store = tmp_path / "store"
        store.mkdir(exist_ok=True)
        running = _start(store, break_mode=break_mode)
        started.append(running)
        return running

    try:
        yield start
    finally:
        for running in started:
            running.kill()


def _get(url: str, path: str = "", method: str = "GET"):
    rest = url.split("://", 1)[1].rstrip("/")
    host, _, port = rest.partition(":")
    connection = HTTPConnection(host, int(port), timeout=30)
    try:
        connection.request(method, path or "/")
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# The product smoke test
# ---------------------------------------------------------------------------


def test_the_operators_command_starts_serves_the_dashboard_and_stops(dashboard) -> None:
    """**The whole sequence, in one test.** Start, become ready, answer the main
    route with a recognisable dashboard, and stop on Ctrl-C with a zero exit."""
    running = dashboard()

    # 1. It starts, and says what it is doing before it makes anyone wait.
    preparing = running.line_starting(PREPARING_PREFIX, timeout=READY_TIMEOUT)
    assert preparing is not None, (
        "the command printed no address; stdout was "
        f"{running.stdout!r}, stderr was {running.stderr!r}"
    )

    # 2. It does not crash on the way up, and it becomes ready.
    url = running.url()
    assert url is not None, (
        "the dashboard never announced a URL it could answer; stdout was "
        f"{running.stdout!r}, stderr was {running.stderr!r}"
    )
    assert url.startswith("http://127.0.0.1:")
    assert running.process.poll() is None, "the process died before serving"

    # 3. The main route answers.
    status, headers, body = _get(url)
    assert status == 200, f"the main route answered {status}"

    # 4. What came back is the FMITS dashboard, not an empty 200. The page must
    #    carry the product's own identity, the navigation to its other routes,
    #    and a figure that only an engine read could have put there.
    page = body.decode("utf-8")
    assert len(body) > 4000, f"the main route returned {len(body)} bytes"
    assert "<title>FMITS · Overview</title>" in page
    assert "FMITS Operator Dashboard" in page
    for route in ROUTES:
        if route != "/":
            assert f'href="{route}"' in page, f"the page does not link {route}"
    assert "Global market pulse" in page
    assert "BTC" in page, "no benchmark from the pulse read reached the page"
    assert "read-only" in page or "read only" in page

    # 5. Ctrl-C stops it cleanly.
    code = running.interrupt()
    assert code == 0, f"Ctrl-C exited {code}; stderr was {running.stderr!r}"
    assert any("stopped" in line for line in running.stderr), (
        f"the command did not report stopping; stderr was {running.stderr!r}"
    )


def test_the_url_is_announced_only_once_it_can_be_answered(dashboard) -> None:
    """**The repair, asserted directly, against a refresh that costs real time.**

    The outage was a URL printed 30-45 s before anything could answer it: the
    browser's connection was accepted and then received no byte for the whole of
    the refresh, which every browser reports as a server that stopped
    responding. Which side of the announcement pays for the refresh is the whole
    of the repair, and it is only observable when the refresh costs something —
    so this test uses the driver's slow refresh rather than its instant one.

    Revert the repair and this test fails on both halves at once: the *open*
    line arrives immediately, and the first request to it takes the refresh."""
    running = dashboard(break_mode="slow")

    # The address is offered straight away, so the wait is never a silent one.
    started = time.monotonic()
    assert running.line_starting(PREPARING_PREFIX, timeout=READY_TIMEOUT) is not None
    address_after = time.monotonic() - started
    assert address_after < SLOW_REFRESH_SECONDS, (
        f"the bound address took {address_after:.1f}s to appear; the operator is "
        "watching a silent terminal"
    )

    # The URL is not offered until the refresh behind it is done.
    url = running.url()
    assert url is not None
    open_after = time.monotonic() - started
    assert open_after >= SLOW_REFRESH_SECONDS * 0.8, (
        f"the URL was announced {open_after:.1f}s in, before a "
        f"{SLOW_REFRESH_SECONDS:.0f}s refresh could have finished — the "
        "dashboard is announcing an address it cannot yet answer"
    )

    # And the browser therefore waits for none of it.
    started = time.monotonic()
    status, _, body = _get(url)
    elapsed = time.monotonic() - started
    assert status == 200
    assert elapsed < SLOW_REFRESH_SECONDS / 3, (
        f"the first request after the URL was announced took {elapsed:.1f}s; "
        "the refresh is being paid inside the request again"
    )
    assert b"FMITS" in body


def test_every_route_the_page_links_answers(dashboard) -> None:
    """A dashboard whose nav leads to 404s has not opened either."""
    running = dashboard()
    url = running.url()
    assert url is not None

    for route in ROUTES:
        status, _, body = _get(url, route)
        assert status == 200, f"{route} answered {status}"
        assert b"FMITS" in body, f"{route} returned a page that is not FMITS"


def test_starting_the_dashboard_needs_no_live_market_provider(dashboard) -> None:
    """**An architecture assertion, not a convenience.** The shell must render
    from what the engines return, including from what they could not read. If
    rendering it ever requires a reachable venue, this test stops passing
    offline and the requirement becomes visible instead of implicit."""
    running = dashboard()
    assert running.url() is not None
    status, _, _ = _get(running.url(), "/")
    assert status == 200


# ---------------------------------------------------------------------------
# Non-vacuity: the smoke test must be able to fail
# ---------------------------------------------------------------------------


def test_a_dashboard_that_crashes_on_startup_is_caught(dashboard) -> None:
    """``--break startup`` raises inside the first refresh. If the smoke test
    could not tell this from a healthy dashboard it would be measuring
    nothing."""
    running = dashboard(break_mode="startup")

    assert running.url(timeout=EXIT_TIMEOUT) is None, (
        "a dashboard whose first refresh raises announced itself as ready"
    )
    code = running.process.wait(timeout=EXIT_TIMEOUT)
    assert code != 0, "a dashboard that crashed on startup exited zero"


def test_a_dashboard_whose_main_route_is_broken_is_caught(dashboard) -> None:
    """``--break route`` makes every path resolve to nothing. The process still
    starts and still announces a URL — which is exactly the trap a startup-only
    check would fall into — so the smoke test's assertion on the *response* is
    what has to catch it, and does."""
    running = dashboard(break_mode="route")

    url = running.url()
    assert url is not None, "the broken-route build did not even start"

    status, _, body = _get(url)
    assert status == 404, f"a broken main route answered {status}"
    assert b"<title>FMITS \xc2\xb7 Overview</title>" not in body

    running.interrupt()
