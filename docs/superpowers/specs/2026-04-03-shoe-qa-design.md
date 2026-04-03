# Shoe QA — GLB Model Quality Analysis System

## Overview

Web-based application for automated quality analysis of 3D shoe models (GLB). Enter a SKU, the system downloads 3 model variants from the ShopAR dashboard, runs geometry and texture analysis via Blender headless, and generates a visual HTML report with localized issue screenshots.

## Problem

QA of 3D shoe models is manual — artists and QA reviewers visually inspect models in the dashboard viewer without automated checks for geometry issues (flipped normals, UV problems) or systematic texture comparison between pipeline stages. This misses subtle issues and doesn't scale.

## Three Models Compared

For each SKU (left shoe only), three pipeline stages are compared:

1. **Raw scan** — Original geometry from Covision scanner (`scan.glbFilename`)
2. **Touched-up** — Artist's manual fixes (`iteration.previewFilename`)
3. **AutoShadow** — Autoshadow script applied to touched-up model (`iteration.autoShadowFilename`)

## Architecture

```
Browser UI (HTML/CSS/JS)
    │
    │ REST API + SSE (progress)
    ▼
FastAPI Backend (Python)
    │
    ├── ShopAR Dashboard API (/api/scans)
    ├── Blender 4.58 headless (subprocess)
    └── Playwright (web preview screenshots)
```

### Tech Stack

- **Backend**: Python 3.12+ / FastAPI / uvicorn
- **Frontend**: Plain HTML/CSS/JS (no framework)
- **Background jobs**: asyncio tasks
- **Blender**: 4.58, launched as subprocess with analysis scripts
- **Image processing**: NumPy + Pillow
- **Screenshots**: Playwright
- **Reports**: Jinja2 HTML templates with base64-embedded images
- **Storage**: Filesystem + SQLite index

## Dashboard API Integration

### Authentication

API key passed as header:
```
x-api-key: {configured_api_key}
```

### SKU Lookup

```
GET https://dashboard.shopar.ai/api/scans?search={SKU}
```

From the response, find the scan where `product.clientTags[]` contains `key === "clientSku"` matching the input SKU.

### Extracting GLB Filenames

From the matched scan document:

- **Raw scan**: `scan.glbFilename`
- **Touched-up**: Find left shoe task with `method === "covision_scan_touch_up"`, get `iterations[last].previewFilename`
- **AutoShadow**: Same iteration, `iterations[last].autoShadowFilename`

### Download & Decrypt

All files served encrypted from CloudFront:
```
https://dj5e08oeu5ym4.cloudfront.net/3e/{filename}
```

Decryption: XOR cipher with Xorshift32 PRNG, seeded by file size in bytes.

```python
def decrypt(data: bytes) -> bytes:
    n = len(data)
    rng_state = int32(n)
    random_bytes = np.zeros(n, dtype=np.uint8)
    for i in range(n):
        rng_state = int32(rng_state ^ int32(rng_state << 13))
        rng_state = int32(rng_state ^ int32(rng_state >> 17))
        rng_state = int32(rng_state ^ int32(rng_state << 5))
        random_bytes[i] = rng_state & 0xFF
    return np.bitwise_xor(np.frombuffer(data, np.uint8), random_bytes).tobytes()
```

Validation: Check first 4 bytes are `glTF` magic (0x67, 0x6C, 0x54, 0x46).

## QA Analysis Pipeline

### Step 1: Geometry Analysis (Blender Headless)

For each of the 3 models, Blender script analyzes:

**Per-model checks:**
- Vertex count, face count
- Bounding box dimensions
- Flipped normals detection (faces with inverted normals)
- Non-manifold edges
- Loose vertices
- UV map validation:
  - UV overlaps (faces sharing UV space)
  - Negative UV coordinates (outside 0-1 range, prevents baking)
  - UV island count
- Material slot count and names
- Texture resolution check (flag if not 4096x4096)

**Cross-model comparison:**
- Vertex/face count delta between stages
- Bounding box size changes
- File size comparison

**Issue localization:**
When a problem is detected:
1. Calculate centroid of affected faces
2. Point camera at the centroid, framed to show the issue
3. Apply red overlay material to problem faces
4. Dim the rest of the model (semi-transparent)
5. Render zoomed-in evidence screenshot + full-model context shot

Output: JSON results + issue screenshot PNGs.

### Step 2: Texture Extraction (Blender Headless)

Extract PBR maps from each model's materials:
- Base color map
- Normal map
- Roughness map (from ORM packed texture)
- Metallic map (from ORM packed texture)

Follows Principled BSDF input connections, handles glTF Settings group nodes for ORM unpacking.

### Step 3: Texture Comparison (Python — NumPy/Pillow)

For each texture type, two comparisons:
- Raw scan vs Touched-up
- Touched-up vs AutoShadow

**Outputs per comparison:**
- **Side-by-side** — All 3 versions at full resolution
- **Pixel-level diff heatmap** — Color-coded by difference intensity (blue=minor, red=major)
- **Marked overlay** — Original texture with red outlines around modified regions
- **3D localized view** — Map changed UV regions back to 3D positions, render camera pointed at affected area on the model

**Stats per comparison:**
- Percentage of pixels changed
- Max pixel difference
- Mean pixel difference
- Affected region locations

### Step 4: Web Preview Screenshots (Playwright)

Load each GLB into the dashboard viewer:
```
https://dashboard.shopar.ai/admin/viewer
```

Capture 4 angles per model:
- Front view
- Side view
- Back view
- Top-down view

3 models x 4 angles = 12 screenshots, arranged in comparison grid.

## HTML Report

Self-contained HTML file with all images embedded as base64.

### Sections:

1. **Header** — SKU, brand, color, silhouette, generation date
2. **Summary table** — Side-by-side stats for all 3 models (vertices, faces, file size, texture res, issue count)
3. **Issues** — Expandable cards per issue, each with:
   - Issue type and severity
   - 3D localized screenshot (camera pointed at problem)
   - UV/texture view with region marked
   - Face count affected
4. **Texture Comparison** — Per map type (basecolor, normal, roughness, metallic):
   - Three-way side-by-side
   - Diff heatmaps
   - Marked overlays showing changed regions
   - Stats (% changed, max diff, mean diff)
5. **Web Preview Screenshots** — 3x4 comparison grid
6. **Geometry Details** — Full stats per model

## Web UI

### Main Page
- SKU text input + "Analyze" button
- Live progress feed via SSE showing pipeline steps
- Link to report when complete

### Reports/Library Page
- List of past reports grouped by SKU
- Each SKU shows history of analysis sessions
- Click to open HTML report
- Download button for sharing
- Search/filter by SKU

## Local Storage

```
~/ShoeQA/
├── reports/
│   ├── {SKU}/
│   │   ├── {YYYY-MM-DD_HHMMSS}/
│   │   │   ├── report.html
│   │   │   ├── raw_scan.glb
│   │   │   ├── touched_up.glb
│   │   │   ├── autoshadow.glb
│   │   │   ├── textures/
│   │   │   │   ├── raw_basecolor.png
│   │   │   │   ├── raw_normal.png
│   │   │   │   ├── raw_roughness.png
│   │   │   │   ├── raw_metallic.png
│   │   │   │   ├── touchedup_basecolor.png
│   │   │   │   ├── ... (all 3 models)
│   │   │   │   ├── diff_basecolor_raw_vs_touchedup.png
│   │   │   │   └── ... (diffs for all types)
│   │   │   ├── screenshots/
│   │   │   │   ├── raw_front.png
│   │   │   │   └── ...
│   │   │   ├── issues/
│   │   │   │   ├── issue_001_flipped_normals.png
│   │   │   │   └── ...
│   │   │   └── metadata.json
│   │   └── {another_session}/
│   └── {another_SKU}/
├── config.json
└── shoe_qa.db              ← SQLite index
```

- Organized by SKU then timestamp
- Re-analyzing same SKU creates new session, preserves history
- Raw GLBs kept for manual Blender inspection
- SQLite indexes metadata for fast search/filter in web UI

## Project Structure

```
shoe-qa/
├── backend/
│   ├── main.py                 ← FastAPI app, routes, SSE
│   ├── dashboard_api.py        ← ShopAR API client
│   ├── downloader.py           ← Download + decrypt GLBs
│   ├── crypto.py               ← XOR/Xorshift32 decryption
│   ├── blender_analysis.py     ← Subprocess launcher
│   ├── texture_compare.py      ← NumPy/Pillow diff engine
│   ├── screenshot.py           ← Playwright capture
│   ├── report_generator.py     ← HTML report builder
│   ├── storage.py              ← File organization + SQLite
│   └── config.py               ← Settings
├── blender/
│   ├── geometry_analyzer.py    ← Geometry QA (runs in Blender)
│   ├── texture_extractor.py    ← PBR map extraction
│   └── issue_renderer.py       ← Camera-to-issue screenshots
├── frontend/
│   ├── index.html              ← SKU input + progress
│   ├── reports.html            ← Library/archive
│   ├── style.css
│   └── app.js                  ← SSE + fetch
├── templates/
│   └── report_template.html    ← Jinja2 report template
├── config.json
├── requirements.txt
└── README.md
```

## Dependencies

```
fastapi
uvicorn
numpy
Pillow
playwright
jinja2
aiosqlite
httpx
```

No dependency on existing ShopAR repos. Decryption algorithm ported directly.

## Configuration

`config.json`:
```json
{
  "api_key": "...",
  "cloudfront_base": "https://dj5e08oeu5ym4.cloudfront.net/3e",
  "dashboard_api": "https://dashboard.shopar.ai/api",
  "dashboard_viewer": "https://dashboard.shopar.ai/admin/viewer",
  "blender_path": "/Applications/Blender 4.58.app/Contents/MacOS/Blender",
  "reports_dir": "~/ShoeQA/reports",
  "port": 8080
}
```
