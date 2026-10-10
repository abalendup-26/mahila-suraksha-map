#!/usr/bin/env python3
"""Rule-based (no AI) extraction of the most specific place of an incident from article text, plus
geocoding bounded to the incident's district. Runs unattended in GitHub Actions.

1. fetch_article(url): publisher article text (trafilatura if installed, else <p> paragraphs). Text is used in
   memory only and never stored; data/article_cache.json keeps only the extracted place names + incident date.
2. place_candidates(text): police station ("थाना X", "X थाना क्षेत्र", "X कोतवाली", "X police station"),
   locality ("X इलाके", "मोहल्ला X", "X कॉलोनी", "Sector 12", "X Nagar/Colony/Vihar", "in X area"),
   village ("X गांव", "ग्राम X", "X village"), landmark/street ("X चौराहे", "X बाजार", "X Road", "near X market").
3. OSM gazetteer per district (Overpass: place=suburb/neighbourhood/quarter/village/hamlet/locality and
   amenity=police, names incl. name:hi), cached in data/osm/<district>.json.
4. geocode: gazetteer match first, else Nominatim bounded to the district bounding box; every result must fall
   inside the district polygon (or within 25 km of the city) and must not be the city itself.
"""
import json, os, re, time, html, urllib.request, urllib.parse, math, hashlib, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); DATA = os.path.join(ROOT, "data")
BUA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
OSM_UA = {"User-Agent": "SafeNaksha/1.0 (+https://github.com/abalendup-26/mahila-suraksha-map; non-commercial women-safety awareness map)"}
try:
    import trafilatura
except Exception:
    trafilatura = None

# ------------------------------------------------------------------ article text
def fetch_article(url):
    req = urllib.request.Request(url, headers={**BUA, "Accept-Language": "en-IN,hi;q=0.8"})
    h = urllib.request.urlopen(req, timeout=25).read(1500000).decode("utf-8", "ignore")
    txt = None
    if trafilatura:
        try: txt = trafilatura.extract(h, include_comments=False, include_tables=False, favor_precision=True)
        except Exception: txt = None
    if not txt:
        h2 = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", h)
        paras = [html.unescape(re.sub(r"<[^>]+>", " ", x)) for x in re.findall(r"(?is)<p[^>]*>(.*?)</p>", h2)]
        txt = "\n".join(re.sub(r"\s+", " ", x).strip() for x in paras if len(x.strip()) > 40)
    return (txt or "")[:6000]

# ------------------------------------------------------------------ candidates
HW = r"[\u0900-\u097F]+"
HN1 = r"(" + HW + r")"; HN2 = r"(" + HW + r"(?:\s" + HW + r")?)"
EW = r"[A-Z][a-zA-Z'’.-]+"; EN2 = r"(" + EW + r"(?:\s" + EW + r"){0,2})"
HI_SUFFIX = r"(?:नगर|कॉलोनी|कालोनी|विहार|पुरम|गंज|बाग|पुरी|पुर|एन्क्लेव|बस्ती)"
EN_SUFFIX = r"(?:Nagar|Colony|Vihar|Enclave|Puram|Ganj|Bagh|Extension|Layout|Basti|Mohalla|Chowk|Bazaar|Bazar|Market|Road|Marg|Park|Halli)"
PAT = [  # (regex, kind, group)
    (re.compile(r"थाना\s+(?:क्षेत्र\s+)?" + HN2 + r"(?=\s+(?:क्षेत्र|इलाके|इलाका|के|की|में|पुलिस|से|ने|,))"), "police", 1),
    (re.compile(HN2 + r"\s+(?:थाना|थाने)(?:\s*क्षेत्र)?"), "police", 1),
    (re.compile(HN1 + r"\s+कोतवाली"), "police", 1),
    (re.compile(r"कोतवाली\s+" + HN1 + r"(?=\s+(?:क्षेत्र|इलाके|के|की|में|पुलिस))"), "police", 1),
    (re.compile(EN2 + r"\s+police\s+station"), "police", 1),
    (re.compile(r"(?:jurisdiction|limits) of (?:the )?" + EN2 + r"(?:\s+police)?"), "police", 1),
    (re.compile(r"(" + HW + r"(?:\s" + HW + r")?\s" + HI_SUFFIX + r")(?=\s|,|।|$)"), "locality", 1),
    (re.compile(r"(?:मोहल्ला|मोहल्ले|मुहल्ला|कॉलोनी|सेक्टर)\s+" + HN1), "locality", 1),
    (re.compile(HN2 + r"\s+(?:इलाके|इलाका|मोहल्ले|मोहल्ला|कॉलोनी|कालोनी)"), "locality", 1),
    (re.compile(r"\b(Sector[-\s]?\d{1,3}[A-Z]?)\b"), "locality", 1),
    (re.compile(r"(?:सेक्टर)[-\s]?(\d{1,3})"), "sector", 1),
    (re.compile(r"(" + EW + r"(?:\s" + EW + r")?\s" + EN_SUFFIX + r")\b"), "locality", 1),
    (re.compile(r"\bin\s+(?:the\s+)?" + EN2 + r"\s+(?:area|locality|neighbourhood|neighborhood)\b"), "locality", 1),
    (re.compile(HN1 + r"\s+(?:गांव|गाँव|ग्राम)"), "village", 1),
    (re.compile(r"(?:गांव|गाँव|ग्राम)\s+" + HN1), "village", 1),
    (re.compile(EN2 + r"\s+village\b"), "village", 1),
    (re.compile(r"\bvillage\s+" + EN2), "village", 1),
    (re.compile(HN2 + r"\s+(?:चौराहे|चौराहा|चौक|बाजार|बाज़ार|मार्ग|रोड|मेट्रो\sस्टेशन|बस\sस्टैंड)"), "street", 1),
    (re.compile(r"near\s+(?:the\s+)?" + EN2 + r"\s+(?:metro station|bus stand|railway station|market|temple|chowk|crossing)"), "street", 1),
]
STOP_HI = set("""जिला जिले जनपद नगर की के का ने से में यूपी पुलिस थाना थाने उत्तर प्रदेश स्थानीय राज्य अधीक्षक महिला क्षेत्र सदर कोतवाली मामले
आरोपी युवती नाबालिग त्वरित बड़ी कार्रवाई द्वारा टीम ग्रामीण देहात शहर इस उस एक और भी को है था थी गांव कस्बा संबंधित संबंधित पीड़िता पीड़ित परिजनों
परिवार उसके उनके अपने किसी वहीं यहां वहां अन्य दूसरे पहले बाद पास मुख्य सभी स्थित निवासी रहने वाली वाले वाला गई गए किया कर लेकर पर तक लिए
शिकायत मुकदमा केस एफआईआर रिपोर्ट प्रभारी इंस्पेक्टर निरीक्षक एसएचओ एसपी डीएसपी सीओ महिलाओं बच्ची लड़की युवक पति पत्नी ससुराल मायके दहेज
बदमाश बदमाशों चोर लुटेरे स्नैचर आरोपियों मौके संबंधित साइबर महिला-थाना शहरी नगर-निगम उक्त जांच कोर्ट न्यायालय""".split())
STOP_EN = set("""the a an this that police station district city town village area local woman women girl minor man men accused victim her his their
women's mahila cyber all several one two three nearby same main city's state national railway government new old north south east west central
district's police's sadar kotwali civil lines""".split())

def _clean(name):
    name = re.sub(r"[।|:;!?()\[\]{}“”\"]", " ", name).strip(" .,-’'")
    name = re.sub(r"\s+", " ", name)
    parts = name.split()
    while parts and (parts[0] in STOP_HI or parts[0].lower() in STOP_EN): parts = parts[1:]
    while parts and (parts[-1] in STOP_HI or parts[-1].lower() in STOP_EN): parts = parts[:-1]
    return " ".join(parts)

def place_candidates(text, city_names=()):
    """-> [(name, kind)] in text order, de-duplicated. city_names are skipped (not more specific)."""
    if not text: return []
    bad = {c.lower() for c in city_names if c}
    out = []
    for rx, kind, g in PAT:
        for m in rx.finditer(text):
            n = _clean(m.group(g))
            if kind == "sector": n = "Sector " + n; kind2 = "locality"
            else: kind2 = kind
            if len(n) < 3 or n.lower() in bad or n in STOP_HI or n.lower() in STOP_EN: continue
            if re.fullmatch(r"[\u0900-\u097F]{1,2}", n): continue
            if any(w.lower() in bad for w in n.split()) and kind2 != "locality": continue
            out.append((m.start(), n, kind2))
    out.sort()
    seen, res = set(), []
    for _, n, k in out:
        if (n, k) in seen: continue
        seen.add((n, k)); res.append((n, k))
    return res[:12]

# ------------------------------------------------------------------ districts
def pip(lon, lat, geom):
    def inring(r):
        ins = False; j = len(r) - 1
        for i in range(len(r)):
            xi, yi = r[i][0], r[i][1]; xj, yj = r[j][0], r[j][1]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi: ins = not ins
            j = i
        return ins
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return any(inring(p[0]) for p in polys)

def bbox(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    xs = [c[0] for p in polys for c in p[0]]; ys = [c[1] for p in polys for c in p[0]]
    return min(xs), min(ys), max(xs), max(ys)

class Districts:
    def __init__(self):
        self.f = json.load(open(os.path.join(DATA, "districts.geojson"), encoding="utf-8"))["features"]
        self.bb = [bbox(f["geometry"]) for f in self.f]
    def find(self, lat, lon):
        for f, b in zip(self.f, self.bb):
            if b[0] <= lon <= b[2] and b[1] <= lat <= b[3] and pip(lon, lat, f["geometry"]): return f, b
        return None, None

def km(a, b, c, d):
    R = 6371; r = math.pi / 180
    x = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))

# ------------------------------------------------------------------ OSM gazetteer (Overpass)
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
OSM_DIR = os.path.join(DATA, "osm")
OSM_STATE = {"n": 0, "fail": 0}
def norm(s):
    s = unicodedata.normalize("NFC", s or "").lower().replace("़", "")
    s = re.sub(r"\b(nagar|colony|police station|thana|village|gaon)\b", lambda m: m.group(0), s)
    return re.sub(r"[^\w\u0900-\u097F ]+", " ", s).strip()

def osm_gazetteer(dkey, b, max_new=40):
    os.makedirs(OSM_DIR, exist_ok=True)
    fn = os.path.join(OSM_DIR, re.sub(r"[^a-z0-9]+", "_", dkey.lower()).strip("_") + ".json")
    if os.path.exists(fn): return json.load(open(fn, encoding="utf-8"))
    if os.environ.get("OVERPASS") == "0" or OSM_STATE["n"] >= max_new or OSM_STATE["fail"] >= 2: return None
    OSM_STATE["n"] += 1
    s, w, n, e = b[1], b[0], b[3], b[2]
    q = (f'[out:json][timeout:60];(node["place"~"^(suburb|neighbourhood|quarter|village|hamlet|locality|town)$"]({s},{w},{n},{e});'
         f'nwr["amenity"="police"]({s},{w},{n},{e});way["place"~"^(suburb|neighbourhood|quarter)$"]({s},{w},{n},{e});'
         ');out center tags;')
    for attempt in range(2):
        ep = OVERPASS[(attempt + OSM_STATE['fail']) % len(OVERPASS)]
        try:
            r = urllib.request.urlopen(urllib.request.Request(ep, data=urllib.parse.urlencode({"data": q}).encode(), headers=OSM_UA), timeout=70).read()
            d = json.loads(r)
            rows = []
            for el in d.get("elements", []):
                t = el.get("tags", {}); nm = t.get("name")
                if not nm: continue
                lat = el.get("lat") or el.get("center", {}).get("lat"); lon = el.get("lon") or el.get("center", {}).get("lon")
                if lat is None: continue
                kind = "police" if t.get("amenity") == "police" else ("residential" if t.get("landuse") == "residential" else t.get("place"))
                rows.append([nm, t.get("name:hi") or "", t.get("name:en") or "", round(lat, 5), round(lon, 5), kind])
            json.dump(rows, open(fn, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
            time.sleep(2)
            return rows
        except Exception as ex:
            print("overpass fail", ep.split("/")[2], str(ex)[:60]); time.sleep(5 * (attempt + 1))
    OSM_STATE["fail"] += 1
    return None

_PS_RX = re.compile(r"\b(police station|police chowki|police post|police outpost|thana|chowki|पुलिस स्टेशन|पुलिस चौकी|थाना|थाने|कोतवाली|police)\b", re.I)
def gaz_match(rows, name, kind):
    if not rows: return None
    k = norm(name); cands = []
    for nm, hi, en, lat, lon, typ in rows:
        names = [x for x in (nm, hi, en) if x]
        if kind == "police":
            if typ != "police": continue
            base = [_PS_RX.sub("", x).strip() for x in names]
            if any(norm(x) == k or skel_eq(x, name) for x in base if x): cands.append((lat, lon, typ, nm))
        else:
            if typ == "police": continue
            if any(norm(x) == k or skel_eq(x, name) for x in names): cands.append((lat, lon, typ, nm))
    if len(cands) == 1 or (cands and kind == "police"): return cands[0]
    if len(cands) > 1:  # ambiguous name inside the district: accept only if all hits are within 3 km
        if all(km(cands[0][0], cands[0][1], c[0], c[1]) < 3 for c in cands): return cands[0]
    return None

# ------------------------------------------------------------------ Nominatim bounded
NOM_FN = os.path.join(DATA, "geocode_cache.json")
_last = [0.0]
def nominatim_bounded(q, b, cache):
    key = f"{q}|{b[0]:.2f},{b[1]:.2f},{b[2]:.2f},{b[3]:.2f}"
    if key in cache: return cache[key]
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    _last[0] = time.time()
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "jsonv2", "limit": 3, "countrycodes": "in", "namedetails": 1, "viewbox": f"{b[0]},{b[3]},{b[2]},{b[1]}", "bounded": 1})
    try: r = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={**OSM_UA, "Accept-Language": "en"}), timeout=30).read())
    except Exception as ex: print("nominatim fail", q, str(ex)[:60]); return None
    res = [{"lat": float(x["lat"]), "lon": float(x["lon"]), "type": x.get("addresstype") or x.get("type"), "cls": x.get("category") or x.get("class"),
            "display": x["display_name"], "names": sorted(set(v for kk, v in (x.get("namedetails") or {}).items() if kk.startswith(("name", "alt_name", "old_name"))))} for x in r]
    cache[key] = res
    return res

LEVEL = {"street": "Street / landmark (approx., ±0.5–1 km)", "locality": "Locality / neighbourhood (approx., ±1–2 km)",
         "police": "Police-station area (approx., ±2–3 km)", "village": "Village (approx., ±1–2 km)",
         "city": "City/district only – not pinned on the map"}
LOCAL_TYPES = {"suburb": "locality", "neighbourhood": "locality", "quarter": "locality", "residential": "locality", "city_district": "locality",
               "borough": "locality", "locality": "locality", "allotments": "locality", "village": "village", "hamlet": "village", "isolated_dwelling": "village",
               "town": "locality", "road": "street", "square": "street", "amenity": "street", "railway": "street", "shop": "street", "highway": "street",
               "police": "police", "retail": "street", "city_block": "locality", "district": None, "county": None, "state": None, "city": None, "commercial": "street", "place_of_worship": "street", "bus_station": "street", "station": "street", "market": "street"}

def classify_result(x, kind):
    if x.get("type") == "police" or (kind == "police" and x.get("cls") == "amenity"): return "police"
    t = LOCAL_TYPES.get(x.get("type")) or LOCAL_TYPES.get(x.get("cls"))
    return t

def _name_ok(cand, names):
    """the geocoder result must actually carry the reported name (exact, contained, or same consonant skeleton)"""
    c = norm(_PS_RX.sub("", cand)).strip()
    for n in names:
        n2 = norm(_PS_RX.sub("", n or "")).strip()
        if not n2: continue
        if c == n2 or (len(c) >= 5 and (c in n2.split() or n2.startswith(c + " "))) or skel_eq(c, n2): return True
    return False

def locate(cands, dist, b, city_ll, gaz_rows, nomcache, city_names=()):
    """-> dict(lat, lon, level, name, kind, method) or None"""
    order = {"street": 0, "locality": 1, "village": 2, "police": 3}
    bad = {c.lower() for c in city_names}
    def ok(lat, lon):
        inside = dist is not None and pip(lon, lat, dist["geometry"])
        near = city_ll and km(city_ll[0], city_ll[1], lat, lon) <= 25
        not_city = not city_ll or km(city_ll[0], city_ll[1], lat, lon) > 0.3
        return (inside or near) and not_city
    for name, kind in sorted(cands, key=lambda c: order.get(c[1], 9))[:5]:
        if name.lower() in bad or any(skel_eq(name, c) for c in city_names if c): continue
        g = gaz_match(gaz_rows, name, kind)
        if g and ok(g[0], g[1]):
            lvl = "police" if g[2] == "police" else ("village" if g[2] in ("village", "hamlet") else "locality")
            return {"lat": g[0], "lon": g[1], "level": lvl, "name": name, "kind": kind,
                    "method": f"matched OpenStreetMap {g[2]} “{g[3]}” in the district gazetteer (Overpass)"}
        if b is None: continue
        lat_name = romanize(name) if re.search(r"[\u0900-\u097F]", name) else name
        qs = [f"{lat_name} police station", lat_name] if kind == "police" else [lat_name]
        for q in qs:
            for x in nominatim_bounded(q, b, nomcache) or []:
                lvl = classify_result(x, kind)
                if lvl and ok(x["lat"], x["lon"]) and _name_ok(name, x.get("names") or [x["display"].split(",")[0]]) \
                        and not any(skel_eq(x["display"].split(",")[0], c) for c in city_names if c):
                    return {"lat": x["lat"], "lon": x["lon"], "level": lvl, "name": name, "kind": kind,
                            "method": f"OpenStreetMap Nominatim query “{q}” limited to the district → {x['display'].split(',')[0]} ({x['type']})"}
        for x in [y for q in ([lat_name + " police", lat_name] if kind == "police" else [lat_name]) for y in (photon(q, b) or [])]:
            lvl = classify_result(x, kind)
            if lvl and ok(x["lat"], x["lon"]) and _name_ok(name, [x["name"]]) and not any(skel_eq(x["name"], c) for c in city_names if c):
                return {"lat": x["lat"], "lon": x["lon"], "level": lvl, "name": name, "kind": kind,
                        "method": f"OpenStreetMap Photon search “{lat_name}” limited to the district → {x['name']} ({x['type']})"}
    return None

if __name__ == "__main__":
    for t in ["गाजियाबाद के मुरादनगर थाना क्षेत्र के एक गांव में", "थाना कोतवाली नगर क्षेत्र के मोहल्ला किला में युवती से छेड़छाड़",
              "The incident took place in Bhajanpura area of northeast Delhi under the jurisdiction of Bhajanpura police station",
              "near Rajiv Chowk metro station", "a resident of Shastri Nagar", "सेक्टर 62 में", "Ramnagar village in Baghpat", "सिकंदरपुर में"]:
        print(t, "->", place_candidates(t))

# ------------------------------------------------------------------ Hindi -> Latin (for geocoding Hindi place names)
_C = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n", "ट": "t", "ठ": "th", "ड": "d",
      "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y",
      "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l"}
_NUK = {"क": "q", "ख": "kh", "ग": "gh", "ज": "z", "फ": "f", "ड": "r", "ढ": "rh"}
_V = {"अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o"}
_M = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o"}
def romanize(s):
    s = unicodedata.normalize("NFD", s); out = []; i = 0
    while i < len(s):
        ch = s[i]; nxt = s[i + 1] if i + 1 < len(s) else ""
        if ch in _C:
            c = _C[ch]
            if nxt == "़": c = _NUK.get(ch, c); i += 1; nxt = s[i + 1] if i + 1 < len(s) else ""
            out.append(c)
            if nxt == "्": i += 1
            elif nxt in _M: out.append(_M[nxt]); i += 1
            else: out.append("@")
        elif ch in _V: out.append(_V[ch])
        elif ch in "ंँ": out.append("n")
        elif ch == "ः": out.append("h")
        elif ch == " ": out.append(" ")
        i += 1
    w = "".join(out)
    w = re.sub(r"@(?=\s|$)", "", w).replace("@", "a")
    w = re.sub(r"anv\b", "aon", w)  # final inherent-schwa deletion
    return " ".join(x.capitalize() for x in w.split())

def skel(s):
    """Consonant skeleton used to compare a Hindi name with an English OSM name."""
    if re.search(r"[\u0900-\u097F]", s or ""): s = romanize(s)
    s = re.sub(r"c(?=[ei])", "s", (s or "").lower())
    for a, b in (("chh", "c"), ("ch", "c"), ("sh", "s"), ("ph", "f"), ("kh", "k"), ("gh", "g"), ("jh", "j"), ("th", "t"), ("dh", "d"), ("bh", "b"),
                 ("w", "v"), ("z", "j"), ("q", "k"), ("x", "ks"), ("ck", "k")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]", "", s); s = re.sub(r"[aeiouyh]", "", s)
    return re.sub(r"(.)\1+", r"\1", s)

PHOTON_FN = os.path.join(DATA, "photon_cache.json")
_photon = json.load(open(PHOTON_FN, encoding="utf-8")) if os.path.exists(PHOTON_FN) else {}
_plast = [0.0]
def photon(q, b):
    key = f"{q}|{b[0]:.2f},{b[1]:.2f},{b[2]:.2f},{b[3]:.2f}"
    if key in _photon: return _photon[key]
    wait = 1.1 - (time.time() - _plast[0])
    if wait > 0: time.sleep(wait)
    _plast[0] = time.time()
    url = "https://photon.komoot.io/api/?" + urllib.parse.urlencode({"q": q, "limit": 6, "bbox": f"{b[0]},{b[1]},{b[2]},{b[3]}"})
    try: r = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=OSM_UA), timeout=30).read())
    except Exception as ex: print("photon fail", q, str(ex)[:60]); return None
    res = [{"lat": f["geometry"]["coordinates"][1], "lon": f["geometry"]["coordinates"][0], "name": f["properties"].get("name", ""),
            "type": f["properties"].get("osm_value"), "cls": f["properties"].get("osm_key")} for f in r.get("features", [])]
    _photon[key] = res
    json.dump(_photon, open(PHOTON_FN, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return res

def skel_eq(a, b):
    x, y = skel(a), skel(b)
    if len(x) < 3 or len(y) < 3: return False
    if x == y: return True
    if min(len(x), len(y)) >= 4 and abs(len(x) - len(y)) == 1 and (x.startswith(y) or y.startswith(x)): return True
    return False
