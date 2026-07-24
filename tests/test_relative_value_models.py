"""Tests for RVE result/error models (fmis.relative_value.models)."""

from __future__ import annotations

import pytest

from fmis.relative_value.models import (
    InsufficientObservationsError,
    MetricStatus,
    NotAlignedError,
    RelativeValueError,
    RelativeValueResult,
    UndefinedReason,
)


# --- enums -------------------------------------------------------------------


def test_metric_status_members() -> None:
    assert {s.name for s in MetricStatus} == {"OK", "UNDEFINED"}


def test_undefined_reason_members() -> None:
    assert {r.name for r in UndefinedReason} == {
        "ZERO_DENOMINATOR",
        "ZERO_VARIANCE",
        "ZERO_REFERENCE_VOLATILITY",
        "NON_FINITE_RESULT",
    }


# --- OK results --------------------------------------------------------------


def test_ok_result_via_classmethod() -> None:
    r = RelativeValueResult.ok("m", 1.5, {"k": "v"})
    assert r.status is MetricStatus.OK
    assert r.value == 1.5
    assert r.reason is None
    assert r.metadata["k"] == "v"


def test_ok_result_allows_zero_and_negative() -> None:
    assert RelativeValueResult.ok("m", 0.0, {}).value == 0.0
    assert RelativeValueResult.ok("m", -2.0, {}).value == -2.0


def test_ok_result_rejects_none_value() -> None:
    with pytest.raises(ValueError, match="OK result requires a float"):
        RelativeValueResult(
            name="m", value=None, status=MetricStatus.OK, reason=None
        )


def test_ok_result_rejects_non_finite() -> None:
    for bad in (float("inf"), float("-inf"), float("nan")):
        with pytest.raises(ValueError, match="must be finite"):
            RelativeValueResult(
                name="m", value=bad, status=MetricStatus.OK, reason=None
            )


def test_ok_result_rejects_bool_value() -> None:
    with pytest.raises(ValueError, match="OK result requires a float"):
        RelativeValueResult(
            name="m", value=True, status=MetricStatus.OK, reason=None  # type: ignore[arg-type]
        )


def test_ok_result_rejects_int_value() -> None:
    # Metrics always produce float; an int is a programming error.
    with pytest.raises(ValueError, match="OK result requires a float"):
        RelativeValueResult(
            name="m", value=1, status=MetricStatus.OK, reason=None  # type: ignore[arg-type]
        )


def test_ok_result_rejects_reason() -> None:
    with pytest.raises(ValueError, match="must not carry a reason"):
        RelativeValueResult(
            name="m",
            value=1.0,
            status=MetricStatus.OK,
            reason=UndefinedReason.ZERO_VARIANCE,
        )


# --- UNDEFINED results -------------------------------------------------------


def test_undefined_result_via_classmethod() -> None:
    r = RelativeValueResult.undefined("m", UndefinedReason.ZERO_VARIANCE, {"k": 1})
    assert r.status is MetricStatus.UNDEFINED
    assert r.value is None
    assert r.reason is UndefinedReason.ZERO_VARIANCE
    assert r.metadata["k"] == 1


def test_undefined_result_requires_none_value() -> None:
    with pytest.raises(ValueError, match="value=None"):
        RelativeValueResult(
            name="m",
            value=1.0,
            status=MetricStatus.UNDEFINED,
            reason=UndefinedReason.ZERO_DENOMINATOR,
        )


def test_undefined_result_requires_reason() -> None:
    with pytest.raises(ValueError, match="requires an UndefinedReason"):
        RelativeValueResult(
            name="m", value=None, status=MetricStatus.UNDEFINED, reason=None
        )


# --- generic validation ------------------------------------------------------


def test_empty_name_rejected() -> None:
    with pytest.raises(ValueError, match="name cannot be empty"):
        RelativeValueResult.ok("  ", 1.0, {})


def test_bad_status_rejected() -> None:
    with pytest.raises(ValueError, match="status must be a MetricStatus"):
        RelativeValueResult(
            name="m", value=1.0, status="ok", reason=None  # type: ignore[arg-type]
        )


# --- immutability ------------------------------------------------------------


def test_result_is_frozen() -> None:
    r = RelativeValueResult.ok("m", 1.0, {})
    with pytest.raises(AttributeError):
        r.value = 2.0  # type: ignore[misc]


def test_metadata_is_read_only() -> None:
    r = RelativeValueResult.ok("m", 1.0, {"k": 1})
    with pytest.raises(TypeError):
        r.metadata["k"] = 2  # type: ignore[index]


def test_metadata_is_defensively_copied() -> None:
    original = {"k": 1}
    r = RelativeValueResult.ok("m", 1.0, original)
    original["k"] = 99
    assert r.metadata["k"] == 1


# --- exception hierarchy -----------------------------------------------------


def test_exception_hierarchy() -> None:
    assert issubclass(NotAlignedError, RelativeValueError)
    assert issubclass(NotAlignedError, ValueError)
    assert issubclass(InsufficientObservationsError, RelativeValueError)
    assert issubclass(InsufficientObservationsError, ValueError)


def test_insufficient_observations_carries_context() -> None:
    err = InsufficientObservationsError(metric="period_return", required=2, actual=1)
    assert err.metric == "period_return"
    assert err.required == 2
    assert err.actual == 1
    assert "at least 2" in str(err)
