"""Builders for Milestone CD's tests. **Every value here is fabricated on purpose.**

A CD test must never reach a network, a capture or a store, so these builders
construct the exact shapes the estimator and the artifact consume and nothing
else. `record` produces a Milestone CA `PairedRecord`; `row` produces a CD
`ObservationRow`; `panel` produces a whole grid of them with a known structure.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fmis.paired_dependence.observations import ObservationRow
from fmis.swing_lab.admission import FORWARD_HORIZONS
from fmis.swing_lab.admission_preregistration import CA_NULL_FAMILIES, PRIMARY_HORIZON
from fmis.swing_lab.admission_study import PairedRecord
from fmis.swing_setup.models import Direction

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
FAMILIES = {item.family_id: item for item in CA_NULL_FAMILIES}
TIMING = FAMILIES["ca_null_matched_timing"]
DIGEST = "d" * 64


def record(
    *,
    difference: float,
    symbol: str = "BTCUSDT",
    bar_index: int = 100,
    sample: str = "development",
    family_id: str = TIMING.family_id,
    direction: Direction = Direction.LONG,
    control: float = 0.0,
) -> PairedRecord:
    """One Milestone CA paired record whose primary-horizon difference is known."""
    admission = {h: control + difference for h in FORWARD_HORIZONS}
    controls = {h: control for h in FORWARD_HORIZONS}
    return PairedRecord(
        family_id=family_id,
        sample=sample,
        symbol=symbol,
        bar_index=bar_index,
        as_of=T0 + timedelta(hours=4 * bar_index),
        direction=direction,
        segment=None,
        volatility="steady",
        pool_size=120,
        radius_tier=0,
        admission_forward=admission,
        admission_mfe={h: abs(difference) for h in FORWARD_HORIZONS},
        admission_mae={h: -abs(difference) for h in FORWARD_HORIZONS},
        admission_race={h: None for h in FORWARD_HORIZONS},  # type: ignore[dict-item]
        control_forward=controls,
        control_mfe=controls,
        control_mae=controls,
        control_race_favourable={h: 0 for h in FORWARD_HORIZONS},
        control_race_adverse={h: 0 for h in FORWARD_HORIZONS},
        control_race_ambiguous={h: 0 for h in FORWARD_HORIZONS},
        control_primary_draws=(control, control),
    )


def row(
    *,
    difference: float,
    symbol: str = "BTCUSDT",
    bar_index: int = 100,
    sample: str = "development",
    family_id: str = TIMING.family_id,
    economic_asset: str | None = None,
    control: float = 0.0,
) -> ObservationRow:
    """One CD observation row with consistent parts."""
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    return ObservationRow(
        observation_id=f"{family_id}|{sample}|{symbol}|{bar_index}",
        family_id=family_id,
        sample=sample,
        universe="primary",
        symbol=symbol,
        base_asset=base,
        economic_asset=base if economic_asset is None else economic_asset,
        bar_index=bar_index,
        as_of=T0 + timedelta(hours=4 * bar_index),
        direction="long",
        horizon=PRIMARY_HORIZON,
        segment=None,
        volatility="steady",
        pool_size=120,
        radius_tier=0,
        control_draws=200,
        admission_forward=control + difference,
        control_forward=control,
        difference=difference,
        capture_content_digest=DIGEST,
        capture_captured_at="2026-09-03T00:00:00+00:00",
    )


def panel(
    *,
    assets: int = 12,
    blocks: int = 20,
    block_bars: int = 60,
    per_cell: int = 1,
    market: float = 0.0,
    level: float = 0.0,
    sample: str = "development",
    family_id: str = TIMING.family_id,
) -> tuple[ObservationRow, ...]:
    """A deterministic grid of rows with a stated block factor and asset level.

    No randomness at all: the "factor" is a fixed function of the block index and
    the "level" a fixed function of the asset index, so a test asserting a
    direction of movement never fights a seed.
    """
    rows: list[ObservationRow] = []
    for asset_index in range(assets):
        symbol = f"A{asset_index:02d}USDT"
        for block in range(blocks):
            factor = market * ((block % 5) - 2)
            offset = level * ((asset_index % 5) - 2)
            for slot in range(per_cell):
                rows.append(
                    row(
                        difference=factor + offset + 0.01 * slot,
                        symbol=symbol,
                        bar_index=block * block_bars + slot,
                        sample=sample,
                        family_id=family_id,
                    )
                )
    return tuple(rows)
