from backend.qa_rules import ALL_RULES, QARule


def test_all_rules_have_required_fields():
    assert len(ALL_RULES) >= 12
    for rule_id, rule in ALL_RULES.items():
        assert rule.id == rule_id
        assert rule.category in (
            "geometry", "texture_raw_vs_autoshadow",
            "resolution", "filesize"
        )
        assert rule.severity in ("critical", "warning", "info", "expected")
        assert len(rule.title) > 3
        assert len(rule.explanation) > 20
        assert len(rule.what_to_do) > 5


def test_geometry_rules_exist():
    geo_rules = [r for r in ALL_RULES.values() if r.category == "geometry"]
    assert len(geo_rules) >= 5
    ids = {r.id for r in geo_rules}
    assert "flipped_normals" in ids
    assert "negative_uv" in ids


def test_texture_rules_cover_raw_vs_autoshadow():
    auto_rules = [r for r in ALL_RULES.values() if r.category == "texture_raw_vs_autoshadow"]
    assert len(auto_rules) >= 4  # basecolor, normal (ok + unexpected), roughness, metallic
