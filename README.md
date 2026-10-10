# Mahila Suraksha Map – women's safety risk map (India)

Live: https://abalendup-26.github.io/mahila-suraksha-map/

A single-page web app (Leaflet + OpenStreetMap, no API keys) that shows
* **Layer A – district colours:** NCRB *Crime in India 2024* district-wise Crime against Women data
  (11 selectable crime heads, counts or per lakh women) – registered cases only.
* **Layer B – incident markers:** a cumulative, daily-updated log of news (Google News RSS, English + Hindi) and
  public X posts about crimes against women (rape, molestation/harassment, stalking, snatching, kidnapping,
  acid attack, dowry/domestic violence). Every marker cites outlet(s), article link(s), publish date, the exact place
  text as reported, and how/with what precision it was geocoded. Items without a verifiable link are hidden.
* "Use my location", place search, time filter (Today / 7 / 30 days / All / custom), CSV + PDF export,
  emergency numbers 112 / 181, and a "Sources & method" panel.

Victim identities are never stored or shown (BNS Sec. 72): no names, ages, photos; X post text is not reproduced.
Data is incomplete – no markers or a green district does **not** mean an area is safe.

## Repository layout
```
index.html                 the app (static, served by GitHub Pages)
.nojekyll
data/
  districts.geojson        Layer A: district polygons + NCRB 2022/2023/2024 values + Census-2011 female pop
  incidents.json           Layer B: cumulative incident log (append-only, schema 4)
  incidents.csv            same, flat (verifiable incidents only)
  incident_reports.pdf     full printable report (with Hindi text)
  ncrb_raw.geojson         raw NCRB district layer download (input to build_districts.py)
  census.csv               Census 2011 district population (input to build_districts.py)
  layer_meta.json          field definitions of the NCRB layer
scripts/
  daily_update.sh          one-shot daily pipeline: fetch → merge → CSV/PDF → copy → commit/push if changed
  build_incidents.py       collect + classify + geocode + append-only merge of incidents
  gazetteer.py             district/city name list (English from NCRB layer + hand-written Devanagari)
  build_districts.py       builds data/districts.geojson
  make_report_pdf.py       renders data/incident_reports.pdf via headless Chrome
  verify.py / verify_live.py  headless Playwright checks + screenshots
requirements.txt, .gitignore
```
Not in the repo (kept locally in the build folder): raw fetched news/X dumps (`data/raw_news/YYYY-MM-DD/`,
`data/raw_x/YYYY-MM-DD/`), `data/backups/`, geocode/URL caches, logs, virtualenvs. They are reproducible inputs/caches;
without them a fresh clone can still serve the site and continue appending (the merge starts from `data/incidents.json`).

## Setup
```
git clone https://github.com/abalendup-26/mahila-suraksha-map.git && cd mahila-suraksha-map
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # only needed for verify scripts
.venv/bin/playwright install chromium   # or use system google-chrome (scripts default to /usr/bin/google-chrome)
python3 -m http.server 8765             # open http://localhost:8765/  (geolocation needs https or localhost)
```
Build folder used by the maintainer: `/workspace/safety-map` (source + raw archives), published clone:
`/workspace/safety-map-site`. Override with `SRC=... SITE=... bash scripts/daily_update.sh`.
Pushing uses the GitHub CLI login (`gh auth login`); no token is stored in this repo.

## Data sources
* NCRB, *Crime in India 2024* (+2022, 2023) district-wise Crime against Women, via Esri India Living Atlas layer
  `NCRB/District_Wise_Crime_Against_Women_2022` (MapServer/0), which also supplies boundaries. NCRB does not number
  its district-wise tables. Cross-check: district sum of 2024 rape cases 29,441 vs 29,536 in CII 2024 Vol. I
  Table 3A.2; Rajasthan, Maharashtra, Madhya Pradesh and Telangana match exactly.
* Census 2011 district population (GitHub mirror nishusharma1608/India-Census-2011-Analysis).
* Google News RSS search; X API (search_posts_all / search_news); OpenStreetMap Nominatim geocoding.

## Daily update (append-only, cumulative)
Incident data is cumulative: `scripts/build_incidents.py` loads the existing `data/incidents.json`, dedupes new
items by source URL (and the same-type/same-city/~2-day grouping rule), appends, and never drops old incidents.
Each incident keeps `date` (= report date of its first source), `first_seen` (date this map first collected it)
and `last_updated`. Before any change the previous file is copied to `data/backups/incidents_<IST timestamp>.json`.
Raw inputs are archived by IST date: `data/raw_news/YYYY-MM-DD/*.xml`, `data/raw_x/YYYY-MM-DD/*.txt`.

Exact daily procedure:
1. X data (needs the X MCP tools; a shell script cannot call them). Run these searches with
   `search_posts_all` (sort_order=recency, start_time = yesterday 00:00Z, max_results=100,
   post.fields=created_at,entities,author_id,text, expansions=author_id, user.fields=username,verified,name)
   and `search_news` (max_age_hours=48), with write_to_file=true, then copy each result file to
   `/workspace/safety-map/data/raw_x/$(TZ=Asia/Kolkata date +%F)/<name>.txt`. Suggested queries:
   - दुष्कर्म आरोपी गिरफ्तार पुलिस · छेड़छाड़ आरोपी गिरफ्तार पुलिस · चेन स्नैचिंग महिला पुलिस · दहेज हत्या मुकदमा दर्ज
   - rape accused arrested police India · gang-raped case registered police station arrested
   - search_news: "rape molestation women India police arrested", "women harassment stalking acid attack dowry India police"
   (Skipping this step is fine: the run then uses news only.)
2. Run: `bash /workspace/safety-map/scripts/daily_update.sh`
   - fetches Google News RSS (EN+HI) into today's archive folder, merges, rebuilds CSV + full PDF only if data changed,
     copies site files + source code (scripts/, README, requirements, .gitignore, NCRB/census inputs) to /workspace/safety-map-site, commits and pushes to `main` only if something differs.
   - Options: `--no-fetch` (re-ingest archived files only), `--no-push` (commit locally only). A lock prevents parallel runs.
   - Log: `logs/daily_<timestamp>.log`; look for `RESULT: CHANGED|NOCHANGE` and `Pushed to main.`
3. Optional check: `gh api repos/abalendup-26/mahila-suraksha-map/pages/builds/latest --jq .status` → `built`.

Rebuild district layer: `python3 scripts/build_districts.py`. Local check: `.venv/bin/python scripts/verify.py`;
live check: `.venv/bin/python scripts/verify_live.py https://abalendup-26.github.io/mahila-suraksha-map/ screenshots/live.png`.

## Privacy
Ages are regex-removed from headlines (digits and Hindi number words), names after victim nouns are removed,
X post text is never shown (template summary + link only), and redaction rules are re-applied to old incidents on every run.
