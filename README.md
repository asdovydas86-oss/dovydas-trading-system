# dovydas-trading-system

**FMITS** (Financial Market Intelligence & Trading System) — a personal, AI-assisted market
decision-support system built as a deterministic Python pipeline (`src/fmis/`), plus the TradingView
Desktop automation workspace (config, scripts, prompts) it grew out of and still uses via Claude Code
(through the [tradingview-mcp](https://github.com/tradesdontlie/tradingview-mcp) MCP bridge over Chrome
DevTools Protocol).

All code and prompts here are public. API keys, tokens, and other secrets never live in this
repo — see `.env.example` and `docs/SETUP.md`.

## Structure

- `src/fmis/` — the FMITS Python package: deterministic market-analysis engines, application layer and
  CLI (`fmits facts|mtf|regime|swing|daily`)
- `tests/` — the pytest suite (3,900+ tests) and fixtures
- `config/` — non-secret config templates (e.g. `mcp.json.example`)
- `scripts/` — helper scripts, e.g. `tradingview-launcher.sh`
- `docs/` — architecture, decision records and usage docs
- `reports/` — dated, point-in-time operational reports (audits, design/implementation records)
- `prompts/` — reusable prompt snippets for chart analysis / Pine Script work

## AI Session Entry

Every new AI session starts from
[`docs/AI_HANDOFF/START_HERE_FOR_AI.md`](docs/AI_HANDOFF/START_HERE_FOR_AI.md) — the single entry
point for engineering rules, current status, architecture and navigation. Read only that document
first; it links to everything else on demand.

## Product documents

Living operational documents, updated as work moves:

- [FMITS_PRODUCT_BACKLOG.md](FMITS_PRODUCT_BACKLOG.md) — what is being built now, next and later
- [FMITS_PRODUCT_CHANGELOG.md](FMITS_PRODUCT_CHANGELOG.md) — what the system can actually do, and since when

Architecture, decisions and milestone records live in [docs/](docs/README.md); dated analyses live in
[reports/](reports/README.md).

## Quick start

See [docs/SETUP.md](docs/SETUP.md).

## Opening the dashboard

The FMITS Operator Dashboard is the system's only visual surface: a local, read-only page over the
market pulse, macro context, the swing decision workspace, the recorded portfolio, paper trades,
performance statistics and the state of every data source a refresh touched.

```
source .venv/bin/activate     # `fmits` lives in the virtualenv, not on $PATH
fmits dashboard               # or, without activating: uv run fmits dashboard
```

It prints the address, then performs its first refresh — **four live engine reads, 30-45 s** — and
prints the URL only once a request to it can be answered:

```
FMITS Operator Dashboard — read only
  address  http://127.0.0.1:8787/
  reading  the first refresh performs four live engine reads and takes 30-45 s. …
  open     http://127.0.0.1:8787/
  stop     Ctrl-C
```

**Open the `open` line, not the `address` line.** Binds loopback only; binding anywhere else needs
`--allow-public`, because the page states your positions, open risk and account figures. Answers
`GET` and `HEAD` only, and writes nothing. `--port 0` picks a free port if 8787 is taken.
