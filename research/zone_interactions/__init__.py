"""R3 / R4 — zone interaction semantics research.

The harness behind report 0052. It implements
`docs/design/ZONE_INTERACTION_RESEARCH_QUESTIONS_V1.md`, sealed at commit
`296831a` before the first line of this package was written.

Nothing here is product code, nothing here may be imported by `fmis`, and
nothing here names a state `BREAKOUT`, `ACCEPTANCE` or `RETEST`. The
vocabulary is the observable one the preregistration fixes in §5:
`INSIDE` / `OUTSIDE_ABOVE` / `OUTSIDE_BELOW`, and the events `EXIT`,
`TRAVERSE` and `RETURN`.
"""
