# Merlin Settings: Emulation Mode
import os
import json


def _optional_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


# API Connectivity
MERLIN_API_HOST = "0.0.0.0"
MERLIN_API_PORT = 8000

# LLM Backend Selection: "lmstudio", "ollama", "openai", "huggingface", "parallel", "adaptive"
LLM_BACKEND = os.getenv("LLM_BACKEND", "lmstudio")

# Parallel LLM Strategy: "voting", "routing", "cascade", "consensus", "auto"
PARALLEL_STRATEGY = os.getenv("PARALLEL_STRATEGY", "voting")

# Adaptive LLM Settings
LEARNING_MODE = os.getenv("LEARNING_MODE", "enabled")
MIN_LEARNING_SAMPLES = int(os.getenv("MIN_LEARNING_SAMPLES", "5"))

# LM Studio Configuration
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")

# Ollama Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODELS = json.loads(
    os.getenv("OLLAMA_MODELS", '["llama3.2", "mistral", "nomic", "glm4"]')
)
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "30"))

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_URL = os.getenv("OPENAI_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

# Nemotron 3 Configuration
NEMOTRON_API_KEY = os.getenv("NEMOTRON_API_KEY", "")
NEMOTRON_URL = os.getenv("NEMOTRON_URL", "http://localhost:8001/v1/chat/completions")
NEMOTRON_MODEL = os.getenv("NEMOTRON_MODEL", "nemotron-3")

# GLM Configuration
GLM_API_KEY = os.getenv("GLM_API_KEY", "")
GLM_URL = os.getenv("GLM_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-4")

# Nomic Configuration
NOMIC_URL = os.getenv("NOMIC_URL", "http://localhost:11434/api/chat")
NOMIC_MODEL = os.getenv("NOMIC_MODEL", "nomic-embed-text")

# HuggingFace Configuration
HF_API_KEY = os.getenv("HF_API_KEY", "")
HF_API_URL = os.getenv(
    "HF_API_URL",
    "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2",
)
HF_TIMEOUT = int(os.getenv("HF_TIMEOUT", "60"))

# Voice Configuration
MERLIN_VOICE_PRIMARY_ENGINE = os.getenv("MERLIN_VOICE_PRIMARY_ENGINE", "xtts")
MERLIN_VOICE_FALLBACK_ENGINE = os.getenv("MERLIN_VOICE_FALLBACK_ENGINE", "pyttsx3")
MERLIN_VOICE_XTTS_MODEL = os.getenv("MERLIN_VOICE_XTTS_MODEL", "")
MERLIN_VOICE_XTTS_DEVICE = os.getenv("MERLIN_VOICE_XTTS_DEVICE", "cuda")
MERLIN_VOICE_XTTS_LANGUAGE = os.getenv("MERLIN_VOICE_XTTS_LANGUAGE", "en")
MERLIN_VOICE_REFERENCE_WAV = os.getenv("MERLIN_VOICE_REFERENCE_WAV", "")
MERLIN_VOICE_PIPER_PATH = os.getenv("MERLIN_VOICE_PIPER_PATH", "piper")
MERLIN_VOICE_PIPER_MODEL = os.getenv("MERLIN_VOICE_PIPER_MODEL", "")
MERLIN_VOICE_PIPER_SPEAKER_ID = _optional_int(
    os.getenv("MERLIN_VOICE_PIPER_SPEAKER_ID")
)
MERLIN_VOICE_PIPER_LENGTH_SCALE = _optional_float(
    os.getenv("MERLIN_VOICE_PIPER_LENGTH_SCALE")
)
MERLIN_VOICE_PIPER_NOISE_SCALE = _optional_float(
    os.getenv("MERLIN_VOICE_PIPER_NOISE_SCALE")
)
MERLIN_VOICE_PIPER_NOISE_W = _optional_float(os.getenv("MERLIN_VOICE_PIPER_NOISE_W"))
MERLIN_VOICE_PLAYBACK = os.getenv("MERLIN_VOICE_PLAYBACK", "true").lower() == "true"
MERLIN_VOICE_PLAYBACK_COMMAND = os.getenv("MERLIN_VOICE_PLAYBACK_COMMAND", "")
MERLIN_VOICE_CACHE_DIR = os.getenv("MERLIN_VOICE_CACHE_DIR", "artifacts/voice")
MERLIN_VOICE_KEEP_TEMP_AUDIO = (
    os.getenv("MERLIN_VOICE_KEEP_TEMP_AUDIO", "false").lower() == "true"
)

# Speech-to-Text Configuration
MERLIN_STT_PRIMARY_ENGINE = os.getenv("MERLIN_STT_PRIMARY_ENGINE", "google")
MERLIN_STT_FALLBACK_ENGINE = os.getenv("MERLIN_STT_FALLBACK_ENGINE", "whisper")
MERLIN_STT_GOOGLE_LANGUAGE = os.getenv("MERLIN_STT_GOOGLE_LANGUAGE", "en-US")
MERLIN_STT_WHISPER_MODEL = os.getenv("MERLIN_STT_WHISPER_MODEL", "whisper-1")
MERLIN_STT_WHISPER_LANGUAGE = os.getenv("MERLIN_STT_WHISPER_LANGUAGE", "")
MERLIN_STT_WHISPER_BASE_URL = os.getenv(
    "MERLIN_STT_WHISPER_BASE_URL", "https://api.openai.com/v1"
)
MERLIN_STT_WHISPER_TIMEOUT_S = _optional_float(
    os.getenv("MERLIN_STT_WHISPER_TIMEOUT_S", "60")
)
MERLIN_STT_TIMEOUT_S = _optional_float(os.getenv("MERLIN_STT_TIMEOUT_S", "5"))
MERLIN_STT_PHRASE_TIME_LIMIT_S = _optional_float(
    os.getenv("MERLIN_STT_PHRASE_TIME_LIMIT_S", "12")
)
MERLIN_STT_DYNAMIC_ENERGY = (
    os.getenv("MERLIN_STT_DYNAMIC_ENERGY", "true").lower() == "true"
)
MERLIN_STT_ENERGY_THRESHOLD = _optional_int(os.getenv("MERLIN_STT_ENERGY_THRESHOLD"))

# Security
MERLIN_API_KEY = os.getenv("MERLIN_API_KEY", "merlin-secret-key")

# Path to Dev Library
DEV_LIBRARY_PATH = "D:/Dev library/AaroneousAutomationSuite"
