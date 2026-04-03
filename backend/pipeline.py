import asyncio
import json
import os
from typing import Callable, Awaitable
from backend.config import Config
from backend.dashboard_api import find_scan_by_sku, ScanData
from backend.downloader import download_and_decrypt
from backend.blender_runner import run_geometry_analysis, run_texture_extraction, run_issue_renderer
from backend.texture_compare import compare_textures
from backend.report_generator import generate_report
from backend.storage import Storage


async def run_qa_pipeline(
    config: Config, sku: str,
    on_progress: Callable[[str], Awaitable[None]] = None,
    urls: dict = None,
    metadata: dict = None,
):
    """Run QA pipeline. If urls dict provided, skip API lookup and download directly.
    urls format: {"raw": "cloudfront_url", "touchedup": "cloudfront_url", "autoshadow": "cloudfront_url"}
    metadata format: {"brand": "...", "color": "...", "silhouette": "..."}
    """
    storage = Storage(config.reports_dir)

    async def progress(msg: str):
        if on_progress:
            await on_progress(msg)

    scan_info = {"sku": sku, "brand": "Unknown", "color": "Unknown", "silhouette": "Unknown"}
    if metadata:
        scan_info.update({k: v for k, v in metadata.items() if v and v != "Unknown"})

    if urls:
        # Direct URL mode — skip API lookup
        await progress(f"Using provided URLs for {sku}")
    else:
        # API mode — try to look up scan data
        try:
            await progress(f"Looking up SKU {sku} on dashboard...")
            scan_data = await find_scan_by_sku(config.dashboard_api, config.api_key, sku)
            await progress(f"Found: {scan_data.brand} {scan_data.sku} ({scan_data.color}, {scan_data.silhouette})")
            scan_info = {"sku": scan_data.sku, "brand": scan_data.brand, "color": scan_data.color, "silhouette": scan_data.silhouette}
            urls = {
                "raw": f"{config.cloudfront_base}/{scan_data.raw_scan_filename}",
                "touchedup": f"{config.cloudfront_base}/{scan_data.touchedup_filename}",
                "autoshadow": f"{config.cloudfront_base}/{scan_data.autoshadow_filename}",
            }
        except Exception as e:
            raise ValueError(f"API lookup failed: {e}. Use URL mode instead.")

    # Step 2: Create session
    session_dir = storage.create_session(sku)
    await progress("Session created")

    # Step 3: Download & decrypt from URLs
    raw_path = os.path.join(session_dir, "raw_scan.glb")
    touchedup_path = os.path.join(session_dir, "touched_up.glb")
    autoshadow_path = os.path.join(session_dir, "autoshadow.glb")

    for label, url_key, out_path in [
        ("raw scan", "raw", raw_path),
        ("touched-up", "touchedup", touchedup_path),
        ("autoshadow", "autoshadow", autoshadow_path),
    ]:
        try:
            await progress(f"Downloading {label}...")
            await download_and_decrypt(urls[url_key], out_path, progress)
        except Exception as e:
            raise ValueError(f"Failed to download {label}: {e}")

    # Step 4: Geometry analysis
    await progress("Running Blender geometry analysis on raw scan...")
    raw_geom = run_geometry_analysis(config.blender_path, raw_path, os.path.join(session_dir, "geometry_raw.json"))
    await progress(f"Raw scan: {raw_geom.get('vertices', 0)} verts, {raw_geom.get('total_issues', 0)} issues")

    await progress("Running Blender geometry analysis on touched-up...")
    touchedup_geom = run_geometry_analysis(config.blender_path, touchedup_path, os.path.join(session_dir, "geometry_touchedup.json"))
    await progress(f"Touched-up: {touchedup_geom.get('vertices', 0)} verts, {touchedup_geom.get('total_issues', 0)} issues")

    await progress("Running Blender geometry analysis on autoshadow...")
    autoshadow_geom = run_geometry_analysis(config.blender_path, autoshadow_path, os.path.join(session_dir, "geometry_autoshadow.json"))
    await progress(f"AutoShadow: {autoshadow_geom.get('vertices', 0)} verts, {autoshadow_geom.get('total_issues', 0)} issues")

    geometry_results = {"raw": raw_geom, "touchedup": touchedup_geom, "autoshadow": autoshadow_geom}

    # Step 5: Extract textures (with error resilience)
    tex_dir = os.path.join(session_dir, "textures")

    raw_tex = {"textures": {}}
    touchedup_tex = {"textures": {}}
    autoshadow_tex = {"textures": {}}

    for label, path, result_ref in [
        ("raw scan", raw_path, "raw"),
        ("touched-up", touchedup_path, "touchedup"),
        ("autoshadow", autoshadow_path, "autoshadow"),
    ]:
        try:
            await progress(f"Extracting textures from {label}...")
            tex_result = run_texture_extraction(config.blender_path, path, tex_dir)
            if result_ref == "raw":
                raw_tex = tex_result
            elif result_ref == "touchedup":
                touchedup_tex = tex_result
            else:
                autoshadow_tex = tex_result
            tex_count = len(tex_result.get("textures", {}))
            await progress(f"  Extracted {tex_count} textures from {label}")
        except Exception as e:
            await progress(f"Warning: Texture extraction failed for {label}: {e}")

    # Step 6: Texture comparison
    await progress("Comparing textures...")
    texture_diffs = {}
    for tex_type in ["basecolor", "normal", "roughness", "metallic"]:
        raw_t = raw_tex.get("textures", {}).get(tex_type, {}).get("path")
        touchedup_t = touchedup_tex.get("textures", {}).get(tex_type, {}).get("path")
        autoshadow_t = autoshadow_tex.get("textures", {}).get(tex_type, {}).get("path")
        comparisons = {}
        if raw_t and touchedup_t:
            comparisons["raw_vs_touchedup"] = compare_textures(raw_t, touchedup_t, tex_dir, f"{tex_type}_raw_vs_touchedup")
        if touchedup_t and autoshadow_t:
            comparisons["touchedup_vs_autoshadow"] = compare_textures(touchedup_t, autoshadow_t, tex_dir, f"{tex_type}_touchedup_vs_autoshadow")
        if comparisons:
            texture_diffs[tex_type] = comparisons
    await progress(f"Texture comparison complete: {len(texture_diffs)} map types analyzed")

    # Step 7: Render issue screenshots
    await progress("Rendering issue screenshots...")
    issue_renders = []
    issues_dir = os.path.join(session_dir, "issues")
    for model_name, geom, model_path in [
        ("raw", raw_geom, raw_path),
        ("touchedup", touchedup_geom, touchedup_path),
        ("autoshadow", autoshadow_geom, autoshadow_path)
    ]:
        if geom.get("total_issues", 0) > 0:
            issues_json = os.path.join(session_dir, f"geometry_{model_name}.json")
            try:
                render_result = run_issue_renderer(config.blender_path, model_path, issues_json, issues_dir)
                for render in render_result.get("renders", []):
                    render["model"] = model_name
                    issue_renders.append(render)
            except Exception as e:
                await progress(f"Warning: Issue rendering failed for {model_name}: {e}")

    # Step 8: Generate report
    await progress("Generating HTML report...")
    template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
    report_path = generate_report(
        session_dir=session_dir,
        scan_data=scan_info,
        geometry_results=geometry_results,
        texture_diffs=texture_diffs,
        issue_renders=issue_renders,
        screenshots={},
        template_dir=template_dir)

    storage.save_metadata(session_dir, {
        **scan_info, "created_at": os.path.basename(session_dir),
        "status": "complete",
        "total_issues": sum(g.get("total_issues", 0) for g in [raw_geom, touchedup_geom, autoshadow_geom]),
        "report_path": report_path})

    await progress(f"Report ready!")
    return report_path, session_dir
