#!/usr/bin/env python3
"""Render data/incidents.json as a printable HTML report and PDF (headless Chrome)."""
import json, os, html, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D = os.path.join(ROOT, "data")
j = json.load(open(os.path.join(D, "incidents.json"))); e = html.escape
rows = []
u_ = lambda u: u if str(u).startswith(("http://", "https://")) else "#"
vis = [i for i in j["incidents"] if i.get("verifiable", True)]
for i in sorted(vis, key=lambda x: (x["state"], x["place"], x["date"])):
    ss = [s for s in i["sources"] if s.get("kind", "article") in ("article", "x_post")]
    src = "<br>".join(f'<b>{e(s["name"])}</b> (published {e(s["date"])}): <a href="{e(u_(s.get("article_url") or s["url"]))}">{e(s.get("article_url") or s["url"])}</a>' for s in ss)
    pin = "±2–5 km" if i["precision"].startswith("Locality") else "±10–30 km"
    placeline = f'“{e(i.get("place_reported",""))}” as reported by {e(i.get("place_reported_by",""))} ({e(i.get("place_reported_in",""))}); map pin approx {pin} at {e(i["place"])}<br><i>{e(i.get("geocode",""))}</i>' 
    rows.append(f"<div class='r'><h3>{e(i['id'])} · {e(i['type_label'])} · {'SOCIAL MEDIA – UNVERIFIED' if i['channel']=='social' else 'News report'}</h3>"
                f"<table><tr><td>Source(s)</td><td>{src}</td></tr><tr><td>Place as reported</td><td>{placeline}</td></tr><tr><td>Report date</td><td>{e(i['date'])} (first seen {e(i.get('first_seen',''))})</td></tr><tr><td>Place</td><td>{e(i['place'])} <i>({e(i['precision'])})</i></td></tr>"
                + (f"<tr><td>Headline</td><td>{e(i['headline'])}</td></tr>" if i['headline'] else "") +
                f"<tr><td>Summary</td><td>{e(i['summary'])}</td></tr><tr><td>Status</td><td>{e(i['status'])}</td></tr>"
                f"<tr><td>Verification</td><td>{e(i['verification'])}</td></tr></table></div>")
doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>SafeNaksha – Incident reports</title><style>
body{{font-family:'Inter','Noto Sans','Noto Sans Devanagari',sans-serif;font-size:10px;margin:20px}} h1{{font-size:16px;color:#4B2A84}}
.r{{border:1px solid #ccc;border-radius:4px;padding:4px 8px;margin:6px 0;page-break-inside:avoid}} h3{{font-size:11px;margin:2px 0}}
td{{vertical-align:top;padding:1px 4px}} td:first-child{{color:#666;white-space:nowrap}} a{{color:#1565c0;word-break:break-all}}
.d{{background:#fff3e0;border:1px solid #ffb74d;padding:6px}}</style></head><body>
<h1>SafeNaksha – Incident reports ({len(vis)} incidents with verifiable source links, cumulative, report dates {j['date_span'][0]} to {j['date_span'][1]}, last updated {j['last_updated']})</h1>
<div class="d">Automatically collected from public news (Google News RSS, English &amp; Hindi) and public X posts/stories. Locations are approximate (city/district or police-station area). Social-media items are unverified. Absence of reports does not mean an area is safe. Adult ages are shown as published; ages of minors are replaced by “minor”/“नाबालिग”. Names and identifying details (family names, house address, school/college/workplace, phone numbers, photos) are removed (BNS Sec. 72; POCSO Sec. 23). Information only – not an official government or police document; district/area figures are statistical and not a judgement on residents. Corrections: see the Terms of Use on the website. Emergency 112 · Women helpline 181.</div>
{''.join(rows)}</body></html>"""
open(os.path.join(D, "incident_reports.html"), "w").write(doc)
subprocess.run(["google-chrome", "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={os.path.join(D, 'incident_reports.pdf')}", "file://" + os.path.join(D, "incident_reports.html")],
               check=True, capture_output=True)
print("pdf written")
