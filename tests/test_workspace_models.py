"""Milestone AK — the workspace value types.

The model carries the promises the whole milestone rests on: the page is
complete, its order is fixed, an unavailable section cannot masquerade as an
answered one, and a tier cannot be changed on the way to a renderer.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from fmis.workspace.models import (
    SECTION_ORDER,
    WORKSPACE_SCHEMA_VERSION,
    NoteBlock,
    Provenance,
    Row,
    RowBlock,
    Section,
    SectionId,
    SectionStatus,
    TableBlock,
    Tier,
    Unavailable,
    Workspace,
    WorkspaceError,
    require_sections,
)

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def section(section_id: SectionId = SectionId.INSTRUMENT, **overrides) -> Section:
    fields = dict(
        id=section_id,
        title="TITLE",
        status=SectionStatus.AVAILABLE,
        summary=("a summary",),
        body=(RowBlock((Row("label", "value"),)),),
    )
    fields.update(overrides)
    return Section(**fields)  # type: ignore[arg-type]


def unavailable(section_id: SectionId) -> Unavailable:
    return Unavailable(
        id=section_id,
        title="TITLE",
        owner="EP-99",
        reason="not built",
        prohibition="do not infer one",
    )


def full_sections() -> tuple:
    built = {
        SectionId.RISK,
        SectionId.PORTFOLIO,
        SectionId.TRADE_PLAN,
        SectionId.INTERPRETATION,
    }
    return tuple(
        unavailable(sid) if sid in built else section(sid) for sid in SECTION_ORDER
    )


def workspace(**overrides) -> Workspace:
    fields = dict(
        symbol="BTCUSDT",
        objective="swing_trade",
        as_of=_BASE,
        source="fixture",
        sections=full_sections(),
    )
    fields.update(overrides)
    return Workspace(**fields)  # type: ignore[arg-type]


# ============ 1. the page is complete and ordered ===========================


def test_a_workspace_must_carry_every_section() -> None:
    """An omitted section is invisible, and an invisible gap reads as no gap."""
    partial = tuple(s for s in full_sections() if s.id is not SectionId.RISK)
    with pytest.raises(WorkspaceError) as excinfo:
        workspace(sections=partial)
    assert "risk" in str(excinfo.value)


def test_sections_must_follow_the_canonical_order() -> None:
    reordered = tuple(reversed(full_sections()))
    with pytest.raises(WorkspaceError) as excinfo:
        workspace(sections=reordered)
    assert "SECTION_ORDER" in str(excinfo.value)


def test_a_section_may_not_appear_twice() -> None:
    doubled = full_sections() + (section(SectionId.INSTRUMENT),)
    with pytest.raises(WorkspaceError):
        workspace(sections=doubled)


def test_the_canonical_order_covers_every_section_id_exactly_once() -> None:
    assert set(SECTION_ORDER) == set(SectionId)
    assert len(SECTION_ORDER) == len(set(SECTION_ORDER))


def test_limitations_is_last_and_instrument_is_first() -> None:
    """The order is the argument: data quality gates the page, caveats close it."""
    assert SECTION_ORDER[0] is SectionId.INSTRUMENT
    assert SECTION_ORDER[-1] is SectionId.LIMITATIONS


def test_regime_precedes_structure() -> None:
    """SPEC §5 and the v3 correction both put the environment before the reading."""
    assert SECTION_ORDER.index(SectionId.REGIME) < SECTION_ORDER.index(
        SectionId.STRUCTURE
    )


def test_conflicts_precede_every_unbuilt_planning_section() -> None:
    conflicts = SECTION_ORDER.index(SectionId.CONFLICTS)
    for later in (SectionId.RISK, SectionId.TRADE_PLAN, SectionId.INTERPRETATION):
        assert conflicts < SECTION_ORDER.index(later)


def test_require_sections_orders_canonically() -> None:
    shuffled = tuple(reversed(full_sections()))
    assert [s.id for s in require_sections(shuffled)] == list(SECTION_ORDER)


def test_require_sections_rejects_a_string_or_a_stranger() -> None:
    with pytest.raises(TypeError):
        require_sections("not a sequence")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        require_sections([object()])  # type: ignore[list-item]


# ============ 2. unavailable is a different thing ===========================


def test_a_section_may_not_claim_unavailable_status() -> None:
    """The two carry different obligations, so they are different types."""
    with pytest.raises(WorkspaceError) as excinfo:
        section(status=SectionStatus.UNAVAILABLE)
    assert "Unavailable" in str(excinfo.value)


def test_unavailable_exposes_the_same_surface_as_a_section() -> None:
    item = unavailable(SectionId.RISK)
    assert item.status is SectionStatus.UNAVAILABLE
    assert item.body == ()
    assert item.caveats == ()
    assert item.provenance is None
    assert item.summary == (item.reason, item.prohibition)
    assert item.reason_text == item.reason


def test_unavailable_requires_an_owner_and_a_prohibition() -> None:
    """A blank slot teaches the reader it was considered; a prohibition does not."""
    for field in ("title", "owner", "reason", "prohibition"):
        with pytest.raises(WorkspaceError):
            Unavailable(
                **{
                    **dict(
                        id=SectionId.RISK,
                        title="T",
                        owner="O",
                        reason="R",
                        prohibition="P",
                    ),
                    field: "  ",
                }
            )


def test_unavailable_rejects_a_non_section_id() -> None:
    with pytest.raises(TypeError):
        Unavailable(
            id="risk", title="T", owner="O", reason="R", prohibition="P"
        )  # type: ignore[arg-type]


def test_a_failed_section_must_say_why() -> None:
    with pytest.raises(WorkspaceError) as excinfo:
        section(status=SectionStatus.FAILED, reason=None)
    assert "why" in str(excinfo.value)
    assert section(status=SectionStatus.FAILED, reason="the fetch failed")


# ============ 3. blocks validate their own shape ============================


def test_a_table_rejects_a_record_that_does_not_match_its_columns() -> None:
    """A short record means a provider lost a value; padding would hide it."""
    with pytest.raises(WorkspaceError) as excinfo:
        TableBlock(columns=("a", "b"), records=(("only one",),))
    assert "declares 2 columns" in str(excinfo.value)


def test_a_table_requires_columns() -> None:
    with pytest.raises(WorkspaceError):
        TableBlock(columns=(), records=())


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(columns=["a"], records=()),
        dict(columns=(1,), records=()),
        dict(columns=("a",), records=[("x",)]),
        dict(columns=("a",), records=(["x"],)),
        dict(columns=("a",), records=((1,),)),
        dict(columns=("a",), records=(), heading=7),
    ],
)
def test_table_type_validation(kwargs: dict) -> None:
    with pytest.raises(TypeError):
        TableBlock(**kwargs)  # type: ignore[arg-type]


def test_a_note_block_needs_at_least_one_non_empty_note() -> None:
    with pytest.raises(WorkspaceError):
        NoteBlock(())
    with pytest.raises(WorkspaceError):
        NoteBlock(("  ",))


def test_a_row_block_validates_its_rows() -> None:
    with pytest.raises(TypeError):
        RowBlock(rows=[Row("a", "b")])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        RowBlock(rows=("not a row",))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        RowBlock(rows=(), heading=7)  # type: ignore[arg-type]


def test_a_row_requires_a_label_and_a_tier() -> None:
    with pytest.raises(WorkspaceError):
        Row("   ", "value")
    with pytest.raises(TypeError):
        Row("label", 7)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Row("label", "value", tier="fact")  # type: ignore[arg-type]


def test_a_section_rejects_an_unknown_block_type() -> None:
    with pytest.raises(TypeError) as excinfo:
        section(body=("not a block",))
    assert "RowBlock, TableBlock or NoteBlock" in str(excinfo.value)


@pytest.mark.parametrize("field", ["summary", "caveats"])
def test_summary_and_caveat_lines_must_be_non_empty(field: str) -> None:
    with pytest.raises(WorkspaceError):
        section(**{field: ("  ",)})
    with pytest.raises(TypeError):
        section(**{field: ["a"]})


def test_section_type_validation() -> None:
    with pytest.raises(TypeError):
        section(section_id="instrument")  # type: ignore[arg-type]
    with pytest.raises(WorkspaceError):
        section(title="  ")
    with pytest.raises(TypeError):
        section(status="available")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        section(body=[RowBlock(())])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        section(provenance="fmis")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        section(reason=7)  # type: ignore[arg-type]


# ============ 4. provenance ================================================


def test_provenance_requires_an_engine() -> None:
    with pytest.raises(WorkspaceError):
        Provenance(engine="  ")
    with pytest.raises(TypeError):
        Provenance(engine="e", policy_id=7)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Provenance(engine="e", as_of="2026")  # type: ignore[arg-type]


def test_provenance_permits_no_policy_and_no_timestamp() -> None:
    """Stating "no policy" plainly beats an empty string a reader must interpret."""
    item = Provenance(engine="fmis.workspace")
    assert item.policy_id is None
    assert item.as_of is None


# ============ 5. the workspace object =======================================


def test_a_workspace_is_immutable_and_copies_its_metadata() -> None:
    source = {"a": 1}
    built = workspace(metadata=source)
    source["a"] = 2
    assert built.metadata["a"] == 1
    with pytest.raises(TypeError):
        built.metadata["b"] = 3  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        built.symbol = "ETHUSDT"  # type: ignore[misc]


def test_projections_never_store_a_second_copy() -> None:
    built = workspace()
    assert set(built.by_id) == set(SECTION_ORDER)
    assert len(built.available) + len(built.unavailable) == len(SECTION_ORDER)
    assert all(s.status is SectionStatus.UNAVAILABLE for s in built.unavailable)


def test_the_schema_version_travels_with_the_artifact() -> None:
    """A stored workspace must be readable years later; a schema-less one is not."""
    assert workspace().schema_version == WORKSPACE_SCHEMA_VERSION
    with pytest.raises(TypeError):
        workspace(schema_version="1")
    with pytest.raises(TypeError):
        workspace(schema_version=True)


@pytest.mark.parametrize("field", ["symbol", "objective", "source"])
def test_a_workspace_requires_its_identity(field: str) -> None:
    with pytest.raises(WorkspaceError):
        workspace(**{field: "  "})


def test_workspace_type_validation() -> None:
    with pytest.raises(TypeError):
        workspace(as_of="2026-01-01")
    with pytest.raises(TypeError):
        workspace(sections=list(full_sections()))
    with pytest.raises(TypeError):
        workspace(sections=("not a section",) * len(SECTION_ORDER))


def test_equality_is_structural() -> None:
    assert workspace() == workspace()
    assert workspace() != workspace(symbol="ETHUSDT")


# ============ 6. tiers ======================================================


def test_every_tier_is_reachable_and_named_without_direction() -> None:
    assert {t.value for t in Tier} == {"fact", "derived", "interpretation", "absence"}
    for member in Tier:
        for banned in ("bullish", "bearish", "long", "short", "buy", "sell"):
            assert banned not in member.value


def test_a_row_defaults_to_fact_and_can_be_marked_otherwise() -> None:
    assert Row("a", "b").tier is Tier.FACT
    assert Row("a", "b", tier=Tier.ABSENCE).tier is Tier.ABSENCE


def test_a_note_block_rejects_a_non_tuple() -> None:
    with pytest.raises(TypeError):
        NoteBlock(notes=["a note"])  # type: ignore[arg-type]
