import asyncio
import os
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.responses import StreamingResponse
from backend.config import load_config
from backend.pipeline import run_qa_pipeline
from backend.storage import Storage

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
config = load_config(CONFIG_PATH)
storage = Storage(config.reports_dir)

app = FastAPI(title="Shoe QA")

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

jobs: dict[str, dict] = {}


@app.get("/")
async def index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.get("/reports")
async def reports_page():
    return FileResponse(os.path.join(frontend_dir, "reports.html"))


@app.post("/api/analyze/{sku}")
async def start_analysis(sku: str):
    sku = sku.strip().upper()
    if sku in jobs and jobs[sku].get("status") == "running":
        raise HTTPException(400, f"Analysis already running for {sku}")
    jobs[sku] = {"status": "running", "messages": [], "result": None, "session_dir": None}

    async def run():
        try:
            async def on_progress(msg):
                jobs[sku]["messages"].append(msg)
            report_path, session_dir = await run_qa_pipeline(config, sku, on_progress)
            jobs[sku]["status"] = "complete"
            jobs[sku]["result"] = report_path
            jobs[sku]["session_dir"] = session_dir
        except Exception as e:
            jobs[sku]["status"] = "error"
            jobs[sku]["messages"].append(f"Error: {str(e)}")

    asyncio.create_task(run())
    return {"job_id": sku, "status": "started"}


@app.get("/api/status/{sku}")
async def job_status(sku: str):
    sku = sku.strip().upper()

    async def event_stream():
        sent = 0
        while True:
            job = jobs.get(sku)
            if not job:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Job not found'})}\n\n"
                break
            while sent < len(job["messages"]):
                yield f"data: {json.dumps({'type': 'progress', 'message': job['messages'][sent]})}\n\n"
                sent += 1
            if job["status"] == "complete":
                session_dir = job.get("session_dir", "")
                sku_name = os.path.basename(os.path.dirname(session_dir)) if session_dir else sku
                session_name = os.path.basename(session_dir) if session_dir else ""
                yield f"data: {json.dumps({'type': 'complete', 'sku': sku_name, 'session': session_name})}\n\n"
                break
            elif job["status"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': job['messages'][-1] if job['messages'] else 'Pipeline failed'})}\n\n"
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(event_stream(), media_type="text/event-stream")


class UrlAnalysisRequest(BaseModel):
    sku: str
    raw_url: str
    touchedup_url: str
    autoshadow_url: str
    brand: str = "Unknown"
    color: str = "Unknown"
    silhouette: str = "Unknown"


def _fix_url(url: str) -> str:
    """Ensure URL has https:// protocol prefix."""
    url = url.strip()
    if not url:
        return url
    if not url.startswith("http://") and not url.startswith("https://"):
        # If it looks like a CloudFront path, add protocol
        if url.startswith("dj5e08oeu5ym4") or url.startswith("//"):
            url = "https://" + url.lstrip("/")
        else:
            url = "https://" + url
    return url


@app.post("/api/analyze-urls")
async def start_analysis_urls(req: UrlAnalysisRequest):
    """Start QA analysis using direct CloudFront URLs."""
    sku = req.sku.strip().upper()
    if sku in jobs and jobs[sku].get("status") == "running":
        raise HTTPException(400, f"Analysis already running for {sku}")
    jobs[sku] = {"status": "running", "messages": [], "result": None, "session_dir": None}

    urls = {
        "raw": _fix_url(req.raw_url),
        "touchedup": _fix_url(req.touchedup_url),
        "autoshadow": _fix_url(req.autoshadow_url),
    }

    async def run():
        try:
            async def on_progress(msg):
                jobs[sku]["messages"].append(msg)
            report_path, session_dir = await run_qa_pipeline(config, sku, on_progress, urls=urls)
            jobs[sku]["status"] = "complete"
            jobs[sku]["result"] = report_path
            jobs[sku]["session_dir"] = session_dir
        except Exception as e:
            jobs[sku]["status"] = "error"
            jobs[sku]["messages"].append(f"Error: {str(e)}")

    asyncio.create_task(run())
    return {"job_id": sku, "status": "started"}


@app.get("/api/reports")
async def list_reports():
    return storage.list_reports()


@app.get("/api/reports/{sku}/{session}/report.html")
async def get_report(sku: str, session: str):
    report_path = os.path.join(config.reports_dir, sku, session, "report.html")
    if not os.path.exists(report_path):
        raise HTTPException(404, "Report not found")
    return FileResponse(report_path, media_type="text/html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.port)
