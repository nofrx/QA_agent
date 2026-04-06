import os
import tempfile
from backend.storage import Storage

def test_create_session():
    with tempfile.TemporaryDirectory() as d:
        storage = Storage(d)
        path = storage.create_session("F5714D05U-K11")
        assert os.path.isdir(path)
        assert "F5714D05U-K11" in path
        assert os.path.isdir(os.path.join(path, "textures"))

def test_list_reports():
    with tempfile.TemporaryDirectory() as d:
        storage = Storage(d)
        storage.create_session("SKU-A")
        storage.create_session("SKU-B")
        storage.create_session("SKU-A")
        reports = storage.list_reports()
        assert len(reports) == 3
        sku_a_reports = [r for r in reports if r["sku"] == "SKU-A"]
        assert len(sku_a_reports) == 2
