"""
Geometry analysis script for Blender headless.
Usage: blender -b -P geometry_analyzer.py -- --glb_path /path/to.glb --output /path/to/results.json
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
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def import_glb(path):
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o.type == 'MESH']


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
        "min": mins,
        "max": maxs,
        "size": [maxs[i] - mins[i] for i in range(3)],
    }

    # Flipped normals
    flipped = []
    mesh_center = sum((v.co for v in bm.verts), Vector()) / max(len(bm.verts), 1)
    for face in bm.faces:
        center = face.calc_center_median()
        to_center = (mesh_center - center).normalized()
        if face.normal.dot(to_center) > 0.5:
            flipped.append({
                "face_index": face.index,
                "center": list(center),
                "normal": list(face.normal),
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
                "center": list(center),
            })
    result["non_manifold_edges"] = non_manifold[:100]
    result["non_manifold_count"] = len(non_manifold)

    # Loose vertices
    loose = [
        {"index": v.index, "co": list(v.co)}
        for v in bm.verts if not v.link_edges
    ]
    result["loose_vertices"] = loose[:100]
    result["loose_vertices_count"] = len(loose)

    # UV analysis
    uv_layers = mesh.uv_layers
    result["uv_layer_count"] = len(uv_layers)
    if uv_layers:
        uv_layer = bm.loops.layers.uv.active
        if uv_layer:
            negative_uvs = []
            for face in bm.faces:
                for loop in face.loops:
                    uv = loop[uv_layer].uv
                    if uv.x < 0 or uv.y < 0:
                        center = face.calc_center_median()
                        negative_uvs.append({
                            "face_index": face.index,
                            "uv": [uv.x, uv.y],
                            "center": list(center),
                        })
            result["negative_uv_coords"] = negative_uvs[:50]
            result["negative_uv_count"] = len(negative_uvs)

            uv_positions = {}
            overlaps = 0
            for face in bm.faces:
                face_uvs = tuple(
                    (round(loop[uv_layer].uv.x, 4), round(loop[uv_layer].uv.y, 4))
                    for loop in face.loops
                )
                if face_uvs in uv_positions:
                    overlaps += 1
                else:
                    uv_positions[face_uvs] = face.index
            result["uv_overlap_count"] = overlaps

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
    for mat in obj.data.materials:
        if not mat or not mat.node_tree:
            continue
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                img = node.image
                textures.append({
                    "name": img.name,
                    "width": img.size[0],
                    "height": img.size[1],
                    "is_4k": img.size[0] == 4096 and img.size[1] == 4096,
                })
    return textures


def main():
    args = get_args()
    clear_scene()
    meshes = import_glb(args.glb_path)

    if not meshes:
        result = {"error": "No meshes found in GLB"}
    else:
        main_mesh = max(meshes, key=lambda o: len(o.data.polygons))
        result = analyze_mesh(main_mesh)
        result["textures"] = analyze_textures(main_mesh)
        result["total_meshes"] = len(meshes)
        result["file_path"] = args.glb_path
        result["file_size_mb"] = round(os.path.getsize(args.glb_path) / (1024 * 1024), 2)

    result["total_issues"] = (
        result.get("flipped_normals_count", 0)
        + result.get("non_manifold_count", 0)
        + result.get("loose_vertices_count", 0)
        + result.get("negative_uv_count", 0)
        + result.get("uv_overlap_count", 0)
    )

    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"GEOMETRY_ANALYSIS_COMPLETE: {args.output}")


if __name__ == "__main__":
    main()
