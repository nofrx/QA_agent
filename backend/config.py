import json
import os
from dataclasses import dataclass

@dataclass
class Config:
    api_key: str
    cloudfront_base: str
    dashboard_api: str
    dashboard_viewer: str
    blender_path: str
    reports_dir: str
    port: int
    glb_cache_dir: str = ""

def load_config(path: str) -> Config:
    with open(path) as f:
        data = json.load(f)
    data["reports_dir"] = os.path.expanduser(data["reports_dir"])
    data.setdefault("glb_cache_dir", os.path.expanduser("~/.shoe-qa-cache/glb"))
    return Config(**data)
