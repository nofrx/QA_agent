"""
QA Rules knowledge base — defines what is expected vs problematic
for 3D shoe model quality analysis.
"""
from dataclasses import dataclass, field


@dataclass
class QARule:
    id: str
    category: str          # geometry, texture_raw_vs_touchedup, texture_touchedup_vs_autoshadow, resolution, filesize
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


# ─── TEXTURE: RAW SCAN vs TOUCHED-UP ─────────────────────────

TEX_RAW_TOUCHUP_BASECOLOR = QARule(
    id="tex_raw_touchup_basecolor",
    category="texture_raw_vs_touchedup",
    severity="expected",
    title="Base color changes (raw → touched-up)",
    explanation=(
        "Artist corrected scanning artifacts, color bleeding, seam issues, and material appearance. "
        "Large percentage of changed pixels is normal — artists often repaint entire areas in Substance Painter. "
        "More changes generally mean more thorough quality improvement."
    ),
    what_to_do="No action needed. This is expected artist work.",
)

TEX_RAW_TOUCHUP_NORMAL = QARule(
    id="tex_raw_touchup_normal",
    category="texture_raw_vs_touchedup",
    severity="expected",
    title="Normal map changes (raw → touched-up)",
    explanation=(
        "Artist smoothed out scan noise and corrected surface details in the normal map. "
        "Expected and good quality improvement."
    ),
    what_to_do="No action needed unless normal values appear doubled (see separate check).",
)

TEX_RAW_TOUCHUP_NORMAL_DOUBLED = QARule(
    id="tex_raw_touchup_normal_doubled",
    category="texture_raw_vs_touchedup",
    severity="critical",
    title="Normal map appears doubled/multiplied",
    explanation=(
        "The normal map shows values that appear to be multiplied or applied twice. "
        "This happens when a normal map is baked on top of an existing normal map without flattening first. "
        "The result is exaggerated surface detail that looks unnatural — bumps appear twice as deep."
    ),
    what_to_do=(
        "Re-bake the normal map from a flat base, or flatten the existing normal map "
        "before applying additional details in Substance Painter."
    ),
)

TEX_RAW_TOUCHUP_ROUGHNESS = QARule(
    id="tex_raw_touchup_roughness",
    category="texture_raw_vs_touchedup",
    severity="expected",
    title="Roughness changes (raw → touched-up)",
    explanation=(
        "Artist corrected roughness values to match real material properties. "
        "Raw scan roughness is often noisy or inaccurate. More corrections mean better material fidelity."
    ),
    what_to_do="No action needed. This is expected artist work.",
)

TEX_RAW_TOUCHUP_METALLIC = QARule(
    id="tex_raw_touchup_metallic",
    category="texture_raw_vs_touchedup",
    severity="expected",
    title="Metallic map changes (raw → touched-up)",
    explanation=(
        "Artist corrected metal vs non-metal classification. Raw scan metallic data is often incorrect. "
        "Proper metallic values are essential for physically-based rendering to look correct."
    ),
    what_to_do="No action needed. More corrections indicate better quality.",
)


# ─── TEXTURE: TOUCHED-UP vs AUTOSHADOW ───────────────────────

TEX_AUTOSHADOW_BASECOLOR = QARule(
    id="tex_autoshadow_basecolor",
    category="texture_touchedup_vs_autoshadow",
    severity="expected",
    title="Base color shadow applied (touched-up → autoshadow)",
    explanation=(
        "The autoshadow script darkened the insole/interior area to simulate ambient occlusion. "
        "Changes should be concentrated in the shoe opening and interior. "
        "This is the primary purpose of the autoshadow pipeline."
    ),
    what_to_do="Verify the shadow looks natural and is only applied to the interior area.",
)

TEX_AUTOSHADOW_BASECOLOR_EXTERIOR = QARule(
    id="tex_autoshadow_basecolor_exterior",
    category="texture_touchedup_vs_autoshadow",
    severity="warning",
    title="Autoshadow modified exterior base color",
    explanation=(
        "The autoshadow script appears to have changed base color outside the insole area. "
        "This may indicate the shadow mask leaked onto the exterior of the shoe, "
        "causing unwanted darkening on visible surfaces."
    ),
    what_to_do="Check the autoshadow result visually. If exterior surfaces are darkened, re-run with adjusted mask.",
)

TEX_AUTOSHADOW_NORMAL = QARule(
    id="tex_autoshadow_normal_unexpected",
    category="texture_touchedup_vs_autoshadow",
    severity="warning",
    title="Autoshadow modified normal map",
    explanation=(
        "The autoshadow script should NOT significantly change the normal map. "
        "Normal map modifications suggest the script is altering surface detail, "
        "which could introduce visual artifacts on the shoe surface."
    ),
    what_to_do="Compare the normal maps visually. If surface detail changed, investigate the autoshadow script.",
)

TEX_AUTOSHADOW_NORMAL_OK = QARule(
    id="tex_autoshadow_normal_ok",
    category="texture_touchedup_vs_autoshadow",
    severity="expected",
    title="Normal map unchanged by autoshadow",
    explanation="The autoshadow script correctly left the normal map untouched.",
    what_to_do="No action needed.",
)

TEX_AUTOSHADOW_ROUGHNESS = QARule(
    id="tex_autoshadow_roughness",
    category="texture_touchedup_vs_autoshadow",
    severity="expected",
    title="Roughness modified in insole area",
    explanation=(
        "The autoshadow script increased roughness inside the shoe to simulate the matte "
        "appearance of shoe interiors. This is expected behavior."
    ),
    what_to_do="No action needed.",
)

TEX_AUTOSHADOW_METALLIC = QARule(
    id="tex_autoshadow_metallic",
    category="texture_touchedup_vs_autoshadow",
    severity="expected",
    title="Metallic reduced in insole area",
    explanation=(
        "The autoshadow script reduced metallic values inside the shoe. "
        "Shoe interiors are non-metallic, so this correction is expected."
    ),
    what_to_do="No action needed.",
)


# ─── RESOLUTION RULES ────────────────────────────────────────

TEX_RESOLUTION_NOT_4K = QARule(
    id="tex_resolution_not_4k",
    category="resolution",
    severity="warning",
    title="Texture resolution below 4K",
    explanation=(
        "Production models require 4096x4096 textures for sufficient detail in AR viewers. "
        "Lower resolution textures will appear blurry when viewed up close."
    ),
    what_to_do="Re-export textures at 4096x4096 resolution.",
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

FILESIZE_TOUCHUP_LARGER = QARule(
    id="filesize_touchup_larger",
    category="filesize",
    severity="info",
    title="Touched-up model larger than raw scan",
    explanation=(
        "Typically the touched-up model should be smaller because the artist decimates "
        "the high-density scanner mesh to production polygon count. A larger file may indicate "
        "the mesh was not decimated, or additional geometry was added."
    ),
    what_to_do="Verify the polygon count is appropriate for production (usually 50K-300K faces).",
)

FILESIZE_AUTOSHADOW_MUCH_LARGER = QARule(
    id="filesize_autoshadow_much_larger",
    category="filesize",
    severity="warning",
    title="AutoShadow file significantly larger than touched-up",
    explanation=(
        "The autoshadow model is much larger than the touched-up input. "
        "The autoshadow script should only modify textures, not geometry. "
        "A large size increase suggests the script added geometry or rebaked textures at higher resolution."
    ),
    what_to_do="Check if the autoshadow script is increasing geometry count or texture resolution unnecessarily.",
)


# ─── RULE REGISTRY ───────────────────────────────────────────

ALL_RULES = {r.id: r for r in [
    FLIPPED_NORMALS, NEGATIVE_UVS, OUT_OF_RANGE_UVS, NON_MANIFOLD, LOOSE_VERTICES,
    TEX_RAW_TOUCHUP_BASECOLOR, TEX_RAW_TOUCHUP_NORMAL, TEX_RAW_TOUCHUP_NORMAL_DOUBLED,
    TEX_RAW_TOUCHUP_ROUGHNESS, TEX_RAW_TOUCHUP_METALLIC,
    TEX_AUTOSHADOW_BASECOLOR, TEX_AUTOSHADOW_BASECOLOR_EXTERIOR,
    TEX_AUTOSHADOW_NORMAL, TEX_AUTOSHADOW_NORMAL_OK,
    TEX_AUTOSHADOW_ROUGHNESS, TEX_AUTOSHADOW_METALLIC,
    TEX_RESOLUTION_NOT_4K, TEX_RESOLUTION_MISMATCH,
    FILESIZE_TOUCHUP_LARGER, FILESIZE_AUTOSHADOW_MUCH_LARGER,
]}
