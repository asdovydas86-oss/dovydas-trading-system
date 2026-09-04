"""Rebuilding the Milestone BZ capture that Milestones BZ and CA were measured over.

**This module exists because that file was never kept.** Milestone CA is a pure
function of a saved BZ capture — `fmis.swing_lab.admission_study.study_from_capture`
has no live path at all — and Milestone CB and CC then reasoned about CA's sample
from *published figures* rather than from the observations themselves. The
capture, however, was produced by an ad-hoc runner during BZ and never persisted
into `reports/artifacts/`, so by the time Milestone CD needed the paired effects
back, nothing in the repository could produce them.

That is the provenance gap CD was told to close rather than widen, and closing it
means writing the runner down. Everything here is a **composition** of functions
that already exist:

    fmis.swing_lab.validation_study.capture_for_window   ← fetch + replay (BX/BY's)
    fmis.swing_lab.persistence_replay.TimelineCollector  ← the observer sink (BZ's)
    fmis.swing_lab.persistence_artifact.encode_capture   ← the payload (BZ's)

No window, no symbol, no threshold and no interval is chosen here. The two
universes are read from the sealed sample specifications, exactly as
`fmis.swing_lab.persistence_study.run_persistence_experiment` reads them, and a
regression asserts the windows this module derives are identical to the ones that
function derives.

**The capture it writes is NOT the capture CA measured.** Binance's history is
mutable at source and three years have passed; a re-capture is a *new dataset
taken under the same rules*, and it is recorded that way. Its manifest carries
its own `captured_at`, and CD's report compares its reconstructed admission
counts against CA's published ones rather than assuming they agree.

**This is the only module in `fmis.paired_dependence` permitted to reach a
network**, and an architecture guard asserts that.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from fmis.swing_lab.models import SwingLabError

__all__ = [
    "CA_UNIVERSE_FOR_SAMPLE",
    "capture_windows",
    "capture_ca_sources",
]

#: Which captured universe each sealed CA sample is cut from. This is the exact
#: mapping `fmits research admission` passes to `study_from_capture`, named once
#: here so CD's reconstruction cannot drift from the CLI's.
CA_UNIVERSE_FOR_SAMPLE: Mapping[str, str] = {
    "development": "primary",
    "validation": "primary",
    "holdout": "holdout",
}


def capture_windows() -> dict[str, tuple[tuple[str, ...], datetime, datetime]]:
    """The two universes, their symbols and their windows. **Read, never chosen.**

    ``primary`` spans development ∪ validation because they are the same fifteen
    symbols over adjacent windows and BZ captured them in one replay; ``holdout``
    is its own symbols over its own window. Both are taken from the sealed
    `fmis.swing_lab.preregistration.SAMPLES`, so a symbol cannot be added here
    without breaking a seal somewhere else.
    """
    from fmis.swing_lab.preregistration import SAMPLES

    by_name = {item.name: item for item in SAMPLES}
    development = by_name["development"]
    validation = by_name["validation"]
    holdout = by_name["holdout"]
    if development.symbols != validation.symbols:
        raise SwingLabError(
            "development and validation no longer name the same symbols, so they "
            "cannot be cut from one 'primary' capture; this module's assumption "
            "is broken and the mapping must be revisited rather than patched"
        )
    return {
        "primary": (
            development.symbols,
            min(development.signal_start, validation.signal_start),
            max(development.signal_end, validation.signal_end),
        ),
        "holdout": (
            holdout.symbols,
            holdout.signal_start,
            holdout.signal_end,
        ),
    }


def capture_ca_sources(
    *,
    run_at: datetime,
    universes: Sequence[str] = ("primary", "holdout"),
    evaluation_window_bars: int | None = None,
    limit: int | None = None,
    transport: Any = None,
    base_url: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Replay the CA universes and encode them as a BZ capture payload.

    One replay per universe with a `TimelineCollector` attached, so the geometry
    candidates and the structural timeline come out of the **same** walk — BZ's
    reason, unchanged: a timeline paired with a different capture would describe
    a different market at the same bar index.

    Raises:
        SwingLabError: a name in ``universes`` is not one this module knows, or
            the provider cannot satisfy some symbol's window.
    """
    from fmis.swing_lab.persistence_artifact import encode_capture
    from fmis.swing_lab.persistence_preregistration import (
        BZ_PREREGISTRATION_DIGEST,
        BZ_PREREGISTRATION_ID,
        DECIDING_COST_POLICY_ID,
    )
    from fmis.swing_lab.persistence_replay import TimelineCollector
    from fmis.swing_lab.validation_study import capture_for_window
    from fmis.swing_setup.backtest_harness import (
        DEFAULT_BACKTEST_LIMIT,
        DEFAULT_EVALUATION_WINDOW_BARS,
    )

    if not isinstance(run_at, datetime) or run_at.utcoffset() is None:
        raise SwingLabError("run_at must be a timezone-aware datetime")
    say = progress if progress is not None else (lambda _message: None)
    windows = capture_windows()
    unknown = [name for name in universes if name not in windows]
    if unknown:
        raise SwingLabError(
            f"no universe named {', '.join(sorted(unknown))}; this module knows "
            f"{', '.join(sorted(windows))}"
        )
    window_bars = (
        DEFAULT_EVALUATION_WINDOW_BARS
        if evaluation_window_bars is None
        else evaluation_window_bars
    )
    candle_limit = DEFAULT_BACKTEST_LIMIT if limit is None else limit

    collected: dict[str, tuple[Any, Mapping[str, Any]]] = {}
    for name in universes:
        symbols, start, end = windows[name]
        say(f"replaying {name}: {len(symbols)} symbols, {start.date()} → {end.date()}")
        collector = TimelineCollector()
        capture = capture_for_window(
            symbols,
            measurement_start=start,
            measurement_end=end,
            run_at=run_at,
            evaluation_window_bars=window_bars,
            limit=candle_limit,
            transport=transport,
            base_url=base_url,
            observer=collector,
        )
        say(
            f"  {name}: {len(capture.candidates)} candidates, "
            f"{collector.observed} observations"
        )
        collected[name] = (capture, collector.timelines())

    return encode_capture(
        collected,
        manifest={
            "preregistration_id": BZ_PREREGISTRATION_ID,
            "preregistration_digest": BZ_PREREGISTRATION_DIGEST,
            "captured_at": run_at.isoformat(),
            "evaluation_window_bars": window_bars,
            "deciding_cost_policy_id": DECIDING_COST_POLICY_ID,
            "candle_limit": candle_limit,
            "writer": "fmis.paired_dependence.capture.capture_ca_sources",
        },
    )
