#!/usr/bin/env python3
"""Read-only IBKR Gateway client.

Connects to a local IB Gateway API socket, reads basic account metadata and
one market-data snapshot, then disconnects. This script intentionally contains
no order placement, modification, or cancellation logic.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ib_insync import IB, Stock

COMMON_GATEWAY_PORTS = [4002, 4001]
DEFAULT_GATEWAY_APP = Path.home() / "Applications" / "IB Gateway 10.45" / "IB Gateway 10.45.app"


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


def tcp_probe(host: str, port: int, timeout: float = 1.0) -> dict:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"port": port, "listening": True, "error": ""}
    except Exception as e:
        return {"port": port, "listening": False, "error": str(e)}


def gateway_processes() -> list[str]:
    try:
        out = subprocess.run(["ps", "-axo", "pid=,command="], text=True, capture_output=True, timeout=3)
        rows = []
        for line in out.stdout.splitlines():
            stripped = line.strip()
            parts = stripped.split(maxsplit=1)
            command = parts[1] if len(parts) == 2 else ""
            if command.endswith(".app/Contents/MacOS/JavaApplicationStub") and "IB Gateway" in command:
                rows.append(stripped)
        return rows
    except Exception:
        return []


def start_gateway(app_path: Path) -> bool:
    if not app_path.exists():
        return False
    subprocess.run(["open", str(app_path)], check=False)
    return True


def diagnostics(host: str, ports: list[int], gateway_app: Path) -> dict:
    return {
        "gatewayApp": str(gateway_app),
        "gatewayAppExists": gateway_app.exists(),
        "gatewayProcesses": gateway_processes(),
        "ports": [tcp_probe(host, p) for p in ports],
        "notes": [
            "IB Gateway must be running and logged in before the API socket listens.",
            "Paper IB Gateway commonly listens on 4002; live commonly listens on 4001.",
            "TWS is intentionally out of scope for this repo.",
        ],
    }


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
    p = argparse.ArgumentParser(description="Read-only IBKR Gateway client")
    p.add_argument("--host", default="127.0.0.1", help="IB Gateway API host")
    p.add_argument("--port", type=int, default=4002, help="IB Gateway API port; paper Gateway commonly 4002")
    p.add_argument("--client-id", type=int, default=71, help="API client id")
    p.add_argument("--symbol", default="SPY", help="Stock symbol for market data snapshot")
    p.add_argument("--exchange", default="SMART", help="Exchange routing for stock contract")
    p.add_argument("--currency", default="USD", help="Contract currency")
    p.add_argument("--output", help="Optional JSON output path")
    p.add_argument("--timeout", type=float, default=10, help="Connection timeout seconds")
    p.add_argument("--diagnose", action="store_true", help="Only print local Gateway/process/port diagnostics")
    p.add_argument("--start-gateway", action="store_true", help="Open the installed IB Gateway app before connecting")
    p.add_argument("--gateway-app", default=str(DEFAULT_GATEWAY_APP), help="Path to IB Gateway .app for --start-gateway")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    gateway_app = Path(args.gateway_app).expanduser()
    if args.start_gateway:
        start_gateway(gateway_app)
    diag = diagnostics(args.host, sorted(set(COMMON_GATEWAY_PORTS + [args.port])), gateway_app)
    result = {
        "timestamp": datetime.now(ZoneInfo("Asia/Jerusalem")).isoformat(),
        "host": args.host,
        "port": args.port,
        "clientId": args.client_id,
        "connected": False,
        "diagnostics": diag,
        "managedAccounts": [],
        "accountSummary": [],
        "positions": [],
        "marketSnapshot": {},
        "error": "",
        "nextStep": "",
    }
    if args.diagnose:
        text = json.dumps(result, ensure_ascii=False, indent=2)
        print(text)
        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text + "\n", encoding="utf-8")
        return 0

    if not any(p["port"] == args.port and p["listening"] for p in diag["ports"]):
        result["error"] = f"IB Gateway API port is not listening on {args.host}:{args.port}"
        result["nextStep"] = "Start/log in to IB Gateway, choose Paper Trading, and enable/configure the API socket."
    else:
        ib = IB()
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
            result["nextStep"] = "Gateway socket was reachable but API login/read failed; check Gateway API settings and login state."
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
