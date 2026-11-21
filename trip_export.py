"""Kompyuterdagi Trip.com kirish holatini (trip_profile) trip_state.json fayliga chiqaradi.
Shu faylni serverga yuklasangiz, serverdagi bot Trip.com'ga kirgan holatda ishlaydi."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

BASE = Path(__file__).parent


async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(str(BASE / "trip_profile"), headless=True)
        page = await ctx.new_page()
        await page.goto("https://www.trip.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await ctx.storage_state(path=str(BASE / "trip_state.json"))
        n = len([c for c in (await ctx.cookies()) if "trip" in c["domain"]])
        await ctx.close()
    print(f"OK: trip_state.json tayyor ({n} ta Trip.com cookie)")

asyncio.run(main())
