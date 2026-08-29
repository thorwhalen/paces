import sys, asyncio
from playwright.async_api import async_playwright


async def main():
    url, out = sys.argv[1], sys.argv[2]
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 1280
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 900
    full = len(sys.argv) > 5 and sys.argv[5] == "full"
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
        errs = []
        pg.on(
            "console",
            lambda m: (
                errs.append(f"{m.type}: {m.text}")
                if m.type in ("error", "warning")
                else None
            ),
        )
        pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
        await pg.goto(url, wait_until="networkidle")
        await pg.wait_for_timeout(2500)
        await pg.screenshot(path=out, full_page=full)
        print("OK", out)
        for e in errs[:20]:
            print("CONSOLE", e)
        await b.close()


asyncio.run(main())
