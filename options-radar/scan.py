#!/usr/bin/env python3
"""Scan option chains for low-priced contracts.

This script is intentionally self-contained and does not depend on Google Sheets.
It reads a local universe CSV, scans option chains with yfinance, writes local
CSV/JSON outputs, and optionally prints/sends a concise summary.
"""

import argparse
import csv
import json
import math
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_EXPIRIES = ["2026-06-18", "2026-07-17"]
DEFAULT_MAX_PRICE = 0.30
DEFAULT_MAX_WORKERS = 8
DEFAULT_UNIVERSE = Path("options-radar/universe.csv")
DEFAULT_OUTPUT_DIR = Path("options-radar/output")
HEADER = [
    "Scan timestamp", "Ticker", "Company / Theme", "Category", "Underlying price",
    "Expiry", "Type", "Strike", "Bid", "Ask", "Mid", "Volume", "Open interest",
    "Spread note", "Risk / relevance note"
]


def market_window_ok(now=None, enforce=True):
    if not enforce:
        return True, datetime.now(ZoneInfo("America/New_York"))
    now = now or datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False, now
    return time(9, 0) <= now.time() <= time(16, 0), now


def load_universe(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Universe file not found: {path}. Copy options-radar/universe.example.csv to options-radar/universe.csv "
            "or pass --universe /path/to/file.csv"
        )

    rows = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            use = str(r.get("Use in scanner", "TRUE")).strip().upper()
            ticker = str(r.get("Ticker", "")).strip().upper()
            if ticker and use not in {"FALSE", "0", "NO", "N"}:
                rows.append({
                    "ticker": ticker,
                    "theme": str(r.get("Company / Theme", "")).strip(),
                    "category": str(r.get("Category", "")).strip(),
                    "notes": str(r.get("Notes", "")).strip(),
                })

    seen, out_rows = set(), []
    for row in rows:
        if row["ticker"] not in seen:
            seen.add(row["ticker"])
            out_rows.append(row)
    return out_rows


def safe_float(x):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return None
        return float(x)
    except Exception:
        return None


def scan_ticker(row, target_expiries, max_price):
    import yfinance as yf

    ticker = row["ticker"]
    results = []
    try:
        t = yf.Ticker(ticker)
        underlying = None
        try:
            fi = t.fast_info
            underlying = safe_float(fi.get("last_price") or fi.get("lastPrice"))
        except Exception:
            pass
        if underlying is None:
            try:
                hist = t.history(period="1d", interval="1m", prepost=True)
                if not hist.empty:
                    underlying = safe_float(hist["Close"].dropna().iloc[-1])
            except Exception:
                pass

        try:
            expiries = list(t.options or [])
        except Exception:
            expiries = []

        scan_exp = [e for e in target_expiries if e in expiries]
        # If an exact requested July expiry is absent, pick a nearby mid-July expiry.
        if "2026-07-17" in target_expiries and "2026-07-17" not in scan_exp:
            for e in expiries:
                if e.startswith("2026-07-"):
                    day = int(e[-2:])
                    if 10 <= day <= 24:
                        scan_exp.append(e)
                        break

        for exp in scan_exp:
            try:
                ch = t.option_chain(exp)
            except Exception:
                continue
            for opt_type, df in [("Call", ch.calls), ("Put", ch.puts)]:
                if df is None or df.empty:
                    continue
                for _, o in df.iterrows():
                    bid = safe_float(o.get("bid"))
                    ask = safe_float(o.get("ask"))
                    if bid is None or ask is None:
                        continue
                    if bid == 0 and ask == 0:
                        continue
                    mid = (bid + ask) / 2.0
                    ok = (ask > 0 and ask <= max_price) or (mid <= max_price and ask > 0)
                    if not ok:
                        continue
                    strike = safe_float(o.get("strike"))
                    vol = o.get("volume")
                    oi = o.get("openInterest")
                    spread_note = ""
                    if mid > 0 and (ask - bid) / mid > 1.0:
                        spread_note = "Wide spread"
                    elif bid == 0:
                        spread_note = "Bid 0 / speculative"
                    risk = row.get("notes") or row.get("category") or "High-risk low-priced option"
                    results.append({
                        "timestamp": "",
                        "ticker": ticker,
                        "theme": row.get("theme", ""),
                        "category": row.get("category", ""),
                        "underlying": underlying,
                        "expiry": exp,
                        "type": opt_type,
                        "strike": strike,
                        "bid": bid,
                        "ask": ask,
                        "mid": mid,
                        "volume": "" if vol is None or (isinstance(vol, float) and math.isnan(vol)) else int(vol),
                        "oi": "" if oi is None or (isinstance(oi, float) and math.isnan(oi)) else int(oi),
                        "spread": spread_note,
                        "risk": risk,
                    })
    except Exception:
        pass
    return results


def fmt(x):
    if x == "" or x is None:
        return ""
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        return f"{x:.2f}"
    return str(x)


def result_row(ts, r):
    return [
        ts, r["ticker"], r["theme"], r["category"], fmt(r["underlying"]),
        r["expiry"], r["type"], fmt(r["strike"]), fmt(r["bid"]), fmt(r["ask"]),
        fmt(r["mid"]), r["volume"], r["oi"], r["spread"], r["risk"]
    ]


def write_outputs(rows, output_dir, basename="options-radar"):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / f"{basename}.csv"
    json_path = output_dir / f"{basename}.json"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerows(rows)

    payload = [dict(zip(HEADER, row)) for row in rows]
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def send_whatsapp(message, target):
    if not target or not message or message.strip() == "NO_REPLY":
        return
    cmd = ["wacli", "send", "text", "--to", target, "--message", message, "--json"]
    if Path("/opt/homebrew/bin/wacli").exists():
        cmd[0] = "/opt/homebrew/bin/wacli"
    subprocess.run(cmd, check=True, text=True, capture_output=True, timeout=120)


def build_summary(ts, all_results, csv_path, max_price, target_expiries, top_n):
    if not all_results:
        return (
            f"Options Radar scan — {ts}\n"
            f"No option candidates found under ${max_price:.2f}.\n"
            f"Expiries: {', '.join(target_expiries)}.\n"
            f"Output: {csv_path}\n"
            "Information only, not investment advice."
        )

    top = all_results[:top_n]
    lines = [
        f"Options Radar scan — {ts}",
        f"Filter: bid/ask only, not last trade. Max price: ${max_price:.2f}. Expiries: {', '.join(target_expiries)}.",
        "",
    ]
    for i, r in enumerate(top, 1):
        vol = r["volume"] if r.get("volume") != "" else "N/A"
        oi = r["oi"] if r.get("oi") != "" else "N/A"
        spread = r.get("spread") or "not flagged"
        category = r.get("category") or r.get("risk") or "high-risk option"
        lines.append(
            f"{i}) {r['ticker']} — {r['type']} ${fmt(r['strike'])}\n"
            f"Expiry: {r['expiry']}\n"
            f"Underlying: ${fmt(r['underlying'])}\n"
            f"Bid / Ask / Mid: {fmt(r['bid'])} / {fmt(r['ask'])} / {fmt(r['mid'])}\n"
            f"Volume / OI: {vol} / {oi}\n"
            f"Spread: {spread}\n"
            f"Theme/Risk: {category}\n"
        )
    if len(all_results) > len(top):
        lines.append(f"More candidates in {csv_path}: {len(all_results) - len(top)} additional rows.")
    lines.append(f"Output: {csv_path}")
    lines.append("Information only, not investment advice.")
    return "\n".join(lines)


def parse_args():
    p = argparse.ArgumentParser(description="Scan low-priced options for a local ticker universe.")
    p.add_argument("--universe", default=os.getenv("OPTIONS_RADAR_UNIVERSE", str(DEFAULT_UNIVERSE)))
    p.add_argument("--output-dir", default=os.getenv("OPTIONS_RADAR_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
    p.add_argument("--expiry", action="append", dest="expiries", help="Target expiry YYYY-MM-DD. Repeatable.")
    p.add_argument("--max-price", type=float, default=float(os.getenv("OPTIONS_RADAR_MAX_PRICE", DEFAULT_MAX_PRICE)))
    p.add_argument("--max-workers", type=int, default=int(os.getenv("OPTIONS_RADAR_MAX_WORKERS", DEFAULT_MAX_WORKERS)))
    p.add_argument("--top", type=int, default=int(os.getenv("OPTIONS_RADAR_TOP", 12)))
    p.add_argument("--send-whatsapp-to", default=os.getenv("OPTIONS_RADAR_WHATSAPP_TARGET", ""))
    p.add_argument("--ignore-market-window", action="store_true", help="Run even outside regular US market hours.")
    return p.parse_args()


def main():
    args = parse_args()
    target_expiries = args.expiries or DEFAULT_EXPIRIES
    ok, _ = market_window_ok(enforce=not args.ignore_market_window)
    il_now = datetime.now(ZoneInfo("Asia/Jerusalem"))
    ts = il_now.strftime("%Y-%m-%d %H:%M") + " Israel"
    if not ok:
        print("NO_REPLY")
        return

    universe = load_universe(args.universe)
    all_results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futs = [ex.submit(scan_ticker, r, target_expiries, args.max_price) for r in universe]
        for fut in as_completed(futs, timeout=240):
            try:
                all_results.extend(fut.result())
            except Exception:
                pass

    def score(r):
        bid = r.get("bid") or 0
        vol = r.get("volume") or 0
        oi = r.get("oi") or 0
        mid = r.get("mid") or 0
        ask = r.get("ask") or 0
        spread_pct = ((ask - bid) / mid) if mid else 99
        return (-int(bid > 0), -int(vol or 0), -int(oi or 0), spread_pct, r["ticker"], r["expiry"], r["type"], r.get("strike") or 0)

    all_results.sort(key=score)
    rows = [result_row(ts, r) for r in all_results[:120]]
    csv_path, _json_path = write_outputs(rows, args.output_dir)
    summary = build_summary(ts, all_results, csv_path, args.max_price, target_expiries, args.top)
    print(summary)
    send_whatsapp(summary, args.send_whatsapp_to)


if __name__ == "__main__":
    main()
