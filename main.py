"""
ReelerCoaster - Main Application Entrypoint
FastAPI Web Studio + Background Job Processing Pipeline
"""

import os
import sys
import uuid
import json
import threading
from typing import Dict, Any, Optional
from pathlib import Path

import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from config import BASE_DIR, STORAGE_DIR, UPLOAD_DIR, PROCESSED_DIR, TEMP_DIR, FFMPEG_BIN
from core.pipeline import ReelerPipeline
from core.downloader import save_uploaded_file

app = FastAPI(title="ReelerCoaster Studio", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static and storage dirs
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

# In-memory Job Tracker
JOBS: Dict[str, Dict[str, Any]] = {}


def run_pipeline_task(job_id: str, params: Dict[str, Any]):
    """Background worker for job processing."""
    try:
        pipeline = ReelerPipeline(job_id=job_id)

        def on_progress(pct: int, msg: str):
            if job_id in JOBS:
                JOBS[job_id]["progress"] = pct
                JOBS[job_id]["message"] = msg

        result = pipeline.process(
            source_type=params["source_type"],
            source_val=params["source_val"],
            mode=params.get("mode", "irl"),
            webcam_pos=params.get("webcam_position", "none"),
            custom_webcam_box=params.get("custom_webcam_box"),
            split_strategy=params.get("split_strategy", "highlights"),
            target_part_duration=params.get("target_part_duration", 60.0),
            enable_subtitles=params.get("enable_subtitles", True),
            subtitle_style=params.get("subtitle_style", "beast"),
            target_clips=params.get("target_clips", 3),
            min_clip_duration=params.get("min_clip_duration", 20.0),
            max_clip_duration=params.get("clip_duration", 45.0),
            whisper_model=params.get("whisper_model", "base"),
            language=params.get("language", None),
            cleanup_source=params.get("cleanup_source", True),
            progress_cb=on_progress
        )

        JOBS[job_id]["status"] = "completed"
        JOBS[job_id]["progress"] = 100
        JOBS[job_id]["message"] = "Готово!"
        JOBS[job_id]["result"] = result

    except Exception as e:
        import traceback
        traceback.print_exc()
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)
        JOBS[job_id]["message"] = f"Ошибка: {e}"


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = BASE_DIR / "web" / "templates" / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


@app.get("/api/system")
async def system_info():
    import torch
    return {
        "gpu_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
        "ffmpeg_bin": FFMPEG_BIN
    }


@app.post("/api/video/preview-frame")
async def get_preview_frame(
    url: Optional[str] = Form(None)
):
    """Fetch video thumbnail for URL."""
    if not url:
        raise HTTPException(status_code=400, detail="URL не указан")
    
    import yt_dlp
    try:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            thumb = info.get("thumbnail")
            return {"thumbnail_url": thumb}
    except Exception as e:
        print(f"[Preview] Error: {e}")
        return {"thumbnail_url": None}


@app.post("/api/jobs/create")
async def create_job(
    background_tasks: BackgroundTasks,
    source_type: str = Form(...),
    url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    mode: str = Form("irl"),
    webcam_position: str = Form("none"),
    webcam_box: Optional[str] = Form(None),
    split_strategy: str = Form("highlights"),
    target_part_duration: float = Form(60.0),
    enable_subtitles: bool = Form(True),
    subtitle_style: str = Form("beast"),
    whisper_model: str = Form("base"),
    target_clips: int = Form(3),
    clip_duration: float = Form(45.0),
    cleanup_source: bool = Form(True)
):
    job_id = str(uuid.uuid4())[:8]

    if source_type == "url":
        if not url:
            raise HTTPException(status_code=400, detail="Не указана ссылка на видео.")
        source_val = url.strip()
    elif source_type == "file":
        if not file:
            raise HTTPException(status_code=400, detail="Файл видео не загружен.")
        # Save file to uploads
        saved = save_uploaded_file(file.file, file.filename or "upload.mp4")
        source_val = saved["path"]
    else:
        raise HTTPException(status_code=400, detail="Неверный тип источника.")

    # Parse custom webcam coordinates if provided
    custom_box_dict = None
    if webcam_box:
        try:
            custom_box_dict = json.loads(webcam_box)
            # If coordinates are given, set webcam_position to custom
            webcam_position = "custom"
        except Exception as e:
            print(f"[Main] Error parsing webcam_box: {e}")

    # Register job
    JOBS[job_id] = {
        "id": job_id,
        "status": "processing",
        "progress": 5,
        "message": "Задача добавлена в очередь...",
        "result": None,
        "error": None
    }

    params = {
        "source_type": source_type,
        "source_val": source_val,
        "mode": mode,
        "webcam_position": webcam_position,
        "custom_webcam_box": custom_box_dict,
        "split_strategy": split_strategy,
        "target_part_duration": target_part_duration,
        "enable_subtitles": enable_subtitles,
        "subtitle_style": subtitle_style,
        "whisper_model": whisper_model,
        "target_clips": target_clips,
        "clip_duration": clip_duration,
        "cleanup_source": cleanup_source
    }

    # Run in background thread
    t = threading.Thread(target=run_pipeline_task, args=(job_id, params), daemon=True)
    t.start()

    return {"job_id": job_id, "status": "processing"}


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return JOBS[job_id]


def start_server(port: int = 8000):
    print("=" * 60)
    print("🎢  ReelerCoaster Web Studio запущен!")
    print(f"👉  Откройте в браузере: http://localhost:{port}")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ReelerCoaster Studio")
    parser.add_argument("--port", type=int, default=8000, help="Web UI port (default: 8000)")
    args = parser.parse_args()
    start_server(port=args.port)
