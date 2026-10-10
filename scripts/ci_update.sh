#!/usr/bin/env bash
# One unattended data update, run from the repository root (GitHub Actions or any checkout). No absolute paths.
#   1. fetch Google News RSS -> data/raw_news/<date>/ (temporary, not committed)
#   2. append-only merge into data/incidents.json (+ CSV), decode Google News links, read articles,
#      extract incident date + most specific place, geocode (caches in data/*.json and data/osm/ ARE committed)
#   3. slim app JSON; full PDF only when data changed
# Exit 0 on success; commit/push is done by the workflow.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
LOG=logs/ci_update.log
python3 -u scripts/build_incidents.py "$@" 2>&1 | tee "$LOG"
python3 scripts/make_app_data.py 2>&1 | tee -a "$LOG"
if grep -q "RESULT: CHANGED" "$LOG" || [ ! -f data/incident_reports.pdf ]; then
  python3 scripts/make_report_pdf.py 2>&1 | tee -a "$LOG"
fi
python3 - <<'PY'
import json
j = json.load(open("data/incidents.json", encoding="utf-8"))
v = [i for i in j["incidents"] if i.get("verifiable", True)]
from collections import Counter
print("SUMMARY incidents:", len(v), "| pin levels:", dict(Counter(i.get("pin_level") for i in v)),
      "| incident date:", dict(Counter(i.get("incident_date_basis") for i in v)))
PY
