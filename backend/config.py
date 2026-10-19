import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    return env(name, "true" if default else "false").lower() in ("1", "true", "yes")


APP_NAME = env("APP_NAME", "Community Watch API")
BOT_NAME = env("BOT_NAME", "Community Watch")

_database_path = env("DATABASE_PATH", "community_watch.db")
if not os.path.isabs(_database_path):
    _database_path = str(BASE_DIR / _database_path)
DATABASE_PATH = _database_path

CORS_ALLOW_ALL = env_bool("CORS_ALLOW_ALL", True)
CORS_ORIGINS = [
    item.strip()
    for item in env(
        "CORS_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:8000",
    ).split(",")
    if item.strip()
]

WHATSAPP_VERIFY_TOKEN = env("WHATSAPP_VERIFY_TOKEN", "community-watch")
WHATSAPP_ACCESS_TOKEN = env("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_APP_SECRET = env("WHATSAPP_APP_SECRET")
GRAPH_VERSION = env("GRAPH_VERSION", "v21.0")

OPENROUTER_API_KEY = env("OPENROUTER_API_KEY")
OPENROUTER_MODEL = env("OPENROUTER_MODEL", "openrouter/auto")
OPENROUTER_BASE_URL = env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_TIMEOUT_SECONDS = env_int("OPENROUTER_TIMEOUT_SECONDS", 40)
AI_MAX_INPUT_CHARS = env_int("AI_MAX_INPUT_CHARS", 4000)
AI_SUMMARY_MAX_LENGTH = env_int("AI_SUMMARY_MAX_LENGTH", 300)

ELEVENLABS_API_KEY = env("ELEVENLABS_API_KEY")
ELEVENLABS_STT_MODEL = env("ELEVENLABS_STT_MODEL", "scribe_v2")
ELEVENLABS_BASE_URL = env("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io")
ELEVENLABS_TIMEOUT_SECONDS = env_int("ELEVENLABS_TIMEOUT_SECONDS", 60)
VOICE_MAX_BYTES = env_int("VOICE_MAX_BYTES", 25 * 1024 * 1024)
