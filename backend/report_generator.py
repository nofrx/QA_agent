import base64
import os
from datetime import datetime
from io import BytesIO
from PIL import Image
from jinja2 import Environment, FileSystemLoader

MAX_EMBED_SIZE = 1024  # Max dimension for images embedded in HTML report


def image_to_base64(path: str, max_size: int = MAX_EMBED_SIZE) -> str:
    """Convert an image file to a resized base64 data URI string."""
    if not path or not os.path.exists(path):
        return ""
    try:
        img = Image.open(path)
        # Resize if larger than max_size
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
    """Assign severity: critical / warning / info."""
    if count == 0:
        return "clean"
    if issue_type == "flipped_normals":
        return "critical" if count > 50 else "warning" if count > 5 else "info"
    if issue_type == "negative_uv":
        return "critical"  # Always critical — prevents baking
    if issue_type == "out_of_range_uv":
        return "warning"
    if issue_type == "non_manifold":
        return "critical" if count > 100 else "warning" if count > 10 else "info"
    if issue_type == "loose_vertices":
        return "info"
    return "info"


def build_geometry_summary(geometry_results: dict) -> dict:
    """Build a clean summary with severity levels for the report."""
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
            issues.append({
                "label": label,
                "count": count,
                "severity": severity,
            })

        # Texture resolution check
        tex_warning = None
        for t in geom.get("textures", []):
            if not t.get("is_4k"):
                tex_warning = f"{t['name']} is {t['width']}x{t['height']} (not 4K)"
                break

        summary[model_key] = {
            "vertices": geom.get("vertices", 0),
            "faces": geom.get("faces", 0),
            "file_size_mb": geom.get("file_size_mb", 0),
            "material_count": geom.get("material_count", 0),
            "total_issues": geom.get("total_issues", 0),
            "issues": issues,
            "textures": geom.get("textures", []),
            "tex_warning": tex_warning,
            "bounding_box": geom.get("bounding_box", {}),
        }
    return summary


def build_texture_summary(texture_diffs: dict) -> dict:
    """Build texture comparison data with embedded images."""
    sections = {}
    for tex_type, comparisons in texture_diffs.items():
        section = {}
        for comp_name, diff in comparisons.items():
            # Only show meaningful changes (above noise)
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
                "heatmap": image_to_base64(diff.heatmap_path),
                "overlay": image_to_base64(diff.overlay_path),
                "side_by_side": image_to_base64(diff.side_by_side_path),
                "regions": diff.changed_regions,
            }
        sections[tex_type] = section
    return sections


def build_multi_view_sections(multi_view_renders: list) -> dict:
    """Organise multi-view renders into a nested dict for the template.

    Returns:
      {
        "material":          { view: { model: b64, ... }, ... },
        "face_orientation":  { view: { model: b64, ... }, ... },
        "basecolor":         { "34": { model: b64, ... } },
        "normal":            { ... },
        "roughness":         { ... },
        "metallic":          { ... },
      }
    """
    sections: dict = {}
    for render in (multi_view_renders or []):
        channel = render.get("channel", "")
        view = render.get("view", "")
        model = render.get("model", "")
        path = render.get("path", "")
        b64 = image_to_base64(path, max_size=512)
        if not b64:
            continue
        sections.setdefault(channel, {}).setdefault(view, {})[model] = b64
    return sections


def generate_report(
    session_dir, scan_data, geometry_results, texture_diffs,
    issue_renders, screenshots, template_dir, qa_report=None,
    multi_view_renders=None,
):
    """Generate an HTML QA report with embedded images and QA findings."""
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)
    env.filters['b64'] = image_to_base64
    template = env.get_template("report_template.html")

    geometry_summary = build_geometry_summary(geometry_results)
    texture_sections = build_texture_summary(texture_diffs)
    visual_sections = build_multi_view_sections(multi_view_renders)

    # Build issue screenshots map for linking to findings
    issue_images = {}
    for issue in (issue_renders or []):
        img = image_to_base64(issue.get("path", ""))
        if img:
            issue_images[issue.get("type", "")] = img

    # Convert QA findings to template-friendly dicts
    findings_list = []
    if qa_report:
        for f in qa_report.findings:
            finding_dict = {
                "rule_id": f.rule_id,
                "severity": f.severity,
                "title": f.title,
                "explanation": f.explanation,
                "recommendation": f.recommendation,
                "model": f.model,
                "data": f.data,
                "image": issue_images.get(f.rule_id, ""),
            }
            findings_list.append(finding_dict)

    html = template.render(
        sku=scan_data.get("sku", "Unknown"),
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
        issue_images=issue_images,
        screenshots={k: image_to_base64(v) for k, v in screenshots.items()} if screenshots else {},
        visual=visual_sections,
    )

    output_path = os.path.join(session_dir, "report.html")
    with open(output_path, 'w') as f:
        f.write(html)
    return output_path
