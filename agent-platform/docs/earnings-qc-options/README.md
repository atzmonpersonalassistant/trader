# Earnings QC Options Scan

This directory tracks the production scripts and skill spec for Uriel's QC/LEAN-only earnings options scanner.

Runtime deployment target on the Trader VPS:

- `/agents/research/bin/earnings-qc-research`

Research state is persisted in PostgreSQL database `trader_research`, schema `earnings_cache`.

High-level flow:

1. VPS fetches Nasdaq forward earnings calendar for companies reporting in 21-28 days.
2. VPS chunks the universe and orchestrates QC Cloud runs with conservative concurrency.
3. QC Cloud runs option availability, expiry, cheap-call, liquidity/Greeks, historical events, and historical option-PnL checks.
4. VPS records campaign/run/stage/candidate/decision state in Postgres.
5. VPS aggregates chunk outputs and reports only final candidates or blockers.
6. LLM/agent can inspect `status`, `history`, and `insights`, document decisions, resume a run, expand historical PnL from 1 year to wider windows, and run cleanup.

See `SKILL.md` for the authoritative rules and guardrails.
