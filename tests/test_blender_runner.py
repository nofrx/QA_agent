import os
import pytest
from backend.blender_runner import run_blender_script


def test_run_blender_script_nonexistent_blender():
    with pytest.raises(FileNotFoundError):
        run_blender_script("/nonexistent/blender", "test.py", [])


def test_run_geometry_analysis_invalid_glb():
    """Geometry analysis on a non-GLB file should fail."""
    blender = "/Applications/Blender 4.58.app/Contents/MacOS/Blender"
    if not os.path.exists(blender):
        pytest.skip("Blender 4.58 not installed")
    from backend.blender_runner import run_geometry_analysis
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as f:
        f.write(b"not a glb file")
        tmp = f.name
    try:
        with pytest.raises(RuntimeError):
            run_geometry_analysis(blender, tmp, "/tmp/test_geom.json")
    finally:
        os.unlink(tmp)
