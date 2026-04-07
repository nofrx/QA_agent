"""Tests for the storyboard HTML export endpoint."""
import os
import json
import tempfile
from datetime import datetime
from jinja2 import Environment, FileSystemLoader


TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")


def _render_storyboard(tickets, sku="TEST-SKU", brand="TestBrand", color="Black"):
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
    template = env.get_template("storyboard_template.html")
    for t in tickets:
        try:
            dt = datetime.fromisoformat(t.get("created_at", "").replace("Z", "+00:00"))
            t["created_at_pretty"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            t["created_at_pretty"] = t.get("created_at", "")
    return template.render(
        sku=sku,
        brand=brand,
        color=color,
        generated_at="2026-04-07 12:00",
        tickets=tickets,
        model_labels={
            "raw": "Raw Scan",
            "source": "Source",
            "optimised": "Optimised",
            "autoshadow": "AutoShadow",
        },
    )


def test_storyboard_renders_with_no_tickets():
    html = _render_storyboard([])
    assert "<!DOCTYPE html>" in html
    assert "TEST-SKU" in html
    assert "No annotations yet" in html


def test_storyboard_renders_with_tickets():
    tickets = [
        {
            "id": "t1",
            "color": "#ff2020",
            "comment": "Visible seam on the heel",
            "model_key": "raw",
            "screenshot": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA",
            "created_at": "2026-04-07T10:30:00",
            "points": [{"x": 1, "y": 2, "z": 3}],
        },
        {
            "id": "t2",
            "color": "#66bb6a",
            "comment": "Looks good here",
            "model_key": "autoshadow",
            "screenshot": "",
            "created_at": "2026-04-07T10:35:00",
            "points": [],
        },
    ]
    html = _render_storyboard(tickets)
    assert "Visible seam on the heel" in html
    assert "Looks good here" in html
    assert "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA" in html
    assert "Raw Scan" in html
    assert "AutoShadow" in html
    assert "No screenshot captured" in html  # second ticket has no screenshot
    assert "#ff2020" in html
    assert "#66bb6a" in html


def test_storyboard_escapes_html_in_comments():
    tickets = [{
        "id": "t1",
        "color": "#ff2020",
        "comment": "<script>alert('xss')</script>",
        "model_key": "raw",
        "screenshot": "",
        "created_at": "2026-04-07T10:30:00",
        "points": [],
    }]
    html = _render_storyboard(tickets)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html or "&amp;lt;script&amp;gt;" in html


def test_storyboard_handles_unknown_model_key():
    tickets = [{
        "id": "t1",
        "color": "#ff2020",
        "comment": "test",
        "model_key": "weird_model",
        "screenshot": "",
        "created_at": "2026-04-07T10:30:00",
        "points": [],
    }]
    html = _render_storyboard(tickets)
    assert "weird_model" in html  # falls back to the raw key
