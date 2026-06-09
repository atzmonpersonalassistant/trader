# Options Planning

Research-first options trading planning workspace for challenging, scanning, and evaluating options trade ideas before risking capital.

## Current Scope

Build a modular research pipeline for:

- market data ingestion
- feature generation
- candidate scanning
- stock-level signal validation
- options pricing/proxy analysis
- strategy selection
- backtest/report generation

This is **not** a live-trading system. Live execution is explicitly out of scope until approved.

## Project Files

- `PROJECT_PLAN.md` — task list and approval workflow.
- `ARCHITECTURE.md` — proposed modular architecture.
- `context/` — conversation-derived context, preferences, lessons, and source-of-truth notes.
- `docs/` — strategy/system design docs.

## Legacy Radar Cleanup

The old standalone scanner folders were removed from this repo:

- `earnings-volatility-radar/`
- `market-radar/`
- `options-radar/`

Future scanner work should be implemented under the coherent `planning/` structure, not as separate top-level radar projects.

## Outputs

This project is currently a research/planning folder, not a runnable scanner. It does not generate runtime outputs yet.

The intended future output locations, according to `ARCHITECTURE.md`, are:

- `planning/data/results/` — scan and backtest output artifacts.
- `planning/reports/daily/` — generated daily candidate reports.
- `planning/reports/backtests/` — generated backtest reports.

When implementation starts, generated data/results/reports should be clearly documented here and ignored/tracked intentionally in `.gitignore`.

## Workflow Rule

No new task starts until Uriel explicitly approves continuing from the latest completed task.

Project work should move through GitHub issues, branches, and pull requests so planning, code changes, and approvals stay auditable.
