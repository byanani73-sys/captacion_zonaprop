import asyncio
from playwright.async_api import async_playwright

DETAIL_URL = "https://www.zonaprop.com.ar/propiedades/clasificado/veclappa-semipiso-reciclado-a-nuevo-en-palermo-cochera-58188617.html"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--headless=new"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="es-AR"
        )
        page = await context.new_page()

        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        await page.goto(DETAIL_URL, wait_until="domcontentloaded")

        # Esperar a que pase el challenge de Cloudflare (hasta 30s)
        for i in range(30):
            title = await page.title()
            if "moment" not in title.lower() and "cloudflare" not in title.lower():
                break
            await page.wait_for_timeout(1000)

        await page.wait_for_timeout(3000)
        html = await page.content()
        with open("data/detalle.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML guardado en data/detalle.html ({len(html)} bytes)")
        print(f"Titulo: {await page.title()}")
        await browser.close()

asyncio.run(main())
