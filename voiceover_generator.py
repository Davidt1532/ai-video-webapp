import os
import asyncio
import time
import edge_tts
from pydub import AudioSegment
from config import TTS_VOICE, TTS_RATE, TTS_VOLUME, AUDIO_DIR


def ensure_dirs():
    os.makedirs(AUDIO_DIR, exist_ok=True)


async def generate_audio(text: str, output_path: str, voice: str = None) -> bool:
    """Generate audio file from text using edge-tts."""
    v = voice or TTS_VOICE
    communicate = edge_tts.Communicate(text, v, rate=TTS_RATE, volume=TTS_VOLUME)
    await communicate.save(output_path)
    return os.path.exists(output_path)


def generate_voiceover(scene_number: int, text: str, output_dir: str = None, voice: str = None) -> tuple[str, float]:
    """Generate voiceover for a scene. Returns (audio_path, duration_seconds).

    Never raises: edge-tts is flaky from datacenter IPs, so we retry once and then
    return an empty result so the rest of the video can still be built.
    """
    audio_dir = os.path.join(output_dir, "audio") if output_dir else AUDIO_DIR
    os.makedirs(audio_dir, exist_ok=True)
    output_path = os.path.join(audio_dir, f"scene_{scene_number:02d}.mp3")

    if os.path.exists(output_path):
        duration = get_audio_duration(output_path)
        print(f"  [skip] Audio already exists: {output_path} ({duration:.1f}s)")
        return output_path, duration

    if not (text or "").strip():
        print(f"  [error] Skipping voiceover for scene {scene_number}: empty text")
        return "", 0.0

    for attempt in range(2):
        print(f"  [tts] Generating voiceover for scene {scene_number} (attempt {attempt + 1})...")
        try:
            success = asyncio.run(generate_audio(text, output_path, voice))
            if success:
                duration = get_audio_duration(output_path)
                if duration > 0:
                    print(f"  [done] Saved: {output_path} ({duration:.1f}s)")
                    return output_path, duration
                print(f"  [error] Audio file empty for scene {scene_number}; retrying...")
        except Exception as e:
            print(f"  [error] TTS failed for scene {scene_number}: {e}")
            if attempt == 0:
                time.sleep(2)
    print(f"  [error] Giving up voiceover for scene {scene_number} after retries")
    return "", 0.0


def get_audio_duration(audio_path: str) -> float:
    """Get duration of audio file in seconds."""
    try:
        audio = AudioSegment.from_file(audio_path)
        return len(audio) / 1000.0
    except Exception:
        return 0.0


def generate_all_voiceovers(scenes: list) -> dict[int, tuple[str, float]]:
    """Generate voiceovers for all scenes. Returns {scene_number: (audio_path, duration)}."""
    voiceovers = {}
    total = len(scenes)

    for scene in scenes:
        print(f"\nVoiceover for scene {scene.number}/{total}: {scene.title}")
        audio_path, duration = generate_voiceover(scene.number, scene.narration)
        if audio_path:
            voiceovers[scene.number] = (audio_path, duration)

    return voiceovers


if __name__ == "__main__":
    from scene_splitter import load_story
    scenes = load_story("story.txt")
    voiceovers = generate_all_voiceovers(scenes)
    for num, (path, dur) in voiceovers.items():
        print(f"Scene {num}: {path} ({dur:.1f}s)")
