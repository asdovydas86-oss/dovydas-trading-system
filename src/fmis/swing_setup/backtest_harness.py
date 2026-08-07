"""The deterministic Swing Setup historical backtest harness (Milestone AV).

    run_backtest(symbols, start_time=..., end_time=..., run_at=...)  ──►  BacktestRun

**What this answers.** "What would the CURRENT Swing Setup v1 policy have
produced historically?" — nothing more. This module adds no strategy, no
scoring, no probability and no realized PnL. It replays real historical
closed-candle prefixes through the **unmodified** production composition
path (`fmis.swing_setup.compose.setup_inputs_and_assessment_for_sheet`, via
`fmis.pipeline.multi_timeframe.multi_timeframe_facts_for_symbol`), and
records what that path said at each instant.

**No lookahead, by construction of the replay transport.** For simulated
instant ``T`` the harness builds a `Transport`
(`fmis.swing_setup.backtest_replay.build_replay_transport`) bound to ``T``
and a matching fixed ``clock``. Every fact the composition path reads —
candles, regime, evidence, decision context, the setup assessment itself —
is a pure function of what that transport and clock exposed, and both
independently enforce ``close_time < T``. See `backtest_replay`'s module
docstring for the two-independent-check argument in full.

**Outcome evaluation is the one place look-forward is correct.**
`fmis.swing_setup.backtest_outcomes.evaluate_outcome` reads the *full*
historical execution series, deliberately, because judging what happened
after a confirmed setup requires seeing after it. It never feeds back into
an earlier instant's decision.

**One evaluation per confirmed setup, not one per bar.**
`fmis.swing_setup.backtest_identity.IdentityTracker` is walked in
chronological order per symbol; only the first bar at which a given identity
reaches `CONFIRMED` triggers an outcome evaluation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Final

from fmis.decision_context import ContextPolicy
from fmis.ingest import decode_candle_series
from fmis.market_regime import RegimePolicy
from fmis.pipeline.market_analysis import InsufficientDataError
from fmis.pipeline.multi_timeframe import (
    DEFAULT_TIMEFRAMES,
    TimeframeRole,
    multi_timeframe_facts_for_symbol,
)
from fmis.pipeline.regime import regime_features
from fmis.pipeline.structural_facts import DetectionSettings
from fmis.providers.binance import Transport, map_kline
from fmis.data import CandleSeries
from fmis.swing_setup.backtest_identity import IdentityTracker
from fmis.swing_setup.backtest_models import (
    BACKTEST_SCHEMA_VERSION,
    BacktestError,
    BacktestRun,
    DataBoundary,
    FamilyLean,
    HistoricalObservation,
    SetupOutcome,
)
from fmis.swing_setup.backtest_outcomes import evaluate_outcome
from fmis.swing_setup.backtest_replay import (
    CLOSE_TIME_INDEX,
    build_replay_transport,
    fetch_historical_dataset,
    from_epoch_ms,
)
from fmis.swing_setup.compose import setup_inputs_and_assessment_for_sheet
from fmis.swing_setup.models import SetupState
from fmis.swing_setup.policy import SETUP_POLICY_ID

__all__ = [
    "DEFAULT_EVALUATION_WINDOW_BARS",
    "DEFAULT_BACKTEST_LIMIT",
    "DEFAULT_BACKTEST_SYMBOLS",
    "DEFAULT_BACKTEST_DAYS",
    "BACKTEST_LIMITATIONS",
    "run_backtest",
]

#: The task brief's own suggested first-serious-run universe: ten liquid
#: crypto pairs, distinct from (and smaller than) `fmis.swing_setup.scan`'s
#: twenty-symbol `SCAN_UNIVERSE` — this is a measurement run, not a scan, and
#: keeping its own explicit list avoids the two silently drifting together.
DEFAULT_BACKTEST_SYMBOLS: Final[tuple[str, ...]] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "DOTUSDT",
)

#: A default lookback the CLI applies when ``--start`` is omitted. 400 days —
#: not 180 — because the context-role (1w) regime structure dimension needs
#: `fmis.market_regime`'s moving-average family, which needs EMA(50) on 50
#: closed weekly candles (roughly 350 days) before it can classify anything
#: at all; a shorter default would spend most of the window unable to
#: produce a directional candidate for a reason that has nothing to do with
#: the market. Chosen for that structural reason and for compute
#: tractability at the default ten-symbol, 4H-execution scope (see the
#: design record) — not for a favourable result. The task brief forbids
#: choosing a period to make the policy look better, and this constant is
#: fixed before any run's results are seen.
DEFAULT_BACKTEST_DAYS: Final[int] = 400

#: The execution role's confirmation-lookback constant is 10 bars
#: (`fmis.swing_setup.policy.CONFIRMATION_LOOKBACK_BARS`). 60 execution-role
#: bars — six times that window, ten days on the default 4H execution role —
#: is a conservative, stated v1 measurement policy, not a tuned or optimised
#: value: this milestone measures the existing policy and forbids changing it
#: to make results look better, and that discipline extends to this constant.
DEFAULT_EVALUATION_WINDOW_BARS: Final[int] = 60

#: Candles requested per role per analysis instant. Structural detection
#: needs `market_structure.required_candles` (5 with default 2/2 bars) —
#: this is generous headroom for the structural chain and for feature
#: warm-up without paying the full 1000-candle maximum's structural-chain
#: cost (`derive_level_crossings` is documented as
#: O(candles × levels)) at every one of thousands of simulated instants.
DEFAULT_BACKTEST_LIMIT: Final[int] = 250

#: A UTC instant after any real historical candle this harness will ever
#: replay, used only to decode the *full* execution series for outcome
#: evaluation — a series already entirely in the past is unconditionally
#: "closed" regardless of which instant marks it so.
_FAR_FUTURE: Final[datetime] = datetime(2100, 1, 1, tzinfo=timezone.utc)

BACKTEST_LIMITATIONS: tuple[str, ...] = (
    "AV-1: This measures the existing Swing Setup v1 policy exactly as it "
    "stands. It is not a portfolio backtest: no fees, slippage, spread or "
    "execution delay are modelled, and no position sizing is applied.",
    "AV-2: Printed R:R is not realized PnL. TARGET_FIRST/STOP_FIRST describe "
    "which level price touched first (by wick, not by close); they are not "
    "a win rate and not a claim of profitability.",
    "AV-3: A same-bar touch of both stop and target is reported as "
    "AMBIGUOUS_SAME_BAR — OHLC data cannot establish intrabar order, and "
    "this harness does not guess one from candle colour or any other proxy.",
    "AV-4: Entry reference is the execution-timeframe close at the "
    "confirming bar — the same reference the live product prints. No fill "
    "at a wick, and no next-bar-open assumption, is made.",
    "AV-5: Setup identity is derived from the confirming/watched structural "
    "level's origin (index and label). A level with no origin falls back to "
    "its price; a candidate with no watched level falls back to direction "
    "only. Either fallback can under- or over-count distinct setups that "
    "share a price or lack a level.",
    "AV-6: NEITHER_WITHIN_WINDOW does not distinguish 'price never reached "
    "either level' from 'the historical dataset ended before the window "
    "did' — both look identical from this harness's own record.",
    "AV-7: The evaluation window (60 execution-role bars) is a stated "
    "measurement policy, not a backtested or optimised value, and was fixed "
    "before any result was seen.",
    "AV-8: Every limitation `fmis.swing_setup` itself already carries "
    "(uncalibrated probability, no position sizing, nearest-detected-level "
    "stops/targets, the 10-bar confirmation lookback) applies unchanged to "
    "every historical observation this harness records.",
    "AV-9: The RR/stop/target geometry distributions measure each setup "
    "occurrence's formation bar only (the first bar it became CANDIDATE or "
    "CONFIRMED). A later bar in the same occurrence may have read a "
    "different stop or target as new structural levels formed; that later "
    "geometry is not separately measured.",
)


def _decode_full_series(symbol: str, interval: str, rows: Sequence[Sequence[Any]]) -> CandleSeries:
    """Decode a raw historical kline cache into its full closed `CandleSeries`.

    Reuses `fmis.providers.binance.map_kline` and
    `fmis.ingest.decode_candle_series` exactly as `fetch_klines` does — the
    only difference is the rows come from the pre-fetched cache rather than
    a live HTTP call. ``now_ms`` is stamped far in the future because every
    row here is already, unconditionally, historical.
    """
    now_ms = round(_FAR_FUTURE.timestamp() * 1000)
    records = [
        map_kline(raw, symbol=symbol, interval=interval, now_ms=now_ms, index=i)
        for i, raw in enumerate(rows)
    ]
    series = decode_candle_series(records, symbol=symbol, timeframe=interval)
    return series.closed()


def run_backtest(
    symbols: Sequence[str],
    *,
    start_time: datetime,
    end_time: datetime,
    run_at: datetime,
    timeframes: Mapping[TimeframeRole, str] | None = None,
    limit: int | None = None,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
    evaluation_window_bars: int = DEFAULT_EVALUATION_WINDOW_BARS,
    transport: Transport | None = None,
    base_url: str | None = None,
) -> BacktestRun:
    """Replay the Swing Setup v1 policy over real historical candles. Deterministic.

    For each requested symbol, and for each execution-role candle close
    inside ``[start_time, end_time]``, this simulates "what would `fmits
    setup SYMBOL` have said, right then" by calling the unmodified
    production composition path against a replay transport that can only see
    candles already closed at that instant. Results are recorded in
    requested-symbol order, chronologically within each symbol.

    ``run_at`` is a required, caller-supplied stamp (this module reads no
    wall clock of its own, matching every composition root in this
    repository) used for `BacktestRun.created_at` and every
    `DataBoundary.fetched_at`.

    Two calls with equal arguments and an equal historical dataset (i.e. an
    equal ``transport``) return an equal `BacktestRun`, ``run_at`` aside.

    Raises:
        BacktestError: bad arguments, or a historical fetch failed.
        Any exception `multi_timeframe_facts_for_symbol` or
            `setup_inputs_and_assessment_for_sheet` raises other than
            `InsufficientDataError` — a defect in this repository must not be
            silently absorbed into a market-shaped result.
    """
    if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence) or not symbols:
        raise BacktestError("symbols must be a non-empty, non-string sequence")
    for symbol in symbols:
        if not isinstance(symbol, str) or not symbol.strip():
            raise BacktestError("every symbol must be a non-empty str")
    if not isinstance(start_time, datetime) or start_time.utcoffset() is None:
        raise BacktestError("start_time must be a timezone-aware datetime")
    if not isinstance(end_time, datetime) or end_time.utcoffset() is None:
        raise BacktestError("end_time must be a timezone-aware datetime")
    if start_time >= end_time:
        raise BacktestError("start_time must be before end_time")
    if not isinstance(run_at, datetime) or run_at.utcoffset() is None:
        raise BacktestError("run_at must be a timezone-aware datetime")
    if isinstance(evaluation_window_bars, bool) or not isinstance(evaluation_window_bars, int):
        raise BacktestError("evaluation_window_bars must be an int")
    if evaluation_window_bars <= 0:
        raise BacktestError("evaluation_window_bars must be positive")

    requested = dict(DEFAULT_TIMEFRAMES if timeframes is None else timeframes)
    missing = [role for role in TimeframeRole if role not in requested]
    if missing:
        raise BacktestError(
            f"timeframes must map every role; missing {[r.value for r in missing]}"
        )
    execution_interval = requested[TimeframeRole.EXECUTION]
    distinct_intervals = tuple(sorted(set(requested.values())))
    chosen_limit = DEFAULT_BACKTEST_LIMIT if limit is None else limit
    settings = DetectionSettings() if detection is None else detection

    cache, boundaries = fetch_historical_dataset(
        symbols,
        distinct_intervals,
        start_time=start_time,
        end_time=end_time,
        fetched_at=run_at,
        transport=transport,
        base_url=base_url,
    )

    observations: list[HistoricalObservation] = []
    outcomes: list[SetupOutcome] = []
    tracker = IdentityTracker()

    for symbol in symbols:
        execution_rows = cache[(symbol, execution_interval)]
        full_execution_series = _decode_full_series(symbol, execution_interval, execution_rows)
        instants = sorted(
            {from_epoch_ms(row[CLOSE_TIME_INDEX] + 1) for row in execution_rows}
        )

        for instant in instants:
            replay_transport = build_replay_transport(cache, now=instant)
            try:
                sheet = multi_timeframe_facts_for_symbol(
                    symbol,
                    timeframes=requested,
                    limit=chosen_limit,
                    features=regime_features(),
                    detection=settings,
                    transport=replay_transport,
                    clock=lambda moment=instant: moment,
                    base_url=base_url,
                )
                inputs, assessment = setup_inputs_and_assessment_for_sheet(
                    sheet, policy=policy, context_policy=context_policy
                )
            except InsufficientDataError:
                continue

            execution_view = sheet.by_role[TimeframeRole.EXECUTION]
            trigger = assessment.trigger
            setup_id, is_new_setup, is_first_confirmation = tracker.observe(
                symbol, assessment.direction, trigger, assessment.state
            )

            observations.append(
                HistoricalObservation(
                    symbol=symbol,
                    as_of=assessment.as_of,
                    status=assessment.state,
                    direction=assessment.direction,
                    setup_id=setup_id,
                    is_new_setup=is_new_setup,
                    directional_factors=tuple(
                        FamilyLean(family=factor.family, lean=factor.lean.value)
                        for factor in assessment.directional_factors
                    ),
                    thesis=assessment.thesis,
                    confirmation=assessment.confirmation,
                    trigger_kind=None if trigger is None else trigger.kind.value,
                    trigger_price=(
                        None if trigger is None or trigger.level is None
                        else trigger.level.price
                    ),
                    reference_price=assessment.reference_price,
                    stop_price=None if assessment.stop is None else assessment.stop.price,
                    target_price=(
                        None if not assessment.targets else assessment.targets[0].price
                    ),
                    risk_reward_ratio=(
                        None if assessment.risk_reward is None
                        else assessment.risk_reward.ratio
                    ),
                    sufficiency=assessment.sufficiency.value,
                    context_regime_structure=inputs.context_regime_structure.value,
                    context_regime_volatility=inputs.context_regime_volatility.value,
                    context_regime_participation=inputs.context_regime_participation.value,
                    execution_last_timestamp=execution_view.sheet.window.last_timestamp,
                    policy_id=assessment.policy_id,
                )
            )

            if (
                is_first_confirmation
                and assessment.risk_reward is not None
                and assessment.stop is not None
                and assessment.targets
                and assessment.reference_price is not None
                and execution_view.sheet.window.last_timestamp is not None
            ):
                outcomes.append(
                    evaluate_outcome(
                        full_execution_series,
                        setup_id=setup_id,
                        symbol=symbol,
                        direction=assessment.direction,
                        confirmed_at=execution_view.sheet.window.last_timestamp,
                        reference_price=assessment.reference_price,
                        stop_price=assessment.stop.price,
                        target_price=assessment.targets[0].price,
                        risk_reward_ratio=assessment.risk_reward.ratio,
                        window_bars=evaluation_window_bars,
                    )
                )

    return BacktestRun(
        schema_version=BACKTEST_SCHEMA_VERSION,
        created_at=run_at,
        symbols=tuple(symbols),
        timeframes={role.value: interval for role, interval in requested.items()},
        evaluation_window_bars=evaluation_window_bars,
        data_boundaries=boundaries,
        policy_id=SETUP_POLICY_ID,
        context_policy_id=(
            ContextPolicy().policy_id if context_policy is None else context_policy.policy_id
        ),
        observations=tuple(observations),
        outcomes=tuple(outcomes),
        limitations=BACKTEST_LIMITATIONS,
    )
