"""The CC seal: pinned, deterministic, and sensitive to every material field.

A pre-registration whose digest does not move when a threshold moves is not a
seal — it is a comment. The mutation class below changes one scientifically
material field at a time and asserts the digest changes, which is the only thing
that makes `CC_PREREGISTRATION_DIGEST` evidence of anything.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from decimal import Decimal

import pytest

from fmis.swing_lab.admission_preregistration import (
    CA_PREREGISTRATION_DIGEST,
    MIN_ADMISSION_EDGE_ATR,
)
from fmis.swing_lab.preregistration import SAMPLES
from fmis.universe.models import FeasibilityVerdict, SurvivorshipClass, UniverseError
from fmis.universe.preregistration import (
    CC_PREREGISTRATION_DIGEST,
    CC_PRE_REGISTRATION,
    DENSITY_SUBSAMPLE_SEED,
    EFFECT_SIZE_GRID,
    ELIGIBLE_QUOTE_ASSET,
    PRIMARY_EFFECT_ATR,
    CcPreregistration,
    cc_preregistration_digest,
    measurement_window,
    representative_of,
    verify_cc_preregistration,
)
from fmis.universe.models import PairStatus, TradingPair


class TestTheSealIsPinned:
    def test_the_recomputed_digest_matches_the_pinned_one(self) -> None:
        """If this fails, the pre-registration changed and the pin did not."""
        assert cc_preregistration_digest() == CC_PREREGISTRATION_DIGEST

    def test_verify_accepts_the_pinned_digest_and_refuses_another(self) -> None:
        assert verify_cc_preregistration(CC_PREREGISTRATION_DIGEST)
        assert not verify_cc_preregistration("0" * 64)

    def test_verify_refuses_a_non_string(self) -> None:
        with pytest.raises(TypeError):
            verify_cc_preregistration(None)  # type: ignore[arg-type]

    def test_the_digest_refuses_a_foreign_object(self) -> None:
        with pytest.raises(TypeError):
            cc_preregistration_digest(object())  # type: ignore[arg-type]

    def test_the_digest_is_stable_across_hash_seeds(self) -> None:
        """A digest that moved with PYTHONHASHSEED would seal nothing."""
        seen = set()
        for seed in ("0", "1", "12345", "999983"):
            result = subprocess.run(
                [
                    sys.executable, "-c",
                    "from fmis.universe.preregistration import "
                    "cc_preregistration_digest as d; print(d())",
                ],
                capture_output=True, text=True, env={"PYTHONHASHSEED": seed, "PATH": ""},
            )
            assert result.returncode == 0, result.stderr
            seen.add(result.stdout.strip())
        assert seen == {CC_PREREGISTRATION_DIGEST}


class TestTheSealMovesWithEveryMaterialField:
    """Mutation coverage. **Every field here can change a scientific answer.**"""

    @pytest.mark.parametrize(
        "field, value",
        [
            ("eligible_quote_asset", "USDC"),
            ("depth_interval", "1w"),
            ("depth_bars_per_year", 252.0),
            ("min_measurement_years", 0.5),
            ("max_missing_fraction", 0.10),
            ("max_gap_bars", 30),
            ("min_median_quote_volume", 1.0),
            ("density_subsample_size", 3),
            ("density_subsample_seed", "a" * 64),
            ("provider", "some-other-exchange"),
            ("representative_rule", "the most liquid pair wins"),
            ("ordering_rule", "descending expectancy"),
            ("discovery_rule", "a hand-written list of fifteen symbols"),
            ("research_question", "does the strategy make money"),
            ("ca_preregistration_digest", "f" * 64),
            ("growth_sizes", (1, 2, 3)),
            ("dependence_scenarios", ("independent",)),
            ("verdict_rules", ("everything is feasible",)),
            ("refutation_conditions", ("nothing could refute this",)),
            ("limitations", ("there are no limitations",)),
        ],
    )
    def test_mutating_a_material_field_moves_the_digest(self, field, value) -> None:
        mutated = replace(CC_PRE_REGISTRATION, **{field: value})
        assert cc_preregistration_digest(mutated) != CC_PREREGISTRATION_DIGEST

    def test_mutating_the_effect_grid_moves_the_digest(self) -> None:
        mutated = replace(
            CC_PRE_REGISTRATION,
            effect_grid=(Decimal("0.10"), Decimal("0.25")),
        )
        assert cc_preregistration_digest(mutated) != CC_PREREGISTRATION_DIGEST

    def test_mutating_the_identity_rules_moves_the_digest(self) -> None:
        """The stablecoin, wrapped and leveraged sets decide the cluster count."""
        rules = dict(CC_PRE_REGISTRATION.identity_rules)
        rules["stablecoin_assets"] = []
        assert cc_preregistration_digest(
            replace(CC_PRE_REGISTRATION, identity_rules=rules)
        ) != CC_PREREGISTRATION_DIGEST

    def test_reordering_a_dict_literal_does_NOT_move_the_digest(self) -> None:
        """`sort_keys` is on, so an editor's reordering is not a seal break."""
        rules = dict(reversed(list(CC_PRE_REGISTRATION.identity_rules.items())))
        assert cc_preregistration_digest(
            replace(CC_PRE_REGISTRATION, identity_rules=rules)
        ) == CC_PREREGISTRATION_DIGEST


class TestTheSealRefusesAnIncoherentDesign:
    def test_a_primary_effect_outside_the_grid_is_refused(self) -> None:
        with pytest.raises(UniverseError, match="not in the declared"):
            replace(CC_PRE_REGISTRATION, primary_effect=Decimal("0.15"))

    @pytest.mark.parametrize(
        "field, value",
        [
            ("density_subsample_size", 0),
            ("min_measurement_years", 0.0),
            ("max_missing_fraction", 1.5),
            ("max_gap_bars", 0),
            ("min_median_quote_volume", -1.0),
        ],
    )
    def test_an_impossible_threshold_is_refused(self, field, value) -> None:
        with pytest.raises(UniverseError):
            replace(CC_PRE_REGISTRATION, **{field: value})

    @pytest.mark.parametrize(
        "field", ["verdict_rules", "refutation_conditions", "limitations"],
    )
    def test_an_empty_required_tuple_is_refused(self, field) -> None:
        with pytest.raises(UniverseError, match="non-empty tuple"):
            replace(CC_PRE_REGISTRATION, **{field: ()})

    def test_an_empty_text_field_is_refused(self) -> None:
        with pytest.raises(UniverseError):
            replace(CC_PRE_REGISTRATION, provider="")


class TestItImportsRatherThanRestates:
    def test_the_primary_effect_is_CA_s_own_constant(self) -> None:
        """A retyped +0.10 could drift from CA's and the two would stop agreeing."""
        assert PRIMARY_EFFECT_ATR == Decimal(str(MIN_ADMISSION_EDGE_ATR))

    def test_the_CA_seal_is_carried_by_identity(self) -> None:
        assert CC_PRE_REGISTRATION.ca_preregistration_digest == CA_PREREGISTRATION_DIGEST

    def test_the_window_is_milestone_BY_s_development_sample(self) -> None:
        start, end = measurement_window()
        development = next(item for item in SAMPLES if item.name == "development")
        assert (start, end) == (development.signal_start, development.signal_end)

    def test_the_primary_effect_is_in_the_grid_and_is_the_smallest(self) -> None:
        assert PRIMARY_EFFECT_ATR in EFFECT_SIZE_GRID
        assert PRIMARY_EFFECT_ATR == min(EFFECT_SIZE_GRID)

    def test_the_subsample_seed_is_derived_not_typed(self) -> None:
        import hashlib

        from fmis.universe.preregistration import CC_PREREGISTRATION_ID

        assert DENSITY_SUBSAMPLE_SEED == hashlib.sha256(
            CC_PREREGISTRATION_ID.encode("utf-8")
        ).hexdigest()


class TestTheRepresentativeRule:
    def _pair(self, symbol: str, quote: str) -> TradingPair:
        return TradingPair(
            symbol=symbol, base_asset="BTC", quote_asset=quote,
            status=PairStatus.TRADING,
        )

    def test_it_prefers_the_eligible_quote_asset(self) -> None:
        chosen = representative_of(
            (self._pair("BTCBUSD", "BUSD"), self._pair("BTCUSDT", ELIGIBLE_QUOTE_ASSET))
        )
        assert chosen.symbol == "BTCUSDT"

    def test_it_falls_back_to_lexicographic_when_none_is_eligible(self) -> None:
        chosen = representative_of(
            (self._pair("BTCEUR", "EUR"), self._pair("BTCBUSD", "BUSD"))
        )
        assert chosen.symbol == "BTCBUSD"

    def test_it_does_not_depend_on_input_order(self) -> None:
        pairs = (
            self._pair("BTCUSDT", ELIGIBLE_QUOTE_ASSET),
            self._pair("BTCFDUSD", "FDUSD"),
        )
        assert representative_of(pairs) == representative_of(tuple(reversed(pairs)))

    def test_it_refuses_an_empty_group(self) -> None:
        with pytest.raises(UniverseError, match="no pairs"):
            representative_of(())


class TestTheVocabularyIsSealed:
    def test_every_verdict_and_survivorship_member_is_in_the_payload(self) -> None:
        """Adding a verdict member must move the seal, not slip in silently."""
        payload = CC_PRE_REGISTRATION.payload()
        assert payload["verdict_vocabulary"] == [
            item.value for item in FeasibilityVerdict
        ]
        assert payload["survivorship_vocabulary"] == [
            item.value for item in SurvivorshipClass
        ]
