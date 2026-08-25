"""What the 1W gate actually did. **The milestone's central question, measured.**

Two different questions live here and are deliberately kept apart, because
conflating them is the easiest way to produce a dramatic and meaningless number:

1. **How often did the gate block an instant?** Counting instants where the
   weekly regime was not `TRENDING`. This number is large and mostly
   uninteresting: the overwhelming majority of blocked instants had no
   direction to block, and reporting it alone would suggest the gate was
   throwing away thousands of trades.

2. **How often did the gate block something that would otherwise have become a
   trade?** Counting only instants where the same facts, under a treatment that
   removes the gate, produced a `CANDIDATE` or a `CONFIRMED` setup. This is the
   number that matters, and it is always smaller.

**A blocked setup is never judged by what price did next.** The brief is
explicit and this module obeys it: a setup the gate blocked is evaluated by
replaying it through the *same* entry, stop, target and lifecycle rules as every
other trade. "Price later rose" is not a finding; "this setup, entered at the
same rule's fill, with the same stop and the same target, returned +1.7R" is.
Those counterfactual trades are exactly the trades the gate-free variant
produced and the baseline did not, so they are found by **set difference on
setup identity** rather than re-simulated — which guarantees they were measured
identically.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from fmis.swing_lab.metrics import VariantMetrics, compute_lab_metrics
from fmis.swing_lab.models import GateObservation, GateVerdict, LabTrade, SwingLabError
from fmis.swing_setup.models import Direction

__all__ = [
    "GateImpact",
    "measure_gate_impact",
]


@dataclass(frozen=True, slots=True)
class GateImpact:
    """Everything the study can say about the production context-role gate.

    ``blocked_*`` counts are **instants**, not setups: one setup that stayed
    blocked for twenty bars contributes twenty. ``counterfactual`` is the
    trade-level answer and is measured over setup identities, so it counts
    opportunities rather than bars.
    """

    instants: int
    not_reached: int
    allowed: int
    blocked_without_effect: int
    blocked_candidate: int
    blocked_confirmed: int
    blocked_long: int
    blocked_short: int
    counterfactual: VariantMetrics | None
    baseline_variant_id: str | None
    counterfactual_variant_id: str | None
    counterfactual_note: str

    @property
    def blocked(self) -> int:
        """Every instant the gate refused, effective or not."""
        return (
            self.blocked_without_effect
            + self.blocked_candidate
            + self.blocked_confirmed
        )

    @property
    def materially_blocked(self) -> int:
        """Instants where removing the gate would have changed the state."""
        return self.blocked_candidate + self.blocked_confirmed

    @property
    def block_rate(self) -> Decimal | None:
        """Share of *reached* instants the gate refused, or ``None`` if none were."""
        reached = self.instants - self.not_reached
        return None if reached <= 0 else Decimal(self.blocked) / Decimal(reached)

    @property
    def material_block_rate(self) -> Decimal | None:
        """Share of reached instants where the refusal actually removed a setup."""
        reached = self.instants - self.not_reached
        return (
            None
            if reached <= 0
            else Decimal(self.materially_blocked) / Decimal(reached)
        )


def measure_gate_impact(
    observations: Sequence[GateObservation],
    results: Sequence[object],
) -> GateImpact:
    """Fold gate observations into counts, and find the trades the gate removed.

    ``results`` is the study's `VariantResult` sequence. The counterfactual
    trade set is the trades whose ``setup_id`` appears under the gate-free
    variant and **not** under the production baseline — the opportunities the
    gate removed, measured through the identical trade simulator rather than by
    inspecting subsequent price.

    Returns a `GateImpact` with ``counterfactual`` set to ``None`` when the
    study held no gate-free variant to compare against, rather than reporting
    zero removed trades — an absent comparison and a comparison that found
    nothing are different facts.
    """
    counts = {verdict: 0 for verdict in GateVerdict}
    blocked_long = blocked_short = 0
    for item in observations:
        if not isinstance(item, GateObservation):
            raise TypeError("every observation must be a GateObservation")
        counts[item.verdict] += 1
        if item.verdict.is_material:
            if item.counterfactual_direction is Direction.LONG:
                blocked_long += 1
            elif item.counterfactual_direction is Direction.SHORT:
                blocked_short += 1

    baseline_id: str | None = None
    gate_free_id: str | None = None
    baseline_trades: tuple[LabTrade, ...] = ()
    gate_free_trades: tuple[LabTrade, ...] = ()
    for result in results:
        variant = getattr(result, "variant", None)
        if variant is None:  # pragma: no cover - callers pass VariantResult
            continue
        if variant.is_production_baseline and baseline_id is None:
            baseline_id, baseline_trades = variant.variant_id, result.trades
        elif (
            variant.context_role is not None
            and variant.effective_context_role.value == "vote_only"
            and gate_free_id is None
        ):
            gate_free_id, gate_free_trades = variant.variant_id, result.trades

    counterfactual: VariantMetrics | None = None
    note = (
        "No gate-free variant was present in this study, so the trades the gate "
        "removed were not measured. This is an absent comparison, not an empty one."
    )
    if gate_free_id is not None and baseline_id is not None:
        seen = {(trade.symbol, trade.setup_id) for trade in baseline_trades}
        removed = tuple(
            trade
            for trade in gate_free_trades
            if (trade.symbol, trade.setup_id) not in seen
        )
        counterfactual = compute_lab_metrics(removed, label="gate_removed_setups")
        note = (
            f"The {len(removed)} trade(s) present under {gate_free_id} and absent "
            f"under {baseline_id}, measured through the identical entry, stop, "
            "target and cost rules as every other trade in this study. A setup "
            "is never called good because price later rose."
        )

    return GateImpact(
        instants=len(observations),
        not_reached=counts[GateVerdict.NOT_REACHED],
        allowed=counts[GateVerdict.ALLOWED],
        blocked_without_effect=counts[GateVerdict.BLOCKED_WITHOUT_EFFECT],
        blocked_candidate=counts[GateVerdict.BLOCKED_CANDIDATE],
        blocked_confirmed=counts[GateVerdict.BLOCKED_CONFIRMED],
        blocked_long=blocked_long,
        blocked_short=blocked_short,
        counterfactual=counterfactual,
        baseline_variant_id=baseline_id,
        counterfactual_variant_id=gate_free_id,
        counterfactual_note=note,
    )
