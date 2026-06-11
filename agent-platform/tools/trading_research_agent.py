#!/usr/bin/env python3
"""Strategy/Quant Research Agent CLI.

This agent does not write code, review PRs, or place trades. It produces and
maintains research hypotheses/specs that a QuantConnect runner can test.
"""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_STATE_DIR = Path("/agents/research/state")
DEFAULT_REPORTS_DIR = Path("/agents/research/reports")
DEFAULT_WORKSPACE_DIR = Path("/agents/research/lean-workspace")
DEFAULT_SHARED_PROJECTS_DIR = Path("/agents/shared/lean-projects")
DEFAULT_SHARED_ARTIFACTS_DIR = Path("/agents/shared/research-artifacts")
DEFAULT_QUEUE_PATH = DEFAULT_STATE_DIR / "strategy-queue.json"



RESEARCH_MANDATE: dict[str, Any] = {
    "status": "draft_from_uriel_2026_06_10_continue_questions_tomorrow",
    "mode": "autonomous_24_7_within_mandate",
    "primary_goal": "Find options-only setups with balanced positive expectancy, validated rigorously before notifying as candidates.",
    "research_scope": {
        "asset_scope": "Anything QuantConnect supports, provided options data/liquidity are adequate for validation.",
        "instrument_scope": "Options only. Ignore good non-options/equity-only setups as candidates.",
        "strategy_scope": "Any options strategy is allowed if the structure fits the setup, risk is defined/measurable, and QC can test it.",
        "structure_selection": "Mixed rule: long-premium structures are allowed when max risk is limited to premium; short-premium structures must be defined-risk; naked shorts are always forbidden; if two similar structures are tied or uncertain, prefer defined-risk.",
        "short_premium": "Allowed only as defined-risk structures such as credit spreads, iron condors, butterflies, and defined-risk calendars/diagonals. Naked short options are forbidden.",
        "complexity_policy": "Any options structure may be researched, but complexity requires stronger justification. Penalize structures that are complex without a clear edge, volatility/time-structure fit, or risk-control reason.",
        "liquidity_prefilter": "Run a quick liquidity check before deep research. If option chain liquidity, spread, volume, or open interest is poor, discard or downgrade to low priority before spending on deep backtests.",
        "zero_dte": "Allowed if backtestable, but must be labeled ultra-short/high execution risk.",
        "initial_timeframe": "Near-term opportunities: days to two weeks.",
        "payoff_objective": "Balanced expectancy: positive expected value with reasonable payoff/risk, drawdown, trade count, and validation quality.",
        "risk_profiles": "All risk profiles may be explored, but every candidate must be labeled conservative/balanced/aggressive or equivalent.",
    },
    "candidate_gate": {
        "candidate_requires_full_validation": "A candidate may be sent to Uriel only after full validation over 2018-present or an equivalent walk-forward/out-of-sample protocol.",
        "watch_policy": "Technically interesting setups without full validation remain internal and should not be sent as watch alerts.",
        "benchmark": "Primary benchmark is S&P 500 / SPY. Add secondary benchmark when obviously relevant.",
        "benchmark_comparisons": ["strategy_vs_SPY", "strategy_vs_underlying_when_relevant", "strategy_vs_naive_options_baseline_when_relevant"],
        "minimum_metrics": [
            "total_return", "max_drawdown", "win_rate", "profit_factor", "expectancy_per_trade",
            "number_of_trades", "average_holding_period", "sharpe", "sortino", "comparison_vs_SPY",
            "worst_period_or_regime", "liquidity_risk", "event_risk", "verdict"
        ],
        "conviction_format": "low/medium/high plus breakdown: setup quality, liquidity risk, backtest evidence, event risk, payoff/risk, and why the structure fits.",
        "low_sample_policy": "Do not automatically discard low-trade/short-history ideas if the thesis is strong; lower conviction and document the limitation.",
        "parameter_stability": "No candidate if performance depends on a single magic parameter; require stability across nearby parameter ranges.",
        "overfitting_policy": "If there is material overfitting suspicion, the idea is not a candidate until it passes OOS, walk-forward, or robustness validation.",
        "parameter_search_disclosure": "Every report must disclose how many variations/parameter combinations were tested, what was selected, and reduce conviction when many trials were needed to find a good result.",
        "correlation_overlap": "Every candidate report must include overlap/correlation versus existing candidates. Do not block research solely because exposure overlaps, but flag repeated bets such as multiple bullish tech/Nasdaq structures.",
        "drawdown_policy": "Judge drawdown relative to strategy profile. Aggressive strategies may tolerate deeper drawdown only if convexity/return justifies it.",
        "regime_specific_policy": "A strategy that works only in one period/regime can be a candidate only if it identifies that regime in advance.",
    },
    "validation_protocol": {
        "qc_default": "QuantConnect/LEAN Cloud is the default validation platform.",
        "concurrency": "One QC cloud backtest at a time with the current single B2-8 backtest node; hypotheses may be planned/scored in parallel.",
        "daily_cap": "No hard daily backtest cap within existing paid resources, but use retry caps, loop guards, and bug stop rules.",
        "backtest_periods": "Use initial/recent diagnostics as needed, but candidates require 2018-present validation or walk-forward/OOS evidence.",
        "execution_scenarios": ["optimistic", "realistic", "conservative"],
        "resolution_policy": "Adaptive: daily for coarse screening; hourly/minute for validation when timing matters; 0DTE/very-short-dated strategies generally require minute-level evidence.",
        "regime_policy": "Adaptive: start with simple bull/bear/sideways tags; if strategy performance is regime-sensitive, deepen into trend, volatility, rates/macro, and sector leadership.",
        "data_quality_policy": "Material data quality problems block candidate status until explained or fixed. If option-chain gaps, bad fills, odd prices, sparse quotes, or recurring data failures appear, open a technical issue.",
        "runtime_policy": "Start with cheap diagnostics, deepen only when there is signal, and if a backtest is stuck/too expensive/repeatedly failing, open an issue and move to another idea.",
        "llm_judgment_policy": "LLM may choose next research steps, propose refinements, explain failures, and assign combined conviction from numbers/context/risk, but may not override weak evidence. Candidates must be evidence-based.",
        "asymmetric_candidate_policy": "Keep a separate asymmetric/speculative candidate category. Huge upside is not enough; it still requires positive expectancy after validation.",
        "optimization_policy": "Parameter optimization may be used as part of adaptive search, but no optimized result can become a candidate without out-of-sample or walk-forward validation, combination-count disclosure, robustness checks, and complexity penalty.",
        "latency_policy": "Quality before speed. Do not reject good research for being slow, but stop/report technical stuck loops or repeated failures.",
        "cost_policy": "Use existing paid QC resources freely. Do not increase subscriptions, nodes, or costs without approval. May open issues/recommend upgrades if bottleneck is clear.",
        "lookahead_policy": "External or market data without clear timestamp/real-time availability may seed hypotheses only; confidence is penalized and candidate status requires a version using only data available at decision time.",
    },
    "external_sources": {
        "allowed": "Any public/legal/cited source may be used to generate hypotheses, including news, filings, earnings calendars, analyst changes, social/sentiment, and public company materials.",
        "forbidden": "No paywall/protected-source scraping and no non-public information.",
        "citation_required": True,
        "evidence_rule": "External context can generate hypotheses but is not proof of edge; QC validation is required before candidate status.",
        "tooling_policy": "Prefer dedicated CLIs/tools for external sources instead of ad-hoc curl. If a new CLI/tool is needed, open a GitHub issue; do not install it silently.",
        "api_key_policy": "If a source requires API key/login, open a GitHub issue and ask Uriel to decide; do not touch secrets independently.",
        "cache_policy": "Retention depends on source: keep QC reports/metrics/failure library/audit trail long-term; filings/public docs may keep raw if evidence; news/social should generally store summaries, links, timestamps, and short-lived cache rather than raw dumps.",
    },
    "notifications_and_governance": {
        "notify_on": "Send WhatsApp for reasonable validated candidates, daily summary, and hourly alive heartbeat if no interesting candidate.",
        "heartbeat_frequency": "Hourly when running, even with no findings, including alive/running-or-idle, hypotheses today, QC status, and current focus.",
        "daily_summary": "Full daily summary: checked, discarded, refine queue, candidates, failures, tomorrow plan, and recommendations to change mandate/caps/universe.",
        "github_permissions": "Research agent may open GitHub issues only. It may not open PRs or trigger coding agent without approval.",
        "paper_trading": "If candidate is strong, open a promote-to-paper GitHub issue. Do not start paper trading automatically.",
        "mandate_changes": "If mandate is blocking/defective, the agent may temporarily adapt within principles to avoid getting stuck, then must open a GitHub issue documenting the problem, temporary deviation, rationale, and proposed permanent mandate change.",
        "reports": "WhatsApp summaries should be concise; full reports should live in files/GitHub artifacts.",
        "audit_trail": "Full audit trail required: prompt/job spec, sources/citations, hypotheses, parameters, QC ids, metrics, decisions, failures, temporary mandate deviations, issues/links.",
        "failure_library": "Keep structured failure summaries and use them to steer future research, avoid repeated disproven ideas, and create new hypotheses when a failure reveals a useful insight.",
        "market_hours_policy": "During regular market hours, focus more on monitoring/candidates/setups relevant now; during closed-market hours, prioritize heavy research, refinement, failure analysis, and reports.",
    },
    "hard_forbidden": [
        "live_trading", "placing_orders", "opening_or_closing_positions", "changing_secrets_or_auth",
        "increasing_costs_or_subscriptions_without_approval", "deleting_state_or_reports",
        "changing_mandate_permanently_without_issue", "opening_PRs_or_triggering_coding_agent_without_approval",
        "naked_short_options", "paywall_or_protected_source_scraping", "using_non_public_information"
    ],
    "open_questions_next": [
        "Question 68 pending: pre-market/after-hours policy. Current recommendation was monitoring/context only, no candidate without regular-session validation.",
        "Any additional sizing/capital assumptions later if Uriel wants position sizing; currently none.",
    ],
}

QC_RESEARCH_PROMPT = """You are the Strategy / Quant Research Agent for the Trader project.

Use QuantConnect as the primary research platform. Prefer Lean CLI and QC Cloud workflows over raw REST when possible. Use REST only for gaps or artifact extraction. Backtests must run in QuantConnect Cloud unless explicitly labeled local diagnostics. Follow RESEARCH_MANDATE exactly; it captures Uriel's current instructions and unresolved questions.

For every hypothesis:
1. Convert the direction into a precise, testable research spec.
2. Run diagnostics first: signal count, option-chain availability, contract counts under filters, rejection reasons, missing Greeks/IV, and trade/event counts by symbol/year/regime.
3. Only run broad backtests after diagnostics show enough data/events.
4. Use QC capabilities deeply: option chains/universes, Greeks/delta/IV, History, indicators, scheduled scanners, cloud backtests, parameters/sweeps, logs/ObjectStore/artifacts where accessible.
5. Save artifacts under /agents/research/reports/<run-id>/ or /agents/shared/research-artifacts/<run-id>/ without secrets.
6. End with a verdict: discard, refine, retest_after_technical_fix, or candidate_for_validator_review.

Do not place live trades. Do not make trade recommendations from weak or technically blocked evidence. If QC access, compute nodes, logs, ObjectStore, or data coverage block the run, say so plainly and recommend the exact next technical step.
"""

def lean_setup_commands(workspace_dir: Path) -> list[str]:
    workspace = shlex.quote(str(workspace_dir))
    return [
        "python3 -m pip install --user --upgrade lean",
        "python3 -m pipx install lean  # acceptable alternative when pipx is available",
        "printf '%s\\n' \"$QUANTCONNECT_API_TOKEN\" | lean login --user-id $QUANTCONNECT_USER_ID",
        f"mkdir -p {workspace} && cd {workspace} && lean init",
        "lean whoami",
    ]


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


def cmd_mandate(args: argparse.Namespace) -> int:
    print(json.dumps({"ok": True, "mandate": RESEARCH_MANDATE}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_qc_prompt(args: argparse.Namespace) -> int:
    payload = {
        "ok": True,
        "prompt": QC_RESEARCH_PROMPT,
        "mandate": RESEARCH_MANDATE,
        "lean_first": True,
        "qc_cloud_default": True,
        "reports_dir": str(Path(args.reports_dir)),
        "workspace_dir": str(Path(args.workspace_dir)),
        "shared_projects_dir": str(DEFAULT_SHARED_PROJECTS_DIR),
        "shared_artifacts_dir": str(DEFAULT_SHARED_ARTIFACTS_DIR),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_qc_lean_setup_plan(args: argparse.Namespace) -> int:
    payload = {
        "ok": True,
        "type": "lean_setup_plan",
        "workspace_dir": str(Path(args.workspace_dir)),
        "shared_projects_dir": str(DEFAULT_SHARED_PROJECTS_DIR),
        "shared_artifacts_dir": str(DEFAULT_SHARED_ARTIFACTS_DIR),
        "credential_env": "/etc/trading-agents/secrets/quantconnect/env",
        "commands": lean_setup_commands(Path(args.workspace_dir)),
        "verification": [
            "command -v lean",
            "lean --version",
            "lean whoami",
        ],
        "notes": [
            "Run as agent-research with HOME=/home/agent-research.",
            "Coding/review roles may edit Lean project files but must not receive raw QuantConnect env access.",
            "Do not print QUANTCONNECT_API_TOKEN or the Lean credentials file.",
            "Cloud backtests should use lean cloud backtest <project> --push.",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research-only strategy agent")
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE_PATH))
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument("--workspace-dir", default=str(DEFAULT_WORKSPACE_DIR))
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed-cheap-calls", help="Seed initial cheap-call research queue")
    seed.set_defaults(func=cmd_seed)
    list_cmd = sub.add_parser("list", help="List research candidates")
    list_cmd.add_argument("--status")
    list_cmd.set_defaults(func=cmd_list)
    next_cmd = sub.add_parser("next", help="Return the next queued research candidate")
    next_cmd.set_defaults(func=cmd_next)
    mandate_cmd = sub.add_parser("mandate", help="Print Uriel's current autonomous research mandate")
    mandate_cmd.set_defaults(func=cmd_mandate)
    prompt_cmd = sub.add_parser("qc-prompt", help="Print the default QC/Lean-first research prompt")
    prompt_cmd.set_defaults(func=cmd_qc_prompt)
    setup_cmd = sub.add_parser("qc-lean-setup-plan", help="Print the Lean/QC setup plan for agent-research")
    setup_cmd.set_defaults(func=cmd_qc_lean_setup_plan)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
