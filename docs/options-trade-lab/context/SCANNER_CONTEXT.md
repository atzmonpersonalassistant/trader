# Existing Scanner Context

This document preserves what was built before `options-trade-lab` became the main project container.

## Previous Local Project

Older scanner code existed at:

```text
/Users/atzmonpersonalassistant/code/trading
```

Relevant files copied into this repository under:

```text
legacy/trading-scanner/
```

Copied files:

- `options_rules_scanner.py`
- `long_strangle_scanner.py`
- `requirements.txt`
- `README.md`
- latest CSV outputs if present

## Previous Continuation Scanner Behavior

The scanner was based on continuation rules from the options tracker:

- strong daily move
- price near high/low
- VWAP alignment
- EMA9/EMA21 alignment
- 60-minute slope
- HH/HL or LH/LL structure
- late volume
- option/risk/exit rules

Expected output style:

- Hebrew summary
- clear trade cards rather than raw tables
- contract
- price / max entry check
- trigger
- invalidation
- score
- volume/open interest
- IV
- bid/ask warning

If no clean option candidates exist, report strongest stock signals and say there is no clean option trade.

## Previous Cron Note

A previous cron job ran the continuation scanner every 30 minutes from the old folder with roughly:

```bash
source .venv/bin/activate && python options_rules_scanner.py --max-premium 1 --max-spread-pct 300 --top 5
```

That cron job was later cancelled/inactivated at Uriel's request. Delivery to a WhatsApp group had been unreliable; local send status was not proof of visible WhatsApp delivery.
