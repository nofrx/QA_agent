from dataclasses import dataclass
import os
import re
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


def extract_from_asset(asset: dict, sku: str) -> ScanData:
    """Extract GLB filenames from an asset's canonicalAsset (product) data."""
    product = asset.get("canonicalAsset", {})
    brand = product.get("brand", "Unknown")
    color = product.get("color", "Unknown")
    silhouette = product.get("silhouette", "Unknown")

    versions = product.get("versions", [])
    if not versions:
        raise ValueError(f"No published version found for {sku}")

    # Search versions in reverse (latest first) for left shoe touch-up
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
            source = latest.get("sourceFilename")
            touchedup = latest.get("previewFilename")
            autoshadow = latest.get("autoShadowFilename")
            if touchedup and autoshadow and source:
                return ScanData(
                    sku=sku, brand=brand, color=color, silhouette=silhouette,
                    raw_scan_filename=source,
                    touchedup_filename=touchedup,
                    autoshadow_filename=autoshadow,
                )

    raise ValueError(f"No touch-up iteration with all 3 files found for {sku}")


async def find_scan_by_sku(api_base: str, api_key: str, sku: str) -> ScanData:
    """Find scan data for a SKU. Tries API key, then Chrome AppleScript."""
    # Try API key auth first
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{api_base}/scans",
                headers={"x-api-key": api_key},
                params={"search": sku}
            )
            resp.raise_for_status()
            data = resp.json()
            return _find_sku_in_scan_docs(data.get("docs", []), sku)
    except Exception:
        pass

    # Fall back to Chrome AppleScript via assets API
    return await find_scan_by_sku_chrome(api_base, sku)


async def find_scan_by_sku_chrome(api_base: str, sku: str) -> ScanData:
    """Use AppleScript + Chrome to search assets API and extract GLB data."""
    import json as json_mod
    import subprocess
    import tempfile

    safe_sku = re.sub(r"[^A-Za-z0-9\-_]", "", sku)
    if not safe_sku:
        raise ValueError(f"Invalid SKU: {sku}")

    # JavaScript that:
    # 1. Paginates through /api/assets (200 per page, up to 100 pages = 20K assets)
    # 2. Finds asset with matching sku field
    # 3. Extracts GLB filenames from the canonicalAsset's latest version
    js_code = (
        "var sku='" + safe_sku + "';"
        "var found=null;"
        "for(var p=1;p<=100;p++){"
        "var x=new XMLHttpRequest();"
        "x.open('GET','/api/assets?limit=200&page='+p,false);"
        "x.send();"
        "if(x.status!==200)break;"
        "var d=JSON.parse(x.responseText);"
        "for(var i=0;i<d.docs.length;i++){"
        "if(d.docs[i].sku===sku){found=d.docs[i];break;}}"
        "if(found||!d.hasNextPage)break;}"
        "if(!found){'NOT_FOUND';}else{"
        "var cp=found.canonicalAsset;"
        "var vs=cp.versions||[];"
        "var result=null;"
        "for(var vi=vs.length-1;vi>=0;vi--){"
        "var files=vs[vi].files||[];"
        "for(var fi=0;fi<files.length;fi++){"
        "var f=files[fi];"
        "if(f.laterality==='left'&&f.type==='3d'&&f.task&&f.task.three"
        "&&f.task.three.method==='covision_scan_touch_up'){"
        "var its=f.task.three.iterations||[];"
        "if(its.length>0){"
        "var last=its[its.length-1];"
        "result=JSON.stringify({"
        "sku:sku,source:last.sourceFilename||'',"
        "touchedup:last.previewFilename||'',"
        "autoshadow:last.autoShadowFilename||'',"
        "brand:cp.brand||'',color:cp.color||'',"
        "silhouette:cp.silhouette||''});"
        "break;}}}"
        "if(result)break;}"
        "result||'NO_TOUCHUP';}"
    )

    applescript = (
        'tell application "Google Chrome"\n'
        '    set windowCount to count of windows\n'
        '    repeat with w from 1 to windowCount\n'
        '        set tabCount to count of tabs of window w\n'
        '        repeat with i from 1 to tabCount\n'
        '            set tabURL to URL of tab i of window w\n'
        '            if tabURL contains "dashboard.shopar.ai" then\n'
        '                set jsCode to "' + js_code + '"\n'
        '                set jsResult to execute tab i of window w javascript jsCode\n'
        '                return jsResult\n'
        '            end if\n'
        '        end repeat\n'
        '    end repeat\n'
        '    return "NO_DASHBOARD_TAB"\n'
        'end tell'
    )

    with tempfile.NamedTemporaryFile(mode='w', suffix='.scpt', delete=False) as f:
        f.write(applescript)
        script_path = f.name

    try:
        result = subprocess.run(
            ["osascript", script_path],
            capture_output=True, text=True, timeout=120  # Allow time for pagination
        )
        output = result.stdout.strip()

        if result.returncode != 0:
            raise ValueError(f"Chrome script failed: {result.stderr.strip()[:200]}")

        if not output or output == "NO_DASHBOARD_TAB":
            raise ValueError(
                "No dashboard.shopar.ai tab found in Chrome. "
                "Open the dashboard in Chrome and try again."
            )

        if output == "NOT_FOUND":
            raise ValueError(
                f"SKU {sku} not found in dashboard assets. "
                "Check the SKU is correct (e.g., F5714D05U-K11)."
            )

        if output == "NO_TOUCHUP":
            raise ValueError(
                f"SKU {sku} found but has no touch-up data yet. "
                "The model may not have been processed."
            )

        data = json_mod.loads(output)
        return ScanData(
            sku=data["sku"],
            brand=data.get("brand", "Unknown"),
            color=data.get("color", "Unknown"),
            silhouette=data.get("silhouette", "Unknown"),
            raw_scan_filename=data["source"],
            touchedup_filename=data["touchedup"],
            autoshadow_filename=data["autoshadow"],
        )

    except json_mod.JSONDecodeError:
        raise ValueError(f"Invalid response from Chrome: {output[:200]}")
    except subprocess.TimeoutExpired:
        raise ValueError("Chrome lookup timed out. The dashboard may be slow.")
    finally:
        os.unlink(script_path)


def _find_sku_in_scan_docs(docs: list, sku: str) -> ScanData:
    """Find matching left-shoe scan in /api/scans response docs."""
    for scan in docs:
        if scan.get("laterality") != "left":
            continue
        product = scan.get("product", {})
        for tag in product.get("clientTags", []):
            if tag.get("key") == "clientSku" and tag.get("value", "").upper() == sku.upper():
                return _extract_from_scan(scan, sku)
        if product.get("modelCode", "").upper() == sku.upper():
            return _extract_from_scan(scan, sku)
    raise ValueError(f"No scan found for SKU: {sku}")


def _extract_from_scan(scan: dict, sku: str) -> ScanData:
    """Extract data from a /api/scans document (legacy format)."""
    product = scan.get("product", {})
    brand = product.get("brand", "Unknown")
    color = product.get("color", "Unknown")
    silhouette = product.get("silhouette", "Unknown")

    versions = product.get("versions", [])
    if not versions:
        raise ValueError(f"No published version found for {sku}")

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
            source = latest.get("sourceFilename", scan.get("glbFilename", ""))
            touchedup = latest.get("previewFilename")
            autoshadow = latest.get("autoShadowFilename")
            if touchedup and autoshadow:
                return ScanData(
                    sku=sku, brand=brand, color=color, silhouette=silhouette,
                    raw_scan_filename=source,
                    touchedup_filename=touchedup,
                    autoshadow_filename=autoshadow,
                    scan_id=scan.get("id", ""),
                )

    raise ValueError(f"No touch-up data found for {sku}")
