import os

# Video API settings (NovAI - truly free cogvideox-flash, $0/generation)
# Get free key at: https://aiapi-pro.com
# NOTE: keys must be set via env vars (never hardcode/commit them)
#   VIDEO_API_KEYS   = comma-separated NovAI keys, rotated automatically when a
#                      key hits its free daily generation limit (e.g. "k1,k2,k3")
#   VIDEO_API_KEY    = single key (fallback for older setups)
VIDEO_API_KEY = os.getenv("VIDEO_API_KEY", "")
VIDEO_API_KEYS = os.getenv("VIDEO_API_KEYS", "")
VIDEO_API_BASE_URL = "https://aiapi-pro.com/v1"

# Free tier video generation quota (per key, resets at midnight UTC+8)
FREE_DAILY_VIDEO_LIMIT = 5
QUOTA_OFFSET_HOURS = 8  # UTC offset of the reset timezone

# Public base URL of this app - used to build absolute URLs for uploaded
# reference images so the video API can fetch them from the internet.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")

# Video generation settings
VIDEO_MODEL = "cogvideox-flash"  # $0/generation on NovAI
VIDEO_DURATION = 4  # seconds per clip (max 6)
ASPECT_RATIO = "16:9"

# TTS voice settings (edge-tts)
# Curated "human tune" neural voices exposed to users.
# Auto = smart voice picked per-scene by the narration engine.
CURATED_VOICES = [
    {"name": "en-US-ChristopherNeural", "label": "Christopher — Deep & dramatic"},
    {"name": "en-US-MichelleNeural", "label": "Michelle — Bright & lively"},
    {"name": "en-GB-RyanNeural", "label": "Ryan — British gentleman"},
    {"name": "en-GB-SoniaNeural", "label": "Sonia — Warm & storytelling"},
    {"name": "en-IN-PrabhatNeural", "label": "Prabhat — Calm & clear"},
]
TTS_VOICE = "en-US-ChristopherNeural"  # default used when Auto selection fails
TTS_RATE = "+0%"
TTS_VOLUME = "+0%"

# Smart narration settings (free GLM model on NovAI)
SMART_VOICEOVER = True
NARRATION_MODEL = "glm-4.6v-flash"
NARRATION_TIMEOUT = 20  # seconds per LLM call
NARRATION_MAX_TEXT = 600  # narration is capped so it fits inside a short clip

# Output settings
OUTPUT_DIR = "output"
CLIPS_DIR = os.path.join(OUTPUT_DIR, "clips")
AUDIO_DIR = os.path.join(OUTPUT_DIR, "audio")
FINAL_OUTPUT = os.path.join(OUTPUT_DIR, "final_video.mp4")

# Transition settings
CROSSFADE_DURATION = 0.5  # seconds

# API retry settings
MAX_RETRIES = 3
POLL_INTERVAL = 5  # seconds between status checks
MAX_POLL_TIME = 900  # max seconds to wait for a single clip (free tier queues are slow)
