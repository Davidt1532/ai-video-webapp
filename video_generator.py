import os
import time
import requests
from config import (
    VIDEO_API_BASE_URL, VIDEO_MODEL,
    VIDEO_DURATION, ASPECT_RATIO, MAX_RETRIES,
    POLL_INTERVAL, MAX_POLL_TIME, CLIPS_DIR,
)
from key_pool import key_pool


class DailyQuotaExceeded(Exception):
    """Raised when every API key has used up its free daily generation quota."""


def ensure_dirs():
    os.makedirs(CLIPS_DIR, exist_ok=True)


def _detail(e) -> str:
    if e.response is None:
        return ""
    try:
        return (e.response.json() or {}).get("detail", "") or ""
    except Exception:
        return ""


def generate_video(prompt: str, scene_number: int, output_dir: str = None,
                   image_url: str = None) -> str:
    """Generate a video clip from a prompt via NovAI API. Returns path to downloaded MP4.

    NovAI uses async jobs: submit a job, poll until status is 'succeeded'.
    cogvideox-flash is billed at $0/generation.

    image_url (optional): a public URL used as the first frame. cogvideox-flash
    may ignore it, so on rejection we retry as text-only rather than failing.
    """
    clips_dir = os.path.join(output_dir, "clips") if output_dir else CLIPS_DIR
    os.makedirs(clips_dir, exist_ok=True)
    output_path = os.path.join(clips_dir, f"scene_{scene_number:02d}.mp4")

    if os.path.exists(output_path):
        print(f"  [skip] Clip already exists: {output_path}")
        return output_path

    def _headers(key: str) -> dict:
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    payload = {
        "model": VIDEO_MODEL,
        "prompt": prompt,
    }
    if image_url:
        payload["image_url"] = [image_url]

    # Submit job, rotating API keys when one hits its free daily quota.
    task_id = None
    task_key = None
    used_image = bool(image_url)

    key = key_pool.get_video_key()
    if key is None:
        raise DailyQuotaExceeded(key_pool.all_exhausted_message())

    attempt = 0
    while True:
        try:
            print(f"  [submit] Sending video generation request (key {key[:8]}...)...")
            if image_url:
                print(f"  [submit]   first-frame image: {image_url[:80]}")
            resp = requests.post(
                f"{VIDEO_API_BASE_URL}/video/generations",
                headers=_headers(key),
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            task_id = data.get("id") or data.get("task_id")
            if task_id:
                key_pool.mark_submitted(key)
                task_key = key
                print(f"  [submit] Task ID: {task_id} (key {key[:8]}...)")
                break
            else:
                print(f"  [warn] No task ID in response: {data}")
                key = key_pool.get_video_key()
                if key is None:
                    raise DailyQuotaExceeded(key_pool.all_exhausted_message())
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else 0
            if used_image and status_code in (400, 422):
                # Character image not supported by this model: retry text-only.
                print(f"  [warn] API rejected image input ({status_code}); retrying text-only")
                payload.pop("image_url", None)
                used_image = False
                continue
            if status_code == 429:
                detail = _detail(e)
                if "daily limit" in detail.lower():
                    # Free tier caps generations/day/key: retire this key for today.
                    key_pool.mark_exhausted(key)
                    key = key_pool.get_video_key()
                    if key is None:
                        raise DailyQuotaExceeded(key_pool.all_exhausted_message())
                    print(f"  [warn] Key reached daily limit; switching keys")
                    continue
            print(f"  [error] Request failed: {e}")
            attempt += 1
            if attempt >= MAX_RETRIES:
                print(f"  [error] Could not submit video job after {MAX_RETRIES} attempts")
                return ""
            if status_code == 429:
                wait = 60 * attempt
                print(f"  [wait] Rate limited. Waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                time.sleep(POLL_INTERVAL * 2)
        except requests.RequestException as e:
            print(f"  [error] Request failed: {e}")
            attempt += 1
            if attempt >= MAX_RETRIES:
                print(f"  [error] Could not submit video job after {MAX_RETRIES} attempts")
                return ""
            time.sleep(POLL_INTERVAL * 2)

    if not task_key:
        return ""

    # Poll for completion (try /video/generations/{id}, fall back to /video/tasks/{id})
    # NOTE: must poll with the same key that created the task.
    headers = _headers(task_key)
    start_time = time.time()
    poll_paths = [
        f"{VIDEO_API_BASE_URL}/video/generations/{task_id}",
        f"{VIDEO_API_BASE_URL}/video/tasks/{task_id}",
    ]
    poll_index = 0
    while True:
        elapsed = time.time() - start_time
        if elapsed > MAX_POLL_TIME:
            print(f"  [error] Timed out after {MAX_POLL_TIME}s waiting for clip")
            return ""

        try:
            resp = requests.get(
                poll_paths[poll_index],
                headers=headers,
                params={"model": VIDEO_MODEL},
                timeout=60,
            )
            if resp.status_code == 404 and poll_index == 0:
                # Poll path might differ per provider version; try the alternate one.
                print(f"  [warn] Poll endpoint 404, falling back to {poll_paths[1].split('/v1/')[-1]}")
                poll_index = 1
                continue
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"  [warn] Poll failed: {e}, retrying...")
            time.sleep(POLL_INTERVAL)
            continue

        status = (data.get("task_status") or data.get("status") or "").lower()

        if status in ("succeeded", "success", "completed", "done"):
            # NovAI format: video_result is a list of {url, cover_image_url, ...}
            video_result = data.get("video_result") or []
            video_url = None
            if isinstance(video_result, list) and video_result:
                video_url = video_result[0].get("url")
            if not video_url:
                video_url = data.get("video_url") or (data.get("content") or {}).get("video_url")

            if not video_url:
                print(f"  [error] Success but no video URL in response: {data}")
                return ""

            print(f"  [download] Downloading clip from {video_url[:80]}...")
            return download_video(video_url, output_path)

        elif status in ("failed", "error"):
            print(f"  [error] Generation failed: {data}")
            return ""

        else:
            print(f"  [poll] Status: {status} ({int(elapsed)}s elapsed)")
            time.sleep(POLL_INTERVAL)


def download_video(url: str, output_path: str) -> str:
    """Download video file from URL."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, stream=True, timeout=180)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            file_size = os.path.getsize(output_path)
            print(f"  [done] Saved: {output_path} ({file_size / 1024:.1f} KB)")
            return output_path
        except requests.RequestException as e:
            print(f"  [error] Download failed: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(5)

    print(f"  [error] Could not download after {MAX_RETRIES} attempts")
    return ""


def generate_all_clips(scenes: list, image_url: str = None) -> dict[int, str]:
    """Generate video clips for all scenes. Returns {scene_number: clip_path}."""
    clips = {}
    total = len(scenes)

    for idx, scene in enumerate(scenes):
        print(f"\n{'='*50}")
        print(f"Scene {scene.number}/{total}: {scene.title}")
        print(f"Prompt: {scene.video_prompt[:100]}...")
        print(f"{'='*50}")

        clip_path = generate_video(scene.video_prompt, scene.number, image_url=image_url)
        if clip_path:
            clips[scene.number] = clip_path
        else:
            print(f"  [warn] Skipping scene {scene.number} - no clip generated")

        # Pause between clips to avoid rate limits (free tier is sensitive)
        if clip_path and idx < total - 1:
            wait = 20
            print(f"  [wait] Cooling down {wait}s before next clip...")
            time.sleep(wait)

    return clips


if __name__ == "__main__":
    from scene_splitter import load_story
    scenes = load_story("story.txt")
    clips = generate_all_clips(scenes)
    print(f"\nGenerated {len(clips)}/{len(scenes)} clips")