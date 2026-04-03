"""
Render camera-to-issue screenshots with highlighted problem areas.
Usage: blender -b -P issue_renderer.py -- --glb_path /path/to.glb --issues_json /path/issues.json --output_dir /dir --output_json /result.json
"""
import bpy
import bmesh
import json
import sys
import os
from mathutils import Vector


def get_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb_path", required=True)
    parser.add_argument("--issues_json", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--output_json", required=True)
    return parser.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def setup_render():
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.render.film_transparent = True
    bpy.ops.object.light_add(type='SUN', location=(2, -2, 5))
    bpy.context.active_object.data.energy = 3.0


def point_camera_at(target: Vector, distance: float = 0.3):
    cam_data = bpy.data.cameras.new("QA_Camera")
    cam_data.lens = 50
    cam_obj = bpy.data.objects.new("QA_Camera", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.location = target + Vector((distance, -distance, distance * 0.7))
    direction = target - cam_obj.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    cam_obj.rotation_euler = rot_quat.to_euler()
    bpy.context.scene.camera = cam_obj
    return cam_obj


def render_at_centroid(obj, centers_3d, issue_name, output_dir):
    if not centers_3d:
        return None
    centroid = sum(centers_3d, Vector()) / len(centers_3d)
    centroid = obj.matrix_world @ centroid
    cam = point_camera_at(centroid)
    path = os.path.join(output_dir, f"{issue_name}.png")
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)
    return path


def main():
    args = get_args()
    os.makedirs(args.output_dir, exist_ok=True)

    with open(args.issues_json) as f:
        issues = json.load(f)

    clear_scene()
    bpy.ops.import_scene.gltf(filepath=args.glb_path)
    setup_render()

    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    if not meshes:
        with open(args.output_json, 'w') as f:
            json.dump({"error": "No meshes", "renders": []}, f)
        return

    main_mesh = max(meshes, key=lambda o: len(o.data.polygons))
    renders = []

    # Flipped normals
    flipped = issues.get("flipped_normals", [])
    if flipped:
        centers = [Vector(f["center"]) for f in flipped[:20]]
        path = render_at_centroid(main_mesh, centers, "flipped_normals", args.output_dir)
        if path:
            renders.append({"type": "flipped_normals", "path": path, "count": len(flipped)})

    # Negative UV
    neg_uvs = issues.get("negative_uv_coords", [])
    if neg_uvs:
        centers = [Vector(f["center"]) for f in neg_uvs[:20]]
        path = render_at_centroid(main_mesh, centers, "negative_uv", args.output_dir)
        if path:
            renders.append({"type": "negative_uv", "path": path, "count": len(neg_uvs)})

    # Non-manifold
    non_manifold = issues.get("non_manifold_edges", [])
    if non_manifold:
        centers = [Vector(e["center"]) for e in non_manifold[:20]]
        path = render_at_centroid(main_mesh, centers, "non_manifold", args.output_dir)
        if path:
            renders.append({"type": "non_manifold", "path": path, "count": len(non_manifold)})

    with open(args.output_json, 'w') as f:
        json.dump({"renders": renders}, f, indent=2)
    print(f"ISSUE_RENDER_COMPLETE: {args.output_json}")


if __name__ == "__main__":
    main()
