import pytest
from backend.dashboard_api import extract_from_asset, _extract_from_scan, ScanData

SAMPLE_ASSET = {
    "id": "test123",
    "sku": "F5714D05U-K11",
    "canonicalAsset": {
        "id": "prod123",
        "brand": "Friboo",
        "color": "Navy",
        "silhouette": "sneaker",
        "versions": [{
            "files": [{
                "filename": "27d51ba0.glb",
                "type": "3d",
                "laterality": "left",
                "task": {
                    "three": {
                        "method": "covision_scan_touch_up",
                        "laterality": "left",
                        "iterations": [{
                            "sourceFilename": "132fb406.glb",
                            "previewFilename": "27d51ba0.glb",
                            "autoShadowFilename": "8806197c.glb"
                        }]
                    }
                }
            }]
        }]
    }
}

SAMPLE_SCAN = {
    "glbFilename": "rawscan.glb",
    "laterality": "left",
    "product": {
        "modelCode": "F5714D05U-K11",
        "brand": "Friboo",
        "color": "Navy",
        "silhouette": "sneaker",
        "clientTags": [{"key": "clientSku", "value": "F5714D05U-K11"}],
        "versions": [{
            "files": [{
                "type": "3d",
                "laterality": "left",
                "task": {
                    "three": {
                        "method": "covision_scan_touch_up",
                        "iterations": [{
                            "sourceFilename": "source.glb",
                            "previewFilename": "preview.glb",
                            "autoShadowFilename": "shadow.glb"
                        }]
                    }
                }
            }]
        }]
    }
}


def test_extract_from_asset():
    result = extract_from_asset(SAMPLE_ASSET, "F5714D05U-K11")
    assert result.sku == "F5714D05U-K11"
    assert result.brand == "Friboo"
    assert result.color == "Navy"
    assert result.silhouette == "sneaker"
    assert result.raw_scan_filename == "132fb406.glb"
    assert result.touchedup_filename == "27d51ba0.glb"
    assert result.autoshadow_filename == "8806197c.glb"


def test_extract_from_asset_no_versions():
    asset = {"canonicalAsset": {"versions": []}}
    with pytest.raises(ValueError, match="No published version"):
        extract_from_asset(asset, "TEST")


def test_extract_from_scan():
    result = _extract_from_scan(SAMPLE_SCAN, "F5714D05U-K11")
    assert result.sku == "F5714D05U-K11"
    assert result.touchedup_filename == "preview.glb"
    assert result.autoshadow_filename == "shadow.glb"
