#!/usr/bin/env python3
"""Build data/districts.geojson from the NCRB district layer (Esri India Living Atlas mirror of
NCRB 'Crime in India' district-wise Crime Against Women tables) + Census 2011 female population."""
import json, csv, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D = os.path.join(ROOT, "data")
src = json.load(open(os.path.join(D, "ncrb_raw.geojson")))
pop = {r["District code"]: r for r in csv.DictReader(open(os.path.join(D, "census.csv")))}
KEYS = {"rape": "totrape24", "pocso": "totpocso24", "attempt": "totcmrape24", "modesty": "totmod24", "sexh": "totsexh24",
        "stalk": "totstk24", "kidnap": "totkidabd24", "acid": "acidatt24", "dowry": "dwydeath24", "cruelty": "crlhus24",
        "total": "totcrwom24", "rape23": "totrape23", "rape22": "totrape22"}
feats, matched_pop, with_data = [], 0, 0
for f in src["features"]:
    p = f["properties"]; c = p.get("census2011")
    q = {"d": p["dis"].strip(), "s": p["state"]}
    for k, v in KEYS.items(): q[k] = p.get(v)
    if q["rape"] is not None: with_data += 1
    if c in pop:
        q["fpop11"] = int(pop[c]["Female"]); q["pop11"] = int(pop[c]["Population"]); matched_pop += 1
    feats.append({"type": "Feature", "properties": q, "geometry": f["geometry"]})
json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(D, "districts.geojson"), "w"), separators=(",", ":"))
print("features", len(feats), "with 2024 data", with_data, "with census-2011 population", matched_pop)
