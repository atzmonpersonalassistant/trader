#!/usr/bin/env python3
"""MVP-0 Coding Agent CLI skeleton.

This entry point intentionally does not modify repositories yet. It proves that
agent-coding can load configuration, accept an issue number, write an audit log,
and exit cleanly.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(os.environ.get("TRADING_CODING_CONFIG", "/agents/coding/config.json"))
DEFAULT_LOG_DIR = Path(os.environ.get("TRADING_CODING_LOG_DIR", "/agents/coding/logs"))

DEFAULT_CONFIG: dict[str, Any] = {
    "agent": "coding",
    "repo": "atzmonpersonalassistant/trader",
    "base_branch": "main",
    "workspace_root": "/agents/coding/workspaces",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_config(path: Path) -> tuple[dict[str, Any], bool]:
    if not path.exists():
        return dict(DEFAULT_CONFIG), False
    with path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    config = dict(DEFAULT_CONFIG)
    config.update(loaded)
    return config, True


def write_log(log_dir: Path, event: dict[str, Any]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "coding-agent.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")
    log_path.chmod(0o600)
    return log_path


def cmd_run(args: argparse.Namespace) -> int:
    config, config_found = load_config(args.config)
    ts = now_iso()
    event = {
        "ok": True,
        "type": "coding_agent_run",
        "timestamp": ts,
        "issue": args.issue,
        "config_path": str(args.config),
        "config_found": config_found,
        "config": config,
        "user": os.environ.get("USER") or os.environ.get("LOGNAME"),
    }
    log_path = write_log(args.log_dir, event)
    print(json.dumps({**event, "log_path": str(log_path)}, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading-coding-agent")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run")
    run.add_argument("--issue", required=True, type=int)
    run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
