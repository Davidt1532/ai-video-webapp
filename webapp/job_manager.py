import os
import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone

sys_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

from scene_splitter import load_story_text
from video_generator import generate_video
from voiceover_generator import generate_voiceover
from video_combiner import build_final_video

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


class JobManager:
    """SQLite-backed job queue with a single background worker.
    One job runs at a time (free-tier hosts are RAM constrained).
    """

    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.jobs_dir = os.path.join(self.data_dir, "jobs")
        os.makedirs(self.jobs_dir, exist_ok=True)
        self.db_path = os.path.join(self.data_dir, "jobs.db")
        self._lock = threading.Lock()
        self._queue = []
        self._worker = None
        self._init_db()
        self._start_worker()

    # ---------- DB ----------
    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    prompt TEXT,
                    story_text TEXT,
                    voice TEXT,
                    duration INTEGER,
                    aspect_ratio TEXT,
                    status TEXT DEFAULT 'queued',
                    scenes_total INTEGER DEFAULT 0,
                    scenes_done INTEGER DEFAULT 0,
                    current_scene TEXT,
                    scenes_detail TEXT DEFAULT '[]',
                    error TEXT,
                    video_path TEXT,
                    cover_path TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ---------- Public API ----------
    def create_job(self, mode: str, prompt: str = "", story_text: str = "",
                   voice: str = "", duration: int = 4, aspect_ratio: str = "16:9") -> dict:
        job_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        job_dir = os.path.join(self.jobs_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)

        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO jobs
                   (id, mode, prompt, story_text, voice, duration, aspect_ratio,
                    status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (job_id, mode, prompt, story_text, voice, duration, aspect_ratio,
                 "queued", now, now),
            )

        with self._lock:
            self._queue.append(job_id)
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        job = dict(row)
        job["scenes_detail"] = json.loads(job.get("scenes_detail") or "[]")
        job["video_url"] = f"/api/jobs/{job_id}/video" if job.get("status") == "completed" and job.get("video_path") else None
        child_urls = []
        if os.path.isdir(os.path.join(self.jobs_dir, job_id, "clips")):
            for name in sorted(os.listdir(os.path.join(self.jobs_dir, job_id, "clips"))):
                if name.lower().endswith(".mp4"):
                    child_urls.append(f"/api/jobs/{job_id}/clip/{name}")
        job["clip_urls"] = child_urls
        return job

    def list_jobs(self, limit: int = 50) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        jobs = []
        for row in rows:
            job = dict(row)
            job["scenes_detail"] = json.loads(job.get("scenes_detail") or "[]")
            job["video_url"] = f"/api/jobs/{job['id']}/video" if job.get("status") == "completed" and job.get("video_path") else None
            jobs.append(job)
        return jobs

    def delete_job(self, job_id: str) -> bool:
        job_dir = os.path.join(self.jobs_dir, job_id)
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        if os.path.isdir(job_dir):
            import shutil
            shutil.rmtree(job_dir, ignore_errors=True)
        return cur.rowcount > 0

    def rerun_job(self, job_id: str) -> dict:
        job = self.get_job(job_id)
        if not job:
            return None
        # wipe old outputs
        job_dir = os.path.join(self.jobs_dir, job_id)
        import shutil
        if os.path.isdir(job_dir):
            shutil.rmtree(job_dir, ignore_errors=True)
        os.makedirs(job_dir, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            conn.execute(
                """UPDATE jobs SET status='queued', scenes_total=0, scenes_done=0,
                   current_scene=NULL, scenes_detail='[]', error=NULL,
                   video_path=NULL, cover_path=NULL, updated_at=? WHERE id=?""",
                (now, job_id),
            )
        with self._lock:
            if job_id not in self._queue:
                self._queue.append(job_id)
        return self.get_job(job_id)

    # ---------- Worker ----------
    def _start_worker(self):
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def _worker_loop(self):
        while True:
            job_id = None
            with self._lock:
                if self._queue:
                    job_id = self._queue.pop(0)
            if job_id:
                try:
                    self._process_job(job_id)
                except Exception as e:
                    self._set_error(job_id, str(e))
            else:
                time.sleep(2)

    def _process_job(self, job_id: str):
        job = self.get_job(job_id)
        if not job:
            return

        mode = job["mode"]
        job_dir = os.path.join(self.jobs_dir, job_id)
        self._update(job_id, status="running", updated=True)

        scenes_detail = []
        if mode == "clip":
            prompt = job["prompt"] or "An empty scene, cinematic."
            self._update(job_id, scenes_total=1, current_scene="Generating clip")
            clip = generate_video(prompt, 1, output_dir=job_dir)
            if not clip:
                raise RuntimeError("Video generation failed - check API key or retry later (rate limits).")
            # Optional: nothing to stitch for a single clip
            final = os.path.join(job_dir, "final_video.mp4")
            os.replace(clip, final)
            scenes_detail = [{"number": 1, "title": "Clip", "status": "done"}]
            self._update(job_id, scenes_done=1, current_scene="Done",
                         scenes_detail=scenes_detail, video_path=final, status="completed", updated=True)
        else:
            story_text = job["story_text"] or job["prompt"]
            scenes = load_story_text(story_text)
            if not scenes:
                raise RuntimeError("No scenes found. Use 'Scene N: Title' format or '---' separators.")

            total = len(scenes)
            clips = {}
            voiceovers = {}
            video_path = None

            for i, scene in enumerate(scenes):
                scenes_detail = [
                    {"number": s.number, "title": s.title,
                     "status": "done" if s.number < scene.number
                               else ("processing" if s.number == scene.number else "pending")}
                    for s in scenes
                ]
                self._update(job_id, scenes_total=total, scenes_done=max(0, i),
                             current_scene=f"Scene {scene.number}: {scene.title}",
                             scenes_detail=scenes_detail, updated=True)

                clip = generate_video(scene.video_prompt, scene.number, output_dir=job_dir)
                if clip:
                    clips[scene.number] = clip
                audio, dur = generate_voiceover(scene.number, scene.narration, output_dir=job_dir, voice=job["voice"] or None)
                if audio:
                    voiceovers[scene.number] = (audio, dur)

                self._update(job_id, scenes_done=i + 1, updated=True)

            if not clips:
                raise RuntimeError("No video clips were generated. Rate-limited or API error.")

            video_path = build_final_video(clips, voiceovers, scenes, output_dir=job_dir)
            if not video_path:
                raise RuntimeError("Failed to stitch final video (FFmpeg error).")

            scenes_detail = [
                {"number": s.number, "title": s.title, "status": "done"} for s in scenes
            ]
            self._update(job_id, scenes_total=total, scenes_done=total,
                         current_scene="Done", scenes_detail=scenes_detail,
                         video_path=video_path, status="completed", updated=True)

    def _set_error(self, job_id: str, error: str):
        self._update(job_id, status="failed", error=error, updated=True)

    def _update(self, job_id: str, **fields):
        fields = {k: v for k, v in fields.items() if v is not None}
        if fields.get("updated"):
            del fields["updated"]
        if not fields:
            return
        now = datetime.now(timezone.utc).isoformat()
        # serialize list/dict fields for SQLite (JSON columns)
        for k, v in fields.items():
            if isinstance(v, (list, dict)):
                fields[k] = json.dumps(v)
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values())
        values.append(now)
        with self._get_conn() as conn:
            conn.execute(f"UPDATE jobs SET {set_clause}, updated_at=? WHERE id=?", values + [job_id])


if __name__ == "__main__":
    m = JobManager()
    job = m.create_job(mode="clip", prompt="A cat playing piano at sunset, cinematic.")
    print("Created:", job["id"])
    for _ in range(60):
        time.sleep(10)
        j = m.get_job(job["id"])
        print(f"  {j['status']}: {j.get('current_scene')}")
        if j["status"] in ("completed", "failed"):
            print("Final:", j["video_path"] or j["error"])
            break