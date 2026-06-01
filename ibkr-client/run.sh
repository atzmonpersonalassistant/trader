#!/bin/zsh
set -euo pipefail

# Simple local runner for IB Gateway + read-only IBKR client.
# It does not place orders. It opens IB Gateway, waits briefly, prints diagnostics,
# auto-detects the local Gateway API port, then reads account/market data.

SCRIPT_DIR="${0:A:h}"
REPO_DIR="${SCRIPT_DIR:h}"
cd "$REPO_DIR"

HOST="${IBKR_CLIENT_HOST:-127.0.0.1}"
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

# Prefer paper Gateway port 4002 when available, but auto-fallback to 4001 if
# that is the only local Gateway API socket listening. Users can override with
# IBKR_CLIENT_PORT=4002/4001.
if [[ -n "${IBKR_CLIENT_PORT:-}" ]]; then
  PORT="$IBKR_CLIENT_PORT"
else
  PORT=$(/usr/bin/python3 - <<'PY'
import socket
host = '127.0.0.1'
for port in (4002, 4001):
    try:
        with socket.create_connection((host, port), timeout=0.5):
            print(port)
            raise SystemExit(0)
    except OSError:
        pass
print(4002)
PY
)
fi

echo "\nDiagnostics for ${HOST}:${PORT}:"
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
  echo "If Gateway is open, log in and enable API socket:"
  echo "Configure -> Settings -> API -> Settings -> Enable ActiveX and Socket Clients"
  echo "Trusted IP / localhost should include 127.0.0.1"
  echo "If needed, force a port with: IBKR_CLIENT_PORT=4001 ibkr-client/run.sh"
  exit "$CODE"
fi

echo "\nSuccess. Output written to: $OUTPUT"
