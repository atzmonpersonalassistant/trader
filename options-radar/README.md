# Options Radar

Local scanner for low-priced options contracts.

It reads a local ticker universe CSV, scans option chains with `yfinance`, writes CSV/JSON outputs, and can optionally send a concise WhatsApp summary.

## Files

- `scan.py` — main scanner.
- `run.sh` — launchd/cron-friendly wrapper with weekday/time gates.
- `universe.example.csv` — example ticker universe.
- `output/` — generated scanner outputs and local runtime artifacts.

## Setup

Create your local universe file:

```bash
cp options-radar/universe.example.csv options-radar/universe.csv
```

Edit `options-radar/universe.csv` with the tickers you want scanned.

## Run manually

From the repo root:

```bash
uv run --with yfinance --with pandas python options-radar/scan.py \
  --universe options-radar/universe.csv \
  --output-dir options-radar/output \
  --ignore-market-window
```

Or with the example universe:

```bash
uv run --with yfinance --with pandas python options-radar/scan.py \
  --universe options-radar/universe.example.csv \
  --output-dir options-radar/output \
  --ignore-market-window
```

## Scheduler wrapper

```bash
options-radar/run.sh
```

The wrapper resolves paths relative to this directory. By default it runs only on weekdays, at minutes `05` and `35`, between local hours `16:00-22:00`.

Useful environment variables:

- `OPTIONS_RADAR_UNIVERSE` — path to universe CSV.
- `OPTIONS_RADAR_OUTPUT_DIR` — output directory.
- `OPTIONS_RADAR_MAX_PRICE` — max ask/mid filter, default `$0.30`.
- `OPTIONS_RADAR_WHATSAPP_TARGET` — optional WhatsApp target for sending summaries.
- `OPTIONS_RADAR_LOG_FILE` — wrapper log file.
- `OPTIONS_RADAR_IGNORE_WRAPPER_WINDOW=1` — bypass wrapper time gate.

Information only, not investment advice.
