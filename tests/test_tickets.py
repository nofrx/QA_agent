import os
import json
import tempfile
from backend.storage import Storage


def test_load_tickets_returns_empty_when_missing():
    with tempfile.TemporaryDirectory() as d:
        storage = Storage(d)
        tickets = storage.load_tickets("SKU-A", "session-1")
        assert tickets == []


def test_save_then_load_round_trip():
    with tempfile.TemporaryDirectory() as d:
        storage = Storage(d)
        # Need a real session dir for save to work
        session_dir = storage.create_session("SKU-A")
        session_name = os.path.basename(session_dir)
        sample = [
            {"id": "t1", "color": "#ff2020", "comment": "issue here", "points": [{"x": 1, "y": 2, "z": 3}]},
            {"id": "t2", "color": "#66bb6a", "comment": "looks good", "points": []},
        ]
        storage.save_tickets("SKU-A", session_name, sample)
        loaded = storage.load_tickets("SKU-A", session_name)
        assert loaded == sample


def test_save_tickets_path_traversal_sanitized():
    with tempfile.TemporaryDirectory() as d:
        storage = Storage(d)
        session_dir = storage.create_session("SKU-A")
        session_name = os.path.basename(session_dir)
        # Attempt traversal in sku — basename should strip it
        storage.save_tickets("../../etc/passwd", session_name, [{"id": "x"}])
        # File should NOT exist outside the storage dir
        bad_path = os.path.join(d, "..", "..", "etc", "passwd")
        assert not os.path.exists(bad_path)


def test_load_tickets_handles_corrupt_json():
    with tempfile.TemporaryDirectory() as d:
        storage = Storage(d)
        session_dir = storage.create_session("SKU-A")
        session_name = os.path.basename(session_dir)
        # Write garbage to tickets file
        path = os.path.join(session_dir, "tickets.json")
        with open(path, "w") as f:
            f.write("{not valid json")
        loaded = storage.load_tickets("SKU-A", session_name)
        assert loaded == []
