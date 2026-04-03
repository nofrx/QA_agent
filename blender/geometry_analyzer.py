"""
Geometry analysis script for Blender headless.
Usage: blender -b -P geometry_analyzer.py -- --glb_path /path/to.glb --output /path/to/results.json
"""
import bpy
import bmesh
import json
import sys
import os
import traceback
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
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def import_glb(path):
    """Import GLB and return mesh objects. Raises on failure."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"GLB file not found: {path}")
    result = bpy.ops.import_scene.gltf(filepath=path)
    if 'FINISHED' not in result:
        raise RuntimeError(f"GLB import failed: {result}")
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    if not meshes:
        raise RuntimeError("No mesh objects found after GLB import")
    return meshes


def analyze_mesh(obj):
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.normal_update()

    result = {
        "name": obj.name,
        "vertices": len(bm.verts),
        "faces": len(bm.faces),
        "edges": len(bm.edges),
    }

    # Bounding box
    bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    mins = [min(v[i] for v in bbox) for i in range(3)]
    maxs = [max(v[i] for v in bbox) for i in range(3)]
    result["bounding_box"] = {
        "min": [round(v, 4) for v in mins],
        "max": [round(v, 4) for v in maxs],
        "size": [round(maxs[i] - mins[i], 4) for i in range(3)],
    }

    # Flipped normals — use local neighborhood comparison, not global center.
    # A face is "flipped" if its normal points opposite to the average of its neighbors.
    flipped = []
    for face in bm.faces:
        neighbor_normals = []
        for edge in face.edges:
            for linked_face in edge.link_faces:
                if linked_face != face:
                    neighbor_normals.append(linked_face.normal)
        if neighbor_normals:
            avg_neighbor = sum(neighbor_normals, Vector()) / len(neighbor_normals)
            if face.normal.dot(avg_neighbor) < -0.5:
                center = face.calc_center_median()
                flipped.append({
                    "face_index": face.index,
                    "center": [round(center.x, 4), round(center.y, 4), round(center.z, 4)],
                    "normal": [round(face.normal.x, 4), round(face.normal.y, 4), round(face.normal.z, 4)],
                })
    result["flipped_normals"] = flipped[:100]
    result["flipped_normals_count"] = len(flipped)

    # Non-manifold edges
    non_manifold = []
    for edge in bm.edges:
        if not edge.is_manifold and not edge.is_boundary:
            center = (edge.verts[0].co + edge.verts[1].co) / 2
            non_manifold.append({
                "edge_index": edge.index,
                "center": [round(center.x, 4), round(center.y, 4), round(center.z, 4)],
            })
    result["non_manifold_edges"] = non_manifold[:100]
    result["non_manifold_count"] = len(non_manifold)

    # Loose vertices
    loose = [
        {"index": v.index, "co": [round(v.co.x, 4), round(v.co.y, 4), round(v.co.z, 4)]}
        for v in bm.verts if not v.link_edges
    ]
    result["loose_vertices"] = loose[:100]
    result["loose_vertices_count"] = len(loose)

    # UV analysis
    uv_layers = mesh.uv_layers
    result["uv_layer_count"] = len(uv_layers)
    result["negative_uv_count"] = 0
    result["out_of_range_uv_count"] = 0
    result["uv_overlap_count"] = 0

    if uv_layers:
        uv_layer = bm.loops.layers.uv.active
        if uv_layer:
            # Negative UV coordinates (< 0) — can't be baked
            negative_uvs = []
            out_of_range_uvs = []
            for face in bm.faces:
                for loop in face.loops:
                    uv = loop[uv_layer].uv
                    if uv.x < 0 or uv.y < 0:
                        center = face.calc_center_median()
                        negative_uvs.append({
                            "face_index": face.index,
                            "uv": [round(uv.x, 4), round(uv.y, 4)],
                            "center": [round(center.x, 4), round(center.y, 4), round(center.z, 4)],
                        })
                        break  # One per face is enough
                    if uv.x > 1.01 or uv.y > 1.01:
                        center = face.calc_center_median()
                        out_of_range_uvs.append({
                            "face_index": face.index,
                            "uv": [round(uv.x, 4), round(uv.y, 4)],
                            "center": [round(center.x, 4), round(center.y, 4), round(center.z, 4)],
                        })
                        break
            result["negative_uv_coords"] = negative_uvs[:50]
            result["negative_uv_count"] = len(negative_uvs)
            result["out_of_range_uv_coords"] = out_of_range_uvs[:50]
            result["out_of_range_uv_count"] = len(out_of_range_uvs)

    # Materials
    result["material_count"] = len(mesh.materials)
    result["materials"] = [
        {"name": mat.name if mat else "None", "index": i}
        for i, mat in enumerate(mesh.materials)
    ]

    bm.free()
    return result


def analyze_textures(obj):
    textures = []
    seen = set()
    for mat in obj.data.materials:
        if not mat or not mat.node_tree:
            continue
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                img = node.image
                if img.name in seen:
                    continue
                seen.add(img.name)
                textures.append({
                    "name": img.name,
                    "width": img.size[0],
                    "height": img.size[1],
                    "is_4k": img.size[0] == 4096 and img.size[1] == 4096,
                })
    return textures


def main():
    args = get_args()

    try:
        clear_scene()
        meshes = import_glb(args.glb_path)
        main_mesh = max(meshes, key=lambda o: len(o.data.polygons))

        result = analyze_mesh(main_mesh)
        result["textures"] = analyze_textures(main_mesh)
        result["total_meshes"] = len(meshes)
        result["file_path"] = args.glb_path
        result["file_size_mb"] = round(os.path.getsize(args.glb_path) / (1024 * 1024), 2)

    except Exception as e:
        traceback.print_exc()
        result = {
            "error": str(e),
            "file_path": args.glb_path,
            "vertices": 0, "faces": 0, "edges": 0,
            "flipped_normals_count": 0, "non_manifold_count": 0,
            "loose_vertices_count": 0, "negative_uv_count": 0,
            "out_of_range_uv_count": 0, "uv_overlap_count": 0,
            "textures": [], "materials": [],
        }

    result["total_issues"] = (
        result.get("flipped_normals_count", 0)
        + result.get("non_manifold_count", 0)
        + result.get("loose_vertices_count", 0)
        + result.get("negative_uv_count", 0)
        + result.get("out_of_range_uv_count", 0)
    )

    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"GEOMETRY_ANALYSIS_COMPLETE: {args.output}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Write error JSON even on crash so backend doesn't hang
        traceback.print_exc()
        args = get_args()
        with open(args.output, 'w') as f:
            json.dump({"error": str(e), "total_issues": 0}, f)
        sys.exit(1)
