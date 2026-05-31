# Trading Options Rules Scanner

Location:

```text
~/code/trading/options_rules_scanner.py
```

This scanner follows Uriel's Google Sheet `Options Setups Tracker` rules.

## Current Rules

- Find continuation setups from intraday candles.
- LONG setup:
  - stock up strongly / trend continuation
  - near day high
  - above VWAP
  - EMA9 > EMA21
  - last 60 minutes rising
  - use **OTM CALLS** only
- SHORT setup:
  - stock down strongly / trend continuation
  - near day low
  - below VWAP
  - EMA9 < EMA21
  - last 60 minutes falling
  - use **ITM PUTS** only
- Expiry:
  - not limited to next week
  - default scans all expiries from **6 to 45 DTE**
  - can force one expiry with `--expiry YYYY-MM-DD`
- Option price:
  - must be <= `$1` unless changed with `--max-premium`
- Strike distance:
  - within `--strike-distance` percent from spot, default 10%
- Always verify live bid/ask in broker before acting.

## Setup

```bash
cd ~/code/trading
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
cd ~/code/trading
source .venv/bin/activate
python options_rules_scanner.py --max-premium 1 --max-spread-pct 300 --top 5
```

## Useful variations

Allow options up to $2:

```bash
python options_rules_scanner.py --max-premium 2 --max-spread-pct 300 --top 10
```

Force a specific expiry:

```bash
python options_rules_scanner.py --expiry 2026-05-22 --max-premium 1 --max-spread-pct 300
```

Scan specific tickers:

```bash
python options_rules_scanner.py QUBT RGTI QBTS MARA ONDS --max-premium 1 --max-spread-pct 300
```

## Output files

The script writes CSV files relative to the current working directory:

- `options_tools/latest_stock_signals.csv`
- `options_tools/latest_candidates.csv`

## Warning

This is a scanner, not an automatic trading system. yfinance/Yahoo option data can be stale or wrong intraday. Confirm contract, bid/ask, spread, volume/OI, and invalidation in the broker before trading.
