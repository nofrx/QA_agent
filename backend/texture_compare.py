import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import os
from dataclasses import dataclass


@dataclass
class TextureDiff:
    pct_changed: float
    max_diff: int
    mean_diff: float
    heatmap_path: str
    overlay_path: str
    side_by_side_path: str
    changed_regions: list


def compare_textures(path_a: str, path_b: str, output_dir: str, name: str) -> TextureDiff:
    img_a = np.array(Image.open(path_a).convert('RGB'))
    img_b = np.array(Image.open(path_b).convert('RGB'))

    if img_a.shape != img_b.shape:
        h = max(img_a.shape[0], img_b.shape[0])
        w = max(img_a.shape[1], img_b.shape[1])
        img_a = np.array(Image.fromarray(img_a).resize((w, h)))
        img_b = np.array(Image.fromarray(img_b).resize((w, h)))

    diff = np.abs(img_a.astype(np.int16) - img_b.astype(np.int16)).astype(np.uint8)
    diff_gray = np.max(diff, axis=2)

    threshold = 5
    changed_mask = diff_gray > threshold
    total_pixels = diff_gray.size
    changed_pixels = int(np.sum(changed_mask))

    pct_changed = round(changed_pixels / total_pixels * 100, 2)
    max_diff = int(np.max(diff_gray))
    mean_diff = round(float(np.mean(diff_gray[changed_mask])) if changed_pixels > 0 else 0, 2)

    # Heatmap
    heatmap = np.zeros((*diff_gray.shape, 3), dtype=np.uint8)
    if max_diff > 0:
        normalized = (diff_gray.astype(np.float32) / max(max_diff, 1) * 255).astype(np.uint8)
        heatmap[:, :, 0] = normalized
        heatmap[:, :, 2] = 255 - normalized
        heatmap[~changed_mask] = [0, 0, 0]
    heatmap_path = os.path.join(output_dir, f"{name}_heatmap.png")
    Image.fromarray(heatmap).save(heatmap_path)

    # Overlay with red outlines
    mask_img = Image.fromarray((changed_mask * 255).astype(np.uint8))
    dilated = mask_img.filter(ImageFilter.MaxFilter(5))
    eroded = mask_img.filter(ImageFilter.MinFilter(5))
    outline = np.array(dilated).astype(np.int16) - np.array(eroded).astype(np.int16)
    outline = np.clip(outline, 0, 255).astype(np.uint8)
    overlay_arr = img_a.copy()
    outline_mask = outline > 128
    overlay_arr[outline_mask, 0] = 255
    overlay_arr[outline_mask, 1] = 0
    overlay_arr[outline_mask, 2] = 0
    overlay_path = os.path.join(output_dir, f"{name}_overlay.png")
    Image.fromarray(overlay_arr).save(overlay_path)

    # Side-by-side (A | B | Heatmap)
    h, w = img_a.shape[:2]
    gap = 10
    sbs = np.zeros((h, w * 3 + gap * 2, 3), dtype=np.uint8)
    sbs[:, :w] = img_a
    sbs[:, w + gap:w * 2 + gap] = img_b
    sbs[:, w * 2 + gap * 2:] = np.array(Image.fromarray(heatmap).resize((w, h)))
    sbs_path = os.path.join(output_dir, f"{name}_sidebyside.png")
    Image.fromarray(sbs).save(sbs_path)

    # Find changed regions
    regions = []
    if np.any(changed_mask):
        rows = np.any(changed_mask, axis=1)
        cols = np.any(changed_mask, axis=0)
        if np.any(rows) and np.any(cols):
            y_min, y_max = int(np.where(rows)[0][0]), int(np.where(rows)[0][-1])
            x_min, x_max = int(np.where(cols)[0][0]), int(np.where(cols)[0][-1])
            if (x_max - x_min) * (y_max - y_min) >= 100:
                regions.append({"x": x_min, "y": y_min, "w": x_max - x_min, "h": y_max - y_min})

    return TextureDiff(
        pct_changed=pct_changed, max_diff=max_diff, mean_diff=mean_diff,
        heatmap_path=heatmap_path, overlay_path=overlay_path,
        side_by_side_path=sbs_path, changed_regions=regions
    )
