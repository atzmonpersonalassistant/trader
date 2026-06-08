#!/usr/bin/env python3
"""MVP-0 trading orchestrator CLI skeleton.

This is intentionally small: it creates the durable SQLite schema, exposes
operator commands, and implements a safe SQLite backup command. GitHub polling
and agent dispatch are added in later Group D tasks.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(os.environ.get("TRADING_ORCHESTRATOR_DB", "/agents/orchestrator/state/orchestrator.db"))
DEFAULT_BACKUP_DIR = Path(os.environ.get("TRADING_ORCHESTRATOR_BACKUP_DIR", "/agents/orchestrator/backups"))

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  number INTEGER,
  title TEXT,
  state TEXT NOT NULL DEFAULT 'unknown',
  labels TEXT NOT NULL DEFAULT '[]',
  payload_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pull_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  number INTEGER,
  issue_external_id TEXT,
  branch TEXT,
  state TEXT NOT NULL DEFAULT 'unknown',
  labels TEXT NOT NULL DEFAULT '[]',
  payload_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(issue_external_id) REFERENCES issues(external_id)
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT UNIQUE,
  entity_type TEXT NOT NULL,
  entity_external_id TEXT,
  event_type TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'new',
  payload_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS locks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL DEFAULT 'held',
  owner TEXT NOT NULL,
  labels TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  expires_at TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  entity_type TEXT NOT NULL,
  entity_external_id TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'started',
  labels TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  result_json TEXT
);

CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL DEFAULT 'pending',
  labels TEXT NOT NULL DEFAULT '[]',
  channel TEXT,
  message TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS inbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL DEFAULT 'new',
  labels TEXT NOT NULL DEFAULT '[]',
  source TEXT,
  message TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  acknowledged_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""

TABLES = ["issues", "pull_requests", "events", "locks", "attempts", "outbox", "inbox", "settings"]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        db_path.chmod(0o600)
    except FileNotFoundError:
        pass
    return conn


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        ts = now_iso()
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("schema_version", "1", ts, ts),
        )


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in TABLES}


def cmd_status(args: argparse.Namespace) -> int:
    init_db(args.db)
    with connect(args.db) as conn:
        data: dict[str, Any] = {
            "ok": True,
            "db_path": str(args.db),
            "backup_dir": str(args.backup_dir),
            "schema_version": conn.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0],
            "counts": table_counts(conn),
        }
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    init_db(args.db)
    data = {
        "ok": True,
        "command": "scan",
        "implemented": False,
        "next_task": "D4 GitHub scan for ready issues",
    }
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


def cmd_outbox_next(args: argparse.Namespace) -> int:
    init_db(args.db)
    with connect(args.db) as conn:
        row = conn.execute(
            "SELECT * FROM outbox WHERE state='pending' ORDER BY created_at, id LIMIT 1"
        ).fetchone()
    print(json.dumps(dict(row) if row else None, indent=2, sort_keys=True))
    return 0


def cmd_inbox_ack(args: argparse.Namespace) -> int:
    init_db(args.db)
    ts = now_iso()
    with connect(args.db) as conn:
        cur = conn.execute(
            "UPDATE inbox SET state='acknowledged', acknowledged_at=?, updated_at=? WHERE external_id=?",
            (ts, ts, args.external_id),
        )
        changed = cur.rowcount
    print(json.dumps({"ok": changed == 1, "external_id": args.external_id, "updated": changed}, sort_keys=True))
    return 0 if changed == 1 else 1


def cmd_db_init(args: argparse.Namespace) -> int:
    init_db(args.db)
    print(json.dumps({"ok": True, "db_path": str(args.db)}, sort_keys=True))
    return 0


def cmd_db_backup(args: argparse.Namespace) -> int:
    init_db(args.db)
    args.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = args.backup_dir / f"orchestrator-{stamp}.db"
    with sqlite3.connect(args.db) as src, sqlite3.connect(dest) as dst:
        src.backup(dst)
    dest.chmod(0o600)
    print(json.dumps({"ok": True, "source": str(args.db), "backup": str(dest)}, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trading-orchestrator")
    p.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    p.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    sub = p.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    status.set_defaults(func=cmd_status)

    scan = sub.add_parser("scan")
    scan.set_defaults(func=cmd_scan)

    outbox = sub.add_parser("outbox")
    outbox_sub = outbox.add_subparsers(dest="outbox_command", required=True)
    outbox_next = outbox_sub.add_parser("next")
    outbox_next.set_defaults(func=cmd_outbox_next)

    inbox = sub.add_parser("inbox")
    inbox_sub = inbox.add_subparsers(dest="inbox_command", required=True)
    inbox_ack = inbox_sub.add_parser("ack")
    inbox_ack.add_argument("external_id")
    inbox_ack.set_defaults(func=cmd_inbox_ack)

    db = sub.add_parser("db")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_init = db_sub.add_parser("init")
    db_init.set_defaults(func=cmd_db_init)
    db_backup = db_sub.add_parser("backup")
    db_backup.set_defaults(func=cmd_db_backup)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
