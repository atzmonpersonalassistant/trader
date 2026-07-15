# Earnings QC Options Scan

This directory tracks the production scripts and skill spec for Uriel's QC/LEAN-only earnings options scanner.

Runtime deployment target on the Trader VPS:

- `/agents/research/bin/earnings-qc-research`

High-level flow:

1. VPS fetches Nasdaq forward earnings calendar for companies reporting in 21-28 days.
2. VPS chunks the universe and orchestrates QC Cloud runs with conservative concurrency.
3. QC Cloud runs option availability, expiry, cheap-call, liquidity/Greeks, historical events, and historical option-PnL checks.
4. VPS aggregates chunk outputs and reports only final candidates or blockers.

See `SKILL.md` for the authoritative rules and guardrails.
