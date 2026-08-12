"""The domain's citation of an archived analysis page.

One type. The page itself stays owned by `fmis.archive`, unmodified.
"""

from __future__ import annotations

from fmis.analysis_record.models import (
    ANALYSIS_RECORD_KIND,
    ANALYSIS_RECORD_SCHEMA_VERSION,
    SUPPORTED_ANALYSIS_RECORD_VERSIONS,
    AnalysisRecord,
    AnalysisRecordError,
)

__all__ = [
    "AnalysisRecordError",
    "AnalysisRecord",
    "ANALYSIS_RECORD_SCHEMA_VERSION",
    "SUPPORTED_ANALYSIS_RECORD_VERSIONS",
    "ANALYSIS_RECORD_KIND",
]
