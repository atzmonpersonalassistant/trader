# QuantConnect Options Strategy POC

This folder contains the first small research scaffold for a QuantConnect/LEAN options strategy.

**Research only. This is not a trade recommendation and must not be deployed live.**

## Strategy candidate

- Underlying: `SPY` or `QQQ`
- Structure: defined-risk credit spread only
  - `bear_call`: sell call, buy higher-strike call
  - `bull_put`: sell put, buy lower-strike put
- Default DTE: 14-45 days
- Default short-leg delta target: ~0.20
- Default max risk: 0.5% of portfolio, capped to one spread in this POC
- No naked options
- No 0DTE default

## Files

- `algorithms/spy_qqq_credit_spread_poc.py` — QuantConnect algorithm skeleton.
- `reports/research_report.py` — local report generator from exported or mocked QuantConnect metrics.

## How to use in QuantConnect Cloud

1. Create a new Python QuantConnect project.
2. Copy `algorithms/spy_qqq_credit_spread_poc.py` into the project as `main.py`.
3. Set parameters in QuantConnect, for example:
   - `underlying=QQQ`
   - `strategy=bear_call`
   - `min_dte=14`
   - `max_dte=45`
   - `short_delta_target=0.20`
   - `spread_width=10`
   - `max_risk_fraction=0.005`
4. Run a cloud backtest.
5. Export/copy summary metrics into JSON and generate a report:

```bash
python3 quantconnect-poc/reports/research_report.py \
  --config config.json \
  --metrics metrics.json \
  --output report.md
```

## Minimum evidence before paper trading

A result is not interesting unless it survives:

- realistic commissions and slippage
- 30+ trades minimum
- walk-forward / out-of-sample testing
- drawdown sanity check
- regime review
- manual review of fills and option-chain selection

The report verdict is intentionally conservative: `discard_or_refine` unless basic thresholds pass.
