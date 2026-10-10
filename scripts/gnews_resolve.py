#!/usr/bin/env python3
"""Decode news.google.com/rss/articles/... redirect links to the publisher article URL.
Method (same as the current `googlenewsdecoder` approach): GET the article page to read its signature
(data-n-a-sg) and timestamp (data-n-a-ts), then ask Google's batchexecute endpoint ("garturlreq") for the
real URL. Several links are decoded per batchexecute call, with exponential backoff on HTTP 429."""
import json, re, time, urllib.request, urllib.parse

BUA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

def _params(aid):
    for ep in (f"https://news.google.com/rss/articles/{aid}", f"https://news.google.com/articles/{aid}"):
        try:
            h = urllib.request.urlopen(urllib.request.Request(ep, headers=BUA), timeout=20).read().decode("utf-8", "ignore")
        except Exception as ex:
            print("gnews page fail", str(ex)[:60]); continue
        sg = re.search(r'data-n-a-sg="([^"]+)"', h); ts = re.search(r'data-n-a-ts="([^"]+)"', h)
        if sg and ts: return sg.group(1), ts.group(1)
    return None

def _batch(items):
    """items: [(aid, sg, ts)] -> {aid: url}"""
    reqs = [["Fbv4je", f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{a}",{t},"{s}"]', None, str(k + 1)]
            for k, (a, s, t) in enumerate(items)]
    body = "f.req=" + urllib.parse.quote(json.dumps([reqs]))
    r = urllib.request.urlopen(urllib.request.Request("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=body.encode(),
            headers={**BUA, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}), timeout=30).read().decode("utf-8", "ignore")
    out = {}
    for line in r.splitlines():
        if not line.startswith("[["): continue
        try: arr = json.loads(line)
        except Exception: continue
        for row in arr:
            if len(row) > 2 and row[0] == "wrb.fr" and row[2]:
                try:
                    inner = json.loads(row[2]); idx = int(row[-1]) - 1 if str(row[-1]).isdigit() else None
                    if inner[0] == "garturlres" and idx is not None: out[items[idx][0]] = inner[1]
                except Exception: pass
    return out

def resolve_many(urls, cache, max_n=200, batch=8, save=None, log=print):
    """Resolve up to max_n uncached Google News URLs; updates cache {url: publisher_url|None}."""
    todo = [u for u in dict.fromkeys(urls) if "news.google.com" in u and u not in cache][:max_n]
    if not todo: return 0
    done, delay = 0, 60
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]; items = []
        for u in chunk:
            aid = u.split("/articles/")[1].split("?")[0]
            p = _params(aid); time.sleep(0.7)
            if p: items.append((aid, p[0], p[1]))
        for attempt in range(4):
            try:
                res = _batch(items) if items else {}; break
            except Exception as ex:
                if "429" in str(ex) and attempt < 3:
                    log(f"gnews 429; backing off {delay}s"); time.sleep(delay); delay = min(delay * 2, 600); continue
                log("gnews batch fail", str(ex)[:80]); return done
        for u in chunk:
            aid = u.split("/articles/")[1].split("?")[0]
            if aid in res: cache[u] = res[aid]; done += 1
        if save: save()
        log(f"gnews resolved {done}/{len(todo)}")
        time.sleep(3)
    return done
