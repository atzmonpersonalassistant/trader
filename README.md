# trader

Trading tools and experiments.

## Options Radar

Local option-chain scanner for low-priced contracts. It does **not** depend on Google Sheets.

### Setup

```bash
cp config/universe.example.csv config/universe.csv
```

Edit `config/universe.csv` with the tickers you want to scan.

### Run manually

```bash
uv run --with yfinance --with pandas python scripts/options_radar_scan.py --ignore-market-window
```

Outputs are written to:

- `output/options-radar.csv`
- `output/options-radar.json`

### Scheduler wrapper

```bash
bin/run_options_radar.sh
```

The wrapper is intended for launchd/cron. By default it runs only on weekdays, at minutes `05` and `35`, between local hours `16:00-22:00`.

Useful environment variables:

- `OPTIONS_RADAR_UNIVERSE` — path to universe CSV
- `OPTIONS_RADAR_OUTPUT_DIR` — output directory
- `OPTIONS_RADAR_MAX_PRICE` — max ask/mid filter, default `0.30`
- `OPTIONS_RADAR_WHATSAPP_TARGET` — optional WhatsApp target for sending the summary
- `OPTIONS_RADAR_LOG_FILE` — log file used by the wrapper
- `OPTIONS_RADAR_IGNORE_WRAPPER_WINDOW=1` — bypass wrapper time gate

Information only, not investment advice.

## Market Radar

RSS-only market-news radar. It fetches market RSS feeds, scores relevant items, deduplicates stories, stores seen item IDs locally, and optionally sends a concise WhatsApp summary.

```bash
MARKET_RADAR_IGNORE_MARKET_WINDOW=1 uv run python scripts/market_radar_scan.py --ignore-market-window
```

Runtime files are written under `output/` by default:

- `output/market_radar_state.json`
- `output/market_radar_cron.log`

Useful environment variables:

- `MARKET_RADAR_WHATSAPP_TARGET` — optional WhatsApp target for sending summaries
- `MARKET_RADAR_STATE_PATH` — state file path
- `MARKET_RADAR_LOG_FILE` — wrapper log file
- `MARKET_RADAR_IGNORE_MARKET_WINDOW=1` — bypass script market-hours gate
- `MARKET_RADAR_IGNORE_WRAPPER_WINDOW=1` — bypass wrapper time gate

RSS only — no YouTube and no independent stock scanning.
