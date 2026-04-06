from backend.qa_analyzer import analyze, Finding, QAReport
from backend.texture_compare import TextureDiff


def _mock_geom(flipped=0, negative_uv=0, non_manifold=0, loose=0, out_of_range=0, file_mb=10.0):
    return {
        "vertices": 100000, "faces": 200000, "file_size_mb": file_mb,
        "flipped_normals_count": flipped, "negative_uv_count": negative_uv,
        "non_manifold_count": non_manifold, "loose_vertices_count": loose,
        "out_of_range_uv_count": out_of_range,
        "textures": [{"name": "test", "width": 4096, "height": 4096, "is_4k": True}],
        "material_count": 1, "total_issues": flipped + negative_uv + non_manifold + loose + out_of_range,
    }


def _mock_diff(pct=50.0, max_diff=200, mean_diff=80.0):
    return TextureDiff(
        pct_changed=pct, max_diff=max_diff, mean_diff=mean_diff,
        heatmap_path="", overlay_path="", side_by_side_path="",
        changed_regions=[], resolution_a=(4096, 4096), resolution_b=(4096, 4096),
        resolution_mismatch=False,
    )


def test_clean_model_passes():
    geom = {"raw": _mock_geom(), "autoshadow": _mock_geom(file_mb=3.5)}
    report = analyze(geom, {})
    assert report.verdict == "PASS"
    assert report.critical_count == 0


def test_flipped_normals_fails():
    geom = {"raw": _mock_geom(), "autoshadow": _mock_geom(flipped=18)}
    report = analyze(geom, {})
    assert report.verdict == "FAIL"
    assert report.critical_count >= 1
    critical = [f for f in report.findings if f.severity == "critical"]
    assert any("flipped" in f.title.lower() for f in critical)


def test_raw_vs_autoshadow_basecolor_is_expected():
    geom = {"raw": _mock_geom(), "autoshadow": _mock_geom()}
    diffs = {"basecolor": {"raw_vs_autoshadow": _mock_diff(pct=90.0)}}
    report = analyze(geom, diffs)
    expected = [f for f in report.findings if f.severity == "expected" and "basecolor" in f.title.lower()]
    assert len(expected) >= 1


def test_autoshadow_normal_change_warns():
    geom = {"raw": _mock_geom(), "autoshadow": _mock_geom()}
    diffs = {"normal": {"raw_vs_autoshadow": _mock_diff(pct=80.0, max_diff=255, mean_diff=120.0)}}
    report = analyze(geom, diffs)
    assert report.verdict == "NEEDS_REVIEW"
    warnings = [f for f in report.findings if f.severity == "warning"]
    assert any("normal" in f.title.lower() for f in warnings)


def test_autoshadow_normal_minimal_is_ok():
    geom = {"raw": _mock_geom(), "autoshadow": _mock_geom()}
    diffs = {"normal": {"raw_vs_autoshadow": _mock_diff(pct=0.5, max_diff=10)}}
    report = analyze(geom, diffs)
    expected = [f for f in report.findings if f.rule_id == "tex_autoshadow_normal_ok"]
    assert len(expected) == 1


def test_doubled_normal_is_warning():
    geom = {"raw": _mock_geom(), "autoshadow": _mock_geom()}
    diffs = {"normal": {"raw_vs_autoshadow": _mock_diff(pct=80.0, max_diff=255, mean_diff=120.0)}}
    report = analyze(geom, diffs)
    warnings = [f for f in report.findings if f.severity == "warning"]
    assert any("normal" in f.title.lower() for f in warnings)
