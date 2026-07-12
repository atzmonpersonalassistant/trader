---
name: earnings-qc-options-scan
description: QC/LEAN-only earnings options scanner for Uriel's Trader VPS. Use when scanning companies reporting in 21-28 days for long OTM calls up to $0.50, building funnel counts, validating option chains/Greeks/liquidity through QuantConnect only, or configuring the daily Trader cron/job for this earnings run-up strategy.
---

# Earnings QC Options Scan

Use this skill for Uriel's daily earnings run-up options scanner.

## Non-negotiables

- **Only Step 1 uses Nasdaq.** Use the free Nasdaq public earnings calendar API only to build the first-stage forward earnings universe for companies reporting in 21-28 calendar days.
- Label Nasdaq calendar rows explicitly as `source=nasdaq_public_calendar`; this is a free public endpoint, not QC evidence and not a guaranteed commercial feed.
- **Steps 2-6 must use QC/LEAN evidence.** Option chain availability, expiries, pricing, bid/ask, volume/open interest, Greeks/IV, historical prices, historical run-up calculations, funnel validation, candidate/watchlist evidence, and backtest price/option evidence must come from QC/LEAN.
- Historical run-up may use Nasdaq's `last_year_report_date` only as the event-date anchor from Step 1. The run-up price data and return calculation must be from `QCAlgorithm.history` / QC/LEAN, not Nasdaq and not Yahoo.
- For multi-year historical backtesting, use **QC/EODHDUpcomingEarnings** as the approved historical earnings event-date source. A live QC probe on 2026-07-12 confirmed historical events from 2018-2026 for AAPL/MSFT/AMD/NVDA/PLTR. QC/LEAN remains the source for historical prices/options and now also the approved source for historical earnings event dates when EODHDUpcomingEarnings data is available. If QC/EODHDUpcomingEarnings is unavailable for a symbol/window, mark that symbol/window as blocked; do not fake dates silently.
- Do **not** use Yahoo/yfinance for earnings calendar, option chain, Greeks, liquidity, IV, prices, or historical earnings-run-up validation unless Uriel explicitly approves it for a one-off diagnostic.
- If Nasdaq calendar retrieval fails, fall back only to another explicitly approved free source or stop with a blocker; do not silently revert to Yahoo.
- If QC batch diagnostics are not implemented or cannot run after the Nasdaq calendar stage, report `BLOCKED_QC_BATCH_NOT_READY`; do not produce a Yahoo-based funnel.
- Research only: no live trading, no broker orders.
- WhatsApp reports should be concise Hebrew.

## Current VPS

SSH pattern:

```bash
ssh -i ~/.ssh/ovh_vps_ce2ba5e7 -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=15 ubuntu@144.217.82.149 '<command>'
```

Run as `agent-research` for research jobs and `agent-orchestrator` for outbox.

## Workflow

1. **Nasdaq-only calendar step:** Generate the first-stage universe from Nasdaq public earnings calendar API for `today+21` through `today+28`.
   - Endpoint pattern: `https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD`.
   - Use browser-like headers (`User-Agent`, `Accept`, `Origin`, `Referer`) and cache each fetched date locally.
   - Normalize `time-after-hours` / `time-pre-market` / `time-not-supplied`, EPS forecast, analyst count, market cap, fiscal quarter, company name, and `last_year_report_date` when present.
2. **Chunked QC end-to-end execution:** After the Nasdaq calendar stage, split the universe into small chunks and run each chunk through the full QC pipeline. Default to conservative QC concurrency, currently `parallel=2`, and only increase after observing stable QC compile/backtest behavior, rate limits, and runtime-stat output size.
   - The VPS is only the orchestrator: chunk scheduling, retry, aggregation, and reporting.
   - QC/LEAN Cloud is responsible for all option-chain, Greeks/liquidity, historical event, and historical option-PnL evidence.
   - Each chunk should be independently retryable; a failed chunk must not require rerunning the whole universe.
3. **QC-only option availability + near-expiry filter, per chunk:** Run QC/LEAN diagnostics for option chain availability and keep only call contracts expiring after the earnings date but no later than **7 calendar days after earnings**. Do not select first/second expiry if it is more than 7 days after the report.
4. **QC-only cheap call filter, per chunk:** Filter long calls using QC option-chain data only: ask <= $0.50, bid/ask, volume/open interest, Greeks/IV when available. Do **not** require a fixed OTM threshold such as 3% before this step. Instead, compute each contract's `required_move_pct = strike / spot - 1` and carry it forward.
5. **QC-only liquidity/Greeks quality filter, per chunk:** For each cheap call, record and score the exact liquidity inputs: bid, ask, mid, absolute spread, spread/mid %, volume, open interest, IV, delta, DTE, and whether volume is zero. Prefer explicit pass/fail reasons over a generic `liquidity_pass` boolean.
6. **Mandatory QC/EODHD multi-year option-PnL backtesting up to 10 years, per chunk — the historical gate:** For forward candidates that pass option availability, expiry, cheap-call, and liquidity/Greeks evidence inside a chunk, query historical earnings events through QC/EODHDUpcomingEarnings and test configurable lookback windows: 1y, 3y, 5y, and up to 10y when data exists. This is the historical validation gate. For each historical event, use QC/LEAN prices/options to simulate the same rule family:
   - event dates from QC/EODHDUpcomingEarnings only
   - buy window / observation window before earnings
   - expiry after earnings but no later than 7 calendar days after earnings
   - ask <= $0.50 or the closest historical equivalent rule
   - required move based on selected contract's strike/spot
   - liquidity/Greeks evidence when available historically
   - max loss, win rate, median/mean return, drawdown, and sample size
   If QC/EODHDUpcomingEarnings has insufficient events for a symbol/window, report a symbol/window-level blocker such as `BLOCKED_QC_EODHD_HISTORICAL_EVENTS_INSUFFICIENT` or `BLOCKED_HISTORICAL_OPTION_SAMPLE_INSUFFICIENT`; do not fake dates silently. Do not promote final candidates without multi-year option-PnL evidence unless Uriel explicitly asks for a forward-only watchlist.
   - Optional report/debug context: when `last_year_report_date` is available from Nasdaq, the report may include the prior single-year pre-earnings equity run-up versus the current contract's `required_move_pct`, but this must never be a pipeline stage, hard filter, or candidate gate.
7. **QC-derived funnel + watchlist aggregation:** Produce funnel counts and candidate/watchlist from the chunk-validated results:
   - Nasdaq earnings calendar universe
   - QC option chain available
   - QC expiry within 0-7 days after earnings
   - QC calls ask <= $0.50
   - QC liquidity/Greeks quality pass
   - QC/EODHD historical events available
   - mandatory QC/EODHD historical option-PnL backtest pass or explicit symbol/window blocker
   - QC final candidate/watchlist only after multi-year option-PnL evidence passes
8. Notify only candidates or blockers. No empty daily spam.

## Bundled scripts

- `scripts/run_earnings_qc_scan.sh`: wrapper that runs the VPS scanner and enforces the no-Yahoo guard.
- VPS runner should prefer `/agents/research/bin/earnings-qc-options-full-scan run --parallel 2 --end-to-end` or equivalent defaults. Keep QC concurrency conservative until measured stable; increase only after reviewing failed chunks, QC rate/compile stability, runtime-stat truncation, and total wall-clock time.

When setting cron, invoke the script/wrapper; do not run old ad-hoc yfinance scanner.
