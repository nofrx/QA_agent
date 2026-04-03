"""
Extract PBR textures from GLB materials.
Usage: blender -b -P texture_extractor.py -- --glb_path /path/to.glb --output_dir /path/to/out --output_json /path/to/result.json
"""
import bpy
import json
import sys
import os


def get_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb_path", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--output_json", required=True)
    return parser.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def find_image_from_input(socket):
    if not socket.is_linked:
        return None
    node = socket.links[0].from_node
    if node.type == 'TEX_IMAGE' and node.image:
        return node
    if node.type == 'NORMAL_MAP':
        color_input = node.inputs.get("Color")
        if color_input:
            return find_image_from_input(color_input)
    if node.type in ('SEPARATE_COLOR', 'SEPRGB', 'SEPXYZ'):
        return find_image_from_input(node.inputs[0])
    if node.type == 'GROUP':
        for inp in node.inputs:
            result = find_image_from_input(inp)
            if result:
                return result
    for inp in node.inputs:
        if inp.is_linked:
            result = find_image_from_input(inp)
            if result:
                return result
    return None


def extract_textures(mesh_obj, output_dir, prefix):
    results = {}
    for mat in mesh_obj.data.materials:
        if not mat or not mat.node_tree:
            continue

        bsdf = None
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                bsdf = node
                break
        if not bsdf:
            continue

        texture_map = {
            "basecolor": "Base Color",
            "normal": "Normal",
            "roughness": "Roughness",
            "metallic": "Metallic",
        }

        for tex_name, input_name in texture_map.items():
            input_socket = bsdf.inputs.get(input_name)
            if not input_socket:
                continue
            img_node = find_image_from_input(input_socket)
            if not img_node or not img_node.image:
                continue
            img = img_node.image
            output_path = os.path.join(output_dir, f"{prefix}_{tex_name}.png")
            img.filepath_raw = output_path
            img.file_format = 'PNG'
            img.save()
            results[tex_name] = {
                "path": output_path,
                "width": img.size[0],
                "height": img.size[1],
                "name": img.name,
            }

        # Try ORM packed texture
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                name_lower = node.image.name.lower()
                if 'orm' in name_lower or 'occlusionroughnessmetallic' in name_lower:
                    img = node.image
                    output_path = os.path.join(output_dir, f"{prefix}_orm.png")
                    img.filepath_raw = output_path
                    img.file_format = 'PNG'
                    img.save()
                    results["orm"] = {
                        "path": output_path,
                        "width": img.size[0],
                        "height": img.size[1],
                        "name": img.name,
                    }
        break
    return results


def main():
    args = get_args()
    os.makedirs(args.output_dir, exist_ok=True)
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=args.glb_path)
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']

    if not meshes:
        result = {"error": "No meshes found", "textures": {}}
    else:
        main_mesh = max(meshes, key=lambda o: len(o.data.polygons))
        basename = os.path.basename(args.glb_path).replace('.glb', '')
        textures = extract_textures(main_mesh, args.output_dir, basename)
        result = {"textures": textures, "mesh_name": main_mesh.name}

    with open(args.output_json, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"TEXTURE_EXTRACTION_COMPLETE: {args.output_json}")


if __name__ == "__main__":
    main()
