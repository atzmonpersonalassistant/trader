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

- `MARKET_RADAR_WHATSAPP_TARGET` — optional WhatsApp target for sending summaries.
- `MARKET_RADAR_STATE_PATH` — state file path.
- `MARKET_RADAR_LOG_FILE` — wrapper log file.
- `MARKET_RADAR_IGNORE_MARKET_WINDOW=1` — bypass script market-hours gate.
- `MARKET_RADAR_IGNORE_WRAPPER_WINDOW=1` — bypass wrapper time gate.
