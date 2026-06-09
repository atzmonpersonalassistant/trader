# Options Credit Spread Trading System Spec

Status: Draft v0.1  
Owner: Uriel  
Target platform: QuantConnect Cloud + Interactive Brokers  
Language: Python

## 1. Executive Summary

Build a serious, scalable automated options-trading system focused first on **limited-risk premium-selling strategies**. The initial implementation will research and backtest credit-spread strategies on highly liquid ETFs, then progress through validation, paper trading, small live capital, and eventually fully automated live trading through Interactive Brokers.

The system is intended to start with a small account of **$1,000**, but the architecture should be clean enough to scale to substantially larger capital later.

The initial strategy family is **defined-risk option selling**, not naked options.

## 2. Goals

### 2.1 Primary Goal

Build a long-term, serious trading infrastructure that can eventually run fully automated options strategies through Interactive Brokers.

### 2.2 Initial Research Goal

Research and backtest limited-risk options credit strategies using historical options data:

- Bull put spreads
- Bear call spreads
- Iron condors

### 2.3 Long-Term Goal

Create a system that can support:

- Strategy research
- Backtesting
- Walk-forward validation
- Paper trading
- Live trading
- Risk monitoring
- WhatsApp alerts
- Kill switch controls
- Future extension to additional strategies

## 3. Non-Goals / Out of Scope for Phase 1

Phase 1 does **not** include:

- Naked options
- Manual discretionary trading workflows
- Intraday execution optimization beyond what is required for daily checks
- Stock-specific earnings strategies as a primary module
- Broad universe scanning across many equities
- Building a custom broker integration from scratch

Future extension:

- Earnings strategies in individual stocks may be explored later, but they are only a future extension and not part of the first strategy module.

## 4. Core User Decisions Captured

| Area | Decision |
|---|---|
| Strategic objective | Build serious long-term infrastructure |
| Asset class | Options |
| Initial strategy style | Selling premium with limited risk |
| Naked options | Strictly forbidden |
| Initial underlyings | SPY + QQQ |
| Initial platform | QuantConnect Cloud |
| Broker | Interactive Brokers |
| Language | Python |
| First phase | Backtest only |
| Final operating mode | Fully automated |
| Alert target | WhatsApp |
| Kill switch | Required: manual + automatic |
| Starting capital | $1,000 |
| Future scale target | Architecture should scale up significantly, potentially to $1M+ |
| Max risk per trade initially | $50 |
| Max total open risk initially | $200 |
| Position count | Determined by total risk limit, not fixed count |
| Check frequency | Daily |
| DTE scope | Test multiple DTE ranges, including 0DTE |
| 0DTE | Allowed in backtest, limited-risk spreads only |
| Strategy success metric | Not fixed yet; determine after initial results |
| Backtest history | Use as much available history as possible + regime splits |

## 5. Strategy Universe

### 5.1 Initial Underlyings

Phase 1 universe:

- `SPY`
- `QQQ`

Rationale:

- Highly liquid options markets
- Tight spreads relative to most products
- Strong historical data availability
- Broad market exposure
- Easier to validate than single-stock strategies

### 5.2 Potential Future Underlyings

Future expansion may include:

- `IWM`
- Other highly liquid index ETFs
- Mega-cap equities
- Earnings-specific single-stock strategies

Any expansion must be separately validated.

## 6. Strategy Types

### 6.1 Bull Put Spreads

Defined-risk bullish/neutral premium-selling strategy.

Potential use case:

- Underlying is in uptrend or stable regime
- Implied volatility is attractive
- Short put selected by delta and/or probability
- Long put defines max loss

### 6.2 Bear Call Spreads

Defined-risk bearish/neutral premium-selling strategy.

Potential use case:

- Underlying is in downtrend or overextended rally
- Implied volatility is attractive
- Short call selected by delta and/or probability
- Long call defines max loss

### 6.3 Iron Condors

Defined-risk neutral/range-bound premium-selling strategy.

Potential use case:

- Underlying expected to remain range-bound
- IV is attractive
- Trend strength is weak or neutral
- Both put and call spreads are opened as one defined-risk structure

## 7. Signal Design

The initial signal framework should combine:

1. **Delta-based strike selection**
2. **IV-based environment filter**
3. **Trend filter**

### 7.1 Delta Filter

Candidate short strikes should be selected using option delta ranges.

Examples to test:

- Short delta around 0.10
- Short delta around 0.15
- Short delta around 0.20
- Short delta around 0.25
- Short delta around 0.30

Exact ranges are not fixed yet and should be part of the research grid.

### 7.2 IV Filter

The system should test whether trades perform better when filtered by implied volatility conditions.

Possible metrics:

- IV Rank
- IV Percentile
- Implied volatility vs realized volatility
- VIX regime
- IV term structure where available

Example filters to test:

- IV Rank > 30
- IV Rank > 50
- IV Rank > 70
- No IV filter baseline

### 7.3 Trend Filter

The system should test trend filters to avoid selling premium against strong directional movement.

Possible trend filters:

- Price above/below SMA 200
- Price above/below SMA 50
- SMA 50 vs SMA 200
- Momentum over 1/3/6 months
- RSI regime
- ADX/trend strength

Examples:

- Bull put spreads only when underlying is above SMA 200
- Bear call spreads only when underlying is below SMA 200 or overextended
- Iron condors only when trend strength is low/neutral

## 8. DTE Research Scope

The system should test multiple expiration ranges rather than choosing one upfront.

DTE buckets to test:

- 0DTE
- 1-7DTE
- 7-21DTE
- 30-60DTE
- 60-120DTE

Notes:

- 0DTE is allowed in research, but only as defined-risk spreads.
- 0DTE may later become either part of the main strategy or a separate module depending on results.
- Higher gamma risk in short-dated options must be explicitly measured.

## 9. Position Sizing

### 9.1 Initial Account Size

Initial design capital:

- $1,000

### 9.2 Max Risk Per Trade

Initial max risk per trade:

- $50

This equals 5% of the initial account size. This is aggressive but acceptable for research, given the stated objective of maximizing return. It must be validated before live use.

### 9.3 Max Total Open Risk

Initial max aggregate open risk:

- $200

This equals 20% of the initial account size. This is aggressive and must be treated as a hard research parameter, not automatically approved for live trading.

### 9.4 Number of Concurrent Positions

No fixed number of concurrent positions.

The number of open positions should be constrained by:

- Max total open risk
- Per-underlying concentration limits
- Available capital/margin
- Strategy signal quality
- Liquidity and spread constraints

### 9.5 Position Sizing Methods to Test

Backtest multiple sizing methods:

1. Fixed dollar risk per trade
2. Fixed percentage risk per trade
3. Volatility-adjusted sizing
4. VIX/regime-adjusted sizing
5. Conviction-score sizing

Initial implementation should start simple, then add complexity only if it improves out-of-sample results.

## 10. Risk Management

### 10.1 Hard Constraint: No Naked Options

The system must never open uncovered short options.

Allowed:

- Credit spreads
- Debit spreads if later needed
- Iron condors
- Other defined-risk multi-leg strategies

Forbidden:

- Naked short calls
- Naked short puts
- Any undefined-risk option position

### 10.2 Max Loss Per Trade

Every trade must have a known max loss at order creation.

Required calculation:

```text
Max loss = spread width - credit received - estimated costs
```

For iron condors:

```text
Max loss = max(put wing width, call wing width) - total credit received - estimated costs
```

### 10.3 Portfolio-Level Risk

Track at minimum:

- Total open max loss
- Open risk by underlying
- Open risk by expiration date
- Open risk by strategy type
- Daily realized P&L
- Unrealized P&L
- Drawdown from equity peak
- Margin usage

### 10.4 Concentration Risk

Whether total open risk can be concentrated in one underlying is undecided.

Backtest should compare:

- Allow concentration in SPY or QQQ
- Force diversification between SPY and QQQ
- Allow concentration only with high conviction

### 10.5 Macro Event Risk

The system should test whether macro-event filters improve performance.

Events to consider:

- FOMC / Fed rate decisions
- CPI
- PPI
- NFP / jobs report
- Major volatility shocks
- Other high-impact calendar events

Policies to test:

- Do nothing
- Avoid opening new trades before events
- Reduce position size before events
- Close existing positions before events
- Hold existing positions but pause new entries

### 10.6 Earnings Risk

Not relevant for the first SPY/QQQ module.

Future extension:

- Earnings strategies in individual stocks can be researched separately.

## 11. Exit Rules

The system should test combinations of exit rules.

### 11.1 Profit Target

Examples:

- Close at 25% of max profit captured
- Close at 50% of max profit captured
- Close at 75% of max profit captured
- Hold until time-based exit

### 11.2 Stop Loss

Examples:

- Close when loss reaches 1x credit received
- Close when loss reaches 2x credit received
- Close when spread value reaches a fixed multiple of credit
- Close when max loss probability or delta exceeds threshold

### 11.3 Time-Based Exit

Examples:

- Close X days before expiration
- Close at 50% of original DTE elapsed
- Never hold into final expiration day except explicit 0DTE module

### 11.4 Signal-Based Exit

Examples:

- Trend filter invalidated
- IV regime changed materially
- Short strike delta exceeded threshold
- Underlying breached technical risk level

### 11.5 Expiration Handling

The system should avoid accidental assignment or unwanted expiration risk unless explicitly tested.

For non-0DTE strategies, default should be:

- Do not hold through expiration
- Close before expiration according to tested rule

For 0DTE research:

- Assignment/pin risk must be explicitly modeled or avoided by closing before market close.

## 12. Scheduling and Execution Frequency

Initial decision:

- Daily evaluation frequency

The strategy should run once per trading day during a defined window.

Potential daily workflow:

1. Refresh market and options data
2. Update indicators and regime metrics
3. Evaluate open positions for exits
4. Evaluate new entry candidates
5. Enforce risk limits
6. Submit orders if in live/paper mode
7. Send notifications
8. Write logs and daily summary

Exact execution time should be determined later, but candidates include:

- Shortly after market open
- Midday
- Before close

For 0DTE research, intraday timing may need separate treatment.

## 13. Backtesting Requirements

### 13.1 Historical Coverage

Use as much historical options data as available.

Also break results into regimes:

- Bull market
- Bear market
- Sideways market
- High volatility
- Low volatility
- Crisis periods
- 2020-style volatility shock
- 2022-style bear market/rate shock
- Recent post-2023 regime

### 13.2 Required Cost Modeling

Backtests must include:

- Commissions
- Bid/ask spread assumptions
- Slippage
- Realistic fill assumptions
- Liquidity constraints

No backtest result should be accepted without costs.

### 13.3 Required Validation

At minimum:

- In-sample / out-of-sample split
- Walk-forward testing
- Parameter sensitivity analysis
- Regime analysis
- Trade count and statistical significance
- Drawdown analysis
- Tail-loss analysis
- Worst-trade and worst-period analysis

### 13.4 Overfitting Controls

Avoid strategies that only work with many finely tuned parameters.

Red flags:

- High Sharpe only in one period
- Too few trades
- Extreme dependence on one DTE or delta value
- Results collapse after costs
- Results depend on exact entry time
- Performance disappears out-of-sample

## 14. Success Metrics

The primary success metric is currently undecided.

The research system should report multiple metrics before choosing the final optimization target.

Required metrics:

- CAGR / annualized return
- Max drawdown
- CAGR / Max Drawdown
- Sharpe ratio
- Sortino ratio
- Win rate
- Average win/loss
- Profit factor
- Expected value per trade
- Tail loss / worst trade
- Number of trades
- Average days in trade
- Return by regime
- Return by DTE bucket
- Return by underlying
- Return by strategy type
- Commissions/slippage impact

Recommended decision framework later:

- Do not optimize for raw return alone.
- Prefer strategies with strong return relative to drawdown and stable performance across regimes.

## 15. System Architecture

### 15.1 Target Runtime

Initial/final runtime decision:

- QuantConnect Cloud

Broker:

- Interactive Brokers

Language:

- Python

### 15.2 Main Modules

Recommended module structure:

1. `UniverseModule`
2. `MarketDataModule`
3. `OptionChainModule`
4. `RegimeModule`
5. `SignalModule`
6. `StrategySelector`
7. `StrikeSelector`
8. `PositionSizingModule`
9. `RiskManager`
10. `ExecutionModule`
11. `ExitManager`
12. `NotificationModule`
13. `KillSwitchModule`
14. `ReportingModule`
15. `BacktestAnalysisModule`

### 15.3 Module Responsibilities

#### UniverseModule

Defines tradable underlyings.

Phase 1:

- SPY
- QQQ

#### MarketDataModule

Provides:

- Underlying prices
- Historical prices
- Indicators
- VIX or proxy data
- Macro calendar data if available

#### OptionChainModule

Provides:

- Option chains
- Expirations
- Strikes
- Greeks
- Bid/ask
- Open interest
- Volume
- Implied volatility

#### RegimeModule

Classifies market regime using metrics such as:

- Trend
- Volatility
- VIX level
- Realized volatility
- IV rank/percentile
- Momentum

#### SignalModule

Generates candidate setups:

- Bull put spread signal
- Bear call spread signal
- Iron condor signal

#### StrategySelector

Chooses which strategy type to use based on:

- Trend regime
- IV regime
- Underlying behavior
- Candidate score
- Risk availability

#### StrikeSelector

Selects strikes based on:

- Delta target
- DTE bucket
- Spread width
- Liquidity
- Max risk limits
- Minimum credit threshold

#### PositionSizingModule

Determines size/contracts based on:

- Account value
- Max per-trade risk
- Max total open risk
- Strategy score
- Volatility regime

#### RiskManager

Enforces:

- No naked options
- Max risk per trade
- Max total open risk
- Concentration limits
- Margin limits
- Drawdown limits once defined
- Kill switch state

#### ExecutionModule

Handles order submission.

In QuantConnect, this should use native option order APIs and brokerage model behavior rather than direct IB API plumbing.

#### ExitManager

Evaluates open positions for:

- Profit target
- Stop loss
- Time exit
- Signal invalidation
- Risk event exit

#### NotificationModule

Sends:

- Trade-open alerts
- Trade-close alerts
- Daily summaries
- Risk alerts
- Kill switch alerts

Target endpoint:

- WhatsApp via external integration layer

#### KillSwitchModule

Supports:

- Manual kill switch
- Automatic kill switch
- Trading halt state
- New-entry pause state
- Emergency flatten behavior, if enabled

#### ReportingModule

Produces:

- Daily summary
- Open risk report
- Closed trades report
- Strategy performance report
- Regime report

#### BacktestAnalysisModule

Analyzes:

- Performance metrics
- Regime split
- DTE split
- Underlying split
- Strategy split
- Parameter sensitivity

## 16. Live Trading Rollout Plan

Even though the final target is fully automated, rollout must be staged.

### Phase 1: Research / Backtest

- Build strategy framework
- Run historical backtests
- Compare DTE buckets
- Compare delta filters
- Compare IV filters
- Compare trend filters
- Compare sizing methods
- Compare exit rules
- Analyze regimes

Exit criteria:

- Stable out-of-sample results
- Realistic cost assumptions included
- No overfit parameter dependency
- Risk profile understood

### Phase 2: Paper Trading

- Deploy to QuantConnect Cloud paper/live simulation mode
- Connect to IBKR paper if appropriate
- Validate order behavior
- Validate option-chain selection
- Validate fills vs expected assumptions
- Validate alerts
- Validate kill switch

Exit criteria:

- Minimum observation period met
- No critical execution bugs
- Risk limits enforced correctly
- Notifications reliable

### Phase 3: Small Live Capital

Initial live capital:

- $1,000

Constraints:

- Max risk/trade: $50
- Max total open risk: $200
- No naked options
- Daily monitoring
- Kill switch enabled

Exit criteria:

- Live behavior matches paper reasonably
- No operational failures
- Slippage and fills acceptable
- Emotional/operational comfort confirmed

### Phase 4: Scale-Up

Increase capital only after:

- Sufficient live sample
- Strategy remains within risk expectations
- Drawdowns acceptable
- Execution reliable
- Monitoring/alerts mature

## 17. Notifications and WhatsApp Integration

### 17.1 Required Alerts

The system should eventually send WhatsApp messages for:

- Every opened trade
- Every closed trade
- Daily summary
- Risk limit breach
- Kill switch activation
- Data/brokerage failure
- Unexpected exception

### 17.2 Likely Architecture

QuantConnect supports notifications such as email, webhooks, and Telegram more naturally than WhatsApp.

Likely path:

```text
QuantConnect webhook -> small bridge service -> WhatsApp delivery
```

The bridge service can later be implemented through OpenClaw or another controlled service.

### 17.3 Example Trade Open Alert

```text
Opened bull put spread
Underlying: SPY
Expiration: 2026-07-17
Short put: 510
Long put: 505
Credit: $0.80
Max risk: $420
Contracts: 1
Reason: IV Rank 62, price above SMA200, short delta 0.20
Total open risk after trade: $X
```

## 18. Kill Switch

### 18.1 Requirement

The system must support both:

- Manual kill switch
- Automatic kill switch

### 18.2 Automatic Conditions

Exact conditions are undecided and should be calibrated in research.

Candidate triggers:

- Daily loss above threshold
- Weekly loss above threshold
- Drawdown from peak above threshold
- Consecutive losing trades
- Broker/data connection issue
- Margin/usage breach
- Unexpected position state
- Strategy bug or exception

### 18.3 Kill Switch Modes

Possible modes:

1. Pause new entries only
2. Close all positions immediately
3. Close risky positions only
4. Require manual review before resuming

Default recommendation for early live:

- Automatic kill switch pauses new entries immediately.
- Closing existing positions depends on severity.

## 19. Data Requirements

### 19.1 Required Data

- Historical underlying prices for SPY and QQQ
- Historical option chains
- Historical Greeks, or enough data to compute/estimate Greeks
- Bid/ask prices
- Volume/open interest where available
- IV data
- VIX or volatility proxy
- Macro event calendar if event filters are tested

### 19.2 Data Quality Concerns

Critical risks:

- Bad or missing option-chain data
- Survivorship/data availability bias
- Unrealistic fills at mid price
- Not modeling bid/ask spreads
- Using future information in indicators
- Ignoring assignment/pin risk near expiration

## 20. Technical Implementation Notes for QuantConnect

### 20.1 Brokerage Model

Use Interactive Brokers brokerage model for realism:

```python
self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)
```

Account type may be adjusted later.

### 20.2 Option Subscriptions

Add options for SPY and QQQ and filter expirations/strikes.

The implementation should expose DTE and delta buckets as research parameters.

### 20.3 Parameterization

The strategy should be parameterized, not hardcoded.

Examples:

- Underlyings
- DTE buckets
- Delta targets
- Spread widths
- IV filter thresholds
- Trend filters
- Profit target
- Stop loss
- Time exit
- Per-trade risk
- Total open risk

### 20.4 Logging

Every trade decision should log:

- Candidate underlyings
- Candidate strategy
- Rejected candidates and reason
- Selected strikes
- Expected credit
- Max risk
- Signal values
- Risk state before/after

This is essential for debugging and avoiding black-box behavior.

## 21. Research Questions to Answer

The research phase should answer:

1. Which strategy works best on SPY/QQQ: bull put, bear call, iron condor?
2. Which DTE buckets are robust?
3. Does 0DTE improve or degrade risk-adjusted performance?
4. Which delta target works best after costs?
5. Does IV filtering add value?
6. Does trend filtering add value?
7. What exit rule is most robust?
8. What position sizing method produces the best return/risk tradeoff?
9. Should risk be diversified between SPY and QQQ?
10. Do macro event filters improve results?
11. What drawdown and kill-switch thresholds are reasonable?
12. What metric should become the primary optimization target?

## 22. Key Risks

### 22.1 Strategy Risk

- Premium selling can have high win rate but ugly tail losses.
- 0DTE can create large gamma-driven losses quickly.
- Backtests can overstate performance if fills are unrealistic.

### 22.2 Data Risk

- Historical options data may be incomplete or expensive.
- Greeks may be missing or estimated differently across providers.
- Bid/ask spreads can materially change results.

### 22.3 Execution Risk

- Live fills may be worse than backtest assumptions.
- Multi-leg option orders may not fill cleanly.
- IBKR connection/authentication can fail.
- QuantConnect/IBKR live integration requires operational monitoring.

### 22.4 Overfitting Risk

- Too many parameters can create fake edge.
- Optimizing across DTE, delta, filters, exits, and sizing can overfit quickly.
- Walk-forward and out-of-sample validation are mandatory.

### 22.5 Account Size Risk

- $1,000 is small for options spreads.
- Even defined-risk spreads may consume too much capital.
- Commissions and spreads matter more in small accounts.

## 23. Open Questions

Still undecided:

1. Primary success metric
2. Final drawdown limit
3. Automatic kill switch thresholds
4. Whether 0DTE belongs in main strategy or separate module
5. Whether concentration in one underlying should be allowed
6. Exact macro-event handling
7. Exact live execution timing
8. Whether to use margin or cash account assumptions for first live run
9. Which data provider will be used for historical options data
10. Whether QuantConnect built-in data is sufficient for all research needs

## 24. Initial Development Tasks

Suggested first tasks:

1. Create QuantConnect project skeleton in Python
2. Add SPY/QQQ underlying subscriptions
3. Add option chain subscriptions
4. Implement parameterized option filter by DTE and delta
5. Implement spread candidate generator
6. Implement max-risk calculation
7. Implement no-naked-options validation
8. Implement simple bull put spread backtest
9. Add bear call spread
10. Add iron condor
11. Add transaction cost/slippage assumptions
12. Add basic reporting metrics
13. Add regime split analysis
14. Add parameter grid runner
15. Add walk-forward validation
16. Draft paper-trading rollout checklist

## 25. Recommended First Build Slice

The smallest useful implementation should be:

- Python QuantConnect algorithm
- SPY only initially, then QQQ
- Bull put spread only initially
- 30-60DTE only initially
- Delta target parameterized
- Fixed spread width parameterized
- Fixed max risk per trade
- Profit target + stop loss + time exit
- Full logs and metrics

After that works, expand to:

- Bear call spreads
- Iron condors
- More DTE buckets
- 0DTE research
- IV filters
- Trend filters
- Position sizing variants
- Event filters

## 26. Design Principle

Do not build a clever machine first.

Build a boring, auditable research engine that can prove or kill ideas honestly.

For options premium selling, the danger is not being wrong often. The danger is being right often and then losing badly once. The system must be designed around that reality.
