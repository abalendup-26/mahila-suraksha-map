#!/usr/bin/env python3
"""Extract the date a crime OCCURRED from report text (headline / article body), resolved against the
publish date. Returns (YYYY-MM-DD, matched_phrase) or None. Only short matched phrases are kept, never text."""
import re
from datetime import date, timedelta

EN_MON = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
HI_MON = {"जनवरी": 1, "फरवरी": 2, "फ़रवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6, "जुलाई": 7, "अगस्त": 8,
          "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10, "अक्तूबर": 10, "नवंबर": 11, "नवम्बर": 11, "दिसंबर": 12, "दिसम्बर": 12}
EN_DAY = {d: i for i, d in enumerate("monday tuesday wednesday thursday friday saturday sunday".split())}
HI_DAY = {"सोमवार": 0, "मंगलवार": 1, "बुधवार": 2, "गुरुवार": 3, "बृहस्पतिवार": 3, "वीरवार": 3, "शुक्रवार": 4, "शनिवार": 5, "रविवार": 6}
NUMW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "a": 1, "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10}
def _n(x): return int(x) if x.isdigit() else NUMW.get(x.lower(), None)

_MON_RX = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_NUM_RX = r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|a)"
_HNUM_RX = r"(\d{1,2}|एक|दो|तीन|चार|पांच|पाँच|छह|सात|आठ|नौ|दस)"
PATTERNS = [  # (regex, kind)
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MON_RX + r"\.?(?:,?\s+(\d{4}))?\b", re.I), "dmy"),
    (re.compile(r"\b" + _MON_RX + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", re.I), "mdy"),
    (re.compile(r"(\d{1,2})\s+(" + "|".join(HI_MON) + r")(?:,?\s+(\d{4}))?"), "hdmy"),
    (re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b"), "num"),
    (re.compile(r"\b(?:on|late on|early on|last)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:\s+(?:night|evening|morning|afternoon))?\b(?!['’]s)", re.I), "wd"),
    (re.compile(r"(" + "|".join(HI_DAY) + r")(?:\s+(?:को|की|देर|रात|शाम|सुबह|दोपहर))"), "hwd"),
    (re.compile(r"\b(yesterday|last night|late last night|on the previous night)\b", re.I), "y"),
    (re.compile(r"(बीती रात|कल रात|कल देर रात|कल शाम|बीते दिन|बीते कल)"), "y"),
    (re.compile(r"(?<!India )\b(earlier today|this morning|today|tonight)\b"), "t"),  # lower-case only ("India Today" is an outlet)
    (re.compile(r"(आज सुबह|आज दोपहर|आज शाम|आज तड़के)"), "t"),
    (re.compile(r"\b" + _NUM_RX + r"\s+days?\s+(?:ago|back|earlier)\b", re.I), "da"),
    (re.compile(_HNUM_RX + r"\s+दिन\s+(?:पहले|पूर्व)"), "da"),
    (re.compile(r"\b" + _NUM_RX + r"\s+years?\s+(?:ago|back|earlier)\b", re.I), "ya"),
    (re.compile(_HNUM_RX + r"\s+(?:साल|वर्ष)\s+(?:पहले|पूर्व|पुराने)"), "ya"),
]

def _resolve(kind, m, pub):
    g = m.groups()
    try:
        if kind in ("dmy", "mdy", "hdmy"):
            if kind == "dmy": d, mo, y = int(g[0]), EN_MON[g[1][:3].lower()], g[2]
            elif kind == "mdy": mo, d, y = EN_MON[g[0][:3].lower()], int(g[1]), g[2]
            else: d, mo, y = int(g[0]), HI_MON[g[1]], g[2]
            if y: return date(int(y), mo, d)
            x = date(pub.year, mo, d)
            return x if x <= pub else date(pub.year - 1, mo, d)
        if kind == "num": return date(int(g[2]), int(g[1]), int(g[0]))  # Indian D/M/Y
        if kind in ("wd", "hwd"):
            wd = EN_DAY[g[0].lower()] if kind == "wd" else HI_DAY[g[0]]
            back = (pub.weekday() - wd) % 7
            if back == 0 and m.group(0).lower().strip().startswith("last"): back = 7
            return pub - timedelta(days=back)
        if kind == "y": return pub - timedelta(days=1)
        if kind == "t": return pub
        if kind == "da":
            n = _n(g[0]); return pub - timedelta(days=n) if n and n <= 60 else None
        if kind == "ya":
            n = _n(g[0]); return date(pub.year - n, pub.month, min(pub.day, 28)) if n and n <= 40 else None
    except (ValueError, KeyError):
        return None

COURT_RE = re.compile(r"court|convict|sentenc|verdict|acquit|life term|jail term|bail|अदालत|कोर्ट|दोषी|सजा|सज़ा|उम्रकैद|बरी|जमानत", re.I)

def extract(text, pub, mode="headline", court=False):
    """text: headline or article text; pub: datetime.date of publication. Earliest-in-text valid match wins.
    mode="article" is stricter because web pages also carry datelines, "updated N days ago" widgets and
    related-story lists: there, "today"/"N days ago" are ignored, an explicit date within 2 days of the publish
    date (a dateline) is ignored, a year-less date must fall within 60 days before publication, and a bare
    weekday needs "on"/"last" or a time of day (night, evening ...).
    court=True (headline is about a court verdict): weekday / yesterday / today terms are ignored."""
    if not text: return None
    hits = []
    for rx, kind in PATTERNS:
        if mode == "article" and kind in ("t", "da"): continue
        if court and kind in ("wd", "hwd", "y", "t"): continue  # in court-verdict reports these refer to the hearing
        for m in rx.finditer(text):
            if mode == "article":
                d0 = _resolve(kind, m, pub); g0 = m.group(0).strip().lower()
                if d0 is None: continue
                if kind in ("dmy", "mdy", "hdmy", "num"):
                    if abs((pub - d0).days) <= 2: continue
                    if not re.search(r"\d{4}", g0) and (pub - d0).days > 60: continue
                if kind == "wd" and not re.search(r"^(on|last|late|early)\b|night|evening|morning|afternoon", g0): continue
            # "on Tuesday" etc. must not be part of a longer unrelated phrase like "Tuesday's hearing"
            d = _resolve(kind, m, pub)
            if d and date(pub.year - 41, 1, 1) <= d <= pub:
                if kind in ("dmy", "mdy", "num") and (pub - d).days > 400 and not re.search(r"\d{4}", m.group(0)): continue
                hits.append((m.start(), d, m.group(0).strip(), kind))
                break  # first valid match of each pattern only
    if not hits: return None
    hits.sort()
    _, d, phrase, kind = hits[0]
    return d.isoformat(), phrase[:40], kind

if __name__ == "__main__":
    P = date(2026, 10, 8)  # a Thursday
    for t in ["Woman molested on Tuesday night in Bhajanpura", "मंगलवार रात युवती से छेड़छाड़", "Girl raped yesterday, accused held",
              "बीती रात चेन स्नैचिंग", "Body found two days ago", "दहेज हत्या 14 साल पहले", "Incident on October 3 near station",
              "5 अक्टूबर को हुई घटना", "Accused held", "Sunday's hearing", "on 05.10.2026 the accused", "Dec 25 party"]:
        print(t, "->", extract(t, P))
