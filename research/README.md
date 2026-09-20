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

## `zone_interactions/`

The harness behind [report 0052](../reports/0052_2026-09-20_PRICE_ZONE_INTERACTION_SEMANTICS_RESEARCH_GATE.md),
which answered research questions **R3** and **R4** — and answered them mostly in the negative.

```
.venv/bin/python research/zone_interactions/run.py       # events      -> reports/artifacts/0052_zone_interaction_events.json.gz
.venv/bin/python research/zone_interactions/analyze.py   # every table -> reports/artifacts/0052_zone_interaction_tables.json.gz
.venv/bin/python research/zone_interactions/posthoc.py   # POST-HOC    -> reports/artifacts/0052_posthoc_placebo_r3.json.gz
.venv/bin/python research/zone_interactions/fixtures.py  # 68 adversarial assertions
.venv/bin/python research/zone_interactions/verify.py    # 27 invariant + isolation checks
```

**No network.** The same committed Milestone CD capture report 0050 used.

**Pure Python, on purpose.** `pyproject.toml` declares `dependencies = []` and the repository has
kept that property through every milestone. A first draft of `events.py` used NumPy; it was
rewritten rather than install a numerical library into an environment that has never needed one.
The cost stays linear because outside episodes are **disjoint** — an `EXIT` requires the previous
bar to be `INSIDE` — so resolving every return costs one traversal per band, not one per event.

**Every structural fact is produced by production `fmis` code**: `detect_swings` ·
`compare_swing_sequence` · `label_swing_sequence` · `structural_levels` · `zone_width_series` ·
`derive_price_zones` · `AverageTrueRange.compute_series`. This package owns the event walk, the
placebo construction, the metrics and the inference, and nothing else.

**`posthoc.py` is named for what it is.** It runs a control the preregistration did **not**
require, added after reading the R3 result, and it is labelled `POST-HOC` in the module docstring,
in the artifact and in every table it reaches.

The preregistration it implements is
[`ZONE_INTERACTION_RESEARCH_QUESTIONS_V1.md`](../docs/design/ZONE_INTERACTION_RESEARCH_QUESTIONS_V1.md),
sealed at commit `296831a` before the first line here was written.
