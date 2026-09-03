"""The vocabulary a research universe is described in. **Values, never comments.**

Milestone CB established that Milestone CA's experiment is `UNDERPOWERED` and that
the binding dimension is `cluster_count`: roughly 4,823 matched admissions, which
at CA's observed density is roughly 467 symbols. Milestone CC asks whether such a
universe can be built at all — and this module is the vocabulary that question is
asked in.

**One distinction does most of the work here.** A *trading pair* is a market. An
*economic asset* is a thing the market prices. `BTCUSDT` and `BTCUSDC` are two
pairs and one asset; `WBTCUSDT` is a third pair and still that same asset. A
universe that counted pairs would report three independent experimental clusters
where there is at most one, and every ``1/sqrt(K)`` term downstream would be
wrong by that factor. `EconomicAsset` exists so the inflation is impossible rather
than discouraged.

**Every exclusion carries a machine-readable reason.** `ExclusionReason` is an
enum and `Exclusion` requires a non-empty detail sentence alongside it, because a
funnel that narrowed from 3,645 instruments to a few dozen without saying which
rule removed each one is not a filter — it is an assertion.

**No verdict here approves anything.** `FeasibilityVerdict` answers whether an
experiment *could be built*, never whether a strategy works or may trade.
`is_approved_for_trading` is `False` for every member and a test asserts it over
the whole enum, exactly as Milestone CA asserts it over `CaVerdict`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

__all__ = [
    "UniverseError",
    "AssetClass",
    "PairStatus",
    "TradingPair",
    "EconomicAsset",
    "FunnelStage",
    "ExclusionReason",
    "Exclusion",
    "CoverageMetrics",
    "QualityMetrics",
    "LiquidityEvidence",
    "AssetAssessment",
    "SurvivorshipClass",
    "FeasibilityVerdict",
    "require_text",
    "require_count",
    "require_fraction",
    "require_aware",
]


class UniverseError(Exception):
    """A universe that cannot be described as stated."""


# ---------------------------------------------------------------- validation ---


def require_text(value: Any, field: str) -> str:
    """A non-empty string, or a refusal naming the field.

    Used by every reason and detail slot in this package. An exclusion whose
    reason is the empty string is indistinguishable from an exclusion nobody
    wrote down, and the funnel's whole claim is that no such exclusion exists.
    """
    if not isinstance(value, str) or not value.strip():
        raise UniverseError(f"{field} must be a non-empty str")
    return value


def require_count(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UniverseError(f"{field} must be an int, got {type(value).__name__}")
    if value < minimum:
        raise UniverseError(f"{field} must be >= {minimum}, got {value}")
    return value


def require_fraction(value: Any, field: str, *, low: float = 0.0, high: float = 1.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UniverseError(f"{field} must be a real number")
    number = float(value)
    if number != number:  # NaN compares false against every bound
        raise UniverseError(f"{field} must be a real number, got NaN")
    if not low <= number <= high:
        raise UniverseError(f"{field} must lie in [{low}, {high}], got {number}")
    return number


def require_aware(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise UniverseError(f"{field} must be a datetime, got {type(value).__name__}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise UniverseError(
            f"{field} must be timezone-aware; a naive instant is a different "
            "moment on two machines and a universe boundary cannot be one"
        )
    return value.astimezone(timezone.utc)


# ------------------------------------------------------------------ identity ---


class AssetClass(Enum):
    """What kind of thing a base asset is. **Decided by rule, never by taste.**

    The classification exists to stop three specific inflations of the cluster
    count, each of which would make a universe look more informative than it is:

    * a **stablecoin** tracks a peg, so its returns are the peg's noise. A
      trend-following admission rule measured on one is measuring nothing, and its
      near-zero volatility would dominate every volatility-normalised statistic.
      Milestone BY dropped TUSDUSDT and USDCUSDT for exactly this reason.
    * a **wrapped** representation is the same economic exposure through a
      different token. WBTC and BTC are one asset priced twice.
    * a **leveraged token** is a derivative of an asset already in the universe,
      with its own decay. Counting it as an independent cluster counts BTC twice
      and then claims the second copy is new information.
    """

    NATIVE = "native"
    STABLECOIN = "stablecoin"
    WRAPPED = "wrapped"
    LEVERAGED_TOKEN = "leveraged_token"

    @property
    def may_be_an_independent_cluster(self) -> bool:
        """Whether an asset of this class can stand as its own experimental unit."""
        return self is AssetClass.NATIVE


class PairStatus(Enum):
    """Whether the provider still trades this pair. **A research fact, not a bug.**

    Binance retains halted spot pairs in `exchangeInfo` with ``status="BREAK"`` and
    continues to serve their klines up to the instant they stopped trading. That
    retention is the only reason a survivorship question can be asked of this
    provider at all: a `HALTED` pair is an instrument that *disappeared*, and a
    universe holding some of them is measurably less survivor-biased than one
    holding none.
    """

    TRADING = "trading"
    HALTED = "halted"

    @classmethod
    def from_provider(cls, status: str) -> "PairStatus":
        """Map a provider status word. **Anything not TRADING is halted.**

        Binance documents ``TRADING``, ``BREAK`` and ``HALT``; the conservative
        reading of an unfamiliar word is that the pair is not currently tradable,
        because the alternative — assuming it trades — would admit an instrument
        into a tradability filter it never passed.
        """
        require_text(status, "provider status")
        return cls.TRADING if status.upper() == "TRADING" else cls.HALTED

    @property
    def is_current_survivor(self) -> bool:
        return self is PairStatus.TRADING


@dataclass(frozen=True, slots=True)
class TradingPair:
    """One market, as the provider lists it. **A pair is not an asset.**

    Carries provider identity only. Everything economic — what this pair is
    exposure to, whether that exposure is already in the universe — is
    `EconomicAsset`'s and is deliberately not reachable from here.
    """

    symbol: str
    base_asset: str
    quote_asset: str
    status: PairStatus

    def __post_init__(self) -> None:
        require_text(self.symbol, "symbol")
        require_text(self.base_asset, "base_asset")
        require_text(self.quote_asset, "quote_asset")
        if not isinstance(self.status, PairStatus):
            raise UniverseError("status must be a PairStatus")
        if self.base_asset == self.quote_asset:
            raise UniverseError(
                f"pair {self.symbol!r} quotes {self.base_asset} in itself; that is "
                "not a market, it is a malformed listing"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class EconomicAsset:
    """One thing the market prices, and every pair that prices it.

    ``asset_id`` is the canonical economic identity — ``"BTC"`` for BTC, WBTC and
    BTCUP alike. ``representative`` is the single pair chosen to stand for it,
    by a sealed deterministic rule, so that the universe holds exactly one series
    per economic exposure. Every other pair is recorded in ``pairs`` and excluded
    with `ExclusionReason.DUPLICATE_ECONOMIC_EXPOSURE`, never silently dropped.
    """

    asset_id: str
    asset_class: AssetClass
    representative: TradingPair
    pairs: tuple[TradingPair, ...]
    identity_rule: str

    def __post_init__(self) -> None:
        require_text(self.asset_id, "asset_id")
        require_text(self.identity_rule, "identity_rule")
        if not isinstance(self.asset_class, AssetClass):
            raise UniverseError("asset_class must be an AssetClass")
        if not isinstance(self.representative, TradingPair):
            raise UniverseError("representative must be a TradingPair")
        if not isinstance(self.pairs, tuple) or not self.pairs:
            raise UniverseError(
                f"economic asset {self.asset_id!r} holds no pairs; an asset with no "
                "market has no price series and cannot be an experimental unit"
            )
        for pair in self.pairs:
            if not isinstance(pair, TradingPair):
                raise UniverseError("every entry of pairs must be a TradingPair")
        if self.representative not in self.pairs:
            raise UniverseError(
                f"economic asset {self.asset_id!r} nominates {self.representative.symbol!r} "
                "as its representative, which is not among its own pairs"
            )

    @property
    def duplicate_pairs(self) -> tuple[TradingPair, ...]:
        """Every pair this asset holds except the representative one."""
        return tuple(pair for pair in self.pairs if pair != self.representative)

    def payload(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_class": self.asset_class.value,
            "representative": self.representative.symbol,
            "pairs": [pair.payload() for pair in self.pairs],
            "identity_rule": self.identity_rule,
        }


# -------------------------------------------------------------------- funnel ---


class FunnelStage(Enum):
    """Where in the staged assessment an instrument was removed.

    The order is the order the stages run in, and it is deliberately cheapest
    first: everything before `HISTORICAL_DEPTH` is decided from provider metadata
    alone, so no candle is downloaded for an instrument a name-level rule already
    refused.
    """

    DISCOVERED = "discovered"
    QUOTE_CURRENCY = "quote_currency"
    ASSET_CLASS = "asset_class"
    ECONOMIC_IDENTITY = "economic_identity"
    HISTORICAL_DEPTH = "historical_depth"
    DATA_QUALITY = "data_quality"
    LIQUIDITY = "liquidity"

    @property
    def needs_candles(self) -> bool:
        """Whether reaching this stage costs a market-data download."""
        return self in (
            FunnelStage.HISTORICAL_DEPTH,
            FunnelStage.DATA_QUALITY,
            FunnelStage.LIQUIDITY,
        )


class ExclusionReason(Enum):
    """Why one instrument is not in the research universe. **Never absent.**

    Each member names one rule. The set is closed: `assess` refuses to remove an
    instrument for a reason not listed here, so a funnel cannot acquire an
    undocumented filter by accident.
    """

    QUOTE_CURRENCY_NOT_ELIGIBLE = "quote_currency_not_eligible"
    BASE_IS_STABLECOIN = "base_is_stablecoin"
    BASE_IS_WRAPPED_REPRESENTATION = "base_is_wrapped_representation"
    BASE_IS_LEVERAGED_TOKEN = "base_is_leveraged_token"
    DUPLICATE_ECONOMIC_EXPOSURE = "duplicate_economic_exposure"
    NO_HISTORY_AVAILABLE = "no_history_available"
    INSUFFICIENT_HISTORY_FOR_WARMUP = "insufficient_history_for_warmup"
    INSUFFICIENT_MEASUREMENT_COVERAGE = "insufficient_measurement_coverage"
    INSUFFICIENT_FORWARD_WINDOW = "insufficient_forward_window"
    EXCESSIVE_MISSING_BARS = "excessive_missing_bars"
    EXCESSIVE_GAP = "excessive_gap"
    DUPLICATE_BARS = "duplicate_bars"
    MALFORMED_BARS = "malformed_bars"
    INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"
    NO_LIQUIDITY_EVIDENCE = "no_liquidity_evidence"

    @property
    def stage(self) -> FunnelStage:
        """Which funnel stage owns this reason. **One owner each.**"""
        return _REASON_STAGES[self]


_REASON_STAGES: dict[ExclusionReason, FunnelStage] = {
    ExclusionReason.QUOTE_CURRENCY_NOT_ELIGIBLE: FunnelStage.QUOTE_CURRENCY,
    ExclusionReason.BASE_IS_STABLECOIN: FunnelStage.ASSET_CLASS,
    ExclusionReason.BASE_IS_WRAPPED_REPRESENTATION: FunnelStage.ASSET_CLASS,
    ExclusionReason.BASE_IS_LEVERAGED_TOKEN: FunnelStage.ASSET_CLASS,
    ExclusionReason.DUPLICATE_ECONOMIC_EXPOSURE: FunnelStage.ECONOMIC_IDENTITY,
    ExclusionReason.NO_HISTORY_AVAILABLE: FunnelStage.HISTORICAL_DEPTH,
    ExclusionReason.INSUFFICIENT_HISTORY_FOR_WARMUP: FunnelStage.HISTORICAL_DEPTH,
    ExclusionReason.INSUFFICIENT_MEASUREMENT_COVERAGE: FunnelStage.HISTORICAL_DEPTH,
    ExclusionReason.INSUFFICIENT_FORWARD_WINDOW: FunnelStage.HISTORICAL_DEPTH,
    ExclusionReason.EXCESSIVE_MISSING_BARS: FunnelStage.DATA_QUALITY,
    ExclusionReason.EXCESSIVE_GAP: FunnelStage.DATA_QUALITY,
    ExclusionReason.DUPLICATE_BARS: FunnelStage.DATA_QUALITY,
    ExclusionReason.MALFORMED_BARS: FunnelStage.DATA_QUALITY,
    ExclusionReason.INSUFFICIENT_LIQUIDITY: FunnelStage.LIQUIDITY,
    ExclusionReason.NO_LIQUIDITY_EVIDENCE: FunnelStage.LIQUIDITY,
}


@dataclass(frozen=True, slots=True)
class Exclusion:
    """One instrument, one rule, one sentence saying what the rule measured.

    ``detail`` is required and must be non-empty. A reason code says *which* rule
    fired; the detail says *what number* made it fire, and without the second a
    reader cannot tell a threshold that was missed by a hair from one missed by an
    order of magnitude.
    """

    symbol: str
    reason: ExclusionReason
    detail: str

    def __post_init__(self) -> None:
        require_text(self.symbol, "symbol")
        if not isinstance(self.reason, ExclusionReason):
            raise UniverseError("reason must be an ExclusionReason")
        require_text(self.detail, "exclusion detail")

    @property
    def stage(self) -> FunnelStage:
        return self.reason.stage

    def payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "stage": self.stage.value,
            "reason": self.reason.value,
            "detail": self.detail,
        }


# ------------------------------------------------------------------ measured ---


@dataclass(frozen=True, slots=True)
class CoverageMetrics:
    """How much usable history one instrument actually has.

    Every field is knowable from bar *timestamps* — none reads a price, and none
    reads a strategy outcome. That is what lets coverage decide eligibility
    without touching the protected holdout's results, and a control asserts it.
    """

    symbol: str
    first_bar: datetime
    last_bar: datetime
    bars_observed: int
    bars_expected: int
    duplicate_bars: int
    malformed_bars: int
    longest_gap_bars: int

    def __post_init__(self) -> None:
        require_text(self.symbol, "symbol")
        require_aware(self.first_bar, "first_bar")
        require_aware(self.last_bar, "last_bar")
        require_count(self.bars_observed, "bars_observed")
        require_count(self.bars_expected, "bars_expected", minimum=1)
        require_count(self.duplicate_bars, "duplicate_bars")
        require_count(self.malformed_bars, "malformed_bars")
        require_count(self.longest_gap_bars, "longest_gap_bars")
        if self.last_bar < self.first_bar:
            raise UniverseError(
                f"{self.symbol}: last bar {self.last_bar.isoformat()} precedes "
                f"first bar {self.first_bar.isoformat()}"
            )

    @property
    def missing_fraction(self) -> float:
        """The share of expected bars the provider did not return.

        Clamped at zero rather than allowed to go negative: a provider returning
        *more* bars than the calendar expects is a duplicate problem, and
        ``duplicate_bars`` is where that is reported. A negative missing fraction
        would read as unusually complete data, which is the opposite of the truth.
        """
        return max(0.0, 1.0 - self.bars_observed / self.bars_expected)

    @property
    def usable_years(self) -> float:
        return (self.last_bar - self.first_bar).days / 365.25

    def payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "first_bar": self.first_bar.isoformat(),
            "last_bar": self.last_bar.isoformat(),
            "bars_observed": self.bars_observed,
            "bars_expected": self.bars_expected,
            "duplicate_bars": self.duplicate_bars,
            "malformed_bars": self.malformed_bars,
            "longest_gap_bars": self.longest_gap_bars,
            "missing_fraction": self.missing_fraction,
            "usable_years": self.usable_years,
        }


@dataclass(frozen=True, slots=True)
class QualityMetrics:
    """Whether one instrument's bars are usable, and which rule says otherwise."""

    symbol: str
    missing_fraction: float
    longest_gap_bars: int
    duplicate_bars: int
    malformed_bars: int

    def __post_init__(self) -> None:
        require_text(self.symbol, "symbol")
        require_fraction(self.missing_fraction, "missing_fraction")
        require_count(self.longest_gap_bars, "longest_gap_bars")
        require_count(self.duplicate_bars, "duplicate_bars")
        require_count(self.malformed_bars, "malformed_bars")

    def payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "missing_fraction": self.missing_fraction,
            "longest_gap_bars": self.longest_gap_bars,
            "duplicate_bars": self.duplicate_bars,
            "malformed_bars": self.malformed_bars,
        }


@dataclass(frozen=True, slots=True)
class LiquidityEvidence:
    """What can honestly be said about whether this market was tradable.

    ``median_quote_volume`` is measured **inside the research window**, never from
    today's book. Today's liquidity is evidence about today; a universe that
    admitted an instrument because it is liquid *now* would be selecting on
    information the study period did not have, and for a delisted instrument it
    would be selecting on information that does not exist.

    ``is_measured`` is `False` when the window held no volume data at all. That is
    a different statement from "illiquid", and the two are kept apart because one
    is a fact about the market and the other is a fact about the record.
    """

    symbol: str
    median_quote_volume: float | None
    observed_days: int
    window_start: datetime
    window_end: datetime
    source: str

    def __post_init__(self) -> None:
        require_text(self.symbol, "symbol")
        require_text(self.source, "liquidity source")
        require_count(self.observed_days, "observed_days")
        require_aware(self.window_start, "window_start")
        require_aware(self.window_end, "window_end")
        if self.window_end <= self.window_start:
            raise UniverseError(
                f"{self.symbol}: liquidity window ends at or before it starts"
            )
        if self.median_quote_volume is not None:
            if isinstance(self.median_quote_volume, bool) or not isinstance(
                self.median_quote_volume, (int, float)
            ):
                raise UniverseError("median_quote_volume must be a real number or None")
            if float(self.median_quote_volume) < 0.0:
                raise UniverseError(
                    f"{self.symbol}: median quote volume "
                    f"{self.median_quote_volume} is negative, which no traded "
                    "notional can be"
                )
            if not self.observed_days:
                raise UniverseError(
                    f"{self.symbol}: a median quote volume was reported over zero "
                    "observed days. A statistic with no observations behind it is "
                    "the impossible-evidence case this field exists to refuse"
                )
        elif self.observed_days:
            raise UniverseError(
                f"{self.symbol}: {self.observed_days} observed day(s) produced no "
                "median. Days without a median is a computation that was skipped, "
                "not a market without volume"
            )

    @property
    def is_measured(self) -> bool:
        return self.median_quote_volume is not None

    def payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "median_quote_volume": self.median_quote_volume,
            "observed_days": self.observed_days,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class AssetAssessment:
    """One economic asset's complete decision, with everything that decided it."""

    asset: EconomicAsset
    coverage: CoverageMetrics | None
    quality: QualityMetrics | None
    liquidity: LiquidityEvidence | None
    eligible: bool
    exclusion: Exclusion | None

    def __post_init__(self) -> None:
        if not isinstance(self.asset, EconomicAsset):
            raise UniverseError("asset must be an EconomicAsset")
        if not isinstance(self.eligible, bool):
            raise UniverseError("eligible must be a bool")
        if self.eligible and self.exclusion is not None:
            raise UniverseError(
                f"{self.asset.asset_id}: an eligible asset carries an exclusion "
                f"({self.exclusion.reason.value}). One of the two is wrong and a "
                "funnel that reported both would be uncountable"
            )
        if not self.eligible and self.exclusion is None:
            raise UniverseError(
                f"{self.asset.asset_id}: excluded with no reason. Every exclusion "
                "must be attributable to a named rule"
            )

    @property
    def symbol(self) -> str:
        return self.asset.representative.symbol

    def payload(self) -> dict[str, Any]:
        return {
            "asset": self.asset.payload(),
            "coverage": None if self.coverage is None else self.coverage.payload(),
            "quality": None if self.quality is None else self.quality.payload(),
            "liquidity": None if self.liquidity is None else self.liquidity.payload(),
            "eligible": self.eligible,
            "exclusion": None if self.exclusion is None else self.exclusion.payload(),
        }


# -------------------------------------------------------------- survivorship ---


class SurvivorshipClass(Enum):
    """How much of the disappeared universe this one can see. **Never flattered.**

    `SURVIVORSHIP_AWARE` requires that every instrument which ever traded and met
    the criteria is recoverable. No public exchange endpoint this repository can
    reach makes that promise, so the member exists to be *unreachable* by the
    current provider path rather than to be claimed — and a hostile test asserts
    that a current-survivor-only universe can never be labelled with it.
    """

    SURVIVORSHIP_AWARE = "survivorship_aware"
    PARTIALLY_SURVIVORSHIP_AWARE = "partially_survivorship_aware"
    CURRENT_SURVIVOR_ONLY = "current_survivor_only"

    @property
    def is_unbiased(self) -> bool:
        return self is SurvivorshipClass.SURVIVORSHIP_AWARE


# ------------------------------------------------------------------- verdict ---


class FeasibilityVerdict(Enum):
    """Whether the question can be *asked*. **No member says it was answered.**

    Every one of these is a statement about experimental design. None approves
    trading, paper trading, shadow trading or a strategy, and none says whether an
    admission edge exists — CA's `NO_EDGE` stands regardless of what CC concludes.
    """

    FEASIBLE = "feasible"
    FEASIBLE_WITH_LIMITATIONS = "feasible_with_limitations"
    INFEASIBLE = "infeasible"
    INDETERMINATE = "indeterminate"

    @property
    def is_approved_for_trading(self) -> bool:
        """**Always False.** Asserted over the whole enum by a hostile test."""
        return False

    @property
    def earns_forward_test(self) -> bool:
        """**Always False.** Feasibility is not permission of any kind."""
        return False

    @property
    def says_nothing_about_the_hypothesis(self) -> bool:
        """**Always True.** CC measures information, never edge."""
        return True

    @property
    def target_is_reachable(self) -> bool:
        """Whether the primary target could be tested under the sealed assumptions."""
        return self in (
            FeasibilityVerdict.FEASIBLE,
            FeasibilityVerdict.FEASIBLE_WITH_LIMITATIONS,
        )
