import sys
import os
import time
import subprocess

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import VIDEO_API_KEY, FINAL_OUTPUT
from scene_splitter import load_story
from video_generator import generate_all_clips
from voiceover_generator import generate_all_voiceovers
from video_combiner import build_final_video


def check_ffmpeg():
    """Check if FFmpeg is installed."""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=10)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_api_key():
    """Check if API key is configured."""
    if VIDEO_API_KEY == "YOUR_NOVAI_KEY_HERE" or not VIDEO_API_KEY:
        return False
    return True


def print_header():
    print("""
╔══════════════════════════════════════════════════╗
║          AI Story Video Generator                ║
║    Free.ai + edge-tts + FFmpeg                   ║
╚══════════════════════════════════════════════════╝
    """)


def print_scenes(scenes):
    print("\n📖 Parsed Story Scenes:")
    print("─" * 50)
    for s in scenes:
        print(f"  Scene {s.number}: {s.title}")
        print(f"  Prompt: {s.video_prompt[:80]}...")
        print(f"  Narration: {s.narration[:80]}...")
        print()
    print("─" * 50)


def main():
    print_header()

    # Pre-flight checks
    if not check_ffmpeg():
        print("❌ FFmpeg not found! Install it first:")
        print("   winget install ffmpeg")
        print("   or download from https://ffmpeg.org/download.html")
        sys.exit(1)

    if not check_api_key():
        print("❌ NovAI API key not configured!")
        print("   1. Get free key (no card) at: https://aiapi-pro.com")
        print("   2. Set it in config.py or as env var VIDEO_API_KEY")
        sys.exit(1)

    # Get story file path
    story_file = sys.argv[1] if len(sys.argv) > 1 else "story.txt"
    if not os.path.exists(story_file):
        print(f"❌ Story file not found: {story_file}")
        print("   Create a story.txt or pass a file path as argument")
        sys.exit(1)

    # Step 1: Parse story
    print(f"📖 Loading story from: {story_file}")
    scenes = load_story(story_file)
    if not scenes:
        print("❌ No scenes found in story file!")
        print("   Use 'Scene N: Title' format or separate scenes with '---'")
        sys.exit(1)

    print_scenes(scenes)
    print(f"✅ Found {len(scenes)} scenes")

    # Step 2: Generate video clips
    print(f"\n{'='*50}")
    print(f"🎬 Step 2: Generating {len(scenes)} video clips via Free.ai")
    print(f"{'='*50}")
    clips = generate_all_clips(scenes)
    print(f"\n✅ Generated {len(clips)}/{len(scenes)} video clips")

    if not clips:
        print("❌ No clips generated. Check your API key and Free.ai status.")
        sys.exit(1)

    # Step 3: Generate voiceovers
    print(f"\n{'='*50}")
    print(f"🎙️ Step 3: Generating voiceovers with edge-tts")
    print(f"{'='*50}")
    voiceovers = generate_all_voiceovers(scenes)
    print(f"\n✅ Generated {len(voiceovers)}/{len(scenes)} voiceovers")

    if not voiceovers:
        print("❌ No voiceovers generated.")
        sys.exit(1)

    # Step 4: Combine into final video
    print(f"\n{'='*50}")
    print(f"🎥 Step 4: Combining into final video")
    print(f"{'='*50}")
    result = build_final_video(clips, voiceovers, scenes)

    if result:
        print(f"\n{'='*50}")
        print(f"🎉 DONE! Your video is ready:")
        print(f"   {os.path.abspath(result)}")
        file_size = os.path.getsize(result) / (1024 * 1024)
        print(f"   Size: {file_size:.1f} MB")
        print(f"{'='*50}")
    else:
        print("\n❌ Failed to create final video.")
        sys.exit(1)


if __name__ == "__main__":
    main()
