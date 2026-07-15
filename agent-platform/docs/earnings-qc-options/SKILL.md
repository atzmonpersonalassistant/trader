---
name: earnings-qc-options-scan
description: Active QC/LEAN-only earnings options research loop for Uriel's Trader VPS. Use when searching for earnings run-up option candidates, iterating scanner parameters, running Nasdaq→QC→multi-year option-PnL workflows, or using the earnings-qc-research CLI to find final trade candidates.
---

# Earnings QC Options Research Loop

This is an **active research skill**, not a one-shot scanner.

Use the CLI as a resumable, database-backed research instrument: inspect Postgres history/insights first, run the Nasdaq→QC→historical-PnL workflow, document decisions, adjust guardrailed parameters, rerun or resume from a stage, and continue until either final QC/EODHD-backed candidates emerge or the reasonable search space is exhausted.

Research only: no live trading and no broker orders.

## Canonical CLI

Use one canonical CLI for the full flow. Start historical validation with one year unless Uriel asks for a wider window, then expand explicitly (for example to 10 years) and document the decision:

```bash
/agents/research/bin/earnings-qc-research run --campaign earnings-runup-cheap-calls --parallel 1 --years 1 --end-to-end
```

This CLI owns the complete workflow:

1. fetch Nasdaq public earnings calendar for `today+21` through `today+28`
2. cache/normalize the forward earnings universe
3. split the universe into chunks
4. run QC/LEAN option-chain/Greeks/liquidity diagnostics per chunk
5. run QC/EODHD multi-year historical option-PnL validation for forward candidates
6. aggregate funnel counts, blockers, final candidates, and reports

The public interface is intentionally one CLI. Stage-specific code may exist internally under `libexec`, but agents and users should not call it directly.

## Database-backed research memory

PostgreSQL (`trader_research`, schema `earnings_cache`) is part of the research loop. The CLI records campaigns, runs, stages, artifacts, candidate dossiers, decisions, and cleanup runs.

Before changing parameters or launching a new run, inspect what is already known:

```bash
/agents/research/bin/earnings-qc-research status --campaign earnings-runup-cheap-calls --pretty
/agents/research/bin/earnings-qc-research history --campaign earnings-runup-cheap-calls --last 10 --pretty
/agents/research/bin/earnings-qc-research insights --campaign earnings-runup-cheap-calls --pretty
```

Use DB history to look for repeated bottlenecks, promising forward-only leads, years already tested, and parameter changes that helped or hurt. Prefer extracting leads from prior candidate dossiers before widening the search blindly.

## Runtime invocation

Run the canonical CLI in the Trader research environment as the research user:

```bash
/agents/research/bin/earnings-qc-research run --parallel 1 --end-to-end
```

Environment-specific hostnames, SSH keys, usernames, and private paths are intentionally kept out of this repo. Use the private local OpenClaw skill wrapper for VPS invocation.

Prefer `--parallel 1` while experimenting with QC Cloud reliability/cost.

## Non-negotiables

- Nasdaq is only the first-stage forward earnings calendar source.
- Nasdaq access is deterministic code inside the CLI, not LLM browsing/manual extraction.
- Steps after calendar must use QC/LEAN evidence only: option chains, bid/ask, Greeks, IV, liquidity, prices, historical earnings events, and option PnL.
- Do not use Yahoo/yfinance unless Uriel explicitly approves a one-off diagnostic.
- Do not promote a trade without QC/EODHD multi-year historical option-PnL evidence.
- Default exit rule: pre-earnings run-up trade; exit before earnings. Do not hold through earnings unless explicitly running a separately-labeled variant.
- If a source/stage is unavailable, report a blocker; do not fake data.

## Dynamic research knobs

The CLI supports guardrailed environment knobs. The agent may vary these during research sweeps:

- `QC_MAX_PREMIUM` default `0.50`, allowed `0.01..5.00`
- `QC_MIN_BID` default `0.05`, allowed `0.00..5.00`
- `QC_MAX_SPREAD_PCT` default `0.60`, allowed `0.01..5.00`
- `QC_MIN_RELATIVE_SPREAD` default `0.25`, allowed `0.00..5.00`
- `QC_VOL_SPREAD_FACTOR` default `0.50`, allowed `0.00..10.00`
- `QC_EXPECTED_MOVE_SPREAD_FRACTION` default `0.15`, allowed `0.00..5.00`

Example:

```bash
sudo -n -u agent-research env \
  HOME=/home/agent-research \
  PYTHONDONTWRITEBYTECODE=1 \
  QC_MAX_PREMIUM=0.75 \
  QC_MIN_BID=0.02 \
  /agents/research/bin/earnings-qc-research run --parallel 1 --end-to-end
```

Effective tuning is recorded in output and Postgres. Compare runs by campaign, run id, run directory, years, and tuning.

When changing knobs, document the rationale before or immediately after running:

```bash
/agents/research/bin/earnings-qc-research decision add \
  --campaign earnings-runup-cheap-calls \
  --actor llm \
  --type relax_min_bid \
  --rationale "Previous runs repeatedly blocked at min bid while otherwise finding cheap calls" \
  --parameter-changes-json '{"QC_MIN_BID":{"from":0.05,"to":0.02}}'
```

## Research loop

When asked to search for candidates:

1. Read `status`, `history`, and `insights` for the campaign.
2. Start new historical validation with `--years 1` unless Uriel explicitly asks for a wider window.
3. If a one-year result is interesting, document the decision and extend the same run with `historical --years 10 --run-dir <run_dir>` or `run --from-stage historical_option_pnl --years 10 --run-dir <run_dir>`.
4. Read the latest run dir from `/agents/research/state/earnings-qc-options-scan/latest-full-run.txt` only as a fallback if DB history is unavailable.
5. Inspect funnel and blockers:
   - Nasdaq universe count
   - QC option chain availability
   - expiry within 0–7 days after earnings
   - calls under configured max premium
   - liquidity/Greeks gate pass
   - multi-year option-PnL pass/fail
   - final candidates
6. If no candidates, diagnose the bottleneck:
   - too few contracts under premium → consider raising `QC_MAX_PREMIUM`
   - too many low-bid failures → consider lowering `QC_MIN_BID` carefully
   - spread too strict → consider spread knobs carefully
   - missing Greeks/IV → do not bypass blindly; may indicate QC data limitation
   - historical option-PnL fails → do not promote; refine parameters or conclude no trade
7. Stop stale runs before starting a replacement run to avoid wasting QC.
8. Rerun with one controlled parameter change at a time when practical.
9. Continue until final candidates appear or a clear no-trade conclusion is supported.

## Resume and stage expansion

Use the same public CLI to continue work from an existing run:

```bash
/agents/research/bin/earnings-qc-research run --campaign earnings-runup-cheap-calls --run-dir <run_dir> --resume --parallel 1 --years 1 --end-to-end
/agents/research/bin/earnings-qc-research historical --campaign earnings-runup-cheap-calls --run-dir <run_dir> --years 10
/agents/research/bin/earnings-qc-research run --campaign earnings-runup-cheap-calls --run-dir <run_dir> --from-stage historical_option_pnl --years 10
```

Every historical year window is recorded as its own stage name, e.g. `historical_option_pnl_years_1` and `historical_option_pnl_years_10`.

## Cleanup

No cron is installed. Run cleanup manually/agent-driven when useful:

```bash
/agents/research/bin/earnings-qc-research cleanup --older-than-days 14 --keep-last 20 --dry-run
/agents/research/bin/earnings-qc-research cleanup --older-than-days 14 --keep-last 20
```

Cleanup removes old report directories but keeps DB history and key summaries/artifacts tracked in Postgres.

## Optimize for chance of success vs profit

Do not merely loosen filters until something appears. Optimize for expected trade quality:

- probability of success / win rate
- mean and median return
- max loss and drawdown
- sample size and robustness across windows/regimes
- premium paid vs required move
- spread/slippage and tradability
- consistency of historical option-PnL, not just one exceptional event

A candidate with a lower headline return but better robustness, smaller drawdown, better liquidity, and stronger median outcome may be preferable to a high-upside fragile candidate.

## Final candidate standard

A final candidate must have:

- forward earnings event from Nasdaq calendar
- QC option chain available
- expiry after earnings and no more than 7 calendar days after earnings
- call ask <= configured max premium
- liquidity/Greeks gate pass
- QC/EODHD historical earnings events available
- multi-year QC/LEAN historical option-PnL pass under the configured pre-earnings exit rule
- explicit metrics: sample size, win rate, median/mean return, drawdown, max loss, and exit timing/slippage

Forward-only watchlists are allowed only if explicitly labeled as not final trade candidates.

## Reporting style

WhatsApp reports should be concise Hebrew:

- current run dir
- current offset / progress
- funnel counts
- active bottleneck
- final candidates, if any
- next parameter change, if continuing

Do not spam empty daily reports. Notify candidates or meaningful blockers.
