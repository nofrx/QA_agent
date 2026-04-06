import base64
import json
import os
from datetime import datetime
from io import BytesIO
from PIL import Image
from jinja2 import Environment, FileSystemLoader

MAX_EMBED_SIZE = 1024  # Max dimension for texture comparison images


def image_to_base64(path: str, max_size: int = MAX_EMBED_SIZE) -> str:
    """Convert an image file to a resized base64 data URI string."""
    if not path or not os.path.exists(path):
        return ""
    try:
        img = Image.open(path)
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        data = base64.b64encode(buf.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{data}"
    except Exception:
        return ""


def classify_issue_severity(issue_type: str, count: int) -> str:
    if count == 0:
        return "clean"
    if issue_type == "flipped_normals":
        return "critical" if count > 50 else "warning" if count > 5 else "info"
    if issue_type == "negative_uv":
        return "critical"
    if issue_type == "out_of_range_uv":
        return "warning"
    if issue_type == "non_manifold":
        return "critical" if count > 100 else "warning" if count > 10 else "info"
    if issue_type == "loose_vertices":
        return "info"
    return "info"


def build_geometry_summary(geometry_results: dict) -> dict:
    summary = {}
    for model_key in ["raw", "touchedup", "autoshadow"]:
        geom = geometry_results.get(model_key, {})
        issues = []
        for issue_key, label in [
            ("flipped_normals_count", "Flipped normals"),
            ("non_manifold_count", "Non-manifold edges"),
            ("loose_vertices_count", "Loose vertices"),
            ("negative_uv_count", "Negative UV coords"),
            ("out_of_range_uv_count", "Out-of-range UVs"),
        ]:
            count = geom.get(issue_key, 0)
            severity = classify_issue_severity(issue_key.replace("_count", ""), count)
            issues.append({"label": label, "count": count, "severity": severity})

        summary[model_key] = {
            "vertices": geom.get("vertices", 0),
            "faces": geom.get("faces", 0),
            "file_size_mb": geom.get("file_size_mb", 0),
            "material_count": geom.get("material_count", 0),
            "total_issues": geom.get("total_issues", 0),
            "issues": issues,
            "textures": geom.get("textures", []),
            "bounding_box": geom.get("bounding_box", {}),
        }
    return summary


def _image_url(path: str, sku: str, session: str) -> str:
    """Convert an image file path to a file-server URL, or empty string if missing."""
    if not path or not os.path.exists(path):
        return ""
    filename = os.path.basename(path)
    return f"/api/reports/{sku}/{session}/files/textures/{filename}"


def build_texture_summary(texture_diffs: dict, sku: str = "", session: str = "") -> dict:
    sections = {}
    for tex_type, comparisons in texture_diffs.items():
        section = {}
        for comp_name, diff in comparisons.items():
            is_meaningful = diff.pct_changed > 0.5 or diff.max_diff > 20
            res_note = ""
            if diff.resolution_mismatch:
                res_note = f"{diff.resolution_a[0]}x{diff.resolution_a[1]} vs {diff.resolution_b[0]}x{diff.resolution_b[1]}"
            section[comp_name] = {
                "pct_changed": diff.pct_changed,
                "max_diff": diff.max_diff,
                "mean_diff": diff.mean_diff,
                "is_meaningful": is_meaningful,
                "resolution_mismatch": diff.resolution_mismatch,
                "resolution_note": res_note,
                "heatmap": _image_url(diff.heatmap_path, sku, session),
                "overlay": _image_url(diff.overlay_path, sku, session),
                "side_by_side": _image_url(diff.side_by_side_path, sku, session),
                "regions": diff.changed_regions,
            }
        sections[tex_type] = section
    return sections


def build_issues_data(geometry_results: dict) -> dict:
    """Build per-model issue data including flipped normal positions for 3D overlay."""
    data = {}
    for model_key in ["raw", "touchedup", "autoshadow"]:
        geom = geometry_results.get(model_key, {})
        # Collect flipped normal positions + directions for viewer markers
        flipped = []
        for fn in geom.get("flipped_normals", []):
            flipped.append({
                "c": fn["center"],    # [x, y, z] position
                "n": fn["normal"],    # [nx, ny, nz] direction
            })
        data[model_key] = {
            "flipped_normals": geom.get("flipped_normals_count", 0),
            "flipped_positions": flipped,
            "non_manifold": geom.get("non_manifold_count", 0),
            "loose_vertices": geom.get("loose_vertices_count", 0),
            "negative_uv": geom.get("negative_uv_count", 0),
            "out_of_range_uv": geom.get("out_of_range_uv_count", 0),
        }
    return data


def generate_report(
    session_dir, scan_data, geometry_results, texture_diffs,
    qa_report, glb_urls, template_dir,
    # Legacy params kept for backward compatibility
    issue_renders=None, screenshots=None, multi_view_renders=None,
):
    """Generate an HTML QA report with embedded texture comparisons and interactive 3D viewer."""
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)
    env.filters['b64'] = image_to_base64
    template = env.get_template("report_template.html")

    sku = scan_data.get("sku", "Unknown")
    session_name = os.path.basename(session_dir)

    geometry_summary = build_geometry_summary(geometry_results)
    texture_sections = build_texture_summary(texture_diffs, sku=sku, session=session_name)
    issues_data = build_issues_data(geometry_results)

    findings_list = []
    if qa_report:
        for f in qa_report.findings:
            findings_list.append({
                "rule_id": f.rule_id,
                "severity": f.severity,
                "title": f.title,
                "explanation": f.explanation,
                "recommendation": f.recommendation,
                "model": f.model,
                "data": f.data,
            })

    html = template.render(
        sku=sku,
        brand=scan_data.get("brand", "Unknown"),
        color=scan_data.get("color", "Unknown"),
        silhouette=scan_data.get("silhouette", "Unknown"),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        geometry=geometry_summary,
        textures=texture_sections,
        findings=findings_list,
        verdict=qa_report.verdict if qa_report else "UNKNOWN",
        verdict_summary=qa_report.verdict_summary if qa_report else "",
        critical_count=qa_report.critical_count if qa_report else 0,
        warning_count=qa_report.warning_count if qa_report else 0,
        expected_count=qa_report.expected_count if qa_report else 0,
        glb_urls=glb_urls,
        issues_data=json.dumps(issues_data),
    )

    output_path = os.path.join(session_dir, "report.html")
    with open(output_path, 'w') as f:
        f.write(html)
    return output_path
