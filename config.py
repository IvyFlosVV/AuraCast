"""
Configuration for AuraCast. Loads settings from environment; no secrets in code.
"""
import os
from pathlib import Path

# Load .env so GEMINI_API_KEY is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Base directory (project root)
BASE_DIR = Path(__file__).resolve().parent

# API key from environment only
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Upload and output paths
UPLOAD_FOLDER = BASE_DIR / "uploads"
OUTPUT_FOLDER = BASE_DIR / "output"

# Max upload size (e.g. 50 MB)
MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 50 * 1024 * 1024))

# Allowed extensions for eBooks
ALLOWED_EXTENSIONS = {"pdf", "epub"}

# Max extracted text length (parser); further cap before sending to API
MAX_TEXT_LENGTH = int(os.environ.get("MAX_TEXT_LENGTH", 300_000))
# Max characters per chunk (for episode generation). Defaults to GEMINI_MAX_INPUT_CHARS.
GEMINI_MAX_INPUT_CHARS = int(os.environ.get("GEMINI_MAX_INPUT_CHARS", 30_000))
MAX_CHUNK_CHARS = int(os.environ.get("MAX_CHUNK_CHARS", GEMINI_MAX_INPUT_CHARS))
# PDF chunking: pages per chunk when parsing to episodes
PDF_CHUNK_PAGES = int(os.environ.get("PDF_CHUNK_PAGES", 8))
# Chunk store (in-memory): TTL in seconds and max number of uploads
CHUNK_STORE_TTL_SEC = int(os.environ.get("CHUNK_STORE_TTL_SEC", 3600))
CHUNK_STORE_MAX_ENTRIES = int(os.environ.get("CHUNK_STORE_MAX_ENTRIES", 20))

# Gemini model and generation settings
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", 120))
# Seconds to wait before retrying after a rate-limit (free tier: 30–60 often helps)
RETRY_DELAY_SEC = int(os.environ.get("RETRY_DELAY_SEC", 30))
