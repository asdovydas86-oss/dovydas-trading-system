"""Milestone BM — the outer edge: fetch what the store needs, value it.

Everything that touches a network lives in `fmis.valuation.compose`, so this is
where the network-facing rules are pinned — with an injected transport, so no
test here opens a socket.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from marks_helpers import failing_transport, klines_transport
from persistence_helpers import new_store, write_request
from trade_domain_helpers import AT, MARKET, USDT, trade
from valuation_helpers import DUST, store_with, with_cash

from fmis.money import Money
from fmis.provenance import Absent
from fmis.valuation import (
    DEFAULT_BASE_CURRENCY,
    DEFAULT_PORTFOLIO_ID,
    VALUATION_DUST_POLICY,
    PortfolioStoreError,
    marks_for_store,
    run_valuation,
)

CLOCK = lambda: AT(20)  # noqa: E731 - a pinned instant, injected everywhere below


# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------


def test_the_default_portfolio_id_is_a_legal_domain_identifier() -> None:
    """Underscored rather than hyphenated: a default that failed
    `IDENTIFIER_PATTERN` would fail at the first call rather than at review."""
    from fmis.records import IDENTIFIER_PATTERN, require_pattern

    assert require_pattern(DEFAULT_PORTFOLIO_ID, IDENTIFIER_PATTERN, "id")


def test_the_default_base_currency_is_what_the_priced_markets_quote_in() -> None:
    assert DEFAULT_BASE_CURRENCY == "USDT"


def test_the_dust_policy_configures_no_threshold() -> None:
    """Zero is the only tolerance that is not a policy decision, and this package
    chooses no policy on the owner's behalf."""
    assert VALUATION_DUST_POLICY.thresholds == ()


# --------------------------------------------------------------------------
# marks_for_store
# --------------------------------------------------------------------------


def test_only_the_markets_the_store_holds_are_fetched(tmp_path) -> None:
    root = tmp_path / "store"
    store_with(root)
    seen: list[str] = []

    def _capturing(url: str):
        seen.append(url)
        return klines_transport(60000.0, 61000.0)(url)

    prices = marks_for_store(
        root, taken_at=AT(20), transport=_capturing, clock=CLOCK
    )
    assert len(seen) == 1
    assert "symbol=BTCUSDT" in seen[0]
    assert prices.reading_for("BTCUSDT").price == 61000.0


def test_an_owner_holding_nothing_costs_no_request(tmp_path) -> None:
    def _never(url: str):  # pragma: no cover - proving it is never reached
        raise AssertionError("a request was made for a store with no positions")

    prices = marks_for_store(
        tmp_path / "empty", taken_at=AT(20), transport=_never
    )
    assert prices.is_empty is True
    assert "no open position" in prices.source


def test_a_provider_outage_becomes_a_reason_rather_than_a_failed_run(
    tmp_path,
) -> None:
    root = tmp_path / "store"
    store_with(root)
    prices = marks_for_store(
        root, taken_at=AT(20), transport=failing_transport("connection reset"),
        clock=CLOCK,
    )
    assert prices.priced_symbols == ()
    assert "connection reset" in prices.reason_for("BTCUSDT")


def test_a_corrupt_store_is_reported_as_this_packages_own_error(tmp_path) -> None:
    """`fmis.pipeline.cli` may not import the store, so it cannot catch an
    exception it has no name for. Wrapping here is what keeps that boundary."""
    root = tmp_path / "store"
    store_with(root)
    index = next(root.rglob("*.jsonl"))
    index.write_text("{ not json at all\n", encoding="utf-8")
    with pytest.raises(PortfolioStoreError, match="could not be read"):
        marks_for_store(root, taken_at=AT(20), transport=klines_transport(1.0))


def test_the_interval_reaches_the_request(tmp_path) -> None:
    root = tmp_path / "store"
    store_with(root)
    seen: list[str] = []

    def _capturing(url: str):
        seen.append(url)
        return klines_transport(1.0, 2.0)(url)

    marks_for_store(
        root, taken_at=AT(20), interval="4h", transport=_capturing, clock=CLOCK
    )
    assert "interval=4h" in seen[0]


# --------------------------------------------------------------------------
# run_valuation
# --------------------------------------------------------------------------


def test_a_full_run_prices_the_store_and_reports_money(tmp_path) -> None:
    root = tmp_path / "store"
    store_with(root, snapshots=(with_cash(),))
    valuation = run_valuation(
        root, as_of=AT(20), transport=klines_transport(60000.0, 61000.0),
        clock=CLOCK,
    )
    assert valuation.market_value == Money(Decimal("30500"), USDT)
    assert valuation.marked_equity == Money(Decimal("33000"), USDT)
    assert valuation.is_fully_marked is True


def test_skipping_marks_is_different_from_every_fetch_failing(tmp_path) -> None:
    """A page that could not tell them apart would report an outage when the
    owner had simply asked not to look."""
    root = tmp_path / "store"
    store_with(root)

    def _never(url: str):  # pragma: no cover - proving it is never reached
        raise AssertionError("a request was made with read_marks=False")

    skipped = run_valuation(root, as_of=AT(20), read_marks=False, transport=_never)
    failed = run_valuation(
        root, as_of=AT(20), transport=failing_transport(), clock=CLOCK
    )
    assert skipped.prices.source == "no price source was consulted"
    assert skipped.prices.unavailable == ()
    assert failed.prices.unavailable != ()


def test_a_skipped_run_still_lists_every_position(tmp_path) -> None:
    root = tmp_path / "store"
    store_with(root)
    valuation = run_valuation(root, as_of=AT(20), read_marks=False)
    assert len(valuation.positions) == 1
    assert isinstance(valuation.market_value, Absent)


def test_a_corrupt_store_fails_the_valuation_rather_than_reading_as_empty(
    tmp_path,
) -> None:
    """A page saying the owner holds nothing is the one output a detected
    corruption must never produce."""
    root = tmp_path / "store"
    store_with(root)
    next(root.rglob("*.jsonl")).write_text("{ not json at all\n", encoding="utf-8")
    with pytest.raises(PortfolioStoreError):
        run_valuation(root, as_of=AT(20), read_marks=False)


def test_a_missing_store_root_is_a_complete_page_rather_than_a_failure(
    tmp_path,
) -> None:
    valuation = run_valuation(tmp_path / "never-created", as_of=AT(20))
    assert valuation.positions == ()
    assert isinstance(valuation.marked_equity, Absent)


def test_a_run_creates_nothing_under_the_store_root(tmp_path) -> None:
    root = tmp_path / "never-created"
    run_valuation(root, as_of=AT(20), read_marks=False)
    assert not root.exists()


def test_two_runs_over_one_store_and_one_price_are_equal(tmp_path) -> None:
    root = tmp_path / "store"
    store_with(root)
    kwargs = dict(
        as_of=AT(20), transport=klines_transport(60000.0, 61000.0), clock=CLOCK
    )
    assert (
        run_valuation(root, **kwargs).to_payload()
        == run_valuation(root, **kwargs).to_payload()
    )


def test_the_portfolio_id_and_currency_are_the_callers_choice(tmp_path) -> None:
    root = tmp_path / "store"
    new_store(root, dust=DUST).trades.create(trade(), request=write_request())
    valuation = run_valuation(
        root, as_of=AT(20), portfolio_id="swing_book", base_currency="USDT",
        read_marks=False,
    )
    assert valuation.portfolio_id == "swing_book"


def test_a_malformed_argument_is_never_reported_as_a_broken_store(tmp_path) -> None:
    """A typo in a flag and a corrupt payload raise the same exception family.
    Validating first is what keeps the owner from being sent to their store
    files over an asset code.
    """
    from fmis.records import DomainValidationError

    root = tmp_path / "store"
    store_with(root)
    with pytest.raises(DomainValidationError, match="asset code"):
        run_valuation(root, as_of=AT(20), base_currency="not a code",
                      read_marks=False)
    with pytest.raises(DomainValidationError, match="portfolio_id"):
        run_valuation(root, as_of=AT(20), portfolio_id="Owner-Portfolio",
                      read_marks=False)


def test_a_past_reference_refuses_todays_price_rather_than_using_it(
    tmp_path,
) -> None:
    """Asking what the portfolio was worth earlier fetches candles that have
    closed since; a mark from after the moment it marks is not that moment's."""
    root = tmp_path / "store"
    store_with(root)
    valuation = run_valuation(
        root, as_of=AT(12), transport=klines_transport(60000.0, 61000.0,
                                                      first_hour=18),
        clock=CLOCK,
    )
    assert valuation.is_fully_marked is False
    assert "after the instant this snapshot describes" in (
        valuation.marks.reasons[MARKET.value]
    )
