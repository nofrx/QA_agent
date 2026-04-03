# Shoe QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web-based QA tool that downloads 3D shoe models from ShopAR dashboard by SKU, analyzes geometry and textures via Blender headless, and generates visual HTML comparison reports.

**Architecture:** FastAPI backend orchestrates a pipeline: query ShopAR API for scan data, download/decrypt 3 GLB variants from CloudFront, launch Blender 4.58 headless for geometry analysis and texture extraction, run NumPy/Pillow pixel-level texture comparison, capture Playwright screenshots, and generate a self-contained HTML report. Simple HTML/JS frontend with SSE for live progress.

**Tech Stack:** Python 3.12+, FastAPI, uvicorn, NumPy, Pillow, Playwright, Jinja2, aiosqlite, httpx, Blender 4.58 headless

**Spec:** `docs/superpowers/specs/2026-04-03-shoe-qa-design.md`

---

## File Structure

```
shoe-qa/
├── backend/
│   ├── __init__.py
│   ├── main.py                 ← FastAPI app, routes, SSE progress
│   ├── config.py               ← Settings loader (config.json)
│   ├── crypto.py               ← XOR/Xorshift32 GLB decryption
│   ├── dashboard_api.py        ← ShopAR /api/scans client
│   ├── downloader.py           ← Download from CloudFront + decrypt
│   ├── storage.py              ← File organization + SQLite index
│   ├── pipeline.py             ← Orchestrates full QA pipeline
│   ├── blender_runner.py       ← Subprocess launcher for Blender
│   ├── texture_compare.py      ← NumPy/Pillow diff engine
│   ├── screenshot.py           ← Playwright web preview capture
│   └── report_generator.py     ← Jinja2 HTML report builder
├── blender/
│   ├── geometry_analyzer.py    ← Geometry QA script (runs inside Blender)
│   ├── texture_extractor.py    ← Extract PBR maps from GLB materials
│   └── issue_renderer.py       ← Render camera-to-issue screenshots
├── frontend/
│   ├── index.html              ← Main page: SKU input + progress feed
│   ├── reports.html            ← Library page: past reports by SKU
│   ├── style.css               ← Minimal styling
│   └── app.js                  ← SSE listener + API calls
├── templates/
│   └── report_template.html    ← Jinja2 template for QA HTML reports
├── tests/
│   ├── __init__.py
│   ├── test_crypto.py
│   ├── test_dashboard_api.py
│   ├── test_storage.py
│   ├── test_texture_compare.py
│   └── test_config.py
├── config.json
└── requirements.txt
```

---

### Task 1: Project Scaffolding & Configuration

**Files:**
- Create: `requirements.txt`
- Create: `config.json`
- Create: `backend/__init__.py`
- Create: `backend/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.115.0
uvicorn==0.32.0
numpy>=1.26.0
Pillow>=10.0.0
playwright>=1.40.0
jinja2>=3.1.0
aiosqlite>=0.20.0
httpx>=0.27.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 2: Create config.json with defaults**

```json
{
  "api_key": "d4cc0dd1-99b2-43b6-b59a-7f2107146ce1",
  "cloudfront_base": "https://dj5e08oeu5ym4.cloudfront.net/3e",
  "dashboard_api": "https://dashboard.shopar.ai/api",
  "dashboard_viewer": "https://dashboard.shopar.ai/admin/viewer",
  "blender_path": "/Applications/Blender 4.58.app/Contents/MacOS/Blender",
  "reports_dir": "~/ShoeQA/reports",
  "port": 8080
}
```

- [ ] **Step 3: Write test for config loading**

```python
# tests/test_config.py
import json
import os
import tempfile
import pytest
from backend.config import load_config, Config

def test_load_config_from_file():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({
            "api_key": "test-key",
            "cloudfront_base": "https://example.com/3e",
            "dashboard_api": "https://example.com/api",
            "dashboard_viewer": "https://example.com/viewer",
            "blender_path": "/usr/bin/blender",
            "reports_dir": "/tmp/reports",
            "port": 9090
        }, f)
        f.flush()
        config = load_config(f.name)
    os.unlink(f.name)
    assert config.api_key == "test-key"
    assert config.port == 9090
    assert config.reports_dir == "/tmp/reports"

def test_config_expands_home_dir():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({
            "api_key": "k",
            "cloudfront_base": "https://example.com/3e",
            "dashboard_api": "https://example.com/api",
            "dashboard_viewer": "https://example.com/viewer",
            "blender_path": "/usr/bin/blender",
            "reports_dir": "~/ShoeQA/reports",
            "port": 8080
        }, f)
        f.flush()
        config = load_config(f.name)
    os.unlink(f.name)
    assert "~" not in config.reports_dir
    assert os.path.expanduser("~") in config.reports_dir
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd /Users/tomislavbelacic/shoe-qa && python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.config'`

- [ ] **Step 5: Implement config.py**

```python
# backend/config.py
import json
import os
from dataclasses import dataclass

@dataclass
class Config:
    api_key: str
    cloudfront_base: str
    dashboard_api: str
    dashboard_viewer: str
    blender_path: str
    reports_dir: str
    port: int

def load_config(path: str) -> Config:
    with open(path) as f:
        data = json.load(f)
    data["reports_dir"] = os.path.expanduser(data["reports_dir"])
    return Config(**data)
```

Also create `backend/__init__.py` and `tests/__init__.py` as empty files.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/tomislavbelacic/shoe-qa && python -m pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 7: Install dependencies**

Run: `cd /Users/tomislavbelacic/shoe-qa && pip install -r requirements.txt`

- [ ] **Step 8: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add -A
git commit -m "feat: project scaffolding with config loader"
```

---

### Task 2: GLB Decryption (crypto.py)

**Files:**
- Create: `backend/crypto.py`
- Create: `tests/test_crypto.py`

- [ ] **Step 1: Write test for decryption**

```python
# tests/test_crypto.py
import numpy as np
from backend.crypto import decrypt_glb, is_valid_glb

def test_decrypt_known_gltf_magic():
    """Encrypt known glTF data, then decrypt and verify magic bytes."""
    # Create fake glTF data starting with magic bytes
    original = b'glTF' + b'\x02\x00\x00\x00' + b'\x00' * 100
    # Encrypt it using the same algorithm
    n = len(original)
    data = np.frombuffer(original, dtype=np.uint8).copy()
    rng_state = np.int32(n)
    key = np.zeros(n, dtype=np.uint8)
    for i in range(n):
        rng_state = np.int32(rng_state ^ np.int32(rng_state << np.int32(13)))
        rng_state = np.int32(rng_state ^ np.int32(rng_state >> np.int32(17)))
        rng_state = np.int32(rng_state ^ np.int32(rng_state << np.int32(5)))
        key[i] = int(rng_state) & 0xFF
    encrypted = np.bitwise_xor(data, key).tobytes()
    
    decrypted = decrypt_glb(encrypted)
    assert decrypted[:4] == b'glTF'
    assert decrypted == original

def test_is_valid_glb():
    assert is_valid_glb(b'glTF\x02\x00\x00\x00')
    assert not is_valid_glb(b'\x00\x00\x00\x00')
    assert not is_valid_glb(b'')

def test_decrypt_already_valid():
    """If data is already valid glTF, return as-is."""
    data = b'glTF' + b'\x02\x00\x00\x00' + b'\x00' * 100
    result = decrypt_glb(data)
    assert result == data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tomislavbelacic/shoe-qa && python -m pytest tests/test_crypto.py -v`
Expected: FAIL

- [ ] **Step 3: Implement crypto.py**

```python
# backend/crypto.py
import numpy as np
from ctypes import c_int32

def _int32(n: int) -> int:
    return c_int32(n).value

def decrypt_glb(data: bytes) -> bytes:
    """Decrypt XOR/Xorshift32-encrypted GLB data. Returns bytes."""
    if is_valid_glb(data):
        return data
    
    arr = np.frombuffer(data, dtype=np.uint8).copy()
    n = len(arr)
    
    rng_state = _int32(n)
    key = np.zeros(n, dtype=np.uint8)
    
    for i in range(n):
        rng_state = _int32(rng_state ^ _int32(rng_state << 13))
        rng_state = _int32(rng_state ^ _int32(rng_state >> 17))
        rng_state = _int32(rng_state ^ _int32(rng_state << 5))
        key[i] = rng_state & 0xFF
    
    decrypted = np.bitwise_xor(arr, key)
    return decrypted.tobytes()

def is_valid_glb(data: bytes) -> bool:
    """Check if data starts with glTF magic bytes."""
    return len(data) >= 4 and data[:4] == b'glTF'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tomislavbelacic/shoe-qa && python -m pytest tests/test_crypto.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add backend/crypto.py tests/test_crypto.py
git commit -m "feat: GLB XOR/Xorshift32 decryption"
```

---

### Task 3: Dashboard API Client (dashboard_api.py)

**Files:**
- Create: `backend/dashboard_api.py`
- Create: `tests/test_dashboard_api.py`

- [ ] **Step 1: Write test for SKU data extraction**

```python
# tests/test_dashboard_api.py
import pytest
from backend.dashboard_api import extract_sku_files, ScanData

SAMPLE_SCAN = {
    "glbFilename": "2c7265d7-0089-4044-8d05-bca28639cd28.glb",
    "laterality": "left",
    "product": {
        "modelCode": "F5714D05U-K11",
        "brand": "Friboo",
        "color": "Navy",
        "silhouette": "sneaker",
        "clientTags": [
            {"key": "clientSku", "value": "F5714D05U-K11"}
        ],
        "versions": [{
            "files": [{
                "filename": "27d51ba0-2e90-490b-ba82-281b8f4c6604.glb",
                "type": "3d",
                "laterality": "left",
                "task": {
                    "three": {
                        "method": "covision_scan_touch_up",
                        "laterality": "left",
                        "iterations": [{
                            "sourceFilename": "132fb406-41bd-4388-8fe2-d184e9e8d8e4.glb",
                            "previewFilename": "27d51ba0-2e90-490b-ba82-281b8f4c6604.glb",
                            "autoShadowFilename": "8806197c-44cf-4cbc-b2c0-522ab8067bd1.glb"
                        }]
                    }
                }
            }]
        }]
    }
}

def test_extract_sku_files():
    result = extract_sku_files(SAMPLE_SCAN)
    assert result.sku == "F5714D05U-K11"
    assert result.brand == "Friboo"
    assert result.color == "Navy"
    assert result.silhouette == "sneaker"
    assert result.raw_scan_filename == "2c7265d7-0089-4044-8d05-bca28639cd28.glb"
    assert result.touchedup_filename == "27d51ba0-2e90-490b-ba82-281b8f4c6604.glb"
    assert result.autoshadow_filename == "8806197c-44cf-4cbc-b2c0-522ab8067bd1.glb"

def test_extract_sku_files_no_iterations():
    scan = {
        "glbFilename": "raw.glb",
        "laterality": "left",
        "product": {
            "modelCode": "TEST-SKU",
            "clientTags": [{"key": "clientSku", "value": "TEST-SKU"}],
            "versions": []
        }
    }
    with pytest.raises(ValueError, match="No published version"):
        extract_sku_files(scan)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tomislavbelacic/shoe-qa && python -m pytest tests/test_dashboard_api.py -v`
Expected: FAIL

- [ ] **Step 3: Implement dashboard_api.py**

```python
# backend/dashboard_api.py
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
    """Extract the 3 GLB filenames from a scan API response."""
    product = scan.get("product", {})
    
    # Get SKU from clientTags
    sku = product.get("modelCode", "")
    for tag in product.get("clientTags", []):
        if tag.get("key") == "clientSku":
            sku = tag["value"]
            break
    
    brand = product.get("brand", "Unknown")
    color = product.get("color", "Unknown")
    silhouette = product.get("silhouette", "Unknown")
    raw_scan_filename = scan.get("glbFilename", "")
    
    # Find latest version with left shoe touch-up iteration
    versions = product.get("versions", [])
    if not versions:
        raise ValueError(f"No published version found for {sku}")
    
    touchedup = None
    autoshadow = None
    
    # Search versions in reverse (latest first)
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
    
    return ScanData(
        sku=sku,
        brand=brand,
        color=color,
        silhouette=silhouette,
        raw_scan_filename=raw_scan_filename,
        touchedup_filename=touchedup,
        autoshadow_filename=autoshadow,
        scan_id=scan.get("id", "")
    )

async def find_scan_by_sku(api_base: str, api_key: str, sku: str) -> ScanData:
    """Query ShopAR /api/scans to find a scan by SKU."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try search parameter first
        resp = await client.get(
            f"{api_base}/scans",
            headers={"x-api-key": api_key},
            params={"search": sku}
        )
        resp.raise_for_status()
        data = resp.json()
        
        docs = data.get("docs", [])
        
        # Find matching scan (left shoe with matching SKU)
        for scan in docs:
            if scan.get("laterality") != "left":
                continue
            product = scan.get("product", {})
            for tag in product.get("clientTags", []):
                if tag.get("key") == "clientSku" and tag.get("value", "").upper() == sku.upper():
                    return extract_sku_files(scan)
            # Also check modelCode
            if product.get("modelCode", "").upper() == sku.upper():
                return extract_sku_files(scan)
        
        raise ValueError(f"No scan found for SKU: {sku}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tomislavbelacic/shoe-qa && python -m pytest tests/test_dashboard_api.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add backend/dashboard_api.py tests/test_dashboard_api.py
git commit -m "feat: ShopAR dashboard API client with SKU lookup"
```

---

### Task 4: Download & Decrypt (downloader.py)

**Files:**
- Create: `backend/downloader.py`

- [ ] **Step 1: Implement downloader.py**

```python
# backend/downloader.py
import os
import httpx
from backend.crypto import decrypt_glb, is_valid_glb

async def download_and_decrypt(url: str, output_path: str, on_progress=None) -> str:
    """Download GLB from CloudFront URL, decrypt, and save."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        encrypted_data = resp.content
    
    if on_progress:
        await on_progress(f"Downloaded {len(encrypted_data) / 1024 / 1024:.1f} MB")
    
    if is_valid_glb(encrypted_data):
        decrypted_data = encrypted_data
    else:
        decrypted_data = decrypt_glb(encrypted_data)
    
    if not is_valid_glb(decrypted_data):
        raise ValueError(f"Decryption failed — output is not valid glTF")
    
    with open(output_path, 'wb') as f:
        f.write(decrypted_data)
    
    if on_progress:
        await on_progress(f"Saved to {output_path}")
    
    return output_path

async def download_sku_models(
    cloudfront_base: str,
    raw_filename: str,
    touchedup_filename: str,
    autoshadow_filename: str,
    output_dir: str,
    on_progress=None
) -> tuple[str, str, str]:
    """Download and decrypt all 3 GLBs for a SKU."""
    raw_path = os.path.join(output_dir, "raw_scan.glb")
    touchedup_path = os.path.join(output_dir, "touched_up.glb")
    autoshadow_path = os.path.join(output_dir, "autoshadow.glb")
    
    if on_progress:
        await on_progress("Downloading raw scan...")
    raw_url = f"{cloudfront_base}/{raw_filename}"
    await download_and_decrypt(raw_url, raw_path, on_progress)
    
    if on_progress:
        await on_progress("Downloading touched-up model...")
    touchedup_url = f"{cloudfront_base}/{touchedup_filename}"
    await download_and_decrypt(touchedup_url, touchedup_path, on_progress)
    
    if on_progress:
        await on_progress("Downloading autoshadow model...")
    autoshadow_url = f"{cloudfront_base}/{autoshadow_filename}"
    await download_and_decrypt(autoshadow_url, autoshadow_path, on_progress)
    
    return raw_path, touchedup_path, autoshadow_path
```

- [ ] **Step 2: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add backend/downloader.py
git commit -m "feat: GLB download and decrypt from CloudFront"
```

---

### Task 5: Storage & Session Management (storage.py)

**Files:**
- Create: `backend/storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write test for session creation**

```python
# tests/test_storage.py
import os
import tempfile
import pytest
import asyncio
from backend.storage import Storage

@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d

def test_create_session(tmp_dir):
    storage = Storage(tmp_dir)
    path = storage.create_session("F5714D05U-K11")
    assert os.path.isdir(path)
    assert "F5714D05U-K11" in path
    # Should have textures, screenshots, issues subdirs
    assert os.path.isdir(os.path.join(path, "textures"))
    assert os.path.isdir(os.path.join(path, "screenshots"))
    assert os.path.isdir(os.path.join(path, "issues"))

def test_list_reports(tmp_dir):
    storage = Storage(tmp_dir)
    storage.create_session("SKU-A")
    storage.create_session("SKU-B")
    storage.create_session("SKU-A")  # second session for same SKU
    reports = storage.list_reports()
    assert len(reports) == 3
    sku_a_reports = [r for r in reports if r["sku"] == "SKU-A"]
    assert len(sku_a_reports) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tomislavbelacic/shoe-qa && python -m pytest tests/test_storage.py -v`
Expected: FAIL

- [ ] **Step 3: Implement storage.py**

```python
# backend/storage.py
import os
import json
from datetime import datetime

class Storage:
    def __init__(self, reports_dir: str):
        self.reports_dir = reports_dir
        os.makedirs(reports_dir, exist_ok=True)
    
    def create_session(self, sku: str) -> str:
        """Create a new session directory for a SKU analysis."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        session_dir = os.path.join(self.reports_dir, sku, timestamp)
        os.makedirs(session_dir, exist_ok=True)
        os.makedirs(os.path.join(session_dir, "textures"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "screenshots"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "issues"), exist_ok=True)
        
        # Write initial metadata
        metadata = {
            "sku": sku,
            "created_at": datetime.now().isoformat(),
            "status": "in_progress"
        }
        with open(os.path.join(session_dir, "metadata.json"), 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return session_dir
    
    def save_metadata(self, session_dir: str, metadata: dict):
        """Update metadata for a session."""
        path = os.path.join(session_dir, "metadata.json")
        with open(path, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    def list_reports(self) -> list[dict]:
        """List all reports across all SKUs."""
        reports = []
        if not os.path.isdir(self.reports_dir):
            return reports
        
        for sku in sorted(os.listdir(self.reports_dir)):
            sku_dir = os.path.join(self.reports_dir, sku)
            if not os.path.isdir(sku_dir):
                continue
            for session in sorted(os.listdir(sku_dir), reverse=True):
                session_dir = os.path.join(sku_dir, session)
                if not os.path.isdir(session_dir):
                    continue
                meta_path = os.path.join(session_dir, "metadata.json")
                meta = {}
                if os.path.exists(meta_path):
                    with open(meta_path) as f:
                        meta = json.load(f)
                reports.append({
                    "sku": sku,
                    "session": session,
                    "path": session_dir,
                    "has_report": os.path.exists(os.path.join(session_dir, "report.html")),
                    **meta
                })
        return reports
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tomislavbelacic/shoe-qa && python -m pytest tests/test_storage.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add backend/storage.py tests/test_storage.py
git commit -m "feat: session storage with SKU-organized directories"
```

---

### Task 6: Blender Geometry Analyzer (blender/geometry_analyzer.py)

**Files:**
- Create: `blender/geometry_analyzer.py`
- Create: `backend/blender_runner.py`

This script runs INSIDE Blender headless — it uses `bpy` and outputs JSON to stdout.

- [ ] **Step 1: Implement geometry_analyzer.py**

```python
# blender/geometry_analyzer.py
"""
Geometry analysis script for Blender headless.
Usage: blender -b -P geometry_analyzer.py -- --glb_path /path/to.glb --output /path/to/results.json
"""
import bpy
import bmesh
import json
import sys
import os
import math
from mathutils import Vector

def get_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb_path", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv)

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

def import_glb(path):
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    return meshes

def analyze_mesh(obj):
    """Analyze a single mesh object for geometry issues."""
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.normal_update()
    
    result = {
        "name": obj.name,
        "vertices": len(bm.verts),
        "faces": len(bm.faces),
        "edges": len(bm.edges),
    }
    
    # Bounding box
    bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    mins = [min(v[i] for v in bbox) for i in range(3)]
    maxs = [max(v[i] for v in bbox) for i in range(3)]
    result["bounding_box"] = {
        "min": mins,
        "max": maxs,
        "size": [maxs[i] - mins[i] for i in range(3)]
    }
    
    # Flipped normals (faces where normal points inward)
    flipped = []
    for face in bm.faces:
        center = face.calc_center_median()
        # Check if normal points toward mesh center
        mesh_center = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
        to_center = (mesh_center - center).normalized()
        if face.normal.dot(to_center) > 0.5:
            flipped.append({
                "face_index": face.index,
                "center": [center.x, center.y, center.z],
                "normal": [face.normal.x, face.normal.y, face.normal.z]
            })
    result["flipped_normals"] = flipped
    result["flipped_normals_count"] = len(flipped)
    
    # Non-manifold edges
    non_manifold = []
    for edge in bm.edges:
        if not edge.is_manifold and not edge.is_boundary:
            center = (edge.verts[0].co + edge.verts[1].co) / 2
            non_manifold.append({
                "edge_index": edge.index,
                "center": [center.x, center.y, center.z]
            })
    result["non_manifold_edges"] = non_manifold
    result["non_manifold_count"] = len(non_manifold)
    
    # Loose vertices
    loose = [{"index": v.index, "co": [v.co.x, v.co.y, v.co.z]}
             for v in bm.verts if not v.link_edges]
    result["loose_vertices"] = loose
    result["loose_vertices_count"] = len(loose)
    
    # UV analysis
    uv_layers = mesh.uv_layers
    result["uv_layer_count"] = len(uv_layers)
    
    if uv_layers:
        uv_layer = bm.loops.layers.uv.active
        if uv_layer:
            negative_uvs = []
            for face in bm.faces:
                for loop in face.loops:
                    uv = loop[uv_layer].uv
                    if uv.x < 0 or uv.y < 0:
                        center = face.calc_center_median()
                        negative_uvs.append({
                            "face_index": face.index,
                            "uv": [uv.x, uv.y],
                            "center": [center.x, center.y, center.z]
                        })
            result["negative_uv_coords"] = negative_uvs[:50]  # Cap at 50
            result["negative_uv_count"] = len(negative_uvs)
            
            # UV overlap detection (simplified — check for duplicate UV positions)
            uv_positions = {}
            overlaps = 0
            for face in bm.faces:
                face_uvs = tuple(
                    (round(loop[uv_layer].uv.x, 4), round(loop[uv_layer].uv.y, 4))
                    for loop in face.loops
                )
                key = face_uvs
                if key in uv_positions:
                    overlaps += 1
                else:
                    uv_positions[key] = face.index
            result["uv_overlap_count"] = overlaps
    
    # Material slots
    result["material_count"] = len(mesh.materials)
    result["materials"] = [
        {"name": mat.name if mat else "None", "index": i}
        for i, mat in enumerate(mesh.materials)
    ]
    
    bm.free()
    return result

def analyze_textures(obj):
    """Check texture resolutions for all materials."""
    textures = []
    for mat in obj.data.materials:
        if not mat or not mat.node_tree:
            continue
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                img = node.image
                textures.append({
                    "name": img.name,
                    "width": img.size[0],
                    "height": img.size[1],
                    "is_4k": img.size[0] == 4096 and img.size[1] == 4096
                })
    return textures

def main():
    args = get_args()
    clear_scene()
    
    meshes = import_glb(args.glb_path)
    
    if not meshes:
        result = {"error": "No meshes found in GLB"}
    else:
        # Analyze the main mesh (largest by face count)
        main_mesh = max(meshes, key=lambda o: len(o.data.polygons))
        
        result = analyze_mesh(main_mesh)
        result["textures"] = analyze_textures(main_mesh)
        result["total_meshes"] = len(meshes)
        result["file_path"] = args.glb_path
        result["file_size_mb"] = os.path.getsize(args.glb_path) / (1024 * 1024)
    
    # Count total issues
    result["total_issues"] = (
        result.get("flipped_normals_count", 0) +
        result.get("non_manifold_count", 0) +
        result.get("loose_vertices_count", 0) +
        result.get("negative_uv_count", 0) +
        result.get("uv_overlap_count", 0)
    )
    
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"GEOMETRY_ANALYSIS_COMPLETE: {args.output}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Implement blender_runner.py**

```python
# backend/blender_runner.py
import subprocess
import json
import os

def run_blender_script(blender_path: str, script_path: str, args: list[str], timeout: int = 300) -> str:
    """Run a Python script inside Blender headless. Returns stdout."""
    cmd = [blender_path, "-b", "-P", script_path, "--"] + args
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout
    )
    
    if result.returncode != 0:
        raise RuntimeError(
            f"Blender script failed (exit {result.returncode}):\n"
            f"STDOUT: {result.stdout[-2000:]}\n"
            f"STDERR: {result.stderr[-2000:]}"
        )
    
    return result.stdout

def run_geometry_analysis(blender_path: str, glb_path: str, output_json: str) -> dict:
    """Run geometry analysis on a GLB file. Returns parsed JSON results."""
    script_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "blender")
    script_path = os.path.join(script_dir, "geometry_analyzer.py")
    
    run_blender_script(blender_path, script_path, [
        "--glb_path", glb_path,
        "--output", output_json
    ])
    
    with open(output_json) as f:
        return json.load(f)

def run_texture_extraction(blender_path: str, glb_path: str, output_dir: str) -> dict:
    """Extract PBR textures from a GLB file. Returns parsed JSON results."""
    script_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "blender")
    script_path = os.path.join(script_dir, "texture_extractor.py")
    
    output_json = os.path.join(output_dir, "extraction_result.json")
    
    run_blender_script(blender_path, script_path, [
        "--glb_path", glb_path,
        "--output_dir", output_dir,
        "--output_json", output_json
    ])
    
    with open(output_json) as f:
        return json.load(f)

def run_issue_renderer(blender_path: str, glb_path: str, issues_json: str, output_dir: str) -> dict:
    """Render camera-to-issue screenshots. Returns parsed JSON results."""
    script_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "blender")
    script_path = os.path.join(script_dir, "issue_renderer.py")
    
    output_json = os.path.join(output_dir, "render_result.json")
    
    run_blender_script(blender_path, script_path, [
        "--glb_path", glb_path,
        "--issues_json", issues_json,
        "--output_dir", output_dir,
        "--output_json", output_json
    ], timeout=600)
    
    with open(output_json) as f:
        return json.load(f)
```

- [ ] **Step 3: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add blender/geometry_analyzer.py backend/blender_runner.py
git commit -m "feat: Blender headless geometry analyzer and runner"
```

---

### Task 7: Blender Texture Extractor (blender/texture_extractor.py)

**Files:**
- Create: `blender/texture_extractor.py`

- [ ] **Step 1: Implement texture_extractor.py**

```python
# blender/texture_extractor.py
"""
Extract PBR textures from GLB materials.
Usage: blender -b -P texture_extractor.py -- --glb_path /path/to.glb --output_dir /path/to/out --output_json /path/to/result.json
"""
import bpy
import json
import sys
import os

def get_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb_path", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--output_json", required=True)
    return parser.parse_args(argv)

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

def find_image_from_input(socket):
    """Follow node connections back to find an image texture node."""
    if not socket.is_linked:
        return None
    node = socket.links[0].from_node
    
    if node.type == 'TEX_IMAGE' and node.image:
        return node
    
    # Follow through Normal Map nodes
    if node.type == 'NORMAL_MAP':
        color_input = node.inputs.get("Color")
        if color_input:
            return find_image_from_input(color_input)
    
    # Follow through Separate RGB/XYZ
    if node.type in ('SEPARATE_COLOR', 'SEPRGB', 'SEPXYZ'):
        vec_input = node.inputs[0]
        if vec_input:
            return find_image_from_input(vec_input)
    
    # Follow through group nodes (glTF Settings for ORM)
    if node.type == 'GROUP':
        for input_socket in node.inputs:
            result = find_image_from_input(input_socket)
            if result:
                return result
    
    # Follow through any node with image inputs
    for input_socket in node.inputs:
        if input_socket.is_linked:
            result = find_image_from_input(input_socket)
            if result:
                return result
    
    return None

def extract_textures(mesh_obj, output_dir, prefix):
    """Extract PBR textures from mesh materials."""
    results = {}
    
    for mat in mesh_obj.data.materials:
        if not mat or not mat.node_tree:
            continue
        
        # Find Principled BSDF
        bsdf = None
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                bsdf = node
                break
        
        if not bsdf:
            continue
        
        # Map of texture type -> BSDF input name
        texture_map = {
            "basecolor": "Base Color",
            "normal": "Normal",
            "roughness": "Roughness",
            "metallic": "Metallic",
        }
        
        for tex_name, input_name in texture_map.items():
            input_socket = bsdf.inputs.get(input_name)
            if not input_socket:
                continue
            
            img_node = find_image_from_input(input_socket)
            if not img_node or not img_node.image:
                continue
            
            img = img_node.image
            output_path = os.path.join(output_dir, f"{prefix}_{tex_name}.png")
            
            # Save image
            img.filepath_raw = output_path
            img.file_format = 'PNG'
            img.save()
            
            results[tex_name] = {
                "path": output_path,
                "width": img.size[0],
                "height": img.size[1],
                "name": img.name
            }
        
        # Also try to extract ORM packed texture
        # Check for glTF Settings group node or ORM-like textures
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                name_lower = node.image.name.lower()
                if 'orm' in name_lower or 'occlusionroughnessmetallic' in name_lower:
                    img = node.image
                    output_path = os.path.join(output_dir, f"{prefix}_orm.png")
                    img.filepath_raw = output_path
                    img.file_format = 'PNG'
                    img.save()
                    results["orm"] = {
                        "path": output_path,
                        "width": img.size[0],
                        "height": img.size[1],
                        "name": img.name
                    }
        
        break  # Only process first material with BSDF
    
    return results

def main():
    args = get_args()
    os.makedirs(args.output_dir, exist_ok=True)
    
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=args.glb_path)
    
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    if not meshes:
        result = {"error": "No meshes found", "textures": {}}
    else:
        main_mesh = max(meshes, key=lambda o: len(o.data.polygons))
        
        # Determine prefix from filename
        basename = os.path.basename(args.glb_path).replace('.glb', '')
        textures = extract_textures(main_mesh, args.output_dir, basename)
        result = {"textures": textures, "mesh_name": main_mesh.name}
    
    with open(args.output_json, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"TEXTURE_EXTRACTION_COMPLETE: {args.output_json}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add blender/texture_extractor.py
git commit -m "feat: Blender PBR texture extractor"
```

---

### Task 8: Blender Issue Renderer (blender/issue_renderer.py)

**Files:**
- Create: `blender/issue_renderer.py`

- [ ] **Step 1: Implement issue_renderer.py**

```python
# blender/issue_renderer.py
"""
Render camera-to-issue screenshots with highlighted problem areas.
Usage: blender -b -P issue_renderer.py -- --glb_path /path/to.glb --issues_json /path/to/issues.json --output_dir /dir --output_json /result.json
"""
import bpy
import bmesh
import json
import sys
import os
import math
from mathutils import Vector

def get_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb_path", required=True)
    parser.add_argument("--issues_json", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--output_json", required=True)
    return parser.parse_args(argv)

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

def setup_render():
    """Configure render settings for issue screenshots."""
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.render.film_transparent = True
    
    # Add basic lighting
    bpy.ops.object.light_add(type='SUN', location=(2, -2, 5))
    sun = bpy.context.active_object
    sun.data.energy = 3.0

def create_highlight_material():
    """Create a bright red semi-transparent material for highlighting issues."""
    mat = bpy.data.materials.new("QA_Highlight")
    mat.use_nodes = True
    mat.blend_method = 'BLEND'
    nodes = mat.node_tree.nodes
    nodes.clear()
    
    output = nodes.new('ShaderNodeOutputMaterial')
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (1.0, 0.0, 0.0, 1.0)
    bsdf.inputs['Alpha'].default_value = 0.7
    
    mat.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    return mat

def point_camera_at(target: Vector, distance: float = 0.3):
    """Create and position camera looking at target point."""
    cam_data = bpy.data.cameras.new("QA_Camera")
    cam_data.lens = 50
    cam_obj = bpy.data.objects.new("QA_Camera", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    
    # Position camera offset from target
    cam_obj.location = target + Vector((distance, -distance, distance * 0.7))
    
    # Point at target
    direction = target - cam_obj.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    cam_obj.rotation_euler = rot_quat.to_euler()
    
    bpy.context.scene.camera = cam_obj
    return cam_obj

def render_issue(obj, face_indices, issue_name, output_dir):
    """Highlight specific faces and render a screenshot."""
    # Duplicate the mesh for highlighting
    highlight_mat = create_highlight_material()
    
    # Create bmesh to select faces
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    
    # Calculate centroid of problem faces
    centers = []
    for idx in face_indices:
        if idx < len(bm.faces):
            centers.append(bm.faces[idx].calc_center_median())
    
    bm.free()
    
    if not centers:
        return None
    
    centroid = sum(centers, Vector()) / len(centers)
    # Transform to world space
    centroid = obj.matrix_world @ centroid
    
    # Point camera at the issue
    cam = point_camera_at(centroid)
    
    # Render
    output_path = os.path.join(output_dir, f"{issue_name}.png")
    bpy.context.scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)
    
    # Cleanup camera
    bpy.data.objects.remove(cam)
    
    return output_path

def main():
    args = get_args()
    os.makedirs(args.output_dir, exist_ok=True)
    
    with open(args.issues_json) as f:
        issues = json.load(f)
    
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=args.glb_path)
    setup_render()
    
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    if not meshes:
        with open(args.output_json, 'w') as f:
            json.dump({"error": "No meshes", "renders": []}, f)
        return
    
    main_mesh = max(meshes, key=lambda o: len(o.data.polygons))
    renders = []
    
    # Render flipped normals
    flipped = issues.get("flipped_normals", [])
    if flipped:
        face_indices = [f["face_index"] for f in flipped]
        path = render_issue(main_mesh, face_indices, "flipped_normals", args.output_dir)
        if path:
            renders.append({"type": "flipped_normals", "path": path, "count": len(flipped)})
    
    # Render negative UV faces
    neg_uvs = issues.get("negative_uv_coords", [])
    if neg_uvs:
        face_indices = [f["face_index"] for f in neg_uvs]
        path = render_issue(main_mesh, face_indices, "negative_uv", args.output_dir)
        if path:
            renders.append({"type": "negative_uv", "path": path, "count": len(neg_uvs)})
    
    # Render non-manifold edges area
    non_manifold = issues.get("non_manifold_edges", [])
    if non_manifold:
        # Use nearby faces for non-manifold edges
        centers = [Vector(e["center"]) for e in non_manifold[:20]]
        centroid = sum(centers, Vector()) / len(centers)
        centroid = main_mesh.matrix_world @ centroid
        cam = point_camera_at(centroid)
        path = os.path.join(args.output_dir, "non_manifold.png")
        bpy.context.scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(cam)
        renders.append({"type": "non_manifold", "path": path, "count": len(non_manifold)})
    
    with open(args.output_json, 'w') as f:
        json.dump({"renders": renders}, f, indent=2)
    
    print(f"ISSUE_RENDER_COMPLETE: {args.output_json}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add blender/issue_renderer.py
git commit -m "feat: Blender issue renderer with camera-to-problem localization"
```

---

### Task 9: Texture Comparison Engine (backend/texture_compare.py)

**Files:**
- Create: `backend/texture_compare.py`
- Create: `tests/test_texture_compare.py`

- [ ] **Step 1: Write test for texture comparison**

```python
# tests/test_texture_compare.py
import numpy as np
from PIL import Image
import tempfile
import os
from backend.texture_compare import compare_textures, TextureDiff

def test_identical_textures():
    """Identical textures should have 0% difference."""
    img = np.full((256, 256, 3), 128, dtype=np.uint8)
    with tempfile.TemporaryDirectory() as d:
        path_a = os.path.join(d, "a.png")
        path_b = os.path.join(d, "b.png")
        Image.fromarray(img).save(path_a)
        Image.fromarray(img).save(path_b)
        
        result = compare_textures(path_a, path_b, d, "test")
    
    assert result.pct_changed == 0.0
    assert result.max_diff == 0
    assert result.mean_diff == 0.0

def test_different_textures():
    """Changed region should be detected."""
    img_a = np.full((256, 256, 3), 128, dtype=np.uint8)
    img_b = img_a.copy()
    img_b[100:150, 100:150] = 255  # Change a 50x50 block
    
    with tempfile.TemporaryDirectory() as d:
        path_a = os.path.join(d, "a.png")
        path_b = os.path.join(d, "b.png")
        Image.fromarray(img_a).save(path_a)
        Image.fromarray(img_b).save(path_b)
        
        result = compare_textures(path_a, path_b, d, "test")
    
    assert result.pct_changed > 0
    assert result.max_diff == 127
    assert os.path.exists(result.heatmap_path)
    assert os.path.exists(result.overlay_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tomislavbelacic/shoe-qa && python -m pytest tests/test_texture_compare.py -v`
Expected: FAIL

- [ ] **Step 3: Implement texture_compare.py**

```python
# backend/texture_compare.py
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import os
from dataclasses import dataclass

@dataclass
class TextureDiff:
    pct_changed: float
    max_diff: int
    mean_diff: float
    heatmap_path: str
    overlay_path: str
    side_by_side_path: str
    changed_regions: list  # List of (x, y, w, h) bounding boxes

def compare_textures(path_a: str, path_b: str, output_dir: str, name: str) -> TextureDiff:
    """Compare two texture images pixel-by-pixel. Generate visual diffs."""
    img_a = np.array(Image.open(path_a).convert('RGB'))
    img_b = np.array(Image.open(path_b).convert('RGB'))
    
    # Resize if different dimensions
    if img_a.shape != img_b.shape:
        h = max(img_a.shape[0], img_b.shape[0])
        w = max(img_a.shape[1], img_b.shape[1])
        img_a_resized = np.array(Image.fromarray(img_a).resize((w, h)))
        img_b_resized = np.array(Image.fromarray(img_b).resize((w, h)))
    else:
        img_a_resized = img_a
        img_b_resized = img_b
    
    # Compute per-pixel absolute difference
    diff = np.abs(img_a_resized.astype(np.int16) - img_b_resized.astype(np.int16)).astype(np.uint8)
    diff_gray = np.max(diff, axis=2)  # Max channel diff per pixel
    
    # Stats
    threshold = 5  # Ignore tiny differences (compression artifacts)
    changed_mask = diff_gray > threshold
    total_pixels = diff_gray.size
    changed_pixels = np.sum(changed_mask)
    
    pct_changed = round(changed_pixels / total_pixels * 100, 2)
    max_diff = int(np.max(diff_gray))
    mean_diff = round(float(np.mean(diff_gray[changed_mask])) if changed_pixels > 0 else 0, 2)
    
    # Generate heatmap (blue=minor, red=major)
    heatmap = np.zeros((*diff_gray.shape, 3), dtype=np.uint8)
    if max_diff > 0:
        normalized = (diff_gray.astype(np.float32) / max(max_diff, 1) * 255).astype(np.uint8)
        heatmap[:, :, 0] = normalized  # Red channel = diff intensity
        heatmap[:, :, 2] = 255 - normalized  # Blue channel = inverse
        # Zero out where no change
        heatmap[~changed_mask] = [0, 0, 0]
    
    heatmap_path = os.path.join(output_dir, f"{name}_heatmap.png")
    Image.fromarray(heatmap).save(heatmap_path)
    
    # Generate overlay (original with red outlines around changed regions)
    overlay_img = Image.fromarray(img_a_resized).copy()
    # Dilate the mask to get outlines
    mask_img = Image.fromarray((changed_mask * 255).astype(np.uint8))
    dilated = mask_img.filter(ImageFilter.MaxFilter(5))
    eroded = mask_img.filter(ImageFilter.MinFilter(5))
    outline = np.array(dilated).astype(np.int16) - np.array(eroded).astype(np.int16)
    outline = np.clip(outline, 0, 255).astype(np.uint8)
    
    # Apply red outline to overlay
    overlay_arr = np.array(overlay_img)
    outline_mask = outline > 128
    overlay_arr[outline_mask, 0] = 255  # Red
    overlay_arr[outline_mask, 1] = 0
    overlay_arr[outline_mask, 2] = 0
    
    overlay_path = os.path.join(output_dir, f"{name}_overlay.png")
    Image.fromarray(overlay_arr).save(overlay_path)
    
    # Side-by-side
    h = img_a_resized.shape[0]
    w = img_a_resized.shape[1]
    side_by_side = np.zeros((h, w * 3 + 20, 3), dtype=np.uint8)
    side_by_side[:, :w] = img_a_resized
    side_by_side[:, w+10:w*2+10] = img_b_resized
    # Put heatmap in third slot
    heatmap_resized = np.array(Image.fromarray(heatmap).resize((w, h)))
    side_by_side[:, w*2+20:] = heatmap_resized
    
    sbs_path = os.path.join(output_dir, f"{name}_sidebyside.png")
    Image.fromarray(side_by_side).save(sbs_path)
    
    # Find changed region bounding boxes (simplified)
    regions = find_changed_regions(changed_mask)
    
    return TextureDiff(
        pct_changed=pct_changed,
        max_diff=max_diff,
        mean_diff=mean_diff,
        heatmap_path=heatmap_path,
        overlay_path=overlay_path,
        side_by_side_path=sbs_path,
        changed_regions=regions
    )

def find_changed_regions(mask: np.ndarray, min_area: int = 100) -> list:
    """Find bounding boxes of changed regions using connected components."""
    from PIL import Image as PILImage
    
    # Simple approach: find contiguous regions by dilating and finding bounds
    mask_img = PILImage.fromarray((mask * 255).astype(np.uint8))
    # Dilate to merge nearby changes
    dilated = mask_img.filter(ImageFilter.MaxFilter(15))
    dilated_arr = np.array(dilated) > 128
    
    # Find bounding boxes of connected regions (simplified via row/col projection)
    regions = []
    rows = np.any(dilated_arr, axis=1)
    cols = np.any(dilated_arr, axis=0)
    
    if np.any(rows) and np.any(cols):
        y_min, y_max = np.where(rows)[0][[0, -1]]
        x_min, x_max = np.where(cols)[0][[0, -1]]
        area = (x_max - x_min) * (y_max - y_min)
        if area >= min_area:
            regions.append({
                "x": int(x_min), "y": int(y_min),
                "w": int(x_max - x_min), "h": int(y_max - y_min)
            })
    
    return regions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tomislavbelacic/shoe-qa && python -m pytest tests/test_texture_compare.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add backend/texture_compare.py tests/test_texture_compare.py
git commit -m "feat: texture comparison engine with heatmaps and overlays"
```

---

### Task 10: Playwright Screenshot Capture (backend/screenshot.py)

**Files:**
- Create: `backend/screenshot.py`

- [ ] **Step 1: Implement screenshot.py**

```python
# backend/screenshot.py
import asyncio
import os

async def capture_viewer_screenshots(
    viewer_url: str,
    glb_path: str,
    output_dir: str,
    prefix: str,
    api_key: str = None
) -> list[str]:
    """Load GLB in dashboard viewer and capture screenshots from multiple angles."""
    from playwright.async_api import async_playwright
    
    os.makedirs(output_dir, exist_ok=True)
    screenshots = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        
        # Navigate to viewer
        await page.goto(viewer_url, wait_until="networkidle", timeout=30000)
        
        # Wait for viewer to be ready
        await page.wait_for_timeout(3000)
        
        # Take screenshot of current view
        path = os.path.join(output_dir, f"{prefix}_default.png")
        await page.screenshot(path=path)
        screenshots.append(path)
        
        await browser.close()
    
    return screenshots

async def capture_local_glb_screenshots(
    glb_path: str,
    output_dir: str,
    prefix: str
) -> list[str]:
    """
    Capture screenshots of a local GLB using a simple three.js viewer.
    Fallback if dashboard viewer isn't accessible.
    """
    # For now, we'll use Blender renders as the screenshot source
    # This can be enhanced later with a local three.js viewer
    return []
```

- [ ] **Step 2: Install Playwright browsers**

Run: `python -m playwright install chromium`

- [ ] **Step 3: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add backend/screenshot.py
git commit -m "feat: Playwright screenshot capture for web preview"
```

---

### Task 11: HTML Report Generator (report_generator.py + template)

**Files:**
- Create: `backend/report_generator.py`
- Create: `templates/report_template.html`

- [ ] **Step 1: Create Jinja2 report template**

Create `templates/report_template.html` — a self-contained HTML file with embedded CSS that renders:
- Header with SKU, brand, color, silhouette, date
- Summary stats table (3 columns: raw / touched-up / autoshadow)
- Issues section with expandable cards and embedded screenshots
- Texture comparison section with side-by-side, heatmaps, overlays per map type
- Web preview screenshot grid
- Geometry detail tables

All images embedded as base64 `data:image/png;base64,...` URIs.

The template should be clean, professional, dark-themed (matching dashboard aesthetic), with collapsible sections using pure CSS/JS (no external dependencies).

- [ ] **Step 2: Implement report_generator.py**

```python
# backend/report_generator.py
import base64
import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

def image_to_base64(path: str) -> str:
    """Convert an image file to a base64 data URI."""
    if not path or not os.path.exists(path):
        return ""
    with open(path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('utf-8')
    ext = os.path.splitext(path)[1].lstrip('.')
    if ext == 'jpg':
        ext = 'jpeg'
    return f"data:image/{ext};base64,{data}"

def generate_report(
    session_dir: str,
    scan_data: dict,
    geometry_results: dict,  # {raw: {...}, touchedup: {...}, autoshadow: {...}}
    texture_diffs: dict,     # {basecolor: {raw_vs_touchedup: TextureDiff, ...}, ...}
    issue_renders: list,
    screenshots: dict,
    template_dir: str
) -> str:
    """Generate an HTML QA report and save to session_dir/report.html."""
    env = Environment(loader=FileSystemLoader(template_dir))
    env.filters['b64'] = image_to_base64
    
    template = env.get_template("report_template.html")
    
    # Prepare texture diff data with base64 images
    texture_sections = {}
    for tex_type, comparisons in texture_diffs.items():
        section = {}
        for comp_name, diff in comparisons.items():
            section[comp_name] = {
                "pct_changed": diff.pct_changed,
                "max_diff": diff.max_diff,
                "mean_diff": diff.mean_diff,
                "heatmap": image_to_base64(diff.heatmap_path),
                "overlay": image_to_base64(diff.overlay_path),
                "side_by_side": image_to_base64(diff.side_by_side_path),
                "regions": diff.changed_regions
            }
        texture_sections[tex_type] = section
    
    # Prepare issue renders with base64
    issues_with_images = []
    for issue in issue_renders:
        issues_with_images.append({
            **issue,
            "image": image_to_base64(issue.get("path", ""))
        })
    
    html = template.render(
        sku=scan_data.get("sku", "Unknown"),
        brand=scan_data.get("brand", "Unknown"),
        color=scan_data.get("color", "Unknown"),
        silhouette=scan_data.get("silhouette", "Unknown"),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        geometry=geometry_results,
        textures=texture_sections,
        issues=issues_with_images,
        screenshots={k: image_to_base64(v) for k, v in screenshots.items()} if screenshots else {},
    )
    
    output_path = os.path.join(session_dir, "report.html")
    with open(output_path, 'w') as f:
        f.write(html)
    
    return output_path
```

- [ ] **Step 3: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add backend/report_generator.py templates/report_template.html
git commit -m "feat: HTML report generator with Jinja2 templates"
```

---

### Task 12: Pipeline Orchestrator (backend/pipeline.py)

**Files:**
- Create: `backend/pipeline.py`

- [ ] **Step 1: Implement pipeline.py**

```python
# backend/pipeline.py
import asyncio
import json
import os
from typing import Callable, Awaitable

from backend.config import Config
from backend.dashboard_api import find_scan_by_sku, ScanData
from backend.downloader import download_sku_models
from backend.blender_runner import run_geometry_analysis, run_texture_extraction, run_issue_renderer
from backend.texture_compare import compare_textures
from backend.report_generator import generate_report
from backend.storage import Storage

async def run_qa_pipeline(
    config: Config,
    sku: str,
    on_progress: Callable[[str], Awaitable[None]] = None
):
    """Run the full QA pipeline for a SKU."""
    storage = Storage(config.reports_dir)
    
    async def progress(msg: str):
        if on_progress:
            await on_progress(msg)
    
    # Step 1: Find scan
    await progress(f"Looking up SKU {sku} on dashboard...")
    scan_data = await find_scan_by_sku(config.dashboard_api, config.api_key, sku)
    await progress(f"Found: {scan_data.brand} {scan_data.sku} ({scan_data.color}, {scan_data.silhouette})")
    
    # Step 2: Create session
    session_dir = storage.create_session(sku)
    await progress(f"Session: {session_dir}")
    
    # Step 3: Download & decrypt
    raw_path, touchedup_path, autoshadow_path = await download_sku_models(
        config.cloudfront_base,
        scan_data.raw_scan_filename,
        scan_data.touchedup_filename,
        scan_data.autoshadow_filename,
        session_dir,
        on_progress=progress
    )
    
    # Step 4: Geometry analysis
    await progress("Running Blender geometry analysis on raw scan...")
    raw_geom = run_geometry_analysis(
        config.blender_path, raw_path,
        os.path.join(session_dir, "geometry_raw.json")
    )
    
    await progress("Running Blender geometry analysis on touched-up...")
    touchedup_geom = run_geometry_analysis(
        config.blender_path, touchedup_path,
        os.path.join(session_dir, "geometry_touchedup.json")
    )
    
    await progress("Running Blender geometry analysis on autoshadow...")
    autoshadow_geom = run_geometry_analysis(
        config.blender_path, autoshadow_path,
        os.path.join(session_dir, "geometry_autoshadow.json")
    )
    
    geometry_results = {
        "raw": raw_geom,
        "touchedup": touchedup_geom,
        "autoshadow": autoshadow_geom
    }
    
    # Step 5: Extract textures
    await progress("Extracting textures from raw scan...")
    tex_dir = os.path.join(session_dir, "textures")
    raw_tex = run_texture_extraction(config.blender_path, raw_path, tex_dir)
    
    await progress("Extracting textures from touched-up...")
    touchedup_tex = run_texture_extraction(config.blender_path, touchedup_path, tex_dir)
    
    await progress("Extracting textures from autoshadow...")
    autoshadow_tex = run_texture_extraction(config.blender_path, autoshadow_path, tex_dir)
    
    # Step 6: Texture comparison
    await progress("Comparing textures...")
    texture_diffs = {}
    
    for tex_type in ["basecolor", "normal", "roughness", "metallic"]:
        raw_t = raw_tex.get("textures", {}).get(tex_type, {}).get("path")
        touchedup_t = touchedup_tex.get("textures", {}).get(tex_type, {}).get("path")
        autoshadow_t = autoshadow_tex.get("textures", {}).get(tex_type, {}).get("path")
        
        comparisons = {}
        if raw_t and touchedup_t:
            comparisons["raw_vs_touchedup"] = compare_textures(
                raw_t, touchedup_t, tex_dir, f"{tex_type}_raw_vs_touchedup"
            )
        if touchedup_t and autoshadow_t:
            comparisons["touchedup_vs_autoshadow"] = compare_textures(
                touchedup_t, autoshadow_t, tex_dir, f"{tex_type}_touchedup_vs_autoshadow"
            )
        
        if comparisons:
            texture_diffs[tex_type] = comparisons
    
    # Step 7: Render issue screenshots
    await progress("Rendering issue screenshots...")
    issue_renders = []
    issues_dir = os.path.join(session_dir, "issues")
    
    for model_name, geom in [("raw", raw_geom), ("touchedup", touchedup_geom), ("autoshadow", autoshadow_geom)]:
        if geom.get("total_issues", 0) > 0:
            model_path = {"raw": raw_path, "touchedup": touchedup_path, "autoshadow": autoshadow_path}[model_name]
            issues_json = os.path.join(session_dir, f"geometry_{model_name}.json")
            try:
                render_result = run_issue_renderer(
                    config.blender_path, model_path, issues_json, issues_dir
                )
                for render in render_result.get("renders", []):
                    render["model"] = model_name
                    issue_renders.append(render)
            except Exception as e:
                await progress(f"Warning: Issue rendering failed for {model_name}: {e}")
    
    # Step 8: Generate report
    await progress("Generating HTML report...")
    template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
    
    report_path = generate_report(
        session_dir=session_dir,
        scan_data={
            "sku": scan_data.sku,
            "brand": scan_data.brand,
            "color": scan_data.color,
            "silhouette": scan_data.silhouette
        },
        geometry_results=geometry_results,
        texture_diffs=texture_diffs,
        issue_renders=issue_renders,
        screenshots={},
        template_dir=template_dir
    )
    
    # Update metadata
    storage.save_metadata(session_dir, {
        "sku": scan_data.sku,
        "brand": scan_data.brand,
        "color": scan_data.color,
        "silhouette": scan_data.silhouette,
        "created_at": os.path.basename(session_dir),
        "status": "complete",
        "total_issues": sum(g.get("total_issues", 0) for g in [raw_geom, touchedup_geom, autoshadow_geom]),
        "report_path": report_path
    })
    
    await progress(f"Report ready: {report_path}")
    return report_path
```

- [ ] **Step 2: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add backend/pipeline.py
git commit -m "feat: QA pipeline orchestrator"
```

---

### Task 13: FastAPI Backend (backend/main.py)

**Files:**
- Create: `backend/main.py`

- [ ] **Step 1: Implement main.py**

```python
# backend/main.py
import asyncio
import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from starlette.responses import StreamingResponse
from backend.config import load_config
from backend.pipeline import run_qa_pipeline
from backend.storage import Storage

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
config = load_config(CONFIG_PATH)
storage = Storage(config.reports_dir)

app = FastAPI(title="Shoe QA")

# Serve frontend
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# Track running jobs
jobs: dict[str, dict] = {}

@app.get("/")
async def index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.get("/reports")
async def reports_page():
    return FileResponse(os.path.join(frontend_dir, "reports.html"))

@app.post("/api/analyze/{sku}")
async def start_analysis(sku: str):
    """Start QA analysis for a SKU. Returns job ID."""
    sku = sku.strip().upper()
    if sku in jobs and jobs[sku].get("status") == "running":
        raise HTTPException(400, f"Analysis already running for {sku}")
    
    jobs[sku] = {"status": "running", "messages": [], "result": None}
    
    async def run():
        try:
            async def on_progress(msg):
                jobs[sku]["messages"].append(msg)
            
            report_path = await run_qa_pipeline(config, sku, on_progress)
            jobs[sku]["status"] = "complete"
            jobs[sku]["result"] = report_path
        except Exception as e:
            jobs[sku]["status"] = "error"
            jobs[sku]["messages"].append(f"Error: {str(e)}")
    
    asyncio.create_task(run())
    return {"job_id": sku, "status": "started"}

@app.get("/api/status/{sku}")
async def job_status(sku: str):
    """SSE stream of progress messages for a running job."""
    sku = sku.strip().upper()
    
    async def event_stream():
        sent = 0
        while True:
            job = jobs.get(sku)
            if not job:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Job not found'})}\n\n"
                break
            
            # Send new messages
            while sent < len(job["messages"]):
                msg = job["messages"][sent]
                yield f"data: {json.dumps({'type': 'progress', 'message': msg})}\n\n"
                sent += 1
            
            if job["status"] == "complete":
                yield f"data: {json.dumps({'type': 'complete', 'report': job['result']})}\n\n"
                break
            elif job["status"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': 'Pipeline failed'})}\n\n"
                break
            
            await asyncio.sleep(0.5)
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/api/reports")
async def list_reports():
    """List all past QA reports."""
    return storage.list_reports()

@app.get("/api/reports/{sku}/{session}/report.html")
async def get_report(sku: str, session: str):
    """Serve a generated HTML report."""
    report_path = os.path.join(config.reports_dir, sku, session, "report.html")
    if not os.path.exists(report_path):
        raise HTTPException(404, "Report not found")
    return FileResponse(report_path, media_type="text/html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.port)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add backend/main.py
git commit -m "feat: FastAPI backend with SSE progress and report serving"
```

---

### Task 14: Frontend (HTML/CSS/JS)

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/reports.html`
- Create: `frontend/style.css`
- Create: `frontend/app.js`

- [ ] **Step 1: Implement frontend files**

`frontend/index.html` — Main page with SKU input, analyze button, and live progress feed via SSE.

`frontend/reports.html` — Library page showing past reports grouped by SKU with timestamps, issue counts, and links to open/download reports.

`frontend/style.css` — Dark theme matching the ShopAR dashboard aesthetic. Clean, functional.

`frontend/app.js` — SSE listener for `/api/status/{sku}`, fetch calls for `/api/analyze/{sku}` and `/api/reports`.

- [ ] **Step 2: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add frontend/
git commit -m "feat: frontend UI with SKU input, progress feed, and report library"
```

---

### Task 15: Report HTML Template

**Files:**
- Create: `templates/report_template.html`

- [ ] **Step 1: Implement report Jinja2 template**

Full self-contained HTML with:
- Dark theme, professional layout
- Collapsible sections (pure CSS/JS)
- Summary stats table
- Issues with embedded screenshots
- Texture comparison grids with heatmaps and overlays
- Image zoom on click
- All images as base64 data URIs

- [ ] **Step 2: Commit**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add templates/report_template.html
git commit -m "feat: QA report HTML template with visual comparisons"
```

---

### Task 16: Integration Test — End-to-End

- [ ] **Step 1: Run the full app**

```bash
cd /Users/tomislavbelacic/shoe-qa
python -m backend.main
```

- [ ] **Step 2: Test with a real SKU**

Open `http://localhost:8080` in browser. Enter `F5714D05U-K11`. Click Analyze. Verify:
- Progress messages stream in
- Models download and decrypt
- Blender analysis runs
- Textures extracted and compared
- Report generated and viewable

- [ ] **Step 3: Verify report quality**

Check the HTML report:
- All texture comparisons show visual diffs
- Issue screenshots are localized correctly
- Stats are accurate
- Report is self-contained (works when saved and opened standalone)

- [ ] **Step 4: Fix any issues found during testing**

- [ ] **Step 5: Commit final fixes**

```bash
cd /Users/tomislavbelacic/shoe-qa
git add -A
git commit -m "fix: integration test fixes"
```
