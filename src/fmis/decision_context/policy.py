"""The policy a decision-context evaluation cites, and why it holds no thresholds.

Every other policy object in this repository carries numbers — `RegimePolicy` has
its bands, `DetectionSettings` its bar counts. **This one deliberately carries
none.**

Each requirement delegates its rule to the layer that already declared it:
`required_candles` for depth, the feature engine's warm-up metadata for
readiness, `fmis.market_regime` for whether a dimension could classify,
`fmis.level_crossing` for whether a level exists, and ADR-0008 §7 for whether the
evidence layer had enough directional observations. Inventing a threshold here
would create a **second** definition of a rule some layer already owns, and the
second definition is the one that drifts.

What the policy does carry is its **identity**, so a stored context names the
ruleset that produced it, and `strict`, the one genuine choice: whether a
limiting gap is treated as blocking. That choice is a caller's tolerance, not a
market fact, which is exactly the kind of thing a policy should hold.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ContextPolicy", "DEFAULT_CONTEXT_POLICY", "ContextPolicyError"]


class ContextPolicyError(ValueError):
    """A policy that could not produce a reproducible evaluation."""


#: Carried on every result produced with the default ruleset. A version string
#: rather than a hash, because a reader comparing two runs needs to see *which*
#: policy differed, not that two digests are unequal.
DEFAULT_POLICY_ID = "context-v1"


@dataclass(frozen=True, slots=True)
class ContextPolicy:
    """Which ruleset was applied, and how strictly.

    ``strict`` promotes every limiting gap to blocking. A caller running a
    watchlist unattended will want it; a human reading one page will not. It is
    **one flag, not a per-requirement override**: a set of individually
    demotable severities would let a caller quietly switch off the single check
    that was about to stop them, which is the shape of gate
    `docs/analysis-notes.md` blames for the v2 bias.

    Frozen, slotted and hashable, so a policy can be compared, put in a set, and
    cannot drift after a result has cited it.
    """

    policy_id: str = DEFAULT_POLICY_ID
    strict: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ContextPolicyError("policy_id must be a non-empty str")
        if not isinstance(self.strict, bool):
            raise TypeError(
                f"strict must be a bool, got {type(self.strict).__name__}"
            )

    def describe(self) -> tuple[tuple[str, str], ...]:
        """The policy as ordered ``(name, value)`` pairs, for rendering.

        A tuple of pairs rather than a mapping, so the display order is the
        policy's own and not a dict's insertion accident. Formatting lives here,
        beside the values, rather than being re-invented by each renderer.
        """
        return (
            ("policy_id", self.policy_id),
            ("strict", "yes — limiting gaps block" if self.strict else "no"),
            ("thresholds", "none; every rule is delegated to the layer that owns it"),
        )


#: The policy used when a caller does not choose one. Module-level and frozen, so
#: two runs that did not name a policy provably used the same one.
DEFAULT_CONTEXT_POLICY = ContextPolicy()
