# Options Research MVP Roadmap

## Purpose

Build an options research evidence engine, not a money-printing machine.

The goal is to create infrastructure that can take an options strategy hypothesis, test it rigorously, and produce a clear report about whether the idea deserves more work. A negative result is still useful if it prevents us from fooling ourselves.

## MVP1 — Paid Quant Researcher Infrastructure Pipeline

MVP1 should use the paid QuantConnect Quant Researcher tier if the objective is real infrastructure rather than a mostly manual proof-of-concept.

The free tier is useful for learning and manual exploration, but it is a poor fit for an agentic research platform because it lacks the API/CLI automation we need.

### Goal

Build the first working version of the automated options research infrastructure.

The system should be able to take one or two options strategy hypotheses, preferably seeded from QuantConnect community/library examples, run them through a repeatable research pipeline, and produce a critical report.

MVP1 is still not a trading bot. It is an evidence engine.

### Why Paid in MVP1

Use the paid tier if it unlocks:

- QuantConnect API access
- LEAN CLI / local or VPS-driven workflow
- automated cloud backtest runs
- result retrieval and report generation
- future paper-trading path
- better fit for GitHub/VPS/agent orchestration

This avoids building MVP1 around a workflow we already know we will throw away in MVP2.

### Scope

- Use QuantConnect/LEAN as the strategy/backtest engine.
- Use the API/CLI path where possible instead of relying on manual Web IDE steps.
- Start from community strategies as hypotheses, not as trade recommendations.
- Focus on defined-risk options strategies.
- Produce research reports and evidence, not live trades.
- Store strategy code, configs, reports, and research artifacts in the repo.
- Route changes through GitHub issues, PRs, coding agent, and review agent.

### First Strategy Candidates

Start with simple, liquid, defined-risk strategies:

- SPY or QQQ bull put spread
- SPY or QQQ bear call spread
- SPY or QQQ iron condor

Avoid in MVP1:

- naked short options
- 0DTE strategies
- complex multi-strategy portfolios
- live trading or broker execution
- aggressive parameter optimization

### Required Pipeline

For each strategy hypothesis:

1. Define the research spec:
   - strategy family
   - universe
   - entry rules
   - exit rules
   - DTE and strike/delta rules
   - sizing and max-risk rules
   - benchmark
   - expected failure modes
2. Implement or reproduce the strategy in Python/LEAN.
3. Run backtests through the QuantConnect/LEAN workflow.
4. Pull result metrics and artifacts automatically where possible.
5. Include transaction costs and realistic slippage assumptions where possible.
6. Compare against SPY/QQQ benchmarks.
7. Tag market regimes:
   - VIX high/low or proxy if VIX is unavailable
   - SPY above/below 200-day moving average
   - market drawdown weeks
   - high-volatility periods
8. Run basic out-of-sample or walk-forward validation where feasible.
9. Score results using:
   - return
   - max drawdown
   - win rate
   - profit factor
   - trade count
   - alpha/beta versus benchmark
   - robustness across parameter variations
10. Generate a concise report:
   - what was tested
   - what data was used
   - what worked
   - what failed
   - when the strategy breaks
   - recommendation: discard, refine, or candidate for paper testing

### MVP1 Success Criteria

MVP1 succeeds if a single command, issue, or agent task can produce a trustworthy strategy report for a simple options strategy.

The strategy does not need to be profitable. The infrastructure is the product.

Success means:

- the pipeline is reproducible
- reports are clear
- basic bias checks exist
- results include costs, benchmarks, and regime context
- the system can reject bad ideas instead of only celebrating good-looking backtests
- the agent/platform workflow is ready to scale to more strategies

## MVP2 — Paper-Trading and Scale

MVP2 should build on the paid infrastructure from MVP1.

### Goal

Move from research evidence generation toward paper-trading readiness and broader strategy coverage.

MVP2 candidates:

- paper trading for one validated candidate strategy
- broader strategy coverage
- better parameter robustness testing
- richer reporting and artifacts
- more automated comparison between strategy variants
- tighter integration between QuantConnect results and the GitHub/VPS agent workflow

### Still Out of Scope in MVP2

- automatic live trading
- unapproved broker execution
- high-risk 0DTE automation
- treating community strategies as validated without independent testing

## MVP3 — Open Direction

MVP3 is intentionally undecided.

Possible directions:

- dedicated historical options data provider such as ThetaData, IVolatility, ORATS, or Polygon
- deeper IV rank/percentile, skew, and term-structure analysis
- systematic paper-trading portfolio
- strategy portfolio construction
- advanced walk-forward and robustness tooling
- live-trading readiness review, only with explicit human approval

Do not lock MVP3 until MVP1 and MVP2 results show what is actually valuable.

## Community Strategy Policy

QuantConnect community strategies are useful as starting points, but they are not evidence by themselves.

Treat each community strategy as a hypothesis:

1. Understand the thesis.
2. Reproduce it in our repo.
3. Check for look-ahead bias.
4. Add costs and slippage.
5. Compare against benchmark exposure.
6. Test across market regimes.
7. Run out-of-sample or walk-forward validation where feasible.
8. Decide whether to discard, refine, or paper-test.

Never treat a copied strategy as ready for capital without independent validation.

## Research Philosophy

The system should answer:

- Is there evidence this idea works?
- Is the result just market beta?
- Does it survive costs and slippage?
- Does it only work in one regime?
- Is the sample size large enough?
- Is it likely overfit?
- What would make us reject it?

The goal is disciplined evidence, not optimism.
