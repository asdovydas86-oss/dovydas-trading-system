"""Builders for trading-domain fixtures.

Every builder returns a *valid* record with sensible, obviously-fake values, and
takes keyword overrides so a test can make exactly one thing wrong. The pattern is
`tests/archive_helpers.py`'s, applied to the owner half.

No value here is a policy threshold: dust thresholds, risk limits and confidence
labels are all supplied by the caller, because the domain invents none and a
helper that quietly chose one would make a test pass for the wrong reason.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fmis.accounts import AccountId, Book, MarketId, MarketMode, OwnerContext, VenueId
from fmis.money import AssetCode, DustPolicy, Money, Quantity
from fmis.provenance import Absent, ValueOrigin, VersionedTerm
from fmis.records import ConsumedSource, RecordAudit
from fmis.snapshotting import (
    Anchor,
    ConflictNote,
    DecisionWindow,
    EvidenceFamilyReading,
    FreshnessReading,
    IndependenceDisclosure,
    LevelOriginRef,
    LevelReading,
    LevelSideRef,
    MarketSnapshot,
    RegimeDimensionReading,
    RegimeReading,
    RequirementReading,
    RiskRewardReading,
    RoleReading,
    SetupReading,
    SnapshotRole,
    SnapshotTrigger,
    StopTriggerSemantics,
    SufficiencyReading,
    TradeDirection,
    TriggerBasis,
    WindowBar,
    WindowMode,
    series_digest_of,
)
from fmis.versioning import VersionAxis, VersionSet

__all__ = [
    "AT",
    "MARKET",
    "OTHER_MARKET",
    "ACCOUNT",
    "USDT",
    "BTC",
    "version_set",
    "owner_context",
    "dust_policy",
    "level_origin",
    "level",
    "role_reading",
    "sufficiency",
    "setup_reading",
    "market_snapshot",
    "decision_window",
    "anchor",
    "money",
    "quantity",
    "reason_tag",
    "consumed",
]

USDT = AssetCode("USDT")
BTC = AssetCode("BTC")
MARKET = MarketId(VenueId("binance"), BTC, USDT, MarketMode.SPOT)
OTHER_MARKET = MarketId(VenueId("binance"), AssetCode("ETH"), USDT, MarketMode.SPOT)
ACCOUNT = AccountId("binance_spot")


def AT(hour: int = 9, *, day: int = 12, minute: int = 0) -> datetime:
    """A fixed UTC instant. Tests never call `now()` — a clock is not a fixture."""
    return datetime(2026, 8, day, hour, minute, tzinfo=timezone.utc)


def version_set(**axes: str) -> VersionSet:
    supplied = {
        VersionAxis.CODE_VERSION: "7ced9e2",
        VersionAxis.POLICY_VERSION: "swing-setup-v1",
        VersionAxis.CALCULATION_VERSION: "position-fold-v1",
    }
    for name, value in axes.items():
        supplied[VersionAxis(name)] = value
    return VersionSet.of(supplied)


def owner_context(**overrides: Any) -> OwnerContext:
    values: dict[str, Any] = {
        "display_timezone": "Europe/Stockholm",
        "base_currency": AssetCode("SEK"),
        "tax_period_timezone": "Europe/Stockholm",
        "routine_times": ("07:00", "14:15", "22:15"),
    }
    values.update(overrides)
    return OwnerContext(**values)


def dust_policy(threshold: str = "0.00000001", **overrides: Any) -> DustPolicy:
    values: dict[str, Any] = {
        "policy_id": "dust-v1",
        "version": 1,
        "thresholds": ((BTC, Decimal(threshold)),),
    }
    values.update(overrides)
    return DustPolicy(**values)


def level_origin(origin_id: str = "swing-low-114", **overrides: Any) -> LevelOriginRef:
    values: dict[str, Any] = {
        "origin_id": origin_id,
        "swing_index": 42,
        "confirmation_bars": 3,
    }
    values.update(overrides)
    return LevelOriginRef(**values)


def level(
    price: str = "58400",
    side: LevelSideRef = LevelSideRef.BELOW,
    origin: LevelOriginRef | None = None,
    label: str = "prior swing low",
) -> LevelReading:
    return LevelReading(
        price=Decimal(price),
        side=side,
        origin=origin if origin is not None else level_origin(),
        label=label,
    )


def _regime() -> RegimeReading:
    return RegimeReading(
        (
            RegimeDimensionReading("structure", "trending", ("higher highs",), ()),
            RegimeDimensionReading(
                "volatility", Absent("ATR still warming up"), (), ("atr_14",)
            ),
            RegimeDimensionReading("participation", "normal", (), ()),
        )
    )


def role_reading(
    role: SnapshotRole = SnapshotRole.CONTEXT, interval: str = "1d", **overrides: Any
) -> RoleReading:
    values: dict[str, Any] = {
        "role": role,
        "interval": interval,
        "as_of": AT(9),
        "closed_count": 300,
        "bar_age": 2,
        "structural_trend": "up",
        "sequence_state": "higher_high_higher_low",
        "nearest_level_above": level("64000", LevelSideRef.ABOVE, label="swing high"),
        "nearest_level_below": level(),
        "latest_break": Absent("none in window"),
        "latest_change_of_character": Absent("none in window"),
        "regime": _regime(),
    }
    values.update(overrides)
    return RoleReading(**values)


def _roles() -> tuple[RoleReading, ...]:
    return (
        role_reading(SnapshotRole.CONTEXT, "1d"),
        role_reading(SnapshotRole.SETUP, "4h"),
        role_reading(SnapshotRole.EXECUTION, "1h"),
    )


def sufficiency(state: str = "sufficient") -> SufficiencyReading:
    return SufficiencyReading(
        state=state,
        checks=(
            RequirementReading(
                "primary_data_depth",
                True,
                "blocking",
                "300 closed candles against 200 required",
                "fmis.market_structure",
            ),
            RequirementReading(
                "evidence_present",
                True,
                "blocking",
                "the evidence layer produced a reading",
                "fmis.decision_support",
            ),
        ),
    )


def anchor(
    direction: TradeDirection = TradeDirection.LONG,
    market: MarketId | None = None,
    book: Book = Book.SWING,
    origin: LevelOriginRef | None = None,
) -> Anchor:
    return Anchor(
        market=market if market is not None else MARKET,
        book=book,
        direction=direction,
        invalidation_origin=origin if origin is not None else level_origin(),
    )


def setup_reading(**overrides: Any) -> SetupReading:
    invalidation = overrides.pop("invalidation", level())
    values: dict[str, Any] = {
        "as_of": AT(9),
        "state": "candidate",
        "direction": TradeDirection.LONG,
        "policy_id": "swing-setup-v1",
        "thesis": "trend continuation retest",
        "directional_factors": ("trend up on context", "volume expanding"),
        "confirmation": Absent("no execution break yet"),
        "trigger": "close above 62000",
        "reference_price": Decimal("61500"),
        "invalidation": invalidation,
        "stop": invalidation,
        "targets": (level("64000", LevelSideRef.ABOVE, label="swing high"),),
        "risk_reward": RiskRewardReading(Decimal("3100"), Decimal("6200")),
        "probability": "NOT_CALIBRATED",
        "limitations": ("structure breaks are close-only",),
        "anchor": anchor(),
        "freshness": FreshnessReading(AT(9), 2, 1, 0),
        "stop_trigger_semantics": StopTriggerSemantics(
            TriggerBasis.TOUCH, TriggerBasis.CLOSE
        ),
    }
    values.update(overrides)
    return SetupReading(**values)


def consumed(record_id: str, digest_seed: str = "a", kind: str = "trade") -> ConsumedSource:
    return ConsumedSource(
        record_id=record_id,
        content_digest="sha256:" + (digest_seed * 64)[:64],
        kind=kind,
    )


def market_snapshot(**overrides: Any) -> MarketSnapshot:
    built_at = overrides.pop("built_at", AT(9))
    values: dict[str, Any] = {
        "market": MARKET,
        "built_at": built_at,
        "trigger": SnapshotTrigger.PROPOSAL_CREATED,
        "roles": _roles(),
        "sufficiency": sufficiency(),
        "evidence": (
            EvidenceFamilyReading("trend", "supports", "aligned", ("ema stack",)),
            EvidenceFamilyReading("context", "supports", "aligned", ("regime gate",)),
        ),
        "conflicts": (
            ConflictNote("timeframe", "setup and execution roles disagree on trend"),
        ),
        "setup": setup_reading(),
        "independence": IndependenceDisclosure(
            pair_kappas=(("context/trend", Decimal("0.41")),),
            family_participation=(("context", Decimal("1")),),
            sample_size=578,
            note="measured on the AW sample; superseded by the corrected harness",
            superseded_by=Absent("no later study loaded"),
        ),
        "analysis_record_ids": ("workspace-BTCUSDT-20260812T090000Z-0123456789abcdef",),
        "consumed_sources": (),
        "limitations": ("no order-book depth is ingested",),
        "decision_window_id": Absent("no window was captured"),
        "version_set": version_set(),
        "audit": RecordAudit.frozen_at(built_at),
    }
    values.update(overrides)
    return MarketSnapshot(**values)


def _bars(count: int = 5) -> tuple[WindowBar, ...]:
    return tuple(
        WindowBar(
            close_time=AT(0, day=1 + index),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("12.5"),
        )
        for index in range(count)
    )


def decision_window(mode: WindowMode = WindowMode.CAPTURE, **overrides: Any) -> DecisionWindow:
    bars = overrides.pop("bars", _bars())
    values: dict[str, Any] = {
        "market": MARKET,
        "interval": "1d",
        "first_close_time": bars[0].close_time,
        "last_close_time": bars[-1].close_time,
        "bar_count": len(bars),
        "series_digest": series_digest_of(bars),
        "mode": mode,
        "version_set": version_set(),
        "audit": RecordAudit.frozen_at(AT(9)),
        "bars": bars if mode is WindowMode.CAPTURE else (),
    }
    values.update(overrides)
    return DecisionWindow(**values)


def money(amount: str, asset: AssetCode = USDT) -> Money:
    return Money(Decimal(amount), asset)


def quantity(amount: str, asset: AssetCode = BTC) -> Quantity:
    return Quantity(Decimal(amount), asset)


def reason_tag(
    term_id: str = "thesis_no_longer_valid", vocabulary_id: str = "rejection_reason"
) -> VersionedTerm:
    return VersionedTerm(
        vocabulary_id=vocabulary_id, term_id=term_id, taxonomy_version=1
    )


def later(moment: datetime, *, hours: int = 1) -> datetime:
    return moment + timedelta(hours=hours)


def trade(**overrides: Any) -> "Trade":
    """A recorded BUY of 0.5 BTC at 60000 USDT, fee in USDT."""
    from fmis.ledger import LedgerSource, Trade, TradeSide

    occurred = overrides.pop("occurred_at", AT(10))
    values: dict[str, Any] = {
        "occurred_at": occurred,
        "recorded_at": occurred,
        "account": ACCOUNT,
        "book": Book.SWING,
        "market": MARKET,
        "side": TradeSide.BUY,
        "quantity": Quantity(Decimal("0.5"), BTC),
        "price": Decimal("60000"),
        "fee": Money(Decimal("15"), USDT),
        "fx_rate_to_tax_currency": Decimal("10.5"),
        "fx_source": "riksbank",
        "fx_timestamp": occurred,
        "source": LedgerSource.MANUAL,
        "asserted_by": "owner",
        "audit": RecordAudit.frozen_at(occurred),
    }
    values.update(overrides)
    return Trade(**values)


def correction(original: "Trade", replacement: "Trade", **overrides: Any) -> "Correction":
    from fmis.ledger import Correction

    occurred = overrides.pop("occurred_at", AT(11))
    values: dict[str, Any] = {
        "supersedes": original.event_id,
        "replacement": replacement,
        "reason": reason_tag("typed_the_wrong_quantity", "correction_reason"),
        "author": "owner",
        "occurred_at": occurred,
        "recorded_at": occurred,
        "audit": RecordAudit.frozen_at(occurred),
    }
    values.update(overrides)
    return Correction(**values)


__all__.extend(["trade", "correction"])


def proposal(**overrides: Any) -> "OpportunityProposal":
    """A policy-authored LONG proposal resting on the default market snapshot."""
    from fmis.proposal import (
        DirectionalAssessment,
        DirectionalCase,
        EvidenceCitation,
        OpportunityProposal,
        ProposalAuthor,
        StatedConfidence,
    )

    created = overrides.pop("created_at", AT(9))
    invalidation = overrides.pop("invalidation", level())
    values: dict[str, Any] = {
        "created_at": created,
        "valid_until": AT(9, day=15),
        "author": ProposalAuthor.DETERMINISTIC_POLICY,
        "market": MARKET,
        "book": Book.SWING,
        "direction": TradeDirection.LONG,
        "directional_assessment": DirectionalAssessment(
            DirectionalCase(
                TradeDirection.LONG, ("context trend up",), "continuation is supported"
            ),
            DirectionalCase(
                TradeDirection.SHORT, ("momentum stretched",), "the move is extended"
            ),
        ),
        "entry_conditions": ("close above 62000 on the execution role",),
        "invalidation": invalidation,
        "stop": invalidation,
        "take_profit_structure": (level("64000", LevelSideRef.ABOVE, label="swing high"),),
        "risk_reward": RiskRewardReading(Decimal("3100"), Decimal("6200")),
        "stated_confidence": StatedConfidence("moderate"),
        "supporting_evidence": (
            EvidenceCitation("trend", "ema stack aligned", "fmis.decision_support"),
        ),
        "opposing_evidence": (
            EvidenceCitation("momentum", "rsi extended", "fmis.decision_support"),
        ),
        "unavailable_evidence": ("order-book depth is not ingested",),
        "market_snapshot_id": market_snapshot().snapshot_id,
        "anchor": anchor(),
        "counterfactual_assumption_version": "counterfactual-v1",
        "version_set": version_set(),
        "audit": RecordAudit.frozen_at(created),
        "policy_id": "swing-setup-v1",
    }
    values.update(overrides)
    return OpportunityProposal(**values)


def lifecycle_event(
    subject: "OpportunityProposal", kind: Any, hour: int, **overrides: Any
) -> "ProposalLifecycleEvent":
    from fmis.proposal import MEASURED_KINDS, ProposalLifecycleEvent

    occurred = overrides.pop("occurred_at", AT(hour, day=13))
    values: dict[str, Any] = {
        "proposal_id": subject.proposal_id,
        "kind": kind,
        "occurred_at": occurred,
        "recorded_at": occurred,
        "audit": RecordAudit.frozen_at(occurred),
        "reason_tag": Absent("this kind is measured, not reasoned"),
        "causing_close_time": (
            occurred if kind in MEASURED_KINDS else Absent("asserted, not caused by a candle")
        ),
    }
    values.update(overrides)
    return ProposalLifecycleEvent(**values)


__all__.extend(["proposal", "lifecycle_event"])
