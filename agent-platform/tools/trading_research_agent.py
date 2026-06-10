#!/usr/bin/env python3
"""Strategy/Quant Research Agent CLI.

This agent does not write code, review PRs, or place trades. It produces and
maintains research hypotheses/specs that a QuantConnect runner can test.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_STATE_DIR = Path("/agents/research/state")
DEFAULT_REPORTS_DIR = Path("/agents/research/reports")
DEFAULT_QUEUE_PATH = DEFAULT_STATE_DIR / "strategy-queue.json"


@dataclass(frozen=True)
class StrategyCandidate:
    id: str
    name: str
    priority: int
    family: str
    thesis: str
    structure: str
    universe: list[str]
    entry_rules: list[str]
    exit_rules: list[str]
    risk_controls: list[str]
    required_data: list[str]
    llm_value: str
    pitfalls: list[str]
    minimum_viability: list[str]
    quantconnect_test_spec: dict[str, Any]
    status: str = "queued"


def cheap_call_seed_queue() -> list[StrategyCandidate]:
    """Initial research queue for cheap upside via calls/debit structures."""
    return [
        StrategyCandidate(
            id="qqq-pullback-low-debit-bull-call-spread",
            name="QQQ low-debit bull call spread after pullback",
            priority=1,
            family="bull_call_spread",
            thesis="In an uptrend, a controlled QQQ pullback may offer cheap upside exposure through a debit call spread instead of an expensive outright call.",
            structure="Buy 30-60 DTE call around 0.40-0.55 delta; sell higher strike call around 0.20-0.35 delta.",
            universe=["QQQ"],
            entry_rules=[
                "Underlying above SMA200",
                "3-7% pullback from 20-day high",
                "RSI(14) between 35 and 50",
                "IV percentile <= 60 when available",
                "Debit <= configured cap",
            ],
            exit_rules=[
                "Take profit at 80-120% of debit",
                "Stop at 50% loss of debit",
                "Exit at 14-21 DTE",
                "Exit if underlying closes below SMA200",
            ],
            risk_controls=[
                "Max loss is net debit",
                "No averaging down",
                "One open trade per underlying",
                "Portfolio debit exposure cap",
            ],
            required_data=["QQQ equity history", "QQQ option chain", "Greeks/delta", "IV or proxy"],
            llm_value="Selects hypotheses/regime explanations and interprets failure modes; deterministic engine handles signals, fills, and metrics.",
            pitfalls=[
                "Theta decay may dominate",
                "Backtest may rely on mid fills that are not realistic",
                "Result may be concentrated in a single bull market year",
                "Signal uses close; fills must occur no earlier than next bar/session",
            ],
            minimum_viability=[
                "30+ trades",
                "Positive expectancy after costs/slippage",
                "Out-of-sample Sharpe > 0.5",
                "No single year explains most profit",
                "Drawdown acceptable versus debit exposure",
            ],
            quantconnect_test_spec={
                "algorithm_template": "cheap_call_debit_spread",
                "underlying": "QQQ",
                "strategy": "bull_call_spread",
                "min_dte": 30,
                "max_dte": 60,
                "buy_delta_range": [0.40, 0.55],
                "sell_delta_range": [0.20, 0.35],
                "pullback_from_20d_high_pct": [3, 7],
                "rsi_range": [35, 50],
            },
        ),
        StrategyCandidate(
            id="spy-cheap-momentum-long-call-iv-filter",
            name="SPY cheap momentum long call with IV filter",
            priority=2,
            family="long_call",
            thesis="Outright calls only deserve testing when momentum is strong and implied volatility is not already expensive.",
            structure="Buy 45-75 DTE call around 0.30-0.45 delta with premium cap.",
            universe=["SPY"],
            entry_rules=[
                "SPY above SMA50 and SMA200",
                "Close above 20-day high",
                "MACD positive or momentum improving",
                "IV percentile < 50 when available",
                "Option premium <= configured cap",
            ],
            exit_rules=["Take profit at 100-150%", "Stop at 50% loss", "Exit below SMA50", "Exit at 21 DTE"],
            risk_controls=["Max loss is premium", "No averaging down", "Small fixed debit per trade"],
            required_data=["SPY equity history", "SPY option chain", "Greeks/delta", "IV or proxy"],
            llm_value="Frames when long calls are structurally sensible instead of blindly buying lottery tickets.",
            pitfalls=["Low win rate can hide negative expectancy", "Theta decay", "IV crush after entry", "Survivorship/regime concentration"],
            minimum_viability=["Positive convex payoff after costs", "Profit factor >= 1.1", "30+ trades", "Robust across DTE/delta variations"],
            quantconnect_test_spec={
                "algorithm_template": "cheap_long_call",
                "underlying": "SPY",
                "strategy": "long_call",
                "min_dte": 45,
                "max_dte": 75,
                "delta_range": [0.30, 0.45],
                "breakout_lookback_days": 20,
            },
        ),
        StrategyCandidate(
            id="qqq-bollinger-squeeze-bull-call-spread",
            name="QQQ bull call spread after Bollinger squeeze breakout",
            priority=3,
            family="bull_call_spread",
            thesis="After volatility compression, a QQQ upside breakout may produce enough directional movement for a low-debit call spread.",
            structure="Buy 30-45 DTE call near 0.50 delta; sell call near 0.25-0.30 delta.",
            universe=["QQQ"],
            entry_rules=["Bollinger bandwidth percentile < 25", "Bandwidth expanding", "Close above upper band or 20-day high", "Price above SMA100", "IV percentile <= 60"],
            exit_rules=["Take profit at 80-100%", "Stop at 40-50% loss", "Exit if breakout level fails", "Max hold 15-25 trading days"],
            risk_controls=["Debit-only risk", "One open trade per ETF"],
            required_data=["QQQ equity history", "QQQ option chain", "Bollinger bandwidth", "Greeks/delta"],
            llm_value="Identifies breakout/squeeze hypothesis families and interprets fakeout regimes after reports.",
            pitfalls=["Fakeouts", "Poor fills", "Overfit bandwidth thresholds"],
            minimum_viability=["Out-of-sample positive expectancy", "Drawdown controlled", "Parameter robustness around bandwidth threshold"],
            quantconnect_test_spec={
                "algorithm_template": "squeeze_call_spread",
                "underlying": "QQQ",
                "strategy": "bull_call_spread",
                "min_dte": 30,
                "max_dte": 45,
                "bandwidth_percentile_max": 25,
            },
        ),
    ]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def load_queue(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def cmd_seed(args: argparse.Namespace) -> int:
    queue_path = Path(args.queue)
    existing = {item["id"]: item for item in load_queue(queue_path)}
    for candidate in cheap_call_seed_queue():
        existing.setdefault(candidate.id, asdict(candidate))
    queue = sorted(existing.values(), key=lambda item: (item.get("priority", 999), item["id"]))
    write_json(queue_path, queue)
    print(json.dumps({"ok": True, "queue": str(queue_path), "count": len(queue)}, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    queue = load_queue(Path(args.queue))
    if args.status:
        queue = [item for item in queue if item.get("status") == args.status]
    print(json.dumps({"ok": True, "count": len(queue), "candidates": queue}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    queue = load_queue(Path(args.queue))
    queued = [item for item in queue if item.get("status") == "queued"]
    if not queued:
        print(json.dumps({"ok": True, "type": "none"}, ensure_ascii=False, sort_keys=True))
        return 0
    candidate = sorted(queued, key=lambda item: (item.get("priority", 999), item["id"]))[0]
    print(json.dumps({"ok": True, "type": "candidate", "candidate": candidate}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research-only strategy agent")
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE_PATH))
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed-cheap-calls", help="Seed initial cheap-call research queue")
    seed.set_defaults(func=cmd_seed)
    list_cmd = sub.add_parser("list", help="List research candidates")
    list_cmd.add_argument("--status")
    list_cmd.set_defaults(func=cmd_list)
    next_cmd = sub.add_parser("next", help="Return the next queued research candidate")
    next_cmd.set_defaults(func=cmd_next)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
