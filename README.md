# dovydas-trading-system

Personal trading automation workspace: config, scripts, docs, and prompts for working with
TradingView Desktop via Claude Code (through the [tradingview-mcp](https://github.com/tradesdontlie/tradingview-mcp)
MCP bridge over Chrome DevTools Protocol).

All code and prompts here are public. API keys, tokens, and other secrets never live in this
repo — see `.env.example` and `docs/SETUP.md`.

## Structure

- `config/` — non-secret config templates (e.g. `mcp.json.example`)
- `scripts/` — helper scripts, e.g. `tradingview-launcher.sh`
- `docs/` — setup and usage docs
- `prompts/` — reusable prompt snippets for chart analysis / Pine Script work

## Product documents

Living operational documents, updated as work moves:

- [FMITS_PRODUCT_BACKLOG.md](FMITS_PRODUCT_BACKLOG.md) — what is being built now, next and later
- [FMITS_PRODUCT_CHANGELOG.md](FMITS_PRODUCT_CHANGELOG.md) — what the system can actually do, and since when

Architecture, decisions and milestone records live in [docs/](docs/README.md); dated analyses live in
[reports/](reports/README.md).

## Quick start

See [docs/SETUP.md](docs/SETUP.md).
