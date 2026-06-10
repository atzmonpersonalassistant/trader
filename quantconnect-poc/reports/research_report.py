#!/usr/bin/env python3
"""Generate a small Markdown verdict from exported/mocked QuantConnect metrics."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ResearchVerdict:
    verdict: str
    reasons: list[str]


def _as_float(metrics: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = metrics.get(key, default)
    if isinstance(value, dict):
        value = value.get("value", default)
    if isinstance(value, str):
        value = value.replace("%", "").replace(",", "").strip()
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def validate_config(config: dict[str, Any]) -> None:
    if config.get("live_trading"):
        raise ValueError("POC must not enable live_trading")
    if config.get("underlying", "SPY") not in {"SPY", "QQQ"}:
        raise ValueError("underlying must be SPY or QQQ")
    if config.get("strategy", "bear_call") not in {"bear_call", "bull_put"}:
        raise ValueError("strategy must be bear_call or bull_put")
    max_risk = float(config.get("max_risk_fraction", 0.005))
    if max_risk <= 0 or max_risk > 0.02:
        raise ValueError("max_risk_fraction must be >0 and <=0.02 for POC")


def evaluate(metrics: dict[str, Any]) -> ResearchVerdict:
    trades = int(_as_float(metrics, "trade_count", _as_float(metrics, "Total Trades", 0)))
    sharpe = _as_float(metrics, "sharpe", _as_float(metrics, "Sharpe Ratio", 0))
    drawdown = abs(_as_float(metrics, "max_drawdown_pct", _as_float(metrics, "Drawdown", 100)))
    profit_factor = _as_float(metrics, "profit_factor", _as_float(metrics, "Profit Factor", 0))

    reasons: list[str] = []
    if trades < 30:
        reasons.append("too few trades for statistical confidence (<30)")
    if sharpe < 0.5:
        reasons.append("out-of-sample/overall Sharpe below 0.5 threshold")
    if drawdown > 20:
        reasons.append("max drawdown above 20%")
    if profit_factor and profit_factor < 1.1:
        reasons.append("profit factor below 1.1")

    if reasons:
        return ResearchVerdict("discard_or_refine", reasons)
    return ResearchVerdict("paper_test_candidate", ["basic metrics pass minimum POC thresholds"])


def render_report(config: dict[str, Any], metrics: dict[str, Any]) -> str:
    validate_config(config)
    verdict = evaluate(metrics)
    lines = [
        "# QuantConnect Options POC Research Report",
        "",
        "Research only. Not a trade recommendation and not approved for live trading.",
        "",
        "## Hypothesis",
        config.get("hypothesis", "Defined-risk ETF credit spread can harvest elevated option premium with controlled downside."),
        "",
        "## Parameters",
    ]
    for key in sorted(config):
        if "secret" in key.lower() or "token" in key.lower():
            continue
        lines.append(f"- {key}: `{config[key]}`")
    lines.extend(["", "## Metrics"])
    for key in sorted(metrics):
        lines.append(f"- {key}: `{metrics[key]}`")
    lines.extend(["", "## Verdict", f"**{verdict.verdict}**", ""])
    for reason in verdict.reasons:
        lines.append(f"- {reason}")
    lines.extend([
        "",
        "## Required next checks",
        "- Verify no look-ahead bias: signals using close must trade next bar/session.",
        "- Include commissions, bid/ask spread, and slippage assumptions.",
        "- Run walk-forward/out-of-sample periods before considering paper trading.",
        "- Keep max loss per spread and total portfolio exposure explicit.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text())
    metrics = json.loads(Path(args.metrics).read_text())
    Path(args.output).write_text(render_report(config, metrics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
