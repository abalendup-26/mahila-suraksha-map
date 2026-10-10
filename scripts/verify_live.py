"""Headless check of a deployed/local URL: loads, layers present, 'Last 7 days' filter, popup credibility block, modal."""
import asyncio, sys
from playwright.async_api import async_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765/index.html"
OUT = sys.argv[2] if len(sys.argv) > 2 else "screenshots/live_last7days.png"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        ctx = await b.new_context(viewport={"width":1400,"height":900}, geolocation={"latitude":28.6139,"longitude":77.2090}, permissions=["geolocation"])
        pg = await ctx.new_page(); errs=[]
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(URL + ("&" if "?" in URL else "?") + "nocache=1", wait_until="domcontentloaded")
        await pg.wait_for_function("window.__ready", timeout=90000)
        print("ready", await pg.evaluate("window.__ready"), "hidden(no verifiable link):", await pg.evaluate("window.__hidden"))
        print("tInfo:", await pg.inner_text("#tInfo"))
        print("All time:", await pg.inner_text("#countB"))
        await pg.click("#loc"); await pg.wait_for_timeout(2500)
        n_all = await pg.inner_text("#nearby")
        await pg.select_option("#tPreset", "7"); await pg.wait_for_timeout(1500)
        print("Last 7 days:", await pg.inner_text("#countB"))
        print("markers on map:", await pg.evaluate("markerLayer.getLayers().length"))
        print("nearby all-time vs 7d:", n_all.split('\n')[2][:90], '|', (await pg.inner_text("#nearby")).split('\n')[2][:90])
        await pg.evaluate("""()=>{const l=markerLayer.getLayers().find(m=>m.inc.precision.startsWith('Locality')&&m.inc.channel==='news')||markerLayer.getLayers()[0];map.setView(l.getLatLng(),13);setTimeout(()=>{map.closePopup();l.openPopup()},900);}""")
        await pg.wait_for_timeout(3000)
        print("POPUP:", (await pg.inner_text(".leaflet-popup-content"))[:600])
        await pg.screenshot(path=OUT)
        await pg.evaluate("map.closePopup()"); await pg.evaluate("map.setView([22.5,79],5)"); await pg.wait_for_timeout(2500)
        await pg.screenshot(path=OUT.replace(".png", "_india.png"))
        await pg.click("#mbtn"); await pg.wait_for_timeout(500)
        print("modal visible:", await pg.is_visible("#mmodal"))
        await pg.screenshot(path=OUT.replace(".png", "_methodology.png"))
        await pg.click("#mmodal button"); 
        await pg.evaluate("""()=>{const f=distData.features.find(f=>f.properties.d==='Lucknow');L.geoJSON(f).getLayers()[0];}""")
        async with pg.expect_download() as d: await pg.click("#dlcsv")
        dl = await d.value; path = OUT.replace(".png", "_export.csv"); await dl.save_as(path)
        print("csv rows (7d):", sum(1 for _ in open(path, encoding="utf-8-sig")) - 1, "header:", open(path, encoding="utf-8-sig").readline().strip()[:200])
        print("errors", errs); await b.close()
asyncio.run(main())
