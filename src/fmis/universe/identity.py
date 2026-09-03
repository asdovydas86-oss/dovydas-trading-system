"""What a ticker is exposure *to*. **The rule that stops the cluster count inflating.**

Milestone CB's requirement is roughly 467 **clusters**, and the cluster axis
Milestone CA sealed is the symbol. That makes the mapping from ticker to
experimental unit the single most consequential rule in Milestone CC: a universe
that counted `BTCUSDT`, `WBTCUSDT` and `BTCUPUSDT` as three clusters would report
three independent markets where there is one, and every ``1/sqrt(K)`` term drawn
from it would be too small by ``sqrt(3)``.

**Sealed lists, not regular expressions.** The obvious implementation classifies a
leveraged token by its suffix — anything ending ``UP``, ``DOWN``, ``BULL`` or
``BEAR``. Run against Binance's actual USDT listings that rule removes `JUP`
(Jupiter) and `SYRUP` (Maple), two ordinary tokens, and it would keep removing
whatever is listed next whose name happens to end that way. A pattern that
silently deletes real assets to catch derivative ones is worse than a list that
must be maintained, because the list's failure mode is visible in a diff and the
pattern's is not. So every classification below is an explicit, sealed,
digest-covered set.

**The list can only err in one direction, and that direction is stated.** An asset
missing from `STABLECOIN_ASSETS` is classified `NATIVE` and enters the universe,
inflating the cluster count by one. That is the anti-conservative direction, so
the name rule is not trusted alone: `peg_like_by_volatility` is a **measured**
backstop that flags any asset whose realised volatility over the research window
sits below a sealed floor, whatever it is called. The data is allowed to disagree
with the label, and when it does the disagreement is reported rather than
resolved silently.

**Nothing here reads a price direction, an outcome or a strategy result.** Asset
identity is a property of what an instrument *is*, and if it could be influenced
by how an instrument *performed* the universe would be selected on outcomes. A
control asserts this module imports nothing from the swing laboratory.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from typing import Final

from fmis.universe.models import (
    AssetClass,
    EconomicAsset,
    TradingPair,
    UniverseError,
    require_text,
)

__all__ = [
    "STABLECOIN_ASSETS",
    "WRAPPED_REPRESENTATIONS",
    "LEVERAGED_TOKENS",
    "REDENOMINATIONS",
    "PEG_VOLATILITY_FLOOR",
    "IDENTITY_RULE_ID",
    "IDENTITY_RULE_DESCRIPTION",
    "classify_asset",
    "economic_asset_id",
    "peg_like_by_volatility",
    "group_by_economic_asset",
    "identity_rules_payload",
]

#: The identity ruleset's own name, carried into the seal so a later change to
#: any set below changes the pre-registration digest.
IDENTITY_RULE_ID: Final[str] = "cc-economic-identity-v1"

IDENTITY_RULE_DESCRIPTION: Final[str] = (
    "A base asset is STABLECOIN if it appears in STABLECOIN_ASSETS, WRAPPED if it "
    "appears in WRAPPED_REPRESENTATIONS, LEVERAGED_TOKEN if it appears in "
    "LEVERAGED_TOKENS, and NATIVE otherwise. Its economic identity is the "
    "underlying named by WRAPPED_REPRESENTATIONS or LEVERAGED_TOKENS where one "
    "exists, the successor named by REDENOMINATIONS where one exists, and the "
    "base asset itself otherwise. Membership is by exact string equality; no "
    "prefix, suffix or pattern rule is used, because a suffix rule for leveraged "
    "tokens removes JUP and SYRUP."
)

#: Assets that track a peg rather than float against one. **Pegged to anything.**
#:
#: A trend-following admission rule measured on a peg is measuring the peg's
#: tracking noise, and the near-zero ATR of a peg would dominate every
#: volatility-normalised statistic in the study — which is why Milestone BY
#: dropped TUSDUSDT from development and USDCUSDT from the holdout. Euro-pegged
#: tokens are here for the identical reason: the peg is to a different currency,
#: not absent.
#: `PAXG` is deliberately **absent**: it is a claim on gold, which floats against
#: the dollar at roughly fifteen per cent annualised. It is a genuine independent
#: exposure and the only commodity one this listing offers.
STABLECOIN_ASSETS: Final[frozenset[str]] = frozenset(
    {
        # USD-pegged.
        "BFUSD", "BUSD", "DAI", "FDUSD", "PAX", "RLUSD", "SUSD", "TUSD",
        "USD1", "USDC", "USDE", "USDP", "USDS", "USDSB", "USDSOLD", "USDT", "XUSD",
        # Non-USD pegs. A peg to the euro is still a peg, and a trend measured
        # across one is the cross rate's trend rather than the asset's.
        "AEUR", "EUR", "EURI", "GBP", "AUD", "TRY", "BRL", "ARS", "RUB", "UAH",
        "IDRT", "NGN", "ZAR", "BIDR", "BVND",
    }
)

#: A wrapped or receipt token and the economic asset it *is*.
#:
#: Deliberately short. Only mappings that are unambiguous by construction appear:
#: WBTC is BTC by redemption, WBETH and BETH are Binance's ETH staking receipts.
#: `BTCST` is **absent on purpose** — it is a hashrate token whose price tracks
#: mining economics rather than BTC by redemption, and asserting an identity that
#: does not hold would merge two genuinely different exposures.
WRAPPED_REPRESENTATIONS: Final[Mapping[str, str]] = {
    "WBTC": "BTC",
    "WBETH": "ETH",
    "BETH": "ETH",
    "STETH": "ETH",
    "WSTETH": "ETH",
}

#: A leveraged or inverse token and the asset it is a derivative of.
#:
#: These are not independent markets: they are a rebalanced, decaying position in
#: an asset the universe may already hold. Every member below was observed in
#: Binance's current spot listing.
LEVERAGED_TOKENS: Final[Mapping[str, str]] = {
    "BNBBULL": "BNB",
    "BNBBEAR": "BNB",
    "EOSBULL": "EOS",
    "EOSBEAR": "EOS",
    "ETHBULL": "ETH",
    "ETHBEAR": "ETH",
    "XRPBULL": "XRP",
    "XRPBEAR": "XRP",
    "BTCUP": "BTC",
    "BTCDOWN": "BTC",
    "ETHUP": "ETH",
    "ETHDOWN": "ETH",
    "BNBUP": "BNB",
    "BNBDOWN": "BNB",
    "XRPUP": "XRP",
    "XRPDOWN": "XRP",
    "ADAUP": "ADA",
    "ADADOWN": "ADA",
    "LINKUP": "LINK",
    "LINKDOWN": "LINK",
    "DOTUP": "DOT",
    "DOTDOWN": "DOT",
    "TRXUP": "TRX",
    "TRXDOWN": "TRX",
    "LTCUP": "LTC",
    "LTCDOWN": "LTC",
    "SUSHIUP": "SUSHI",
    "SUSHIDOWN": "SUSHI",
    "YFIUP": "YFI",
    "YFIDOWN": "YFI",
    "XLMUP": "XLM",
    "XLMDOWN": "XLM",
    "AAVEUP": "AAVE",
    "AAVEDOWN": "AAVE",
    "FILUP": "FIL",
    "FILDOWN": "FIL",
    "UNIUP": "UNI",
    "UNIDOWN": "UNI",
    "SXPUP": "SXP",
    "SXPDOWN": "SXP",
    "1INCHUP": "1INCH",
    "1INCHDOWN": "1INCH",
}

#: A retired ticker and the ticker that replaced the same economic exposure.
#:
#: A migration is not a new asset. VEN's holders received VET in 2018 and BCC was
#: renamed BCH; treating either pair as two clusters would count one history
#: twice. Where both tickers survive in the listing, the older one's series ends
#: where the newer one's begins, so the merge is a **history join question** and
#: this map is what makes it visible rather than silent. Milestone CC does not
#: splice the two series together — it excludes the retired ticker as a duplicate
#: economic exposure and says so.
REDENOMINATIONS: Final[Mapping[str, str]] = {
    "VEN": "VET",
    "BCC": "BCH",
    "BCHABC": "BCH",
    "BCHSV": "BSV",
    "STORM": "STMX",
    "ERD": "EGLD",
    "NANO": "XNO",
}

#: The annualised realised-volatility floor below which an asset is flagged as
#: behaving like a peg **whatever its name**.
#:
#: Set at 5 % annualised. A USD stablecoin against USDT realises well under 1 %;
#: the least volatile genuinely floating crypto asset in this listing realises
#: many multiples of 5 %. The gap between those two populations is wide enough
#: that the exact number is not load-bearing, which is the property a threshold
#: should have when it is chosen before the data is seen. It is a **detector, not
#: a filter**: what it produces is a disagreement with the sealed name list, and
#: the disagreement is reported.
PEG_VOLATILITY_FLOOR: Final[float] = 0.05


def classify_asset(base_asset: str) -> AssetClass:
    """Which `AssetClass` a base asset belongs to. **Exact match, sealed sets.**

    Raises:
        UniverseError: ``base_asset`` is not a non-empty string.
    """
    asset = require_text(base_asset, "base_asset")
    if asset in STABLECOIN_ASSETS:
        return AssetClass.STABLECOIN
    if asset in LEVERAGED_TOKENS:
        return AssetClass.LEVERAGED_TOKEN
    if asset in WRAPPED_REPRESENTATIONS:
        return AssetClass.WRAPPED
    return AssetClass.NATIVE


def economic_asset_id(base_asset: str) -> str:
    """The economic identity a base asset resolves to.

    ``WBTC`` and ``BTCUP`` both resolve to ``BTC``; ``VEN`` resolves to ``VET``.
    An asset naming no other resolves to itself. The three maps are applied in a
    fixed order — wrapped, then leveraged, then redenomination — and the result is
    resolved once more so a chain such as a redenominated wrapped token lands on
    the same identity from either direction.

    Raises:
        UniverseError: ``base_asset`` is not a non-empty string, or the maps
            describe a cycle.
    """
    asset = require_text(base_asset, "base_asset")
    seen = [asset]
    current = asset
    for _ in range(len(WRAPPED_REPRESENTATIONS) + len(LEVERAGED_TOKENS) + len(REDENOMINATIONS) + 1):
        nxt = (
            WRAPPED_REPRESENTATIONS.get(current)
            or LEVERAGED_TOKENS.get(current)
            or REDENOMINATIONS.get(current)
        )
        if nxt is None:
            return current
        if nxt in seen:
            raise UniverseError(
                f"the identity maps resolve {asset!r} in a cycle: "
                f"{' -> '.join([*seen, nxt])}. An asset that is its own underlying "
                "has no economic identity"
            )
        seen.append(nxt)
        current = nxt
    raise UniverseError(  # pragma: no cover - the loop bound exceeds every chain
        f"the identity maps do not terminate for {base_asset!r}"
    )


def peg_like_by_volatility(
    closes: Sequence[float], *, bars_per_year: float, floor: float = PEG_VOLATILITY_FLOOR
) -> bool | None:
    """Whether a price series behaves like a peg. **Measured, not named.**

    Returns `None` when there are fewer than three closes, because a volatility
    estimated from two points is not an estimate. Returns `True` when the
    annualised standard deviation of log returns sits below ``floor``.

    This is the backstop on `STABLECOIN_ASSETS`: a peg that nobody added to the
    sealed list still gets caught, and the catch is reported as a disagreement
    between the name rule and the data rather than quietly applied.

    Raises:
        UniverseError: a close is non-positive, ``bars_per_year`` is not positive,
            or ``floor`` is negative.
    """
    if isinstance(bars_per_year, bool) or not isinstance(bars_per_year, (int, float)):
        raise UniverseError("bars_per_year must be a real number")
    if float(bars_per_year) <= 0.0:
        raise UniverseError(f"bars_per_year must be positive, got {bars_per_year}")
    if isinstance(floor, bool) or not isinstance(floor, (int, float)):
        raise UniverseError("floor must be a real number")
    if float(floor) < 0.0:
        raise UniverseError(f"floor must be non-negative, got {floor}")
    if len(closes) < 3:
        return None
    from math import log, sqrt

    returns: list[float] = []
    previous = None
    for value in closes:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise UniverseError("every close must be a real number")
        price = float(value)
        if price <= 0.0:
            raise UniverseError(
                f"a close of {price} cannot be a traded price; a log return over it "
                "is undefined and silently skipping it would understate volatility"
            )
        if previous is not None:
            returns.append(log(price / previous))
        previous = price
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * sqrt(float(bars_per_year)) < float(floor)


def group_by_economic_asset(
    pairs: Sequence[TradingPair],
    *,
    representative_of,
) -> tuple[EconomicAsset, ...]:
    """Collapse pairs onto economic assets, one representative each.

    ``representative_of`` is a callable taking the tuple of pairs sharing one
    economic identity and returning the single pair that will stand for it. It is
    supplied rather than fixed here because *how* a representative is chosen is a
    sealed research decision — see `fmis.universe.preregistration` — and a default
    would be that decision made silently.

    Assets are returned in ascending ``asset_id`` order, and the pairs inside each
    are in ascending symbol order, so the result never depends on the provider's
    own ordering. That independence is what a hostile test checks by shuffling the
    input.

    Raises:
        UniverseError: ``pairs`` holds two entries with the same symbol, or the
            chosen representative is not among the pairs it was chosen from.
    """
    seen: set[str] = set()
    buckets: dict[str, list[TradingPair]] = {}
    classes: dict[str, AssetClass] = {}
    for pair in pairs:
        if not isinstance(pair, TradingPair):
            raise UniverseError("every entry of pairs must be a TradingPair")
        if pair.symbol in seen:
            raise UniverseError(
                f"pair {pair.symbol!r} appears twice. A universe that counted one "
                "market twice would report one cluster as two"
            )
        seen.add(pair.symbol)
        identity = economic_asset_id(pair.base_asset)
        buckets.setdefault(identity, []).append(pair)
        # The class of the *identity* is the class of the asset it resolves TO,
        # so WBTC lands in BTC's NATIVE bucket rather than making BTC wrapped.
        classes.setdefault(identity, classify_asset(identity))

    assets: list[EconomicAsset] = []
    for identity in sorted(buckets):
        members = tuple(sorted(buckets[identity], key=lambda item: item.symbol))
        chosen = representative_of(members)
        if chosen not in members:
            raise UniverseError(
                f"the representative rule returned {chosen!r} for economic asset "
                f"{identity!r}, which is not one of its pairs"
            )
        assets.append(
            EconomicAsset(
                asset_id=identity,
                asset_class=classes[identity],
                representative=chosen,
                pairs=members,
                identity_rule=IDENTITY_RULE_ID,
            )
        )
    return tuple(assets)


def identity_rules_payload() -> dict[str, object]:
    """The sealed identity rules, as data. **Digested with the pre-registration.**

    Every set and map that can change which instruments become clusters is here,
    so mutating any one of them moves the CC seal.
    """
    return {
        "rule_id": IDENTITY_RULE_ID,
        "description": IDENTITY_RULE_DESCRIPTION,
        "stablecoin_assets": sorted(STABLECOIN_ASSETS),
        "wrapped_representations": dict(sorted(WRAPPED_REPRESENTATIONS.items())),
        "leveraged_tokens": dict(sorted(LEVERAGED_TOKENS.items())),
        "redenominations": dict(sorted(REDENOMINATIONS.items())),
        "peg_volatility_floor": PEG_VOLATILITY_FLOOR,
    }
