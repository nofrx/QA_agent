from dataclasses import dataclass
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
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{api_base}/scans",
                                headers={"x-api-key": api_key},
                                params={"search": sku})
        resp.raise_for_status()
        data = resp.json()
        docs = data.get("docs", [])
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
