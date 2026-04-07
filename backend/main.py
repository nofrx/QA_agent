import asyncio
import os
import json
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

# Jobs keyed by unique job_id (not SKU) to avoid collisions
jobs: dict[str, dict] = {}
# Map SKU to latest job_id for SSE lookup
sku_to_job: dict[str, str] = {}
# Keep max 50 completed jobs in memory
MAX_JOBS = 50


@app.get("/")
async def index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.get("/reports")
async def reports_page():
    return FileResponse(os.path.join(frontend_dir, "reports.html"))


def _create_job(sku: str) -> str:
    """Create a new job and return its ID. Prunes old completed jobs."""
    # Prune old completed jobs to prevent memory leak
    completed = [k for k, v in jobs.items() if v["status"] in ("complete", "error")]
    if len(completed) > MAX_JOBS:
        for old_id in completed[:len(completed) - MAX_JOBS]:
            jobs.pop(old_id, None)

    job_id = f"{sku}_{uuid.uuid4().hex[:8]}"
    jobs[job_id] = {"status": "running", "messages": [], "result": None, "session_dir": None, "sku": sku}
    sku_to_job[sku] = job_id
    return job_id


@app.post("/api/analyze/{sku}")
async def start_analysis(sku: str):
    sku = sku.strip().upper()
    if not sku:
        raise HTTPException(400, "SKU is required")

    # Check if already running for this SKU
    existing = sku_to_job.get(sku)
    if existing and jobs.get(existing, {}).get("status") == "running":
        raise HTTPException(400, f"Analysis already running for {sku}")

    job_id = _create_job(sku)

    async def run():
        try:
            async def on_progress(msg):
                jobs[job_id]["messages"].append(msg)
            report_path, session_dir = await run_qa_pipeline(config, sku, on_progress)
            jobs[job_id]["status"] = "complete"
            jobs[job_id]["result"] = report_path
            jobs[job_id]["session_dir"] = session_dir
        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["messages"].append(f"Error: {str(e)}")

    task = asyncio.create_task(run())
    jobs[job_id]["_task"] = task  # prevent GC collection
    return {"job_id": job_id, "sku": sku, "status": "started"}


class UrlAnalysisRequest(BaseModel):
    sku: str
    raw_url: str
    source_url: str = ""
    optimised_url: str = ""
    autoshadow_url: str = ""
    brand: str = "Unknown"
    color: str = "Unknown"
    silhouette: str = "Unknown"


def _fix_url(url: str) -> str:
    """Ensure URL has https:// protocol and is a valid CloudFront/HTTP URL."""
    url = url.strip()
    if not url:
        return url
    if not url.startswith("http://") and not url.startswith("https://"):
        if url.startswith("dj5e08oeu5ym4") or url.startswith("//"):
            url = "https://" + url.lstrip("/")
        else:
            url = "https://" + url
    return url


@app.post("/api/analyze-urls")
async def start_analysis_urls(req: UrlAnalysisRequest):
    """Start QA analysis using direct CloudFront URLs."""
    sku = req.sku.strip().upper()
    if not sku:
        raise HTTPException(400, "SKU is required")

    existing = sku_to_job.get(sku)
    if existing and jobs.get(existing, {}).get("status") == "running":
        raise HTTPException(400, f"Analysis already running for {sku}")

    urls = {
        "raw": _fix_url(req.raw_url),
    }
    if req.source_url:
        urls["source"] = _fix_url(req.source_url)
    if req.optimised_url:
        urls["optimised"] = _fix_url(req.optimised_url)
    if req.autoshadow_url:
        urls["autoshadow"] = _fix_url(req.autoshadow_url)

    # Validate raw URL is present
    if not urls["raw"]:
        raise HTTPException(400, "Missing URL for raw scan")

    job_id = _create_job(sku)

    async def run():
        try:
            async def on_progress(msg):
                jobs[job_id]["messages"].append(msg)
            meta = {"brand": req.brand, "color": req.color, "silhouette": req.silhouette}
            report_path, session_dir = await run_qa_pipeline(config, sku, on_progress, urls=urls, metadata=meta)
            jobs[job_id]["status"] = "complete"
            jobs[job_id]["result"] = report_path
            jobs[job_id]["session_dir"] = session_dir
        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["messages"].append(f"Error: {str(e)}")

    task = asyncio.create_task(run())
    jobs[job_id]["_task"] = task
    return {"job_id": job_id, "sku": sku, "status": "started"}


@app.post("/api/analyze-files")
async def start_analysis_files(
    sku: str = Form(...),
    raw_file: UploadFile = File(...),
    source_file: UploadFile = File(None),
    optimised_file: UploadFile = File(None),
    autoshadow_file: UploadFile = File(None),
):
    """Start QA analysis using locally uploaded GLB files."""
    sku = sku.strip().upper()
    if not sku:
        raise HTTPException(400, "SKU is required")

    existing = sku_to_job.get(sku)
    if existing and jobs.get(existing, {}).get("status") == "running":
        raise HTTPException(400, f"Analysis already running for {sku}")

    job_id = _create_job(sku)

    # Save uploaded files to a temp session dir
    session_dir = storage.create_session(sku)
    file_paths = {}

    async def _save(upload: UploadFile, filename: str) -> str:
        path = os.path.join(session_dir, filename)
        content = await upload.read()
        with open(path, "wb") as f:
            f.write(content)
        return path

    file_paths["raw"] = await _save(raw_file, "raw_scan.glb")
    if source_file:
        file_paths["source"] = await _save(source_file, "source.glb")
    if optimised_file:
        file_paths["optimised"] = await _save(optimised_file, "optimised.glb")
    if autoshadow_file:
        file_paths["autoshadow"] = await _save(autoshadow_file, "autoshadow.glb")

    async def run():
        try:
            async def on_progress(msg):
                jobs[job_id]["messages"].append(msg)

            await on_progress(f"Using uploaded files for {sku}")
            for key in ["raw", "source", "optimised", "autoshadow"]:
                if key in file_paths:
                    size_mb = os.path.getsize(file_paths[key]) / 1024 / 1024
                    await on_progress(f"  {key}: {size_mb:.1f} MB")

            # Run pipeline with local_files instead of urls
            report_path, sess_dir = await run_qa_pipeline(
                config, sku, on_progress,
                local_files=file_paths,
                session_dir_override=session_dir,
            )
            jobs[job_id]["status"] = "complete"
            jobs[job_id]["result"] = report_path
            jobs[job_id]["session_dir"] = sess_dir
        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["messages"].append(f"Error: {str(e)}")

    task = asyncio.create_task(run())
    jobs[job_id]["_task"] = task
    return {"job_id": job_id, "sku": sku, "status": "started"}


@app.get("/api/status/{job_id}")
async def job_status(job_id: str):
    """SSE stream of progress for a job. Accepts job_id or SKU."""
    job_id = job_id.strip()
    if job_id not in jobs:
        # Try looking up by SKU (uppercase for SKU matching)
        mapped = sku_to_job.get(job_id.upper())
        if mapped:
            job_id = mapped

    async def event_stream():
        sent = 0
        while True:
            job = jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Job not found'})}\n\n"
                break
            while sent < len(job["messages"]):
                yield f"data: {json.dumps({'type': 'progress', 'message': job['messages'][sent]})}\n\n"
                sent += 1
            if job["status"] == "complete":
                session_dir = job.get("session_dir", "")
                sku_name = job.get("sku", "")
                session_name = os.path.basename(session_dir) if session_dir else ""
                yield f"data: {json.dumps({'type': 'complete', 'sku': sku_name, 'session': session_name})}\n\n"
                break
            elif job["status"] == "error":
                last_msg = job["messages"][-1] if job["messages"] else "Pipeline failed"
                yield f"data: {json.dumps({'type': 'error', 'message': last_msg})}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/reports")
async def list_reports():
    return storage.list_reports()


@app.get("/api/reports/{sku}/{session}/report.html")
async def get_report(sku: str, session: str):
    # Sanitize path components to prevent traversal
    sku = os.path.basename(sku)
    session = os.path.basename(session)
    report_path = os.path.join(config.reports_dir, sku, session, "report.html")
    if not os.path.exists(report_path):
        raise HTTPException(404, "Report not found")
    return FileResponse(report_path, media_type="text/html")


@app.get("/api/reports/{sku}/{session}/files/{filepath:path}")
async def get_session_file(sku: str, session: str, filepath: str):
    """Serve GLB, JSON, and PNG files from a session directory (including subdirs like textures/)."""
    sku = os.path.basename(sku)
    session = os.path.basename(session)
    # Sanitize each path component to prevent traversal
    parts = filepath.split("/")
    parts = [os.path.basename(p) for p in parts if p and p != ".."]
    if not parts:
        raise HTTPException(400, "Missing filename")
    # Only allow safe file types
    ext = os.path.splitext(parts[-1])[1].lower()
    allowed = {".glb": "model/gltf-binary", ".json": "application/json", ".png": "image/png"}
    if ext not in allowed:
        raise HTTPException(400, f"File type {ext} is not served")
    file_path = os.path.join(config.reports_dir, sku, session, *parts)
    if not os.path.exists(file_path):
        raise HTTPException(404, f"File not found: {filepath}")
    return FileResponse(file_path, media_type=allowed[ext])


@app.delete("/api/reports/{sku}/{session}")
async def delete_report(sku: str, session: str):
    """Delete a report session."""
    import shutil
    sku = os.path.basename(sku)
    session = os.path.basename(session)
    session_dir = os.path.join(config.reports_dir, sku, session)
    if not os.path.isdir(session_dir):
        raise HTTPException(404, "Session not found")
    shutil.rmtree(session_dir)
    # Clean up empty SKU directory
    sku_dir = os.path.join(config.reports_dir, sku)
    if os.path.isdir(sku_dir) and not os.listdir(sku_dir):
        os.rmdir(sku_dir)
    return {"status": "deleted", "sku": sku, "session": session}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.port)
