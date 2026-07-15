#!/usr/bin/env bash
set -euo pipefail
export TZ=Asia/Jerusalem
export PYTHONDONTWRITEBYTECODE=1
export QC_FULL_CHUNK_SIZE="${QC_FULL_CHUNK_SIZE:-25}"
export QC_FULL_PARALLEL="${QC_FULL_PARALLEL:-1}"
export QC_FULL_CHUNK_DELAY_SECONDS="${QC_FULL_CHUNK_DELAY_SECONDS:-45}"
export QC_STAGE2_BACKTEST_ATTEMPTS="${QC_STAGE2_BACKTEST_ATTEMPTS:-4}"
export QC_STAGE2_BACKTEST_RETRY_BASE_SECONDS="${QC_STAGE2_BACKTEST_RETRY_BASE_SECONDS:-60}"
export QC_MULTIYEAR_YEARS="${QC_MULTIYEAR_YEARS:-8}"
LOG_DIR=/agents/research/logs/earnings-qc-options-scan
mkdir -p "$LOG_DIR"
chown -R agent-research:agent-research "$LOG_DIR" 2>/dev/null || true
LOG="$LOG_DIR/daily-$(date +%Y%m%d).log"
# Full skill-backed QC-only scanner. Calendar may come from Nasdaq; option data,
# liquidity/Greeks, and historical validation must be QC/LEAN-only.
exec sudo -n -u agent-research env \
  TZ="$TZ" \
  PYTHONDONTWRITEBYTECODE="$PYTHONDONTWRITEBYTECODE" \
  QC_FULL_CHUNK_SIZE="$QC_FULL_CHUNK_SIZE" \
  QC_FULL_PARALLEL="$QC_FULL_PARALLEL" \
  QC_FULL_CHUNK_DELAY_SECONDS="$QC_FULL_CHUNK_DELAY_SECONDS" \
  QC_STAGE2_BACKTEST_ATTEMPTS="$QC_STAGE2_BACKTEST_ATTEMPTS" \
  QC_STAGE2_BACKTEST_RETRY_BASE_SECONDS="$QC_STAGE2_BACKTEST_RETRY_BASE_SECONDS" \
  QC_MULTIYEAR_YEARS="$QC_MULTIYEAR_YEARS" \
  /agents/research/bin/earnings-qc-research run --chunk-size "$QC_FULL_CHUNK_SIZE" --parallel "$QC_FULL_PARALLEL" --end-to-end \
  >> "$LOG" 2>&1
