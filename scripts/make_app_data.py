#!/usr/bin/env python3
"""Write data/incidents.app.json: a slim copy of incidents.json for the web app (faster mobile load).
Keeps only incidents with a verifiable source link and only the fields the UI uses. incidents.json stays the
full append-only master (unchanged)."""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D = os.path.join(ROOT, "data")
j = json.load(open(os.path.join(D, "incidents.json"), encoding="utf-8"))
F = ["id", "type", "type_label", "channel", "date", "first_seen", "place", "state", "lat", "lon", "precision", "headline",
     "summary", "status", "verification", "place_reported", "place_reported_by", "place_reported_in", "geocode",
     "incident_date", "incident_date_basis", "incident_date_text", "pin_level", "city", "city_lat", "city_lon"]
out = []
for i in j["incidents"]:
    if i.get("verifiable") is False or i.get("channel") == "social": continue
    o = {k: i.get(k) for k in F if i.get(k) not in (None, "")}
    src = []
    for s in i["sources"]:
        t = {"name": s.get("name"), "date": s.get("date"), "kind": s.get("kind", "article")}
        if s.get("article_url"): t["article_url"] = s["article_url"]
        else: t["url"] = s.get("url")
        src.append(t)
    o["sources"] = src; out.append(o)
meta = {k: j.get(k) for k in ("schema", "last_updated", "first_collected", "date_span", "incident_date_span", "count", "count_visible")}
meta["hidden"] = len(j["incidents"]) - len(out); meta["incidents"] = out
tmp = os.path.join(D, "incidents.app.json.tmp")
json.dump(meta, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
os.replace(tmp, os.path.join(D, "incidents.app.json"))
print("app data:", len(out), "incidents,", os.path.getsize(os.path.join(D, "incidents.app.json")), "bytes")
