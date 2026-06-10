#!/usr/bin/env bash
# Bootstrap a fresh VPS for the Trader agent platform.
#
# This script creates the local Linux users, directory layout, permissions,
# sudoers dispatch rules, and placeholder config paths needed before GitHub
# Actions can deploy the agent tools. It does not install or copy secrets.

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run as root, e.g. sudo $0" >&2
  exit 1
fi

INSTALL_TOOLS="0"
if [[ "${1:-}" == "--install-system-packages" ]]; then
  INSTALL_TOOLS="1"
fi
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd -- "${SCRIPT_DIR}/../tools" && pwd)"

log() { printf '[bootstrap-new-vps] %s\n' "$*"; }

ensure_user() {
  local user="$1"
  if id -u "$user" >/dev/null 2>&1; then
    log "user exists: $user"
  else
    log "creating system user: $user"
    useradd --system --create-home --shell /usr/sbin/nologin "$user"
  fi
}

install_dir() {
  local owner="$1"
  local group="$2"
  local mode="$3"
  local path="$4"
  install -d -o "$owner" -g "$group" -m "$mode" "$path"
}

if [[ "$INSTALL_TOOLS" == "1" ]]; then
  if command -v apt-get >/dev/null 2>&1; then
    log "installing base packages via apt-get"
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl gh git jq nodejs npm openssh-client openssl python3 sqlite3 sudo
    if ! command -v codex >/dev/null 2>&1; then
      npm install -g @openai/codex
    fi
  else
    log "apt-get not found; skipping package install"
  fi
fi

log "creating role users and QuantConnect access group"
if getent group agent-quantconnect >/dev/null 2>&1; then
  log "group exists: agent-quantconnect"
else
  log "creating group: agent-quantconnect"
  groupadd --system agent-quantconnect
fi
ensure_user agent-orchestrator
ensure_user agent-coding
ensure_user agent-review
ensure_user agent-validator
ensure_user agent-research
# Orchestrator needs group access only for cleanup/traversal of coding/review workspaces.
# Do not put all roles in one shared writable group.
usermod -aG agent-coding agent-orchestrator
usermod -aG agent-review agent-orchestrator
# QuantConnect credentials are shared from a single root-owned env file, readable
# only by roles in agent-quantconnect.
usermod -aG agent-quantconnect agent-orchestrator
usermod -aG agent-quantconnect agent-validator
usermod -aG agent-quantconnect agent-research

log "creating /agents layout"
install_dir root root 711 /agents
install_dir agent-orchestrator agent-orchestrator 750 /agents/orchestrator
install_dir agent-orchestrator agent-orchestrator 750 /agents/orchestrator/state
install_dir agent-orchestrator agent-orchestrator 750 /agents/orchestrator/logs
install_dir agent-orchestrator agent-orchestrator 750 /agents/orchestrator/backups

install_dir agent-coding agent-coding 750 /agents/coding
install_dir agent-coding agent-coding 750 /agents/coding/state
install_dir agent-coding agent-coding 2770 /agents/coding/workspaces
install_dir agent-coding agent-coding 755 /agents/coding/logs
install_dir agent-coding agent-coding 750 /agents/coding/controller

install_dir agent-review agent-review 750 /agents/review
install_dir agent-review agent-review 750 /agents/review/state
install_dir agent-review agent-review 2770 /agents/review/workspaces
install_dir agent-review agent-review 750 /agents/review/logs

install_dir agent-research agent-research 750 /agents/research
install_dir agent-research agent-research 750 /agents/research/state
install_dir agent-research agent-research 750 /agents/research/logs
install_dir agent-research agent-research 750 /agents/research/reports
chown -R agent-research:agent-research /agents/research
chmod 750 /agents/research /agents/research/state /agents/research/logs /agents/research/reports

install_dir agent-validator agent-validator 750 /agents/validator
install_dir agent-validator agent-validator 750 /agents/validator/state
install_dir agent-validator agent-validator 750 /agents/validator/logs
install_dir agent-validator agent-validator 755 /agents/validator/workspaces

log "creating server-local secret/config directories without secret contents"
install_dir root root 755 /etc/trading-agents
install_dir root root 711 /etc/trading-agents/secrets
for role in orchestrator coding review validator research; do
  install_dir root "agent-${role}" 750 "/etc/trading-agents/secrets/${role}"
done
install_dir root agent-research 750 /etc/trading-agents/secrets/research
install_dir root agent-quantconnect 750 /etc/trading-agents/secrets/quantconnect
if [[ -e /etc/trading-agents/secrets/quantconnect/env ]]; then
  chown root:agent-quantconnect /etc/trading-agents/secrets/quantconnect/env
  chmod 640 /etc/trading-agents/secrets/quantconnect/env
fi

log "installing root-owned dispatch wrappers"
install -o root -g root -m 755 "${TOOLS_DIR}/trading-dispatch-coding-agent" /usr/local/sbin/trading-dispatch-coding-agent
install -o root -g root -m 755 "${TOOLS_DIR}/trading-dispatch-coding-agent-stub" /usr/local/sbin/trading-dispatch-coding-agent-stub

log "installing sudoers rules"
cat > /etc/sudoers.d/trading-agent-orchestrator-dispatch <<'SUDOERS'
# Allow orchestrator to dispatch only fixed coding-agent run commands through
# root-owned validation wrappers. Do not grant wildcard access to the full
# trading-coding-agent CLI; it accepts config paths and token commands.
agent-orchestrator ALL=(root) NOPASSWD: /usr/local/sbin/trading-dispatch-coding-agent *
agent-orchestrator ALL=(root) NOPASSWD: /usr/local/sbin/trading-dispatch-coding-agent-stub *
SUDOERS
chmod 440 /etc/sudoers.d/trading-agent-orchestrator-dispatch
visudo -cf /etc/sudoers.d/trading-agent-orchestrator-dispatch >/dev/null

log "creating placeholder config files if missing"
if [[ ! -e /etc/trading-agents/github-apps.json ]]; then
  cat > /etc/trading-agents/github-apps.json <<'JSON'
{
  "orchestrator": {
    "app_slug": "trading-orchestrator-agent",
    "app_id": "REPLACE_ME",
    "installation_id": "REPLACE_ME",
    "private_key_path": "/etc/trading-agents/secrets/orchestrator/private-key.pem",
    "linux_user": "agent-orchestrator"
  },
  "coding": {
    "app_slug": "trading-coding-agent",
    "app_id": "REPLACE_ME",
    "installation_id": "REPLACE_ME",
    "private_key_path": "/etc/trading-agents/secrets/coding/private-key.pem",
    "linux_user": "agent-coding"
  },
  "review": {
    "app_slug": "trading-review-agent",
    "app_id": "REPLACE_ME",
    "installation_id": "REPLACE_ME",
    "private_key_path": "/etc/trading-agents/secrets/review/private-key.pem",
    "linux_user": "agent-review"
  },
  "validator": {
    "app_slug": "trading-validator-agent",
    "app_id": "REPLACE_ME",
    "installation_id": "REPLACE_ME",
    "private_key_path": "/etc/trading-agents/secrets/validator/private-key.pem",
    "linux_user": "agent-validator"
  },
  "research": {
    "app_slug": "trading-research-agent",
    "app_id": "REPLACE_ME",
    "installation_id": "REPLACE_ME",
    "private_key_path": "/etc/trading-agents/secrets/research/private-key.pem",
    "linux_user": "agent-research"
  }
}
JSON
  # This file contains IDs and private-key paths only, not private-key contents.
  # It must be readable by agent-orchestrator, agent-coding, agent-review,
  # agent-validator, and agent-research because each role may run tools as its own user.
  chmod 644 /etc/trading-agents/github-apps.json
  chown root:root /etc/trading-agents/github-apps.json
fi

log "bootstrap complete"
cat <<'NEXT'

Next manual steps:
1. Install real GitHub App private keys under /etc/trading-agents/secrets/*/private-key.pem.
2. Replace /etc/trading-agents/github-apps.json placeholder IDs with real App/installation IDs.
3. Install Codex/OpenAI auth for agent-coding and agent-review if those roles run Codex on the VPS.
4. Update GitHub Actions secrets: VPS_HOST, VPS_USER, VPS_SSH_PRIVATE_KEY, VPS_SSH_HOST_KEY.
5. Run the vps-deploy workflow and then the validation checklist in server-migration.md.
NEXT
