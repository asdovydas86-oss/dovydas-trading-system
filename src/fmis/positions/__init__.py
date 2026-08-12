"""The position fold — a rebuildable projection over the resolved ledger.

Delete every position, recompute, and the answer must be identical. That property
is what makes `Position` deletable and everything above it not.
"""

from __future__ import annotations

from fmis.positions.fold import POSITION_CALCULATION_VERSION, fold_positions
from fmis.positions.models import (
    POSITION_STATE_TRANSITIONS,
    AverageCost,
    IllegalPositionTransitionError,
    Position,
    PositionDirection,
    PositionKey,
    PositionsError,
    PositionState,
    ReconciliationState,
    advance_position_state,
    total_fees,
)

__all__ = [
    "PositionsError",
    "IllegalPositionTransitionError",
    "PositionState",
    "POSITION_STATE_TRANSITIONS",
    "advance_position_state",
    "PositionDirection",
    "ReconciliationState",
    "PositionKey",
    "AverageCost",
    "Position",
    "total_fees",
    "fold_positions",
    "POSITION_CALCULATION_VERSION",
]
