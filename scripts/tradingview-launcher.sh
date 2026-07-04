#!/usr/bin/env bash
#
# tradingview-launcher.sh
# Launches TradingView Desktop on macOS with the Chrome DevTools Protocol
# debug port open, so the tradingview-mcp server can connect to it.
#
set -euo pipefail

TV_PATH="/Applications/TradingView.app/Contents/MacOS/TradingView"
DEBUG_PORT="${1:-9222}"

if [ ! -x "$TV_PATH" ]; then
  echo "TradingView Desktop not found at: $TV_PATH"
  echo "Install it from https://www.tradingview.com/desktop/ and try again."
  exit 1
fi

if pgrep -f "TradingView.app/Contents/MacOS/TradingView" > /dev/null 2>&1; then
  echo "TradingView is already running. Quit it fully first (Cmd+Q), then re-run this script,"
  echo "otherwise it will relaunch without the debug port enabled."
  exit 1
fi

echo "Launching TradingView with remote debugging on port $DEBUG_PORT..."
"$TV_PATH" --remote-debugging-port="$DEBUG_PORT" &

echo "Launched (pid $!). Give it a few seconds to fully load, then verify with tv_health_check."
