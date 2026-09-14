import os
import subprocess
from pydub import AudioSegment
from config import CLIPS_DIR, AUDIO_DIR, FINAL_OUTPUT, CROSSFADE_DURATION


def get_video_duration(video_path: str) -> float:
    """Get duration of video file in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def loop_video_to_duration(video_path: str, target_duration: float, output_path: str) -> str:
    """Loop/pad a video clip to match a target duration."""
    current_duration = get_video_duration(video_path)
    if current_duration <= 0:
        return video_path

    if current_duration >= target_duration:
        # Trim to target duration
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-t", str(target_duration),
            "-c:v", "libx264", "-an",
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            output_path
        ]
    else:
        # Loop video to fill duration
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", video_path,
            "-t", str(target_duration),
            "-c:v", "libx264", "-an",
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            output_path
        ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"  [error] FFmpeg loop failed: {e}")
        return video_path


def overlay_audio(video_path: str, audio_path: str, output_path: str) -> str:
    """Overlay audio onto a video clip."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"  [error] FFmpeg overlay failed: {e}")
        return video_path


def prepare_scene(scene_number: int, clip_path: str, audio_path: str, duration: float, output_dir: str = None) -> str:
    """Prepare a scene: loop video to audio length, overlay audio. Returns path to prepared clip."""
    clipped_parent = os.path.dirname(clip_path)
    prepared_dir = os.path.join(clipped_parent, "prepared")
    os.makedirs(prepared_dir, exist_ok=True)

    looped_path = os.path.join(prepared_dir, f"scene_{scene_number:02d}_looped.mp4")
    final_path = os.path.join(prepared_dir, f"scene_{scene_number:02d}_final.mp4")

    # Step 1: Loop video to match audio duration
    print(f"  [loop] Extending video to {duration:.1f}s...")
    loop_video_to_duration(clip_path, duration, looped_path)

    # Step 2: Overlay audio
    print(f"  [overlay] Adding voiceover...")
    result = overlay_audio(looped_path, audio_path, final_path)

    return result


def concatenate_scenes(prepared_clips: list[str], output_path: str) -> bool:
    """Concatenate all prepared scenes into final video using FFmpeg concat demuxer."""
    # Create concat list file with ABSOLUTE paths
    # (ffmpeg resolves relative paths relative to the list file's directory)
    list_path = os.path.join(os.path.dirname(output_path), "concat_list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for clip in prepared_clips:
            abs_path = os.path.abspath(clip)
            safe_path = abs_path.replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_path,
        "-c:v", "libx264", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path
    ]

    try:
        print(f"  [concat] Stitching {len(prepared_clips)} scenes into final video...")
        result = subprocess.run(cmd, capture_output=True, timeout=600, check=True)
        file_size = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  [done] Final video: {output_path} ({file_size:.1f} MB)")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [error] Concatenation failed: {e.stderr.decode()[:200] if e.stderr else ''}")
        return False


def build_final_video(clips: dict[int, str], voiceovers: dict[int, tuple[str, float]], scenes: list, output_dir: str = None) -> str:
    """Main pipeline: prepare each scene and combine into final video."""
    if output_dir:
        final_output = os.path.join(output_dir, "final_video.mp4")
    else:
        final_output = FINAL_OUTPUT
    os.makedirs(os.path.dirname(final_output), exist_ok=True)
    prepared_clips = []

    for scene in scenes:
        num = scene.number
        if num not in clips or num not in voiceovers:
            print(f"  [skip] Scene {num} missing clip or audio")
            continue

        clip_path = clips[num]
        audio_path, duration = voiceovers[num]

        if duration <= 0:
            print(f"  [skip] Scene {num} has no audio duration")
            continue

        print(f"\nPreparing scene {num}: {scene.title}")
        prepared = prepare_scene(num, clip_path, audio_path, duration, output_dir)
        if prepared:
            prepared_clips.append(prepared)

    if not prepared_clips:
        print("\n[error] No scenes were prepared. Cannot create final video.")
        return ""

    print(f"\n{'='*50}")
    print(f"Combining {len(prepared_clips)} scenes...")
    print(f"{'='*50}")

    if concatenate_scenes(prepared_clips, final_output):
        return final_output
    return ""


if __name__ == "__main__":
    print("video_combiner.py - Run via main.py")
