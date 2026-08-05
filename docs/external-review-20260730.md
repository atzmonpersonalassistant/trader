# External Review Findings - 2026-07-30

Source: https://stormy-rafter-c9fc.here.now/
Archived by Codex autonomous worker on 2026-07-30 because the source Site was reported to expire on 2026-07-31T12:20Z.

# Trader earnings-QC research system — findings and action items

External review, 2026-07-30. Compiled by Claude (reviewer) with read-only access to
`atzmonpersonalassistant/trader`.

Ordered by information gained per unit of effort. Each item's value depends on the ones above it.

**VERIFIED** = I read the code and confirmed it myself. **REVIEW** = found by a delegated review pass,
substantive but not personally re-verified.

## Why this list exists

The system has never run a valid end-to-end test. Two defects were concealing each other: the
multi-year gate was unsatisfiable at `--years 1`, so it emitted zero final candidates and
looked cautious — and on the one day it did fire, it promoted SPCE with a **negative mean return** and
1 win in 15 trades. Fixing the first exposed the second. The items below are what stands between the
current state and a first trustworthy run.

One pattern accounts for six separate defects: **a field asserting behaviour the code does
not implement** — the status label claiming historical validation it never ran, the 3y/5y windows
claiming coverage from one year of data, promotion reading the aggregate instead of the per-candidate
status, `strike_window_per_expiry` reporting 30 while the code used 100,
`final_candidate_gate` advertising thresholds the deciding gate never reads, and six CLI flags
recorded in the database as applied and then discarded. **Standing rule: every reported limit, threshold
or status must be emitted by the code path that enforces it, never restated alongside it.**

## P0 — do these first, in this order

### P0-1  The dropout may be DAILY option resolution, not liquidity policy `VERIFIED`

**evidence — generated multiyear algorithm**

```
self.universe_settings.resolution = Resolution.DAILY
opt = self.add_option(c["symbol"], Resolution.DAILY)
...
"missing_volatility_inputs": iv is None or delta is None
def liquidity_pass(self, q, spot, dte):
    ...
    if m['missing_volatility_inputs']: return False
```

**how it fails**

Entry requires both IV and delta per contract while the subscription is DAILY. QC option data is
minute-native, so DAILY does not reduce what QC reads — it coarsens the quotes and Greeks the gate depends
on. If either comes back `None`, every contract fails, every event drains into
`no_eligible_entry_contract`, sample size falls under 12, and the run reports
`BLOCKED_HISTORICAL_OPTION_WINDOW_GATE` — indistinguishable from "the strategy does not work".

**why this outranks the liquidity split**

The forward scan reported `missing_greeks: 0`, so Greeks are present *there*. The dropout
appears in the **multiyear** stage: TE 1 trade from 4 events, VNET 0 from 3, JOBY 6 from 22.
I previously attributed this to the OI/volume split and asked for the forward scan to match the validator
(PR #129). That change is still correct on its own terms, but it may not touch the dropout at all.

**the test — one symbol, one run, four numbers**
1. add a `missing_volatility_inputs` counter to the `blockers` dict — right now
`liquidity_pass` returns a bare `False` and the caller records only
`no_eligible_entry_contract`, so missing Greeks is invisible
2. re-run the multiyear for ONE symbol with option resolution MINUTE or HOUR instead of DAILY
3. report `historical_event_count`, `sample_size`, the `blockers` dict,
and the new counter

**Hold PR #129 until this is answered.** If the cause is resolution, #129 tightens the forward funnel
for no gain while the real cause stays untouched.

### P0-2  Forward candidates are silently discarded whenever a chunk finds 3 or more `VERIFIED`

**evidence — export side, then the parent that reads it**

```
self.set_runtime_statistic("trader.candidates_json",
    json.dumps(self.candidate_details[:40], sort_keys=True, separators=(",",":"))[:3900])
```

```
try:
    candidate_details = json.loads(stats.get('trader.candidates_json') or '[]')
except Exception:
    candidate_details = []
    candidate_details_parse_failed = True
```

**how it fails**

`[:3900]` slices the JSON *string*, not the list. I measured a real candidate payload —
symbol, spot, earnings date, two status strings, contract count, two best contracts with full diagnostics —
at **~1,385 characters**. So the budget holds **two** candidates. At three the JSON is cut
mid-structure, `json.loads` raises, and the chunk reports **zero** candidates. Meanwhile the
count comes from a different, untruncated statistic (`trader.candidates`), so the funnel says
three while the list is empty.

**why nobody noticed**

Chunk size 25 → 191 symbols is 8 chunks, and recent runs found roughly one candidate per chunk.
**It only bites on a good day** — which means it will mask exactly the improvement every other fix on
this list is meant to produce.

**fix**

Candidates already travel intact in the properly chunked payload the parent reassembles
(`trader.stage2_json_NN`). Read them from there, or chunk `candidates_json` the same
way. Make `candidate_details_parse_failed` a **hard chunk failure** — a chunk that cannot
report its candidates has not succeeded. Add an assertion that
`candidate_count == len(candidate_details)` and fail loudly on mismatch.

### P0-3  The deploy restarts services an operator deliberately stopped — this caused both incidents `VERIFIED`

**evidence — vps-deploy.yml ~line 587**

```
if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files --type=service | grep -q '^trading-research-agent\.service'; then
  sudo systemctl restart trading-research-agent.service
fi
```

**how it fails**

`systemctl list-unit-files` lists units **regardless of state** — a disabled, stopped unit
still appears, with state `disabled`. So the guard only asks "does a unit file exist on disk",
which is true for a service that was deliberately stopped. And `systemctl restart` on an
inactive unit **starts** it.

This is the root cause of the unguarded generation windows on 07-29 and 07-30 (11:06–11:15Z). The
service was inactive and disabled; the 12:30Z deploy matched this guard and brought it back ACTIVE.

**fix — note the verb**

```
if systemctl is-enabled --quiet trading-research-agent.service && systemctl is-active --quiet trading-research-agent.service; then
  sudo systemctl try-restart trading-research-agent.service
fi
```

`try-restart` restarts only an already-running unit and is a no-op otherwise. Do not use
`restart`.

**Blocker:** `agent-platform/tests/test_mvp0_agents.py` asserts the literal string
`systemctl restart trading-research-agent.service`. CI will fail until that assertion is
updated in the same change — the bug is test-locked.

### P0-4  A truncated SSH stream produces a green deploy `VERIFIED`

**how it fails**

The remote script runs via `bash -s` fed from a heredoc over SSH. bash reads and executes
incrementally, so if the stream is cut — network blip, idle timeout, sshd disconnect, runner hiccup — bash
sees a clean EOF and exits with the status of whatever it last ran. Usually 0. `ssh` returns 0,
the step is green, and half the binaries are installed with none of the verification run.

**the sentinel exists and is never checked**

There is an `echo DEPLOY_OK` at the end of the remote script. I grepped the whole workflow:
**it appears exactly once — the echo itself.** Never captured, never asserted.

**fix**

```
ssh ... | tee /tmp/deploy.out
grep -q '^DEPLOY_OK$' /tmp/deploy.out
```

Better: `scp` the script and run it from a file, so truncation is impossible. Also note
`concurrency: cancel-in-progress: true` — two merges in quick succession kill deploy #1
mid-script and label the run *cancelled*, not failed.

### P0-5  Three copies of the final gate; the deciding one ignores every threshold you set `VERIFIED`

**evidence — the runner has its own gate, hardcoded**

```
def result_passes(r:dict)->bool:
    if r.get('status')!='OK': return False
    ...
    base_ok = sample>=12 and win>=0.35 and mean>0 and loo>0 and dropout<=40 and dd<80 and ml>-95
```

No `os.environ`, no `QC_FINAL_*` lookup. The runner also carries its own
`candidate_historical_status_blocks()` and `promoted_final_candidate()`, and writes
`final_candidates`, `candidate_count`, `final_candidate_count`,
`ok` and `status` directly into `full_summary.json`.

**and the caller adopts it wholesale**

```
mb = None if (args.end_to_end and summary.get('chunk_multiyear_statuses')) else run_multiyear_if_requested(run_dir, args)
if mb is not None:
    fp = run_dir/'full_summary.json'
    if fp.exists():
        summary = json.loads(fp.read_text())
```

**why the failure direction matters**

Loosening a threshold via env is inert — harmless. **Tightening one is also inert** — not harmless.
The `win_rate >= 0.35` decision, #124's criteria, any sweep: all operate on values the deciding
path never reads, while the artifact's `final_candidate_gate` block advertises the stricter
numbers as though applied. **The safety rail is currently unadjustable.**

**trigger**

`run --no-end-to-end`, then `run --resume --end-to-end` on the same run-dir.
Chunks then have `candidate_details` but no `chunk_multiyear_backtest`, so
`chunk_multiyear_statuses` is empty and the run-level runner fires.

**fix**

Delete `result_passes`, `candidate_historical_status_blocks` and
`promoted_final_candidate` from the runner — it emits `results` only and never writes
promotion fields. `earnings-qc-research` owns promotion in exactly one function. Also reconcile
`aggregate()` and `refresh_summary_after_historical()`, which still disagree: with
zero forward candidates one gives `ok=True / OK_FULL_QC_SCAN` and the other
`ok=False / NO_FORWARD_CANDIDATES`; `refresh`'s `ok` ignores
`historical_failed_chunks` entirely.

**test that proves it**

Set `QC_FINAL_MIN_WIN_RATE=0.99` against a fixture that otherwise passes; assert zero final
candidates. That one test would have caught this.

## P1 — correctness

### P1-6  The one fail-open default in the gate `VERIFIED`

```
windows = r.get('window_results') or []
if windows:
    return base_ok and all(...)
return base_ok
```

Missing or empty `window_results` skips the per-window requirement entirely — absent data
yields PASS. Every other field in both gate copies defaults fail-closed, correctly; this is the single
exception. Should be `BLOCKED_MISSING_WINDOW_EVIDENCE`. Three lines.

### P1-7  The backtest cannot fit in node memory `VERIFIED`

```
self.snapshots.setdefault(sym, {})[day]={"underlying":round(spot,4),"contracts":rows}
```

Grepped for `del`, `pop`, `clear` on that dict: **zero hits**. It
accumulates every day's full contract list for every symbol across the whole span — up to 10 years, up to
25 symbols per chunk, with `strikes(-50, 300)` and no `calls_only()`, so half of what
is stored is puts the code discards on the next line.

Order of magnitude: ~3,000 rows/day/symbol, ~2 MB/day/symbol, ~2,000 sessions → gigabytes for a single
symbol. And `on_end_of_algorithm` reads exactly two snapshot dates per event, so >99% is never
touched. Keep only the entry/exit windows of the next unprocessed event, or use
`self.object_store`.

Worth cross-checking against the 20 `QC_BACKTEST_FAILED` statuses in history —
an OOM or node timeout on a 10-year 25-symbol run would present exactly that way.

### P1-8  Chunked payloads reassemble out of order past 99 fragments `VERIFIED`

```
for i in range(0, len(txt), 3500):
    self.set_runtime_statistic('multiyear_json_%02d' % (i//3500), txt[i:i+3500])
...
parts=[stats[k] for k in sorted(stats) if k.startswith('multiyear_json_')]
```

`%02d` does not zero-pad past 99 and `sorted()` is lexicographic, so
`multiyear_json_100` sorts **before** `multiyear_json_99`. Past ~350 KB the
fragments scramble and `json.loads` fails into `parse_error` — reported as a parse
failure, not as truncation, after a 10-year backtest is already paid for. The payload includes full
`trades` and `per_trade_return_pct` for up to 25 symbols, so 350 KB is reachable.

Same defect: `stage2_json_%02d`. `qc_extract_json_%03d` breaks at 1000 instead.
Use `%04d`, or stop using runtime statistics as a data channel —
`self.object_store` is the intended vehicle and appears nowhere in the tree.

### P1-9  Validation runs after mutation, and after the restart `VERIFIED`

Ordering in the remote script: all binaries installed → the new loop is *executed* as a smoke test →
service restarted → **then** `bash -n` syntax checks → **then** ~30 guardrail greps.

So the live service runs new code before `bash -n` has confirmed it parses. A guardrail-grep
failure is exactly the signal "we just shipped something that lost a safety property" — and by the time it
fires, the unsafe code is live with no rollback.

**Fix:** run every syntax check and guardrail assertion against the staging directory before the first
`install`; move the restart to the last statement before the `DEPLOY_OK` sentinel.

### P1-10  The deploy cannot detect that it regressed live behaviour `VERIFIED`

Grepped the workflow for every drift primitive — `cmp`, `--backup`,
`sha256sum`, `md5sum`, `rsync`: **zero hits**. ~20
`sudo install` calls overwrite live paths unconditionally, with no diff, no backup, no log line
noting the previous content differed.

**And this is why the ~30 guardrail greps did not help:** every one greps the file the deploy just
installed *from the repo*. They are tautological with respect to live state and can only detect a
regression *in the repo*. A guardrail existing only on the box is invisible to all of them by
construction.

**Fix:** `cmp -s` each target against the incoming file before install and log any
difference; `install --backup=numbered` or copy the previous version to
`/var/backups/trader-deploy/<sha>/`. This is the only change that makes the next revert
detectable rather than archaeological.

### P1-11  The backtest ignores six parameters it is handed `VERIFIED`

`--entry-window`, `--exit-days-before`, `--exit-policy`,
`--historical-resolution`, `--max-contracts`, `--path-metrics` are parsed
into `params`, echoed into `parameters_json`, and **never passed to
`write_project()`**. The generated algorithm hardcodes the real criteria:

```
self.max_premium = 0.50
self.max_days_after_earnings = 7
self.entry_min_days = 21
self.entry_max_days = 28
self.max_spread_pct = 0.60
self.min_bid = 0.05
self.min_open_interest = 50
self.min_volume = 10
opt.set_filter(... .strikes(-50, 300) ...)
```

So every "parameter experiment" burns a full multi-year all-strikes backtest producing
**byte-identical logic** to the previous one, with the requested values recorded as though applied.
Any comparison of sweep results is comparing noise. **This is a prerequisite for any premium sweep** —
a sweep at `QC_MAX_PREMIUM=2.00` surfaces candidates at 2.00 and validates them against a fixed
0.50 ceiling.

Also here: `dte < 1` admits 1DTE contracts, which the mandate excludes.

### P1-12  Funnel measurement bugs — these corrupt the numbers we reason from `VERIFIED`

**(a) Zero-bid contracts double-count.** When `bid <= 0`, `mid2` is
`None`, `rel_spread` becomes the sentinel 999, and the contract then fails the spread
check — recording **both** `low_bid` and `spread_too_wide`. The 297 spread and 210
bid failures overlap heavily; spread-too-wide is largely an artifact of having no bid. Record
`no_two_sided_market` instead, and never let a missing mid manufacture a spread failure.

**(b) Stage 03 measures two filters and reports one.** `selected` applies the expiry
window *and* the OTM strike test, but increments
`expiry_within_0_7d_after_earnings`. Symbols dropped for having no OTM strike are misattributed
— which specifically hides the number most relevant to the moneyness question. Split the counters.

**(c) Duplicate key in the funnel literal.**
`expiry_within_0_7d_after_earnings` appears twice in the same dict. Legal Python, second wins,
but a stage counter was probably intended and is silently unmeasured.

**(d) Nothing validates that `spot` is positive.** The OTM test is
`float(c.strike) > spot`. A zero or stale spot makes every strike qualify and silently nulls
`required_move_pct`. TE reported spot exactly 5.00 on 07-28 — check whether that path fired.
Assert `spot > 0` and record `spot_unavailable`.

### P1-13  Rate limits and timeouts are misclassified as strategy failure `REVIEW`

Only one of four backtest launchers recognises quota errors, by stdout substring match on
`too many backtest requests` / `no spare nodes available`. Everywhere else a 429
becomes `QC_BACKTEST_FAILED` → `BLOCKED_MULTIYEAR_OPTION_PNL_BACKTEST`: a transient
quota error **permanently marks a hypothesis as blocked** and consumes the run slot. Lift the retry into
a shared helper and classify quota distinctly from strategy failure.

`subprocess.TimeoutExpired` is uncaught at six launch sites, so a timeout yields a raw
traceback instead of the structured `fail(...)` JSON callers parse. And killing the local
`lean` process **does not cancel the cloud backtest** — there is no abort call anywhere in the
tree, so the node runs to completion unread.

`trading-research-qc-api-extract` has `"ok": data.get("success", True)` — a
response shape missing the field is promoted to success, and the caller gates on exactly that field.

### P1-14  `retry-failed` silently mixes parameters `REVIEW`

It passes `args=None` into `run_chunk`, so retried chunks are re-scanned under
**default** parameters — no `--as-of-date`, no premium/liquidity/expiry/delta/IV knobs, no
`--symbols` — then aggregated alongside chunks scanned with the run's real parameters. The
subparser offers no way to supply them. One run, two parameter sets, no marker.

### P1-15  The database asserts validation it has no record of `REVIEW`

On the chunked path, dossier rows get `verdict='final_candidate'` with
`historical_pnl_json='{}'`, because the evidence lives in each chunk's
`chunk_multiyear_backtest` rather than `summary['multiyear_backtest']`.

Related labelling defects: `historical_option_pnl_years_{years}` is named from the
**scan** horizon (default 1) while validation used `--validation-years` (default 10);
`'NOT_IMPLEMENTED_IN_RUNNER_YET_QC_EODHD_APPROVED'` is persisted whenever the gate did not run,
claiming non-implementation for an implemented gate; funnel keys and the Hebrew report hardcode "0-7d" and
"21-28d" even when the flags change them; and `to_stage == 'candidate_scan'` overwrites
`historical_gate_blocked` to False while leaving `multiyear_failed` intact, masking a
real infrastructure failure as `ok=True`.

## Security

### S-1  Plaintext QuantConnect token, guessable path, world-traversable, cleanup only on success `REVIEW`

The token is `scp`'d to `/tmp/trader-agent-tools-<commit sha>`. The SHA is
public, so the path is guessable; the directory is created with plain `mkdir` at
`0755`; and `scp` without `-p` does not carry the source's
`0600`. So during the install phase the token is readable by **every local user** — including
`agent-coding`, `agent-review`, `agent-research-runner` and
`agent-research-watchdog`, the exact four principals the workflow itself asserts must
*not* have QC access.

Cleanup is the last line under `set -euo pipefail`, so any earlier failure — including any
guardrail grep — leaves the plaintext token on disk indefinitely, one directory per failed SHA.

**Fix:** `install -d -m 700`, `scp -p`, `chmod 600` immediately after
upload, and move cleanup into a remote `trap ... EXIT`.

### S-2  The QC secret on the box is overwritten unconditionally, while its sibling is guarded `REVIEW`

The research env file uses the correct idiom —
`if ! sudo test -e ... then install /dev/null`. The QuantConnect env file does not: it is
installed unconditionally on every deploy. A token rotated on the box during an incident is reverted to the
GitHub Secrets value on the next merge, and `lean login` then re-authenticates with the reverted
credential — surfacing later as a QC auth error with no obvious link to the deploy.

Repo secret audit, for the record: I scanned all 137 commits. No IP addresses, no
key-shaped strings, no credential files ever tracked. The workflow references everything properly through
`${{ secrets.* }}`. The VPS address is not in the repo at all.

## Waste — we are not leveraging QC

### W-1  Cloud backtests used as a data API, at ~66× the needed subscription `VERIFIED`

Stage 2 is not a backtest — it is a query: "for these 25 symbols, on this one date, give me the option
chain." It is implemented as a compiled cloud backtest whose results are smuggled out through numbered
status strings in 3,500-character fragments, with a 3,900-character cap on the part that matters. That
design *is* what created P0-2.

|                        | current                              | what the strategy needs |
| ---------------------- | ------------------------------------ | ----------------------- |
| strikes                | `strikes(-50, 300)` = 351 per expiry | ~30 above spot          |
| expiries               | `expiration(0, 120)` ≈ 17 weeklies   | ~3                      |
| per symbol             | ~5,967 contract subscriptions        | ~90                     |
| per chunk (25 symbols) | ~149,000                             | ~2,250                  |

**~66× over-subscription**, paid on every symbol of every chunk of every daily run. The multiyear
filter is worse: same `strikes(-50, 300)`, no `calls_only()` despite discarding every
put on the next line, over a 10-year span.

**The right fix:** move the single-day snapshot to QC's Research environment
(`qb.option_chain` / `qb.History(option_symbol, ...)`) — no algorithm, no compile, no
queue, no length-capped output channel. That removes P0-2 rather than patching it and collapses eight
serial backtests into a few API calls. Reserve backtests for the multi-year validation, which genuinely
needs to simulate time.

**The cheap interim fix:** narrow to roughly `strikes(0, 40).expiration(18, 40)` and add
`calls_only()`. No behaviour change, immediate saving.

Your own loop comment already states the intent: QuantBook is "the preferred diagnostics and
exploration layer before cloud backtests". But `TRADING_RESEARCH_FORCE_QC_CLOUD_EXTRACT`
defaults to `1`, so the broker tries the surfaces in **most-expensive-first** order. The
QuantBook probe is currently weaker only because it calls `GetOptionContractList` and never
requests quotes or Greeks.

### W-2  Project and compile waste `REVIEW`
- every backtest **pushes twice** — an explicit push, then `lean cloud backtest --push`.
The scan retry loop re-pushes on each of up to four attempts.
- `trading-research-qc-run` creates a **new timestamped QC cloud project per run**, with no
`cloud-id` cached and no `projects/delete` anywhere in the tree. A 4-variation sweep
is 4 new cloud projects and 4 cold compiles.
- the `cloud-id` cache in the earnings paths is **defeated by ordering**:
`config.json` is written with `'cloud-id': 0` and only *then* is
`ensure_qc_project` called, whose fast path tests `cloud-id > 0`. Never true — so
every chunk does a full `projects/read` account listing, which gets slower as the orphaned
projects above accumulate.
- algorithms are generated by string interpolation with dates baked in, so the source changes daily even
when nothing semantic did — **no compile caching is possible by construction**. Use
`self.get_parameter()`, which already works elsewhere in this codebase.
- stage 2 loads and discards a full extra session: `start = previous_weekday_before(valuation_date)`
as a "warm-up", but `on_data` opens with `if current_date < self.valuation_date: return`.
Use `set_warm_up`.
- fixed sleeps instead of asking QC about capacity — 30 s between chunks, 300 s between sweep variations.
No `nodes/read` call exists anywhere.

### W-3  Deploy waste on every merge `REVIEW`
- a multi-GB `docker pull` of `quantconnect/research:latest` on **every**
deploy, including doc-only changes — a `docker image inspect` already exists later in the file
and could gate it
- `apt-get update` run up to **four times** in one deploy
- `pip install --break-system-packages --upgrade lean` — **unpinned**. A new
`lean` release silently changes the deployed toolchain with no repo change: another source of
"live behaviour changed and nothing in git explains it". Pin it.
- a `chmod` walk over every file in `site-packages/lean` on every deploy, even when
the install was skipped
- full 30-file `scp` every run with no checksum comparison — which also makes P1-10 worse,
since nothing knows which files actually changed
- the deploy silently reverts and re-enables cron: it strips managed blocks and specific bare lines, then
unconditionally re-appends the `*/5` postrun-review and `*/15` watchdog schedules.
An operator who disabled either has it reinstated on the next merge. Same for
`earnings-otm-daily.sh`, regenerated from a heredoc, so live edits to its flags are reverted.

## In-flight work
- **PR #129** — forward scan adopting the validator's OI/volume rule, and un-hardcoding the backtest
knobs. **Hold the OI/volume half until P0-1 is answered**; the knob-threading half is P1-11 and should
land regardless.
- **PR #128** — resolve the reviewer disagreement by doing **both**: a shell-level skip of
`generate-ideas` when the provider is missing, *and* the Python candidate-level filter,
*and* gate the legacy seed path. They operate at different times and are not alternatives. Eleven of
the twelve generated queue rows were event-driven, so "preserving non-event work" protects one off-mandate
item — and a single fine-grained layer is exactly what the 12:30Z deploy removed. Keep
`TRADING_RESEARCH_REQUIRE_EVENT_PROVIDER=0` as the explicit opt-out.
- **After any deploy, re-run the four file-level greps and report the numbers, not a summary.** A green
workflow hid a partial restore for three hours.
- **Quarantine** the 19 directories (3 + 11 on 07-29, 1 + 4 on 07-30) and 12 queue rows — move, do not
delete; mark rows `produced_without_event_guardrails`.

## Needs Uriel, not the agent
- **`win_rate >= 0.35` versus the premium cap** — convex or directional. Deep OTM
pre-earnings calls win 15–25% and pay in the tail, so a 35% floor while the cap forces deep OTM strikes is
the two halves of the system disagreeing. **Blocked behind P0-5** — the threshold is not currently read
by the deciding path, so there is nothing to decide yet. It is a risk-appetite question, not a measurement:
the agent may sweep it as a labelled experiment, but final promotion must only count under the agreed
defaults, and any candidate produced under an override must be stamped override-derived.
- Quarantine approval.
- Repo visibility — flip back to private and add `sawuratzmon` as a read-only collaborator.
History is clean, so nothing leaked; but forks made while public survive the flip.

## Two suggested standing tests
1. `QC_FINAL_MIN_WIN_RATE=0.99` on a passing fixture must yield zero final candidates.
Catches P0-5 and any future re-divergence of the gate.
2. A guardrail **manifest** — file + pattern + must-exist/must-not-exist, iterated in one loop — instead
of the hand-listed greps, so adding a guardrail forces adding its assertion. The generation gate has no
assertion today, which is precisely why it survived a capture, a PR, a review-agent pass and three deploys
unnoticed.
