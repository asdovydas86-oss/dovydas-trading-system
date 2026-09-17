"""Market Technical Context — what the sheet already knows, kept past the seam.

    technical_context_for_sheet(sheet, regimes)  ──►  MarketTechnicalContext

**A projection over a `MultiTimeframeFactSheet`, and nothing else** (ADR-0032).
`build_setup_inputs` receives three complete `StructuralFactSheet`s and emits
twenty-two scalars and two level tuples; everything else — the context-role
levels, every crossing, every change of character, the nearest-level pairs, the
setup-role breaks, the setup- and execution-role regimes and all three
`FeatureSet`s — stopped there. Report 0047 §7 traced each one to the line it
died at; `CAPABILITY_REGISTRY.md` §2.2 classifies them `PRODUCT_UNREACHABLE`,
*computed correctly and thrown away one layer before the operator*.

This module is the carriage. It sits in `fmis.pipeline` because `fmis.pipeline`
owns the sheet (ADR-0022, ADR-0023), and a view of a sheet belongs beside it.

**No calculation is defined here.** Every value is an object an engine below
already produced, carried **by reference** — `PriceLevel`, `LevelCrossingEvent`,
`StructureBreak`, `ChangeOfCharacter`, `MarketRegime` and `FeatureSet` are all
frozen, so sharing them is safe and copying them would only create somewhere to
drift. A test asserts this module contains **no arithmetic operator at all**,
the same guard `structural_facts` and `multi_timeframe` hold.

**Carriage is not interpretation.** A `CLOSE_BREACH` is a close beyond a number
at a bar, not a breakout. A `ChangeOfCharacter` is two breaks on opposite sides
in a stated order, not a reversal. The nearest level above the last close is the
**nearest structural level above** — not resistance, and the one below is not
support: that derivation is forbidden by ADR-0019 §I and by the report 0047
review disposition §E. A `FeatureSet` value is a measurement, never a lean. This
object carries no direction, opportunity, score, probability, confidence,
ranking or recommendation, and there is no field one could be stored in.

**Roles are never blended.** Three views, in the sheet's own canonical order,
each complete and each separate. No agreement flag, no alignment count, no "two
of three" anything — the refusal `MultiTimeframeFactSheet`'s docstring calls its
load-bearing decision, inherited verbatim.

**Bounded summaries are selected here, never in a renderer.** A crossing history
runs to hundreds of events at production window sizes and must not be rendered
raw. Which event a surface prints — the latest, the latest close breach — is
decided beside the full history it is selected from, using only classifications
`fmis.level_crossing` already assigned and an order it already fixed. The full
history stays reachable for the later deterministic engines that need event
identity, timing and classification; the summary is what a page shows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from fmis.change_of_character import ChangeOfCharacter
from fmis.features import FeatureSet
from fmis.level_crossing import CrossingKind, LevelCrossingEvent, PriceLevel
from fmis.market_regime import (
    MarketRegime,
    ParticipationState,
    RegimeDimensionName,
    StructureState,
    VolatilityState,
)
from fmis.pipeline.multi_timeframe import MultiTimeframeFactSheet, TimeframeRole
from fmis.structural_trend import StructuralTrendType
from fmis.structure_break import StructureBreak

__all__ = [
    "CrossingHistory",
    "TechnicalContextView",
    "MarketTechnicalContext",
    "TECHNICAL_CONTEXT_LIMITATIONS",
    "technical_context_for_sheet",
]


#: Limitations of the recovered context itself, stated on the object rather than
#: left in an ADR — a carriage that omits what it cannot say reads as more
#: complete than it is. These are **about the carriage**; the facts carried keep
#: the limitations their own sheets already state.
TECHNICAL_CONTEXT_LIMITATIONS: tuple[tuple[str, str], ...] = (
    (
        "TC-1",
        "Nothing here is interpreted. A close breach is a close beyond a price "
        "at a bar, a change of character is two breaks on opposite sides, and a "
        "level is where a confirmed swing sat. None of them is a breakout, a "
        "reversal, a signal or a reason to trade.",
    ),
    (
        "TC-2",
        "The nearest level above and the nearest level below are stated as "
        "positions relative to the last close. Neither is support or "
        "resistance: a role would have to come from interaction history, which "
        "this repository does not yet derive.",
    ),
    (
        "TC-3",
        "Indicator values are the latest closed-candle readings. No slope, rate "
        "of change, crossover, divergence or compression is computed, and none "
        "of these values is an evidence family, a vote or a direction.",
    ),
    (
        "TC-4",
        "The three roles are read separately, close at different rates and are "
        "never combined. Nothing here says whether they agree.",
    ),
    (
        "TC-5",
        "No value on this object reaches the swing policy. It is assembled "
        "after the assessment, from facts the assessment was already reasoned "
        "from, and changes no decision.",
    ),
)


@dataclass(frozen=True, slots=True)
class CrossingHistory:
    """One role's complete level-crossing run, and the two events a page prints.

    ``events`` is the engine's own tuple, **by reference and in full** — the
    nine-way classification per candle per level that used to reach the operator
    as a single integer. It is carried whole because a later interaction engine
    needs which level, when, how far and how it arrived, and a count answers none
    of those.

    ``latest`` is the last event in the engine's own order, and
    ``latest_close_breach`` the last one whose kind is `CLOSE_BREACH` — the
    strongest classification `fmis.level_crossing` assigns, filtered on rather
    than reinterpreted. Both are **selections, not derivations**: no threshold,
    no new vocabulary, and no claim that either one means anything.

    Two events sharing a bar index are ordered by the level ordering and **not**
    by time — ADR-0019 §2.6 — so "the latest" is the last in a published order,
    which is a fact about the sequence rather than a claim about the market.
    """

    events: tuple[LevelCrossingEvent, ...]
    latest: LevelCrossingEvent | None = None
    latest_close_breach: LevelCrossingEvent | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.events, tuple):
            raise TypeError("events must be a tuple of LevelCrossingEvent")
        for position, event in enumerate(self.events):
            if not isinstance(event, LevelCrossingEvent):
                raise TypeError(
                    f"events[{position}] must be a LevelCrossingEvent, got "
                    f"{type(event).__name__}"
                )
        for name in ("latest", "latest_close_breach"):
            value = getattr(self, name)
            if value is None:
                continue
            if not isinstance(value, LevelCrossingEvent):
                raise TypeError(
                    f"{name} must be a LevelCrossingEvent or None, got "
                    f"{type(value).__name__}"
                )
            # Identity, not equality. The invariant is that a summary **is** one
            # of the carried events, not that it looks like one: two equal
            # events from two derivations would satisfy `in` and would still be
            # a second source of truth. Scanning from the end also makes the
            # common case — `latest`, which is the final element — immediate.
            if not any(carried is value for carried in reversed(self.events)):
                raise ValueError(
                    f"{name} is not one of the carried events; a summary that "
                    "names an event the history does not contain is a second "
                    "source of truth"
                )

    @property
    def count(self) -> int:
        """How many crossings this role produced. A **projection** over events."""
        return len(self.events)


@dataclass(frozen=True, slots=True)
class TechnicalContextView:
    """One timeframe role's complete technical picture, carried by reference.

    Every field is a value `fmis.pipeline.structural_facts` or
    `fmis.pipeline.regime` already produced for this role. Nothing is recomputed,
    nothing is converted to text, and nothing is merged with another role.

    ``nearest_above`` / ``nearest_below`` are `NearestLevels`' own pair, kept
    under neutral names. `None` on a side means no level lies that way — usually
    because the run is short or price is beyond every level detected so far — and
    it is an absence, never a zero.

    ``warming_up`` names the features that returned no value for lack of history,
    carried so a surface can say *not enough history yet* rather than showing a
    blank that could equally mean *computed to be nothing*.
    """

    role: str
    interval: str
    symbol: str
    as_of: datetime
    closed_count: int
    last_close: float | None
    structural_trend: StructuralTrendType
    regime: MarketRegime
    features: FeatureSet
    warming_up: tuple[str, ...]
    levels: tuple[PriceLevel, ...]
    nearest_above: PriceLevel | None
    nearest_below: PriceLevel | None
    upper_level_count: int
    lower_level_count: int
    crossings: CrossingHistory
    breaks: tuple[StructureBreak, ...]
    latest_break: StructureBreak | None
    changes: tuple[ChangeOfCharacter, ...]
    latest_change: ChangeOfCharacter | None

    def __post_init__(self) -> None:
        for name in ("role", "interval", "symbol"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise TypeError(f"{name} must be a non-empty str")
        if not isinstance(self.as_of, datetime):
            raise TypeError(
                f"as_of must be a datetime, got {type(self.as_of).__name__}"
            )
        if not isinstance(self.structural_trend, StructuralTrendType):
            raise TypeError(
                "structural_trend must be a StructuralTrendType, got "
                f"{type(self.structural_trend).__name__}"
            )
        if not isinstance(self.regime, MarketRegime):
            raise TypeError(
                f"regime must be a MarketRegime, got {type(self.regime).__name__}"
            )
        if not isinstance(self.features, FeatureSet):
            raise TypeError(
                f"features must be a FeatureSet, got {type(self.features).__name__}"
            )
        if not isinstance(self.crossings, CrossingHistory):
            raise TypeError(
                "crossings must be a CrossingHistory, got "
                f"{type(self.crossings).__name__}"
            )

    def regime_state(
        self, dimension: RegimeDimensionName
    ) -> StructureState | VolatilityState | ParticipationState | None:
        """One regime dimension's state for this role, or `None` if unread.

        A container lookup over `MarketRegime.by_dimension`, exposed so a reader
        asking *what is the weekly volatility dimension* does not index a mapping
        by hand and does not reach for `fmis.market_regime`'s internals.
        """
        found = self.regime.by_dimension.get(dimension)
        return None if found is None else found.state

    @property
    def regime_structure(self) -> StructureState | None:
        """This role's structure dimension. A **projection** over ``regime``.

        The three named projections exist so a consumer — a surface in
        particular — can read one dimension without importing
        `fmis.market_regime`'s dimension vocabulary to index a mapping with. They
        are not stored: a copy of a value two attributes away is somewhere for it
        to drift (ADR-0016 §4).
        """
        return self.regime_state(RegimeDimensionName.STRUCTURE)

    @property
    def regime_volatility(self) -> VolatilityState | None:
        """This role's volatility dimension. A **projection** over ``regime``."""
        return self.regime_state(RegimeDimensionName.VOLATILITY)

    @property
    def regime_participation(self) -> ParticipationState | None:
        """This role's participation dimension. A **projection** over ``regime``."""
        return self.regime_state(RegimeDimensionName.PARTICIPATION)


@dataclass(frozen=True, slots=True)
class MarketTechnicalContext:
    """One symbol's recovered technical context, per timeframe role.

    ``views`` are in the sheet's own canonical order — context, setup, execution
    — so a reader sees the gating role first, which is the order the policy
    applies them in.

    ``newest_as_of`` is the sheet's own value, carried rather than recomputed. It
    is **not** a shared observation instant: the views are not synchronised, and
    each one carries its own timestamp for exactly that reason.

    **This object is never read by a policy.** It is assembled after the
    assessment, from facts the assessment was already reasoned from, and adding
    it changed no conclusion — the eighty-one-fixture non-regression matrix
    proves that directly (ADR-0032 §7).
    """

    symbol: str
    source: str
    newest_as_of: datetime
    views: tuple[TechnicalContextView, ...]
    limitations: tuple[tuple[str, str], ...] = TECHNICAL_CONTEXT_LIMITATIONS

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise TypeError("symbol must be a non-empty str")
        if not isinstance(self.views, tuple):
            raise TypeError("views must be a tuple of TechnicalContextView")
        for position, view in enumerate(self.views):
            if not isinstance(view, TechnicalContextView):
                raise TypeError(
                    f"views[{position}] must be a TechnicalContextView, got "
                    f"{type(view).__name__}"
                )
        roles = [view.role for view in self.views]
        if len(set(roles)) != len(roles):
            raise ValueError(
                f"each timeframe role may appear once; got {roles}. Two views "
                "for one role is two answers about one timeframe"
            )
        mismatched = sorted(
            {view.symbol for view in self.views if view.symbol != self.symbol}
        )
        if mismatched:
            raise ValueError(
                f"every view must describe {self.symbol!r}; found {mismatched}"
            )

    @property
    def by_role(self) -> Mapping[str, TechnicalContextView]:
        """The views keyed by role name, for a caller that wants one of them."""
        return MappingProxyType({view.role: view for view in self.views})

    def view_for(self, role: str) -> TechnicalContextView | None:
        """One role's view, or `None` for a role this sheet did not carry."""
        return self.by_role.get(role)


def _latest(events: Sequence[LevelCrossingEvent]) -> LevelCrossingEvent | None:
    """The last event in the engine's own order, or `None` for an empty run."""
    return events[-1] if events else None


def _latest_close_breach(
    events: Sequence[LevelCrossingEvent],
) -> LevelCrossingEvent | None:
    """The last event classified `CLOSE_BREACH`, or `None` if none occurred.

    A filter on a classification `fmis.level_crossing` already assigned — never a
    re-derivation of it, and never a claim that a close beyond a level confirmed
    anything. `close > level` is explicitly not a definition this repository
    accepts for any market concept (report 0047 §17.2); it is only a kind.
    """
    for event in reversed(events):
        if event.kind is CrossingKind.CLOSE_BREACH:
            return event
    return None


def _crossing_history(events: Sequence[LevelCrossingEvent]) -> CrossingHistory:
    """The full run plus the two bounded selections a surface may print."""
    carried = tuple(events)
    return CrossingHistory(
        events=carried,
        latest=_latest(carried),
        latest_close_breach=_latest_close_breach(carried),
    )


def technical_context_for_sheet(
    sheet: MultiTimeframeFactSheet,
    regimes: Mapping[TimeframeRole, MarketRegime],
) -> MarketTechnicalContext:
    """Recover one symbol's per-role technical context from an already-built sheet.

    Args:
        sheet: the composed multi-timeframe sheet. Every fact carried comes from
            one of its views.
        regimes: the `MarketRegime` already evaluated for each of the sheet's
            roles. A **parameter, not a derivation**: the swing composition has
            already evaluated all three, and evaluating them again here would be
            a second regime for one reading — the defect ADR-0025's own boundary
            exists to prevent — as well as wasted work.

    Returns:
        A `MarketTechnicalContext` with one view per role, in the sheet's order.

    Raises:
        TypeError: ``sheet`` is not a `MultiTimeframeFactSheet`.
        KeyError: a role on the sheet has no regime in ``regimes``. Raised rather
            than defaulted: a view whose regime was silently replaced by an empty
            one would read as *the market has no regime* instead of *the caller
            forgot to evaluate it*.

    Pure: no clock, no network, no randomness, and no arithmetic. Two calls over
    equal inputs return equal contexts.
    """
    if not isinstance(sheet, MultiTimeframeFactSheet):
        raise TypeError(
            f"sheet must be a MultiTimeframeFactSheet, got {type(sheet).__name__}"
        )

    views = tuple(
        TechnicalContextView(
            role=view.role.value,
            interval=view.interval,
            symbol=view.sheet.symbol,
            as_of=view.sheet.as_of,
            closed_count=view.sheet.window.closed_count,
            last_close=view.sheet.window.last_close,
            structural_trend=view.sheet.structure.trend,
            regime=regimes[view.role],
            features=view.sheet.features,
            warming_up=view.sheet.warming_up,
            levels=view.sheet.structure.levels,
            nearest_above=view.sheet.nearest_levels.above,
            nearest_below=view.sheet.nearest_levels.below,
            upper_level_count=view.sheet.nearest_levels.upper_count,
            lower_level_count=view.sheet.nearest_levels.lower_count,
            crossings=_crossing_history(view.sheet.structure.crossings),
            breaks=view.sheet.structure.breaks,
            latest_break=view.sheet.structure.latest_break,
            changes=view.sheet.structure.changes,
            latest_change=view.sheet.structure.latest_change,
        )
        for view in sheet.views
    )
    return MarketTechnicalContext(
        symbol=sheet.symbol,
        source=sheet.source,
        newest_as_of=sheet.newest_as_of,
        views=views,
    )
