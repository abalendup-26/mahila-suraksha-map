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
TOL = 0.006  # ~0.6 km Douglas-Peucker tolerance (degrees); keeps the file small for mobile

def dp(pts, tol):
    """Iterative Douglas-Peucker on a list of [x, y]."""
    if len(pts) < 3: return pts
    keep = [False] * len(pts); keep[0] = keep[-1] = True; st = [(0, len(pts) - 1)]
    while st:
        a, b = st.pop(); ax, ay = pts[a]; bx, by = pts[b]; dx, dy = bx - ax, by - ay; L = (dx * dx + dy * dy) or 1e-18
        best, bi = -1, -1
        for i in range(a + 1, b):
            px, py = pts[i]; t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
            d = (ax + t * dx - px) ** 2 + (ay + t * dy - py) ** 2
            if d > best: best, bi = d, i
        if best > tol * tol: keep[bi] = True; st += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]

def simp_ring(r):
    o = [[round(x, 3), round(y, 3)] for x, y in dp(r, TOL)]
    o = [p for i, p in enumerate(o) if i == 0 or p != o[i - 1]]
    if len(o) < 4: o = [[round(x, 3), round(y, 3)] for x, y in r]  # never drop a small district
    if o[0] != o[-1]: o.append(o[0])
    return o

def simplify(g):
    if not g: return g
    if g["type"] == "Polygon": return {"type": "Polygon", "coordinates": [simp_ring(r) for r in g["coordinates"]]}
    if g["type"] == "MultiPolygon":
        return {"type": "MultiPolygon", "coordinates": [[simp_ring(r) for r in poly] for poly in g["coordinates"]]}
    return g

feats, matched_pop, with_data = [], 0, 0
for f in src["features"]:
    p = f["properties"]; c = p.get("census2011")
    q = {"d": p["dis"].strip(), "s": p["state"]}
    for k, v in KEYS.items(): q[k] = p.get(v)
    if q["rape"] is not None: with_data += 1
    if c in pop:
        q["fpop11"] = int(pop[c]["Female"]); q["pop11"] = int(pop[c]["Population"]); matched_pop += 1
    feats.append({"type": "Feature", "properties": q, "geometry": simplify(f["geometry"])})
json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(D, "districts.geojson"), "w"), separators=(",", ":"))
print("features", len(feats), "with 2024 data", with_data, "with census-2011 population", matched_pop)
