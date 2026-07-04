# Setup

## TradingView MCP

The TradingView MCP server (https://github.com/tradesdontlie/tradingview-mcp) is installed
separately at `~/mcp-servers/tradingview-mcp` (not part of this repo — it's third-party code).

Global Claude Code MCP config lives at `~/.claude/.mcp.json` and points to that install path.
See `config/mcp.json.example` in this repo for the shape of that config (with secrets/paths
templated out).

## Launching TradingView with the debug port

```bash
./scripts/tradingview-launcher.sh        # defaults to port 9222
./scripts/tradingview-launcher.sh 9222   # explicit port
```

TradingView must be fully quit (Cmd+Q) before running this — if it's already running without
the debug flag, relaunching it here won't add the flag.

## Verifying the connection

Once TradingView is up with the debug port open and Claude Code has been restarted (MCP servers
only load at startup), ask Claude to run `tv_health_check`. Expected result:

```json
{ "success": true, "cdp_connected": true, "chart_symbol": "...", "api_available": true }
```

## Secrets

Copy `.env.example` to `.env` and fill in real values. `.env` is git-ignored and must stay on
this Mac only — never commit it.
