"""Milestone CB extracted three primitives out of `swing_lab`. **Nothing moved.**

Each of these functions is now defined once, in `fmis.research_design.numeric`,
and the laboratory calls it. An extraction that changed a value would change
Milestone CA's control draws, Milestone BZ's excursion quantiles and Milestone
BX's concentration figures at once, so each is pinned here by value, by error type
and by error message.

The seed test is the one that matters most: a different seed is a different set
of controls, and a study whose controls moved is a different experiment reported
under the same digest.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest

from fmis.research_design.models import ResearchDesignError
from fmis.research_design.numeric import (
    derive_seed as general_seed,
    largest_share,
    nearest_rank_quantile as general_quantile,
)
from fmis.swing_lab.admission_matching import derive_seed
from fmis.swing_lab.metrics import nearest_rank_quantile
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.robustness import concentration_of_magnitudes


class TestTheSeedIsUnchanged:
    """The identity string is byte-for-byte what Milestone CA sealed."""

    def test_the_seed_is_still_sha256_over_the_pipe_joined_identity(self) -> None:
        identity = "7|fam|development|BTCUSDT|123|4"
        expected = int.from_bytes(
            hashlib.sha256(identity.encode("utf-8")).digest()[:8], "big"
        )
        assert (
            derive_seed(
                master=7,
                family_id="fam",
                sample="development",
                symbol="BTCUSDT",
                bar_index=123,
                replicate=4,
            )
            == expected
        )

    def test_the_laboratory_wrapper_and_the_general_function_agree(self) -> None:
        assert derive_seed(
            master=1,
            family_id="ca_null_matched_timing",
            sample="holdout",
            symbol="TRXUSDT",
            bar_index=9_001,
            replicate=0,
        ) == general_seed(
            master=1,
            parts=("ca_null_matched_timing", "holdout", "TRXUSDT", 9_001, 0),
        )

    def test_two_different_identities_never_share_a_seed(self) -> None:
        first = derive_seed(
            master=1, family_id="a", sample="b", symbol="c", bar_index=1, replicate=2
        )
        second = derive_seed(
            master=1, family_id="a", sample="b", symbol="c", bar_index=2, replicate=1
        )
        assert first != second

    def test_the_laboratory_keeps_its_own_error_type_and_message(self) -> None:
        with pytest.raises(SwingLabError, match="master must be an int"):
            derive_seed(
                master="1",  # type: ignore[arg-type]
                family_id="a",
                sample="b",
                symbol="c",
                bar_index=1,
                replicate=0,
            )
        with pytest.raises(SwingLabError, match="replicate must be a non-negative int"):
            derive_seed(
                master=1, family_id="a", sample="b", symbol="c", bar_index=1, replicate=-1
            )

    def test_a_separator_inside_an_identity_part_is_refused(self) -> None:
        """Two identities that join to one string would share one seed."""
        with pytest.raises(SwingLabError, match="separator"):
            derive_seed(
                master=1,
                family_id="a|b",
                sample="c",
                symbol="d",
                bar_index=1,
                replicate=0,
            )

    def test_a_seed_with_no_identity_at_all_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="parts must name"):
            general_seed(master=1, parts=())


class TestTheQuantileIsUnchanged:
    def test_the_nearest_rank_rule_still_returns_a_real_element(self) -> None:
        values = [3.0, 1.0, 2.0, 4.0]
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            assert nearest_rank_quantile(values, fraction) in values

    def test_it_matches_the_general_function_exactly(self) -> None:
        values = [Decimal("1.5"), Decimal("-2"), Decimal("0")]
        for fraction in (0.0, 0.025, 0.5, 0.975, 1.0):
            assert nearest_rank_quantile(values, fraction) == general_quantile(
                values, fraction
            )

    def test_an_empty_sequence_is_an_absence_not_a_zero(self) -> None:
        assert nearest_rank_quantile([], 0.5) is None

    def test_the_laboratory_keeps_its_own_error_type_and_message(self) -> None:
        with pytest.raises(SwingLabError, match="fraction must be a real number"):
            nearest_rank_quantile([1], "half")  # type: ignore[arg-type]
        with pytest.raises(SwingLabError, match=r"fraction must lie in \[0, 1\], got 2"):
            nearest_rank_quantile([1], 2.0)


class TestTheShareIsUnchanged:
    def test_the_largest_cohort_share_is_the_same_number(self) -> None:
        contributions = [("a", Decimal("3")), ("b", Decimal("1")), ("a", Decimal("1"))]
        assert concentration_of_magnitudes(contributions) == Decimal("4") / Decimal("5")

    def test_nothing_contributed_is_an_absence_not_a_zero_share(self) -> None:
        assert concentration_of_magnitudes([("a", Decimal("0"))]) is None

    def test_it_is_generic_over_float_and_decimal(self) -> None:
        assert largest_share([("a", 3.0), ("b", 1.0)]) == pytest.approx(0.75)
        assert largest_share([("a", Decimal("3")), ("b", Decimal("1"))]) == Decimal(
            "0.75"
        )

    def test_the_laboratory_keeps_its_own_error_type_and_message(self) -> None:
        with pytest.raises(SwingLabError, match="negative magnitude"):
            concentration_of_magnitudes([("a", Decimal("-1"))])
