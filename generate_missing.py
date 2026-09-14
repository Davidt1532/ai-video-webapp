import os
import time
from scene_splitter import load_story
from video_generator import generate_video

scenes = load_story("story.txt")
clips_dir = "output/clips"

for scene in scenes:
    clip = os.path.join(clips_dir, f"scene_{scene.number:02d}.mp4")
    if os.path.exists(clip):
        print(f"Scene {scene.number}: already exists - skip")
        continue

    print(f"\nGenerating scene {scene.number}: {scene.title}")
    path = generate_video(scene.video_prompt, scene.number)
    if path:
        print(f"Scene {scene.number}: OK")
    else:
        print(f"Scene {scene.number}: FAILED")
        print("Waiting 120s before next attempt...")
        time.sleep(120)

    time.sleep(15)