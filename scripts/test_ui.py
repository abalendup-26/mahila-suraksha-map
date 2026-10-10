#!/usr/bin/env python3
"""Playwright audit of the web app (desktop + mobile). Usage: test_ui.py [base_url] [screenshot_prefix]
Checks: console/page errors, consent banner, filters, time edge cases, geolocation denied, search no result,
zero-row export, mobile popup + bottom sheet, XSS escaping (injected malicious headline), clustered markers, legal pages."""
import asyncio, sys, json, time
from playwright.async_api import async_playwright
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765/").rstrip("/") + "/"
OUT = sys.argv[2] if len(sys.argv) > 2 else "screenshots/test"
results = []
def check(name, ok, info=""):
    results.append((name, bool(ok), info)); print(("PASS " if ok else "FAIL ") + name, info)

async def run(p, mobile):
    tag = "mobile" if mobile else "desktop"
    b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    opts = dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2) if mobile else dict(viewport={"width": 1440, "height": 900})
    ctx = await b.new_context(**opts)  # no geolocation permission => denied path
    pg = await ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
    # XSS probe: add one malicious incident to the app data
    async def inject(route):
        r = await route.fetch(); j = await r.json()
        j["incidents"].append({"id": "incXSS", "type": "rape", "type_label": "Rape / sexual assault", "channel": "news", "date": j["date_span"][1],
            "place": "Testpur\"><img src=x onerror=window.__xss=1>", "state": "X", "lat": 12.97, "lon": 77.59, "precision": "City", 
            "headline": "<img src=x onerror=window.__xss=1><script>window.__xss=2</script>", "summary": "<b onmouseover=alert(1)>s</b>",
            "status": "x", "verification": "x", "sources": [{"name": "<svg onload=window.__xss=3>", "date": "2026-01-01", "kind": "article", "article_url": "javascript:window.__xss=4"}]})
        await route.fulfill(response=r, body=json.dumps(j))
    await pg.route("**/data/incidents.app.json", inject)
    t0 = time.time()
    await pg.goto(BASE, wait_until="domcontentloaded")
    await pg.wait_for_function("window.__ready", timeout=90000)
    check(f"{tag}: data loaded", True, f"{time.time()-t0:.1f}s " + json.dumps(await pg.evaluate("window.__ready")))
    check(f"{tag}: consent banner shown on first visit", await pg.is_visible("#consent"))
    await pg.screenshot(path=f"{OUT}_{tag}_first_visit.png")
    await pg.click("#cok"); check(f"{tag}: consent dismissed+stored", not await pg.is_visible("#consent") and await pg.evaluate("localStorage.getItem('safenaksha_consent_v1')") == "1")
    total = await pg.evaluate("visible().length")
    # XSS
    await pg.evaluate("""()=>{const m=markerLayer.getLayers().find(m=>m.inc.id==='incXSS');markerLayer.zoomToShowLayer(m,()=>m.openPopup());}""")
    await pg.wait_for_timeout(1500)
    html = await pg.evaluate("document.querySelector('.leaflet-popup-content')?.innerHTML||''")
    check(f"{tag}: XSS headline escaped", "&lt;img" in html and "<img src=\"x\"" not in html and await pg.evaluate("window.__xss") is None)
    check(f"{tag}: javascript: link neutralised", "javascript:" not in html)
    await pg.evaluate("void map.closePopup()")
    # type filters
    await pg.evaluate("document.querySelectorAll('.tchk').forEach(c=>{c.checked=false});document.querySelector('.tchk').dispatchEvent(new Event('change'))")
    n0 = await pg.evaluate("markerLayer.getLayers().length")
    check(f"{tag}: all types off -> 0 markers + empty state", n0 == 0 and await pg.is_visible("#empty"), f"markers={n0}")
    check(f"{tag}: export buttons disabled at 0 rows", await pg.evaluate("$('dlcsv').disabled && $('dlpdf').disabled"))
    await pg.evaluate("$('dlcsv').disabled=false;$('dlcsv').click()"); await pg.wait_for_timeout(300)
    check(f"{tag}: zero-row export shows message", "Nothing to export" in (await pg.inner_text("#toast")))
    await pg.click("#resetF"); await pg.wait_for_timeout(300)
    check(f"{tag}: reset restores all", await pg.evaluate("visible().length") == total and not await pg.is_visible("#empty"))
    # channel filter
    await pg.evaluate("$('chSocial').checked=false;$('chSocial').dispatchEvent(new Event('change'))")
    check(f"{tag}: news-only filter", await pg.evaluate("visible().every(i=>i.channel==='news')") and await pg.evaluate("visible().length") < total)
    await pg.evaluate("$('chSocial').checked=true;$('chSocial').dispatchEvent(new Event('change'))")
    # time presets
    if mobile: await pg.evaluate("setSheet('full')"); await pg.wait_for_timeout(400)
    counts = {}
    for pz in ["today", "7", "30", "all"]:
        await pg.click(f"#tChips [data-p='{pz}']"); await pg.wait_for_timeout(200); counts[pz] = await pg.evaluate("visible().length")
    check(f"{tag}: time presets monotonic", counts["today"] <= counts["7"] <= counts["30"] <= counts["all"] == total, json.dumps(counts))
    lo, hi = await pg.evaluate("[incidents.map(i=>i.date).sort()[0], incidents.map(i=>i.date).sort().pop()]")
    await pg.click("#tChips [data-p='custom']")
    await pg.fill("#tFrom", hi); await pg.fill("#tTo", lo); await pg.dispatch_event("#tTo", "change")
    check(f"{tag}: custom reversed range swapped", await pg.evaluate("visible().length") == total, await pg.inner_text("#toast"))
    await pg.fill("#tFrom", "2020-01-01"); await pg.fill("#tTo", "2020-01-31"); await pg.dispatch_event("#tTo", "change")
    check(f"{tag}: custom empty range -> empty state", await pg.evaluate("visible().length") == 0 and await pg.is_visible("#empty"))
    await pg.fill("#tFrom", ""); await pg.fill("#tTo", ""); await pg.dispatch_event("#tTo", "change")
    check(f"{tag}: custom blank = all", await pg.evaluate("visible().length") == total)
    await pg.click("#tChips [data-p='all']")
    if mobile: await pg.evaluate("setSheet('peek')"); await pg.wait_for_timeout(400)
    # geolocation denied
    await pg.click("#loc"); await pg.wait_for_timeout(1500)
    check(f"{tag}: geolocation denied handled", "denied" in (await pg.inner_text("#toast")).lower() or "not available" in (await pg.inner_text("#toast")).lower(), await pg.inner_text("#toast"))
    # search no results / results
    await pg.fill("#q", "qwxzvbnmplk zzqq"); await pg.press("#q", "Enter"); await pg.wait_for_timeout(4000)
    check(f"{tag}: search no-result message", "No place found" in (await pg.inner_text("#toast")) or "unavailable" in (await pg.inner_text("#toast")), await pg.inner_text("#toast"))
    await pg.fill("#q", "Connaught Place, Delhi"); await pg.press("#q", "Enter")
    try:
        await pg.wait_for_selector("#nearby .big", timeout=15000); check(f"{tag}: search shows nearby card", True, (await pg.inner_text("#nearby")).replace("\n", " ")[:160])
    except Exception as e: check(f"{tag}: search shows nearby card", False, str(e)[:100])
    await pg.wait_for_timeout(1500)
    # stacked markers: Delhi centroid cluster spiderfies
    sp = await pg.evaluate("""async ()=>{const ms=markerLayer.getLayers().filter(m=>m.inc.lat===28.6665&&m.inc.lon===77.217);
       if(!ms.length)return 'none'; let done=null; markerLayer.once('spiderfied',e=>done='spiderfied '+e.markers.length+' at zoom '+map.getZoom());
       map.setView([28.6665,77.217],10,{animate:false}); await new Promise(r=>setTimeout(r,800));
       for(let k=0;k<12&&!done;k++){const c=markerLayer.getVisibleParent(ms[0]); if(!c||c===ms[0])return 'unclustered at zoom '+map.getZoom();
         c._icon.dispatchEvent(new MouseEvent('click',{bubbles:true})); await new Promise(r=>setTimeout(r,1000));}
       return done||'no spiderfy, zoom '+map.getZoom();}""")
    check(f"{tag}: same-point markers fan out (spiderfy)", sp.startswith("spiderfied") or sp.startswith("none"), sp)
    await pg.wait_for_timeout(800)
    await pg.screenshot(path=f"{OUT}_{tag}_spiderfy.png")
    # popup on a real marker
    await pg.evaluate("""()=>{markerLayer.unspiderfy();const m=markerLayer.getLayers().find(m=>m.inc.precision.startsWith('Locality')&&m.inc.channel==='news'&&m.inc.id!=='incXSS');map.setView(m.getLatLng(),16,{animate:false});setTimeout(()=>{markerLayer.zoomToShowLayer(m,()=>m.openPopup());},600);}""")
    await pg.wait_for_selector(".leaflet-popup-content", timeout=15000); await pg.wait_for_timeout(1200)
    box = await pg.evaluate("(()=>{const r=document.querySelector('.leaflet-popup-content-wrapper').getBoundingClientRect();return [r.left,r.top,r.right,r.bottom,innerWidth,innerHeight]})()")
    check(f"{tag}: popup fits viewport", box[0] >= 0 and box[2] <= box[4] and box[1] >= 0, str([round(x) for x in box]))
    txt = await pg.inner_text(".leaflet-popup-content")
    check(f"{tag}: popup has source+place+correction link", "Source" in txt and "as reported by" in txt and "Report an error" in txt)
    await pg.screenshot(path=f"{OUT}_{tag}_popup.png")
    await pg.evaluate("void map.closePopup()")
    # CSV export
    async with pg.expect_download() as d: await pg.evaluate("$('dlcsv').click()")
    dl = await d.value; pth = f"{OUT}_{tag}.csv"; await dl.save_as(pth)
    import csv as _csv; rows = sum(1 for _ in _csv.reader(open(pth, encoding="utf-8-sig", newline=""))) - 1
    check(f"{tag}: CSV export rows", rows == total, f"{rows} rows (+header) vs {total}")
    # PDF (print view) export
    async with ctx.expect_page() as np_: await pg.evaluate("$('dlpdf').click()")
    rp = await np_.value; await rp.wait_for_load_state(); await rp.wait_for_timeout(1500)
    check(f"{tag}: PDF print view opens with all rows", await rp.evaluate("document.querySelectorAll('.r').length") == total)
    if not mobile:
        await rp.pdf(path=f"{OUT}_filtered_export.pdf", format="A4")
    await rp.close()
    # methodology modal
    await pg.click("#mbtn"); await pg.wait_for_timeout(300)
    check(f"{tag}: methodology modal opens", await pg.is_visible("#mmodal")); await pg.keyboard.press("Escape")
    check(f"{tag}: modal closes on Escape", not await pg.is_visible("#mmodal"))
    # district popup
    await pg.evaluate("void map.setView([26.85,80.95],9)"); await pg.wait_for_timeout(1200)
    await pg.evaluate("""()=>{let L1;distLayer.eachLayer(l=>{if(l.feature.properties.d==='Lucknow')L1=l});L1.openPopup(L1.getBounds().getCenter());}""")
    await pg.wait_for_timeout(800)
    t = await pg.inner_text(".leaflet-popup-content"); check(f"{tag}: district popup cites NCRB", "NCRB" in t and "Lucknow" in t)
    await pg.evaluate("void map.closePopup();void map.setView([22.5,79],5)")
    if mobile:
        await pg.evaluate("setSheet('half')"); await pg.wait_for_timeout(500); await pg.screenshot(path=f"{OUT}_{tag}_sheet_half.png")
        await pg.evaluate("setSheet('peek')"); await pg.wait_for_timeout(500)
    await pg.wait_for_timeout(1500); await pg.screenshot(path=f"{OUT}_{tag}_home.png")
    # legal pages
    for page_ in ["terms.html", "privacy.html", "disclaimer.html"]:
        lp = await ctx.new_page(); r = await lp.goto(BASE + page_)
        check(f"{tag}: {page_} loads", r.ok and "TODO" in await lp.content())
        if page_ == "terms.html": await lp.screenshot(path=f"{OUT}_{tag}_terms.png")
        await lp.close()
    # manifest
    man = await pg.evaluate("fetch('manifest.webmanifest').then(r=>r.json())")
    check(f"{tag}: manifest", man.get("short_name") == "SafeNaksha" and len(man["icons"]) >= 3)
    ignore = ("favicon", "ERR_FAILED", "429", "Failed to load resource")
    real = [e for e in errs if not any(x in e for x in ignore)]
    check(f"{tag}: no console/page errors", not real, "; ".join(errs)[:400])
    await b.close()

async def main():
    async with async_playwright() as p:
        await run(p, False); await run(p, True)
    f = [r for r in results if not r[1]]
    print(f"\n{len(results)-len(f)}/{len(results)} passed"); [print("FAILED:", r) for r in f]
asyncio.run(main())
