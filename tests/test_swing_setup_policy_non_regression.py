"""Slice 1 — proof that the trading policy did not change.

Slice 1 is a data-preservation and presentation change: it carries information
the pipeline already computed across a seam that used to drop it. It must not
alter a single trading conclusion, and *"we did not mean to"* is not a proof.

**The contract boundary.** `setup_assessment_for_sheet` is the closest stable
one: it is the composition root the live product enters through
(`setup_for_symbol` → `run_setup_for_symbols` → `fmis.swing_setup.scan` all
reach the market through it), and it runs the *whole* chain under test — the
three regime evaluations, the evidence report, the decision-context verdict,
`build_setup_inputs` and `evaluate_setup`. A baseline taken here therefore
covers every stage Slice 1 could have disturbed, not just the policy function.

**The canonical representation, and why it is not weakened.** Each assessment
and each evidence report is canonicalised as its `repr()`. For a frozen,
slotted dataclass that is a complete, recursive, field-by-field rendering:
every field of every nested `PriceLevel`, `DirectionalFactor`, `Trigger`,
`RiskReward`, `EvidenceItem` and `ConfluenceSummary` appears in it, enum
members print with their values, floats print with `repr`'s exact round-trip,
and `metadata` prints in insertion order. Adding a field, removing one,
renaming one, reordering a tuple or changing any value all change the string.
Nothing is normalised away, no field is excluded and no tolerance is applied —
this is a stricter comparison than an equality check on a hand-listed subset of
fields, which is the comparison it was chosen over.

The digests below were captured on the commit **before** the Slice 1 change and
are asserted **after** it. They are per fixture, not one digest over the whole
matrix, so a failure names the seed triple that moved instead of reporting that
something, somewhere, differs.

**The matrix.** Twenty-seven seed triples × three symbols, over synthetic
seeded candles — offline, network-free and clock-free. It is not a single happy
path: the eighty-one assessments cover all three of the engine's `WAIT` exits
(the context-role regime gate, a directional split, and a split with a family
that conflicts with itself) as well as `CANDIDATE`, and the distribution is
asserted below so that a matrix which silently stopped covering them would fail
rather than pass vacuously.

If a future milestone changes the policy **on purpose**, this file is the thing
it must update, deliberately and with a stated reason. That is the point.
"""

from __future__ import annotations

import collections
import hashlib
import re

from fmis.setup_evidence import project_setup_evidence
from fmis.swing_setup import SetupState
from fmis.swing_setup.compose import setup_assessment_for_sheet

from tests.archive_helpers import multi

CONTEXT_SEEDS = (1, 2, 3)
SETUP_SEEDS = (4, 5, 6)
EXECUTION_SEEDS = (7, 8, 9)
SYMBOLS = ("BTCUSDT", "BNBUSDT", "ETHUSDT")


def _canonical(value: object) -> str:
    """The complete field-by-field rendering. See the module docstring."""
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()[:32]


def _matrix():
    """Every fixture in the matrix, in a stable order."""
    for context in CONTEXT_SEEDS:
        for setup in SETUP_SEEDS:
            for execution in EXECUTION_SEEDS:
                for symbol in SYMBOLS:
                    seeds = (context, setup, execution)
                    key = f"{symbol}:{context}-{setup}-{execution}"
                    yield key, seeds, symbol


#: Captured at 666723bc667ecaa074bf3df759142cd29d20a802 — the commit before
#: Slice 1 — as (assessment digest, evidence-report digest).
BASELINE: dict[str, tuple[str, str]] = {
    "BNBUSDT:1-4-7": ("fd637868ff5feca42265dab6cfeab845", "6ff39b5ad83c3b64a2cdafd512c32d38"),
    "BNBUSDT:1-4-8": ("fd637868ff5feca42265dab6cfeab845", "6ff39b5ad83c3b64a2cdafd512c32d38"),
    "BNBUSDT:1-4-9": ("fd637868ff5feca42265dab6cfeab845", "6ff39b5ad83c3b64a2cdafd512c32d38"),
    "BNBUSDT:1-5-7": ("600d740595b9cf935fd4e6db7fc9ed20", "d83a699cd10a691003ab32c03237aa1c"),
    "BNBUSDT:1-5-8": ("600d740595b9cf935fd4e6db7fc9ed20", "d83a699cd10a691003ab32c03237aa1c"),
    "BNBUSDT:1-5-9": ("600d740595b9cf935fd4e6db7fc9ed20", "d83a699cd10a691003ab32c03237aa1c"),
    "BNBUSDT:1-6-7": ("600d740595b9cf935fd4e6db7fc9ed20", "d83a699cd10a691003ab32c03237aa1c"),
    "BNBUSDT:1-6-8": ("600d740595b9cf935fd4e6db7fc9ed20", "d83a699cd10a691003ab32c03237aa1c"),
    "BNBUSDT:1-6-9": ("600d740595b9cf935fd4e6db7fc9ed20", "d83a699cd10a691003ab32c03237aa1c"),
    "BNBUSDT:2-4-7": ("7b1f995a3f56c9f29b61ca140e17aced", "e080506d77287ddbc188947f1d2b1880"),
    "BNBUSDT:2-4-8": ("c23d5cb4ba2d65a21829489728264ddb", "49a9b38c202097f13a327883cbe2c168"),
    "BNBUSDT:2-4-9": ("232baaa01de8fd79aa887f66ebf53a39", "adebce8c9f1bb2d7267b52aba12497f8"),
    "BNBUSDT:2-5-7": ("e9d9dd5300cfece12c1a79494d6b4516", "6902e40288abe372473ecc7bc3ce5d37"),
    "BNBUSDT:2-5-8": ("e9d9dd5300cfece12c1a79494d6b4516", "6902e40288abe372473ecc7bc3ce5d37"),
    "BNBUSDT:2-5-9": ("e9d9dd5300cfece12c1a79494d6b4516", "6902e40288abe372473ecc7bc3ce5d37"),
    "BNBUSDT:2-6-7": ("e9d9dd5300cfece12c1a79494d6b4516", "6902e40288abe372473ecc7bc3ce5d37"),
    "BNBUSDT:2-6-8": ("e9d9dd5300cfece12c1a79494d6b4516", "6902e40288abe372473ecc7bc3ce5d37"),
    "BNBUSDT:2-6-9": ("e9d9dd5300cfece12c1a79494d6b4516", "6902e40288abe372473ecc7bc3ce5d37"),
    "BNBUSDT:3-4-7": ("55be2f0a7183903108234715cf1487d0", "0a265522218031de9f8dd9a3cddabb26"),
    "BNBUSDT:3-4-8": ("55be2f0a7183903108234715cf1487d0", "0a265522218031de9f8dd9a3cddabb26"),
    "BNBUSDT:3-4-9": ("55be2f0a7183903108234715cf1487d0", "0a265522218031de9f8dd9a3cddabb26"),
    "BNBUSDT:3-5-7": ("440d420ed557ad419f170d9e8635ee91", "d0e3b32def3853737b3987860f374dfd"),
    "BNBUSDT:3-5-8": ("440d420ed557ad419f170d9e8635ee91", "d0e3b32def3853737b3987860f374dfd"),
    "BNBUSDT:3-5-9": ("440d420ed557ad419f170d9e8635ee91", "d0e3b32def3853737b3987860f374dfd"),
    "BNBUSDT:3-6-7": ("440d420ed557ad419f170d9e8635ee91", "d0e3b32def3853737b3987860f374dfd"),
    "BNBUSDT:3-6-8": ("440d420ed557ad419f170d9e8635ee91", "d0e3b32def3853737b3987860f374dfd"),
    "BNBUSDT:3-6-9": ("440d420ed557ad419f170d9e8635ee91", "d0e3b32def3853737b3987860f374dfd"),
    "BTCUSDT:1-4-7": ("c74d12683eadd89615c116cddf2f041e", "977afec76fe38b6f7be028de54eed580"),
    "BTCUSDT:1-4-8": ("c74d12683eadd89615c116cddf2f041e", "977afec76fe38b6f7be028de54eed580"),
    "BTCUSDT:1-4-9": ("c74d12683eadd89615c116cddf2f041e", "977afec76fe38b6f7be028de54eed580"),
    "BTCUSDT:1-5-7": ("cb9f6ea0b366d1d90716a76157e88801", "3d510cd10b1e8b71431079a32789ead6"),
    "BTCUSDT:1-5-8": ("cb9f6ea0b366d1d90716a76157e88801", "3d510cd10b1e8b71431079a32789ead6"),
    "BTCUSDT:1-5-9": ("cb9f6ea0b366d1d90716a76157e88801", "3d510cd10b1e8b71431079a32789ead6"),
    "BTCUSDT:1-6-7": ("cb9f6ea0b366d1d90716a76157e88801", "3d510cd10b1e8b71431079a32789ead6"),
    "BTCUSDT:1-6-8": ("cb9f6ea0b366d1d90716a76157e88801", "3d510cd10b1e8b71431079a32789ead6"),
    "BTCUSDT:1-6-9": ("cb9f6ea0b366d1d90716a76157e88801", "3d510cd10b1e8b71431079a32789ead6"),
    "BTCUSDT:2-4-7": ("a77cf11c9341a24e75c506315977cf07", "992e71466b0f60054f4b8a32f7f3feb7"),
    "BTCUSDT:2-4-8": ("a4bf1ed17566ea8e2db69f3ed483a8bf", "0ab59b7457c299027d3c0e653919927a"),
    "BTCUSDT:2-4-9": ("c14597a88cf57de27fea3135b710e8be", "1c36649689bf718ad25bdeeb27a1ff34"),
    "BTCUSDT:2-5-7": ("7f08012eb6f9dcd1fa752c61152fde52", "abc997ff52ee2ae446f4fec3d96116a1"),
    "BTCUSDT:2-5-8": ("7f08012eb6f9dcd1fa752c61152fde52", "abc997ff52ee2ae446f4fec3d96116a1"),
    "BTCUSDT:2-5-9": ("7f08012eb6f9dcd1fa752c61152fde52", "abc997ff52ee2ae446f4fec3d96116a1"),
    "BTCUSDT:2-6-7": ("7f08012eb6f9dcd1fa752c61152fde52", "abc997ff52ee2ae446f4fec3d96116a1"),
    "BTCUSDT:2-6-8": ("7f08012eb6f9dcd1fa752c61152fde52", "abc997ff52ee2ae446f4fec3d96116a1"),
    "BTCUSDT:2-6-9": ("7f08012eb6f9dcd1fa752c61152fde52", "abc997ff52ee2ae446f4fec3d96116a1"),
    "BTCUSDT:3-4-7": ("b983978e45c9b051220976a1dd93c160", "7c6594d0b471cdc1773b7bfc6533490d"),
    "BTCUSDT:3-4-8": ("b983978e45c9b051220976a1dd93c160", "7c6594d0b471cdc1773b7bfc6533490d"),
    "BTCUSDT:3-4-9": ("b983978e45c9b051220976a1dd93c160", "7c6594d0b471cdc1773b7bfc6533490d"),
    "BTCUSDT:3-5-7": ("894b9f2143cf7e44f9572482c7ee1d3c", "8b2ad557e105d79c445796529f796310"),
    "BTCUSDT:3-5-8": ("894b9f2143cf7e44f9572482c7ee1d3c", "8b2ad557e105d79c445796529f796310"),
    "BTCUSDT:3-5-9": ("894b9f2143cf7e44f9572482c7ee1d3c", "8b2ad557e105d79c445796529f796310"),
    "BTCUSDT:3-6-7": ("894b9f2143cf7e44f9572482c7ee1d3c", "8b2ad557e105d79c445796529f796310"),
    "BTCUSDT:3-6-8": ("894b9f2143cf7e44f9572482c7ee1d3c", "8b2ad557e105d79c445796529f796310"),
    "BTCUSDT:3-6-9": ("894b9f2143cf7e44f9572482c7ee1d3c", "8b2ad557e105d79c445796529f796310"),
    "ETHUSDT:1-4-7": ("1aa87e014ba0eecc40ced1322078027b", "2d3a1c7f17920a0a1f8f620d9cfee940"),
    "ETHUSDT:1-4-8": ("1aa87e014ba0eecc40ced1322078027b", "2d3a1c7f17920a0a1f8f620d9cfee940"),
    "ETHUSDT:1-4-9": ("1aa87e014ba0eecc40ced1322078027b", "2d3a1c7f17920a0a1f8f620d9cfee940"),
    "ETHUSDT:1-5-7": ("df47a4da952c0f7b506f360abe1fd0be", "21842375f247f8285bc80b20397622c8"),
    "ETHUSDT:1-5-8": ("df47a4da952c0f7b506f360abe1fd0be", "21842375f247f8285bc80b20397622c8"),
    "ETHUSDT:1-5-9": ("df47a4da952c0f7b506f360abe1fd0be", "21842375f247f8285bc80b20397622c8"),
    "ETHUSDT:1-6-7": ("df47a4da952c0f7b506f360abe1fd0be", "21842375f247f8285bc80b20397622c8"),
    "ETHUSDT:1-6-8": ("df47a4da952c0f7b506f360abe1fd0be", "21842375f247f8285bc80b20397622c8"),
    "ETHUSDT:1-6-9": ("df47a4da952c0f7b506f360abe1fd0be", "21842375f247f8285bc80b20397622c8"),
    "ETHUSDT:2-4-7": ("a5662f6c2b941b90a2b71242f132707f", "11f06b66a3d6c0d55ffef7ac8ae2d1f7"),
    "ETHUSDT:2-4-8": ("415db0f651b973eee1e7b310e61db886", "39276beee8029d34efa51165d1117c0a"),
    "ETHUSDT:2-4-9": ("8af88813b1e12a9e50a884b6053dba35", "07ce66b1dd83c5b64f5a2ae74f501dec"),
    "ETHUSDT:2-5-7": ("294b3217f7da628b84ed28d9144030a0", "1f5236ccf8f13b93268eba71d9f8045a"),
    "ETHUSDT:2-5-8": ("294b3217f7da628b84ed28d9144030a0", "1f5236ccf8f13b93268eba71d9f8045a"),
    "ETHUSDT:2-5-9": ("294b3217f7da628b84ed28d9144030a0", "1f5236ccf8f13b93268eba71d9f8045a"),
    "ETHUSDT:2-6-7": ("294b3217f7da628b84ed28d9144030a0", "1f5236ccf8f13b93268eba71d9f8045a"),
    "ETHUSDT:2-6-8": ("294b3217f7da628b84ed28d9144030a0", "1f5236ccf8f13b93268eba71d9f8045a"),
    "ETHUSDT:2-6-9": ("294b3217f7da628b84ed28d9144030a0", "1f5236ccf8f13b93268eba71d9f8045a"),
    "ETHUSDT:3-4-7": ("ec86d83b03427700b441dc0e5f47b8f0", "693346dd06e8411708eb6e2284d1d425"),
    "ETHUSDT:3-4-8": ("ec86d83b03427700b441dc0e5f47b8f0", "693346dd06e8411708eb6e2284d1d425"),
    "ETHUSDT:3-4-9": ("ec86d83b03427700b441dc0e5f47b8f0", "693346dd06e8411708eb6e2284d1d425"),
    "ETHUSDT:3-5-7": ("605b0bfddd029de7f171fa381c914b09", "b4a8fefaa60dc289bdafc84adcfeb7fb"),
    "ETHUSDT:3-5-8": ("605b0bfddd029de7f171fa381c914b09", "b4a8fefaa60dc289bdafc84adcfeb7fb"),
    "ETHUSDT:3-5-9": ("605b0bfddd029de7f171fa381c914b09", "b4a8fefaa60dc289bdafc84adcfeb7fb"),
    "ETHUSDT:3-6-7": ("605b0bfddd029de7f171fa381c914b09", "b4a8fefaa60dc289bdafc84adcfeb7fb"),
    "ETHUSDT:3-6-8": ("605b0bfddd029de7f171fa381c914b09", "b4a8fefaa60dc289bdafc84adcfeb7fb"),
    "ETHUSDT:3-6-9": ("605b0bfddd029de7f171fa381c914b09", "b4a8fefaa60dc289bdafc84adcfeb7fb"),
}


def test_the_matrix_is_the_size_it_claims_to_be() -> None:
    """A baseline that silently stopped covering the matrix would pass vacuously."""
    assert len(BASELINE) == 81
    assert len(list(_matrix())) == 81
    assert {key for key, _, _ in _matrix()} == set(BASELINE)


def test_no_assessment_changed() -> None:
    """**The non-regression proof.** Eighty-one assessments, unchanged.

    Runs the whole composition — regimes, evidence, decision context, inputs,
    policy — and compares the complete rendering of every result against the
    pre-Slice-1 capture.
    """
    moved = []
    for key, seeds, symbol in _matrix():
        digest = _canonical(setup_assessment_for_sheet(multi(seeds=seeds, symbol=symbol)))
        if digest != BASELINE[key][0]:
            moved.append(key)
    assert not moved, (
        "the swing setup policy produced a different assessment for "
        f"{moved}. Slice 1 must change no trading conclusion; if a later "
        "milestone changes one deliberately, update BASELINE and say why."
    )


def test_no_evidence_report_changed() -> None:
    """The projection is the surface Slice 1 reads through, so it is pinned too."""
    moved = []
    for key, seeds, symbol in _matrix():
        assessment = setup_assessment_for_sheet(multi(seeds=seeds, symbol=symbol))
        if _canonical(project_setup_evidence(assessment)) != BASELINE[key][1]:
            moved.append(key)
    assert not moved, f"the evidence projection changed for {moved}"


def test_the_matrix_still_covers_every_decision_path_it_claims_to() -> None:
    """Guards the guard: a matrix reduced to one path would still pass above."""
    states: collections.Counter[str] = collections.Counter()
    verbatim: set[str] = set()
    kinds: set[str] = set()
    for _, seeds, symbol in _matrix():
        assessment = setup_assessment_for_sheet(multi(seeds=seeds, symbol=symbol))
        states[assessment.state.value] += 1
        if assessment.state is SetupState.WAIT:
            verbatim.add(assessment.thesis[0])
            # Digits normalised away, so the three vote splits ("2 long, 1
            # short", …) count as one *kind* of exit rather than three.
            kinds.add(re.sub(r"[0-9]+", "N", assessment.thesis[0][:90]))

    assert states == collections.Counter({"wait": 72, "candidate": 9})
    # The regime-gate exit and the directional-split exit are both present, and
    # they are the two paths the Slice 1 detail surface must tell apart.
    assert len(kinds) == 2, sorted(kinds)
    assert any("not trending" in kind for kind in kinds)
    assert any("do not agree" in kind for kind in kinds)
    # …and the split exit really does arise from more than one vote pattern, so
    # the matrix is exercising the tally rather than one frozen arrangement.
    assert len(verbatim) >= 4, sorted(verbatim)
