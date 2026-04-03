import subprocess
import json
import os


def run_blender_script(
    blender_path: str, script_path: str, args: list[str], timeout: int = 300
) -> str:
    cmd = [blender_path, "-b", "-P", script_path, "--"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"Blender script failed (exit {result.returncode}):\n"
            f"STDOUT: {result.stdout[-2000:]}\n"
            f"STDERR: {result.stderr[-2000:]}"
        )
    return result.stdout


def run_geometry_analysis(
    blender_path: str, glb_path: str, output_json: str
) -> dict:
    script_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blender"
    )
    script_path = os.path.join(script_dir, "geometry_analyzer.py")
    run_blender_script(
        blender_path, script_path, ["--glb_path", glb_path, "--output", output_json]
    )
    with open(output_json) as f:
        return json.load(f)


def run_texture_extraction(
    blender_path: str, glb_path: str, output_dir: str
) -> dict:
    script_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blender"
    )
    script_path = os.path.join(script_dir, "texture_extractor.py")
    output_json = os.path.join(output_dir, "extraction_result.json")
    run_blender_script(
        blender_path,
        script_path,
        ["--glb_path", glb_path, "--output_dir", output_dir, "--output_json", output_json],
    )
    with open(output_json) as f:
        return json.load(f)


def run_issue_renderer(
    blender_path: str, glb_path: str, issues_json: str, output_dir: str
) -> dict:
    script_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blender"
    )
    script_path = os.path.join(script_dir, "issue_renderer.py")
    output_json = os.path.join(output_dir, "render_result.json")
    run_blender_script(
        blender_path,
        script_path,
        [
            "--glb_path", glb_path,
            "--issues_json", issues_json,
            "--output_dir", output_dir,
            "--output_json", output_json,
        ],
        timeout=600,
    )
    with open(output_json) as f:
        return json.load(f)
