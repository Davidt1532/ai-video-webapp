import re
from dataclasses import dataclass


@dataclass
class Scene:
    number: int
    title: str
    narration: str
    video_prompt: str


def parse_story(story_text: str) -> list[Scene]:
    """Parse story text into scenes. Expects 'Scene N: Title' markers."""
    scene_pattern = re.compile(r"Scene\s+(\d+):\s*(.+)", re.IGNORECASE)
    raw_scenes = scene_pattern.split(story_text.strip())

    scenes = []
    i = 0
    while i < len(raw_scenes) - 2:
        number = int(raw_scenes[i + 1])
        title = raw_scenes[i + 2].strip()
        body = raw_scenes[i + 3].strip() if i + 3 < len(raw_scenes) else ""
        if i + 3 < len(raw_scenes):
            # Next scene marker or end of text
            next_text = raw_scenes[i + 3]
            parts = next_text.strip().split("\n\n", 1)
            narration = parts[0].strip()
            video_prompt = narration_to_video_prompt(title, narration)
            scenes.append(Scene(number=number, title=title, narration=narration, video_prompt=video_prompt))
        i += 3

    # Handle last scene if pattern left remainder
    if i < len(raw_scenes):
        remaining = raw_scenes[i].strip()
        if remaining:
            # Try to extract last scene
            match = scene_pattern.search(remaining)
            if not match:
                # This is narration body for last scene
                pass

    return scenes


def narration_to_video_prompt(title: str, narration: str) -> str:
    """Convert narration text into a cinematic video generation prompt."""
    # Take first sentence and make it cinematic
    sentences = [s.strip() for s in re.split(r"[.!?]", narration) if s.strip()]
    if sentences:
        base = sentences[0]
    else:
        base = narration

    prompt = f"{base}. Cinematic lighting, dramatic atmosphere, movie scene, high quality."
    return prompt


def parse_simple_scenes(story_text: str) -> list[Scene]:
    """Alternative parser: split by double newlines or '---' separators."""
    scenes = []

    # Try splitting by ---
    if "---" in story_text:
        blocks = [b.strip() for b in story_text.split("---") if b.strip()]
    else:
        blocks = [b.strip() for b in story_text.split("\n\n") if b.strip()]

    for i, block in enumerate(blocks, 1):
        lines = block.split("\n", 1)
        title_line = lines[0].strip()
        narration = lines[1].strip() if len(lines) > 1 else block

        # Clean title
        title = re.sub(r"^Scene\s+\d+[:\s]*", "", title_line, flags=re.IGNORECASE).strip()
        if not title:
            title = f"Scene {i}"

        video_prompt = narration_to_video_prompt(title, narration)
        scenes.append(Scene(number=i, title=title, narration=narration, video_prompt=video_prompt))

    return scenes


def load_story(filepath: str) -> list[Scene]:
    """Load story from file and parse into scenes."""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    return load_story_text(text)


def load_story_text(text: str) -> list[Scene]:
    """Parse story text into scenes (no file needed)."""
    scenes = parse_story(text)
    if not scenes:
        scenes = parse_simple_scenes(text)
    return scenes


if __name__ == "__main__":
    scenes = load_story("story.txt")
    for s in scenes:
        print(f"\n{'='*60}")
        print(f"Scene {s.number}: {s.title}")
        print(f"Video Prompt: {s.video_prompt}")
        print(f"Narration: {s.narration[:100]}...")
