# IBKR Client

Minimal Interactive Brokers Gateway client utility for local IB Gateway account and market data access.

This project is intentionally **read-only** for now. It does not place, modify, or cancel orders.

## Intended setup

Use **IB Gateway only** for automation-oriented access. TWS is intentionally out of scope for this project.

Recommended first connection:

- Environment: **Paper Trading**
- Host: `127.0.0.1`
- Common paper port:
  - IB Gateway paper: `4002`
- Keep API access restricted to localhost at first.

## Files

- `client.py` — connects to IB Gateway and prints basic account and quote data.
- `output/` — optional local outputs/logs.


## One-command local run

From repo root:

```bash
ibkr-client/run.sh
```

What it does:

1. opens the installed IB Gateway app;
2. waits a few seconds so you can complete login if needed;
3. prints diagnostics;
4. tries the read-only client against Paper Gateway port `4002`;
5. writes JSON to `ibkr-client/output/client.json`.

Useful overrides:

```bash
IBKR_CLIENT_PORT=4002 IBKR_CLIENT_SYMBOL=AAPL ibkr-client/run.sh
```

## Install/run

From repo root:

```bash
uv run --with ib-insync python ibkr-client/client.py --host 127.0.0.1 --port 4002
```

Local diagnostics only, without connecting to the API:

```bash
uv run --with ib-insync python ibkr-client/client.py --diagnose
```

Open the installed Gateway app first, then try connecting:

```bash
uv run --with ib-insync python ibkr-client/client.py --start-gateway --host 127.0.0.1 --port 4002
```

Test a different symbol:

```bash
uv run --with ib-insync python ibkr-client/client.py --symbol AAPL
```

## Outputs

By default this script prints JSON to stdout only. The JSON includes local diagnostics: whether the Gateway app exists, matching Gateway processes, and whether common Gateway API ports are listening.

If `--output ibkr-client/output/client.json` is passed, it also writes the result there.

Runtime outputs are ignored by git except for `output/README.md`.


## Current local status note

On this Mac, IB Gateway 10.45 was installed under:

```text
~/Applications/IB Gateway 10.45/IB Gateway 10.45.app
```

The client can open that app with `--start-gateway`, but the API socket will not listen until Gateway is logged in and API access is enabled/configured inside Gateway.

## What the client reads

The client attempts to read:

- local Gateway process/port diagnostics;
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
