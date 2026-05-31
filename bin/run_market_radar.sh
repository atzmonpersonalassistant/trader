#!/bin/zsh
set -euo pipefail

# Same cadence as Options Radar: launchd can wake every 5 minutes;
# the heavy script runs only at :05/:35 during the configured local window.
HOUR=$(date +%H)
MIN=$(date +%M)
DOW=$(date +%u)  # 1=Mon ... 7=Sun

if [[ "${MARKET_RADAR_IGNORE_WRAPPER_WINDOW:-0}" != "1" ]]; then
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

LOG_FILE="${MARKET_RADAR_LOG_FILE:-$REPO_DIR/output/market_radar_cron.log}"
mkdir -p "${LOG_FILE:h}"

/opt/homebrew/bin/uv run python scripts/market_radar_scan.py "$@" >> "$LOG_FILE" 2>&1
