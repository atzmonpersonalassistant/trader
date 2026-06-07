#!/usr/bin/env python3
"""Mint short-lived GitHub installation tokens for trading-agent GitHub Apps.

This local MVP helper reads private keys from ~/.trading-agents/github-apps.
The future VM version should read keys from GCP Secret Manager or locked-down
role-specific files.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CONFIG = {
    "orchestrator": {
        "app_slug": "trading-orchestrator-agent",
        "app_id": 3988813,
        "installation_id": 138640121,
        "private_key_path": "~/.trading-agents/github-apps/orchestrator.private-key.pem",
    },
    "coding": {
        "app_slug": "trading-coding-agent",
        "app_id": 3988816,
        "installation_id": 138640143,
        "private_key_path": "~/.trading-agents/github-apps/coding.private-key.pem",
    },
    "review": {
        "app_slug": "trading-review-agent",
        "app_id": 3988836,
        "installation_id": 138640182,
        "private_key_path": "~/.trading-agents/github-apps/review.private-key.pem",
    },
    "validator": {
        "app_slug": "trading-validator-agent",
        "app_id": 3988837,
        "installation_id": 138640218,
        "private_key_path": "~/.trading-agents/github-apps/validator.private-key.pem",
    },
}


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign_jwt(app_id: int, private_key_path: Path) -> str:
    now = int(time.time())
    header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = b64url(json.dumps({"iat": now - 60, "exp": now + 540, "iss": app_id}, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = subprocess.check_output(["openssl", "dgst", "-sha256", "-sign", str(private_key_path)], input=signing_input)
    return f"{header}.{payload}.{b64url(sig)}"


def mint_token(role: str) -> dict:
    cfg = CONFIG[role]
    key_path = Path(cfg["private_key_path"]).expanduser()
    if not key_path.exists():
        raise SystemExit(f"Missing private key for {role}: {key_path}")
    jwt = sign_jwt(cfg["app_id"], key_path)
    url = f"https://api.github.com/app/installations/{cfg['installation_id']}/access_tokens"
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
    p.add_argument("role", choices=sorted(CONFIG))
    p.add_argument("--json", action="store_true", help="print full token response JSON")
    args = p.parse_args()
    data = mint_token(args.role)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(data["token"])


if __name__ == "__main__":
    main()
