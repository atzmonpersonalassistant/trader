# IBKR Client

Minimal Interactive Brokers client utilities for local connectivity checks and market/account data access.

This project is intentionally **read-only** for now. It does not place, modify, or cancel orders.

## Intended setup

Use **IB Gateway**, not TWS, for automation-oriented access.

Recommended first connection:

- Environment: **Paper Trading**
- Host: `127.0.0.1`
- Common paper ports:
  - IB Gateway paper: `4002`
  - TWS paper: `7497`
- Keep API access restricted to localhost at first.

## Files

- `connectivity_check.py` — connects to IB Gateway/TWS and prints basic account and quote data.
- `output/` — optional local outputs/logs.

## Install/run

From repo root:

```bash
uv run --with ib-insync python ibkr-client/connectivity_check.py --host 127.0.0.1 --port 4002
```

If using TWS paper instead:

```bash
uv run --with ib-insync python ibkr-client/connectivity_check.py --host 127.0.0.1 --port 7497
```

Test a different symbol:

```bash
uv run --with ib-insync python ibkr-client/connectivity_check.py --symbol AAPL
```

## Outputs

By default this script prints JSON to stdout only.

If `--output ibkr-client/output/connectivity.json` is passed, it also writes the result there.

Runtime outputs are ignored by git except for `output/README.md`.

## What the check reads

The connectivity check attempts to read:

- server version / connection status;
- managed accounts;
- account summary;
- positions;
- one market data snapshot, default `SPY`.

## Safety guardrails

- No order-placement functions are implemented.
- Start with Paper Trading.
- Do not commit credentials, account numbers, tokens, or screenshots containing private account data.
- Live trading integration requires explicit separate approval.

Information only, not investment advice.
