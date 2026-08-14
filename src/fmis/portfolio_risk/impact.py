"""What changes in the portfolio if the owner opens this trade now.

The milestone's central question, answered as **two portfolio states and the
differences between them** — never as a verdict. There is no field on any type in
this module that could hold `BUY`, `SELL`, `TAKE` or `REJECT`, and a guard test
asserts the package names none of those words. `AP` §15.5: *"`EXCEEDED` on the
open-risk budget is a fact; 'don't take this trade' is the owner's conclusion."*

**The after-state is built by the same function that built the before-state.**
`build_state` runs twice over two line sets, so a before/after comparison can
never compare two differently-computed numbers — the failure that makes an impact
figure wrong in a way nobody can see. The only difference between the two calls is
which lines went in.

**A proposed line is valued at its own entry price, and says so.** A mark is a
measured price with a source; a proposal has no mark, but it does state the price
the owner intends to transact at, and that is the only honest valuation of
exposure that does not exist yet. `PROPOSED_MARK_SOURCE` is what the `MarkQuote`
carries, so a reader can always tell a proposed valuation from a measured one —
and `ExposureLine.origin` reports `ASSERTED` rather than `MEASURED` for it.

**Direction is netted, because that is what the position fold already does.**
FMITS models one net position per `(account, market, book)`: `fold_positions`
splits a fill that carries exposure through zero into a close and an open, and a
hedge-mode two-sided position is not representable anywhere in this domain. An
opposite-direction proposal is therefore read as reducing, closing or reversing
the existing exposure — a stated convention consistent with the fold, not an
inference about intent. Where the facts genuinely do not support a reading,
`IntendedEffect` is `Absent(reason)`.

**Same symbol on another venue is duplicate exposure, and is reported as such.**
Two venues do not net: `binance:BTCUSDT:spot` and `evedex:BTCUSDT:perpetual` are
two markets with two counterparties, so a long on one and a short on the other is
*two* positions rather than a flat book. `PositionOverlap.same_instrument_elsewhere`
names them and a note says so, because presenting correlated or duplicated
exposure as diversification is the single most expensive thing a portfolio page
can do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fmis.accounts import AccountId, Book, MarketId, OwnerContext
from fmis.money import Money, Quantity, canonical_decimal_text
from fmis.plan import TradePlan
from fmis.portfolio import MarkQuote
from fmis.positions import PositionDirection
from fmis.provenance import Absent, ValueOrigin
from fmis.records import (
    DomainValidationError,
    require_member,
    require_text,
    require_tuple_of,
    require_utc,
)
from fmis.risk import RiskBudget
from fmis.snapshotting import TradeDirection

from fmis.portfolio_risk.classification import ClassificationMap
from fmis.portfolio_risk.constraints import (
    PortfolioConstraintCheck,
    evaluate_constraints,
    remaining_risk_capacity,
)
from fmis.portfolio_risk.exposure import SPOT_ONLY_MODES, build_state
from fmis.portfolio_risk.geometry import (
    RISK_BASIS,
    PortfolioRiskError,
    RiskGeometryError,
    capital_at_risk_of,
)
from fmis.portfolio_risk.models import (
    UNCLASSIFIED,
    ExposureLine,
    ExposureSource,
    PortfolioState,
    direction_of,
)

__all__ = [
    "PROPOSED_MARK_SOURCE",
    "ProposedTrade",
    "PositionRelationship",
    "IntendedEffect",
    "PositionOverlap",
    "PortfolioNote",
    "PortfolioImpact",
    "detect_overlap",
    "lines_after",
    "evaluate_impact",
]

#: What a proposed line's `MarkQuote` names as its source. A constant rather than
#: a literal at the call site, so a surface can test for it and render a proposed
#: valuation differently from a measured one.
PROPOSED_MARK_SOURCE = "the proposal's own entry price, not a measured mark"


class PositionRelationship(Enum):
    """How a candidate stands against exposure already held in the same scope.

    Three members and no fourth: *"there is nothing here"*, *"there is something
    pointing the same way"*, *"there is something pointing the other way"*. What
    the owner intends to do about it is `IntendedEffect`, which is a separate
    question with a separate answer — a single enum mixing the two would make
    *"I hold a long"* and *"I am adding to a long"* the same value.
    """

    NO_EXISTING_POSITION = "no_existing_position"
    SAME_DIRECTION = "same_direction"
    OPPOSITE_DIRECTION = "opposite_direction"


class IntendedEffect(Enum):
    """What the candidate would do to the exposure in its own scope.

    Derived from the two quantities and the two directions, under the netting
    convention the position fold already implements. `REVERSAL_CANDIDATE` rather
    than `REVERSAL`: whether the owner means to end up short is their statement,
    and all this arithmetic can say is that the quantity is larger than what is
    open.
    """

    NEW_POSITION = "new_position"
    SCALE_IN = "scale_in"
    REDUCTION = "reduction"
    CLOSE = "close"
    REVERSAL_CANDIDATE = "reversal_candidate"


@dataclass(frozen=True, slots=True)
class ProposedTrade:
    """A candidate, in the narrowest terms the arithmetic needs.

    **Not a `TradePlan`, and not a duplicate of one.** A plan holds the
    commitment — its stop, its targets, the confidence it was taken with — and
    deliberately holds **no size and no account**, because *"capital at risk is a
    product over one number this record holds and two the `Trade` holds"*. This
    type is the missing half: a size, an account and an entry price, with
    `from_plan` supplying the rest from a commitment the owner already recorded so
    nothing is retyped.

    `ASSERTED` throughout. Everything on it is the owner's statement of what they
    intend, and intent can be wrong.
    """

    account: AccountId
    market: MarketId
    book: Book
    direction: TradeDirection
    entry: Decimal
    stop: Decimal
    quantity: Quantity
    plan_id: str | Absent = field(
        default_factory=lambda: Absent("this candidate is not a recorded commitment")
    )

    def __post_init__(self) -> None:
        if not isinstance(self.account, AccountId):
            raise TypeError("account must be an AccountId")
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        require_member(self.book, Book, "book")
        require_member(self.direction, TradeDirection, "direction")
        if not self.direction.is_directional:
            raise DomainValidationError(
                "NO_TRADE is a decision not to act; it proposes no exposure and "
                "has no stop to be wrong about"
            )
        for name in ("entry", "stop"):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
            if value <= 0:
                raise DomainValidationError(f"{name} must be positive, got {value}")
            object.__setattr__(self, name, Decimal(canonical_decimal_text(value)))
        if not isinstance(self.quantity, Quantity):
            raise TypeError("quantity must be a Quantity")
        if self.quantity.amount <= 0:
            raise DomainValidationError(
                f"quantity must be positive, got {self.quantity}; direction is "
                "carried by `direction` and a signed quantity would be the same "
                "fact twice"
            )
        if self.quantity.asset != self.market.base_asset:
            raise DomainValidationError(
                f"quantity is denominated in {self.quantity.asset} but the market "
                f"trades {self.market.base_asset} as its base asset"
            )
        if not isinstance(self.plan_id, Absent):
            object.__setattr__(self, "plan_id", require_text(self.plan_id, "plan_id"))

    @property
    def origin(self) -> ValueOrigin:
        """`ASSERTED`. A proposal is intent, and intent can be wrong."""
        return ValueOrigin.ASSERTED

    @property
    def side(self) -> PositionDirection:
        return direction_of(self.direction)

    @property
    def scope(self) -> tuple[str, str, str]:
        return (self.account.value, self.market.value, self.book.value)

    def capital_at_risk(self) -> Money | Absent:
        """`risk distance × quantity`, or the reason the geometry has none."""
        try:
            return capital_at_risk_of(
                self.side,
                entry=self.entry,
                stop=self.stop,
                quantity=self.quantity,
                quote_asset=self.market.quote_asset,
            )
        except RiskGeometryError as error:
            return Absent(str(error))

    def notional(self) -> Money:
        """`quantity × entry` in the quote asset — a product, never stored."""
        return self.quantity.value_at(self.entry, self.market.quote_asset)

    def as_line(self, as_of: datetime) -> ExposureLine:
        """The candidate as one more unit of exposure, marked at its own entry."""
        moment = require_utc(as_of, "as_of")
        return ExposureLine(
            account=self.account,
            market=self.market,
            book=self.book,
            direction=self.side,
            quantity=self.quantity,
            source=ExposureSource.PROPOSED,
            entry=self.entry,
            stop=self.stop,
            mark=MarkQuote(
                price=self.entry,
                quote_asset=self.market.quote_asset,
                source=PROPOSED_MARK_SOURCE,
                as_of=moment,
            ),
            origin_ids=(
                () if isinstance(self.plan_id, Absent) else (self.plan_id,)
            ),
        )

    @classmethod
    def from_plan(
        cls,
        plan: TradePlan,
        *,
        account: AccountId,
        entry: Decimal,
        quantity: Quantity,
    ) -> ProposedTrade:
        """Size a commitment the owner already recorded, without retyping it.

        The market, the book, the side and **the stop** all come from the plan and
        cannot be overridden here: `initial_invalidation` is the field the whole
        plan entity exists to keep immutable, and a sizing helper that let a
        caller pass a different stop would be the edit path it was built to
        prevent.
        """
        if not isinstance(plan, TradePlan):
            raise TypeError(f"plan must be a TradePlan, got {type(plan).__name__}")
        return cls(
            account=account,
            market=plan.market,
            book=plan.book,
            direction=plan.direction,
            entry=entry,
            stop=plan.initial_invalidation,
            quantity=quantity,
            plan_id=plan.plan_id,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "account": self.account.value,
            "market": self.market.to_payload(),
            "book": self.book.value,
            "direction": self.direction.value,
            "entry": canonical_decimal_text(self.entry),
            "stop": canonical_decimal_text(self.stop),
            "quantity": self.quantity.to_payload(),
            "plan_id": (
                {"absent": self.plan_id.to_payload()}
                if isinstance(self.plan_id, Absent)
                else {"value": self.plan_id}
            ),
        }


@dataclass(frozen=True, slots=True)
class PositionOverlap:
    """What the candidate meets: in its own scope, and everywhere else.

    Two fields answering two questions that are constantly confused. `matched` and
    `effect` are about the one `(account, market, book)` the trade would land in.
    `same_instrument_elsewhere` is about the *portfolio* — the same pair held in
    another account, another book or at another venue — and it is the field that
    turns *"I am not adding to anything"* into *"I already hold this twice."*
    """

    relationship: PositionRelationship
    effect: IntendedEffect | Absent
    matched: ExposureLine | Absent
    same_instrument_elsewhere: tuple[ExposureLine, ...] = ()
    #: Exposure to the **same base asset** under a *different* traded pair —
    #: a `BTCUSDC` holding beside a `BTCUSDT` candidate. Separate from
    #: `same_instrument_elsewhere` because it is a different sentence: the
    #: instrument is genuinely different, and the *bet* is the same one.
    same_asset_elsewhere: tuple[ExposureLine, ...] = ()

    def __post_init__(self) -> None:
        require_member(self.relationship, PositionRelationship, "relationship")
        if not isinstance(self.effect, (IntendedEffect, Absent)):
            raise TypeError("effect must be an IntendedEffect or Absent")
        if not isinstance(self.matched, (ExposureLine, Absent)):
            raise TypeError("matched must be an ExposureLine or Absent")
        require_tuple_of(
            self.same_instrument_elsewhere, ExposureLine, "same_instrument_elsewhere"
        )
        require_tuple_of(
            self.same_asset_elsewhere, ExposureLine, "same_asset_elsewhere"
        )
        if (
            self.relationship is PositionRelationship.NO_EXISTING_POSITION
        ) != isinstance(self.matched, Absent):
            raise DomainValidationError(
                "a relationship of NO_EXISTING_POSITION and a matched line are "
                "contradictory; one of the two would have to be ignored"
            )

    @property
    def is_duplicate(self) -> bool:
        """Whether this **bet** is already held somewhere in the portfolio.

        Base-asset exposure counts. A candidate long `BTCUSDT` against a held
        `BTCUSDC` is not a new idea, and answering *"no duplicate"* there would
        be the flattering answer rather than the true one.
        """
        return (
            not isinstance(self.matched, Absent)
            or bool(self.same_instrument_elsewhere)
            or bool(self.same_asset_elsewhere)
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "relationship": self.relationship.value,
            "same_asset_elsewhere": [
                line.to_payload() for line in self.same_asset_elsewhere
            ],
            "effect": (
                {"absent": self.effect.to_payload()}
                if isinstance(self.effect, Absent)
                else {"value": self.effect.value}
            ),
            "matched": (
                {"absent": self.matched.to_payload()}
                if isinstance(self.matched, Absent)
                else {"value": self.matched.to_payload()}
            ),
            "same_instrument_elsewhere": [
                line.to_payload() for line in self.same_instrument_elsewhere
            ],
        }


@dataclass(frozen=True, slots=True, order=True)
class PortfolioNote:
    """One qualification on this impact. A code and a statement, and nothing else.

    **No severity and no rank.** This package produces no ordering by importance:
    a severity field would be the first place one appeared, and the owner reads
    every note rather than the top one.
    """

    code: str
    statement: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", require_text(self.code, "code"))
        object.__setattr__(self, "statement", require_text(self.statement, "statement"))


@dataclass(frozen=True, slots=True)
class PortfolioImpact:
    """Two states, the differences, and every constraint evaluated against both.

    **This object reports facts.** It holds no recommendation, no score and no
    verdict, and the two constraint checks it carries are the same object type
    `AP` §15.5 specifies — per-limit results, binding constraints, and
    indeterminate results kept in their own list so a surface cannot render the
    third as the first.
    """

    proposed: ProposedTrade
    before: PortfolioState
    after: PortfolioState
    overlap: PositionOverlap
    incremental_notional: Money | Absent
    incremental_capital_required: Money | Absent
    incremental_open_risk: Money | Absent
    remaining_risk_budget: Money | Absent
    before_check: PortfolioConstraintCheck
    after_check: PortfolioConstraintCheck
    notes: tuple[PortfolioNote, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.proposed, ProposedTrade):
            raise TypeError("proposed must be a ProposedTrade")
        for name in ("before", "after"):
            if not isinstance(getattr(self, name), PortfolioState):
                raise TypeError(f"{name} must be a PortfolioState")
        if self.before.base_currency != self.after.base_currency:
            raise DomainValidationError(
                "the before and after states are stated in two base currencies; "
                "the difference between them would not be a number"
            )
        if self.before.as_of != self.after.as_of:
            raise DomainValidationError(
                "the before and after states are dated at two instants; an impact "
                "compares one portfolio with itself, not a portfolio with a later "
                "one"
            )
        if not isinstance(self.overlap, PositionOverlap):
            raise TypeError("overlap must be a PositionOverlap")
        for name in (
            "incremental_notional",
            "incremental_capital_required",
            "incremental_open_risk",
            "remaining_risk_budget",
        ):
            if not isinstance(getattr(self, name), (Money, Absent)):
                raise TypeError(f"{name} must be a Money or Absent")
        for name in ("before_check", "after_check"):
            if not isinstance(getattr(self, name), PortfolioConstraintCheck):
                raise TypeError(f"{name} must be a PortfolioConstraintCheck")
        require_tuple_of(self.notes, PortfolioNote, "notes")

    @property
    def origin(self) -> ValueOrigin:
        return ValueOrigin.POLICY_DERIVED

    @property
    def resulting_gross_exposure(self) -> Money | Absent:
        return self.after.gross_exposure

    @property
    def resulting_net_exposure(self) -> Money | Absent:
        return self.after.net_exposure

    @property
    def resulting_long_exposure(self) -> Money | Absent:
        return self.after.long_exposure

    @property
    def resulting_short_exposure(self) -> Money | Absent:
        return self.after.short_exposure

    @property
    def resulting_open_risk(self) -> Money | Absent:
        return self.after.open_risk

    @property
    def newly_binding(self) -> tuple[str, ...]:
        """Limits the trade would move to `AT_LIMIT` or `EXCEEDED`.

        The difference between the two checks, and the reason both are carried:
        *"this trade breaches your concentration cap"* and *"you were already over
        it"* are different sentences and only one of them is about the trade.
        """
        was = {result.limit_id for result in self.before_check.binding_constraints}
        return tuple(
            result.limit_id
            for result in self.after_check.binding_constraints
            if result.limit_id not in was
        )

    @property
    def already_binding(self) -> tuple[str, ...]:
        return tuple(
            result.limit_id for result in self.before_check.binding_constraints
        )

    @property
    def risk_basis(self) -> str:
        return RISK_BASIS

    def to_payload(self) -> dict[str, Any]:
        return {
            "proposed": self.proposed.to_payload(),
            "before": self.before.to_payload(),
            "after": self.after.to_payload(),
            "overlap": self.overlap.to_payload(),
            "incremental_notional": _amount(self.incremental_notional),
            "incremental_capital_required": _amount(
                self.incremental_capital_required
            ),
            "incremental_open_risk": _amount(self.incremental_open_risk),
            "remaining_risk_budget": _amount(self.remaining_risk_budget),
            "before_check": self.before_check.to_payload(),
            "after_check": self.after_check.to_payload(),
            "newly_binding": list(self.newly_binding),
            "already_binding": list(self.already_binding),
            "notes": [
                {"code": note.code, "statement": note.statement}
                for note in self.notes
            ],
            "risk_basis": self.risk_basis,
        }


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def detect_overlap(state: PortfolioState, proposed: ProposedTrade) -> PositionOverlap:
    """What the candidate meets, in its scope and across the whole portfolio.

    Matching is on `(account, market, book)` — the triple one open position lives
    in. Book is part of it because books never share capacity, so the same market
    held in `SWING` and proposed in `INVESTING` is a **new position** and not a
    scale-in; merging them would move risk between two capacity pools.
    """
    if not isinstance(state, PortfolioState):
        raise TypeError("state must be a PortfolioState")
    if not isinstance(proposed, ProposedTrade):
        raise TypeError("proposed must be a ProposedTrade")
    matches = state.lines_in_scope(proposed.scope)
    elsewhere = tuple(
        line
        for line in state.lines_for_symbol(proposed.market.pair_symbol)
        if line.scope != proposed.scope
    )
    # The same base asset under a *different* pair. Disjoint from `elsewhere` by
    # construction, so a `BTCUSDC` holding is reported once and as the thing it
    # is — a second bet on BTC rather than a second BTCUSDT position.
    other_pair = tuple(
        line
        for line in state.lines_for_asset(proposed.market.base_asset)
        if line.market.pair_symbol != proposed.market.pair_symbol
    )
    if len(matches) > 1:
        # Unreachable from a fold, which produces one open position per triple.
        # Reachable from caller-supplied lines, and an effect computed against an
        # arbitrary one of two would be a guess wearing an answer's clothes.
        return PositionOverlap(
            relationship=PositionRelationship.SAME_DIRECTION
            if matches[0].direction is proposed.side
            else PositionRelationship.OPPOSITE_DIRECTION,
            effect=Absent(
                f"{len(matches)} open lines sit in one (account, market, book); "
                "which one this trade would act on is not stated by anything "
                "recorded"
            ),
            matched=matches[0],
            same_instrument_elsewhere=elsewhere,
            same_asset_elsewhere=other_pair,
        )
    if not matches:
        return PositionOverlap(
            relationship=PositionRelationship.NO_EXISTING_POSITION,
            effect=IntendedEffect.NEW_POSITION,
            matched=Absent(
                f"nothing is open in {proposed.market.value} in book "
                f"{proposed.book.value} in account {proposed.account.value}"
            ),
            same_instrument_elsewhere=elsewhere,
            same_asset_elsewhere=other_pair,
        )
    existing = matches[0]
    if existing.direction is proposed.side:
        return PositionOverlap(
            relationship=PositionRelationship.SAME_DIRECTION,
            effect=IntendedEffect.SCALE_IN,
            matched=existing,
            same_instrument_elsewhere=elsewhere,
            same_asset_elsewhere=other_pair,
        )
    if proposed.quantity < existing.quantity:
        effect = IntendedEffect.REDUCTION
    elif proposed.quantity == existing.quantity:
        effect = IntendedEffect.CLOSE
    else:
        effect = IntendedEffect.REVERSAL_CANDIDATE
    return PositionOverlap(
        relationship=PositionRelationship.OPPOSITE_DIRECTION,
        effect=effect,
        matched=existing,
        same_instrument_elsewhere=elsewhere,
        same_asset_elsewhere=other_pair,
    )


def lines_after(
    state: PortfolioState, proposed: ProposedTrade, *, as_of: datetime
) -> tuple[ExposureLine, ...]:
    """The lines the portfolio would hold, with the candidate applied.

    The netting mirrors `fold_positions` exactly, because the after-state must be
    the state the fold would actually produce once the fill is recorded:

    * nothing there, or exposure the same way → the candidate is **added** as its
      own line. Two lines rather than one blended line, because blending would
      need a weighted-average stop the owner never stated, and the open risk of a
      scale-in with its own stop is the **sum** of the two risks.
    * exposure the other way, smaller → the existing line is **reduced**.
    * equal → the existing line is **removed**.
    * larger → the existing line is removed and the remainder opens the other
      way, which is the split `_crosses_zero` already performs.
    """
    overlap = detect_overlap(state, proposed)
    candidate = proposed.as_line(as_of)
    if isinstance(overlap.matched, Absent) or isinstance(overlap.effect, Absent):
        return state.lines + (candidate,)
    existing = overlap.matched
    if overlap.effect is IntendedEffect.SCALE_IN:
        return state.lines + (candidate,)
    remaining = tuple(line for line in state.lines if line is not existing)
    if overlap.effect is IntendedEffect.REDUCTION:
        return remaining + (
            existing.with_quantity(existing.quantity - proposed.quantity),
        )
    if overlap.effect is IntendedEffect.CLOSE:
        return remaining
    return remaining + (
        candidate.with_quantity(proposed.quantity - existing.quantity),
    )


def _incremental_capital(proposed: ProposedTrade, notional: Money) -> Money | Absent:
    """What the trade actually ties up, or why that is not the notional.

    Only answerable for an unleveraged long. A short posts margin and a perpetual
    posts margin, and how much is a venue fact this domain records nowhere —
    reporting the notional under the name "capital required" would overstate a
    short's cost and understate its risk in the same number.
    """
    if proposed.market.mode not in SPOT_ONLY_MODES:
        return Absent(
            f"{proposed.market.value} is a {proposed.market.mode.value} market: "
            "what it ties up is margin, which this domain records nowhere. The "
            "notional is reported separately and is not the same figure"
        )
    if proposed.side is PositionDirection.SHORT:
        return Absent(
            "a short's committed capital is margin rather than cost, and no "
            "margin figure is recorded anywhere in this domain"
        )
    return notional


def _group_notes(
    proposed: ProposedTrade,
    before: PortfolioState,
    classification: ClassificationMap,
) -> list[PortfolioNote]:
    """Whether the candidate lands in a group the portfolio is already in."""
    groups = classification.groups_for(proposed.market.base_asset)
    if isinstance(groups, Absent):
        return [
            PortfolioNote(
                "PR-N7",
                f"{proposed.market.base_asset} is {UNCLASSIFIED} under the owner's "
                f"classification {classification.version!r}: {groups.reason}. Its "
                "group exposure is therefore not measured, which is not the same "
                "as measuring it and finding none.",
            )
        ]
    held = {
        group
        for line in before.lines
        for group in _groups_of(line, classification)
    }
    shared = sorted(set(groups) & held)
    if not shared:
        return []
    return [
        PortfolioNote(
            "PR-N2",
            f"{proposed.market.base_asset} is in "
            f"{', '.join(repr(group) for group in shared)}, which this portfolio "
            "already holds exposure in. Exposure in one group is one bet held "
            "several times, and adding to it is concentration rather than "
            "diversification.",
        )
    ]


def _groups_of(line: ExposureLine, classification: ClassificationMap) -> tuple[str, ...]:
    groups = classification.groups_for(line.market.base_asset)
    return () if isinstance(groups, Absent) else groups


def _notes_for(
    proposed: ProposedTrade,
    before: PortfolioState,
    after: PortfolioState,
    overlap: PositionOverlap,
    before_check: PortfolioConstraintCheck,
    after_check: PortfolioConstraintCheck,
    classification: ClassificationMap,
) -> tuple[PortfolioNote, ...]:
    """Everything qualifying this impact, in a fixed order.

    Fixed rather than sorted by severity: ordering by severity would make the list
    read as ranked by importance, and this package ranks nothing.
    """
    notes: list[PortfolioNote] = []
    if overlap.same_instrument_elsewhere:
        where = ", ".join(
            sorted(
                f"{line.direction.value} {line.quantity} in {line.market.value} "
                f"({line.account.value} · {line.book.value})"
                for line in overlap.same_instrument_elsewhere
            )
        )
        notes.append(
            PortfolioNote(
                "PR-N1",
                f"{proposed.market.pair_symbol} is already held elsewhere in this "
                f"portfolio: {where}. Positions in different accounts, books or "
                "venues do not net against each other — a long at one venue and a "
                "short at another is two positions and two counterparties, not a "
                "flat book.",
            )
        )
    if overlap.same_asset_elsewhere:
        where = ", ".join(
            sorted(
                f"{line.direction.value} {line.quantity} in {line.market.value}"
                for line in overlap.same_asset_elsewhere
            )
        )
        notes.append(
            PortfolioNote(
                "PR-N10",
                f"this portfolio already holds {proposed.market.base_asset} under a "
                f"different pair: {where}. A different quote currency is a "
                "different instrument and the same bet — the exposure adds up "
                f"even though {proposed.market.pair_symbol} appears nowhere else.",
            )
        )
    if overlap.effect is IntendedEffect.REVERSAL_CANDIDATE:
        notes.append(
            PortfolioNote(
                "PR-N6",
                "This quantity is larger than the opposite-direction exposure "
                "already open in the same scope, so recording it would close that "
                "position and open a new one the other way. FMITS models one net "
                "position per (account, market, book); a two-sided hedge is not "
                "representable here.",
            )
        )
    if isinstance(overlap.effect, Absent):
        notes.append(PortfolioNote("PR-N8", overlap.effect.reason))
    notes.extend(_group_notes(proposed, before, classification))
    already_ids = {
        result.limit_id for result in before_check.binding_constraints
    }
    for result in after_check.binding_constraints:
        if result.limit_id in already_ids:
            continue
        notes.append(
            PortfolioNote(
                "PR-N3",
                f"limit {result.limit_id!r} ({result.scope.value}) moves to "
                f"{result.status.value} if this trade is opened.",
            )
        )
    for result in before_check.binding_constraints:
        notes.append(
            PortfolioNote(
                "PR-N4",
                f"limit {result.limit_id!r} ({result.scope.value}) is already "
                f"{result.status.value} before this trade.",
            )
        )
    if after_check.indeterminate:
        names = ", ".join(
            repr(result.limit_id) for result in after_check.indeterminate
        )
        notes.append(
            PortfolioNote(
                "PR-N5",
                f"{len(after_check.indeterminate)} limit(s) could not be measured "
                f"({names}). An unmeasured limit is not a limit that was met — "
                "read each reason rather than the absence of a breach.",
            )
        )
    if after.unstopped:
        notes.append(
            PortfolioNote(
                "PR-N9",
                f"{len(after.unstopped)} open position(s) have no recorded stop, "
                "so total open risk cannot be stated and every risk figure above "
                "that depends on it is absent rather than smaller.",
            )
        )
    return tuple(notes)


def evaluate_impact(
    *,
    proposed: ProposedTrade,
    before: PortfolioState,
    budget: RiskBudget,
    owner: OwnerContext,
    classification: ClassificationMap,
) -> PortfolioImpact:
    """The whole question: what changes if the owner opens this trade now.

    Both states are built by `build_state` and both are evaluated by
    `evaluate_constraints`, so every number on the after-state is comparable with
    its before-state counterpart by construction rather than by care.
    """
    if not isinstance(proposed, ProposedTrade):
        raise TypeError("proposed must be a ProposedTrade")
    if not isinstance(before, PortfolioState):
        raise TypeError("before must be a PortfolioState")
    if not isinstance(classification, ClassificationMap):
        raise TypeError("classification must be a ClassificationMap")
    if proposed.book not in before.books_covered:
        raise PortfolioRiskError(
            f"this candidate is in book {proposed.book.value}, and the portfolio "
            f"state covers "
            f"{sorted(book.value for book in before.books_covered)}. Books never "
            "share capacity, so a trade in an uncovered book cannot be evaluated "
            "against this reading — build a state that covers it"
        )
    overlap = detect_overlap(before, proposed)
    after = build_state(
        portfolio_id=before.portfolio_id,
        base_currency=before.base_currency,
        as_of=before.as_of,
        lines=lines_after(before, proposed, as_of=before.as_of),
        pending=before.pending,
        equity=before.equity,
        cash=before.cash,
        classification=classification,
        books_covered=before.books_covered,
    )
    candidate_risk = proposed.capital_at_risk()
    if (
        isinstance(candidate_risk, Money)
        and candidate_risk.asset != before.base_currency
    ):
        candidate_risk = Absent(
            f"the candidate's risk is stated in {candidate_risk.asset} and this "
            f"portfolio's base currency is {before.base_currency}; no rate between "
            "them was supplied"
        )
    before_check = evaluate_constraints(budget, before, owner=owner)
    after_check = evaluate_constraints(
        budget, after, owner=owner, candidate_risk=candidate_risk
    )
    notional = proposed.notional()
    if notional.asset != before.base_currency:
        notional_or_absent: Money | Absent = Absent(
            f"the candidate is quoted in {notional.asset} and this portfolio's "
            f"base currency is {before.base_currency}; no rate between them was "
            "supplied"
        )
        capital_required: Money | Absent = notional_or_absent
    else:
        notional_or_absent = notional
        capital_required = _incremental_capital(proposed, notional)
    return PortfolioImpact(
        proposed=proposed,
        before=before,
        after=after,
        overlap=overlap,
        incremental_notional=notional_or_absent,
        incremental_capital_required=capital_required,
        incremental_open_risk=_incremental_risk(before, after),
        remaining_risk_budget=remaining_risk_capacity(
            after_check, base=before.base_currency
        ),
        before_check=before_check,
        after_check=after_check,
        notes=_notes_for(
            proposed,
            before,
            after,
            overlap,
            before_check,
            after_check,
            classification,
        ),
    )


def _incremental_risk(
    before: PortfolioState, after: PortfolioState
) -> Money | Absent:
    """`after open risk − before open risk`. Signed: a reduction lowers it.

    A subtraction over two figures the two states already hold, rather than the
    candidate's own risk, because an opposite-direction trade *reduces* open risk
    and reporting its standalone risk as the increment would report a de-risking
    trade as the portfolio's largest addition.
    """
    if isinstance(after.open_risk, Absent):
        return Absent(
            f"the resulting open risk is not known: {after.open_risk.reason}"
        )
    if isinstance(before.open_risk, Absent):
        return Absent(
            f"the current open risk is not known: {before.open_risk.reason}"
        )
    return after.open_risk - before.open_risk


def _amount(value: Money | Absent) -> dict[str, Any]:
    if isinstance(value, Absent):
        return {"absent": value.to_payload()}
    return {"value": value.to_payload()}
