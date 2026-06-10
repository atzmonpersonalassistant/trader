# Research Run Storage Design Draft

Status: Draft / parked for Uriel review  
Last updated: 2026-06-10 Asia/Jerusalem

## Purpose

Capture the current design discussion for how MVP1 should store QuantConnect research-run state, reports, metrics, and artifacts.

This is intentionally not merged/approved yet. It exists so we can resume the architecture discussion later without losing context.

## Current MVP1 Workflow Decisions

### Research workflow style

MVP1 should be **GitHub issue-first**:

1. A GitHub issue describes a research hypothesis.
2. The orchestrator detects the issue.
3. Agents/code produce or update strategy code/config.
4. GitHub Actions launches a QuantConnect backtest.
5. QuantConnect Cloud runs the backtest.
6. The orchestrator watches for completion, pulls/links results, and posts/sends summaries.

### Issue detection

Decision so far: **Orchestrator on the VPS detects research issues**.

Rationale:

- It already runs 24/7.
- It already owns queue/outbox/notifications.
- It can resume after failures.

### QuantConnect execution split

Important clarification: the actual backtest runs on **QuantConnect Cloud**, not on GitHub or the VPS.

Proposed responsibility split:

- **GitHub Actions** = launch/submitter only.
  - Receives workflow inputs.
  - Syncs/updates QuantConnect project if needed.
  - Compiles if needed.
  - Submits backtest.
  - Captures `project_id`, `compile_id`, `backtest_id`, `workflow_run_id`.
  - Exits quickly; does not wait for multi-hour tests.
- **QuantConnect Cloud** = LEAN/backtest engine.
- **VPS Orchestrator** = long-running watcher/coordinator.
  - Polls slowly.
  - Tracks job state.
  - Fetches/links results.
  - Produces summaries/reports/notifications.

### Launch trigger

Decision so far: **Hybrid label + `workflow_dispatch`**.

- Labels provide visible state on the issue, such as `research:queued`, `research:launching`, `research:running`, `research:completed`, `research:failed`.
- `workflow_dispatch` provides exact structured inputs, such as strategy, symbol, dates, parameters, issue number, and run id.

## Storage Design Principles

1. Do not store everything forever.
2. Store enough to reproduce and compare research decisions.
3. Keep long-term data small, readable, and versioned.
4. Keep raw/debug artifacts temporary unless a run is important.
5. Preserve linkability between GitHub issue, GitHub Actions run, QuantConnect backtest, VPS state, and final report.
6. Avoid using GitHub artifacts as a long-term data warehouse.
7. Use compression for raw text-heavy artifacts.

## Proposed Storage Layers

### 1. VPS SQLite — operational source of truth

SQLite on the VPS stores both in-progress and completed run records.

For **in-progress runs**, SQLite is the operational source of truth.
It should contain enough data for the orchestrator to resume after restart/failure.

For **completed runs**, SQLite becomes an index/catalog, not the full archive.
It should point to reports, metrics, QuantConnect ids, artifacts, and issue links.

Candidate table: `research_runs`

Suggested fields:

```text
run_id
issue_number
issue_url
strategy_name
symbol
status
status_detail
parameters_json
github_workflow_run_id
github_workflow_url
quantconnect_project_id
quantconnect_compile_id
quantconnect_backtest_id
quantconnect_backtest_url
report_path
metrics_path
repo_commit_sha
artifact_url
artifact_storage_kind
artifact_expires_at
artifact_sha256
compressed_artifact_bytes
uncompressed_artifact_bytes
verdict
retry_count
last_poll_at
next_poll_at
created_at
submitted_at
completed_at
updated_at
```

Operational statuses may include:

```text
queued
launching
submitted
running
fetching_results
reporting
completed
failed
cancelled
timeout
needs_human
```

### 2. Repo — long-term research ledger

The repo stores small, durable, human/auditable outputs.

Proposed structure:

```text
research-runs/
  2026/
    06/
      2026-06-10-spy-bull-put-001/
        run.yaml
        report.md
        metrics.json
```

#### `run.yaml`

Purpose: reproducibility and linking.

Should include:

```yaml
run_id: 2026-06-10-spy-bull-put-001
issue: 123
issue_url: https://github.com/atzmonpersonalassistant/trader/issues/123
strategy: spy_bull_put_credit_spread
symbol: SPY
commit_sha: abc123
quantconnect:
  project_id: 123456
  compile_id: abcdef
  backtest_id: deadbeef
  backtest_url: https://www.quantconnect.com/project/...
github_actions:
  workflow_run_id: 123456789
  workflow_url: https://github.com/atzmonpersonalassistant/trader/actions/runs/123456789
parameters:
  dte_min: 30
  dte_max: 45
  short_delta: 0.20
  spread_width: 5
  start_date: 2018-01-01
  end_date: 2025-12-31
assumptions:
  fees: TBD
  slippage: TBD
  benchmark: SPY buy-and-hold
artifacts:
  temporary_url: null
  expires_at: null
  sha256: null
verdict: refine
created_at: 2026-06-10T00:00:00Z
completed_at: 2026-06-10T00:00:00Z
```

#### `metrics.json`

Purpose: machine-readable summary metrics.

Should include:

```json
{
  "return": null,
  "max_drawdown": null,
  "win_rate": null,
  "profit_factor": null,
  "trade_count": null,
  "benchmark_return": null,
  "fees": null,
  "slippage": null,
  "regime_summary": {},
  "verdict": "refine"
}
```

#### `report.md`

Purpose: human-readable research memory.

Should include:

- Hypothesis.
- Strategy/config tested.
- Date range and data source.
- Assumptions: fees, slippage, benchmark.
- Key results.
- Regime breakdown.
- Failure modes.
- Bias/overfit concerns.
- Verdict: `discard`, `refine`, or `paper-test candidate`.
- Links to issue, GitHub Actions run, QuantConnect backtest, and temporary artifacts if any.

### 3. GitHub issue — visibility and links only

GitHub issue comments are not the source of truth.

They should contain concise status updates and links:

```text
Research run completed ✅

Run: 2026-06-10-spy-bull-put-001
Verdict: refine
Report: <repo link>
QuantConnect: <backtest link/id>
Workflow: <actions run link>
```

This keeps the issue self-contained without duplicating full reports or raw data.

### 4. GitHub Actions artifacts — temporary compressed artifacts

Artifacts are useful for debugging and handoff between launch/reporting stages, but should not be long-term storage.

Suggested artifact:

```text
artifacts.tar.zst
```

Contents may include:

```text
raw-qc-response.json
orders.jsonl or orders.csv
charts.json
logs.txt
launch.json
backtest-submit-response.json
```

Retention policy:

```text
default successful run: 7 days
failed/debug run: 14 days
important/promotion candidate: 30-90 days
long-term raw artifact retention: only by explicit keep flag
```

Compression recommendation:

- Prefer `zstd` for text-heavy artifacts if available.
- Use `tar.gz` if compatibility is more important.

Expected compression:

- JSON/CSV/logs: often 70-95% smaller.
- Charts/images: little benefit if already compressed.
- Parquet: already compressed depending on codec.

### 5. QuantConnect — original raw backtest source

QuantConnect should remain the original raw backtest source.

We store references:

```text
project_id
compile_id
backtest_id
backtest_url
```

QuantConnect can provide, depending on API and plan:

- statistics.
- charts.
- orders.
- logs.
- backtest reports.

Known constraints from research:

- Quant Researcher tier has about 100KB logs/backtest and 3MB logs/day.
- If backtest result payload exceeds around 700MB, QuantConnect may not upload/display results properly.
- If a backtest is deleted or the account/project is inactive for 12 months, QuantConnect may archive results.
- QuantConnect should be treated as the execution platform and original results source, not our research ledger.

## GitHub Artifact Cost Notes

The `trader` repo is private.

GitHub documentation says private repositories receive included Actions minutes and artifact storage depending on plan:

```text
GitHub Free: 500MB artifacts, 2,000 minutes/month
GitHub Pro: 1GB artifacts, 3,000 minutes/month
GitHub Team: 2GB artifacts, 3,000 minutes/month
Enterprise Cloud: 50GB artifacts, 50,000 minutes/month
```

GitHub Actions storage billing is hourly/GB-hour based. Deleting artifacts reduces current storage and future accrual, but does not erase already-accrued usage during the billing cycle.

GitHub pricing references suggest additional storage is roughly `$0.25/GB-month` (about `$0.008/GB-day`), but exact billing should be verified in GitHub Billing UI for the account.

The current CLI token could not read billing details for the personal account (`403`), so exact account plan/usage must be checked in GitHub UI:

```text
GitHub -> Settings -> Billing and licensing -> Usage / Metered usage -> Actions
```

## Expected Storage Size

For MVP1 simple SPY/QQQ daily-ish options research:

Single run, compressed:

```text
config/spec: KBs
metrics/report: <1MB usually
raw JSON/CSV/logs compressed: often <1-5MB
```

Parameter sweeps of 50-100 backtests may be tens of MB or more depending on saved raw data.

The risk is not one run. The risk is hundreds/thousands of runs with no compression, retention, or cleanup policy.

## What To Keep Forever

Keep long-term:

- `run.yaml`
- `report.md`
- `metrics.json`
- QuantConnect ids/links
- GitHub issue/workflow links
- verdict and decision rationale

Do not keep forever by default:

- raw logs
- full raw API responses
- full order dumps
- full chart points
- debug archives

Keep raw artifacts longer only when:

- the run is promoted toward paper trading.
- the run is unusually important.
- the run failed in an informative way.
- Uriel explicitly requests preservation.

## Open Questions

1. Should repo reports live under top-level `research-runs/` or under `planning/reports/research-runs/`?
2. What is the exact retention default: 7 days or 14 days?
3. Should important raw archives be stored on VPS disk, GitHub artifacts, QuantConnect Object Store, or future object storage?
4. Should the orchestrator automatically create a PR with `run.yaml`, `metrics.json`, and `report.md` after every completed run?
5. Should completed failed runs always create repo reports, or only issue comments/state records?
6. Should the report generator run on the VPS or in GitHub Actions after QuantConnect completion?

## Current Recommendation

For MVP1:

- VPS SQLite = operational state and completed-run index.
- Repo = small long-term research ledger (`run.yaml`, `metrics.json`, `report.md`).
- GitHub issue = short visibility update with links.
- GitHub Actions artifacts = compressed temporary debug/raw bundle with short retention.
- QuantConnect = original raw backtest result source.

This gives full linkability without turning GitHub artifacts or git history into a heavy data warehouse.
