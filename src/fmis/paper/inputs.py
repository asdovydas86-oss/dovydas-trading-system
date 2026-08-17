"""Where the owner's text becomes a domain value. **The CLI converts nothing.**

`fmis.pipeline` is a market-half package and may not reach the trading domain or
the store — Milestone `BJ`'s rule, enforced by a guard test, and this milestone
keeps it. So the parser never builds an `AccountId`, never parses a price and
never opens a store: every one of those lives here, where it can be tested without
a parser.

**A refusal names the two values that disagree**, and is a `PaperRefusedError`
rather than a crash, so a script can tell *"FMITS would not simulate that"* from
*"FMITS broke"*.

**The store is opened through `fmis.trade_capture.open_store`.** One store root
policy and one dust policy for the whole owner half: a simulator that opened its
own would draw the boundary between two round trips somewhere the page that
reports them does not.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence

import fmis

from fmis.accounts import AccountId
from fmis.money import AssetCode, Quantity
from fmis.persistence import TradingStore
from fmis.provenance import Absent
from fmis.records import TradeDomainError, require_text
from fmis.trade_capture import capture_store_root, open_store as open_capture_store
from fmis.trade_lifecycle import (
    SUGGESTED_AMENDMENT_REASONS,
    BreakEvenRule,
    EntryType,
    StopManagement,
    TradeLifecycleError,
    TradeLifecycleState,
    TrailingRule,
)
from fmis.paper.compose import (
    ActivateRequest,
    AmendStopRequest,
    CancelRequest,
)
from fmis.paper.models import PaperError, PaperRefusedError

__all__ = [
    "PAPER_ERRORS",
    "ENTRY_TYPE_CHOICES",
    "LIFECYCLE_STATE_CHOICES",
    "AMENDMENT_REASON_SUGGESTIONS",
    "DEFAULT_PAPER_ACCOUNT",
    "paper_store_root",
    "open_store",
    "activate_request_from_text",
    "amend_request_from_text",
    "cancel_request_from_text",
    "states_from_text",
]

#: Every failure family a paper-trading command may legitimately report. The
#: domain's own errors are included because a refusal raised inside a record's
#: constructor is still a refusal the owner can act on.
PAPER_ERRORS: tuple[type[BaseException], ...] = (
    PaperError,
    TradeLifecycleError,
    TradeDomainError,
)

#: Derived from the enums rather than retyped, so a member added appears at the
#: CLI without an edit and one removed cannot linger in a help string.
ENTRY_TYPE_CHOICES: tuple[str, ...] = tuple(entry.value for entry in EntryType)
LIFECYCLE_STATE_CHOICES: tuple[str, ...] = tuple(
    state.value for state in TradeLifecycleState
)

#: `AP` §9.3's six terms, offered in the CLI's help and **not enforced**. The
#: vocabulary is the owner's; see `fmis.trade_lifecycle.stops` for why this
#: repository follows §20.2 where the two design records disagree.
AMENDMENT_REASON_SUGGESTIONS: tuple[str, ...] = SUGGESTED_AMENDMENT_REASONS

#: The account a paper fill sits in when the owner names none. A **surface**
#: default, never a fallback in a record: the activation still states an account
#: and a simulation in another one says so.
DEFAULT_PAPER_ACCOUNT = "paper"


def paper_store_root() -> Path:
    """The owner's store, when a command names none. `fmis.trade_capture`'s."""
    return capture_store_root()


def open_store(root: str | Path | None) -> TradingStore:
    """The store at `root`, or the owner's own — through the one existing opener."""
    return open_capture_store(root)


def _decimal(raw: str, name: str) -> Decimal:
    """Exact text → exact `Decimal`, refusing anything that is not a number.

    `Decimal(text)` and never `Decimal(float(text))`. One pass through a float
    would put a fifty-five-digit expansion into a content digest and therefore
    into a record id, and the same amount typed twice would produce two records.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise PaperRefusedError(f"{name} is required and must be a number")
    try:
        return Decimal(raw.strip())
    except InvalidOperation as error:
        raise PaperRefusedError(f"{name} {raw!r} is not a number") from error


def _optional_decimal(raw: str | None, name: str) -> Decimal | Absent:
    if raw is None:
        return Absent(f"no {name} was stated")
    return _decimal(raw, name)


def _instant(raw: str, name: str) -> datetime:
    """ISO-8601 text → a UTC instant, refusing a naive one.

    ADR-0001: UTC is canonical for storage. A naive timestamp is refused rather
    than assumed local, because the assumption would be invisible in the stored
    bytes and wrong for exactly the owner this system has.
    """
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise PaperRefusedError(
            f"{name} {raw!r} is not an ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None:
        raise PaperRefusedError(
            f"{name} {raw!r} has no timezone. Name one — '+00:00' for UTC — "
            "because a naive instant assumed local would be invisible in the "
            "stored bytes"
        )
    return parsed.astimezone(timezone.utc)


def _instant_or(raw: str | None, fallback: datetime, name: str) -> datetime:
    return fallback if raw is None else _instant(raw, name)


def _entry_type(raw: str) -> EntryType:
    try:
        return EntryType(raw)
    except ValueError as error:
        raise PaperRefusedError(
            f"entry type {raw!r} is not one of "
            f"{sorted(ENTRY_TYPE_CHOICES)}"
        ) from error


def _stop_management(
    *,
    break_even_r: str | None,
    break_even_offset_r: str | None,
    trail_r: str | None,
    trail_start_r: str | None,
) -> StopManagement:
    """The two automatic rules, or the absences that say the owner enabled none.

    **Nothing is defaulted on.** A trail nobody asked for would move a stop the
    owner never agreed to move, and a break-even trigger this layer invented would
    be a trading policy chosen by a parser.
    """
    if break_even_offset_r is not None and break_even_r is None:
        raise PaperRefusedError(
            "a break-even offset was stated with no trigger to offset from; the "
            "offset says how far past the entry, and without a trigger there is "
            "nothing to be past"
        )
    if trail_start_r is not None and trail_r is None:
        raise PaperRefusedError(
            "a trail start was stated with no trail distance; the start says when "
            "to begin trailing and the distance says by how much"
        )
    return StopManagement(
        break_even=(
            Absent("no break-even rule was stated")
            if break_even_r is None
            else BreakEvenRule(
                trigger_r=_decimal(break_even_r, "break-even trigger"),
                offset_r=(
                    Decimal(0)
                    if break_even_offset_r is None
                    else _decimal(break_even_offset_r, "break-even offset")
                ),
            )
        ),
        trailing=(
            Absent("no trailing rule was stated")
            if trail_r is None
            else TrailingRule(
                distance_r=_decimal(trail_r, "trail distance"),
                activate_at_r=(
                    Absent("the trail runs from the first bar")
                    if trail_start_r is None
                    else _decimal(trail_start_r, "trail start")
                ),
            )
        ),
    )


def activate_request_from_text(
    store: TradingStore,
    *,
    plan_id: str,
    size: str,
    entry_type: str,
    interval: str,
    filed_at: datetime,
    code_version: str | None = None,
    account: str | None = None,
    entry: str | None = None,
    fractions: Sequence[str] | None = None,
    break_even_r: str | None = None,
    break_even_offset_r: str | None = None,
    trail_r: str | None = None,
    trail_start_r: str | None = None,
    expires: str | None = None,
    activated_at: str | None = None,
    note: str | None = None,
) -> ActivateRequest:
    """Every string `fmits trade activate` accepts, converted exactly once.

    The **size's asset is read off the commitment**, never typed. A size in the
    wrong asset is the one input the domain cannot catch on its own: `1` is a
    legal quantity of BTC and of USDT, and only the market the plan names says
    which one the owner meant.
    """
    plan = store.plans.load(require_text(plan_id, "plan_id"))
    return ActivateRequest(
        plan_id=plan.plan_id,
        account=AccountId(account or DEFAULT_PAPER_ACCOUNT),
        quantity=Quantity(_decimal(size, "size"), plan.market.base_asset),
        entry_type=_entry_type(entry_type),
        interval=interval,
        activated_at=_instant_or(activated_at, filed_at, "activated-at"),
        written_at=filed_at,
        code_version=code_version or fmis.__version__,
        entry_price=_optional_decimal(entry, "entry price"),
        fractions=tuple(
            _decimal(share, f"share {position + 1}")
            for position, share in enumerate(fractions or ())
        ),
        stop_management=_stop_management(
            break_even_r=break_even_r,
            break_even_offset_r=break_even_offset_r,
            trail_r=trail_r,
            trail_start_r=trail_start_r,
        ),
        expires_at=(
            Absent("this activation does not expire")
            if expires is None
            else _instant(expires, "expires")
        ),
        note=Absent("no note") if note is None else note,
    )


def amend_request_from_text(
    *,
    activation_id: str,
    new_stop: str,
    reason: str,
    author: str,
    filed_at: datetime,
    code_version: str | None = None,
    occurred_at: str | None = None,
    note: str | None = None,
) -> AmendStopRequest:
    return AmendStopRequest(
        activation_id=activation_id,
        new_stop=_decimal(new_stop, "stop"),
        reason=reason,
        author=author,
        occurred_at=_instant_or(occurred_at, filed_at, "occurred-at"),
        written_at=filed_at,
        code_version=code_version or fmis.__version__,
        note=Absent("no note") if note is None else note,
    )


def cancel_request_from_text(
    *,
    activation_id: str,
    reason: str,
    author: str,
    filed_at: datetime,
    code_version: str | None = None,
    occurred_at: str | None = None,
    note: str | None = None,
) -> CancelRequest:
    return CancelRequest(
        activation_id=activation_id,
        reason=reason,
        author=author,
        occurred_at=_instant_or(occurred_at, filed_at, "occurred-at"),
        written_at=filed_at,
        code_version=code_version or fmis.__version__,
        note=Absent("no note") if note is None else note,
    )


def states_from_text(states: Sequence[str] | None) -> tuple[TradeLifecycleState, ...]:
    """A filter over lifecycle states, or the empty one that matches everything.

    Empty means *no restriction* rather than *nothing*: a filter whose default
    excludes rows silently truncates the first listing anybody writes.
    """
    if not states:
        return ()
    resolved: list[TradeLifecycleState] = []
    for raw in states:
        try:
            resolved.append(TradeLifecycleState(raw))
        except ValueError as error:
            raise PaperRefusedError(
                f"lifecycle state {raw!r} is not one of "
                f"{sorted(LIFECYCLE_STATE_CHOICES)}"
            ) from error
    return tuple(resolved)
