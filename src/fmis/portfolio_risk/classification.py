"""The owner's own groupings, applied at read time and never written down.

`AP` §15.7's rule, implemented rather than restated: *"classifications are a
versioned mapping applied at read time, never a field written onto a holding.
Re-classifying an asset in 2029 therefore does not rewrite 2026's records."* A
`ClassificationMap` is that mapping. Nothing in this module writes a group onto a
line, a position or a trade, and there is no code path that could.

**This module names no group.** BTC-beta, Layer 1, DeFi, AI, meme and exchange
tokens are the owner's words for the owner's ideas, and a taxonomy shipped here
would age badly and would be wrong for somebody: *"narratives change faster than
schemas."* Every member is supplied at construction, exactly as `fmis.risk`
supplies no threshold.

**An asset may belong to several groups at once**, and the consequence is stated
rather than smoothed away: group buckets overlap, so they sum to *more* than the
portfolio's gross exposure, and `ExposureBreakdown.overlapping_keys` names every
asset that is double-counted. Normalizing the overlap away would invent a
weighting the owner never chose.

**An asset the map does not name is `UNCLASSIFIED`, never guessed.** Not omitted
either: exposure filed under a word is visible, and exposure dropped from a
breakdown reads as a fully classified portfolio.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from fmis.money import AssetCode
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError, require_text

from fmis.portfolio_risk.models import UNCLASSIFIED

__all__ = ["ClassificationMap", "unclassified_map"]


@dataclass(frozen=True, slots=True)
class ClassificationMap:
    """`asset → group ids`, at a stated version. `ASSERTED` — the owner's own.

    The version travels with every breakdown computed under it, because two
    allocations produced by two versions are *visibly two different things* and
    must never be silently contradictory. That is the same discipline
    `AllocationEntry.classification_version` carries inside a frozen snapshot.
    """

    version: str
    #: `((asset, (group id, …)), …)` — a tuple of pairs rather than a dict so the
    #: map is hashable, frozen and orders deterministically.
    assignments: tuple[tuple[AssetCode, tuple[str, ...]], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", require_text(self.version, "version"))
        if not isinstance(self.assignments, tuple):
            raise TypeError("assignments must be a tuple of (AssetCode, groups) pairs")
        seen: set[str] = set()
        normalized: list[tuple[AssetCode, tuple[str, ...]]] = []
        for position, pair in enumerate(self.assignments):
            if not isinstance(pair, tuple):
                raise TypeError(
                    f"assignments[{position}] must be an (AssetCode, groups) pair"
                )
            try:
                raw_asset, groups = pair
            except ValueError as error:
                raise TypeError(
                    f"assignments[{position}] must be an (AssetCode, groups) pair"
                ) from error
            asset = raw_asset if isinstance(raw_asset, AssetCode) else AssetCode(raw_asset)
            if not isinstance(groups, tuple):
                raise TypeError(
                    f"assignments[{position}] groups must be a tuple of str"
                )
            labels = tuple(
                sorted(
                    {
                        require_text(group, f"assignments[{position}] group")
                        for group in groups
                    }
                )
            )
            if not labels:
                raise DomainValidationError(
                    f"{asset} is listed with no group; an asset the owner has not "
                    f"classified is left out of the map and reads as "
                    f"{UNCLASSIFIED!r}, which is a different statement from "
                    "'classified into nothing'"
                )
            if UNCLASSIFIED in labels:
                raise DomainValidationError(
                    f"{UNCLASSIFIED!r} is what an unnamed asset resolves to and is "
                    "not a group the owner may assign; assigning it would make "
                    "'not classified' and 'classified as not classified' the same "
                    "bucket"
                )
            if asset.code in seen:
                raise DomainValidationError(
                    f"asset {asset} is assigned twice; one asset, one group list"
                )
            seen.add(asset.code)
            normalized.append((asset, labels))
        object.__setattr__(
            self,
            "assignments",
            tuple(sorted(normalized, key=lambda entry: entry[0].code)),
        )

    @property
    def origin(self) -> ValueOrigin:
        """`ASSERTED`. A classification is the owner's opinion about the world."""
        return ValueOrigin.ASSERTED

    @property
    def is_empty(self) -> bool:
        return not self.assignments

    @property
    def groups(self) -> tuple[str, ...]:
        """Every group the owner named, in a stable order."""
        return tuple(
            sorted({group for _, groups in self.assignments for group in groups})
        )

    def groups_for(self, asset: AssetCode | str) -> tuple[str, ...] | Absent:
        """The groups one asset belongs to, or the absence that says it has none.

        `Absent` rather than `(UNCLASSIFIED,)`: *"we have not classified this"*
        and *"this is classified"* are different facts, and a caller that cannot
        tell them apart will report an unclassified portfolio as a diversified
        one. `ExposureBreakdown` files the absence under `UNCLASSIFIED` on the
        page, which is a rendering decision made once and visibly.
        """
        wanted = asset if isinstance(asset, AssetCode) else AssetCode(asset)
        for candidate, groups in self.assignments:
            if candidate == wanted:
                return groups
        return Absent(
            f"the owner's classification {self.version!r} does not name {wanted}"
        )

    def multi_group_assets(self, assets: Iterable[AssetCode]) -> tuple[str, ...]:
        """Which of the supplied assets this map files in more than one group.

        The overlap that makes group buckets sum past the portfolio's gross
        exposure. Reported so a reader is never handed shares that add to more
        than one without being told why.
        """
        found: set[str] = set()
        for asset in assets:
            groups = self.groups_for(asset)
            if not isinstance(groups, Absent) and len(groups) > 1:
                found.add(asset.code)
        return tuple(sorted(found))

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "assignments": [
                {"asset": asset.code, "groups": list(groups)}
                for asset, groups in self.assignments
            ],
        }

    @classmethod
    def of(cls, version: str, mapping: Mapping[str, Iterable[str]]) -> ClassificationMap:
        """Build from the shape a caller actually has — `{"BTC": ["l1", …]}`."""
        if not isinstance(mapping, Mapping):
            raise TypeError("mapping must be a Mapping of asset code to group ids")
        return cls(
            version=version,
            assignments=tuple(
                (AssetCode(str(asset)), tuple(str(group) for group in groups))
                for asset, groups in mapping.items()
            ),
        )


def unclassified_map(version: str) -> ClassificationMap:
    """A map that names nothing, so every asset resolves to `UNCLASSIFIED`.

    The honest default for an owner who has not written a taxonomy yet. It is
    still versioned, so the day they write one, the two readings are visibly
    different rather than one silently replacing the other.
    """
    return ClassificationMap(version=version)
