"""
AuraCast: Flask application. Serves the UI and the podcast generation API.
Orchestrates parser, LLM, and TTS; no business logic here.
V2: chunk store for episode list; /api/parse returns upload_id + episodes without Gemini.
"""
import logging
import time
import traceback
import uuid
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory

import config
from parser import parse_ebook, parse_ebook_chunks, ParsingError
from llm_generator import (
    generate_podcast_script,
    generate_episode_script,
    generate_interrupt_reply,
    ScriptGenerationError,
)
from tts_engine import synthesize_podcast

# In-memory chunk store: upload_id -> {"chunks": list[dict], "ts": float}. Evict by TTL and max size.
_CHUNK_STORE = {}

# Ensure upload and output directories exist
config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
config.OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH


def allowed_file(filename: str) -> bool:
    """Check if filename has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS


def _chunk_store_evict():
    """Remove expired entries and trim to CHUNK_STORE_MAX_ENTRIES (oldest first)."""
    now = time.time()
    ttl = getattr(config, "CHUNK_STORE_TTL_SEC", 3600)
    max_entries = getattr(config, "CHUNK_STORE_MAX_ENTRIES", 20)
    expired = [uid for uid, data in _CHUNK_STORE.items() if (now - data["ts"]) > ttl]
    for uid in expired:
        del _CHUNK_STORE[uid]
    if len(_CHUNK_STORE) <= max_entries:
        return
    by_ts = sorted(_CHUNK_STORE.items(), key=lambda x: x[1]["ts"])
    for uid, _ in by_ts[: len(_CHUNK_STORE) - max_entries]:
        _CHUNK_STORE.pop(uid, None)


def _chunk_store_get(upload_id: str) -> list[dict] | None:
    """Return list of chunks for upload_id or None if missing/expired."""
    _chunk_store_evict()
    data = _CHUNK_STORE.get(upload_id)
    if not data:
        return None
    ttl = getattr(config, "CHUNK_STORE_TTL_SEC", 3600)
    if (time.time() - data["ts"]) > ttl:
        del _CHUNK_STORE[upload_id]
        return None
    return data["chunks"]


def _chunk_store_set(upload_id: str, chunks: list[dict]) -> None:
    """Store chunks for upload_id; refresh ts. Evicts if over capacity."""
    _chunk_store_evict()
    _CHUNK_STORE[upload_id] = {"chunks": chunks, "ts": time.time()}


@app.route("/")
def index():
    """Serve the single-page UI."""
    return render_template("index.html")


@app.route("/api/parse", methods=["POST"])
def api_parse():
    """
    Parse uploaded eBook into chunks. Store chunks server-side; return upload_id and episode list (id, title only).
    Does not call Gemini or TTS. File is kept for later episode generation.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Only PDF and EPUB files are allowed"}), 400

    upload_id = uuid.uuid4().hex
    ext = file.filename.rsplit(".", 1)[1].lower()
    upload_name = f"{upload_id}.{ext}"
    upload_path = config.UPLOAD_FOLDER / upload_name

    try:
        file.save(str(upload_path))
    except OSError:
        return jsonify({"error": "Failed to save upload."}), 500

    try:
        chunks = parse_ebook_chunks(str(upload_path), file.filename)
    except ParsingError as e:
        upload_path.unlink(missing_ok=True)
        return jsonify({"error": str(e)}), 400
    except Exception:
        upload_path.unlink(missing_ok=True)
        return jsonify({"error": "Failed to parse the file. Please try another PDF or EPUB."}), 500

    _chunk_store_set(upload_id, chunks)
    episodes = [{"id": c["id"], "title": c["title"]} for c in chunks]
    return jsonify({"upload_id": upload_id, "episodes": episodes})


# Hardcoded demo script (no Gemini) so users can always see/hear the app working.
DEMO_SCRIPT = [
    {"speaker": "Host A", "text": "Welcome to AuraCast! This is a quick demo so you can hear how we sound together."},
    {"speaker": "Host B", "text": "That's right. Once you upload a book and pick a chapter, we'll have real conversations about the content — powered by AI."},
    {"speaker": "Host A", "text": "This demo uses only text-to-speech, no API limits. So you can always click Try demo to see the app working."},
    {"speaker": "Host B", "text": "When you're ready, upload your eBook, parse it, then generate an episode. We'll be here!"},
]

@app.route("/api/demo_episode", methods=["POST"])
def api_demo_episode():
    """
    Generate a demo episode: fixed script + TTS only (no Gemini). So the app always has a working example.
    """
    out_name = f"{uuid.uuid4().hex}.mp3"
    out_path = config.OUTPUT_FOLDER / out_name
    try:
        synthesize_podcast(DEMO_SCRIPT, str(out_path))
    except Exception as e:
        out_path.unlink(missing_ok=True)
        return jsonify({"error": f"Audio synthesis failed: {e}. Check that ffmpeg is installed."}), 500
    return jsonify({"script": DEMO_SCRIPT, "audio_url": f"/output/{out_name}"})


@app.route("/api/generate_episode", methods=["POST"])
def api_generate_episode():
    """
    Generate one episode: lookup chunk by upload_id + episode_id, run Gemini + TTS, return script + audio_url.
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400
    data = request.get_json() or {}
    upload_id = data.get("upload_id")
    episode_id = data.get("episode_id")
    user_prompt = (data.get("user_prompt") or "").strip()
    if not upload_id:
        return jsonify({"error": "upload_id is required"}), 400
    try:
        episode_id = int(episode_id)
    except (TypeError, ValueError):
        return jsonify({"error": "episode_id must be an integer"}), 400

    chunks = _chunk_store_get(upload_id)
    if not chunks:
        return jsonify({"error": "Session expired or invalid. Please re-upload the book."}), 404
    chunk = next((c for c in chunks if c.get("id") == episode_id), None)
    if not chunk:
        return jsonify({"error": "Episode not found."}), 404

    try:
        script = generate_episode_script(chunk["text"], user_prompt)
    except ScriptGenerationError as e:
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        return jsonify({"error": "Failed to generate script. Please try again."}), 500

    out_name = f"{uuid.uuid4().hex}.mp3"
    out_path = config.OUTPUT_FOLDER / out_name
    try:
        synthesize_podcast(script, str(out_path))
    except Exception as e:
        out_path.unlink(missing_ok=True)
        return jsonify({"error": f"Audio synthesis failed: {e}. Check that ffmpeg is installed."}), 500

    return jsonify({"script": script, "audio_url": f"/output/{out_name}"})


@app.route("/api/ask_hosts", methods=["POST"])
def api_ask_hosts():
    """
    User interrupted the podcast with a question. Generate a short 2-line Host A/B reply, synthesize, return script + audio_url.
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400
    data = request.get_json() or {}
    question = (data.get("question") or "").strip()
    episode_script = data.get("episode_script")
    chunk_text = data.get("chunk_text")
    if not question:
        return jsonify({"error": "question is required"}), 400
    if not episode_script or not isinstance(episode_script, list):
        return jsonify({"error": "episode_script (array) is required"}), 400

    try:
        script = generate_interrupt_reply(
            question,
            episode_script,
            chunk_text=(chunk_text if chunk_text else None),
        )
    except ScriptGenerationError as e:
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        return jsonify({"error": "Failed to generate reply. Please try again."}), 500

    out_name = f"{uuid.uuid4().hex}.mp3"
    out_path = config.OUTPUT_FOLDER / out_name
    try:
        synthesize_podcast(script, str(out_path))
    except Exception as e:
        out_path.unlink(missing_ok=True)
        return jsonify({"error": f"Audio synthesis failed: {e}."}), 500

    return jsonify({"script": script, "audio_url": f"/output/{out_name}"})


@app.route("/api/generate-podcast", methods=["POST"])
def generate_podcast():
    """
    Run full pipeline: save upload → parse → Gemini script → TTS → return script + audio URL.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Only PDF and EPUB files are allowed"}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    upload_name = f"{uuid.uuid4().hex}.{ext}"
    upload_path = config.UPLOAD_FOLDER / upload_name

    try:
        file.save(str(upload_path))
    except OSError as e:
        return jsonify({"error": "Failed to save upload."}), 500

    try:
        # 1. Extract text from eBook
        extracted_text = parse_ebook(str(upload_path), file.filename)
    except ParsingError as e:
        upload_path.unlink(missing_ok=True)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        upload_path.unlink(missing_ok=True)
        return jsonify({"error": "Failed to parse the file. Please try another PDF or EPUB."}), 500

    try:
        # 2. Generate podcast script with Gemini
        script = generate_podcast_script(extracted_text)
    except ScriptGenerationError as e:
        upload_path.unlink(missing_ok=True)
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        upload_path.unlink(missing_ok=True)
        return jsonify({"error": "Failed to generate script. Please try again."}), 500

    out_name = f"{uuid.uuid4().hex}.mp3"
    out_path = config.OUTPUT_FOLDER / out_name

    try:
        # 3. Synthesize audio and merge to one MP3
        synthesize_podcast(script, str(out_path))
    except Exception as e:
        upload_path.unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)
        return jsonify({"error": f"Audio synthesis failed: {e}. Check that ffmpeg is installed."}), 500

    upload_path.unlink(missing_ok=True)
    return jsonify({
        "state": "ready",
        "script": script,
        "audio_url": f"/output/{out_name}",
    })


@app.route("/output/<path:filename>")
def serve_output(filename):
    """Serve generated MP3 files from the output folder."""
    return send_from_directory(config.OUTPUT_FOLDER, filename, mimetype="audio/mpeg")


# Theme backgrounds: served from static/images/ (deployed with app; supports .png, .jpg, .webp)
BG_NAMES = {"dark", "light", "dark_bg", "light_bg"}
BG_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
STATIC_IMAGES = Path(__file__).resolve().parent / "static" / "images"


@app.route("/bg/<name>")
def serve_bg(name):
    """Serve theme background from static/images/ so it works on Render (tries .png, .jpg, .webp)."""
    if name not in BG_NAMES:
        return "", 404
    for ext in BG_EXTENSIONS:
        path = STATIC_IMAGES / f"{name}{ext}"
        if path.is_file():
            return send_from_directory(STATIC_IMAGES, path.name)
    return "", 404


if __name__ == "__main__":
    # Use 5001 by default; macOS often reserves 5000 for AirPlay Receiver
    app.run(debug=True, port=5001)
