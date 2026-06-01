#!/bin/zsh
set -euo pipefail

# launchd/cron-friendly wrapper. The scanner is rolling/dynamic, but we still
# gate routine runs to weekdays and the normal Israel afternoon/evening window.
HOUR=$(date +%H)
MIN=$(date +%M)
DOW=$(date +%u)  # 1=Mon ... 7=Sun

if [[ "${EARNINGS_VOL_RADAR_IGNORE_WRAPPER_WINDOW:-0}" != "1" ]]; then
  if [[ "$DOW" -lt 1 || "$DOW" -gt 5 ]]; then
    exit 0
  fi

  if [[ "$MIN" != "05" && "$MIN" != "35" ]]; then
    exit 0
  fi

  if [[ "$HOUR" -lt 16 || "$HOUR" -gt 22 ]]; then
    exit 0
  fi
fi

SCRIPT_DIR="${0:A:h}"
REPO_DIR="${SCRIPT_DIR:h}"
cd "$REPO_DIR"

LOG_FILE="${EARNINGS_VOL_RADAR_LOG_FILE:-$SCRIPT_DIR/output/earnings_volatility_radar.log}"
mkdir -p "${LOG_FILE:h}"

/opt/homebrew/bin/uv run --with yfinance --with pandas \
  python earnings-volatility-radar/scan.py "$@" >> "$LOG_FILE" 2>&1
