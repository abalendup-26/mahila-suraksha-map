# SafeNaksha – women's safety awareness map (India) · महिला सुरक्षा जागरूकता नक्शा

Live: https://abalendup-26.github.io/mahila-suraksha-map/  (installable as a PWA: browser menu → "Install app" / "Add to Home screen")

> Formerly "Mahila Suraksha Map". Renamed because several existing apps/schemes use "Mahila Suraksha"/"Suraksha"
> (e.g. Govt of Rajasthan's *Raj Mahila Suraksha Tracker*). The repository name/URL is unchanged so existing links keep working.
> **Information only. Not an official government or police app.** See `terms.html`, `privacy.html`, `disclaimer.html`
> (drafts – to be reviewed by a lawyer; placeholders are marked `TODO`).

A single-page web app (Leaflet + OpenStreetMap, no API keys) that shows
* **Layer A – district colours:** NCRB *Crime in India 2024* district-wise Crime against Women data
  (11 selectable crime heads, counts or per lakh women) – registered cases only.
* **Layer B – incident markers:** a cumulative, daily-updated log of news (Google News RSS, English + Hindi) and
  public X posts about crimes against women (rape, molestation/harassment, stalking, snatching, kidnapping,
  acid attack, dowry/domestic violence). Every marker cites outlet(s), article link(s), publish date, the exact place
  text as reported, and how/with what precision it was geocoded. Items without a verifiable link are hidden.
* "Use my location", place search, time filter (Today / 7 / 30 days / All / custom), CSV + PDF export,
  emergency numbers 112 / 181, and a "Sources & method" panel.

Ages shown; names and identifying details removed: adult ages as published, minors' ages replaced by "minor"/"नाबालिग"; no victim/family names, house addresses, school/college/workplace names, phone numbers or photos (BNS Sec. 72; POCSO Sec. 23). X post text is not reproduced.
Data is incomplete – no markers or a light-coloured district does **not** mean an area is safe.

## Repository layout
```
index.html                 the app (static, served by GitHub Pages)
terms.html privacy.html disclaimer.html legal.css   legal pages (drafts; fill every TODO)
manifest.webmanifest sw.js PWA manifest + network-first service worker
assets/                    logo.svg, favicons, PWA icons (192/512/maskable), apple-touch-icon, og-image.png
.github/ISSUE_TEMPLATE/correction.yml   public "Report an error / request correction" form
.nojekyll
data/
  districts.geojson        Layer A: district polygons + NCRB 2022/2023/2024 values + Census-2011 female pop
  incidents.json           Layer B: cumulative incident log (append-only, schema 4)
  incidents.app.json       slim copy for the web app (verifiable incidents, UI fields only) – built by make_app_data.py
  incidents.csv            same, flat (verifiable incidents only)
  takedowns.json           hand-maintained correction/takedown list (see "Corrections & takedowns")
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
  make_app_data.py         writes data/incidents.app.json
  make_icons.py            re-renders assets/ icons + OG image from assets/logo.svg (manual)
  test_ui.py               full Playwright audit, desktop + mobile (filters, time edge cases, geolocation denied,
                           search no-result, zero-row export, XSS probe, spiderfy, popups, legal pages)
  verify_live.py           live smoke check + desktop/mobile screenshots
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
   - fetches Google News RSS (EN+HI) into today's archive folder, merges (applying data/takedowns.json), rebuilds CSV +
     full PDF only if data changed, writes data/incidents.app.json, copies site files (app, legal pages, PWA files, assets) + source code (scripts/, README, requirements, .gitignore, NCRB/census inputs) to /workspace/safety-map-site, commits and pushes to `main` only if something differs.
   - Options: `--no-fetch` (re-ingest archived files only), `--no-push` (commit locally only). A lock prevents parallel runs.
   - Log: `logs/daily_<timestamp>.log`; look for `RESULT: CHANGED|NOCHANGE` and `Pushed to main.`
3. Optional check: `gh api repos/abalendup-26/mahila-suraksha-map/pages/builds/latest --jq .status` → `built`.

Rebuild district layer: `python3 scripts/build_districts.py`. Local audit: `python3 -m http.server 8765` then
`.venv/bin/python scripts/test_ui.py http://localhost:8765/ screenshots/test`; live check:
`.venv/bin/python scripts/verify_live.py https://abalendup-26.github.io/mahila-suraksha-map/ screenshots/live`.

## Corrections & takedowns
Requests arrive by email (address in the legal pages – `TODO`) or the public GitHub issue form
(`.github/ISSUE_TEMPLATE/correction.yml`; the form warns users not to post personal details).
To remove an item, add it to `data/takedowns.json` and run the daily script:
```json
{"incidents": {"inc0123": "Removed on request (identity concern)"}, "urls": {"https://example.com/article": "Retracted by outlet"}}
```
The builder then strips the incident's headline, place, coordinates and links from incidents.json/CSV/PDF/app data,
keeps only its id + SHA-1 hashes of its source URLs (so the same articles are never re-added), and marks it hidden.
Victim/child-identity complaints: act within 24 h (IT Rules 2021, Rule 3(2)(b)). Note: older git commits still contain
earlier versions of the data; purging those needs a history rewrite (force-push) – a separate, deliberate decision.

## Privacy
Headlines are rebuilt from the archived original text on every run. Adult ages are kept; ages < 18 (digits, English/Hindi number words, months-old) become "minor"/"नाबालिग". Removed: names after victim/relative nouns, "Name (16)"-style names, "Justice for <name>", phone numbers, house/flat/street numbers, school/college/coaching/company names (name heuristics are skipped for Title-Case headlines to avoid false hits),
X post text is never shown (template summary + link only), and redaction rules are re-applied to old incidents on every run.
