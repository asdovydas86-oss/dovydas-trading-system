"""The three things an approval needs from the store, and none of them guessed.

    budget_in_effect(store, at)   ──►  the owner's limits, or why there are none
    sole_account(store)           ──►  the account, when there is exactly one
    plan_to_size(store, plan_id)  ──►  a recorded commitment, ready to be sized

**The only module in this package that touches persistence, and it only reads.**
A guard test asserts it names no write verb, for the reason
`fmis.portfolio_risk.reading` and `fmis.trade_capture.views` both give: a read
path that repaired something would make the store's contents depend on who looked
at it.

**Exactly one, or none — never the first.** Both resolvers follow the rule
`fmis.today.builder` already applies to budgets and portfolio snapshots: *"with
more than one, none is chosen, because picking the first would make which limits
apply depend on an id sort nobody wrote down."* Applied to an account the rule is
sharper still — an approval scoped to the wrong account measures the wrong
capacity pool and reports a clean answer about a portfolio the owner does not
have.

**Every failure is `Absent(reason)`, never `None`.** *"There is no budget"* and
*"there are three budgets and you must say which"* are different facts with
different remedies, and a caller handed `None` for both cannot tell the owner
which one they are looking at.
"""

from __future__ import annotations

from datetime import datetime

from fmis.accounts import AccountId
from fmis.persistence import TradingStore
from fmis.plan import TradePlan
from fmis.provenance import Absent
from fmis.records import require_text, require_utc
from fmis.risk import RiskBudget

__all__ = [
    "budget_in_effect",
    "sole_account",
    "accounts_in",
    "plan_to_size",
]


def _require_store(store: object) -> TradingStore:
    if not isinstance(store, TradingStore):
        raise TypeError(f"store must be a TradingStore, got {type(store).__name__}")
    return store


def budget_in_effect(store: TradingStore, *, at: datetime) -> RiskBudget | Absent:
    """The single risk-budget lineage in force at an instant, or why there is none.

    Three outcomes and three reasons: no budget has ever been recorded, several
    lineages exist and none is chosen, or one lineage exists but nothing in it was
    in force yet at this instant. The third is `RiskRepository.in_force_at`'s own
    `Absent`, forwarded rather than re-worded, because *"no budget existed"* and
    *"the first budget applied"* are a distinction that repository already draws.
    """
    trading = _require_store(store)
    moment = require_utc(at, "at")
    identifiers = trading.risk.budget_ids()
    if not identifiers:
        return Absent(
            "no risk budget has been recorded, so there is no limit set to "
            "evaluate this candidate against. That is a gap in the owner's own "
            "policy rather than a measurement failure, and no limit is invented "
            "in its place"
        )
    if len(identifiers) > 1:
        return Absent(
            f"{len(identifiers)} risk-budget lineages are recorded "
            f"({', '.join(identifiers)}) and none is chosen; which limits apply "
            "would otherwise depend on an id sort nobody wrote down"
        )
    return trading.risk.in_force_at(identifiers[0], moment)


def accounts_in(store: TradingStore) -> tuple[str, ...]:
    """Every account the recorded fills name, in a stable order.

    Read from the ledger through the resolver rather than from a registry,
    because this domain holds no account registry: an account exists exactly when
    something was recorded against it.
    """
    trading = _require_store(store)
    return tuple(
        sorted({entry.trade.account.value for entry in trading.ledger.resolved()})
    )


def sole_account(store: TradingStore) -> AccountId | Absent:
    """The one account this store records fills in, when there is exactly one.

    The convenience that makes `fmits approve` usable without a flag on the
    single-account setup FMITS actually has, and a refusal the moment that stops
    being true. An approval is scoped to an account because books never share
    capacity across accounts; silently picking one would produce a confident
    answer about the wrong capacity pool.
    """
    found = accounts_in(store)
    if not found:
        return Absent(
            "no account can be inferred, because this store records no fill in "
            "any account. Name one explicitly — an approval is scoped to an "
            "account, and an unscoped one measures nothing in particular"
        )
    if len(found) > 1:
        return Absent(
            f"this store records fills in {len(found)} accounts "
            f"({', '.join(found)}); which one this candidate would consume "
            "capacity in is not stated by anything recorded, and choosing one "
            "would answer a question about the wrong portfolio"
        )
    return AccountId(found[0])


def plan_to_size(store: TradingStore, plan_id: str) -> TradePlan | Absent:
    """One recorded commitment, so its stop is read rather than retyped.

    `PositionProposal.from_plan` takes the market, the book, the side, the stop
    and the target ladder from here and lets a caller override none of them.
    `initial_invalidation` is the field the plan entity exists to keep immutable,
    and a sizing path that accepted a different stop would be the edit path it was
    built to prevent.
    """
    trading = _require_store(store)
    wanted = require_text(plan_id, "plan_id")
    for plan in trading.plans.plans():
        if plan.plan_id == wanted:
            return plan
    return Absent(
        f"this store holds no commitment {wanted!r}. A plan is what states a "
        "stop, and a stop is what a size is computed from"
    )
