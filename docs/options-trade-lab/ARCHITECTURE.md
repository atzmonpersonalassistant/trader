# Options Trade Lab — Architecture

## Status

Task #2: **Define modular architecture**.

This document defines the intended architecture only. It does **not** implement the modules yet.

## Design Principles

1. **Research first, execution later** — the system must help us test ideas before risking capital.
2. **Do not invent the wheel** — use proven libraries where appropriate: `pandas`, `numpy`, `polars`, `duckdb`, `vectorbt`, `py_vollib`, `ib_insync`, and dedicated options-data providers later.
3. **Separate concerns aggressively** — data, features, signals, strategy selection, backtesting, risk, and reports should be independent modules.
4. **Backtests are guilty until proven innocent** — every backtest must account for look-ahead bias, transaction costs, slippage, sample size, and out-of-sample validation.
5. **Options require special treatment** — stock-level signal quality and option-pricing quality are different problems and must be tested separately.
6. **Provider-agnostic design** — start with `yfinance`, but design adapters so IBKR, Polygon, ThetaData, or ORATS can be added without rewriting the pipeline.
7. **Auditable artifacts** — every scan/backtest should be reproducible from saved config, input data version, and output artifacts.
8. **No live trading in MVP** — first build scanner, research, backtest, and paper-trade flows; live execution comes only after explicit approval.

## Architecture Overview

```text
Data Providers
  └── Data Adapters
        └── Raw Data Store
              └── Canonical Data Layer
                    └── Feature Engine
                          ├── Candidate Scanners
                          ├── Signal Research
                          └── Backtest Engine
                                ├── Stock-Level Backtests
                                ├── Options Proxy Backtests
                                └── Historical Options Backtests later
                                      └── Analytics / Reports
                                            └── Review / Approval / Paper Trading
```

## Proposed Project Structure

```text
options-trade-lab/
├── PROJECT_PLAN.md
├── ARCHITECTURE.md
├── README.md                         # later: usage and project overview
├── pyproject.toml                    # later: dependencies, tooling, package config
├── configs/
│   ├── default.yaml                  # global defaults
│   ├── universe.yaml                 # stock universe definitions
│   ├── scanner_momentum.yaml         # scanner-specific thresholds
│   └── backtest_default.yaml         # costs, slippage, holding rules
├── data/
│   ├── raw/                          # immutable vendor pulls
│   ├── canonical/                    # normalized OHLCV/options/fundamentals
│   ├── features/                     # saved feature sets
│   └── results/                      # scan/backtest outputs
├── notebooks/                        # exploratory research only, not production logic
├── reports/
│   ├── daily/                        # generated daily candidate reports
│   └── backtests/                    # generated backtest reports
├── scripts/
│   └── cli.py                        # later: command entrypoint
├── src/
│   └── options_trade_lab/
│       ├── __init__.py
│       ├── config/                   # config loading and validation
│       ├── data/                     # provider adapters and canonical schemas
│       ├── features/                 # technical, volatility, liquidity, regime features
│       ├── scanners/                 # candidate discovery logic
│       ├── signals/                  # reusable entry/exit signal definitions
│       ├── options/                  # chains, pricing, Greeks, IV/HV analysis
│       ├── strategies/               # option strategy selection rules
│       ├── backtesting/              # stock, proxy-options, and later real-options tests
│       ├── risk/                     # sizing, loss limits, portfolio exposure rules
│       ├── analytics/                # metrics, stats, walk-forward analysis
│       ├── reporting/                # Markdown/CSV/HTML reports
│       ├── persistence/              # Parquet/SQLite/DuckDB helpers
│       └── utils/                    # logging, dates, market calendar helpers
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

## Module Responsibilities

### `config/`
Loads and validates YAML config files.

Must eventually support:
- universe selection
- scanner thresholds
- risk limits
- transaction-cost assumptions
- data-provider settings
- backtest parameters

### `data/`
Responsible for vendor-specific data access and canonical normalization.

Initial adapter:
- `YFinanceMarketDataProvider`

Future adapters:
- `IBKRMarketDataProvider`
- `PolygonMarketDataProvider`
- `ThetaDataOptionsProvider`
- `ORATSOptionsProvider`

Important rule: downstream modules should consume canonical schemas, not vendor-specific payloads.

### `features/`
Computes reusable feature columns.

Initial feature families:
- returns: 1D, 5D, 20D, 60D
- trend: SMA/EMA 20/50/200, distance from moving averages
- volume: volume ratio vs 20D/60D average
- volatility: ATR, HV20, HV60
- relative strength: stock return vs SPY/QQQ/IWM
- regime: SPY/QQQ trend, VIX proxy later

Technical indicators are allowed, but they are features — not magic trading rules.

### `scanners/`
Turns features into candidate lists.

Initial scanner types:
- momentum scanner
- breakout scanner
- volatility-value scanner
- catalyst-aware scanner later
- theme/universe scanner later

Each scanner should output candidates with scores and reasons, not blind buy/sell decisions.

### `signals/`
Defines reusable entry/exit conditions.

Examples:
- price above 20DMA and 50DMA
- 20D return > threshold
- volume ratio > threshold
- breakout above N-day high
- market regime filter is risk-on

Signals must be timestamp-safe: if a signal uses today’s close, the simulated trade happens no earlier than next open/next available price.

### `options/`
Handles options-specific calculations.

Initial scope:
- Black-Scholes pricing
- Greeks
- IV vs HV comparison
- breakeven calculation
- DTE and strike selection helpers

Future scope:
- historical chain loading
- IV rank/percentile
- skew and term structure
- liquidity filters by bid/ask, volume, open interest

### `strategies/`
Maps a trade thesis to option structures.

Initial strategy selector:
- bullish + IV acceptable => long call candidate
- bullish + IV expensive => bull call spread candidate
- bearish + IV acceptable => long put candidate later
- high move + low IV => straddle/strangle candidate later

This module does not decide whether a stock is interesting; it only maps an approved setup into an option structure.

### `backtesting/`
Backtesting is split into three levels:

1. **Stock-level backtest** — validates whether the underlying setup has directional edge.
2. **Options proxy backtest** — simulates option P/L using pricing models when historical chains are unavailable.
3. **Historical options backtest** — uses real historical option chains once we have a provider.

Required guardrails:
- train/test or walk-forward validation
- transaction costs
- slippage assumptions
- trade count reporting
- max adverse excursion / max favorable excursion
- no same-bar close-signal and close-fill leakage

### `risk/`
Defines position sizing and constraints.

Initial rules:
- max loss per trade
- max total options exposure
- max correlated theme exposure
- stop-loss and take-profit templates

No live-risk or broker integration yet.

### `analytics/`
Calculates result metrics.

Required metrics:
- win rate
- average win/loss
- expectancy
- profit factor
- max drawdown
- Sharpe/Sortino where appropriate
- number of trades
- holding-period distribution
- performance by regime

### `reporting/`
Produces human-readable outputs.

Initial outputs:
- Markdown daily scan report
- CSV candidates file
- Markdown backtest summary

Reports should explain *why* a candidate appeared and list warnings.

### `persistence/`
Handles local storage.

Recommended storage:
- Parquet for time-series datasets
- SQLite or DuckDB for metadata/results

Rationale: simple, local, auditable, and enough for MVP scale.

## Data Model — Initial Canonical Schemas

### OHLCV bars

```text
date
ticker
open
high
low
close
adj_close
volume
provider
pulled_at
```

### Feature rows

```text
date
ticker
close
ret_5d
ret_20d
ret_60d
sma_20
sma_50
sma_200
volume_ratio_20d
atr_14
hv_20
hv_60
rs_vs_spy_20d
risk_on_flag
```

### Candidate rows

```text
scan_date
ticker
scanner_name
score
setup_type
reasons
warnings
feature_snapshot_id
```

### Backtest trade rows

```text
strategy_id
ticker
entry_signal_date
entry_fill_date
entry_price
exit_date
exit_price
pnl_pct
max_adverse_excursion
max_favorable_excursion
exit_reason
config_hash
```

### Options candidate rows

```text
scan_date
ticker
underlying_price
option_type
expiration
strike
dte
bid
ask
mid
iv
delta
gamma
theta
vega
breakeven
move_required_pct
liquidity_score
pricing_warning
```

## Library Choices — MVP Recommendation

### Use now

- `pandas` / `numpy` — baseline data work
- `yfinance` — quick start for OHLCV and current options chains
- `py_vollib` or small internal Black-Scholes implementation — option pricing/Greeks
- `pytest` — tests
- `pyyaml` — configs

### Consider soon

- `duckdb` — local analytics over Parquet
- `polars` — faster data transforms if needed
- `vectorbt` — fast stock-level signal/backtest experimentation
- `pandas-ta` or `ta` — technical indicators, but only as feature generators
- `ib_insync` — IBKR integration after account is ready

### Do not add yet

- web frontend
- live execution
- complex ML/RL
- Docker/Celery/Postgres
- multi-language acceleration

Those are premature until we have validated signals.

## Key Architecture Decision

For MVP, do **not** build a full options backtesting engine from scratch.

Instead:
1. Build a clean research pipeline.
2. Validate stock-level signals first.
3. Use an options proxy model to test structure sensitivity.
4. Add real historical option-chain backtesting only after a signal shows promise.

Reason: historical options backtesting is data-heavy and expensive. If the underlying setup has no edge, a perfect options engine will not save it.

## Open Questions Before Task #3

1. Should the MVP be pure Python package + CLI, or do we also want notebooks from day one?
2. Should persistence start with flat Parquet files only, or Parquet + DuckDB metadata?
3. What is the first target universe: S&P 500, NASDAQ 100, high-volume optionable stocks, or themed watchlists?
4. Should we optimize first for long calls only, or keep strategy selection generic from the start?
5. What data provider should we plan around for historical options once we outgrow proxy backtests?

## Recommended Answers

1. **Python package + CLI, with notebooks only for exploration.**
2. **Parquet first; add DuckDB when queries become annoying.**
3. **Start with high-volume optionable stocks plus a manual themed watchlist.**
4. **Optimize first for long calls, but keep interfaces strategy-agnostic.**
5. **Evaluate ThetaData, ORATS, and Polygon before choosing.**
