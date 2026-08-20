"""Which evidence items are **not** independent of each other, and why.

This module exists because the failure it prevents is the one a reader cannot
see. Three items that all restate the same upstream reading look exactly like
three-fold corroboration on a page, and a report that counts them as three is
more misleading than a report that had never grouped anything at all.

Two different mechanisms are kept apart on purpose:

  * **Structural independence** — computed, never declared. Two items are
    family-disjoint when their `EvidenceFamily` sets do not intersect. This is
    arithmetic over `EvidenceItem.families` and needs no maintenance.
  * **Named correlations** — declared, because no family set can express them.
    That two items read the same candles, or that one is a precondition the
    other already satisfied, is a fact about the *upstream wiring*, and the only
    honest way to hold it is to write it down with its reason and check the
    reason still holds.

Every rule below states a claim that is checkable against the source it names,
and `tests/test_setup_evidence_architecture.py` §4 checks each one against the
live code rather than trusting this docstring.

**Nothing here weights anything.** A correlation removes a claim of
independence; it never scales, discounts or ranks an item. The item stays in
the report, fully visible, with the correlation named beside it.
"""

from __future__ import annotations

from dataclasses import dataclass

from fmis.evidence import EvidenceFamily
from fmis.setup_evidence.models import EvidenceItem, SetupEvidenceError

__all__ = [
    "FACTOR_FAMILIES",
    "CorrelationRule",
    "KNOWN_CORRELATIONS",
    "KEY_CONTEXT_TREND",
    "KEY_SETUP_TREND",
    "KEY_EVIDENCE_ALIGNMENT",
    "KEY_REGIME_GATE",
    "KEY_CONFIRMATION",
    "KEY_TRIGGER",
    "KEY_GEOMETRY",
    "KEY_CALIBRATION",
    "family_order",
    "sorted_families",
    "correlations_for",
    "standing_family_note",
    "correlated_keys_for",
    "independent_pairs_exist",
]

#: Stable item keys. Written out as constants rather than inlined at each call
#: site so the correlation rules below and the projection cannot drift apart —
#: a renamed key is one edit, checked by the type system rather than by grep.
KEY_CONTEXT_TREND = "factor:context_structural_trend"
KEY_SETUP_TREND = "factor:setup_structural_trend"
KEY_EVIDENCE_ALIGNMENT = "factor:setup_evidence_alignment"
KEY_REGIME_GATE = "regime:structure_gate"
KEY_CONFIRMATION = "confirmation"
KEY_TRIGGER = "trigger"
KEY_GEOMETRY = "geometry:risk_reward"
KEY_CALIBRATION = "calibration:probability"

#: How each `DirectionalFactor.family` the Swing Setup policy emits maps onto the
#: ADR-0011 shared vocabulary.
#:
#: `setup_evidence_alignment` maps to **two** families, and that is the honest
#: reading rather than a hedge: `fmis.decision_support` reduces three TREND
#: observations (`price_vs_ema_fast`, `price_vs_ema_slow`, `ema_fast_vs_ema_slow`)
#: and two MOMENTUM observations (`macd_vs_signal`, `macd_histogram`) to a single
#: `dominant_alignment`, and does not report which of the two drove it. Assigning
#: it to one family would be a fabricated attribution; assigning it to both is
#: what the upstream grouping actually supports.
#:
#: A factor family absent from this mapping resolves to an empty family tuple and
#: raises a report warning. That is deliberate: a future policy adding a fourth
#: factor should produce a visibly unclassified item, never a silently guessed
#: family.
FACTOR_FAMILIES: dict[str, tuple[EvidenceFamily, ...]] = {
    "context_structural_trend": (EvidenceFamily.TREND,),
    "setup_structural_trend": (EvidenceFamily.TREND,),
    "setup_evidence_alignment": (EvidenceFamily.TREND, EvidenceFamily.MOMENTUM),
}


@dataclass(frozen=True, slots=True)
class CorrelationRule:
    """One stated reason two or more items are not independent readings.

    A rule over a **single** key is not a mistake: it records that one item is
    internally composed of correlated parts, which is a caveat a reader needs
    even though it links to nothing else.

    ``reason`` names the source that makes the claim checkable. It is prose
    because it is read by a person; it is precise because a test verifies the
    mechanism it describes still exists.
    """

    keys: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.keys, tuple) or not self.keys:
            raise SetupEvidenceError("keys must be a non-empty tuple of str")
        for key in self.keys:
            if not isinstance(key, str) or not key.strip():
                raise SetupEvidenceError("every key must be a non-empty str")
        if len(set(self.keys)) != len(self.keys):
            raise SetupEvidenceError(f"keys must not repeat, got {list(self.keys)}")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise SetupEvidenceError("reason must be a non-empty str")


#: The correlations this repository has actually established, each traceable to
#: the source that creates it. Ordered by how badly each one would mislead.
KNOWN_CORRELATIONS: tuple[CorrelationRule, ...] = (
    CorrelationRule(
        keys=(KEY_CONTEXT_TREND, KEY_REGIME_GATE),
        reason=(
            "The regime STRUCTURE gate and the context structural-trend factor "
            "read the same value. `fmis.swing_setup.compose.build_setup_inputs` "
            "derives both from the context view, and "
            "the `market_regime` classifier reads `subject.structural_trend` for "
            "the swing-structure evidence family that STRUCTURE depends on. "
            "Because STRUCTURE is TRENDING only when that trend is sustained, "
            "and a sustained trend is exactly what makes this factor cast a "
            "directional vote, passing the gate *implies* the vote. The gate is "
            "a precondition this factor already satisfied, never a second "
            "opinion about it."
        ),
    ),
    CorrelationRule(
        keys=(KEY_CONTEXT_TREND, KEY_SETUP_TREND),
        reason=(
            "Both are `structural_trend` engine readings produced by the same "
            "method, differing only in the interval they were computed over. "
            "Distinct candles make them non-identical, but one shared method on "
            "one instrument is a single family observed twice, not two "
            "independent families."
        ),
    ),
    CorrelationRule(
        keys=(KEY_SETUP_TREND, KEY_EVIDENCE_ALIGNMENT),
        reason=(
            "Both read the setup-role interval. The structural trend is computed "
            "from that series' swing structure, and three of the five "
            "observations behind `fmis.decision_support`'s dominant alignment "
            "are price-versus-EMA comparisons over the same series. Agreement "
            "between them is partly a restatement of one series' direction."
        ),
    ),
    CorrelationRule(
        keys=(KEY_EVIDENCE_ALIGNMENT,),
        reason=(
            "Internally double-counted upstream. Within "
            "`fmis.decision_support`, `macd_vs_signal` and `macd_histogram` are "
            "the same fact — `fmis.features.indicators.macd` computes "
            "`histogram = macd_line - signal_line`, so a positive histogram and "
            "a macd line above its signal are one observation counted twice. "
            "The three EMA comparisons are transitive for the same reason: "
            "price above the fast average and the fast above the slow force "
            "price above the slow. This item's single alignment therefore rests "
            "on fewer independent readings than the five observations behind it "
            "suggest."
        ),
    ),
    CorrelationRule(
        keys=(KEY_CONFIRMATION,),
        reason=(
            "The trigger and the confirmation line are one sentence. "
            "`fmis.swing_setup.policy` builds `Trigger.statement` from the "
            "string it puts in `confirmation[0]` on both of its branches, so "
            "the two are projected as a single item — the trigger's level and "
            "bar index, which are genuinely additional, are carried in that "
            "item's inputs."
        ),
    ),
    CorrelationRule(
        keys=(KEY_GEOMETRY,),
        reason=(
            "One level, three views, projected once. The assessment reports the "
            "protective level directly, restates it in its invalidation line "
            "(whose own text says it is 'the same level'), and carries it again "
            "inside `risk_reward`. They are one geometric fact and are projected "
            "as a single item rather than three."
        ),
    ),
)


def family_order(family: EvidenceFamily) -> int:
    """Declaration position of a family in `EvidenceFamily`.

    Used as the canonical sort key everywhere in this package, so two runs over
    equal inputs order every family sequence identically.
    """
    return tuple(EvidenceFamily).index(family)


def sorted_families(families: object) -> tuple[EvidenceFamily, ...]:
    """Distinct families in canonical declaration order."""
    return tuple(sorted(set(families), key=family_order))  # type: ignore[arg-type]


def correlations_for(key: str) -> tuple[CorrelationRule, ...]:
    """Every declared rule naming ``key``, in registry order."""
    return tuple(rule for rule in KNOWN_CORRELATIONS if key in rule.keys)


def correlated_keys_for(key: str) -> tuple[str, ...]:
    """The other item keys ``key`` is declared not independent of, sorted.

    Sorted rather than registry-ordered because this becomes a field on a frozen
    item, and a stable order is what makes two reports over equal inputs
    byte-identical.
    """
    found: set[str] = set()
    for rule in correlations_for(key):
        found.update(other for other in rule.keys if other != key)
    return tuple(sorted(found))


def _declared_together(left: str, right: str) -> bool:
    return any(
        left in rule.keys and right in rule.keys for rule in KNOWN_CORRELATIONS
    )


def standing_family_note() -> str | None:
    """One sentence about the factor set as a whole, or `None` if there is none.

    **Derived from `FACTOR_FAMILIES`, never written down.** The claim is that no
    two of the policy's directional factors are family-disjoint, which is a
    property of the mapping above rather than a fact about any one symbol. A
    future policy adding a genuinely independent family makes this return
    `None`, and the note disappears from every surface at once instead of
    becoming a stale sentence somebody has to remember to delete.

    It exists so a compact surface — `fmits today` — can state the caveat once
    for a whole page without computing anything per symbol, and without offering
    a per-row figure that would be read as a ranking.
    """
    entries = sorted(FACTOR_FAMILIES.items())
    if len(entries) < 2:
        return None
    for position, (_, families) in enumerate(entries):
        for _, other in entries[position + 1:]:
            if not (set(families) & set(other)):
                return None
    shared = sorted_families(
        [family for _, families in entries for family in families]
    )
    return (
        "The directional factors behind every line here draw on overlapping "
        f"evidence families ({', '.join(family.value for family in shared)}), so "
        "their agreement is not independent corroboration. Run "
        "`fmits evidence SYMBOL` for the specific correlations."
    )


def independent_pairs_exist(items: tuple[EvidenceItem, ...]) -> bool:
    """Whether any two of ``items`` are genuinely independent readings.

    Both conditions must hold for a pair to count:

      1. their family sets are **disjoint** — they are not two views of one
         subject area; and
      2. no `CorrelationRule` names them together — they do not share an
         upstream input that the family sets alone cannot express.

    An item carrying **no** family cannot establish independence with anything.
    That is deliberate rather than conservative: an unclassified item is one
    whose subject area is unknown, and unknown is not the same as different.
    """
    for position, item in enumerate(items):
        if not item.families:
            continue
        for other in items[position + 1:]:
            if not other.families:
                continue
            if set(item.families) & set(other.families):
                continue
            if _declared_together(item.key, other.key):
                continue
            return True
    return False
