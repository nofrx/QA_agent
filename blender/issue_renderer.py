"""
Render issue screenshots: full shoe with bright red markers on problem areas.
Projects 3D issue locations to 2D screen space and draws red markers.
Usage: blender -b -P issue_renderer.py -- --glb_path /path/to.glb --issues_json /path/issues.json --output_dir /dir --output_json /result.json
"""
import bpy
import bmesh
import json
import sys
import os
import math
import numpy as np
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
    bpy.ops.object.light_add(type='SUN', location=(-2, 2, 3))
    bpy.context.active_object.data.energy = 1.5


def frame_camera_on_object(obj):
    """Position camera to show the full shoe from a 3/4 angle."""
    bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    center = sum(bbox_corners, Vector()) / 8
    max_dist = max((corner - center).length for corner in bbox_corners)

    cam_data = bpy.data.cameras.new("QA_Camera")
    cam_data.lens = 50
    fov = 2 * math.atan(36 / (2 * cam_data.lens))
    distance = (max_dist * 1.4) / math.tan(fov / 2)

    cam_obj = bpy.data.objects.new("QA_Camera", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)

    angle_h = math.radians(35)
    angle_v = math.radians(25)
    offset = Vector((
        distance * math.cos(angle_v) * math.sin(angle_h),
        -distance * math.cos(angle_v) * math.cos(angle_h),
        distance * math.sin(angle_v)
    ))
    cam_obj.location = center + offset
    direction = center - cam_obj.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    cam_obj.rotation_euler = rot_quat.to_euler()
    bpy.context.scene.camera = cam_obj
    return cam_obj


def world_to_screen(cam_obj, point_3d, render_w, render_h):
    """Project a 3D world point to 2D screen coordinates."""
    from bpy_extras.object_utils import world_to_camera_view
    scene = bpy.context.scene
    co = world_to_camera_view(scene, cam_obj, point_3d)
    # co.x and co.y are 0-1, co.z is depth
    if co.z <= 0:
        return None  # Behind camera
    x = int(co.x * render_w)
    y = int((1 - co.y) * render_h)  # Flip Y (screen space is top-down)
    if 0 <= x < render_w and 0 <= y < render_h:
        return (x, y)
    return None


def draw_markers_on_image(image_path, markers, output_path, radius=20, color=(255, 20, 40)):
    """Draw bright red circles/diamonds on a rendered image at the given screen positions."""
    # Load via Blender's image system and convert to numpy
    bimg = bpy.data.images.load(image_path)
    w, h = bimg.size
    pixels = np.array(bimg.pixels[:]).reshape(h, w, 4)
    # Blender images are bottom-up, flip to top-down for drawing
    pixels = np.flipud(pixels)

    r_f, g_f, b_f = color[0] / 255.0, color[1] / 255.0, color[2] / 255.0

    for mx, my in markers:
        # Draw filled circle
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                dist = math.sqrt(dx * dx + dy * dy)
                px, py = mx + dx, my + dy
                if 0 <= px < w and 0 <= py < h:
                    if dist <= radius:
                        # Solid core
                        pixels[py, px, 0] = r_f
                        pixels[py, px, 1] = g_f
                        pixels[py, px, 2] = b_f
                        pixels[py, px, 3] = 1.0
                    elif dist <= radius + 2:
                        # White border
                        pixels[py, px, 0] = 1.0
                        pixels[py, px, 1] = 1.0
                        pixels[py, px, 2] = 1.0
                        pixels[py, px, 3] = 1.0

    # Flip back to bottom-up and save
    pixels = np.flipud(pixels)
    out_img = bpy.data.images.new("QA_Marked", w, h, alpha=True)
    out_img.pixels = pixels.flatten().tolist()
    out_img.filepath_raw = output_path
    out_img.file_format = 'PNG'
    out_img.save()

    bpy.data.images.remove(bimg)
    bpy.data.images.remove(out_img)


def render_issue(obj, issue_items, issue_name, output_dir, cam):
    """Render shoe + draw red markers at issue locations."""
    if not issue_items:
        return None

    # Get 3D centers of issue faces in world space
    centers_3d = []
    for item in issue_items:
        if "center" in item:
            local = Vector(item["center"])
            world = obj.matrix_world @ local
            centers_3d.append(world)

    if not centers_3d:
        return None

    # Render the shoe
    shoe_path = os.path.join(output_dir, f"{issue_name}_base.png")
    bpy.context.scene.render.filepath = shoe_path
    bpy.ops.render.render(write_still=True)

    # Project 3D issue centers to 2D screen space
    render_w = bpy.context.scene.render.resolution_x
    render_h = bpy.context.scene.render.resolution_y

    markers = []
    for center in centers_3d:
        screen_pos = world_to_screen(cam, center, render_w, render_h)
        if screen_pos:
            markers.append(screen_pos)

    # Cluster nearby markers to avoid overlapping circles
    clustered = cluster_markers(markers, min_dist=30)

    if clustered:
        # Draw red markers on the rendered image
        final_path = os.path.join(output_dir, f"{issue_name}.png")
        draw_markers_on_image(shoe_path, clustered, final_path, radius=15)
        os.remove(shoe_path)
        print(f"MARKERS: {len(clustered)} markers drawn for {len(issue_items)} issues")
        return final_path
    else:
        # No visible markers (all behind camera), just use the shoe render
        final_path = os.path.join(output_dir, f"{issue_name}.png")
        os.rename(shoe_path, final_path)
        return final_path


def cluster_markers(markers, min_dist=30):
    """Merge nearby markers into centroids."""
    if not markers:
        return []
    clusters = []
    used = [False] * len(markers)
    for i, (x1, y1) in enumerate(markers):
        if used[i]:
            continue
        cluster = [(x1, y1)]
        used[i] = True
        for j, (x2, y2) in enumerate(markers):
            if not used[j] and math.sqrt((x1 - x2)**2 + (y1 - y2)**2) < min_dist:
                cluster.append((x2, y2))
                used[j] = True
        cx = int(sum(x for x, y in cluster) / len(cluster))
        cy = int(sum(y for x, y in cluster) / len(cluster))
        clusters.append((cx, cy))
    return clusters


def main():
    args = get_args()
    os.makedirs(args.output_dir, exist_ok=True)
    renders = []

    try:
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
        cam = frame_camera_on_object(main_mesh)

        issue_types = [
            ("flipped_normals", "flipped_normals"),
            ("negative_uv_coords", "negative_uv"),
            ("non_manifold_edges", "non_manifold"),
            ("out_of_range_uv_coords", "out_of_range_uv"),
        ]

        # Only render the shoe once, reuse for all issue types
        shoe_rendered = False
        for json_key, render_name in issue_types:
            items = issues.get(json_key, [])
            if items:
                path = render_issue(main_mesh, items, render_name, args.output_dir, cam)
                if path:
                    renders.append({"type": render_name, "path": path, "count": len(items)})

        bpy.data.objects.remove(cam)

    except Exception as e:
        import traceback
        traceback.print_exc()
        renders = [{"type": "error", "error": str(e), "count": 0}]

    with open(args.output_json, 'w') as f:
        json.dump({"renders": renders}, f, indent=2)
    print(f"ISSUE_RENDER_COMPLETE: {args.output_json}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        args = get_args()
        with open(args.output_json, 'w') as f:
            json.dump({"error": str(e), "renders": []}, f)
        sys.exit(1)
