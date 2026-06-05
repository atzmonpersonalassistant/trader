# QuantConnect-First Options Research & Agentic Development Platform — Low-Level Design

Status: Draft v1.0  
Owner: Uriel  
Primary asset class: US options  
MVP underlying: SPY  
Architecture direction: QuantConnect-first, cloud-first, GitHub-driven, agentic PR workflow

---

## 1. Executive Summary

This document defines a cloud-first quantitative options research and development platform.

The platform uses **GitHub as the source of truth**, **GitHub Actions as the automation layer**, and **QuantConnect Cloud / LEAN** as the primary research, backtesting, optimization, paper-trading, and future live-trading environment.

The first strategy family implemented in the MVP is a conservative **SPY Bull Put Credit Spread** backtester with parameter sweep support. The broader architecture is designed to support all major options strategy families over time.

The system includes an agentic software-development workflow with four separate agent roles:

1. **Coding Agent** — works on GitHub issues, writes code, opens PRs, and may auto-merge when checks pass.
2. **Review Agent** — required blocking PR review/check for code quality and quant-risk issues.
3. **Quant Research Validator Agent** — required PR validator plus full post-merge analysis of backtests/sweeps.
4. **Reporting/Orchestration Agent** — creates issues, updates experiment registry, sends WhatsApp summaries, and opens promotion PRs.

Live trading is explicitly **not implemented in the MVP**. The design includes live-trading guardrails and placeholders so the architecture does not need to be reworked later.

---

## 2. Goals

### 2.1 Product Goals

- Build a cloud-first options research and trading-development platform with no dependency on Uriel's local machine.
- Use QuantConnect as the primary data, research, backtest, optimization, paper-trading, and future live-trading environment.
- Keep GitHub as the canonical source of truth for code, configs, notebooks, workflows, and experiment registry.
- Enable autonomous code improvement through PR-based agents with strict guardrails.
- Produce actionable reports after backtests, sweeps, promotions, and paper-trading runs.
- Support automatic promotion to paper trading if strict validation gates pass.

### 2.2 Technical Goals

- Use **Lean CLI inside GitHub Actions** to interact with QuantConnect Cloud.
- Run full QuantConnect parameter sweeps after merge to `main`.
- Run lightweight tests, lint, notebook checks, code review, and quant validation before merge.
- Store sweep/backtest results as GitHub artifacts and structured registry entries.
- Send concise WhatsApp summaries for important success/failure/promotion events.
- Keep configs versioned in YAML while storing secrets only in GitHub/QuantConnect secrets.

---

## 3. Non-Goals

The following are intentionally out of scope for the MVP:

- Live trading implementation.
- Automatic live deployment.
- KDB+/q as an active runtime or data-layer dependency.
- Google Cloud research layer.
- External market-data sources such as Polygon/Tiingo/EODHD as primary data.
- Scraping Bloomberg, Refinitiv, FactSet, or other protected/paywalled market-data sources.
- HFT / sub-second / latency-sensitive execution.
- Institutional-scale tick warehouse.
- Large custom dashboard.

---

## 4. Key Decisions

| Area | Decision |
|---|---|
| Architecture | QuantConnect-first |
| Deployment model | Cloud-first only |
| Source of truth | GitHub |
| Automation | GitHub Actions |
| QuantConnect integration | Lean CLI inside GitHub Actions |
| Primary language | Python first, C# later if performance requires |
| First asset class | Options |
| MVP underlying | SPY |
| MVP strategy | Conservative Bull Put Credit Spread |
| DTE | 30–45 DTE |
| Strike selection | Parameterized delta sweep, not fixed manually |
| Backtest type | Full backtester, not scanner-only |
| Sweep | Included from the start; default 50–100 combinations |
| Full sweep trigger | Merge to `main` |
| PR checks | tests + lint + review agent + quant validator + required notebook checks |
| PR merge | Coding Agent may auto-merge if required checks pass |
| Review agent | TBD tool, required blocking check |
| Paper promotion | Promotion PR; agent may merge if checks pass |
| Paper trading | QuantConnect paper first, future IBKR integration target |
| Live trading | Future phase; guardrails/skeleton only |
| Data | QuantConnect primary; Polygon/external data extension point later |
| KDB+/q | Not in MVP; future optional extension only |
| Reports | HTML charts + JSON metrics + Markdown summary |
| Notifications | WhatsApp summaries for important events |
| Experiment registry | Lightweight JSON/Markdown registry in repo/artifacts |

---

## 5. Architecture Overview

```text
GitHub Repository
  ├─ source code
  ├─ strategy configs
  ├─ clean research notebooks
  ├─ GitHub Actions workflows
  ├─ experiment registry
  └─ documentation

GitHub Actions
  ├─ PR validation
  │   ├─ tests
  │   ├─ lint
  │   ├─ required notebooks light suite
  │   ├─ Review Agent required check
  │   └─ Quant Validator required check
  │
  ├─ main merge workflow
  │   ├─ Lean CLI sync/run
  │   ├─ QuantConnect full parameter sweep
  │   ├─ artifact collection
  │   ├─ full Quant Validator analysis
  │   ├─ experiment registry update
  │   └─ WhatsApp summary
  │
  └─ paper promotion workflow
      ├─ promotion PR opened by Orchestration Agent
      ├─ checks + review
      ├─ merge by Coding Agent if allowed
      └─ QuantConnect paper deployment/update

QuantConnect Cloud
  ├─ Research notebooks / QuantBook
  ├─ SPY options data
  ├─ LEAN algorithms
  ├─ backtests
  ├─ parameter optimization/sweeps
  ├─ paper trading project
  └─ future live trading project placeholder
```

---

## 6. QuantConnect Project Model

Use separate QuantConnect projects/environments:

```text
QuantConnect Organization
  ├─ spy-options-research-dev
  │   ├─ research notebooks
  │   ├─ backtest algorithm
  │   └─ parameter sweep configs
  │
  ├─ spy-options-paper
  │   ├─ paper-trading algorithm/configs
  │   └─ promoted strategy versions
  │
  └─ spy-options-live-placeholder
      └─ no real live implementation in MVP
```

### 6.1 Environment Rules

| Environment | Purpose | MVP Status |
|---|---|---|
| `research` | Backtests, sweeps, notebooks | Active |
| `paper` | QuantConnect paper trading | Active after promotion workflow exists |
| `live` | Future live trading | Placeholder only |

### 6.2 GitHub Environments

Use GitHub Environments:

```text
research
paper
live-placeholder
```

- `research`: QuantConnect cloud backtest/sweep secrets.
- `paper`: QuantConnect paper project/deploy secrets.
- `live-placeholder`: no active live secrets in MVP; requires manual approval if ever used.

---

## 7. Repository Structure

Recommended structure:

```text
quantconnect-options-platform/
  README.md

  docs/
    quantconnect-options-agentic-platform-lld.md

  algorithms/
    spy_bull_put_credit_spread/
      main.py
      strategy.py
      contracts.py
      risk.py
      config_loader.py
      reporting.py
      tests/
        test_config.py
        test_risk.py
        test_contract_selection.py

  research/
    notebooks/
      required/
        spy_options_data_smoke.ipynb
        bull_put_spread_assumptions.ipynb
      exploratory/
        001_spy_options_iv_exploration.ipynb
        002_delta_sensitivity_research.ipynb
    lib/
      options_metrics.py
      notebook_helpers.py
      qc_research_helpers.py

  configs/
    research/
      spy_bull_put_default.yaml
      spy_bull_put_sweep.yaml
    paper/
      paper_portfolio.yaml
      promoted_strategies.yaml
    live/
      live_placeholder.yaml

  reports/
    templates/
      backtest_summary.md.j2
      paper_daily_summary.md.j2

  registry/
    experiments.jsonl
    promotions.jsonl
    decisions.md

  agents/
    coding_agent_policy.md
    review_agent_checklist.md
    validator_policy.md
    orchestration_policy.md

  scripts/
    qc_sync_and_backtest.sh
    qc_run_sweep.sh
    parse_qc_results.py
    update_experiment_registry.py
    open_followup_issues.py
    open_promotion_pr.py
    send_whatsapp_summary.py
    run_required_notebooks.py

  .github/
    workflows/
      pr-checks.yml
      main-quantconnect-sweep.yml
      paper-promotion.yml
      paper-daily-report.yml
    CODEOWNERS
```

---

## 8. MVP Strategy Design

### 8.1 Strategy

MVP strategy:

```text
SPY Bull Put Credit Spread
```

Rationale:

- Defined-risk options strategy.
- More conservative than long calls/puts.
- Simpler than iron condor because it has one side instead of two.
- Suitable first strategy to validate the full research/backtest/promotion pipeline.

### 8.2 Strategy Rules

The backtester must model:

- SPY options chain selection.
- 30–45 DTE candidate expirations.
- Short put strike selected by delta sweep.
- Long put strike selected by spread width sweep.
- Entry schedule sweep.
- Profit target / stop loss / exit timing sweep.
- Transaction costs and slippage assumptions.
- Position sizing by max risk per trade.
- Max concurrent positions.
- Portfolio-level open risk cap.

### 8.3 Configurable Defaults

| Parameter | MVP Default |
|---|---|
| Underlying | SPY |
| Strategy | Bull Put Credit Spread |
| DTE | 30–45 |
| Short put delta | sweep over conservative bounds |
| Max risk per trade | configurable, default 0.5% |
| Max concurrent positions per strategy | configurable, default 1 |
| Max active paper strategies | configurable, default 3 |
| Portfolio total open risk cap | configurable, default 2% |
| Initial capital | configurable, no fixed default requirement |

---

## 9. Parameter Sweep Design

Parameter sweep is included from the start.

### 9.1 Sweep Scope

Default sweep size:

```text
50–100 parameter combinations
```

Configurable upper/lower bounds.

### 9.2 Candidate Parameter Families

```yaml
strategy:
  name: spy_bull_put_credit_spread
  underlying: SPY

sweep:
  dte:
    min: 30
    max: 45
    candidates: [30, 37, 45]

  short_put_delta:
    candidates: [0.10, 0.15, 0.20, 0.25]

  spread_width:
    candidates: [5, 10]

  entry_frequency:
    candidates:
      - weekly
      - two_or_three_times_weekly
      - daily_if_conditions_pass
      - iv_filtered

  profit_target_pct_of_credit:
    candidates: [0.50, 0.70]

  stop_loss_multiple_of_credit:
    candidates: [2.0, 3.0]
```

### 9.3 Selection Rule

The system must not select the “winner” by raw maximum profit.

Candidate ranking must consider:

- out-of-sample / walk-forward performance where available
- max drawdown
- profit factor
- Sortino/Sharpe
- tail loss behavior
- number of trades
- baseline comparison
- stability across time periods
- performance during stress regimes such as 2020 and 2022

---

## 10. Validation & Promotion Gates

### 10.1 Paper Promotion Gate

A strategy/config can be promoted to paper only if it passes conservative validation.

Default criteria:

```text
- Backtest includes costs and slippage.
- Backtest includes out-of-sample or walk-forward validation where feasible.
- At least 100 historical trades or enough historical cycles to avoid pure randomness.
- At least 5 years of history if QuantConnect data availability permits.
- Max drawdown <= 20% on allocated strategy capital.
- Profit factor >= 1.2.
- Sortino > 0.8 or Sharpe > 0.7.
- No catastrophic failure in stress periods.
- Performance is not dependent on one magical parameter setting.
- Shows advantage versus baseline, not merely positive absolute return.
```

### 10.2 Baselines

Every report must compare results against:

- SPY buy-and-hold.
- Cash/no-trade.
- Default conservative config versus sweep candidates.

### 10.3 Promotion/Rejection Decision Log

Every promotion or rejection must be documented.

Example:

```text
Rejected: profit factor passed, but max drawdown exceeded threshold and strategy underperformed baseline in 2022 stress period.
```

### 10.4 Paper-to-Live Readiness

Live is not implemented in MVP.

Future live consideration requires at least:

```text
- 3 months paper trading
- at least 30 paper trades
- no unresolved critical risk issues
- manual human approval
- live risk config review
```

---

## 11. Backtest and Paper Workflows

### 11.1 Pull Request Workflow

Triggered on every PR to `main`.

```text
PR opened/updated
  -> install dependencies
  -> run lint
  -> run unit tests
  -> run required lightweight notebooks
  -> run Review Agent required check
  -> run Quant Validator required check
  -> allow merge only if all required checks pass
```

Full parameter sweep does not run on PR.

### 11.2 Main Merge Workflow

Triggered on merge to `main`.

```text
Merge to main
  -> Lean CLI authenticates with QuantConnect
  -> sync project to QuantConnect research project
  -> run full QuantConnect parameter sweep
  -> collect results
  -> generate HTML report + JSON metrics + Markdown summary
  -> update experiment registry
  -> Quant Validator performs full result analysis
  -> Reporting Agent sends WhatsApp summary
  -> if failed/poor results: open issue + optional fix PR
  -> if passed promotion gate: open promotion PR
```

### 11.3 Promotion Workflow

```text
Promotion PR opened
  -> updates paper config / promoted strategy registry
  -> PR checks run
  -> Review Agent check required
  -> Quant Validator check required
  -> Coding Agent may auto-merge if all checks pass
  -> merge triggers QuantConnect paper deployment/update
  -> WhatsApp summary sent
```

### 11.4 Paper Trading Reports

Paper trading reports are sent:

- daily after US market close
- daily in Israel morning

Report content:

- active paper strategies
- open positions
- daily P&L
- drawdown
- risk used versus cap
- alerts/failures
- paper-to-live readiness progress
- next actions/issues for the agents

---

## 12. GitHub Branch Protection

Branch strategy:

```text
main only + temporary PR branches
```

No `develop`, `paper`, or `live` branches.

### 12.1 Required Protections for `main`

`main` must require:

```text
- pull request before merge
- tests required check
- lint required check
- required notebook suite check
- Review Agent required check
- Quant Validator required check
- no direct pushes by agents
- branch up to date before merge if practical
```

### 12.2 Agent Auto-Merge Rule

Coding Agent may auto-merge only if:

```text
- PR has required labels/scope
- all required checks pass
- Review Agent passes
- Quant Validator passes
- no forbidden files changed
- no live-sensitive change requiring human approval
```

### 12.3 Live/Risk Sensitive Paths

Changes to live-sensitive paths require manual owner approval.

Examples:

```text
configs/live/**
.github/workflows/*live*
execution/live/**
secrets documentation/config bindings
risk limits for live
broker live deployment settings
```

Research/paper risk configs may go through CI + Review Agent + Quant Validator without manual approval.

---

## 13. Agent Architecture

The system uses four separate agents.

### 13.1 Coding Agent

Responsibilities:

- Pull issues from GitHub backlog.
- Work only on issues marked `agent:ready`.
- Create branches.
- Modify code/configs/docs/tests.
- Open PRs.
- Respond to review comments.
- Auto-merge if all required checks pass and no guardrail blocks it.

Restrictions:

- No secrets access.
- No admin access.
- No live deployment.
- No live risk-limit changes.
- No direct pushes to `main`.
- New strategies only if issue has `type:strategy` and `agent:ready`.

### 13.2 Review Agent

Responsibilities:

- Required blocking check on PRs.
- Review code quality.
- Review test coverage.
- Review quant-specific risk checklist.
- Detect suspicious changes to validation, costs, slippage, look-ahead protections, or risk gates.

Review checklist includes:

```text
- no obvious look-ahead bias
- transaction costs/slippage not removed
- validation gates not weakened silently
- configs remain within allowed bounds
- no secrets or credentials in code
- no live-sensitive changes without approval
- no overfitting-oriented shortcut
```

Implementation tool is TBD. Candidate tools include Baz/Bazz, CodeRabbit, Copilot Review, or a custom GitHub Action reviewer.

### 13.3 Quant Research Validator Agent

Responsibilities:

- Required PR check before merge using light/static validation.
- Full post-merge validation after QuantConnect sweep results are available.
- Decide whether a result qualifies for paper-promotion PR.
- Mark issues `agent:ready` only when there is research evidence.
- Document promotion/rejection decisions.

PR-time validation:

```text
- config bounds valid
- required costs/slippage present
- validation gates intact
- notebooks required suite passes
- no suspicious parameter overfitting pattern
```

Post-merge validation:

```text
- parse JSON metrics
- compare to baselines
- inspect stability
- inspect stress-period results
- accept/reject promotion
- open follow-up issue if needed
```

### 13.4 Reporting/Orchestration Agent

Responsibilities:

- Create issues from failures, improvement suggestions, research ideas, and promotion follow-ups.
- Update experiment registry.
- Send WhatsApp summaries.
- Open promotion PRs after Validator approval.
- Maintain daily paper reports.

Restrictions:

- Can open `type:strategy` issues, but cannot mark them `agent:ready` automatically.
- Does not write trading logic directly.
- Does not approve live-sensitive changes.

---

## 14. GitHub Issue Labels

Use labels:

```text
agent:ready
agent:blocked

type:bug
type:research
type:strategy
type:infra
type:reporting

priority:p0
priority:p1
priority:p2
priority:p3

risk:live-sensitive
needs:human-approval
```

### 14.1 Issue Readiness Rule

Only the following can apply `agent:ready`:

- Uriel
- Quant Research Validator Agent

For `type:strategy`, Validator may apply `agent:ready` only with evidence:

- backtest result
- research notebook
- experiment registry entry
- or clear hypothesis + validation plan

---

## 15. Config Design

Configs are stored as YAML in the repository. Secrets are not stored in YAML.

### 15.1 Example Research Config

```yaml
strategy:
  id: spy_bull_put_credit_spread
  underlying: SPY
  asset_class: options
  language: python

backtest:
  start_date: "2019-01-01"
  end_date: "2025-12-31"
  initial_capital: null # required at run time or environment config
  benchmark:
    - spy_buy_and_hold
    - cash

risk:
  max_risk_per_trade_pct:
    default: 0.005
    configurable: true
  max_concurrent_positions_per_strategy:
    default: 1
    configurable: true
  portfolio_total_open_risk_pct:
    default: 0.02
    configurable: true

execution_model:
  include_commissions: true
  include_slippage: true
  conservative_fill_assumptions: true

sweep:
  enabled: true
  max_combinations_default: 100
  dte_candidates: [30, 37, 45]
  short_put_delta_candidates: [0.10, 0.15, 0.20, 0.25]
  spread_width_candidates: [5, 10]
  profit_target_pct_of_credit_candidates: [0.50, 0.70]
  stop_loss_multiple_of_credit_candidates: [2.0, 3.0]
  entry_frequency_candidates:
    - weekly
    - two_or_three_times_weekly
    - daily_if_conditions_pass
    - iv_filtered

promotion_gate:
  min_trades: 100
  min_years_if_available: 5
  max_drawdown_pct: 0.20
  min_profit_factor: 1.20
  min_sortino: 0.80
  min_sharpe: 0.70
  require_baseline_advantage: true
  require_stress_period_check: true
```

### 15.2 Example Paper Portfolio Config

```yaml
paper:
  max_active_strategies:
    default: 3
    configurable: true

  portfolio_total_open_risk_pct:
    default: 0.02
    configurable: true

  report_schedule:
    after_us_market_close: true
    israel_morning: true

  broker_target:
    current: quantconnect_paper
    future: interactive_brokers
```

---

## 16. GitHub Actions Skeletons

### 16.1 PR Checks

```yaml
name: PR Checks

on:
  pull_request:
    branches: [main]

jobs:
  tests-lint-notebooks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Lint
        run: make lint
      - name: Unit tests
        run: make test
      - name: Required lightweight notebooks
        run: python scripts/run_required_notebooks.py --suite pr-light

  review-agent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Review Agent
        run: python scripts/run_review_agent.py

  quant-validator:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run PR Quant Validator
        run: python scripts/run_quant_validator.py --mode pr
```

### 16.2 Main QuantConnect Sweep

```yaml
name: Main QuantConnect Sweep

on:
  push:
    branches: [main]

jobs:
  quantconnect-sweep:
    runs-on: ubuntu-latest
    environment: research
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install Lean CLI
        run: pip install lean
      - name: Authenticate QuantConnect
        env:
          QC_USER_ID: ${{ secrets.QUANTCONNECT_USER_ID }}
          QC_API_TOKEN: ${{ secrets.QUANTCONNECT_API_TOKEN }}
        run: scripts/qc_login.sh
      - name: Sync and run sweep
        run: scripts/qc_run_sweep.sh configs/research/spy_bull_put_sweep.yaml
      - name: Parse results
        run: python scripts/parse_qc_results.py --out artifacts/results.json
      - name: Generate reports
        run: python scripts/generate_report.py --metrics artifacts/results.json
      - name: Full Quant Validator
        run: python scripts/run_quant_validator.py --mode post-merge --metrics artifacts/results.json
      - name: Update experiment registry
        run: python scripts/update_experiment_registry.py --metrics artifacts/results.json
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: quantconnect-sweep-report
          path: artifacts/
      - name: Orchestrate follow-ups and WhatsApp summary
        run: python scripts/orchestrate_after_sweep.py --metrics artifacts/results.json
```

### 16.3 Paper Promotion

```yaml
name: Paper Promotion

on:
  pull_request:
    paths:
      - "configs/paper/**"
      - "registry/promotions.jsonl"

jobs:
  validate-paper-promotion:
    runs-on: ubuntu-latest
    environment: paper
    steps:
      - uses: actions/checkout@v4
      - name: Validate promotion evidence
        run: python scripts/validate_promotion_pr.py
      - name: Review Agent
        run: python scripts/run_review_agent.py
      - name: Quant Validator
        run: python scripts/run_quant_validator.py --mode promotion
```

---

## 17. Reports and Artifacts

Each full sweep/backtest produces:

```text
artifacts/
  report.html
  metrics.json
  summary.md
  charts/
    equity_curve.png
    drawdown.png
    parameter_stability.png
```

CSV trades are optional in MVP if QuantConnect result extraction supports it easily.

### 17.1 metrics.json Shape

```json
{
  "commit_sha": "abc123",
  "strategy_id": "spy_bull_put_credit_spread",
  "run_id": "qc-backtest-id",
  "config_hash": "sha256...",
  "sweep": {
    "combinations": 84,
    "best_candidate_id": "candidate_017"
  },
  "metrics": {
    "cagr": 0.08,
    "max_drawdown": 0.14,
    "profit_factor": 1.35,
    "sharpe": 0.9,
    "sortino": 1.1,
    "trades": 142
  },
  "baseline": {
    "spy_buy_and_hold": {
      "cagr": 0.11,
      "max_drawdown": 0.34
    },
    "cash": {
      "cagr": 0.0,
      "max_drawdown": 0.0
    }
  },
  "promotion_decision": {
    "eligible_for_paper": true,
    "reason": "Passed risk-adjusted criteria and improved drawdown versus SPY baseline."
  }
}
```

---

## 18. Experiment Registry

Use lightweight registry files in MVP.

### 18.1 `registry/experiments.jsonl`

Each line:

```json
{
  "timestamp": "2026-06-05T12:00:00Z",
  "commit_sha": "abc123",
  "strategy_id": "spy_bull_put_credit_spread",
  "config_hash": "sha256...",
  "qc_backtest_id": "...",
  "artifact_url": "...",
  "summary": {
    "max_drawdown": 0.14,
    "profit_factor": 1.35,
    "sortino": 1.1,
    "trades": 142
  },
  "decision": "promote_to_paper_candidate"
}
```

### 18.2 Agent Usage

Coding Agent may use the registry to propose follow-up experiments only inside predefined sweep/config bounds.

---

## 19. Data Architecture

### 19.1 MVP

Primary data source:

```text
QuantConnect SPY options data
```

Research uses:

```text
QuantConnect Research Notebooks + QuantBook
```

No external data vendor is required for MVP.

### 19.2 Future External Data

Potential future sources:

- Polygon
- Tiingo
- EODHD
- Alpha Vantage
- other licensed APIs

These remain extension points only.

### 19.3 KDB+/q

KDB+/q is not part of the MVP.

Potential future role:

```text
External analytical store for high-volume intraday/tick/options-chain analytics.
```

If adopted later, KDB will not be assumed to be a native QuantConnect Cloud dependency. It would feed QuantConnect via exported custom datasets or support a separate own-cloud research layer.

---

## 20. Notebooks

Notebooks are stored in GitHub, but must be clean and reproducible.

Rules:

```text
- no secrets
- no heavy outputs committed
- important logic belongs in .py modules
- notebooks should be restart-and-run capable
- required notebooks have timeouts
- exploratory notebooks do not block CI
```

### 20.1 Notebook CI

```text
PR:
  required lightweight notebooks only

main:
  full required notebook suite

exploratory:
  stored but not automatically blocking
```

---

## 21. Notifications

WhatsApp summaries are sent to Uriel for important events:

- full sweep success/failure
- promotion PR opened/merged
- paper deploy/update started or failed
- critical CI/backtest failures
- daily paper trading reports

The 24/7 Coding Agent does not work via WhatsApp. It works from GitHub issues/backlog only.

---

## 22. Failure Handling

If full sweep/backtest fails or produces poor results:

```text
- mark GitHub workflow failed or warning
- open issue automatically
- send WhatsApp summary
- Coding Agent may open a fix PR
- no automatic paper promotion
- no automatic revert in MVP
```

If paper deployment fails:

```text
- open issue
- send WhatsApp summary
- block promotion status
- Coding Agent may open fix PR
```

---

## 23. Security and Secrets

No secrets in code, notebooks, configs, reports, or registry.

Secret storage:

```text
GitHub Secrets
QuantConnect Secrets
```

Likely secrets:

```text
QUANTCONNECT_USER_ID
QUANTCONNECT_API_TOKEN
WHATSAPP_NOTIFICATION_WEBHOOK_OR_OPENCLAW_ENDPOINT
IBKR credentials in future only
```

Agent rules:

```text
- agents do not read raw secrets
- agents cannot print secrets
- agents cannot modify secret wiring without human approval if live-sensitive
```

---

## 24. Implementation Phases

### Phase 0 — Repo and Governance

- Create repository layout.
- Add branch protection.
- Add issue labels.
- Add agent policy docs.
- Add GitHub environments.

### Phase 1 — QuantConnect MVP Backtester

- Implement SPY Bull Put Credit Spread strategy in Python.
- Implement YAML config loading.
- Implement risk defaults.
- Implement QuantConnect project sync via Lean CLI.
- Implement one full sweep workflow.

### Phase 2 — Reports and Registry

- Parse QuantConnect results.
- Generate HTML/JSON/Markdown artifacts.
- Add experiment registry.
- Add baseline comparison.
- Add WhatsApp summaries.

### Phase 3 — Agentic Workflow

- Add Coding Agent integration.
- Add Review Agent required check.
- Add Quant Validator required check.
- Add Reporting/Orchestration Agent.
- Enable auto-merge when all checks pass.

### Phase 4 — Paper Promotion

- Implement promotion gate.
- Open promotion PRs automatically.
- Deploy/update QuantConnect paper project.
- Send daily paper reports.

### Phase 5 — Future Extensions

- Add more strategy families.
- Add external data provider if needed.
- Consider own-cloud research layer if QuantConnect becomes limiting.
- Consider KDB+/q only if data scale justifies it.
- Add live trading only after paper criteria and explicit human approval.

---

## 25. Open Implementation Questions

These are intentionally left for implementation-time decisions:

1. Which exact Review Agent tool: Baz/Bazz, CodeRabbit, Copilot Review, or custom GitHub Action?
2. Which exact Coding Agent runtime?
3. Exact QuantConnect plan/node requirements after testing sweep runtime.
4. Exact WhatsApp notification mechanism.
5. Exact Lean CLI commands/API required for cloud sweep orchestration.
6. How much options-chain detail QuantConnect exposes cleanly for the desired SPY spread backtests.
7. Whether C# migration is needed for performance later.

---

## 26. Final MVP Definition

The MVP is complete when:

```text
- GitHub repo contains clean notebooks, Python algorithm, configs, workflows, and docs.
- PRs require tests/lint/notebook checks/review-agent/quant-validator.
- Merge to main triggers QuantConnect sweep through Lean CLI.
- Sweep produces HTML report, JSON metrics, Markdown summary, and registry entry.
- Report compares strategy to baselines.
- Validator decides promotion/rejection with documented reason.
- Passing results open a promotion PR.
- Promotion PR can deploy/update QuantConnect paper project after checks pass.
- WhatsApp summaries are sent for important events.
- No live trading is implemented.
```
