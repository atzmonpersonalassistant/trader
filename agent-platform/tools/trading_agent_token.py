#!/usr/bin/env python3
"""Mint short-lived GitHub installation tokens for agent GitHub Apps.

This helper intentionally does not hard-code app IDs, installation IDs, or
private-key paths. Configure them with a JSON file, typically:

    /etc/trading-agents/github-apps.json

Override with TRADING_AGENT_APPS_CONFIG when needed.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pwd
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(os.environ.get("TRADING_AGENT_APPS_CONFIG", "/etc/trading-agents/github-apps.json"))


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise SystemExit(
            f"Missing GitHub App config: {path}. "
            "Create it from agent-platform/config-examples/github-apps.example.json."
        )
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not data:
        raise SystemExit(f"Invalid GitHub App config: {path}")
    return data


def sign_jwt(app_id: int, private_key_path: Path) -> str:
    now = int(time.time())
    header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = b64url(json.dumps({"iat": now - 60, "exp": now + 540, "iss": app_id}, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = subprocess.check_output(["openssl", "dgst", "-sha256", "-sign", str(private_key_path)], input=signing_input)
    return f"{header}.{payload}.{b64url(sig)}"


def expected_linux_user(role: str, cfg: dict[str, Any]) -> str:
    return str(cfg.get("linux_user") or f"agent-{role}")


def enforce_role_user(role: str, cfg: dict[str, Any]) -> None:
    expected = expected_linux_user(role, cfg)
    actual = pwd.getpwuid(os.geteuid()).pw_name
    if actual != expected:
        raise SystemExit(f"Refusing to mint {role!r} token as OS user {actual!r}; expected {expected!r}")


def mint_token(role: str, config: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    cfgs = config or load_config()
    if role not in cfgs:
        raise SystemExit(f"Unknown role {role!r}. Available roles: {', '.join(sorted(cfgs))}")
    cfg = cfgs[role]
    enforce_role_user(role, cfg)
    required = ["app_id", "installation_id", "private_key_path"]
    missing = [key for key in required if key not in cfg]
    if missing:
        raise SystemExit(f"Role {role!r} is missing required config keys: {', '.join(missing)}")
    key_path = Path(str(cfg["private_key_path"])).expanduser()
    if not key_path.exists():
        raise SystemExit(f"Missing private key for {role}: {key_path}")
    jwt = sign_jwt(int(cfg["app_id"]), key_path)
    url = f"https://api.github.com/app/installations/{int(cfg['installation_id'])}/access_tokens"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        data=b"{}",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("role", help="agent role from the GitHub App config, e.g. orchestrator/coding/review")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="GitHub App config JSON path")
    p.add_argument("--json", action="store_true", help="print full token response JSON")
    args = p.parse_args()
    data = mint_token(args.role, load_config(args.config))
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(data["token"])


if __name__ == "__main__":
    main()
