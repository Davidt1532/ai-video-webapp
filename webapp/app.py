import os
import asyncio
import uuid
import mimetypes
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from job_manager import JobManager
from config import CURATED_VOICES, TTS_VOICE

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = os.getenv("DATA_DIR", str(BASE_DIR / "data"))
REFS_DIR = os.path.join(DATA_DIR, "refs")
os.makedirs(REFS_DIR, exist_ok=True)

app = FastAPI(title="AI Story Video Generator")
manager = JobManager(data_dir=DATA_DIR)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/history")
async def history_page():
    return FileResponse(str(STATIC_DIR / "history.html"))


@app.get("/api/voices")
async def list_voices():
    """Return only the curated human-tune voices (Auto + 5)."""
    voices = [{"name": "", "label": "Auto — smart voice (recommended)", "auto": True}]
    voices += [
        {"name": v["name"], "label": v["label"], "auto": False}
        for v in CURATED_VOICES
    ]
    return {"voices": voices, "default": TTS_VOICE}


@app.post("/api/refs")
async def upload_ref(request: Request):
    """Upload a character reference image. Returns a ref token used in jobs."""
    try:
        form = await request.form()
        file: UploadFile = form.get("file")
        if not file:
            raise HTTPException(400, "No file provided")
        data = await file.read()
        if not data:
            raise HTTPException(400, "Empty file")
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(400, "Image too large (max 10 MB)")

        ext = Path(file.filename or "ref.png").suffix.lower() or ".png"
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            raise HTTPException(400, "Only PNG/JPG/WebP images are supported")

        ref = uuid.uuid4().hex[:12]
        path = os.path.join(REFS_DIR, f"{ref}{ext}")
        with open(path, "wb") as f:
            f.write(data)
        return {"ref": f"{ref}{ext}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Upload failed: {e}")


@app.get("/api/refs/{ref}")
async def get_ref(ref: str):
    safe = os.path.basename(ref)
    path = os.path.join(REFS_DIR, safe)
    if not os.path.exists(path):
        raise HTTPException(404, "Ref not found")
    media = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media)


@app.get("/api/jobs")
async def list_jobs(limit: int = 50):
    return manager.list_jobs(limit)


@app.post("/api/jobs")
async def create_job(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    mode = body.get("mode", "clip")
    if mode not in ("clip", "story"):
        raise HTTPException(400, "mode must be 'clip' or 'story'")

    prompt = body.get("prompt", "").strip()
    story_text = body.get("story_text", "").strip()
    if mode == "story" and not story_text:
        story_text = prompt
    if not prompt and not story_text:
        raise HTTPException(400, "No prompt or story provided")

    duration = int(body.get("duration", 4))
    duration = max(2, min(6, duration))
    aspect_ratio = body.get("aspect_ratio", "16:9")
    voice = body.get("voice", "").strip()
    ref_image = body.get("ref_image", "").strip()
    voice_instructions = body.get("voice_instructions", "").strip()
    smart_voiceover = bool(body.get("smart_voiceover", True))

    job = manager.create_job(
        mode=mode, prompt=prompt, story_text=story_text,
        voice=voice, duration=duration, aspect_ratio=aspect_ratio,
        ref_image=ref_image, voice_instructions=voice_instructions,
        smart_voiceover=smart_voiceover,
    )
    return job


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/api/jobs/{job_id}/rerun")
async def rerun_job(job_id: str):
    job = manager.rerun_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    ok = manager.delete_job(job_id)
    if not ok:
        raise HTTPException(404, "Job not found")
    return {"ok": True}


@app.get("/api/jobs/{job_id}/video")
async def get_video(job_id: str):
    job = manager.get_job(job_id)
    if not job or not job.get("video_path"):
        raise HTTPException(404, "Video not found")
    path = job["video_path"]
    if not os.path.exists(path):
        raise HTTPException(404, "Video file missing")
    return FileResponse(path, media_type="video/mp4", filename=f"story_{job_id}.mp4")


@app.get("/api/jobs/{job_id}/clip/{filename}")
async def get_clip(job_id: str, filename: str):
    job_dir = os.path.join(manager.jobs_dir, job_id, "clips")
    safe = os.path.basename(filename)
    path = os.path.join(job_dir, safe)
    if not os.path.exists(path):
        raise HTTPException(404, "Clip not found")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/health")
async def health():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))