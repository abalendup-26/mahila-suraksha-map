# Mahila Suraksha Map

Women's safety risk map for India: NCRB *Crime in India 2024* district data + a cumulative, daily-updated log of
news / social-media incident reports (area/city level). Live: https://abalendup-26.github.io/mahila-suraksha-map/

Victim identities are never shown (BNS Sec. 72). Data is incomplete; no markers does not mean safe. Emergency 112 · Women helpline 181.

Data files: `data/incidents.json` (cumulative, append-only), `data/incidents.csv`, `data/incident_reports.pdf`, `data/districts.geojson`.
The build pipeline lives outside this repo (`/workspace/safety-map`, see its README: run `scripts/daily_update.sh`).
