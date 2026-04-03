import os
import json
from datetime import datetime

class Storage:
    def __init__(self, reports_dir: str):
        self.reports_dir = reports_dir
        os.makedirs(reports_dir, exist_ok=True)

    def create_session(self, sku: str) -> str:
        # Sanitize SKU to prevent path traversal
        sku = os.path.basename(sku)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        session_dir = os.path.join(self.reports_dir, sku, timestamp)
        os.makedirs(session_dir, exist_ok=True)
        os.makedirs(os.path.join(session_dir, "textures"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "screenshots"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "issues"), exist_ok=True)
        metadata = {"sku": sku, "created_at": datetime.now().isoformat(), "status": "in_progress"}
        with open(os.path.join(session_dir, "metadata.json"), 'w') as f:
            json.dump(metadata, f, indent=2)
        return session_dir

    def save_metadata(self, session_dir: str, metadata: dict):
        with open(os.path.join(session_dir, "metadata.json"), 'w') as f:
            json.dump(metadata, f, indent=2)

    def list_reports(self) -> list[dict]:
        reports = []
        if not os.path.isdir(self.reports_dir):
            return reports
        for sku in sorted(os.listdir(self.reports_dir)):
            sku_dir = os.path.join(self.reports_dir, sku)
            if not os.path.isdir(sku_dir):
                continue
            for session in sorted(os.listdir(sku_dir), reverse=True):
                session_dir = os.path.join(sku_dir, session)
                if not os.path.isdir(session_dir):
                    continue
                meta_path = os.path.join(session_dir, "metadata.json")
                meta = {}
                if os.path.exists(meta_path):
                    with open(meta_path) as f:
                        meta = json.load(f)
                reports.append({"sku": sku, "session": session, "path": session_dir,
                               "has_report": os.path.exists(os.path.join(session_dir, "report.html")), **meta})
        return reports
