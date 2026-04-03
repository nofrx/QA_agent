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


async def run_qa_pipeline(config: Config, sku: str, on_progress: Callable[[str], Awaitable[None]] = None):
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
    await progress(f"Session created")

    # Step 3: Download & decrypt
    raw_path, touchedup_path, autoshadow_path = await download_sku_models(
        config.cloudfront_base, scan_data.raw_scan_filename,
        scan_data.touchedup_filename, scan_data.autoshadow_filename,
        session_dir, on_progress=progress)

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

    # Step 5: Extract textures
    tex_dir = os.path.join(session_dir, "textures")
    await progress("Extracting textures from raw scan...")
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
        scan_data={"sku": scan_data.sku, "brand": scan_data.brand, "color": scan_data.color, "silhouette": scan_data.silhouette},
        geometry_results=geometry_results,
        texture_diffs=texture_diffs,
        issue_renders=issue_renders,
        screenshots={},
        template_dir=template_dir)

    storage.save_metadata(session_dir, {
        "sku": scan_data.sku, "brand": scan_data.brand, "color": scan_data.color,
        "silhouette": scan_data.silhouette, "created_at": os.path.basename(session_dir),
        "status": "complete",
        "total_issues": sum(g.get("total_issues", 0) for g in [raw_geom, touchedup_geom, autoshadow_geom]),
        "report_path": report_path})

    await progress(f"Report ready!")
    return report_path, session_dir
