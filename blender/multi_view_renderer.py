"""
Multi-view renderer for shoe QA.
Renders 6 orthographic views + face orientation overlay + PBR channel views per model.

Usage:
  blender -b -P multi_view_renderer.py -- \\
    --glb_path /path/to.glb \\
    --model_name raw|touchedup|autoshadow \\
    --output_dir /path/to/renders \\
    --output_json /path/to/result.json \\
    [--textures_json /path/to/textures.json]
"""
import bpy
import bmesh
import json
import sys
import os
import math
import traceback

import mathutils


# ─── Args ────────────────────────────────────────────────────────────────────

def get_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb_path", required=True)
    parser.add_argument("--model_name", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--output_json", required=True)
    parser.add_argument("--textures_json", default=None,
                        help="JSON file with pre-extracted texture paths from texture_extractor")
    return parser.parse_args(argv)


# ─── Scene setup ─────────────────────────────────────────────────────────────

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for block in bpy.data.meshes:
        bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        bpy.data.materials.remove(block)
    for block in bpy.data.cameras:
        bpy.data.cameras.remove(block)
    for block in bpy.data.lights:
        bpy.data.lights.remove(block)


def setup_render(resolution=512):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    # Fast EEVEE settings
    scene.eevee.taa_render_samples = 16
    scene.eevee.use_gtao = False
    scene.eevee.use_bloom = False
    scene.eevee.use_ssr = False


def add_world_lighting():
    world = bpy.data.worlds.new("QA_World")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.5, 0.5, 0.5, 1.0)
        bg.inputs[1].default_value = 1.0
    bpy.context.scene.world = world


def add_sun_light():
    light_data = bpy.data.lights.new("Sun", type='SUN')
    light_data.energy = 3.0
    light_obj = bpy.data.objects.new("Sun", light_data)
    bpy.context.scene.collection.objects.link(light_obj)
    light_obj.rotation_euler = (math.radians(45), math.radians(30), math.radians(45))
    return light_obj


# ─── Bounds helper ───────────────────────────────────────────────────────────

def get_model_bounds(meshes):
    min_c = [float('inf')] * 3
    max_c = [float('-inf')] * 3
    for obj in meshes:
        for corner in obj.bound_box:
            wc = obj.matrix_world @ mathutils.Vector(corner)
            for i in range(3):
                min_c[i] = min(min_c[i], wc[i])
                max_c[i] = max(max_c[i], wc[i])
    center = tuple((min_c[i] + max_c[i]) / 2 for i in range(3))
    size = max(max_c[i] - min_c[i] for i in range(3))
    return center, max(size, 0.001)


# ─── Camera helpers ───────────────────────────────────────────────────────────

# (view_name, location_direction, rotation_euler)
# Blender: Y=forward, Z=up. Ortho cameras point along -Z in their local space.
VIEW_CONFIGS = [
    ("front",   (0, -1,  0), (math.radians(90),  0,                  0)),
    ("back",    (0,  1,  0), (math.radians(90),  0,  math.radians(180))),
    ("left",    (-1, 0,  0), (math.radians(90),  0,   math.radians(90))),
    ("right",   ( 1, 0,  0), (math.radians(90),  0,  math.radians(-90))),
    ("top",     (0,  0,  1), (0,                 0,                  0)),
    ("bottom",  (0,  0, -1), (math.radians(180), 0,                  0)),
]


def create_ortho_camera(name, center, loc_dir, rotation, dist, ortho_scale):
    cam_data = bpy.data.cameras.new(name)
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = ortho_scale
    cam_data.clip_end = dist * 10
    cam_obj = bpy.data.objects.new(name, cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.location = (
        center[0] + loc_dir[0] * dist,
        center[1] + loc_dir[1] * dist,
        center[2] + loc_dir[2] * dist,
    )
    cam_obj.rotation_euler = rotation
    return cam_obj


def create_perspective_camera(name, center, dist):
    """3/4 perspective view for PBR channel renders."""
    cam_data = bpy.data.cameras.new(name)
    cam_data.type = 'PERSP'
    cam_data.lens = 50
    cam_data.clip_end = dist * 10
    cam_obj = bpy.data.objects.new(name, cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.location = (
        center[0] + dist * 0.6,
        center[1] - dist * 0.9,
        center[2] + dist * 0.5,
    )
    direction = mathutils.Vector(center) - mathutils.Vector(cam_obj.location)
    rot_quat = direction.to_track_quat('-Z', 'Y')
    cam_obj.rotation_euler = rot_quat.to_euler()
    return cam_obj


def render_to(camera, output_path):
    bpy.context.scene.camera = camera
    bpy.context.scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)


# ─── Material helpers ─────────────────────────────────────────────────────────

def save_materials(meshes):
    return [[mat for mat in obj.data.materials] for obj in meshes]


def restore_materials(meshes, saved):
    for obj, mats in zip(meshes, saved):
        obj.data.materials.clear()
        for mat in mats:
            obj.data.materials.append(mat)


def apply_material(meshes, mat):
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(mat)


def make_face_orientation_material():
    """Blue=correct normals, red=flipped normals using Backfacing geometry node."""
    mat = bpy.data.materials.new("FaceOrient")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    geom = nodes.new("ShaderNodeNewGeometry")

    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = 'MIX'
    mix.inputs[1].default_value = (0.05, 0.35, 1.0, 1.0)   # blue = correct
    mix.inputs[2].default_value = (1.0, 0.1, 0.05, 1.0)    # red = flipped

    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 1.0

    output = nodes.new("ShaderNodeOutputMaterial")

    links.new(geom.outputs["Backfacing"], mix.inputs[0])
    links.new(mix.outputs[0], emission.inputs["Color"])
    links.new(emission.outputs[0], output.inputs["Surface"])

    return mat


def make_emission_material(name, image):
    """Simple emission material showing a texture image."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image

    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 1.0

    output = nodes.new("ShaderNodeOutputMaterial")

    links.new(tex.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs[0], output.inputs["Surface"])

    return mat


def make_emission_channel_material(name, image, channel):
    """Emission material showing a single texture channel (grayscale for metallic/roughness/ao)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.image.colorspace_settings.name = 'Non-Color' if channel != "basecolor" else 'sRGB'

    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 1.0
    output = nodes.new("ShaderNodeOutputMaterial")

    if channel in ("metallic", "roughness", "ao"):
        separate = nodes.new("ShaderNodeSeparateColor")
        links.new(tex.outputs["Color"], separate.inputs["Color"])
        # ORM: R=AO, G=Roughness, B=Metallic
        channel_map = {"ao": "Red", "roughness": "Green", "metallic": "Blue"}
        ch = channel_map.get(channel, "Green")
        combine = nodes.new("ShaderNodeCombineColor")
        links.new(separate.outputs[ch], combine.inputs["Red"])
        links.new(separate.outputs[ch], combine.inputs["Green"])
        links.new(separate.outputs[ch], combine.inputs["Blue"])
        links.new(combine.outputs["Color"], emission.inputs["Color"])
    else:
        links.new(tex.outputs["Color"], emission.inputs["Color"])

    links.new(emission.outputs[0], output.inputs["Surface"])
    return mat


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = get_args()
    os.makedirs(args.output_dir, exist_ok=True)
    renders = []

    clear_scene()
    setup_render(512)
    add_world_lighting()
    add_sun_light()

    # Import GLB
    if not os.path.exists(args.glb_path):
        raise FileNotFoundError(f"GLB not found: {args.glb_path}")
    bpy.ops.import_scene.gltf(filepath=args.glb_path)
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    if not meshes:
        raise RuntimeError("No mesh objects found")

    center, size = get_model_bounds(meshes)
    dist = size * 2.0
    ortho_scale = size * 1.15

    model = args.model_name

    # ── 1. Create cameras ─────────────────────────────────────────────────────
    ortho_cams = []
    for view_name, loc_dir, rotation in VIEW_CONFIGS:
        cam = create_ortho_camera(
            f"cam_{view_name}", center, loc_dir, rotation, dist, ortho_scale
        )
        ortho_cams.append((view_name, cam))

    persp_cam = create_perspective_camera("cam_34", center, dist)

    saved_mats = save_materials(meshes)

    # ── 2. Material views (6 angles) ──────────────────────────────────────────
    for view_name, cam in ortho_cams:
        out = os.path.join(args.output_dir, f"{model}_{view_name}_material.png")
        render_to(cam, out)
        renders.append({"model": model, "view": view_name, "channel": "material", "path": out})

    # ── 3. Face orientation views (6 angles) ──────────────────────────────────
    face_mat = make_face_orientation_material()
    apply_material(meshes, face_mat)
    for view_name, cam in ortho_cams:
        out = os.path.join(args.output_dir, f"{model}_{view_name}_face_orientation.png")
        render_to(cam, out)
        renders.append({"model": model, "view": view_name, "channel": "face_orientation", "path": out})
    restore_materials(meshes, saved_mats)

    # ── 4. PBR channel views (3/4 perspective) ────────────────────────────────
    tex_paths = {}
    if args.textures_json and os.path.exists(args.textures_json):
        with open(args.textures_json) as f:
            tex_data = json.load(f)
        for ch, info in tex_data.get("textures", {}).items():
            p = info.get("path")
            if p and os.path.exists(p):
                tex_paths[ch] = p

    pbr_channels = [
        ("basecolor", "basecolor"),
        ("normal",    "normal"),
        ("roughness", "roughness"),
        ("metallic",  "metallic"),
    ]

    for channel, tex_key in pbr_channels:
        tex_path = tex_paths.get(tex_key)
        if not tex_path:
            continue
        try:
            img = bpy.data.images.load(tex_path)
            pbr_mat = make_emission_channel_material(f"pbr_{channel}", img, channel)
            apply_material(meshes, pbr_mat)
            out = os.path.join(args.output_dir, f"{model}_34_{channel}.png")
            render_to(persp_cam, out)
            renders.append({"model": model, "view": "34", "channel": channel, "path": out})
            restore_materials(meshes, saved_mats)
        except Exception as e:
            print(f"[multi_view_renderer] PBR channel {channel} failed: {e}")
            restore_materials(meshes, saved_mats)

    result = {"renders": renders}
    with open(args.output_json, "w") as f:
        json.dump(result, f, indent=2)

    print(f"[multi_view_renderer] Done: {len(renders)} renders → {args.output_json}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        argv = sys.argv
        if "--" in argv:
            argv = argv[argv.index("--") + 1:]
        import argparse
        p = argparse.ArgumentParser()
        p.add_argument("--output_json", required=True)
        p.add_argument("--glb_path", default="")
        p.add_argument("--model_name", default="")
        p.add_argument("--output_dir", default="")
        p.add_argument("--textures_json", default=None)
        a, _ = p.parse_known_args(argv)
        with open(a.output_json, "w") as f:
            json.dump({"error": str(e), "renders": []}, f)
        sys.exit(1)
