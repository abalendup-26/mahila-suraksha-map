#!/usr/bin/env python3
"""Render assets/ icons + OG image from assets/logo.svg (needs playwright + Chrome). Run manually; outputs are committed."""
import asyncio
from playwright.async_api import async_playwright
A="/workspace/safety-map/assets/"
logo=open(A+"logo.svg").read()
def page(size,pad,bg,radius):
    inner=int(size*(1-2*pad))
    return f"""<html><body style="margin:0;background:transparent"><div style="width:{size}px;height:{size}px;background:{bg};border-radius:{radius}px;display:flex;align-items:center;justify-content:center">
    <div style="width:{inner}px;height:{inner}px">{logo.replace('<svg ','<svg width="100%" height="100%" ')}</div></div></body></html>"""
OG="""<html><head><style>body{margin:0;font-family:Inter,'Noto Sans Devanagari',sans-serif}
.c{width:1200px;height:630px;background:linear-gradient(135deg,#2E1A52 0%,#4B2A84 55%,#6A3FB0 100%);color:#fff;display:flex;align-items:center;padding:0 80px;box-sizing:border-box;gap:56px;position:relative;overflow:hidden}
.g{position:absolute;right:-120px;top:-80px;width:620px;height:620px;border-radius:50%;background:radial-gradient(circle,rgba(224,69,123,.35),transparent 65%)}
h1{font-size:96px;margin:0;font-weight:800;letter-spacing:-2px}h2{font-size:40px;margin:6px 0 22px;font-weight:600;color:#F3D9E6}
p{font-size:28px;margin:0;line-height:1.4;color:#E9E3F5;max-width:720px}.pill{display:inline-block;margin-top:28px;font-size:22px;background:rgba(255,255,255,.14);padding:10px 18px;border-radius:999px}
</style></head><body><div class="c"><div class="g"></div><div style="width:250px;height:250px;flex:none">LOGO</div>
<div><h1>SafeNaksha</h1><h2>महिला सुरक्षा जागरूकता नक्शा</h2><p>Women's-safety awareness map for India — NCRB district statistics + source-linked news reports.</p>
<div class="pill">Information only · Not an official app · Emergency 112 · Helpline 181</div></div></div></body></html>""".replace("LOGO",logo.replace('<svg ','<svg width="100%" height="100%" ').replace('fill="#4B2A84"','fill="#FFFFFF"',1).replace('fill="#3A1F68"','fill="#EDE7F6"').replace('fill="#fff"','fill="#4B2A84"'))
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(executable_path="/usr/bin/google-chrome",args=["--no-sandbox"])
        for name,size,pad,bg,rad in [("icon-192.png",192,.08,"#FFFFFF",40),("icon-512.png",512,.08,"#FFFFFF",108),
                                     ("icon-maskable-512.png",512,.2,"#4B2A84",0),("apple-touch-icon.png",180,.1,"#FFFFFF",0),
                                     ("favicon-32.png",32,0,"transparent",0),("favicon-16.png",16,0,"transparent",0)]:
            pg=await b.new_page(viewport={"width":size,"height":size})
            html=page(size,pad,bg,rad)
            if "maskable" in name: html=html.replace('fill="#4B2A84"','fill="#FFFFFF"',1).replace('fill="#3A1F68"','fill="#EDE7F6"').replace('fill="#fff"','fill="#4B2A84"')
            await pg.set_content(html); await pg.screenshot(path=A+name,omit_background=True); await pg.close()
        pg=await b.new_page(viewport={"width":1200,"height":630}); await pg.set_content(OG); await pg.wait_for_timeout(500)
        await pg.screenshot(path=A+"og-image.png"); await b.close()
asyncio.run(main())
