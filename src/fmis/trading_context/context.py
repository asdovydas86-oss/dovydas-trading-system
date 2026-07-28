"""What a *trading* analysis is being asked to look at.

Two types, no behaviour: `TradingObjective` names the kind of trading in view,
and `TradingAnalysisContext` records the timeframes and reference points chosen
for it. Both are descriptive. Nothing here computes, selects, ranks, or decides.

Why `str` for timeframes: the repository has **no canonical timeframe value
object**. `Candle.timeframe`, `CandleSeries.timeframe`, and
`ObservationSeries.frequency` are all plain `str`, and the only interval
vocabulary that exists — `KLINE_INTERVALS` — is Binance's, which ADR-0006 §6
records as provider-native precisely because a canonical vocabulary has not been
decided. Importing it here would both break this package's dependency rules and
freeze one exchange's spelling as though it were canonical. So a timeframe is a
`str`, matching the canonical models, and its *syntax* is deliberately not
validated. When a canonical timeframe type is introduced, this is one of the
places that adopts it.

What is checked is only what can be checked without inventing a vocabulary: that
a timeframe is present and non-blank, that supporting timeframes do not repeat,
and that the primary is not also listed as supporting. Values are stored exactly
as given — never trimmed, reordered, deduplicated, or substituted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

__all__ = ["TradingObjective", "TradingAnalysisContext"]


class TradingObjective(str, Enum):
    """The kind of trading an analysis is being prepared for.

    Swing and day trading are separate members rather than one "trading" value
    because they are different activities: they read different timeframes, and
    the same measurement means different things to each. Naming them separately
    keeps that distinction explicit from the start, before any reasoning layer
    exists to be confused by it.

    **Long-term investing is deliberately absent.** It is not a slower kind of
    trade — it rests on thesis, fundamentals, valuation, catalysts and portfolio
    construction, none of which a trading objective implies. It will be its own
    module with its own context type, and adding a `LONG_TERM_INVESTMENT` member
    here would quietly commit the system to interpreting it with trading logic.
    """

    SWING_TRADE = "swing_trade"
    DAY_TRADE = "day_trade"


def _require_label(value: object, *, field: str) -> str:
    """A present, non-blank string. Content is not otherwise inspected."""
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a str, got {type(value).__name__}")
    if not value or not value.strip():
        raise ValueError(f"{field} cannot be empty")
    return value


@dataclass(frozen=True, slots=True)
class TradingAnalysisContext:
    """The declared scope of one trading analysis. Descriptive input only.

    ``primary_timeframe`` is the timeframe the analysis is centred on;
    ``supporting_timeframes`` are additional ones consulted alongside it, kept in
    the order supplied because that order is the caller's stated priority and is
    not the system's to reorder.

    The fields absent from this type matter as much as the ones present: there is
    no direction, no entry, no stop, no target, no size, no leverage, no holding
    period, no risk setting, and no strategy. Each of those belongs to a later
    module that can define and test it properly, and a placeholder here would
    invite treating an unfilled field as a decision.

    Invariants (violations raise, and nothing is silently corrected):
      * ``objective`` is a `TradingObjective`.
      * ``primary_timeframe`` is a present, non-blank ``str``.
      * ``supporting_timeframes`` accepts any non-string iterable and is stored
        as a tuple; every entry is a present, non-blank ``str``; entries are
        unique; the primary timeframe is not among them.
      * ``benchmark_symbol`` and ``notes`` are either absent or non-blank ``str``.

    Uniqueness and the primary/supporting check compare strings exactly. No
    normalization is applied, so ``"4h"`` and ``"4H"`` are two different labels —
    consistent with the rest of the system, which treats a timeframe label as
    opaque until a canonical vocabulary exists.
    """

    objective: TradingObjective
    primary_timeframe: str
    supporting_timeframes: tuple[str, ...] = ()
    benchmark_symbol: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.objective, TradingObjective):
            raise TypeError(
                f"objective must be a TradingObjective, "
                f"got {type(self.objective).__name__}"
            )

        _require_label(self.primary_timeframe, field="primary_timeframe")

        # A str is iterable, so tuple("4h") would silently become ('4', 'h').
        # Reject it explicitly rather than storing nonsense.
        supporting = self.supporting_timeframes
        if isinstance(supporting, (str, bytes)):
            raise TypeError(
                "supporting_timeframes must be a sequence of timeframe strings, "
                "not a single string; pass e.g. ('1d',) rather than '1d'"
            )
        if not isinstance(supporting, Iterable):
            raise TypeError(
                "supporting_timeframes must be an iterable of str, "
                f"got {type(supporting).__name__}"
            )
        # Accept any iterable at construction; store an immutable tuple so a
        # caller mutating the original cannot mutate this context.
        object.__setattr__(self, "supporting_timeframes", tuple(supporting))

        seen: set[str] = set()
        for index, timeframe in enumerate(self.supporting_timeframes):
            _require_label(timeframe, field=f"supporting_timeframes[{index}]")
            if timeframe in seen:
                raise ValueError(
                    f"duplicate supporting timeframe {timeframe!r} at index {index}"
                )
            seen.add(timeframe)
        if self.primary_timeframe in seen:
            raise ValueError(
                f"primary_timeframe {self.primary_timeframe!r} must not also "
                "appear in supporting_timeframes"
            )

        if self.benchmark_symbol is not None:
            _require_label(self.benchmark_symbol, field="benchmark_symbol")
        if self.notes is not None:
            _require_label(self.notes, field="notes")

    @property
    def timeframes(self) -> tuple[str, ...]:
        """Primary first, then supporting in the order supplied.

        A container accessor, not a selection: it neither chooses nor ranks a
        timeframe, it only presents the ones already declared.
        """
        return (self.primary_timeframe, *self.supporting_timeframes)
