"""Milestone BU — the refusal mechanism, and every comparison it must refuse.

The brief names the comparisons that must not be made, and each is a test here:

    BTC over 24 hourly bars vs SPX over 24 session bars, as one duration
    a price return ranked against a yield's basis-point change
    a VIX level ranked against a gold return
    two markets whose units differ, ordered by percentage move

None of those raises anything on its own. They are all arithmetic that works,
producing a page that is wrong in a way no crash reveals — so the refusal has to
be a computed value rather than a convention a renderer is trusted to observe,
and these tests are what prove it is one.
"""

from __future__ import annotations

import itertools

import pytest

from fmis.macro import (
    COMPARABILITY_RULE,
    CORRELATION_COMPARABILITY_RULE,
    Comparability,
    ComparabilityKey,
    NotComparableReason,
    compare_for_correlation,
    compare_keys,
)
from fmis.market_pulse import QuantityKind

RETURN = "period_return"


def key(
    *,
    kind: QuantityKind = QuantityKind.PRICE_LIKE,
    unit: str = "USDT",
    interval: str = "1h",
    horizon: str = "24_bars",
    metric: str = RETURN,
) -> ComparabilityKey:
    return ComparabilityKey(
        quantity_kind=kind,
        quote_unit=unit,
        observation_interval=interval,
        horizon_id=horizon,
        metric=metric,
    )


CRYPTO = key()
EQUITY = key(unit="index points", interval="1d", horizon="21_observations")
YIELD = key(
    kind=QuantityKind.RATE_LIKE,
    unit="percent per annum",
    interval="1d",
    horizon="21_observations",
)


# --------------------------------------------------------------------------
# The permitted case
# --------------------------------------------------------------------------


def test_two_identical_keys_are_comparable_and_carry_no_reason() -> None:
    verdict = compare_keys(CRYPTO, key())
    assert verdict.is_comparable
    assert verdict.reasons == ()
    assert verdict.explain() == ""


def test_two_markets_differing_only_in_identity_are_comparable() -> None:
    """*BTC's 24-bar return against ETH's 24-bar return* — the valid case the
    brief names. A key holds no benchmark id, precisely so that two different
    markets measured identically compare equal."""
    assert compare_keys(key(), key()).is_comparable


# --------------------------------------------------------------------------
# Each component refuses on its own
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("other", "reason"),
    [
        (
            key(kind=QuantityKind.RATE_LIKE),
            NotComparableReason.DIFFERENT_QUANTITY_KIND,
        ),
        (key(unit="EUR"), NotComparableReason.DIFFERENT_QUOTE_UNIT),
        (key(interval="1d"), NotComparableReason.DIFFERENT_OBSERVATION_INTERVAL),
        (key(horizon="168_bars"), NotComparableReason.DIFFERENT_HORIZON),
        (
            key(metric="realized_volatility"),
            NotComparableReason.DIFFERENT_METRIC,
        ),
    ],
)
def test_one_differing_component_refuses_and_names_itself(
    other: ComparabilityKey, reason: NotComparableReason
) -> None:
    verdict = compare_keys(CRYPTO, other)
    assert not verdict.is_comparable
    assert verdict.reasons == (reason,)
    assert reason.value.replace("_", " ") in verdict.explain()


def test_every_component_of_the_key_has_a_check() -> None:
    """A field added to the key without a check here would be a component that
    silently never refuses. This is what makes that omission visible."""
    fields = set(ComparabilityKey.__dataclass_fields__)
    refusing = set()
    for field in fields:
        changed = {
            "quantity_kind": QuantityKind.RATE_LIKE,
            "quote_unit": "OTHER",
            "observation_interval": "99d",
            "horizon_id": "other",
            "metric": "other_metric",
        }[field]
        other = ComparabilityKey(
            **{**{f: getattr(CRYPTO, f) for f in fields}, field: changed}
        )
        if not compare_keys(CRYPTO, other).is_comparable:
            refusing.add(field)
    assert refusing == fields


# --------------------------------------------------------------------------
# A refusal names every difference, not the first
# --------------------------------------------------------------------------


def test_a_refusal_names_every_component_that_differs() -> None:
    """*A reader told only that units differ will change the units and be
    refused again for the interval.*"""
    verdict = compare_keys(CRYPTO, YIELD)
    assert not verdict.is_comparable
    assert set(verdict.reasons) == {
        NotComparableReason.DIFFERENT_QUANTITY_KIND,
        NotComparableReason.DIFFERENT_QUOTE_UNIT,
        NotComparableReason.DIFFERENT_OBSERVATION_INTERVAL,
        NotComparableReason.DIFFERENT_HORIZON,
    }


def test_the_reasons_are_ordered_deterministically() -> None:
    """The page prints them, so their order must be a function of the rule
    rather than of a set's iteration order."""
    first = compare_keys(CRYPTO, YIELD).reasons
    for _ in range(20):
        assert compare_keys(CRYPTO, YIELD).reasons == first


def test_no_component_is_named_twice() -> None:
    verdict = compare_keys(CRYPTO, YIELD)
    assert len(set(verdict.reasons)) == len(verdict.reasons)


# --------------------------------------------------------------------------
# The comparisons the brief forbids
# --------------------------------------------------------------------------


def test_crypto_hourly_against_equity_session_bars_is_refused() -> None:
    """*24 hourly bars and 24 daily bars are the same count over windows
    differing by a factor of twenty-four.*"""
    hourly = key(horizon="24_bars", interval="1h")
    session = key(horizon="24_bars", interval="1d", unit="USDT")
    verdict = compare_keys(hourly, session)
    assert not verdict.is_comparable
    assert (
        NotComparableReason.DIFFERENT_OBSERVATION_INTERVAL in verdict.reasons
    )


def test_a_yield_basis_point_change_against_a_price_return_is_refused() -> None:
    assert not compare_keys(EQUITY, YIELD).is_comparable
    assert (
        NotComparableReason.DIFFERENT_QUANTITY_KIND
        in compare_keys(EQUITY, YIELD).reasons
    )


def test_a_volatility_level_against_a_price_return_is_refused() -> None:
    """*VIX level vs gold return ranked together as "strongest".*"""
    vix = key(unit="volatility points", interval="1d", horizon="21_observations")
    gold = key(unit="USD per troy ounce", interval="1d", horizon="21_observations")
    assert not compare_keys(vix, gold).is_comparable


def test_two_different_metrics_over_one_market_are_refused() -> None:
    """A correlation and a return are not two values of one quantity."""
    assert not compare_keys(
        key(metric="period_return"), key(metric="pearson_correlation")
    ).is_comparable


# --------------------------------------------------------------------------
# Symmetry
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right"), list(itertools.combinations([CRYPTO, EQUITY, YIELD], 2))
)
def test_comparability_is_symmetric(
    left: ComparabilityKey, right: ComparabilityKey
) -> None:
    """*Comparability is a property of the pair rather than of an order.*"""
    forward = compare_keys(left, right)
    backward = compare_keys(right, left)
    assert forward.is_comparable == backward.is_comparable
    assert set(forward.reasons) == set(backward.reasons)


# --------------------------------------------------------------------------
# The correlation rule — weaker, and only in the unit
# --------------------------------------------------------------------------


def test_a_correlation_ignores_the_unit_because_returns_are_ratios() -> None:
    """*Refusing to correlate the S&P with Bitcoin because one is quoted in
    index points would refuse the whole cross-asset question.*"""
    left = key(unit="USDT", interval="1d", horizon="21_observations")
    right = key(unit="index points", interval="1d", horizon="21_observations")
    assert not compare_keys(left, right).is_comparable
    assert compare_for_correlation(left, right).is_comparable


def test_a_correlation_still_refuses_a_yield_against_a_price() -> None:
    """*A yield's simple return is a ratio of two rates.* The one requirement
    that must not be dropped along with the unit."""
    left = key(interval="1d", horizon="21_observations")
    right = key(
        kind=QuantityKind.RATE_LIKE,
        unit="percent per annum",
        interval="1d",
        horizon="21_observations",
    )
    verdict = compare_for_correlation(left, right)
    assert not verdict.is_comparable
    assert verdict.reasons == (NotComparableReason.DIFFERENT_QUANTITY_KIND,)


def test_a_correlation_still_refuses_two_different_cadences() -> None:
    left = key(interval="1h")
    right = key(interval="1d")
    assert not compare_for_correlation(left, right).is_comparable


def test_a_correlation_still_refuses_two_different_horizons() -> None:
    assert not compare_for_correlation(
        key(horizon="24_bars"), key(horizon="168_bars")
    ).is_comparable


def test_a_correlation_still_refuses_two_different_metrics() -> None:
    assert not compare_for_correlation(
        key(metric="a"), key(metric="b")
    ).is_comparable


def test_the_correlation_rule_drops_the_unit_and_nothing_else() -> None:
    """Stated structurally, so a future edit that quietly dropped a second
    requirement fails here rather than on a page."""
    unit_only = key(unit="EUR")
    assert compare_for_correlation(CRYPTO, unit_only).is_comparable
    for other in (
        key(kind=QuantityKind.RATE_LIKE),
        key(interval="1d"),
        key(horizon="other"),
        key(metric="other"),
    ):
        assert not compare_for_correlation(CRYPTO, other).is_comparable


# --------------------------------------------------------------------------
# The verdict type cannot express a contradiction
# --------------------------------------------------------------------------


def test_a_permitted_comparison_cannot_carry_an_objection() -> None:
    with pytest.raises(ValueError, match="cannot be permitted while carrying"):
        Comparability(
            is_comparable=True,
            reasons=(NotComparableReason.DIFFERENT_QUOTE_UNIT,),
        )


def test_a_refusal_cannot_be_made_without_a_reason() -> None:
    with pytest.raises(ValueError, match="refused for no stated reason"):
        Comparability(is_comparable=False, reasons=())


def test_a_component_cannot_be_named_twice_as_a_reason() -> None:
    with pytest.raises(ValueError, match="named twice"):
        Comparability(
            is_comparable=False,
            reasons=(
                NotComparableReason.DIFFERENT_QUOTE_UNIT,
                NotComparableReason.DIFFERENT_QUOTE_UNIT,
            ),
        )


def test_a_reason_must_be_a_reason() -> None:
    with pytest.raises(TypeError, match="NotComparableReason"):
        Comparability(is_comparable=False, reasons=("different unit",))


# --------------------------------------------------------------------------
# The key itself
# --------------------------------------------------------------------------


def test_a_key_is_frozen_and_hashable_so_grouping_is_a_lookup() -> None:
    assert hash(key()) == hash(key())
    assert len({key(), key(), key(unit="EUR")}) == 2
    with pytest.raises(Exception):
        key().quote_unit = "EUR"


@pytest.mark.parametrize("argument", ["unit", "interval", "horizon", "metric"])
def test_a_key_refuses_a_blank_component(argument: str) -> None:
    """A component nobody stated is not a component that matches everything."""
    with pytest.raises(ValueError, match="must not be blank"):
        key(**{argument: "   "})


@pytest.mark.parametrize("argument", ["unit", "interval", "horizon", "metric"])
def test_a_key_refuses_a_component_that_is_not_text(argument: str) -> None:
    with pytest.raises(TypeError, match="must be a str"):
        key(**{argument: 7})


def test_a_key_refuses_a_quantity_kind_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="QuantityKind"):
        ComparabilityKey(
            quantity_kind="price_like",
            quote_unit="USDT",
            observation_interval="1h",
            horizon_id="h",
            metric="m",
        )


def test_the_key_label_names_every_component_it_compares() -> None:
    label = EQUITY.label
    for part in ("period_return", "price_like", "index points", "21_observations", "1d"):
        assert part in label


def test_compare_refuses_something_that_is_not_a_key() -> None:
    for bad in ("key", None, 7):
        with pytest.raises(TypeError, match="ComparabilityKey"):
            compare_keys(CRYPTO, bad)
        with pytest.raises(TypeError, match="ComparabilityKey"):
            compare_keys(bad, CRYPTO)
        with pytest.raises(TypeError, match="ComparabilityKey"):
            compare_for_correlation(CRYPTO, bad)


# --------------------------------------------------------------------------
# The rules are printed, not implied
# --------------------------------------------------------------------------


def test_both_rules_are_stated_in_prose_for_the_page_to_print() -> None:
    assert "same kind of quantity" in COMPARABILITY_RULE
    assert "same unit" in COMPARABILITY_RULE
    assert "carry no unit" in CORRELATION_COMPARABILITY_RULE
    assert COMPARABILITY_RULE != CORRELATION_COMPARABILITY_RULE


def test_no_rule_claims_a_causal_relationship() -> None:
    for text in (COMPARABILITY_RULE, CORRELATION_COMPARABILITY_RULE):
        lowered = text.lower()
        for banned in ("because of", "causes", "drives", "leads to", "predicts"):
            assert banned not in lowered
