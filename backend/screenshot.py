import asyncio
import os


async def capture_viewer_screenshots(
    viewer_url: str, glb_path: str, output_dir: str, prefix: str, api_key: str = None
) -> list:
    """Capture screenshots of a 3D model viewer using Playwright."""
    from playwright.async_api import async_playwright

    os.makedirs(output_dir, exist_ok=True)
    screenshots = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(viewer_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        path = os.path.join(output_dir, f"{prefix}_default.png")
        await page.screenshot(path=path)
        screenshots.append(path)

        await browser.close()

    return screenshots


async def capture_local_glb_screenshots(
    glb_path: str, output_dir: str, prefix: str
) -> list:
    """Placeholder for local GLB screenshot capture via Blender."""
    return []
