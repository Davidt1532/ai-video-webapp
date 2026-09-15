"""Smart voiceover engine.

Uses NovAI's free GLM chat model (glm-4.6v-flash, $0) to:
  - rewrite raw scene narration into a professional, natural voiceover script
    following the user's instructions
  - pick the best matching voice from the curated set based on scene mood

Every call fails soft: if the LLM is unavailable or times out we fall back to
the original text / default voice so video generation always continues.
"""
import re
import requests

from config import (
    VIDEO_API_KEY, VIDEO_API_BASE_URL, NARRATION_MODEL,
    NARRATION_TIMEOUT, NARRATION_MAX_TEXT, TTS_VOICE, CURATED_VOICES,
)


def _chat(messages: list[dict], max_tokens: int = 300) -> str:
    """Call the free NovAI chat model. Returns response text or "" on failure."""
    if not VIDEO_API_KEY:
        return ""
    try:
        resp = requests.post(
            f"{VIDEO_API_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {VIDEO_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": NARRATION_MODEL,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": max_tokens,
            },
            timeout=NARRATION_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        print(f"  [narration] LLM call failed: {e}")
        return ""


def enhance_narration(narration: str, instructions: str = "", scene_title: str = "") -> str:
    """Rewrite a scene's narration into a professional voiceover script."""
    text = (narration or "").strip()
    if not text:
        return text

    instructions = (instructions or "").strip()
    if instructions:
        instruction_line = f"Follow these creator instructions and weave them in naturally:\n{instructions}"
    else:
        instruction_line = "Keep the tone warm, vivid and storybook-like."

    prompt = f"""You are a professional voiceover scriptwriter for animated short films.

{instruction_line}

Scene title: {scene_title or 'Untitled scene'}
Original scene text:
\"\"\"
{text[:NARRATION_MAX_TEXT]}
\"\"\"

Write the final narration script for this scene ONLY (no quotes, no scene label).
Rules:
- Sound natural when read aloud (speakable, rhythmic, easy to narrate).
- Keep the original meaning and no more than 2-4 sentences.
- Do not describe camera directions or add [sound effects]."""

    result = _chat([{"role": "user", "content": prompt}], max_tokens=400)
    if not result:
        return text
    # Strip wrapping quotes if the model returned any.
    cleaned = re.sub(r'^["\']+|["\']+$', "", result).strip()
    return cleaned if cleaned else text


def pick_voice(text: str, instructions: str = "", scene_title: str = "") -> str:
    """Auto-select the best curated voice for a scene. Returns empty string if
    the caller should keep the current/default voice."""
    voice_names = [v["name"] for v in CURATED_VOICES]
    voice_list = "; ".join(voice_names)

    instructions = (instructions or "").strip()
    instruction_line = f"Creator instructions to respect:\n{instructions}" if instructions else ""

    prompt = f"""You cast narrators for AI short films. Pick the ONE most fitting voice for the scene.

Available voices: {voice_list}
Default (use only if unsure): {TTS_VOICE}

{instruction_line}

Scene: {scene_title or 'Untitled'}
Scene narration:
\"\"\"
{(text or '').strip()[:NARRATION_MAX_TEXT]}
\"\"\"

Answer with exactly one voice name from the list above. No extra text."""

    result = _chat([{"role": "user", "content": prompt}], max_tokens=60)
    if not result:
        return ""
    for name in voice_names:
        if name.lower() in result.lower():
            return name
    return ""


if __name__ == "__main__":
    sample = input("Scene text: ") or "A lone lighthouse keeper watches the storm roll in."
    print("\nEnhanced narotion:")
    print(enhance_narration(sample))
    print("\nPicked voice:", pick_voice(sample))