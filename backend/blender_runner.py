import subprocess
import json
import os


def run_blender_script(
    blender_path: str, script_path: str, args: list[str], timeout: int = 300
) -> str:
    """Run a Python script inside Blender headless."""
    if not os.path.exists(blender_path):
        raise FileNotFoundError(f"Blender not found: {blender_path}")

    cmd = [blender_path, "-b", "-P", script_path, "--"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Blender script timed out after {timeout}s: {script_path}")

    if result.returncode != 0:
        raise RuntimeError(
            f"Blender script failed (exit {result.returncode}):\n"
            f"STDOUT: {result.stdout[-2000:]}\n"
            f"STDERR: {result.stderr[-2000:]}"
        )
    return result.stdout


def _read_json_output(output_json: str, script_name: str) -> dict:
    """Read and validate Blender script JSON output."""
    if not os.path.exists(output_json):
        raise RuntimeError(
            f"Blender {script_name} did not produce output file: {output_json}"
        )
    with open(output_json) as f:
        data = json.load(f)
    if "error" in data and not data.get("textures") and not data.get("renders"):
        raise RuntimeError(f"Blender {script_name} error: {data['error']}")
    return data


def _blender_script_path(script_name: str) -> str:
    """Get path to a Blender script in the blender/ directory."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "blender", script_name
    )


def run_geometry_analysis(blender_path: str, glb_path: str, output_json: str) -> dict:
    run_blender_script(
        blender_path,
        _blender_script_path("geometry_analyzer.py"),
        ["--glb_path", glb_path, "--output", output_json],
        timeout=600,
    )
    return _read_json_output(output_json, "geometry_analyzer")


def run_texture_extraction(blender_path: str, glb_path: str, output_dir: str) -> dict:
    basename = os.path.splitext(os.path.basename(glb_path))[0]
    output_json = os.path.join(output_dir, f"extraction_{basename}.json")
    run_blender_script(
        blender_path,
        _blender_script_path("texture_extractor.py"),
        ["--glb_path", glb_path, "--output_dir", output_dir, "--output_json", output_json],
        timeout=600,
    )
    return _read_json_output(output_json, "texture_extractor")


def run_issue_renderer(blender_path: str, glb_path: str, issues_json: str, output_dir: str) -> dict:
    output_json = os.path.join(output_dir, "render_result.json")
    run_blender_script(
        blender_path,
        _blender_script_path("issue_renderer.py"),
        ["--glb_path", glb_path, "--issues_json", issues_json,
         "--output_dir", output_dir, "--output_json", output_json],
        timeout=600,
    )
    return _read_json_output(output_json, "issue_renderer")
