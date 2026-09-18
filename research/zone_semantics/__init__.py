"""Price-zone semantics research — **NOT production code**.

Nothing under `research/` is importable by `fmis`, is exercised by the
production test suite, or may be depended on by the operator dashboard. It
exists to answer report 0047's decisions D1 and D2 and is deletable without
touching a single production guarantee.

The preregistration this harness implements is
`docs/design/ZONE_PARAMETER_RESEARCH_QUESTIONS_V1.md`, sealed at commit
`c05e870` before any line of this package was written.

Every structural fact this harness consumes is produced by **production**
`fmis` code, called and never reimplemented: `detect_swings`,
`compare_swing_sequence`, `label_swing_sequence`, `structural_levels` and
`AverageTrueRange.compute_series`. The research code owns the grouping
policies and the metrics, and nothing else.
"""
