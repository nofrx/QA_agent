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
    raw_scan_filename: str       # from referenceFiles[0].name (actual raw scanner output)
    source_filename: str         # from iter.sourceFilename (big touched-up source, ~89 MB)
    optimised_filename: str      # from iter.previewFilename (small optimised preview, ~3.83 MB) — optional
    autoshadow_filename: str     # from iter.autoShadowFilename — optional
    scan_id: str = ""


def extract_from_asset(asset: dict, sku: str) -> ScanData:
    """Extract GLB filenames from an asset's canonicalAsset (product) data."""
    product = asset.get("canonicalAsset", {})
    brand = product.get("brand", "Unknown")
    color = product.get("color", "Unknown")
    silhouette = product.get("silhouette", "Unknown")

    # Raw scan file lives in referenceFiles[0]
    reference_files = product.get("referenceFiles", []) or []
    raw_scan_filename = ""
    if reference_files:
        raw_scan_filename = reference_files[0].get("name", "") or ""

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
            source = latest.get("sourceFilename") or ""
            optimised = latest.get("previewFilename") or ""
            autoshadow = latest.get("autoShadowFilename") or ""
            if source:
                # Fall back to source as raw scan if referenceFiles missing
                raw = raw_scan_filename or source
                return ScanData(
                    sku=sku, brand=brand, color=color, silhouette=silhouette,
                    raw_scan_filename=raw,
                    source_filename=source,
                    optimised_filename=optimised,
                    autoshadow_filename=autoshadow,
                )

    raise ValueError(f"No touch-up iteration with source file found for {sku}")


async def find_scan_by_sku(api_base: str, api_key: str, sku: str) -> ScanData:
    """Find scan data for a SKU. Tries API key, then Chrome AppleScript."""
    # Try API key auth first
    api_error = None
    if api_key:
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
        except httpx.HTTPStatusError as e:
            api_error = f"API key returned {e.response.status_code} (may be expired)"
        except Exception as e:
            api_error = str(e)

    # Fall back to Chrome AppleScript via assets API
    try:
        return await find_scan_by_sku_chrome(api_base, sku)
    except ValueError as e:
        # Add API key context to the Chrome fallback error
        msg = str(e)
        if api_error and "No dashboard" in msg:
            msg += f"\n\nAPI key also failed: {api_error}.\nOpen https://dashboard.shopar.ai in Chrome to use auto-lookup."
        raise ValueError(msg)


async def find_scan_by_sku_chrome(api_base: str, sku: str) -> ScanData:
    """Use AppleScript + Chrome to search assets API and extract GLB data."""
    import json as json_mod
    import subprocess
    import tempfile

    safe_sku = re.sub(r"[^A-Za-z0-9\-_]", "", sku)
    if not safe_sku:
        raise ValueError(f"Invalid SKU: {sku}")

    # JavaScript that uses Payload CMS where-query to find asset by SKU directly.
    # Single API call instead of paginating through all assets.
    js_code = (
        "(function(){"
        "var sku='" + safe_sku + "';"
        "var x=new XMLHttpRequest();"
        "x.open('GET','/api/assets?limit=1&where[sku][equals]='+sku,false);"
        "x.send();"
        "if(x.status!==200)return 'API_ERROR_'+x.status;"
        "var d=JSON.parse(x.responseText);"
        "if(!d.docs||!d.docs.length){"
        "var x2=new XMLHttpRequest();"
        "x2.open('GET','/api/assets?limit=1&where[sku][equals]='+sku.toUpperCase(),false);"
        "x2.send();"
        "if(x2.status===200){d=JSON.parse(x2.responseText);}"
        "if(!d.docs||!d.docs.length)return 'NOT_FOUND';}"
        "var found=d.docs[0];"
        "var cp=found.canonicalAsset;"
        "if(!cp)return 'NO_CANONICAL';"
        "var rfs=cp.referenceFiles||[];"
        "var rawScan=(rfs.length>0?(rfs[0].name||''):'');"
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
        "sku:sku.toUpperCase(),"
        "raw_scan:rawScan,"
        "source:last.sourceFilename||'',"
        "optimised:last.previewFilename||'',"
        "autoshadow:last.autoShadowFilename||'',"
        "brand:cp.brand||'',color:cp.color||'',"
        "silhouette:cp.silhouette||''});"
        "break;}}}"
        "if(result)break;}"
        "return result||'NO_TOUCHUP';})()"
    )

    # Try Chrome first, then Safari as fallback
    applescript_chrome = (
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

    applescript_safari = (
        'tell application "Safari"\n'
        '    set windowCount to count of windows\n'
        '    repeat with w from 1 to windowCount\n'
        '        set tabCount to count of tabs of window w\n'
        '        repeat with i from 1 to tabCount\n'
        '            set tabURL to URL of tab i of window w\n'
        '            if tabURL contains "dashboard.shopar.ai" then\n'
        '                set jsResult to do JavaScript "' + js_code + '" in tab i of window w\n'
        '                return jsResult\n'
        '            end if\n'
        '        end repeat\n'
        '    end repeat\n'
        '    return "NO_DASHBOARD_TAB"\n'
        'end tell'
    )

    # Try Chrome, fall back to Safari
    applescript = applescript_chrome
    import subprocess as _sp
    with tempfile.NamedTemporaryFile(mode='w', suffix='.scpt', delete=False) as _f:
        _f.write(applescript_chrome)
        _chrome_path = _f.name
    try:
        _r = _sp.run(["osascript", _chrome_path], capture_output=True, text=True, timeout=10)
        if _r.returncode != 0 or "NO_DASHBOARD_TAB" in (_r.stdout.strip()):
            applescript = applescript_safari
    except Exception:
        applescript = applescript_safari
    finally:
        os.unlink(_chrome_path)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.scpt', delete=False) as f:
        f.write(applescript)
        script_path = f.name

    try:
        result = subprocess.run(
            ["osascript", script_path],
            capture_output=True, text=True, timeout=60  # ~25 pages at ~1-2s each
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
                "Check the SKU is correct, or use URL mode."
            )

        if output == "NO_TOUCHUP":
            raise ValueError(
                f"SKU {sku} found but has no touch-up data yet. "
                "The model may not have been processed."
            )

        data = json_mod.loads(output)
        source = data.get("source", "") or ""
        raw_scan = data.get("raw_scan", "") or source
        if not source:
            raise ValueError(f"SKU {sku} has no source GLB in latest iteration")
        return ScanData(
            sku=data["sku"],
            brand=data.get("brand", "Unknown"),
            color=data.get("color", "Unknown"),
            silhouette=data.get("silhouette", "Unknown"),
            raw_scan_filename=raw_scan,
            source_filename=source,
            optimised_filename=data.get("optimised", "") or "",
            autoshadow_filename=data.get("autoshadow", "") or "",
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
            source = latest.get("sourceFilename") or scan.get("glbFilename", "") or ""
            optimised = latest.get("previewFilename") or ""
            autoshadow = latest.get("autoShadowFilename") or ""
            # Legacy /api/scans format — raw scan is scan.glbFilename
            raw_scan = scan.get("glbFilename", "") or source
            if source:
                return ScanData(
                    sku=sku, brand=brand, color=color, silhouette=silhouette,
                    raw_scan_filename=raw_scan,
                    source_filename=source,
                    optimised_filename=optimised,
                    autoshadow_filename=autoshadow,
                    scan_id=scan.get("id", ""),
                )

    raise ValueError(f"No touch-up data found for {sku}")
