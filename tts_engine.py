"""
Synthesize podcast audio from script using edge-tts; merge segments with ffmpeg.
No Flask imports. Requires ffmpeg for concatenating MP3s (avoids pydub/audioop on Python 3.13+).
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path

import edge_tts

# Voice mapping: Host A (female), Host B (male). Use en-US by default.
VOICE_HOST_A = "en-US-AriaNeural"
VOICE_HOST_B = "en-US-GuyNeural"


def _voice_for_speaker(speaker: str) -> str:
    """Return edge-tts voice id for Host A or Host B."""
    return VOICE_HOST_A if speaker.strip() == "Host A" else VOICE_HOST_B


async def _synthesize_segment(text: str, voice: str, path: str) -> None:
    """Generate one MP3 segment via edge-tts."""
    if not text or not text.strip():
        return
    communicate = edge_tts.Communicate(text.strip(), voice)
    await communicate.save(path)


def synthesize_podcast(script: list[dict], output_path: str) -> str:
    """
    Generate audio for each script line with edge-tts, then merge into one MP3.
    script: list of {"speaker": "Host A"|"Host B", "text": "..."}
    Returns output_path. Raises on failure (e.g. network, unsupported voice).
    """
    if not script:
        raise ValueError("Script is empty.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temp_dir = Path(tempfile.mkdtemp())
    temp_files = []

    async def run_all():
        for i, item in enumerate(script):
            speaker = item.get("speaker", "Host A")
            text = item.get("text", "")
            if not text:
                continue
            voice = _voice_for_speaker(speaker)
            segment_path = temp_dir / f"seg_{i:04d}.mp3"
            temp_files.append(segment_path)
            await _synthesize_segment(text, voice, str(segment_path))

    try:
        asyncio.run(run_all())
    except Exception as e:
        for f in temp_files:
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            temp_dir.rmdir()
        except OSError:
            pass
        raise RuntimeError(f"TTS failed: {e}") from e

    # Merge with ffmpeg concat (avoids pydub/audioop dependency)
    segments = sorted(temp_dir.glob("seg_*.mp3"))
    try:
        if segments:
            list_file = temp_dir / "concat.txt"
            list_file.write_text(
                "\n".join(f"file '{p.resolve()}'" for p in segments),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(list_file),
                    "-c", "copy",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
            )
    finally:
        for f in temp_files:
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            temp_dir.rmdir()
        except OSError:
            pass

    return str(output_path)
