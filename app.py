"""
AuraCast: Flask application. Serves the UI and the podcast generation API.
Orchestrates parser, LLM, and TTS; no business logic here.
"""
import os
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory

import config

# Ensure upload and output directories exist
config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
config.OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH


def allowed_file(filename: str) -> bool:
    """Check if filename has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS


@app.route("/")
def index():
    """Serve the single-page UI."""
    return render_template("index.html")


@app.route("/api/generate-podcast", methods=["POST"])
def generate_podcast():
    """
    Placeholder for Phase 5: accept file, run pipeline, return script + audio URL.
    For Phase 1 we return a mock response so the frontend can drive state transitions.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Only PDF and EPUB files are allowed"}), 400

    # Phase 1: mock success so UI can show state flow
    return jsonify({
        "state": "ready",
        "script": [
            {"speaker": "Host A", "text": "Welcome to the book podcast. (Demo script.)"},
            {"speaker": "Host B", "text": "Thanks for having me. (Demo script.)"},
        ],
        "audio_url": None,
    })


@app.route("/output/<path:filename>")
def serve_output(filename):
    """Serve generated MP3 files from the output folder."""
    return send_from_directory(config.OUTPUT_FOLDER, filename, mimetype="audio/mpeg")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
