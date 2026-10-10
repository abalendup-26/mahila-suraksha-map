#!/usr/bin/env python3
"""Collect recent news reports about crimes against women in India, extract only the area/city, geocode,
and write data/incidents.json + data/incidents.csv. Runs unattended in GitHub Actions (.github/workflows/daily-update.yml).

Source: Google News RSS search (English + Hindi queries) -> raw XML in data/raw_news/YYYY-MM-DD/ (not committed).
(Social media / X was removed on 2026-10-10; X-only incidents are no longer published.)
APPEND-ONLY: existing data/incidents.json is loaded and never shrinks. New records are deduped by source URL,
attached to an existing incident when the grouping rule matches, otherwise added as new incidents.
Files are rewritten only when something changed (a backup is kept in data/backups/, local runs only).
Incident date: the date the crime occurred, extracted from the headline/article text when stated
(scripts/incident_date.py), otherwise approximated by the report (publish) date.
Prints "RESULT: CHANGED" or "RESULT: NOCHANGE".
Privacy: adult ages kept; minors' ages -> "minor"/"नाबालिग"; names and identifying details removed.
"""
import json, os, re, sys, csv, time, glob, math, hashlib, html
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from gazetteer import Gazetteer
from incident_date import extract as extract_incident_date, COURT_RE
from datetime import date as _date

UA = "SafeNaksha/1.0 (+https://github.com/abalendup-26/mahila-suraksha-map; non-commercial women-safety awareness map)"
NOW = datetime.now(timezone.utc)
IST = timezone(timedelta(hours=5, minutes=30))
TODAY = NOW.astimezone(IST).strftime("%Y-%m-%d")
MAX_AGE_DAYS = 45
FETCH = "--no-fetch" not in sys.argv
RESOLVE = "--no-resolve" not in sys.argv

EN_Q = ["rape case arrested", "gangrape police", "molestation arrested", "eve-teasing arrested",
        "woman stalking arrested", "chain snatching woman", "woman kidnapped police",
        "acid attack woman", "dowry death", "sexual harassment FIR woman", "minor raped accused held"]
HI_Q = ["दुष्कर्म आरोपी गिरफ्तार", "सामूहिक दुष्कर्म", "छेड़छाड़ आरोपी गिरफ्तार", "चेन स्नैचिंग",
        "युवती अपहरण", "तेजाब हमला", "दहेज हत्या", "महिला से छेड़खानी", "नाबालिग से दुष्कर्म"]

TYPES = [  # (id, label, regex) - priority order
 ("rape", "Rape / sexual assault", r"\brap(e|ed|es|ing|ist)\b|gang-?rap|sexual(ly)? assault|बलात्कार|दुष्कर्म|रेप|गैंगरेप|गैंग रेप"),
 ("acid", "Acid attack", r"acid attack|acid on|तेजाब|तेज़ाब|एसिड"),
 ("dowry", "Dowry death / domestic violence", r"dowry|domestic violence|दहेज|घरेलू हिंसा"),
 ("kidnap", "Kidnapping / abduction of woman", r"kidnap|abduct|अपहरण|अगवा"),
 ("stalking", "Stalking", r"stalk|पीछा कर"),
 ("harassment", "Molestation / sexual harassment / eve-teasing", r"molest|eve-?teas|sexual(ly)? harass|harass|grop|indecent|छेड़छाड़|छेड़खानी|छेडछाड|अश्लील हरकत|यौन उत्पीड़न|फब्तियां"),
 ("snatching", "Chain / phone snatching", r"snatch|स्नैच|चेन लूट|झपट|छीन"),
]
TYPE_LABEL = {t[0]: t[1] for t in TYPES}
# Must look like it is about a woman/girl for kidnap/snatching/stalking (those words are generic)
WOMAN_RE = re.compile(r"\b(woman|women|girl|girls|minor|teen|wife|bride|student|lady|daughter)\b|महिला|युवती|किशोरी|नाबालिग|छात्रा|लड़की|बच्ची|पत्नी|विवाहिता|बहू", re.I)
MINOR_RE = re.compile(r"\bminors?\b|\bchild\b|\bteen|\bschoolgirl|\bgirl student|\bna+ba+lig|\bbachchi|नाबालिग|नाबालिका|किशोरी|बच्ची|बालिका|मासूम|छात्रा|POCSO|पॉक्सो", re.I)
STATUS = [
 ("Acquitted by court", r"acquit|बरी"),
 ("Convicted / sentenced (court)", r"convicted|sentenced|life imprisonment|death sentence|सजा|उम्रकैद|दोषी|कैद"),
 ("Accused shot/held after police encounter", r"encounter|मुठभेड़"),
 ("Arrest reported", r"arrest|\bheld\b|\bnab|detained|in custody|गिरफ्तार|दबोच|हिरासत|धराए|धराया|पकड़ा|निरुद्ध"),
 ("Accused absconding", r"abscond|absconding|on the run|फरार"),
 ("FIR / case registered", r"\bFIR\b|case (registered|filed|lodged)|booked|मुकदमा दर्ज|मामला दर्ज|केस दर्ज|प्राथमिकी|एफआईआर"),
 ("Complaint / allegation, police action not stated", r"alleg|complain|आरोप|शिकायत"),
]
DEBUNK_RE = re.compile(r"debunk|fake claim|false claim|rumou?r|अफवाह|फर्जी दावा", re.I)
EXCLUDE_RE = re.compile(r"High Court|\bHC\b|Supreme Court|हाई कोर्ट|हाईकोर्ट|drop in|rise in|decline|NCRB|statistic|data shows|opinion|editorial|explained|top court says|accountability|how to |pakistan|bangladesh|nepal|sri lanka|\bUS\b|\bUK\b|canada|australia|cornell|sindh|kamloops|calgary|"
                        r"\b(19[5-9]\d|200\d|201\d|202[0-4])\b", re.I)
NEWS_DOMAINS = re.compile(r"timesofindia|indiatimes|hindustantimes|ndtv|thehindu|indianexpress|aajtak|amarujala|jagran|"
                          r"bhaskar|livehindustan|abplive|news18|zeenews|indiatoday|tribuneindia|deccanherald|"
                          r"patrika|navbharattimes|thequint|scroll|theprint|ptinews|aninews|ians|republicworld|"
                          r"etvbharat|tv9|firstpost|newindianexpress|telegraphindia|bhaskarenglish|royalbulletin|youtu", re.I)
POLICE_HANDLE = re.compile(r"pol(ice)?$|police|^sp_|^ssp|^dcp|^cp|^dgp|^adg|^ig|uppolice", re.I)

# Ages are SHOWN (user decision 2026-10-10). Only names and other identifying details are removed.
HI_NUM = r"(?:\d{1,2}|एक|दो|तीन|चार|पांच|पाँच|छह|छः|सात|आठ|नौ|दस|ग्यारह|बारह|तेरह|चौदह|पंद्रह|सोलह|सत्रह)"
HI_NUM_VAL = {"एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
              "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14, "पंद्रह": 15, "सोलह": 16, "सत्रह": 17}
EN_NUM_VAL = {w: i + 1 for i, w in enumerate("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen".split())}
AGE_EN = re.compile(r"\b(\d{1,2}|" + "|".join(EN_NUM_VAL) + r")[\s-]*(?:year|yr)s?[\s-]*old\b|\baged\s+(\d{1,2})\b", re.I)
AGE_HI = re.compile(HI_NUM + r"\s*(?:साल|वर्ष|बरस)(?:ीय)?|(\d{1,2})\s*वर्षीय")
def ages_in(t):
    out = []
    for m in AGE_EN.finditer(t or ""):
        v = m.group(1) or m.group(2); out.append(int(v) if v.isdigit() else EN_NUM_VAL.get(v.lower(), 99))
    for m in AGE_HI.finditer(t or ""):
        w = re.match(HI_NUM, m.group(0)); v = (w.group(0) if w else m.group(1)) or ""
        out.append(int(v) if v.isdigit() else HI_NUM_VAL.get(v, 99))
    return out
def is_minor(t):
    """Minor victim: explicit words (minor / nabalig / bachchi …) or a stated age below 18."""
    return bool(MINOR_RE.search(t or "")) or any(a < 18 for a in ages_in(t))
# Other identifiers that are always removed (phone numbers, house/street addresses, institutions, relatives' names).
ID_PATTERNS = [
 (re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{4}[\s-]?\d{5}\b"), "[phone removed]"),
 (re.compile(r"\b(?:house|h\.?\s?no|flat|plot|door)\s*(?:no\.?|number|#)?\s*[:.]?\s*[\w/-]*\d[\w/-]*", re.I), "[address removed]"),
 (re.compile(r"\b(?:[A-Z][\w.]*\s){0,3}(?:street|lane|gali|marg|road)\s*(?:no\.?\s*)?\d+\b", re.I), "[address removed]"),
 (re.compile(r"(?:मकान|घर|फ्लैट|प्लॉट)\s*(?:नंबर|नं\.?|संख्या)\s*[\w/-]+"), "[पता हटाया]"),
 (re.compile(r"(?:गली|मोहल्ला)\s*(?:नंबर|नं\.?)\s*[\w/-]+"), "[पता हटाया]"),
 ("INST_EN", None),
 (re.compile(r"(?:[\u0900-\u097F]+\s){1,2}(?:पब्लिक स्कूल|इंटर कॉलेज|डिग्री कॉलेज|विद्या मंदिर|शिशु मंदिर|कान्वेंट स्कूल|मॉडल स्कूल|इंटरनेशनल स्कूल|एकेडमी|अकादमी)(?=[\s,।]|$)"), "[संस्थान हटाया] "),
 (re.compile(r"\b(father|mother|husband|brother|sister|uncle|aunt|son|daughter|in-law)(\s+of)?\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)(?=\W|$)"),
  lambda m: m.group(1) + (m.group(2) or "") + " " + ("[name removed]" if m.group(3).split()[0] not in EN_OK else m.group(3))),
]
# Ages of minors (< 18, incl. "N-month-old") are replaced by "minor" / "नाबालिग"; adult ages are kept as published.
def _v(x):
    x = (x or "").strip()
    return int(x) if x.isdigit() else HI_NUM_VAL.get(x, EN_NUM_VAL.get(x.lower(), 99))
_ENW = r"(?:\d{1,2}|" + "|".join(EN_NUM_VAL) + r")"
AGE_SUBS = [
 # "11 और छह साल की", "14, 15 वर्ष"
 (re.compile(r"(" + HI_NUM + r"(?:\s*(?:और|व|,)\s*" + HI_NUM + r")*)\s*(?:साल|वर्ष|बरस)(?:ीय)?(\s*(?:की|के|का))?" + r"(?=\s*(?:बच्ची|बच्चि|बच्चे|बच्चा|बच्चों|लड़की|लड़कि|लड़के|लड़का|किशोरी|किशोर|मासूम|छात्रा|छात्र|महिला|युवती|युवक|बालिका|बालक|नाबालिग|बेटी|बेटा|पुत्री|पुत्र|भतीजी|भांजी|पोती|नातिन))"),
  lambda m: "नाबालिग" if any(_v(n) < 18 for n in re.findall(HI_NUM, m.group(1))) else m.group(0)),
 (re.compile(r"(\d{1,2})\s*वर्षीय"), lambda m: "नाबालिग" if int(m.group(1)) < 18 else m.group(0)),
 (re.compile(r"\d{1,2}\s*(?:महीने|माह)\s*(?:की|के|का)?" + r"(?=\s*(?:बच्ची|बच्चि|बच्चे|बच्चा|बच्चों|लड़की|लड़कि|लड़के|लड़का|किशोरी|किशोर|मासूम|छात्रा|छात्र|महिला|युवती|युवक|बालिका|बालक|नाबालिग|बेटी|बेटा|पुत्री|पुत्र|भतीजी|भांजी|पोती|नातिन))"), lambda m: "नाबालिग "),
 # "14-year-old", "fourteen year old", "14 and 16-year-old", "14-yr-old"
 (re.compile(r"\b(" + _ENW + r"(?:\s*(?:,|and|&)\s*" + _ENW + r")*)[\s-]*(?:year|yr)s?[\s-]*old\b", re.I),
  lambda m: "minor" if any(_v(n) < 18 for n in re.findall(_ENW, m.group(1), re.I)) else m.group(0)),
 (re.compile(r"\b" + _ENW + r"[\s-]*months?[\s-]*old\b", re.I), lambda m: "minor"),
 (re.compile(r"\baged\s+(\d{1,2})\b", re.I), lambda m: "a minor" if int(m.group(1)) < 18 else m.group(0)),
 (re.compile(r"\(\s*(\d{1,2})\s*\)"), lambda m: "(minor)" if int(m.group(1)) < 18 else m.group(0)),
]
INST_EN = re.compile(r"\b(?:[A-Z][\w.'&-]*\s){1,4}(?:Public School|School|College|Vidyalaya|Vidya Mandir|Academy|Convent|Coaching|Pvt\.? Ltd)\b")
INST_GENERIC = set("A An The At In Of Her His Their Govt Government Private Medical Engineering Law Degree Inter Local Village Coaching Night Day Boarding High Primary Senior Junior Middle".split())
def is_title(t):
    w = [x for x in re.findall(r"[A-Za-z][A-Za-z']+", t or "") if len(x) > 3]
    return len(w) >= 4 and sum(x[0].isupper() for x in w) / len(w) > 0.6
def _inst(m):
    first = m.group(0).split()[0]
    return m.group(0) if first in INST_GENERIC else "[institution removed]"

def redact_ages(t):
    for rx, fn in AGE_SUBS: t = rx.sub(fn, t)
    t = re.sub(r"(नाबालिग)(\s+नाबालिग)+", r"\1", t)
    t = re.sub(r"(^|[.:|;!?]\s*)minor\b", lambda m: m.group(1) + "Minor", t)
    return t

# Names of victims that appeared in collected items and must never be displayed (manual review list).
NAME_BLOCKLIST = [r"Sowjanya", r"Nimisha\s+Thakuria"]

VICTIM_NOUN_HI = r"(नवविवाहिता|विवाहिता|विवाहित|युवती|छात्रा|किशोरी|पीड़िता|मृतका|बच्ची|बालिका|पिता|माता|मां|पति|भाई|बहन|बेटी|पुत्री|ससुर|सास|चाचा)"
HI_NOT_NAME = set("न्यायालय अदालत कोर्ट पुलिस साक्ष्य सबूत जेल थाने थाना गांव शहर बयान मौके इलाज अस्पताल बेटी बेटे बच्चों ससुराल मायके दोनों तीनों सभी लोगों पक्ष आरोपी दोषी युवक युवती महिला नाबालिग बच्ची किशोरी छात्रा लड़की सास ससुर देवर ननद जेठ से के की का को ने पर में और ही भी थी था है हुई हुआ गई गया अपहरण हत्या मौत शव दुष्कर्म छेड़छाड़ छेड़खानी रेप गैंगरेप सुसाइड आत्महत्या उत्पीड़न हमला मामले मामला केस परिजनों परिवार साथ पति प्रेमी लापता घर कॉलेज स्कूल दहेज सामूहिक तेजाब एसिड शिकायत".split())
def redact_names(t, title=False):
    def hi(m):
        w = m.group(2)
        return m.group(1) + " " + ("" if w in HI_NOT_NAME else "[नाम हटाया]") + ("" if w not in HI_NOT_NAME else w)
    t = re.sub(VICTIM_NOUN_HI + r"\s+([\u0900-\u097F]{2,})(?=\s+(की|के|का|को|ने|पर|से)(\s|$))", hi, t)
    if not title: t = re.sub(r"\b((?i:victim|survivor|Justice for|woman|girl|student|wife|bride|teen|minor|daughter))\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)(?=\W|$)",
               lambda m: m.group(1) + " " + ("[name removed]" if m.group(2).split()[0] not in EN_OK else m.group(2)), t)
    t = re.sub(r"\b(Justice for)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", r"\1 [name removed]", t)
    return t
EN_OK = set("Girl Girls Woman Women Boy Man Men Teen Teenager Minor Wife Husband Bride Student Students Daughter Mother Sister Father Brother Victim Survivor Family Rape Raped Gangraped Sexually Sexual Assault Harassment Molestation Murder Body Burnt Burns Set Shot Stabbed Beaten Thrashed Dies Missing Rescued Sold Forced Lured Trafficked Pregnant Minors Neighbour Relative Cousin Friend Lover Boyfriend Tutor Priest Driver Youth Accused Man's Two Three Four Five Six Seven Eight Nine Ten After Before For With By As To Into Over Near Inside Outside Under Behind During Was Were Has Had Gets Got Being Allegedly Assaulted Tortured Abused Groped Chased Followed Threatened Blackmailed Filmed Drugged Abducted Kidnapped Attacked Stalked Murdered Killed Held Arrested Booked Case FIR Police Cops Court Delhi Mumbai In From Of At On And Who Was Is Found Dies Died Allegedly Raped Gang Molested Harassed Kidnapped Abducted Attacked Assaulted Stalked Murdered Killed Held Arrested Case Engineer Doctor Nurse Student Teacher Biker Police Cops Delhi Mumbai".split())

def redact(t, minor=None):
    """Remove victim names and identifying details. Adult ages are kept; ages of minors become "minor"/"नाबालिग"."""
    t = html.unescape(t or "")
    t = re.sub(r"\[age removed\]|\[उम्र हटाई\]", "", t)  # legacy markers (only if the original text is unavailable)
    title = is_title(t)  # Title-Case headlines: capitalisation is no evidence of a name, so name heuristics are skipped
    t = redact_names(t, title)
    for rx, rep in ID_PATTERNS:
        if rx == "INST_EN":
            if not title: t = INST_EN.sub(_inst, t)
            continue
        if title and rep is not None and not isinstance(rep, str): continue  # relative-name rule
        t = rx.sub(rep, t)
    # "Name (16)" / "Name, 16," style: a capitalised word directly followed by an age is a person's name
    if not title:
        t = re.sub(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)(?=\s*(?:\(\s*\d{1,2}\s*\)|,\s*\d{1,2}\s*,))",
                   lambda m: m.group(1) if m.group(1).split()[0] in EN_OK else "[name removed]", t)
    t = redact_ages(t)
    t = re.sub(r"\b(minor)(\s+minor)+\b", r"\1", t, flags=re.I)
    for n in NAME_BLOCKLIST: t = re.sub(n, "[name removed]", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()

def classify(text):
    for tid, _, rx in TYPES:
        if re.search(rx, text, re.I):
            if tid in ("kidnap", "stalking", "harassment", "acid") and not WOMAN_RE.search(text):
                continue
            return tid
    return None

def status_of(text):
    for label, rx in STATUS:
        if re.search(rx, text, re.I): return label
    return "Not stated in source"

# ---------------------------------------------------------------- fetch
def http(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r: return r.read()

def fetch_rss():
    day = os.path.join(DATA, "raw_news", TODAY); os.makedirs(day, exist_ok=True)
    stamp = NOW.astimezone(IST).strftime("%H%M%S")
    for lang, qs in (("en", EN_Q), ("hi", HI_Q)):
        for q in qs:
            fn = os.path.join(day, f"{lang}_{hashlib.md5(q.encode()).hexdigest()[:8]}_{stamp}.xml")
            params = {"q": q + " when:30d", "hl": "en-IN" if lang == "en" else "hi", "gl": "IN",
                      "ceid": "IN:en" if lang == "en" else "IN:hi"}
            url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
            try:
                b = http(url); open(fn, "wb").write(b); print("rss", lang, q, len(b))
            except Exception as e: print("rss fail", q, e)
            time.sleep(1)

def read_rss():
    items = []
    for fn in sorted(glob.glob(os.path.join(DATA, "raw_news", "**", "*.xml"), recursive=True)):
        try: root = ET.parse(fn).getroot()
        except Exception: continue
        for it in root.iter("item"):
            title = it.findtext("title") or ""; src = it.find("source")
            srcname = src.text if src is not None else ""
            if srcname and title.endswith(" - " + srcname): title = title[: -len(srcname) - 3]
            try: dt = parsedate_to_datetime(it.findtext("pubDate"))
            except Exception: continue
            items.append({"kind": "news", "title": title.strip(), "link": it.findtext("link"),
                          "source": srcname, "source_url": src.get("url") if src is not None else "",
                          "date": dt.astimezone(timezone.utc), "text": title})
    return items

# ---------------------------------------------------------------- resolve Google News links to publisher article URLs
RES_FN = os.path.join(DATA, "url_resolve_cache.json")
rescache = json.load(open(RES_FN)) if os.path.exists(RES_FN) else {}
BUA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
RES_STATE = {"n": 0, "blocked": False}
RES_MAX_PER_RUN = 120  # Google rate-limits (HTTP 429); unresolved links are retried on later runs
def resolve_gnews(u):
    """Return the publisher URL behind a news.google.com/rss/articles/... link (cached), or None."""
    if "news.google.com" not in u: return u
    if u in rescache: return rescache[u]
    if RES_STATE["blocked"] or RES_STATE["n"] >= RES_MAX_PER_RUN: return None
    RES_STATE["n"] += 1
    out = None
    try:
        aid = u.split("/articles/")[1].split("?")[0]
        h = urllib.request.urlopen(urllib.request.Request(f"https://news.google.com/articles/{aid}", headers=BUA), timeout=20).read().decode("utf-8", "ignore")
        sg = re.search(r'data-n-a-sg="([^"]+)"', h); ts = re.search(r'data-n-a-ts="([^"]+)"', h)
        if sg and ts:
            req = ["Fbv4je", f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{aid}",{ts.group(1)},"{sg.group(1)}"]']
            body = "f.req=" + urllib.parse.quote(json.dumps([[req]]))
            r = urllib.request.urlopen(urllib.request.Request("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=body.encode(),
                    headers={**BUA, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}), timeout=20).read().decode("utf-8", "ignore")
            m = re.search(r'garturlres\\",\\"(https?://[^"\\]+)', r)
            if m: out = m.group(1)
    except Exception as ex:
        print("resolve fail", ex)
        if "429" in str(ex): RES_STATE["blocked"] = True; print("rate-limited by Google; remaining links resolved on a later run")
        return None  # not cached: retry next run
    rescache[u] = out; json.dump(rescache, open(RES_FN, "w"), indent=0)
    time.sleep(1.5)
    return out

# ---------------------------------------------------------------- article text -> incident date + place candidates
# Article text is used in memory only. data/article_cache.json keeps per article URL only: extracted place-name
# candidates ("c"), the extracted incident date ("d": [date, phrase, kind]) and whether the fetch worked ("ok").
import locate as LOC
ART_FN = os.path.join(DATA, "article_cache.json")
artcache = json.load(open(ART_FN, encoding="utf-8")) if os.path.exists(ART_FN) else {}
ART_STATE = {"n": 0}
ART_MAX_PER_RUN = int(os.environ.get("ART_MAX_PER_RUN", "150"))
def save_art(): json.dump(artcache, open(ART_FN, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
def get_article(url, pub, gaz=None, bad=()):
    c = artcache.get(url)
    if c and not (c.get("ok") and c.get("g") is None and gaz):  # re-fetch only to run a now-available gazetteer scan
        return c
    if ART_STATE["n"] >= ART_MAX_PER_RUN or not url.startswith("http"): return c
    ART_STATE["n"] += 1
    try:
        body = LOC.fetch_article(url); ok = len(body) > 200
    except Exception as ex:
        print("article fetch fail", url[:80], str(ex)[:60]); body, ok = "", False
    d = extract_incident_date(body[:1500], pub, mode="article") if body else None
    # only place names that also exist in the district's OSM gazetteer are kept from the scan (never other words)
    artcache[url] = {"ok": ok, "c": LOC.place_candidates(body), "d": list(d) if d else None,
                     "g": gaz_scan(gaz, body, bad) if (ok and gaz) else None}
    if ART_STATE["n"] % 10 == 0: save_art()
    time.sleep(0.8)
    return artcache[url]
def article_date(url, pub, court=False):
    c = get_article(url, pub)
    if not c or not c.get("d"): return None
    d = c["d"]
    if court and d[2] in ("wd", "hwd", "y", "t"): return None
    return tuple(d)

# ---------------------------------------------------------------- geocode
CACHE_FN = os.path.join(DATA, "geocode_cache.json")
cache = json.load(open(CACHE_FN)) if os.path.exists(CACHE_FN) else {}
_last = [0.0]
def nominatim(q):
    if q in cache: return cache[q]
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    _last[0] = time.time()
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "in"})
    try: r = json.loads(http(url, {"Accept-Language": "en"}))
    except Exception as e: print("geocode fail", q, e); return None
    res = {"lat": float(r[0]["lat"]), "lon": float(r[0]["lon"]), "type": r[0].get("addresstype") or r[0].get("type"),
           "display": r[0]["display_name"]} if r else None
    cache[q] = res; json.dump(cache, open(CACHE_FN, "w"), ensure_ascii=False, indent=0)
    return res

def km(a, b):
    R = 6371; p1, p2 = math.radians(a[0]), math.radians(b[0]); dl = math.radians(b[1] - a[1]); dp = p2 - p1
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(h))

HI_STOP = set("जिला जनपद नगर की के का ने से में यूपी पुलिस थाना थाने उत्तर प्रदेश स्थानीय राज्य अधीक्षक महिला क्षेत्र सदर कोतवाली मामले आरोपी युवती "
              "नाबालिग त्वरित बड़ी कार्रवाई द्वारा टीम ग्रामीण देहात शहर जिले इस उस एक और भी को है था थी गांव कस्बा".split())
EN_STOP = set("police station area district city village town the a an case accused woman girl minor man men".split())
def area_candidates(text):
    c = []
    for m in re.finditer(r"(?:थाना|थाने)[_\s]+([\u0900-\u097F]{3,}(?:[_\s][\u0900-\u097F]{3,})?)", text): c.append(m.group(1).replace("_", " "))
    for m in re.finditer(r"([\u0900-\u097F]{3,})\s+(?:थाना|थाने|पुलिस|कोतवाली)", text): c.append(m.group(1))
    for m in re.finditer(r"#Ps([A-Z][a-z]+)", text): c.append(m.group(1))
    for m in re.finditer(r"(?:'s|’s)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", text): c.append(m.group(1))
    for m in re.finditer(r"\bin\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s*,\s*[A-Z]", text): c.append(m.group(1))
    out = []
    for x in c:
        w = x.strip()
        if not w or w in HI_STOP or w.lower() in EN_STOP or any(t in HI_STOP for t in w.split()): continue
        if w not in out: out.append(w)
    return out[:3]

# ---------------------------------------------------------------- precise location (pins only at locality or better)
DISTRICTS = None
KIND_LABEL = {"police": "Police station", "locality": "Locality", "village": "Village", "street": "Street/landmark"}
GAZ_SCAN_TYPES = {"suburb", "neighbourhood", "quarter", "village", "residential", "police", "locality"}
def gaz_scan(rows, text, bad):
    """Names from the district's OSM gazetteer that literally occur in the article/headline (fallback)."""
    if not rows or not text: return []
    # a name counts only in a place context: "in/at/near/from X" (English) or "X में/के/स्थित/निवासी/इलाके/गांव/थाना" (Hindi)
    ws = set(m.group(1) for m in re.finditer(r"\b(?:in|at|near|from|of)\s+([A-Z][a-z]{3,}(?:\s[A-Z][a-z]{3,}){0,2})", text))
    ws |= set(m.group(1) for m in re.finditer(r"([\u0900-\u097F]{3,}(?:\s[\u0900-\u097F]{3,})?)\s+(?:में|के|की|स्थित|निवासी|इलाके|इलाका|गांव|गाँव|थाना|थाने|क्षेत्र|मोहल्ले|मोहल्ला)", text))
    for w in list(ws):
        if " " in w: ws.update(w.split())
    lower = set(re.findall(r"\b[a-z]{4,}\b", text))  # words also used in lower case are ordinary words, not names
    hits = []
    for nm, hi, en, lat, lon, typ in rows:
        if typ not in GAZ_SCAN_TYPES: continue
        for n in (nm, hi, en):
            if not n: continue
            base = re.sub(r"\s*(Police Station|Police Chowki|Police Post|Thana|पुलिस स्टेशन|थाना|कोतवाली)\s*", " ", n).strip() if typ == "police" else n
            if len(base) < 5 or base.lower() in bad or base in LOC.STOP_HI or base.lower() in LOC.STOP_EN: continue
            if base in ws and base.lower() not in lower:
                hits.append((base, "police" if typ == "police" else ("village" if typ in ("village", "hamlet") else "locality"))); break
    return list(dict.fromkeys(hits))[:8]

def refine_location(e, rec_by_url):
    global DISTRICTS
    if DISTRICTS is None: DISTRICTS = LOC.Districts()
    if e.get("city_lat") is None:
        if e.get("precision", "").startswith("City"): e["city_lat"], e["city_lon"] = e["lat"], e["lon"]
        else:
            c = nominatim(f"{e['city']}, {e['state']}, India") or {"lat": e["lat"], "lon": e["lon"]}
            e["city_lat"], e["city_lon"] = c["lat"], c["lon"]
    if e.get("loc_v") == 2 and e.get("pin_level") != "city": return  # already precise
    clat, clon = e["city_lat"], e["city_lon"]
    dist, bb = DISTRICTS.find(clat, clon)
    dname = dist["properties"].get("d", "") if dist else ""
    if e.get("pin_level") in (None, "city") and not e.get("city_reported"): e["city_reported"] = e.get("place_reported") or e["city"]
    bad = {x.lower() for x in (e["city"], dname, e["state"], e["place"].split(",")[0], e.get("city_reported")) if x}
    gaz = LOC.osm_gazetteer(f"{dname}_{dist['properties'].get('s','')}", bb) if dist else None
    found = None
    srcs = sorted(e["sources"], key=lambda z: z["date"])
    texts = []  # (outlet, where, candidates, words, raw_text)
    for sx in srcs:
        r_ = rec_by_url.get(sx["url"]); head = (r_ or {}).get("title") or e.get("headline") or ""
        texts.append((sx["name"], "headline", LOC.place_candidates(head), [], head))
    for sx in srcs:
        if sx.get("article_url"):
            c = get_article(sx["article_url"], _date.fromisoformat(sx["date"]), gaz, bad)
            if c and c.get("ok"): texts.append((sx["name"], "article text", [(LOC._clean(x[0]), x[1]) for x in c.get("c", []) if len(LOC._clean(x[0])) >= 3], [tuple(x) for x in (c.get("g") or [])], ""))
    tried = set()
    for outlet, where, cands, words, raw in texts:
        cands = [c for c in cands if c[0].lower() not in bad and c not in tried]; tried.update(cands)
        found = LOC.locate(cands, dist, bb, (clat, clon), gaz, cache, sorted(bad)) if cands else None
        if found: found["outlet"], found["where"] = outlet, where; break
    if not found:
        for outlet, where, cands, words, raw in texts:
            sc = words if where == "article text" else gaz_scan(gaz, raw, bad)
            found = LOC.locate(sc, dist, bb, (clat, clon), gaz, cache, sorted(bad)) if sc else None
            if found:
                found["outlet"], found["where"] = outlet, where; found["method"] = "name found in " + where + " and " + found["method"]; break
    json.dump(cache, open(CACHE_FN, "w"), ensure_ascii=False, indent=0)
    e["loc_v"] = 2
    if found:
        lvl = found["level"]
        e.update(lat=round(found["lat"], 5), lon=round(found["lon"], 5), pin_level=lvl, precision=LOC.LEVEL[lvl],
                 place=f"{found['name']}, {e['city']}", place_reported=found["name"], place_reported_by=found["outlet"],
                 place_reported_in=found["where"],
                 geocode=f"{KIND_LABEL.get(found['kind'], 'Place')} “{found['name']}” as stated in the {found['outlet']} {found['where']}; {found['method']}; map pin {LOC.LEVEL[lvl].split('(')[1].rstrip(')')}")
    elif e.get("precision", "").startswith("Locality"):
        e["pin_level"] = "locality"  # earlier locality match from the headline (kept)
    else:
        e.update(lat=clat, lon=clon, pin_level="city", precision=LOC.LEVEL["city"], place=f"{e['city']}, {e['state']}" if e["city"] != e["state"] else e["city"],
                 geocode=f"Only the city/district “{e.get('place_reported') or e['city']}” is named in the {'headline and article text' if any(t[1] == 'article text' for t in texts) else 'headline (article text not available)'}; no locality, police station or village could be matched inside the district, so this report is listed under “Location not specific” and not pinned")

# ---------------------------------------------------------------- build
def main():
    if FETCH: fetch_rss()
    gz = Gazetteer(os.path.join(DATA, "ncrb_raw.geojson"))
    raw = read_rss()
    print("raw items", len(raw))
    cut = NOW - timedelta(days=MAX_AGE_DAYS)
    recs, skipped = [], {"old": 0, "type": 0, "place": 0, "excluded": 0, "geocode": 0}
    seen_links = set()
    for it in raw:
        if it["link"] in seen_links: continue
        seen_links.add(it["link"])
        if it["date"] < cut: skipped["old"] += 1; continue
        text = it["text"]
        if EXCLUDE_RE.search(it.get("title") or text): skipped["excluded"] += 1; continue
        t = classify(it["title"] if it["kind"] == "x_story" else text)
        if not t: skipped["type"] += 1; continue
        places = gz.find(text)
        if not places: skipped["place"] += 1; continue
        disp, state, matched, _ = places[0]
        gq = f"{disp}, {state}, India"
        city = nominatim(gq)
        if not city: gq = f"{disp}, India"; city = nominatim(gq)
        if not city: skipped["geocode"] += 1; continue
        lat, lon, precision, place = city["lat"], city["lon"], "City/district level (approx., ±10–30 km)", f"{disp}, {state}"
        reported = matched; geo = f"City/district name \u201c{matched}\u201d matched; geocoded with OpenStreetMap Nominatim query \u201c{gq}\u201d \u2192 {city['display'].split(',')[0]} ({city.get('type')}); pin approx \u00b110\u201330 km"
        for a in area_candidates(text):
            g = nominatim(f"{a}, {disp}, {state}, India")
            if g and km((g["lat"], g["lon"]), (city["lat"], city["lon"])) < 40 and g["type"] not in ("state", "country", "state_district"):
                eng = g["display"].split(",")[0]
                if eng.lower() == disp.lower() or km((g["lat"], g["lon"]), (city["lat"], city["lon"])) < 1.5: continue
                lat, lon, place = g["lat"], g["lon"], f"{eng}, {disp}, {state}"
                precision = "Locality / police-station area (approx., ±2–5 km)"
                reported = f"{a} \u2026 {matched}" if a != matched else a
                geo = f"Locality/police-station name \u201c{a}\u201d with city \u201c{matched}\u201d; geocoded with OpenStreetMap Nominatim query \u201c{a}, {disp}, {state}, India\u201d \u2192 {eng} ({g.get('type')}), accepted because within 40 km of {disp}; pin approx \u00b12\u20135 km"
                break
        recs.append({**it, "type": t, "place": place, "city": disp, "state": state, "lat": round(lat, 4), "lon": round(lon, 4),
                     "precision": precision, "status": status_of(text), "minor": is_minor(text),
                     "place_reported": reported, "geocode": geo,
                     "reported_in": {"news": "headline", "x_post": "X post text", "x_story": "X news story title/summary"}[it["kind"]]})
    print("kept", len(recs), "skipped", skipped)

    METROS = {"Delhi","New Delhi","Mumbai","Bengaluru","Kolkata","Chennai","Hyderabad","Pune","Ahmedabad","Lucknow","Jaipur","Patna","Kanpur","Ghaziabad","Noida","Gurugram","Indore","Bhopal","Thane","Surat","Nagpur"}
    def toks(s): return set(w for w in re.findall(r"\w+", (s or "").lower()) if len(w) > 3)
    def same_group(g, r, tk):
        sim = len(tk & g["_tok"]) / max(1, len(tk | g["_tok"]))
        return g["type"] == r["type"] and g["city"] == r["city"] and abs((r["date"] - g["_last"]).total_seconds()) <= 2.5*86400 \
            and g["_kind"] == ("news" if r["kind"] == "news" else "social") and sim >= 0.2  # wording must overlap (prevents merging different incidents in one city)
    # 0) takedown / correction requests (data/takedowns.json, maintained by hand; see README "Corrections & takedowns").
    #    Format: {"incidents": {"inc0123": "short generic reason"}, "urls": {"https://...": "reason"}}
    #    Removed incidents keep only their id (append-only numbering) and SHA-1 hashes of their source URLs, so the same
    #    articles are never re-added by a later run. Their text, place and links are stripped from every published file.
    TK = os.path.join(DATA, "takedowns.json")
    takedowns = json.load(open(TK, encoding="utf-8")) if os.path.exists(TK) else {}
    td_ids = dict(takedowns.get("incidents") or {}); td_urls = dict(takedowns.get("urls") or {})
    h1 = lambda u: "sha1:" + hashlib.sha1(u.encode("utf-8")).hexdigest()
    blocked = {h1(u) for u in td_urls}
    _JF = os.path.join(DATA, "incidents.json")
    if os.path.exists(_JF):
        for e0 in json.load(open(_JF)).get("incidents", []):
            urls0 = e0.get("all_urls") or [x["url"] for x in e0.get("sources", [])]
            if e0["id"] in td_ids or any(u in td_urls for u in urls0) or e0.get("removed"):
                blocked |= {u if u.startswith("sha1:") else h1(u) for u in urls0}
    nb = len(recs); recs = [r for r in recs if h1(r["link"]) not in blocked]
    if nb != len(recs): print("takedown filter dropped", nb - len(recs), "raw records")

    # 1) group this batch (all raw records) exactly like before
    recs.sort(key=lambda r: (r["date"], r["link"]))
    groups = []
    for r in recs:
        tk = toks(r.get("title") or r.get("head_text"))
        for g in groups:
            if same_group(g, r, tk): g["_recs"].append(r); g["_tok"] |= tk; g["_last"] = r["date"]; break
        else:
            groups.append({"type": r["type"], "city": r["city"], "_kind": "news" if r["kind"] == "news" else "social",
                           "_tok": tk, "_last": r["date"], "_recs": [r]})

    # 2) load existing (append-only base)
    JF = os.path.join(DATA, "incidents.json")
    old = json.load(open(JF)) if os.path.exists(JF) else {"incidents": []}
    existing = old["incidents"]
    n_social = sum(1 for e in existing if e.get("channel") == "social")
    if n_social:  # X/social media removed: drop X-only incidents from published data (local backups keep them)
        os.makedirs(os.path.join(DATA, "backups"), exist_ok=True)
        bk = os.path.join(DATA, "backups", f"incidents_with_x_{NOW.astimezone(IST).strftime('%Y%m%d_%H%M%S')}.json")
        json.dump(old, open(bk, "w"), ensure_ascii=False, indent=1)
        existing = [e for e in existing if e.get("channel") != "social"]
        print("removed", n_social, "social-media (X) incidents from published data; backup:", bk)
    before = len(existing)
    for e in existing:  # migrate older records
        e.setdefault("city", e["place"].split(", ")[-2] if e["place"].count(", ") >= 1 else e["place"])
        e.setdefault("first_seen", (old.get("generated") or old.get("last_updated") or NOW.isoformat())[:10])
        e.setdefault("last_updated", e["first_seen"])
        e.setdefault("report_date", e["date"])
        e.setdefault("minor", "involving a minor" in e["summary"])
        e.setdefault("police_src", "official police account" in e["verification"])
        e.setdefault("newslink_src", "links to / summarises" in e["verification"])
        e.setdefault("all_urls", [x["url"] for x in e["sources"]])
    url2inc = {}
    for e in existing:
        for u in e["all_urls"]: url2inc[u] = e
    next_id = max([int(e["id"][3:]) for e in existing] + [0]) + 1
    order = [st[0] for st in STATUS] + ["Not stated in source"]

    def finalize(e):
        social = e["channel"] == "social"
        if social:
            if e["police_src"]: ver = "Social media – posted by an official police account (not independently verified)"
            elif e["newslink_src"]: ver = "Social media – unverified (post links to / summarises news reports)"
            else: ver = "Social media – unverified"
        else:
            outlets = sorted(set(x["name"] for x in e["sources"]))
            ver = f"News report – {len(outlets)} outlet{'s' if len(outlets) > 1 else ''}" + (" (multiple reports)" if len(outlets) > 1 else " (single source)")
        n = len(e["all_urls"])
        if n > 1: ver += f"; {n} reports from the same city/type within ~2 days were auto-grouped (likely the same incident)"
        e["verification"] = ver
        srcdesc = "News media" if not social else ("A police social-media account" if e["police_src"] else "Social-media posts")
        who = "a minor" if e["minor"] else "a woman"
        e["summary"] = f"{srcdesc} reported an alleged {TYPE_LABEL[e['type']].lower()} incident involving {who} in the {e['place']} area. Status in reports: {e['status']}."

    KIND = {"news": "article", "x_post": "x_post", "x_story": "x_story"}
    def src_of(x): return {"name": x["source"], "url": x["link"], "date": x["date"].astimezone(IST).strftime("%Y-%m-%d"),
                           "kind": KIND[x["kind"]], "outlet_url": x.get("source_url") or ""}
    def set_place_info(e, x):
        e["place_reported"] = x["place_reported"]; e["place_reported_by"] = x["source"]
        e["place_reported_in"] = x["reported_in"]; e["geocode"] = x["geocode"]
    def add_recs(e, rs):
        for x in rs:
            if x["link"] in e["all_urls"]: continue
            e["all_urls"].append(x["link"]); e["sources"].append(src_of(x)); url2inc[x["link"]] = e
            e["status"] = min([e["status"], x["status"]], key=order.index)
            e["minor"] = e["minor"] or x["minor"]
            e["police_src"] = e["police_src"] or bool(x.get("police"))
            e["newslink_src"] = e["newslink_src"] or bool(x.get("news_link") or x["kind"] == "x_story")
            if "Locality" in x["precision"] and "Locality" not in e["precision"]:
                e.update(place=x["place"], lat=x["lat"], lon=x["lon"], precision=x["precision"]); set_place_info(e, x)
            if not e.get("place_reported"): set_place_info(e, x)
            if not e.get("headline") and x["kind"] in ("news", "x_story"): e["headline"] = redact(x["title"], x["minor"] or e["minor"])
        e["last_updated"] = TODAY; finalize(e)

    added_inc, added_src = 0, 0
    cut = NOW - timedelta(days=MAX_AGE_DAYS)
    for g in groups:
        rs = g["_recs"]
        new_rs = [x for x in rs if x["link"] not in url2inc]
        if not new_rs: continue
        hit = next((url2inc[x["link"]] for x in rs if x["link"] in url2inc), None)
        if hit is None:  # attach to an existing incident by grouping rule
            for e in existing:
                if e.get("removed") or e["type"] != g["type"] or e["city"] != g["city"] or e["channel"] != g["_kind"]: continue
                last = max(datetime.fromisoformat(s_["date"]).replace(tzinfo=IST) for s_ in e["sources"])
                tk = toks(e.get("headline")) | g["_tok"] if g["_kind"] == "news" else set()
                pseudo = {"type": e["type"], "city": e["city"], "_kind": e["channel"], "_tok": toks(e.get("headline")), "_last": last}
                if same_group(pseudo, new_rs[0], g["_tok"]): hit = e; break
        if hit is not None:
            added_src += len(new_rs); add_recs(hit, new_rs); continue
        if all(x["date"] < cut for x in new_rs): continue  # brand-new but stale
        first = new_rs[0]
        e = {"id": f"inc{next_id:04d}", "type": g["type"], "type_label": TYPE_LABEL[g["type"]], "channel": g["_kind"],
             "date": first["date"].astimezone(IST).strftime("%Y-%m-%d"), "place": first["place"], "state": first["state"],
             "city": first["city"], "lat": first["lat"], "lon": first["lon"], "precision": first["precision"],
             "headline": redact(first["title"], first["minor"]) if first["kind"] in ("news", "x_story") else None, "summary": "",
             "status": "Not stated in source", "verification": "", "sources": [], "all_urls": [],
             "first_seen": TODAY, "minor": False, "police_src": False, "newslink_src": False}
        e["report_date"] = e["date"]
        next_id += 1; existing.append(e); added_inc += 1; added_src += len(new_rs); add_recs(e, new_rs)

    # backfill credibility fields on older incidents from archived raw records (deterministic)
    rec_by_url = {r["link"]: r for r in recs}
    if RESOLVE:  # batched Google News decoding (see gnews_resolve.py), capped per run; the rest on later runs
        from gnews_resolve import resolve_many
        pend = [sx["url"] for e in existing if not e.get("removed") for sx in e["sources"] if "news.google.com" in sx["url"] and not sx.get("article_url")]
        resolve_many(pend, rescache, max_n=int(os.environ.get("RESOLVE_MAX_PER_RUN", "250")),
                     save=lambda: json.dump(rescache, open(RES_FN, "w"), indent=0))
        json.dump(rescache, open(RES_FN, "w"), indent=0)
    enriched = 0
    for e in existing:
        before_e = json.dumps(e, sort_keys=True, ensure_ascii=False)
        for sx in e["sources"]:
            r = rec_by_url.get(sx["url"])
            if "kind" not in sx:
                sx["kind"] = KIND[r["kind"]] if r else ("x_story" if "/i/trending/" in sx["url"] else "x_post" if "x.com/" in sx["url"] else "article")
            if "outlet_url" not in sx: sx["outlet_url"] = (r.get("source_url") or "") if r else ""
            if "article_url" not in sx and sx["kind"] == "article":
                au = rescache.get(sx["url"]) if "news.google.com" in sx["url"] else sx["url"]
                if au: sx["article_url"] = au
        if not e.get("place_reported") and not e.get("removed"):
            rs = [rec_by_url[u] for u in e["all_urls"] if u in rec_by_url]
            pick = next((r for r in rs if r["place"] == e["place"]), rs[0] if rs else None)
            if pick: set_place_info(e, pick)
            else: e.update(place_reported=e["place"], place_reported_by="(raw record unavailable)", place_reported_in="", geocode="Place from earlier build; raw record unavailable")
        if not e.get("removed"):
            rs_e = [rec_by_url[u] for u in e.get("all_urls", []) if u in rec_by_url]
            e["minor"] = bool(e.get("minor") or any(r_["minor"] for r_ in rs_e))
            src_head = next((r_ for r_ in rs_e if r_["kind"] in ("news", "x_story")), None)
            if src_head: e["headline"] = redact(src_head["title"], e["minor"])  # rebuilt from the original text (ages kept)
            elif e.get("headline"): e["headline"] = redact(e["headline"], e["minor"])
            finalize(e)
            if e.get("incident_date_basis") != "stated in report":
                res = None
                for sx in sorted(e["sources"], key=lambda z: z["date"]):
                    pub = _date.fromisoformat(sx["date"]); r_ = rec_by_url.get(sx["url"])
                    head = (r_ or {}).get("title") or e.get("headline") or ""
                    court = bool(COURT_RE.search(head))
                    res = extract_incident_date(head, pub, court=court)
                    if not res and sx.get("article_url"): res = article_date(sx["article_url"], pub, court)
                    if res and res[0] > e["date"]: res = None  # cannot be after the first report
                    if res: break
                if res: e.update(incident_date=res[0], incident_date_basis="stated in report", incident_date_text=res[1])
                else: e.update(incident_date=e["date"], incident_date_basis="approx = report date", incident_date_text="")
        if not e.get("removed"): refine_location(e, rec_by_url)
        ok = [sx for sx in e["sources"] if sx["url"].startswith("http") and sx["kind"] in ("article", "x_post")]
        e["verifiable"] = bool(ok)
        e["hidden_reason"] = None if ok else "No verifiable source link (only an aggregated X news-story summary)"
        if e.get("headline") and DEBUNK_RE.search(e["headline"]):
            e["verifiable"] = False; e["hidden_reason"] = "Report says the claim was debunked/false"
        urls_e = e.get("all_urls") or []
        if e["id"] in td_ids or any(u in td_urls for u in urls_e) or e.get("removed"):
            reason = td_ids.get(e["id"]) or next((td_urls[u] for u in urls_e if u in td_urls), None) or e.get("hidden_reason") or "Removed after a correction/takedown request"
            e.update(removed=True, verifiable=False, hidden_reason=reason, headline=None, sources=[],
                     summary="Removed after a correction/takedown request.", place_reported="", place_reported_by="",
                     place_reported_in="", geocode="", place="(removed)", city="(removed)", lat=None, lon=None,
                     all_urls=[u if u.startswith("sha1:") else h1(u) for u in urls_e])
        if json.dumps(e, sort_keys=True, ensure_ascii=False) != before_e: enriched += 1
    print("enriched/updated metadata on", enriched, "incidents; not verifiable (hidden):", sum(not e["verifiable"] for e in existing))
    save_art()
    changed = added_src > 0 or enriched > 0 or n_social > 0 or old.get("schema") != 7
    print(f"before {before} incidents; added {added_inc} new incidents, {added_src} new source links; total {len(existing)}")
    if not changed:
        print("RESULT: NOCHANGE"); return
    if os.path.exists(JF):
        os.makedirs(os.path.join(DATA, "backups"), exist_ok=True)
        import shutil; shutil.copy2(JF, os.path.join(DATA, "backups", f"incidents_{NOW.astimezone(IST).strftime('%Y%m%d_%H%M%S')}.json"))
    dates = sorted(e["date"] for e in existing)
    out = {"schema": 7, "last_updated": NOW.astimezone(IST).isoformat(timespec="seconds"),
           "first_collected": old.get("first_collected") or (old.get("generated") or NOW.isoformat())[:10],
           "date_span": [dates[0], dates[-1]] if dates else None, "count": len(existing),
           "incident_date_span": [min(x), max(x)] if (x := [e["incident_date"] for e in existing if e.get("incident_date")]) else None,
           "count_visible": sum(e["verifiable"] for e in existing), "incidents": existing}
    out["generated"] = out["last_updated"]  # backward-compat
    json.dump(out, open(JF, "w"), ensure_ascii=False, indent=1)
    with open(os.path.join(DATA, "incidents.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        class _W:  # neutralise spreadsheet formula injection in text cells (=, +, -, @ at start)
            def __init__(s_, f): s_.w = csv.writer(f)
            def writerow(s_, row): s_.w.writerow([("'" + c) if isinstance(c, str) and c[:1] in ("=", "+", "-", "@", "\t", "\r") else c for c in row])
        w = _W(fh); w.writerow(["id", "incident_date", "incident_date_basis", "report_date", "first_seen", "crime_type", "channel", "outlets", "article_urls", "publish_dates",
                                        "place_as_reported", "place_reported_by", "geocoding_method", "map_place", "state", "lat", "lon", "pin_level", "precision",
                                        "headline", "summary", "status", "verification"])
        for o in existing:
            if not o["verifiable"]: continue
            ss = [x for x in o["sources"] if x["kind"] in ("article", "x_post")]
            w.writerow([o["id"], o.get("incident_date", o["date"]), o.get("incident_date_basis", ""), o["date"], o["first_seen"], o["type_label"], o["channel"], " | ".join(x["name"] for x in ss), " | ".join(x.get("article_url") or x["url"] for x in ss),
                        " | ".join(x["date"] for x in ss), o["place_reported"], f'{o["place_reported_by"]} ({o["place_reported_in"]})', o["geocode"],
                        o["place"], o["state"], o["lat"], o["lon"], o.get("pin_level", ""), o["precision"], o["headline"] or "", o["summary"], o["status"], o["verification"]])
    from collections import Counter
    print("incidents", len(existing), Counter(o["channel"] for o in existing), Counter(o["type"] for o in existing))
    print("RESULT: CHANGED")

if __name__ == "__main__": main()
