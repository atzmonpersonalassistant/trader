#!/usr/bin/env python3
"""
Options Rules Scanner

Scans stocks for continuation setups and next-week options using Uriel's Options Setups Tracker rules.

Default logic:
- Detect LONG/SHORT continuation candidates from intraday candles.
- LONG: strong up day, near high, above VWAP, EMA9 > EMA21, last-hour rising.
- SHORT: strong down day, near low, below VWAP, EMA9 < EMA21, last-hour falling.
- Then scan options:
  - LONG -> OTM calls
  - SHORT -> ITM puts
  - expiry can be a specific date, or all expiries within a configurable DTE window
  - strike within configurable distance from current price
  - option ask/price <= max premium
  - prefer real volume/open interest and tighter spreads

Data source: yfinance/Yahoo. Always verify bid/ask in broker before trading.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from statistics import NormalDist
from typing import Iterable, Optional

import pandas as pd
import yfinance as yf

N = NormalDist()

DEFAULT_WATCHLIST = """
QUBT QBTS RGTI IONQ POET ASTS HIMS MARA LUNR RKLB MSTR IREN COIN RIOT ONDS OKTA CSCO TSLA NVDA HPQ CRM BILI TGT SOUN PLTR SMCI AMD DELL MRVL SNOW UBER RDDT HOOD SOFI UPST AFRM CVNA ROKU DKNG
""".split()


@dataclass
class StockSignal:
    symbol: str
    bias: str
    score: int
    last: float
    change_pct: float
    day_range_pct: float
    range_position: float
    vwap: float
    slope_60m_pct: float
    long_score: int
    short_score: int
    volume: int


@dataclass
class OptionCandidate:
    symbol: str
    bias: str
    score: int
    option_type: str
    expiry: str
    contract: str
    spot: float
    strike: float
    strike_distance_pct: float
    price: float
    bid: Optional[float]
    ask: Optional[float]
    last_price: Optional[float]
    spread_pct: Optional[float]
    calc_iv_pct: Optional[float]
    volume: Optional[float]
    open_interest: Optional[float]
    stock_change_pct: float
    stock_slope_60m_pct: float
    reason: str


def parse_symbols(args_symbols: list[str], file_path: Optional[str]) -> list[str]:
    symbols: list[str] = []
    if file_path:
        text = Path(file_path).read_text()
        for token in text.replace(",", " ").split():
            token = token.strip().upper()
            if token and not token.startswith("#"):
                symbols.append(token)
    for item in args_symbols:
        for token in item.replace(",", " ").split():
            token = token.strip().upper()
            if token:
                symbols.append(token)
    if not symbols:
        symbols = DEFAULT_WATCHLIST[:]
    return sorted(set(symbols))


def next_friday_iso(today: Optional[pd.Timestamp] = None) -> str:
    today = today or pd.Timestamp.today().normalize()
    # next Friday, not today if today is Friday; options usually expire Friday.
    days_ahead = (4 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return str((today + pd.Timedelta(days=days_ahead)).date())


def bs_price(spot: float, strike: float, years: float, rate: float, sigma: float, option_type: str) -> float:
    if years <= 0 or sigma <= 0:
        return max(0.0, spot - strike) if option_type == "call" else max(0.0, strike - spot)
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * years) / (sigma * math.sqrt(years))
    d2 = d1 - sigma * math.sqrt(years)
    if option_type == "call":
        return spot * N.cdf(d1) - strike * math.exp(-rate * years) * N.cdf(d2)
    return strike * math.exp(-rate * years) * N.cdf(-d2) - spot * N.cdf(-d1)


def implied_vol(price: float, spot: float, strike: float, years: float, option_type: str, rate: float = 0.045) -> Optional[float]:
    if not (price and price > 0 and spot > 0 and strike > 0 and years > 0):
        return None
    lo, hi = 0.0001, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2
        val = bs_price(spot, strike, years, rate, mid, option_type)
        if val < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def get_stock_signal(symbol: str, min_move_pct: float) -> Optional[StockSignal]:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1d", interval="5m", prepost=False, auto_adjust=False)
    if len(hist) < 20:
        return None

    close = hist["Close"].astype(float)
    high = hist["High"].astype(float)
    low = hist["Low"].astype(float)
    vol = hist["Volume"].fillna(0).astype(float)

    last = float(close.iloc[-1])
    day_high = float(high.max())
    day_low = float(low.min())
    open_price = float(hist["Open"].iloc[0])

    try:
        fast = ticker.fast_info
        prev_close = fast.get("previousClose") or fast.get("previous_close")
    except Exception:
        prev_close = None
    change_pct = ((last - prev_close) / prev_close * 100) if prev_close else ((last / open_price - 1) * 100)
    day_range_pct = (day_high - day_low) / day_low * 100 if day_low else 0.0
    range_position = (last - day_low) / (day_high - day_low) if day_high > day_low else 0.5
    vwap = float((close * vol).sum() / vol.sum()) if vol.sum() > 0 else float(close.mean())
    ema9 = float(close.ewm(span=9).mean().iloc[-1])
    ema21 = float(close.ewm(span=21).mean().iloc[-1])

    last_60m = close.tail(12)
    slope_60m_pct = float((last_60m.iloc[-1] / last_60m.iloc[0] - 1) * 100) if len(last_60m) > 1 else 0.0

    lows = low.tail(12).values
    highs = high.tail(12).values
    higher_lows = sum(1 for i in range(1, len(lows)) if lows[i] >= lows[i - 1])
    lower_highs = sum(1 for i in range(1, len(highs)) if highs[i] <= highs[i - 1])
    late_volume_elevated = vol.tail(12).sum() > vol.mean() * 12 if vol.mean() > 0 else False

    long_score = 0
    short_score = 0

    if change_pct >= min_move_pct:
        long_score += 2
    if range_position >= 0.75:
        long_score += 2
    if last > vwap:
        long_score += 1
    if last > ema9 > ema21:
        long_score += 2
    if slope_60m_pct > 1:
        long_score += 2
    if higher_lows >= 7:
        long_score += 1
    if late_volume_elevated:
        long_score += 1

    if change_pct <= -min_move_pct:
        short_score += 2
    if range_position <= 0.25:
        short_score += 2
    if last < vwap:
        short_score += 1
    if last < ema9 < ema21:
        short_score += 2
    if slope_60m_pct < -1:
        short_score += 2
    if lower_highs >= 7:
        short_score += 1
    if late_volume_elevated:
        short_score += 1

    bias = "LONG" if long_score >= short_score else "SHORT"
    score = max(long_score, short_score)

    return StockSignal(
        symbol=symbol,
        bias=bias,
        score=score,
        last=last,
        change_pct=change_pct,
        day_range_pct=day_range_pct,
        range_position=range_position,
        vwap=vwap,
        slope_60m_pct=slope_60m_pct,
        long_score=long_score,
        short_score=short_score,
        volume=int(vol.sum()),
    )


def scan_options_for_signal(
    signal: StockSignal,
    expiry: Optional[str],
    max_premium: float,
    strike_distance_pct: float,
    min_volume: int,
    min_open_interest: int,
    max_spread_pct: float,
    asof: pd.Timestamp,
    min_dte: int,
    max_dte: int,
) -> list[OptionCandidate]:
    ticker = yf.Ticker(signal.symbol)
    try:
        all_expiries = list(ticker.options)
    except Exception:
        return []

    today = asof.normalize()
    if expiry:
        expiries = [expiry] if expiry in all_expiries else []
    else:
        expiries = []
        for exp in all_expiries:
            dte = (pd.Timestamp(exp) - today).days
            if min_dte <= dte <= max_dte:
                expiries.append(exp)

    option_type = "call" if signal.bias == "LONG" else "put"
    out: list[OptionCandidate] = []

    for exp in expiries:
        try:
            chain = ticker.option_chain(exp)
        except Exception:
            continue
        df = chain.calls.copy() if option_type == "call" else chain.puts.copy()
        if df.empty:
            continue

        for col in ["strike", "lastPrice", "bid", "ask", "volume", "openInterest", "impliedVolatility"]:
            if col not in df.columns:
                df[col] = pd.NA
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Use ask when live-ish ask exists; otherwise lastPrice as fallback.
        df["price"] = df["ask"].where(df["ask"] > 0, df["lastPrice"])
        df["spread"] = df["ask"] - df["bid"]
        df["mid"] = (df["ask"] + df["bid"]) / 2
        df["spread_pct"] = (df["spread"] / df["mid"] * 100).where(df["mid"] > 0)
        df["distance_pct"] = (df["strike"] / signal.last - 1) * 100

        if option_type == "call":
            # LONG continuation: OTM calls from ATM to +strike_distance_pct.
            filt = (df["strike"] >= signal.last) & (df["strike"] <= signal.last * (1 + strike_distance_pct / 100))
            moneyness = "OTM call"
        else:
            # SHORT continuation: ITM puts, meaning strike above current stock price,
            # up to +strike_distance_pct. Price must still pass max_premium.
            filt = (df["strike"] >= signal.last) & (df["strike"] <= signal.last * (1 + strike_distance_pct / 100))
            moneyness = "ITM put"

        filt &= (df["price"] > 0) & (df["price"] <= max_premium)
        filt &= df["volume"].fillna(0) >= min_volume
        filt &= df["openInterest"].fillna(0) >= min_open_interest
        # If spread is missing because Yahoo data is bad, allow but mark it. If present, enforce threshold.
        filt &= df["spread_pct"].isna() | (df["spread_pct"] <= max_spread_pct)

        dte = max((pd.Timestamp(exp) - today).days, 1)
        years = dte / 365

        for _, row in df[filt].iterrows():
            price = float(row["price"])
            calc_iv = implied_vol(price, signal.last, float(row["strike"]), years, option_type)
            spread_pct = None if pd.isna(row["spread_pct"]) else float(row["spread_pct"])
            reason = (
                f"{signal.bias} continuation score {signal.score}; {moneyness}; "
                f"stock {signal.change_pct:+.1f}% today; range position {signal.range_position:.2f}; "
                f"60m slope {signal.slope_60m_pct:+.1f}%; option <= ${max_premium:g}."
            )
            out.append(
                OptionCandidate(
                    symbol=signal.symbol,
                    bias=signal.bias,
                    score=signal.score,
                    option_type=option_type,
                    expiry=exp,
                    contract=str(row.get("contractSymbol", "")),
                    spot=signal.last,
                    strike=float(row["strike"]),
                    strike_distance_pct=float(row["distance_pct"]),
                    price=price,
                    bid=None if pd.isna(row["bid"]) else float(row["bid"]),
                    ask=None if pd.isna(row["ask"]) else float(row["ask"]),
                    last_price=None if pd.isna(row["lastPrice"]) else float(row["lastPrice"]),
                    spread_pct=spread_pct,
                    calc_iv_pct=None if calc_iv is None else calc_iv * 100,
                    volume=None if pd.isna(row["volume"]) else float(row["volume"]),
                    open_interest=None if pd.isna(row["openInterest"]) else float(row["openInterest"]),
                    stock_change_pct=signal.change_pct,
                    stock_slope_60m_pct=signal.slope_60m_pct,
                    reason=reason,
                )
            )
    return out


def write_csv(path: str, rows: Iterable[dict]) -> None:
    rows = list(rows)
    if not rows:
        Path(path).write_text("")
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def fmt_money(value: Optional[float]) -> str:
    return "n/a" if value is None else f"${value:.2f}"


def fmt_num(value: Optional[float], suffix: str = "") -> str:
    return "n/a" if value is None else f"{value:.0f}{suffix}"


def format_trade_card(candidate: OptionCandidate, rank: int) -> str:
    direction_he = "לונג / CALL" if candidate.bias == "LONG" else "שורט / PUT"
    trigger = (
        "כניסה רק אם המניה ממשיכה מעל VWAP/גבוה 5 דק׳ אחרון"
        if candidate.bias == "LONG"
        else "כניסה רק אם המניה נשארת מתחת VWAP ושוברת/שומרת נמוך 5 דק׳ אחרון"
    )
    invalidation = (
        "יציאה אם המניה חוזרת מתחת VWAP או שוברת higher lows"
        if candidate.bias == "LONG"
        else "יציאה אם המניה חוזרת מעל VWAP או שוברת lower highs"
    )
    spread = "n/a" if candidate.spread_pct is None else f"{candidate.spread_pct:.0f}%"
    iv = "n/a" if candidate.calc_iv_pct is None else f"{candidate.calc_iv_pct:.0f}%"
    oi = "n/a" if candidate.open_interest is None else f"{int(candidate.open_interest)}"
    vol = "n/a" if candidate.volume is None else f"{int(candidate.volume)}"
    ask_or_price = candidate.ask if candidate.ask and candidate.ask > 0 else candidate.price
    max_entry = ask_or_price
    return "\n".join(
        [
            f"#{rank} {candidate.symbol} — {direction_he}",
            f"חוזה: {candidate.contract}",
            f"פקיעה: {candidate.expiry} | סטרייק: {candidate.strike:g} ({candidate.strike_distance_pct:+.1f}% מהמחיר)",
            f"מחיר מניה: ${candidate.spot:.2f} | תנועה היום: {candidate.stock_change_pct:+.1f}% | 60 דק׳: {candidate.stock_slope_60m_pct:+.1f}%",
            f"מחיר אופציה: {fmt_money(candidate.price)} | Bid/Ask: {fmt_money(candidate.bid)} / {fmt_money(candidate.ask)} | מקס׳ כניסה לבדיקה: עד {fmt_money(max_entry)}",
            f"Volume/OI: {vol}/{oi} | IV מחושב: {iv} | Spread: {spread} | ציון סטאפ: {candidate.score}/11",
            f"טריגר כניסה: {trigger}",
            f"אינבלידציה: {invalidation}",
            f"למה זה עלה בסריקה: {candidate.reason}",
        ]
    )


def format_signal_line(signal: StockSignal, rank: int) -> str:
    direction_he = "לונג" if signal.bias == "LONG" else "שורט"
    return (
        f"#{rank} {signal.symbol} — {direction_he}, ציון {signal.score}/11, "
        f"תנועה היום {signal.change_pct:+.1f}%, 60 דק׳ {signal.slope_60m_pct:+.1f}%, "
        f"מיקום בטווח {signal.range_position:.2f}, ווליום {signal.volume:,}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan stocks/options using Uriel's continuation rules.")
    parser.add_argument("symbols", nargs="*", help="Tickers, comma or space separated. Defaults to built-in watchlist.")
    parser.add_argument("--symbols-file", help="File with tickers separated by whitespace/comma.")
    parser.add_argument("--expiry", default="", help="Option expiry YYYY-MM-DD. Default: scan all expiries in DTE window.")
    parser.add_argument("--min-dte", type=int, default=6, help="Minimum days to expiry when --expiry is omitted. Default 6")
    parser.add_argument("--max-dte", type=int, default=45, help="Maximum days to expiry when --expiry is omitted. Default 45")
    parser.add_argument("--max-premium", type=float, default=1.0, help="Max option price/ask. Default 1.0")
    parser.add_argument("--strike-distance", type=float, default=10.0, help="Strike distance percent from spot. Default 10")
    parser.add_argument("--min-move", type=float, default=5.0, help="Strong stock move threshold percent. Default 5")
    parser.add_argument("--min-score", type=int, default=7, help="Minimum continuation score. Default 7")
    parser.add_argument("--min-volume", type=int, default=1, help="Minimum option volume. Default 1")
    parser.add_argument("--min-oi", type=int, default=0, help="Minimum open interest. Default 0")
    parser.add_argument("--max-spread-pct", type=float, default=80.0, help="Max option spread percent if bid/ask exists. Default 80")
    parser.add_argument("--out", default="options_tools/latest_candidates.csv", help="Output CSV path.")
    parser.add_argument("--signals-out", default="options_tools/latest_stock_signals.csv", help="Output stock signals CSV path.")
    parser.add_argument("--top", type=int, default=30, help="Rows to print. Default 30")
    args = parser.parse_args()

    symbols = parse_symbols(args.symbols, args.symbols_file)
    asof = pd.Timestamp.today()

    signals: list[StockSignal] = []
    candidates: list[OptionCandidate] = []

    for sym in symbols:
        try:
            sig = get_stock_signal(sym, args.min_move)
            if not sig:
                continue
            signals.append(sig)
            if sig.score >= args.min_score:
                candidates.extend(
                    scan_options_for_signal(
                        sig,
                        expiry=args.expiry or None,
                        max_premium=args.max_premium,
                        strike_distance_pct=args.strike_distance,
                        min_volume=args.min_volume,
                        min_open_interest=args.min_oi,
                        max_spread_pct=args.max_spread_pct,
                        asof=asof,
                        min_dte=args.min_dte,
                        max_dte=args.max_dte,
                    )
                )
        except Exception as exc:
            print(f"WARN {sym}: {exc}")

    signals.sort(key=lambda s: s.score, reverse=True)
    candidates.sort(
        key=lambda c: (
            c.score,
            c.volume or 0,
            c.open_interest or 0,
            c.calc_iv_pct or 0,
        ),
        reverse=True,
    )

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.signals_out, [asdict(s) for s in signals])
    write_csv(args.out, [asdict(c) for c in candidates])

    print("סריקת אופציות לפי Rules")
    print(f"נסרקו {len(symbols)} מניות | סיגנלים: {len(signals)} | מועמדי אופציות: {len(candidates)}")
    expiry_label = args.expiry if args.expiry else f"כל הפקיעות בטווח {args.min_dte}-{args.max_dte} DTE"
    print(f"פקיעה: {expiry_label} | מחיר מקס׳: ${args.max_premium:g} | מרחק סטרייק: {args.strike_distance:g}%")
    print(f"CSV: {args.out}")
    print()

    if not candidates:
        print("אין כרגע טרייד אופציה נקי לפי כל הפילטרים.")
        print("\nהמניות הכי קרובות לסטאפ:")
        for i, sig in enumerate(signals[: min(args.top, 8)], start=1):
            print(format_signal_line(sig, i))
        print("\nמה לעשות עם זה: לא לקחת טרייד רק מהמניה. לחכות שאופציה מתאימה תופיע או להריץ עם פרמטרים פחות קשוחים.")
        print("אזהרה: חייבים לבדוק Bid/Ask חי בברוקר לפני כל פעולה.")
        return 0

    print("מועמדי טרייד מסודרים")
    print("שים לב: זה סורק, לא הוראת קנייה. בדוק Bid/Ask חי, גודל פוזיציה, וטריגר לפני פעולה.")
    print()
    for i, c in enumerate(candidates[: args.top], start=1):
        print(format_trade_card(c, i))
        print("-" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
