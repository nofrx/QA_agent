import numpy as np
from PIL import Image
import tempfile
import os
from backend.texture_compare import compare_textures, TextureDiff


def test_identical_textures():
    img = np.full((256, 256, 3), 128, dtype=np.uint8)
    with tempfile.TemporaryDirectory() as d:
        path_a = os.path.join(d, "a.png")
        path_b = os.path.join(d, "b.png")
        Image.fromarray(img).save(path_a)
        Image.fromarray(img).save(path_b)
        result = compare_textures(path_a, path_b, d, "test")
    assert result.pct_changed == 0.0
    assert result.max_diff == 0
    assert result.mean_diff == 0.0


def test_different_textures():
    img_a = np.full((256, 256, 3), 128, dtype=np.uint8)
    img_b = img_a.copy()
    img_b[100:150, 100:150] = 255
    with tempfile.TemporaryDirectory() as d:
        path_a = os.path.join(d, "a.png")
        path_b = os.path.join(d, "b.png")
        Image.fromarray(img_a).save(path_a)
        Image.fromarray(img_b).save(path_b)
        result = compare_textures(path_a, path_b, d, "test")
        assert result.pct_changed > 0
        assert result.max_diff == 127
        assert os.path.exists(result.heatmap_path)
        assert os.path.exists(result.overlay_path)
