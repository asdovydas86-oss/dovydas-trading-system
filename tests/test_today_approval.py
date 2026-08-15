"""Milestone BN's integration into `fmits today`: an approval per candidate.

The rule this file exists to hold is a single one, and it is negative: **a
candidate with no approval prints a stated absence, never a blank.** A blank in
the column where a status belongs reads as a candidate nothing objected to, and
that is the single most expensive misreading this page can produce.

Four inputs can be missing — the store, the price source, a risk budget, an
account — and each produces its own sentence, because the four have four
different remedies and one blank.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from persistence_helpers import risk_budget, write_request
from portfolio_risk_helpers import groups, line, state, usdt
from position_sizing_helpers import ceiling, engine, owner, policy
from today_helpers import REFERENCE, reading, result
from tests.test_swing_setup_render import (
    candidate_short_with_watched_level,
    confirmed_long,
    waiting,
)
from trade_domain_helpers import ACCOUNT, AT, trade
from valuation_helpers import store_with, valued, with_cash

from fmis.accounts import AccountId, Book
from fmis.position_sizing import (
    ApprovalResult,
    SizingPolicy,
    approve_results,
)
from fmis.provenance import Absent
from fmis.today import (
    NotAvailable,
    OpportunityLine,
    StoreReading,
    TodayError,
    approvals_for,
    build_today,
    render_today,
)
from fmis.today.sections import opportunities_from_results


# --------------------------------------------------------------------------
# Real assessments, produced by the real engine.
# --------------------------------------------------------------------------
#
# Hand-built stand-ins were the first draft and `SetupRunResult` refused them,
# which is the type doing its job: a page assembled from a shape the engine
# cannot produce proves nothing about the page. `confirmed_long()` is BTCUSDT at
# a reference close of 100.0 with a stop at 90.0 and a target at 110.0 — a risk
# distance of 10 and a reward distance of 10.


def scan(*assessments: Any) -> tuple[Any, ...]:
    return tuple(result(item) for item in (assessments or (confirmed_long(),)))


def priced(root: Path) -> Any:
    """A store reading with a valuation, a budget and one account."""
    store = store_with(root, trade(), snapshots=(with_cash(),))
    store.risk.create(
        risk_budget(limits=(ceiling("0.02"),)), request=write_request()
    )
    return store


# ==========================================================================
# 1. The five fields on an opportunity line
# ==========================================================================


def test_a_line_with_no_approval_carries_none_in_all_five_fields() -> None:
    built = OpportunityLine(symbol="BTCUSDT", state="confirmed", sufficiency="sufficient")
    assert built.approval_status is None
    assert built.recommended_size is None
    assert built.open_risk_after is None
    assert built.blocking_reasons == ()
    assert built.approval_warnings == ()
    assert not built.was_approved_against_limits


def test_reasons_without_a_status_are_refused_because_nothing_could_trace_them() -> None:
    with pytest.raises(TodayError, match="approval reasons with no approval status"):
        OpportunityLine(
            symbol="BTCUSDT",
            state="confirmed",
            sufficiency="sufficient",
            blocking_reasons=("no stop",),
        )


def test_a_status_alone_is_a_complete_line() -> None:
    built = OpportunityLine(
        symbol="BTCUSDT",
        state="confirmed",
        sufficiency="sufficient",
        approval_status="approved",
    )
    assert built.was_approved_against_limits


@pytest.mark.parametrize(
    "field", ["approval_status", "recommended_size", "open_risk_after"]
)
def test_every_approval_field_is_text_or_none(field: str) -> None:
    with pytest.raises(TodayError):
        OpportunityLine(
            symbol="BTCUSDT",
            state="confirmed",
            sufficiency="sufficient",
            **{field: "  "},
        )


# ==========================================================================
# 2. An approval reaches the line
# ==========================================================================


def approved(results: Any = None, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "engine": engine(classification=groups(BTC=["l1"])),
        "state": state(line(), equity=usdt("100000")),
        "budget": risk_budget(limits=(ceiling("0.02"),)),
        "owner": owner(),
        "account": ACCOUNT,
        "book": Book.SWING,
    }
    values.update(overrides)
    return approve_results(scan() if results is None else results, **values)


def test_an_approval_reaches_the_opportunity_line_as_five_printable_values() -> None:
    found = opportunities_from_results(scan(), approved())
    entry = found.confirmed[0]
    assert entry.approval_status in {"approved", "blocked", "indeterminate"}
    assert "BTC" in entry.recommended_size
    assert "USDT" in entry.open_risk_after


def test_a_refused_candidate_becomes_a_blocking_reason_rather_than_a_silence() -> None:
    """*'No stop, so no size'* is the most useful sentence on the row."""
    found = opportunities_from_results(
        scan(),
        {"BTCUSDT": Absent("BTCUSDT has no stop level, so no size can be produced")},
    )
    entry = found.confirmed[0]
    assert entry.approval_status == "not sizeable"
    assert entry.blocking_reasons
    assert "no size can be produced" in entry.blocking_reasons[0]
    assert "unavailable — " in entry.recommended_size


def test_no_approvals_at_all_leaves_every_field_none() -> None:
    entry = opportunities_from_results(scan()).confirmed[0]
    assert entry.approval_status is None


def test_an_approval_that_produced_no_size_prints_the_reason_in_its_place() -> None:
    """The approval ran; the size did not exist. A blank would read as zero.

    The budget here states a ceiling with no default below it and the owner
    stated no fraction, which is the product's *"a ceiling is not a target"*
    refusal reaching the workspace page.
    """
    found = opportunities_from_results(
        scan(),
        approved(budget=risk_budget(limits=(ceiling("0.02", default=None),))),
    )
    entry = found.confirmed[0]
    assert entry.approval_status == "indeterminate"
    assert entry.recommended_size.startswith("unavailable — ")
    assert "ceiling is a ceiling and not a target" in entry.recommended_size


def test_a_candidate_state_carries_an_approval_too() -> None:
    results = scan(candidate_short_with_watched_level())
    found = opportunities_from_results(results, approved(results=results))
    assert found.candidates[0].approval_status is not None


def test_a_waiting_result_is_never_approved_because_it_has_no_side() -> None:
    """A `WAIT` falls out of the candidate filter on the engine's own fact."""
    results = scan(waiting())
    assert approved(results=results) == {}
    found = opportunities_from_results(results)
    assert found.waiting
    assert not found.confirmed


# ==========================================================================
# 3. The note — four missing inputs, four sentences
# ==========================================================================


def test_no_valuation_says_so_and_names_the_flags_that_fix_it() -> None:
    found, note = approvals_for(reading(), scan(), policy=policy())
    assert found == {}
    assert isinstance(note, NotAvailable)
    assert "no portfolio reading was produced" in note.reason
    assert "--no-records" in note.owned_by


def test_no_budget_says_the_owner_has_recorded_no_limits(tmp_path: Path) -> None:
    valuation = valued(tmp_path, trade(), snapshots=(with_cash(),))
    found, note = approvals_for(
        reading(valuation=valuation, budget=None, account=ACCOUNT),
        scan(),
        policy=policy(),
    )
    assert found == {}
    assert "no single risk-budget lineage is in force" in note.reason


def test_no_resolvable_account_says_which_flag_names_one(tmp_path: Path) -> None:
    valuation = valued(tmp_path, trade(), snapshots=(with_cash(),))
    found, note = approvals_for(
        reading(
            valuation=valuation,
            budget=risk_budget(limits=(ceiling("0.02"),)),
            account=Absent("this store records fills in 2 accounts"),
        ),
        scan(),
        policy=policy(),
    )
    assert found == {}
    assert "records fills in 2 accounts" in note.reason
    assert "--account" in note.owned_by


def test_a_store_that_was_never_read_says_that_rather_than_naming_an_account(
    tmp_path: Path,
) -> None:
    valuation = valued(tmp_path, trade(), snapshots=(with_cash(),))
    _, note = approvals_for(
        reading(
            valuation=valuation,
            budget=risk_budget(limits=(ceiling("0.02"),)),
            account=None,
        ),
        scan(),
        policy=policy(),
    )
    assert "the store was not read" in note.reason


def test_a_complete_reading_produces_approvals_and_a_note_naming_the_scope(
    tmp_path: Path,
) -> None:
    valuation = valued(tmp_path, trade(), snapshots=(with_cash(),))
    found, note = approvals_for(
        reading(
            valuation=valuation,
            budget=risk_budget(limits=(ceiling("0.02"),)),
            account=ACCOUNT,
        ),
        scan(),
        policy=policy(risk_fraction=Decimal("0.01")),
    )
    assert isinstance(found["BTCUSDT"], ApprovalResult)
    assert isinstance(note, str)
    assert "swing_budget" in note
    assert "binance_spot" in note
    assert "independently of the others" in note


def test_an_explicit_account_overrides_the_one_the_store_inferred(
    tmp_path: Path,
) -> None:
    valuation = valued(tmp_path, trade(), snapshots=(with_cash(),))
    _, note = approvals_for(
        reading(
            valuation=valuation,
            budget=risk_budget(limits=(ceiling("0.02"),)),
            account=Absent("two accounts"),
        ),
        scan(),
        policy=policy(risk_fraction=Decimal("0.01")),
        account=AccountId("chosen"),
    )
    assert "account chosen" in note


def test_a_stated_timezone_reaches_the_owner_context(tmp_path: Path) -> None:
    valuation = valued(tmp_path, trade(), snapshots=(with_cash(),))
    found, _ = approvals_for(
        reading(
            valuation=valuation,
            budget=risk_budget(limits=(ceiling("0.02"),)),
            account=ACCOUNT,
        ),
        scan(),
        policy=policy(risk_fraction=Decimal("0.01")),
        timezone="Europe/London",
    )
    assert found


def test_the_policy_must_be_a_policy() -> None:
    with pytest.raises(TypeError, match="SizingPolicy"):
        approvals_for(reading(), scan(), policy="owner_sizing")  # type: ignore[arg-type]


# ==========================================================================
# 4. The page
# ==========================================================================


def workspace(**overrides: Any) -> Any:
    values: dict[str, Any] = {
        "results": scan(),
        "reading": reading(),
        "reference_time": REFERENCE,
        "source": "test",
    }
    values.update(overrides)
    results = values.pop("results")
    return build_today(results, **values)


def test_the_page_prints_a_stated_absence_when_nothing_was_approved() -> None:
    text = render_today(workspace())
    assert "approval" in text
    assert "not available" in text
    assert "Do not read an unapproved candidate" in text
    assert "- — see the note above" in text


def test_the_page_prints_the_status_the_size_and_the_open_risk_after(
    tmp_path: Path,
) -> None:
    valuation = valued(tmp_path, trade(), snapshots=(with_cash(),))
    store_reading = reading(
        valuation=valuation,
        budget=risk_budget(limits=(ceiling("0.02"),)),
        account=ACCOUNT,
    )
    found, note = approvals_for(
        store_reading, scan(), policy=policy(risk_fraction=Decimal("0.01"))
    )
    text = render_today(
        workspace(reading=store_reading, approvals=found, approval_note=note)
    )
    assert "approval    " in text
    assert "size        " in text
    assert "open risk after" in text


def test_the_page_prints_a_blocking_reason_under_its_own_label() -> None:
    found = {"BTCUSDT": Absent("BTCUSDT has no stop level, so no size is produced")}
    text = render_today(
        workspace(
            results=scan(),
            approvals=found,
            approval_note="one candidate could not be sized",
        )
    )
    assert "NOT SIZEABLE" in text
    assert "blocking:" in text


def test_no_line_on_the_page_exceeds_the_width(tmp_path: Path) -> None:
    valuation = valued(tmp_path, trade(), snapshots=(with_cash(),))
    store_reading = reading(
        valuation=valuation,
        budget=risk_budget(limits=(ceiling("0.02"),)),
        account=ACCOUNT,
    )
    found, note = approvals_for(
        store_reading, scan(), policy=policy(risk_fraction=Decimal("0.01"))
    )
    text = render_today(
        workspace(reading=store_reading, approvals=found, approval_note=note)
    )
    assert [row for row in text.splitlines() if len(row) > 78] == []


# ==========================================================================
# 5. The store reading carries the account it inferred
# ==========================================================================


def test_a_store_reading_carries_the_account_or_the_reason_there_is_none(
    tmp_path: Path,
) -> None:
    from fmis.today import read_store

    priced(tmp_path)
    found = read_store(tmp_path, at=AT(12))
    assert found.account == ACCOUNT


def test_an_empty_reading_carries_no_account_at_all() -> None:
    from fmis.today import empty_reading

    assert empty_reading("/tmp/nowhere").account is None


def test_the_schema_version_moved_because_the_shape_did() -> None:
    from fmis.today import TODAY_SCHEMA_VERSION

    assert TODAY_SCHEMA_VERSION == 2
