"""The one enforced read path over the ledger.

`AP` §5.1 and §27 rule 8: *"Events are exposed only through a resolver applying
supersession; consumers receive a resolved type they cannot construct; reading
ledger files directly is a test-enforced violation. Without this, one consumer
eventually reports a superseded value and nothing detects it."*

That is implemented literally here. `ResolvedTrade` requires a token this module
holds, so a caller who wants a resolved value must go through `LedgerResolver`
and cannot fabricate one by hand. It is a guard rail rather than a security
boundary — a determined caller can reach the private name — which is exactly why
the model calls violating it a *test*-enforced offence.

Three integrity rules the resolver enforces, each traceable to a named hazard:

1. **Identical content is one event.** Re-submitting a fill after a crash is an
   idempotent success, not a second position-moving event.
2. **A correction chain extends; it never branches.** Two live corrections of one
   event is a rejected state, never a merge — otherwise *what actually happened*
   has two answers.
3. **Every correction must resolve.** A correction pointing at an event that is
   not in the stream is a detected gap, which is the cheap, chain-free half of
   the ordering-and-completeness question the investigation left open.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from fmis.ledger.models import (
    Correction,
    LedgerError,
    Trade,
    TradeStatus,
    advance_trade_status,
    balance_effects,
)
from fmis.records import DomainValidationError, require_tuple_of

__all__ = [
    "SupersessionError",
    "DanglingCorrectionError",
    "ResolvedTrade",
    "LedgerResolver",
    "resolve",
]

#: The capability a `ResolvedTrade` requires. Module-private on purpose.
_RESOLVER_TOKEN = object()


class SupersessionError(LedgerError, ValueError):
    """A correction chain that branches, loops, or corrects a draft."""


class DanglingCorrectionError(LedgerError, ValueError):
    """A correction naming an event that is not in the stream.

    Its own class because the remedy is different from every other ledger error:
    nothing is malformed, and a record is *missing*. An artifact referencing an
    event that no longer resolves is a detected gap rather than a silent
    disagreement, which is the integrity property Law 8 buys without constraining
    backfill at all.
    """


@dataclass(frozen=True, slots=True)
class ResolvedTrade:
    """What a trade currently says, after supersession — the only readable form.

    Consumers receive this and cannot construct it. `chain` names every event id
    from the original to this one, so *"what did the owner first believe, and what
    do we now know"* is answerable without reading the raw stream.
    """

    token: Any
    trade: Trade
    chain: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.token is not _RESOLVER_TOKEN:
            raise SupersessionError(
                "a ResolvedTrade is produced by LedgerResolver and cannot be "
                "constructed directly. Reading the ledger without applying "
                "supersession is how one consumer eventually reports a value the "
                "owner already corrected"
            )
        if not isinstance(self.trade, Trade):
            raise TypeError("trade must be a Trade")
        require_tuple_of(self.chain, str, "chain", minimum_length=1)

    @property
    def status(self) -> TradeStatus:
        """Always `RECORDED`: a resolved trade is the live reading, by definition."""
        return TradeStatus.RECORDED

    @property
    def was_corrected(self) -> bool:
        return len(self.chain) > 1

    @property
    def original_event_id(self) -> str:
        return self.chain[0]

    @property
    def event_id(self) -> str:
        return self.chain[-1]

    def balance_effects(self) -> tuple[Any, ...]:
        """The postings this trade implies — derived here, stored nowhere."""
        return balance_effects(self.trade)


@dataclass(frozen=True, slots=True)
class LedgerResolver:
    """Applies supersession over a stream of trades and corrections."""

    trades: tuple[Trade, ...]
    corrections: tuple[Correction, ...] = ()
    _resolved: tuple[ResolvedTrade, ...] = field(default=(), init=False, repr=False)

    def __post_init__(self) -> None:
        require_tuple_of(self.trades, Trade, "trades")
        require_tuple_of(self.corrections, Correction, "corrections")
        object.__setattr__(self, "_resolved", self._resolve())

    # -- resolution ----------------------------------------------------------

    def _resolve(self) -> tuple[ResolvedTrade, ...]:
        originals: dict[str, Trade] = {}
        for trade in self.trades:
            if trade.status is TradeStatus.DRAFT:
                raise DomainValidationError(
                    f"trade {trade.event_id} is a draft and is not in the ledger; "
                    "promote it with `Trade.recorded()` before resolving"
                )
            existing = originals.get(trade.event_id)
            if existing is not None and existing.digest_basis != trade.digest_basis:
                # Unreachable while ids are digests of exactly this basis, and
                # kept because a future id scheme must fail loudly here rather
                # than silently keep whichever arrived last.
                raise SupersessionError(  # pragma: no cover
                    f"two different events share the id {trade.event_id}"
                )
            originals[trade.event_id] = trade

        successors: dict[str, Correction] = {}
        for correction in self.corrections:
            target = correction.supersedes
            if target in successors:
                raise SupersessionError(
                    f"event {target} is superseded by two corrections "
                    f"({successors[target].event_id} and {correction.event_id}). A "
                    "chain extends; it never branches, because a branch gives "
                    "'what actually happened' two answers"
                )
            successors[target] = correction

        known = set(originals) | {
            correction.event_id for correction in self.corrections
        }
        dangling = sorted(set(successors) - known)
        if dangling:
            raise DanglingCorrectionError(
                f"correction(s) supersede event(s) not in this stream: {dangling}. "
                "An artifact referencing an event that no longer resolves is a "
                "detected gap, not something to resolve by guessing"
            )

        superseded = set(successors)
        resolved: list[ResolvedTrade] = []
        for event_id in originals:
            chain = self._walk(event_id, successors)
            if chain[-1] in superseded:  # pragma: no cover - _walk ends unsuperseded
                continue
            final = self._trade_at(chain[-1], originals, successors)
            resolved.append(
                ResolvedTrade(token=_RESOLVER_TOKEN, trade=final, chain=chain)
            )
        return tuple(sorted(resolved, key=lambda item: (item.trade.occurred_at, item.event_id)))

    def _walk(
        self, event_id: str, successors: dict[str, Correction]
    ) -> tuple[str, ...]:
        chain = [event_id]
        seen = {event_id}
        current = event_id
        while current in successors:
            correction = successors[current]
            if correction.event_id in seen:  # pragma: no cover - ids are digests
                raise SupersessionError(
                    f"correction chain starting at {event_id} loops back to "
                    f"{correction.event_id}"
                )
            seen.add(correction.event_id)
            chain.append(correction.event_id)
            current = correction.event_id
        return tuple(chain)

    def _trade_at(
        self,
        event_id: str,
        originals: dict[str, Trade],
        successors: dict[str, Correction],
    ) -> Trade:
        if event_id in originals:
            return originals[event_id]
        for correction in self.corrections:
            if correction.event_id == event_id:
                return correction.replacement
        raise DanglingCorrectionError(  # pragma: no cover - _walk guarantees presence
            f"event {event_id} is neither a trade nor a correction in this stream"
        )

    # -- the read API --------------------------------------------------------

    def resolved(self) -> tuple[ResolvedTrade, ...]:
        """Every live trade, ordered by `occurred_at`. The only way to read one."""
        return self._resolved

    def superseded_digests(self) -> dict[str, str]:
        """`{original event id: the digest it now resolves to}`.

        The map a captured artifact's `stale_inputs` compares its own
        `consumed_sources` against. This is the whole of the adopted answer to
        *"what does a correction owe a frozen artifact?"* — the artifact is never
        rewritten and never recomputed; a surface renders the staleness.
        """
        result: dict[str, str] = {}
        for entry in self._resolved:
            if entry.was_corrected:
                for stale_id in entry.chain[:-1]:
                    result[stale_id] = entry.trade.content_digest
        return result

    def status_of(self, event_id: str) -> TradeStatus:
        """`RECORDED` if this id is the live head, `SUPERSEDED` if it was corrected."""
        for entry in self._resolved:
            if entry.event_id == event_id:
                return TradeStatus.RECORDED
            if event_id in entry.chain:
                return advance_trade_status(TradeStatus.RECORDED, TradeStatus.SUPERSEDED)
        raise DanglingCorrectionError(f"event {event_id} is not in this stream")

    def for_market_and_book(self, market: Any, book: Any) -> tuple[ResolvedTrade, ...]:
        """The live trades in one `(market, book)` pair — the position fold's input."""
        return tuple(
            entry
            for entry in self._resolved
            if entry.trade.market == market and entry.trade.book is book
        )


def resolve(
    trades: Iterable[Trade], corrections: Iterable[Correction] = ()
) -> LedgerResolver:
    """Convenience constructor taking any iterables."""
    return LedgerResolver(tuple(trades), tuple(corrections))
