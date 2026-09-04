"""Builders for the Slice 1 per-symbol decision tests.

Offline, clock-free and network-free. Assessments come from the **real**
composition root (`setup_assessment_for_sheet`) run over `archive_helpers.multi`,
which builds a three-view fact sheet from seeded synthetic candles — so the
decision paths under test are the ones the live product reaches, not paths
hand-written to be convenient.

The three seed triples are chosen because they reach three different exits of
`evaluate_setup`, and the two `WAIT` exits are the two the audit named:

    GATE_REJECTED   the context-role regime gate rejects, before any
                    directional tally happens at all      (the BTC-shaped case)
    FAMILIES_SPLIT  the gate passes, and the families then split one long
                    against two short                     (the BNB-shaped case)
    CANDIDATE       the tally agrees and a directional candidate exists

Symbols are deliberately **not** named BTCUSDT/BNBUSDT. The audit's live values
will have moved by the time anybody reads this, and a test that hard-coded them
would be asserting what the market did rather than what the code carries.
"""

from __future__ import annotations

from fmis.operator_dashboard import build_snapshot
from fmis.swing_setup.compose import (
    SetupRunResult,
    setup_inputs_and_assessment_for_sheet,
    setup_readings_for,
)
from fmis.swing_workspace import build_swing_workspace

from tests.archive_helpers import multi
from tests.operator_dashboard_helpers import AT
from tests.swing_workspace_helpers import run_of

__all__ = [
    "GATE_REJECTED",
    "GATE_LEANING",
    "FAMILIES_SPLIT",
    "CANDIDATE",
    "live",
    "two_wait_paths",
    "workspace_of",
    "snapshot_of",
]

GATE_REJECTED = (1, 5, 9)
FAMILIES_SPLIT = (3, 5, 9)
CANDIDATE = (2, 4, 7)

#: The **BTC-shaped** case Slice 2 exists for: every readable family leans the
#: same way, and the reading was stopped by the higher-timeframe regime gate
#: before the tally ever ran. `WAIT`, with directional evidence developing —
#: the exact combination that must never be rendered as a signal.
GATE_LEANING = (1, 4, 9)


def live(
    seeds: tuple[int, int, int], symbol: str, *, readings: bool = True
) -> SetupRunResult:
    """One result from the real composition root, over synthetic candles.

    ``readings=False`` builds the pre-Slice-2 shape — an assessment with none of
    the structured facts it was reasoned from — which is what a hand-built
    result and every caller before this milestone produced. Used to assert that
    the surfaces state the gap rather than inventing a per-role instant.
    """
    sheet = multi(seeds=seeds, symbol=symbol)
    inputs, assessment = setup_inputs_and_assessment_for_sheet(sheet)
    return SetupRunResult(
        requested_symbol=symbol,
        assessment=assessment,
        readings=setup_readings_for(sheet, inputs) if readings else None,
    )


def two_wait_paths() -> tuple[SetupRunResult, SetupRunResult]:
    """One symbol rejected at the gate, one rejected by a family split."""
    return live(GATE_REJECTED, "AAAUSDT"), live(FAMILIES_SPLIT, "BBBUSDT")


def workspace_of(*results: SetupRunResult):
    """A full `SwingWorkspace` over the supplied results."""
    return build_swing_workspace(run_of(*results))


def snapshot_of(*results: SetupRunResult):
    """A full dashboard snapshot over the supplied results."""
    return build_snapshot(
        refreshed_at=AT, reference_time=AT, workspace=workspace_of(*results)
    )
