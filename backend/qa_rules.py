"""
QA Rules knowledge base — defines what is expected vs problematic
for 3D shoe model quality analysis.
"""
from dataclasses import dataclass, field


@dataclass
class QARule:
    id: str
    category: str          # geometry, texture_raw_vs_autoshadow, resolution, filesize
    severity: str          # critical, warning, info, expected
    title: str
    explanation: str       # 2-3 sentences for a QA artist
    what_to_do: str        # actionable recommendation


# ─── GEOMETRY RULES ───────────────────────────────────────────

FLIPPED_NORMALS = QARule(
    id="flipped_normals",
    category="geometry",
    severity="critical",
    title="Flipped normals",
    explanation=(
        "Faces with inverted normals will render black or invisible in real-time viewers and AR. "
        "This is always a production blocker that must be fixed before publishing."
    ),
    what_to_do=(
        "Select the affected faces in Blender (Edit Mode → Select → Select All by Trait → Face Orientation), "
        "then flip them (Mesh → Normals → Flip). Recalculate normals outward on the entire mesh."
    ),
)

NEGATIVE_UVS = QARule(
    id="negative_uv",
    category="geometry",
    severity="critical",
    title="Negative UV coordinates",
    explanation=(
        "UV islands positioned below the 0,0 origin cannot be baked correctly. "
        "Textures will tile incorrectly or bake to wrong areas, causing visual artifacts in production."
    ),
    what_to_do=(
        "Open UV Editor, select all islands, and move them into the 0-1 UV tile space. "
        "Check that no island extends below 0 on either axis."
    ),
)

OUT_OF_RANGE_UVS = QARule(
    id="out_of_range_uv",
    category="geometry",
    severity="warning",
    title="UV coordinates outside 0-1 range",
    explanation=(
        "UV islands extending beyond the 1.0 boundary may cause tiling artifacts in some renderers. "
        "Sometimes intentional for repeating materials, but usually unintended for scanned shoe models."
    ),
    what_to_do="Review UV layout and move any unintentionally out-of-range islands back into the 0-1 tile.",
)

NON_MANIFOLD = QARule(
    id="non_manifold",
    category="geometry",
    severity="warning",  # escalated to critical if count > 100
    title="Non-manifold geometry",
    explanation=(
        "Edges shared by more than 2 faces, or internal faces creating impossible geometry. "
        "Causes artifacts with subdivision, booleans, and some real-time renderers."
    ),
    what_to_do=(
        "Select non-manifold edges (Select → All by Trait → Non-Manifold), "
        "then merge by distance or delete overlapping geometry."
    ),
)

LOOSE_VERTICES = QARule(
    id="loose_vertices",
    category="geometry",
    severity="info",
    title="Loose vertices",
    explanation=(
        "Vertices not connected to any face. Usually harmless but indicate incomplete cleanup. "
        "Won't affect rendering but add unnecessary data to the file."
    ),
    what_to_do="Select all loose vertices (Select → All by Trait → Loose Vertices) and delete them.",
)


# ─── TEXTURE: RAW SCAN vs AUTOSHADOW ─────────────────────────

TEX_AUTOSHADOW_BASECOLOR = QARule(
    id="tex_autoshadow_basecolor",
    category="texture_raw_vs_autoshadow",
    severity="expected",
    title="Base color changes (raw scan → autoshadow)",
    explanation=(
        "The autoshadow pipeline applies artist touch-ups and insole shadow to the raw scan. "
        "Changes include scanning artifact correction, color bleeding fixes, and insole darkening. "
        "Large percentage of changed pixels is expected."
    ),
    what_to_do="Verify the shadow looks natural and exterior surfaces are not unintentionally darkened.",
)

TEX_AUTOSHADOW_BASECOLOR_EXTERIOR = QARule(
    id="tex_autoshadow_basecolor_exterior",
    category="texture_raw_vs_autoshadow",
    severity="warning",
    title="Autoshadow modified exterior base color unexpectedly",
    explanation=(
        "The autoshadow output appears to have unexpected base color changes outside the insole area. "
        "This may indicate the shadow mask leaked onto the exterior of the shoe, "
        "causing unwanted darkening on visible surfaces."
    ),
    what_to_do="Check the autoshadow result visually. If exterior surfaces are darkened, re-run with adjusted mask.",
)

TEX_AUTOSHADOW_NORMAL = QARule(
    id="tex_autoshadow_normal_unexpected",
    category="texture_raw_vs_autoshadow",
    severity="warning",
    title="Significant normal map changes (raw scan → autoshadow)",
    explanation=(
        "The normal map changed significantly between raw scan and autoshadow output. "
        "While some normal map correction is expected from artist touch-up, large changes "
        "could indicate the normal map was doubled or the autoshadow script altered surface detail."
    ),
    what_to_do="Compare the normal maps visually. If surface detail looks exaggerated, investigate.",
)

TEX_AUTOSHADOW_NORMAL_OK = QARule(
    id="tex_autoshadow_normal_ok",
    category="texture_raw_vs_autoshadow",
    severity="expected",
    title="Normal map changes acceptable (raw scan → autoshadow)",
    explanation="The normal map changes between raw scan and autoshadow output are within expected range.",
    what_to_do="No action needed.",
)

TEX_AUTOSHADOW_ROUGHNESS = QARule(
    id="tex_autoshadow_roughness",
    category="texture_raw_vs_autoshadow",
    severity="expected",
    title="Roughness modified (raw scan → autoshadow)",
    explanation=(
        "Roughness changes between raw scan and autoshadow output include artist corrections "
        "and insole roughness adjustment. This is expected behavior."
    ),
    what_to_do="No action needed.",
)

TEX_AUTOSHADOW_METALLIC = QARule(
    id="tex_autoshadow_metallic",
    category="texture_raw_vs_autoshadow",
    severity="expected",
    title="Metallic modified (raw scan → autoshadow)",
    explanation=(
        "Metallic changes between raw scan and autoshadow output include artist corrections "
        "and insole metallic reduction. This is expected behavior."
    ),
    what_to_do="No action needed.",
)


# ─── RESOLUTION RULES ────────────────────────────────────────

TEX_RESOLUTION_NOT_4K = QARule(
    id="tex_resolution_not_4k",
    category="resolution",
    severity="warning",
    title="AutoShadow output texture not 4K",
    explanation=(
        "The autoshadow script rebakes textures at 4096x4096, so the final output should always be 4K. "
        "If the autoshadow output is not 4K, the script may have a configuration error."
    ),
    what_to_do="Check the autoshadow script resolution settings and re-run to produce 4K output textures.",
)

TEX_RESOLUTION_MISMATCH = QARule(
    id="tex_resolution_mismatch",
    category="resolution",
    severity="info",
    title="Resolution differs between pipeline stages",
    explanation=(
        "The texture resolution changed between pipeline stages. This is common when the artist "
        "works at a different resolution than the scanner output. Comparison accuracy is reduced "
        "because images are resized for comparison."
    ),
    what_to_do="Ensure the final production model uses 4K textures.",
)


# ─── FILE SIZE RULES ─────────────────────────────────────────

FILESIZE_AUTOSHADOW_MUCH_LARGER = QARule(
    id="filesize_autoshadow_much_larger",
    category="filesize",
    severity="info",
    title="AutoShadow file significantly larger than raw scan",
    explanation=(
        "The autoshadow model may be larger than the raw scan due to rebaked 4K textures "
        "and additional processing. This is generally expected pipeline behavior."
    ),
    what_to_do="No action needed. Verify the file size increase is reasonable.",
)


# ─── RULE REGISTRY ───────────────────────────────────────────

ALL_RULES = {r.id: r for r in [
    FLIPPED_NORMALS, NEGATIVE_UVS, OUT_OF_RANGE_UVS, NON_MANIFOLD, LOOSE_VERTICES,
    TEX_AUTOSHADOW_BASECOLOR, TEX_AUTOSHADOW_BASECOLOR_EXTERIOR,
    TEX_AUTOSHADOW_NORMAL, TEX_AUTOSHADOW_NORMAL_OK,
    TEX_AUTOSHADOW_ROUGHNESS, TEX_AUTOSHADOW_METALLIC,
    TEX_RESOLUTION_NOT_4K, TEX_RESOLUTION_MISMATCH,
    FILESIZE_AUTOSHADOW_MUCH_LARGER,
]}
