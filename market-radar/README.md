# Market Radar

RSS-only market-news radar.

It fetches configured market RSS feeds, scores relevant items, deduplicates previously seen stories, and can optionally send a concise Hebrew WhatsApp summary.

Design constraints:

- RSS only.
- No YouTube.
- No independent stock scanning.
- Avoid spam: if there are no high-value new RSS items, send nothing.

## Files

- `scan.py` — main RSS scanner.
- `run.sh` — launchd/cron-friendly wrapper with weekday/time gates.
- `output/` — local state/logs when configured to write here.


## Outputs

By default, runtime state/logs are written under:

- `market-radar/output/market_radar_state.json` — deduplication state for seen RSS items and recently sent stories.
- `market-radar/output/market_radar_cron.log` — wrapper log when `run.sh` is used with the default log path.

The paths can be changed with:

- `MARKET_RADAR_STATE_PATH`
- `MARKET_RADAR_LOG_FILE` for the wrapper log
- `MARKET_RADAR_LOG_PATH` for the script's internal log path if used

If `MARKET_RADAR_WHATSAPP_TARGET` is set, high-value summaries are sent to the **Market Radar** WhatsApp group. The repo does not hard-code the group JID; configure it through `MARKET_RADAR_WHATSAPP_TARGET`. If it is not set, the message is printed to stdout instead.

`market-radar/output/*` is ignored by git except for `output/README.md`. Runtime state/logs are local artifacts.

## Run manually

From the repo root:

```bash
MARKET_RADAR_IGNORE_MARKET_WINDOW=1 uv run python market-radar/scan.py --ignore-market-window
```

## Scheduler wrapper

```bash
market-radar/run.sh
```

Useful environment variables:

- `MARKET_RADAR_WHATSAPP_TARGET` — WhatsApp target for the **Market Radar** group.
- `MARKET_RADAR_STATE_PATH` — state file path.
- `MARKET_RADAR_LOG_FILE` — wrapper log file.
- `MARKET_RADAR_IGNORE_MARKET_WINDOW=1` — bypass script market-hours gate.
- `MARKET_RADAR_IGNORE_WRAPPER_WINDOW=1` — bypass wrapper time gate.
