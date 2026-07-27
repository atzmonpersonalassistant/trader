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
SCRIPTS_DIR="$SCRIPT_DIR"
EARNINGS_DIR="${SCRIPTS_DIR}/earnings-qc-options"

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

configure_shared_collab_dir() {
  local path="$1"
  install_dir root agent-lean 2770 "$path"
  chgrp -R agent-lean "$path"
  chmod -R g+rwX "$path"
  find "$path" -type d -exec chmod 2770 {} +
  if command -v setfacl >/dev/null 2>&1; then
    setfacl -m g:agent-lean:rwx,m::rwx "$path"
    find "$path" -type d -exec setfacl -m g:agent-lean:rwx,d:g:agent-lean:rwx,d:m::rwx,m::rwx {} +
  else
    log "setfacl not found; shared Lean roles should run write workflows with umask 0002"
  fi
}

if [[ "$INSTALL_TOOLS" == "1" ]]; then
  if command -v apt-get >/dev/null 2>&1; then
    log "installing base packages via apt-get"
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      acl ca-certificates curl docker.io gh git jq nodejs npm openssh-client openssl python3 python3-pip python3-venv sqlite3 sudo
    if command -v systemctl >/dev/null 2>&1; then
      systemctl enable --now docker
    elif command -v service >/dev/null 2>&1; then
      service docker start || true
    fi
    if ! command -v codex >/dev/null 2>&1; then
      npm install -g @openai/codex
    fi
    if ! python3 -c 'import lean' >/dev/null 2>&1 || ! command -v lean >/dev/null 2>&1; then
      python3 -m pip install --break-system-packages --upgrade lean
    fi
    python3 - <<'PY_LEAN_MODULES'
import lean.models
PY_LEAN_MODULES
    python3 - <<'PY_CHMOD'
import importlib.util
import os
from pathlib import Path
spec = importlib.util.find_spec("lean")
if spec and spec.submodule_search_locations:
    Path(spec.submodule_search_locations[0]).chmod(0o755)
    for root, dirs, files in os.walk(spec.submodule_search_locations[0]):
        for d in dirs:
            Path(root, d).chmod(0o755)
        for f in files:
            file = Path(root, f)
            file.chmod(file.stat().st_mode | 0o444)
PY_CHMOD
  else
    log "apt-get not found; skipping package install"
  fi
fi

log "creating role users and Lean/QuantConnect access groups"
if getent group agent-lean >/dev/null 2>&1; then
  log "group exists: agent-lean"
else
  log "creating group: agent-lean"
  groupadd --system agent-lean
fi
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
ensure_user agent-research-runner
ensure_user agent-research-watchdog
# Orchestrator needs group access only for cleanup/traversal of coding/review workspaces.
# Do not put all roles in one shared writable group.
usermod -aG agent-coding agent-orchestrator
usermod -aG agent-review agent-orchestrator
# agent-research stages handoff files for the isolated runner; it needs
# membership in the runner group to chgrp files without gaining runner secrets.
usermod -aG agent-research-runner agent-research
usermod -aG agent-research-watchdog agent-research
# Lean workspaces are a platform capability across research, coding, review,
# and validator roles. This group grants access only to shared project/artifact
# directories; raw QuantConnect credentials remain scoped separately below.
usermod -aG agent-lean agent-research
usermod -aG agent-lean agent-research-runner
usermod -aG agent-lean agent-coding
usermod -aG agent-lean agent-review
usermod -aG agent-lean agent-validator
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
install_dir agent-coding agent-coding 750 /agents/coding/lean-workspace
install_dir agent-coding agent-coding 755 /agents/coding/logs
install_dir agent-coding agent-coding 750 /agents/coding/controller

install_dir agent-review agent-review 750 /agents/review
install_dir agent-review agent-review 750 /agents/review/state
install_dir agent-review agent-review 2770 /agents/review/workspaces
install_dir agent-review agent-review 750 /agents/review/lean-workspace
install_dir agent-review agent-review 750 /agents/review/logs

install_dir agent-research agent-research 750 /agents/research
install_dir agent-research agent-research 750 /agents/research/state
install_dir agent-research agent-research 750 /agents/research/logs
install_dir agent-research agent-research 750 /agents/research/reports
install_dir agent-research agent-research 750 /agents/research/lean-workspace
chown -R agent-research:agent-research /agents/research
chmod 750 /agents/research /agents/research/state /agents/research/logs /agents/research/reports /agents/research/lean-workspace
install_dir agent-research agent-research-runner 750 /agents/research/handoff

install_dir agent-validator agent-validator 750 /agents/validator
install_dir agent-validator agent-validator 750 /agents/validator/state
install_dir agent-validator agent-validator 750 /agents/validator/logs
install_dir agent-validator agent-validator 755 /agents/validator/workspaces
install_dir agent-validator agent-validator 750 /agents/validator/lean-workspace

install_dir root agent-lean 750 /agents/shared
configure_shared_collab_dir /agents/shared/lean-projects
configure_shared_collab_dir /agents/shared/research-artifacts

log "creating server-local secret/config directories without secret contents"
install_dir root root 755 /etc/trading-agents
install_dir root root 711 /etc/trading-agents/secrets
for role in orchestrator coding review validator research research-runner research-watchdog; do
  install_dir root "agent-${role}" 750 "/etc/trading-agents/secrets/${role}"
done
install_dir root agent-research 750 /etc/trading-agents/secrets/research
if [[ ! -e /etc/trading-agents/secrets/research/env ]]; then
  touch /etc/trading-agents/secrets/research/env
fi
chown root:agent-research /etc/trading-agents/secrets/research/env
chmod 640 /etc/trading-agents/secrets/research/env
install_dir root agent-quantconnect 750 /etc/trading-agents/secrets/quantconnect
if [[ -e /etc/trading-agents/secrets/quantconnect/env ]]; then
  chown root:agent-quantconnect /etc/trading-agents/secrets/quantconnect/env
  chmod 640 /etc/trading-agents/secrets/quantconnect/env
fi

log "installing root-owned dispatch wrappers"
install -o root -g root -m 755 "${TOOLS_DIR}/trading-dispatch-coding-agent" /usr/local/sbin/trading-dispatch-coding-agent
install -o root -g root -m 755 "${TOOLS_DIR}/trading-dispatch-review-agent" /usr/local/sbin/trading-dispatch-review-agent
install -o root -g root -m 755 "${TOOLS_DIR}/trading-dispatch-coding-agent-stub" /usr/local/sbin/trading-dispatch-coding-agent-stub

log "installing research loop scripts"
install -o root -g root -m 755 "${SCRIPTS_DIR}/trading-research-agent-loop" /usr/local/bin/trading-research-agent-loop
install -o root -g root -m 755 "${SCRIPTS_DIR}/trading-research-qc-smoke" /usr/local/bin/trading-research-qc-smoke
install -o root -g root -m 755 "${SCRIPTS_DIR}/trading-research-qc-broker" /usr/local/bin/trading-research-qc-broker
install -o root -g root -m 755 "${SCRIPTS_DIR}/trading-research-qc-cloud-extract" /usr/local/bin/trading-research-qc-cloud-extract
install -o root -g root -m 755 "${SCRIPTS_DIR}/trading-research-qc-cloud-run" /usr/local/bin/trading-research-qc-cloud-run
install -o root -g root -m 755 "${SCRIPTS_DIR}/trading-research-qc-run" /usr/local/bin/trading-research-qc-run
install -o root -g root -m 755 "${SCRIPTS_DIR}/trading-research-qc-api-extract" /usr/local/bin/trading-research-qc-api-extract
install -o root -g root -m 755 "${SCRIPTS_DIR}/trading-research-qc-docker-run" /usr/local/sbin/trading-research-qc-docker-run
install -o root -g root -m 755 "${EARNINGS_DIR}/trading-research-bounded-earnings-qc" /usr/local/sbin/trading-research-bounded-earnings-qc


log "preparing isolated research runner Codex auth directory"
install_dir agent-research-runner agent-research-runner 700 /home/agent-research-runner/.codex
install_dir agent-research-watchdog agent-research-watchdog 700 /home/agent-research-watchdog/.codex
if [[ -s /home/agent-research/.codex/auth.json && ! -s /home/agent-research-runner/.codex/auth.json ]]; then
  install -o agent-research-runner -g agent-research-runner -m 600 /home/agent-research/.codex/auth.json /home/agent-research-runner/.codex/auth.json
fi
if [[ -s /home/agent-research/.codex/auth.json && ! -s /home/agent-research-watchdog/.codex/auth.json ]]; then
  install -o agent-research-watchdog -g agent-research-watchdog -m 600 /home/agent-research/.codex/auth.json /home/agent-research-watchdog/.codex/auth.json
fi

log "installing sudoers rules"
cat > /etc/sudoers.d/trading-agent-orchestrator-dispatch <<'SUDOERS'
# Allow orchestrator to dispatch only fixed agent run commands through
# root-owned validation wrappers. Do not grant wildcard access to full agent CLIs.
agent-orchestrator ALL=(root) NOPASSWD: /usr/local/sbin/trading-dispatch-coding-agent *
agent-orchestrator ALL=(root) NOPASSWD: /usr/local/sbin/trading-dispatch-review-agent *
agent-orchestrator ALL=(root) NOPASSWD: /usr/local/sbin/trading-dispatch-coding-agent-stub *
SUDOERS
chmod 440 /etc/sudoers.d/trading-agent-orchestrator-dispatch
visudo -cf /etc/sudoers.d/trading-agent-orchestrator-dispatch >/dev/null

cat > /usr/local/bin/trading-research-runner-codex <<'RUNNER_CODEX'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$#" -lt 2 || "$#" -gt 3 ]]; then
  echo "usage: trading-research-runner-codex TASK_FILE OUTPUT_DIR [MODEL]" >&2
  exit 64
fi
TASK_FILE="$1"
OUTPUT_DIR="$2"
MODEL="${3:-gpt-5.4-mini}"
case "$MODEL" in
  *[!A-Za-z0-9._/-]*|"") echo "ERROR: unsafe model name" >&2; exit 70 ;;
esac
case "$TASK_FILE" in
  /agents/research/handoff/research-pass-*-task.txt|/agents/research/handoff/idea-generation-*-task.txt) ;;
  *) echo "ERROR: task file must be an approved research handoff" >&2; exit 65 ;;
esac
case "$OUTPUT_DIR" in
  /agents/research/reports/research-pass-*|/agents/research/reports/idea-generation-*) ;;
  *) echo "ERROR: output dir must be an approved research reports directory" >&2; exit 67 ;;
esac
if [[ -L "$TASK_FILE" || -L "$OUTPUT_DIR" || ! -r "$TASK_FILE" || ! -d "$OUTPUT_DIR" || ! -w "$OUTPUT_DIR" ]]; then
  echo "ERROR: task/output permissions are not usable" >&2
  exit 66
fi
TASK_REAL="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$TASK_FILE")"
OUT_REAL="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$OUTPUT_DIR")"
case "$TASK_REAL" in
  /agents/research/handoff/research-pass-*-task.txt|/agents/research/handoff/idea-generation-*-task.txt) ;;
  *) echo "ERROR: resolved task path escaped handoff" >&2; exit 68 ;;
esac
case "$OUT_REAL" in
  /agents/research/reports/research-pass-*|/agents/research/reports/idea-generation-*) ;;
  *) echo "ERROR: resolved output path escaped reports" >&2; exit 69 ;;
esac
cd "$OUT_REAL"
export HOME=/home/agent-research-runner
export PATH=/usr/local/bin:/usr/bin:/bin
export PYTHONDONTWRITEBYTECODE=1
umask 0007
if [[ -r /etc/trading-agents/secrets/quantconnect/env ]]; then
  echo "ERROR: runner user can read QuantConnect secrets" >&2
  exit 71
fi
exec /usr/bin/timeout 6h /usr/local/bin/codex exec --skip-git-repo-check --sandbox workspace-write -c approval_policy="never" --model "$MODEL" "$(cat "$TASK_REAL")"
RUNNER_CODEX
chown root:root /usr/local/bin/trading-research-runner-codex
chmod 755 /usr/local/bin/trading-research-runner-codex

cat > /usr/local/bin/trading-research-watchdog-codex >/dev/null <<'WATCHDOG_CODEX'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$#" -lt 2 || "$#" -gt 3 ]]; then
  echo "usage: trading-research-watchdog-codex TASK_FILE OUTPUT_DIR [MODEL]" >&2
  exit 64
fi
TASK_FILE="$1"
OUTPUT_DIR="$2"
MODEL="${3:-gpt-5.4-mini}"
case "$MODEL" in
  *[!A-Za-z0-9._/-]*|"") echo "ERROR: unsafe model name" >&2; exit 70 ;;
esac
case "$TASK_FILE" in
  /agents/research/handoff/research-watchdog-*-task.txt) ;;
  *) echo "ERROR: task file must be an approved watchdog handoff" >&2; exit 65 ;;
esac
case "$OUTPUT_DIR" in
  /agents/research/reports/research-watchdog-*) ;;
  *) echo "ERROR: output dir must be an approved watchdog reports directory" >&2; exit 67 ;;
esac
if [[ -L "$TASK_FILE" || -L "$OUTPUT_DIR" || ! -r "$TASK_FILE" || ! -d "$OUTPUT_DIR" || ! -w "$OUTPUT_DIR" ]]; then
  echo "ERROR: task/output permissions are not usable" >&2
  exit 66
fi
TASK_REAL="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$TASK_FILE")"
OUT_REAL="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$OUTPUT_DIR")"
case "$TASK_REAL" in
  /agents/research/handoff/research-watchdog-*-task.txt) ;;
  *) echo "ERROR: resolved task path escaped watchdog handoff" >&2; exit 68 ;;
esac
case "$OUT_REAL" in
  /agents/research/reports/research-watchdog-*) ;;
  *) echo "ERROR: resolved output path escaped watchdog reports" >&2; exit 69 ;;
esac
cd "$OUT_REAL"
export HOME=/home/agent-research-watchdog
export PATH=/usr/local/bin:/usr/bin:/bin
export PYTHONDONTWRITEBYTECODE=1
umask 0007
if [[ -r /etc/trading-agents/secrets/quantconnect/env ]]; then
  echo "ERROR: watchdog user can read QuantConnect secrets" >&2
  exit 71
fi
if sudo -n -l 2>/dev/null | grep -q 'trading-research-bounded-earnings-qc'; then
  echo "ERROR: watchdog user has bounded QC sudo access" >&2
  exit 72
fi
exec /usr/bin/timeout 20m /usr/local/bin/codex exec --skip-git-repo-check --sandbox workspace-write -c approval_policy="never" --model "$MODEL" "$(cat "$TASK_REAL")"
WATCHDOG_CODEX
chown root:root /usr/local/bin/trading-research-watchdog-codex
chmod 755 /usr/local/bin/trading-research-watchdog-codex


cat > /etc/sudoers.d/trading-agent-research-runner <<'SUDOERS_RUNNER'
# Allow the research loop to run only the offline Codex wrapper as the isolated runner user.
agent-research ALL=(agent-research-runner) NOPASSWD: /usr/local/bin/trading-research-runner-codex *
agent-research ALL=(agent-research-watchdog) NOPASSWD: /usr/local/bin/trading-research-watchdog-codex *
# Allow the isolated runner to execute only bounded public earnings-QC research actions.
agent-research-runner ALL=(agent-research) NOPASSWD: /usr/local/sbin/trading-research-bounded-earnings-qc *
SUDOERS_RUNNER
chmod 440 /etc/sudoers.d/trading-agent-research-runner
visudo -cf /etc/sudoers.d/trading-agent-research-runner >/dev/null

cat > /etc/sudoers.d/trading-agent-research-qc-docker <<'SUDOERS_QC_DOCKER'
# Allow the research broker to run only the safe QC/LEAN Docker wrapper as root.
agent-research ALL=(root) NOPASSWD: /usr/local/sbin/trading-research-qc-docker-run *
SUDOERS_QC_DOCKER
chmod 440 /etc/sudoers.d/trading-agent-research-qc-docker
visudo -cf /etc/sudoers.d/trading-agent-research-qc-docker >/dev/null

log "creating placeholder config files if missing"
if [[ ! -s /etc/trading-agents/qc-lean-docker-image ]]; then
  printf '%s\n' 'quantconnect/research:latest' > /etc/trading-agents/qc-lean-docker-image
fi
chown root:root /etc/trading-agents/qc-lean-docker-image
chmod 644 /etc/trading-agents/qc-lean-docker-image
if command -v docker >/dev/null 2>&1; then
  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable --now docker || true
  elif command -v service >/dev/null 2>&1; then
    service docker start || true
  fi
  docker pull "$(head -n 1 /etc/trading-agents/qc-lean-docker-image)" || true
else
  log "docker is not installed; QC local Research/QuantBook execution will be blocked until Docker is installed"
fi

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
4. Confirm Lean CLI is available for agent-research/agent-validator and run Lean login from the QuantConnect env file only for roles with QuantConnect env access. Docker is optional, but if local LEAN/QC research containers are expected, install/start Docker and pre-pull the approved QuantConnect/LEAN image under operator control.
5. Update GitHub Actions secrets: VPS_HOST, VPS_USER, VPS_SSH_PRIVATE_KEY, VPS_SSH_HOST_KEY.
6. Run the vps-deploy workflow and then the validation checklist in server-migration.md.
NEXT
