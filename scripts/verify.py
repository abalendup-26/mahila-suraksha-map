import asyncio, json
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        ctx = await b.new_context(viewport={"width":1400,"height":900}, geolocation={"latitude":28.6139,"longitude":77.2090}, permissions=["geolocation"])
        pg = await ctx.new_page(); errs=[]
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type=="error" and errs.append(m.text))
        await pg.goto("http://localhost:8765/index.html"); await pg.wait_for_function("window.__ready", timeout=60000)
        r = await pg.evaluate("window.__ready"); print("ready", r)
        print("district paths", await pg.locator("path.leaflet-interactive").count(), "marker layers", await pg.evaluate("markerLayer.getLayers().length"))
        print(await pg.inner_text("#countB"))
        await pg.wait_for_timeout(2500); await pg.screenshot(path="screenshots/desktop_india.png")
        await pg.click("#loc"); await pg.wait_for_timeout(3000)
        print("NEARBY:", await pg.inner_text("#nearby"))
        await pg.screenshot(path="screenshots/desktop_my_location_delhi.png")
        # open a marker popup
        await pg.evaluate("""()=>{const l=markerLayer.getLayers().find(m=>m.inc.channel==='news'&&m.inc.place.includes('Delhi')&&m.inc.precision.startsWith('Locality'));map.setView(l.getLatLng(),13);setTimeout(()=>{map.closePopup();l.openPopup()},800);}""")
        await pg.wait_for_timeout(2500)
        print("POPUP:", (await pg.inner_text(".leaflet-popup-content"))[:700])
        await pg.screenshot(path="screenshots/desktop_popup.png")
        await pg.evaluate("""()=>{const l=markerLayer.getLayers().find(m=>m.inc.channel==='social'&&m.inc.verification.includes('police'));map.setView(l.getLatLng(),12);setTimeout(()=>{map.closePopup();l.openPopup()},800);}""")
        await pg.wait_for_timeout(2500)
        print("SOCIAL POPUP:", (await pg.inner_text(".leaflet-popup-content"))[:700])
        await pg.screenshot(path="screenshots/desktop_popup_social.png")
        # place search
        await pg.fill("#q", "Hazratganj, Lucknow"); await pg.click("#sform button"); await pg.wait_for_timeout(4000)
        print("SEARCH:", (await pg.inner_text("#nearby"))[:300])
        # category switch
        await pg.select_option("#cat", "modesty"); await pg.check("input[value=rate]"); await pg.wait_for_timeout(1500)
        print("LEGEND modesty/rate:", await pg.inner_text("#legendA"))
        await pg.screenshot(path="screenshots/desktop_search_lucknow_modesty_rate.png")
        async with pg.expect_download() as d: await pg.click("#dlcsv")
        dl = await d.value; await dl.save_as("screenshots/test_download.csv"); print("csv ok")
        async with pg.expect_download() as d: await pg.click("#dlpdf")
        dl = await d.value; await dl.save_as("screenshots/test_download.pdf"); print("pdf ok")
        m = await b.new_context(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True, device_scale_factor=2)
        mp = await m.new_page(); await mp.goto("http://localhost:8765/index.html"); await mp.wait_for_function("window.__ready", timeout=60000)
        await mp.wait_for_timeout(2500); await mp.screenshot(path="screenshots/mobile.png")
        await mp.click("#toggle"); await mp.wait_for_timeout(600); await mp.screenshot(path="screenshots/mobile_panel_open.png")
        print("errors", errs)
        await b.close()
asyncio.run(main())
