"""The thresholds a regime classification depends on, made impossible to skew.

`ARCH` §9 requires regime classification to be diffable, versioned and
reproducible on historical data. None of that is true of a number written into a
comparison, so every threshold lives here, on a frozen object that travels with
the result.

**Symmetry is structural, not validated.** `docs/analysis-notes.md` records the
v2 failure in detail: the LONG and SHORT checklists *looked* symmetric — nine
mirrored items each — but their gates were not mirror images, so one side was
satisfied most of the time and the other required a deep bear market. A pair of
independently-settable thresholds reproduces that hazard exactly, and a validator
that checked they were "close enough to symmetric" would be a warning where a
guarantee belongs.

So a band is **one** number. The upper edge is ``1 + band`` and the lower edge is
``1 / (1 + band)`` — the multiplicative mirror, which is the correct symmetry for
a ratio. There is no way to express an asymmetric gate through this API, which is
a stronger statement than any test could make about two separate fields.

**The defaults are stated policy, not measurement.** ADR-0017 set the precedent
when it fixed `MINIMUM_DIRECTIONAL_SHIFTS` at 2: a number chosen deliberately and
labelled as a choice is honest, while the same number presented as an empirical
finding is not. No backtest justifies these values, because this repository has
no backtester; when it has one, the policy is the object to sweep.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "RegimePolicy",
    "DEFAULT_POLICY",
    "RegimePolicyError",
]


class RegimePolicyError(ValueError):
    """A policy that could not produce a reproducible classification."""


#: The identifier carried on every result produced with the default parameters.
#: A version string rather than a hash, because a reader comparing two runs needs
#: to see *which policy* differed, not that two opaque digests are unequal.
DEFAULT_POLICY_ID = "regime-v1"

#: Twenty per cent above or below the baseline. Stated policy, not measurement —
#: wide enough that ordinary bar-to-bar noise does not flip the state, narrow
#: enough to move within a normal market cycle. Chosen, and labelled as chosen.
DEFAULT_BAND = 0.20

#: A change of character within this many closed candles reports the structure
#: dimension as transitioning. Stated policy: it is the repository's own event,
#: and the only question here is how long it stays newsworthy.
DEFAULT_TRANSITION_LOOKBACK_BARS = 5


@dataclass(frozen=True, slots=True)
class RegimePolicy:
    """Every threshold one regime classification used, carried with its result.

    ``volatility_band`` and ``participation_band`` are each **one** number
    producing two mirrored edges; see the module docstring for why they are not
    two numbers. ``transition_lookback_bars`` is a count of closed candles.

    Frozen, slotted and hashable, so a policy can be compared, put in a set, and
    cannot drift after a result has cited it.
    """

    policy_id: str = DEFAULT_POLICY_ID
    volatility_band: float = DEFAULT_BAND
    participation_band: float = DEFAULT_BAND
    transition_lookback_bars: int = DEFAULT_TRANSITION_LOOKBACK_BARS

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise RegimePolicyError("policy_id must be a non-empty str")
        for name in ("volatility_band", "participation_band"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number, got {type(value).__name__}")
            if not math.isfinite(value):
                raise RegimePolicyError(f"{name} must be finite, got {value}")
            if value <= 0.0:
                raise RegimePolicyError(
                    f"{name} must be greater than 0, got {value}; a band of zero "
                    "would classify every ratio as expanding or contracting and "
                    "never as steady"
                )
        if isinstance(self.transition_lookback_bars, bool) or not isinstance(
            self.transition_lookback_bars, int
        ):
            raise TypeError(
                "transition_lookback_bars must be an int, got "
                f"{type(self.transition_lookback_bars).__name__}"
            )
        if self.transition_lookback_bars < 0:
            raise RegimePolicyError(
                "transition_lookback_bars cannot be negative, got "
                f"{self.transition_lookback_bars}"
            )

    @property
    def volatility_upper_edge(self) -> float:
        """``1 + band``. A ratio at or above this reads as expanding."""
        return 1.0 + self.volatility_band

    @property
    def volatility_lower_edge(self) -> float:
        """``1 / (1 + band)`` — the multiplicative mirror of the upper edge."""
        return 1.0 / (1.0 + self.volatility_band)

    @property
    def participation_upper_edge(self) -> float:
        """``1 + band``. Relative volume at or above this reads as elevated."""
        return 1.0 + self.participation_band

    @property
    def participation_lower_edge(self) -> float:
        """``1 / (1 + band)`` — the multiplicative mirror of the upper edge."""
        return 1.0 / (1.0 + self.participation_band)

    def describe(self) -> tuple[tuple[str, str], ...]:
        """The policy as ordered ``(name, value)`` pairs, for rendering.

        Returned as a tuple of pairs rather than a mapping so the display order
        is the policy's own and not a dict's insertion accident. Values are
        already strings: formatting belongs here, beside the numbers, rather than
        being re-invented by each renderer.
        """
        return (
            ("policy_id", self.policy_id),
            ("volatility band", f"±{self.volatility_band:.0%} (multiplicative)"),
            (
                "volatility edges",
                f"{self.volatility_lower_edge:.4f} / {self.volatility_upper_edge:.4f}",
            ),
            ("participation band", f"±{self.participation_band:.0%} (multiplicative)"),
            (
                "participation edges",
                f"{self.participation_lower_edge:.4f} / "
                f"{self.participation_upper_edge:.4f}",
            ),
            ("transition lookback", f"{self.transition_lookback_bars} closed candles"),
        )


#: The policy used when a caller does not choose one. Module-level and frozen, so
#: two runs that did not name a policy provably used the same one.
DEFAULT_POLICY = RegimePolicy()
