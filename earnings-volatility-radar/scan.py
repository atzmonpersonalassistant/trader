#!/usr/bin/env python3
"""Rolling Earnings Volatility Radar.

Builds a daily dynamic universe from upcoming earnings + a fixed watchlist,
checks option-chain liquidity/expected move with yfinance, compares against a
local earnings-history file when available, and writes candidate outputs.

This is a radar, not a trade executor. It classifies situations for manual
review: LONG_VOL_CANDIDATE, SHORT_VOL_CANDIDATE, CALENDAR_CANDIDATE, NO_EDGE,
WATCH_ONLY, POST_EARNINGS_REVIEW, or rejected states.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

try:
    import yfinance as yf
except Exception:  # pragma: no cover - handled at runtime
    yf = None

DEFAULT_PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_EARNINGS = DEFAULT_PROJECT_DIR / "config" / "earnings.csv"
DEFAULT_WATCHLIST = DEFAULT_PROJECT_DIR / "config" / "watchlist.csv"
DEFAULT_HISTORY = DEFAULT_PROJECT_DIR / "data" / "earnings_history.csv"
DEFAULT_OUTPUT_DIR = DEFAULT_PROJECT_DIR / "output"
DEFAULT_LOOKAHEAD_DAYS = 7
DEFAULT_MAX_WORKERS = 8

POSTURE_LONG_VOL = "LONG_VOL_CANDIDATE"
POSTURE_SHORT_VOL = "SHORT_VOL_CANDIDATE"
POSTURE_CALENDAR = "CALENDAR_CANDIDATE"
POSTURE_NO_EDGE = "NO_EDGE"
POSTURE_WATCH = "WATCH_ONLY"
POSTURE_REVIEW = "POST_EARNINGS_REVIEW"

HEADER = [
    "scan_timestamp",
    "ticker",
    "event_status",
    "earnings_date",
    "earnings_time",
    "days_to_earnings",
    "price",
    "front_expiry",
    "back_expiry",
    "atm_strike",
    "atm_call_mid",
    "atm_put_mid",
    "expected_move_pct",
    "historical_median_move_pct",
    "historical_avg_move_pct",
    "sample_size",
    "front_iv",
    "back_iv",
    "front_back_iv_ratio",
    "liquidity_score",
    "edge_score",
    "posture",
    "send_candidate",
    "reason",
]


@dataclass
class UniverseRow:
    ticker: str
    reason: str = ""
    always_scan: bool = False
    notes: str = ""
    earnings_date: str = ""
    earnings_time: str = "UNKNOWN"
    source: str = ""


@dataclass
class Candidate:
    scan_timestamp: str
    ticker: str
    event_status: str
    earnings_date: str
    earnings_time: str
    days_to_earnings: int | str
    price: float | str
    front_expiry: str
    back_expiry: str
    atm_strike: float | str
    atm_call_mid: float | str
    atm_put_mid: float | str
    expected_move_pct: float | str
    historical_median_move_pct: float | str
    historical_avg_move_pct: float | str
    sample_size: int
    front_iv: float | str
    back_iv: float | str
    front_back_iv_ratio: float | str
    liquidity_score: int
    edge_score: int
    posture: str
    send_candidate: bool
    reason: str


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def parse_date(value: str) -> date | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_earnings(path: Path) -> dict[str, UniverseRow]:
    rows: dict[str, UniverseRow] = {}
    for r in read_csv(path):
        ticker = str(r.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        rows[ticker] = UniverseRow(
            ticker=ticker,
            earnings_date=str(r.get("earnings_date", "")).strip(),
            earnings_time=str(r.get("earnings_time", "UNKNOWN")).strip().upper() or "UNKNOWN",
            source=str(r.get("source", "")).strip(),
        )
    return rows


def load_watchlist(path: Path) -> dict[str, UniverseRow]:
    rows: dict[str, UniverseRow] = {}
    for r in read_csv(path):
        ticker = str(r.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        rows[ticker] = UniverseRow(
            ticker=ticker,
            reason=str(r.get("reason", "")).strip(),
            always_scan=parse_bool(r.get("always_scan", "true")),
            notes=str(r.get("notes", "")).strip(),
        )
    return rows


def build_universe(earnings_path: Path, watchlist_path: Path, today: date, lookahead_days: int) -> list[UniverseRow]:
    earnings = load_earnings(earnings_path)
    watch = load_watchlist(watchlist_path)
    merged: dict[str, UniverseRow] = {}

    for ticker, row in earnings.items():
        ed = parse_date(row.earnings_date)
        if not ed:
            continue
        delta = (ed - today).days
        if -1 <= delta <= lookahead_days:
            merged[ticker] = row

    for ticker, row in watch.items():
        if ticker in merged:
            merged[ticker].reason = row.reason
            merged[ticker].always_scan = row.always_scan
            merged[ticker].notes = row.notes
        elif row.always_scan:
            merged[ticker] = row

    return sorted(merged.values(), key=lambda r: (event_sort_key(r, today), r.ticker))


def event_status(row: UniverseRow, today: date) -> tuple[str, int | str]:
    ed = parse_date(row.earnings_date)
    if not ed:
        return POSTURE_WATCH, ""
    delta = (ed - today).days
    if delta == -1:
        return POSTURE_REVIEW, delta
    if delta == 0:
        return "PRE_EARNINGS_TODAY", delta
    if delta == 1:
        return "PRE_EARNINGS_TOMORROW", delta
    if 2 <= delta <= 7:
        return "PRE_EARNINGS_SOON", delta
    return POSTURE_WATCH, delta


def event_sort_key(row: UniverseRow, today: date) -> tuple[int, int, str]:
    status, delta = event_status(row, today)
    rank = {
        "PRE_EARNINGS_TODAY": 0,
        "PRE_EARNINGS_TOMORROW": 1,
        "PRE_EARNINGS_SOON": 2,
        POSTURE_REVIEW: 3,
        POSTURE_WATCH: 4,
    }.get(status, 9)
    return rank, int(delta) if isinstance(delta, int) else 999, row.ticker


def load_history(path: Path) -> dict[str, list[float]]:
    hist: dict[str, list[float]] = {}
    for r in read_csv(path):
        ticker = str(r.get("ticker", "")).strip().upper()
        try:
            move = abs(float(r.get("actual_move_pct", "")))
        except Exception:
            continue
        if ticker and math.isfinite(move):
            hist.setdefault(ticker, []).append(move)
    return hist


def mid(row) -> float:
    bid = safe_float(row.get("bid"))
    ask = safe_float(row.get("ask"))
    last = safe_float(row.get("lastPrice"))
    if bid > 0 and ask > 0:
        return round((bid + ask) / 2, 4)
    if ask > 0:
        return ask
    return last


def safe_float(value) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else 0.0
    except Exception:
        return 0.0


def nearest(values: list[float], target: float) -> float | None:
    if not values:
        return None
    return min(values, key=lambda x: abs(x - target))


def liquidity_score(call_row, put_row) -> tuple[int, list[str]]:
    reasons = []
    score = 0
    for label, row in [("call", call_row), ("put", put_row)]:
        bid = safe_float(row.get("bid"))
        ask = safe_float(row.get("ask"))
        volume = safe_float(row.get("volume"))
        oi = safe_float(row.get("openInterest"))
        m = mid(row)
        spread_pct = ((ask - bid) / m * 100) if bid > 0 and ask > 0 and m > 0 else 999
        if volume >= 50:
            score += 15
        elif volume >= 10:
            score += 8
        else:
            reasons.append(f"low {label} volume")
        if oi >= 200:
            score += 15
        elif oi >= 50:
            score += 8
        else:
            reasons.append(f"low {label} OI")
        if spread_pct <= 10:
            score += 20
        elif spread_pct <= 25:
            score += 10
        else:
            reasons.append(f"wide {label} spread")
    return min(score, 100), reasons


def choose_expiries(expiries: list[str], earnings_date: str) -> tuple[str, str]:
    ed = parse_date(earnings_date) or date.today()
    parsed = [(parse_date(e), e) for e in expiries]
    parsed = [(d, e) for d, e in parsed if d]
    parsed.sort()
    front = next((e for d, e in parsed if d and d >= ed), parsed[0][1] if parsed else "")
    front_date = parse_date(front) or ed
    back = next((e for d, e in parsed if d and d >= front_date + timedelta(days=21)), "")
    return front, back


def option_snapshot(ticker: str, earnings_date: str) -> dict:
    if yf is None:
        raise RuntimeError("yfinance is not installed")
    t = yf.Ticker(ticker)
    hist = t.history(period="5d")
    if hist.empty:
        raise RuntimeError("no price history")
    price = float(hist["Close"].dropna().iloc[-1])
    expiries = list(getattr(t, "options", []) or [])
    if not expiries:
        raise RuntimeError("no option expiries")
    front, back = choose_expiries(expiries, earnings_date)
    if not front:
        raise RuntimeError("no usable front expiry")
    chain = t.option_chain(front)
    strikes = sorted(set(chain.calls["strike"].astype(float)).intersection(set(chain.puts["strike"].astype(float))))
    atm = nearest(strikes, price)
    if atm is None:
        raise RuntimeError("no common ATM strike")
    call = chain.calls[chain.calls["strike"].astype(float) == atm].iloc[0]
    put = chain.puts[chain.puts["strike"].astype(float) == atm].iloc[0]
    call_mid = mid(call)
    put_mid = mid(put)
    expected = ((call_mid + put_mid) / price * 100) if price > 0 else 0
    front_iv = (safe_float(call.get("impliedVolatility")) + safe_float(put.get("impliedVolatility"))) / 2
    back_iv = ""
    if back:
        try:
            bchain = t.option_chain(back)
            bstrikes = sorted(set(bchain.calls["strike"].astype(float)).intersection(set(bchain.puts["strike"].astype(float))))
            batm = nearest(bstrikes, price)
            if batm is not None:
                bcall = bchain.calls[bchain.calls["strike"].astype(float) == batm].iloc[0]
                bput = bchain.puts[bchain.puts["strike"].astype(float) == batm].iloc[0]
                back_iv = (safe_float(bcall.get("impliedVolatility")) + safe_float(bput.get("impliedVolatility"))) / 2
        except Exception:
            back_iv = ""
    liq, liq_reasons = liquidity_score(call, put)
    return {
        "price": round(price, 2),
        "front_expiry": front,
        "back_expiry": back,
        "atm_strike": atm,
        "atm_call_mid": call_mid,
        "atm_put_mid": put_mid,
        "expected_move_pct": round(expected, 2),
        "front_iv": round(front_iv, 4) if front_iv else "",
        "back_iv": round(back_iv, 4) if isinstance(back_iv, float) and back_iv else "",
        "liquidity_score": liq,
        "liquidity_reasons": liq_reasons,
    }


def classify(row: UniverseRow, snapshot: dict | None, hist_moves: list[float], today: date) -> tuple[str, int, bool, str]:
    status, _delta = event_status(row, today)
    if status == POSTURE_REVIEW:
        return POSTURE_REVIEW, 70, True, "earnings passed yesterday; review expected vs actual move"
    if status == POSTURE_WATCH:
        return POSTURE_WATCH, 0, False, "watchlist only; no near-term earnings event"
    if snapshot is None:
        return "REJECTED_DATA_ERROR", 0, False, "missing option/price data"
    if snapshot["liquidity_score"] < 45:
        return "REJECTED_ILLIQUID", snapshot["liquidity_score"], False, "; ".join(snapshot.get("liquidity_reasons", [])) or "liquidity score too low"

    expected = safe_float(snapshot.get("expected_move_pct"))
    sample_size = len(hist_moves)
    hist_med = median(hist_moves) if hist_moves else 0.0
    front_iv = safe_float(snapshot.get("front_iv"))
    back_iv = safe_float(snapshot.get("back_iv"))
    iv_ratio = (front_iv / back_iv) if front_iv and back_iv else 0

    score = snapshot["liquidity_score"] // 2
    if status == "PRE_EARNINGS_TODAY":
        score += 20
    elif status == "PRE_EARNINGS_TOMORROW":
        score += 18
    else:
        score += 12
    if sample_size >= 4:
        score += 10
    elif sample_size >= 2:
        score += 5

    if hist_med > 0:
        gap = expected - hist_med
        if gap >= 2.0:
            score += 20
            posture = POSTURE_SHORT_VOL
            reason = f"implied move {expected:.1f}% is rich vs historical median {hist_med:.1f}%"
        elif gap <= -2.0:
            score += 20
            posture = POSTURE_LONG_VOL
            reason = f"implied move {expected:.1f}% is cheap vs historical median {hist_med:.1f}%"
        else:
            posture = POSTURE_NO_EDGE
            reason = f"implied move {expected:.1f}% is close to historical median {hist_med:.1f}%"
    else:
        posture = POSTURE_NO_EDGE
        reason = "no earnings-move history yet"

    if iv_ratio >= 1.10 and posture in {POSTURE_NO_EDGE, POSTURE_SHORT_VOL}:
        score += 10
        posture = POSTURE_CALENDAR
        reason += f"; front/back IV ratio {iv_ratio:.2f} suggests event IV term-structure"

    score = min(score, 100)
    send = score >= 70 and posture not in {POSTURE_NO_EDGE, POSTURE_WATCH}
    return posture, score, send, reason


def scan_row(row: UniverseRow, hist: dict[str, list[float]], today: date, ts: str) -> Candidate:
    status, delta = event_status(row, today)
    snapshot = None
    error = ""
    if status != POSTURE_WATCH:
        try:
            snapshot = option_snapshot(row.ticker, row.earnings_date)
        except Exception as e:
            error = str(e)
    hist_moves = hist.get(row.ticker, [])
    posture, score, send, reason = classify(row, snapshot, hist_moves, today)
    if error and posture == "REJECTED_DATA_ERROR":
        reason = error
    hist_med = round(median(hist_moves), 2) if hist_moves else ""
    hist_avg = round(sum(hist_moves) / len(hist_moves), 2) if hist_moves else ""
    front_iv = snapshot.get("front_iv", "") if snapshot else ""
    back_iv = snapshot.get("back_iv", "") if snapshot else ""
    iv_ratio = round(safe_float(front_iv) / safe_float(back_iv), 2) if safe_float(front_iv) and safe_float(back_iv) else ""
    return Candidate(
        scan_timestamp=ts,
        ticker=row.ticker,
        event_status=status,
        earnings_date=row.earnings_date,
        earnings_time=row.earnings_time,
        days_to_earnings=delta,
        price=snapshot.get("price", "") if snapshot else "",
        front_expiry=snapshot.get("front_expiry", "") if snapshot else "",
        back_expiry=snapshot.get("back_expiry", "") if snapshot else "",
        atm_strike=snapshot.get("atm_strike", "") if snapshot else "",
        atm_call_mid=snapshot.get("atm_call_mid", "") if snapshot else "",
        atm_put_mid=snapshot.get("atm_put_mid", "") if snapshot else "",
        expected_move_pct=snapshot.get("expected_move_pct", "") if snapshot else "",
        historical_median_move_pct=hist_med,
        historical_avg_move_pct=hist_avg,
        sample_size=len(hist_moves),
        front_iv=front_iv,
        back_iv=back_iv,
        front_back_iv_ratio=iv_ratio,
        liquidity_score=snapshot.get("liquidity_score", 0) if snapshot else 0,
        edge_score=score,
        posture=posture,
        send_candidate=send,
        reason=reason,
    )


def write_outputs(candidates: list[Candidate], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "candidates.csv"
    json_path = output_dir / "candidates.json"
    rows = [asdict(c) for c in candidates]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def compose_message(candidates: list[Candidate], csv_path: Path) -> str:
    sendable = [c for c in candidates if c.send_candidate]
    if not sendable:
        return "NO_REPLY"
    lines = ["*Earnings Volatility Radar*", ""]
    for c in sorted(sendable, key=lambda x: x.edge_score, reverse=True)[:8]:
        lines.append(f"*{c.ticker}* — {c.posture} / score {c.edge_score}")
        lines.append(f"Event: {c.event_status} {c.earnings_date} {c.earnings_time}")
        lines.append(f"Expected move: {c.expected_move_pct}% | Hist median: {c.historical_median_move_pct or 'n/a'}%")
        lines.append(f"Reason: {c.reason}")
        lines.append("")
    lines.append(f"Output: {csv_path}")
    return "\n".join(lines).strip()


def send_whatsapp(target: str, message: str) -> None:
    if not target or message == "NO_REPLY":
        return
    cmd = ["wacli", "send", "text", "--to", target, "--message", message, "--json"]
    if Path("/opt/homebrew/bin/wacli").exists():
        cmd[0] = "/opt/homebrew/bin/wacli"
    subprocess.run(cmd, check=True, text=True, capture_output=True, timeout=120)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rolling earnings options-volatility radar")
    p.add_argument("--earnings", default=os.getenv("EARNINGS_VOL_RADAR_EARNINGS", str(DEFAULT_EARNINGS)))
    p.add_argument("--watchlist", default=os.getenv("EARNINGS_VOL_RADAR_WATCHLIST", str(DEFAULT_WATCHLIST)))
    p.add_argument("--history", default=os.getenv("EARNINGS_VOL_RADAR_HISTORY", str(DEFAULT_HISTORY)))
    p.add_argument("--output-dir", default=os.getenv("EARNINGS_VOL_RADAR_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
    p.add_argument("--lookahead-days", type=int, default=int(os.getenv("EARNINGS_VOL_RADAR_LOOKAHEAD_DAYS", DEFAULT_LOOKAHEAD_DAYS)))
    p.add_argument("--max-workers", type=int, default=int(os.getenv("EARNINGS_VOL_RADAR_MAX_WORKERS", DEFAULT_MAX_WORKERS)))
    p.add_argument("--send-whatsapp-to", default=os.getenv("EARNINGS_VOL_RADAR_WHATSAPP_TARGET", ""))
    p.add_argument("--today", help="Override today as YYYY-MM-DD for reproducible tests")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    today = parse_date(args.today) if args.today else datetime.now(ZoneInfo("Asia/Jerusalem")).date()
    if today is None:
        raise SystemExit("invalid --today; expected YYYY-MM-DD")
    ts = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M Israel")
    universe = build_universe(Path(args.earnings), Path(args.watchlist), today, args.lookahead_days)
    hist = load_history(Path(args.history))

    candidates: list[Candidate] = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futures = [ex.submit(scan_row, row, hist, today, ts) for row in universe]
        for fut in as_completed(futures):
            candidates.append(fut.result())

    candidates.sort(key=lambda c: (not c.send_candidate, -c.edge_score, str(c.days_to_earnings), c.ticker))
    csv_path, json_path = write_outputs(candidates, Path(args.output_dir))
    message = compose_message(candidates, csv_path)
    send_whatsapp(args.send_whatsapp_to, message)
    print(message)
    print(f"JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
