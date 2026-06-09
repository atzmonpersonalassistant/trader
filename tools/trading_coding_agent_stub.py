#!/usr/bin/env python3
"""MVP-0 Coding Agent dispatch stub.

This placeholder proves the Orchestrator can invoke work under the
agent-coding Linux identity. It does not modify code or open PRs yet.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOG_DIR = Path(os.environ.get("TRADING_CODING_LOG_DIR", "/agents/coding/logs"))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(prog="trading-coding-agent-stub")
    parser.add_argument("--issue-number", required=True, type=int)
    parser.add_argument("--issue-external-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    args = parser.parse_args()

    args.log_dir.mkdir(parents=True, exist_ok=True)
    ts = now_iso()
    event = {
        "ok": True,
        "type": "coding_agent_stub",
        "timestamp": ts,
        "user": os.environ.get("USER") or os.environ.get("LOGNAME"),
        "issue": {
            "number": args.issue_number,
            "external_id": args.issue_external_id,
            "title": args.title,
        },
    }
    log_path = args.log_dir / f"coding-stub-issue-{args.issue_number}.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")
    log_path.chmod(0o600)
    print(json.dumps({**event, "log_path": str(log_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
