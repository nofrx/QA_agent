# QA Agent — Session Handoff Summary

**Repo**: https://github.com/nofrx/QA_agent  
**Working dir**: `/Users/tomislavbelacic/shoe-qa`  
**Reports dir**: `/Users/tomislavbelacic/ShoeQA/reports/`  
**Server**: `python3 -m uvicorn backend.main:app --port 8080`

---

## What This Is

A 3D shoe model QA analysis pipeline that downloads GLB models from the ShopAR dashboard, runs geometry + texture analysis via Blender, and generates an interactive HTML report with a Three.js 3D viewer.

## Architecture

```
frontend/          → Web UI (index.html, app.js, style.css, autoshadow.hdr)
backend/
  main.py          → FastAPI server (port 8080)
  pipeline.py      → Orchestrates: download → geometry → textures → compare → report
  dashboard_api.py → SKU lookup via Chrome/Safari AppleScript on dashboard.shopar.ai
  downloader.py    → Downloads + XOR decrypts GLBs from CloudFront (with SHA-256 URL cache)
  crypto.py        → Xorshift32 XOR decryption
  blender_runner.py→ Spawns Blender headless processes
  qa_analyzer.py   → Rules engine: geometry + texture → findings with severity
  qa_rules.py      → Rule definitions (expected vs problematic patterns)
  report_generator.py → Jinja2 HTML report with file-server texture URLs
  texture_compare.py  → Pixel-level texture diffing with heatmaps
  config.py        → Loads config.json (+ glb_cache_dir)
  storage.py       → Session directory management
blender/
  geometry_analyzer.py  → Blender script: vertex count, flipped normals, UVs, non-manifold
  texture_extractor.py  → Blender script: extracts PBR textures from GLB materials
templates/
  report_template.html → Full HTML report with embedded Three.js viewer
tests/               → 27 tests (pytest)
config.json          → API keys, Blender path, CloudFront base URL
```

## Pipeline Flow (parallel)

1. **SKU Lookup** — AppleScript JS injection into Chrome/Safari dashboard tab (falls back between browsers)
2. **Parallel Downloads** — 3 GLBs via `asyncio.gather` from CloudFront + XOR decrypt
3. **Parallel Geometry Analysis** — 3 concurrent Blender processes (flipped normals, UVs, non-manifold, loose verts)
4. **Parallel Texture Extraction** — 3 concurrent Blender processes (basecolor, normal, roughness, metallic)
5. **Parallel Texture Comparison** — pixel diffs with heatmaps for each channel pair
6. **QA Analysis** — rules engine produces PASS/NEEDS_REVIEW/FAIL verdict
7. **HTML Report** — Jinja2 template with Three.js viewer + texture comparison images

## Interactive 3D Viewer (in report)

- **Three.js** ES modules loaded via importmap from CDN (v0.165.0)
- **DRACOLoader** for Draco-compressed GLBs
- **RGBELoader** loads custom `autoshadow.hdr` environment map from `/static/`
- **3 model tabs**: Raw Scan / Touched-Up / AutoShadow
- **7 view modes**: Standard PBR, Base Color, Normal Map, Roughness, Metallic, Face Orientation, Wireframe
- **Face Orientation**: `gl_FrontFacing` shader (blue=correct, red=backfacing) + red dot/arrow markers at exact flipped normal positions from Blender geometry data
- **Base Color**: `MeshBasicMaterial` with `toneMapped: false` to prevent ACES double-darkening
- **Channel preview**: ShaderMaterial with swizzle for grayscale channels; tone mapping disabled in non-standard modes

## Key Technical Decisions

### QA Rules (Phase 1 fixes)
- Touched-up non-4K textures → **info** (intentional artist optimization, not a defect)
- AutoShadow file size larger → **info** (expected 2K→4K rebake behavior)
- AutoShadow non-4K → **warning** (it should always produce 4K output)
- UV reorganization + bake extend pixel notes added to raw→touchedup texture findings

### Face Orientation Detection
- Blender geometry analyzer uses **neighbor-comparison**: `face.normal.dot(avg_neighbor_normals) < -0.5`
- **Area-aware filtering**: each flipped face includes `area` and `relative_area` (fraction of total mesh surface)
- Faces below 0.01% of total mesh area are classified as "insignificant" (sub-pixel geometry artifacts)
- `significant_flipped_normals_count` is the primary metric; insignificant-only findings are severity="info" not "critical"
- 3D viewer markers only show for significant flipped normals
- GLB export normalizes vertex winding, so Three.js `gl_FrontFacing` can't detect flipped normals
- Solution: pass exact face center + normal positions from geometry JSON → render as red `ArrowHelper` markers

### Dashboard API Auth
- Primary: API key via `x-api-key` header (currently returns 403 — expired)
- Fallback: AppleScript JS injection into Chrome, then Safari — requires "Allow JavaScript from Apple Events" enabled in browser Developer menu
- SKU lookup uses Payload CMS `where[sku][equals]` query — instant lookup across all 34K+ assets (no pagination needed)

### Optional AutoShadow
- Pipeline gracefully handles SKUs without autoshadow models
- Downloads, geometry analysis, and texture extraction skip missing models
- Report viewer hides AutoShadow tab and geometry table column when unavailable

### Performance
- Downloads: parallel `asyncio.gather` (wall time = slowest file, not sum)
- Blender: parallel `run_in_executor` for geometry + texture extraction
- Removed Blender screenshot rendering entirely (replaced by interactive viewer)
- Local files mode: ~31s total (skipping downloads)
- With downloads: ~3-7min depending on connection (110MB autoshadow is the bottleneck)

## Running

```bash
cd /Users/tomislavbelacic/shoe-qa

# Start server
python3 -m uvicorn backend.main:app --port 8080

# Open http://localhost:8080, enter SKU, click Analyze
# Requires: dashboard.shopar.ai open + logged in in Chrome or Safari
# Requires: "Allow JavaScript from Apple Events" enabled in browser

# Run tests
python3 -m pytest tests/ -q

# Run analysis from CLI (local files, no download)
python3 -c "
import asyncio
from backend.config import load_config
from backend.pipeline import run_qa_pipeline
config = load_config('config.json')
asyncio.run(run_qa_pipeline(config, 'SKU_HERE', local_files={
    'raw': '/path/to/raw_scan.glb',
    'touchedup': '/path/to/touched_up.glb',
    'autoshadow': '/path/to/autoshadow.glb',
}))
"
```

## Blender Path

Set in `config.json` → `blender_path`. Currently points to the Blender 4.x binary. The scripts handle both EEVEE (3.x) and EEVEE_NEXT (4.x).

## Environment Map

Custom HDRI at `frontend/autoshadow.hdr` (332KB), served at `/static/autoshadow.hdr`. To swap: replace the file.

## Open Items / Next Steps

- API key needs renewal (currently 403)
- ~~Consider caching downloaded GLBs across sessions for the same SKU~~ ✓ Implemented — SHA-256 URL-keyed cache in `~/.shoe-qa-cache/glb/`, re-analysis skips downloads
- ~~The `multi_view_renderer.py` and `issue_renderer.py` Blender scripts are still in `/blender/` but no longer called from pipeline — can be deleted~~ ✓ Deleted, along with wrapper functions in `blender_runner.py`
- ~~Report file size is ~32MB due to embedded texture comparison heatmaps (base64 PNGs)~~ ✓ Fixed — heatmaps now served via file server route (`/api/reports/{sku}/{session}/files/textures/`) instead of base64 embedding
- Ralph loop prompt at `.ralph-prompt.md` has 2-iteration validation template
