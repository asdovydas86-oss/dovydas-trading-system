"""Scan memory — **what changed since the previous comparable completed scan.**

    record_scan(workspace, store=..., ...)  ──►  ScanComparison

**The product problem.** The Swing workspace answers *what is happening with this
symbol now, and why*. It could not answer *what changed since the last time I
looked*, so the operator held the previous dashboard in his head and compared
twenty symbols by memory — or, in practice, did not compare them at all. This
package remembers the scan so he does not have to.

**Four rules, and every one of them is a guard test:**

  * **Observation only.** History is never an input to a trading decision. The
    dependency arrow runs `swing_workspace → scan_memory` and never back;
    `SetupAssessment`, the regime gates, the evidence tally and candidate
    admission cannot reach anything here.
  * **Structured state, never prose.** A change is a difference between two
    named values an engine already decided. No sentence, thesis line or rendered
    fragment is compared anywhere in this package.
  * **No score and no ranking.** `WAIT → CANDIDATE` is a named factual
    transition, not a 95/100. Changed symbols are *partitioned* from unchanged
    ones so the operator can find them, in the scan's own universe order.
  * **Time passing is not a change.** The comparator's whole field list is
    `CHANGE_DIMENSIONS`, and no instant, age or bar count is on it — so a
    refresh an hour later over an unchanged market reports nothing at all.

**Absence of history is a valid state and is never rendered as an error.** The
first scan says a baseline was recorded; a scan that cannot be compared says why;
a scan whose history could not be read says that, and the market analysis on the
page is unaffected by all three.

**This package makes no claim about profitability.** A remembered transition is
an observation of the system's own state. It is not a signal, not a validated
edge, not a calibrated probability and not a reason to trade — the research
record (CA `NO_EDGE`, CB `UNDERPOWERED`, CC `INFEASIBLE`, CD's dependence
findings) is unchanged by anything here.
"""

from __future__ import annotations

from fmis.scan_memory.comparison import (
    EVIDENCE_DECLINED,
    EVIDENCE_PROJECTED,
    INDEPENDENCE_ESTABLISHED,
    INDEPENDENCE_NOT_ESTABLISHED,
    compare_scans,
    dimension_values,
    incomparable_reason,
    transitions_between,
)
from fmis.scan_memory.codec import decode_scan, encode_scan
from fmis.scan_memory.models import (
    ABSENT,
    CHANGE_DIMENSIONS,
    PRESENT,
    SCAN_MEMORY_SCHEMA_VERSION,
    STRUCTURE_DIMENSIONS,
    NOT_STATED,
    ChangeDimension,
    ComparisonStatus,
    ScanComparison,
    ScanHistoryFormatError,
    ScanHistoryIOError,
    ScanIdentity,
    ScanMemoryError,
    ScanRecord,
    StateTransition,
    SymbolChange,
    SymbolState,
)
from fmis.scan_memory.projection import (
    scan_identity_for,
    scan_record_from,
    symbol_state_of,
)
from fmis.scan_memory.recorder import (
    NO_PREVIOUS_SCAN_REASON,
    compare_and_record,
    record_scan,
)
from fmis.scan_memory.store import (
    DEFAULT_RETAINED_SCANS,
    DEFAULT_SCAN_MEMORY_ROOT,
    HISTORY_ERRORS,
    SCANS_DIRECTORY,
    ScanHistoryStore,
    StoredScan,
    default_scan_memory_root,
)

__all__ = [
    # the model
    "SCAN_MEMORY_SCHEMA_VERSION",
    "NOT_STATED",
    "PRESENT",
    "ABSENT",
    "ScanMemoryError",
    "ScanHistoryFormatError",
    "ScanHistoryIOError",
    "ChangeDimension",
    "CHANGE_DIMENSIONS",
    "STRUCTURE_DIMENSIONS",
    "ComparisonStatus",
    "ScanIdentity",
    "SymbolState",
    "ScanRecord",
    "StateTransition",
    "SymbolChange",
    "ScanComparison",
    # projection
    "scan_identity_for",
    "symbol_state_of",
    "scan_record_from",
    # comparison
    "INDEPENDENCE_ESTABLISHED",
    "INDEPENDENCE_NOT_ESTABLISHED",
    "EVIDENCE_PROJECTED",
    "EVIDENCE_DECLINED",
    "incomparable_reason",
    "dimension_values",
    "transitions_between",
    "compare_scans",
    # persistence
    "encode_scan",
    "decode_scan",
    "DEFAULT_SCAN_MEMORY_ROOT",
    "DEFAULT_RETAINED_SCANS",
    "SCANS_DIRECTORY",
    "HISTORY_ERRORS",
    "default_scan_memory_root",
    "StoredScan",
    "ScanHistoryStore",
    # the composition
    "NO_PREVIOUS_SCAN_REASON",
    "compare_and_record",
    "record_scan",
]
