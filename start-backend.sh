#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-claude-sso}"
REGION="${AWS_REGION:-us-east-1}"
PORT="${PORT:-8001}"

aws sso login --profile "$PROFILE"

export AWS_PROFILE="$PROFILE"
export AWS_REGION="$REGION"
export AWS_DEFAULT_REGION="$REGION"
export AWS_SDK_LOAD_CONFIG="1"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
export INTENT_PIPELINE_STORE_PATH="$SCRIPT_DIR/backend/pipeline_store.json"

# Ensure SSO credentials are used (static env creds override profiles if present)
unset AWS_ACCESS_KEY_ID || true
unset AWS_SECRET_ACCESS_KEY || true
unset AWS_SESSION_TOKEN || true
unset AWS_SECURITY_TOKEN || true

aws sts get-caller-identity --profile "$PROFILE"

cd "$SCRIPT_DIR/backend"

python -m uvicorn app.chat_main:app --reload --port "$PORT"
