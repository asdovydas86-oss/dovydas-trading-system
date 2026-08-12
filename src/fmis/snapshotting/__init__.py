"""Frozen market facts: `MarketSnapshot` and `DecisionWindow`.

**This package imports no engine.** It holds the shape of a frozen bundle; the
composition root fills it. That single rule is what keeps the trading domain's
"reads the market half, is never read by it" boundary checkable by one import
guard instead of by reading every import in the domain.
"""

from __future__ import annotations

from fmis.snapshotting.readings import (
    ROLE_ORDER,
    Anchor,
    ConflictNote,
    EvidenceFamilyReading,
    FreshnessReading,
    IndependenceDisclosure,
    LevelOriginRef,
    LevelReading,
    LevelSideRef,
    RegimeDimensionReading,
    RegimeReading,
    RequirementReading,
    RiskRewardReading,
    SetupReading,
    SnapshotError,
    SnapshotRole,
    SnapshotTrigger,
    StopTriggerSemantics,
    SufficiencyReading,
    TradeDirection,
    TriggerBasis,
    RoleReading,
)
from fmis.snapshotting.snapshot import (
    FIELD_GROUP_ORIGINS,
    MARKET_SNAPSHOT_KIND,
    MARKET_SNAPSHOT_SCHEMA_VERSION,
    MARKET_SNAPSHOT_TYPE_SLUG,
    SUPPORTED_MARKET_SNAPSHOT_VERSIONS,
    MarketSnapshot,
)
from fmis.snapshotting.window import (
    DECISION_WINDOW_KIND,
    DECISION_WINDOW_SCHEMA_VERSION,
    DECISION_WINDOW_TYPE_SLUG,
    SUPPORTED_DECISION_WINDOW_VERSIONS,
    DecisionWindow,
    WindowBar,
    WindowMode,
    series_digest_of,
)

__all__ = [
    "SnapshotError",
    # readings
    "SnapshotRole",
    "ROLE_ORDER",
    "SnapshotTrigger",
    "TradeDirection",
    "LevelSideRef",
    "LevelOriginRef",
    "LevelReading",
    "RiskRewardReading",
    "RegimeDimensionReading",
    "RegimeReading",
    "RequirementReading",
    "SufficiencyReading",
    "EvidenceFamilyReading",
    "IndependenceDisclosure",
    "ConflictNote",
    "FreshnessReading",
    "TriggerBasis",
    "StopTriggerSemantics",
    "SetupReading",
    "Anchor",
    "RoleReading",
    # the snapshot
    "MarketSnapshot",
    "MARKET_SNAPSHOT_SCHEMA_VERSION",
    "SUPPORTED_MARKET_SNAPSHOT_VERSIONS",
    "MARKET_SNAPSHOT_TYPE_SLUG",
    "MARKET_SNAPSHOT_KIND",
    "FIELD_GROUP_ORIGINS",
    # the window
    "DecisionWindow",
    "WindowMode",
    "WindowBar",
    "series_digest_of",
    "DECISION_WINDOW_SCHEMA_VERSION",
    "SUPPORTED_DECISION_WINDOW_VERSIONS",
    "DECISION_WINDOW_TYPE_SLUG",
    "DECISION_WINDOW_KIND",
]
