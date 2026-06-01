# Trader

Trading tools and experiments. This repo is organized by project: each top-level project directory contains its own scanner, wrapper, config/example files, outputs, and README.

## Projects

### `options-radar/`

Scanner for low-priced option contracts across a local ticker universe.

- Main docs: `options-radar/README.md`
- Main script: `options-radar/scan.py`
- Scheduler wrapper: `options-radar/run.sh`
- Outputs: `options-radar/output/options-radar.csv`, `options-radar/output/options-radar.json`, and optional WhatsApp summary to the Options radar group
- Universe example: `options-radar/universe.example.csv`

### `market-radar/`

RSS-only market-news radar that scores and deduplicates high-value market items.

- Main docs: `market-radar/README.md`
- Main script: `market-radar/scan.py`
- Scheduler wrapper: `market-radar/run.sh`
- Outputs: `market-radar/output/market_radar_state.json`, `market-radar/output/market_radar_cron.log`, and optional WhatsApp summary to the Market Radar group


### `earnings-volatility-radar/`

Rolling earnings options-volatility radar. It dynamically builds a daily universe from upcoming earnings plus a fixed watchlist, estimates expected moves from ATM straddles, compares them with local earnings-move history, and classifies candidates for manual review.

- Main docs: `earnings-volatility-radar/README.md`
- Main script: `earnings-volatility-radar/scan.py`
- Scheduler wrapper: `earnings-volatility-radar/run.sh`
- Outputs: `earnings-volatility-radar/output/candidates.csv`, `earnings-volatility-radar/output/candidates.json`, and optional WhatsApp summary to the Options radar group


### `ibkr-client/`

Read-only Interactive Brokers connectivity utilities for **IB Gateway only**. Starts with local Paper Trading checks only: managed accounts, account summary, positions, and one quote snapshot.

- Main docs: `ibkr-client/README.md`
- Main script: `ibkr-client/client.py`
- Outputs: stdout by default, or `ibkr-client/output/client.json` when `--output` is supplied

### `options-trade-lab/`

Research/planning docs for the broader Options Trade Lab idea. Currently no runtime output; planned future outputs live under `options-trade-lab/data/results/` and `options-trade-lab/reports/`.

Legacy scanner code from the old `legacy/options-trade-lab-scanner` folder was intentionally removed from this repo structure; active scanner work should live in a dedicated top-level project directory.

## Safety

These tools are for research and alerting only. Information only, not investment advice. Verify quotes, liquidity, bid/ask spreads, and risk manually before any trade.
