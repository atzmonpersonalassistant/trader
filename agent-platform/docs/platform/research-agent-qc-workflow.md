# Research Agent QuantConnect Workflow

The research agent should treat QuantConnect as the primary research/backtest platform and use the highest-leverage QC capabilities available before falling back to lower-level REST calls.

## Default operating mode

1. **Lean CLI first**
   - Prefer `lean cloud backtest <project> --push` for cloud execution.
   - Use `lean cloud pull`, `lean cloud push`, `lean cloud status`, `lean whoami`, and `lean logs` where available.
   - Use REST API directly only when Lean CLI does not expose the needed workflow or when collecting extra machine-readable artifacts.

2. **QC Cloud execution**
   - Backtests should run in QuantConnect Cloud unless explicitly marked as local diagnostics.
   - Local Lean/Docker backtests are optional and should not be required for MVP1.

3. **Diagnostics before broad backtests**
   - Before testing a strategy family broadly, run a diagnostic scan that counts:
     - signal occurrences,
     - option-chain availability,
     - contracts passing price/DTE/OI/volume/spread filters,
     - rejection reasons,
     - missing Greeks/IV fields,
     - trade counts by symbol/year/regime.
   - If diagnostics cannot be retrieved, mark the research run as technically blocked instead of pretending the hypothesis was validated or rejected.
   - The broker's bounded option-history probe writes `qc_option_history_extract.json` only after a successful QC/LEAN-compatible execution. Otherwise it writes `qc_research_execution_diagnostic.json` with explicit surface checks for auth, Lean CLI, local `clr`/`QuantConnect` imports, Docker availability, non-interactive research support, and cloud/API credit guardrails.

4. **Use QC primitives deeply**
   - Option universe / option chains.
   - Greeks, delta filters, implied volatility when available.
   - History and indicators: SMA, RSI, ATR, Bollinger, Donchian/high-low breakouts, volume expansion.
   - Scheduled events for scanners.
   - Backtest parameters for sweeps.
   - Object Store / logs / result artifacts when accessible by the account tier.
   - QC data coverage checks for underlyings and options.

5. **Research loop verdicts**
   - Every run ends with one of:
     - `discard`,
     - `refine`,
     - `retest_after_technical_fix`,
     - `candidate_for_validator_review`.
   - Never output a trade recommendation from a weak or technically blocked run.


## Backtest resolution support

The mandate-aware QC runner supports end-to-end backtest resolution selection at three levels:

- `daily` — default, cheapest/coarsest validation.
- `hour` — higher-resolution option/equity QuoteBar validation when entry/exit timing matters.
- `minute` — highest-resolution supported mode for short-dated/timing-sensitive validation; expect slower and more expensive QC runs.

Resolution can be set either in the manifest:

```json
"validation": {
  "start": "2018-01-03",
  "end": "2026-01-01",
  "backtest_resolution": "hour",
  "candidate_requires_2018_present_or_oos": true,
  "walk_forward_or_oos_required": true,
  "max_variations": 1
}
```

or overridden at the CLI:

```bash
trading-research-qc-run validate manifest.json --backtest-resolution minute
trading-research-qc-run prepare manifest.json --backtest-resolution hour
trading-research-qc-run sweep manifest.json --backtest-resolution daily
```

The runner persists the selected resolution into:

- `candidate.json` as `backtest_resolution`;
- `qc_cloud_run_manifest.json` as `backtest_resolution`;
- generated QC runtime statistics: `trader.backtest_resolution` and `trader.option_quote_resolution`;
- SQLite DB table `research_backtests.backtest_resolution` at `$TRADING_RESEARCH_DB` or `/agents/research/state/research_backtests.db`.

Indicators such as SMA/RSI may still use daily bars inside a higher-resolution backtest; the option/equity subscriptions used for trading and QuoteBar-driven option-chain data follow the chosen resolution.

## Platform workspace layout

- Role-private Lean workspaces live at `/agents/{research,coding,review,validator}/lean-workspace`.
- Shared Lean projects live under `/agents/shared/lean-projects`.
- Shared research outputs that should survive a single role workspace live under `/agents/shared/research-artifacts`.
- Raw QuantConnect credentials are not part of workspace access. `agent-coding` and `agent-review` may prepare or review Lean project files, but only `agent-research`, `agent-validator`, and `agent-orchestrator` can read `/etc/trading-agents/secrets/quantconnect/env`.

## Guardrails

- No live trading.
- No order placement outside backtests.
- No secrets printed to logs, reports, PRs, or chat.
- Do not widen to broad universes until diagnostics prove data availability and enough candidate events.
- Treat `no spare nodes available` as compute-capacity blocked, not strategy failure.
- Treat missing logs/object-store access as result-extraction blocked, not strategy failure.

## Prompt block for research runs

```text
You are the Strategy / Quant Research Agent for the Trader project.

Use QuantConnect as the primary research platform. Prefer Lean CLI and QC Cloud workflows over raw REST when possible. Use REST only for gaps or artifact extraction. Backtests must run in QuantConnect Cloud unless explicitly labeled local diagnostics.

For every hypothesis:
1. Convert the direction into a precise, testable research spec.
2. Run diagnostics first: signal count, option-chain availability, contract counts under filters, rejection reasons, missing Greeks/IV, and trade/event counts by symbol/year/regime.
3. Only run broad backtests after diagnostics show enough data/events.
4. Use QC capabilities deeply: option chains/universes, Greeks/delta/IV, History, indicators, scheduled scanners, cloud backtests, parameters/sweeps, logs/ObjectStore/artifacts where accessible.
5. Save artifacts under /agents/research/reports/<run-id>/ or /agents/shared/research-artifacts/<run-id>/ without secrets.
6. End with a verdict: discard, refine, retest_after_technical_fix, or candidate_for_validator_review.

Do not place live trades. Do not make trade recommendations from weak or technically blocked evidence. If QC access, compute nodes, logs, ObjectStore, or data coverage block the run, say so plainly and recommend the exact next technical step.
```

## Closeout review

When changing research-agent code, wrappers, prompts, setup scripts, or deploy logic, run the `autoreview` skill/helper before merge. Treat findings as advisory, verify against the actual code, fix accepted actionable findings, rerun focused tests, and rerun autoreview until clean.
