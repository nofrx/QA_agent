import pytest
from backend.dashboard_api import extract_sku_files, ScanData

SAMPLE_SCAN = {
    "glbFilename": "2c7265d7-0089-4044-8d05-bca28639cd28.glb",
    "laterality": "left",
    "product": {
        "modelCode": "F5714D05U-K11",
        "brand": "Friboo",
        "color": "Navy",
        "silhouette": "sneaker",
        "clientTags": [
            {"key": "clientSku", "value": "F5714D05U-K11"}
        ],
        "versions": [{
            "files": [{
                "filename": "27d51ba0-2e90-490b-ba82-281b8f4c6604.glb",
                "type": "3d",
                "laterality": "left",
                "task": {
                    "three": {
                        "method": "covision_scan_touch_up",
                        "laterality": "left",
                        "iterations": [{
                            "sourceFilename": "132fb406-41bd-4388-8fe2-d184e9e8d8e4.glb",
                            "previewFilename": "27d51ba0-2e90-490b-ba82-281b8f4c6604.glb",
                            "autoShadowFilename": "8806197c-44cf-4cbc-b2c0-522ab8067bd1.glb"
                        }]
                    }
                }
            }]
        }]
    }
}

def test_extract_sku_files():
    result = extract_sku_files(SAMPLE_SCAN)
    assert result.sku == "F5714D05U-K11"
    assert result.brand == "Friboo"
    assert result.color == "Navy"
    assert result.silhouette == "sneaker"
    assert result.raw_scan_filename == "2c7265d7-0089-4044-8d05-bca28639cd28.glb"
    assert result.touchedup_filename == "27d51ba0-2e90-490b-ba82-281b8f4c6604.glb"
    assert result.autoshadow_filename == "8806197c-44cf-4cbc-b2c0-522ab8067bd1.glb"

def test_extract_sku_files_no_iterations():
    scan = {
        "glbFilename": "raw.glb",
        "laterality": "left",
        "product": {
            "modelCode": "TEST-SKU",
            "clientTags": [{"key": "clientSku", "value": "TEST-SKU"}],
            "versions": []
        }
    }
    with pytest.raises(ValueError, match="No published version"):
        extract_sku_files(scan)
