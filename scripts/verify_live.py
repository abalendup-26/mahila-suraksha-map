#!/usr/bin/env python3
"""Live smoke check + desktop/mobile screenshots of a deployed URL.
Usage: verify_live.py [url] [screenshot_prefix]   (full functional audit: scripts/test_ui.py)"""
import asyncio, sys, json
from playwright.async_api import async_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "https://abalendup-26.github.io/mahila-suraksha-map/"
OUT = sys.argv[2] if len(sys.argv) > 2 else "screenshots/live"
OPEN_POPUP = """()=>{const m=markerLayer.getLayers().find(m=>m.inc.precision.startsWith('Locality')&&m.inc.channel==='news')||markerLayer.getLayers()[0];
  map.setView(m.getLatLng(),14,{animate:false});setTimeout(()=>markerLayer.zoomToShowLayer(m,()=>m.openPopup()),700);}"""
async def shoot(p, mobile):
    tag = "mobile" if mobile else "desktop"
    b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    o = dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2) if mobile else dict(viewport={"width": 1440, "height": 900})
    ctx = await b.new_context(**o, geolocation={"latitude": 28.6139, "longitude": 77.2090}, permissions=["geolocation"])
    pg = await ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    r = await pg.goto(URL + ("&" if "?" in URL else "?") + "nocache=1", wait_until="domcontentloaded")
    await pg.wait_for_function("window.__ready", timeout=90000)
    print(tag, "HTTP", r.status, "title:", await pg.title()); print(tag, "ready", json.dumps(await pg.evaluate("window.__ready")))
    print(tag, "consent banner visible:", await pg.is_visible("#consent"))
    await pg.screenshot(path=f"{OUT}_{tag}_first_visit.png")
    await pg.click("#cok")
    if mobile: await pg.evaluate("setSheet('full')"); await pg.wait_for_timeout(400)
    await pg.click("#tChips [data-p='7']"); await pg.wait_for_timeout(800)
    print(tag, "Last 7 days:", await pg.inner_text("#countB"))
    if mobile: await pg.evaluate("setSheet('peek')"); await pg.wait_for_timeout(400)
    await pg.click("#loc"); await pg.wait_for_selector("#nearby .big", timeout=15000); await pg.wait_for_timeout(1500)
    print(tag, "nearby:", (await pg.inner_text("#nearby")).replace("\n", " ")[:140])
    await pg.screenshot(path=f"{OUT}_{tag}_last7_mylocation.png")
    if mobile: await pg.evaluate("setSheet('peek')")
    await pg.evaluate(OPEN_POPUP); await pg.wait_for_selector(".leaflet-popup-content", timeout=15000); await pg.wait_for_timeout(1500)
    print(tag, "popup:", (await pg.inner_text(".leaflet-popup-content")).replace("\n", " ")[:220])
    await pg.screenshot(path=f"{OUT}_{tag}_popup.png")
    await pg.evaluate("void map.closePopup()"); await pg.click("#tChips [data-p='all']") if not mobile else await pg.evaluate("setPreset('all')")
    await pg.evaluate("void map.setView([22.5,79],5,{animate:false})"); await pg.wait_for_timeout(2500)
    if mobile: await pg.evaluate("setSheet('half')"); await pg.wait_for_timeout(600)
    await pg.screenshot(path=f"{OUT}_{tag}_india.png")
    for page_ in ["terms.html", "privacy.html", "disclaimer.html", "manifest.webmanifest", "assets/og-image.png", "data/incidents.app.json"]:
        rr = await pg.request.get(URL.split("?")[0].rstrip("/") + "/" + page_); print(tag, page_, rr.status)
    print(tag, "errors:", [e for e in errs if "favicon" not in e])
    await b.close()
async def main():
    async with async_playwright() as p:
        await shoot(p, False); await shoot(p, True)
asyncio.run(main())
