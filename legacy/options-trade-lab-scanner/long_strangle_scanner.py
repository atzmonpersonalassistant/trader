#!/usr/bin/env python3
"""
Long Strangle Scanner

Finds candidate long strangles where realized stock volatility is high but the
option package is not too expensive relative to spot.

Data source: yfinance/Yahoo. Quotes can be delayed/stale. Always verify live
bid/ask, volume/OI, and use limit orders in the broker before trading.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from io import StringIO
from typing import Iterable, Optional

import pandas as pd
import requests
import yfinance as yf

DEFAULT_WATCHLIST = """
DDOG NET ARM AMD SOFI HOOD RBLX HIMS SMCI GME MSTR RKLB QBTS RGTI IONQ QUBT
SOUN BBAI AI PLTR RDDT AFRM UPST CVNA DKNG LUNR ASTS JOBY ACHR SERV TEM MARA
RIOT CLSK BITF COIN WULF HUT BTBT WOLF MU NVDA TSLA AVGO MRVL INTC BILI BIDU
BABA JD PDD FUTU TIGR NIO XPEV LI OPEN CHPT LCID RIVN FUBO SNAP PINS U ROKU
TOST CRWD ZS MDB SNOW WIX DT AKA AEYE REZI WMT TGT HD LOW DE NTES VIPS GME AMC
BYND TLRY CGC
""".split()

THEMES = {
    "quantum": {"QBTS", "RGTI", "IONQ", "QUBT"},
    "ai": {"SOUN", "BBAI", "AI", "PLTR", "NVDA", "AMD", "SMCI", "ARM"},
    "crypto": {"MSTR", "COIN", "MARA", "RIOT", "CLSK", "HUT", "WULF", "BTBT", "BITF"},
    "semis": {"NVDA", "AMD", "ARM", "SMCI", "MU", "MRVL", "AVGO", "INTC", "WOLF"},
    "consumer_high_beta": {"SOFI", "HOOD", "RBLX", "CVNA", "UPST", "AFRM", "DKNG", "RDDT"},
}

WINDOWS = {
    # These labels are useful for manual runs. Preferred production mode is
    # --expiry-mode next_fridays, which scans each of the next N Friday expiries.
    "weekly": (7, 10, 4.0),
    "short_swing": (10, 21, 5.0),
    "monthly": (21, 35, 7.0),
    "mid_swing": (35, 45, 8.5),
    "longer_swing": (45, 65, 10.0),
}


@dataclass
class Candidate:
    symbol: str
    theme: str
    window: str
    expiry: str
    dte: int
    spot: float
    hv20_pct: float
    hv_used_pct: float
    hv_window: int
    avg_abs_20d_pct: float
    avg_abs_used_pct: float
    day_change_pct: float
    move_5d_pct: float
    move_20d_pct: float
    atr14_pct: float
    otm_pct: int
    call_contract: str
    call_strike: float
    call_bid: float
    call_ask: float
    call_mid: float
    call_volume: float
    call_oi: float
    put_contract: str
    put_strike: float
    put_bid: float
    put_ask: float
    put_mid: float
    put_volume: float
    put_oi: float
    total_cost: float
    cost_pct: float
    breakeven_up: float
    breakeven_down: float
    breakeven_up_dist_pct: float
    breakeven_down_dist_pct: float
    max_spread_pct: float
    leg_volume: float
    leg_oi: float
    value_score: float
    trigger_score: float
    final_score: float
    trigger_reason: str
    warnings: str


def pct(a: float, b: float) -> float:
    return (a / b - 1.0) * 100 if b else 0.0


def mid_price(row: pd.Series) -> float:
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    last = float(row.get("lastPrice", 0) or 0)
    if bid > 0 and ask > 0:
        return (bid + ask) / 2
    if ask > 0:
        return ask
    return last


def spread_pct(row: pd.Series) -> float:
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        return (ask - bid) / mid * 100 if mid else 999.0
    return 999.0


def parse_option_dates(options: Iterable[str]) -> list[date]:
    dates = []
    for opt in options:
        try:
            dates.append(datetime.strptime(opt, "%Y-%m-%d").date())
        except ValueError:
            continue
    return dates


def nearest_expiry(options: Iterable[str], min_dte: int, max_dte: int) -> Optional[date]:
    today = date.today()
    dates = []
    for d in parse_option_dates(options):
        dte = (d - today).days
        if min_dte <= dte <= max_dte:
            dates.append(d)
    if not dates:
        return None
    target = (min_dte + max_dte) / 2
    return min(dates, key=lambda d: abs((d - today).days - target))


def next_friday_expiries(options: Iterable[str], count: int = 8, min_dte: int = 1) -> list[date]:
    """Return the next available Friday option expiries for a symbol."""
    today = date.today()
    dates = [d for d in parse_option_dates(options) if (d - today).days >= min_dte and d.weekday() == 4]
    return sorted(dates)[:count]


def expiry_bucket(dte: int) -> tuple[str, float]:
    """Human label and max-cost guardrail for a DTE."""
    if dte <= 10:
        return "weekly", 4.0
    if dte <= 21:
        return "short_swing", 5.0
    if dte <= 35:
        return "monthly", 7.0
    if dte <= 45:
        return "mid_swing", 8.5
    return "longer_swing", 10.0


def realized_window_for_dte(dte: int) -> int:
    """Use a realized-vol lookback that matches the trade horizon better than always HV20."""
    if dte <= 10:
        return 5
    if dte <= 21:
        return 10
    if dte <= 45:
        return 20
    return 30


def realized_vol_pct(close: pd.Series, lookback: int) -> float:
    ret = close.pct_change().dropna()
    if len(ret) < max(3, lookback):
        return 0.0
    return float(ret.tail(lookback).std() * math.sqrt(252) * 100)


def avg_abs_pct(close: pd.Series, lookback: int) -> float:
    ret = close.pct_change().dropna()
    if len(ret) < max(3, lookback):
        return 0.0
    return float(ret.tail(lookback).abs().mean() * 100)


def calc_atr_pct(hist: pd.DataFrame, n: int = 14) -> float:
    if len(hist) < n + 1:
        return 0.0
    high = hist["High"]
    low = hist["Low"]
    close = hist["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = float(tr.tail(n).mean())
    spot = float(close.iloc[-1])
    return atr / spot * 100 if spot else 0.0


def theme_for(symbol: str) -> str:
    hits = [name for name, members in THEMES.items() if symbol in members]
    return ",".join(hits) if hits else ""


def trigger_analysis(symbol: str, hist: pd.DataFrame, theme_moves: dict[str, float]) -> tuple[float, str]:
    close = hist["Close"]
    volume = hist["Volume"] if "Volume" in hist else pd.Series(dtype=float)
    spot = float(close.iloc[-1])
    score = 0.0
    reasons = []

    if len(close) >= 21:
        high20 = float(close.tail(20).max())
        low20 = float(close.tail(20).min())
        dist_high = (high20 / spot - 1) * 100 if spot else 999
        dist_low = (spot / low20 - 1) * 100 if low20 else 999
        if dist_high <= 3:
            score += 1.5
            reasons.append(f"near 20D high ({dist_high:.1f}%)")
        if dist_low <= 3:
            score += 1.5
            reasons.append(f"near 20D low ({dist_low:.1f}%)")

    if len(close) >= 6:
        m5 = pct(float(close.iloc[-1]), float(close.iloc[-6]))
        if abs(m5) >= 8:
            score += 1.0
            reasons.append(f"5D move {m5:+.1f}%")

    if len(close) >= 2:
        day = pct(float(close.iloc[-1]), float(close.iloc[-2]))
        atr = calc_atr_pct(hist)
        if atr and abs(day) >= 1.3 * atr:
            score += 1.2
            reasons.append(f"today {day:+.1f}% > 1.3x ATR")

    if len(volume) >= 21 and float(volume.tail(20).mean()) > 0:
        vol_ratio = float(volume.iloc[-1]) / float(volume.tail(20).mean())
        if vol_ratio >= 1.5:
            score += 1.0
            reasons.append(f"volume {vol_ratio:.1f}x avg")

    theme = theme_for(symbol)
    if theme:
        for part in theme.split(","):
            tm = theme_moves.get(part, 0.0)
            if abs(tm) >= 2.0:
                score += 0.8
                reasons.append(f"{part} basket {tm:+.1f}%")

    return score, "; ".join(reasons) if reasons else "watchlist only — no strong quantified trigger"


def fetch_history(symbol: str) -> Optional[pd.DataFrame]:
    try:
        hist = yf.Ticker(symbol).history(period="4mo", interval="1d", auto_adjust=False)
        if hist is None or len(hist) < 45:
            return None
        return hist.dropna(subset=["Close"])
    except Exception:
        return None


def build_theme_moves(histories: dict[str, pd.DataFrame]) -> dict[str, float]:
    out = {}
    for theme, members in THEMES.items():
        moves = []
        for sym in members:
            h = histories.get(sym)
            if h is not None and len(h) >= 2:
                moves.append(pct(float(h["Close"].iloc[-1]), float(h["Close"].iloc[-2])))
        if moves:
            out[theme] = sum(moves) / len(moves)
    return out


def load_dynamic_universe(min_price: float = 5.0, max_symbols: int = 0) -> list[str]:
    """Fetch a broad US-listed ticker universe from Nasdaq Trader symbol directories.

    This is dynamic enough for daily scanning and avoids a hard-coded volatility list.
    It includes Nasdaq + NYSE/AMEX/ARCA listed symbols, then drops ETFs/tests/odd symbols.
    Price/options/volatility filters happen later.
    """
    urls = [
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    ]
    symbols: set[str] = set()
    for url in urls:
        text = requests.get(url, timeout=20).text
        text = "\n".join(line for line in text.splitlines() if not line.startswith("File Creation Time"))
        df = pd.read_csv(StringIO(text), sep="|")
        sym_col = "Symbol" if "Symbol" in df.columns else "ACT Symbol"
        if sym_col not in df.columns:
            continue
        for _, row in df.iterrows():
            sym = str(row.get(sym_col, "")).strip().upper()
            if not sym or sym == "NAN":
                continue
            if row.get("Test Issue", "N") == "Y":
                continue
            if "ETF" in row and str(row.get("ETF", "N")) == "Y":
                continue
            # Keep common stocks/options-friendly tickers; skip warrants, units, preferreds/classes with separators.
            if any(ch in sym for ch in ["$", ".", "^", "/"]):
                continue
            if len(sym) > 5:
                continue
            symbols.add(sym)
    out = sorted(symbols)
    return out[:max_symbols] if max_symbols and max_symbols > 0 else out


def scan_symbol(symbol: str, windows: list[str], otms: list[int], args, histories, theme_moves) -> list[Candidate]:
    hist = histories.get(symbol)
    if hist is None:
        return []
    close = hist["Close"]
    spot = float(close.iloc[-1])
    if spot < args.min_price:
        return []
    hv20 = realized_vol_pct(close, 20)
    avg_abs = avg_abs_pct(close, 20)
    # Broad pre-filter only. Final volatility relevance is computed per-expiry using
    # a DTE-adjusted lookback (HV5/HV10/HV20/HV30). This keeps short-DTE trades from
    # being judged only by stale 20-day behavior.
    if hv20 < args.min_hv20 and realized_vol_pct(close, 10) < args.min_hv20 and realized_vol_pct(close, 5) < args.min_hv20:
        return []
    if avg_abs < args.min_avg_abs and avg_abs_pct(close, 10) < args.min_avg_abs and avg_abs_pct(close, 5) < args.min_avg_abs:
        return []

    t = yf.Ticker(symbol)
    try:
        options = list(t.options)
    except Exception:
        return []

    trigger_score, trigger_reason = trigger_analysis(symbol, hist, theme_moves)
    day_change = pct(float(close.iloc[-1]), float(close.iloc[-2])) if len(close) >= 2 else 0.0
    move_5d = pct(float(close.iloc[-1]), float(close.iloc[-6])) if len(close) >= 6 else 0.0
    move_20d = pct(float(close.iloc[-1]), float(close.iloc[-21])) if len(close) >= 21 else 0.0
    atr14 = calc_atr_pct(hist)

    candidates: list[Candidate] = []
    today = date.today()
    expiries: list[tuple[str, date, float]] = []
    if args.expiry_mode == "next_fridays":
        for expiry in next_friday_expiries(options, count=args.next_fridays, min_dte=args.min_dte):
            dte = (expiry - today).days
            window, max_cost_pct = expiry_bucket(dte)
            expiries.append((window, expiry, max_cost_pct))
    else:
        for window in windows:
            min_dte, max_dte, max_cost_pct = WINDOWS[window]
            expiry = nearest_expiry(options, min_dte, max_dte)
            if expiry:
                expiries.append((window, expiry, max_cost_pct))

    for window, expiry, max_cost_pct in expiries:
        dte = (expiry - today).days
        hv_window = realized_window_for_dte(dte)
        hv_used = realized_vol_pct(close, hv_window)
        avg_abs_used = avg_abs_pct(close, hv_window)
        if hv_used < args.min_hv20 or avg_abs_used < args.min_avg_abs:
            continue
        try:
            chain = t.option_chain(expiry.isoformat())
        except Exception:
            continue
        calls = chain.calls.copy()
        puts = chain.puts.copy()
        if calls.empty or puts.empty:
            continue
        for df in (calls, puts):
            for col in ["strike", "bid", "ask", "lastPrice", "volume", "openInterest"]:
                if col not in df.columns:
                    df[col] = 0
                df[col] = df[col].fillna(0)
            df["mid"] = df.apply(mid_price, axis=1)
            df["spread_pct"] = df.apply(spread_pct, axis=1)

        for otm in otms:
            call_target = spot * (1 + otm / 100)
            put_target = spot * (1 - otm / 100)
            call = calls.iloc[(calls["strike"] - call_target).abs().argsort()[:1]].iloc[0]
            put = puts.iloc[(puts["strike"] - put_target).abs().argsort()[:1]].iloc[0]
            cost = float(call["mid"] + put["mid"])
            if cost <= 0:
                continue
            cost_pct = cost / spot * 100
            leg_oi = float(call["openInterest"] + put["openInterest"])
            leg_vol = float(call["volume"] + put["volume"])
            max_spread = max(float(call["spread_pct"]), float(put["spread_pct"]))

            warnings = []
            if cost_pct > max_cost_pct:
                warnings.append(f"cost>{max_cost_pct:.1f}% for {window}")
            if leg_oi < args.min_oi:
                warnings.append("low OI")
            if leg_vol < args.min_volume:
                warnings.append("low volume")
            if max_spread > args.max_spread_pct:
                warnings.append("wide spread")
            if float(call["bid"]) == 0 or float(put["bid"]) == 0:
                warnings.append("zero bid")
            if trigger_score < args.min_trigger_score and window == "weekly":
                warnings.append("weekly needs stronger trigger")

            # Keep imperfect rows if --include-watchlist, otherwise enforce core filters.
            if not args.include_watchlist and warnings:
                continue

            be_up = float(call["strike"]) + cost
            be_down = float(put["strike"]) - cost
            be_up_dist = (be_up / spot - 1) * 100
            be_down_dist = (spot / be_down - 1) * 100 if be_down > 0 else 999.0
            value_score = hv_used / cost_pct if cost_pct else 0.0
            liquidity_penalty = max(max_spread - 20, 0) / 10 + max(args.min_oi - leg_oi, 0) / 500
            final_score = value_score + trigger_score * 2 - liquidity_penalty

            candidates.append(Candidate(
                symbol=symbol,
                theme=theme_for(symbol),
                window=window,
                expiry=expiry.isoformat(),
                dte=dte,
                spot=round(spot, 2),
                hv20_pct=round(hv20, 1),
                hv_used_pct=round(hv_used, 1),
                hv_window=hv_window,
                avg_abs_20d_pct=round(avg_abs, 2),
                avg_abs_used_pct=round(avg_abs_used, 2),
                day_change_pct=round(day_change, 2),
                move_5d_pct=round(move_5d, 2),
                move_20d_pct=round(move_20d, 2),
                atr14_pct=round(atr14, 2),
                otm_pct=otm,
                call_contract=str(call.get("contractSymbol", "")),
                call_strike=float(call["strike"]),
                call_bid=float(call["bid"]),
                call_ask=float(call["ask"]),
                call_mid=round(float(call["mid"]), 2),
                call_volume=float(call["volume"]),
                call_oi=float(call["openInterest"]),
                put_contract=str(put.get("contractSymbol", "")),
                put_strike=float(put["strike"]),
                put_bid=float(put["bid"]),
                put_ask=float(put["ask"]),
                put_mid=round(float(put["mid"]), 2),
                put_volume=float(put["volume"]),
                put_oi=float(put["openInterest"]),
                total_cost=round(cost, 2),
                cost_pct=round(cost_pct, 2),
                breakeven_up=round(be_up, 2),
                breakeven_down=round(be_down, 2),
                breakeven_up_dist_pct=round(be_up_dist, 2),
                breakeven_down_dist_pct=round(be_down_dist, 2),
                max_spread_pct=round(max_spread, 1),
                leg_volume=leg_vol,
                leg_oi=leg_oi,
                value_score=round(value_score, 2),
                trigger_score=round(trigger_score, 2),
                final_score=round(final_score, 2),
                trigger_reason=trigger_reason,
                warnings=", ".join(warnings),
            ))
    return candidates


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scan long strangle candidates")
    p.add_argument("--symbols", nargs="*", default=None, help="Explicit symbols. If omitted, uses --universe.")
    p.add_argument("--universe", choices=["dynamic", "watchlist"], default="dynamic")
    p.add_argument("--max-symbols", type=int, default=0, help="Limit dynamic universe for testing; 0 = no limit")
    p.add_argument("--expiry-mode", choices=["next_fridays", "windows"], default="next_fridays")
    p.add_argument("--next-fridays", type=int, default=8, help="When --expiry-mode next_fridays, scan this many upcoming Friday expiries")
    p.add_argument("--min-dte", type=int, default=7, help="Skip expiries closer than this many days; default avoids 0DTE/1DTE noise")
    p.add_argument("--windows", nargs="*", choices=list(WINDOWS), default=list(WINDOWS))
    p.add_argument("--otm", nargs="*", type=int, default=[10, 15, 20])
    p.add_argument("--min-price", type=float, default=5.0)
    p.add_argument("--min-hv20", type=float, default=50.0)
    p.add_argument("--min-avg-abs", type=float, default=2.5)
    p.add_argument("--min-oi", type=float, default=500.0)
    p.add_argument("--min-volume", type=float, default=50.0)
    p.add_argument("--max-spread-pct", type=float, default=30.0)
    p.add_argument("--min-trigger-score", type=float, default=1.0)
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--include-watchlist", action="store_true", help="Include rows with warnings instead of strict filtering")
    p.add_argument("--csv", help="Optional CSV output path")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.symbols:
        symbols = sorted(set(s.upper() for s in args.symbols))
    elif args.universe == "dynamic":
        symbols = load_dynamic_universe(min_price=args.min_price, max_symbols=args.max_symbols)
    else:
        symbols = sorted(set(DEFAULT_WATCHLIST))

    print(f"Scanning {len(symbols)} symbols | expiry_mode={args.expiry_mode} | otm={args.otm}")
    histories = {sym: fetch_history(sym) for sym in symbols}
    histories = {k: v for k, v in histories.items() if v is not None}
    theme_moves = build_theme_moves(histories)

    rows: list[Candidate] = []
    for sym in symbols:
        rows.extend(scan_symbol(sym, args.windows, args.otm, args, histories, theme_moves))

    rows.sort(key=lambda r: r.final_score, reverse=True)
    rows = rows[: args.top]

    if args.csv:
        pd.DataFrame([asdict(r) for r in rows]).to_csv(args.csv, index=False)

    if not rows:
        print("No candidates passed filters. Try --include-watchlist or relax thresholds.")
        return 0

    print("⚠️ Yahoo/yfinance quotes may be delayed or stale. Verify live broker bid/ask and use limit orders.\n")
    for r in rows:
        print(
            f"{r.symbol} {r.window} {r.expiry} DTE={r.dte} score={r.final_score} "
            f"HV{r.hv_window}={r.hv_used_pct}% HV20={r.hv20_pct}% cost={r.total_cost} ({r.cost_pct}%) {r.otm_pct}%OTM "
            f"BE↑ {r.breakeven_up} (+{r.breakeven_up_dist_pct}%) BE↓ {r.breakeven_down} (-{r.breakeven_down_dist_pct}%)"
        )
        print(
            f"  {r.call_contract} K{r.call_strike:g} bid/ask {r.call_bid:g}/{r.call_ask:g} "
            f"+ {r.put_contract} K{r.put_strike:g} bid/ask {r.put_bid:g}/{r.put_ask:g}"
        )
        print(
            f"  vol/OI={r.leg_volume:.0f}/{r.leg_oi:.0f} spread={r.max_spread_pct}% "
            f"trigger={r.trigger_reason}"
        )
        if r.warnings:
            print(f"  warnings: {r.warnings}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
