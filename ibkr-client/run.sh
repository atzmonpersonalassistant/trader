#!/bin/zsh
set -euo pipefail

# Simple local runner for IB Gateway + read-only IBKR client.
# It does not place orders. It opens IB Gateway, waits briefly, prints diagnostics,
# then tries the paper Gateway API port (4002 by default).

SCRIPT_DIR="${0:A:h}"
REPO_DIR="${SCRIPT_DIR:h}"
cd "$REPO_DIR"

HOST="${IBKR_CLIENT_HOST:-127.0.0.1}"
PORT="${IBKR_CLIENT_PORT:-4002}"
CLIENT_ID="${IBKR_CLIENT_ID:-71}"
SYMBOL="${IBKR_CLIENT_SYMBOL:-SPY}"
OUTPUT="${IBKR_CLIENT_OUTPUT:-$SCRIPT_DIR/output/client.json}"
GATEWAY_APP="${IBKR_GATEWAY_APP:-$HOME/Applications/IB Gateway 10.45/IB Gateway 10.45.app}"
WAIT_SECONDS="${IBKR_CLIENT_WAIT_SECONDS:-8}"

mkdir -p "${OUTPUT:h}"

echo "Opening IB Gateway..."
open "$GATEWAY_APP"

echo "Waiting ${WAIT_SECONDS}s for Gateway to start. If login is required, complete it in IB Gateway."
sleep "$WAIT_SECONDS"

echo "\nDiagnostics:"
/opt/homebrew/bin/uv run --with ib-insync python ibkr-client/client.py \
  --host "$HOST" \
  --port "$PORT" \
  --client-id "$CLIENT_ID" \
  --diagnose

echo "\nTrying read-only IBKR client on ${HOST}:${PORT}..."
set +e
/opt/homebrew/bin/uv run --with ib-insync python ibkr-client/client.py \
  --host "$HOST" \
  --port "$PORT" \
  --client-id "$CLIENT_ID" \
  --symbol "$SYMBOL" \
  --output "$OUTPUT"
CODE=$?
set -e

if [[ "$CODE" -ne 0 ]]; then
  echo "\nIBKR client could not connect yet."
  echo "If Gateway is open, log in to Paper Trading and enable API socket on port ${PORT}:"
  echo "Configure -> Settings -> API -> Settings -> Enable ActiveX and Socket Clients"
  echo "Trusted IP / localhost should include 127.0.0.1"
  exit "$CODE"
fi

echo "\nSuccess. Output written to: $OUTPUT"
