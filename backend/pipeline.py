import asyncio
import json
import os
import time
from typing import Callable, Awaitable
from backend.config import Config
from backend.dashboard_api import find_scan_by_sku, ScanData
from backend.downloader import download_and_decrypt_cached
from backend.blender_runner import run_geometry_analysis, run_texture_extraction
from backend.texture_compare import compare_textures
from backend.report_generator import generate_report
from backend.qa_analyzer import analyze as run_qa_analysis
from backend.storage import Storage

# ─── Measured step timings (NE241A0IE-A11, sequential baseline) ───────────────
# Downloads (sequential):     ~90s  (3 × ~30s each, ~7-30MB files)
# Geometry analysis (seq):    ~90s  (3 × ~30s each Blender process)
# Texture extraction (seq):   ~60s  (3 × ~20s each Blender process)
# Texture comparison:         ~5s
# Issue renderer (removed):   ~60s  (now replaced by interactive viewer)
# Multi-view renders (removed): ~200s (18 Blender renders, now interactive viewer)
# Total before:               ~8-12min
# Total after parallel:       ~3-4min (downloads + blender run concurrently)


async def run_qa_pipeline(
    config: Config, sku: str,
    on_progress: Callable[[str], Awaitable[None]] = None,
    urls: dict = None,
    metadata: dict = None,
    local_files: dict = None,
    session_dir_override: str = None,
):
    """Run QA pipeline.
    Modes:
    - auto: look up SKU on dashboard, download from CloudFront
    - urls: download from provided CloudFront URLs
    - local_files: use already-saved local GLB files ({"raw": path, "autoshadow": path})
    """
    storage = Storage(config.reports_dir)

    async def progress(msg: str):
        if on_progress:
            await on_progress(msg)

    def _t(t0: float) -> str:
        return f"{time.time() - t0:.1f}s"

    start_time = time.time()

    scan_info = {"sku": sku, "brand": "Unknown", "color": "Unknown", "silhouette": "Unknown"}
    if metadata:
        scan_info.update({k: v for k, v in metadata.items() if v and v != "Unknown"})

    # ── Step 1-3: Resolve GLB paths ───────────────────────────────────────────
    if local_files:
        session_dir = session_dir_override or storage.create_session(sku)
        raw_path = local_files["raw"]
        autoshadow_path = local_files.get("autoshadow")

    else:
        if not urls:
            # API mode — look up scan data
            try:
                await progress(f"Looking up SKU {sku} on dashboard...")
                scan_data = await find_scan_by_sku(config.dashboard_api, config.api_key, sku)
                await progress(f"Found: {scan_data.brand} {scan_data.sku} ({scan_data.color}, {scan_data.silhouette})")
                scan_info = {"sku": scan_data.sku, "brand": scan_data.brand, "color": scan_data.color, "silhouette": scan_data.silhouette}
                urls = {}
                if scan_data.raw_scan_filename:
                    urls["raw"] = f"{config.cloudfront_base}/{scan_data.raw_scan_filename}"
                if scan_data.autoshadow_filename:
                    urls["autoshadow"] = f"{config.cloudfront_base}/{scan_data.autoshadow_filename}"
                if not urls.get("raw"):
                    raise ValueError(f"SKU {sku} is missing raw scan model")
            except Exception as e:
                raise ValueError(f"API lookup failed: {e}. Use URL mode instead.")
        else:
            await progress(f"Using provided URLs for {sku}")

        session_dir = session_dir_override or storage.create_session(sku)
        raw_path = os.path.join(session_dir, "raw_scan.glb")
        autoshadow_path = os.path.join(session_dir, "autoshadow.glb") if "autoshadow" in urls else None

        # ── Parallel downloads ─────────────────────────────────────────────────
        t0 = time.time()
        model_count = 1 + (1 if autoshadow_path else 0)
        await progress(f"Downloading {model_count} model{'s' if model_count > 1 else ''} in parallel...")

        async def _download(label, url_key, out_path):
            try:
                await download_and_decrypt_cached(urls[url_key], out_path, config.glb_cache_dir, progress)
            except Exception as e:
                raise ValueError(f"Failed to download {label}: {e}")

        download_tasks = [
            _download("raw scan", "raw", raw_path),
        ]
        if autoshadow_path:
            download_tasks.append(_download("autoshadow", "autoshadow", autoshadow_path))
        await asyncio.gather(*download_tasks)
        await progress(f"  Downloads done in {_t(t0)}")
        if not autoshadow_path:
            await progress("  Note: no autoshadow model available for this SKU")

    # ── Step 4: Parallel geometry analysis ────────────────────────────────────
    loop = asyncio.get_event_loop()
    t0 = time.time()
    model_count = 1 + (1 if autoshadow_path else 0)
    await progress(f"Analyzing geometry ({model_count} model{'s' if model_count > 1 else ''} in parallel)...")

    geom_tasks = [
        loop.run_in_executor(None, run_geometry_analysis, config.blender_path, raw_path,        os.path.join(session_dir, "geometry_raw.json")),
    ]
    if autoshadow_path:
        geom_tasks.append(loop.run_in_executor(None, run_geometry_analysis, config.blender_path, autoshadow_path, os.path.join(session_dir, "geometry_autoshadow.json")))

    geom_results_list = await asyncio.gather(*geom_tasks)
    raw_geom = geom_results_list[0]
    autoshadow_geom = geom_results_list[1] if autoshadow_path else {}

    await progress(f"  Raw: {raw_geom.get('vertices', 0):,} verts, {raw_geom.get('total_issues', 0)} issues")
    if autoshadow_path:
        await progress(f"  AutoShadow: {autoshadow_geom.get('vertices', 0):,} verts, {autoshadow_geom.get('total_issues', 0)} issues")
    await progress(f"  Geometry done in {_t(t0)}")

    geometry_results = {"raw": raw_geom, "autoshadow": autoshadow_geom}

    # ── Step 5: Parallel texture extraction ───────────────────────────────────
    tex_dir = os.path.join(session_dir, "textures")
    t0 = time.time()
    await progress(f"Extracting textures ({model_count} model{'s' if model_count > 1 else ''} in parallel)...")

    async def _extract(label, path):
        try:
            result = await loop.run_in_executor(None, run_texture_extraction, config.blender_path, path, tex_dir)
            await progress(f"  {label}: {len(result.get('textures', {}))} textures")
            return result
        except Exception as e:
            await progress(f"  {label}: extraction failed ({e})")
            return {"textures": {}}

    tex_tasks = [
        _extract("raw scan", raw_path),
    ]
    if autoshadow_path:
        tex_tasks.append(_extract("autoshadow", autoshadow_path))

    tex_results_list = await asyncio.gather(*tex_tasks)
    raw_tex = tex_results_list[0]
    autoshadow_tex = tex_results_list[1] if autoshadow_path else {"textures": {}}
    await progress(f"  Texture extraction done in {_t(t0)}")

    # ── Step 6: Texture comparison ────────────────────────────────────────────
    t0 = time.time()
    await progress("Comparing textures...")
    texture_diffs = {}

    async def _compare(tex_type):
        raw_t = raw_tex.get("textures", {}).get(tex_type, {}).get("path")
        autoshadow_t = autoshadow_tex.get("textures", {}).get(tex_type, {}).get("path")
        comparisons = {}
        tasks = []
        if raw_t and autoshadow_t:
            tasks.append(("raw_vs_autoshadow", loop.run_in_executor(None, compare_textures, raw_t, autoshadow_t, tex_dir, f"{tex_type}_raw_vs_autoshadow")))
        if tasks:
            results = await asyncio.gather(*[t for _, t in tasks])
            for (name, _), result in zip(tasks, results):
                comparisons[name] = result
        return tex_type, comparisons

    tex_results = await asyncio.gather(*[_compare(t) for t in ["basecolor", "normal", "roughness", "metallic"]])
    for tex_type, comparisons in tex_results:
        if comparisons:
            texture_diffs[tex_type] = comparisons
    await progress(f"  Texture comparison done in {_t(t0)} — {len(texture_diffs)} map types")

    # ── Step 7: QA analysis ───────────────────────────────────────────────────
    await progress("Running QA analysis...")
    qa_report = run_qa_analysis(geometry_results, texture_diffs)
    await progress(f"QA verdict: {qa_report.verdict} ({qa_report.critical_count} critical, {qa_report.warning_count} warnings, {qa_report.expected_count} expected)")

    # ── Step 8: Generate report ───────────────────────────────────────────────
    await progress("Generating HTML report...")
    template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")

    # Build GLB URLs for the interactive 3D viewer
    session_name = os.path.basename(session_dir)
    glb_urls = {
        "raw":        f"/api/reports/{sku}/{session_name}/files/raw_scan.glb",
    }
    if autoshadow_path:
        glb_urls["autoshadow"] = f"/api/reports/{sku}/{session_name}/files/autoshadow.glb"

    report_path = generate_report(
        session_dir=session_dir,
        scan_data=scan_info,
        geometry_results=geometry_results,
        texture_diffs=texture_diffs,
        qa_report=qa_report,
        glb_urls=glb_urls,
        template_dir=template_dir,
    )

    storage.save_metadata(session_dir, {
        **scan_info, "created_at": os.path.basename(session_dir),
        "status": "complete",
        "verdict": qa_report.verdict,
        "total_issues": qa_report.critical_count + qa_report.warning_count,
        "report_path": report_path})

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    await progress(f"Done in {minutes}m {seconds}s — verdict: {qa_report.verdict}")
    return report_path, session_dir
