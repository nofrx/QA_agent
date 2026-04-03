import json
import os
import tempfile
import pytest
from backend.config import load_config, Config

def test_load_config_from_file():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({
            "api_key": "test-key",
            "cloudfront_base": "https://example.com/3e",
            "dashboard_api": "https://example.com/api",
            "dashboard_viewer": "https://example.com/viewer",
            "blender_path": "/usr/bin/blender",
            "reports_dir": "/tmp/reports",
            "port": 9090
        }, f)
        f.flush()
        config = load_config(f.name)
    os.unlink(f.name)
    assert config.api_key == "test-key"
    assert config.port == 9090
    assert config.reports_dir == "/tmp/reports"

def test_config_expands_home_dir():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({
            "api_key": "k",
            "cloudfront_base": "https://example.com/3e",
            "dashboard_api": "https://example.com/api",
            "dashboard_viewer": "https://example.com/viewer",
            "blender_path": "/usr/bin/blender",
            "reports_dir": "~/ShoeQA/reports",
            "port": 8080
        }, f)
        f.flush()
        config = load_config(f.name)
    os.unlink(f.name)
    assert "~" not in config.reports_dir
    assert os.path.expanduser("~") in config.reports_dir
