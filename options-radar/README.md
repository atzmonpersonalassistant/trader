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


## Outputs

By default, scanner results are written under:

- `options-radar/output/options-radar.csv` — latest tabular candidate list.
- `options-radar/output/options-radar.json` — latest machine-readable candidate list.
- `options-radar/output/options_radar_cron.log` — wrapper log when `run.sh` is used with the default log path.

The output directory can be changed with `--output-dir` or `OPTIONS_RADAR_OUTPUT_DIR`.

If `OPTIONS_RADAR_WHATSAPP_TARGET` or `--send-whatsapp-to` is set, the scanner also sends the concise summary to the **Options radar** WhatsApp group. The repo does not hard-code the group JID; configure it through `OPTIONS_RADAR_WHATSAPP_TARGET` (or `--send-whatsapp-to` for manual runs).

`options-radar/output/*` is ignored by git except for `output/README.md`. Runtime outputs are disposable artifacts, not source-of-truth research records.

## Scheduler wrapper

```bash
options-radar/run.sh
```

The wrapper resolves paths relative to this directory. By default it runs only on weekdays, at minutes `05` and `35`, between local hours `16:00-22:00`.

Useful environment variables:

- `OPTIONS_RADAR_UNIVERSE` — path to universe CSV.
- `OPTIONS_RADAR_OUTPUT_DIR` — output directory.
- `OPTIONS_RADAR_MAX_PRICE` — max ask/mid filter, default `$0.30`.
- `OPTIONS_RADAR_WHATSAPP_TARGET` — WhatsApp target for the **Options radar** group.
- `OPTIONS_RADAR_LOG_FILE` — wrapper log file.
- `OPTIONS_RADAR_IGNORE_WRAPPER_WINDOW=1` — bypass wrapper time gate.

Information only, not investment advice.
