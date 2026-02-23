#!/bin/bash
# integrity_check.sh
# Verify model weights and Python environment integrity.
# Designed to run as llm-service via launchd (see config/ for plist).
#
# Checks:
#   1. Model weight SHA256 checksums against CHECKSUMS.sha256
#   2. Python environment packages against frozen requirements
#
# On failure: logs to /var/log/vllm-metal/ and writes to syslog (local0.alert)
#
# Usage:
#   ./integrity_check.sh                           # Check default model
#   MODEL_DIR=/path/to/model ./integrity_check.sh  # Check specific model

set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/Users/llm-service/models/llama-3.2-3b}"
VENV_DIR="${VENV_DIR:-/Users/llm-service/.venv-vllm-metal}"
FROZEN_REQ="${FROZEN_REQ:-/Users/llm-service/requirements-frozen.txt}"
LOGFILE="/var/log/vllm-metal/integrity-$(date +%Y%m%d).log"
CURRENT=""
FAIL=0

cleanup() { [ -n "$CURRENT" ] && rm -f "$CURRENT"; }
trap cleanup EXIT

echo "$(date -u) Integrity check started" >> "$LOGFILE"

# Model weights
if cd "$MODEL_DIR" && shasum -a 256 -c CHECKSUMS.sha256 --quiet 2>/dev/null; then
    echo "$(date -u) Model weights: OK" >> "$LOGFILE"
else
    echo "$(date -u) MODEL WEIGHTS: FAILED" >> "$LOGFILE"
    logger -p local0.alert "vLLM Metal: model weight integrity check FAILED"
    FAIL=1
fi

# Python environment
CURRENT=$(mktemp)
"${VENV_DIR}/bin/pip" freeze > "$CURRENT"
if diff -q "$FROZEN_REQ" "$CURRENT" >/dev/null 2>&1; then
    echo "$(date -u) Python env: OK" >> "$LOGFILE"
else
    echo "$(date -u) Python env: CHANGED" >> "$LOGFILE"
    logger -p local0.alert "vLLM Metal: Python environment integrity check FAILED"
    FAIL=1
fi

if [ $FAIL -eq 1 ]; then
    echo "$(date -u) INTEGRITY CHECK FAILED" >> "$LOGFILE"
    exit 1
fi

echo "$(date -u) All checks passed" >> "$LOGFILE"
