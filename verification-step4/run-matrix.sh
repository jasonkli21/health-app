#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec ./run.sh "${1:?provide a new absolute fixture directory outside repository trees}" \
    ok concurrent lost-ack 429 timeout disconnect changed-detail expired-before-publication \
    health-ai-consent health-cross-domain-consent health-owner health-firebase-revoked \
    health-record health-recipient health-crossed-recipient crossed-pas-owner \
    regrant-higher-epoch pas-memory pas-source pas-owner pas-release interrupt-after-health-commit \
    pas-root-failure pas-after-fence health-revoked-after-fence forged-terminal
