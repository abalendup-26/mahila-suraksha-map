#!/usr/bin/env bash
# SafeNaksha daily update – NOW RUNS IN GITHUB ACTIONS (.github/workflows/daily-update.yml, 06:51 IST daily).
# This helper is only for a manual run from a machine with the GitHub CLI logged in:
#   bash scripts/daily_update.sh            -> trigger the workflow, wait for it, then pull the result
#   bash scripts/daily_update.sh --local    -> run the same pipeline in this checkout (no commit/push)
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "--local" ]; then shift; exec bash scripts/ci_update.sh "$@"; fi
REPO=${REPO:-abalendup-26/mahila-suraksha-map}
gh workflow run daily-update.yml -R "$REPO"
sleep 8
RUN=$(gh run list -R "$REPO" --workflow daily-update.yml --limit 1 --json databaseId -q '.[0].databaseId')
echo "run: https://github.com/$REPO/actions/runs/$RUN"
gh run watch "$RUN" -R "$REPO" --exit-status
git pull -q --rebase origin main || true
