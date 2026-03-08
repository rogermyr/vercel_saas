#!/usr/bin/env bash
# Deploy helper para Hetzner
# Uso: ./deploy_to_hetzner.sh user@host [path/to/.env]

set -euo pipefail

REMOTE="$1"
ENV_FILE="${2:-}"

PROJECT_DIR="/opt/pncp-jobs"
CRON_SRC="$PROJECT_DIR/deployment/pncp-jobs.cron"
CRON_DST="/etc/cron.d/pncp-jobs"
LOG_DIR="/var/log/pncp-jobs"
VENV_PATH="$PROJECT_DIR/venv"
PYTHON_BIN="python3.12"

if [ -z "$REMOTE" ]; then
  echo "Uso: $0 user@host [path/to/.env]"
  exit 2
fi

echo "Deploying to: $REMOTE"
if [ -n "$ENV_FILE" ]; then
  echo "Will upload env file: $ENV_FILE"
fi

# Quick SSH check
echo "Checking SSH connectivity..."
ssh -o BatchMode=yes -o ConnectTimeout=10 "$REMOTE" echo ok >/dev/null 2>&1 || {
  echo "SSH connection failed. Ensure key access or passwordless SSH for $REMOTE" >&2
  exit 3
}

# Create remote user, directories and set ownership
ssh "$REMOTE" bash -s <<'SSH_EOF'
set -euo pipefail
# Create pncp user if not exists
if ! id -u pncp >/dev/null 2>&1; then
  sudo useradd -r -s /bin/bash -d /opt/pncp-jobs -m pncp
fi

sudo mkdir -p /opt/pncp-jobs
sudo mkdir -p /var/log/pncp-jobs
sudo chown -R pncp:pncp /opt/pncp-jobs /var/log/pncp-jobs
sudo chmod 755 /var/log/pncp-jobs
SSH_EOF

# Rsync project (exclude venv and .env)
RSYNC_EXCLUDES=("--exclude=venv" "--exclude=.env" "--exclude=__pycache__" "--exclude=*.pyc" "--exclude=.git")
rsync -av --delete "${RSYNC_EXCLUDES[@]}" ./ "$REMOTE:$PROJECT_DIR/"

# If user provided an env file, copy it (secure permissions)
if [ -n "$ENV_FILE" ]; then
  scp "$ENV_FILE" "$REMOTE:$PROJECT_DIR/.env"
  ssh "$REMOTE" sudo chown pncp:pncp "$PROJECT_DIR/.env" && ssh "$REMOTE" sudo chmod 600 "$PROJECT_DIR/.env"
else
  echo "No env file provided; ensure /opt/pncp-jobs/.env exists on remote."
fi

# Remote: create venv if missing, install requirements, copy cron, set perms
ssh "$REMOTE" bash -s <<'SSH_EOF'
set -euo pipefail
PROJECT_DIR=/opt/pncp-jobs
VENV=/opt/pncp-jobs/venv
PY=$PYTHON_BIN

# Install python3.12 if missing (best-effort; requires apt)
if ! command -v $PY >/dev/null 2>&1; then
  echo "Warning: $PY not found on remote. Please install Python 3.12 or edit script to use available Python."
fi

if [ ! -d "$VENV" ]; then
  sudo -u pncp $PY -m venv "$VENV"
fi

# Install requirements
sudo -u pncp "$VENV/bin/pip" install -r "$PROJECT_DIR/requirements.txt" --upgrade

# Install cron file
if [ -f "$PROJECT_DIR/deployment/pncp-jobs.cron" ]; then
  sudo cp "$PROJECT_DIR/deployment/pncp-jobs.cron" /etc/cron.d/pncp-jobs
  sudo chmod 644 /etc/cron.d/pncp-jobs
  sudo chown root:root /etc/cron.d/pncp-jobs
else
  echo "Cron source file not found in project. Skipping cron install." >&2
fi

# Reload cron service
if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl reload cron || sudo systemctl restart cron || true
else
  sudo service cron reload || sudo service cron restart || true
fi
SSH_EOF

# Run a smoke test of the reset job (as pncp)
echo "Running smoke test: reset_quotas.py on remote"
ssh "$REMOTE" sudo -u pncp $VENV_PATH/bin/python $PROJECT_DIR/scripts/reset_quotas.py || true

# Tail the recent log lines (if present)
echo "----- recent cron-reset-quotas log -----"
ssh "$REMOTE" sudo tail -n 200 /var/log/pncp-jobs/cron-reset-quotas.log || true

echo "Deploy finished. Please verify logs and database state."
