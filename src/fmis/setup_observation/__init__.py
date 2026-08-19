"""Setup observation — the application-layer bridge from a reading to an identity.

Two modules. `observe` is the only place in the repository that turns the
swing-setup engine's `SetupAssessment` into the domain's `SetupObservation` and
its stable `Anchor` identity; `render` prints that identity as a page block, on
this side of the line because the engine's own renderer is a market-half module
and may not import a domain value.

The package exists as its own application-layer tier rather than as a module
under the pipeline for the reason `observe`'s own docstring gives: Law 6 forbids
any market-half package from importing the trading domain, and this translation
must name both. It stores nothing, adds no record kind, and computes no market
value.
"""

from __future__ import annotations

from fmis.setup_observation.render import (
    IDENTITY_WIDTH,
    render_identity_run,
    render_setup_identity,
)
from fmis.setup_observation.observe import (
    SETUP_OBSERVATION_BOOK,
    STOP_TRIGGER_SEMANTICS,
    SetupIdentityRun,
    observation_from_assessment,
    observe_setup_series,
    setup_version_set,
)

__all__ = [
    "SETUP_OBSERVATION_BOOK",
    "STOP_TRIGGER_SEMANTICS",
    "SetupIdentityRun",
    "setup_version_set",
    "observation_from_assessment",
    "observe_setup_series",
    "IDENTITY_WIDTH",
    "render_setup_identity",
    "render_identity_run",
]
