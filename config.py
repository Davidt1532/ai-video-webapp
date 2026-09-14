import os

# Video API settings (NovAI - truly free cogvideox-flash, $0/generation)
# Get free key at: https://aiapi-pro.com
# NOTE: key must be set via VIDEO_API_KEY env var (never hardcode/commit it)
VIDEO_API_KEY = os.getenv("VIDEO_API_KEY", "")
VIDEO_API_BASE_URL = "https://aiapi-pro.com/v1"

# Video generation settings
VIDEO_MODEL = "cogvideox-flash"  # $0/generation on NovAI
VIDEO_DURATION = 4  # seconds per clip (max 6)
ASPECT_RATIO = "16:9"

# TTS voice settings (edge-tts)
TTS_VOICE = "en-US-GuyNeural"  # Options: en-US-GuyNeural, en-US-AvaNeural, en-GB-RyanNeural, en-IN-PrabhatNeural
TTS_RATE = "+0%"
TTS_VOLUME = "+0%"

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
