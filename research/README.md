# `research/` — study code, deliberately outside `src/`

Code here answers a question. It is **not** part of the product.

| Rule | Why |
|---|---|
| `fmis` never imports from `research/` | asserted by `verify.py`, which greps `src/` and `tests/` and requires **0** hits |
| `fmis` imports with `research/` absent from the path | also asserted by `verify.py` |
| The production test suite never runs this code | it is not under `tests/` |
| Any package here is deletable without touching a product guarantee | that is the point of the directory |

Study code that lived inside a production namespace is how `fmis.paired_dependence` and
`fmis.swing_lab` came to carry milestone-specific preregistrations in `src/`. That was the right call
for those milestones, which shipped a `fmits research` command. It is the wrong call for a gate that
ships no capability, so this directory exists instead.

## `zone_semantics/`

The harness behind [report 0050](../reports/0050_2026-09-18_PRICE_ZONE_SEMANTICS_RESEARCH_GATE.md),
which resolved report 0047's **D1** and **D2**.

```
.venv/bin/python research/zone_semantics/run.py        # the main grid  -> reports/artifacts/0050_zone_semantics_results.json.gz
.venv/bin/python research/zone_semantics/secondary.py  # regimes + D2   -> reports/artifacts/0050_zone_semantics_secondary.json.gz
.venv/bin/python research/zone_semantics/analyze.py    # every table in the report
.venv/bin/python research/zone_semantics/verify.py     # determinism + the two isolation assertions
```

**No network.** The dataset is `reports/artifacts/0040_cd_source_capture.json.gz`, a committed
capture written for Milestone CD — which is why it could not have been chosen to flatter this
milestone's result.

**Every structural fact is produced by production `fmis` code**, called and never reimplemented:
`detect_swings` · `compare_swing_sequence` · `label_swing_sequence` · `structural_levels` ·
`derive_level_crossings` · `AverageTrueRange.compute_series`. This package owns the candidate
grouping policies and the metrics, and nothing else.

The preregistration it implements is
[`ZONE_PARAMETER_RESEARCH_QUESTIONS_V1.md`](../docs/design/ZONE_PARAMETER_RESEARCH_QUESTIONS_V1.md),
sealed at commit `c05e870` before the first line here was written.
