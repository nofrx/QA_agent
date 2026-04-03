from dataclasses import dataclass
import os
import httpx

@dataclass
class ScanData:
    sku: str
    brand: str
    color: str
    silhouette: str
    raw_scan_filename: str
    touchedup_filename: str
    autoshadow_filename: str
    scan_id: str = ""

def extract_sku_files(scan: dict) -> ScanData:
    product = scan.get("product", {})
    sku = product.get("modelCode", "")
    for tag in product.get("clientTags", []):
        if tag.get("key") == "clientSku":
            sku = tag["value"]
            break
    brand = product.get("brand", "Unknown")
    color = product.get("color", "Unknown")
    silhouette = product.get("silhouette", "Unknown")
    raw_scan_filename = scan.get("glbFilename", "")

    versions = product.get("versions", [])
    if not versions:
        raise ValueError(f"No published version found for {sku}")

    touchedup = None
    autoshadow = None
    for version in reversed(versions):
        for file_entry in version.get("files", []):
            if file_entry.get("laterality") != "left" or file_entry.get("type") != "3d":
                continue
            task = file_entry.get("task", {})
            three = task.get("three", {})
            if three.get("method") != "covision_scan_touch_up":
                continue
            iterations = three.get("iterations", [])
            if not iterations:
                continue
            latest = iterations[-1]
            touchedup = latest.get("previewFilename")
            autoshadow = latest.get("autoShadowFilename")
            if touchedup and autoshadow:
                break
        if touchedup and autoshadow:
            break

    if not touchedup or not autoshadow:
        raise ValueError(f"No published version with touch-up data found for {sku}")

    return ScanData(sku=sku, brand=brand, color=color, silhouette=silhouette,
                    raw_scan_filename=raw_scan_filename, touchedup_filename=touchedup,
                    autoshadow_filename=autoshadow, scan_id=scan.get("id", ""))

async def find_scan_by_sku(api_base: str, api_key: str, sku: str) -> ScanData:
    """Try API key first, fall back to Playwright browser session."""
    # Try API key auth
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{api_base}/scans",
                                    headers={"x-api-key": api_key},
                                    params={"search": sku})
            resp.raise_for_status()
            data = resp.json()
            return _find_sku_in_docs(data.get("docs", []), sku)
    except Exception:
        pass

    # Fall back to Playwright with Chrome session
    return await find_scan_by_sku_cdp(api_base, sku)

async def find_scan_by_sku_cdp(api_base: str, sku: str) -> ScanData:
    """Use AppleScript + Chrome to fetch scan data via sync XHR in a dashboard tab."""
    import json as json_mod
    import subprocess
    import tempfile

    # Sanitize SKU — only allow alphanumeric, dash, underscore
    import re
    safe_sku = re.sub(r"[^A-Za-z0-9\-_]", "", sku)
    if not safe_sku:
        raise ValueError(f"Invalid SKU: {sku}")

    # Write AppleScript to temp file — use single quotes inside JS to avoid AppleScript quote conflicts
    applescript = (
        'tell application "Google Chrome"\n'
        '    set windowCount to count of windows\n'
        '    repeat with w from 1 to windowCount\n'
        '        set tabCount to count of tabs of window w\n'
        '        repeat with i from 1 to tabCount\n'
        '            set tabURL to URL of tab i of window w\n'
        '            if tabURL contains "dashboard.shopar.ai" then\n'
        '                set jsCode to "var x=new XMLHttpRequest();x.open(\'GET\',\'/api/scans?search=' + safe_sku + '\',false);x.send();x.status===200?x.responseText:\'ERROR:\'+x.status;"\n'
        '                set jsResult to execute tab i of window w javascript jsCode\n'
        '                return jsResult\n'
        '            end if\n'
        '        end repeat\n'
        '    end repeat\n'
        '    return "NO_DASHBOARD_TAB"\n'
        'end tell'
    )

    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.scpt', delete=False) as f:
        f.write(applescript)
        script_path = f.name

    try:
        result = subprocess.run(
            ["osascript", script_path],
            capture_output=True, text=True, timeout=15
        )
        output = result.stdout.strip()

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise ValueError(f"AppleScript failed: {stderr[:200]}")

        if not output or output == "NO_DASHBOARD_TAB":
            raise ValueError(
                "No dashboard.shopar.ai tab found in Chrome. "
                "Please open the dashboard in Chrome first."
            )

        if output.startswith("ERROR:"):
            raise ValueError(f"Dashboard API returned {output}")

        data = json_mod.loads(output)
        return _find_sku_in_docs(data.get("docs", []), sku)

    except json_mod.JSONDecodeError:
        raise ValueError(f"Invalid response from dashboard: {output[:200]}")
    except subprocess.TimeoutExpired:
        raise ValueError("Chrome AppleScript timed out")
    finally:
        os.unlink(script_path)

def _find_sku_in_docs(docs: list, sku: str) -> ScanData:
    """Find matching left-shoe scan in API response docs."""
    for scan in docs:
        if scan.get("laterality") != "left":
            continue
        product = scan.get("product", {})
        for tag in product.get("clientTags", []):
            if tag.get("key") == "clientSku" and tag.get("value", "").upper() == sku.upper():
                return extract_sku_files(scan)
        if product.get("modelCode", "").upper() == sku.upper():
            return extract_sku_files(scan)
    raise ValueError(f"No scan found for SKU: {sku}")
