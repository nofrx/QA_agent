"""
Smart QA Analyzer — applies rules to geometry and texture data,
produces findings with expert-level explanations.
"""
from dataclasses import dataclass, field
from backend.qa_rules import ALL_RULES, QARule


@dataclass
class Finding:
    rule_id: str
    severity: str          # critical, warning, info, expected
    title: str
    explanation: str
    recommendation: str
    model: str = ""        # raw, touchedup, autoshadow
    data: dict = field(default_factory=dict)
    has_screenshot: bool = False


@dataclass
class QAReport:
    verdict: str           # PASS, NEEDS_REVIEW, FAIL
    verdict_summary: str   # Human-readable summary
    findings: list         # List[Finding]
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    expected_count: int = 0


def analyze(geometry_results: dict, texture_diffs: dict, issue_renders: list = None) -> QAReport:
    """Run all QA rules against the data and produce a report with findings.
    issue_renders is kept for backward compatibility but no longer used.
    """
    findings = []

    # ─── Geometry analysis ────────────────────────────────
    for model_key, label in [("raw", "Raw scan"), ("touchedup", "Touched-up"), ("autoshadow", "AutoShadow")]:
        geom = geometry_results.get(model_key, {})
        findings.extend(_check_geometry(geom, model_key, label))

    # ─── File size analysis ───────────────────────────────
    findings.extend(_check_file_sizes(geometry_results))

    # ─── Texture resolution analysis ──────────────────────
    findings.extend(_check_texture_resolution(geometry_results))

    # ─── Texture comparison analysis ──────────────────────
    findings.extend(_check_texture_diffs(texture_diffs))

    # ─── Compute verdict ──────────────────────────────────
    critical = sum(1 for f in findings if f.severity == "critical")
    warnings = sum(1 for f in findings if f.severity == "warning")
    info = sum(1 for f in findings if f.severity == "info")
    expected = sum(1 for f in findings if f.severity == "expected")

    if critical > 0:
        verdict = "FAIL"
        verdict_summary = (
            f"{critical} critical issue{'s' if critical != 1 else ''} found that must be fixed before production. "
            f"Review the findings below and address all critical items."
        )
    elif warnings > 0:
        verdict = "NEEDS_REVIEW"
        verdict_summary = (
            f"{warnings} warning{'s' if warnings != 1 else ''} found. "
            f"A senior artist should review these before publishing."
        )
    else:
        verdict = "PASS"
        verdict_summary = "No critical issues or warnings. Model is ready for production."

    return QAReport(
        verdict=verdict,
        verdict_summary=verdict_summary,
        findings=findings,
        critical_count=critical,
        warning_count=warnings,
        info_count=info,
        expected_count=expected,
    )


def _check_geometry(geom: dict, model_key: str, label: str) -> list:
    """Check geometry rules for a single model."""
    findings = []
    if not geom or geom.get("error"):
        return findings

    # Flipped normals
    count = geom.get("flipped_normals_count", 0)
    if count > 0:
        rule = ALL_RULES["flipped_normals"]
        findings.append(Finding(
            rule_id=rule.id, severity="critical", model=model_key,
            title=f"{label}: {count} flipped normal{'s' if count != 1 else ''}",
            explanation=rule.explanation,
            recommendation=rule.what_to_do,
            data={"count": count, "model": label},
            has_screenshot=True,
        ))

    # Negative UVs
    count = geom.get("negative_uv_count", 0)
    if count > 0:
        rule = ALL_RULES["negative_uv"]
        findings.append(Finding(
            rule_id=rule.id, severity="critical", model=model_key,
            title=f"{label}: {count} face{'s' if count != 1 else ''} with negative UV coordinates",
            explanation=rule.explanation,
            recommendation=rule.what_to_do,
            data={"count": count, "model": label},
        ))

    # Out-of-range UVs
    count = geom.get("out_of_range_uv_count", 0)
    if count > 0:
        rule = ALL_RULES["out_of_range_uv"]
        findings.append(Finding(
            rule_id=rule.id, severity="warning", model=model_key,
            title=f"{label}: {count} face{'s' if count != 1 else ''} with UVs outside 0-1 range",
            explanation=rule.explanation,
            recommendation=rule.what_to_do,
            data={"count": count, "model": label},
        ))

    # Non-manifold
    count = geom.get("non_manifold_count", 0)
    if count > 0:
        rule = ALL_RULES["non_manifold"]
        sev = "critical" if count > 100 else "warning"
        findings.append(Finding(
            rule_id=rule.id, severity=sev, model=model_key,
            title=f"{label}: {count} non-manifold edge{'s' if count != 1 else ''}",
            explanation=rule.explanation,
            recommendation=rule.what_to_do,
            data={"count": count, "model": label},
        ))

    # Loose vertices
    count = geom.get("loose_vertices_count", 0)
    if count > 0:
        rule = ALL_RULES["loose_vertices"]
        findings.append(Finding(
            rule_id=rule.id, severity="info", model=model_key,
            title=f"{label}: {count} loose {'vertex' if count == 1 else 'vertices'}",
            explanation=rule.explanation,
            recommendation=rule.what_to_do,
            data={"count": count, "model": label},
        ))

    return findings


def _check_file_sizes(geometry_results: dict) -> list:
    """Check file size relationships between models."""
    findings = []
    raw_size = geometry_results.get("raw", {}).get("file_size_mb", 0)
    tu_size = geometry_results.get("touchedup", {}).get("file_size_mb", 0)
    auto_size = geometry_results.get("autoshadow", {}).get("file_size_mb", 0)

    if tu_size > 0 and raw_size > 0 and tu_size > raw_size * 1.1:
        rule = ALL_RULES["filesize_touchup_larger"]
        findings.append(Finding(
            rule_id=rule.id, severity="info", model="touchedup",
            title=f"Touched-up ({tu_size:.1f} MB) is larger than raw scan ({raw_size:.1f} MB)",
            explanation=rule.explanation,
            recommendation=rule.what_to_do,
            data={"raw_mb": raw_size, "touchedup_mb": tu_size},
        ))

    if auto_size > 0 and tu_size > 0 and auto_size > tu_size * 2:
        rule = ALL_RULES["filesize_autoshadow_much_larger"]
        findings.append(Finding(
            rule_id=rule.id, severity="info", model="autoshadow",
            title=f"AutoShadow ({auto_size:.1f} MB) is {auto_size/tu_size:.1f}x larger than touched-up ({tu_size:.1f} MB)",
            explanation=rule.explanation,
            recommendation=rule.what_to_do,
            data={"touchedup_mb": tu_size, "autoshadow_mb": auto_size},
        ))

    return findings


def _check_texture_resolution(geometry_results: dict) -> list:
    """Check texture resolutions across models."""
    findings = []

    for model_key, label in [("raw", "Raw scan"), ("touchedup", "Touched-up"), ("autoshadow", "AutoShadow")]:
        geom = geometry_results.get(model_key, {})
        for tex in geom.get("textures", []):
            if not tex.get("is_4k") and tex.get("width", 0) > 0:
                if model_key == "touchedup":
                    # Touched-up intentionally uses smaller textures — info only
                    rule = ALL_RULES["tex_resolution_touchedup_optimized"]
                    findings.append(Finding(
                        rule_id=rule.id, severity="info", model=model_key,
                        title=f"Touched-up: {tex['name']} is {tex['width']}x{tex['height']} (intentional optimization)",
                        explanation=rule.explanation,
                        recommendation=rule.what_to_do,
                        data={"width": tex["width"], "height": tex["height"], "name": tex["name"]},
                    ))
                elif model_key == "autoshadow":
                    # AutoShadow must produce 4K — flag as warning
                    rule = ALL_RULES["tex_resolution_not_4k"]
                    findings.append(Finding(
                        rule_id=rule.id, severity="warning", model=model_key,
                        title=f"AutoShadow output: {tex['name']} is {tex['width']}x{tex['height']} (should be 4K)",
                        explanation=rule.explanation,
                        recommendation=rule.what_to_do,
                        data={"width": tex["width"], "height": tex["height"], "name": tex["name"]},
                    ))
                else:
                    # Raw scan — info only
                    findings.append(Finding(
                        rule_id="tex_resolution_not_4k", severity="info", model=model_key,
                        title=f"Raw scan: {tex['name']} is {tex['width']}x{tex['height']} (scanner output)",
                        explanation=(
                            f"The raw scan has textures at {tex['width']}x{tex['height']}. "
                            "Scanner output resolution varies and is expected to differ from production targets."
                        ),
                        recommendation="Ensure the final autoshadow output uses 4K textures.",
                        data={"width": tex["width"], "height": tex["height"], "name": tex["name"]},
                    ))
                break  # One finding per model is enough

    return findings


def _check_texture_diffs(texture_diffs: dict) -> list:
    """Check texture comparison results against rules."""
    findings = []

    for tex_type in ["basecolor", "normal", "roughness", "metallic"]:
        comparisons = texture_diffs.get(tex_type, {})

        # ─── Raw vs Touched-up ────────────────────────
        diff = comparisons.get("raw_vs_touchedup")
        if diff:
            findings.extend(_check_raw_vs_touchedup(tex_type, diff))

        # ─── Touched-up vs AutoShadow ─────────────────
        diff = comparisons.get("touchedup_vs_autoshadow")
        if diff:
            findings.extend(_check_touchedup_vs_autoshadow(tex_type, diff))

    return findings


_UV_REORG_NOTE = (
    " Note: UV islands were reorganized (logos cut out and repositioned for shoe mirroring preparation), "
    "so part of the pixel difference reflects UV layout changes rather than purely artist edits — "
    "the comparison is between different UV layouts."
)
_BAKE_EXTEND_NOTE = (
    " Background areas outside UV islands show extended pixels from Blender's bake 'extend' fill — "
    "this is intentional seam prevention, not an issue."
)


def _check_raw_vs_touchedup(tex_type: str, diff) -> list:
    """Analyze raw scan vs touched-up texture differences."""
    findings = []
    pct = diff.pct_changed
    max_d = diff.max_diff

    tex_label = tex_type.replace("_", " ").title()

    if tex_type == "basecolor":
        rule = ALL_RULES["tex_raw_touchup_basecolor"]
        findings.append(Finding(
            rule_id=rule.id, severity="expected", model="touchedup",
            title=f"{tex_label}: {pct}% changed by artist",
            explanation=rule.explanation + _UV_REORG_NOTE + _BAKE_EXTEND_NOTE,
            recommendation=rule.what_to_do,
            data={"pct_changed": pct, "max_diff": max_d},
        ))

    elif tex_type == "normal":
        # Check for doubled normals: if mean diff is very high (>100) it may be doubled
        if diff.mean_diff > 100 and pct > 50:
            rule = ALL_RULES["tex_raw_touchup_normal_doubled"]
            findings.append(Finding(
                rule_id=rule.id, severity="critical", model="touchedup",
                title=f"Normal map may be doubled (mean diff: {diff.mean_diff:.0f}, {pct}% changed)",
                explanation=rule.explanation,
                recommendation=rule.what_to_do,
                data={"pct_changed": pct, "mean_diff": diff.mean_diff, "max_diff": max_d},
            ))
        else:
            rule = ALL_RULES["tex_raw_touchup_normal"]
            findings.append(Finding(
                rule_id=rule.id, severity="expected", model="touchedup",
                title=f"{tex_label}: {pct}% corrected by artist",
                explanation=rule.explanation + _UV_REORG_NOTE + _BAKE_EXTEND_NOTE,
                recommendation=rule.what_to_do,
                data={"pct_changed": pct, "max_diff": max_d},
            ))

    elif tex_type == "roughness":
        rule = ALL_RULES["tex_raw_touchup_roughness"]
        findings.append(Finding(
            rule_id=rule.id, severity="expected", model="touchedup",
            title=f"{tex_label}: {pct}% corrected by artist",
            explanation=rule.explanation + _UV_REORG_NOTE + _BAKE_EXTEND_NOTE,
            recommendation=rule.what_to_do,
            data={"pct_changed": pct, "max_diff": max_d},
        ))

    elif tex_type == "metallic":
        rule = ALL_RULES["tex_raw_touchup_metallic"]
        findings.append(Finding(
            rule_id=rule.id, severity="expected", model="touchedup",
            title=f"{tex_label}: {pct}% corrected by artist",
            explanation=rule.explanation + _UV_REORG_NOTE + _BAKE_EXTEND_NOTE,
            recommendation=rule.what_to_do,
            data={"pct_changed": pct, "max_diff": max_d},
        ))

    return findings


def _check_touchedup_vs_autoshadow(tex_type: str, diff) -> list:
    """Analyze touched-up vs autoshadow texture differences."""
    findings = []
    pct = diff.pct_changed
    max_d = diff.max_diff

    tex_label = tex_type.replace("_", " ").title()

    if tex_type == "basecolor":
        rule = ALL_RULES["tex_autoshadow_basecolor"]
        findings.append(Finding(
            rule_id=rule.id, severity="expected", model="autoshadow",
            title=f"{tex_label}: {pct}% modified by autoshadow (insole darkening)",
            explanation=rule.explanation,
            recommendation=rule.what_to_do,
            data={"pct_changed": pct, "max_diff": max_d},
        ))

    elif tex_type == "normal":
        # Normal map should NOT change much
        if pct > 2:
            rule = ALL_RULES["tex_autoshadow_normal_unexpected"]
            findings.append(Finding(
                rule_id=rule.id, severity="warning", model="autoshadow",
                title=f"Normal map changed {pct}% by autoshadow (should be minimal)",
                explanation=rule.explanation,
                recommendation=rule.what_to_do,
                data={"pct_changed": pct, "max_diff": max_d},
            ))
        else:
            rule = ALL_RULES["tex_autoshadow_normal_ok"]
            findings.append(Finding(
                rule_id=rule.id, severity="expected", model="autoshadow",
                title=f"Normal map: {pct}% change (acceptable)",
                explanation=rule.explanation,
                recommendation=rule.what_to_do,
                data={"pct_changed": pct},
            ))

    elif tex_type == "roughness":
        rule = ALL_RULES["tex_autoshadow_roughness"]
        findings.append(Finding(
            rule_id=rule.id, severity="expected", model="autoshadow",
            title=f"{tex_label}: {pct}% modified in insole area",
            explanation=rule.explanation,
            recommendation=rule.what_to_do,
            data={"pct_changed": pct, "max_diff": max_d},
        ))

    elif tex_type == "metallic":
        rule = ALL_RULES["tex_autoshadow_metallic"]
        findings.append(Finding(
            rule_id=rule.id, severity="expected", model="autoshadow",
            title=f"{tex_label}: {pct}% modified in insole area",
            explanation=rule.explanation,
            recommendation=rule.what_to_do,
            data={"pct_changed": pct, "max_diff": max_d},
        ))

    return findings
