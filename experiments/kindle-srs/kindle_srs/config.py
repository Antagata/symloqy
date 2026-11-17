"""Configuration from environment variables.

Nothing is required at import time, so every module can be imported (and
unit-tested) without credentials. main.py calls require() before doing any work.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional outside local runs
    pass

# --- Anthropic ---
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")  # any vision-capable Claude model

# --- Readwise ---
READWISE_TOKEN: str = os.environ.get("READWISE_TOKEN", "")

# --- Google Drive ---
# For GitHub Actions: set GOOGLE_CREDENTIALS_JSON to the full JSON string
# For local dev: set GOOGLE_CREDENTIALS_FILE to path of service account JSON
GOOGLE_CREDENTIALS_JSON: str | None = os.environ.get("GOOGLE_CREDENTIALS_JSON")
GOOGLE_CREDENTIALS_FILE: str | None = os.environ.get("GOOGLE_CREDENTIALS_FILE", "assets/credentials.json")

DRIVE_PHOTOS_FOLDER: str = os.environ.get("DRIVE_PHOTOS_FOLDER", "KindleSRS/MyPhotos")
DRIVE_ROOT_FOLDER: str = os.environ.get("DRIVE_ROOT_FOLDER", "KindleSRS")
DB_FILENAME: str = "kindle_srs.db"

# --- Email ---
GMAIL_USER: str = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD: str = os.environ.get("GMAIL_APP_PASSWORD", "")
SEND_TO_EMAIL: str = os.environ.get("SEND_TO_EMAIL", "")

# --- Session ---
# The sessions table has two photo slots, so a session holds 1 or 2 photos.
PHOTOS_PER_SESSION: int = min(2, max(1, int(os.environ.get("PHOTOS_PER_SESSION", "2"))))
WORDS_PER_PHOTO: int = int(os.environ.get("WORDS_PER_PHOTO", "3"))
# How many candidate words to offer Claude per photo (Claude selects WORDS_PER_PHOTO from these)
CANDIDATE_POOL_SIZE: int = int(os.environ.get("CANDIDATE_POOL_SIZE", "25"))

TIMEZONE: str = os.environ.get("TIMEZONE", "UTC")

SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY: str = os.environ.get("SUPABASE_SERVICE_KEY", "")

REQUIRED = (
    "ANTHROPIC_API_KEY", "READWISE_TOKEN", "GMAIL_USER", "GMAIL_APP_PASSWORD",
    "SEND_TO_EMAIL", "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
)


def require(names=REQUIRED) -> None:
    """Fail fast, with one clear message listing every missing variable."""
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise RuntimeError("Missing environment variables: " + ", ".join(missing)
                           + ". Copy .env.example to .env and fill them in.")
