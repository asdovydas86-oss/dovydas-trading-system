"""Comparing variants against the baseline, and a true replay against a post-filter.

    compare_variant(baseline, variant)        ──►  VariantComparison
    post_filter_comparison(baseline, replay)  ──►  PostFilterComparison

**Comparison is only meaningful because the join key is variant-invariant.**
An opportunity is a maximal run of same-direction observations
(`fmis.swing_setup.research_identity`), and the confirmation-age override
cannot change where those runs begin or end — it decides `CONFIRMED` versus
`CANDIDATE`, never whether a direction exists. So the same history decomposes
into the same opportunities under every variant, and the five lineage questions
the milestone brief asks reduce to a join:

* *same opportunity, different confirmation time?* — in both, timestamps differ
* *opportunity disappears?* — cannot happen, and the count proves it rather
  than assuming it
* *CANDIDATE becomes CONFIRMED later?* — in both, variant timestamp is later
* *confirmation lost entirely?* — in baseline, absent from variant
* *new confirmation caused by a later break?* — the same "shifted later" row,
  read from the other end; a confirmation with **no** baseline counterpart at
  all is counted separately as ``added``

**Part 13, stated as code.** `post_filter_comparison` reproduces Milestone BA's
method — keep the baseline confirmations whose recorded break age already
satisfies a bound, drop the rest — and sets it beside what replaying the policy
under that bound actually produces. The difference between the two is BB
finding #2 made numerical. Nothing here argues that one bound is better; the
functions compute differences and refuse to rank them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fmis.swing_setup.backtest_models import OutcomeStatus, SetupOutcome
from fmis.swing_setup.research_metrics import confirmation_records
from fmis.swing_setup.research_models import (
    ConfirmationRecord,
    PostFilterComparison,
    ResearchBacktestRun,
    ResearchError,
    VariantComparison,
)

__all__ = [
    "MAX_SHIFTED_EXAMPLES",
    "compare_variant",
    "post_filter_keep",
    "post_filter_comparison",
    "OutcomeSplit",
    "split_outcomes",
]

#: How many shifted confirmations a comparison carries as named examples. A
#: comparison is a set of counts; the examples exist so a reader can check one
#: by hand, not so the object becomes a second copy of the run.
MAX_SHIFTED_EXAMPLES: int = 5


def _by_identity(
    records: Sequence[ConfirmationRecord],
) -> Mapping[tuple[str, str], ConfirmationRecord]:
    index: dict[tuple[str, str], ConfirmationRecord] = {}
    for record in records:
        if record.identity in index:
            raise ResearchError(
                f"two first confirmations share identity {record.identity!r}; "
                "an opportunity confirms at most once by construction, so this "
                "means the identity rule is not doing its job"
            )
        index[record.identity] = record
    return index


def compare_variant(
    baseline: ResearchBacktestRun, variant: ResearchBacktestRun
) -> VariantComparison:
    """How ``variant``'s confirmed population differs from ``baseline``'s, opportunity by opportunity.

    Both runs must share a window and a symbol set — comparing confirmations
    measured over different periods would produce differences that say nothing
    about policy.

    Raises:
        ResearchError: the two runs do not share a window, symbols, or segments.
    """
    for run in (baseline, variant):
        if not isinstance(run, ResearchBacktestRun):
            raise TypeError("both arguments must be a ResearchBacktestRun")
    if baseline.window != variant.window:
        raise ResearchError(
            "a variant comparison requires one shared measurement window; "
            "differences over different periods are not policy differences"
        )
    if baseline.symbols != variant.symbols:
        raise ResearchError("a variant comparison requires one shared symbol set")

    base_index = _by_identity(confirmation_records(baseline))
    variant_index = _by_identity(confirmation_records(variant))

    unchanged = shifted_later = shifted_earlier = removed = 0
    examples: list[tuple[str, str, object, object]] = []
    for identity, base_record in base_index.items():
        counterpart = variant_index.get(identity)
        if counterpart is None:
            removed += 1
            continue
        if counterpart.confirmed_at == base_record.confirmed_at:
            unchanged += 1
            continue
        if counterpart.confirmed_at > base_record.confirmed_at:
            shifted_later += 1
        else:
            shifted_earlier += 1
        if len(examples) < MAX_SHIFTED_EXAMPLES:
            examples.append(
                (
                    base_record.symbol,
                    base_record.opportunity_key,
                    base_record.confirmed_at,
                    counterpart.confirmed_at,
                )
            )
    added = sum(1 for identity in variant_index if identity not in base_index)

    return VariantComparison(
        baseline_variant_id=baseline.variant.variant_id,
        variant_id=variant.variant.variant_id,
        baseline_confirmations=len(base_index),
        variant_confirmations=len(variant_index),
        unchanged=unchanged,
        shifted_later=shifted_later,
        shifted_earlier=shifted_earlier,
        removed=removed,
        added=added,
        shifted_examples=tuple(examples),
    )


def post_filter_keep(
    baseline: ResearchBacktestRun, max_confirmation_age: int
) -> tuple[ConfirmationRecord, ...]:
    """Milestone BA's method, reproduced exactly: keep baseline confirmations already fresh enough.

    This is a **filter over an existing record**, which is precisely why it
    cannot answer the counterfactual: it can only ever return a subset of what
    the baseline already saw, so a confirmation that would exist under a
    stricter bound — because the bound deferred a candidate onto a later,
    fresher break — is unreachable from here by construction.

    A record with no recorded age is dropped: BA had no age to filter on either,
    and silently keeping it would flatter the method under test.
    """
    if isinstance(max_confirmation_age, bool) or not isinstance(max_confirmation_age, int):
        raise TypeError("max_confirmation_age must be an int")
    if max_confirmation_age < 0:
        raise ResearchError("max_confirmation_age cannot be negative")
    return tuple(
        record
        for record in confirmation_records(baseline)
        if record.confirmation_break_age_bars is not None
        and record.confirmation_break_age_bars <= max_confirmation_age
    )


@dataclass(frozen=True, slots=True)
class OutcomeSplit:
    """Outcome counts for one set of confirmations, joined back to their outcomes."""

    total: int
    target_first: int
    stop_first: int
    ambiguous_same_bar: int
    unresolved: int


def split_outcomes(
    run: ResearchBacktestRun, identities: Sequence[tuple[str, str]]
) -> OutcomeSplit:
    """Outcome counts for the subset of ``run``'s outcomes matching ``identities``.

    Joins on ``(symbol, setup_id)`` — the research harness stores each outcome's
    opportunity key in ``setup_id``, so this is an exact join rather than a
    match on a rounded timestamp.
    """
    wanted = set(identities)
    selected = [
        outcome
        for outcome in run.outcomes
        if (outcome.symbol, outcome.setup_id) in wanted
    ]
    return _split(selected)


def _split(outcomes: Sequence[SetupOutcome]) -> OutcomeSplit:
    return OutcomeSplit(
        total=len(outcomes),
        target_first=sum(1 for o in outcomes if o.status is OutcomeStatus.TARGET_FIRST),
        stop_first=sum(1 for o in outcomes if o.status is OutcomeStatus.STOP_FIRST),
        ambiguous_same_bar=sum(
            1 for o in outcomes if o.status is OutcomeStatus.AMBIGUOUS_SAME_BAR
        ),
        unresolved=sum(
            1 for o in outcomes if o.status is OutcomeStatus.NEITHER_WITHIN_WINDOW
        ),
    )


def post_filter_comparison(
    baseline: ResearchBacktestRun,
    replay: ResearchBacktestRun,
) -> PostFilterComparison:
    """BA's post-filter beside BC's true replay, at the replay's own staleness bound.

    ``replay`` must be a counterfactual variant — the production baseline has
    nothing to be compared against itself under.

    Outcome counts are reported for both populations, from the run each one
    belongs to: the post-filtered rows keep the baseline's outcomes (that is
    what BA had), and the replayed rows carry the replay's own, which is the
    point — a deferred confirmation has a different entry, stop and target, so
    its outcome is genuinely a different measurement rather than a relabelled
    one.

    Raises:
        ResearchError: ``replay`` applies the production constant, so there is
            no counterfactual bound to filter at.
    """
    if replay.variant.max_confirmation_age is None:
        raise ResearchError(
            "post_filter_comparison needs a counterfactual variant; the "
            "production baseline has no override to compare a filter against"
        )
    bound = replay.variant.max_confirmation_age
    baseline_records = confirmation_records(baseline)
    kept = post_filter_keep(baseline, bound)
    replayed = confirmation_records(replay)

    kept_identities = {record.identity for record in kept}
    replay_identities = {record.identity for record in replayed}
    in_both = len(kept_identities & replay_identities)

    post_split = split_outcomes(baseline, tuple(kept_identities))
    replay_split = split_outcomes(replay, tuple(replay_identities))

    return PostFilterComparison(
        max_confirmation_age=bound,
        baseline_confirmations=len(baseline_records),
        post_filter_kept=len(kept_identities),
        replay_confirmations=len(replay_identities),
        in_both=in_both,
        only_in_post_filter=len(kept_identities - replay_identities),
        only_in_replay=len(replay_identities - kept_identities),
        post_filter_target_first=post_split.target_first,
        post_filter_stop_first=post_split.stop_first,
        replay_target_first=replay_split.target_first,
        replay_stop_first=replay_split.stop_first,
    )
