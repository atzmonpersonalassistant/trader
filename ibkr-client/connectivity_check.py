#!/usr/bin/env python3
"""Read-only IBKR connectivity check.

Connects to a local IB Gateway API socket, reads basic account metadata and
one market-data snapshot, then disconnects. This script intentionally contains
no order placement, modification, or cancellation logic.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ib_insync import IB, Stock


def safe_float(value):
    try:
        if value is None:
            return None
        x = float(value)
        if x != x:  # NaN
            return None
        return x
    except Exception:
        return None


def account_summary(ib: IB) -> list[dict]:
    rows = []
    for item in ib.accountSummary():
        rows.append({
            "account": item.account,
            "tag": item.tag,
            "value": item.value,
            "currency": item.currency,
        })
    return rows


def positions(ib: IB) -> list[dict]:
    rows = []
    for p in ib.positions():
        rows.append({
            "account": p.account,
            "symbol": p.contract.symbol,
            "secType": p.contract.secType,
            "exchange": p.contract.exchange,
            "currency": p.contract.currency,
            "position": safe_float(p.position),
            "avgCost": safe_float(p.avgCost),
        })
    return rows


def market_snapshot(ib: IB, symbol: str, exchange: str, currency: str) -> dict:
    contract = Stock(symbol, exchange, currency)
    ib.qualifyContracts(contract)
    ticker = ib.reqMktData(contract, "", snapshot=True, regulatorySnapshot=False)
    ib.sleep(3)
    return {
        "symbol": symbol,
        "exchange": exchange,
        "currency": currency,
        "bid": safe_float(ticker.bid),
        "ask": safe_float(ticker.ask),
        "last": safe_float(ticker.last),
        "close": safe_float(ticker.close),
        "marketPrice": safe_float(ticker.marketPrice()),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only IBKR connectivity check")
    p.add_argument("--host", default="127.0.0.1", help="IB Gateway API host")
    p.add_argument("--port", type=int, default=4002, help="IB Gateway API port; paper Gateway commonly 4002")
    p.add_argument("--client-id", type=int, default=71, help="API client id")
    p.add_argument("--symbol", default="SPY", help="Stock symbol for market data snapshot")
    p.add_argument("--exchange", default="SMART", help="Exchange routing for stock contract")
    p.add_argument("--currency", default="USD", help="Contract currency")
    p.add_argument("--output", help="Optional JSON output path")
    p.add_argument("--timeout", type=float, default=10, help="Connection timeout seconds")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    ib = IB()
    result = {
        "timestamp": datetime.now(ZoneInfo("Asia/Jerusalem")).isoformat(),
        "host": args.host,
        "port": args.port,
        "clientId": args.client_id,
        "connected": False,
        "managedAccounts": [],
        "accountSummary": [],
        "positions": [],
        "marketSnapshot": {},
        "error": "",
    }
    try:
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=args.timeout, readonly=True)
        result["connected"] = ib.isConnected()
        result["serverVersion"] = ib.client.serverVersion()
        result["managedAccounts"] = ib.managedAccounts()
        result["accountSummary"] = account_summary(ib)
        result["positions"] = positions(ib)
        result["marketSnapshot"] = market_snapshot(ib, args.symbol.upper(), args.exchange, args.currency)
    except Exception as e:
        result["error"] = str(e)
    finally:
        if ib.isConnected():
            ib.disconnect()

    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0 if result["connected"] and not result["error"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
