"""Project constants."""

APP_NAME = "MuseSplit"
APP_VERSION = "0.1.0"
STEM_NAMES = ["vocals", "drums", "bass", "other"]
SUPPORTED_AUDIO_EXTENSIONS = {
    ".wav",
    ".flac",
    ".mp3",
    ".m4a",
    ".ogg",
    ".aac",
}
DEFAULT_MODEL = "htdemucs_ft"
DEMUCS_MODEL_OPTIONS = [
    "htdemucs",
    "htdemucs_ft",
    "mdx",
    "mdx_extra",
    "mdx_extra_q",
    "mdx_q",
]
DEFAULT_EXPORT_FORMAT = "wav"
