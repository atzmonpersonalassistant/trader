# Options Trade Lab — Project Plan

## Rule of Engagement

No new task starts until Uriel explicitly approves continuing from the latest completed task.

## Approved Scope

Build a modular research pipeline for challenging and evaluating options trades.

## Task Breakdown

1. **Create project folder** — create `code/options-planning`. ✅ Completed
2. **Define modular architecture** — structure modules for data, features, scanners, backtests, options, reports, config, and tests. 🔄 In review / not yet approved
3. **Move project workflow to GitHub** — manage all project tasks, approvals, code changes, and progress through GitHub issues/branches/PRs.
4. **Create config layer** — central config for universe, thresholds, data sources, risk rules, and backtest assumptions.
5. **Implement market data module** — fetch OHLCV with `yfinance` first, with clean interfaces for IBKR/Polygon/ThetaData later.
6. **Implement feature engine** — compute returns, moving averages, volume ratio, RSI, ATR, historical volatility, and relative strength.
7. **Implement candidate scanner** — rank stocks by momentum, liquidity, volatility setup, and risk filters.
8. **Implement stock-level backtester** — test whether recurring stock setups have directional edge before options are considered.
9. **Implement options proxy module** — Black-Scholes pricing and Greeks for simulated long calls when historical option chains are unavailable.
10. **Implement options strategy selector** — choose candidate option structures based on direction, IV, DTE, liquidity, and risk profile.
11. **Implement reporting layer** — generate Markdown/CSV reports with candidates, rationale, warnings, and possible trades.
12. **Add persistence layer** — store raw data, features, scan results, and backtest results as Parquet/SQLite.
13. **Add tests and validation checks** — unit tests plus guardrails against look-ahead bias and calculation mistakes.
14. **Add CLI entrypoints** — commands like `download-data`, `scan`, `backtest`, and `report`.
15. **Write README and research rules** — document how to run it, what the backtest means, and what not to infer.
16. **Add future integration hooks** — clean interfaces for IBKR, historical options providers, and paper trading.

## Current Status

- Project folder created.
- `PROJECT_PLAN.md` created.
- `ARCHITECTURE.md` drafted.
- Task #2 is still under review and not considered complete until Uriel approves the architecture.
