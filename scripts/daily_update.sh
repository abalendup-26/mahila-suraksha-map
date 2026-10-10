#!/usr/bin/env bash
# Daily update for SafeNaksha (repo/URL: mahila-suraksha-map). Safe to run repeatedly (idempotent).
#
# What it does
#   1. Fetches Google News RSS (English + Hindi) -> data/raw_news/<YYYY-MM-DD IST>/*.xml (archived, never deleted)
#   2. Ingests X data: X search results are fetched with the X MCP tools (search_posts_all / search_news),
#      which a shell script cannot call. BEFORE running this script, the caller (agent) must save each X
#      search result JSON as a file in  data/raw_x/<YYYY-MM-DD>/<anything>.txt  (or .json). This script only
#      ingests whatever files are present there; with no new X files it simply uses news only.
#   3. Merges new items into data/incidents.json (APPEND-ONLY: dedupe by source URL + grouping rule;
#      old incidents never dropped; backup in data/backups/ before each change)
#   4. If incidents changed: rebuilds incidents.csv (done by the builder) and the full PDF report
#   5. Copies site files AND the source code (scripts/, README.md, requirements.txt, .gitignore, NCRB/census inputs)
#      into /workspace/safety-map-site and commits + pushes to main ONLY if files differ.
#      Raw news/X dumps, backups, caches, logs and venvs are NOT copied (they stay local).
#
# Usage:  bash /workspace/safety-map/scripts/daily_update.sh [--no-fetch] [--no-push]
set -euo pipefail
SRC=${SRC:-/workspace/safety-map}
SITE=${SITE:-/workspace/safety-map-site}
TODAY=$(TZ=Asia/Kolkata date +%F)
FETCH_FLAG=""; PUSH=1
for a in "$@"; do case "$a" in --no-fetch) FETCH_FLAG="--no-fetch";; --no-push) PUSH=0;; esac; done

exec 9>/tmp/safety-map-daily.lock
flock -n 9 || { echo "another daily_update is running; exiting"; exit 0; }

cd "$SRC"
mkdir -p "data/raw_news/$TODAY" "data/raw_x/$TODAY" data/backups logs
LOG="logs/daily_$(TZ=Asia/Kolkata date +%F_%H%M%S).log"
echo "== daily_update $(TZ=Asia/Kolkata date '+%F %T IST')" | tee "$LOG"
echo "X files present for today: $(ls data/raw_x/$TODAY 2>/dev/null | wc -l)" | tee -a "$LOG"

python3 scripts/build_incidents.py $FETCH_FLAG 2>&1 | tee -a "$LOG"
# Re-render the PDF when data changed in this run OR the PDF is older than incidents.json (e.g. after a manual build)
if grep -q "RESULT: CHANGED" "$LOG" || [ ! -f data/incident_reports.pdf ] || [ data/incidents.json -nt data/incident_reports.pdf ]; then
  python3 scripts/make_report_pdf.py 2>&1 | tee -a "$LOG"
fi

# slim JSON used by the web app (deterministic; only changes when incidents.json does)
python3 scripts/make_app_data.py 2>&1 | tee -a "$LOG"

# PDF bytes differ on every render, so it is only re-rendered (and thus only copied as changed) when data changed.
mkdir -p "$SITE/data" "$SITE/assets" "$SITE/.github/ISSUE_TEMPLATE"
# static site files (app shell, legal pages, PWA files, icons, issue template)
for f in index.html terms.html privacy.html disclaimer.html legal.css manifest.webmanifest sw.js assets/* .github/ISSUE_TEMPLATE/*; do
  [ -f "$f" ] || continue
  if ! cmp -s "$f" "$SITE/$f"; then cp "$f" "$SITE/$f"; fi
done
for f in districts.geojson incidents.json incidents.app.json incidents.csv incident_reports.pdf takedowns.json; do
  [ -f "data/$f" ] || continue
  if ! cmp -s "data/$f" "$SITE/data/$f"; then cp "data/$f" "$SITE/data/$f"; fi
done
for f in census.csv ncrb_raw.geojson layer_meta.json; do
  if ! cmp -s "data/$f" "$SITE/data/$f"; then cp "data/$f" "$SITE/data/$f"; fi
done
# source code (keep repo in sync; never copy caches/raw dumps/venvs)
mkdir -p "$SITE/scripts"
for f in scripts/*.py scripts/*.sh README.md requirements.txt .gitignore; do
  [ -f "$f" ] || continue
  if ! cmp -s "$f" "$SITE/$f"; then cp -p "$f" "$SITE/$f"; fi
done
[ -f "$SITE/.nojekyll" ] || touch "$SITE/.nojekyll"

cd "$SITE"
git add -A
if git diff --cached --quiet; then
  echo "No site changes; nothing to commit." | tee -a "$SRC/$LOG"
  exit 0
fi
COUNT=$(python3 -c "import json;print(json.load(open('data/incidents.json'))['count'])")
git commit -q -m "Data update $TODAY: $COUNT incidents (cumulative)" 
if [ "$PUSH" = 1 ]; then git -c credential.helper= -c credential.helper='!gh auth git-credential' push -q origin main && echo "Pushed to main." | tee -a "$SRC/$LOG"; else echo "Committed (not pushed: --no-push)." | tee -a "$SRC/$LOG"; fi
