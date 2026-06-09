# QuantConnect MVP1 Research Notes

Last updated: 2026-06-10 Asia/Jerusalem

Purpose: collect platform capability/limit findings and open questions before drafting the detailed MVP1 implementation plan.

## Current Direction

MVP1 should treat QuantConnect/LEAN as the execution/backtest/data platform and our repo/agents as the research orchestration layer.

MVP1 is an options research evidence engine, not live trading and not a money-printing machine.

## Auth / Secrets

- QuantConnect API credentials were found via Gmail and stored as GitHub repository secrets:
  - `QUANTCONNECT_USER_ID`
  - `QUANTCONNECT_API_TOKEN`
- Credentials were not committed to the repo.
- API authentication was verified successfully against `https://www.quantconnect.com/api/v2/authenticate`.
- QuantConnect API authentication uses `USER_ID` plus SHA-256 hash of `API_TOKEN:timestamp`, sent via Basic Auth and `Timestamp` header. The raw API token should never be sent or logged.

## Local Environment Findings

- `lean` CLI is not currently installed on the local Mac PATH.
- `docker` is not currently installed/found on the local Mac PATH.
- Python `requests` is not available in the current default Python environment, but API calls can be made with stdlib `urllib` or a project venv.

Implication: MVP1 setup needs an explicit LEAN CLI + Docker/local environment decision. If we prefer cloud-only via API at first, Docker can be delayed, but LEAN CLI/local backtests likely need Docker.

## Quant Researcher Capabilities Relevant to MVP1

From QuantConnect docs / tier feature docs:

- Paid organization tier is required for LEAN CLI use.
- Quant Researcher includes:
  - QuantConnect API access.
  - LEAN CLI and local LEAN workflow.
  - second and tick resolution data from Datasets Market.
  - unlimited projects.
  - up to 100KB logs per backtest.
  - up to 3MB logs per day.
  - up to 10M orders per backtest.
  - up to 2 backtesting nodes / about 2 concurrent backtests.
  - up to 2 active coding sessions.
  - parameter optimization tools after successful backtests.
  - ability to subscribe to up to 2 live trading nodes for paper/live later.
  - live algorithm notifications: up to 20 Email/Telegram/Webhook notifications per hour for free.

## Backtest / Node Limits

- Backtesting nodes determine speed/concurrency.
- Option data and large universes are memory intensive.
- Free B-MICRO has a 20-second launch delay and 200 backtests/day cap; docs say these restrictions are lifted/replaced when upgrading to paid tier and adding a new backtesting node.
- Cloud backtests can run up to 12 hours.
- More powerful node models have more CPU/RAM; options workloads may need stronger nodes if chains/universe are too broad.

MVP1 implication: use a small universe, narrow chain filters, limited parameter grid, and queue backtests instead of blasting many runs.

## LEAN CLI Workflow

Relevant commands/docs:

- `lean login` — stores user id/API token in local credentials file.
- `lean project-create --language python "Project Name"` — creates a Python project with `main.py`, research notebook, project config, and editor config.
- `lean cloud backtest PROJECT --push --name NAME --parameter key value` — pushes local project changes and runs a cloud backtest.
- `lean backtest PROJECT --output DIR` — runs local Docker-based LEAN backtest.
- `lean backtest --download-data` / `--data-provider-historical QuantConnect` can pull data from QuantConnect for local backtests, but this can incur QCC costs.
- `--data-purchase-limit <integer>` exists and should be used whenever a workflow could download paid data.

MVP1 implication: prefer cloud backtests initially to avoid local bulk data purchases. If local backtests are used, require `--data-purchase-limit 0` or a strict explicit budget unless Uriel approves otherwise.

## API Workflow

API docs show endpoints for:

- `/authenticate` — verify credentials.
- `/backtests/create` — create a backtest from project id + compile id.
- `/backtests/read` — read backtest statistics/results.
- `/backtests/update` — update backtest metadata.
- `/backtests/delete` — delete backtest.
- `/backtests/list` — list backtests, optionally with statistics.

Backtest creation requires a project and compile id, so MVP1 needs project/compile management research next.

## Research Environment / Notebooks

QuantConnect research environment provides:

- Jupyter-style notebooks attached to QuantConnect data repository.
- QuantBook for research workflows.
- historical data requests.
- charting with Jupyter-supported libraries.
- indicators.
- Object Store.
- ML workflows.
- meta-analysis of backtest/optimization/live results.

MVP1 implication: notebooks are useful for exploration and reports, but production strategy/backtest code should live in `.py` and be reproducible via CLI/API.

## Options Support

QuantConnect supports Equity Options and Index Options in LEAN. Docs include sections for:

- requesting options data.
- handling options data.
- Greeks and implied volatility.
- market hours.
- basic options templates.

Subagent and docs findings:

- US Equity Options data is available historically in QC cloud; option chain work can be heavy.
- Option data may include prices, strikes, expirations, open interest, Greeks/IV depending on workflow and model.
- Universe/chain filtering is essential: ticker(s), DTE window, strike/delta range, liquidity constraints.

MVP1 implication: start with SPY/QQQ and one/two defined-risk strategies. Avoid broad option universes and 0DTE in MVP1.

## Data Cost / Download Risk

Important distinction:

- Cloud backtesting can use QC cloud datasets within platform terms.
- Local data downloads from QuantConnect Dataset Market may cost QCC per file/download.
- `lean data download` and `lean backtest --download-data` can trigger paid data acquisition if configured.

MVP1 rule candidate:

- No bulk local options data download.
- Any command that can spend QCC must default to a zero or tiny `--data-purchase-limit` unless explicitly approved.
- Keep MVP1 cloud-first for historical options data.

## Logging / Artifacts

Quant Researcher logs are limited:

- 100KB per backtest.
- 3MB per day.

MVP1 logging rule candidate:

- Do not log every option contract, minute, chain, or trade detail through QC logs.
- Use summary logs only.
- Store structured outputs as metrics/artifacts where possible:
  - JSON metrics.
  - CSV trade summary.
  - Markdown report.
  - compressed artifacts on our side (`.json.gz`, `.csv.gz`) after retrieval.
- QC logs are not a data warehouse.

## Community Strategy Reuse

QuantConnect has:

- official strategy library tutorials.
- community/tutorial strategies.
- options examples/templates.
- external/community repositories such as options frameworks.
- built-in LEAN helpers for some option strategy structures.

Policy for MVP1:

- Treat community strategies as hypotheses/seeds, not validated strategies.
- Do not copy blindly into production.
- For each candidate strategy:
  1. identify source and license/terms if external code is copied.
  2. understand thesis and assumptions.
  3. reimplement or minimally adapt in our own clean structure where possible.
  4. add costs/slippage assumptions.
  5. compare to benchmark exposure.
  6. run regime analysis.
  7. check sample size and out-of-sample/walk-forward where feasible.
  8. produce verdict: discard / refine / paper-test candidate.

Known options-relevant strategy seeds from QC docs/library include:

- Volatility Risk Premium Effect: sells ATM straddle and buys OTM puts monthly; risky and not ideal as first MVP strategy unless converted to defined-risk and audited carefully.
- Basic options templates in LEAN GitHub/docs.
- Common option structures supported/documented: vertical spreads, iron condors, straddles/strangles, butterflies, calendars.

MVP1 recommendation: use community examples for learning and scaffolding, but first implemented strategy should be a simple clean template such as SPY/QQQ bull put spread or iron condor.

## Key MVP1 Design Implications

1. Build a narrow pipeline before broad strategy coverage.
2. Prefer cloud backtests for options data.
3. Install/configure LEAN CLI only after deciding local vs VPS vs GitHub Actions workflow.
4. Protect against data spend by default.
5. Keep logs tiny and artifacts structured.
6. Force review gates for costs, benchmark, trade count, no live trading, no 0DTE, no naked options.
7. Treat copied/community strategies as untrusted research inputs.


## Additional Deep-Dive Findings

### API Surface

QuantConnect API appears to cover more than only backtests. Relevant surfaces for MVP1 include:

- Project management.
- File management.
- Compile.
- Backtest management.
- Optimization.
- Object Store.
- Reports.
- Account / LEAN version metadata.
- Live management exists, but live trading remains out of MVP1 scope.

Practical workflow candidate:

1. Create/update project files.
2. Compile project.
3. Create backtest with `projectId`, `compileId`, `backtestName`, and parameters.
4. Poll/read backtest by `backtestId`.
5. Extract statistics, runtime stats, charts/trades where available.
6. Persist our own normalized result summary.

### Object Store

QuantConnect Object Store is organization-level key-value storage. It can be used for artifacts shared between research/backtest/live contexts, such as:

- small models.
- signals.
- intermediate datasets.
- compact analysis outputs.

Known constraints from research:

- Free object store: roughly 50MB and 1,000 files.
- Paid storage add-ons mentioned in docs/research: 2GB/20k files, 5GB/50k files, 10GB/100k files, 50GB/500k files at increasing monthly cost.
- QC recommends keeping objects small; live access can be slower.

MVP1 implication: use Object Store sparingly for compact artifacts, not as a data lake. Prefer our own repo/CI artifacts/DB for normalized reports and run metadata.

### Options Data Local Download Scale

Research found that broad local options data is huge and expensive. Approximate scale mentioned:

- Full US equity options daily: hundreds of GB.
- Full US equity options hour: hundreds of GB.
- Full US equity options minute: multiple TB.

Approximate per-file local download costs found in QC docs/research:

- Minute options: about 15 QCC / file, roughly $0.15.
- Hour options: about 900 QCC / file, roughly $9.
- Daily options: about 300 QCC / file, roughly $3.
- Option Universe: about 100 QCC / file, roughly $1.

MVP1 implication: local download of broad options data is not acceptable by default. Use cloud backtests and strict whitelists.

### Research Notebook Constraint

QuantConnect Research / QuantBook is useful for exploration, plotting, and historical data requests, but notebook execution can have responsiveness/time limits. Treat notebooks as exploratory artifacts, not the production pipeline.

### Community / Legal/IP Notes

- LEAN itself is open-source under Apache 2.0.
- Official docs/examples are useful references.
- Forum/community code and external repos may have unclear licenses and should not be copied blindly.
- AlphaStreams-related SDK/license is specialized and not a general permission to reuse strategies commercially.

MVP1 policy candidate:

- Use official docs/examples and community strategies as learning/reference/hypothesis seeds.
- Prefer clean-room/simple reimplementation in our repo.
- Record source links for any strategy inspiration.
- If copying code, verify license first.

### Additional Strategy Structures Available in QC/LEAN

QC/LEAN docs and helpers cover many structures, including:

- covered call / covered put.
- protective put / protective call / collar.
- bull/bear call spreads.
- bull/bear put spreads.
- straddles / strangles.
- iron condors.
- iron butterflies.
- calendar spreads.
- box spreads, jelly rolls, ladders.
- 0DTE examples.
- combo orders / `OptionStrategies` helpers.

MVP1 should still avoid 0DTE and complex/naked structures.

## Open Questions for Uriel

### Product / MVP Boundary

1. Should MVP1 be command-first (`run one research job and create a report`) or GitHub-issue-first (`issue -> agent -> code -> backtest -> report -> PR`)?
2. Is MVP1 success defined as a working infrastructure/report pipeline even if the first strategy fails? Recommendation: yes.
3. Should MVP1 include any paper trading, or is paper trading explicitly MVP2? Recommendation: MVP2.

### Universe / Instruments

4. Start with `SPY` only or `SPY + QQQ`?
5. Include index options such as `SPX`, or only equity/ETF options for MVP1? Recommendation: ETF options only.
6. Use one ticker per backtest run, or allow a tiny universe of 2-5 symbols?

### Strategy Choice

7. First strategy family: bull put spread, bear call spread, iron condor, long straddle/strangle, calendar/diagonal?
8. Use community strategy as direct seed, or build clean implementation while referencing community examples? Recommendation: clean implementation, community as reference.
9. Validate one strategy deeply, or compare 2-3 basic variants shallowly? Recommendation: one deep first.

### Data / Runtime

10. Historical range: 3 years, 5 years, or from 2012 where available?
11. Resolution: minute data from the start, or daily/hourly for first pipeline scaffold? Recommendation: minute for options fills if cloud performance is acceptable; otherwise scaffold lighter then upgrade.
12. Are local options data downloads forbidden unless explicitly approved? Recommendation: yes.
13. Is a small QCC spend allowed if needed, or zero data purchases in MVP1? Recommendation: zero/unapproved.

### Backtest Realism

14. Fill model: market/mid-price/conservative bid-ask/limit approximation?
15. Required cost model: commissions + slippage from first version? Recommendation: yes.
16. How strict should assignment/expiration modeling be? Recommendation: avoid holding to expiration in MVP1; exit before expiration to reduce assignment complexity.
17. Required metrics: return, max drawdown, win rate, profit factor, trade count, alpha/beta vs SPY/QQQ, tail loss, margin usage?

### Regime / Noise Isolation

18. Required regime tags: VIX high/low, SPY above/below 200MA, drawdown weeks, high-volatility periods, Fed/earnings weeks?
19. Should the report only describe regime performance, or explicitly recommend regime filters such as “do not run when VIX > X”?

### Automation / Agent Workflow

20. Should LEAN CLI run locally, on the VPS, or in GitHub Actions?
21. Should GitHub Actions use `QUANTCONNECT_*` secrets immediately, or should only the VPS use them initially?
22. Can the agent create/update QuantConnect cloud projects automatically, or should it only run against pre-created projects?
23. Should review agent block any PR that lacks: costs, benchmark, trade count, regime analysis, no-live-trading guard, and data-spend guard?

### Reporting

24. Preferred output: Markdown report, JSON metrics, notebook, charts, WhatsApp summary?
25. Should reports be committed to the repo, stored as CI artifacts, or stored outside git with only summaries committed?
26. How much detail should WhatsApp include: verdict only, or metrics summary?

### Safety / Governance

27. Confirm no live trading in MVP1.
28. Confirm no 0DTE in MVP1.
29. Confirm no naked short options in MVP1.
30. Confirm no automatic paper/live deployment without explicit approval.
