"""
Configuration for AuraCast. Loads settings from environment; no secrets in code.
"""
import os
from pathlib import Path

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

# Max extracted text length to send to Gemini (avoid context overflow)
MAX_TEXT_LENGTH = int(os.environ.get("MAX_TEXT_LENGTH", 300_000))

# Gemini model and generation settings
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", 120))
