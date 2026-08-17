"""Paper trading: the complete deterministic life of a swing trade, simulated.

The engine half of Milestone `BO`. `fmis.trade_lifecycle` owns the four record
types; this package owns the one candle crossing, the simulator, and the surfaces
behind `fmits simulate`, `fmits trade activate/stop/cancel/status/history/lifecycle`.

```
fmis.data.Candle            (float)
  → fmis.paper.bars          the ONLY fmis.data import in either package
  → PriceBar                 (exact)
  → fmis.paper.engine        advance(state, bar) → StepResult
  → fmis.paper.replay        the fold over a series
  → fmis.paper.compose       fills, events, amendments, journal, outcome
```

**Paper only.** No exchange execution, no broker adapter, no API credential, no
websocket, no order routing, no automated trading, no model and no prediction. A
guard asserts the package names no execution verb and reaches no venue outside
the one composition module every provider call in this repository already lives
beside.

**A simulated fill is a real ledger `Trade` under `Book.PAPER`.** `AP` §5.5
already says what that book means, so the position fold, the exposure engine, the
constraint engine, the valuation and `fmits today` all work on a paper trade with
no new code — the milestone brief's *"reuse the existing architecture"* satisfied
by construction rather than by a parallel implementation.

**Replaying the same bars writes nothing the second time.** Every derived value is
a function of the bars alone and every id is a digest of its record's content, so
resume is not a mechanism — it is a consequence.

**Three refusals worth carrying forward.** A level is filled on touch, at the
level or at the bar's open when it gapped through, and the rule is written once so
a favourable gap and an unfavourable one cannot be treated differently. An entry
that fills inside a bar defers every exit test to the next bar, withholding a stop
and a target equally. And a bar that opens between the stop and a target and
reaches both **halts the trade** rather than guessing which came first — ADR-0021's
refusal, applied a third time.
"""

from __future__ import annotations

from fmis.paper.bars import bar_from_candle, bars_from_candles, bars_from_series
from fmis.paper.compose import (
    ACTIVATE_REASON,
    AMEND_REASON,
    LIFECYCLE_TAG_VOCABULARY,
    PAPER_AUTHOR,
    PAPER_DUST_POLICY,
    PAPER_FX_RATE,
    PAPER_FX_SOURCE,
    PAPER_TAXONOMY_VERSION,
    SIMULATE_REASON,
    ActivateRequest,
    ActivationOutcome,
    AmendStopRequest,
    CancelRequest,
    SimulationReport,
    TradeRunReport,
    activate_trade,
    amend_stop,
    bars_for_run,
    cancel_activation,
    paper_version_set,
    run_simulation,
    simulate_activation,
)
from fmis.paper.engine import advance, initial_run_state
from fmis.paper.fills import (
    ENTRY_IS_FAVOURABLE,
    entry_fill,
    entry_level_of,
    entry_reached,
    entry_resolves_the_bar,
    fill_at_level,
    reached_legs,
    stop_fill,
    stop_reached,
    target_fill,
)
from fmis.paper.inputs import (
    AMENDMENT_REASON_SUGGESTIONS,
    DEFAULT_PAPER_ACCOUNT,
    ENTRY_TYPE_CHOICES,
    LIFECYCLE_STATE_CHOICES,
    PAPER_ERRORS,
    activate_request_from_text,
    amend_request_from_text,
    cancel_request_from_text,
    states_from_text,
)
from fmis.paper.models import (
    PAPER_FILL_POLICY_ID,
    PAPER_FILL_POLICY_VERSION,
    PAPER_LIMITATIONS,
    PAPER_ZERO_COST_POLICY,
    Excursion,
    Fill,
    FillKind,
    FillTrigger,
    LifecycleStep,
    PaperError,
    PaperRefusedError,
    PriceBar,
    StepResult,
    StopMoveIntent,
    TradeRunState,
)
from fmis.paper.monitor import MONITOR_BASIS, TradeMonitor, monitor_trade
from fmis.paper.render import (
    render_activation,
    render_history,
    render_lifecycle,
    render_simulation,
    render_status,
)
from fmis.paper.replay import ReplayResult, replay_bars
from fmis.paper.stopping import break_even_stop, derive_stop_move, trailing_stop
from fmis.paper.views import (
    ACTIVATION_SUBJECT_KIND,
    FILL_EVENT_KINDS,
    OutcomeReading,
    PaperTradeNotFoundError,
    PaperTradeView,
    PaperWarning,
    fill_references,
    fills_for_activation,
    list_paper_trades,
    load_paper_trade,
    owner_stop_moves,
    read_outcome,
    run_state_for,
)

__all__ = [
    # errors
    "PaperError",
    "PaperRefusedError",
    "PaperTradeNotFoundError",
    "PAPER_ERRORS",
    # policies and limitations
    "PAPER_FILL_POLICY_ID",
    "PAPER_FILL_POLICY_VERSION",
    "PAPER_ZERO_COST_POLICY",
    "PAPER_LIMITATIONS",
    "PAPER_DUST_POLICY",
    "PAPER_TAXONOMY_VERSION",
    "PAPER_FX_RATE",
    "PAPER_FX_SOURCE",
    "PAPER_AUTHOR",
    "LIFECYCLE_TAG_VOCABULARY",
    "ACTIVATE_REASON",
    "AMEND_REASON",
    "SIMULATE_REASON",
    "MONITOR_BASIS",
    # the exact bar, and the one crossing
    "PriceBar",
    "bar_from_candle",
    "bars_from_candles",
    "bars_from_series",
    # fill arithmetic
    "ENTRY_IS_FAVOURABLE",
    "fill_at_level",
    "entry_level_of",
    "entry_reached",
    "entry_fill",
    "entry_resolves_the_bar",
    "stop_reached",
    "stop_fill",
    "reached_legs",
    "target_fill",
    # stop rules
    "break_even_stop",
    "trailing_stop",
    "derive_stop_move",
    # the engine
    "Excursion",
    "Fill",
    "FillKind",
    "FillTrigger",
    "LifecycleStep",
    "StopMoveIntent",
    "TradeRunState",
    "StepResult",
    "initial_run_state",
    "advance",
    "ReplayResult",
    "replay_bars",
    # monitoring
    "TradeMonitor",
    "monitor_trade",
    # reading
    "ACTIVATION_SUBJECT_KIND",
    "FILL_EVENT_KINDS",
    "OutcomeReading",
    "PaperWarning",
    "PaperTradeView",
    "fill_references",
    "fills_for_activation",
    "owner_stop_moves",
    "run_state_for",
    "read_outcome",
    "load_paper_trade",
    "list_paper_trades",
    # writing
    "ActivateRequest",
    "AmendStopRequest",
    "CancelRequest",
    "ActivationOutcome",
    "TradeRunReport",
    "SimulationReport",
    "paper_version_set",
    "activate_trade",
    "amend_stop",
    "bars_for_run",
    "cancel_activation",
    "simulate_activation",
    "run_simulation",
    # the text boundary
    "ENTRY_TYPE_CHOICES",
    "LIFECYCLE_STATE_CHOICES",
    "AMENDMENT_REASON_SUGGESTIONS",
    "DEFAULT_PAPER_ACCOUNT",
    "activate_request_from_text",
    "amend_request_from_text",
    "cancel_request_from_text",
    "states_from_text",
    # rendering
    "render_activation",
    "render_simulation",
    "render_status",
    "render_history",
    "render_lifecycle",
]
