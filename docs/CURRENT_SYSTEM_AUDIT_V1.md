# Current System Audit V1

**Date:** 2026-07-17
**Scope:** Read-only audit of the `dovydas-trading-system` repository.
**Method:** Direct inspection of every tracked and untracked file in the repository, plus git history and status. No application code was created or modified to produce this report.

> **How to read this document.** Findings are tagged:
> - **[FACT]** — directly verified from a file in this repository or from git.
> - **[EVIDENCE]** — an observation that supports an inference, with its source cited.
> - **[ASSUMPTION]** — a reasonable inference not directly verified.
> - **[UNKNOWN]** — an open question requiring verification before it is relied upon.

---

## 1. Executive Summary

**[FACT]** This repository currently contains **no application code**. It is a scaffold of configuration templates, setup documentation, one shell launcher script, and one AI prompt. The complete tracked-and-untracked file set is listed in §2.

**[FACT]** The functioning "system" today is a workflow rather than a program: Claude Code drives a live TradingView Desktop chart through a third-party MCP server (installed outside this repository) using the strategy encoded in [prompts/swing-trading-analyzer-v3.md](../prompts/swing-trading-analyzer-v3.md).

**[EVIDENCE]** The most substantial in-repo assets are analytical documents, not code: [docs/analysis-notes.md](analysis-notes.md) records a root-cause analysis of directional bias, and [PROJECT_SPECIFICATION_V1.md](../PROJECT_SPECIFICATION_V1.md) defines the target architecture (data → deterministic calculations → structured features → AI interpretation → decision support).

**[FACT]** The gap between the current state and that target architecture is large but clean: there is no legacy application code to untangle. Migration is additive, not a rewrite.

**[FACT]** Secret hygiene is currently sound: no secret values are present in the repository, `.env` is git-ignored and does not exist on disk, and `.env.example` contains only a non-secret port number.

---

## 2. Current Repository Structure

**[FACT]** Complete file listing (excluding `.git/` internals and `.DS_Store`):

```
dovydas-trading-system/
├── .claude/settings.local.json     # Claude Code tool-permission config (local; untracked)
├── .env.example                    # secret template: TV_DEBUG_PORT + commented placeholders
├── .gitignore                      # ignores .env, node_modules/, .DS_Store, *.log
├── .mcp.json                       # project MCP config (untracked; machine-specific path)
├── PROJECT_SPECIFICATION_V1.md     # target architecture spec (untracked)
├── PROJECT_VISION_ADDENDUM_V1.md   # vision update dated 2026-07-16 (untracked)
├── README.md                       # repository overview
├── config/mcp.json.example         # templated (path-redacted) version of .mcp.json
├── docs/
│   ├── SETUP.md                    # TradingView MCP setup + CDP launch instructions
│   ├── analysis-notes.md           # v2→v3 directional-bias post-mortem
│   └── CURRENT_SYSTEM_AUDIT_V1.md  # this document
├── prompts/
│   └── swing-trading-analyzer-v3.md  # the active strategy definition
└── scripts/tradingview-launcher.sh # launches TradingView Desktop with CDP debug port
```

**[FACT]** Languages/frameworks in the repository: none. There is no `package.json`, no Python source, and no `tests/` directory. The referenced MCP server is third-party Node.js code installed elsewhere on the machine.

**[FACT]** No `v2` prompt file exists in the repository. Only `v3` is present, alongside a written description of `v2`'s flaws in [docs/analysis-notes.md](analysis-notes.md).

---

## 3. Current Runtime / Data Flow

**[FACT]** Verified from [docs/SETUP.md](SETUP.md), [scripts/tradingview-launcher.sh](../scripts/tradingview-launcher.sh), and [config/mcp.json.example](../config/mcp.json.example):

1. `tradingview-launcher.sh` starts TradingView Desktop with a Chrome DevTools Protocol (CDP) remote-debugging port (default `9222`).
2. Claude Code loads a `tradingview` MCP server (`node .../tradingview-mcp/src/server.js`), which attaches to TradingView over CDP.
3. The user invokes the v3 prompt; Claude reads chart state and indicator values through MCP tools, reasons through the checklist, and draws entry/stop/target lines back onto the chart.

**[FACT]** There is no program entry point in the repository. The "runtime" is a Claude Code conversation.

**[EVIDENCE]** Regime classification, both-direction scoring, divergence detection, support/resistance identification, and position sizing are all described as tasks performed by the model inside the prompt ([prompts/swing-trading-analyzer-v3.md](../prompts/swing-trading-analyzer-v3.md)); none are performed by repository code. No analysis output is persisted to disk by anything in the repository.

---

## 4. Existing Components and Recommended Disposition

| Component | Location | Disposition |
|---|---|---|
| TradingView MCP integration | referenced in [config/mcp.json.example](../config/mcp.json.example); server installed off-repo | **Preserve as a temporary working adapter** — see §11 |
| CDP launcher script | [scripts/tradingview-launcher.sh](../scripts/tradingview-launcher.sh) | **Preserve** — small and correct |
| v3 strategy prompt | [prompts/swing-trading-analyzer-v3.md](../prompts/swing-trading-analyzer-v3.md) | **Preserve** as the strategy definition; canonical status to be confirmed (§7) |
| v2→v3 bias analysis | [docs/analysis-notes.md](analysis-notes.md) | **Preserve** — first decision-log-style record |
| Project spec + vision addendum | [PROJECT_SPECIFICATION_V1.md](../PROJECT_SPECIFICATION_V1.md), [PROJECT_VISION_ADDENDUM_V1.md](../PROJECT_VISION_ADDENDUM_V1.md) | **Preserve and commit** (currently untracked) |
| Secret-handling conventions | [.env.example](../.env.example), [.gitignore](../.gitignore) | **Preserve** |

---

## 5. Deterministic vs AI Responsibilities (current split)

**[FACT]** The only deterministic computation currently available is whatever TradingView itself calculates and exposes through the MCP data tools (EMA/RSI/MACD values, OHLCV, quotes). No repository code consumes those values programmatically.

**[EVIDENCE]** Everything else is delegated to the model by the prompt: regime classification, all checklist evaluations, divergence and pattern detection, support/resistance identification, the 0–9 scores, eligibility rules, position sizing, and risk/reward math ([prompts/swing-trading-analyzer-v3.md](../prompts/swing-trading-analyzer-v3.md), Steps 1–3 and the indicator rules).

**[FACT]** This inverts the target architecture in [PROJECT_SPECIFICATION_V1.md](../PROJECT_SPECIFICATION_V1.md) §3, which requires objective values to be computed by code and reserves the model for contextual interpretation.

---

## 6. Technical Analysis Engine Assessment

**[FACT]** There is no technical-analysis engine in the repository. The v3 prompt is its de facto specification.

**[EVIDENCE]** Assessed against [PROJECT_SPECIFICATION_V1.md](../PROJECT_SPECIFICATION_V1.md) §4, the v3 prompt conflicts with the spec's own principles in specific places:

- **Binary rules the spec forbids.** [prompts/swing-trading-analyzer-v3.md:90-91](../prompts/swing-trading-analyzer-v3.md) states "Price BREAKS ABOVE EMA 200 = strong LONG signal" and "Golden Cross = very strong LONG." Spec §4.1 explicitly rejects "bullish crossover = automatically enter long." The prompt has no notion of EMA slope, distance, or compression.
- **Evidence double-counting the spec forbids.** Checklist items 2, 6, and 8 on each side ([prompts/swing-trading-analyzer-v3.md:42-61](../prompts/swing-trading-analyzer-v3.md)) are all momentum proxies and can score independently for what is essentially one underlying move. Spec §4.6 requires grouping correlated indicators.
- **Shallow MACD treatment** relative to spec §4.2 (which asks for rate of change, consecutive improvement, zero-line context, distance from signal).

**[EVIDENCE]** Useful elements to carry forward: regime-first ordering, mirrored bullish/bearish tool definitions, single-point trend alignment, and weekly EMA 50 as the actionable level with EMA 200 demoted ([prompts/swing-trading-analyzer-v3.md:20-61,82-86](../prompts/swing-trading-analyzer-v3.md)).

---

## 7. Strategy and Signal Logic Assessment

**[FACT]** v3 is the only strategy artifact in the repository. v2 exists only as described in [docs/analysis-notes.md](analysis-notes.md).

**[UNKNOWN] The canonical status of the v3 prompt must be confirmed.** It is present in the repository, but whether this file is the single source of truth (versus a copy maintained elsewhere) has not been verified. This must be resolved before the prompt is treated as authoritative.

**[EVIDENCE]** The v2→v3 iteration documented in [docs/analysis-notes.md](analysis-notes.md) diagnoses six real prompt-engineering failure modes (trend-gate double counting, a contradictory short definition, bullish-only tool definitions, a rarely-activating RSI gate, no NO-TRADE option, and order anchoring) and applies symmetric fixes.

**[EVIDENCE]** The decision rule (score ≥ 3 of 9, higher side wins, tie or both-low → NO TRADE) is explicit ([prompts/swing-trading-analyzer-v3.md:63-68](../prompts/swing-trading-analyzer-v3.md)) but the threshold is unvalidated, and the scores are produced by the model rather than by code, so they are not reproducible.

**[FACT]** Risk logic is per-trade only (2% risk rule, minimum 1:2 R:R) and is computed by the model. There is no portfolio-level risk logic and no volatility-based (ATR) sizing in the repository.

---

## 8. Testing and Backtesting Assessment

**[FACT]** There are zero tests, zero backtesting code, and zero persistence in the repository. Nothing is currently verifiable through automated means, because there is no code to test and no analysis output is recorded to disk.

**[FACT]** The v3 prompt's stated expected outcome — that LONG/SHORT frequency should track market conditions ([docs/analysis-notes.md:74-78](analysis-notes.md)) — is currently untestable, because no analyses are recorded.

**[FACT]** The only presently verifiable item is the MCP connection itself, via the health check documented in [docs/SETUP.md](SETUP.md).

---

## 9. Risks and Technical Debt

**[FACT] Closed-candle handling is not addressed anywhere in the repository.** The v3 prompt contains no rule restricting analysis to closed candles, and the MCP data tools can return the live, still-forming bar. **Closed-candle handling must be explicitly implemented and tested before any signal is considered reproducible** (see §12, milestone B/C).

**[EVIDENCE]** Non-reproducible signals: model-judged regimes, divergences, support/resistance levels, and scores cannot be audited after the fact, because no record of the input data or the reasoning is stored.

**[FACT]** Classic look-ahead / data-leakage bias is not currently present because no backtesting exists — but the spec's backtesting plans ([PROJECT_SPECIFICATION_V1.md](../PROJECT_SPECIFICATION_V1.md) §18) will require explicit guards that do not yet exist.

**[EVIDENCE]** Prompt monolith: strategy rules, indicator education, risk math, chart-drawing instructions, and output formatting are combined in one 199-line file ([prompts/swing-trading-analyzer-v3.md](../prompts/swing-trading-analyzer-v3.md)), the tightest coupling in the project.

**[EVIDENCE]** Single point of failure: the workflow depends on TradingView Desktop + CDP port + a third-party MCP server + Claude Code, with no abstraction layer in the repository.

**[EVIDENCE]** Fragile launcher assumptions: a hardcoded application path and a `pgrep` pattern ([scripts/tradingview-launcher.sh:9,18](../scripts/tradingview-launcher.sh)) will break if TradingView's install layout changes.

**[EVIDENCE] References to Python script names `ta.py`, `ta_w.py`, and `ta_4h.py` appear in local Claude permission configuration** ([.claude/settings.local.json:20-24](../.claude/settings.local.json), e.g. `"Bash(python3 ta.py)"`). **[UNKNOWN]** The contents, past existence on disk, and quality of these scripts are unverified. No files with these names exist in the repository. No claim about what they computed or whether the work was valuable is made here.

---

## 10. Security and Configuration Review

**[FACT]** No secret values were found in the repository or in the two-commit git history. `.env` does not exist on disk. `.env.example` contains only `TV_DEBUG_PORT` and commented placeholders.

**[FACT]** Config file structure (names only, no values):
- [.env.example](../.env.example): `TV_DEBUG_PORT` plus commented future-key placeholders.
- [config/mcp.json.example](../config/mcp.json.example) and the untracked `.mcp.json`: an MCP server command and a local install path only; no credentials.

**[EVIDENCE]** Risks to note:
- The CDP debug port is an unauthenticated local control channel: any local process can attach to the logged-in TradingView session while it is open. Acceptable for single-user local use; a reason not to route execution through this channel.
- The third-party MCP server runs unaudited Node code with access to that session. Acceptable for read/draw use; revisit before any execution capability exists.
- [.claude/settings.local.json](../.claude/settings.local.json) grants broad Bash permissions (e.g. an arbitrary `python3 -c` pattern). Worth tightening once real scripts exist. This file is local and should remain untracked (§13).

**[FACT]** No execution/order-placement capability exists anywhere in the repository, consistent with the capital-preservation mandate.

---

## 11. Recommended Target Architecture (direction only)

**[EVIDENCE]** The layout in [PROJECT_SPECIFICATION_V1.md](../PROJECT_SPECIFICATION_V1.md) §17 is sound and nothing in the current repository obstructs it. Concrete near-term guidance:

- **Preserve TradingView MCP as a temporary working adapter, not as the permanent system core.** It should sit behind a `MarketDataProvider`-style interface so an exchange/historical-data source can replace or supplement it later without changes downstream. This matches spec §3.3 ("external services should be treated as replaceable adapters; TradingView MCP … should not become the permanent core").
- **Decompose the v3 prompt** into (a) a deterministic feature engine in code, (b) a strategy rule/config file, and (c) a shorter AI interpretation prompt that consumes structured features. Keep the current prompt working until replacements exist.

---

## 12. Incremental Migration Plan (documentation only — not executed here)

Each step preserves the current working prompt workflow. The **first implementation milestone is split into small, independently committable steps:**

- **A. Python project skeleton.** Package layout, `pyproject.toml`/equivalent, and a `tests/` directory, with no behavior change to the existing workflow.
- **B. Saved OHLCV fixture and data contract.** A committed sample OHLCV dataset plus a documented internal data structure. Closed-candle handling is defined here (e.g., exclude the still-forming bar).
- **C. Deterministic feature calculations with tests.** EMA/RSI/MACD/ATR, volume ratios, and swing-structure classification computed in code and unit-tested **against the saved fixture from step B**. Closed-candle handling is tested here before any signal is treated as reproducible.
- **D. TradingView adapter integration only after the calculations work against saved data.** Wire the existing MCP tools in behind the provider interface once C passes on fixtures, so live data is never a prerequisite for correctness testing.

Later milestones (per spec §22, not part of the first milestone): regime/checklist scoring in code, a slimmed interpretation prompt, an analysis journal for reproducibility and bias measurement, and only then historical backtesting with explicit bias guards.

---

## 13. Git Hygiene Recommendation

**[FACT]** The following should **not** be committed, as they are local or machine-specific:
- `.mcp.json` (contains a machine-specific absolute path; the redacted template [config/mcp.json.example](../config/mcp.json.example) is the committed form)
- `.claude/settings.local.json` (local tool permissions)
- `.env` (secrets; already git-ignored, does not exist)
- any other machine-specific configuration

Documentation files (this audit, and the currently-untracked spec and vision documents) are appropriate to commit. Specific per-file recommendations are provided in the chat response accompanying this document.

---

## 14. Open Questions Requiring Verification

- **[UNKNOWN]** Contents, prior existence, and quality of `ta.py` / `ta_w.py` / `ta_4h.py`, referenced only in [.claude/settings.local.json](../.claude/settings.local.json).
- **[UNKNOWN]** Whether the repository's v3 prompt is canonical or a copy maintained elsewhere (§7).
- **[UNKNOWN]** Whether a v2 prompt copy exists anywhere for regression comparison.
- **[UNKNOWN]** The historical depth and data quality of the MCP OHLCV feed, including whether it returns the forming bar — to be verified empirically before milestone B.
- **[UNKNOWN]** Preferred implementation language for the feature engine (not specified in the spec).
- **[UNKNOWN]** Whether v3 has measurably reduced the LONG bias, which cannot be checked until analyses are recorded.
