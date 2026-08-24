"""A local, read-only HTTP server for the dashboard. Standard library only.

**Why `http.server` and not a framework.** This repository declares
``dependencies = []`` and a guard test asserts the package imports nothing from
`flask`, `django` or `fastapi` — and `pandas`/`numpy` are on the same forbidden
list, which rules out Streamlit's dependency tree with it. A local, read-only,
single-user page that renders server-side HTML needs routing, escaping and a
socket; the standard library has all three. The alternative was a dependency
tree measured in hundreds of packages to serve seven static routes.

**The safety posture, in four rules the code enforces rather than documents:**

  * **`GET` and `HEAD` only.** Every other method returns 405 without ever
    reaching a handler. `do_POST`, `do_PUT`, `do_PATCH` and `do_DELETE` are
    defined and all four refuse — defined deliberately, because
    `BaseHTTPRequestHandler`'s own 501 is a *"not implemented yet"* that invites
    somebody to implement it.

  * **Loopback by default, and widening it is loud.** `DEFAULT_HOST` is
    ``127.0.0.1``. Binding anywhere else must be asked for explicitly, and
    binding to all interfaces additionally requires `allow_public=True`, so the
    financial position of the owner is not published to a café network because a
    flag looked harmless.

  * **No filesystem is served.** There is no static route, no path is joined to
    a filesystem root, and the router is a fixed mapping. A path-traversal
    attempt cannot reach a file because no request path is ever turned into one.

  * **Nothing writes.** The server holds a snapshot in memory and re-reads
    engines on request. No handler reaches a store verb, and a guard asserts the
    whole package is free of write verbs and file-opening.

**The refresh model is explicit and stated on every page.** One snapshot is held
and shared by all seven routes, so navigating between them shows one consistent
instant rather than seven pages that each re-fetched and disagree. A refresh
happens only when asked for — ``?refresh=1`` — or on the first request. The
header always carries the refresh instant and the data instant, so an old page
never passes for a live one.

**Concurrent refreshes collapse into one.** A lock guards the snapshot, so two
browser tabs reloading together perform one set of engine reads rather than
eight, and neither tab sees a half-assembled snapshot.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import parse_qs, unquote, urlsplit

from fmis.operator_dashboard.compose import refresh as refresh_snapshot
from fmis.operator_dashboard.models import OperatorDashboardSnapshot
from fmis.operator_dashboard.render import PAGES, render_page

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "ALLOWED_METHODS",
    "SnapshotHolder",
    "DashboardServer",
    "build_server",
    "serve",
    "resolve_route",
]

#: Loopback. Chosen, not defaulted-into: this page states an owner's positions,
#: open risk and account figures, and it must not leave the machine.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

#: The only two methods that reach a handler at all.
ALLOWED_METHODS = ("GET", "HEAD")

_KNOWN_PATHS = frozenset(path for path, _ in PAGES)


def resolve_route(path: str) -> tuple[str, str | None] | None:
    """Map a request path onto a page, or `None` if there is no such page.

    Returns ``(page_path, symbol)``. The symbol route is the only dynamic one,
    and it is matched by prefix rather than by joining anything to anything —
    there is no filesystem underneath, so ``/swing/../../etc/passwd`` resolves
    to a symbol name that no setup matches and renders the ordinary *not on this
    page* message.
    """
    # `"".rstrip("/") or "/"` and `"/".rstrip("/") or "/"` both yield "/", so the
    # empty path and the bare root are already handled by the membership test
    # below. A separate `if path == ""` branch here can never be taken.
    clean = path.rstrip("/") or "/"
    if clean in _KNOWN_PATHS:
        return clean, None
    if clean.startswith("/swing/"):
        symbol = unquote(clean[len("/swing/") :])
        if symbol and "/" not in symbol:
            return "/swing", symbol
    return None


class SnapshotHolder:
    """One snapshot, shared by every route, refreshed only when asked.

    **Why a holder rather than a fetch per page.** Seven routes each performing
    their own reads would mean seven different instants behind one header, and
    the header can only state one. Holding the snapshot makes the page honest:
    every panel on every route describes the same refresh, and the refresh
    instant is printed.

    **The lock is not an optimisation.** Two tabs reloading simultaneously would
    otherwise run two full sets of engine reads and race to install the result;
    the second to finish would win, and the first tab would render a snapshot
    that had already been replaced. One refresh at a time, and waiters get the
    result of the refresh that was already running.
    """

    def __init__(
        self,
        *,
        refresher: Callable[..., OperatorDashboardSnapshot] = refresh_snapshot,
        clock: Callable[[], datetime] | None = None,
        symbols: Sequence[str] | None = None,
        store_root: Path | str | None = None,
        benchmarks: Sequence[str] | None = None,
        with_relationships: bool = True,
    ) -> None:
        self._refresher = refresher
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._symbols = symbols
        self._store_root = store_root
        self._benchmarks = benchmarks
        self._with_relationships = with_relationships
        self._lock = threading.Lock()
        self._snapshot: OperatorDashboardSnapshot | None = None
        #: Counts every completed refresh. A test asserts that navigating four
        #: routes performs one refresh, not four.
        self.refresh_count = 0

    def _read(self) -> OperatorDashboardSnapshot:
        snapshot = self._refresher(
            refreshed_at=self._clock(),
            symbols=self._symbols,
            store_root=self._store_root,
            benchmarks=self._benchmarks,
            with_relationships=self._with_relationships,
        )
        self._snapshot = snapshot
        self.refresh_count += 1
        return snapshot

    def current(self, *, force: bool = False) -> OperatorDashboardSnapshot:
        """The held snapshot, refreshing only on demand or on the first request."""
        with self._lock:
            if force or self._snapshot is None:
                return self._read()
            return self._snapshot


def _handler_class(holder: SnapshotHolder, *, quiet: bool) -> type:
    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "FMITS-Dashboard"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        # -- output ------------------------------------------------------

        def _send(self, status: HTTPStatus, body: bytes, *, head: bool = False) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            # The page renders one owner's positions. Nothing about it should be
            # cached by anything, embedded anywhere, or sniffed into another
            # content type.
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:",
            )
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def _error(self, status: HTTPStatus, message: str) -> None:
            body = (
                "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
                f"<title>FMITS · {status.value}</title></head><body>"
                f"<h1>{status.value} {status.phrase}</h1><p>{message}</p>"
                '<p><a href="/">Back to the dashboard</a></p>'
                "</body></html>"
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            if status is HTTPStatus.METHOD_NOT_ALLOWED:
                self.send_header("Allow", ", ".join(ALLOWED_METHODS))
            self.end_headers()
            self.wfile.write(body)

        # -- routing -----------------------------------------------------

        def _serve(self, *, head: bool) -> None:
            parts = urlsplit(self.path)
            route = resolve_route(parts.path)
            if route is None:
                self._error(
                    HTTPStatus.NOT_FOUND,
                    "No such page. This dashboard serves a fixed set of routes "
                    "and no files.",
                )
                return
            page, symbol = route
            query = parse_qs(parts.query)
            force = query.get("refresh", ["0"])[0] not in ("0", "", "false")
            snapshot = holder.current(force=force)
            body = render_page(snapshot, page, symbol=symbol).encode("utf-8")
            self._send(HTTPStatus.OK, body, head=head)

        def do_GET(self) -> None:  # noqa: N802 - stdlib's naming
            self._serve(head=False)

        def do_HEAD(self) -> None:  # noqa: N802
            self._serve(head=True)

        # -- everything that could change something ----------------------

        def _refuse(self) -> None:
            """Defined on purpose, so the refusal is explicit rather than a
            not-implemented-yet that reads as an invitation."""
            self._error(
                HTTPStatus.METHOD_NOT_ALLOWED,
                "This dashboard is read-only. It accepts GET and HEAD, and "
                "exposes no method that could change anything.",
            )

        do_POST = _refuse  # noqa: N815
        do_PUT = _refuse  # noqa: N815
        do_PATCH = _refuse  # noqa: N815
        do_DELETE = _refuse  # noqa: N815
        do_OPTIONS = _refuse  # noqa: N815

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            if not quiet:
                super().log_message(format, *args)

    return DashboardHandler


class DashboardServer(ThreadingHTTPServer):
    """Threaded so one slow refresh does not block a second tab's page load."""

    daemon_threads = True
    allow_reuse_address = True


def build_server(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    holder: SnapshotHolder | None = None,
    allow_public: bool = False,
    quiet: bool = False,
) -> tuple[DashboardServer, SnapshotHolder]:
    """Build a bound server without serving. `serve` calls this; tests call it too.

    Args:
        host: the interface to bind. Defaults to loopback.
        port: ``0`` asks the operating system for a free port, which is what a
            test wants and what an owner whose 8787 is taken can pass.
        allow_public: required to bind a non-loopback interface. Without it,
            binding one is refused rather than warned about — this page states
            an owner's open positions and account figures, and a warning printed
            to a terminal nobody reads is not a control.
    """
    if not allow_public and host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError(
            f"refusing to bind {host!r}: this dashboard renders the owner's "
            "positions, open risk and account figures, and binding it off "
            "loopback publishes them to the network. Pass allow_public=True if "
            "that is genuinely what you want."
        )
    holder = holder or SnapshotHolder()
    server = DashboardServer((host, port), _handler_class(holder, quiet=quiet))
    return server, holder


def serve(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    holder: SnapshotHolder | None = None,
    allow_public: bool = False,
    quiet: bool = False,
    announce: Callable[[str, DashboardServer], None] | None = None,
) -> None:
    """Bind, announce, and serve until interrupted. **The only serving loop.**

    The CLI calls this rather than repeating the bind-print-serve-clean
    sequence, so there is one place that knows how the dashboard is started and
    one place that knows how it is stopped.

    ``announce`` is called after the socket is bound and before the loop begins,
    with the URL and the server. Binding failures propagate — `build_server`
    raises `ValueError` for a refused interface and `OSError` for a port already
    in use, and the caller maps those to an exit code rather than this layer
    deciding what a failure to start is worth.
    """
    server, _ = build_server(
        host=host, port=port, holder=holder, allow_public=allow_public, quiet=quiet
    )
    bound_host, bound_port = server.server_address[:2]
    if announce is not None:
        announce(f"http://{bound_host}:{bound_port}/", server)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
