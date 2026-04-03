import base64
import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader


def image_to_base64(path: str) -> str:
    """Convert an image file to a base64 data URI string."""
    if not path or not os.path.exists(path):
        return ""
    with open(path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('utf-8')
    ext = os.path.splitext(path)[1].lstrip('.')
    if ext == 'jpg':
        ext = 'jpeg'
    return f"data:image/{ext};base64,{data}"


def generate_report(
    session_dir, scan_data, geometry_results, texture_diffs,
    issue_renders, screenshots, template_dir
):
    """Generate an HTML QA report with embedded images."""
    env = Environment(loader=FileSystemLoader(template_dir))
    env.filters['b64'] = image_to_base64
    template = env.get_template("report_template.html")

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
