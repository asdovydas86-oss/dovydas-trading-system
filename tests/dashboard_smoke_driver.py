"""Runs the real ``fmits dashboard`` command in a real process, offline.

**Why a driver script rather than a fixture.** The startup smoke test exists
because the dashboard once started and never opened, and nothing in a suite of
fourteen thousand tests noticed. What failed was not a function; it was the
sequence a person performs — run the command, get a URL, open it, see the page.
Reproducing that means an actual process with an actual entrypoint, an actual
socket, and an actual interrupt, because every one of those was in the path of
the outage and none of them is exercised by calling a function in-process.

So this script is spawned by `test_operator_dashboard_startup_smoke` and calls
`fmis.pipeline.cli.main` with the same argument vector the operator types. It
adds nothing to the startup path and it removes nothing from it: the parser, the
runner, `serve`, `build_server`, `SnapshotHolder`, `compose.refresh`,
`build_snapshot`, every `sections` mapping, `render_page` and the HTTP handler
are all the production code.

**What it does replace, and why exactly that.** Three of the four reads named in
`compose.REFRESH_READS` reach a market provider over the network. A smoke test
that reached Binance and FRED would be slow, would fail on a train, and would
report an outage at a venue as a defect in this repository. They are replaced —
through `SnapshotHolder`'s own documented ``refresher`` seam, by binding
`compose.refresh`'s injected runner arguments — with the fixtures the rest of
the dashboard suite already uses, which are real `SwingWorkspace`, `MarketPulse`
and `MacroContextReport` values rather than stubs. The fourth read,
`report_for_store`, is left alone: it reads a store root the test supplies and
touches no network.

**The one thing it adds to the startup path, and why.** `_enable_ctrl_c` puts
`SIGINT` back to the handler CPython installs at startup. A shell without job
control hands a background job an *ignored* `SIGINT`, that disposition survives
`exec`, and a dashboard that cannot receive `SIGINT` turns the two Ctrl-C tests
into a measurement of how the suite was launched. The driver stands in for the
operator's terminal; a terminal always has Ctrl-C live. See the function.

**The break modes are the test's non-vacuity proof.** ``--break startup`` makes
the first refresh raise, ``--break route`` makes the main route resolve to
nothing, and ``--break slow`` makes the refresh cost real seconds. A smoke test
that cannot tell those from a healthy dashboard is not measuring anything, so
the suite runs them and asserts it can.

``slow`` is the one that reproduces the outage itself. Offline, a refresh from
fixtures costs nothing, so whether it is paid before the URL is announced or
inside the first request is invisible — which would make the assertion about the
repair a passing test that measures nothing. With a refresh that takes
`SLOW_REFRESH_SECONDS`, the two orderings are told apart by which of the two
waits: the announcement, or the browser.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
from functools import partial

#: This file is spawned by path, so its own directory is not on `sys.path` and
#: the shared dashboard fixtures beside it would not import.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BREAK_CHOICES = ("none", "startup", "route", "slow")

#: Long enough that paying it inside a request is unmistakable against the
#: sub-second answer a warmed dashboard gives; short enough to sit in a suite.
SLOW_REFRESH_SECONDS = 3.0


def _offline_runners(break_mode: str):
    """The three networked runners, bound to the suite's own fixtures.

    Returned as keyword arguments rather than as a finished refresher, because
    the command wires its own refresher — `compose.refresh` with scan memory
    around it — and this driver must keep that wiring rather than replace it.
    Binding the runners into whatever the command wired replaces exactly the
    three reads that reach a network and nothing else.
    """
    import time

    from operator_dashboard_helpers import benchmark, macro_of, pulse_of, reading_for
    from swing_workspace_helpers import assessment, result, workspace_of

    workspace = workspace_of(result(assessment()))
    pulse = pulse_of((reading_for(benchmark("BTC")), reading_for(benchmark("ETH"))))
    macro = macro_of((reading_for(benchmark("SPX")),))

    def workspace_runner(*_args, **_kwargs):
        return workspace

    def pulse_runner(**_kwargs):
        return pulse

    def macro_runner(**_kwargs):
        return macro

    if break_mode == "slow":
        # Stands in for the four live engine reads, whose real cost is 30-45 s.
        def slow_workspace_runner(*args, **kwargs):
            time.sleep(SLOW_REFRESH_SECONDS)
            return workspace

        workspace_runner = slow_workspace_runner

    return {
        "workspace_runner": workspace_runner,
        "pulse_runner": pulse_runner,
        "macro_runner": macro_runner,
    }


def _install(break_mode: str) -> None:
    from fmis.operator_dashboard import compose
    from fmis.operator_dashboard import server as server_module
    from fmis.operator_dashboard.server import SnapshotHolder
    from fmis.pipeline import cli
    from operator_dashboard_helpers import AT

    if break_mode == "startup":

        def raise_at_startup(**_kwargs):
            # Not a provider failure — `compose.refresh` absorbs every one of
            # those into a section that says so. This is the shape of a defect
            # that escapes it, which is what the outage would have looked like.
            raise RuntimeError("smoke driver: deliberately broken first refresh")

        runners = None
    else:
        runners = _offline_runners(break_mode)

    class OfflineSnapshotHolder(SnapshotHolder):
        """The production holder, reading fixtures instead of the network.

        ``refresher`` arrives from the command — which since Slice 3 wraps
        `compose.refresh` in scan memory — and is **kept**, with only the three
        networked runners bound. Discarding it would silently take the recording
        seam out of the very startup path this test exists to exercise.
        """

        def __init__(self, *, refresher=None, **kwargs) -> None:
            if runners is None:
                wired = raise_at_startup
            else:
                wired = partial(refresher or compose.refresh, **runners)
            super().__init__(refresher=wired, clock=lambda: AT, **kwargs)

    cli.SnapshotHolder = OfflineSnapshotHolder

    if break_mode == "route":
        # The handler resolves this name at request time, so replacing it here
        # is enough to make every path — the main one included — a 404.
        server_module.resolve_route = lambda _path: None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="0")
    parser.add_argument("--store-root", required=True)
    # Required, never defaulted: without it the command would resolve the
    # owner's real `~/.fmits/scan_memory` and a test would write to it.
    parser.add_argument("--scan-history-root", required=True)
    parser.add_argument("--break", dest="break_mode", default="none", choices=BREAK_CHOICES)
    args = parser.parse_args(argv)

    _install(args.break_mode)

    from fmis.pipeline.cli import main as cli_main

    return cli_main(
        [
            "dashboard",
            "--port",
            args.port,
            "--store-root",
            args.store_root,
            "--scan-history-root",
            args.scan_history_root,
        ]
    )


def _enable_ctrl_c() -> None:
    """Start with Ctrl-C live, whatever the session that spawned this had.

    A shell without job control — ``pytest &``, `nohup`, and most CI and agent
    runners — starts a background job with `SIGINT` set to `SIG_IGN`, and an
    *ignored* disposition is one of the few things that survives `exec`.
    `subprocess`'s ``restore_signals`` does not undo it: it restores only the
    three signals CPython itself ignores (`SIGPIPE`, `SIGXFZ`, `SIGXFSZ`), not
    one inherited from a shell.

    So a dashboard spawned from such a session cannot receive `SIGINT` at all,
    and the two smoke tests that press Ctrl-C were measuring how the suite had
    been launched rather than how `serve` shuts down: they timed out after 30 s
    against a process that was serving correctly and had never been signalled.
    Backgrounded, the whole suite reported those two — and only those two — as
    failures; in a terminal the same commit passed.

    This driver stands in for the operator's terminal, where Ctrl-C is always
    live, so it installs the handler CPython installs at startup and the test
    goes back to measuring the dashboard.

    **Here, in the child, rather than `preexec_fn` in the parent.** `preexec_fn`
    runs between `fork` and `exec` and is documented as unsafe in a process that
    has threads — and the smoke harness keeps one pipe-draining thread per
    running dashboard, so it is exactly the process that must not use it.

    **Production is deliberately left alone.** ``fmits dashboard &`` ignoring
    Ctrl-C is correct POSIX behaviour for a background job, and a command that
    overrode its own caller's signal disposition would be compensating in the
    product for how a test was started.
    """
    signal.signal(signal.SIGINT, signal.default_int_handler)


if __name__ == "__main__":
    # Only when run as a process. Imported — the smoke test reads
    # `SLOW_REFRESH_SECONDS` from here — this file must change nothing about the
    # pytest process it is imported into.
    _enable_ctrl_c()
    raise SystemExit(main())
